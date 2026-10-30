"""Employee picker widget rendering tests."""

import re

from django import forms
from django.test import RequestFactory, TestCase
from django.urls import reverse

from base.models import Department
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla import horilla_middlewares
from horilla.testkit import make_company, make_employee, make_user
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget


class PickerForm(forms.Form):
    employees = HorillaMultiSelectField(
        queryset=Employee.objects.all(),
        required=False,
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label="Employees",
    )


class DefaultsForm(forms.Form):
    recipient_employees = HorillaMultiSelectField()


class EmployeePickerWidgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Widget Co")
        department = Department.objects.create(department="Engineering")
        cls.ann = make_employee(
            company=company,
            email="ann@widget.test",
            first_name="Ann",
            last_name="Archer",
            department=department,
        )
        cls.viewer = make_user("widget_viewer", is_superuser=True)
        make_employee(
            company=company,
            email="viewer@widget.test",
            first_name="Vic",
            last_name="Viewer",
            phone="9444444444",
            user=cls.viewer,
        )

    def render(self, data=None, form_class=PickerForm, field="employees"):
        request = RequestFactory().get("/")
        request.session = {}
        request.user = self.viewer
        horilla_middlewares._thread_locals.request = request
        try:
            form = form_class(data=data)
            return str(form[field])
        finally:
            horilla_middlewares._thread_locals.request = None

    def test_renders_endpoints_and_token_but_no_rows(self):
        html = self.render()
        self.assertIn(reverse("employee-picker-ids"), html)
        self.assertIn(reverse("employee-picker-rows"), html)
        self.assertIn(reverse("horilla-ajax-choices", args=["picker-department"]), html)
        self.assertRegex(html, r'data-token="[^"]+"')
        self.assertNotIn('class="ep-row"', html)
        self.assertNotIn("Ann Archer", html)

    def test_filter_inputs_cannot_be_submitted_with_the_host_form(self):
        html = self.render()
        filters = re.findall(r"<(?:select|input)[^>]*data-filter=[^>]*>", html, re.S)
        self.assertGreater(len(filters), 10)
        for tag in filters:
            self.assertIn('form="ep-detached"', tag)
            self.assertNotRegex(tag, r'\sname="')

    def test_bare_field_defaults_to_employees_picker_and_name_based_label(self):
        html = self.render(form_class=DefaultsForm, field="recipient_employees")
        self.assertRegex(html, r'data-token="[^"]+"')
        self.assertIn("Recipient employees</h3>", html)
        self.assertNotIn("None</h3>", html)

    def test_default_queryset_is_built_per_form_and_explicit_ones_are_kept(self):
        first = DefaultsForm().fields["recipient_employees"].queryset
        second = DefaultsForm().fields["recipient_employees"].queryset
        self.assertIsNot(first, second)
        self.assertEqual(first.model, Employee)

        class EmptyForm(forms.Form):
            people = HorillaMultiSelectField(queryset=Employee.objects.none())

        self.assertFalse(EmptyForm().fields["people"].queryset.exists())

    def test_only_the_selected_options_are_rendered(self):
        html = self.render(data={"employees": [str(self.ann.pk)]})
        options = re.findall(r'<option value="(\d+)"[^>]*selected>', html)
        self.assertEqual(options, [str(self.ann.pk)])
        self.assertIn("Ann Archer", html)

    def test_a_tampered_selected_value_does_not_break_rendering(self):
        html = self.render(data={"employees": ["abc", str(self.ann.pk)]})
        self.assertIn(f'<option value="{self.ann.pk}"', html)
