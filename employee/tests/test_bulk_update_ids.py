"""
save_employee_bulk_update decoded bulk_employee_ids with json.loads and then
ast.literal_eval on the result. An empty or missing field gave literal_eval a
list ([]), raising ValueError and a 500.
"""

import json

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from employee.models import Employee
from employee.views import parse_posted_id_list
from horilla.testkit import make_company, make_employee, make_user


class ParsePostedIdListTests(SimpleTestCase):
    def test_empty_and_missing_values_mean_no_ids(self):
        for raw in (None, "", "   ", "[]", '"[]"', "null", "garbage", "{"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_posted_id_list(raw), [])

    def test_the_double_encoded_value_the_form_round_trips(self):
        # Step 1 of the form json.dumps() what the browser posted.
        posted = json.dumps(json.dumps([3, 4]))
        self.assertEqual(parse_posted_id_list(posted), [3, 4])
        self.assertEqual(parse_posted_id_list(json.dumps('["3", "4"]')), [3, 4])

    def test_a_plain_json_list_or_python_literal_also_works(self):
        self.assertEqual(parse_posted_id_list("[1, 2]"), [1, 2])
        self.assertEqual(parse_posted_id_list(json.dumps("[1, 2]")), [1, 2])
        self.assertEqual(parse_posted_id_list("'[1, 2]'"), [1, 2])

    def test_entries_that_are_not_integers_are_dropped_and_duplicates_collapse(self):
        self.assertEqual(parse_posted_id_list('["1", "x", null, 2, 1]'), [1, 2])

    def test_a_single_id_is_accepted(self):
        self.assertEqual(parse_posted_id_list("7"), [7])


class SaveEmployeeBulkUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Acme")
        cls.admin_user = make_user("root", password="pw-not-real", is_superuser=True)
        make_employee(company=company, email="root@test.horilla", user=cls.admin_user)
        cls.first = make_employee(
            company=company, email="one@test.horilla", first_name="One"
        )
        cls.second = make_employee(
            company=company, email="two@test.horilla", first_name="Two"
        )

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.url = reverse("save-employee-bulk-update")

    def test_missing_ids_report_an_error_instead_of_a_500(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertIn("No employees selected.", messages)

    def test_empty_and_malformed_ids_are_also_handled(self):
        for raw in ("", "[]", '"[]"', "not json", '["abc"]'):
            with self.subTest(raw=raw):
                response = self.client.post(
                    self.url,
                    {"bulk_employee_ids": raw, "update_fields": '["employee_first_name"]'},
                )
                self.assertEqual(response.status_code, 302)
        self.first.refresh_from_db()
        self.assertEqual(self.first.employee_first_name, "One")

    def test_double_encoded_ids_still_update_the_selected_employees(self):
        ids = json.dumps(json.dumps([self.first.pk, self.second.pk]))
        response = self.client.post(
            self.url,
            {
                "bulk_employee_ids": ids,
                "update_fields": '["employee_first_name"]',
                "employee_first_name": "Renamed",
            },
        )
        self.assertEqual(response.status_code, 302)
        names = Employee.objects.filter(
            pk__in=[self.first.pk, self.second.pk]
        ).values_list("employee_first_name", flat=True)
        self.assertEqual(set(names), {"Renamed"})

    def test_an_unknown_id_is_skipped_not_a_server_error(self):
        ids = json.dumps(json.dumps([self.first.pk, 999999]))
        response = self.client.post(
            self.url,
            {
                "bulk_employee_ids": ids,
                "update_fields": '["employee_first_name"]',
                "employee_first_name": "Renamed",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.first.refresh_from_db()
        self.assertEqual(self.first.employee_first_name, "Renamed")
