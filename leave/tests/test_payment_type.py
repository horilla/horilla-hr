"""Tests for LeaveType payment type / percentage helpers."""

from decimal import Decimal

from django.test import TestCase

from leave.tests.helpers import _make_leave_type


class LeaveTypeGetPaymentPercentageTest(TestCase):
    def _lt(self, **kw):
        return _make_leave_type(**kw)

    def test_paid_returns_100(self):
        lt = self._lt(payment_type="paid")
        self.assertEqual(lt.get_payment_percentage(), 100.0)

    def test_unpaid_returns_0(self):
        lt = self._lt(payment_type="unpaid")
        self.assertEqual(lt.get_payment_percentage(), 0.0)

    def test_custom_uses_payment_percentage(self):
        lt = self._lt(payment_type="custom", payment_percentage=Decimal("75.00"))
        self.assertEqual(lt.get_payment_percentage(), 75.0)

    def test_custom_with_none_percentage_returns_0(self):
        lt = self._lt(payment_type="custom", payment_percentage=None)
        self.assertEqual(lt.get_payment_percentage(), 0.0)

    def test_backward_compat_paid(self):
        lt = self._lt(payment_type=None, payment="paid")
        self.assertEqual(lt.get_payment_percentage(), 100.0)

    def test_backward_compat_unpaid(self):
        lt = self._lt(payment_type=None, payment="unpaid")
        self.assertEqual(lt.get_payment_percentage(), 0.0)


class LeaveTypePaymentTypeDisplayTest(TestCase):
    def test_paid_display(self):
        lt = _make_leave_type(payment_type="paid")
        self.assertRegex(lt.payment_type_display(), r"\(100%\)$")

    def test_unpaid_display(self):
        lt = _make_leave_type(payment_type="unpaid")
        # Exactly 0%: a bare "0" would also match "Paid (100%)".
        self.assertRegex(lt.payment_type_display(), r"\(0%\)$")

    def test_custom_display(self):
        lt = _make_leave_type(payment_type="custom", payment_percentage=Decimal("33"))
        self.assertRegex(lt.payment_type_display(), r"\(33%\)$")
