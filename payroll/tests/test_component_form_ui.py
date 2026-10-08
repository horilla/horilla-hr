"""
The Allowance / Deduction form.

Two failures motivated rebuilding it, and both are guarded here.

The first: choosing "Percentage of another component" or "Custom formula"
revealed nothing. The old form's visibility came from
static/build/js/allowanceWidget.js, a checked-in build artefact with no source
file, which only knew the amount types that existed when it was generated;
anything added since fell into an `else` branch that hid the rate box. The
replacement declares its rules in markup and reads them from a real source
file.

The second: the old body listed the fields it drew by hand, in a chain of name
comparisons, so `percentage_of_code` and `formula` could exist on the model, be
accepted on save, and have nowhere on the form to set them. The layout is now
data, and `unplaced_field_names` is the assertion that nothing is missed.

JavaScript cannot be executed here, so the client-side half is asserted against
its source. That is worth doing for the two mistakes that actually shipped —
a document-wide lookup, and a missing field reading as false — because either
one silently hides fields with nothing in the console to point at.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.filters import AllowanceFilter, DeductionFilter
from payroll.forms.component_forms import AllowanceForm, DeductionForm
from payroll.forms.component_layout import (
    HIDDEN_FIELDS,
    STEPS,
    sections_for,
    steps_for,
    unplaced_field_names,
)

ENGINE = "static/src/js/componentForm.js"
BUILDER = "payroll/templates/payroll/component/_formula_builder.html"


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class LayoutCompletenessTests(TestCase):
    """Every field is placed, or the sweep would have caught it."""

    def test_no_visible_field_is_left_out_of_the_layout(self):
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                self.assertEqual(unplaced_field_names(form_class()), [])

    def test_the_code_is_drawn_and_typed_codes_are_uppercased(self):
        """
        The code is an input beside the title. Blank still means "derive it from
        the title on save", and what is typed is upper-cased so grat -> GRAT.
        """
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                form = form_class()
                drawn = {
                    row["field"].name
                    for section in sections_for(form)
                    for row in section["rows"]
                }
                self.assertIn("code", drawn)
                self.assertNotIn("code", [f.name for f in form.hidden_fields()])
                self.assertEqual(form.fields["code"].clean(" grat "), "GRAT")
                self.assertEqual(form.fields["code"].clean(""), "")

    def test_what_it_is_a_percentage_of_comes_before_the_percentage(self):
        """Asking for a rate before naming its base reads backwards."""
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                names = [
                    row["field"].name
                    for section in sections_for(form_class())
                    for row in section["rows"]
                ]
                self.assertLess(names.index("percentage_of_code"), names.index("rate"))

    def test_the_component_picker_is_styled_like_every_other_select(self):
        """
        percentage_of_code is rebuilt as a plain ChoiceField so its options can
        be the codes that exist. Rebuilding it dropped the widget attrs the
        form had already applied, leaving one bare browser dropdown among the
        oh-select ones.
        """
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                fields = form_class().fields
                self.assertEqual(
                    fields["percentage_of_code"].widget.attrs.get("class"),
                    fields["based_on"].widget.attrs.get("class"),
                )

    def test_sections_are_shared_by_both_component_forms(self):
        allowance = [s["title"] for s in sections_for(AllowanceForm())]
        deduction = [s["title"] for s in sections_for(DeductionForm())]
        self.assertEqual(allowance, deduction)

    def test_hidden_fields_are_named_rather_than_assumed(self):
        self.assertNotIn("code", HIDDEN_FIELDS)
        self.assertIn("update_compensation", HIDDEN_FIELDS)


class BasedOnGroupingTests(TestCase):
    """
    Grouping must not lose a choice, which is the risk of writing the groups
    out by hand: a value missing from the map would silently disappear from the
    form while still being perfectly valid on the model.
    """

    def _flatten(self, choices):
        flat = []
        for value, label in choices:
            if isinstance(label, (list, tuple)):
                flat.extend(v for v, _l in label)
            else:
                flat.append(value)
        return flat

    def test_grouping_keeps_every_choice_the_model_offers(self):
        from payroll.models.models import Allowance, Deduction

        for form_class, model in (
            (AllowanceForm, Allowance),
            (DeductionForm, Deduction),
        ):
            with self.subTest(form=form_class.__name__):
                offered = set(self._flatten(form_class().fields["based_on"].choices))
                declared = {value for value, _label in model.based_on_choice}
                self.assertTrue(declared <= offered, declared - offered)

    def test_custom_formula_sits_under_its_own_heading(self):
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                groups = {
                    str(value): [v for v, _l in label]
                    for value, label in form_class().fields["based_on"].choices
                    if isinstance(label, (list, tuple))
                }
                formula_group = next(
                    name for name, values in groups.items() if "formula" in values
                )
                self.assertNotIn("basic_pay", groups[formula_group])
                self.assertNotIn("attendance", groups[formula_group])

    def test_the_blank_choice_stays_ungrouped_at_the_top(self):
        """It is the "not chosen yet" state, not a kind of amount."""
        first = AllowanceForm().fields["based_on"].choices[0]
        self.assertEqual(first[0], "")


class StepTests(TestCase):
    """
    The form is presented in steps, but it is still one form and one POST.
    That is the whole safety property: if stepping ever started removing
    fields from the DOM, or splitting the submit, every one of these breaks.
    """

    def test_every_section_belongs_to_exactly_one_step(self):
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                form = form_class()
                in_steps = [
                    section["key"]
                    for step in steps_for(form)
                    for section in step["sections"]
                ]
                self.assertEqual(
                    sorted(in_steps),
                    sorted(section["key"] for section in sections_for(form)),
                )
                self.assertEqual(len(in_steps), len(set(in_steps)))

    def test_no_field_is_lost_by_being_grouped_into_steps(self):
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                form = form_class()
                stepped = {
                    row["field"].name
                    for step in steps_for(form)
                    for section in step["sections"]
                    for row in section["rows"]
                }
                flat = {
                    row["field"].name
                    for section in sections_for(form)
                    for row in section["rows"]
                }
                self.assertEqual(stepped, flat)

    def test_steps_are_numbered_from_one_without_gaps(self):
        """
        An empty step is dropped, so the numbering has to be assigned after
        that rather than taken from the STEPS constant.
        """
        for form_class in (AllowanceForm, DeductionForm):
            with self.subTest(form=form_class.__name__):
                indexes = [step["index"] for step in steps_for(form_class())]
                self.assertEqual(indexes, list(range(1, len(indexes) + 1)))

    def test_a_step_with_nothing_in_it_is_not_offered(self):
        class Empty:
            fields = {}

            def visible_fields(self):
                return []

        self.assertEqual(steps_for(Empty()), [])
        self.assertTrue(STEPS)


class NameCollisionTests(TestCase):
    """The reason document-wide lookups are wrong on this page."""

    def test_the_filters_declare_the_same_field_names_as_the_form(self):
        for filterset in (AllowanceFilter, DeductionFilter):
            with self.subTest(filterset=filterset.__name__):
                names = set(filterset.base_filters)
                self.assertIn("based_on", names)
                self.assertIn("is_fixed", names)


class EngineSourceTests(TestCase):
    """
    Asserted against the source because there is no JS runner here. Both of
    these regressed once already and neither produces an error when it does.
    """

    def test_inputs_are_resolved_against_the_fields_own_form(self):
        script = read(ENGINE)
        self.assertIn('closest("form")', script)
        self.assertNotIn('document.querySelector("[name=', script)

    def test_a_rule_about_an_absent_field_does_not_hide_the_row(self):
        """
        One layout serves both forms. The condition rows are gated on
        include_active_employees, which Deduction does not have, so treating a
        missing field as false hid conditions on every deduction.
        """
        self.assertIn("if (!field) return true;", read(ENGINE))

    def test_the_formula_builder_writes_to_its_own_forms_field(self):
        script = read(BUILDER)
        self.assertIn('closest("form")', script)
        self.assertNotIn('document.querySelector("[name=formula]")', script)

    def test_the_engine_is_safe_to_load_more_than_once(self):
        """
        The form arrives by HTMX, which re-runs its <script src> on every open.
        Without a guard each open adds another set of document listeners, and
        one click on "Add condition" then appends a row per time the modal had
        been opened.
        """
        self.assertIn("window.horillaComponentForm", read(ENGINE))

    def test_the_engine_also_listens_through_jquery(self):
        """
        select2 and the oh-switch change fields with jQuery's .trigger(), which
        never reaches a listener added with addEventListener.
        """
        self.assertIn("jQuery(document)", read(ENGINE))


class ComponentFormRenderTests(TestCase):
    def setUp(self):
        user = make_user("componentadmin", is_superuser=True)
        company = make_company("Component Co")
        make_employee(company=company, email="componentadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def _body(self, url_name):
        response = self.client.get(reverse(url_name), **self.hx)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_percentage_input_is_present_for_a_calculated_amount(self):
        """The reported symptom: nowhere to type the percentage."""
        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertIn('name="rate"', body)
                self.assertIn('name="percentage_of_code"', body)
                self.assertIn('data-show-if="is_fixed=off based_on=component"', body)

    def test_the_formula_opens_in_a_popover_rather_than_filling_the_form(self):
        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertIn("data-formula-popover", body)
                self.assertIn("data-open-formula", body)
                self.assertIn("data-formula-summary", body)
                self.assertIn("data-formula-builder", body)

    def test_the_builder_starts_closed(self):
        """
        It rendered open over the form. The panel sets display:flex, which beats
        the [hidden] attribute's display:none from the UA stylesheet, and the
        !important rule that would have won was scoped to .oh-component-form —
        which the popover sits outside of.
        """
        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                # The attribute on the element, and the stylesheet rule that
                # makes it stick. Either one alone leaves the builder open.
                self.assertIn("data-formula-backdrop hidden>", body)
                self.assertIn(".oh-formula-popover[hidden]", body)

    def test_the_builder_can_be_dismissed_more_than_one_way(self):
        body = self._body("create-allowance")
        self.assertIn("data-formula-backdrop", body)
        self.assertEqual(body.count("data-close-formula"), 2)  # the X and Done
        self.assertIn("closeAnyOpenFormula", read(ENGINE))  # Escape

    def test_the_old_widget_bundles_are_gone(self):
        for url_name, bundle in (
            ("create-allowance", "allowanceWidget"),
            ("create-deduction", "deductionWidget"),
        ):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertNotIn(bundle, body)
                self.assertIn("componentForm.js", body)

    def test_conditions_render_server_side_with_a_template_to_add_more(self):
        # The allowance form targets through the table; only deductions keep rules.
        for url_name in ("create-deduction",):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertIn("data-condition-template", body)
                self.assertIn("data-add-condition", body)
                self.assertIn('name="other_fields"', body)

    def test_every_row_is_tied_to_a_section_heading(self):
        """
        A heading has to disappear once everything under it is hidden — "Upper
        limit" was a rule and a caption sitting alone whenever the amount was
        fixed. The rows are the heading's siblings rather than its children,
        because all of them must be direct children of the Bootstrap row, so
        the link is a key and it has to actually be rendered on both ends.
        """
        import re

        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                sections = set(re.findall(r'data-section="([^"]*)"', body))
                rows = re.findall(r'data-section-of="([^"]*)"', body)

                self.assertTrue(sections)
                self.assertTrue(rows)
                self.assertNotIn("", sections)
                self.assertNotIn("", rows, "a row rendered with an empty key")
                self.assertTrue(
                    set(rows) <= sections,
                    f"rows point at headings that do not exist: {set(rows) - sections}",
                )
                self.assertEqual(
                    sections,
                    set(rows),
                    "a heading has no rows, so it could never be hidden",
                )

    def test_the_engine_matches_headings_to_rows_by_key(self):
        """
        The first version looked for [data-row] inside the heading element.
        Rows are siblings, so it always found none and never hid a heading.
        """
        script = read(ENGINE)
        self.assertIn("data-section-of=", script)
        self.assertNotIn('section.querySelectorAll("[data-row]")', script)

    def test_the_steps_render_as_a_rail_over_matching_panels(self):
        import re

        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                tabs = re.findall(r'data-step-tab="([^"]+)"', body)
                panels = re.findall(r'data-step-panel="([^"]+)"', body)
                self.assertTrue(tabs)
                self.assertEqual(tabs, panels)
                self.assertIn("data-step-next", body)
                self.assertIn("data-step-back", body)

    def test_every_field_stays_in_the_dom_on_every_step(self):
        """
        Stepping is presentation. A field that only existed while its step was
        showing would silently drop out of the POST — and the fields most
        likely to be off-screen at submit time are the required ones on the
        last step.
        """
        for url_name, form_class in (
            ("create-allowance", AllowanceForm),
            ("create-deduction", DeductionForm),
        ):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                for name in form_class().fields:
                    # The table writes specific_employees as it is ticked, and the
                    # exclude list is gone from the form on purpose.
                    if name in ("specific_employees", "exclude_employees") or (
                        name in ("is_condition_based", "field", "condition", "value")
                        and url_name == "create-allowance"
                    ):
                        continue
                    self.assertIn(f'name="{name}"', body, name)

    def test_the_form_still_posts_once(self):
        """One form element, one submit — not a step-per-request wizard."""
        body = self._body("create-allowance")
        self.assertEqual(body.count("<form "), 1)
        self.assertEqual(body.count("hx-post="), 1)

    def test_every_section_heading_is_drawn(self):
        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertIn("What this component is", body)
                self.assertIn("How much", body)
                self.assertIn("Who gets it", body)

    def test_the_new_amount_types_are_offered(self):
        for url_name in ("create-allowance", "create-deduction"):
            with self.subTest(form=url_name):
                body = self._body(url_name)
                self.assertIn('value="component"', body)
                self.assertIn('value="formula"', body)


class ComponentFormSaveTests(TestCase):
    """
    The form has to post back what it draws. Rendering was only half the
    reported problem — a percentage-of-component allowance that cannot be
    submitted is no more usable than one that cannot be configured.
    """

    # Fields that are required and are always in the DOM, so a browser posts
    # them whatever is on screen: hiding a row hides it, it does not stop it
    # being submitted. Spelled out here so these payloads are what a real
    # submit looks like rather than the minimum the form happens to accept.
    ALWAYS_POSTED = {
        "maximum_unit": "month_working_days",
        "if_choice": "basic_pay",
        "if_condition": "gt",
        "if_amount": "0",
    }

    def setUp(self):
        user = make_user("saveadmin", is_superuser=True)
        company = make_company("Save Co")
        make_employee(company=company, email="saveadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def _post(self, url, **fields):
        payload = dict(self.ALWAYS_POSTED)
        payload.update(fields)
        response = self.client.post(url, payload, **self.hx)
        self.assertIn(response.status_code, (200, 302))
        return response

    def test_a_percentage_of_another_component_allowance_saves(self):
        from payroll.models.models import Allowance

        basic = Allowance.objects.create(title="Basic Pay", is_fixed=True, amount=1000)
        self._post(
            reverse("create-allowance"),
            title="HRA",
            sequence=200,
            is_taxable="on",
            is_fixed="",
            based_on="component",
            percentage_of_code=basic.code,
            rate="50",
        )

        hra = Allowance.objects.get(title="HRA")
        self.assertFalse(hra.is_fixed)
        self.assertEqual(hra.based_on, "component")
        self.assertEqual(hra.percentage_of_code, basic.code)
        self.assertEqual(hra.rate, 50)

    def test_editing_keeps_the_code_other_components_point_at(self):
        """
        The code is derived only when blank, so a form that did not post it back
        would re-derive from the current title and silently retarget every
        formula and percentage aimed at the old one.
        """
        from payroll.models.models import Allowance

        allowance = Allowance.objects.create(
            title="Travel Allowance", is_fixed=True, amount=500
        )
        original = allowance.code

        self._post(
            reverse("update-allowance", kwargs={"pk": allowance.pk}),
            title="Conveyance Allowance",
            code=original,
            sequence=100,
            is_taxable="on",
            is_fixed="on",
            amount="600",
        )

        allowance.refresh_from_db()
        self.assertEqual(allowance.title, "Conveyance Allowance")
        self.assertEqual(allowance.code, original)


class UpdateCompensationHiddenTests(TestCase):
    """
    update_compensation is off the form but not out of the engine.

    It shrinks the pay head itself, so a later percentage of basic is worked
    out on the reduced figure — nothing else does that. What it does not do is
    respect eligibility, the "when it applies" rules, the ceiling or the period
    basis, and it was sitting among the ordinary attributes with nothing to say
    so. Hiding it stops one being created by accident; these make sure hiding
    it does not destroy one that exists, or create the blank-string row that
    would vanish from a payslip.
    """

    def setUp(self):
        user = make_user("compadmin", is_superuser=True)
        company = make_company("Comp Co")
        make_employee(company=company, email="compadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def test_it_is_not_drawn_on_the_form(self):
        form = DeductionForm()
        drawn = {
            row["field"].name
            for section in sections_for(form)
            for row in section["rows"]
        }
        self.assertNotIn("update_compensation", drawn)
        self.assertIn("update_compensation", HIDDEN_FIELDS)

    def test_it_is_still_posted_so_an_existing_one_survives_an_edit(self):
        form = DeductionForm()
        self.assertIn("update_compensation", [f.name for f in form.hidden_fields()])

    def test_editing_a_compensation_deduction_keeps_it(self):
        from payroll.models.models import Deduction

        deduction = Deduction.objects.create(
            title="Basic Adjustment",
            update_compensation="basic_pay",
            is_fixed=True,
            amount=1500.0,
        )
        response = self.client.post(
            reverse("update-deduction", kwargs={"pk": deduction.pk}),
            {
                "title": "Basic Adjustment",
                "update_compensation": "basic_pay",
                "code": deduction.code,
                "sequence": 100,
                "is_fixed": "on",
                "amount": "1600",
                "maximum_unit": "full_period",
                "if_choice": "basic_pay",
                "if_condition": "gt",
                "if_amount": "0",
            },
            **self.hx,
        )
        self.assertIn(response.status_code, (200, 302))

        deduction.refresh_from_db()
        self.assertEqual(deduction.update_compensation, "basic_pay")
        self.assertEqual(deduction.amount, 1600.0)

    def test_an_empty_value_is_stored_as_null_not_as_a_blank(self):
        """
        The three ordinary phases keep only update_compensation__isnull=True and
        the compensation pass matches an exact type, so "" belongs to neither
        and the deduction disappears from the payslip silently.
        """
        from payroll.models.models import Deduction

        deduction = Deduction.objects.create(
            title="Ordinary", update_compensation="", is_fixed=True, amount=10.0
        )
        deduction.refresh_from_db()
        self.assertIsNone(deduction.update_compensation)

        self.assertTrue(
            Deduction.objects.filter(
                pk=deduction.pk, update_compensation__isnull=True
            ).exists(),
            "a blank value would have hidden this deduction from every phase",
        )
