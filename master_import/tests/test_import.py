import io

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from base.models import Company, Department, JobPosition, JobRole
from employee.models import Employee, EmployeeBankDetails
from horilla.testkit import make_company, make_employee, make_user
from master_import.datasets import get_dataset
from master_import.datasets.base import Context
from master_import.models import ImportJob
from master_import.parsing import apply_mapping, suggest_mapping

EMPLOYEES = get_dataset("employees")


def sheet(rows, columns=None):
    buffer = io.BytesIO()
    pd.DataFrame(rows, columns=columns).to_excel(buffer, index=False)
    return SimpleUploadedFile(
        "people.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


GOOD = {
    "Employee ID": "E-1",
    "Full Name": "Maya Chen",
    "Work Email": "maya.chen@acme.test",
    "Mobile": "9876543210",
    "Dept": "Engineering",
    "Entity": "Acme Ltd",
    "Start Date": "2024-06-12",
    "Bank": "First National",
    "A/C No": "000123456789",
}


class ParsingTests(TestCase):
    def test_columns_are_matched_by_name_and_common_aliases(self):
        mapping = suggest_mapping(list(GOOD), EMPLOYEES.fields)
        self.assertEqual(mapping["Badge ID"], "Employee ID")
        self.assertEqual(mapping["Email"], "Work Email")
        self.assertEqual(mapping["Phone"], "Mobile")
        self.assertEqual(mapping["Department"], "Dept")
        self.assertEqual(mapping["Date Joining"], "Start Date")
        self.assertEqual(mapping["Account Number"], "A/C No")

    def test_a_column_is_matched_to_one_field_only(self):
        mapping = suggest_mapping(["Name"], EMPLOYEES.fields)
        self.assertEqual([k for k, v in mapping.items() if v == "Name"], ["Full Name"])

    def test_rows_are_numbered_like_the_sheet(self):
        frame = pd.DataFrame([GOOD, GOOD])
        rows = apply_mapping(
            frame, suggest_mapping(list(GOOD), EMPLOYEES.fields), EMPLOYEES.fields
        )
        self.assertEqual([r["__row"] for r in rows], [2, 3])


def rows_for(*extra):
    frame = pd.DataFrame([{**GOOD, **e} for e in extra] or [GOOD])
    return apply_mapping(
        frame, suggest_mapping(list(frame.columns), EMPLOYEES.fields), EMPLOYEES.fields
    )


class EmployeeCheckTests(TestCase):
    def check(self, rows, company=None):
        return EMPLOYEES.check(rows, Context(company=company))

    def test_a_good_row_is_valid_and_a_full_name_is_split(self):
        result = self.check(rows_for())
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(result.valid[0]["First Name"], "Maya")
        self.assertEqual(result.valid[0]["Last Name"], "Chen")

    def test_a_new_company_is_allowed_and_announced_on_all_companies(self):
        result = self.check(rows_for())
        self.assertEqual(result.errors, [])
        self.assertEqual(result.will_create["companies"], ["Acme Ltd"])

    def test_on_one_company_another_company_is_refused(self):
        company = make_company("Mine")
        result = self.check(rows_for({"Entity": "Other"}), company=company)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Other", " ".join(result.errors[0]["messages"]))

    def test_on_one_company_a_blank_company_goes_to_it(self):
        company = make_company("Mine")
        result = self.check(rows_for({"Entity": None}), company=company)
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(result.valid[0]["Company"], "Mine")

    def test_department_matching_is_exact_so_a_different_case_is_a_new_one(self):
        Department.objects.create(department="Engineering")
        same = self.check(rows_for())
        other_case = self.check(rows_for({"Dept": "engineering"}))
        self.assertNotIn("Engineering", same.will_create["departments"])
        self.assertEqual(other_case.will_create["departments"], ["engineering"])

    def test_a_badge_id_already_in_use_is_an_error_with_its_row_number(self):
        company = make_company("Acme Ltd")
        make_employee(company=company, email="x@acme.test").__class__  # noqa: B018
        Employee.objects.filter(email="x@acme.test").update(badge_id="E-1")
        result = self.check(rows_for())
        self.assertEqual([e["row"] for e in result.errors], [2])
        self.assertIn("badge", " ".join(result.errors[0]["messages"]).lower())

    def test_bank_details_need_both_a_bank_and_an_account_number(self):
        result = self.check(rows_for({"A/C No": None}))
        self.assertEqual(len(result.errors), 1)
        self.assertIn("bank", " ".join(result.errors[0]["messages"]).lower())

    def test_a_value_too_long_for_its_column_is_that_rows_error_not_a_failed_import(
        self,
    ):
        long_role = "Marketing Researcher - Digital Marketing Specialist"
        self.assertGreater(len(long_role), 50)
        columns = {**GOOD, "Job Role": long_role}
        rows = apply_mapping(
            pd.DataFrame([columns]),
            suggest_mapping(list(columns), EMPLOYEES.fields),
            EMPLOYEES.fields,
        )
        result = self.check(rows)
        self.assertEqual(result.valid, [])
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Job Role", " ".join(result.errors[0]["messages"]))
        self.assertIn("50", " ".join(result.errors[0]["messages"]))

    def test_a_bad_email_is_an_error_not_a_crash(self):
        result = self.check(rows_for({"Work Email": "nope"}))
        self.assertEqual(len(result.errors), 1)

    def test_the_username_defaults_to_the_email(self):
        self.assertEqual(
            self.check(rows_for()).valid[0]["Username"], "maya.chen@acme.test"
        )

    def test_the_username_falls_back_to_the_badge_id_without_an_email(self):
        rows = rows_for()
        rows[0]["Email"] = None
        self.assertEqual(EMPLOYEES.prepare(rows, Context())[0]["Username"], "E-1")

    def test_a_username_in_the_sheet_is_used_and_must_be_unique(self):
        result = self.check(
            rows_for(
                {"Login": "maya"},
                {"Login": "maya", "Employee ID": "E-2", "Work Email": "m2@acme.test"},
            )
        )
        self.assertEqual(result.valid[0]["Username"], "maya")
        self.assertEqual(len(result.errors), 1)
        self.assertIn("username", " ".join(result.errors[0]["messages"]).lower())

    def test_a_simple_password_is_accepted_to_be_changed_at_first_sign_in(self):
        result = self.check(rows_for({"Password": "1234"}))
        self.assertEqual(result.errors, [])

    def test_the_import_signs_people_in_with_the_given_username_and_password(self):
        rows = EMPLOYEES.check(
            rows_for({"Login": "maya", "Password": "Str0ng-Pass#9421"}), Context()
        ).valid
        EMPLOYEES.commit(rows, Context())
        user = Employee.objects.entire().get(badge_id="E-1").employee_user_id
        self.assertEqual(user.username, "maya")
        self.assertTrue(user.check_password("Str0ng-Pass#9421"))


class WizardTests(TestCase):
    def setUp(self):
        self.user = make_user("importer", is_superuser=True)
        make_employee(
            company=make_company("Home"), email="importer@home.test", user=self.user
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def upload(self, rows):
        return self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "file": sheet(rows)},
        )

    def test_the_first_step_lists_the_datasets_and_offers_a_template(self):
        response = self.client.get(reverse("master-import"))
        self.assertContains(response, "Employees")
        self.assertContains(
            response, reverse("master-import-template", args=["employees"])
        )

    def test_the_dataset_dropdown_lists_every_dataset(self):
        html = self.client.get(reverse("master-import")).content.decode()
        self.assertIn("Employees", html)
        self.assertIn("Leave Balances", html)
        self.assertNotIn("Soon", html)

    def test_the_template_is_a_sheet_with_every_field_as_a_column(self):
        response = self.client.get(
            reverse("master-import-template", args=["employees"])
        )
        frame = pd.read_excel(io.BytesIO(response.content))
        self.assertEqual(list(frame.columns), [f.key for f in EMPLOYEES.fields])

    def test_the_template_is_formatted_for_working_in(self):
        from openpyxl import load_workbook

        response = self.client.get(
            reverse("master-import-template", args=["employees"])
        )
        sheet = load_workbook(io.BytesIO(response.content)).active
        self.assertEqual(sheet.freeze_panes, "A2")
        header = sheet["A1"]
        self.assertTrue(header.font.bold)
        self.assertEqual(header.fill.start_color.rgb[-6:], "FFFF00")
        self.assertEqual(header.border.left.style, "thin")
        self.assertEqual(sheet["A2"].border.bottom.style, "thin")
        self.assertEqual(
            sheet["C20"].border.bottom.style, "thin"
        )  # a blank grid below the sample
        self.assertGreaterEqual(sheet.column_dimensions["A"].width, 14)

    def test_an_upload_makes_a_job_and_goes_to_matching(self):
        response = self.upload([GOOD])
        job = ImportJob.objects.get()
        self.assertRedirects(response, reverse("master-import-map", args=[job.pk]))
        self.assertEqual(job.row_count, 1)
        self.assertEqual(job.mapping["Badge ID"], "Employee ID")

    def test_a_file_that_is_not_a_sheet_is_refused(self):
        response = self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "file": SimpleUploadedFile("x.txt", b"hello")},
            follow=True,
        )
        self.assertEqual(ImportJob.objects.count(), 0)
        self.assertContains(response, "Upload a CSV or Excel file")

    def match(self, job):
        return self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )

    def test_matching_moves_on_to_the_review_page(self):
        self.upload([GOOD])
        job = ImportJob.objects.get()
        self.assertRedirects(
            self.match(job), reverse("master-import-review", args=[job.pk])
        )

    def test_matching_without_the_required_fields_stays_put(self):
        self.upload([GOOD])
        job = ImportJob.objects.get()
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["map__Email"] = ""
        response = self.client.post(
            reverse("master-import-map", args=[job.pk]), mapping
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Still to match")

    def test_the_review_page_is_step_three_and_runs_the_check(self):
        self.upload([GOOD])
        job = ImportJob.objects.get()
        self.match(job)
        page = self.client.get(reverse("master-import-review", args=[job.pk]))
        self.assertContains(page, "Confirm &amp; Import")
        self.assertContains(page, reverse("master-import-check", args=[job.pk]))

    def test_the_check_answers_with_tabs_of_editable_records(self):
        self.upload([GOOD, {**GOOD, "Employee ID": "E-2", "Work Email": "bad"}])
        job = ImportJob.objects.get()
        self.match(job)
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.assertTrue(data["ok"])
        self.assertEqual((data["valid"], data["error_count"]), (1, 1))
        for text in (
            "Valid Records",
            "Error Records",
            "maya.chen@acme.test",
            'data-field="Email"',
            "mi__cell--bad",
        ):
            self.assertIn(text, data["html"])
        progress = self.client.get(
            reverse("master-import-check-progress", args=[job.pk])
        )
        self.assertEqual(progress.json()["percent"], 100)

    def test_a_dropdown_offers_database_values_and_the_sheets_own(self):
        Department.objects.create(department="Operations")
        self.upload(
            [
                GOOD,
                {
                    **GOOD,
                    "Employee ID": "E-2",
                    "Work Email": "b@acme.test",
                    "Dept": "Brand New",
                },
            ]
        )
        job = ImportJob.objects.get()
        self.match(job)
        html = self.client.post(reverse("master-import-check", args=[job.pk])).json()[
            "html"
        ]
        for name in ("Operations", "Engineering", "Brand New"):
            self.assertIn(f'<option value="{name}"', html)

    def test_a_fixed_choice_field_is_a_dropdown(self):
        columns = {**GOOD, "Gender": "female"}
        frame = pd.DataFrame([columns])
        rows = apply_mapping(
            frame, suggest_mapping(list(columns), EMPLOYEES.fields), EMPLOYEES.fields
        )
        self.assertEqual(rows[0]["Gender"], "female")
        self.assertEqual(
            next(f for f in EMPLOYEES.fields if f.key == "Gender").kind, "choice"
        )

    def test_fixing_an_error_on_the_review_page_makes_the_row_valid(self):
        self.upload([GOOD, {**GOOD, "Employee ID": "E-2", "Work Email": "bad"}])
        job = ImportJob.objects.get()
        self.match(job)
        saved = self.client.post(
            reverse("master-import-edits", args=[job.pk]),
            data='{"edits": {"3": {"Email": "jon.bell@acme.test"}, "3x": {"Email": "x"}, "4": {"Nope": "x"}}}',
            content_type="application/json",
        )
        self.assertTrue(saved.json()["ok"])
        job.refresh_from_db()
        self.assertEqual(job.edits, {"3": {"Email": "jon.bell@acme.test"}})
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))

    def test_running_the_import_writes_people_company_department_and_bank(self):
        self.upload([GOOD, {**GOOD, "Employee ID": "E-2", "Work Email": "bad"}])
        job = ImportJob.objects.get()
        self.match(job)
        response = self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertRedirects(response, reverse("master-import-done", args=[job.pk]))

        employee = Employee.objects.entire().get(badge_id="E-1")
        self.assertEqual(employee.employee_first_name, "Maya")
        self.assertEqual(employee.employee_work_info.company_id.company, "Acme Ltd")
        self.assertEqual(
            employee.employee_work_info.department_id.department, "Engineering"
        )
        self.assertEqual(
            EmployeeBankDetails.objects.get(employee_id=employee).account_number,
            "000123456789",
        )
        self.assertTrue(Company.objects.filter(company="Acme Ltd").exists())
        # A company made from a name alone has nothing else filled in.
        self.assertIsNone(Company.objects.get(company="Acme Ltd").address)
        self.assertFalse(Employee.objects.entire().filter(badge_id="E-2").exists())

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.DONE)
        self.assertEqual(job.summary["imported"], 1)
        self.assertEqual(job.summary["error_count"], 1)
        self.assertEqual(job.summary["counts"]["companies"], 1)

    def skip(self, job, **rows):
        return self.client.post(
            reverse("master-import-edits", args=[job.pk]),
            data=__import__("json").dumps(
                {"skip": {k.lstrip("r"): v for k, v in rows.items()}}
            ),
            content_type="application/json",
        )

    def test_a_skipped_record_is_left_out_of_the_check_and_the_import(self):
        self.upload(
            [GOOD, {**GOOD, "Employee ID": "E-2", "Work Email": "two@acme.test"}]
        )
        job = ImportJob.objects.get()
        self.match(job)
        self.skip(job, r3=True)
        job.refresh_from_db()
        self.assertEqual(job.skipped, [3])
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Skipped", data["html"])
        self.assertIn(
            'data-skipped="1"', data["html"]
        )  # listed on the Skipped tab, ticked
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertTrue(Employee.objects.entire().filter(badge_id="E-1").exists())
        self.assertFalse(Employee.objects.entire().filter(badge_id="E-2").exists())
        job.refresh_from_db()
        self.assertEqual(job.summary["skipped"], 1)
        self.assertEqual(job.summary["imported"], 1)

    def test_a_skipped_record_can_be_put_back(self):
        self.upload(
            [GOOD, {**GOOD, "Employee ID": "E-2", "Work Email": "two@acme.test"}]
        )
        job = ImportJob.objects.get()
        self.match(job)
        self.skip(job, r3=True)
        self.skip(job, r3=False)
        job.refresh_from_db()
        self.assertEqual(job.skipped, [])
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.assertEqual(data["valid"], 2)

    def test_valid_error_and_skipped_records_can_be_downloaded(self):
        self.upload(
            [
                GOOD,
                {**GOOD, "Employee ID": "E-2", "Work Email": "bad"},
                {**GOOD, "Employee ID": "E-3", "Work Email": "three@acme.test"},
            ]
        )
        job = ImportJob.objects.get()
        self.match(job)
        self.skip(job, r4=True)

        def sheet_of(kind):
            response = self.client.get(
                reverse("master-import-download", args=[job.pk, kind])
            )
            self.assertEqual(response.status_code, 200)
            return pd.read_excel(io.BytesIO(response.content), dtype=str)

        valid, errors, skipped = (
            sheet_of("valid"),
            sheet_of("errors"),
            sheet_of("skipped"),
        )
        self.assertEqual(list(valid["Badge ID"]), ["E-1"])
        self.assertEqual(list(errors["Badge ID"]), ["E-2"])
        self.assertIn("Errors", errors.columns)
        self.assertEqual(list(skipped["Badge ID"]), ["E-3"])
        # only what was matched is in the sheet
        self.assertNotIn("Bank Country", valid.columns)
        self.assertEqual(
            self.client.get(
                reverse("master-import-download", args=[job.pk, "nope"])
            ).status_code,
            404,
        )

    def test_corrected_rows_are_imported(self):
        self.upload([{**GOOD, "Work Email": "bad"}])
        job = ImportJob.objects.get()
        self.match(job)
        self.client.post(
            reverse("master-import-edits", args=[job.pk]),
            data='{"edits": {"2": {"Email": "maya.chen@acme.test"}}}',
            content_type="application/json",
        )
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertTrue(
            Employee.objects.entire()
            .filter(badge_id="E-1", email="maya.chen@acme.test")
            .exists()
        )

    def test_the_summary_lists_errors_and_offers_the_error_file(self):
        self.upload([{**GOOD, "Work Email": "bad"}])
        job = ImportJob.objects.get()
        self.match(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        page = self.client.get(reverse("master-import-done", args=[job.pk]))
        self.assertContains(page, "Rows That Were Not Imported")
        download = self.client.get(reverse("master-import-errors", args=[job.pk]))
        frame = pd.read_excel(io.BytesIO(b"".join(download.streaming_content)))
        self.assertIn("Errors", frame.columns)
        self.assertEqual(frame.loc[0, "Row"], 2)

    def test_a_finished_import_cannot_be_run_twice(self):
        self.upload([GOOD])
        job = ImportJob.objects.get()
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(Employee.objects.entire().filter(badge_id="E-1").count(), 1)

    def test_history_lists_the_import(self):
        self.upload([GOOD])
        self.assertContains(
            self.client.get(reverse("master-import-history")), "people.xlsx"
        )

    def test_someone_without_permission_cannot_import(self):
        other = make_user("plain")
        make_employee(company=make_company("Co"), email="plain@co.test", user=other)
        self.client.force_login(other)
        response = self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "file": sheet([GOOD])},
        )
        self.assertEqual(ImportJob.objects.count(), 0)
        self.assertEqual(response.status_code, 302)

    def test_another_user_cannot_open_the_job(self):
        self.upload([GOOD])
        job = ImportJob.objects.get()
        other = make_user("peer")
        make_employee(company=make_company("Co2"), email="peer@co.test", user=other)
        self.client.force_login(other)
        self.assertEqual(
            self.client.get(reverse("master-import-map", args=[job.pk])).status_code,
            404,
        )


class UpdateModeTests(TestCase):
    """Bulk update: people found by a key, only what the sheet fills in is changed."""

    def setUp(self):
        self.user = make_user("updater", is_superuser=True)
        self.company = make_company("Acme Ltd")
        make_employee(company=self.company, email="updater@acme.test", user=self.user)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        self.maya = make_employee(
            company=self.company, email="maya@acme.test", first_name="Maya"
        )
        self.jon = make_employee(
            company=self.company, email="jon@acme.test", first_name="Jon"
        )
        Employee.objects.filter(pk=self.maya.pk).update(
            badge_id="E-1", phone="9876543210", employee_last_name="Chen"
        )
        Employee.objects.filter(pk=self.jon.pk).update(
            badge_id="E-2", phone="9876500000", employee_last_name="Bell"
        )

    def run_update(self, rows, keys=("Badge ID",)):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": "update", "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.assertEqual(job.mode, "update")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = list(keys)
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        job.refresh_from_db()
        return job

    def check(self, job):
        return self.client.post(reverse("master-import-check", args=[job.pk])).json()

    def run_both(self, rows):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": "both", "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.assertEqual(job.mode, "both")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = ["Badge ID"]
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        job.refresh_from_db()
        return job

    def test_create_or_update_updates_known_people_and_creates_the_rest(self):
        new = {
            "Badge ID": "E-9",
            "First Name": "Nia",
            "Last Name": "Cole",
            "Email": "nia@acme.test",
            "Phone": "9876511111",
            "Company": "Acme Ltd",
        }
        known = {
            "Badge ID": "E-1",
            "First Name": "Maya",
            "Last Name": "Chen",
            "Email": "maya@acme.test",
            "Phone": "9876543210",
            "Company": "Acme Ltd",
            "Location": "Austin",
        }
        job = self.run_both([known, new])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        self.assertIn("Will Create", data["html"])
        self.assertIn("New employee", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(
            Employee.objects.entire().get(pk=self.maya.pk).employee_work_info.location,
            "Austin",
        )
        self.assertEqual(
            Employee.objects.entire().get(badge_id="E-9").employee_first_name, "Nia"
        )
        job.refresh_from_db()
        self.assertEqual(job.summary["counts"]["employees"], 1)
        self.assertEqual(job.summary["counts"]["updated"], 1)

    def test_a_row_is_matched_by_badge_id_and_shows_what_would_change(self):
        job = self.run_update(
            [{"Badge ID": "E-1", "Location": "Austin", "Last Name": "Chen-Smith"}]
        )
        self.assertEqual(job.match_keys, ["Badge ID"])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Last Name: Chen", data["html"])
        self.assertIn("Chen-Smith", data["html"])
        self.assertIn("Will Update", data["html"])

    def test_only_the_matched_person_is_changed_and_blank_cells_change_nothing(self):
        job = self.run_update(
            [{"Badge ID": "E-1", "Location": "Austin", "Last Name": None}]
        )
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        maya = Employee.objects.entire().get(pk=self.maya.pk)
        jon = Employee.objects.entire().get(pk=self.jon.pk)
        self.assertEqual(maya.employee_work_info.location, "Austin")
        self.assertEqual(maya.employee_last_name, "Chen")  # blank: left alone
        self.assertEqual(jon.employee_last_name, "Bell")  # not in the sheet
        job.refresh_from_db()
        self.assertEqual(job.summary["mode"], "update")
        self.assertEqual(job.summary["imported"], 1)

    def test_a_row_that_finds_nobody_is_an_error_not_a_new_person(self):
        job = self.run_update([{"Badge ID": "NOPE", "Location": "Austin"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 1))
        self.assertIn("No employee has this Badge ID", data["html"])
        self.assertFalse(Employee.objects.entire().filter(badge_id="NOPE").exists())

    def test_two_keys_must_agree_on_the_same_person(self):
        job = self.run_update(
            [
                {"Badge ID": "E-1", "Email": "maya@acme.test", "Location": "A"},
                {"Badge ID": "E-1", "Email": "jon@acme.test", "Location": "B"},
            ],
            keys=("Badge ID", "Email"),
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 1))
        self.assertIn("belong to different employees", data["html"])

    def test_a_person_matched_twice_in_the_sheet_is_refused(self):
        job = self.run_update(
            [{"Badge ID": "E-1", "Location": "A"}, {"Badge ID": "E-1", "Location": "B"}]
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 1))
        self.assertIn("already updated by row", data["html"])

    def test_a_row_with_nothing_different_is_unchanged_not_an_update(self):
        job = self.run_update([{"Badge ID": "E-1", "Last Name": "Chen"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 0))
        self.client.post(reverse("master-import-run", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.summary["unchanged"], 1)

    def test_email_changes_the_login_when_found_by_badge_id(self):
        job = self.run_update([{"Badge ID": "E-1", "Email": "maya.new@acme.test"}])
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        maya = Employee.objects.entire().get(pk=self.maya.pk)
        self.assertEqual(maya.email, "maya.new@acme.test")
        self.assertEqual(maya.employee_user_id.username, "maya.new@acme.test")

    def test_email_is_refused_when_taken_or_when_not_found_by_badge_id(self):
        taken = self.run_update([{"Badge ID": "E-1", "Email": "jon@acme.test"}])
        self.assertEqual(self.check(taken)["error_count"], 1)
        by_phone = self.run_update(
            [{"Phone": "9876543210", "Email": "x@acme.test"}], keys=("Phone",)
        )
        self.assertIn("found by Badge ID", self.check(by_phone)["html"])

    def test_a_row_naming_another_company_is_refused(self):
        job = self.run_update(
            [{"Badge ID": "E-1", "Company": "Elsewhere Inc", "Location": "A"}]
        )
        data = self.check(job)
        self.assertEqual(data["error_count"], 1)
        self.assertIn("does not move employees", data["html"])

    def test_new_department_names_are_created_on_update(self):
        job = self.run_update([{"Badge ID": "E-1", "Department": "Brand New Dept"}])
        self.assertEqual(self.check(job)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        maya = Employee.objects.entire().get(pk=self.maya.pk)
        self.assertEqual(
            maya.employee_work_info.department_id.department, "Brand New Dept"
        )

    def test_a_new_bank_account_needs_both_fields_and_an_existing_one_is_updated(self):
        only_bank = self.run_update(
            [{"Badge ID": "E-1", "Bank Name": "First National"}]
        )
        self.assertEqual(self.check(only_bank)["error_count"], 1)
        both = self.run_update(
            [
                {
                    "Badge ID": "E-1",
                    "Bank Name": "First National",
                    "Account Number": "123456",
                }
            ]
        )
        self.check(both)
        self.client.post(reverse("master-import-run", args=[both.pk]))
        self.assertEqual(
            EmployeeBankDetails.objects.get(employee_id=self.maya).bank_name,
            "First National",
        )
        again = self.run_update([{"Badge ID": "E-1", "Bank Name": "Second Bank"}])
        self.assertEqual(self.check(again)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[again.pk]))
        bank = EmployeeBankDetails.objects.get(employee_id=self.maya)
        self.assertEqual(
            (bank.bank_name, bank.account_number), ("Second Bank", "123456")
        )

    def test_the_map_page_asks_for_the_match_key(self):
        self.client.post(
            reverse("master-import-upload"),
            {
                "dataset": "employees",
                "mode": "update",
                "file": sheet([{"Badge ID": "E-1", "Location": "A"}]),
            },
        )
        job = ImportJob.objects.latest("pk")
        page = self.client.get(reverse("master-import-map", args=[job.pk]))
        self.assertContains(page, "Match Employees By")
        response = self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {**{f"map__{k}": v for k, v in job.mapping.items()}, "match": ["Badge ID"]},
        )
        self.assertEqual(response.status_code, 302)

    def test_badge_id_can_be_changed_when_people_are_found_by_email(self):
        job = self.run_update(
            [{"Email": "maya@acme.test", "Badge ID": "E-100"}], keys=("Email",)
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Badge ID: E-1", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(
            Employee.objects.entire().get(pk=self.maya.pk).badge_id, "E-100"
        )
        self.assertEqual(Employee.objects.entire().get(pk=self.jon.pk).badge_id, "E-2")

    def test_a_badge_id_already_in_use_is_refused_on_update(self):
        job = self.run_update(
            [{"Email": "maya@acme.test", "Badge ID": "E-2"}], keys=("Email",)
        )
        data = self.check(job)
        self.assertEqual(data["error_count"], 1)
        self.assertIn("already has this Badge ID", data["html"])

    def test_the_key_itself_is_never_changed(self):
        job = self.run_update([{"Badge ID": "E-1", "Location": "Austin"}])
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(Employee.objects.entire().get(pk=self.maya.pk).badge_id, "E-1")


class SalaryStructureColumnTests(TestCase):
    """The Salary Structure column puts a structure on the person's contract."""

    def setUp(self):
        from payroll.models.models import SalaryStructure

        self.user = make_user("structurer", is_superuser=True)
        self.company = make_company("Acme Ltd")
        make_employee(company=self.company, email="s@acme.test", user=self.user)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        self.structure = SalaryStructure.objects.create(
            title="Standard Monthly", structure_mode="gross_up"
        )

    def importing(self, rows, mode="create", keys=("Badge ID",)):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = list(keys)
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        job.refresh_from_db()
        return job

    def check(self, job):
        return self.client.post(reverse("master-import-check", args=[job.pk])).json()

    def test_the_column_is_a_field_with_a_dropdown_of_structures(self):
        field = next(f for f in EMPLOYEES.fields if f.key == "Salary Structure")
        self.assertEqual(field.group, "Pay")
        job = self.importing([{**GOOD, "Salary Structure": "Standard Monthly"}])
        html = self.check(job)["html"]
        self.assertIn('data-field="Salary Structure"', html)
        self.assertIn('<option value="Standard Monthly"', html)

    def test_a_new_person_gets_the_structure_on_their_contract(self):
        from payroll.models.models import Contract

        job = self.importing([{**GOOD, "Salary Structure": "Standard Monthly"}])
        self.assertEqual(self.check(job)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        employee = Employee.objects.entire().get(badge_id="E-1")
        contract = Contract.objects.entire().get(employee_id=employee)
        self.assertEqual(contract.salary_structure_id, self.structure)

    def test_an_unknown_structure_is_created_and_announced(self):
        from payroll.models.models import Contract, SalaryStructure

        job = self.importing([{**GOOD, "Salary Structure": "Brand New Structure"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Salary Structures", data["html"])
        self.assertIn("Brand New Structure", data["html"])
        self.assertFalse(
            SalaryStructure.objects.entire()
            .filter(title="Brand New Structure")
            .exists()
        )
        self.client.post(reverse("master-import-run", args=[job.pk]))
        made = SalaryStructure.objects.entire().get(title="Brand New Structure")
        self.assertEqual(
            made.company_id.company, "Acme Ltd"
        )  # the person's own company, made by the import
        contract = Contract.objects.entire().get(
            employee_id=Employee.objects.entire().get(badge_id="E-1")
        )
        self.assertEqual(contract.salary_structure_id, made)
        job.refresh_from_db()
        self.assertEqual(job.summary["counts"]["salary_structures"], 1)
        done = self.client.get(
            reverse("master-import-done", args=[job.pk])
        ).content.decode()
        self.assertIn("1 Salary Structures", done)

    def test_two_people_naming_one_new_structure_share_a_single_structure(self):
        from payroll.models.models import SalaryStructure

        job = self.importing(
            [
                {**GOOD, "Salary Structure": "Shared New"},
                {
                    **GOOD,
                    "Employee ID": "E-2",
                    "Work Email": "two@acme.test",
                    "Salary Structure": "Shared New",
                },
            ]
        )
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(
            SalaryStructure.objects.entire().filter(title="Shared New").count(), 1
        )

    def test_a_title_shared_by_two_companies_is_settled_by_the_persons_company(self):
        from payroll.models.models import SalaryStructure

        other = make_company("Other Co")
        SalaryStructure.objects.filter(pk=self.structure.pk).update(
            company_id=self.company
        )
        twin = SalaryStructure.objects.create(
            title="Standard Monthly", structure_mode="gross_up", company_id=other
        )
        job = self.importing([{**GOOD, "Salary Structure": "Standard Monthly"}])
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        from payroll.models.models import Contract

        contract = Contract.objects.entire().get(
            employee_id=Employee.objects.entire().get(badge_id="E-1")
        )
        self.assertEqual(contract.salary_structure_id, self.structure)
        self.assertNotEqual(contract.salary_structure_id, twin)

    def test_update_mode_changes_the_structure_of_an_existing_contract(self):
        from payroll.models.models import Contract, SalaryStructure

        person = make_employee(
            company=self.company, email="p@acme.test", first_name="Pat"
        )
        Employee.objects.filter(pk=person.pk).update(badge_id="P-1")
        other = SalaryStructure.objects.create(
            title="Other Structure", structure_mode="gross_up"
        )
        Contract.objects.entire().filter(employee_id=person).delete()
        Contract.objects.create(
            contract_name="Pat",
            employee_id=person,
            contract_start_date="2024-01-01",
            contract_status="active",
            wage=1000,
            salary_structure_id=other,
        )
        job = self.importing(
            [{"Badge ID": "P-1", "Salary Structure": "Standard Monthly"}], mode="update"
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Salary Structure: Other Structure", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        contract = Contract.objects.entire().get(employee_id=person)
        self.assertEqual(contract.salary_structure_id, self.structure)

    def test_update_mode_creates_a_missing_structure(self):
        from payroll.models.models import Contract, SalaryStructure

        person = make_employee(
            company=self.company, email="r@acme.test", first_name="Ray"
        )
        Employee.objects.filter(pk=person.pk).update(badge_id="R-1")
        Contract.objects.entire().filter(employee_id=person).delete()
        Contract.objects.create(
            contract_name="Ray",
            employee_id=person,
            contract_start_date="2024-01-01",
            contract_status="active",
            wage=1000,
        )
        job = self.importing(
            [{"Badge ID": "R-1", "Salary Structure": "Made On Update"}], mode="update"
        )
        data = self.check(job)
        self.assertEqual(data["valid"], 1)
        self.assertIn("Made On Update (new)", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        contract = Contract.objects.entire().get(employee_id=person)
        self.assertEqual(contract.salary_structure_id.title, "Made On Update")
        self.assertEqual(
            SalaryStructure.objects.entire().filter(title="Made On Update").count(), 1
        )

    def test_update_mode_without_a_contract_is_an_error(self):
        from payroll.models.models import Contract

        person = make_employee(
            company=self.company, email="q@acme.test", first_name="Quin"
        )
        Employee.objects.filter(pk=person.pk).update(badge_id="Q-1")
        Contract.objects.entire().filter(employee_id=person).delete()
        job = self.importing(
            [{"Badge ID": "Q-1", "Salary Structure": "Standard Monthly"}], mode="update"
        )
        data = self.check(job)
        self.assertEqual(data["error_count"], 1)
        self.assertIn("no contract", data["html"])


class CompanyScopeTests(TestCase):
    """Importing company by company and across all companies, with names that repeat."""

    def setUp(self):
        self.user = make_user("scoper", is_superuser=True)
        self.a = make_company("Alpha Ltd")
        self.b = make_company("Beta Ltd")
        make_employee(company=self.a, email="scoper@alpha.test", user=self.user)
        self.client.force_login(self.user)

    def select(self, company):
        session = self.client.session
        session["selected_company"] = "all" if company is None else str(company.pk)
        session.save()

    def person(self, badge, email, company=None, **extra):
        row = {
            "Employee ID": badge,
            "Full Name": extra.pop("name", "Sam Lee"),
            "Work Email": email,
            "Mobile": extra.pop("phone", "9876543210"),
            "Dept": extra.pop("dept", "Sales"),
        }
        if company is not None:
            row["Entity"] = company
        row.update(extra)
        return row

    def run_import(self, rows, mode="create", keys=("Badge ID",)):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = list(keys)
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.client.post(reverse("master-import-run", args=[job.pk]))
        job.refresh_from_db()
        return job, data

    def company_of(self, badge):
        return (
            Employee.objects.entire().get(badge_id=badge).employee_work_info.company_id
        )

    # ------------------------------------------------------- all companies
    def test_all_companies_each_row_goes_to_the_company_it_names(self):
        self.select(None)
        job, data = self.run_import(
            [
                self.person("A-1", "a1@x.test", "Alpha Ltd"),
                self.person("B-1", "b1@x.test", "Beta Ltd"),
            ]
        )
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        self.assertEqual(self.company_of("A-1"), self.a)
        self.assertEqual(self.company_of("B-1"), self.b)

    def test_all_companies_creates_a_new_company_from_its_name_only(self):
        self.select(None)
        self.run_import([self.person("N-1", "n1@x.test", "Gamma Inc")])
        gamma = Company.objects.get(company="Gamma Inc")
        self.assertIsNone(gamma.address)
        self.assertEqual(self.company_of("N-1"), gamma)

    def test_company_names_match_exactly_so_a_different_case_is_a_new_company(self):
        self.select(None)
        self.run_import([self.person("C-1", "c1@x.test", "alpha ltd")])
        self.assertTrue(Company.objects.filter(company="alpha ltd").exists())
        self.assertEqual(Company.objects.filter(company__iexact="alpha ltd").count(), 2)

    def test_all_companies_a_row_without_a_company_has_none(self):
        self.select(None)
        self.run_import([self.person("X-1", "x1@x.test")])
        self.assertIsNone(self.company_of("X-1"))

    def test_the_same_person_name_in_two_companies_imports_as_two_people(self):
        self.select(None)
        job, data = self.run_import(
            [
                self.person("S-1", "sam.a@x.test", "Alpha Ltd", name="Sam Lee"),
                self.person("S-2", "sam.b@x.test", "Beta Ltd", name="Sam Lee"),
            ]
        )
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        self.assertEqual(self.company_of("S-1"), self.a)
        self.assertEqual(self.company_of("S-2"), self.b)

    def test_a_badge_id_or_email_reused_in_another_company_is_still_refused(self):
        self.select(None)
        job, data = self.run_import(
            [
                self.person("D-1", "d1@x.test", "Alpha Ltd"),
                self.person("D-1", "d2@x.test", "Beta Ltd"),
                self.person("D-3", "d1@x.test", "Beta Ltd"),
            ]
        )
        self.assertEqual((data["valid"], data["error_count"]), (1, 2))
        self.assertEqual(
            Employee.objects.entire().filter(badge_id__in=["D-1", "D-3"]).count(), 1
        )

    def test_one_department_name_in_two_companies_is_not_duplicated_on_a_single_import(
        self,
    ):
        self.select(None)
        self.run_import(
            [
                self.person("P-1", "p1@x.test", "Alpha Ltd"),
                self.person("P-2", "p2@x.test", "Beta Ltd"),
            ]
        )
        self.assertEqual(
            Department.objects.entire().filter(department="Sales").count(), 1
        )
        first = (
            Employee.objects.entire()
            .get(badge_id="P-1")
            .employee_work_info.department_id
        )
        second = (
            Employee.objects.entire()
            .get(badge_id="P-2")
            .employee_work_info.department_id
        )
        self.assertEqual(first, second)

    # ------------------------------------------------------ company by company
    def test_one_company_a_row_without_a_company_goes_to_it(self):
        self.select(self.b)
        job, data = self.run_import([self.person("O-1", "o1@x.test")])
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertEqual(self.company_of("O-1"), self.b)

    def test_one_company_rows_naming_another_company_are_refused_and_nothing_is_created(
        self,
    ):
        self.select(self.a)
        job, data = self.run_import(
            [
                self.person("R-1", "r1@x.test", "Alpha Ltd"),
                self.person("R-2", "r2@x.test", "Beta Ltd"),
                self.person("R-3", "r3@x.test", "Brand New Co"),
            ]
        )
        self.assertEqual((data["valid"], data["error_count"]), (1, 2))
        self.assertEqual(self.company_of("R-1"), self.a)
        self.assertFalse(
            Employee.objects.entire().filter(badge_id__in=["R-2", "R-3"]).exists()
        )
        self.assertFalse(Company.objects.filter(company="Brand New Co").exists())

    def test_a_department_name_that_exists_in_another_company_is_reused_not_doubled(
        self,
    ):
        self.select(self.a)
        dept = Department.objects.create(department="Sales")
        dept.company_id.add(self.b)
        self.run_import([self.person("T-1", "t1@x.test")])
        self.assertEqual(
            Department.objects.entire().filter(department="Sales").count(), 1
        )

    # ------------------------------------------------------- structures by company
    def test_a_structure_title_in_two_companies_goes_to_each_persons_own(self):
        from payroll.models.models import Contract, SalaryStructure

        sa = SalaryStructure.objects.create(
            title="Standard", structure_mode="gross_up", company_id=self.a
        )
        sb = SalaryStructure.objects.create(
            title="Standard", structure_mode="gross_up", company_id=self.b
        )
        self.select(None)
        self.run_import(
            [
                self.person(
                    "W-1", "w1@x.test", "Alpha Ltd", **{"Salary Structure": "Standard"}
                ),
                self.person(
                    "W-2", "w2@x.test", "Beta Ltd", **{"Salary Structure": "Standard"}
                ),
            ]
        )
        contract = lambda badge: Contract.objects.entire().get(
            employee_id=Employee.objects.entire().get(badge_id=badge)
        )
        self.assertEqual(contract("W-1").salary_structure_id, sa)
        self.assertEqual(contract("W-2").salary_structure_id, sb)

    # ------------------------------------------------------------ update scope
    def test_update_in_one_company_cannot_reach_a_person_in_another(self):
        self.select(None)
        self.run_import([self.person("U-1", "u1@x.test", "Beta Ltd")])
        self.select(self.a)
        job, data = self.run_import(
            [{"Badge ID": "U-1", "Location": "Austin"}], mode="update"
        )
        self.assertEqual((data["valid"], data["error_count"]), (0, 1))
        self.assertIn("No employee has this Badge ID", data["html"])
        self.assertIsNone(
            Employee.objects.entire().get(badge_id="U-1").employee_work_info.location
        )

    def test_update_across_all_companies_reaches_each_person(self):
        self.select(None)
        self.run_import(
            [
                self.person("V-1", "v1@x.test", "Alpha Ltd"),
                self.person("V-2", "v2@x.test", "Beta Ltd"),
            ]
        )
        job, data = self.run_import(
            [
                {"Badge ID": "V-1", "Location": "One"},
                {"Badge ID": "V-2", "Location": "Two"},
            ],
            mode="update",
        )
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        location = (
            lambda badge: Employee.objects.entire()
            .get(badge_id=badge)
            .employee_work_info.location
        )
        self.assertEqual((location("V-1"), location("V-2")), ("One", "Two"))

    def test_update_never_moves_a_person_to_another_company(self):
        self.select(None)
        self.run_import([self.person("M-1", "m1@x.test", "Alpha Ltd")])
        job, data = self.run_import(
            [{"Badge ID": "M-1", "Entity": "Beta Ltd", "Location": "X"}], mode="update"
        )
        self.assertEqual(data["error_count"], 1)
        self.assertEqual(self.company_of("M-1"), self.a)


class SameNameAcrossCompaniesTests(TestCase):
    """Records that share a name in different companies must resolve to their own company's."""

    def setUp(self):
        self.user = make_user("namer", is_superuser=True)
        self.a = make_company("Alpha Ltd")
        self.b = make_company("Beta Ltd")
        make_employee(company=self.a, email="namer@alpha.test", user=self.user)
        self.client.force_login(self.user)
        # the same department, position and role names, one set per company
        self.dept = {}
        self.position = {}
        self.role = {}
        for company in (self.a, self.b):
            dept = Department.objects.create(department="Sales")
            dept.company_id.add(company)
            position = JobPosition.objects.create(
                job_position="Manager", department_id=dept
            )
            position.company_id.add(company)
            role = JobRole.objects.create(job_role="Lead", job_position_id=position)
            role.company_id.add(company)
            self.dept[company.pk], self.position[company.pk], self.role[company.pk] = (
                dept,
                position,
                role,
            )

    def select(self, company):
        session = self.client.session
        session["selected_company"] = "all" if company is None else str(company.pk)
        session.save()

    def row(self, badge, email, company, **extra):
        row = {
            "Employee ID": badge,
            "Full Name": extra.pop("name", "Pat Kim"),
            "Work Email": email,
            "Mobile": extra.pop("phone", "9876543210"),
            "Entity": company,
            "Dept": "Sales",
            "Designation": "Manager",
            "Role": "Lead",
        }
        row.update(extra)
        return row

    def run_import(self, rows, mode="create", keys=("Badge ID",)):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = list(keys)
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        data = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        self.client.post(reverse("master-import-run", args=[job.pk]))
        return data

    def info(self, badge):
        return Employee.objects.entire().get(badge_id=badge).employee_work_info

    def test_each_person_gets_their_own_companys_department_position_and_role(self):
        self.select(None)
        self.run_import(
            [
                self.row("N-1", "n1@x.test", "Alpha Ltd"),
                self.row("N-2", "n2@x.test", "Beta Ltd"),
            ]
        )
        for badge, company in (("N-1", self.a), ("N-2", self.b)):
            info = self.info(badge)
            self.assertEqual(info.department_id, self.dept[company.pk], badge)
            self.assertEqual(info.job_position_id, self.position[company.pk], badge)
            self.assertEqual(info.job_role_id, self.role[company.pk], badge)

    def test_nothing_is_duplicated_when_each_company_already_has_its_own(self):
        self.select(None)
        self.run_import(
            [
                self.row("N-3", "n3@x.test", "Alpha Ltd"),
                self.row("N-4", "n4@x.test", "Beta Ltd"),
            ]
        )
        self.assertEqual(
            Department.objects.entire().filter(department="Sales").count(), 2
        )
        self.assertEqual(
            JobPosition.objects.entire().filter(job_position="Manager").count(), 2
        )
        self.assertEqual(JobRole.objects.entire().filter(job_role="Lead").count(), 2)

    def test_importing_into_one_company_uses_that_companys_records(self):
        self.select(self.b)
        self.run_import([self.row("N-5", "n5@x.test", "Beta Ltd")])
        info = self.info("N-5")
        self.assertEqual(info.department_id, self.dept[self.b.pk])
        self.assertEqual(info.job_position_id, self.position[self.b.pk])

    def test_a_reporting_manager_named_the_same_in_two_companies_is_the_persons_own(
        self,
    ):
        boss_a = make_employee(
            company=self.a, email="boss@alpha.test", first_name="Alex"
        )
        boss_b = make_employee(
            company=self.b, email="boss@beta.test", first_name="Alex"
        )
        for boss in (boss_a, boss_b):
            Employee.objects.filter(pk=boss.pk).update(employee_last_name="Boss")
        self.select(None)
        self.run_import(
            [
                self.row("N-6", "n6@x.test", "Alpha Ltd", **{"Manager": "Alex Boss"}),
                self.row("N-7", "n7@x.test", "Beta Ltd", **{"Manager": "Alex Boss"}),
            ]
        )
        self.assertEqual(self.info("N-6").reporting_manager_id, boss_a)
        self.assertEqual(self.info("N-7").reporting_manager_id, boss_b)

    def test_update_gives_the_person_their_own_companys_department(self):
        self.select(None)
        self.run_import([self.row("N-8", "n8@x.test", "Alpha Ltd", Dept="Other")])
        self.run_import([{"Badge ID": "N-8", "Dept": "Sales"}], mode="update")
        self.assertEqual(self.info("N-8").department_id, self.dept[self.a.pk])
        self.run_import([self.row("N-9", "n9@x.test", "Beta Ltd", Dept="Other")])
        self.run_import([{"Badge ID": "N-9", "Dept": "Sales"}], mode="update")
        self.assertEqual(self.info("N-9").department_id, self.dept[self.b.pk])

    def test_update_reporting_manager_is_the_persons_own_companys(self):
        boss_a = make_employee(company=self.a, email="ba@alpha.test", first_name="Alex")
        boss_b = make_employee(company=self.b, email="bb@beta.test", first_name="Alex")
        for boss in (boss_a, boss_b):
            Employee.objects.filter(pk=boss.pk).update(employee_last_name="Boss")
        self.select(None)
        self.run_import([self.row("N-10", "n10@x.test", "Beta Ltd")])
        self.run_import([{"Badge ID": "N-10", "Manager": "Alex Boss"}], mode="update")
        self.assertEqual(self.info("N-10").reporting_manager_id, boss_b)

    def test_the_review_does_not_announce_records_that_already_exist_in_the_persons_company(
        self,
    ):
        self.select(None)
        data = self.run_import(
            [
                self.row("N-11", "n11@x.test", "Alpha Ltd"),
                self.row("N-12", "n12@x.test", "Beta Ltd"),
            ]
        )
        self.assertNotIn(
            "Departments",
            (
                data["html"].split("These do not exist yet")[-1][:400]
                if "These do not exist yet" in data["html"]
                else ""
            ),
        )


class AssignedLeaveTests(TestCase):
    """Importing leave balances: Badge ID, Leave Type and days, nothing more."""

    def setUp(self):
        from horilla.testkit.factories import make_leave_type

        self.user = make_user("leaver", is_superuser=True)
        self.company = make_company("Acme Ltd")
        make_employee(company=self.company, email="leaver@acme.test", user=self.user)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        self.maya = make_employee(
            company=self.company, email="maya@acme.test", first_name="Maya"
        )
        Employee.objects.filter(pk=self.maya.pk).update(badge_id="E-1")
        self.casual = make_leave_type("Casual Leave", total_days=12)

    def run_import(self, rows):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "assigned_leave", "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        job.refresh_from_db()
        return job

    def check(self, job):
        return self.client.post(reverse("master-import-check", args=[job.pk])).json()

    def test_the_template_has_the_simple_columns(self):
        response = self.client.get(
            reverse("master-import-template", args=["assigned_leave"])
        )
        columns = list(pd.read_excel(io.BytesIO(response.content)).columns)
        self.assertEqual(
            columns,
            [
                "Badge ID",
                "Leave Type",
                "Available Days",
                "Carryforward Days",
                "Assigned Date",
            ],
        )

    def test_blank_days_are_zero_and_the_balance_is_assigned(self):
        from leave.models import AvailableLeave

        job = self.run_import([{"Badge ID": "E-1", "Leave Type": "casual leave"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.client.post(reverse("master-import-run", args=[job.pk]))
        leave = AvailableLeave.objects.entire().get(
            employee_id=self.maya, leave_type_id=self.casual
        )
        self.assertEqual(
            (leave.available_days, leave.carryforward_days, leave.total_leave_days),
            (0, 0, 0),
        )
        job.refresh_from_db()
        self.assertEqual(job.summary["counts"]["assigned"], 1)

    def test_given_days_and_carryforward_make_the_total(self):
        from leave.models import AvailableLeave

        job = self.run_import(
            [
                {
                    "Badge ID": "E-1",
                    "Leave Type": "Casual Leave",
                    "Available Days": "8",
                    "Carryforward Days": "2",
                }
            ]
        )
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        leave = AvailableLeave.objects.entire().get(employee_id=self.maya)
        self.assertEqual(
            (leave.available_days, leave.carryforward_days, leave.total_leave_days),
            (8, 2, 10),
        )

    def test_unknown_badge_and_bad_days_are_row_errors(self):
        job = self.run_import(
            [
                {"Badge ID": "NOPE", "Leave Type": "Casual Leave"},
                {
                    "Badge ID": "E-1",
                    "Leave Type": "Casual Leave",
                    "Available Days": "-3",
                },
            ]
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 2))
        self.assertIn("No employee has this Badge ID", data["html"])
        self.assertIn("non-negative", data["html"])

    def test_a_leave_type_that_does_not_exist_is_created_by_the_import(self):
        from leave.models import AvailableLeave, LeaveType

        job = self.run_import(
            [
                {"Badge ID": "E-1", "Leave Type": "Study Leave", "Available Days": "5"},
                {"Badge ID": "E-1", "Leave Type": "study leave"},
            ]
        )
        data = self.check(job)
        self.assertEqual(data["error_count"], 1)  # the same pair twice
        self.assertIn("Leave Types", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        study = LeaveType.objects.entire().get(name="Study Leave")
        self.assertEqual(study.total_days, 5)
        self.assertEqual(
            AvailableLeave.objects.entire().get(leave_type_id=study).available_days, 5
        )
        job.refresh_from_db()
        self.assertEqual(job.summary["counts"]["leave_types"], 1)

    def test_an_already_assigned_or_repeated_balance_is_refused(self):
        from horilla.testkit.factories import make_available_leave

        job = self.run_import([{"Badge ID": "E-1", "Leave Type": "Casual Leave"}] * 2)
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 1))
        self.assertIn("more than once", data["html"])
        make_available_leave(employee=self.maya, leave_type=self.casual)
        job = self.run_import([{"Badge ID": "E-1", "Leave Type": "Casual Leave"}])
        self.assertIn("already assigned", self.check(job)["html"])

    def run_mode(self, rows, mode):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "assigned_leave", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.assertEqual((job.mode, job.match_keys), (mode, ["Badge ID", "Leave Type"]))
        response = self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        return job

    def assign(self, available=8, carry=1):
        from horilla.testkit.factories import make_available_leave
        from leave.models import AvailableLeave

        make_available_leave(
            employee=self.maya, leave_type=self.casual, available=available
        )
        AvailableLeave.objects.entire().filter(employee_id=self.maya).update(
            carryforward_days=carry, total_leave_days=available + carry
        )

    def test_update_changes_only_what_the_sheet_fills_in(self):
        from leave.models import AvailableLeave

        self.assign(8, 1)
        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave", "Available Days": "15"}],
            "update",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Available Days: 8.0", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        leave = AvailableLeave.objects.entire().get(employee_id=self.maya)
        self.assertEqual(
            (leave.available_days, leave.carryforward_days, leave.total_leave_days),
            (15, 1, 16),
        )

    def test_update_refuses_a_balance_that_was_never_assigned_and_a_missing_type(self):
        job = self.run_mode(
            [
                {
                    "Badge ID": "E-1",
                    "Leave Type": "Casual Leave",
                    "Available Days": "3",
                },
                {"Badge ID": "E-1", "Leave Type": "Nothing", "Available Days": "3"},
            ],
            "update",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 2))
        self.assertIn("not assigned to the employee yet", data["html"])
        self.assertIn("does not exist", data["html"])

    def test_a_row_with_nothing_different_is_unchanged(self):
        self.assign(8, 1)
        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave", "Available Days": "8"}],
            "update",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 0))

    def test_create_or_update_updates_existing_balances_and_assigns_the_rest(self):
        from horilla.testkit.factories import make_leave_type
        from leave.models import AvailableLeave, LeaveType

        self.assign(8, 0)
        make_leave_type("Sick Leave", total_days=6)
        job = self.run_mode(
            [
                {
                    "Badge ID": "E-1",
                    "Leave Type": "Casual Leave",
                    "Available Days": "10",
                },
                {"Badge ID": "E-1", "Leave Type": "Sick Leave", "Available Days": "4"},
            ],
            "both",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        self.assertIn("Will Create", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(
            AvailableLeave.objects.entire()
            .get(employee_id=self.maya, leave_type_id=self.casual)
            .available_days,
            10,
        )
        sick = LeaveType.objects.entire().get(name="Sick Leave")
        self.assertEqual(
            AvailableLeave.objects.entire()
            .get(employee_id=self.maya, leave_type_id=sick)
            .available_days,
            4,
        )
        job.refresh_from_db()
        self.assertEqual(
            (job.summary["counts"]["assigned"], job.summary["counts"]["updated"]),
            (1, 1),
        )

    def test_the_match_rules_are_fixed_to_badge_id_and_leave_type(self):
        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave"}], "update"
        )
        page = self.client.get(reverse("master-import-map", args=[job.pk]))
        self.assertContains(page, "Match Records By")
        html = page.content.decode()
        self.assertEqual(html.count('name="match"'), 2)
        self.assertEqual(html.count('disabled title="Always used"'), 2)

    def test_an_update_with_nothing_different_says_why_it_is_empty(self):
        self.assign(8, 1)
        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave", "Available Days": "8"}],
            "update",
        )
        self.assertIn("already have these values", self.check(job)["html"])

    def test_imported_and_updated_balances_appear_in_the_leave_ledger(self):
        from leave.models import AvailableLeave

        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave", "Available Days": "8"}],
            "both",
        )
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        leave = AvailableLeave.objects.entire().get(employee_id=self.maya)
        self.assertEqual(leave.history.count(), 1)
        self.assertEqual(
            [e["label"] for e in leave.build_ledger()][:1], ["Initial assignment"]
        )

        job = self.run_mode(
            [{"Badge ID": "E-1", "Leave Type": "Casual Leave", "Available Days": "11"}],
            "both",
        )
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        leave = AvailableLeave.objects.entire().get(employee_id=self.maya)
        self.assertEqual(leave.history.count(), 2)
        labels = [e["label"] for e in leave.build_ledger()]
        self.assertIn("Updated through Master Data Import", labels)


class AssetAllocationTests(TestCase):
    """Giving assets to employees; the asset, category and batch are made when new."""

    def setUp(self):
        self.user = make_user("assetman", is_superuser=True)
        self.company = make_company("Acme Ltd")
        self.me = make_employee(
            company=self.company, email="assetman@acme.test", user=self.user
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        self.maya = make_employee(
            company=self.company, email="maya@acme.test", first_name="Maya"
        )
        Employee.objects.filter(pk=self.maya.pk).update(badge_id="E-1")

    ROW = {
        "Badge ID": "E-1",
        "Serial No.": "LAP-1",
        "Asset Name": "Laptop",
        "Category": "Electronics",
        "Purchase Date": "2024-01-10",
        "Purchase Cost": "55000",
        "Batch Number": "B-01",
    }

    def run_import(self, rows):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "asset_allocation", "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        job.refresh_from_db()
        return job

    def check(self, job):
        return self.client.post(reverse("master-import-check", args=[job.pk])).json()

    def test_a_new_asset_category_and_batch_are_created_and_the_asset_is_given_out(
        self,
    ):
        from asset.models import Asset, AssetAssignment, AssetCategory, AssetLot

        job = self.run_import([{**self.ROW, "Assigned Date": "2024-02-01"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Asset Categories", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        asset = Asset.objects.entire().get(asset_tracking_id="LAP-1")
        self.assertEqual(asset.asset_category_id.asset_category_name, "Electronics")
        self.assertEqual(asset.asset_lot_number_id.lot_number, "B-01")
        self.assertEqual(asset.asset_status, "In use")
        given = AssetAssignment.objects.entire().get(asset_id=asset)
        self.assertEqual(given.assigned_to_employee_id, self.maya)
        self.assertEqual(given.assigned_by_employee_id, self.me)
        self.assertEqual(str(given.assigned_date), "2024-02-01")
        self.assertEqual(given.asset_item_id.status, "In use")
        job.refresh_from_db()
        self.assertEqual(
            (
                job.summary["counts"]["assets"],
                job.summary["counts"]["categories"],
                job.summary["counts"]["batches"],
            ),
            (1, 1, 1),
        )
        self.assertEqual(AssetCategory.objects.entire().count(), 1)
        self.assertEqual(AssetLot.objects.entire().count(), 1)

    def test_an_existing_asset_needs_only_the_serial_and_the_employee(self):
        from asset.models import AssetAssignment

        first = self.run_import([{**self.ROW, "Quantity": "2"}])
        self.check(first)
        self.client.post(reverse("master-import-run", args=[first.pk]))
        other = make_employee(
            company=self.company, email="jon@acme.test", first_name="Jon"
        )
        Employee.objects.filter(pk=other.pk).update(badge_id="E-2")
        job = self.run_import([{"Badge ID": "E-2", "Serial No.": "LAP-1"}])
        self.assertEqual(self.check(job)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(AssetAssignment.objects.entire().count(), 2)

    def test_a_new_asset_without_its_details_and_an_unknown_employee_are_row_errors(
        self,
    ):
        job = self.run_import(
            [
                {"Badge ID": "E-1", "Serial No.": "NEW-1"},
                {**self.ROW, "Badge ID": "NOPE", "Serial No.": "LAP-2"},
            ]
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 2))
        self.assertIn("Asset Name is needed to create asset NEW-1", data["html"])
        self.assertIn("No employee has this Badge ID", data["html"])

    def test_a_single_unit_cannot_be_given_to_two_people_at_once(self):
        other = make_employee(
            company=self.company, email="jon@acme.test", first_name="Jon"
        )
        Employee.objects.filter(pk=other.pk).update(badge_id="E-2")
        job = self.run_import([self.ROW, {**self.ROW, "Badge ID": "E-2"}])
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 1))
        self.assertIn("No unit of this asset is free", data["html"])

    def test_a_row_with_a_return_date_is_recorded_as_returned(self):
        from asset.models import Asset, AssetAssignment

        job = self.run_import(
            [
                {
                    **self.ROW,
                    "Assigned Date": "2024-02-01",
                    "Return Date": "2024-03-01",
                    "Return Status": "healthy",
                }
            ]
        )
        self.assertEqual(self.check(job)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        given = AssetAssignment.objects.entire().get()
        self.assertEqual(
            (str(given.return_date), given.return_status), ("2024-03-01", "Healthy")
        )
        self.assertEqual(Asset.objects.entire().get().asset_status, "Available")

    def test_the_template_has_every_column(self):
        response = self.client.get(
            reverse("master-import-template", args=["asset_allocation"])
        )
        columns = list(pd.read_excel(io.BytesIO(response.content)).columns)
        self.assertIn("Serial No.", columns)
        self.assertIn("Warranty Expiry Date", columns)
        self.assertEqual(len(columns), 17)

    def run_mode(self, rows, mode):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "asset_allocation", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.assertEqual((job.mode, job.match_keys), (mode, ["Badge ID", "Serial No."]))
        self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        job.refresh_from_db()
        return job

    def give(self, **extra):
        job = self.run_import([{**self.ROW, **extra}])
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))

    def test_update_changes_the_asset_and_the_allocation_only_where_filled_in(self):
        from asset.models import Asset, AssetAssignment

        self.give(Quantity="2")
        job = self.run_mode(
            [
                {
                    "Badge ID": "E-1",
                    "Serial No.": "LAP-1",
                    "Asset Name": "Laptop Pro",
                    "Quantity": "3",
                    "Category": "Computers",
                    "Assigned Date": "2024-05-05",
                }
            ],
            "update",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (1, 0))
        self.assertIn("Asset Name: Laptop", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        asset = Asset.objects.entire().get(asset_tracking_id="LAP-1")
        self.assertEqual(
            (
                asset.asset_name,
                asset.quantity,
                asset.asset_category_id.asset_category_name,
            ),
            ("Laptop Pro", 3, "Computers"),
        )
        self.assertEqual(asset.asset_items.count(), 3)
        self.assertEqual(
            asset.asset_purchase_cost, 55000
        )  # not in the sheet: left alone
        self.assertEqual(
            str(AssetAssignment.objects.entire().get().assigned_date), "2024-05-05"
        )

    def test_update_can_return_an_asset_and_frees_its_unit(self):
        from asset.models import Asset, AssetAssignment

        self.give(**{"Assigned Date": "2024-02-01"})
        job = self.run_mode(
            [
                {
                    "Badge ID": "E-1",
                    "Serial No.": "LAP-1",
                    "Return Date": "2024-09-09",
                    "Return Condition": "Fine",
                }
            ],
            "update",
        )
        self.assertEqual(self.check(job)["valid"], 1)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        given = AssetAssignment.objects.entire().get()
        self.assertEqual(
            (str(given.return_date), given.return_status, given.return_condition),
            ("2024-09-09", "Healthy", "Fine"),
        )
        self.assertEqual(Asset.objects.entire().get().asset_status, "Available")

    def test_update_refuses_what_does_not_exist_or_cannot_be_done(self):
        self.give(Quantity="2")
        job = self.run_mode(
            [
                {"Badge ID": "E-1", "Serial No.": "NOPE", "Asset Name": "x"},
                {"Badge ID": "E-1", "Serial No.": "LAP-1", "Quantity": "1"},
            ],
            "update",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 2))
        self.assertIn("This asset does not exist", data["html"])
        self.assertIn("Quantity can only be raised", data["html"])

    def test_create_or_update_updates_the_held_asset_and_gives_out_the_rest(self):
        from asset.models import Asset, AssetAssignment

        self.give()
        other = make_employee(
            company=self.company, email="jon@acme.test", first_name="Jon"
        )
        Employee.objects.filter(pk=other.pk).update(badge_id="E-2")
        job = self.run_mode(
            [
                {"Badge ID": "E-1", "Serial No.": "LAP-1", "Asset Name": "Laptop Pro"},
                {
                    **self.ROW,
                    "Badge ID": "E-2",
                    "Serial No.": "LAP-2",
                    "Asset Name": "Laptop Two",
                },
            ],
            "both",
        )
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (2, 0))
        self.assertIn("Will Create", data["html"])
        self.client.post(reverse("master-import-run", args=[job.pk]))
        self.assertEqual(
            Asset.objects.entire().get(asset_tracking_id="LAP-1").asset_name,
            "Laptop Pro",
        )
        self.assertEqual(AssetAssignment.objects.entire().count(), 2)
        job.refresh_from_db()
        self.assertEqual(
            (job.summary["counts"]["assigned"], job.summary["counts"]["updated"]),
            (1, 1),
        )

    def test_the_match_rules_are_locked(self):
        job = self.run_mode([{"Badge ID": "E-1", "Serial No.": "LAP-1"}], "update")
        html = self.client.get(
            reverse("master-import-map", args=[job.pk])
        ).content.decode()
        self.assertEqual(html.count('name="match"'), 2)
        self.assertEqual(html.count('disabled title="Always used"'), 2)


class HtmxNavigationTests(TestCase):
    """The wizard swaps the settings panel as it moves, instead of reloading the page."""

    def setUp(self):
        self.user = make_user("htmxer", is_superuser=True)
        make_employee(
            company=make_company("Home"), email="htmxer@home.test", user=self.user
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def test_the_wizard_swaps_the_settings_panel(self):
        html = self.client.get(reverse("master-import")).content.decode()
        self.assertIn('hx-boost="true"', html)
        self.assertIn('hx-target="#settingsContainer"', html)
        self.assertIn('hx-select="#settingsContainer"', html)
        self.assertIn('hx-push-url="true"', html)
        self.assertIn("miGo(", html)  # the dataset dropdown
        self.assertIn('data-settings-active="/master-import/"', html)

    def test_downloads_are_not_swapped_in(self):
        html = self.client.get(reverse("master-import")).content.decode()
        template = html[
            html.index(reverse("master-import-template", args=["employees"])) - 80 :
        ]
        self.assertIn('hx-boost="false"', template[:200])

    def test_the_history_page_lights_its_own_menu_item(self):
        html = self.client.get(reverse("master-import-history")).content.decode()
        self.assertIn('data-settings-active="/master-import/history/"', html)


class AssetsDatasetTests(TestCase):
    """The asset register: new, update and both, with no employee involved."""

    def setUp(self):
        self.user = make_user("registrar", is_superuser=True)
        make_employee(
            company=make_company("Acme Ltd"),
            email="registrar@acme.test",
            user=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    ROW = {
        "Serial No.": "LAP-1",
        "Asset Name": "Laptop",
        "Category": "Electronics",
        "Purchase Date": "2024-01-10",
        "Purchase Cost": "55000",
        "Batch Number": "B-01",
        "Batch Description": "First lot",
        "Quantity": "2",
        "Warranty Expiry Date": "2027-01-10",
        "Notify Before (Days)": "30",
    }

    def run_mode(self, rows, mode):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "assets", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        self.assertEqual(job.mode, mode)
        self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        job.refresh_from_db()
        return job

    def check(self, job):
        return self.client.post(reverse("master-import-check", args=[job.pk])).json()

    def execute(self, job):
        self.check(job)
        self.client.post(reverse("master-import-run", args=[job.pk]))
        job.refresh_from_db()
        return job

    def test_the_template_has_every_asset_column_and_needs_no_badge_id(self):
        response = self.client.get(reverse("master-import-template", args=["assets"]))
        columns = list(pd.read_excel(io.BytesIO(response.content)).columns)
        self.assertEqual(len(columns), 12)
        self.assertNotIn("Badge ID", columns)

    def test_new_assets_are_created_with_their_category_batch_and_units(self):
        from asset.models import Asset, AssetCategory, AssetLot

        job = self.execute(self.run_mode([self.ROW], "create"))
        asset = Asset.objects.entire().get(asset_tracking_id="LAP-1")
        self.assertEqual(
            (asset.quantity, asset.asset_items.count(), asset.notify_before), (2, 2, 30)
        )
        self.assertEqual(asset.asset_lot_number_id.lot_description, "First lot")
        self.assertEqual(AssetCategory.objects.entire().count(), 1)
        self.assertEqual(AssetLot.objects.entire().count(), 1)
        self.assertEqual(job.summary["counts"]["categories"], 1)

    def test_an_existing_serial_is_refused_when_creating_and_missing_details_are_errors(
        self,
    ):
        self.execute(self.run_mode([self.ROW], "create"))
        job = self.run_mode([self.ROW, {"Serial No.": "NEW-1"}], "create")
        data = self.check(job)
        self.assertEqual((data["valid"], data["error_count"]), (0, 2))
        self.assertIn("already exists", data["html"])
        self.assertIn("Asset Name is needed to create asset NEW-1", data["html"])

    def test_update_changes_only_what_is_filled_in(self):
        from asset.models import Asset

        self.execute(self.run_mode([self.ROW], "create"))
        job = self.execute(
            self.run_mode(
                [{"Serial No.": "LAP-1", "Asset Name": "Laptop Pro", "Quantity": "3"}],
                "update",
            )
        )
        asset = Asset.objects.entire().get(asset_tracking_id="LAP-1")
        self.assertEqual(
            (asset.asset_name, asset.quantity, asset.asset_items.count()),
            ("Laptop Pro", 3, 3),
        )
        self.assertEqual(asset.asset_purchase_cost, 55000)
        self.assertEqual(job.summary["imported"], 1)

    def test_update_refuses_an_unknown_serial(self):
        job = self.run_mode([{"Serial No.": "NOPE", "Asset Name": "x"}], "update")
        self.assertIn("This asset does not exist", self.check(job)["html"])

    def test_create_or_update_updates_existing_and_creates_new(self):
        from asset.models import Asset

        self.execute(self.run_mode([self.ROW], "create"))
        job = self.execute(
            self.run_mode(
                [
                    {"Serial No.": "LAP-1", "Asset Description": "Updated"},
                    {**self.ROW, "Serial No.": "LAP-2", "Quantity": "1"},
                ],
                "both",
            )
        )
        self.assertEqual(
            Asset.objects.entire().get(asset_tracking_id="LAP-1").asset_description,
            "Updated",
        )
        self.assertTrue(
            Asset.objects.entire().filter(asset_tracking_id="LAP-2").exists()
        )
        self.assertEqual(
            (job.summary["counts"]["assigned"], job.summary["counts"]["updated"]),
            (1, 1),
        )


class SetupChecklistTests(TestCase):
    """The dashboard's Get Started checklist offers Import Data as an optional step."""

    def checklist(self):
        from django.test import override_settings

        user = make_user("setupper", is_superuser=True)
        make_employee(
            company=make_company("Home"), email="setupper@home.test", user=user
        )
        self.client.force_login(user)
        with override_settings(DEBUG=True):
            response = self.client.get("/dashboard/?preview_checklist=1")
        return user, response.context

    def test_import_data_is_a_step_that_links_to_the_import(self):
        _user, context = self.checklist()
        step = next(s for s in context["setup_steps"] if s["key"] == "master_import")
        self.assertEqual(step["url"], reverse("master-import"))
        self.assertTrue(step["optional"])
        self.assertFalse(step["done"])

    def test_a_finished_import_ticks_the_step(self):
        ImportJob.objects.create(
            dataset="employees", original_name="a.xlsx", status=ImportJob.DONE
        )
        _user, context = self.checklist()
        # preview mode shows every step as open, so ask the step builder without it
        from django.test import RequestFactory

        from base.dashboard import _get_setup_checklist_context

        request = RequestFactory().get("/dashboard/")
        request.user = _user
        request.session = self.client.session
        result = _get_setup_checklist_context(request)
        steps = {s["key"]: s["done"] for s in result.get("setup_steps", [])}
        self.assertTrue(steps["master_import"])


class AccessTests(TestCase):
    """Who may import, update, and see whose import."""

    def user_with(self, name, *perms, superuser=False):
        from django.contrib.auth.models import Permission

        user = make_user(name, is_superuser=superuser)
        make_employee(
            company=make_company(f"Home {name}"), email=f"{name}@home.test", user=user
        )
        for code in perms:
            app, codename = code.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app, codename=codename)
            )
        user = type(user).objects.get(pk=user.pk)
        self.client.force_login(user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        return user

    def upload(self, dataset="employees", mode="create"):
        return self.client.post(
            reverse("master-import-upload"),
            {
                "dataset": dataset,
                "mode": mode,
                "file": sheet(
                    [
                        {
                            "Badge ID": "E-1",
                            "First Name": "A",
                            "Email": "a@a.test",
                            "Phone": "9876543210",
                        }
                    ]
                ),
            },
        )

    def test_a_visitor_who_is_not_signed_in_is_sent_to_login(self):
        self.client.logout()
        for name in ("master-import", "master-import-history"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_adding_does_not_allow_updating(self):
        self.user_with("adder", "employee.add_employee")
        self.upload(mode="update")
        self.assertFalse(ImportJob.objects.exists())
        self.upload(mode="both")
        self.assertFalse(ImportJob.objects.exists())
        self.upload(mode="create")
        self.assertEqual(ImportJob.objects.count(), 1)

    def test_changing_as_well_allows_updating(self):
        self.user_with("changer", "employee.add_employee", "employee.change_employee")
        self.upload(mode="update")
        self.assertEqual(ImportJob.objects.get().mode, "update")

    def test_the_update_options_are_not_offered_without_the_change_permission(self):
        self.user_with("adder2", "employee.add_employee")
        html = self.client.get(reverse("master-import")).content.decode()
        self.assertNotIn('value="update"', html)
        self.user_with("changer2", "employee.add_employee", "employee.change_employee")
        self.assertIn(
            'value="update"', self.client.get(reverse("master-import")).content.decode()
        )

    def test_an_update_job_is_closed_to_someone_who_lost_the_change_permission(self):
        self.user_with("owner", "employee.add_employee", "employee.change_employee")
        self.upload(mode="update")
        job = ImportJob.objects.get()
        self.assertEqual(
            self.client.get(reverse("master-import-map", args=[job.pk])).status_code,
            200,
        )
        self.client.logout()
        weaker = self.user_with("weaker", "employee.add_employee")
        ImportJob.objects.filter(pk=job.pk).update(created_by=weaker)
        self.assertEqual(
            self.client.get(reverse("master-import-map", args=[job.pk])).status_code,
            404,
        )

    def test_nobody_sees_another_users_import_but_a_superuser_does(self):
        self.user_with("owner2", "employee.add_employee")
        self.upload()
        job = ImportJob.objects.get()
        ImportJob.objects.filter(pk=job.pk).update(original_name="private.xlsx")
        self.client.logout()
        self.user_with("other", "employee.add_employee")
        for name in (
            "master-import-map",
            "master-import-review",
            "master-import-done",
            "master-import-check-progress",
        ):
            self.assertEqual(
                self.client.get(reverse(name, args=[job.pk])).status_code, 404, name
            )
        self.assertNotContains(
            self.client.get(reverse("master-import-history")), "private.xlsx"
        )
        self.client.logout()
        self.user_with("boss", superuser=True)
        self.assertContains(
            self.client.get(reverse("master-import-history")), "private.xlsx"
        )

    def test_an_import_for_a_dataset_the_user_may_not_use_is_closed(self):
        self.user_with("leaveless", "employee.add_employee")
        self.client.post(
            reverse("master-import-upload"),
            {
                "dataset": "assigned_leave",
                "file": sheet([{"Badge ID": "E-1", "Leave Type": "x"}]),
            },
        )
        self.assertFalse(ImportJob.objects.exists())

    def test_passwords_are_not_kept_or_written_back_out(self):
        import io as _io

        owner = self.user_with("keeper", "employee.add_employee")
        self.client.post(
            reverse("master-import-upload"),
            {
                "dataset": "employees",
                "file": sheet(
                    [
                        {
                            "Badge ID": "E-1",
                            "First Name": "A",
                            "Email": "a@a.test",
                            "Phone": "9876543210",
                            "Password": "Secret#123",
                        },
                        {
                            "Badge ID": "E-2",
                            "First Name": "B",
                            "Email": "bad",
                            "Phone": "9876543211",
                            "Password": "Hidden#456",
                        },
                    ]
                ),
            },
        )
        job = ImportJob.objects.get()
        self.client.post(
            reverse("master-import-map", args=[job.pk]),
            {f"map__{k}": v for k, v in job.mapping.items()},
        )
        self.client.post(reverse("master-import-check", args=[job.pk]))
        errors = self.client.get(
            reverse("master-import-download", args=[job.pk, "errors"])
        )
        self.assertNotIn(b"Hidden#456", errors.content)
        self.assertEqual(
            pd.read_excel(_io.BytesIO(errors.content))["Password"].tolist(),
            ["********"],
        )
        self.client.post(reverse("master-import-run", args=[job.pk]))
        job.refresh_from_db()
        self.assertFalse(job.file)  # the sheet with the passwords is not kept
        self.assertEqual(job.edits, {})
        self.assertEqual(
            self.client.get(
                reverse("master-import-download", args=[job.pk, "valid"])
            ).status_code,
            404,
        )
        self.assertNotIn("Secret#123", str(job.summary))
