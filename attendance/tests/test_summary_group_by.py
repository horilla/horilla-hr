"""Group By on the monthly summary: nested levels, totals per group, paging by group."""

import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from attendance.views.summary import build_group_items, parse_group_fields
from horilla.testkit import make_company, make_employee, make_user


class FakeDept:
    def __init__(self, department):
        self.department = department


class FakeInfo:
    def __init__(self, department=None, job_position=None):
        self.department_id = FakeDept(department) if department else None
        self.job_position_id = (
            type("J", (), {"job_position": job_position})() if job_position else None
        )
        self.shift_id = self.work_type_id = self.company_id = (
            self.reporting_manager_id
        ) = None


class FakeEmployee:
    def __init__(self, name, department=None, job_position=None):
        self.name = name
        self.employee_work_info = FakeInfo(department, job_position)


def row(name, department=None, job_position=None, present=1, absent=0, worked=3600):
    return {
        "employee": FakeEmployee(name, department, job_position),
        "present": present,
        "absent": absent,
        "paid_leave": 0,
        "unpaid_leave": 0,
        "week_off": 0,
        "holiday": 0,
        "conflict_days": 0,
        "resolved_conflicts": 0,
        "worked_seconds": worked,
        "regular_seconds": worked,
        "overtime_seconds": 0,
    }


class ParseTests(SimpleTestCase):
    def test_only_known_levels_once_and_at_most_three(self):
        self.assertEqual(
            parse_group_fields(
                [
                    "department",
                    "",
                    "bogus",
                    "department",
                    "shift",
                    "work_type",
                    "company",
                ]
            ),
            ["department", "shift", "work_type"],
        )

    def test_nothing_chosen_is_no_grouping(self):
        self.assertEqual(parse_group_fields(["", ""]), [])


class TreeTests(SimpleTestCase):
    def setUp(self):
        self.rows = [
            row("a", "Sales", "Rep", present=10, absent=1),
            row("b", "Sales", "Manager", present=8, absent=3),
            row("c", "Engineering", "Dev", present=9, absent=2),
            row("d", None, None, present=5, absent=0),
        ]

    def test_one_level_groups_with_totals_and_the_unset_bucket_last(self):
        top, flatten = build_group_items(self.rows, ["department"])
        self.assertEqual([n["label"] for n in top], ["Engineering", "Sales", "Not Set"])
        sales = top[1]
        self.assertEqual(
            (sales["count"], sales["totals"]["present"], sales["totals"]["absent"]),
            (2, 18, 4),
        )
        self.assertTrue(top[2]["is_unset"])

    def test_two_levels_nest_and_the_parent_total_is_the_sum_of_its_children(self):
        top, flatten = build_group_items(self.rows, ["department", "job_position"])
        sales = next(n for n in top if n["label"] == "Sales")
        self.assertEqual([c["label"] for c in sales["children"]], ["Manager", "Rep"])
        self.assertEqual(
            sum(c["totals"]["present"] for c in sales["children"]),
            sales["totals"]["present"],
        )

    def test_flattening_orders_groups_before_their_rows_and_records_ancestors(self):
        top, flatten = build_group_items(self.rows, ["department", "job_position"])
        items = flatten([n for n in top if n["label"] == "Sales"])
        kinds = [(i["kind"], i["depth"]) for i in items]
        self.assertEqual(
            kinds, [("group", 0), ("group", 1), ("row", 2), ("group", 1), ("row", 2)]
        )
        self.assertEqual(items[0]["anc"], "")
        self.assertEqual(items[1]["anc"], items[0]["gid"])
        self.assertEqual(items[2]["anc"], f'{items[0]["gid"]} {items[1]["gid"]}')

    def test_every_employee_appears_once(self):
        top, flatten = build_group_items(self.rows, ["department", "job_position"])
        names = [i["row"]["employee"].name for i in flatten(top) if i["kind"] == "row"]
        self.assertEqual(sorted(names), ["a", "b", "c", "d"])


class GroupedPageTests(TestCase):
    def setUp(self):
        self.company = make_company("Group Co")
        self.employees = [
            make_employee(company=self.company, email=f"g{i}@test.horilla")
            for i in range(3)
        ]
        user = make_user("hr-group", is_superuser=True)
        make_employee(company=self.company, email="hr@group.test", user=user)
        self.client.force_login(user)

    def _table(self, **params):
        day = datetime.date(2026, 9, 2).isoformat()
        query = {"from_date": day, "to_date": day, **params}
        return self.client.get(
            reverse("attendance-monthly-summary-table"), query, HTTP_HX_REQUEST="true"
        )

    def test_without_grouping_the_table_is_unchanged(self):
        html = self._table().content.decode()
        self.assertNotIn('<tr class="ms-group-row"', html)
        self.assertNotIn('id="ngbBreadcrumbLevels"', html)
        self.assertEqual(html.count('<tr class="ms-summary-row"'), 4)

    def test_grouped_by_department_has_group_rows_and_hidden_employee_rows(self):
        html = self._table(nested_fields="department").content.decode()
        self.assertIn('<tr class="ms-group-row"', html)
        # The Employee directory's "Grouped by" bar, with Expand / Collapse All.
        self.assertIn('id="ngbBreadcrumbLevels"', html)
        self.assertIn("Grouped by", html)
        self.assertIn('id="ms-groups-expand"', html)
        self.assertIn('id="ms-groups-collapse"', html)
        self.assertIn('class="ms-group-tag"', html)
        # Employee rows start closed, each pointing at its group.
        self.assertIn('data-anc="g0" data-depth="1" style="display:none"', html)

    def test_the_picker_opens_on_the_chosen_levels(self):
        response = self.client.get(
            reverse("attendance-monthly-summary"),
            {"nested_fields": ["department", "shift"]},
        )
        html = response.content.decode()
        self.assertIn('<option value="department" selected>', html)
        self.assertIn('<option value="shift" selected>', html)
        # One numbered row per chosen level, as in the Employee directory.
        self.assertEqual(
            html.count('class="flex items-center gap-1.5 nested-group-by-row"'), 2
        )
        self.assertIn('id="nestedGroupByLevels"', html)
        self.assertIn('data-max-levels="3"', html)
        self.assertIn("ngbAddLevel", html)

    def test_with_nothing_chosen_the_picker_has_one_empty_level(self):
        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertEqual(
            html.count('class="flex items-center gap-1.5 nested-group-by-row"'), 1
        )

    def test_the_bar_numbers_each_level_and_blocks_a_field_already_used(self):
        html = self._table(nested_fields=["department", "shift"]).content.decode()
        self.assertEqual(html.count('class="ngb-crumb-row"'), 2)
        self.assertIn('<span class="ngb-crumb-badge">2</span>', html)
        # Shift is already level two, so the first level's list cannot offer it again.
        first_list = html.split('class="ngb-crumb-row"')[1].split(
            'class="ngb-crumb-row"'
        )[0]
        self.assertRegex(
            first_list,
            r'data-value="shift"\s+onclick="ngbCrumbPick\(this\)"\s+disabled',
        )

    def test_the_panel_section_comes_after_advanced(self):
        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertLess(html.index("Advanced"), html.index('id="nestedGroupByLevels"'))

    def test_a_group_is_one_header_across_the_table_with_no_figures(self):
        html = self._table(nested_fields="department").content.decode()
        row = html.split('<tr class="ms-group-row"')[1].split("</tr>")[0]
        self.assertEqual(row.count("<td"), 1)
        self.assertIn('colspan="15"', row)
        self.assertIn('class="ms-group-tag"', row)
        self.assertNotIn("ms-group-nil", row)
