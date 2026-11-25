"""?open_tab= opens a tab by its number or by its title, so dashboard links
keep landing on the right tab when tabs are added or moved."""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}

# Every tab a dashboard (or redirect) opens by title: (tab view, title).
LINKED_TABS = [
    ("attendances-tab-view", "OT Attendances"),
    ("attendances-tab-view", "Validated Attendances"),
    ("attendance-request-tab", "Requested Attendances"),
    ("tab-asset-request-allocation", "Asset Request"),
    ("tab-asset-request-allocation", "Service Request"),
    ("tab-asset-request-allocation", "Asset Allocation"),
    ("tab-objectives-view", "My Objectives"),
    ("ticket-tab", "All Tickets"),
    ("time-sheet-tab-view", "All Timesheets"),
    ("leave-allocation-request-filter", "Leave Allocation Requests"),
    ("compensatory-tab-view", "Compensatory Leave Requests"),
    ("loan-generic-tab-view", "Loan"),
    ("tab-reimbursement", "Reimbursements"),
    ("payslip-batch-tabs", "Batches"),
    ("feedback-generic-tab", "Feedbacks to Review"),
    ("shift-request-tab", "Shift Requests"),
]


class OpenTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("open-tab-admin", is_superuser=True)
        make_employee(
            company=make_company("Open Tab Co"),
            email="open-tab-admin@test.horilla",
            user=cls.user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def opened(self, open_tab, language="en"):
        # Horilla follows only the language switcher's cookie.
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        page = self.client.get(
            reverse("attendances-tab-view"), {"open_tab": open_tab}, **HX
        )
        target = page.context.get("active_target") or ""
        return target.rsplit("attendances-tab", 1)[-1].rstrip('"]') or None

    def test_by_number(self):
        self.assertEqual(self.opened("3"), "3")

    def position(self, source_title):
        """Where the tab titled `source_title` in the code sits, and its title."""
        from attendance.cbv.attendances import AttendancesTabView

        for index, tab in enumerate(AttendancesTabView().tabs, start=1):
            with translation.override(None):
                if str(tab["title"]).strip() == source_title:
                    return str(index), tab["title"]
        raise AssertionError(source_title)

    def test_by_title_ignoring_case_and_spaces(self):
        # The code's titles are " Validated Attendances" and " OT Attendances",
        # with a leading space.
        validated, _title = self.position("Validated Attendances")
        ot, _title = self.position("OT Attendances")
        self.assertEqual(self.opened("Validated Attendances"), validated)
        self.assertEqual(self.opened("  ot attendances "), ot)

    def test_by_title_as_shown_or_as_written_in_another_language(self):
        validated, title = self.position("Validated Attendances")
        with translation.override("de"):
            shown = str(title).strip()
        self.assertNotEqual(shown, "Validated Attendances")
        self.assertEqual(self.opened(shown, "de"), validated)
        self.assertEqual(self.opened("Validated Attendances", "de"), validated)

    def test_every_title_a_link_uses_names_a_tab(self):
        from leave.models import LeaveGeneralSetting

        # Compensatory leave pages open only while it's enabled.
        LeaveGeneralSetting.objects.update_or_create(
            id=1, defaults={"compensatory_leave": True}
        )
        for view, title in LINKED_TABS:
            with self.subTest(view=view, title=title):
                page = self.client.get(reverse(view), {"open_tab": title}, **HX)
                index = page.context["view"].open_tab_index(title)
                self.assertIsNotNone(index)
                tabs = page.context["tabs"]
                with translation.override(None):
                    self.assertEqual(str(tabs[index - 1]["title"]).strip(), title)

    def test_an_unknown_title_opens_no_particular_tab(self):
        self.assertIsNone(self.opened("No Such Tab"))
