"""
The HORILLA_ALLOW_PYTHON_TAX_FORMULAS switch.

A Python tax formula is code that runs on the server for every payslip, so new
ones are opt-in. The switch gates *new* code only: creating a Python-mode
filing status, saving or editing a formula, and test-running one. A formula
that is already stored keeps being evaluated either way, so turning the switch
off can never stop a payroll run.
"""

from django.test import TestCase, override_settings

from horilla.testkit import make_company, make_employee, make_user
from payroll.forms.tax_forms import FilingStatusForm, FilingStatusTaxRulesForm
from payroll.methods.safe_tax_code import python_formulas_enabled, run_tax_code
from payroll.tests.factories_payroll import make_filing_status

WORKING = "def calculate_federal_tax(yearly_income):\n    return yearly_income * 0.1\n"
EDITED = "def calculate_federal_tax(yearly_income):\n    return yearly_income * 0.2\n"
BASE = {"filing_status": "Switch Test", "based_on": "basic_pay", "description": "x"}


def _admin_client(testcase):
    user = make_user("switchadmin", is_superuser=True)
    company = make_company("Switch Co")
    make_employee(company=company, email="switchadmin@test.horilla", user=user)
    testcase.client.force_login(user)
    testcase.hx = {"HTTP_HX_REQUEST": "true"}


@override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
class WhenPythonFormulasAreOffFormTests(TestCase):
    def test_helper_reports_off(self):
        self.assertFalse(python_formulas_enabled())

    def test_a_new_python_mode_filing_status_is_refused(self):
        form = FilingStatusForm(data=dict(BASE, use_py="on"))
        self.assertFalse(form.is_valid())
        self.assertIn("use_py", form.errors)
        self.assertIn("turned off", form.errors["use_py"][0])

    def test_a_new_slab_mode_filing_status_is_unaffected(self):
        form = FilingStatusForm(data=dict(BASE))
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_a_slab_status_cannot_be_switched_to_python(self):
        status = make_filing_status("Slabs", use_py=False)
        form = FilingStatusForm(
            instance=status, data=dict(BASE, filing_status="Slabs", use_py="on")
        )
        self.assertFalse(form.is_valid())
        self.assertIn("use_py", form.errors)

    def test_a_status_already_in_python_mode_still_saves_its_identity(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = FilingStatusForm(
            instance=status,
            data=dict(BASE, filing_status="Coded renamed", use_py="on"),
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.save().python_code, WORKING)

    def test_switching_back_to_slabs_is_always_allowed(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = FilingStatusForm(instance=status, data=dict(BASE, filing_status="Coded"))
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertFalse(form.save().use_py)

    def _rules_form(self, status, code):
        payload = {"standard_deduction": "0", "cess_percent": "0", "python_code": code}
        return FilingStatusTaxRulesForm(payload, instance=status)

    def test_editing_the_stored_formula_is_refused(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = self._rules_form(status, EDITED)
        self.assertFalse(form.is_valid())
        self.assertIn("python_code", form.errors)

    def test_resaving_the_unchanged_formula_with_other_rules_is_allowed(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = self._rules_form(status, WORKING)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_a_stored_formula_is_still_evaluated(self):
        """The switch never stops a payroll run."""
        self.assertEqual(run_tax_code(WORKING, 100000), 10000.0)


@override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
class WhenPythonFormulasAreOffEndpointTests(TestCase):
    def setUp(self):
        _admin_client(self)
        self.status = make_filing_status("Coded", use_py=True, python_code=WORKING)

    def test_saving_new_code_is_refused_and_nothing_is_stored(self):
        response = self.client.post(
            f"/payroll/update-py-code/{self.status.pk}/", {"code": EDITED}, **self.hx
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("turned off", response.json()["message"])
        self.status.refresh_from_db()
        self.assertEqual(self.status.python_code, WORKING)

    def test_saving_the_unchanged_code_is_harmless(self):
        response = self.client.post(
            f"/payroll/update-py-code/{self.status.pk}/", {"code": WORKING}, **self.hx
        )
        self.assertEqual(response.status_code, 200)

    def test_the_test_run_endpoint_is_refused(self):
        response = self.client.post(
            "/payroll/test-py-code/",
            {"code": WORKING, "sample_income": "1000"},
            **self.hx,
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])


@override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=True)
class WhenPythonFormulasAreOnTests(TestCase):
    def setUp(self):
        _admin_client(self)

    def test_helper_reports_on(self):
        self.assertTrue(python_formulas_enabled())

    def test_a_new_python_mode_filing_status_is_accepted(self):
        form = FilingStatusForm(data=dict(BASE, use_py="on"))
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_saving_new_code_stores_it(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        response = self.client.post(
            f"/payroll/update-py-code/{status.pk}/", {"code": EDITED}, **self.hx
        )
        self.assertEqual(response.status_code, 200)
        status.refresh_from_db()
        self.assertEqual(status.python_code, EDITED)

    def test_the_test_run_endpoint_works(self):
        response = self.client.post(
            "/payroll/test-py-code/",
            {"code": WORKING, "sample_income": "1000"},
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], 100.0)


CRLF = WORKING.replace("\n", "\r\n")


@override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
class LineEndingTests(TestCase):
    """Browsers submit a textarea with Windows line endings."""

    def setUp(self):
        _admin_client(self)
        self.status = make_filing_status("Coded", use_py=True, python_code=WORKING)

    def test_an_untouched_formula_posted_with_windows_line_endings_is_not_edited(self):
        payload = {"standard_deduction": "0", "cess_percent": "0", "python_code": CRLF}
        form = FilingStatusTaxRulesForm(payload, instance=self.status)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_the_ajax_save_accepts_it_and_does_not_rewrite_the_stored_text(self):
        response = self.client.post(
            f"/payroll/update-py-code/{self.status.pk}/", {"code": CRLF}, **self.hx
        )
        self.assertEqual(response.status_code, 200)
        self.status.refresh_from_db()
        self.assertEqual(self.status.python_code, WORKING)


class AdminFormTests(TestCase):
    """The Django admin applies the same rules as the payroll pages."""

    def _form(self, instance, **changes):
        from django.forms.models import model_to_dict

        from payroll.admin import FilingStatusAdminForm

        data = {k: v for k, v in model_to_dict(instance).items() if v is not None}
        data.update(changes)
        return FilingStatusAdminForm(data, instance=instance)

    @override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
    def test_editing_a_formula_is_refused_while_off(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        self.assertFalse(self._form(status, python_code=EDITED).is_valid())

    @override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
    def test_turning_python_mode_on_is_refused_while_off(self):
        status = make_filing_status("Slabs", use_py=False)
        self.assertFalse(
            self._form(status, use_py=True, python_code=WORKING).is_valid()
        )

    @override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=False)
    def test_other_fields_still_save_while_off(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = self._form(status, filing_status="Coded renamed")
        self.assertTrue(form.is_valid(), form.errors.as_text())

    @override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=True)
    def test_code_is_checked_when_on(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = self._form(status, python_code="import os\n" + WORKING)
        self.assertFalse(form.is_valid())
        self.assertIn("python_code", form.errors)

    @override_settings(HORILLA_ALLOW_PYTHON_TAX_FORMULAS=True)
    def test_a_valid_edit_saves_when_on(self):
        status = make_filing_status("Coded", use_py=True, python_code=WORKING)
        form = self._form(status, python_code=EDITED)
        self.assertTrue(form.is_valid(), form.errors.as_text())
