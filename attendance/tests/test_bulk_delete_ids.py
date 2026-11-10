"""
attendance_bulk_delete passed request.POST.getlist("ids", "[]") straight to
id__in. One JSON string ("[1,2]") made it convert "[" to an integer and raise
ValueError, a 500.
"""

import json
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.http import QueryDict

from attendance.models import Attendance
from horilla.posted_ids import parse_posted_id_list, posted_ids
from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_attendance


class PostedIdsTests(SimpleTestCase):
    def test_repeated_params(self):
        self.assertEqual(posted_ids(QueryDict("ids=1&ids=2&ids=2")), [1, 2])

    def test_one_json_string(self):
        self.assertEqual(posted_ids(QueryDict("ids=%5B1%2C2%5D")), [1, 2])

    def test_missing_empty_and_garbage(self):
        for query in ("", "ids=", "ids=%5B", "ids=abc", "ids=%5B%5D"):
            with self.subTest(query=query):
                self.assertEqual(posted_ids(QueryDict(query)), [])

    def test_mixed_shapes_collapse(self):
        self.assertEqual(posted_ids(QueryDict("ids=3&ids=%5B3%2C4%5D")), [3, 4])

    def test_double_encoded_value(self):
        self.assertEqual(parse_posted_id_list(json.dumps(json.dumps([5, 6]))), [5, 6])


class AttendanceBulkDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Acme")
        cls.admin_user = make_user("root", password="pw-not-real", is_superuser=True)
        make_employee(company=company, email="root@test.horilla", user=cls.admin_user)
        cls.employee = make_employee(company=company, email="emp@test.horilla")

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.url = reverse("attendance-bulk-delete")

    def make_attendance(self, day):
        return make_attendance(employee=self.employee, attendance_date=day)

    def test_malformed_or_missing_ids_are_reported_not_a_500(self):
        for data in ({}, {"ids": ""}, {"ids": "["}, {"ids": "abc"}, {"ids": "[]"}):
            with self.subTest(data=data):
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 400)

    def test_a_json_string_of_ids_deletes_those_attendances(self):
        first = self.make_attendance(date(2026, 1, 5))
        second = self.make_attendance(date(2026, 1, 6))
        keep = self.make_attendance(date(2026, 1, 7))
        response = self.client.post(
            self.url, {"ids": json.dumps([first.pk, second.pk])}
        )
        self.assertEqual(response.status_code, 200)
        remaining = set(Attendance.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {keep.pk})

    def test_repeated_ids_still_work(self):
        first = self.make_attendance(date(2026, 1, 5))
        second = self.make_attendance(date(2026, 1, 6))
        response = self.client.post(self.url, {"ids": [first.pk, second.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Attendance.objects.filter(pk__in=[first.pk, second.pk]).exists())
