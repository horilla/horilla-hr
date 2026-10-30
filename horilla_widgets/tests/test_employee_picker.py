"""Employee picker filter endpoint and AJAX option search tests."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from base.models import Department
from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user
from horilla_widgets.generic_ajax import dump_queryset


class EmployeePickerIdsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Picker Co")
        cls.engineering = Department.objects.create(department="Engineering")
        cls.sales = Department.objects.create(department="Sales")
        cls.legal = Department.objects.create(department="Legal")
        cls.ann = make_employee(
            company=company,
            email="ann@picker.test",
            first_name="Ann",
            last_name="Archer",
            department=cls.engineering,
            date_joining=date(2020, 1, 10),
        )
        cls.bob = make_employee(
            company=company,
            email="bob@picker.test",
            first_name="Bob",
            last_name="Baker",
            phone="9222222222",
            department=cls.sales,
            date_joining=date(2023, 6, 1),
        )
        cls.cal = make_employee(
            company=company,
            email="cal@picker.test",
            first_name="Cal",
            last_name="Cook",
            phone="9333333333",
            department=cls.legal,
            date_joining=date(2024, 3, 15),
        )
        cls.viewer = make_user("picker_viewer", is_superuser=True)
        cls.viewer_employee = make_employee(
            company=company,
            email="viewer@picker.test",
            first_name="Vic",
            last_name="Viewer",
            phone="9444444444",
            user=cls.viewer,
        )

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url = reverse("employee-picker-ids")

    def token(self, queryset=None):
        return dump_queryset(Employee.objects.all() if queryset is None else queryset)

    def ids(self, **params):
        response = self.client.post(self.url, {"token": self.token(), **params})
        self.assertEqual(response.status_code, 200, response.content)
        return set(response.json()["ids"])

    def test_no_filters_returns_every_employee(self):
        self.assertTrue({self.ann.pk, self.bob.pk, self.cal.pk} <= self.ids())

    def test_name_search_matches_comma_separated_terms(self):
        self.assertEqual(
            self.ids(name_or_badge="ann, cook")
            & {self.ann.pk, self.bob.pk, self.cal.pk},
            {self.ann.pk, self.cal.pk},
        )

    def test_department_accepts_several_values(self):
        found = self.ids(department=[self.engineering.pk, self.sales.pk])
        self.assertEqual(
            found & {self.ann.pk, self.bob.pk, self.cal.pk}, {self.ann.pk, self.bob.pk}
        )

    def test_joining_date_range(self):
        everyone = {self.ann.pk, self.bob.pk, self.cal.pk}
        found = self.ids(joined_from="2023-01-01", joined_till="2023-12-31")
        self.assertEqual(found & everyone, {self.bob.pk})

    def test_filters_combine(self):
        found = self.ids(
            department=[self.engineering.pk, self.sales.pk], name_or_badge="bob"
        )
        self.assertEqual(found, {self.bob.pk})

    def test_unknown_department_id_is_rejected(self):
        response = self.client.post(
            self.url, {"token": self.token(), "department": 999999}
        )
        self.assertEqual(response.status_code, 400)

    def test_ids_respect_the_fields_own_queryset(self):
        only_ann = Employee.objects.filter(pk=self.ann.pk)
        response = self.client.post(
            self.url, {"token": self.token(only_ann), "department": [self.sales.pk]}
        )
        self.assertEqual(response.json()["ids"], [])
        response = self.client.post(self.url, {"token": self.token(only_ann)})
        self.assertEqual(response.json()["ids"], [self.ann.pk])

    def test_missing_or_tampered_token_is_rejected(self):
        self.assertEqual(self.client.post(self.url).status_code, 400)
        tampered = self.token() + "x"
        self.assertEqual(
            self.client.post(self.url, {"token": tampered}).status_code, 400
        )

    def test_get_requests_are_not_allowed(self):
        self.assertEqual(
            self.client.get(self.url, {"token": self.token()}).status_code, 405
        )
        self.assertEqual(
            self.client.get(
                reverse("employee-picker-rows"), {"token": self.token()}
            ).status_code,
            405,
        )

    def test_rows_are_paged_with_total_and_has_more(self):
        rows_url = reverse("employee-picker-rows")
        with mock.patch("horilla_widgets.views.PICKER_PAGE_SIZE", 2):
            first = self.client.post(
                rows_url, {"token": self.token(), "page": 1}
            ).json()
            last = self.client.post(rows_url, {"token": self.token(), "page": 2}).json()
        self.assertEqual(len(first["results"]), 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["total"], Employee.objects.count())
        self.assertLessEqual(len(last["results"]), 2)
        seen = {row["id"] for row in first["results"]} & {
            row["id"] for row in last["results"]
        }
        self.assertEqual(seen, set())

    def test_rows_apply_filters_and_carry_label_and_avatar(self):
        rows_url = reverse("employee-picker-rows")
        data = self.client.post(
            rows_url, {"token": self.token(), "department": [self.sales.pk]}
        ).json()
        self.assertEqual([row["id"] for row in data["results"]], [self.bob.pk])
        self.assertEqual(data["total"], 1)
        self.assertIn("Bob Baker", data["results"][0]["label"])
        self.assertTrue(data["results"][0]["avatar"])

    def test_rows_by_ids_return_only_those_in_the_fields_queryset(self):
        rows_url = reverse("employee-picker-rows")
        only_ann = Employee.objects.filter(pk=self.ann.pk)
        data = self.client.post(
            rows_url,
            {"token": self.token(only_ann), "ids": f"{self.ann.pk},{self.bob.pk}"},
        ).json()
        self.assertEqual([row["id"] for row in data["results"]], [self.ann.pk])

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_department_options_are_searchable_over_ajax(self):
        url = reverse("horilla-ajax-choices", args=["picker-department"])
        response = self.client.get(url, {"q": "eng"})
        self.assertEqual(
            [row["text"] for row in response.json()["results"]], ["Engineering"]
        )
