"""
The Allowances and Deductions pages actually showing their components.

Both pages render a nav above an empty container and nothing else fetches into
it, so the nav has to do the first fetch itself. Two separate things were
stopping that, and each failed silently — an empty list looks exactly like
"no components exist yet":

* `apply_first_filter` left at its default of True tells the nav that whoever
  embedded it has already fetched the content. Nobody had, so the container
  stayed empty until an unrelated save or filter triggered a reload.
* The standalone Deductions page called its container `#listContainer` while
  the nav swapped into `#deductionListContainer`, so search and filter results
  went to an element that did not exist on that page.

These check the pages end to end rather than reading the attributes back,
because the second bug is precisely a case where each half was individually
reasonable and only the pairing was wrong.
"""

import re

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.cbv.allowances import AllowanceNavView
from payroll.cbv.deduction import DeductionNav
from payroll.models.models import Allowance, Deduction

# (page url name, nav url name, nav class), for the standalone pages and for
# the payroll-settings tabs that embed the same navs.
PAGES = [
    ("view-allowance", "allowances-nav-view", AllowanceNavView),
    ("view-deduction", "deduction-view-nav", DeductionNav),
    ("payroll-settings-allowance-tab", "allowances-nav-view", AllowanceNavView),
    ("payroll-settings-deduction-tab", "deduction-view-nav", DeductionNav),
]


class ComponentListPageTests(TestCase):
    def setUp(self):
        user = make_user("listadmin", is_superuser=True)
        company = make_company("List Co")
        make_employee(company=company, email="listadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        Allowance.objects.create(title="Pinned Allowance", is_fixed=True, amount=100.0)
        Deduction.objects.create(title="Pinned Deduction", is_fixed=True, amount=50.0)

    def _page(self, name):
        response = self.client.get(reverse(name), **self.hx)
        self.assertEqual(response.status_code, 200, name)
        return response.content.decode()

    def test_every_page_contains_the_element_its_nav_swaps_into(self):
        """
        The bug this catches: a nav aiming at an id no page on screen has. The
        swap then hits nothing and the list silently never changes.
        """
        for page_name, _nav_name, nav_class in PAGES:
            with self.subTest(page=page_name):
                target = nav_class.search_swap_target.lstrip("#")
                self.assertIn(
                    f'id="{target}"',
                    self._page(page_name),
                    f"{page_name} has no #{target} for its nav to swap into",
                )

    def test_every_nav_fetches_the_list_itself(self):
        """
        Neither page fetches its own container, so the nav must. With
        apply_first_filter True the nav's script only adopts the active view's
        URL; the click that actually fetches is in the other branch.
        """
        for _page_name, nav_name, nav_class in PAGES:
            with self.subTest(nav=nav_name):
                self.assertFalse(
                    nav_class.apply_first_filter,
                    f"{nav_class.__name__} would leave the first fetch to the page",
                )
                body = self.client.get(reverse(nav_name), **self.hx).content.decode()
                self.assertIn("$activeViewBtn.click()", body)

    def test_the_list_the_nav_fetches_has_the_components_in_it(self):
        """
        The other half: the nav firing at an endpoint that returns nothing
        would look identical from the page's side.
        """
        for url_name, title in (
            ("allowances-list-view", "Pinned Allowance"),
            ("deduction-view-list", "Pinned Deduction"),
        ):
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name), **self.hx)
                self.assertEqual(response.status_code, 200)
                self.assertIn(title, response.content.decode())

    def test_two_navs_on_one_page_do_not_share_a_container(self):
        """
        The payroll-settings tabs all live in one document once visited. Two
        tabs sharing a container id would mean one tab's search rewriting the
        other's list.
        """
        targets = [
            nav_class.search_swap_target
            for page, _nav, nav_class in PAGES
            if page.startswith("payroll-settings")
        ]
        self.assertEqual(len(targets), len(set(targets)))

    def test_the_page_script_watches_the_container_the_page_has(self):
        """
        Renaming a container without following the page's own JS would leave
        the nav hidden or shown at the wrong times.
        """
        for page_name, _nav_name, nav_class in PAGES:
            with self.subTest(page=page_name):
                target = nav_class.search_swap_target.lstrip("#")
                body = self._page(page_name)
                # Any container id the page's script mentions must be one the
                # page actually renders.
                for mentioned in set(re.findall(r'"(#?\w*[lL]istContainer)"', body)):
                    self.assertEqual(
                        mentioned.lstrip("#"),
                        target,
                        f"{page_name} script mentions {mentioned}, not #{target}",
                    )
