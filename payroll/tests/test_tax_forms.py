"""
Tests for FilingStatusForm — the tax configuration flow.

The mode choice (tax brackets vs a Python formula) used to be a one-way door
fixed at creation, and the combination that silently taxed everyone at 0 —
Python mode enabled with no code — was accepted at save time.
"""

from django.test import TestCase

from horilla.testkit import make_company, make_employee, make_user
from payroll.forms.tax_forms import FilingStatusForm
from payroll.methods import federal_tax

WORKING = "def calculate_federal_tax(yearly_income):\n    return yearly_income * 0.1\n"

BASE = {"filing_status": "Flow Test", "based_on": "basic_pay", "description": "x"}


def _data(**overrides):
    data = dict(BASE)
    data.update(overrides)
    return data


class FilingStatusModeSwitchTests(TestCase):
    def _create_in_bracket_mode(self):
        form = FilingStatusForm(data=_data())
        self.assertTrue(form.is_valid(), form.errors.as_text())
        return form.save()

    def test_mode_stays_editable_after_creation(self):
        """
        The reported "flow mistake": use_py was deleted from the form whenever
        the record already existed, so bracket mode and Python mode could only
        ever be chosen once. Changing it meant deleting the filing status —
        which Contract.filing_status PROTECTs, so it meant re-pointing every
        contract first.
        """
        instance = self._create_in_bracket_mode()
        self.assertIn("use_py", FilingStatusForm(instance=instance).fields)

    def test_can_switch_to_python_mode_and_back(self):
        instance = self._create_in_bracket_mode()
        self.assertFalse(instance.use_py)

        to_python = FilingStatusForm(instance=instance, data=_data(use_py="on"))
        self.assertTrue(to_python.is_valid(), to_python.errors.as_text())
        instance = to_python.save()
        self.assertTrue(instance.use_py)

        back_to_brackets = FilingStatusForm(instance=instance, data=_data())
        self.assertTrue(back_to_brackets.is_valid(), back_to_brackets.errors.as_text())
        self.assertFalse(back_to_brackets.save().use_py)

    def test_modal_does_not_carry_the_code_editor(self):
        """
        The rules — slabs, adjustments, formula — are edited on the filing
        status' own page. A code editor never fitted this modal: the generic
        form template owns the <form> and its Save buttons, so anything
        appended after it rendered outside the form and spilled below the
        dialog.
        """
        fields = FilingStatusForm().fields
        self.assertNotIn("python_code", fields)
        self.assertNotIn("standard_deduction", fields)

    def test_creating_in_python_mode_seeds_a_starter_formula(self):
        """
        python_code is not on this form, so a new Python-mode filing status
        would otherwise be saved with nothing to run — the exact state that
        used to tax everyone on it at 0.
        """
        form = FilingStatusForm(data=_data(use_py="on"))
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.save().python_code, federal_tax.CODE)

    def test_creating_in_bracket_mode_stores_no_formula(self):
        form = FilingStatusForm(data=_data())
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertFalse((form.save().python_code or "").strip())


class TestPyCodeEndpointTests(TestCase):
    """
    The built-in formula preview that replaces the onecompiler.com iframe.

    The iframe ran the formula in a third party's sandbox against unrelated
    data, so it could not tell an admin what *this* system would compute — and
    it sent the employer's tax formula to another company to find out. This
    endpoint runs the same run_tax_formula the payroll engine calls.
    """

    def setUp(self):
        # Horilla's view decorators resolve the acting employee off the user,
        # so a bare create_superuser is not enough to get past them (it answers
        # 204, not 200).
        user = make_user("taxadmin", is_superuser=True)
        company = make_company("Tax Editor Co")
        make_employee(company=company, email="taxadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.url = "/payroll/test-py-code/"
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def test_working_formula_returns_the_computed_tax(self):
        response = self.client.post(
            self.url, {"code": WORKING, "sample_income": "120000"}, **self.hx
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], 12000.0)

    def test_sandbox_policy_violation_is_reported(self):
        response = self.client.post(
            self.url,
            {"code": "import os\n" + WORKING, "sample_income": "1"},
            **self.hx,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Import", response.json()["error"])

    def test_runaway_formula_times_out_rather_than_hanging(self):
        response = self.client.post(
            self.url,
            {
                "code": "def calculate_federal_tax(y):\n    while True:\n        pass\n",
                "sample_income": "1",
            },
            **self.hx,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("did not finish", response.json()["error"])

    def test_non_numeric_return_is_reported(self):
        response = self.client.post(
            self.url,
            {
                "code": 'def calculate_federal_tax(y):\n    return "nope"\n',
                "sample_income": "1",
            },
            **self.hx,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a number", response.json()["error"])

    def test_non_numeric_sample_income_is_reported(self):
        response = self.client.post(
            self.url, {"code": WORKING, "sample_income": "abc"}, **self.hx
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be a number", response.json()["error"])


class TaxBracketFormSetTests(TestCase):
    """
    The slab table validated as a set.

    TaxBracket.clean() only ever compared one row against an *unordered*
    queryset and took .first() of whatever matched, so overlaps got through
    non-deterministically and nothing ever looked for a gap. A gap matters:
    the engine stops walking brackets at the first one that does not apply, so
    income landing in a hole is silently under-taxed.
    """

    def setUp(self):
        from payroll.models.models import FilingStatus

        self.filing_status = FilingStatus.objects.create(
            filing_status="Slab Test", based_on="basic_pay"
        )

    def _formset(self, rows):
        from payroll.forms.tax_forms import TaxBracketFormSet

        data = {
            "taxbracket_set-TOTAL_FORMS": str(len(rows)),
            "taxbracket_set-INITIAL_FORMS": "0",
            "taxbracket_set-MIN_NUM_FORMS": "0",
            "taxbracket_set-MAX_NUM_FORMS": "1000",
        }
        for index, (low, high, rate) in enumerate(rows):
            data[f"taxbracket_set-{index}-min_income"] = str(low)
            data[f"taxbracket_set-{index}-max_income"] = (
                "" if high is None else str(high)
            )
            data[f"taxbracket_set-{index}-tax_rate"] = str(rate)
        return TaxBracketFormSet(data, instance=self.filing_status)

    def _all_errors(self, formset):
        text = " ".join(str(form.errors) for form in formset.forms)
        return text + " " + str(formset.non_form_errors())

    def test_contiguous_slabs_are_valid(self):
        formset = self._formset(
            [(0, 400000, 0), (400000, 800000, 5), (800000, None, 20)]
        )
        self.assertTrue(formset.is_valid(), self._all_errors(formset))

    def test_gap_between_slabs_is_rejected(self):
        formset = self._formset([(0, 400000, 0), (500000, None, 10)])
        self.assertFalse(formset.is_valid())
        self.assertIn("falls in no slab", self._all_errors(formset))

    def test_overlapping_slabs_are_rejected(self):
        formset = self._formset([(0, 500000, 0), (400000, None, 10)])
        self.assertFalse(formset.is_valid())
        self.assertIn("overlaps", self._all_errors(formset))

    def test_table_must_start_at_zero(self):
        formset = self._formset([(100, None, 10)])
        self.assertFalse(formset.is_valid())
        self.assertIn("must start at 0", self._all_errors(formset))

    def test_only_the_last_slab_may_be_open_ended(self):
        formset = self._formset([(0, None, 0), (400000, None, 10)])
        self.assertFalse(formset.is_valid())
        self.assertIn("highest slab", self._all_errors(formset))

    def test_rows_are_sorted_before_checking(self):
        """Order entered should not matter; order of income should."""
        formset = self._formset(
            [(800000, None, 20), (0, 400000, 0), (400000, 800000, 5)]
        )
        self.assertTrue(formset.is_valid(), self._all_errors(formset))


class SavingAnUnchangedSlabTableTests(TestCase):
    """Saving a slab table unchanged must pass; slabs that meet are not overlaps."""

    def setUp(self):
        from payroll.models.models import FilingStatus
        from payroll.models.tax_models import TaxBracket

        self.filing_status = FilingStatus.objects.create(
            filing_status="Saved Slabs", based_on="taxable_gross_pay"
        )
        self.rows = [
            TaxBracket.objects.create(
                filing_status_id=self.filing_status,
                min_income=low,
                max_income=high,
                tax_rate=rate,
            )
            for low, high, rate in (
                (0, 250000, 0),
                (250000, 500000, 5),
                (500000, 1000000, 20),
                (1000000, None, 30),
            )
        ]

    def test_saving_the_table_unchanged_is_accepted(self):
        from payroll.forms.tax_forms import TaxBracketFormSet

        data = {
            "taxbracket_set-TOTAL_FORMS": str(len(self.rows)),
            "taxbracket_set-INITIAL_FORMS": str(len(self.rows)),
            "taxbracket_set-MIN_NUM_FORMS": "0",
            "taxbracket_set-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(self.rows):
            data[f"taxbracket_set-{index}-id"] = str(row.pk)
            data[f"taxbracket_set-{index}-filing_status_id"] = str(
                self.filing_status.pk
            )
            data[f"taxbracket_set-{index}-min_income"] = str(row.min_income)
            data[f"taxbracket_set-{index}-max_income"] = (
                "" if row.max_income is None else str(row.max_income)
            )
            data[f"taxbracket_set-{index}-tax_rate"] = str(row.tax_rate)
        formset = TaxBracketFormSet(data, instance=self.filing_status)
        self.assertTrue(
            formset.is_valid(),
            " ".join(str(f.errors) for f in formset.forms)
            + str(formset.non_form_errors()),
        )

    def test_a_slab_that_only_meets_its_neighbour_is_not_an_overlap(self):
        from payroll.models.tax_models import TaxBracket

        TaxBracket(
            filing_status_id=self.filing_status,
            min_income=1000000,
            max_income=None,
            tax_rate=31,
        ).clean_fields()
        meeting = TaxBracket(
            filing_status_id=self.filing_status,
            min_income=2000000,
            max_income=3000000,
            tax_rate=1,
        )
        # Still overlaps the open-ended top slab.
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            meeting.clean()

    def test_the_open_ended_slab_stays_null_after_validation(self):
        from payroll.models.tax_models import TaxBracket

        top = TaxBracket.objects.get(pk=self.rows[-1].pk)
        top.clean()
        self.assertIsNone(top.max_income)


class FilingStatusTaxRulesFormTests(TestCase):
    def setUp(self):
        from payroll.models.models import FilingStatus

        self.filing_status = FilingStatus.objects.create(
            filing_status="Rules Test", based_on="basic_pay"
        )

    def _form(self, **data):
        from payroll.forms.tax_forms import FilingStatusTaxRulesForm

        payload = {"standard_deduction": "0", "cess_percent": "0"}
        payload.update(data)
        return FilingStatusTaxRulesForm(payload, instance=self.filing_status)

    def test_half_a_rebate_is_rejected(self):
        """
        A limit with no amount (or vice versa) silently does nothing, which is
        worse than refusing it: the admin believes relief is configured and the
        payslip disagrees.
        """
        self.assertFalse(self._form(rebate_income_limit="1200000").is_valid())
        self.assertFalse(self._form(rebate_max_amount="60000").is_valid())

    def test_complete_rebate_is_accepted(self):
        form = self._form(rebate_income_limit="1200000", rebate_max_amount="60000")
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_no_rebate_at_all_is_accepted(self):
        self.assertTrue(self._form().is_valid())

    def test_python_mode_without_code_is_rejected(self):
        """
        The state that silently taxed everyone on a filing status at 0: Python
        mode on with nothing to run. Validation moved here with the editor.
        """
        self.filing_status.use_py = True
        self.filing_status.save()
        form = self._form(python_code="")
        self.assertFalse(form.is_valid())
        self.assertIn("python_code", form.errors)

    def test_python_mode_rejects_code_failing_sandbox_policy(self):
        self.filing_status.use_py = True
        self.filing_status.save()
        form = self._form(
            python_code="import os\ndef calculate_federal_tax(y):\n    return 0\n"
        )
        self.assertFalse(form.is_valid())
        self.assertIn("python_code", form.errors)

    def test_python_mode_accepts_valid_code(self):
        self.filing_status.use_py = True
        self.filing_status.save()
        form = self._form(python_code=WORKING)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_bracket_mode_ignores_empty_code(self):
        """A slab-based filing status must not be made to supply Python."""
        self.assertTrue(self._form(python_code="").is_valid())


class PythonCodeXssExemptionTests(TestCase):
    """
    python_code holds Python source, and HorillaModel's XSS regex is built for
    HTML. Its inline-event-handler pattern (on\w+\s*=) matches any assignment
    to a variable containing "on", so ordinary formulas were rejected as
    "Potential XSS content detected."
    """

    def test_default_template_can_be_saved(self):
        """
        The shipped starter template assigns to `month_taxable`, whose "onth_"
        matched the handler pattern — so Python mode could not save its own
        default.
        """
        from payroll.models.models import FilingStatus

        status = FilingStatus.objects.create(
            filing_status="Template Save",
            based_on="basic_pay",
            use_py=True,
            python_code=federal_tax.CODE,
        )
        status.refresh_from_db()
        self.assertEqual(status.python_code, federal_tax.CODE)

    def test_formula_with_on_in_a_variable_name_can_be_saved(self):
        from payroll.models.models import FilingStatus

        code = (
            "def calculate_federal_tax(yearly_income):\n"
            "    contribution = yearly_income * 0.1\n"
            "    return contribution\n"
        )
        status = FilingStatus.objects.create(
            filing_status="Contribution",
            based_on="basic_pay",
            use_py=True,
            python_code=code,
        )
        status.refresh_from_db()
        self.assertEqual(status.python_code, code)

    def test_other_text_fields_are_still_xss_checked(self):
        """The exemption is scoped to python_code and nothing else."""
        from django.core.exceptions import ValidationError

        from payroll.models.models import FilingStatus

        with self.assertRaises(ValidationError):
            FilingStatus.objects.create(
                filing_status="Bad",
                based_on="basic_pay",
                description="<script>alert(1)</script>",
            )
