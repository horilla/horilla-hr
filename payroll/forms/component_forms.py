"""
These forms provide a convenient way to handle data input, validation, and customization
of form fields and widgets for the corresponding models in the payroll management system.
"""

import datetime
import logging
import uuid
from typing import Any

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

import payroll.models.models
from base.forms import Form, ModelForm
from base.methods import export_field_label, reload_queryset
from base.models import Company
from employee.filters import EmployeeFilter
from employee.models import BonusPoint, Employee
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla_widgets.forms import HorillaForm, default_select_option_template
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from notifications.signals import notify
from payroll.models import tax_models as models
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    LoanAccount,
    MultipleCondition,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    ReimbursementMultipleAttachment,
    SalaryStructure,
)
from payroll.widgets import component_widgets as widget

logger = logging.getLogger(__name__)


def restrict_maximum_unit_to_calendar_days(form):
    """
    Take "This amount is" (maximum_unit) off the form without losing its value.

    A new component gets the model default, a month's worth split by calendar
    days. An existing one keeps whatever it was set to, because a loan or a
    statutory figure is deliberately flat and the engine still reads the stored
    value. The field stays as a hidden input so an edit posts it back.
    """
    field = form.fields.get("maximum_unit")
    if field is not None:
        field.widget = forms.HiddenInput()


def save_apply_conditions(form, commit):
    """
    Persist the extra "when it applies" rows posted alongside the component.

    Rebuilt from the post each time rather than diffed: the rows have no
    identity in the form, so matching them up would mean inventing one, and a
    rule nobody can point at is not worth the machinery.
    """
    from payroll.models.models import ApplyCondition

    data = form.data
    choices = data.getlist("apply_choices") if hasattr(data, "getlist") else []
    if not form.instance.pk:
        return []

    form.instance.apply_conditions.all().delete()

    conditions = data.getlist("apply_conditions")
    amounts = data.getlist("apply_amounts")
    starts = data.getlist("apply_starts")
    ends = data.getlist("apply_ends")
    codes = data.getlist("apply_codes")

    def number(values, index):
        try:
            return float(values[index])
        except (IndexError, TypeError, ValueError):
            return None

    rows = []
    for index, choice in enumerate(choices):
        if not choice:
            continue
        condition = conditions[index] if index < len(conditions) else "gt"
        row = ApplyCondition(
            choice=choice,
            condition=condition or "gt",
            amount=number(amounts, index) or 0.0,
            start_range=number(starts, index),
            end_range=number(ends, index),
            component_code=(codes[index] if index < len(codes) else "") or "",
        )
        row.save()
        rows.append(row)

    if commit and rows:
        form.instance.apply_conditions.add(*rows)
    return rows


def apply_component_code_choices(form, model):
    """
    Turn percentage_of_code into a dropdown of codes that actually exist.

    It is a plain CharField on the model — any component's code is a valid
    target, including one not created yet — so it cannot be a ModelChoiceField.
    But a free-text box for a value that has to match another record exactly is
    a typo waiting to be a silently wrong payslip: an unknown code resolves to
    0, which looks like a component that simply did not apply.

    The component's own code is excluded; a formula or percentage referring to
    itself reads either a stale value or nothing, depending on ordering.
    """
    from payroll.views.component_formula_views import available_codes

    # The component's own code is derived from its title and is never typed, so
    # it is not drawn on the form — but it still has to round-trip. Deriving it
    # again on save only happens when it is blank, so a form that omitted it
    # would re-derive from the current title and silently retarget every
    # formula and percentage pointing at the old code.
    if "code" in form.fields:
        # Drawn: typed, or left blank to be derived from the title on save. Changing
        # one that is already referenced would leave those formulas pointing at nothing.
        form.fields["code"].required = False
        form.fields["code"].widget.attrs.update(
            {
                "placeholder": _("Auto from title, e.g. HRA"),
                # Upper-cased as it is typed; a style would capitalise the placeholder too.
                "oninput": "this.value = this.value.toUpperCase();",
                "autocomplete": "off",
                "maxlength": 32,
            }
        )
        form.fields["code"].help_text = _(
            "Short name other components and formulas use to refer to this one "
            "(capital letters, digits, underscore; starts with a letter). Leave "
            "blank to make it from the title. Changing it later breaks anything "
            "that refers to the old one."
        )

        def _upper(value):
            return (value or "").strip().upper()

        def _clean_code(value, _f=form.fields["code"]):
            value = forms.CharField.clean(_f, _upper(value))
            _f.run_validators(value)
            instance = getattr(form, "instance", None)
            pk = instance.pk if instance is not None and instance.pk else None
            from payroll.models.models import component_code_taken

            if component_code_taken(value, model, pk):
                raise forms.ValidationError(
                    _("The code %(code)s is already used by another component."),
                    params={"code": value},
                )
            return value

        form.fields["code"].clean = _clean_code

    # Same reasoning as `code`: not drawn, but it has to survive an edit. A
    # form that simply omitted it would blank the setting on the next save.
    if "update_compensation" in form.fields:
        form.fields["update_compensation"].widget = forms.HiddenInput()
        form.fields["update_compensation"].required = False

    # Eleven flat options, three different kinds of answer. Grouping them is
    # what makes "Custom Formula" findable rather than something you have to
    # already know is in there.
    based_on = form.fields.get("based_on")
    if based_on is not None:
        from payroll.forms.component_layout import group_based_on_choices

        group_based_on_choices(based_on)

    field = form.fields.get("percentage_of_code")
    if field is None:
        return

    instance = getattr(form, "instance", None)
    exclude_pk = instance.pk if instance is not None and instance.pk else None
    rows = available_codes(exclude_pk=exclude_pk, exclude_model=model)

    choices = [("", _("Select a component..."))]
    # Labelled by name. The code is derived plumbing the user never chose, so
    # showing it here would ask them to recognise an identifier instead of the
    # component they created.
    choices += [
        (
            row["code"],
            # Under a CTC Down structure basic is worked out from a component, not
            # read off the contract; the label says which "Basic pay" this is.
            (
                f'{row["label"]} ({_("CTC Down structure")})'
                if row["code"] == "BASIC"
                else row["label"]
            ),
        )
        for row in rows
    ]

    current = (
        (form.data.get("percentage_of_code") if form.is_bound else None)
        or getattr(instance, "percentage_of_code", "")
        or ""
    )
    # Keep whatever is already stored selectable even if that code has since
    # been renamed or removed, so re-saving cannot silently retarget it.
    if current and not any(current == value for value, _label in choices):
        choices.insert(1, (current, f"{current} ({_('currently set')})"))

    # Styled like the form's other dropdowns. Not copied from the field being
    # replaced: on the model this is a plain CharField, so its widget is a text
    # input and its classes are the text-input ones. Rebuilding it as a
    # ChoiceField without this left the one bare browser dropdown on a form
    # where every other select is oh-select / select2.
    form.fields["percentage_of_code"] = forms.ChoiceField(
        choices=choices,
        required=False,
        label=field.label,
        help_text=field.help_text,
        initial=field.initial,
        widget=forms.Select(attrs=_select_attrs(form)),
    )

    # The same list for the "when it applies" rule, which measures a component
    # rather than taking a share of it. Deliberately a separate field: what a
    # component is a percentage OF and what decides whether it applies at all
    # are different questions and are often different components.
    gate = form.fields.get("if_component_code")
    if gate is not None:
        gate_current = (
            (form.data.get("if_component_code") if form.is_bound else None)
            or getattr(instance, "if_component_code", "")
            or ""
        )
        gate_choices = list(choices)
        if gate_current and not any(
            gate_current == value for value, _label in gate_choices
        ):
            gate_choices.insert(
                1, (gate_current, f"{gate_current} ({_('currently set')})")
            )
        form.fields["if_component_code"] = forms.ChoiceField(
            choices=gate_choices,
            required=False,
            label=gate.label,
            help_text=gate.help_text,
            initial=gate.initial,
            widget=forms.Select(attrs=_select_attrs(form)),
        )


def _select_attrs(form):
    """
    The widget attrs this form puts on an ordinary single-choice dropdown.

    Read off a sibling rather than hardcoded, so it keeps matching if the form
    styling changes.
    """
    for name in ("based_on", "if_choice", "if_condition", "maximum_unit"):
        widget = form.fields[name].widget if name in form.fields else None
        if isinstance(widget, forms.Select) and not isinstance(
            widget, forms.SelectMultiple
        ):
            if widget.attrs.get("class"):
                return dict(widget.attrs)
    return {"class": "oh-select oh-select-2"}


def restrict_to_system_fields(form):
    """
    Cut a system component's form down to the settings that mean anything.

    A template does not hold an amount, a formula, a rate or a list of
    employees: the loan schedule decides the amount, the attendance record
    decides the days, and the generator decides who it applies to. Leaving
    those fields on the form would offer settings that change nothing, which is
    worse than not offering them — someone sets a rate on "Loan repayment",
    saves, and reasonably expects repayments to change.

    So only the tax treatment and the proration basis survive, and only the
    ones that kind actually has. See payroll/system_components.py.
    """
    from payroll.system_components import editable_fields

    instance = getattr(form, "instance", None)
    if instance is None or not getattr(instance, "is_system", False):
        return

    keep = set(editable_fields(instance.system_key))
    for name in list(form.fields):
        if name not in keep:
            del form.fields[name]
    add_tax_override_fields(form)


PICK_TEMPLATE = r"""
<div class="oh-pick" data-pick="__ID__" data-url="__URL__" data-default="__DEFAULT__" data-i18n='__I18N__'>
  <div data-pick-values hidden></div>
  <div class="oh-pick__kind">
    <span class="oh-pick__chip oh-pick__chip--__KIND__">__KINDLABEL__</span>
    <span class="oh-pick__standard">__STANDARD__</span>
  </div>
  <div class="oh-pick__bar">
    <input type="search" class="oh-pick__search" data-pick-search autocomplete="off">
    __FILTERS__
  </div>
  <div class="oh-pick__scroll" data-pick-scroll>
    <table class="oh-pick__table">
      <thead>
        <tr>
          <th data-t="code"></th><th data-t="employee"></th><th data-pick-group data-t="department"></th>
          <th><label class="oh-pick__tax"><input type="checkbox" data-pick-all><span data-t="tax"></span></label></th>
        </tr>
      </thead>
      <tbody data-pick-body></tbody>
    </table>
    <div class="oh-pick__more" data-pick-more hidden></div>
  </div>
  <div class="oh-pick__count" data-pick-count></div>
</div>
<style>
  .oh-pick { font-size: 13px; }
  .oh-pick__kind { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .oh-pick__chip { padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 500; }
  .oh-pick__chip--earning { background: #e8f7ee; color: #15803d; }
  .oh-pick__chip--deduction { background: #fdecec; color: #b91c1c; }
  .oh-pick__standard { font-size: 12px; color: #6b7280; }
  .oh-pick__bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .oh-pick__search { flex: 1 1 auto; min-width: 0; height: 34px; padding: 0 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; }
  .oh-pick, .oh-pick * { box-sizing: border-box; }
  .oh-pick input[type="checkbox"] { margin: 0; vertical-align: middle; }
  .oh-pick__filter { flex: 0 1 128px; min-width: 0; width: 128px; height: 34px; padding: 0 6px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; background: #fff; }
  .oh-pick__count { margin-top: 6px; font-size: 12px; color: #6b7280; }
  .oh-pick__tax { display: flex; align-items: center; gap: 6px; margin: 0; cursor: pointer; }
  .oh-pick__scroll { max-height: 280px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 8px; scrollbar-width: thin; }
  .oh-pick__table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; }
  .oh-pick__table th { position: sticky; top: 0; z-index: 1; background: #f9fafb; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; padding: 7px 8px; border-bottom: 1px solid #e5e7eb; }
  .oh-pick__table th:nth-child(1) { width: 96px; }
  .oh-pick__table th:nth-child(4), .oh-pick__table td:nth-child(4) { width: 112px; }
  .oh-pick__table td { padding: 6px 8px; border-bottom: 1px solid #f3f4f6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .oh-pick__table tr.is-on td { background: #fdf3f1; }
  .oh-pick__more { padding: 8px; text-align: center; font-size: 12px; color: #6b7280; }
</style>
<script>
(function () {
  var root = document.querySelector('[data-pick="__ID__"]');
  if (!root || root.dataset.wired) return;
  root.dataset.wired = "1";
  var T = JSON.parse(root.dataset.i18n);
  var url = root.dataset.url, body = root.querySelector("[data-pick-body]");
  var scroller = root.querySelector("[data-pick-scroll]"), more = root.querySelector("[data-pick-more]");
  var values = root.querySelector("[data-pick-values]"), count = root.querySelector("[data-pick-count]");
  var all = root.querySelector("[data-pick-all]"), search = root.querySelector("[data-pick-search]");
  root.querySelectorAll("[data-t]").forEach(function (el) { el.textContent = T[el.dataset.t]; });
  search.placeholder = T.search;
  var picked = new Set(__INITIAL__.map(String)), next = "", query = "", busy = false;
  // What everyone follows: the standard setting. The posted ids are the ones that differ from it.
  var standard = root.dataset.default === "1";
  function want(pk) { return standard !== picked.has(pk); }
  var filters = root.querySelectorAll("[data-pick-filter]"), groupHead = root.querySelector("[data-pick-group]");
  function narrow() {
    var s = "";
    filters.forEach(function (f) { if (f.value) s += "&" + f.dataset.pickFilter + "=" + encodeURIComponent(f.value); });
    return s;
  }

  function sync() {
    values.innerHTML = "";
    picked.forEach(function (pk) {
      var i = document.createElement("input");
      i.type = "hidden"; i.name = "__NAME__"; i.value = pk;
      values.appendChild(i);
    });
    count.textContent = picked.size + " " + T.chosen;
    body.querySelectorAll("[data-pick-row]").forEach(function (tr) {
      var on = want(tr.dataset.pk);
      tr.querySelector("[data-pick-box]").checked = on;
      tr.classList.toggle("is-on", on);
    });
    var boxes = body.querySelectorAll("[data-pick-box]");
    var ticked = Array.prototype.filter.call(boxes, function (b) { return b.checked; }).length;
    all.checked = boxes.length > 0 && ticked === boxes.length;
    all.indeterminate = ticked > 0 && ticked < boxes.length;
  }
  function load(reset) {
    if (busy || (!reset && !next)) return;
    busy = true; more.hidden = false; more.textContent = T.loading;
    fetch(url + "?q=" + encodeURIComponent(query) + narrow() + "&page=" + (reset ? 1 : next), { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { var n = r.headers.get("X-Next-Page") || "", c = r.headers.get("X-Column") || "department"; return r.text().then(function (t) { return { t: t, n: n, c: c }; }); })
      .then(function (res) {
        groupHead.textContent = T[res.c];
        if (reset) body.innerHTML = "";
        body.insertAdjacentHTML("beforeend", res.t);
        next = res.n; sync();
      })
      .finally(function () { busy = false; more.hidden = true; if (next && scroller.scrollHeight <= scroller.clientHeight + 4) load(false); });
  }
  scroller.addEventListener("scroll", function () {
    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 40) load(false);
  });
  var timer;
  search.addEventListener("input", function () {
    var v = this.value; clearTimeout(timer);
    timer = setTimeout(function () { query = v; next = ""; load(true); }, 250);
  });
  root.addEventListener("change", function (e) {
    var t = e.target;
    if (t.matches("[data-pick-filter]")) { next = ""; load(true); return; }
    if (t === all) {
      var on = t.checked;
      fetch(url + "?ids=1&q=" + encodeURIComponent(query) + narrow()).then(function (r) { return r.json(); }).then(function (res) {
        res.ids.forEach(function (id) { if (on !== standard) picked.add(id); else picked.delete(id); });
        sync();
      });
    } else if (t.matches("[data-pick-box]")) {
      if (t.checked !== standard) picked.add(t.value); else picked.delete(t.value);
      sync();
    }
  });
  sync(); load(true);
})();
</script>
"""


class EmployeePickWidget(forms.Widget):
    """
    A searchable table of employees with the tax setting ticked or not on each. Everyone starts
    at the component's standard setting; the employees whose tick differs are posted, under the
    field's name. The rows load a page at a time from ``employee-pick-rows``.
    """

    def __init__(
        self,
        tax_default=False,
        tax_label="",
        kind="earning",
        kind_label="",
        standard="",
        attrs=None,
    ):
        super().__init__(attrs)
        self.tax_default = tax_default
        self.tax_label = tax_label
        self.kind = kind
        self.kind_label = kind_label
        self.standard = standard

    @staticmethod
    def filter_choices():
        """(query parameter, first option, [(pk, title)]) for each of the three group filters."""
        from base.models import Department, JobPosition, JobRole

        return (
            (
                "department",
                _("All Departments"),
                Department.objects.order_by("department").values_list(
                    "pk", "department"
                ),
            ),
            (
                "job_position",
                _("All Job Positions"),
                JobPosition.objects.order_by("job_position").values_list(
                    "pk", "job_position"
                ),
            ),
            (
                "job_role",
                _("All Job Roles"),
                JobRole.objects.order_by("job_role").values_list("pk", "job_role"),
            ),
        )

    def value_from_datadict(self, data, files, name):
        return data.getlist(name) if hasattr(data, "getlist") else data.get(name)

    def render(self, name, value, attrs=None, renderer=None):
        import json

        from django.urls import reverse
        from django.utils.html import escape
        from django.utils.safestring import mark_safe

        field_id = (attrs or {}).get("id", f"id_{name}")
        labels = {
            "code": _("Code"),
            "employee": _("Employee"),
            "department": _("Department"),
            "job_position": _("Job Position"),
            "job_role": _("Job Role"),
            "search": _("Search By Name, Code Or Department"),
            "chosen": _("Exceptions"),
            "tax": self.tax_label or _("Taxable"),
            "loading": _("Loading..."),
        }
        initial = [int(v) for v in (value or []) if str(v).isdigit()]
        filters = "".join(
            f'<select class="oh-pick__filter" data-pick-filter="{param}">'
            f'<option value="">{escape(label)}</option>'
            + "".join(
                f'<option value="{pk}">{escape(title)}</option>'
                for pk, title in choices
            )
            + "</select>"
            for param, label, choices in self.filter_choices()
        )
        html = (
            PICK_TEMPLATE.replace(
                "__I18N__",
                escape(json.dumps({k: str(v) for k, v in labels.items()})).replace(
                    "&quot;", '"'
                ),
            )
            .replace("__KINDLABEL__", escape(str(self.kind_label)))
            .replace("__KIND__", "deduction" if self.kind == "deduction" else "earning")
            .replace("__STANDARD__", escape(str(self.standard)))
            .replace("__FILTERS__", filters)
            .replace("__ID__", escape(field_id))
            .replace("__URL__", escape(reverse("employee-pick-rows")))
            .replace("__NAME__", escape(name))
            .replace("__DEFAULT__", "1" if self.tax_default else "0")
            .replace("__INITIAL__", json.dumps(initial))
        )
        return mark_safe(html)


def add_tax_override_fields(form):
    """
    The employees a standard component is taxed the other way for: one table to tick them in.
    Everyone else follows the setting above it; the ones ticked get its opposite.
    """
    from payroll.system_components import tax_field

    instance = form.instance
    field = tax_field(instance.system_key)
    if not field:
        return
    from employee.models import Employee
    from payroll.models.models import SystemComponentTaxOverride

    earning = field == "is_taxable"
    default = bool(getattr(instance, field))
    # The table is the one way to set it: the standard setting stays as it is and only the
    # employees who differ from it are stored.
    form.fields.pop(field, None)
    standard = (
        (_("Taxable") if default else _("Not Taxable"))
        if earning
        else (_("Pre-Tax") if default else _("Post-Tax"))
    )
    form.fields["tax_exception_employees"] = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        required=False,
        label=_("Tax Treatment By Employee"),
        help_text=(
            _(
                "Tick The Employees This Is Taxable For. New Employees Follow The Standard: %(standard)s."
            )
            if earning
            else _(
                "Tick The Employees This Is Taken Pre-Tax For. New Employees Follow The Standard: %(standard)s."
            )
        )
        % {"standard": standard},
        widget=EmployeePickWidget(
            tax_default=default,
            tax_label=_("Taxable") if earning else _("Pre-Tax"),
            kind="earning" if earning else "deduction",
            kind_label=(
                _("Earning")
                if earning
                else (_("Pre-Tax Deduction") if default else _("Deduction"))
            ),
            standard=_("Standard: %(standard)s") % {"standard": standard},
        ),
        initial=list(
            SystemComponentTaxOverride.objects.filter(
                system_key=instance.system_key
            ).values_list("employee_id", flat=True)
        ),
    )


SLAB_TEMPLATE = r"""
<div class="oh-slab" data-slab-table="__ID__" data-i18n='__I18N__'>
  <input type="hidden" name="__NAME__" id="__ID__" value="__VALUE__">
  <div class="oh-slab__head">
    <span class="oh-slab__title" data-t="title"></span>
    <span class="oh-slab__count"></span>
  </div>
  <div class="oh-slab__rows"></div>
  <div class="oh-slab__foot">
    <span class="oh-slab__sum"></span>
    <button type="button" class="oh-slab__add" data-slab-add></button>
  </div>
</div>
<style>
  .oh-slab { --s-line:#ece7e1; --s-mute:#8b90a0; --s-acc:var(--primary-600,#e54f38); --s-soft:#fdeeeb;
    border:1px solid var(--s-line); border-radius:10px; background:#fbf8f5; padding:8px 12px; font-size:12px; }
  .oh-slab__head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; }
  .oh-slab__title { font-weight:700; font-size:12.5px; }
  .oh-slab__count { color:var(--s-mute); font-size:11px; }
  .oh-slab__row { display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; padding:6px 0; border-top:1px solid var(--s-line); }
  .oh-slab__no { width:20px; height:20px; border-radius:50%; background:var(--s-soft); color:var(--s-acc); font-weight:700; font-size:11px; display:flex; align-items:center; justify-content:center; flex:none; }
  .oh-slab__lbl { font-size:9px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--s-mute); line-height:1.1; }
  .oh-slab__val { font-weight:600; font-size:12px; }
  .oh-slab__arrow { color:var(--s-mute); font-size:11px; }
  .oh-slab__until { width:56px; height:28px; border:1px solid #d9d4cd; border-radius:6px; padding:0 6px; background:#fff; font-size:12px; }
  .oh-slab__open { color:var(--s-mute); font-size:11.5px; min-width:56px; line-height:28px; }
  .oh-slab__unit { color:var(--s-mute); font-size:11px; }
  .oh-slab__tog { display:inline-flex; align-items:center; gap:5px; background:#f1ede8; border-radius:6px; padding:3px 8px; font-size:11.5px; color:#5b5f6d; cursor:pointer; user-select:none; margin:0; }
  .oh-slab__tog input { accent-color:var(--s-acc); margin:0; }
  .oh-slab__mult { display:inline-flex; align-items:center; gap:5px; background:var(--s-soft); border:1px solid #f0c9c2; border-radius:8px; padding:3px 10px; margin-left:auto; font-size:12px; }
  .oh-slab__mult input { width:44px; border:0; background:transparent; font-weight:700; font-size:12.5px; outline:none; padding:0; }
  .oh-slab__mult small { font-size:9px; font-weight:600; letter-spacing:.04em; color:var(--s-acc); }
  .oh-slab__del { width:26px; height:26px; border:0; background:transparent; color:#8b90a0; border-radius:6px; cursor:pointer; font-size:18px; line-height:1; padding:0; }
  .oh-slab__from { background:#f1ede8; color:#8b90a0; cursor:not-allowed; }
  .oh-slab__del:disabled { opacity:.35; cursor:not-allowed; }
  .oh-slab__del:disabled:hover { color:#8b90a0; background:transparent; }
  .oh-slab__del:hover { color:var(--s-acc); background:var(--s-soft); }
  .oh-slab__foot { display:flex; justify-content:space-between; align-items:center; gap:8px; border-top:1px solid var(--s-line); padding-top:8px; flex-wrap:wrap; }
  .oh-slab__sum { color:#3a3f4d; font-size:11.5px; }
  .oh-slab__add { border:1px dashed #c9c2b9; background:#fff; border-radius:6px; padding:3px 10px; font-weight:600; font-size:11.5px; cursor:pointer; }
  .oh-slab__add:hover { border-color:var(--s-acc); color:var(--s-acc); }
</style>
<script>
(function () {
  var box = document.querySelector('[data-slab-table="__ID__"]');
  if (!box || box.dataset.ready) return;
  box.dataset.ready = "1";
  var T = JSON.parse(box.dataset.i18n);
  var hidden = box.querySelector("input[type=hidden]");
  var rowsEl = box.querySelector(".oh-slab__rows");
  var bands = [];

  var titleEl = box.querySelector("[data-t=title]");
  titleEl.textContent = T.title;
  titleEl.title = T.help;
  box.querySelector("[data-slab-add]").textContent = "+ " + T.add;

  function num(v) { return +(+v).toFixed(2); }
  function fromOf(i) { return i ? bands[i - 1].to : 0; }

  function load() {
    hidden.value.split("\n").forEach(function (line) {
      if (!line.trim()) return;
      var v = line.split("|");
      bands.push({ to: v[1] === "" || v[1] === undefined ? null : parseFloat(v[1]), mult: v[2] });
    });
    if (!bands.length) bands = [{ to: 2, mult: "1.25" }, { to: null, mult: "1.5" }];
  }

  function rebuild() {
    rowsEl.innerHTML = "";
    bands.forEach(function (b, i) {
      var last = i === bands.length - 1;
      var row = document.createElement("div");
      row.className = "oh-slab__row";
      row.innerHTML =
        '<span class="oh-slab__no">' + (i + 1) + "</span>" +
        '<div><div class="oh-slab__lbl">' + T.from + '</div><input type="text" class="oh-slab__until oh-slab__from" data-from disabled></div>' +
        '<span class="oh-slab__arrow">&rarr;</span>' +
        '<div><div class="oh-slab__lbl">' + T.until + "</div>" +
        (b.to === null
          ? '<div class="oh-slab__open">' + T.noEnd + "</div>"
          : '<input type="number" min="0" step="any" class="oh-slab__until" value="' + b.to + '"> <span class="oh-slab__unit">' + T.hrs + "</span>") +
        "</div>" +
        (last ? '<label class="oh-slab__tog"><input type="checkbox"' + (b.to === null ? " checked" : "") + "> " + T.open + "</label>" : "") +
        '<span class="oh-slab__mult">&times; <input type="number" min="0" step="any" value="' + (b.mult || "") + '"><small>' + T.wage + "</small></span>" +
        '<button type="button" class="oh-slab__del" aria-label="' + T.remove + '"' + (i === 0 ? " disabled" : "") + '>&times;</button>';
      var until = row.querySelector(".oh-slab__until");
      if (until) until.oninput = function () { b.to = parseFloat(until.value); refresh(); };
      row.querySelector(".oh-slab__mult input").oninput = function (e) { b.mult = e.target.value; refresh(); };
      var tog = row.querySelector(".oh-slab__tog input");
      if (tog) tog.onchange = function () { b.to = tog.checked ? null : num(fromOf(i) + 2); rebuild(); };
      row.querySelector(".oh-slab__del").onclick = function () {
        if (bands.length > 1) { bands.splice(i, 1); rebuild(); }
      };
      rowsEl.appendChild(row);
    });
    refresh();
  }

  function refresh() {
    var lines = [], text = [];
    rowsEl.querySelectorAll("[data-from]").forEach(function (el, i) { el.value = num(fromOf(i)) + "h"; });
    bands.forEach(function (b, i) {
      var from = fromOf(i);
      lines.push([from, b.to === null ? "" : b.to, b.mult === undefined ? "" : b.mult].join("|"));
      text.push(num(from) + (b.to === null ? "h+" : "\u2013" + num(b.to) + "h") + " " + T.at + " " + (b.mult || 0) + "\u00d7");
    });
    box.querySelector(".oh-slab__count").textContent = bands.length + " " + T.bands + " \u00b7 " + T.sub;
    box.querySelector(".oh-slab__sum").textContent = T.pays + " " + text.join(", " + T.then + " ") + " " + T.of;
    hidden.value = lines.join("\n");
  }

  box.querySelector("[data-slab-add]").onclick = function () {
    var last = bands[bands.length - 1];
    if (last.to === null) { last.to = num(fromOf(bands.length - 1) + 2); bands.push({ to: null, mult: last.mult }); }
    else bands.push({ to: num(last.to + 2), mult: last.mult });
    rebuild();
  };

  load();
  rebuild();
})();
</script>
"""


class SlabTableWidget(forms.Widget):
    """
    Band editor for overtime slabs. It posts one hidden value of
    "from|to|multiplier" lines, which parse_slabs reads back.
    """

    def render(self, name, value, attrs=None, renderer=None):
        import json

        from django.utils.html import escape
        from django.utils.safestring import mark_safe

        field_id = (attrs or {}).get("id", f"id_{name}")
        labels = {
            "title": _("Overtime Slabs"),
            "sub": _("Multiplier Of Hourly Wage"),
            "bands": _("Bands"),
            "from": _("From"),
            "until": _("Until"),
            "hrs": _("Hrs"),
            "open": _("Open-Ended"),
            "noEnd": _("No Upper End"),
            "wage": _("Wage"),
            "add": _("Add Band"),
            "remove": _("Remove"),
            "pays": _("Pays"),
            "at": _("At"),
            "then": _("Then"),
            "of": _("Of The Hourly Wage."),
            "help": _(
                "Each Hour Of A Day's Overtime Is Paid At The Band It Falls In, As A "
                "Multiple Of The Contract's Hourly Wage. An Employee Whose Contract "
                "Has No Hourly Wage Gets Nothing."
            ),
        }
        html = (
            SLAB_TEMPLATE.replace(
                "__I18N__",
                escape(json.dumps({k: str(v) for k, v in labels.items()})).replace(
                    "&quot;", '"'
                ),
            )
            .replace("__ID__", escape(field_id))
            .replace("__NAME__", escape(name))
            .replace("__VALUE__", escape(value or ""))
        )
        return mark_safe(html)


def parse_slabs(text):
    """
    Turn the table's "from|to|multiplier" lines into (from, to, multiplier)
    tuples, checking they form one run of bands from the first hour up.
    """
    bands = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        parts = (line.split("|") + ["", "", ""])[:3]
        try:
            start = float(parts[0])
            end = float(parts[1]) if parts[1].strip() else None
            multiplier = float(parts[2])
        except ValueError:
            raise forms.ValidationError(_("Every Band Needs A Number In Each Box."))
        if start < 0 or multiplier < 0 or (end is not None and end <= start):
            raise forms.ValidationError(
                _("Each Band Must End After It Starts, And Cannot Be Negative.")
            )
        bands.append((start, end, multiplier))
    bands.sort(key=lambda band: band[0])
    if not bands:
        raise forms.ValidationError(_("Add At Least One Band For Overtime Slabs."))
    if bands[0][0] != 0:
        raise forms.ValidationError(_("The First Band Must Start At Hour 0."))
    for before, after in zip(bands, bands[1:]):
        if before[1] is None or before[1] != after[0]:
            raise forms.ValidationError(
                _("Bands Must Follow On From Each Other, With No Gap Or Overlap.")
            )
    if bands[-1][1] is not None:
        raise forms.ValidationError(
            _("Leave The Last Band's To Hour Empty, So It Covers Every Hour After.")
        )
    return bands


OVERTIME_TYPES = ("overtime", "week_off_overtime", "holiday_overtime")


class AppliesByFormMixin:
    """What an Allowance and a Deduction form share about who the component applies to."""

    def hide_apply_by(self):
        """The applies table draws and updates this field; the form only keeps it."""
        self.fields["apply_by"].widget = forms.HiddenInput()
        self.fields["apply_by"].required = False

    def check_apply_by(self, cleaned_data):
        """A group rule needs at least one group, and is never also an everyone rule."""
        if "apply_by" not in self.fields:
            return
        by = cleaned_data.get("apply_by") or "employees"
        cleaned_data["apply_by"] = by
        if by == "employees":
            return
        field = {
            "department": "apply_departments",
            "job_position": "apply_job_positions",
            "job_role": "apply_job_roles",
        }.get(by)
        if not cleaned_data.get(field):
            self.add_error("apply_by", _("Choose At Least One To Apply It To."))
        cleaned_data["include_active_employees"] = False

    def save_tax_overrides(self):
        """
        Store the exceptions: each ticked employee is taxed the opposite way to the setting this
        form is saving, so they stay exceptions whichever way the setting is later turned.
        """
        if "tax_exception_employees" not in self.fields or not self.instance.pk:
            return
        from payroll.models.models import SystemComponentTaxOverride
        from payroll.system_components import tax_field

        key = self.instance.system_key
        default = bool(getattr(self.instance, tax_field(key)))
        SystemComponentTaxOverride.objects.filter(system_key=key).delete()
        SystemComponentTaxOverride.objects.bulk_create(
            SystemComponentTaxOverride(
                system_key=key, employee_id=employee, value=not default
            )
            for employee in self.cleaned_data.get("tax_exception_employees") or []
        )


class AllowanceForm(AppliesByFormMixin, ModelForm):
    """
    Form for Allowance model
    """

    verbose_name = _("Allowance")

    overtime_slabs = forms.CharField(
        required=False,
        label="",
        widget=SlabTableWidget,
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Allowance
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        if instance := kwargs.get("instance"):
            # django forms not showing value inside the date, time html element.
            # so here overriding default forms instance method to set initial value
            initial = {}
            if instance.one_time_date is not None:
                initial = {
                    "one_time_date": instance.one_time_date.strftime("%Y-%m-%d"),
                }
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields["one_time_date"].initial = None
            self.fields["prorate_partial_days"].initial = True
        else:
            self.fields["overtime_slabs"].initial = "\n".join(
                "|".join(
                    "" if value is None else f"{value:g}"
                    for value in (slab.from_hours, slab.to_hours, slab.multiplier)
                )
                for slab in self.instance.slabs.all()
            )
        # Posts that predate the field leave it out; the model default is flat.
        self.fields["overtime_calc"].required = False
        self.hide_apply_by()
        apply_component_code_choices(self, payroll.models.models.Allowance)
        restrict_to_system_fields(self)
        from payroll.forms.component_layout import apply_labels

        apply_labels(self)
        restrict_maximum_unit_to_calendar_days(self)

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("generic/form.html", context)
        return table_html

    def clean_slabs(self, cleaned_data):
        """Validates the slab table, which only counts for a slab overtime allowance."""
        self.slab_bands = []
        if "overtime_calc" not in self.fields:
            return
        cleaned_data["overtime_calc"] = cleaned_data.get("overtime_calc") or "flat"
        uses_slabs = (
            not cleaned_data.get("is_fixed")
            and cleaned_data.get("based_on") in OVERTIME_TYPES
            and cleaned_data["overtime_calc"] == "slab"
        )
        if not uses_slabs:
            if cleaned_data.get("based_on") not in OVERTIME_TYPES:
                cleaned_data["overtime_calc"] = "flat"
            return
        try:
            self.slab_bands = parse_slabs(cleaned_data.get("overtime_slabs"))
        except forms.ValidationError as error:
            self.add_error("overtime_slabs", error)

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        self.clean_slabs(self.cleaned_data)
        self.check_apply_by(self.cleaned_data)

        if cleaned_data.get("if_condition") == "range":
            cleaned_data["if_amount"] = 0
            start_range = cleaned_data.get("start_range")
            end_range = cleaned_data.get("end_range")
            if start_range and end_range and end_range <= start_range:
                raise forms.ValidationError(
                    {"end_range": "End range cannot be less than start range."}
                )
            if not start_range and not end_range:
                raise forms.ValidationError(
                    {
                        "start_range": 'This field is required when condition is "range".',
                        "end_range": 'This field is required when condition is "range".',
                    }
                )
            elif not start_range:
                raise forms.ValidationError(
                    {"start_range": 'This field is required when condition is "range".'}
                )
            elif not end_range:
                raise forms.ValidationError(
                    {"end_range": 'This field is required when condition is "range".'}
                )
        else:
            cleaned_data["start_range"] = None
            cleaned_data["end_range"] = None

    def save_slabs(self):
        """Replaces the allowance's bands with the ones on the table."""
        if not self.instance.pk:
            return
        self.instance.slabs.all().delete()
        for start, end, multiplier in getattr(self, "slab_bands", []):
            payroll.models.models.AllowanceSlab.objects.create(
                allowance_id=self.instance,
                from_hours=start,
                to_hours=end,
                multiplier=multiplier,
            )

    def save(self, commit: bool = ...) -> Any:
        # Before the component itself is saved: saving it is what re-aligns the lines it generated,
        # and they must read the employee settings as they are now.
        self.save_tax_overrides()
        super().save(commit)
        self.save_slabs()
        other_conditions = self.data.getlist("other_conditions")
        other_fields = self.data.getlist("other_fields")
        other_values = self.data.getlist("other_values")
        multiple_conditions = []
        try:
            if self.instance.pk:
                self.instance.other_conditions.all().delete()
            if self.instance.is_condition_based:
                for index, field in enumerate(other_fields):
                    condition = MultipleCondition(
                        field=field,
                        condition=other_conditions[index],
                        value=other_values[index],
                    )
                    condition.save()
                    multiple_conditions.append(condition)
        except Exception as e:
            logger(e)
        if commit:
            self.instance.other_conditions.add(*multiple_conditions)
        save_apply_conditions(self, commit)
        return multiple_conditions


class DeductionForm(AppliesByFormMixin, ModelForm):
    """
    Form for Deduction model
    """

    verbose_name = _("Deduction")

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Deduction
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "one_time_date": forms.DateTimeInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        if instance := kwargs.get("instance"):
            # django forms not showing value inside the date, time html element.
            # so here overriding default forms instance method to set initial value
            initial = {}
            if instance.one_time_date is not None:
                initial = {
                    "one_time_date": instance.one_time_date.strftime("%Y-%m-%d"),
                }
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.hide_apply_by()
        apply_component_code_choices(self, payroll.models.models.Deduction)
        restrict_to_system_fields(self)
        from payroll.forms.component_layout import apply_labels

        apply_labels(self)
        restrict_maximum_unit_to_calendar_days(self)

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        self.check_apply_by(self.cleaned_data)

        if cleaned_data.get("if_condition") == "range":
            cleaned_data["if_amount"] = 0
            start_range = cleaned_data.get("start_range")
            end_range = cleaned_data.get("end_range")

            if start_range and end_range and int(end_range) <= int(start_range):
                raise forms.ValidationError(
                    {"end_range": "End range cannot be less than start range."}
                )
            if not start_range and not end_range:
                raise forms.ValidationError(
                    {
                        "start_range": 'This field is required when condition is "range".',
                        "end_range": 'This field is required when condition is "range".',
                    }
                )
            elif not start_range:
                raise forms.ValidationError(
                    {"start_range": 'This field is required when condition is "range".'}
                )
            elif not end_range:
                raise forms.ValidationError(
                    {"end_range": 'This field is required when condition is "range".'}
                )
        else:
            cleaned_data["start_range"] = None
            cleaned_data["end_range"] = None

        if (
            self.data.get("update_compensation") is not None
            and self.data.get("update_compensation") != ""
        ):
            if (
                self.data.get("one_time_date") is None
                and self.data.get("one_time_date") == ""
            ):
                raise forms.ValidationError(
                    {"one_time_date": _("This field is required.")}
                )
            if self.data.get("amount") is None and self.data.get("amount") == "":
                raise forms.ValidationError({"amount": _("This field is required.")})
        return cleaned_data

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        self.save_tax_overrides()
        super().save(commit)
        other_conditions = self.data.getlist("other_conditions")
        other_fields = self.data.getlist("other_fields")
        other_values = self.data.getlist("other_values")
        multiple_conditions = []
        try:
            if self.instance.pk:
                self.instance.other_conditions.all().delete()
            if self.instance.is_condition_based:
                for index, field in enumerate(other_fields):
                    condition = MultipleCondition(
                        field=field,
                        condition=other_conditions[index],
                        value=other_values[index],
                    )
                    condition.save()
                    multiple_conditions.append(condition)
        except Exception as e:
            print(e)
        if commit:
            self.instance.other_conditions.add(*multiple_conditions)
        save_apply_conditions(self, commit)
        return multiple_conditions


class SalaryStructureForm(ModelForm):
    """
    Form for SalaryStructure model
    """

    employees = HorillaMultiSelectField(
        queryset=Employee.objects.all(),
        required=False,
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label=_("Employees"),
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = SalaryStructure
        # structure_mode was missing, which made CTC Down unreachable: the mode
        # existed on the model and was read by the engine, but nothing outside a
        # shell could set it.
        fields = ["title", "structure_mode", "allowances", "deductions"]

    def _employees_on_structure(self):
        if not self.instance.pk:
            return Employee.objects.none()
        return Employee.objects.filter(
            contract_set__salary_structure_id=self.instance,
            contract_set__contract_status="active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Neither the per-employee rows a loan generates nor the standard
        # components that govern them belong in a structure: the first are
        # already targeted at one person, the second are never paid at all.
        self.fields["allowances"].queryset = (
            self.fields["allowances"]
            .queryset.exclude(only_show_under_employee=True)
            .exclude(is_system=True)
        )
        self.fields["deductions"].queryset = (
            self.fields["deductions"]
            .queryset.exclude(only_show_under_employee=True)
            .exclude(is_system=True)
        )
        # Only employees this structure may actually take on: an active
        # contract, and that contract not already naming another structure.
        # Offering the rest was offering to silently move someone off whatever
        # structure they were on.
        from payroll.methods.structure_rules import assignable_employees

        self.fields["employees"].queryset = assignable_employees(self.instance)
        if self.instance.pk:
            self.initial["employees"] = self._employees_on_structure()

    def clean(self):

        cleaned_data = super().clean()
        self.errors.pop("employees", None)
        employees = Employee.objects.filter(pk__in=self.data.getlist("employees"))
        cleaned_data["employees"] = employees
        # Enforced here as well as in the queryset: the multi-select's own
        # filter panel queries employees through a generic route that knows
        # nothing about this restriction, so the list is not the last word on
        # what can be submitted.
        from payroll.methods.structure_rules import unassignable_reason

        no_active_contract = []
        taken = []
        for employee in employees:
            reason = unassignable_reason(employee, self.instance)
            if reason == "no_contract":
                no_active_contract.append(employee)
            elif reason is not None:
                taken.append((employee, reason))

        problems = []
        if no_active_contract:
            problems.append(
                _(
                    "These employees have no active contract, so a salary "
                    "structure can't be assigned to them: %(names)s"
                )
                % {"names": ", ".join(str(one) for one in no_active_contract)}
            )
        if taken:
            problems.append(
                _(
                    "These employees are already on another salary structure. "
                    "Remove them from it first, or change their contract: "
                    "%(names)s"
                )
                % {
                    "names": ", ".join(
                        f"{employee} ({structure})" for employee, structure in taken
                    )
                }
            )
        if problems:
            raise forms.ValidationError({"employees": problems})

        # One basic pay component per structure.
        flagged = [
            allowance
            for allowance in (cleaned_data.get("allowances") or [])
            if getattr(allowance, "is_basic_pay", False)
        ]
        if len(flagged) > 1:
            raise forms.ValidationError(
                {
                    "allowances": _(
                        "A structure can have only one basic pay component. "
                        "Marked as basic pay: %(names)s"
                    )
                    % {"names": ", ".join(str(one) for one in flagged)}
                }
            )

        # The component set has to agree with what the mode says the contract
        # wage means. Checked here rather than in Model.clean() because the M2M
        # is not populated during model validation.
        from payroll.methods.structure_rules import structure_problems

        problems = structure_problems(
            cleaned_data.get("structure_mode"),
            cleaned_data.get("allowances") or [],
            cleaned_data.get("deductions") or [],
        )
        if problems:
            raise forms.ValidationError({"allowances": problems})

        return cleaned_data

    def save(self, commit=True):

        previous_allowances = (
            set(self.instance.allowances.all()) if self.instance.pk else set()
        )
        previous_deductions = (
            set(self.instance.deductions.all()) if self.instance.pk else set()
        )
        previous_employees = set(self._employees_on_structure())

        instance = super().save(commit=False)
        instance.save()

        submitted_allowances = set(self.cleaned_data.get("allowances") or [])
        submitted_deductions = set(self.cleaned_data.get("deductions") or [])
        submitted_employees = set(self.cleaned_data.get("employees") or [])

        for allowance in submitted_allowances - previous_allowances:
            instance.add_allowance(allowance)
        for allowance in previous_allowances - submitted_allowances:
            instance.remove_allowance(allowance)

        for deduction in submitted_deductions - previous_deductions:
            instance.add_deduction(deduction)
        for deduction in previous_deductions - submitted_deductions:
            instance.remove_deduction(deduction)

        for employee in submitted_employees - previous_employees:
            contract = employee.contract_set.filter(contract_status="active").first()
            if contract:
                contract.set_salary_structure(instance)
        for employee in previous_employees - submitted_employees:
            contract = employee.contract_set.filter(
                contract_status="active", salary_structure_id=instance
            ).first()
            if contract:
                contract.set_salary_structure(None)

        return instance


class QuickAllowanceForm(ModelForm):
    """
    Minimal Allowance create form, used for the dynamic "create new allowance"
    option inside the Salary Structure form.
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = Allowance
        fields = ["title", "is_taxable", "is_fixed", "amount", "based_on", "rate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].required = True
        self.instance.include_active_employees = False


class QuickDeductionForm(ModelForm):
    """
    Minimal Deduction create form, used for the dynamic "create new deduction"
    option inside the Salary Structure form.
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = Deduction
        fields = [
            "title",
            "is_pretax",
            "is_fixed",
            "amount",
            "based_on",
            "rate",
            "employer_rate",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].required = True
        self.instance.include_active_employees = False


class PayslipForm(ModelForm):
    """
    Form for Payslip
    """

    cols = {
        "employee_id": 12,
        "start_date": 12,
        "end_date": 12,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_contracts = Contract.objects.filter(contract_status="active")
        self.fields["employee_id"].choices = [
            (contract.employee_id.id, contract.employee_id)
            for contract in active_contracts
            if contract.employee_id.is_active
        ]
        self.fields["employee_id"].widget.attrs.update(
            {
                "hx-get": "/payroll/check-contract-start-date",
                "hx-target": "#contractStartDateDiv",
                "hx-include": "#payslipCreateForm",
                "hx-trigger": "change delay:300ms",
                "hx-swap": "innerHTML",
            }
        )
        if self.instance.pk is None:
            self.initial["start_date"] = datetime.date.today().replace(day=1)
            self.initial["end_date"] = datetime.date.today()

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Payslip
        fields = [
            "employee_id",
            "start_date",
            "end_date",
        ]
        exclude = ["is_active"]
        widgets = {
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "hx-get": "/payroll/check-contract-start-date",
                    "hx-target": "#contractStartDateDiv",
                    "hx-include": "#payslipCreateForm",
                    "hx-trigger": "change delay:300ms",
                    "hx-swap": "innerHTML",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


class GeneratePayslipForm(HorillaForm):
    """
    Form for Payslip
    """

    group_name = forms.CharField(
        label="Batch name",
        required=False,
        # help_text="Enter +-something if you want to generate payslips by batches",
    )
    employee_id = HorillaMultiSelectField(
        queryset=Employee.objects.none(),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label="Employee",
        required=True,
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        today = datetime.date.today()
        if end_date < start_date:
            raise forms.ValidationError(
                {
                    "end_date": "The end date must be greater than or equal to the start date."
                }
            )
        if start_date > today:
            raise forms.ValidationError(
                {"end_date": "The start date cannot be in the future."}
            )

        if end_date > today:
            raise forms.ValidationError(
                {"end_date": "The end date cannot be in the future."}
            )
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"].queryset = Employee.objects.filter(
            is_active=True,
            contract_set__isnull=False,
            contract_set__contract_status="active",
        )
        self.fields["employee_id"].widget.attrs.update(
            {"class": "oh-select oh-select-2", "id": uuid.uuid4()}
        )
        self.fields["start_date"].widget.attrs.update({"class": "oh-input w-100"})
        self.fields["group_name"].widget.attrs.update({"class": "oh-input w-100"})
        self.fields["end_date"].widget.attrs.update({"class": "oh-input w-100"})
        self.initial["start_date"] = datetime.date.today().replace(day=1)
        self.initial["end_date"] = datetime.date.today()

    class Meta:
        """
        Meta class for additional options
        """

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class PayrollSettingsForm(ModelForm):
    """
    Form for PayrollSettings model
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = models.PayrollSettings
        fields = ["currency_symbol", "position"]
        widgets = {
            "position": forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        }


excel_columns = [
    ("employee_id", _("Employee")),
    ("group_name", _("Batch")),
    ("start_date", _("Start Date")),
    ("end_date", _("End Date")),
    ("contract_wage", _("Contract Wage")),
    ("basic_pay", _("Basic Pay")),
    ("gross_pay", _("Gross Pay")),
    ("deduction", _("Deduction")),
    ("net_pay", _("Net Pay")),
    ("status", _("Status")),
    ("employee_id__employee_bank_details__bank_name", _("Bank Name")),
    ("employee_id__employee_bank_details__branch", _("Branch")),
    ("employee_id__employee_bank_details__account_number", _("Account Number")),
    ("employee_id__employee_bank_details__any_other_code1", _("Bank Code #1")),
    ("employee_id__employee_bank_details__any_other_code2", _("Bank Code #2")),
    ("employee_id__employee_bank_details__country", _("Country")),
    ("employee_id__employee_bank_details__state", _("State")),
    ("employee_id__employee_bank_details__city", _("City")),
]


class PayslipExportColumnForm(forms.Form):
    selected_fields = forms.MultipleChoiceField(
        choices=excel_columns,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "group_name",
            "start_date",
            "end_date",
            "basic_pay",
            "gross_pay",
            "net_pay",
            "status",
        ],
    )


exclude_fields = ["id", "contract_document", "is_active", "note", "note", "created_at"]


class ContractExportFieldForm(forms.Form):
    model_fields = Contract._meta.get_fields()
    field_choices = [
        (field.name, export_field_label(field.verbose_name))
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in exclude_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "contract_name",
            "employee_id",
            "contract_start_date",
            "contract_end_date",
            "wage_type",
            "wage",
            "filing_status",
            "contract_status",
        ],
    )


def rate_validator(value):
    """
    Percentage validator
    """
    if value < 0:
        raise ValidationError(_("Rate must be greater than 0"))
    if value > 100:
        raise ValidationError(_("Rate must be less than 100"))


class BonusForm(Form):
    """
    Bonus Creating Form
    """

    title = forms.CharField(max_length=100)
    date = forms.DateField(widget=forms.DateInput(), required=False)
    employee_id = forms.IntegerField(label="Employee", widget=forms.HiddenInput())
    is_fixed = forms.BooleanField(
        label="Fixed", initial=True, required=False, widget=forms.CheckboxInput()
    )
    amount = forms.DecimalField(
        label="Amount",
        required=False,
    )
    based_on = forms.ChoiceField(choices=[("BASIC_PAY", "Basic Pay")], required=False)
    rate = forms.FloatField(
        validators=[
            rate_validator,
        ],
        label="Rate",
        required=False,
    )

    def save(self, commit=True):
        title = self.cleaned_data["title"]
        date = self.cleaned_data["date"]
        employee_id = self.cleaned_data["employee_id"]
        amount = self.cleaned_data["amount"]
        is_fixed = self.cleaned_data["is_fixed"]
        rate = self.cleaned_data["rate"]

        bonus = Allowance()
        bonus.title = title
        bonus.one_time_date = date
        bonus.only_show_under_employee = True
        bonus.amount = amount
        bonus.is_fixed = is_fixed
        bonus.rate = rate
        bonus.save()
        bonus.include_active_employees = False
        bonus.specific_employees.set([employee_id])
        bonus.save()

        return bonus

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": "oh-input w-100"})
        self.fields["date"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )
        self.fields["is_fixed"].widget.attrs.update({"class": "oh-switch__checkbox"})


class PayslipAllowanceForm(BonusForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].widget = forms.HiddenInput()


class PayslipDeductionForm(ModelForm):
    """
    Bonus Creating Form
    """

    verbose_name = _("Deduction")

    class Meta:
        model = Deduction
        fields = [
            "title",
            "one_time_date",
            "update_compensation",
            "is_tax",
            "is_pretax",
            "is_fixed",
            "amount",
            "based_on",
            "rate",
            "employer_rate",
            "has_max_limit",
            "maximum_amount",
        ]
        widgets = {
            "one_time_date": forms.HiddenInput(),
        }

    # employee_id = forms.IntegerField(label="Employee", widget=forms.HiddenInput())

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("one_time_deduction.html", context)
        return table_html


class LoanAccountForm(ModelForm):
    """
    LoanAccountForm
    """

    verbose_name = _("Loans & Salary Advances")
    cols = {
        "description": 12,
    }

    class Meta:
        model = LoanAccount
        fields = "__all__"
        exclude = ["is_active", "settled_date"]
        widgets = {
            "provided_date": forms.DateTimeInput(attrs={"type": "date"}),
            "installment_start_date": forms.DateTimeInput(attrs={"type": "date"}),
        }

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["provided_date"] = str(datetime.date.today())
            self.initial["installment_start_date"] = str(datetime.date.today())
        if self.instance.pk:
            self.verbose_name = self.instance.title
            # <input type="date"> needs YYYY-MM-DD; the DateTimeInput widget
            # doesn't render date objects that way, so pass strings.
            if self.instance.provided_date:
                self.initial["provided_date"] = str(self.instance.provided_date)
            if self.instance.installment_start_date:
                self.initial["installment_start_date"] = str(
                    self.instance.installment_start_date
                )
            # Edit shows the same fields as create; the ones that must not
            # change any more are locked (disabled) instead of removed, so
            # both forms keep an identical layout across the Loan / Salary
            # Advance / Fine tabs.
            locked_fields = []
            if Payslip.objects.filter(
                installment_ids__in=list(
                    self.instance.deduction_ids.values_list("id", flat=True)
                )
            ).exists():
                # Once an installment is on a paid payslip the schedule can
                # no longer be regenerated (see payroll.signals
                # create_installments), so these become read-only.
                locked_fields += [
                    "employee_id",
                    "loan_amount",
                    "installments",
                    "installment_amount",
                    "installment_start_date",
                ]
            for field_name in locked_fields:
                if field_name not in self.fields:
                    continue
                field = self.fields[field_name]
                field.disabled = True
                if field_name == "employee_id":
                    # Disabled selects normally render as bare text (see
                    # .oh-select:disabled in the theme) - opt this one back
                    # into a boxed look via oh-select--boxed-locked so it
                    # doesn't stand out next to the other fields here.
                    attrs = field.widget.attrs
                    attrs["class"] = (
                        attrs.get("class", "") + " oh-select--boxed-locked"
                    ).strip()

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)

        start_date = cleaned_data.get("installment_start_date")
        provided_date = cleaned_data.get("provided_date")
        dates_touched = (
            not self.instance.pk
            or "installment_start_date" in self.changed_data
            or "provided_date" in self.changed_data
        )
        if (
            start_date
            and provided_date
            and dates_touched
            and start_date < provided_date
        ):
            raise forms.ValidationError(
                _(
                    "Installment start date should be greater than or equal to provided date"
                )
            )
        if cleaned_data.get("installments") != None:
            if cleaned_data.get("installments") <= 0:
                raise forms.ValidationError(
                    _("Installments needs to be a positive integer")
                )

        return cleaned_data


class AssetFineForm(LoanAccountForm):
    verbose_name = _("Asset Fine")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan_amount"].label = _("Fine Amount")
        self.fields["provided_date"].label = _("Fine Date")

        fields_to_exclude = [
            "employee_id",
            "type",
        ]
        for field in fields_to_exclude:
            if field in self.fields:
                del self.fields[field]
        field_order = [
            "title",
            "loan_amount",
            "provided_date",
            "description",
            "installments",
            "installment_start_date",
            "installment_amount",
            "settled",
        ]

        self.fields = {
            field: self.fields[field] for field in field_order if field in self.fields
        }


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result[0] if result else None


class ReimbursementForm(ModelForm):
    """
    Optimized Reimbursement / Encashment Form
    """

    cols = {"description": 12}

    verbose_name = "Reimbursement / Encashment"

    class Meta:
        model = Reimbursement
        fields = "__all__"
        exclude = ["is_active", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request = getattr(horilla_middlewares._thread_locals, "request", None)
        self.employee = self.get_employee()  # 819

        if not self.instance.pk:
            self.initial["allowance_on"] = str(datetime.date.today())

        self.initial["employee_id"] = self.employee.id if self.employee else None

        # When opened from a specific tab (Reimbursements / Leave Encashments /
        # Bonus Encashments), the tab's own Create button passes ?type=... so
        # the record being created always matches the tab it was opened from -
        # the Type field is then locked instead of shown as a free choice.
        self.fixed_type = (
            self.request.GET.get("type")
            if self.request and not self.instance.pk
            else None
        )
        if self.fixed_type:
            self.initial["type"] = self.fixed_type

        self.configure_fields()

    def get_employee(self):
        """Resolves employee either from form data or request."""
        if hasattr(self.instance, "employee_id") and self.instance.employee_id:
            return self.instance.employee_id

        employee_qs = self.fields["employee_id"].queryset
        employee_id = self.data.get("employee_id") if self.data else None

        if employee_id and (emp := employee_qs.filter(id=employee_id).first()):
            return emp

        if self.request and (emp := self.request.user.employee_get):
            if not self.instance.pk and emp in employee_qs:
                return emp
            if self.instance.pk and emp.id == self.instance.employee_id:
                return emp

        return employee_qs.first()

    def get_encashable_leaves(self, employee):
        LeaveType = get_horilla_model_class(app_label="leave", model="leavetype")
        return LeaveType.objects.filter(
            employee_available_leave__employee_id=employee,
            employee_available_leave__total_leave_days__gte=1,
            is_encashable=True,
        )

    def configure_fields(self):
        exclude_fields = []

        if self.request and not self.request.user.has_perm("payroll.add_reimbursement"):
            exclude_fields.append("employee_id")

        self.setup_leave_fields()

        self.fields["type"].widget.attrs["onchange"] = "toggleReimbursmentType($(this))"
        self.fields["employee_id"].widget.attrs["onchange"] = (
            "getAssignedLeave($(this)); "
            "if (window.refreshBonusPointsNote) refreshBonusPointsNote();"
        )

        self.fields["allowance_on"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )

        self.fields["attachment"] = MultipleFileField(label="Attachments")
        self.fields["attachment"].widget.attrs["accept"] = ".jpg, .jpeg, .png, .pdf"

        # Also hidden when editing - which type a record is doesn't change
        # after creation, so there's nothing to pick here either.
        if self.fixed_type or self.instance.pk:
            self.fields["type"].widget = forms.HiddenInput()

        self.exclude_fields_by_type(exclude_fields)

        for field in exclude_fields:
            self.fields.pop(field, None)

    def setup_leave_fields(self):
        """Setup leave-related fields only if leave app is installed."""
        if not apps.is_installed("leave") or not self.employee:
            return

        AvailableLeave = get_horilla_model_class(
            app_label="leave", model="availableleave"
        )
        assigned_leaves = self.get_encashable_leaves(self.employee)

        self.assigned_leaves = AvailableLeave.objects.filter(
            leave_type_id__in=assigned_leaves, employee_id=self.employee
        )
        self.fields["leave_type_id"].queryset = assigned_leaves
        self.fields["leave_type_id"].empty_label = None
        self.fields["employee_id"].empty_label = None

    def exclude_fields_by_type(self, exclude_fields):
        """Determine which fields to exclude based on type."""
        type = (
            self.data.get("type")
            if self.data
            else (self.fixed_type or (self.instance.type if self.instance else None))
        )
        is_edit = self.instance and self.instance.pk

        if type == "reimbursement" and (is_edit or self.data or self.fixed_type):
            exclude_fields += [
                "leave_type_id",
                "cfd_to_encash",
                "ad_to_encash",
                "bonus_to_encash",
            ]
        elif type == "leave_encashment" and (is_edit or self.data or self.fixed_type):
            exclude_fields += ["attachment", "amount", "bonus_to_encash"]
        elif type == "bonus_encashment" and (is_edit or self.data or self.fixed_type):
            exclude_fields += [
                "attachment",
                "amount",
                "leave_type_id",
                "cfd_to_encash",
                "ad_to_encash",
            ]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()

        type_ = cleaned_data.get("type")
        employee = cleaned_data.get("employee_id")

        if not type_ or not employee:
            return cleaned_data

        if type_ == "bonus_encashment":
            bonus_to_encash = (
                self.instance.bonus_to_encash
                if self.instance.pk
                else cleaned_data.get("bonus_to_encash")
            )
            available_points = BonusPoint.objects.filter(employee_id=employee).first()

            if bonus_to_encash is not None:
                if bonus_to_encash <= 0:
                    self.add_error(
                        "bonus_to_encash", "Points must be greater than zero to redeem."
                    )
                elif not available_points or available_points.points < bonus_to_encash:
                    self.add_error(
                        "bonus_to_encash", "Not enough bonus points to redeem"
                    )

        elif type_ == "leave_encashment":
            leave_type = (
                self.instance.leave_type_id
                if self.instance.pk
                else cleaned_data.get("leave_type_id")
            )
            cfd_to_encash = (
                self.instance.cfd_to_encash
                if self.instance.pk
                else cleaned_data.get("cfd_to_encash", 0)
            )
            ad_to_encash = (
                self.instance.ad_to_encash
                if self.instance.pk
                else cleaned_data.get("ad_to_encash", 0)
            )

            if not leave_type:
                self.add_error("leave_type_id", "This field is required")
            else:
                encashable = self.get_encashable_leaves(employee)
                if leave_type not in encashable:
                    self.add_error("leave_type_id", "This leave type is not encashable")
                else:
                    AvailableLeave = get_horilla_model_class("leave", "availableleave")
                    available_leave = AvailableLeave.objects.filter(
                        leave_type_id=leave_type, employee_id=employee
                    ).first()

                    if available_leave:
                        if cfd_to_encash < 0:
                            self.add_error(
                                "cfd_to_encash", _("Value can't be negative.")
                            )
                        elif cfd_to_encash > available_leave.carryforward_days:
                            self.add_error(
                                "cfd_to_encash",
                                _("Not enough carryforward days to redeem"),
                            )

                        if ad_to_encash < 0:
                            self.add_error(
                                "ad_to_encash", _("Value can't be negative.")
                            )
                        elif ad_to_encash > available_leave.available_days:
                            self.add_error(
                                "ad_to_encash", _("Not enough available days to redeem")
                            )

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
        multiple_attachment_ids = []
        is_new = not self.instance.pk
        attachments = self.files.getlist("attachment")

        if attachments:
            self.instance.attachment = attachments[0]

        instance = super().save(commit=commit)

        if attachments:
            attachment_objs = [
                ReimbursementMultipleAttachment(attachment=file) for file in attachments
            ]
            created_attachments = ReimbursementMultipleAttachment.objects.bulk_create(
                attachment_objs
            )
            multiple_attachment_ids = [obj.pk for obj in created_attachments]
            instance.other_attachments.add(*multiple_attachment_ids)

        if is_new:
            try:
                manager = instance.employee_id.employee_work_info.reporting_manager_id
                if manager and manager.employee_user_id:
                    notify.send(
                        instance.employee_id,  # 816
                        recipient=manager.employee_user_id,
                        verb=gettext_noop(
                            "You have a new reimbursement request to approve for %(employee)s."
                        ),
                        verb_params={"employee": str(instance.employee_id)},
                        icon="information",
                        redirect=f"/payroll/view-reimbursement?id={instance.id}",
                    )
            except Exception:
                pass

        return instance, attachments


class ConditionForm(ModelForm):
    """
    Multiple condition form
    """

    class Meta:
        model = Allowance
        fields = [
            "field",
            "condition",
            "value",
        ]


# ===========================Auto payslip generate================================
class PayslipAutoGenerateForm(ModelForm):
    class Meta:
        model = PayslipAutoGenerate
        fields = ["generate_day", "company_id", "auto_generate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_company_id = horilla_middlewares.get_selected_company()
        if active_company_id and active_company_id != "all":
            self.fields["company_id"].queryset = Company.objects.filter(
                id=active_company_id
            )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class PayAdjustmentForm(ModelForm):
    """Arrears owed to an employee, or an excess payment to take back: one amount on one date."""

    verbose_name = _("Arrears & Recovery")
    cols = {"reason": 12}

    # Saving as Confirmed makes the pay line; saving a confirmed entry as Draft takes it away.
    status = forms.ChoiceField(
        required=False,
        label=_("Status"),
        choices=payroll.models.models.PayAdjustment.STATUS_CHOICES,
    )
    # Taxable for arrears, pre-tax for a recovery (the page relabels it with the type). Always
    # Yes or No: it starts at the standard setting, or the employee's own exception to it.
    tax_treatment = forms.TypedChoiceField(
        choices=[("true", _("Yes")), ("false", _("No"))],
        coerce=lambda value: value == "true",
        label=_("Taxable"),
    )
    field_order = [
        "employee_id",
        "kind",
        "title",
        "pay_date",
        "amount",
        "tax_treatment",
        "status",
        "reason",
    ]

    class Meta:
        model = payroll.models.models.PayAdjustment
        fields = [
            "employee_id",
            "kind",
            "title",
            "pay_date",
            "amount",
            "tax_treatment",
            "reason",
        ]
        widgets = {
            "pay_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "reason": forms.Textarea(attrs={"rows": 2}),
        }

    def render_structured(self):
        """
        The modal's body: the generic form plus a Delete button for a draft. Put in place of
        ``structured`` by the form view, because the base view resets that on every request.
        """
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        # With the request, so the template has the user's permissions (the Delete button needs them).
        return render_to_string(
            "payroll/pay_adjustment/form.html", {"form": self}, request=request
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"].queryset = Employee.objects.filter(is_active=True)
        self.initial["tax_treatment"] = self._tax_initial()
        if not self.instance.pk:
            self.initial["pay_date"] = str(datetime.date.today())
        else:
            self.verbose_name = self.instance.title
            # Choosing Draft on a confirmed entry unlocks it in the same save: the page enables the
            # fields as soon as Draft is picked, so what is posted with it has to be accepted.
            unlocking = (
                self.is_bound
                and self.instance.status == "approved"
                and self.data.get("status") == "draft"
            )
            if not self.instance.is_editable and not unlocking:
                # A confirmed entry has already made its pay line, so only its status can still
                # change (back to Draft, which takes the line away).
                for name, field in self.fields.items():
                    if name == "status":
                        continue
                    field.disabled = True
                    if isinstance(field.widget, forms.Select):
                        # A disabled select shows as bare text in this theme; this class keeps it
                        # looking like the other locked fields, a grey box.
                        attrs = field.widget.attrs
                        attrs["class"] = (
                            attrs.get("class", "") + " oh-select--boxed-locked"
                        ).strip()
        self.initial["status"] = self.instance.status if self.instance.pk else "draft"

    def _tax_initial(self):
        """Yes or No to start at: the entry's own, else the standard for its type and employee."""
        from payroll.system_components import policy_fields, tax_field

        entry = self.instance
        if entry.pk and entry.tax_treatment is not None:
            return "true" if entry.tax_treatment else "false"
        key = entry.kind if entry.pk else "arrears"
        employee = entry.employee_id_id if entry.pk else None
        return (
            "true"
            if policy_fields(key, employee=employee).get(tax_field(key))
            else "false"
        )

    def tax_defaults(self):
        """
        What the tax setting should start at, as JSON for the page: for each type, the standard
        setting and each employee's exception to it. The page picks from it as the type and
        employee change, until the setting is chosen by hand.
        """
        import json

        from payroll.models.models import SystemComponentTaxOverride
        from payroll.system_components import policy_fields, tax_field

        defaults = {}
        for key in ("arrears", "recovery"):
            exceptions = SystemComponentTaxOverride.objects.filter(system_key=key)
            defaults[key] = {
                "standard": bool(policy_fields(key).get(tax_field(key))),
                "employees": {
                    str(employee): bool(value)
                    for employee, value in exceptions.values_list(
                        "employee_id_id", "value"
                    )
                },
            }
        return json.dumps(defaults)

    def clean_status(self):
        current = self.instance.status if self.instance.pk else "draft"
        return self.cleaned_data.get("status") or current

    def clean(self):
        cleaned = super().clean()
        if (
            self.instance.pk
            and self.instance.status == "approved"
            and cleaned.get("status") == "draft"
            and self.instance.is_paid()
        ):
            raise ValidationError(
                _("It Is Already On A Payslip, So This Cannot Go Back To Draft.")
            )
        if (
            self.instance.pk
            and self.instance.status == "approved"
            and cleaned.get("status") == "draft"
        ):
            # It becomes a draft with whatever was edited, so the new date has to be open too.
            day, employee = cleaned.get("pay_date"), cleaned.get("employee_id")
            if (
                day
                and employee
                and payroll.models.models.PayAdjustment._month_has_payslip(
                    employee, day
                )
            ):
                self.add_error(
                    "pay_date",
                    _("A Payslip Already Exists For %(month)s, So It Cannot Take This.")
                    % {"month": day.strftime("%B %Y")},
                )
        return cleaned

    def save(self, commit=True):
        """Save the entry, then confirm it or send it back to Draft when the status was changed."""
        instance = super().save(commit=commit)
        target = self.cleaned_data.get("status") or "draft"
        if commit and target != instance.status:
            if target == "approved":
                request = getattr(horilla_middlewares._thread_locals, "request", None)
                user = getattr(request, "user", None)
                instance.approve(approved_by=getattr(user, "employee_get", None))
            elif target == "draft" and instance.status == "approved":
                instance.revert()
        return instance


class PayAdjustmentBulkForm(forms.Form):
    """What the list's Update changes on the selected entries: anything left blank is left alone."""

    verbose_name = _("Bulk Update")
    # The modal's template shows "Save And Add Another" for a form with no saved record; an update
    # of existing records has none to add, so it is told it has one.
    instance = type("Existing", (), {"pk": "bulk"})()

    status = forms.ChoiceField(
        required=False,
        label=_("Status"),
        choices=[("", "---------")]
        + list(payroll.models.models.PayAdjustment.STATUS_CHOICES),
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        help_text=_(
            "Confirmed Makes The Pay Lines; Draft Takes Them Away, Unless A Payslip Carries Them."
        ),
    )
    taxable = forms.ChoiceField(
        required=False,
        label=_("Taxable (Arrears Only)"),
        choices=[("", "---------"), ("true", _("Yes")), ("false", _("No"))],
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        help_text=_(
            "Changes The Selected Arrears Entries; Recovery Entries Are Left As They Are. Drafts Only."
        ),
    )
    pre_tax = forms.ChoiceField(
        required=False,
        label=_("Pre-Tax (Recovery Only)"),
        choices=[("", "---------"), ("true", _("Yes")), ("false", _("No"))],
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        help_text=_(
            "Changes The Selected Recovery Entries; Arrears Entries Are Left As They Are. Drafts Only."
        ),
    )
    pay_date = forms.DateField(
        required=False,
        label=_("Pay Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
        help_text=_("Drafts Only. For A Month That Has No Payslip For The Employee."),
    )

    def changes(self):
        """The cleaned values as ``bulk_change`` takes them: ``None`` for what was left blank."""
        data = self.cleaned_data

        def yes_no(name):
            return None if not data.get(name) else data[name] == "true"

        return {
            "status": data.get("status") or None,
            "taxable": yes_no("taxable"),
            "pre_tax": yes_no("pre_tax"),
            "pay_date": data.get("pay_date"),
        }

    def clean(self):
        cleaned = super().clean()
        if not any(value not in (None, "") for value in cleaned.values()):
            raise ValidationError(_("Choose Something To Change."))
        return cleaned
