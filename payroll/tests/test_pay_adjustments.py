"""Arrears and recovery: entries, confirming them, the pay line they make, and the tab."""

import json
import re
from datetime import date

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from horilla.testkit import make_company, make_employee, make_user
from payroll.filters import PayAdjustmentFilter
from payroll.forms.component_forms import PayAdjustmentBulkForm, PayAdjustmentForm
from payroll.models.models import (
    Allowance,
    Deduction,
    PayAdjustment,
    Payslip,
    SystemComponentTaxOverride,
)

HX = {"HTTP_HX_REQUEST": "true"}


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Adjust Co")
        # Named and badged, so a name or badge ID search can tell them apart.
        self.adam = make_employee(
            company=self.company, email="adam-adj@test.horilla", first_name="Adam"
        )
        self.bea = make_employee(
            company=self.company, email="bea-adj@test.horilla", first_name="Bea"
        )
        for employee, badge in ((self.adam, "ADJ001"), (self.bea, "ADJ002")):
            employee.badge_id = badge
            employee.save()

    def entry(self, kind="arrears", **fields):
        values = {
            "employee_id": self.adam,
            "kind": kind,
            "title": "Back Pay",
            "amount": 1000.0,
            "pay_date": date(2026, 12, 5),
        }
        values.update(fields)
        return PayAdjustment.objects.create(**values)

    def payslip(self, employee, start, end):
        return Payslip.objects.create(
            employee_id=employee, start_date=start, end_date=end, pay_head_data={}
        )


class ValidationTests(Fixture):
    def test_the_amount_must_be_positive(self):
        with self.assertRaises(ValidationError) as caught:
            self.entry(amount=0).clean()
        self.assertIn("amount", caught.exception.message_dict)

    def test_a_month_with_a_payslip_is_refused_for_either_type(self):
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        for kind in ("arrears", "recovery"):
            with self.assertRaises(ValidationError) as caught:
                self.entry(kind).clean()
            self.assertIn("pay_date", caught.exception.message_dict)
            self.assertIn(
                "December 2026", str(caught.exception.message_dict["pay_date"])
            )

    def test_another_month_or_another_employee_is_fine(self):
        self.payslip(self.adam, date(2026, 11, 1), date(2026, 11, 30))
        self.payslip(self.bea, date(2026, 12, 1), date(2026, 12, 31))
        self.entry().clean()
        self.entry("recovery").clean()

    def test_confirming_checks_again(self):
        entry = self.entry()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        with self.assertRaises(ValidationError):
            entry.approve()
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertIsNone(entry.allowance_id)


class ConfirmTests(Fixture):
    def test_the_statuses_are_draft_and_confirmed(self):
        self.assertEqual(
            [str(label) for _key, label in PayAdjustment.STATUS_CHOICES],
            ["Draft", "Confirmed"],
        )

    def test_a_draft_makes_no_pay_line(self):
        for kind in ("arrears", "recovery"):
            entry = self.entry(kind)
            self.assertEqual(entry.status, "draft")
            self.assertIsNone(entry.pay_line())

    def test_confirming_arrears_makes_one_earning_for_that_employee_only(self):
        entry = self.entry()
        entry.approve(approved_by=self.bea)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "approved")
        self.assertEqual(entry.approved_by, self.bea)
        earning = entry.allowance_id
        self.assertEqual(earning.title, "Back Pay")
        self.assertEqual(earning.amount, 1000.0)
        self.assertEqual(earning.one_time_date, date(2026, 12, 5))
        self.assertTrue(earning.only_show_under_employee)
        self.assertTrue(earning.is_fixed)
        self.assertEqual(list(earning.specific_employees.all()), [self.adam])
        self.assertFalse(earning.is_taxable)
        self.assertIsNone(entry.deduction_id)

    def test_confirming_a_recovery_makes_one_deduction_for_that_employee_only(self):
        entry = self.entry("recovery", title="Excess Paid", amount=600.0)
        entry.approve()
        entry.refresh_from_db()
        deduction = entry.deduction_id
        self.assertEqual((deduction.title, deduction.amount), ("Excess Paid", 600.0))
        self.assertEqual(deduction.one_time_date, date(2026, 12, 5))
        self.assertTrue(deduction.is_fixed)
        self.assertTrue(deduction.is_installment)
        self.assertTrue(deduction.only_show_under_employee)
        self.assertTrue(deduction.is_pretax)
        self.assertEqual(list(deduction.specific_employees.all()), [self.adam])
        self.assertIsNone(entry.allowance_id)

    def test_only_a_draft_can_be_confirmed(self):
        entry = self.entry()
        entry.approve()
        with self.assertRaises(ValidationError):
            entry.approve()

    def test_an_employees_tax_exception_reaches_the_pay_line(self):
        # Each exception is the opposite of the standard: arrears taxable, a recovery post-tax.
        SystemComponentTaxOverride.objects.create(
            system_key="arrears", employee_id=self.adam, value=True
        )
        SystemComponentTaxOverride.objects.create(
            system_key="recovery", employee_id=self.adam, value=False
        )
        earning = self.entry()
        earning.approve()
        recovery = self.entry("recovery", title="Excess")
        recovery.approve()
        self.assertTrue(earning.allowance_id.is_taxable)
        self.assertFalse(recovery.deduction_id.is_pretax)

    def test_another_employee_follows_the_standard_setting(self):
        SystemComponentTaxOverride.objects.create(
            system_key="arrears", employee_id=self.adam, value=True
        )
        other = self.entry(employee_id=self.bea)
        other.approve()
        self.assertFalse(other.allowance_id.is_taxable)

    def test_changing_the_standard_item_reaches_a_confirmed_entry(self):
        arrears = self.entry()
        arrears.approve()
        recovery = self.entry("recovery", title="Excess")
        recovery.approve()
        earning_template = Allowance.objects.entire().get(system_key="arrears")
        earning_template.is_taxable = True
        earning_template.save()
        deduction_template = Deduction.objects.entire().get(system_key="recovery")
        deduction_template.is_pretax = False
        deduction_template.save()
        arrears.allowance_id.refresh_from_db()
        recovery.deduction_id.refresh_from_db()
        self.assertTrue(arrears.allowance_id.is_taxable)
        self.assertFalse(recovery.deduction_id.is_pretax)


class TaxTreatmentTests(Fixture):
    """Taxable for arrears and pre-tax for a recovery, settled per entry or left to the standard."""

    def test_left_empty_the_standard_setting_applies(self):
        arrears, recovery = self.entry(), self.entry("recovery")
        self.assertIsNone(arrears.tax_treatment)
        self.assertEqual(arrears.tax_pin(), {})
        arrears.approve()
        recovery.approve()
        self.assertFalse(arrears.allowance_id.is_taxable)
        self.assertTrue(recovery.deduction_id.is_pretax)

    def test_an_entry_can_make_arrears_taxable_and_a_recovery_post_tax(self):
        arrears = self.entry(tax_treatment=True)
        recovery = self.entry("recovery", tax_treatment=False)
        self.assertEqual(arrears.tax_pin(), {"is_taxable": True})
        self.assertEqual(recovery.tax_pin(), {"is_pretax": False})
        arrears.approve()
        recovery.approve()
        self.assertTrue(arrears.allowance_id.is_taxable)
        self.assertFalse(recovery.deduction_id.is_pretax)

    def test_an_entry_can_also_say_the_same_as_the_standard(self):
        same = self.entry(title="Same", tax_treatment=False)
        same.approve()
        self.assertFalse(same.allowance_id.is_taxable)

    def test_the_entrys_own_choice_beats_the_employees_exception(self):
        SystemComponentTaxOverride.objects.create(
            system_key="arrears", employee_id=self.adam, value=True
        )
        follows, decides = self.entry(title="Follows"), self.entry(
            title="Decides", tax_treatment=False
        )
        follows.approve()
        decides.approve()
        self.assertTrue(follows.allowance_id.is_taxable)
        self.assertFalse(decides.allowance_id.is_taxable)

    def test_editing_the_standard_item_leaves_an_entrys_own_choice_alone(self):
        pinned = self.entry(title="Pinned", tax_treatment=False)
        follows = self.entry(title="Follows")
        pinned.approve()
        follows.approve()
        template = Allowance.objects.entire().get(system_key="arrears")
        template.is_taxable = True
        template.save()
        pinned.allowance_id.refresh_from_db()
        follows.allowance_id.refresh_from_db()
        self.assertFalse(pinned.allowance_id.is_taxable)
        self.assertTrue(follows.allowance_id.is_taxable)
        recovery_template = Deduction.objects.entire().get(system_key="recovery")
        keep = self.entry("recovery", title="Keep", tax_treatment=True)
        move = self.entry("recovery", title="Move")
        keep.approve()
        move.approve()
        recovery_template.is_pretax = False
        recovery_template.save()
        keep.deduction_id.refresh_from_db()
        move.deduction_id.refresh_from_db()
        self.assertTrue(keep.deduction_id.is_pretax)
        self.assertFalse(move.deduction_id.is_pretax)


class RevertAndDeleteTests(Fixture):
    def test_reverting_a_draft_changes_nothing(self):
        entry = self.entry()
        entry.revert()
        self.assertEqual(entry.status, "draft")

    def test_reverting_confirmed_arrears_removes_its_earning_and_it_can_be_confirmed_again(
        self,
    ):
        entry = self.entry()
        entry.approve(approved_by=self.bea)
        earning_id = entry.allowance_id_id
        entry.revert()
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertIsNone(entry.approved_by)
        self.assertIsNone(entry.allowance_id)
        self.assertFalse(Allowance.objects.entire().filter(pk=earning_id).exists())
        entry.approve()
        self.assertEqual(entry.status, "approved")

    def test_reverting_a_confirmed_recovery_removes_its_deduction(self):
        entry = self.entry("recovery")
        entry.approve()
        deduction_id = entry.deduction_id_id
        entry.revert()
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertIsNone(entry.deduction_id)
        self.assertFalse(Deduction.objects.entire().filter(pk=deduction_id).exists())

    def test_arrears_already_on_a_payslip_cannot_go_back_to_draft(self):
        entry = self.entry()
        entry.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        self.assertTrue(entry.is_paid())
        with self.assertRaises(ValidationError):
            entry.revert()
        self.assertEqual(entry.status, "approved")

    def test_a_recovery_a_payslip_has_taken_cannot_go_back_to_draft(self):
        entry = self.entry("recovery")
        entry.approve()
        self.assertFalse(entry.is_paid())
        self.payslip(
            self.adam, date(2026, 12, 1), date(2026, 12, 31)
        ).installment_ids.add(entry.deduction_id)
        self.assertTrue(entry.is_paid())
        with self.assertRaises(ValidationError):
            entry.revert()
        self.assertIsNotNone(entry.deduction_id)

    def test_a_draft_is_never_paid(self):
        self.assertFalse(self.entry().is_paid())

    def test_a_confirmed_entry_cannot_be_deleted_but_a_draft_can(self):
        confirmed = self.entry()
        confirmed.approve()
        with self.assertRaises(ValidationError):
            confirmed.delete()
        draft = self.entry(title="Other")
        draft.delete()
        self.assertFalse(PayAdjustment.objects.filter(title="Other").exists())

    def test_an_entry_on_a_payslip_says_so_when_deleted(self):
        entry = self.entry()
        entry.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        with self.assertRaisesMessage(ValidationError, "On A Payslip"):
            entry.delete()
        self.assertTrue(PayAdjustment.objects.filter(pk=entry.pk).exists())


class AppliedInTests(Fixture):
    def test_a_draft_has_no_payslip(self):
        self.assertIsNone(self.entry().payslip())

    def test_confirmed_arrears_is_pending_until_a_payslip_carries_it(self):
        entry = self.entry()
        entry.approve()
        self.assertIsNone(entry.payslip())

    def test_arrears_is_found_by_its_earning_on_the_payslip(self):
        entry = self.entry()
        entry.approve()
        other = self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        other.pay_head_data = {
            "allowances": [{"allowance_id": entry.allowance_id_id, "amount": 1000.0}]
        }
        other.save()
        self.assertEqual(entry.payslip(), other)

    def test_arrears_falls_back_to_the_employees_payslip_for_the_month(self):
        entry = self.entry()
        entry.approve()
        slip = self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        self.assertEqual(entry.payslip(), slip)
        self.payslip(self.bea, date(2026, 12, 1), date(2026, 12, 31))
        self.assertEqual(entry.payslip(), slip)

    def test_a_recovery_is_found_on_the_payslip_that_took_its_deduction(self):
        entry = self.entry("recovery")
        entry.approve()
        self.assertIsNone(entry.payslip())
        slip = self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        slip.installment_ids.add(entry.deduction_id)
        self.assertEqual(entry.payslip(), slip)


class BulkChangeTests(Fixture):
    """Several entries changed at once, each by the rules of one."""

    def drafts(self, count=3):
        return [
            self.entry(title=f"Draft {n}", amount=100.0 * (n + 1)) for n in range(count)
        ]

    def change(self, entries, **changes):
        return PayAdjustment.bulk_change(
            PayAdjustment.objects.filter(pk__in=[e.pk for e in entries]).order_by("pk"),
            **changes,
        )

    def test_the_tax_setting_and_the_date_change_on_every_draft(self):
        drafts = self.drafts()
        updated, problems = self.change(
            drafts, taxable=True, pay_date=date(2027, 1, 20)
        )
        self.assertEqual((updated, problems), (3, []))
        for entry in PayAdjustment.objects.filter(pk__in=[d.pk for d in drafts]):
            self.assertEqual(
                (entry.tax_treatment, entry.pay_date, entry.status),
                (True, date(2027, 1, 20), "draft"),
            )

    def test_confirming_many_makes_every_pay_line(self):
        drafts = self.drafts()
        updated, problems = self.change(drafts, status="approved", approved_by=self.bea)
        self.assertEqual((updated, problems), (3, []))
        for entry in PayAdjustment.objects.filter(pk__in=[d.pk for d in drafts]):
            self.assertEqual((entry.status, entry.approved_by), ("approved", self.bea))
            self.assertIsNotNone(entry.pay_line())

    def test_an_entry_already_in_that_status_is_not_counted(self):
        entry = self.entry()
        entry.approve()
        self.assertEqual(self.change([entry], status="approved"), (0, []))
        self.assertEqual(
            self.change([self.entry(title="Another")], status="draft"), (0, [])
        )

    def test_sending_confirmed_entries_back_takes_their_pay_lines_away(self):
        confirmed = [self.entry(title="One"), self.entry("recovery", title="Two")]
        for entry in confirmed:
            entry.approve()
        updated, problems = self.change(confirmed, status="draft")
        self.assertEqual((updated, problems), (2, []))
        for entry in PayAdjustment.objects.filter(pk__in=[c.pk for c in confirmed]):
            self.assertEqual(entry.status, "draft")
            self.assertIsNone(entry.pay_line())

    def test_what_a_payslip_carries_is_named_and_stays_confirmed(self):
        paid, free = self.entry(title="Paid"), self.entry(
            title="Free", employee_id=self.bea
        )
        paid.approve()
        free.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        updated, problems = self.change([paid, free], status="draft")
        self.assertEqual(updated, 1)
        self.assertEqual(len(problems), 1)
        self.assertIn("Paid", problems[0])
        paid.refresh_from_db()
        free.refresh_from_db()
        self.assertEqual((paid.status, free.status), ("approved", "draft"))

    def test_edits_to_a_confirmed_entry_are_refused_and_named(self):
        entry = self.entry()
        entry.approve()
        updated, problems = self.change([entry], taxable=True)
        self.assertEqual(updated, 0)
        self.assertIn("Locked", problems[0])
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.tax_treatment), ("approved", None))

    def test_sending_back_and_editing_in_one_go_unlocks_a_confirmed_entry(self):
        entry = self.entry()
        entry.approve()
        updated, problems = self.change(
            [entry], status="draft", taxable=True, pay_date=date(2027, 2, 10)
        )
        self.assertEqual((updated, problems), (1, []))
        entry.refresh_from_db()
        self.assertEqual(
            (entry.status, entry.tax_treatment, entry.pay_date),
            ("draft", True, date(2027, 2, 10)),
        )
        self.assertIsNone(entry.allowance_id)

    def test_editing_and_confirming_in_one_go_uses_the_new_values_on_the_pay_line(self):
        entry = self.entry()
        updated, problems = self.change(
            [entry], status="approved", taxable=True, pay_date=date(2027, 2, 10)
        )
        self.assertEqual((updated, problems), (1, []))
        entry.refresh_from_db()
        self.assertEqual(entry.allowance_id.one_time_date, date(2027, 2, 10))
        self.assertTrue(entry.allowance_id.is_taxable)

    def test_taxable_changes_only_arrears_and_pre_tax_only_recoveries(self):
        arrears = self.entry(title="Arrears One")
        recovery = self.entry("recovery", title="Recovery One", employee_id=self.bea)
        updated, problems = self.change([arrears, recovery], taxable=False)
        self.assertEqual((updated, problems), (1, []))
        arrears.refresh_from_db()
        recovery.refresh_from_db()
        self.assertIs(arrears.tax_treatment, False)
        self.assertIsNone(recovery.tax_treatment)
        updated, problems = self.change([arrears, recovery], pre_tax=True)
        self.assertEqual((updated, problems), (1, []))
        arrears.refresh_from_db()
        recovery.refresh_from_db()
        self.assertIs(arrears.tax_treatment, False)
        self.assertIs(recovery.tax_treatment, True)

    def test_both_settings_together_each_go_to_their_own_type(self):
        arrears = self.entry(title="Arrears Two")
        recovery = self.entry("recovery", title="Recovery Two", employee_id=self.bea)
        self.assertEqual(
            self.change([arrears, recovery], taxable=True, pre_tax=False), (2, [])
        )
        arrears.refresh_from_db()
        recovery.refresh_from_db()
        self.assertEqual((arrears.tax_treatment, recovery.tax_treatment), (True, False))

    def test_a_setting_for_the_other_type_does_not_touch_or_complain_about_a_confirmed_entry(
        self,
    ):
        confirmed_recovery = self.entry("recovery", title="Confirmed Recovery")
        confirmed_recovery.approve()
        self.assertEqual(self.change([confirmed_recovery], taxable=True), (0, []))
        updated, problems = self.change([confirmed_recovery], pre_tax=True)
        self.assertEqual(updated, 0)
        self.assertIn("Locked", problems[0])

    def test_a_closed_month_leaves_that_entry_alone_and_the_rest_change(self):
        self.payslip(self.bea, date(2027, 1, 1), date(2027, 1, 31))
        ok_one = self.entry(title="Fine One")
        blocked = self.entry(title="Blocked", employee_id=self.bea)
        ok_two = self.entry(title="Fine Two", employee_id=self.adam)
        updated, problems = self.change(
            [ok_one, blocked, ok_two], pay_date=date(2027, 1, 15)
        )
        self.assertEqual(updated, 2)
        self.assertEqual(len(problems), 1)
        self.assertIn("Blocked", problems[0])
        self.assertIn("January 2027", problems[0])
        blocked.refresh_from_db()
        self.assertEqual(blocked.pay_date, date(2026, 12, 5))
        self.assertEqual(
            PayAdjustment.objects.get(pk=ok_two.pk).pay_date, date(2027, 1, 15)
        )

    def test_a_failed_entry_does_not_leave_half_a_change_behind(self):
        entry = self.entry()
        self.payslip(self.adam, date(2027, 1, 1), date(2027, 1, 31))
        self.change(
            [entry], status="approved", taxable=True, pay_date=date(2027, 1, 15)
        )
        entry.refresh_from_db()
        self.assertEqual(
            (entry.status, entry.tax_treatment, entry.pay_date),
            ("draft", None, date(2026, 12, 5)),
        )


class BulkFormTests(Fixture):
    def test_something_must_be_chosen(self):
        self.assertFalse(PayAdjustmentBulkForm({}).is_valid())
        blank = {"status": "", "taxable": "", "pre_tax": "", "pay_date": ""}
        self.assertFalse(PayAdjustmentBulkForm(blank).is_valid())

    def test_taxable_and_pre_tax_are_separate_inputs(self):
        form = PayAdjustmentBulkForm()
        self.assertEqual(
            list(form.fields), ["status", "taxable", "pre_tax", "pay_date"]
        )
        self.assertEqual(str(form.fields["taxable"].label), "Taxable (Arrears Only)")
        self.assertEqual(str(form.fields["pre_tax"].label), "Pre-Tax (Recovery Only)")
        self.assertEqual(
            [(key, str(label)) for key, label in form.fields["status"].choices],
            [("", "---------"), ("draft", "Draft"), ("approved", "Confirmed")],
        )
        for name in ("taxable", "pre_tax"):
            self.assertEqual(
                [(key, str(label)) for key, label in form.fields[name].choices],
                [("", "---------"), ("true", "Yes"), ("false", "No")],
            )

    def test_what_is_left_blank_is_not_changed(self):
        form = PayAdjustmentBulkForm({"taxable": "false"})
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.changes(),
            {"status": None, "taxable": False, "pre_tax": None, "pay_date": None},
        )
        form = PayAdjustmentBulkForm(
            {"status": "approved", "pre_tax": "true", "pay_date": "2027-03-01"}
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.changes(),
            {
                "status": "approved",
                "taxable": None,
                "pre_tax": True,
                "pay_date": date(2027, 3, 1),
            },
        )


class FilterTests(Fixture):
    """The list's filters, by type, status, where applied, employee and pay date."""

    def setUp(self):
        super().setUp()
        self.arrears = self.entry(title="Arrears Row")
        self.recovery = self.entry(
            "recovery", title="Recovery Row", employee_id=self.bea
        )
        self.confirmed = self.entry(title="Confirmed Row", pay_date=date(2027, 2, 10))
        self.confirmed.approve()

    def titles(self, *rows, **params):
        """Titles that pass; each row is a (field, lookup, value) of the Advanced "+ Add filter" builder."""
        if rows:
            params["custom_field"], params["custom_lookup"], params["custom_value"] = (
                list(c) for c in zip(*rows)
            )
        queryset = PayAdjustmentFilter(params, queryset=PayAdjustment.objects.all()).qs
        return sorted(entry.title for entry in queryset)

    def test_no_filter_lists_everything(self):
        self.assertEqual(
            self.titles(), ["Arrears Row", "Confirmed Row", "Recovery Row"]
        )

    def test_by_type_and_by_status(self):
        self.assertEqual(self.titles(kind="recovery"), ["Recovery Row"])
        self.assertEqual(self.titles(kind="arrears"), ["Arrears Row", "Confirmed Row"])
        self.assertEqual(self.titles(status="approved"), ["Confirmed Row"])
        self.assertEqual(self.titles(status="draft"), ["Arrears Row", "Recovery Row"])

    def test_by_employee_name_or_badge(self):
        bea = self.bea
        self.assertEqual(
            self.titles(name_or_badge=bea.employee_first_name), ["Recovery Row"]
        )
        self.assertEqual(self.titles(name_or_badge=bea.badge_id), ["Recovery Row"])
        self.assertEqual(self.titles(name_or_badge="Nobody Atall"), [])

    def test_several_names_or_badge_ids_can_be_given_with_commas(self):
        both = f"{self.adam.badge_id}, {self.bea.badge_id}"
        self.assertEqual(
            self.titles(name_or_badge=both),
            ["Arrears Row", "Confirmed Row", "Recovery Row"],
        )
        self.assertEqual(
            self.titles(name_or_badge=f"{self.bea.badge_id},, Nobody"), ["Recovery Row"]
        )

    def test_by_the_employees_email(self):
        self.assertEqual(self.titles(email="bea-adj"), ["Recovery Row"])
        self.assertEqual(
            self.titles(email="adam-adj"), ["Arrears Row", "Confirmed Row"]
        )

    def test_by_the_employees_work_info(self):
        from base.models import Department, JobPosition

        department = Department.objects.create(department="Filter Dept")
        position = JobPosition.objects.create(
            job_position="Filter Position", department_id=department
        )
        work = self.bea.employee_work_info
        work.department_id = department
        work.job_position_id = position
        work.reporting_manager_id = self.adam
        work.save()
        key = "employee_id__employee_work_info__"
        self.assertEqual(
            self.titles(**{key + "department_id": [department.pk]}), ["Recovery Row"]
        )
        self.assertEqual(
            self.titles(**{key + "job_position_id": [position.pk]}), ["Recovery Row"]
        )
        self.assertEqual(
            self.titles(**{key + "reporting_manager_id": [self.adam.pk]}),
            ["Recovery Row"],
        )
        company = self.bea.employee_work_info.company_id
        self.assertEqual(
            self.titles(**{key + "company_id": [company.pk]}),
            ["Arrears Row", "Confirmed Row", "Recovery Row"],
        )

    def test_by_amount_range(self):
        self.entry(title="Big Row", amount=5000.0)
        everyone = ["Arrears Row", "Confirmed Row", "Recovery Row"]
        self.assertEqual(self.titles(("amount", "gte", "2000")), ["Big Row"])
        self.assertEqual(self.titles(("amount", "lte", "1000")), everyone)
        self.assertEqual(
            self.titles(("amount", "gte", "1000"), ("amount", "lte", "1000")), everyone
        )
        self.assertEqual(
            self.titles(("amount", "gte", "1000.5"), ("amount", "lte", "4999")), []
        )
        self.assertEqual(
            self.titles(("amount", "gte", "not a number")),
            sorted(everyone + ["Big Row"]),
        )

    def test_by_title_and_reason(self):
        self.entry(title="Bonus Catch Up", reason="Missed in the last cycle")
        self.assertEqual(
            self.titles(("title", "icontains", "catch")), ["Bonus Catch Up"]
        )
        self.assertEqual(
            self.titles(("reason", "icontains", "last cycle")), ["Bonus Catch Up"]
        )
        self.assertEqual(self.titles(("reason", "icontains", "nothing like this")), [])

    def test_a_row_cannot_name_a_field_or_lookup_outside_the_list(self):
        everyone = ["Arrears Row", "Confirmed Row", "Recovery Row"]
        self.assertEqual(
            self.titles(("employee_id__password", "icontains", "x")), everyone
        )
        self.assertEqual(self.titles(("amount", "regex", ".*")), everyone)

    def test_by_tax_setting(self):
        self.entry(title="Taxed", tax_treatment=True)
        self.entry(title="Untaxed", tax_treatment=False)
        self.assertEqual(self.titles(tax="yes"), ["Taxed"])
        self.assertEqual(self.titles(tax="no"), ["Untaxed"])
        self.assertEqual(
            self.titles(tax="standard"),
            ["Arrears Row", "Confirmed Row", "Recovery Row"],
        )

    def test_by_who_confirmed_it(self):
        self.confirmed.approved_by = self.bea
        self.confirmed.save()
        self.assertEqual(self.titles(approved_by=[self.bea.pk]), ["Confirmed Row"])
        self.assertEqual(self.titles(approved_by=[self.adam.pk]), [])

    def test_by_when_it_was_confirmed(self):
        today = timezone.localdate().isoformat()
        self.assertEqual(self.titles(("confirmed_on", "gte", today)), ["Confirmed Row"])
        self.assertEqual(
            self.titles(("confirmed_on", "exact", today)), ["Confirmed Row"]
        )
        self.assertEqual(self.titles(("confirmed_on", "lte", "2000-01-01")), [])

    def test_by_pay_date_range(self):
        everyone = ["Arrears Row", "Confirmed Row", "Recovery Row"]
        self.assertEqual(
            self.titles(("pay_date", "gte", "2027-01-01")), ["Confirmed Row"]
        )
        self.assertEqual(
            self.titles(("pay_date", "lte", "2026-12-31")),
            ["Arrears Row", "Recovery Row"],
        )
        self.assertEqual(
            self.titles(
                ("pay_date", "gte", "2026-12-01"), ("pay_date", "lte", "2027-02-10")
            ),
            everyone,
        )
        self.assertEqual(self.titles(("pay_date", "gt", "2027-02-10")), [])
        self.assertEqual(
            self.titles(("pay_date", "exact", "2026-12-05")),
            ["Arrears Row", "Recovery Row"],
        )
        self.assertEqual(self.titles(("pay_date", "gte", "2027-03-01")), [])

    def test_by_where_it_was_applied(self):
        self.assertEqual(
            self.titles(applied="not_applied"), ["Arrears Row", "Recovery Row"]
        )
        self.assertEqual(self.titles(applied="pending"), ["Confirmed Row"])
        self.assertEqual(self.titles(applied="applied"), [])
        self.payslip(self.adam, date(2027, 2, 1), date(2027, 2, 28))
        self.assertEqual(self.titles(applied="applied"), ["Confirmed Row"])
        self.assertEqual(self.titles(applied="pending"), [])
        self.assertEqual(
            self.titles(applied="not_applied"), ["Arrears Row", "Recovery Row"]
        )

    def test_filters_combine(self):
        self.assertEqual(
            self.titles(kind="arrears", status="approved"), ["Confirmed Row"]
        )
        self.assertEqual(self.titles(kind="recovery", status="approved"), [])
        self.assertEqual(
            self.titles(kind="arrears", applied="pending"), ["Confirmed Row"]
        )

    def test_search_still_works_beside_the_filters(self):
        self.assertEqual(self.titles(search="Recovery"), ["Recovery Row"])
        self.assertEqual(
            self.titles(search="Row", kind="arrears"), ["Arrears Row", "Confirmed Row"]
        )


class StandardItemTests(Fixture):
    def test_the_two_standard_items_exist_with_their_tax_settings(self):
        arrears = Allowance.objects.entire().get(system_key="arrears")
        recovery = Deduction.objects.entire().get(system_key="recovery")
        self.assertFalse(arrears.is_taxable)
        self.assertTrue(recovery.is_pretax)
        self.assertTrue(arrears.is_system and recovery.is_system)


class ViewTests(Fixture):
    def setUp(self):
        super().setUp()
        user = make_user("adjadmin", is_superuser=True)
        make_employee(company=self.company, email="adjadmin@test.horilla", user=user)
        self.client.force_login(user)

    def get(self, name, *args, **params):
        return self.client.get(reverse(name, args=args), params, **HX).content.decode()

    def data(self, **fields):
        data = {
            "employee_id": self.adam.pk,
            "kind": "arrears",
            "title": "Status Entry",
            "amount": "700",
            "pay_date": "2026-12-05",
            "tax_treatment": "true",
        }
        data.update(fields)
        return data

    def save(self, data, pk=None):
        url = (
            reverse("update-pay-adjustment", args=[pk])
            if pk
            else reverse("create-pay-adjustment")
        )
        return self.client.post(url, data, **HX)

    # ---- the tab, nav and list ----
    def test_the_tab_embeds_the_nav_and_the_list_container(self):
        html = self.get("payroll-settings-pay-adjustment-tab")
        self.assertIn(reverse("pay-adjustment-nav"), html)
        self.assertIn('id="payAdjustmentListContainer"', html)

    def test_the_list_is_tightened_to_one_slim_line_per_entry(self):
        html = self.get("payroll-settings-pay-adjustment-tab")
        self.assertIn("#payAdjustmentListContainer table td", html)
        self.assertIn("height: 26px !important", html)
        self.entry(title="Pill Row")
        row = self.get("pay-adjustment-list-view")
        self.assertIn("padding: 1px 9px", row)
        self.assertNotIn("px-2.5 py-1", row)

    def test_the_tab_is_listed_in_configuration_before_payslip_auto_generation(self):
        html = self.get("payroll-settings-tab-view")
        self.assertIn(reverse("payroll-settings-pay-adjustment-tab"), html)
        self.assertRegex(html, r"Arrears (&amp;|&) Recovery")
        self.assertLess(
            html.index(reverse("payroll-settings-pay-adjustment-tab")),
            html.index(reverse("payroll-settings-auto-payslip-tab")),
        )

    def test_the_nav_has_the_title_search_and_create(self):
        html = self.get("pay-adjustment-nav")
        self.assertIn("Arrears &amp; Recovery", html)
        self.assertIn(reverse("create-pay-adjustment"), html)
        self.assertIn('name="search"', html)

    def test_the_filter_panel_closes_every_div_it_opens(self):
        """An unbalanced panel pushes the nav's Filter, Actions and Create buttons out of line."""
        source = open(
            "payroll/templates/cbv/pay_adjustment/filter.html", encoding="utf-8"
        ).read()
        self.assertEqual(source.count("<div"), source.count("</div>"))

    def test_the_nav_has_a_filter_panel_with_every_filter(self):
        html = self.get("pay-adjustment-nav")
        self.assertIn("filterForm", html)
        key = "employee_id__employee_work_info__"
        names = [
            "kind",
            "status",
            "applied",
            "name_or_badge",
            "email",
            "tax",
            "approved_by",
        ] + [
            key + field
            for field in (
                "company_id",
                "reporting_manager_id",
                "department_id",
                "job_position_id",
                "shift_id",
                "tags",
            )
        ]
        for name in names:
            self.assertIn(f'name="{name}"', html, name)
        labels = (
            "Type",
            "Status",
            "Applied In",
            "Name or Badge ID",
            "Work Info",
            "Email",
            "Company",
            "Reporting Manager",
            "Department",
            "Job Position",
            "Shift",
            "Employee Tag",
            "Taxable / Pre-Tax",
            "Confirmed By",
            "Advanced",
        )
        for label in labels:
            self.assertRegex(html, r">\s*" + label + r"\s*<", label)
        self.assertIn("e.g. John, PEP01, PEP02", html)
        # Sections named for what they hold: no catch-all "Entry".
        self.assertRegex(html, r">\s*Type (&amp;|&) Status\s*<")
        self.assertNotRegex(html, r">\s*Entry\s*<")
        # Each section has its own icon; the up-down arrows are gone.
        for icon in ("pricetag-outline", "briefcase-outline", "options-outline"):
            self.assertIn(f'ion-icon name="{icon}"', html, icon)
        self.assertNotIn("swap-vertical-outline", html)
        # Taxable / Pre-Tax and Confirmed By sit in the first section; Advanced is the "+ Add filter" builder.
        self.assertLess(html.index("Taxable / Pre-Tax"), html.index("Work Info"))
        self.assertLess(html.index("Confirmed By"), html.index("Work Info"))
        self.assertIn("addCustomFilterRow('pay-adjustment')", html)
        # The Advanced rows wait for Apply instead of refreshing the list as they are edited.
        self.assertIn("event.stopPropagation()", html)
        self.assertIn('id="customFilterFields-pay-adjustment"', html)
        for label in ("Amount", "Pay Date", "Confirmed On", "Title", "Reason"):
            self.assertIn(f'"label": "{label}"', html, label)

    def test_the_nav_offers_group_by_with_every_field(self):
        from payroll.cbv.pay_adjustments import GROUP_BY_FIELDS

        html = self.get("pay-adjustment-nav")
        self.assertIn("Group By", html)
        self.assertIn('id="nestedGroupByLevels"', html)
        for field, label in GROUP_BY_FIELDS:
            self.assertIn(f'value="{field}"', html, field)
            self.assertRegex(
                html,
                r'value="'
                + re.escape(field)
                + r'"[^>]*>\s*'
                + re.escape(str(label))
                + r"\s*<",
            )

    def test_the_list_and_the_nav_group_by_the_same_fields(self):
        from payroll.cbv.pay_adjustments import (
            GROUP_BY_FIELDS,
            PayAdjustmentListView,
            PayAdjustmentNav,
        )

        self.assertEqual(PayAdjustmentListView.nested_group_by_fields, GROUP_BY_FIELDS)
        self.assertEqual(PayAdjustmentNav.group_by_fields, GROUP_BY_FIELDS)
        self.assertEqual(PayAdjustmentNav.nested_group_by_fields, GROUP_BY_FIELDS)

    def test_the_list_groups_by_each_field_and_keeps_every_entry(self):
        from payroll.cbv.pay_adjustments import GROUP_BY_FIELDS

        self.entry(title="Grouped Arrears")
        confirmed = self.entry(
            "recovery", title="Grouped Recovery", employee_id=self.bea
        )
        confirmed.approve()
        for field, _label in GROUP_BY_FIELDS:
            response = self.client.get(
                reverse("pay-adjustment-list-view"), {"field": field}, **HX
            )
            self.assertEqual(response.status_code, 200, field)
        html = self.client.get(
            reverse("pay-adjustment-list-view"), {"field": "kind"}, **HX
        ).content.decode()
        for text in ("Arrears", "Recovery"):
            self.assertIn(text, html)
        by_status = self.client.get(
            reverse("pay-adjustment-list-view"), {"field": "status"}, **HX
        ).content.decode()
        self.assertIn("Confirmed", by_status)
        self.assertNotIn(">approved<", by_status)

    def test_the_list_obeys_the_filters(self):
        self.entry(title="Plain Arrears")
        self.entry("recovery", title="Plain Recovery", employee_id=self.bea)
        recoveries = self.get("pay-adjustment-list-view", kind="recovery")
        self.assertIn("Plain Recovery", recoveries)
        self.assertNotIn("Plain Arrears", recoveries)
        drafts_only = self.get("pay-adjustment-list-view", status="approved")
        self.assertNotIn("Plain Arrears", drafts_only)
        later = self.get(
            "pay-adjustment-list-view",
            custom_field="pay_date",
            custom_lookup="gte",
            custom_value="2027-01-01",
        )
        self.assertNotIn("Plain Arrears", later)

    def test_the_list_shows_entries_and_searches_them(self):
        self.entry(title="Findable Entry")
        self.entry(title="Other Entry", employee_id=self.bea)
        self.assertIn("Findable Entry", self.get("pay-adjustment-list-view"))
        searched = self.get("pay-adjustment-list-view", search="Findable")
        self.assertIn("Findable Entry", searched)
        self.assertNotIn("Other Entry", searched)

    def test_the_list_has_just_the_essential_columns_and_where_it_was_applied(self):
        self.entry()
        html = self.get("pay-adjustment-list-view")
        for heading in (
            "Employee",
            "Type",
            "Title",
            "Amount",
            "Pay Date",
            "Applied In",
            "Status",
        ):
            self.assertRegex(html, r">\s*" + heading + r"\s*<", heading)
        for gone in ("Period", "Actions", "Instalments", "Balance Left"):
            self.assertNotRegex(html, r">\s*" + gone + r"\s*<", gone)

    def test_the_status_column_is_a_draft_or_confirmed_dropdown(self):
        draft = self.entry(title="Draft Row")
        confirmed = self.entry(title="Confirmed Row")
        confirmed.approve()
        html = self.get("pay-adjustment-list-view")
        self.assertIn(reverse("set-pay-adjustment-status", args=[draft.pk]), html)
        self.assertIn(reverse("set-pay-adjustment-status", args=[confirmed.pk]), html)
        self.assertRegex(html, r'<option value="draft"\s+selected>\s*Draft')
        self.assertRegex(html, r'<option value="approved"\s+selected>\s*Confirmed')
        # The shared confirm handler re-sends only hx-vals, so the dropdown posts its own value.
        self.assertIn('onchange="payAdjustmentSetStatus(this)"', html)
        self.assertNotIn("hx-confirm", html)
        tab = self.get("payroll-settings-pay-adjustment-tab")
        self.assertIn("function payAdjustmentSetStatus", tab)
        self.assertIn("data-asking", tab)
        self.assertNotIn("Cancelled", html)

    def test_the_applied_in_column_shows_the_payslip_or_pending_or_a_dash(self):
        draft = self.entry(title="Draft Row")
        waiting = self.entry(title="Waiting Row", employee_id=self.bea)
        waiting.approve()
        used = self.entry(title="Used Row", pay_date=date(2027, 3, 5))
        used.approve()
        slip = self.payslip(self.adam, date(2027, 3, 1), date(2027, 3, 31))
        slip.reference = "March Run"
        slip.save()
        html = self.get("pay-adjustment-list-view")
        self.assertRegex(html, r">\s*Applied In\s*<")
        # Applied is a green pill with a tick and the word, in one link: the tooltip gives the period
        # and the run, and clicking opens the payslip.
        self.assertRegex(
            html,
            r'<a href="'
            + re.escape(reverse("view-created-payslip", args=[slip.pk]))
            + r'"\s+'
            r'title="01 Mar 2027 – 31 Mar 2027 · March Run"[^>]*>\s*'
            r'<ion-icon name="checkmark-circle"[^>]*></ion-icon>\s*Applied\s*</a>',
        )
        self.assertNotRegex(html, r">\s*01 Mar 2027")
        self.assertRegex(html, r">\s*Pending\s*<")
        self.assertIsNone(draft.payslip())
        # A draft is a "Not Applied" pill, a waiting entry a "Pending" pill, an applied one a tick.
        self.assertRegex(html, r">\s*Not Applied\s*<")
        self.assertIn('name="checkmark-circle"', html)
        for gone in ("document-outline", "time-outline"):
            self.assertNotIn(f'name="{gone}"', html, gone)

    def test_the_applied_in_column_is_the_last_one(self):
        self.entry()
        html = self.get("pay-adjustment-list-view")
        headings = (
            "Employee",
            "Type",
            "Title",
            "Amount",
            "Pay Date",
            "Status",
            "Applied In",
        )
        positions = [
            re.search(r">\s*" + heading + r"\s*<", html).start() for heading in headings
        ]
        self.assertEqual(positions, sorted(positions))

    # ---- bulk select and update ----
    def bulk_paths(self):
        html = self.get("pay-adjustment-list-view")
        get_path = re.search(r'hx-post="/(get-bulk-update-[^"]+)"', html).group(1)
        return get_path, get_path.replace("get-bulk-update", "post-bulk-update")

    def test_the_list_has_row_checkboxes_and_an_update_button(self):
        entries = [self.entry(title=f"Row {n}") for n in range(3)]
        html = self.get("pay-adjustment-list-view")
        self.assertIn("list-table-row", html)  # the checkbox on each row
        self.assertIn("bulk_udate_", html)
        self.assertIn("get-bulk-update", html)
        self.assertIn(
            'id="selectedInstances"', self.get("payroll-settings-pay-adjustment-tab")
        )
        self.assertEqual(len(entries), 3)

    # ---- bulk delete ----
    def bulk_delete(self, entries, **extra):
        return self.client.post(
            reverse("pay-adjustment-bulk-delete"),
            {"ids": json.dumps([e.pk for e in entries])},
            **extra,
        )

    def test_the_actions_menu_offers_delete_through_the_shared_dialogs(self):
        html = self.get("pay-adjustment-nav")
        self.assertRegex(html, r">\s*Delete\s*<")
        self.assertIn("payAdjustmentBulkDelete()", html)
        tab = self.get("payroll-settings-pay-adjustment-tab")
        self.assertIn("confirmBulkDelete", tab)
        self.assertIn(reverse("pay-adjustment-bulk-delete"), tab)

    def test_bulk_delete_removes_drafts_and_names_what_it_could_not(self):
        drafts = [
            self.entry(title="One"),
            self.entry(title="Two", employee_id=self.bea),
        ]
        confirmed = self.entry(title="Locked", employee_id=self.bea)
        confirmed.approve()
        paid = self.entry(title="Paid", pay_date=date(2026, 12, 6))
        paid.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        response = self.bulk_delete(drafts + [confirmed, paid])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(PayAdjustment.objects.values_list("title", flat=True)),
            ["Locked", "Paid"],
        )
        shown = " | ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("Move A Confirmed Entry Back To Draft", shown)
        self.assertIn("It Is Already On A Payslip", shown)

    def test_bulk_delete_without_ids_is_refused(self):
        self.assertEqual(
            self.client.post(reverse("pay-adjustment-bulk-delete"), {}).status_code, 400
        )

    def test_bulk_delete_needs_the_delete_permission(self):
        entry = self.entry()
        self.client.force_login(make_user("nodelete"))
        self.bulk_delete([entry])
        self.assertTrue(PayAdjustment.objects.filter(pk=entry.pk).exists())

    def test_the_status_of_an_entry_on_a_payslip_is_locked_in_the_list(self):
        entry = self.entry(title="Paid Row")
        entry.approve()
        self.entry(title="Other Row", employee_id=self.bea)
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        html = self.get("pay-adjustment-list-view")
        self.assertEqual(html.count("So Its Status Is Locked"), 1)

    def test_the_update_form_offers_status_the_tax_setting_and_the_date(self):
        entries = [self.entry(title="One"), self.entry(title="Two")]
        get_path, _post = self.bulk_paths()
        response = self.client.post(
            "/" + get_path, {"instance_ids": str([e.pk for e in entries])}, **HX
        )
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        for label in (
            "Status",
            "Taxable (Arrears Only)",
            "Pre-Tax (Recovery Only)",
            "Pay Date",
        ):
            self.assertIn(label, html)
        self.assertNotIn("Taxable / Pre-Tax", html)
        self.assertIn("(2 Records)", html)
        # Styled like the other bulk forms, and with nothing to "add another" of.
        self.assertEqual(html.count("oh-select oh-select-2 w-100"), 3)
        self.assertIn("oh-input w-100", html)
        self.assertNotIn("Save And Add Another", html)

    def test_updating_the_selected_entries_changes_each_by_the_rules_of_one(self):
        drafts = [
            self.entry(title="One"),
            self.entry(title="Two", employee_id=self.bea),
        ]
        confirmed = self.entry(title="Locked")
        confirmed.approve()
        _get, post_path = self.bulk_paths()
        response = self.client.post(
            "/" + post_path,
            {
                "instance_ids": str([d.pk for d in drafts] + [confirmed.pk]),
                "taxable": "true",
                "pre_tax": "false",
                "pay_date": "2027-01-20",
            },
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        for draft in drafts:
            draft.refresh_from_db()
            self.assertEqual(
                (draft.tax_treatment, draft.pay_date), (True, date(2027, 1, 20))
            )
        confirmed.refresh_from_db()
        self.assertEqual(
            (confirmed.tax_treatment, confirmed.pay_date), (None, date(2026, 12, 5))
        )

    def test_the_update_form_sends_taxable_to_arrears_and_pre_tax_to_recoveries(self):
        arrears = self.entry(title="Arrears Row")
        recovery = self.entry("recovery", title="Recovery Row", employee_id=self.bea)
        _get, post_path = self.bulk_paths()
        self.client.post(
            "/" + post_path,
            {
                "instance_ids": str([arrears.pk, recovery.pk]),
                "taxable": "false",
                "pre_tax": "true",
            },
            **HX,
        )
        arrears.refresh_from_db()
        recovery.refresh_from_db()
        self.assertEqual((arrears.tax_treatment, recovery.tax_treatment), (False, True))

    def test_confirming_the_selected_entries_from_the_update_form(self):
        drafts = [
            self.entry(title="One"),
            self.entry("recovery", title="Two", employee_id=self.bea),
        ]
        _get, post_path = self.bulk_paths()
        self.client.post(
            "/" + post_path,
            {"instance_ids": str([d.pk for d in drafts]), "status": "approved"},
            **HX,
        )
        for draft in drafts:
            draft.refresh_from_db()
            self.assertEqual(draft.status, "approved")
            self.assertIsNotNone(draft.pay_line())

    def test_the_update_form_with_nothing_chosen_or_nothing_selected_changes_nothing(
        self,
    ):
        entry = self.entry()
        _get, post_path = self.bulk_paths()
        self.client.post("/" + post_path, {"instance_ids": str([entry.pk])}, **HX)
        self.client.post(
            "/" + post_path, {"instance_ids": "[]", "status": "approved"}, **HX
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_there_are_no_row_action_buttons(self):
        self.entry()
        html = self.get("pay-adjustment-list-view")
        self.assertNotIn("approve-pay-adjustment", html)
        self.assertNotIn("cancel-pay-adjustment", html)
        self.assertNotIn("/delete-pay-adjustment/", html)

    # ---- the status dropdown and delete ----
    def test_the_dropdown_confirms_and_sends_back_to_draft(self):
        for kind, line in (("arrears", "allowance_id"), ("recovery", "deduction_id")):
            entry = self.entry(kind, title=f"{kind} row")
            url = reverse("set-pay-adjustment-status", args=[entry.pk])
            response = self.client.post(url, {"status": "approved"}, **HX)
            self.assertEqual(response.status_code, 200)
            self.assertIn("reloadPayAdjustments", response["HX-Trigger"])
            entry.refresh_from_db()
            self.assertEqual(entry.status, "approved")
            self.assertIsNotNone(getattr(entry, line))
            self.client.post(url, {"status": "draft"}, **HX)
            entry.refresh_from_db()
            self.assertEqual(entry.status, "draft")
            self.assertIsNone(getattr(entry, line))

    def test_the_dropdown_says_so_when_the_status_is_already_that(self):
        entry = self.entry()
        entry.approve()
        response = self.client.post(
            reverse("set-pay-adjustment-status", args=[entry.pk]),
            {"status": "approved"},
            **HX,
        )
        shown = " | ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("Already", shown)
        self.assertNotIn("Only A Draft", shown)

    def test_a_confirmed_entry_not_yet_on_a_payslip_goes_back_to_draft(self):
        entry = self.entry()
        entry.approve()
        self.assertFalse(entry.is_paid())
        self.client.post(
            reverse("set-pay-adjustment-status", args=[entry.pk]),
            {"status": "draft"},
            **HX,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_the_dropdown_cannot_undo_what_a_payslip_carries(self):
        entry = self.entry()
        entry.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        self.client.post(
            reverse("set-pay-adjustment-status", args=[entry.pk]),
            {"status": "draft"},
            **HX,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, "approved")

    def test_the_dropdown_refuses_a_closed_month_and_a_bad_value(self):
        entry = self.entry()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        url = reverse("set-pay-adjustment-status", args=[entry.pk])
        self.client.post(url, {"status": "approved"}, **HX)
        self.client.post(url, {"status": "cancelled"}, **HX)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_the_endpoints_only_accept_a_post(self):
        entry = self.entry()
        self.assertEqual(
            self.client.get(
                reverse("set-pay-adjustment-status", args=[entry.pk]), **HX
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(
                reverse("delete-pay-adjustment", args=[entry.pk]), **HX
            ).status_code,
            405,
        )

    def test_delete_works_for_a_draft_and_not_for_a_confirmed_entry(self):
        draft = self.entry(title="Gone")
        confirmed = self.entry(title="Kept")
        confirmed.approve()
        self.client.post(reverse("delete-pay-adjustment", args=[draft.pk]), **HX)
        self.client.post(reverse("delete-pay-adjustment", args=[confirmed.pk]), **HX)
        self.assertFalse(PayAdjustment.objects.filter(title="Gone").exists())
        self.assertTrue(PayAdjustment.objects.filter(title="Kept").exists())

    # ---- the form ----
    def test_the_form_is_the_pay_adjustment_template_and_has_no_instalments(self):
        html = self.get("create-pay-adjustment")
        self.assertIn('id="payAdjustmentFormRoot"', html)
        self.assertIn("Save And Add Another", html)
        self.assertIn("oh-modal__dialog-header", html)
        for gone in (
            "data-schedule",
            'id="id_lines"',
            'id="id_instalments"',
            "Instalment",
            "data-add-line",
        ):
            self.assertNotIn(gone, html, gone)

    def test_the_form_has_the_same_fields_for_both_types_in_order(self):
        self.assertEqual(
            list(PayAdjustmentForm().fields),
            [
                "employee_id",
                "kind",
                "title",
                "pay_date",
                "amount",
                "tax_treatment",
                "status",
                "reason",
            ],
        )
        html = self.get("create-pay-adjustment")
        order = [
            html.index(f'id="id_{name}_parent_div"')
            for name in (
                "title",
                "pay_date",
                "amount",
                "tax_treatment",
                "status",
                "reason",
            )
        ]
        self.assertEqual(order, sorted(order))

    def test_the_tax_setting_is_just_yes_or_no_and_relabels_with_the_type(self):
        form = PayAdjustmentForm()
        self.assertEqual(
            [(key, str(label)) for key, label in form.fields["tax_treatment"].choices],
            [("true", "Yes"), ("false", "No")],
        )
        self.assertTrue(form.fields["tax_treatment"].required)
        html = self.get("create-pay-adjustment")
        self.assertNotIn("Follow Standard", html)
        self.assertIn('data-taxable-label="Taxable"', html)
        self.assertIn('data-pretax-label="Pre-Tax"', html)
        self.assertIn('kind.value === "recovery" ? root.dataset.pretaxLabel', html)

    def test_the_tax_setting_has_to_be_chosen(self):
        data = self.data(title="No Tax Choice")
        del data["tax_treatment"]
        self.save(data)
        self.assertFalse(PayAdjustment.objects.filter(title="No Tax Choice").exists())

    def test_the_tax_setting_saves_per_entry_and_reaches_the_pay_line(self):
        self.save(
            self.data(title="Not Taxable", tax_treatment="false", status="approved")
        )
        self.save(
            self.data(
                kind="recovery",
                title="Post Tax",
                tax_treatment="false",
                status="approved",
            )
        )
        self.save(
            self.data(
                kind="recovery",
                title="Pre Tax",
                tax_treatment="true",
                status="approved",
            )
        )
        not_taxable = PayAdjustment.objects.get(title="Not Taxable")
        post_tax = PayAdjustment.objects.get(title="Post Tax")
        pre_tax = PayAdjustment.objects.get(title="Pre Tax")
        self.assertIs(not_taxable.tax_treatment, False)
        self.assertFalse(not_taxable.allowance_id.is_taxable)
        self.assertIs(post_tax.tax_treatment, False)
        self.assertFalse(post_tax.deduction_id.is_pretax)
        self.assertIs(pre_tax.tax_treatment, True)
        self.assertTrue(pre_tax.deduction_id.is_pretax)

    def test_a_new_form_starts_not_taxable_for_arrears_and_pre_tax_for_a_recovery(self):
        self.assertEqual(PayAdjustmentForm().initial["tax_treatment"], "false")
        self.assertEqual(
            PayAdjustmentForm(instance=self.entry("recovery")).initial["tax_treatment"],
            "true",
        )

    def test_a_new_form_follows_the_standard_setting_when_it_is_changed(self):
        template = Allowance.objects.entire().get(system_key="arrears")
        template.is_taxable = True
        template.save()
        self.assertEqual(PayAdjustmentForm().initial["tax_treatment"], "true")

    def test_an_older_entry_without_a_choice_opens_at_the_standard_or_its_employees_exception(
        self,
    ):
        SystemComponentTaxOverride.objects.create(
            system_key="arrears", employee_id=self.bea, value=True
        )
        plain = self.entry(title="Plain Old")
        excepted = self.entry(title="Excepted Old", employee_id=self.bea)
        self.assertEqual(
            PayAdjustmentForm(instance=plain).initial["tax_treatment"], "false"
        )
        self.assertEqual(
            PayAdjustmentForm(instance=excepted).initial["tax_treatment"], "true"
        )

    def test_an_entrys_own_choice_is_what_its_form_opens_at(self):
        entry = self.entry(tax_treatment=False)
        self.assertEqual(
            PayAdjustmentForm(instance=entry).initial["tax_treatment"], "false"
        )

    def test_the_page_is_given_the_standard_and_each_employees_exception_to_suggest_from(
        self,
    ):
        import json

        SystemComponentTaxOverride.objects.create(
            system_key="arrears", employee_id=self.adam, value=True
        )
        SystemComponentTaxOverride.objects.create(
            system_key="recovery", employee_id=self.bea, value=False
        )
        defaults = json.loads(PayAdjustmentForm().tax_defaults())
        self.assertEqual(
            defaults["arrears"],
            {"standard": False, "employees": {str(self.adam.pk): True}},
        )
        self.assertEqual(
            defaults["recovery"],
            {"standard": True, "employees": {str(self.bea.pk): False}},
        )
        html = self.get("create-pay-adjustment")
        self.assertIn("data-tax-defaults=", html)
        self.assertIn("function suggest()", html)

    def test_the_tax_setting_can_be_changed_after_going_back_to_draft_and_confirmed_again(
        self,
    ):
        entry = self.entry(tax_treatment=False)
        entry.approve()
        self.save(self.data(tax_treatment="true", status="draft"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.tax_treatment), ("draft", True))
        entry.approve()
        self.assertTrue(entry.allowance_id.is_taxable)

    def test_the_status_choices_are_draft_and_confirmed(self):
        form = PayAdjustmentForm()
        self.assertEqual(
            [(key, str(label)) for key, label in form.fields["status"].choices],
            [("draft", "Draft"), ("approved", "Confirmed")],
        )
        self.assertEqual(form.initial["status"], "draft")

    def test_either_type_saves_as_a_draft(self):
        for kind in ("arrears", "recovery"):
            self.save(self.data(kind=kind, title=f"{kind} draft", amount="600"))
            entry = PayAdjustment.objects.get(title=f"{kind} draft")
            self.assertEqual(
                (entry.status, entry.kind, entry.amount), ("draft", kind, 600.0)
            )
            self.assertIsNone(entry.pay_line())

    def test_the_date_and_amount_are_needed_for_either_type(self):
        for kind in ("arrears", "recovery"):
            self.save(
                {"employee_id": self.adam.pk, "kind": kind, "title": f"Missing {kind}"}
            )
            self.assertFalse(
                PayAdjustment.objects.filter(title=f"Missing {kind}").exists()
            )

    def test_saving_a_new_entry_as_confirmed_makes_the_pay_line(self):
        self.save(self.data(status="approved"))
        entry = PayAdjustment.objects.get(title="Status Entry")
        self.assertEqual(entry.status, "approved")
        self.assertEqual(entry.allowance_id.amount, 700.0)
        self.save(self.data(kind="recovery", title="Taken", status="approved"))
        self.assertEqual(
            PayAdjustment.objects.get(title="Taken").deduction_id.amount, 700.0
        )

    def test_the_form_refuses_a_closed_month(self):
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        self.save(self.data(title="Too Late"))
        self.assertFalse(PayAdjustment.objects.filter(title="Too Late").exists())

    def test_a_draft_can_be_confirmed_from_its_form(self):
        draft = self.entry(title="Draft One")
        self.save(self.data(title="Draft One", status="approved"), draft.pk)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "approved")

    def test_a_confirmed_entry_locks_everything_but_the_status(self):
        entry = self.entry()
        entry.approve()
        form = PayAdjustmentForm(instance=entry)
        self.assertFalse(form.fields["status"].disabled)
        for name in (
            "employee_id",
            "kind",
            "title",
            "pay_date",
            "amount",
            "tax_treatment",
            "reason",
        ):
            self.assertTrue(form.fields[name].disabled, name)
        self.save(self.data(title="Renamed", amount="1"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual(
            (entry.status, entry.title, entry.amount), ("approved", "Back Pay", 1000.0)
        )

    def test_the_locked_dropdowns_keep_the_boxed_look_of_the_other_locked_fields(self):
        entry = self.entry()
        entry.approve()
        form = PayAdjustmentForm(instance=entry)
        for name in ("employee_id", "kind"):
            self.assertIn(
                "oh-select--boxed-locked", form.fields[name].widget.attrs["class"], name
            )
        self.assertNotIn(
            "oh-select--boxed-locked",
            form.fields["status"].widget.attrs.get("class", ""),
        )
        html = self.get("update-pay-adjustment", entry.pk)
        self.assertGreaterEqual(html.count("oh-select--boxed-locked"), 2)
        draft_html = self.get(
            "update-pay-adjustment", self.entry(title="Draft Look").pk
        )
        self.assertNotIn("oh-select--boxed-locked", draft_html)

    def test_picking_draft_on_a_confirmed_entry_saves_the_edits_in_the_same_go(self):
        entry = self.entry()
        entry.approve()
        line_id = entry.allowance_id_id
        self.save(
            self.data(
                title="Edited At Once",
                amount="321",
                pay_date="2027-01-10",
                status="draft",
            ),
            entry.pk,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertEqual(
            (entry.title, entry.amount, entry.pay_date),
            ("Edited At Once", 321.0, date(2027, 1, 10)),
        )
        self.assertIsNone(entry.allowance_id)
        self.assertFalse(Allowance.objects.entire().filter(pk=line_id).exists())

    def test_the_edits_posted_with_draft_must_be_for_an_open_month(self):
        entry = self.entry()
        entry.approve()
        self.payslip(self.adam, date(2027, 1, 1), date(2027, 1, 31))
        self.save(
            self.data(title="Never Saved", pay_date="2027-01-10", status="draft"),
            entry.pk,
        )
        entry.refresh_from_db()
        self.assertEqual(
            (entry.status, entry.title, entry.pay_date),
            ("approved", "Back Pay", date(2026, 12, 5)),
        )
        self.assertIsNotNone(entry.allowance_id)

    def test_edits_posted_without_draft_are_still_ignored_on_a_confirmed_entry(self):
        entry = self.entry()
        entry.approve()
        self.save(self.data(title="Sneaky", amount="5", status="approved"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual((entry.title, entry.amount), ("Back Pay", 1000.0))

    def test_the_confirmed_form_unlocks_its_fields_when_draft_is_picked(self):
        entry = self.entry()
        entry.approve()
        html = self.get("update-pay-adjustment", entry.pk)
        self.assertIn('data-locked="1"', html)
        self.assertIn('status.value === "draft"', html)
        draft_html = self.get(
            "update-pay-adjustment", self.entry(title="Open Draft").pk
        )
        self.assertNotIn('data-locked="1"', draft_html)

    def test_a_confirmed_entry_goes_back_to_draft_from_its_form_and_can_then_be_edited(
        self,
    ):
        entry = self.entry()
        entry.approve()
        self.save(self.data(status="draft"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertIsNone(entry.allowance_id)
        self.save(self.data(title="Edited", amount="42", status="draft"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual((entry.title, entry.amount), ("Edited", 42.0))

    def test_paid_arrears_cannot_go_back_to_draft_from_the_form(self):
        entry = self.entry()
        entry.approve()
        self.payslip(self.adam, date(2026, 12, 1), date(2026, 12, 31))
        self.save(self.data(status="draft"), entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "approved")

    def test_the_form_has_a_delete_button_only_for_a_draft(self):
        draft = self.entry(title="Draft Form")
        confirmed = self.entry(title="Confirmed Form")
        confirmed.approve()
        self.assertIn(
            reverse("delete-pay-adjustment", args=[draft.pk]),
            self.get("update-pay-adjustment", draft.pk),
        )
        self.assertNotIn(
            reverse("delete-pay-adjustment", args=[confirmed.pk]),
            self.get("update-pay-adjustment", confirmed.pk),
        )
        self.assertNotIn("/delete-pay-adjustment/", self.get("create-pay-adjustment"))
