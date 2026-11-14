"""
The badge_id field is called Badge ID wherever people see it. The record id a
sheet identifies a row by is a different number, so it stays out of sight, and
files made under the old headings still import.
"""

import io
from datetime import date, timedelta
from importlib import import_module

import openpyxl
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from base.models import (
    Department,
    EmployeeShift,
    Roster,
    RotatingShift,
    RotatingShiftAssign,
)
from employee.forms import EmployeeForm
from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from project.models import Project


class SignedIn(TestCase):
    def setUp(self):
        self.company = make_company("Badge Co")
        boss = make_user("badgeboss", is_superuser=True)
        make_employee(company=self.company, email="boss@badge.test", user=boss)
        self.client.force_login(boss)
        self.employee = make_employee(company=self.company, email="w@badge.test")
        Employee.objects.filter(pk=self.employee.pk).update(badge_id="B-77")
        self.employee.refresh_from_db()


class FieldLabelTests(SignedIn):
    def test_the_field_has_the_label(self):
        self.assertEqual(EmployeeForm().fields["badge_id"].label, "Badge ID")

    def test_the_form_that_lays_it_out_by_hand_shows_it_once(self):
        html = EmployeeForm(instance=self.employee).as_p()
        self.assertLessEqual(html.count('name="badge_id"'), 1)

    def test_the_profile_calls_it_badge_id(self):
        page = self.client.get(
            reverse("employee-view-individual", args=[self.employee.pk])
        )
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Badge Id")


class RosterSheetTests(SignedIn):
    def setUp(self):
        super().setUp()
        department = Department.objects.create(department="Badge Dept")
        EmployeeWorkInformation.objects.filter(employee_id=self.employee).update(
            department_id=department
        )

    def sheet(self):
        response = self.client.get(reverse("roster-template-download"))
        self.assertEqual(response.status_code, 200)
        return openpyxl.load_workbook(io.BytesIO(response.content))

    def row_of_employee(self, sheet):
        for row in range(2, sheet.max_row + 1):
            if sheet.cell(row, 2).value == self.employee.pk:
                return row
        self.fail("employee row not found")

    def test_people_see_the_badge_id_and_not_the_record_id(self):
        sheet = self.sheet()["Roster"]
        self.assertTrue(sheet.column_dimensions["B"].hidden)
        self.assertEqual(sheet.cell(1, 2).value, "Record ID")
        self.assertIn("(B-77)", sheet.cell(self.row_of_employee(sheet), 1).value)

    def upload(self, book):
        buffer = io.BytesIO()
        book.save(buffer)
        return self.client.post(
            reverse("roster-import"),
            {"file": SimpleUploadedFile("roster.xlsx", buffer.getvalue())},
        )

    def test_the_sheet_imports_against_the_right_person(self):
        book = self.sheet()
        sheet = book["Roster"]
        sheet.cell(self.row_of_employee(sheet), 3).value = "OFF"
        response = self.upload(book)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Roster.objects.filter(employee=self.employee).exists())

    def test_a_sheet_from_before_this_change_still_imports(self):
        day = date.today() + timedelta(days=7)
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(["Employee Name", "Employee ID", day])
        sheet.append(["Anyone", self.employee.pk, "OFF"])
        self.upload(book)
        self.assertTrue(
            Roster.objects.filter(employee=self.employee, date=day).exists()
        )


class ImportHeadingTests(SignedIn):
    def project_upload(self, heading):
        csv = (
            f"Title,{heading},Status,Start Date,End Date,Description,Company\n"
            f"Plan,B-77,new,2030-01-01,2030-02-01,About it,{self.company.company}\n"
        )
        return self.client.post(
            reverse("project-import"),
            {"file": SimpleUploadedFile("p.csv", csv.encode())},
            HTTP_HX_REQUEST="true",
        )

    def test_the_project_import_reads_both_headings(self):
        for heading in ("Manager Badge ID", "Manager Badge id"):
            with self.subTest(heading=heading):
                Project.objects.entire().delete()
                self.project_upload(heading)
                project = Project.objects.entire().get(title="Plan")
                self.assertIn(self.employee, project.managers.all())

    def rotating_upload(self, heading):
        csv = (
            f"{heading},Name,Title,2030-01-01,Day,Night\n"
            "B-77,Worker,Pattern,x,Day,Night\n"
        )
        return self.client.post(
            reverse("rotating-shift-assign-info-import"),
            {"file": SimpleUploadedFile("r.csv", csv.encode())},
            HTTP_HX_REQUEST="true",
        )

    def test_the_rotating_shift_import_reads_both_headings(self):
        EmployeeShift.objects.create(employee_shift="Day")
        EmployeeShift.objects.create(employee_shift="Night")
        for heading in ("Badge ID", "Badge Id"):
            with self.subTest(heading=heading):
                RotatingShiftAssign.objects.all().delete()
                RotatingShift.objects.all().delete()
                self.assertEqual(self.rotating_upload(heading).status_code, 200)
                self.assertTrue(
                    RotatingShiftAssign.objects.filter(
                        employee_id=self.employee
                    ).exists()
                )


class SavedLayoutTests(SimpleTestCase):
    def setUp(self):
        self.migration = import_module(
            "report.migrations.0005_badge_id_in_saved_layouts"
        )

    def test_a_saved_layout_follows_the_new_names(self):
        layout = {
            "rows": ["Badge Id", "Name"],
            "cols": ["Manager Badge Id"],
            "exclusions": {"Badge Id": ["7"]},
        }
        self.assertEqual(
            self.migration.renamed(layout, self.migration.RENAMED),
            {
                "rows": ["Badge ID", "Name"],
                "cols": ["Manager Badge ID"],
                "exclusions": {"Badge ID": ["7"]},
            },
        )

    def test_a_value_that_only_looks_similar_is_left_alone(self):
        names = self.migration.RENAMED
        self.assertEqual(
            self.migration.renamed(["Badge Id Extra"], names), ["Badge Id Extra"]
        )


class SavedLayoutMigrationTests(TestCase):
    def test_saved_templates_are_rewritten(self):
        migration = import_module("report.migrations.0005_badge_id_in_saved_layouts")
        template_model = apps.get_model("report", "ReportTemplate")
        template = template_model.objects.create(
            report_slug="employee", name="Mine", config={"rows": ["Badge Id"]}
        )
        migration.forwards(apps, None)
        template.refresh_from_db()
        self.assertEqual(template.config, {"rows": ["Badge ID"]})
        migration.backwards(apps, None)
        template.refresh_from_db()
        self.assertEqual(template.config, {"rows": ["Badge Id"]})
