from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.urls import resolve, reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from employee.cbv.employee_profile import EmployeeProfileView
from employee.models import Employee
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from notifications.signals import notify
from pms.cbv.key_result import KeyResultFormView
from pms.filters import ActualObjectiveFilter, KeyResultFilter, ObjectiveFilter
from pms.forms import (
    AddAssigneesForm,
    EmployeeKeyResultForm,
    EmployeeObjectiveCreateForm,
    ObjectiveForm,
)
from pms.models import EmployeeKeyResult, EmployeeObjective, Objective


@method_decorator(login_required, name="dispatch")
class ObjectivesView(TemplateView):
    """
    for objectives page
    """

    template_name = "cbv/objectives/objectives.html"


@method_decorator(login_required, name="dispatch")
class ObjectiveTemplateView(TemplateView):
    """
    List-only template objective page
    """

    template_name = "cbv/objectives/objective_templates.html"


@method_decorator(login_required, name="dispatch")
class ObjectivesList(HorillaListView):
    """
    List view of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.template_only = False

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        archive_param = self.request.GET.get("archive")

        qs = super().get_queryset(queryset, filtered, *args, **kwargs)

        if self.template_only:
            qs = qs.filter(is_template=True)

        if archive_param in ["true", "True", "1"]:
            # only archived
            qs = qs.filter(archive=True)
        elif archive_param in ["false", "False", "0", "unknown"]:
            # include False and unknown (NULL)
            qs = qs.filter(Q(archive=False) | Q(archive__isnull=True))

        return qs

    model = Objective
    bulk_update_fields = [
        "self_employee_progress_update",
    ]
    filter_class = ActualObjectiveFilter

    columns = [
        (_("Title"), "title_col"),
        (_("Managers"), "manager_col"),
        (_("Key Results"), "key_res_col"),
        (_("Assignees"), "assingnees_col"),
        (_("Duration"), "duration_col"),
        (_("Description"), "description"),
    ]

    header_attrs = {
        "title_col": 'style="min-width:260px;width:28% !important;"',
        "manager_col": 'style="width:110px;max-width:130px;"',
        "key_res_col": 'style="width:110px;max-width:130px;"',
        "assingnees_col": 'style="width:110px;max-width:130px;"',
        "duration_col": 'style="width:100px;max-width:120px;"',
        "description": 'style="min-width:180px;width:22%;"',
        "action": 'style="width:160px;"',
    }
    row_attrs = """
                id="tr{get_instance_id}"
                class="oh-permission-table--collapsed cursor-pointer"
                hx-get="{get_individual_url}"
                hx-target="#listContainer"
                hx-swap="innerHTML"
                hx-push-url="{get_individual_url}"
                """

    # Mirrors ObjectivesNav.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Managers" and
    # "Assignees" are deliberately left out: they're ManyToManyFields, and
    # the nested engine's `values(*fields).annotate(Count("pk"))`
    # aggregate would fan out one row per related employee, double-
    # counting objectives with more than one manager/assignee.
    nested_group_by_fields = [
        ("title", _("Title")),
        ("duration_unit", _("Duration Unit")),
        ("duration", _("Duration")),
        ("is_template", _("Is Template")),
        ("archive", _("Is Archived")),
        ("company_id", _("Company")),
    ]


class MyObjectives(ObjectivesList):
    """
    My objectives class
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "myObjContainer"
        if self.request.user.has_perm(
            "pms.change_objective"
        ) or self.request.user.has_perm("pms.delete_objective"):
            self.action_method = "self_action_col"

    columns = (
        [
            col
            for col in ObjectivesList.columns
            if col[1] != "assingnees_col" and col[1] != "key_res_col"
        ][:2]
        + [(_("Key Results"), "self_key_res_col")]
        + [
            col
            for col in ObjectivesList.columns
            if col[1] != "assingnees_col" and col[1] != "key_res_col"
        ][2:]
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        queryset = queryset.filter(employee_objective__employee_id=employee)
        queryset = queryset.distinct()
        return queryset


@method_decorator(login_required, name="dispatch")
class AllObjectives(ObjectivesList):
    """
    List view of all objectives
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "allobjContainer"
        if self.request.user.has_perm(
            "pms.change_objective"
        ) or self.request.user.has_perm("pms.delete_objective"):
            self.action_method = "actions_col"

    selected_instances_key_id = "selectedInastacesAll"

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        manager = False
        if Objective.objects.filter(managers=employee).exists():
            manager = True
        if self.request.user.has_perm("pms.view_employeeobjective"):
            queryset = queryset
        elif manager:
            queryset = queryset.filter(Q(managers=employee)) | queryset.filter(
                employee_objective__employee_id=employee
            )
        else:
            queryset = queryset.none()
        return queryset.distinct()


@method_decorator(login_required, name="dispatch")
class ObjectiveTemplateList(AllObjectives):
    """
    List view dedicated for objective templates
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "objectiveTemplateContainer"
        self.search_url = reverse("list-objective-templates-view")
        self.template_only = True


@method_decorator(login_required, name="dispatch")
class ObjectivesTab(HorillaTabView):
    """
    Tab View
    """

    template_name = "cbv/objectives/extended_objectives.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "objContainer"

    def _assigned_objectives_count(self, employee):
        queryset = Objective.objects.filter(
            employee_objective__employee_id=employee
        ).distinct()
        return ActualObjectiveFilter(self.request.GET, queryset=queryset).qs.count()

    def _all_objectives_count(self, employee):
        queryset = Objective.objects.all()
        manager = Objective.objects.filter(managers=employee).exists()
        if self.request.user.has_perm("pms.view_employeeobjective"):
            queryset = queryset.distinct()
        elif manager:
            queryset = (
                queryset.filter(Q(managers=employee))
                | queryset.filter(employee_objective__employee_id=employee)
            ).distinct()
        else:
            return 0
        return ActualObjectiveFilter(self.request.GET, queryset=queryset).qs.count()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_get
        context["instance"] = employee
        template_mode = self.request.GET.get("objective_template") in (
            "true",
            "1",
            "True",
        )
        assigned_objectives_count = self._assigned_objectives_count(employee)
        all_objectives_count = self._all_objectives_count(employee)

        self.view_id = "objContainer"
        manager = False
        if Objective.objects.filter(managers=employee).exists():
            manager = True
        can_view_all = (
            self.request.user.has_perm("pms.view_employeeobjective") or manager
        )

        extra_params = self.request.GET.copy()
        extra_params.pop("view", None)
        query_string = extra_params.urlencode()

        def with_query(url):
            return f"{url}?{query_string}" if query_string else url

        all_objectives_tab = {
            "title": _("All Objectives"),
            "url": with_query(reverse("all-objectives-tab-shell")),
            "badge": all_objectives_count,
        }

        if template_mode:
            self.tabs = [all_objectives_tab] if can_view_all else []
        else:
            self.tabs = [
                {
                    "title": _("Assigned Objectives"),
                    "url": with_query(reverse("my-objectives-tab-shell")),
                    "badge": assigned_objectives_count,
                },
            ]
            if can_view_all:
                self.tabs.append(all_objectives_tab)

        context["tabs"] = self.tabs
        return context


class _ObjectivesTabNavBase(HorillaNavView):
    """
    Shared Search/Filter/Create wiring for each Objectives tab's own,
    independent Nav - only search_url/search_swap_target differ per tab.
    """

    nav_title = _("Objectives")
    filter_instance = ActualObjectiveFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/objectives/filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch, inherited by ObjectiveTemplateNav's
    # generic/inline_nav.html too) -- same treatment as every other
    # panel this session. ActualObjectiveFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.create_attrs = f"""
                        hx-get='{reverse_lazy('create-employee-objective')}'"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-target="#genericModalBody"
                        """
        if self.request.user.has_perm("pms.add_objective"):
            self.actions = [
                {
                    "action": _("Create Objectives"),
                    "attrs": f"""
                        hx-get='{reverse_lazy('objective-creation')}'"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-target="#genericModalBody"
                        style="cursor: pointer;"
                        """,
                }
            ]

    # Mirrors ObjectivesList.nested_group_by_fields
    nested_group_by_fields = [
        ("title", _("Title")),
        ("duration_unit", _("Duration Unit")),
        ("duration", _("Duration")),
        ("is_template", _("Is Template")),
        ("archive", _("Is Archived")),
        ("company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class MyObjectivesNav(_ObjectivesTabNavBase):
    """
    Independent Nav for the Assigned Objectives tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-objectives-view-tab")
        self.search_swap_target = "#myObjectivesListContainer"


@method_decorator(login_required, name="dispatch")
class AllObjectivesNav(_ObjectivesTabNavBase):
    """
    Independent Nav for the All Objectives tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("all-objectives-view-tab")
        self.search_swap_target = "#allObjectivesListContainer"


class MyObjectivesTabShell(AttendanceTabContentShell):
    nav_url_name = "my-objectives-nav"
    container_id = "myObjectivesListContainer"
    tabs_root_id = "objContainer"


class AllObjectivesTabShell(AttendanceTabContentShell):
    nav_url_name = "all-objectives-nav"
    container_id = "allObjectivesListContainer"
    tabs_root_id = "objContainer"


@method_decorator(login_required, name="dispatch")
class ObjectiveTemplateNav(_ObjectivesTabNavBase):
    """
    Nav bar for objective template list page
    """

    nav_title = _("Objective Templates")
    template_name = "generic/inline_nav.html"
    search_swap_target = "#listContainer"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-objective-templates-view")
        if self.request.user.has_perm("pms.add_objective"):
            self.create_attrs = f"""
                            hx-get='{reverse_lazy('objective-template-creation')}'"
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            """
        else:
            self.create_attrs = ""


@method_decorator(login_required, name="dispatch")
class DynamicKeyResultCreateForm(KeyResultFormView):

    is_dynamic_create_view = True


@method_decorator(login_required, name="dispatch")
class CreateEmployeeObjectiveForm(HorillaFormView):
    """
    form view for create employee objective
    """

    form_class = EmployeeObjectiveCreateForm
    model = EmployeeObjective
    new_display_title = _("Create Employee Objective")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = resolve(self.request.path_info).kwargs.get("pk")
        if not pk:
            self.dynamic_create_fields = [("key_result_id", DynamicKeyResultCreateForm)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Employee Objective")
        return context

    def form_valid(self, form: EmployeeObjectiveCreateForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Employee objective Updated successfully")
                form.save()
            else:
                message = _("Employee objective created successfully")
                krs = list(form.cleaned_data["key_result_id"])
                emp_obj = form.save(commit=False)
                obj = emp_obj.objective_id
                obj.assignees.add(emp_obj.employee_id)
                krs.extend([key_result for key_result in obj.key_result_id.all()])
                set_krs = set(krs)
                emp_obj.save()
                for kr in set_krs:
                    emp_obj.key_result_id.add(kr)
                    if not EmployeeKeyResult.objects.filter(
                        employee_objective_id=emp_obj, key_result_id=kr
                    ).exists():
                        emp_kr = EmployeeKeyResult.objects.create(
                            employee_objective_id=emp_obj,
                            key_result_id=kr,
                            progress_type=kr.progress_type,
                            target_value=kr.target_value,
                            start_date=emp_obj.start_date,
                        )
                        emp_kr.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class CreateObjectiveFormView(HorillaFormView):
    """
    form view for create objectives
    """

    form_class = ObjectiveForm
    model = Objective
    new_display_title = _("Create  Objective")
    dynamic_create_fields = [("key_result_id", DynamicKeyResultCreateForm)]
    template_name = "cbv/objectives/form.html"
    force_template = False
    create_message = _("Objective created successfully")
    update_message = _("Objective updated successfully")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "objectiveForm"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form.fields["assignees"].initial = self.form.instance.assignees.all()
            self.form_class.verbose_name = _("Update Objective")
        return context

    def form_valid(self, form: ObjectiveForm) -> HttpResponse:
        if form.is_valid():
            if self.force_template:
                form.instance.is_template = True
            is_new = not form.instance.pk
            objective = form.save()
            assignees = self.form.cleaned_data["assignees"]
            start_date = self.form.cleaned_data["start_date"]
            default_krs = self.form.cleaned_data["key_result_id"]
            if not is_new:
                message = self.update_message
                new_emp = [assignee for assignee in assignees]
                delete_list = []
                if objective.employee_objective.exists():
                    emp_objectives = objective.employee_objective.all()
                    existing_emp = [emp.employee_id for emp in emp_objectives]
                    delete_list = [
                        employee for employee in existing_emp if employee not in new_emp
                    ]
                if len(delete_list) > 0:
                    for emp in delete_list:
                        EmployeeObjective.objects.filter(
                            employee_id=emp, objective_id=objective
                        ).delete()
                for emp in new_emp:
                    if EmployeeObjective.objects.filter(
                        employee_id=emp, objective_id=objective
                    ).exists():
                        emp_obj = EmployeeObjective.objects.filter(
                            employee_id=emp, objective_id=objective
                        ).first()
                        emp_obj.start_date = start_date
                    else:
                        emp_obj = EmployeeObjective(
                            employee_id=emp,
                            objective_id=objective,
                            start_date=start_date,
                        )
                    emp_obj.save()
                    emp_obj.key_result_id.set(default_krs)
                    # assiging default key result
                    if default_krs:
                        for key in default_krs:
                            if not EmployeeKeyResult.objects.filter(
                                employee_objective_id=emp_obj, key_result_id=key
                            ).exists():
                                emp_kr = EmployeeKeyResult.objects.create(
                                    employee_objective_id=emp_obj,
                                    key_result_id=key,
                                    progress_type=key.progress_type,
                                    target_value=key.target_value,
                                    start_date=start_date,
                                )
                                emp_kr.save()
                    notify.send(
                        self.request.user.employee_get,
                        recipient=emp.employee_user_id,
                        verb="You got an OKR!.",
                        verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                        verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                        verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                        verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                        redirect=reverse(
                            "objective-detailed-view", kwargs={"obj_id": objective.id}
                        ),
                    )
            else:
                message = self.create_message
                if assignees:
                    for emp in assignees:
                        emp_objective = EmployeeObjective(
                            objective_id=objective,
                            employee_id=emp,
                            start_date=start_date,
                        )
                        emp_objective.save()
                        # assigning default key result
                        if default_krs:
                            for key in default_krs:
                                emp_kr = EmployeeKeyResult(
                                    employee_objective_id=emp_objective,
                                    key_result_id=key,
                                    progress_type=key.progress_type,
                                    target_value=key.target_value,
                                    start_date=start_date,
                                )
                                emp_kr.save()
                        notify.send(
                            self.request.user.employee_get,
                            recipient=emp.employee_user_id,
                            verb="You got an OKR!.",
                            verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                            verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                            verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                            verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                            redirect=reverse(
                                "objective-detailed-view",
                                kwargs={"obj_id": objective.id},
                            ),
                        )
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class CreateTemplateObjectiveFormView(CreateObjectiveFormView):
    """
    Objective template create/update form view
    """

    force_template = True
    new_display_title = _("Create Objective Template")
    create_message = _("Objective template created successfully")
    update_message = _("Objective template updated successfully")

    def dispatch(self, request, *args, **kwargs):
        pk = resolve(request.path_info).kwargs.get("pk")
        required_perm = "pms.change_objective" if pk else "pms.add_objective"
        if not request.user.has_perm(required_perm):
            messages.info(
                request, _("You don't have permission to perform this action")
            )
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class AddAssigneesFormView(HorillaFormView):
    """
    form view for add assignees
    """

    form_class = AddAssigneesForm
    model = Objective
    new_display_title = _("Add assignees")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Add assignees")
        return context

    def dispatch(self, request, *args, **kwargs):
        obj_id = kwargs.get("pk")

        if not obj_id:
            return HorillaRedirect(request, message=_("Objective ID is missing"))

        self.object = Objective.objects.filter(pk=obj_id).first()

        if not self.object:
            return HorillaRedirect(request, message=_("Invalid Objective"))

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: AddAssigneesForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _(f"{form.instance} Updated")
                objective = form.save(commit=False)
                assignees = form.cleaned_data["assignees"]
                start_date = form.cleaned_data["start_date"]
                for emp in assignees:
                    objective.assignees.add(emp)
                    if not EmployeeObjective.objects.filter(
                        employee_id=emp, objective_id=objective
                    ).exists():
                        emp_obj = EmployeeObjective(
                            employee_id=emp,
                            objective_id=objective,
                            start_date=start_date,
                        )
                        emp_obj.save()
                    # assiging default key result
                    default_krs = objective.key_result_id.all()
                    emp_obj.key_result_id.set(default_krs)
                    if default_krs:
                        for key_result in default_krs:
                            if not EmployeeKeyResult.objects.filter(
                                employee_objective_id=emp_obj, key_result_id=key_result
                            ).exists():
                                emp_kr = EmployeeKeyResult.objects.create(
                                    employee_objective_id=emp_obj,
                                    key_result_id=key_result,
                                    progress_type=key_result.progress_type,
                                    target_value=key_result.target_value,
                                    start_date=start_date,
                                )
                                emp_kr.save()
                    notify.send(
                        self.request.user.employee_get,
                        recipient=emp.employee_user_id,
                        verb="You got an OKR!.",
                        verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                        verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                        verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                        verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                        redirect=reverse(
                            "objective-detailed-view", kwargs={"obj_id": objective.id}
                        ),
                    )
                objective.save()
                messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class CreateEmployeeKeyResultFormView(HorillaFormView):
    """
    form view for create employee key result form
    """

    form_class = EmployeeKeyResultForm
    model = EmployeeKeyResult
    new_display_title = _("Create Key result")
    dynamic_create_fields = [("key_result_id", DynamicKeyResultCreateForm)]
    view_id = "empKeyrsult"

    def dispatch(self, request, *args, **kwargs):
        emp_obj_id = kwargs.get("emp_obj_id")
        pk = kwargs.get("pk")

        if emp_obj_id:
            self.emp_objective = EmployeeObjective.find(emp_obj_id)
        elif pk:
            key_result = EmployeeKeyResult.objects.filter(pk=pk).first()
            self.emp_objective = (
                key_result.employee_objective_id if key_result else None
            )
        else:
            self.emp_objective = None

        if (emp_obj_id or pk) and not self.emp_objective:
            messages.error(request, _("Employee objective not found."))
            return HorillaRedirect(request)

        if not self.has_key_result_permission():
            messages.info(request, _("You dont have permission"))
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def has_key_result_permission(self):
        """
        Only users with objective/key result change permission or the
        objective's managers can create/update an employee key result.
        """

        if (
            self.request.user.has_perm("pms.change_objective")
            or self.request.user.has_perm("pms.change_employeeobjective")
            or self.request.user.has_perm("pms.change_employeekeyresult")
        ):
            return True
        if not self.emp_objective:
            return False
        return (
            self.request.user.employee_get
            in self.emp_objective.objective_id.managers.all()
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        emp_obj_id = self.kwargs.get("emp_obj_id")
        kwargs["emp_objective"] = EmployeeObjective.objects.get(id=emp_obj_id)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.form.instance.pk:
            employee = self.emp_objective.employee_id
            self.form.fields["employee_objective_id"].initial = self.emp_objective.pk
            self.form_class.verbose_name = _(f"Create Key result for {employee}")
        if self.form.instance.pk:
            self.form_class.verbose_name = _(
                f"Update Key result for {self.form.instance}"
            )
        return context

    def form_valid(self, form: EmployeeKeyResultForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Key result updated sucessfully.")
                employee = self.form.instance.employee_objective_id.employee_id
                self.form.instance.employee_objective_id.update_objective_progress()
                form.save()
                notify.send(
                    self.request.user.employee_get,
                    recipient=employee.employee_user_id,
                    verb="Your Key Result updated.",
                    verb_ar="تم تحديث نتيجتك الرئيسية.",
                    verb_de="Ihr Schlüsselergebnis wurde aktualisiert.",
                    verb_es="Se ha actualizado su Resultado Clave.",
                    verb_fr="Votre Résultat Clé a été mis à jour.",
                    redirect=reverse(
                        "objective-detailed-view",
                        kwargs={
                            "obj_id": self.form.instance.employee_objective_id.objective_id.id
                        },
                    ),
                )
            else:
                message = _("Key result assigned sucessfully.")
                emp_obj_id = self.kwargs.get("emp_obj_id")
                emp_objective = EmployeeObjective.objects.get(id=emp_obj_id)
                employee = emp_objective.employee_id
                emp_objective.update_objective_progress()
                key_result = self.form.cleaned_data["key_result_id"]
                emp_objective.key_result_id.add(key_result)
                form.save()
                notify.send(
                    self.request.user.employee_get,
                    recipient=employee.employee_user_id,
                    verb="You got an Key Result!.",
                    verb_ar="لقد حصلت على نتيجة رئيسية!",
                    verb_de="Du hast ein Schlüsselergebnis erreicht!",
                    verb_es="¡Has conseguido un Resultado Clave!",
                    verb_fr="Vous avez obtenu un Résultat Clé!",
                    redirect=reverse(
                        "objective-detailed-view",
                        kwargs={"obj_id": emp_objective.objective_id.id},
                    ),
                )
            messages.success(self.request, _(message))
            return self.HttpResponse("<script>window.location.reload()</script>")
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class EmployeeObjectiveDetailView(HorillaDetailedView):
    """
    Generic Detail view of page
    """

    model = EmployeeObjective

    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "objective_detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    body = [
        (_("Title"), "objective_id__title"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Status"), "status_col"),
        (_("Description"), "objective_id__description"),
    ]

    action_method = "emp_obj_action"

    cols = {"objective_id__description": 12}


def get_history_url(self):
    """
    History url
    """
    return reverse("ekr-history", kwargs={"pk": self.pk})


EmployeeKeyResult.get_history_url = get_history_url


@method_decorator(login_required, name="dispatch")
class EmployeeObjectiveKeyResultDetailListView(HorillaListView):
    """
    List view of the page
    """

    model = EmployeeKeyResult
    filter_class = KeyResultFilter
    columns = [
        (_("Title"), "title_col"),
        (_("Start Value"), "start_value"),
        (_("Current Value"), "get_current_value_col"),
        (_("Target Value"), "target_value"),
        (_("Progress Percentage"), "get_progress_col"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Status"), "status_col"),
    ]
    filter_selected = False
    show_filter_tags = False
    custom_empty_template = "cbv/objectives/compact_empty.html"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_instances_key_id = (
            f'ekrIds{self.request.GET.get("employee_objective_id")}'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.search_url = self.request.path
        emp_objective = EmployeeObjective.objects.filter(
            pk=self.request.GET.get("employee_objective_id")
        ).first()

        self.actions = []
        if (
            self.request.user.has_perm("pms.change_objective")
            or self.request.user.has_perm("pms.change_employeeobjective")
            or self.request.user.has_perm("pms.change_employeekeyresult")
            or self.request.user.employee_get
            in emp_objective.objective_id.managers.all()
        ):
            self.actions.append(
                {
                    "action": _("Edit"),
                    "icon": "create-outline",
                    "attrs": """
                    hx-get='{get_update_url}'
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                    """,
                },
            )
        delete_confirm = _("Are you sure you want to delete	this Key result?")
        if self.request.user.has_perm("pms.delete_employeekeyresult"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "icon": "trash-outline",
                    "attrs": f"""
                        hx-get='{{get_delete_url}}'
                        hx-confirm="{delete_confirm}"
                        hx-swap="none"
                        class="oh-btn oh-btn--danger oh-btn--sq-sm"
                        hx-on-htmx-after-request= "window.location.reload();"
                        style="cursor: pointer;"
                    """,
                }
            )

        if (
            emp_objective
            and self.request.user.employee_get
            in emp_objective.objective_id.managers.all()
            or self.request.user.has_perm("pms.view_employeekeyresult")
        ):
            self.actions.append(
                {
                    "action": _("History"),
                    "icon": "time-outline",
                    "attrs": """
                hx-get='{get_history_url}'
                hx-target="#genericOffCanvas"
                data-target='#genericSidebar'
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm oh-activity-sidebar__open"
                style="cursor: pointer;"
                """,
                }
            )

        context["actions"] = self.actions
        return context

    header_attrs = {
        "title_col": """
                      style="width:200px !important;"
                      """,
        "action": """
            style="width:180px !important;"
        """,
    }
    row_attrs = """
                class = "oh-employee-okr-row"
                data-kr-id = "{get_instance_id}"
                """

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        """
        Get querysetmethod
        """
        self.queryset = (
            super()
            .get_queryset(queryset, filtered, *args, **kwargs)
            .filter(employee_objective_id=self.kwargs["emp_objective_id"])
        )
        return self.queryset


@method_decorator(login_required, name="dispatch")
class EKRTab(EmployeeObjectiveKeyResultDetailListView):
    """
    EKR tab
    """

    columns = [
        (_("Title"), "title_col"),
        (_("Objective"), "employee_objective_id__objective_id__title"),
        (_("Start Value"), "start_value"),
        (_("Current Value"), "current_value"),
        (_("Target Value"), "target_value"),
        (_("Progress Percentage"), "get_progress_col"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Status"), "status"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_instances_key_id = "selectedInstanceIds"

    filter_selected = False

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        self.queryset = HorillaListView.get_queryset(
            self, queryset, filtered, *args, **kwargs
        ).filter(employee_objective_id__employee_id__pk=self.kwargs["pk"])
        self._saved_filters = self._saved_filters.copy()
        self._saved_filters["field"] = "employee_objective_id"
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["compact_group_pagination"] = True
        return context


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Key Results"),
            "view": EKRTab.as_view(),
            "accessibility": "pms.cbv.accessibility.performance_accessibility",
        },
    ]
)
