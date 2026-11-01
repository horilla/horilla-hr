"""
``?page_size=`` is honoured, and bounded.

Every list view instantiates its paginator by hand, and each used a stock
PageNumberPagination -- which has no ``page_size_query_param``. So the
parameter Swagger advertised was silently ignored and every page was 20 rows.
A mobile client wanting one screenful of a directory had to make three round
trips for it.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

EMPLOYEE_LIST_URL = "/api/v1/employee/list/employees/"


class PageSizeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Paging Co")

        self.user = make_user("paging_user")
        make_employee(
            company=self.company,
            email="paging@test.horilla",
            first_name="Pat",
            user=self.user,
        )
        self.user.user_permissions.add(Permission.objects.get(codename="view_employee"))
        # Enough rows to see more than one default page.
        for i in range(29):
            make_employee(
                company=self.company,
                email=f"paging{i}@test.horilla",
                first_name=f"Person{i}",
            )
        self.client.force_authenticate(user=self.user)

    def test_default_page_size_is_unchanged(self):
        """Additive change: callers that send nothing see what they always saw."""
        response = self.client.get(EMPLOYEE_LIST_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data["results"]), 20)

    def test_page_size_is_honoured(self):
        # 30 is deliberately past the old fixed 20.
        for size in (5, 30):
            with self.subTest(page_size=size):
                response = self.client.get(EMPLOYEE_LIST_URL, {"page_size": size})
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(len(response.data["results"]), size)

    def test_page_size_is_capped(self):
        """Not a way to ask the server to serialize a whole table.

        The cap is 100 and the fixture holds 30 rows, so asking for a huge page
        would pass with the cap removed. Add enough rows to go past it, then
        check the server returns exactly the cap.
        """
        for i in range(80):
            make_employee(
                company=self.company,
                email=f"paging_extra{i}@test.horilla",
                first_name=f"Extra{i}",
            )
        response = self.client.get(EMPLOYEE_LIST_URL, {"page_size": 100000})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 110)
        self.assertEqual(len(response.data["results"]), 100)
