"""Fields the employee add and edit templates don't place by hand."""

from unittest import mock

from django import forms
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from employee.forms import EmployeeForm
from horilla.testkit.factories import make_company, make_employee, make_user

TEMPLATE = "employee/create_form/custom_fields.html"


class TestCustomFields(TestCase):
    def test_a_plain_form_has_none_and_no_section(self):
        form = EmployeeForm()
        self.assertEqual(form.custom_fields(), [])
        self.assertNotIn("Custom", render_to_string(TEMPLATE, {"form": form}))

    def test_a_field_added_to_the_form_is_shown(self):
        form = EmployeeForm()
        form.fields["shirt_size"] = forms.CharField(
            label="Shirt size", help_text="As printed on the label"
        )
        self.assertEqual([f.name for f in form.custom_fields()], ["shirt_size"])
        html = render_to_string(TEMPLATE, {"form": form})
        self.assertIn("Custom", html)
        self.assertIn('name="shirt_size"', html)
        self.assertIn("Shirt size", html)
        self.assertIn("As printed on the label", html)

    def test_its_errors_are_shown(self):
        form = EmployeeForm(data={"email": "new@custom.test"})
        form.fields["shirt_size"] = forms.CharField(label="Shirt size")
        form.is_valid()
        html = render_to_string(TEMPLATE, {"form": form})
        self.assertIn("This field is required.", html)


class TestCustomFieldsOnTheAboutTab(TestCase):
    def setUp(self):
        company = make_company()
        self.employee = make_employee(company=company, email="worker@custom.test")
        self.employee.city = "Testville"
        self.employee.save()
        boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@custom.test", user=boss)
        self.client.force_login(boss)
        self.url = reverse("about-tab", args=[self.employee.pk])

    def about(self):
        return self.client.get(self.url, HTTP_HX_REQUEST="true")

    def test_the_section_is_left_out_when_there_are_none(self):
        with mock.patch.object(EmployeeForm, "custom_fields", return_value=[]):
            self.assertNotContains(self.about(), "Custom")

    def test_their_values_are_shown(self):
        placed = EmployeeForm.PLACED_FIELDS - {"city"}
        with mock.patch.object(EmployeeForm, "PLACED_FIELDS", placed):
            page = self.about()
        self.assertContains(page, "Custom")
        html = page.content.decode()
        self.assertIn("Testville", html[html.index("Custom") :])
