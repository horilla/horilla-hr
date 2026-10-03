"""
this page handles cbv of salary structure page
"""

from typing import Any

from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)
from payroll.filters import SalaryStructureFilter
from payroll.forms.component_forms import (
    AllowanceForm,
    DeductionForm,
    QuickAllowanceForm,
    QuickDeductionForm,
    SalaryStructureForm,
)
from payroll.models.models import Allowance, Deduction, SalaryStructure


def _reload_detail_view_script(structure_pk, request):
    """
    Script to refresh the salary structure Detail View sitting in
    #genericModalBody, for forms that are opened on top of it (in
    #relatedObjectModal) rather than opened directly into #genericModalBody.
    Without this, saving/duplicating from within the Detail View closes the
    top form but leaves the Detail View showing stale data underneath.
    """
    if request.META.get("HTTP_HX_TARGET") != "relatedObjectModalBody":
        return ""
    detail_url = reverse("salary-structure-detail-view", kwargs={"pk": structure_pk})
    return f"htmx.ajax('GET', '{detail_url}', {{target: '#genericModalBody'}});"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.view_salarystructure"), name="dispatch"
)
class SalaryStructureListView(HorillaListView):
    """
    list view of salary structures
    """

    model = SalaryStructure
    filter_class = SalaryStructureFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "salary_structure_id"
        self.search_url = reverse("salary-structure-list-view")
        if self.request.user.has_perm(
            "payroll.change_salarystructure"
        ) or self.request.user.has_perm("payroll.delete_salarystructure"):
            self.action_method = "get_salary_structure_actions"
        else:
            self.action_method = None

    columns = [
        (_("Title"), "title"),
        (_("Allowances"), "get_allowances_col"),
        (_("Deductions"), "get_deductions_col"),
        (_("Employees"), "get_employees_col"),
    ]

    sortby_mapping = [
        (_("Title"), "title"),
    ]

    row_attrs = """
                hx-get='{salary_structure_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.view_salarystructure"), name="dispatch"
)
class SalaryStructureNavView(HorillaNavView):
    """
    nav bar of the salary structure page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("salary-structure-list-view")

        if self.request.user.has_perm("payroll.add_salarystructure"):
            self.create_attrs = f"""
                                href="#"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-get="{reverse('create-salary-structure')}"
                                hx-target="#genericModalBody"
                                """

    nav_title = _("Salary Structures")
    filter_instance = SalaryStructureFilter()
    search_swap_target = "#structureContainer"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
class DynamicAllowanceCreateFormView(HorillaFormView):
    """
    Quick "create new allowance" form, opened from the Salary Structure
    form's allowances field.
    """

    model = Allowance
    form_class = QuickAllowanceForm
    new_display_title = _("Create Allowance")
    is_dynamic_create_view = True
    template_name = "payroll/allowance/quick_allowance_form.html"

    def form_valid(self, form: QuickAllowanceForm):
        if form.is_valid():
            form.save()
            messages.success(self.request, _("Allowance created"))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DynamicDeductionCreateFormView(HorillaFormView):
    """
    Quick "create new deduction" form, opened from the Salary Structure
    form's deductions field.
    """

    model = Deduction
    form_class = QuickDeductionForm
    new_display_title = _("Create Deduction")
    is_dynamic_create_view = True
    template_name = "payroll/deduction/quick_deduction_form.html"

    def form_valid(self, form: QuickDeductionForm):
        if form.is_valid():
            form.save()
            messages.success(self.request, _("Deduction created"))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class SalaryStructureFormView(HorillaFormView):
    """
    Create and edit form for salary structures, opened in the shared modal.
    """

    model = SalaryStructure
    form_class = SalaryStructureForm
    new_display_title = _("Create Salary Structure")
    # Its own template: the components are a checkbox table rather than two tag
    # boxes, because a tag box cannot say what a component pays or when.
    template_name = "payroll/salary_structure/structure_form.html"
    dynamic_create_fields = [
        ("allowances", DynamicAllowanceCreateFormView),
        ("deductions", DynamicDeductionCreateFormView),
    ]

    def dispatch(self, request, *args, **kwargs):
        perm = (
            "payroll.change_salarystructure"
            if kwargs.get("pk")
            else "payroll.add_salarystructure"
        )
        if not request.user.has_perm(perm):
            return render(request, "no_perm.html")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Salary Structure")

        from payroll.forms.component_layout import component_picker_rows

        # What is already ticked comes from the bound data on a redisplay, so a
        # failed save does not lose the selection, and from the instance
        # otherwise.
        if self.form.is_bound:
            selected_allowances = self.form.data.getlist("allowances")
            selected_deductions = self.form.data.getlist("deductions")
        elif self.form.instance.pk:
            selected_allowances = self.form.instance.allowances.values_list(
                "pk", flat=True
            )
            selected_deductions = self.form.instance.deductions.values_list(
                "pk", flat=True
            )
        else:
            selected_allowances = selected_deductions = []

        context["picker_rows"] = component_picker_rows(
            selected_allowances, selected_deductions
        )
        return context

    def form_valid(self, form: SalaryStructureForm):
        """
        Handle a valid form submission.
        """
        if form.is_valid():
            message = (
                _("Salary structure updated successfully")
                if form.instance.pk
                else _("Salary structure created successfully")
            )
            form.save()
            messages.success(self.request, message)
            script = _reload_detail_view_script(form.instance.pk, self.request)
            return self.HttpResponse(script=script)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.add_salarystructure"), name="dispatch"
)
class SalaryStructureFormDuplicate(HorillaFormView):
    """
    Duplicate form view for salary structures: pre-fills the title,
    allowances and deductions from an existing structure. Employees are
    intentionally left unassigned - they're tied to the original structure
    through their contract and shouldn't be moved just by duplicating it.
    """

    model = SalaryStructure
    form_class = SalaryStructureForm
    dynamic_create_fields = [
        ("allowances", DynamicAllowanceCreateFormView),
        ("deductions", DynamicDeductionCreateFormView),
    ]

    def get_context_data(self, **kwargs):
        """
        Reuse the framework's own instance-bound form (built by `get_form()`
        from the URL's pk) rather than constructing a separate one, so the
        allowances/deductions dynamic-create widgets stay wired up the same
        way the update form's do - only the title and employees are
        overridden for duplication.
        """
        context = super().get_context_data(**kwargs)
        form = self.get_form()
        form.initial["title"] = _("%(title)s (copy)") % {"title": form.instance.title}
        form.initial["employees"] = Employee.objects.none()
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate Salary Structure")
        return context

    def form_valid(self, form: SalaryStructureForm):
        """
        Ignore the instance-bound form the framework built from the URL's
        pk and save a brand new SalaryStructure from the submitted data.
        """
        form = self.form_class(self.request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                self.request, _("Salary structure duplicated successfully")
            )
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.view_salarystructure"), name="dispatch"
)
class SalaryStructureDetailView(HorillaDetailedView):
    """
    Detail view for a salary structure: the employees on it, then every
    component in the order the engine runs them, then a worked example.

    Allowances and deductions used to sit in two columns showing titles only.
    That hid the two things someone opening a structure actually wants: what
    each component works out to, and the single order they run in across both
    lists — which is what decides what a percentage or a formula may refer to.
    """

    model = SalaryStructure
    detail_view_url_name = "salary-structure-detail-view"
    detail_view_permission = "payroll.view_salarystructure"
    title = _("Salary Structure")

    header = {
        "title": "title",
        "subtitle": "",
        "avatar": "",
    }

    # One block, which renders its own summary bar and tabs. Three stacked
    # blocks put the employees list, a wide component table and an interactive
    # example in one vertical scroll, so reading any of them meant scrolling
    # the other two away.
    body = [
        (_("Structure"), "get_structure_detail_col", True),
    ]

    cols = {
        "get_structure_detail_col": 12,
    }

    # The body here is a long component list or an interactive example, so the
    # title row and the Edit / Delete / Duplicate row are pinned and only the
    # middle scrolls. Otherwise running an example scrolls its own actions off
    # the bottom and the structure's name off the top.
    sticky_chrome = True

    action_method = "salary_structure_detail_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.add_allowance"), name="dispatch")
class AllowanceDuplicateInStructureView(HorillaFormView):
    """
    Duplicate a single allowance from within a salary structure's detail
    view. Pre-fills every field as a copy (employee targeting cleared, since
    it should be re-targeted through the structure it lands on), and on save
    swaps the new copy into this structure in place of the original -
    e.g. keep the shared 500 Travel Allowance everywhere else, but give this
    one structure a 100 copy without touching the original allowance.
    """

    model = Allowance
    form_class = AllowanceForm
    template_name = "payroll/allowance/allowance_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = self.get_form()
        form.initial["title"] = _("%(title)s (copy)") % {"title": form.instance.title}
        form.initial["specific_employees"] = Employee.objects.none()
        form.initial["exclude_employees"] = Employee.objects.none()
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate Allowance")
        return context

    def form_valid(self, form: AllowanceForm):
        original = Allowance.objects.filter(pk=self.kwargs["pk"]).first()
        structure = SalaryStructure.objects.filter(
            pk=self.kwargs["structure_pk"]
        ).first()
        form = self.form_class(self.request.POST)
        if form.is_valid():
            # AllowanceForm.save() returns its MultipleCondition list, not
            # the Allowance - the saved instance lives on form.instance.
            form.save()
            new_allowance = form.instance
            if structure and original:
                structure.remove_allowance(original)
                structure.add_allowance(new_allowance)
            messages.success(self.request, _("Allowance duplicated successfully"))
            script = _reload_detail_view_script(
                self.kwargs["structure_pk"], self.request
            )
            return self.HttpResponse(script=script)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.add_deduction"), name="dispatch")
class DeductionDuplicateInStructureView(HorillaFormView):
    """
    Duplicate a single deduction from within a salary structure's detail
    view. Pre-fills every field as a copy, and on save swaps the new copy
    into this structure in place of the original.
    """

    model = Deduction
    form_class = DeductionForm
    template_name = "payroll/deduction/deduction_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = self.get_form()
        form.initial["title"] = _("%(title)s (copy)") % {"title": form.instance.title}
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate Deduction")
        return context

    def form_valid(self, form: DeductionForm):
        original = Deduction.objects.filter(pk=self.kwargs["pk"]).first()
        structure = SalaryStructure.objects.filter(
            pk=self.kwargs["structure_pk"]
        ).first()
        form = self.form_class(self.request.POST)
        if form.is_valid():
            # DeductionForm.save() returns its MultipleCondition list, not
            # the Deduction - the saved instance lives on form.instance.
            form.save()
            new_deduction = form.instance
            if structure and original:
                structure.remove_deduction(original)
                structure.add_deduction(new_deduction)
            messages.success(self.request, _("Deduction duplicated successfully"))
            script = _reload_detail_view_script(
                self.kwargs["structure_pk"], self.request
            )
            return self.HttpResponse(script=script)
        return super().form_valid(form)
