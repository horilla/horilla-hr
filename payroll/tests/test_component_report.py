"""The allowance and deduction report: what each component paid or took over a period, read from the payslips."""

import csv
import json
from datetime import date
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from horilla.testkit import make_company, make_employee, make_user
from payroll.methods import component_report
from payroll.methods.component_report import ALLOWANCE, DEDUCTION
from payroll.methods.methods import payslip_fields, save_payslip
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, Payslip
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 4, 1)
END = date(2026, 4, 30)
NO_LEAVE = {
    "paid_leave": 0,
    "unpaid_leaves": 0,
    "partial_pay_days": 0,
    "total_leaves": 0,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}
HX = {"HTTP_HX_REQUEST": "true"}
VIEWS = "payroll.views.component_report_views"


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("reportadmin", is_superuser=True)
        self.company = make_company("Report Co")
        make_employee(
            company=self.company, email="reportadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.people = []
        for name in ("Ann", "Ben"):
            employee = make_employee(
                company=self.company,
                email=f"{name.lower()}@report.horilla",
                first_name=name,
            )
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(employee, wage=30000.0)
            self.people.append(employee)

        self.allowance = Allowance.objects.create(
            title="Travel Pay",
            is_fixed=True,
            amount=1000.0,
            include_active_employees=True,
            maximum_unit="full_period",
        )
        self.deduction = Deduction.objects.create(
            title="Provident Fund",
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            employer_rate=12.0,
            include_active_employees=True,
            is_pretax=True,
        )

    def generate(self):
        with patch("payroll.methods.methods.get_leaves", return_value=NO_LEAVE):
            for employee in self.people:
                save_payslip(
                    **payslip_fields(
                        payroll_calculation(employee, START, END),
                        employee,
                        status="draft",
                    )
                )
        return Payslip.objects.all()


class SummariseTests(Fixture):
    def test_an_allowance_is_totalled_over_the_payslips(self):
        rows, totals = component_report.summarise(self.generate(), ALLOWANCE)
        row = next(r for r in rows if r["title"] == "Travel Pay")
        self.assertEqual((row["employees"], row["payslips"]), (2, 2))
        self.assertAlmostEqual(row["total"], 2000.0, places=2)
        self.assertAlmostEqual(row["average"], 1000.0, places=2)
        self.assertAlmostEqual(totals["total"], sum(r["total"] for r in rows), places=2)

    def test_a_deduction_carries_the_employer_share(self):
        rows, totals = component_report.summarise(self.generate(), DEDUCTION)
        row = next(r for r in rows if r["title"] == "Provident Fund")
        self.assertGreater(row["total"], 0)
        self.assertAlmostEqual(row["employer_total"], row["total"], places=2)
        self.assertAlmostEqual(
            totals["employer_total"], sum(r["employer_total"] for r in rows), places=2
        )

    def test_a_line_added_by_hand_is_grouped_by_title_and_cannot_be_opened(self):
        payslips = list(self.generate())
        payslips[0].pay_head_data["allowances"].append(
            {"title": "Spot Award", "amount": 500.0, "custom_id": "x1"}
        )
        rows, _totals = component_report.summarise(payslips, ALLOWANCE)
        row = next(r for r in rows if r["title"] == "Spot Award")
        self.assertTrue(row["by_hand"])
        self.assertIsNone(row["id"])
        self.assertAlmostEqual(row["total"], 500.0, places=2)

    def test_the_rows_are_largest_first(self):
        rows, _totals = component_report.summarise(self.generate(), ALLOWANCE)
        self.assertEqual(
            [r["total"] for r in rows], sorted((r["total"] for r in rows), reverse=True)
        )
        self.assertNotIn("share", rows[0])

    def test_the_breakdown_lists_each_payslip_of_the_component(self):
        lines = component_report.breakdown(
            self.generate(), ALLOWANCE, self.allowance.pk
        )
        self.assertEqual(
            sorted(str(line["employee"]) for line in lines),
            sorted(str(p) for p in self.people),
        )
        self.assertAlmostEqual(sum(line["amount"] for line in lines), 2000.0, places=2)


class ViewTests(Fixture):
    def get(self, name, *args, **params):
        return self.client.get(
            reverse(name, args=args),
            {"from_date": "2026-04-01", "to_date": "2026-04-30", **params},
        )

    def test_the_page_shows_allowances_by_default(self):
        self.generate()
        html = self.get("payroll-component-report").content.decode()
        for text in (
            "Allowance Report",
            "Travel Pay",
            "Total Paid",
            "Read From The Payslips",
        ):
            self.assertIn(text, html)

    def test_the_deductions_page_shows_the_employer_share(self):
        self.generate()
        html = self.get("payroll-component-report", kind="deduction").content.decode()
        for text in (
            "Deduction Report",
            "Provident Fund",
            "Employee Share",
            "Employer Share",
            "Combined Total",
        ):
            self.assertIn(text, html)

    def test_with_no_dates_it_opens_on_the_latest_payslips_not_an_empty_period(self):
        """Nothing is paid in the current pay period yet, so the page shows the period that was last paid."""
        self.generate()
        response = self.client.get(reverse("payroll-component-report"))
        self.assertEqual(
            (response.context["period_start"], response.context["period_end"]),
            (START, END),
        )
        self.assertIn("Travel Pay", response.content.decode())

    def test_dates_that_were_asked_for_are_respected_and_point_to_the_latest_payslips(
        self,
    ):
        self.generate()
        response = self.get(
            "payroll-component-report", from_date="2026-01-01", to_date="2026-01-31"
        )
        self.assertEqual(response.context["rows"], [])
        self.assertEqual(response.context["latest_period"], (START, END))
        self.assertIn("Show The Latest Payslips", response.content.decode())

    def test_an_unknown_kind_falls_back_to_allowances(self):
        self.assertEqual(
            self.get("payroll-component-report", kind="bogus").context["kind"],
            ALLOWANCE,
        )

    def test_the_detail_page_lists_the_employees_behind_the_total(self):
        self.generate()
        response = self.get(
            "payroll-component-report-detail", ALLOWANCE, self.allowance.pk
        )
        self.assertEqual(len(response.context["lines"]), 2)
        self.assertAlmostEqual(response.context["totals"]["amount"], 2000.0, places=2)

    def test_the_detail_page_refuses_an_unknown_kind(self):
        self.assertEqual(
            self.get("payroll-component-report-detail", "bogus", 1).status_code, 404
        )

    def test_someone_without_payslip_access_is_refused(self):
        plain = make_user("plainreport")
        make_employee(
            company=self.company, email="plainreport@test.horilla", user=plain
        )
        self.client.force_login(plain)
        response = self.get("payroll-component-report")
        self.assertNotEqual(response.status_code, 200)


class ExportTests(Fixture):
    """The export is the standard one: the columns and the format are picked, and the file holds the page's table."""

    def post(self, params=None, **data):
        query = urlencode({"range": "all", **(params or {})}, doseq=True)
        return self.client.post(
            reverse("payroll-component-report-export") + "?" + query, data
        )

    @staticmethod
    def columns(*pairs):
        return json.dumps([list(pair) for pair in pairs])

    def csv_rows(self, response):
        rows = list(csv.reader(response.content.decode().splitlines()))
        start = next(
            i
            for i, row in enumerate(rows)
            if row and row[0] in ("Component", "Employee")
        )
        return rows[start], rows[start + 1 :]

    def test_the_picked_columns_and_only_those_are_exported(self):
        self.generate()
        response = self.post(
            format="csv",
            scope="summary",
            columns=self.columns(("Component", "title"), ("Total", "total")),
        )
        header, rows = self.csv_rows(response)
        self.assertEqual(header, ["Component", "Total"])
        self.assertIn("Travel Pay", [row[0] for row in rows])
        self.assertTrue(all(len(row) == 2 for row in rows))

    def test_the_file_has_the_standard_letterhead_lines(self):
        self.generate()
        response = self.post(
            format="csv",
            scope="summary",
            export_file_name="Pay Report",
            columns=self.columns(("Component", "title")),
        )
        lines = response.content.decode().splitlines()
        self.assertEqual(lines[1], "Pay Report")
        self.assertEqual(lines[2], "All Time")
        self.assertIn(
            'attachment; filename="Pay Report.csv"', response["Content-Disposition"]
        )

    def test_the_default_file_name_is_the_report_title(self):
        self.generate()
        response = self.post(
            format="csv", scope="summary", columns=self.columns(("Component", "title"))
        )
        self.assertIn(
            'filename="Allowance Report.csv"', response["Content-Disposition"]
        )

    def test_excel_is_a_workbook_with_the_picked_headers_and_figures(self):
        self.generate()
        response = self.post(
            format="xlsx",
            scope="summary",
            columns=self.columns(("Component", "title"), ("Total", "total")),
        )
        self.assertIn("spreadsheetml", response["Content-Type"])
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(
            [sheet.cell(row=5, column=c).value for c in (1, 2)], ["Component", "Total"]
        )
        found = {
            sheet.cell(row=r, column=1).value: sheet.cell(row=r, column=2).value
            for r in range(6, sheet.max_row + 1)
        }
        self.assertAlmostEqual(float(found["Travel Pay"]), 2000.0, places=2)

    def test_pdf_is_a_pdf(self):
        self.generate()
        response = self.post(
            format="pdf",
            scope="summary",
            columns=self.columns(("Component", "title"), ("Total", "total")),
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_an_unknown_column_is_ignored_and_no_column_is_refused(self):
        self.generate()
        response = self.post(
            format="csv",
            scope="summary",
            columns=self.columns(
                ("Component", "title"), ("Password", "employee_user_id__password")
            ),
        )
        self.assertEqual(self.csv_rows(response)[0], ["Component"])
        refused = self.post(
            format="csv", scope="summary", columns=self.columns(("Nope", "nope"))
        )
        self.assertEqual(refused.status_code, 400)

    def test_an_unknown_format_falls_back_to_excel(self):
        self.generate()
        response = self.post(
            format="exe", scope="summary", columns=self.columns(("Component", "title"))
        )
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_the_export_follows_the_search_and_filters_in_the_query(self):
        self.generate()
        response = self.post(
            {"search": "travel"},
            format="csv",
            scope="summary",
            columns=self.columns(("Component", "title")),
        )
        self.assertEqual([row[0] for row in self.csv_rows(response)[1]], ["Travel Pay"])
        narrowed = self.post(
            {"name_or_badge": "Ann"},
            format="csv",
            scope="detail",
            component_id=self.allowance.pk,
            columns=self.columns(("Employee", "name")),
        )
        self.assertEqual(len(self.csv_rows(narrowed)[1]), 1)

    def test_a_component_page_exports_its_employee_lines(self):
        self.generate()
        response = self.post(
            format="csv",
            scope="detail",
            component_id=self.allowance.pk,
            columns=self.columns(
                ("Employee", "name"), ("Badge ID", "badge_id"), ("Amount", "amount")
            ),
        )
        header, rows = self.csv_rows(response)
        self.assertEqual(header, ["Employee", "Badge ID", "Amount"])
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(sum(float(row[2]) for row in rows), 2000.0, places=2)

    def test_a_shared_deduction_exports_both_shares_and_the_combined_total(self):
        self.generate()
        response = self.post(
            {"kind": "deduction"},
            format="csv",
            scope="summary",
            columns=self.columns(
                ("Component", "title"),
                ("Employee Share", "total"),
                ("Employer Share", "employer_total"),
                ("Combined Total", "combined"),
            ),
        )
        header, rows = self.csv_rows(response)
        row = next(r for r in rows if r[0] == "Provident Fund")
        self.assertEqual(
            header, ["Component", "Employee Share", "Employer Share", "Combined Total"]
        )
        self.assertAlmostEqual(float(row[3]), float(row[1]) + float(row[2]), places=2)

    def test_the_picker_offers_the_table_columns_and_the_standard_formats(self):
        self.generate()
        html = self.client.get(
            reverse("payroll-component-report"), {"range": "all"}
        ).content.decode()
        for text in (
            "componentReportExportModal",
            "Select All",
            "File name",
            "Excel (.xlsx)",
            "CSV (.csv)",
            "PDF (.pdf)",
            'data-label="Component"',
            'data-label="Total"',
        ):
            self.assertIn(text, html)

    def test_the_export_only_accepts_a_post(self):
        self.assertEqual(
            self.client.get(reverse("payroll-component-report-export")).status_code, 405
        )


class QuickFilterTests(Fixture):
    """The quick date filters, the search and the nav, with today fixed so the ranges are known."""

    def get(self, name="payroll-component-report", *args, **params):
        with patch(f"{VIEWS}._today", return_value=date(2026, 5, 15)):
            return self.client.get(reverse(name, args=args), params)

    def test_all_time_has_no_date_bounds_and_includes_every_payslip(self):
        self.generate()
        response = self.get(range="all")
        self.assertEqual(
            (response.context["period_start"], response.context["period_end"]),
            (None, None),
        )
        self.assertIn("Travel Pay", response.content.decode())
        self.assertIn("Across All Time", response.content.decode())

    def test_previous_month_is_the_whole_month_before_today(self):
        self.generate()
        response = self.get(range="previous_month")
        self.assertEqual(
            (response.context["period_start"], response.context["period_end"]),
            (date(2026, 4, 1), date(2026, 4, 30)),
        )
        self.assertIn("Travel Pay", response.content.decode())

    def test_this_month_is_the_month_of_today_and_has_nothing_to_show_here(self):
        self.generate()
        response = self.get(range="this_month")
        self.assertEqual(
            (response.context["period_start"], response.context["period_end"]),
            (date(2026, 5, 1), date(2026, 5, 31)),
        )
        self.assertEqual(response.context["rows"], [])

    def test_last_three_months_and_this_year_span_what_they_say(self):
        self.assertEqual(
            [
                self.get(range="last_3_months").context[k]
                for k in ("period_start", "period_end")
            ],
            [date(2026, 3, 1), date(2026, 5, 31)],
        )
        self.assertEqual(
            [
                self.get(range="this_year").context[k]
                for k in ("period_start", "period_end")
            ],
            [date(2026, 1, 1), date(2026, 12, 31)],
        )

    def test_latest_payslips_is_the_period_of_the_last_payslip(self):
        self.generate()
        response = self.get(range="latest")
        self.assertEqual(
            (response.context["period_start"], response.context["period_end"]),
            (START, END),
        )

    def test_the_page_opens_on_the_latest_payslips_and_offers_no_pay_period_filter(
        self,
    ):
        self.generate()
        for params in ({}, {"range": "pay_period"}):
            with self.subTest(params=params):
                response = self.get(**params)
                self.assertEqual(response.context["range"], "latest")
                self.assertEqual(
                    (response.context["period_start"], response.context["period_end"]),
                    (START, END),
                )
                self.assertNotIn("Pay Period", response.content.decode())

    def test_typed_dates_are_a_custom_range(self):
        self.generate()
        response = self.get(from_date="2026-04-01", to_date="2026-04-30")
        self.assertEqual(response.context["range"], "custom")
        self.assertIn("Travel Pay", response.content.decode())

    def test_the_search_keeps_components_by_title_or_code(self):
        self.generate()
        kept = self.get(range="all", search="travel")
        self.assertEqual([row["title"] for row in kept.context["rows"]], ["Travel Pay"])
        self.assertEqual(self.get(range="all", search="zzz").context["rows"], [])
        self.assertEqual(
            self.get(range="all", search="zzz").context["totals"]["total"], 0
        )

    def test_the_search_on_the_detail_page_keeps_the_employees_it_matches(self):
        self.generate()
        response = self.get(
            "payroll-component-report-detail",
            ALLOWANCE,
            self.allowance.pk,
            range="all",
            search="Ann",
        )
        self.assertEqual(
            [str(line["employee"]) for line in response.context["lines"]],
            [str(self.people[0])],
        )

    def test_a_quick_filter_link_keeps_the_search_and_status(self):
        self.generate()
        html = self.get(range="all", search="travel", status="draft").content.decode()
        self.assertRegex(
            html,
            r'href="\?[^"]*search=travel[^"]*status=draft[^"]*&range=previous_month"|href="\?[^"]*status=draft[^"]*search=travel[^"]*&range=previous_month"',
        )

    def test_the_nav_has_the_search_filter_and_actions_of_the_shared_nav(self):
        self.generate()
        html = self.get(range="all").content.decode()
        for text in (
            "Search Component",
            "Filter",
            "Actions",
            "Export",
            "Previous Month",
            "All Time",
            "Payslip Status",
        ):
            self.assertIn(text, html)

    def test_the_filter_panel_has_the_employee_list_fields(self):
        self.generate()
        html = self.get(range="all").content.decode()
        for text in (
            "modernFilterPanel",
            "Name or Badge ID",
            "Payslip Status",
            "Employee",
            "Company",
            "Department",
            "Job Position",
        ):
            self.assertIn(text, html)

    def test_the_name_or_badge_search_narrows_who_is_counted(self):
        self.generate()
        response = self.get(range="all", name_or_badge="Ann")
        row = next(r for r in response.context["rows"] if r["title"] == "Travel Pay")
        self.assertEqual((row["employees"], row["payslips"]), (1, 1))
        self.assertEqual(response.context["filter_count"], 1)

    def test_picking_employees_narrows_the_report_to_them(self):
        self.generate()
        response = self.get(range="all", employee_id=[self.people[1].pk])
        row = next(r for r in response.context["rows"] if r["title"] == "Travel Pay")
        self.assertEqual((row["employees"], row["total"]), (1, 1000.0))

    def test_the_payslip_status_narrows_the_report(self):
        self.generate()
        self.assertEqual(self.get(range="all", status="paid").context["rows"], [])
        self.assertTrue(self.get(range="all", status="draft").context["rows"])

    def test_each_filter_in_use_has_a_tag_that_drops_only_it(self):
        self.generate()
        response = self.get(
            range="all", search="travel", name_or_badge="Ann", status="draft"
        )
        tags = {str(tag["label"]): tag for tag in response.context["applied_filters"]}
        self.assertEqual(set(tags), {"Search", "Name Or Badge ID", "Payslip Status"})
        self.assertEqual(tags["Payslip Status"]["value"], "Draft")
        self.assertNotIn("search=", tags["Search"]["remove"])
        self.assertIn("name_or_badge=Ann", tags["Search"]["remove"])
        self.assertNotIn("name_or_badge", tags["Name Or Badge ID"]["remove"])
        self.assertIn("kind=allowance", tags["Search"]["remove"])
        html = response.content.decode()
        for text in ("Filters:", "Name Or Badge ID", "filter-value", "clear-all"):
            self.assertIn(text, html)

    def test_picked_employees_are_named_in_their_tag(self):
        self.generate()
        response = self.get(range="all", employee_id=[self.people[0].pk])
        [tag] = response.context["applied_filters"]
        self.assertEqual(
            (str(tag["label"]), str(tag["value"])),
            ("Employee", str(self.people[0]).strip()),
        )

    def test_a_custom_range_has_a_date_tag_that_drops_the_dates(self):
        self.generate()
        response = self.get(from_date="2026-04-01", to_date="2026-04-30")
        [tag] = response.context["applied_filters"]
        self.assertEqual(str(tag["label"]), "Date Range")
        self.assertNotIn("from_date", tag["remove"])

    def test_no_tags_without_filters(self):
        self.generate()
        self.assertEqual(self.get(range="all").context["applied_filters"], [])
        self.assertNotIn("Filters:", self.get(range="all").content.decode())


class EmployerSplitTests(Fixture):
    """A deduction the employer shares in shows both shares and what they come to together."""

    def get(self, name="payroll-component-report", *args, **params):
        return self.client.get(reverse(name, args=args), {"range": "all", **params})

    def test_a_shared_deduction_has_a_combined_total(self):
        self.generate()
        rows, totals = component_report.summarise(Payslip.objects.all(), DEDUCTION)
        row = next(r for r in rows if r["title"] == "Provident Fund")
        self.assertTrue(totals["split"])
        self.assertAlmostEqual(
            row["combined"], row["total"] + row["employer_total"], places=2
        )
        self.assertAlmostEqual(
            totals["combined"], totals["total"] + totals["employer_total"], places=2
        )

    def test_the_summary_and_the_component_page_show_the_split(self):
        self.generate()
        html = self.get(kind="deduction").content.decode()
        for text in ("Employee Share", "Employer Share", "Combined Total"):
            self.assertIn(text, html)
        response = self.get(
            "payroll-component-report-detail", DEDUCTION, self.deduction.pk
        )
        self.assertTrue(response.context["split"])
        line = response.context["lines"][0]
        self.assertAlmostEqual(
            line["combined"], line["amount"] + line["employer_amount"], places=2
        )
        self.assertAlmostEqual(
            response.context["totals"]["combined"],
            response.context["totals"]["amount"]
            + response.context["totals"]["employer_amount"],
            places=2,
        )
        self.assertIn("Combined Total", response.content.decode())

    def test_a_deduction_without_an_employer_share_keeps_a_single_total(self):
        Deduction.objects.filter(pk=self.deduction.pk).update(employer_rate=0)
        self.generate()
        response = self.get(kind="deduction")
        self.assertFalse(response.context["totals"]["split"])
        html = response.content.decode()
        self.assertNotIn("Combined Total", html)
        self.assertIn("Total Deducted", html)
        detail = self.get(
            "payroll-component-report-detail", DEDUCTION, self.deduction.pk
        )
        self.assertFalse(detail.context["split"])
        self.assertNotIn("Combined Total", detail.content.decode())

    def test_an_allowance_is_never_split(self):
        self.generate()
        self.assertFalse(self.get().context["totals"]["split"])
        self.assertNotIn("Combined Total", self.get().content.decode())


class MenuTests(Fixture):
    def test_the_kind_switch_is_an_ajax_link_that_keeps_the_other_choices(self):
        self.generate()
        html = self.client.get(
            reverse("payroll-component-report"),
            {"kind": "deduction", "range": "all", "search": "pro"},
        ).content.decode()
        self.assertIn('hx-target="#componentReportPage"', html)
        link = next(
            part
            for part in html.split("<a ")
            if 'hx-target="#componentReportPage"' in part
        )
        self.assertEqual(
            link.count("kind="), 2
        )  # the href and the hx-get, one kind in each
        self.assertIn("search=pro", link)
        self.assertIn("range=all", link)
        self.assertNotIn("kind=deduction", link)

    def test_the_report_is_in_the_main_menu_just_above_configuration(self):
        from payroll.sidebar import SUBMENUS

        names = [str(item["menu"]) for item in SUBMENUS]
        self.assertEqual(names[names.index("Configuration") - 1], "Component Report")
        entry = SUBMENUS[names.index("Component Report")]
        self.assertEqual(entry["redirect"], reverse("payroll-component-report"))
        self.assertTrue(
            reverse("payroll-component-report-detail", args=[ALLOWANCE, 1]).startswith(
                entry["redirect"]
            )
        )


class RowActionTests(Fixture):
    def test_each_allowance_row_has_a_report_button_for_its_own_report(self):
        html = self.client.get(reverse("allowances-list-view"), **HX).content.decode()
        self.assertIn(
            reverse(
                "payroll-component-report-detail", args=[ALLOWANCE, self.allowance.pk]
            ),
            html,
        )

    def test_each_deduction_row_has_a_report_button_for_its_own_report(self):
        html = self.client.get(reverse("deduction-view-list"), **HX).content.decode()
        self.assertIn(
            reverse(
                "payroll-component-report-detail", args=[DEDUCTION, self.deduction.pk]
            ),
            html,
        )

    def test_the_button_is_not_offered_without_payslip_access(self):
        user = make_user("noreport")
        make_employee(company=self.company, email="noreport@test.horilla", user=user)
        from django.contrib.auth.models import Permission

        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=("view_allowance", "change_allowance")
            )
        )
        self.client.force_login(user)
        html = self.client.get(reverse("allowances-list-view"), **HX).content.decode()
        self.assertNotIn("component-report", html)


class HighlightTests(Fixture):
    """A report row opens the payslip with that component's lines marked."""

    def payslip(self):
        self.generate()
        payslip = Payslip.objects.filter(employee_id=self.people[0]).first()
        session = self.client.session
        session["selected_company"] = str(self.company.pk)
        session.save()
        return payslip

    def test_a_row_of_the_component_page_links_to_the_payslip_with_the_component_to_highlight(
        self,
    ):
        self.generate()
        for kind, component, key in (
            (ALLOWANCE, self.allowance, "a"),
            (DEDUCTION, self.deduction, "d"),
        ):
            with self.subTest(kind=kind):
                response = self.client.get(
                    reverse(
                        "payroll-component-report-detail", args=[kind, component.pk]
                    ),
                    {"range": "all"},
                )
                self.assertEqual(response.context["highlight"], f"{key}:{component.pk}")
                self.assertIn(
                    f"?highlight={key}:{component.pk}'", response.content.decode()
                )

    def test_the_payslip_lines_carry_the_component_they_belong_to(self):
        payslip = self.payslip()
        html = self.client.get(
            reverse("view-created-payslip", args=[payslip.pk])
        ).content.decode()
        self.assertIn(f'data-component="a:{self.allowance.pk}"', html)
        self.assertIn(f'data-component="d:{self.deduction.pk}"', html)

    def test_the_payslip_page_marks_the_lines_it_is_asked_to(self):
        payslip = self.payslip()
        html = self.client.get(
            reverse("view-created-payslip", args=[payslip.pk]),
            {"highlight": f"d:{self.deduction.pk}"},
        ).content.decode()
        for text in (
            "ps__row--hl",
            "cbk__row--hl",
            'get("highlight")',
            "scrollIntoView",
            "replaceState",
            "forwards",
            "setTimeout",
        ):
            self.assertIn(text, html)

    def test_a_key_names_a_stored_line_the_way_the_popovers_do(self):
        from payroll.templatetags.payrollfilters import component_key

        self.assertEqual(component_key({"deduction_id": 5, "title": "PF"}), "d:5")
        self.assertEqual(component_key({"allowance_id": 3, "title": "HRA"}), "a:3")
        self.assertEqual(
            component_key({"allowance_id": 3, "custom_id": "x", "title": "Bonus"}),
            "title:Bonus",
        )
        self.assertEqual(component_key("basic"), "")


class DefaultEntryTests(Fixture):
    """The entries raised for one request repeat a name: they report as one row, told apart only by tax treatment."""

    def entry(self, title, employee, amount, taxable=True, default=True):
        """An earning the way a loan, advance or claim raises it: one date, one employee."""
        entry = Allowance.objects.create(
            title=title,
            is_fixed=True,
            amount=amount,
            include_active_employees=False,
            one_time_date=date(2026, 4, 10),
            maximum_unit="full_period",
            only_show_under_employee=default,
            is_taxable=taxable,
        )
        entry.specific_employees.add(employee)
        return entry

    def rows(self, **extra):
        rows, _totals = component_report.summarise(self.generate(), ALLOWANCE)
        return {row["title"]: row for row in rows}

    def test_the_entries_of_one_name_are_one_row(self):
        self.entry("Staff loan", self.people[0], 7500.0)
        self.entry("Staff loan", self.people[1], 5000.0)
        loan = self.rows()["Staff loan"]
        self.assertEqual(
            (loan["entries"], loan["employees"], loan["payslips"]), (2, 2, 2)
        )
        self.assertAlmostEqual(loan["total"], 12500.0, places=2)
        self.assertEqual(loan["code"], "")

    def test_a_single_entry_keeps_its_code(self):
        self.entry("Medical claim", self.people[0], 500.0)
        claim = self.rows()["Medical claim"]
        self.assertEqual(claim["entries"], 1)
        self.assertEqual(claim["code"], "MEDICAL_CLAIM")

    def test_entries_of_different_tax_treatment_are_told_apart_in_brackets(self):
        self.entry("Staff loan", self.people[0], 7500.0, taxable=True)
        self.entry("Staff loan", self.people[1], 5000.0, taxable=False)
        rows = self.rows()
        self.assertNotIn("Staff loan", rows)
        self.assertAlmostEqual(rows["Staff loan (Taxable)"]["total"], 7500.0, places=2)
        self.assertAlmostEqual(
            rows["Staff loan (Non-Taxable)"]["total"], 5000.0, places=2
        )

    def test_ordinary_components_of_one_name_stay_separate(self):
        self.entry("Bonus", self.people[0], 100.0, default=False)
        self.entry("Bonus", self.people[1], 200.0, default=False)
        rows, _totals = component_report.summarise(self.generate(), ALLOWANCE)
        self.assertEqual(len([row for row in rows if row["title"] == "Bonus"]), 2)

    def test_the_component_page_lists_every_entry_of_the_row(self):
        first = self.entry("Staff loan", self.people[0], 7500.0)
        second = self.entry("Staff loan", self.people[1], 5000.0)
        self.generate()
        for opened in (first, second):
            with self.subTest(opened=opened.code):
                response = self.client.get(
                    reverse(
                        "payroll-component-report-detail", args=[ALLOWANCE, opened.pk]
                    ),
                    {"range": "all"},
                )
                self.assertEqual(len(response.context["lines"]), 2)
                self.assertEqual(response.context["entries"], 2)
                self.assertIn("2 Entries", response.content.decode())

    def test_the_summary_says_how_many_entries_a_row_holds(self):
        self.entry("Staff loan", self.people[0], 7500.0)
        self.entry("Staff loan", self.people[1], 5000.0)
        self.generate()
        html = self.client.get(
            reverse("payroll-component-report"), {"range": "all"}
        ).content.decode()
        self.assertIn("2 Entries", html)

    def test_the_search_finds_a_row_by_the_code_of_any_entry(self):
        first = self.entry("Staff loan", self.people[0], 7500.0)
        second = self.entry("Staff loan", self.people[1], 5000.0)
        rows, _totals = component_report.summarise(
            self.generate(), ALLOWANCE, second.code
        )
        self.assertEqual([row["title"] for row in rows], ["Staff loan"])
        self.assertNotEqual(first.code, second.code)

    def test_only_the_default_entries_are_reported_as_one(self):
        ordinary = self.entry("Bonus", self.people[0], 100.0, default=False)
        generated = self.entry("Staff loan", self.people[0], 7500.0)
        other = self.entry("Staff loan", self.people[1], 5000.0)
        self.assertEqual(
            component_report.member_ids(ALLOWANCE, ordinary), {ordinary.pk}
        )
        self.assertEqual(
            component_report.member_ids(ALLOWANCE, generated), {generated.pk, other.pk}
        )
