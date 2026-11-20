"""
The tags above a filtered list read as the filter form does: the filter's
own label and the name of the chosen option ("OT Approved?: Yes"), not the
query key and raw value ("Attendance overtime approve: True").
"""

from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from attendance.filters import AttendanceFilters
from base.methods import humanize_filter_tags
from horilla.testkit.factories import (
    make_attendance,
    make_company,
    make_employee,
    make_user,
)


def tags(query, filter_class=AttendanceFilters):
    data_dict = {key: list(values) for key, values in query.items()}
    data_dict, labels, _extras = humanize_filter_tags(data_dict, filter_class)
    return (
        {key: str(label) for key, label in labels.items()},
        {key: [str(v) for v in values] for key, values in data_dict.items()},
    )


class TestTagsUseTheFiltersWording(SimpleTestCase):
    def test_label_and_choice_come_from_the_filter(self):
        labels, values = tags({"attendance_overtime_approve": ["True"]})
        self.assertEqual(labels["attendance_overtime_approve"], "OT Approved?")
        self.assertEqual(values["attendance_overtime_approve"], ["Yes"])

    def test_no_is_named_too(self):
        labels, values = tags({"attendance_validated": ["False"]})
        self.assertEqual(labels["attendance_validated"], "Validated?")
        self.assertEqual(values["attendance_validated"], ["No"])

    def test_django_filters_made_up_label_is_not_used(self):
        """A filter with no label of its own keeps the generic tag label."""
        labels, _values = tags(
            {"employee_id__employee_work_info__department_id": ["1"]}
        )
        self.assertNotIn("employee_id__employee_work_info__department_id", labels)

    def test_tags_already_worded_are_kept(self):
        labels, values = tags(
            {
                "attendance_date__gte": ["2026-11-02"],
                "attendance_date__lte": ["2026-11-02"],
            }
        )
        self.assertEqual(labels["attendance_date__gte"], "Attendance date")
        self.assertEqual(values["attendance_date__gte"], ["02 Nov 2026"])

    def test_without_a_filter_class_nothing_changes(self):
        labels, values = tags({"attendance_overtime_approve": ["True"]}, None)
        self.assertEqual(labels, {})
        self.assertEqual(values["attendance_overtime_approve"], ["True"])


class TestListTags(TestCase):
    def setUp(self):
        user = make_user("tags@filter.test", is_superuser=True)
        employee = make_employee(
            user=user, company=make_company(), email="tags@filter.test"
        )
        make_attendance(employee=employee, attendance_date=date(2026, 11, 2))
        self.client.force_login(user)

    def test_validated_attendances_tag(self):
        response = self.client.get(
            reverse("validated-attendance-tab")
            + "?filter_applied=on&attendance_overtime_approve=True",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OT Approved?")
        self.assertNotContains(response, "Attendance overtime approve")
