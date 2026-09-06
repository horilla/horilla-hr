"""
filters.py

This page is used to register filter for employee models

"""

import django
import django_filters
from django import forms
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django_filters import CharFilter

# from attendance.models import Attendance
from accessibility.methods import check_is_accessible
from base.methods import filtersubordinatesemployeemodel
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import (
    Actiontype,
    DisciplinaryAction,
    Employee,
    EmployeeTag,
    EmployeeWorkInformation,
    Policy,
)
from horilla.filters import (
    FilterSet,
    HorillaFilterSet,
    filter_by_name,
    filter_name_or_badge_terms,
)
from horilla.horilla_middlewares import _thread_locals
from horilla_documents.models import Document, DocumentRequest
from horilla_views.templatetags.generic_template_filters import getattribute
from horilla_widgets.generic_ajax import register_ajax_field


class EmployeeFilter(HorillaFilterSet):
    """
    Filter set class for Candidate model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    search = django_filters.CharFilter(method="filter_by_name")
    search_field = django_filters.CharFilter(method="search_in")
    selected_search_field = django_filters.ChoiceFilter(
        label="Search Field",
        choices=[
            ("employee", _("Search in : Employee")),
            ("reporting_manager", _("Search in : Reporting manager")),
            ("department", _("Search in : Department")),
            ("job_position", _("Search in : Job Position")),
        ],
        method="filter_by_name_and_field",
        widget=forms.Select(
            attrs={
                "size": 4,
                "class": "oh-input__icon",
                "style": "border: none; overflow: hidden; display: flex; position: absolute; z-index: 999; margin-left:8%;",
                "onclick": "$('.filterButton')[0].click();",
            }
        ),
    )
    employee_first_name = django_filters.CharFilter(lookup_expr="icontains")
    employee_last_name = django_filters.CharFilter(lookup_expr="icontains")

    # Modern filter panel's single "Employee" search box (filter_employee.html)
    # -- replaces separate First Name / Last Name inputs with one field that
    # matches name (either first or last) or Badge ID, and accepts several
    # comma-separated terms at once (e.g. "PEP01, PEP02, jane" matches any
    # employee whose name or badge matches ANY one of those terms).
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )
    # AJAX-searched "pick specific employee(s)" combobox (see ajax_fields
    # below) -- employee_filters.html's Employee section (First/Last
    # Name, Email, Phone, Country, Gender) for the classic filter
    # dropdowns. field_name="id" since this filters the Employee model
    # itself by primary key, not a related field.
    employee_id = django_filters.ModelMultipleChoiceFilter(
        field_name="id",
        queryset=Employee.objects.all(),
        label=_("Employee"),
    )
    country = django_filters.CharFilter(lookup_expr="icontains")
    department = django_filters.CharFilter(
        field_name="employee_work_info__department_id__department",
        lookup_expr="icontains",
    )

    # Shift and Employee Tag are AJAX-loaded combos (see ajax_fields
    # below), not part of the Advanced custom-filter picker anymore --
    # commonly-used-enough to warrant their own dedicated fields, same
    # reasoning as Groups earlier.
    employee_work_info__shift_id = django_filters.ModelMultipleChoiceFilter(
        field_name="employee_work_info__shift_id",
        queryset=EmployeeShift.objects.all(),
        label=_("Shift"),
    )
    employee_work_info__tags = django_filters.ModelMultipleChoiceFilter(
        field_name="employee_work_info__tags",
        queryset=EmployeeTag.objects.all(),
        label=_("Employee Tag"),
    )

    employee_user_id__user_permissions = django_filters.ModelMultipleChoiceFilter(
        queryset=Permission.objects.select_related("content_type").all(),
        label=_("Permissions"),
    )

    # Groups is an AJAX-loaded combobox (see ajax_fields below), not a
    # checkbox list -- ModelMultipleChoiceFilter still needed here only
    # to give it its own label, same as it would auto-generate from
    # Meta.fields otherwise.
    employee_user_id__groups = django_filters.ModelMultipleChoiceFilter(
        queryset=Group.objects.all(),
        label=_("Groups"),
    )

    # Department/Job Position are AJAX-loaded combos (see ajax_fields
    # below), not checkbox lists -- ModelMultipleChoiceFilter still
    # needed here only for their labels/field_name, same as it would
    # auto-generate from Meta.fields otherwise. Checkbox lists are
    # reserved for genuine choice fields (fixed, non-model option sets,
    # e.g. Is Active) -- every model/queryset-backed field uses the same
    # AJAX combobox for consistency, regardless of its current option
    # count.
    employee_work_info__department_id = django_filters.ModelMultipleChoiceFilter(
        field_name="employee_work_info__department_id",
        queryset=Department.objects.all(),
        label=_("Department"),
    )
    employee_work_info__job_position_id = django_filters.ModelMultipleChoiceFilter(
        field_name="employee_work_info__job_position_id",
        queryset=JobPosition.objects.all(),
        label=_("Job Position"),
    )

    is_active = django_filters.ChoiceFilter(
        field_name="is_active",
        label="Is Active",
        # Segmented Any/Yes/No toggle in the modern filter panel -- the
        # empty leading choice (rendered as "Any") is what lets the field
        # be cleared back to unfiltered; a plain 2-choice Yes/No couldn't
        # express that. (ChoiceField copies THIS list onto the widget in
        # __init__, so it has to live here, not just on widget=... below,
        # or it gets overwritten back to whatever's passed here anyway.)
        choices=[
            ("", _("Any")),
            (True, "Yes"),
            (False, "No"),
        ],
        # ChoiceFilter prepends its OWN blank "---------" choice by default
        # (from FILTERS_EMPTY_CHOICE_LABEL) -- without this, that shows up
        # as a second, redundant empty-value radio alongside the "Any"
        # option declared above.
        empty_label=None,
        initial=True,
        widget=forms.RadioSelect,
    )

    is_from_onboarding = django_filters.ChoiceFilter(
        field_name="is_from_onboarding",
        label="Is From Onboarding",
        choices=[
            (True, "Yes"),
            (False, "No"),
        ],
    )
    is_directly_converted = django_filters.ChoiceFilter(
        field_name="is_directly_converted",
        label="Is Directly Converted",
        choices=[
            (True, "Yes"),
            (False, "No"),
        ],
    )
    probation_from = django_filters.DateFilter(
        field_name="candidate_get__probation_end",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_till = django_filters.DateFilter(
        field_name="candidate_get__probation_end",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # working_today = django_filters.BooleanFilter(
    #     label="Working", method="get_working_today"
    # )

    not_in_yet = django_filters.DateFilter(
        method="not_in_yet_func",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    not_out_yet = django_filters.DateFilter(
        method="not_out_yet_func",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Employee
        fields = [
            "employee_first_name",
            "employee_last_name",
            "email",
            "badge_id",
            "phone",
            "country",
            "gender",
            "is_active",
            "employee_work_info__job_position_id",
            "employee_work_info__department_id",
            "department",
            "employee_work_info__work_type_id",
            "employee_work_info__employee_type_id",
            "employee_work_info__job_role_id",
            "employee_work_info__reporting_manager_id",
            "employee_work_info__company_id",
            "employee_work_info__shift_id",
            "employee_work_info__tags",
            "employee_user_id__groups",
            "employee_user_id__user_permissions",
        ]

    # Model-backed "choice" custom-filter fields (Work Type, Employee Type,
    # Job Role) -- unlike Gender (a genuinely fixed option set), these back
    # onto a real queryset, so they go through the same generic AJAX-search
    # endpoint as the dedicated fields above (horilla_widgets.generic_ajax)
    # rather than pre-rendering every row as an <option> on every filter
    # panel load. Registered here (not via HorillaFilterSet.ajax_fields)
    # because these have no corresponding declared form field to swap a
    # widget onto -- they're pure client-built <select> elements driven by
    # custom_filter_fields JSON, so this dict is both the AJAX registration
    # source (see _build_custom_filter_fields) and, via queryset_fn/
    # display_fn, how _extract_custom_filter_rows resolves a previously
    # applied value's label for the restored row (see there).
    CUSTOM_FILTER_AJAX_FIELDS = {
        "work_type": {
            "key": "employee-custom-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
        "employee_type": {
            "key": "employee-custom-employee-type",
            "queryset_fn": lambda request: EmployeeType.objects.all(),
            "display_fn": lambda obj: obj.employee_type,
            "search_fields": ["employee_type"],
            "placeholder": _("Select employee type..."),
        },
        "job_role": {
            "key": "employee-custom-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
    }

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in this form (Company,
    # Reporting Manager, Department, Job Position, Groups, Permissions)
    # opts in here, regardless of current option count. Checkbox lists
    # are reserved for genuine choice fields instead (a fixed, non-model
    # option set, e.g. Is Active) -- a different widget entirely (every
    # option always visible, not a dropdown), which this doesn't apply
    # to.
    #
    # This previously broke identically for a real user across the first
    # four of these fields (unstyled, empty, no options) despite
    # surviving every reproduction attempted here -- root cause turned
    # out to be a stale browser-cached copy of htmxSelect2.js (WhiteNoise
    # doesn't content-hash this URL), not an actual bug in this
    # mechanism. Fixed via the `?v=` cache-busting query string on that
    # script tag in footer_scripts.html (bump it by hand whenever that
    # file changes).
    ajax_fields = {
        "employee_id": {
            "key": "employee-picker",
            "queryset_fn": lambda request: Employee.objects.all(),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": [
                "employee_first_name",
                "employee_last_name",
                "badge_id",
            ],
            "placeholder": _("Search employee..."),
        },
        "employee_work_info__company_id": {
            "key": "employee-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_work_info__reporting_manager_id": {
            "key": "employee-reporting-manager",
            "queryset_fn": lambda request: filtersubordinatesemployeemodel(
                request,
                Employee.objects.filter(is_active=True),
                "employee.view_employee",
            ),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": [
                "employee_first_name",
                "employee_last_name",
                "badge_id",
            ],
            "placeholder": _("Search employee..."),
        },
        "employee_user_id__groups": {
            "key": "employee-groups",
            "queryset_fn": lambda request: Group.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": _("Select groups..."),
        },
        "employee_work_info__shift_id": {
            "key": "employee-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "employee_work_info__work_type_id": {
            "key": "employee-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
        "employee_work_info__tags": {
            "key": "employee-tag",
            "queryset_fn": lambda request: EmployeeTag.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select employee tag..."),
        },
        "employee_work_info__department_id": {
            "key": "employee-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_work_info__job_position_id": {
            "key": "employee-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_user_id__user_permissions": {
            "key": "employee-permissions",
            "queryset_fn": lambda request: Permission.objects.select_related(
                "content_type"
            ).all(),
            "display_fn": lambda obj: (
                f"{obj.content_type.app_label} | {obj.content_type.name} | {obj.name}"
            ),
            "search_fields": [
                "name",
                "codename",
                "content_type__app_label",
                "content_type__model",
            ],
            "placeholder": _("Select permissions..."),
            "permission": "employee.view_employee",
        },
    }

    def __init__(self, *args, **kwargs):
        # custom_filter_fields/custom_filter_rows are built by
        # HorillaFilterSet.__init__ itself (via this class's own
        # _build_custom_filter_fields override below) -- the "choice"
        # fields' option lists are small live querysets (Shift, Work
        # Type, ...), scoped the same way as everywhere else in the app
        # (HorillaCompanyManager via the current request/company), which
        # is exactly why that base __init__ builds this fresh per
        # request instead of it being a class-level constant.
        super().__init__(*args, **kwargs)
        self._apply_ajax_selects()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder --
        fields that used to have their own permanent input (Phone,
        Country, Gender, Work Type) but were moved out of the default
        layout since they're filtered on far less often than Name/Email/
        Department/Job Position/Reporting Manager/Company/Is Active/
        Groups/Permissions/Shift/Employee Tag. Every one of them stays
        fully reachable, just through a picker instead of a dedicated
        box. Employee Type and Job Role are declared on Meta.fields but
        never had ANY dedicated input anywhere in the form -- added here
        rather than left unreachable.

        Work Type/Employee Type/Job Role are model-backed, so they carry
        an "ajax" sub-dict (see CUSTOM_FILTER_AJAX_FIELDS) instead of a
        "choices" list -- the client builds an AJAX-searched combobox for
        these instead of pre-rendering every row as an <option>. Gender
        stays a plain "choices" list since it's a genuinely fixed option
        set, not a queryset.

        Consumed generically by HorillaNavView (as context
        "custom_filter_fields") and rendered by filter_employee.html;
        applied server-side by _apply_custom_filters below.
        """
        fields = [
            {
                "key": "phone",
                "field": "phone",
                "label": str(_("Phone")),
                "type": "text",
            },
            {
                "key": "country",
                "field": "country",
                "label": str(_("Country")),
                "type": "text",
            },
            {
                "key": "gender",
                "field": "gender",
                "label": str(_("Gender")),
                "type": "choice",
                "choices": [[v, str(l)] for v, l in Employee.choice_gender],
            },
            {
                "key": "work_type",
                "field": "employee_work_info__work_type_id",
                "label": str(_("Work Type")),
                "type": "choice",
            },
            {
                "key": "employee_type",
                "field": "employee_work_info__employee_type_id",
                "label": str(_("Employee Type")),
                "type": "choice",
            },
            {
                "key": "job_role",
                "field": "employee_work_info__job_role_id",
                "label": str(_("Job Role")),
                "type": "choice",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
            ajax_config = self.CUSTOM_FILTER_AJAX_FIELDS.get(entry["key"])
            if ajax_config:
                register_ajax_field(
                    ajax_config["key"],
                    ajax_config["queryset_fn"],
                    ajax_config["display_fn"],
                    ajax_config["search_fields"],
                )
                entry["ajax"] = {
                    # reverse_lazy, not reverse: this can run at class-body
                    # time (EmployeeNav.filter_instance = EmployeeFilter(),
                    # in employee/cbv/employees.py) while horilla/urls.py
                    # is still mid-import -- resolving now would deadlock
                    # as a circular import. json_script's DjangoJSONEncoder
                    # stringifies this lazily-resolved value correctly
                    # (handles Promise the same way it already does for
                    # every str(_(...)) label above), so this only ever
                    # actually resolves at real per-request render time,
                    # same reasoning as HorillaFilterSet._apply_ajax_fields.
                    "url": reverse_lazy(
                        "horilla-ajax-choices", args=[ajax_config["key"]]
                    ),
                    "placeholder": str(ajax_config["placeholder"]),
                }
        return fields

    def _apply_ajax_selects(self):
        """
        Fixes up the "Name or Badge ID" placeholder: horilla.filters.
        FilterSet.__init__ (the base class, already run via
        super().__init__() above) unconditionally overwrites every
        TextInput's native "placeholder" attr with the field's label, so
        a custom one set on the widget itself never survives -- it has
        to be (re-)applied here, after that loop has already run.

        Every model-choice <select> in this form (Company, Reporting
        Manager, Groups, Permissions) is an AJAX-loaded combobox handled
        generically by HorillaFilterSet.ajax_fields (see the class
        attribute above) -- no per-field code is needed here for those.
        """
        name_or_badge_field = self.form.fields.get("name_or_badge")
        if name_or_badge_field is not None:
            name_or_badge_field.widget.attrs["placeholder"] = _(
                "e.g. John, PEP01, PEP02"
            )

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     custom_field = django_filters.BooleanFilter(
    #         label="Working", method=get_working_today
    #     )
    #     self.filters["working_today"] = custom_field
    #     self.form.fields["working_today"] = custom_field.field
    #     self.form.fields["working_today"].label = "Working"
    #     self.Meta.fields.append("working_today")

    def not_in_yet_func(self, queryset, _, value):
        """
        The method to filter out the not check-in yet employees
        """

        # Getting the queryset for those employees dont have any attendance for the date
        # in value.

        queryset1 = queryset.exclude(
            employee_attendances__attendance_date=value,
        )
        queryset2 = queryset.filter(
            employee_attendances__attendance_date=value,
            employee_attendances__attendance_clock_out__isnull=False,
        )

        queryset = (queryset1 | queryset2).distinct()

        return queryset

    def not_out_yet_func(self, queryset, _, value):
        """
        The method to filter out the not check-in yet employees
        """

        # Getting the queryset for those employees dont have any attendance for the date
        # in value.
        queryset = queryset.filter(
            employee_attendances__attendance_date=value,
            employee_attendances__attendance_clock_out__isnull=True,
        )
        return queryset

    def filter_queryset(self, queryset):
        """
        Override the default filtering behavior to handle None option and filter queryset for reporting manager.
        """
        from django.db.models import Q

        # Handle default accessibility and filter based on reporting manager
        request = getattr(_thread_locals, "request", None)
        if request:
            employee = getattr(request.user, "employee_get", None)
            cache_key = request.session.session_key + "accessibility_filter"
            accessible = check_is_accessible("employee_view", cache_key, employee)
            if not accessible and employee.reporting_manager.exists():
                queryset = filtersubordinatesemployeemodel(
                    request=request, queryset=queryset, perm="employee.view_employee"
                )

        # Handle 'not_set' values in the cleaned data
        data = self.form.cleaned_data
        not_set_dict = {}
        for key, value in data.items():
            if isinstance(value, (list, django.db.models.query.QuerySet)):
                if value and "not_set" in value:
                    not_set_dict[key] = value

        if not_set_dict:
            q_objects = Q()
            for key, values in not_set_dict.items():
                for value in values:
                    if value == "not_set":
                        q_objects |= Q(**{f"{key}__isnull": True})
                    else:
                        q_objects |= Q(**{key: value})
            queryset = queryset.filter(q_objects)
        else:
            queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    def filter_by_name(self, queryset, name, value):
        """
        Employee search method
        """
        value = value.lower()

        if self.data.get("search_field"):
            return queryset

        def _icontains(instance):
            result = str(getattribute(instance, "get_full_name")).lower()
            return instance.pk if value in result else None

        ids = list(filter(None, map(_icontains, queryset)))
        return queryset.filter(id__in=ids)

    def filter_name_or_badge(self, queryset, name, value):
        """
        Modern filter panel's unified "Name or Badge ID" search (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset, value, "employee_first_name", "employee_last_name", "badge_id"
        )


class EmployeeReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "select"),
        ("employee_work_info__job_position_id", "Job Position"),
        ("employee_work_info__department_id", "Department"),
        ("employee_work_info__shift_id", "Shift"),
        ("employee_work_info__work_type_id", "Work Type"),
        ("employee_work_info__job_role_id", "Job Role"),
        ("employee_work_info__reporting_manager_id", "Reporting Manager"),
        ("employee_work_info__company_id", "Company"),
    ]


class PolicyFilter(FilterSet):
    """
    PolicyFilter filterset class
    """

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = Policy
        fields = "__all__"


class DocumentRequestFilter(HorillaFilterSet):
    """
    Custom filter for Document Requests.
    """

    # Document.title is a near-constant string set once per document request
    # (e.g. "Upload Passport" for every employee in that group), so matching
    # against it can never narrow a group down to one employee. Search by the
    # employee's name/badge instead, like every other request list in the app.
    search = CharFilter(method=filter_by_name)
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as EmployeeFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    # document_request_id is left as a classic select -- its option list
    # is naturally small (the fixed set of document-request "types" a
    # company has configured, e.g. "Upload Passport"), not a scale
    # concern the way Employee is.
    ajax_fields = {
        "employee_id": {
            "key": "document-request-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "document-request-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "document-request-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "document-request-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "document-request-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "document-request-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "document-request-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "document-request-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the model and fields for the filter.
        """

        model = Document
        fields = [
            "employee_id",
            "document_request_id",
            "status",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__is_active",
            "employee_id__gender",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Created At is the only real date
        column on this model, so it's the sole entry.
        """
        fields = [
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class DocumentPipelineFilter(HorillaFilterSet):
    """
    Filter set class for TaxBracket model.
    """

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = DocumentRequest
        fields = "__all__"

    def search_method(self, queryset, _, value):
        """
        This method is used to search

        Matches either the request type's own title (e.g. "Passport") or the
        name/badge of an employee assigned to it, so searching for a person
        surfaces every document-type group they have a pending request in -
        matching the same "search" convention used across the rest of the app.
        """
        value = " ".join(value.split())
        return queryset.filter(
            Q(title__icontains=value)
            | Q(employee_id__employee_first_name__icontains=value)
            | Q(employee_id__employee_last_name__icontains=value)
            | Q(employee_id__badge_id__icontains=value)
        ).distinct()


class DisciplinaryActionFilter(HorillaFilterSet):
    """
    Custom filter for Disciplinary Action.

    """

    search = CharFilter(method=filter_by_name)

    start_date = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as EmployeeFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation). "action"
    # (Actiontype) is left as a classic select -- its option list is
    # naturally small (the fixed set of disciplinary action types a
    # company has configured), not a scale concern the way Employee is.
    ajax_fields = {
        "employee_id": {
            "key": "disciplinary-action-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "disciplinary-action-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "disciplinary-action-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "disciplinary-action-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "disciplinary-action-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "disciplinary-action-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "disciplinary-action-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "disciplinary-action-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
    }

    class Meta:
        model = DisciplinaryAction
        ordering = ["-id"]
        fields = [
            "employee_id",
            "action",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Date's existing exact-match quick
        field stays in place; this adds the full gte/lte/gt/lt/exact
        set for it, plus Created At.
        """
        fields = [
            {
                "key": "start_date",
                "field": "start_date",
                "label": str(_("Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class ActionTypeFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = Actiontype
        fields = ["title", "action_type"]

    def search_method(self, queryset, _, value):
        """
        This method is used to search
        """

        return (
            (queryset.filter(title__icontains=value))
            | queryset.filter(action_type__icontains=value)
        ).distinct()


class EmployeeTagFilter(FilterSet):

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = EmployeeTag
        fields = [
            "title",
        ]


class EmployeeWorkInformationFilter(HorillaFilterSet):

    search = django_filters.CharFilter(
        field_name="employee_id__employee_first_name", lookup_expr="icontains"
    )

    class Meta:
        model = EmployeeWorkInformation
        fields = ["employee_id"]
