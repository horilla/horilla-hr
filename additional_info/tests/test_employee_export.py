"""The employee export offers the additional fields as columns and fills them in."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from additional_info.integration import EXPORT_PREFIX
from additional_info.models import (
    DATE,
    DROPDOWN,
    FILE,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
    AdditionalInfoValue,
)
from employee.forms import EmployeeExportExcelForm
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser

# The header is the first row: the export has no title block above it.
HEADER_ROW = 0


def field(label, field_type=TEXT, **extra):
    return AdditionalInfoField.objects.create(
        label=label, field_type=field_type, **extra
    )


def value(employee, info_field, **column):
    return AdditionalInfoValue.objects.create(
        employee_id=employee, field=info_field, **column
    )


class ExportFixture(TestCase):
    def setUp(self):
        company = make_company("Export Co")
        admin = make_user("export_admin", password="x", is_superuser=True)
        make_employee(
            company=company, email="export_admin@x.test", user=admin, first_name="Root"
        )
        self.ada = make_employee(company=company, email="ada@e.test", first_name="Ada")
        self.bob = make_employee(company=company, email="bob@e.test", first_name="Bob")
        HorillaUser.objects.update(is_new_employee=False)
        self.client.force_login(admin)

        self.team = field("Team")
        self.years = field("Years", NUMBER)
        self.joined = field("Joined", DATE)
        self.blood = field(
            "Blood Group", DROPDOWN, choices=[{"key": "a_pos", "label": "A+"}]
        )
        self.driver = field("Driver", YES_NO)
        value(self.ada, self.team, value_text="Alpha team")
        value(self.ada, self.years, value_number=Decimal("5.500000"))
        value(self.ada, self.joined, value_date=date(2026, 1, 10))
        value(self.ada, self.blood, value_text="a_pos")
        value(self.ada, self.driver, value_bool=True)

    def column(self, info_field):
        return EXPORT_PREFIX + info_field.key

    def export(self, *columns):
        response = self.client.get(
            reverse("work-info-export"),
            {"selected_fields": ["employee_first_name", *columns]},
        )
        self.assertEqual(response.status_code, 200)
        return (
            pd.read_excel(BytesIO(response.content), dtype=str, header=HEADER_ROW)
            .fillna("")
            .set_index("First Name")
        )


class EmployeeExportTests(ExportFixture):
    # --- the form ---
    def test_the_form_offers_each_active_field_after_the_built_in_ones(self):
        choices = EmployeeExportExcelForm().fields["selected_fields"].choices
        values = [c[0] for c in choices]
        self.assertIn("badge_id", values)
        self.assertEqual(
            [c for c in choices if c[0].startswith(EXPORT_PREFIX)],
            [
                (self.column(f), f.label)
                for f in (self.team, self.years, self.joined, self.blood, self.driver)
            ],
        )
        self.assertLess(values.index("badge_id"), values.index(self.column(self.team)))

    def test_an_inactive_field_is_not_offered(self):
        self.team.is_active = False
        self.team.save()
        values = [
            c[0] for c in EmployeeExportExcelForm().fields["selected_fields"].choices
        ]
        self.assertNotIn(self.column(self.team), values)

    def test_a_field_added_later_is_offered_by_a_new_form(self):
        field("Locker No")
        values = [
            c[0] for c in EmployeeExportExcelForm().fields["selected_fields"].choices
        ]
        self.assertIn(EXPORT_PREFIX + "locker_no", values)

    def test_the_built_in_default_selection_is_unchanged(self):
        initial = EmployeeExportExcelForm().fields["selected_fields"].initial
        self.assertFalse([v for v in initial if v.startswith(EXPORT_PREFIX)])

    # --- the file ---
    def test_the_chosen_fields_become_columns_with_each_employees_values(self):
        frame = self.export(
            *[
                self.column(f)
                for f in (self.team, self.years, self.joined, self.blood, self.driver)
            ]
        )
        ada = frame.loc["Ada"]
        self.assertEqual(
            [
                ada["Team"],
                ada["Years"],
                ada["Joined"],
                ada["Blood Group"],
                ada["Driver"],
            ],
            ["Alpha team", "5.5", "2026-01-10", "A+", "Yes"],
        )

    def test_a_file_field_is_the_complete_media_url(self):
        doc = field("Passport Scan", FILE)
        row = value(
            self.ada,
            doc,
            value_file=SimpleUploadedFile(
                "passport.pdf", b"%PDF-1", content_type="application/pdf"
            ),
        )
        frame = self.export(self.column(doc))
        link = frame.loc["Ada", "Passport Scan"]
        self.assertEqual(
            link, f"http://testserver{settings.MEDIA_URL}{row.value_file.name}"
        )
        self.assertEqual(frame.loc["Bob", "Passport Scan"], "")

    def test_an_employee_with_nothing_filled_in_gets_empty_cells(self):
        frame = self.export(self.column(self.team), self.column(self.driver))
        self.assertEqual(list(frame.loc["Bob"]), ["", ""])

    def test_only_the_chosen_fields_appear(self):
        frame = self.export(self.column(self.team))
        self.assertEqual(list(frame.columns), ["Team"])

    def test_a_field_named_like_a_built_in_column_gets_its_own_column(self):
        phone = field("Phone")
        value(self.ada, phone, value_text="from-info")
        response = self.client.get(
            reverse("work-info-export"),
            {"selected_fields": ["employee_first_name", "phone", self.column(phone)]},
        )
        frame = pd.read_excel(
            BytesIO(response.content), dtype=str, header=HEADER_ROW
        ).fillna("")
        self.assertEqual(list(frame.columns), ["First Name", "Phone", "Phone (2)"])
        self.assertEqual(
            frame.set_index("First Name").loc["Ada", "Phone (2)"], "from-info"
        )

    def test_an_unknown_or_inactive_column_is_ignored(self):
        self.team.is_active = False
        self.team.save()
        frame = self.export(self.column(self.team), EXPORT_PREFIX + "nope")
        self.assertEqual(list(frame.columns), [])

    def test_a_field_key_with_double_underscores_does_not_break_the_export(self):
        odd = field("A__B")
        self.assertIn("__", odd.key)
        value(self.ada, odd, value_text="ok")
        frame = self.export(self.column(odd))
        self.assertEqual(frame.loc["Ada", "A__B"], "ok")


class EmployeeExportStyleTests(ExportFixture):
    """The file is the standard export's styled header over the rows, with no title block."""

    def sheet(self, **extra):
        params = {"selected_fields": ["employee_first_name", "email"], **extra}
        response = self.client.get(reverse("work-info-export"), params)
        self.assertEqual(response.status_code, 200)
        return load_workbook(BytesIO(response.content)).active, response

    def test_the_header_is_the_first_row_and_styled(self):
        sheet, _response = self.sheet()
        header = sheet["A1"]
        self.assertEqual([c.value for c in sheet[1]], ["First Name", "Email"])
        self.assertTrue(header.font.bold)
        self.assertEqual(header.fill.start_color.rgb[-6:], "FFD700")
        self.assertEqual(sheet["A2"].value in ("Ada", "Bob", "Root"), True)
        self.assertFalse(sheet.merged_cells.ranges)

    def test_each_column_is_as_wide_as_its_heading_and_content(self):
        sheet, _response = self.sheet()
        longest_email = max(
            len(str(row[1].value)) for row in sheet.iter_rows(min_row=2)
        )
        self.assertEqual(sheet.column_dimensions["B"].width, longest_email + 2)
        self.assertEqual(
            sheet.column_dimensions["A"].width, max(len("First Name"), 4) + 2
        )

    def test_a_long_entry_is_capped_so_one_column_cannot_take_the_screen(self):
        self.team.label = "Team"
        value(self.bob, self.team, value_text="x" * 300)
        response = self.client.get(
            reverse("work-info-export"),
            {"selected_fields": ["employee_first_name", self.column(self.team)]},
        )
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet.column_dimensions["B"].width, 50)

    def test_the_name_picked_in_the_modal_names_the_file(self):
        _sheet, response = self.sheet(hlv_export_name="Staff List")
        self.assertIn("Staff List.xlsx", response["Content-Disposition"])

    def test_the_default_file_name_is_unchanged(self):
        _sheet, response = self.sheet()
        self.assertIn("employee_export.xlsx", response["Content-Disposition"])

    def test_choosing_no_known_column_is_refused(self):
        response = self.client.get(
            reverse("work-info-export"), {"selected_fields": ["nope"]}
        )
        self.assertEqual(response.status_code, 400)
