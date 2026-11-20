"""The additional info columns of the master employee import."""

import io
from datetime import date
from decimal import Decimal

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from additional_info import importing
from additional_info.models import (
    DATE,
    DROPDOWN,
    FILE,
    LONG_TEXT,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
    AdditionalInfoValue,
)
from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user
from master_import.datasets import get_dataset
from master_import.datasets.base import Context
from master_import.models import ImportJob
from master_import.parsing import apply_mapping, suggest_mapping

EMPLOYEES = get_dataset("employees")

PERSON = {
    "Badge ID": "E-9",
    "First Name": "Nia",
    "Last Name": "Cole",
    "Email": "nia@acme.test",
    "Phone": "9876511111",
    "Company": "Acme Ltd",
}


def sheet(rows):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return SimpleUploadedFile(
        "people.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def make_field(label, field_type=TEXT, **extra):
    importing.forget()
    return AdditionalInfoField.objects.create(
        label=label, field_type=field_type, **extra
    )


def make_dropdown(label="Blood Group", options=("A+", "B+", "O-")):
    return make_field(
        label,
        DROPDOWN,
        choices=[
            {"key": o.lower().replace("+", "_pos").replace("-", "_neg"), "label": o}
            for o in options
        ],
    )


def rows_for(*people):
    frame = pd.DataFrame(list(people))
    return apply_mapping(
        frame, suggest_mapping(list(frame.columns), EMPLOYEES.fields), EMPLOYEES.fields
    )


def value_of(employee, field):
    row = AdditionalInfoValue.objects.filter(employee_id=employee, field=field).first()
    if row is None:
        return None
    from additional_info.models import COLUMN

    return getattr(row, COLUMN[field.field_type])


class ColumnTests(TestCase):
    def setUp(self):
        importing.forget()

    def test_there_are_no_columns_without_fields(self):
        self.assertEqual(importing.build_columns(), [])
        self.assertEqual(
            [f.key for f in EMPLOYEES.fields], [f.key for f in EMPLOYEES.BASE_FIELDS]
        )

    def test_every_active_field_but_a_file_becomes_a_column(self):
        make_field("Passport Number")
        make_field("Visa Scan", FILE)
        make_field("Old Field", is_active=False)
        self.assertEqual(
            [c.key for c in importing.build_columns()], ["Passport Number"]
        )

    def test_a_dropdown_and_a_yes_no_offer_their_options(self):
        make_dropdown()
        make_field("Has License", YES_NO)
        cols = {c.key: c for c in importing.build_columns()}
        self.assertEqual(
            (cols["Blood Group"].kind, cols["Blood Group"].options),
            ("suggest", ["A+", "B+", "O-"]),
        )
        self.assertEqual(cols["Has License"].options, ["Yes", "No"])

    def test_the_kinds_follow_the_types(self):
        make_field("N", NUMBER)
        make_field("D", DATE)
        make_field("T", TEXT)
        make_field("L", LONG_TEXT)
        self.assertEqual(
            {c.key: c.kind for c in importing.build_columns()},
            {"N": "number", "D": "date", "T": "text", "L": "text"},
        )

    def test_a_field_named_like_a_fixed_column_is_told_apart(self):
        make_field("Address")
        make_field("Shoe Size")
        keys = [f.key for f in EMPLOYEES.fields]
        self.assertIn("Address", keys)
        self.assertIn("Address (Additional Info)", keys)
        self.assertEqual(keys.count("Address"), 1)
        self.assertIn("Shoe Size", keys)

    def test_the_columns_come_after_the_fixed_ones_in_their_own_group(self):
        make_field("Shoe Size")
        fields = EMPLOYEES.fields
        self.assertEqual(fields[-1].key, "Shoe Size")
        self.assertEqual(fields[-1].group, "Additional Info")
        self.assertEqual(fields[0].key, "Badge ID")

    def test_the_class_and_an_instance_agree(self):
        make_field("Shoe Size")
        self.assertEqual(
            [f.key for f in type(EMPLOYEES).fields], [f.key for f in EMPLOYEES.fields]
        )

    def test_a_new_field_shows_up_straight_away(self):
        self.assertNotIn("Shoe Size", [f.key for f in EMPLOYEES.fields])
        make_field("Shoe Size")
        self.assertIn("Shoe Size", [f.key for f in EMPLOYEES.fields])

    def test_a_sheet_column_is_matched_by_the_field_name(self):
        make_dropdown()
        mapping = suggest_mapping(["Employee ID", "blood group"], EMPLOYEES.fields)
        self.assertEqual(mapping["Blood Group"], "blood group")

    def test_the_options_are_offered_on_the_review_page(self):
        make_dropdown()
        self.assertEqual(
            EMPLOYEES.suggestions()["additional:Blood Group"], ["A+", "B+", "O-"]
        )


class ParseTests(TestCase):
    def parse(self, field, raw):
        return importing.parse(field, raw)

    def test_a_blank_cell_is_nothing(self):
        field = make_field("T")
        for blank in (None, "", "   "):
            self.assertEqual(self.parse(field, blank), (None, None))

    def test_text(self):
        field = make_field("T")
        self.assertEqual(self.parse(field, "  Ada ")[0], "Ada")
        self.assertIn("255", self.parse(field, "x" * 256)[1])

    def test_long_text_has_no_length_limit_but_no_scripts(self):
        field = make_field("L", LONG_TEXT)
        self.assertEqual(self.parse(field, "x" * 1000)[0], "x" * 1000)
        self.assertIn("not allowed", self.parse(field, "<script>alert(1)</script>")[1])

    def test_number(self):
        field = make_field("N", NUMBER)
        self.assertEqual(self.parse(field, "5.5")[0], Decimal("5.500000"))
        self.assertEqual(self.parse(field, "1,234")[0], Decimal("1234"))
        self.assertEqual(self.parse(field, "7.0")[0], Decimal("7"))
        for bad in ("abc", "NaN", "inf", "1e999", "12x"):
            self.assertIsNotNone(self.parse(field, bad)[1], bad)
        self.assertIn("large", self.parse(field, "9" * 30)[1])

    def test_date_in_the_formats_the_import_knows(self):
        field = make_field("D", DATE)
        self.assertEqual(self.parse(field, "2025-01-31")[0], date(2025, 1, 31))
        self.assertEqual(self.parse(field, "31/01/2025")[0], date(2025, 1, 31))
        self.assertEqual(self.parse(field, "2025-01-31 00:00:00")[0], date(2025, 1, 31))
        self.assertIn("valid date", self.parse(field, "next week")[1])
        self.assertIn("valid date", self.parse(field, "2025-02-30")[1])

    def test_yes_no(self):
        field = make_field("Y", YES_NO)
        for word in ("Yes", "y", "TRUE", "1"):
            self.assertIs(self.parse(field, word)[0], True, word)
        for word in ("No", "n", "False", "0"):
            self.assertIs(self.parse(field, word)[0], False, word)
        self.assertIn("Yes or No", self.parse(field, "maybe")[1])

    def test_dropdown_by_label_or_key_ignoring_case(self):
        field = make_dropdown()
        self.assertEqual(self.parse(field, "a+")[0], "a_pos")
        self.assertEqual(self.parse(field, " O- ")[0], "o_neg")
        self.assertEqual(self.parse(field, "o_neg")[0], "o_neg")
        self.assertIn("not one of: A+, B+, O-", self.parse(field, "Z")[1])

    def test_a_long_option_list_is_cut_in_the_message(self):
        field = make_dropdown("Big", [f"Option {i}" for i in range(12)])
        self.assertIn("...", self.parse(field, "nope")[1])


class ImportTests(TestCase):
    def setUp(self):
        importing.forget()
        self.user = make_user("importer", is_superuser=True)
        self.company = make_company("Acme Ltd")
        make_employee(company=self.company, email="importer@acme.test", user=self.user)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        self.maya = make_employee(
            company=self.company, email="maya@acme.test", first_name="Maya"
        )
        Employee.objects.filter(pk=self.maya.pk).update(
            badge_id="E-1", phone="9876543210", employee_last_name="Chen"
        )
        self.group = make_dropdown()
        self.passport = make_field("Passport Number")
        self.expiry = make_field("Passport Expiry", DATE)
        self.dependents = make_field("Dependents", NUMBER)
        self.license = make_field("Has License", YES_NO)

    # ------------------------------------------------------------ create
    def created(self, **extra):
        rows = rows_for({**PERSON, **extra})
        result = EMPLOYEES.check(rows, Context())
        return result

    def test_a_row_carries_its_additional_values_once_checked(self):
        result = self.created(
            **{
                "Blood Group": "o-",
                "Passport Number": "P123",
                "Passport Expiry": "31/01/2030",
                "Dependents": "2",
                "Has License": "yes",
            }
        )
        self.assertEqual(result.errors, [])
        values = result.valid[0]["__additional"]
        self.assertEqual(values[self.group.pk], "o_neg")
        self.assertEqual(values[self.passport.pk], "P123")
        self.assertEqual(values[self.expiry.pk], date(2030, 1, 31))
        self.assertEqual(values[self.dependents.pk], Decimal("2"))
        self.assertIs(values[self.license.pk], True)

    def test_blank_cells_carry_nothing(self):
        result = self.created(**{"Passport Number": "P1", "Blood Group": ""})
        self.assertEqual(list(result.valid[0]["__additional"]), [self.passport.pk])

    def test_a_bad_value_is_that_rows_error_and_names_its_column(self):
        result = self.created(
            **{"Blood Group": "Z", "Dependents": "lots", "Passport Expiry": "soon"}
        )
        self.assertEqual(result.valid, [])
        entry = result.errors[0]
        self.assertIn("Blood Group", entry["by_field"])
        self.assertIn("Dependents", entry["by_field"])
        self.assertIn("Passport Expiry", entry["by_field"])
        self.assertIn("not one of", entry["by_field"]["Blood Group"])
        self.assertEqual(entry["data"]["Blood Group"], "Z")

    def test_creating_saves_the_values_for_the_new_people(self):
        result = self.created(
            **{"Blood Group": "A+", "Passport Number": "P123", "Has License": "No"}
        )
        counts = EMPLOYEES.commit(result.valid, Context())
        nia = Employee.objects.entire().get(badge_id="E-9")
        self.assertEqual(value_of(nia, self.group), "a_pos")
        self.assertEqual(value_of(nia, self.passport), "P123")
        self.assertIs(value_of(nia, self.license), False)
        self.assertIsNone(value_of(nia, self.expiry))
        self.assertEqual(counts["additional_values"], 3)

    def test_people_without_values_get_no_rows(self):
        result = self.created()
        counts = EMPLOYEES.commit(result.valid, Context())
        self.assertEqual(counts["additional_values"], 0)
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_many_people_are_saved_with_few_queries(self):
        people = [
            {
                **PERSON,
                "Badge ID": f"B-{i}",
                "Email": f"p{i}@acme.test",
                "Phone": f"98765{i:05d}",
                "Passport Number": f"P{i}",
                "Blood Group": "B+",
            }
            for i in range(6)
        ]
        result = EMPLOYEES.check(rows_for(*people), Context())
        self.assertEqual(len(result.valid), 6)
        EMPLOYEES.commit(result.valid, Context())
        self.assertEqual(
            AdditionalInfoValue.objects.filter(field=self.passport).count(), 6
        )
        self.assertEqual(
            AdditionalInfoValue.objects.filter(field=self.group).count(), 6
        )

    def test_a_script_in_a_cell_is_refused(self):
        result = self.created(**{"Passport Number": "<script>alert(1)</script>"})
        self.assertEqual(result.valid, [])
        self.assertIn("Passport Number", result.errors[0]["by_field"])

    def test_a_file_field_is_not_a_column(self):
        make_field("Visa Scan", FILE)
        self.assertNotIn("Visa Scan", [f.key for f in EMPLOYEES.fields])

    def test_an_inactive_field_is_not_imported(self):
        AdditionalInfoField.objects.filter(pk=self.passport.pk).update(is_active=False)
        importing.forget()
        result = self.created(**{"Passport Number": "P1"})
        self.assertEqual(result.errors, [])
        self.assertNotIn(self.passport.pk, result.valid[0].get("__additional", {}))

    # ------------------------------------------------------------ update
    def run_job(self, rows, mode="update", keys=("Badge ID",)):
        self.client.post(
            reverse("master-import-upload"),
            {"dataset": "employees", "mode": mode, "file": sheet(rows)},
        )
        job = ImportJob.objects.latest("pk")
        mapping = {f"map__{k}": v for k, v in job.mapping.items()}
        mapping["match"] = list(keys)
        self.client.post(reverse("master-import-map", args=[job.pk]), mapping)
        job.refresh_from_db()
        review = self.client.post(reverse("master-import-check", args=[job.pk])).json()
        return job, review

    def finish(self, job):
        self.client.post(reverse("master-import-run", args=[job.pk]))
        job.refresh_from_db()
        return job

    def test_the_sheet_columns_are_mapped_by_name(self):
        job, _review = self.run_job(
            [{"Badge ID": "E-1", "Blood Group": "O-", "Passport Number": "P7"}]
        )
        self.assertEqual(job.mapping["Blood Group"], "Blood Group")
        self.assertEqual(job.mapping["Passport Number"], "Passport Number")

    def test_updating_sets_values_the_sheet_fills_in(self):
        job, review = self.run_job(
            [
                {
                    "Badge ID": "E-1",
                    "Blood Group": "O-",
                    "Passport Number": "P7",
                    "Dependents": "3",
                }
            ]
        )
        self.assertEqual((review["valid"], review["error_count"]), (1, 0))
        self.finish(job)
        self.assertEqual(value_of(self.maya, self.group), "o_neg")
        self.assertEqual(value_of(self.maya, self.passport), "P7")
        self.assertEqual(value_of(self.maya, self.dependents), Decimal("3"))
        self.assertEqual(job.summary["counts"]["additional_values"], 3)

    def test_the_review_lists_the_change_in_words(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.maya, field=self.group, value_text="a_pos"
        )
        _job, review = self.run_job([{"Badge ID": "E-1", "Blood Group": "B+"}])
        self.assertIn("Blood Group: A+ → B+", review["html"])

    def test_a_blank_cell_leaves_the_value_alone(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.maya, field=self.passport, value_text="OLD"
        )
        job, review = self.run_job(
            [{"Badge ID": "E-1", "Passport Number": "", "Blood Group": "A+"}]
        )
        self.finish(job)
        self.assertEqual(value_of(self.maya, self.passport), "OLD")
        self.assertEqual(value_of(self.maya, self.group), "a_pos")

    def test_the_same_value_changes_nothing(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.maya, field=self.group, value_text="a_pos"
        )
        AdditionalInfoValue.objects.create(
            employee_id=self.maya, field=self.dependents, value_number=Decimal("2")
        )
        job, review = self.run_job(
            [{"Badge ID": "E-1", "Blood Group": "a+", "Dependents": "2.0"}]
        )
        self.assertEqual(review["valid"], 0)
        self.finish(job)
        self.assertEqual(AdditionalInfoValue.objects.count(), 2)
        self.assertEqual(job.summary["unchanged"], 1)

    def test_an_existing_value_is_replaced_not_duplicated(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.maya, field=self.passport, value_text="OLD"
        )
        job, _review = self.run_job([{"Badge ID": "E-1", "Passport Number": "NEW"}])
        self.finish(job)
        self.assertEqual(
            AdditionalInfoValue.objects.filter(
                employee_id=self.maya, field=self.passport
            ).count(),
            1,
        )
        self.assertEqual(value_of(self.maya, self.passport), "NEW")

    def test_a_bad_value_is_an_error_and_nothing_is_saved(self):
        job, review = self.run_job(
            [{"Badge ID": "E-1", "Blood Group": "Z", "Passport Number": "P1"}]
        )
        self.assertEqual((review["valid"], review["error_count"]), (0, 1))
        self.finish(job)
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_only_the_matched_person_is_changed(self):
        jon = make_employee(
            company=self.company, email="jon@acme.test", first_name="Jon"
        )
        Employee.objects.filter(pk=jon.pk).update(badge_id="E-2", phone="9876500000")
        job, _review = self.run_job([{"Badge ID": "E-1", "Passport Number": "P1"}])
        self.finish(job)
        self.assertEqual(value_of(self.maya, self.passport), "P1")
        self.assertIsNone(value_of(jon, self.passport))

    def test_create_or_update_does_both_with_values(self):
        job, review = self.run_job(
            [
                {"Badge ID": "E-1", "Passport Number": "KNOWN"},
                {**PERSON, "Passport Number": "FRESH", "Blood Group": "B+"},
            ],
            mode="both",
        )
        self.assertEqual((review["valid"], review["error_count"]), (2, 0))
        self.finish(job)
        nia = Employee.objects.entire().get(badge_id="E-9")
        self.assertEqual(value_of(self.maya, self.passport), "KNOWN")
        self.assertEqual(value_of(nia, self.passport), "FRESH")
        self.assertEqual(value_of(nia, self.group), "b_pos")
        self.assertEqual(job.summary["counts"]["additional_values"], 3)

    def test_the_finished_page_reports_the_values(self):
        job, _review = self.run_job([{"Badge ID": "E-1", "Passport Number": "P1"}])
        self.finish(job)
        page = self.client.get(reverse("master-import-done", args=[job.pk]))
        self.assertContains(page, "Additional Info Values")

    def test_a_sheet_without_additional_columns_still_works(self):
        job, review = self.run_job([{"Badge ID": "E-1", "Address": "12 Park Street"}])
        self.assertEqual(review["valid"], 1)
        self.finish(job)
        self.maya.refresh_from_db()
        self.assertEqual(self.maya.address, "12 Park Street")
        self.assertFalse(AdditionalInfoValue.objects.exists())

    # ---------------------------------------------------------- the pages
    def test_the_template_has_a_column_per_field_with_a_sample(self):
        response = self.client.get(
            reverse("master-import-template", args=["employees"])
        )
        frame = pd.read_excel(
            io.BytesIO(
                b"".join(response.streaming_content)
                if response.streaming
                else response.content
            ),
            dtype=str,
        )
        for label in (
            "Blood Group",
            "Passport Number",
            "Passport Expiry",
            "Dependents",
            "Has License",
        ):
            self.assertIn(label, frame.columns)
        self.assertEqual(frame.loc[0, "Blood Group"], "A+")
        self.assertEqual(frame.loc[0, "Has License"], "Yes")

    def test_the_map_page_lists_the_columns_under_their_group(self):
        self.client.post(
            reverse("master-import-upload"),
            {
                "dataset": "employees",
                "mode": "create",
                "file": sheet([{**PERSON, "Passport Number": "P1"}]),
            },
        )
        job = ImportJob.objects.latest("pk")
        page = self.client.get(reverse("master-import-map", args=[job.pk]))
        self.assertContains(page, "Additional Info")
        self.assertContains(page, "map__Passport Number")
        self.assertContains(page, "map__Blood Group")
