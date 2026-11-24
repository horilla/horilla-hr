"""The employee Advanced filter offers the additional fields and applies them."""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.http import QueryDict
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from additional_info.integration import FILTER_PREFIX
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
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla.testkit import make_company, make_employee


def field(label, field_type=TEXT, **extra):
    return AdditionalInfoField.objects.create(
        label=label, field_type=field_type, **extra
    )


def value(employee, info_field, **column):
    return AdditionalInfoValue.objects.create(
        employee_id=employee, field=info_field, **column
    )


class EmployeeFilterFieldsTests(TestCase):
    def setUp(self):
        company = make_company("Filter Co")
        self.ada = make_employee(company=company, email="ada@f.test", first_name="Ada")
        self.bob = make_employee(company=company, email="bob@f.test", first_name="Bob")
        self.cy = make_employee(company=company, email="cy@f.test", first_name="Cy")

        self.team = field("Team")
        self.notes = field("Notes", LONG_TEXT)
        self.years = field("Years", NUMBER)
        self.joined = field("Joined", DATE)
        self.blood = field(
            "Blood Group",
            DROPDOWN,
            choices=[{"key": "a_pos", "label": "A+"}, {"key": "o_neg", "label": "O-"}],
        )
        self.driver = field("Driver", YES_NO)

        value(self.ada, self.team, value_text="Alpha team")
        value(self.bob, self.team, value_text="Beta crew")
        value(self.ada, self.years, value_number=Decimal("5"))
        value(self.bob, self.years, value_number=Decimal("9"))
        value(self.ada, self.joined, value_date=date(2026, 1, 10))
        value(self.bob, self.joined, value_date=date(2026, 6, 1))
        value(self.ada, self.blood, value_text="a_pos")
        value(self.bob, self.blood, value_text="o_neg")
        value(self.ada, self.driver, value_bool=True)
        value(self.bob, self.driver, value_bool=False)

    def entries(self):
        return {e["key"]: e for e in EmployeeFilter().custom_filter_fields}

    def names(self, key, lookup, raw):
        data = QueryDict(mutable=True)
        data.setlist("custom_field", [FILTER_PREFIX + key])
        data.setlist("custom_lookup", [lookup])
        data.setlist("custom_value", [raw])
        found = EmployeeFilter(data, queryset=Employee.objects.entire()).qs
        return set(found.values_list("employee_first_name", flat=True))

    # --- what the builder offers ---
    def test_each_active_field_is_offered_with_the_type_that_suits_it(self):
        entries = self.entries()
        wanted = {
            "team": "text",
            "notes": "text",
            "years": "number",
            "joined": "date_range",
            "blood_group": "choice",
            "driver": "choice",
        }
        for key, kind in wanted.items():
            with self.subTest(key=key):
                self.assertEqual(entries[FILTER_PREFIX + key]["type"], kind)
                self.assertTrue(entries[FILTER_PREFIX + key]["lookups"])

    def test_a_dropdown_offers_its_options_and_yes_no_offers_both_answers(self):
        entries = self.entries()
        self.assertEqual(
            entries[FILTER_PREFIX + "blood_group"]["choices"],
            [["a_pos", "A+"], ["o_neg", "O-"]],
        )
        self.assertEqual(
            [c[0] for c in entries[FILTER_PREFIX + "driver"]["choices"]],
            ["true", "false"],
        )

    def test_a_file_field_and_an_inactive_field_are_not_offered(self):
        field("Passport Scan", FILE)
        field("Old Field", TEXT, is_active=False)
        keys = set(self.entries())
        self.assertNotIn(FILTER_PREFIX + "passport_scan", keys)
        self.assertNotIn(FILTER_PREFIX + "old_field", keys)

    def test_the_built_in_entries_are_still_there(self):
        keys = set(self.entries())
        self.assertTrue({"phone", "country", "gender", "date_joining"} <= keys)

    def test_a_field_added_later_is_offered_without_rebuilding_the_filter(self):
        instance = EmployeeFilter()
        field("Locker No")
        self.assertIn(
            FILTER_PREFIX + "locker_no",
            {e["key"] for e in instance.custom_filter_fields},
        )

    def test_building_the_filter_reads_no_additional_info(self):
        with CaptureQueriesContext(connection) as queries:
            EmployeeFilter()
        self.assertFalse([q for q in queries if "additional_info" in q["sql"]])

    # --- what applying one does ---
    def test_text_filters(self):
        self.assertEqual(self.names("team", "icontains", "team"), {"Ada"})
        self.assertEqual(self.names("team", "istartswith", "beta"), {"Bob"})
        self.assertEqual(self.names("team", "iexact", "alpha team"), {"Ada"})

    def test_number_filters(self):
        self.assertEqual(self.names("years", "gte", "6"), {"Bob"})
        self.assertEqual(self.names("years", "lte", "5"), {"Ada"})

    def test_date_filters(self):
        self.assertEqual(self.names("joined", "lt", "2026-03-01"), {"Ada"})
        self.assertEqual(self.names("joined", "gte", "2026-03-01"), {"Bob"})
        self.assertEqual(self.names("joined", "exact", "2026-01-10"), {"Ada"})

    def test_dropdown_and_yes_no_filters(self):
        self.assertEqual(self.names("blood_group", "exact", "o_neg"), {"Bob"})
        self.assertEqual(self.names("driver", "exact", "true"), {"Ada"})
        self.assertEqual(self.names("driver", "exact", "false"), {"Bob"})

    def test_an_employee_with_no_value_is_not_matched(self):
        self.assertNotIn("Cy", self.names("team", "icontains", "a"))

    def test_a_value_that_cannot_be_read_filters_nothing(self):
        everyone = {"Ada", "Bob", "Cy"}
        for key, lookup, raw in (
            ("years", "gte", "abc"),
            ("joined", "gte", "not-a-date"),
        ):
            with self.subTest(key=key):
                self.assertTrue(everyone <= self.names(key, lookup, raw))

    def test_a_lookup_the_type_does_not_offer_is_ignored(self):
        self.assertTrue({"Ada", "Bob", "Cy"} <= self.names("years", "icontains", "5"))

    def test_an_unknown_or_removed_field_is_ignored(self):
        self.assertTrue({"Ada", "Bob", "Cy"} <= self.names("nope", "icontains", "x"))
        self.team.is_active = False
        self.team.save()
        self.assertTrue(
            {"Ada", "Bob", "Cy"} <= self.names("team", "icontains", "alpha")
        )

    def test_the_applied_row_is_restored_for_the_builder(self):
        data = QueryDict(mutable=True)
        data.setlist("custom_field", [FILTER_PREFIX + "team"])
        data.setlist("custom_lookup", ["icontains"])
        data.setlist("custom_value", ["alpha"])
        rows = EmployeeFilter(
            data, queryset=Employee.objects.entire()
        ).custom_filter_rows
        self.assertEqual(
            rows,
            [
                {
                    "field": FILTER_PREFIX + "team",
                    "lookup": "icontains",
                    "value": "alpha",
                }
            ],
        )
