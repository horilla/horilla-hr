"""Importing arrears and recovery entries from a sheet: checked first, written only on confirmation."""

import datetime
import io
from datetime import date

import pandas as pd
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.methods.pay_adjustment_import import (
    HEADERS,
    MAX_ROWS,
    SheetProblem,
    check_sheet,
    create_entries,
    read_sheet,
)
from payroll.models.models import PayAdjustment, Payslip

HX = {"HTTP_HX_REQUEST": "true"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Import Co")
        self.adam = make_employee(
            company=self.company, email="adam-imp@test.horilla", first_name="Adam"
        )
        self.bea = make_employee(
            company=self.company, email="bea-imp@test.horilla", first_name="Bea"
        )
        self.gone = make_employee(
            company=self.company, email="gone-imp@test.horilla", first_name="Gone"
        )
        for employee, badge in (
            (self.adam, "IMP001"),
            (self.bea, "IMP002"),
            (self.gone, "IMP003"),
        ):
            employee.badge_id = badge
            employee.save()
        self.gone.is_active = False
        self.gone.save()

    def frame(self, *rows, columns=HEADERS):
        return pd.DataFrame(list(rows), columns=columns, dtype=object)

    def good(self, **overrides):
        row = {
            "Badge ID": "IMP001",
            "Type": "Arrears",
            "Title": "Back Pay",
            "Amount": 1000,
            "Pay Date": date(2026, 12, 5),
            "Taxable / Pre-Tax": "Yes",
            "Reason": "Revised",
        }
        row.update(overrides)
        return [row[header] for header in HEADERS]

    def check(self, *rows, columns=HEADERS):
        return check_sheet(self.frame(*rows, columns=columns))

    def payslip(self, employee, start, end):
        return Payslip.objects.create(
            employee_id=employee, start_date=start, end_date=end, pay_head_data={}
        )


class CheckSheetTests(Fixture):
    def test_a_good_row_is_ready_with_everything_resolved(self):
        rows, table = self.check(self.good())
        self.assertEqual(table[0]["errors"], [])
        self.assertEqual(
            rows,
            [
                {
                    "row": 2,
                    "employee_pk": self.adam.pk,
                    "kind": "arrears",
                    "title": "Back Pay",
                    "amount": 1000.0,
                    "pay_date": "2026-12-05",
                    "tax": True,
                    "reason": "Revised",
                }
            ],
        )

    def test_the_sheets_own_row_number_is_reported_the_header_being_row_one(self):
        _rows, table = self.check(self.good(), self.good(**{"Badge ID": "NOPE"}))
        self.assertEqual([row["row"] for row in table], [2, 3])

    def test_the_type_is_arrears_or_recovery_in_any_case(self):
        rows, _t = self.check(
            self.good(Type="RECOVERY"), self.good(Title="Two", Type=" arrears ")
        )
        self.assertEqual([row["kind"] for row in rows], ["recovery", "arrears"])
        _rows, table = self.check(self.good(Type="Bonus"))
        self.assertIn("Type Must Be Arrears Or Recovery.", table[0]["errors"])

    def test_the_badge_must_name_one_active_employee(self):
        _rows, table = self.check(
            self.good(**{"Badge ID": "NOBODY"}),
            self.good(**{"Badge ID": "IMP003"}),
            self.good(**{"Badge ID": None}),
        )
        self.assertIn("No Employee Has This Badge ID.", table[0]["errors"])
        self.assertIn("This Employee Is Not Active.", table[1]["errors"])
        self.assertIn("Badge ID Is Missing.", table[2]["errors"])

    def test_the_title_and_amount_are_needed_and_the_amount_must_be_positive(self):
        _rows, table = self.check(
            self.good(Title=""),
            self.good(Amount=0),
            self.good(Amount=-5),
            self.good(Amount="abc"),
            self.good(Amount=None),
        )
        self.assertIn("Title Is Missing.", table[0]["errors"])
        for index in (1, 2, 3):
            self.assertIn(
                "Amount Must Be A Number More Than Zero.", table[index]["errors"]
            )
        self.assertIn("Amount Is Missing.", table[4]["errors"])

    def test_an_amount_may_be_text_with_a_thousands_comma(self):
        rows, _t = self.check(self.good(Amount="12,500.50"))
        self.assertEqual(rows[0]["amount"], 12500.5)

    def test_the_pay_date_may_be_an_excel_date_a_timestamp_or_iso_text(self):
        rows, _t = self.check(
            self.good(**{"Pay Date": date(2026, 12, 5)}),
            self.good(Title="Two", **{"Pay Date": pd.Timestamp("2026-12-06")}),
            self.good(Title="Three", **{"Pay Date": "2026-12-07"}),
            self.good(
                Title="Four", **{"Pay Date": datetime.datetime(2026, 12, 8, 0, 0)}
            ),
        )
        self.assertEqual(
            [row["pay_date"] for row in rows],
            ["2026-12-05", "2026-12-06", "2026-12-07", "2026-12-08"],
        )

    def test_a_pay_date_that_is_not_a_date_is_refused(self):
        _rows, table = self.check(
            self.good(**{"Pay Date": "next friday"}), self.good(**{"Pay Date": None})
        )
        self.assertIn("Pay Date Must Be A Date, As YYYY-MM-DD.", table[0]["errors"])
        self.assertIn("Pay Date Is Missing.", table[1]["errors"])

    def test_a_month_that_has_a_payslip_is_refused_for_that_employee_only(self):
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        _rows, table = self.check(self.good(), self.good(**{"Badge ID": "IMP002"}))
        self.assertTrue(any("December 2026" in error for error in table[0]["errors"]))
        self.assertEqual(table[1]["errors"], [])

    def test_the_tax_column_is_yes_no_or_empty_and_empty_follows_the_standard(self):
        rows, table = self.check(
            self.good(**{"Taxable / Pre-Tax": "No"}),
            self.good(Title="Two", **{"Taxable / Pre-Tax": None}),
            self.good(Title="Three", **{"Taxable / Pre-Tax": "maybe"}),
        )
        self.assertEqual([row["tax"] for row in rows], [False, None])
        self.assertIn("Taxable / Pre-Tax Must Be Yes, No Or Empty.", table[2]["errors"])

    def test_a_row_repeated_in_the_sheet_is_flagged_the_second_time(self):
        rows, table = self.check(self.good(), self.good())
        self.assertEqual(len(rows), 1)
        self.assertEqual(table[0]["errors"], [])
        self.assertIn("This Row Is Repeated Earlier In The Sheet.", table[1]["errors"])

    def test_an_entry_that_already_exists_is_flagged(self):
        PayAdjustment.objects.create(
            employee_id=self.adam,
            kind="arrears",
            title="Back Pay",
            amount=1000.0,
            pay_date=date(2026, 12, 5),
        )
        _rows, table = self.check(self.good())
        self.assertIn("This Entry Already Exists.", table[0]["errors"])

    def test_a_blank_row_is_skipped_and_every_problem_in_a_row_is_listed(self):
        _rows, table = self.check(
            [None] * 7, self.good(**{"Badge ID": "NOBODY", "Type": "x", "Amount": 0})
        )
        self.assertEqual(len(table), 1)
        self.assertEqual(len(table[0]["errors"]), 3)

    def test_headers_are_matched_loosely_and_extra_columns_ignored(self):
        frame = pd.DataFrame(
            [["IMP001", "arrears", "Back Pay", 10, "2026-12-05", "Hello"]],
            columns=["badge id ", "TYPE", "Title", " Amount", "pay date", "Notes"],
            dtype=object,
        )
        rows, table = check_sheet(frame)
        self.assertEqual((len(rows), table[0]["errors"]), (1, []))
        self.assertIsNone(rows[0]["tax"])

    def test_missing_columns_are_named(self):
        with self.assertRaises(SheetProblem) as caught:
            check_sheet(
                pd.DataFrame(
                    [["IMP001", 5]], columns=["Badge ID", "Amount"], dtype=object
                )
            )
        message = str(caught.exception)
        for name in ("Type", "Title", "Pay Date"):
            self.assertIn(name, message)

    def test_a_numeric_badge_id_still_matches(self):
        self.bea.badge_id = "4005"
        self.bea.save()
        rows, _t = self.check(self.good(**{"Badge ID": 4005.0}))
        self.assertEqual(rows[0]["employee_pk"], self.bea.pk)

    def test_checking_writes_nothing(self):
        self.check(self.good(), self.good(Title="Two"))
        self.assertEqual(PayAdjustment.objects.count(), 0)


class ReadSheetTests(Fixture):
    def upload(self, frame, name="sheet.xlsx"):
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=XLSX)

    def test_an_excel_file_is_read_and_its_dates_survive(self):
        frame = read_sheet(self.upload(self.frame(self.good())))
        rows, table = check_sheet(frame)
        self.assertEqual((len(rows), table[0]["errors"]), (1, []))
        self.assertEqual(rows[0]["pay_date"], "2026-12-05")

    def test_a_csv_file_is_read_too(self):
        csv = "Badge ID,Type,Title,Amount,Pay Date\nIMP001,Arrears,Back Pay,10,2026-12-05\n"
        rows, _t = check_sheet(
            read_sheet(
                SimpleUploadedFile("sheet.csv", csv.encode(), content_type="text/csv")
            )
        )
        self.assertEqual(len(rows), 1)

    def test_other_files_empty_sheets_and_long_sheets_are_refused_with_a_reason(self):
        with self.assertRaises(SheetProblem):
            read_sheet(SimpleUploadedFile("notes.txt", b"hello"))
        with self.assertRaises(SheetProblem):
            read_sheet(SimpleUploadedFile("broken.xlsx", b"not really a sheet"))
        with self.assertRaises(SheetProblem):
            read_sheet(self.upload(pd.DataFrame(columns=HEADERS)))
        many = pd.DataFrame([self.good()] * (MAX_ROWS + 1), columns=HEADERS)
        with self.assertRaises(SheetProblem):
            read_sheet(self.upload(many))


class CreateEntriesTests(Fixture):
    def rows(self, *rows):
        return check_sheet(self.frame(*rows))[0]

    def test_the_checked_rows_become_drafts_with_their_values(self):
        created, skipped = create_entries(
            self.rows(
                self.good(),
                self.good(
                    Title="Two",
                    Type="Recovery",
                    **{"Taxable / Pre-Tax": None, "Badge ID": "IMP002"}
                ),
            )
        )
        self.assertEqual((created, skipped), (2, []))
        first = PayAdjustment.objects.get(title="Back Pay")
        second = PayAdjustment.objects.get(title="Two")
        self.assertEqual(
            (first.status, first.kind, first.amount, first.tax_treatment),
            ("draft", "arrears", 1000.0, True),
        )
        self.assertEqual(
            (second.kind, second.employee_id, second.tax_treatment),
            ("recovery", self.bea, None),
        )
        self.assertIsNone(first.pay_line())

    def test_a_row_that_no_longer_passes_is_skipped_and_named_and_the_rest_are_made(
        self,
    ):
        rows = self.rows(self.good(), self.good(Title="Two", **{"Badge ID": "IMP002"}))
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        created, skipped = create_entries(rows)
        self.assertEqual(created, 1)
        self.assertEqual(skipped[0][0], 2)
        self.assertIn("December 2026", skipped[0][1])
        self.assertFalse(PayAdjustment.objects.filter(title="Back Pay").exists())
        self.assertTrue(PayAdjustment.objects.filter(title="Two").exists())

    def test_an_entry_added_since_the_preview_is_not_made_twice(self):
        rows = self.rows(self.good())
        PayAdjustment.objects.create(
            employee_id=self.adam,
            kind="arrears",
            title="Back Pay",
            amount=1000.0,
            pay_date=date(2026, 12, 5),
        )
        created, skipped = create_entries(rows)
        self.assertEqual(created, 0)
        self.assertIn("Already Exists", skipped[0][1])
        self.assertEqual(PayAdjustment.objects.filter(title="Back Pay").count(), 1)


class ImportViewTests(Fixture):
    def setUp(self):
        super().setUp()
        user = make_user("impadmin", is_superuser=True)
        make_employee(company=self.company, email="impadmin@test.horilla", user=user)
        self.client.force_login(user)

    def sheet(self, *rows, name="sheet.xlsx"):
        buffer = io.BytesIO()
        self.frame(*rows).to_excel(buffer, index=False)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=XLSX)

    def upload(self, *rows):
        return self.client.post(
            reverse("pay-adjustment-import"), {"file": self.sheet(*rows)}, **HX
        )

    def token(self, response):
        return self.client.session["pay_adjustment_import"]["token"]

    # ---- the template and the nav ----
    def test_the_template_is_a_sheet_with_the_columns_and_two_examples(self):
        response = self.client.get(reverse("pay-adjustment-import-template"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX)
        self.assertIn("attachment", response["Content-Disposition"])
        frame = pd.read_excel(io.BytesIO(response.content))
        self.assertEqual(list(frame.columns), HEADERS)
        self.assertEqual(len(frame), 2)
        self.assertEqual(sorted(frame["Type"]), ["Arrears", "Recovery"])

    def test_the_nav_actions_offer_import_only(self):
        html = self.client.get(reverse("pay-adjustment-nav"), **HX).content.decode()
        self.assertIn(reverse("pay-adjustment-import"), html)
        self.assertNotIn(reverse("pay-adjustment-import-template"), html)
        self.assertRegex(html, r">\s*Import\s*<")

    def test_without_permission_to_add_there_is_no_import(self):
        user = make_user("noadd", is_superuser=False)
        make_employee(company=self.company, email="noadd@test.horilla", user=user)
        self.client.force_login(user)
        # A refused request gets the "no permission" fragment, not the page: no file box, no sheet.
        modal = self.client.get(reverse("pay-adjustment-import"), **HX)
        self.assertNotIn('type="file"', modal.content.decode())
        template = self.client.get(reverse("pay-adjustment-import-template"), **HX)
        self.assertNotEqual(template["Content-Type"], XLSX)
        upload = self.client.post(
            reverse("pay-adjustment-import"), {"file": self.sheet(self.good())}, **HX
        )
        self.assertNotIn("Ready", upload.content.decode())
        self.assertNotIn("pay_adjustment_import", self.client.session)
        self.client.post(reverse("pay-adjustment-import-confirm"), {"token": "x"}, **HX)
        self.assertEqual(PayAdjustment.objects.count(), 0)

    # ---- upload and preview ----
    def test_the_modal_opens_with_the_columns_the_template_and_a_file_box(self):
        html = self.client.get(reverse("pay-adjustment-import"), **HX).content.decode()
        self.assertIn("Import Arrears &amp; Recovery", html.replace("& R", "&amp; R"))
        self.assertIn('type="file"', html)
        self.assertIn(reverse("pay-adjustment-import-template"), html)
        for header in (
            "Badge ID",
            "Type",
            "Title",
            "Amount",
            "Pay Date",
            "Taxable / Pre-Tax",
            "Reason",
        ):
            self.assertIn(header, html)

    def test_no_file_or_a_wrong_file_says_so(self):
        html = self.client.post(
            reverse("pay-adjustment-import"), {}, **HX
        ).content.decode()
        self.assertIn("Choose A File To Import.", html)
        wrong = SimpleUploadedFile("notes.txt", b"hello")
        html = self.client.post(
            reverse("pay-adjustment-import"), {"file": wrong}, **HX
        ).content.decode()
        self.assertIn("Upload An Excel (.xlsx) Or CSV File.", html)

    def test_a_sheet_with_missing_columns_names_them(self):
        buffer = io.BytesIO()
        pd.DataFrame([["IMP001", 5]], columns=["Badge ID", "Amount"]).to_excel(
            buffer, index=False
        )
        sheet = SimpleUploadedFile("sheet.xlsx", buffer.getvalue(), content_type=XLSX)
        html = self.client.post(
            reverse("pay-adjustment-import"), {"file": sheet}, **HX
        ).content.decode()
        self.assertIn("The Sheet Is Missing These Columns", html)
        self.assertIn("Pay Date", html)

    def test_the_preview_shows_every_row_and_what_is_wrong_and_writes_nothing(self):
        response = self.upload(
            self.good(),
            self.good(**{"Badge ID": "NOBODY", "Title": "Lost"}),
            self.good(Title="Two", Type="Recovery"),
        )
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("2 Ready", html)
        self.assertIn("1 With Problems", html)
        self.assertIn("No Employee Has This Badge ID.", html)
        self.assertIn("Import 2 Entries As Drafts", html)
        self.assertIn("Download Problems", html)
        self.assertEqual(PayAdjustment.objects.count(), 0)

    def test_a_clean_sheet_has_nothing_to_download(self):
        html = self.upload(self.good()).content.decode()
        self.assertIn("Import 1 Entry As A Draft", html)
        self.assertNotIn("Download Problems", html)
        self.assertNotIn("With Problems", html)

    def test_a_sheet_with_nothing_good_offers_no_import(self):
        html = self.upload(self.good(**{"Badge ID": "NOBODY"})).content.decode()
        self.assertNotIn("As Draft", html)
        self.assertIn("1 With Problems", html)

    # ---- confirmation ----
    @staticmethod
    def shown(response):
        """The toast messages the response queued."""
        return " | ".join(str(m) for m in get_messages(response.wsgi_request))

    def test_confirming_saves_the_good_rows_as_drafts_and_reloads_the_list(self):
        response = self.upload(
            self.good(),
            self.good(
                Title="Two",
                Type="Recovery",
                **{"Badge ID": "IMP002", "Taxable / Pre-Tax": "No"}
            ),
            self.good(**{"Badge ID": "NOBODY", "Title": "Lost"}),
        )
        confirmed = self.client.post(
            reverse("pay-adjustment-import-confirm"),
            {"token": self.token(response)},
            **HX
        )
        self.assertEqual(confirmed.status_code, 200)
        shown = self.shown(confirmed)
        self.assertIn("2 Entries Saved As Drafts.", shown)
        self.assertIn("1 Row(s) With Problems Were Left Out.", shown)
        self.assertIn("reloadMessagesButton", confirmed.content.decode())
        self.assertIn("reloadPayAdjustments", confirmed["HX-Trigger"])
        entries = PayAdjustment.objects.order_by("pk")
        self.assertEqual(
            [(e.title, e.status, e.kind, e.tax_treatment) for e in entries],
            [
                ("Back Pay", "draft", "arrears", True),
                ("Two", "draft", "recovery", False),
            ],
        )
        self.assertFalse(PayAdjustment.objects.filter(title="Lost").exists())

    def test_the_same_import_cannot_be_confirmed_twice(self):
        token = self.token(self.upload(self.good()))
        self.client.post(
            reverse("pay-adjustment-import-confirm"), {"token": token}, **HX
        )
        again = self.client.post(
            reverse("pay-adjustment-import-confirm"), {"token": token}, **HX
        )
        self.assertIn("That Import Has Expired", again.content.decode())
        self.assertEqual(PayAdjustment.objects.count(), 1)

    def test_a_wrong_or_missing_token_creates_nothing(self):
        self.upload(self.good())
        for data in ({"token": "wrong"}, {}):
            html = self.client.post(
                reverse("pay-adjustment-import-confirm"), data, **HX
            ).content.decode()
            self.assertIn("That Import Has Expired", html)
        self.assertEqual(PayAdjustment.objects.count(), 0)

    def test_a_payslip_made_between_the_preview_and_the_confirmation_skips_that_row(
        self,
    ):
        token = self.token(
            self.upload(self.good(), self.good(Title="Two", **{"Badge ID": "IMP002"}))
        )
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        shown = self.shown(
            self.client.post(
                reverse("pay-adjustment-import-confirm"), {"token": token}, **HX
            )
        )
        self.assertIn("1 Entry Saved As A Draft.", shown)
        self.assertIn("Row 2", shown)
        self.assertIn("December 2026", shown)

    def test_a_new_upload_replaces_the_one_waiting(self):
        first = self.token(self.upload(self.good()))
        second = self.token(self.upload(self.good(Title="Other")))
        self.assertNotEqual(first, second)
        html = self.client.post(
            reverse("pay-adjustment-import-confirm"), {"token": first}, **HX
        ).content.decode()
        self.assertIn("That Import Has Expired", html)
        self.assertEqual(PayAdjustment.objects.count(), 0)

    # ---- the problems file ----
    def test_the_problem_rows_download_as_a_sheet_with_their_errors(self):
        token = self.token(
            self.upload(
                self.good(),
                self.good(**{"Badge ID": "NOBODY", "Title": "Lost"}),
                self.good(Title="Bad", Amount=0),
            )
        )
        response = self.client.get(
            reverse("pay-adjustment-import-errors"), {"token": token}
        )
        self.assertEqual(response.status_code, 200)
        frame = pd.read_excel(io.BytesIO(response.content), dtype=object)
        self.assertEqual(list(frame.columns), HEADERS + ["Errors"])
        self.assertEqual(sorted(frame["Title"]), ["Bad", "Lost"])
        errors = " ".join(frame["Errors"])
        self.assertIn("No Employee Has This Badge ID.", errors)
        self.assertIn("Amount Must Be A Number More Than Zero.", errors)

    def test_there_is_no_problems_file_for_a_clean_sheet_or_a_wrong_token(self):
        token = self.token(self.upload(self.good()))
        self.assertEqual(
            self.client.get(
                reverse("pay-adjustment-import-errors"), {"token": token}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("pay-adjustment-import-errors"), {"token": "wrong"}
            ).status_code,
            404,
        )

    def test_going_back_to_the_upload_step_forgets_the_waiting_import(self):
        token = self.token(self.upload(self.good()))
        html = self.client.get(
            reverse("pay-adjustment-import"), {"step": "upload"}, **HX
        ).content.decode()
        self.assertIn('type="file"', html)
        self.assertNotIn("oh-modal__dialog-header", html)
        confirmed = self.client.post(
            reverse("pay-adjustment-import-confirm"), {"token": token}, **HX
        ).content.decode()
        self.assertIn("That Import Has Expired", confirmed)
