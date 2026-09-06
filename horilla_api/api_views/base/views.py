from typing import Any

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.filters import (
    RotatingShiftAssignFilters,
    RotatingWorkTypeAssignFilter,
    ShiftRequestFilter,
    WorkTypeRequestFilter,
)
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeShiftSchedule,
    JobPosition,
    JobRole,
    RotatingShift,
    RotatingShiftAssign,
    RotatingWorkType,
    RotatingWorkTypeAssign,
    ShiftRequest,
    WorkType,
    WorkTypeRequest,
)
from base.views import (
    is_reportingmanger,
    rotating_work_type_assign_export,
    shift_request_export,
    work_type_request_export,
)
from employee.models import Actiontype, Employee
from notifications.signals import notify

from ...api_decorators.base.decorators import (
    check_approval_status,
    manager_or_owner_permission_required,
    manager_permission_required,
    permission_required,
)
from ...api_methods.base.methods import groupby_queryset, permission_based_queryset
from ...api_serializers.base.serializers import (
    CompanySerializer,
    DepartmentSerializer,
    EmployeeShiftScheduleSerializer,
    EmployeeShiftSerializer,
    JobPositionSerializer,
    JobRoleSerializer,
    RotatingShiftAssignSerializer,
    RotatingShiftSerializer,
    RotatingWorkTypeAssignSerializer,
    RotatingWorkTypeSerializer,
    ShiftRequestSerializer,
    WorkTypeRequestSerializer,
    WorkTypeSerializer,
)


def object_check(cls, pk):
    try:
        obj = cls.objects.get(id=pk)
        return obj
    except cls.DoesNotExist:
        return None


def object_delete(cls, pk):
    try:
        cls.objects.get(id=pk).delete()
        return "", 200
    except Exception as e:
        return {"error": str(e)}, 400


def individual_permssion_check(request):
    employee_id = request.GET.get("employee_id")
    employee = Employee.objects.filter(id=employee_id).first()
    if request.user.employee_get == employee:
        return True
    elif employee.employee_work_info.reporting_manager_id == request.user.employee_get:
        return True
    elif request.user.has_perm("base.view_rotatingworktypeassign"):
        return True
    return False


def _is_reportingmanger(request, instance):
    """
    If the instance have employee id field then you can use this method to know the request
    user employee is the reporting manager of the instance
    """
    manager = request.user.employee_get
    try:
        employee_work_info_manager = instance.employee_work_info.reporting_manager_id
    except Exception:
        return HttpResponse("This Employee Dont Have any work information")
    return manager == employee_work_info_manager


class JobPositionView(APIView):
    serializer_class = JobPositionSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_jobposition"))
    def get(self, request, pk=None):
        if pk:
            job_position = object_check(JobPosition, pk)
            if job_position is None:
                return Response({"error": _("Job position not found ")}, status=404)
            serializer = self.serializer_class(job_position)
            return Response(serializer.data, status=200)

        job_positions = JobPosition.objects.all()
        paginater = PageNumberPagination()
        page = paginater.paginate_queryset(job_positions, request)
        serializer = self.serializer_class(page, many=True)
        return paginater.get_paginated_response(serializer.data)

    @method_decorator(permission_required("base.change_jobposition"))
    def put(self, request, pk):
        job_position = object_check(JobPosition, pk)
        if job_position is None:
            return Response({"error": _("Job position not found ")}, status=404)
        serializer = self.serializer_class(job_position, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.add_jobposition"))
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_jobposition"))
    def delete(self, request, pk):
        job_position = object_check(JobPosition, pk)
        if job_position is None:
            return Response({"error": _("Job position not found ")}, status=404)
        response, status_code = object_delete(JobPosition, pk)
        return Response(response, status=status_code)


class DepartmentView(APIView):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_department"), name="dispatch")
    def get(self, request, pk=None):
        if pk:
            department = object_check(Department, pk)
            if department is None:
                return Response({"error": _("Department not found ")}, status=404)
            serializer = self.serializer_class(department)
            return Response(serializer.data, status=200)

        departments = Department.objects.all()
        paginator = PageNumberPagination()
        page: list[Any] | None = paginator.paginate_queryset(departments, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(permission_required("base.change_department"), name="dispatch")
    def put(self, request, pk):
        department = object_check(Department, pk)
        if department is None:
            return Response({"error": _("Department not found ")}, status=404)
        serializer = self.serializer_class(department, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.add_department"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_department"), name="dispatch")
    def delete(self, request, pk):
        department = object_check(Department, pk)
        if department is None:
            return Response({"error": _("Department not found ")}, status=404)
        response, status_code = object_delete(Department, pk)
        return Response(response, status=status_code)


class JobRoleView(APIView):
    serializer_class = JobRoleSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_jobrole"), name="dispatch")
    def get(self, request, pk=None):
        if pk:
            job_role = object_check(JobRole, pk)
            if job_role is None:
                return Response({"error": _("Job role not found ")}, status=404)
            serializer = self.serializer_class(job_role)
            return Response(serializer.data, status=200)

        job_roles = JobRole.objects.all()
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(job_roles, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(permission_required("base.change_jobrole"), name="dispatch")
    def put(self, request, pk):
        job_role = object_check(JobRole, pk)
        if job_role is None:
            return Response({"error": _("Job role not found ")}, status=404)
        serializer = self.serializer_class(job_role, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.add_jobrole"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_jobrole"), name="dispatch")
    def delete(self, request, pk):
        job_role = object_check(JobRole, pk)
        if job_role is None:
            return Response({"error": _("Job role not found ")}, status=404)
        response, status_code = object_delete(JobRole, pk)
        return Response(response, status=status_code)


class CompanyView(APIView):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_company"), name="dispatch")
    def get(self, request, pk=None):
        if pk:
            company = object_check(Company, pk)
            if company is None:
                return Response({"error": _("Company not found ")}, status=404)
            serializer = self.serializer_class(company)
            return Response(serializer.data, status=200)

        companies = Company.objects.all()
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(companies, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(permission_required("base.change_company"), name="dispatch")
    def put(self, request, pk):
        company = object_check(Company, pk)
        if company is None:
            return Response({"error": _("Company not found ")}, status=404)
        serializer = self.serializer_class(company, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.add_company"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_company"), name="dispatch")
    def delete(self, request, pk):
        company = object_check(Company, pk)
        if company is None:
            return Response({"error": _("Company not found ")}, status=400)
        response, status_code = object_delete(Company, pk)
        return Response(response, status=status_code)


class WorkTypeView(APIView):
    serializer_class = WorkTypeSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            work_type = object_check(WorkType, pk)
            if work_type is None:
                return Response({"error": _("WorkType not found")}, status=404)
            serializer = self.serializer_class(work_type)
            return Response(serializer.data, status=200)

        work_types = WorkType.objects.all()
        serializer = self.serializer_class(work_types, many=True)
        return Response(serializer.data)

    @method_decorator(permission_required("base.add_worktype"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.change_worktype"), name="dispatch")
    def put(self, request, pk):
        work_type = object_check(WorkType, pk)
        if work_type is None:
            return Response({"error": _("WorkType not found")}, status=404)
        serializer = self.serializer_class(work_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_worktype"), name="dispatch")
    def delete(self, request, pk):
        work_type = object_check(WorkType, pk)
        if work_type is None:
            return Response({"error": _("WorkType not found")}, status=404)
        response, status_code = object_delete(WorkType, pk)
        return Response(response, status=status_code)


class WorkTypeRequestView(APIView):
    serializer_class = WorkTypeRequestSerializer
    filterset_class = WorkTypeRequestFilter
    permission_classes = [IsAuthenticated]
    queryset = WorkTypeRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self, request=None):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False) or request is None:
            return WorkTypeRequest.objects.none()
        queryset = WorkTypeRequest.objects.all()
        user = request.user
        # checking user level permissions
        perm = "base.view_worktyperequest"
        queryset = permission_based_queryset(user, perm, queryset, user_obj=True)
        return queryset

    def get(self, request, pk=None):
        # individual object workflow
        if pk:
            work_type_request = object_check(WorkTypeRequest, pk)
            if work_type_request is None:
                return Response({"error": _("WorkTypeRequest not found")}, status=404)
            serializer = self.serializer_class(work_type_request)
            return Response(serializer.data, status=200)
        # permission based queryset
        work_type_requests = self.get_queryset(request)
        # filtering queryset
        work_type_request_filter_queryset = self.filterset_class(
            request.GET, queryset=work_type_requests
        ).qs
        # groupby workflow
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(
                request, url, field_name, work_type_request_filter_queryset
            )
        # pagination workflow
        paginater = PageNumberPagination()
        page = paginater.paginate_queryset(work_type_request_filter_queryset, request)
        serializer = self.serializer_class(page, many=True)
        return paginater.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if not request.user.has_perm("base.add_worktyperequest"):
            data["employee_id"] = request.user.employee_get.id
        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            instance = serializer.save()
            try:
                notify.send(
                    instance.employee_id,
                    recipient=(
                        instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    ),
                    verb=f"You have new work type request to \
                                validate for {instance.employee_id}",
                    verb_ar=f"لديك طلب نوع وظيفة جديد للتحقق من \
                                {instance.employee_id}",
                    verb_de=f"Sie haben eine neue Arbeitstypanfrage zur \
                                Validierung für {instance.employee_id}",
                    verb_es=f"Tiene una nueva solicitud de tipo de trabajo para \
                                validar para {instance.employee_id}",
                    verb_fr=f"Vous avez une nouvelle demande de type de travail\
                                à valider pour {instance.employee_id}",
                    icon="information",
                    redirect=f"/employee/work-type-request-view?id={instance.id}",
                    api_redirect=f"/api/base/worktype-requests/{instance.id}",
                )
                return Response(serializer.data, status=201)
            except Exception as E:
                return Response(serializer.errors, status=400)
        return Response(serializer.errors, status=400)

    @check_approval_status(WorkTypeRequest, "base.change_worktyperequest")
    @manager_or_owner_permission_required(
        WorkTypeRequest, "base.change_worktyperequest"
    )
    def put(self, request, pk):
        work_type_request = object_check(WorkTypeRequest, pk)
        if work_type_request is None:
            return Response({"error": _("WorkTypeRequest not found")}, status=404)
        serializer = self.serializer_class(work_type_request, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @check_approval_status(WorkTypeRequest, "base.change_worktyperequest")
    @manager_or_owner_permission_required(
        WorkTypeRequest, "base.delete_worktyperequest"
    )
    def delete(self, request, pk):
        work_type_request = object_check(WorkTypeRequest, pk)
        if work_type_request is None:
            return Response({"error": _("WorkTypeRequest not found")}, status=404)
        response, status_code = object_delete(WorkTypeRequest, pk)
        return Response(response, status=status_code)


class WorkTypeRequestCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        work_type_request = WorkTypeRequest.find(pk)
        if (
            is_reportingmanger(request, work_type_request)
            or request.user.has_perm("base.cancel_worktyperequest")
            or work_type_request.employee_id == request.user.employee_get
            and work_type_request.approved == False
        ):
            work_type_request.canceled = True
            work_type_request.approved = False
            work_type_request.employee_id.employee_work_info.work_type_id = (
                work_type_request.previous_work_type_id
            )
            work_type_request.employee_id.employee_work_info.save()
            work_type_request.save()
            try:
                notify.send(
                    request.user.employee_get,
                    recipient=work_type_request.employee_id.employee_user_id,
                    verb="Your work type request has been rejected.",
                    verb_ar="تم إلغاء طلب نوع وظيفتك",
                    verb_de="Ihre Arbeitstypanfrage wurde storniert",
                    verb_es="Su solicitud de tipo de trabajo ha sido cancelada",
                    verb_fr="Votre demande de type de travail a été annulée",
                    redirect=f"/employee/work-type-request-view?id={work_type_request.id}",
                    icon="close",
                    api_redirect="/api/base/worktype-requests/<int:pk>/",
                )
            except:
                pass
        return Response(status=200)


class WorkRequestApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        work_type_request = WorkTypeRequest.find(pk)
        if (
            is_reportingmanger(request, work_type_request)
            or request.user.has_perm("base.approve_worktyperequest")
            or request.user.has_perm("base.change_worktyperequest")
        ) and not work_type_request.approved:
            """
            Here the request will be approved, can send mail right here
            """
            if not work_type_request.is_any_work_type_request_exists():
                work_type_request.approved = True
                work_type_request.canceled = False
                work_type_request.save()
                try:
                    notify.send(
                        request.user.employee_get,
                        recipient=work_type_request.employee_id.employee_user_id,
                        verb="Your work type request has been approved.",
                        verb_ar="تمت الموافقة على طلب نوع وظيفتك.",
                        verb_de="Ihre Arbeitstypanfrage wurde genehmigt.",
                        verb_es="Su solicitud de tipo de trabajo ha sido aprobada.",
                        verb_fr="Votre demande de type de travail a été approuvée.",
                        redirect=f"/employee/work-type-request-view?id={work_type_request.id}",
                        icon="checkmark",
                        api_redirect="/api/base/worktype-requests/<int:pk>/",
                    )
                    return Response({"status": "approved"})
                except Exception as e:
                    return Response({"error": str(e)}, status=400)
        else:
            return Response({"error": _("You don't have permission")}, status=400)


class WorkTypeRequestExport(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("base.view_worktyperequest")
    def get(self, request):
        return work_type_request_export(request)


class IndividualRotatingWorktypesView(APIView):
    serializer_class = RotatingWorkTypeAssignSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if individual_permssion_check(request) == False:
            return Response({"error": _("you have no permssion to view")}, status=400)
        if pk:
            rotating_work_type_assign = object_check(RotatingWorkTypeAssign, pk)
            if rotating_work_type_assign is None:
                return Response(
                    {"error": _("RotatingWorkTypeAssign not found")}, status=404
                )
            serializer = self.serializer_class(rotating_work_type_assign)
            return Response(serializer.data, status=200)
        employee_id = request.GET.get("employee_id", None)
        rotating_work_type_assigns = RotatingWorkTypeAssign.objects.filter(
            employee_id=employee_id
        )
        pagenation = PageNumberPagination()
        page = pagenation.paginate_queryset(rotating_work_type_assigns, request)
        serializer = self.serializer_class(page, many=True)
        return pagenation.get_paginated_response(serializer.data)


class RotatingWorkTypeAssignView(APIView):
    serializer_class = RotatingWorkTypeAssignSerializer
    filterset_class = RotatingWorkTypeAssignFilter
    permission_classes = [IsAuthenticated]
    queryset = RotatingWorkTypeAssign.objects.none()  # For drf-yasg schema generation

    def _permission_check(self, request, obj=None, pk=None):
        if pk:
            employee = request.user.employee_get
            manager = obj.employee_id.get_reporting_manager()
            if (
                employee == obj.employee_id
                or manager == employee
                or request.user.has_perm("base.view_rotatingworktypeassign")
            ):
                return True
            return False

    @manager_permission_required("base.view_rotatingworktypeassign")
    def get(self, request, pk=None):

        if pk:

            rotating_work_type_assign = object_check(RotatingWorkTypeAssign, pk)
            if rotating_work_type_assign is None:
                return Response(
                    {"error": _("RotatingWorkTypeAssign not found")}, status=404
                )
            serializer = self.serializer_class(rotating_work_type_assign)
            return Response(serializer.data, status=200)
        rotating_work_type_assigns = RotatingWorkTypeAssign.objects.all()
        rotating_work_type_assigns_filter_queryset = self.filterset_class(
            request.GET, queryset=rotating_work_type_assigns
        ).qs
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            # groupby workflow
            url = request.build_absolute_uri()
            return groupby_queryset(
                request, url, field_name, rotating_work_type_assigns_filter_queryset
            )

        pagenation = PageNumberPagination()
        page = pagenation.paginate_queryset(
            rotating_work_type_assigns_filter_queryset, request
        )
        serializer = self.serializer_class(page, many=True)
        return pagenation.get_paginated_response(serializer.data)

    @manager_permission_required("base.add_rotatingworktypeassign")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            try:
                users = [employee.employee_user_id for employee in obj]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb="You are added to rotating work type",
                    verb_ar="تمت إضافتك إلى نوع العمل المتناوب",
                    verb_de="Sie werden zum rotierenden Arbeitstyp hinzugefügt",
                    verb_es="Se le agrega al tipo de trabajo rotativo",
                    verb_fr="Vous êtes ajouté au type de travail rotatif",
                    icon="infinite",
                    redirect="/employee/employee-profile/",
                    api_redirect="",
                )
            except:
                pass
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @manager_permission_required("base.change_rotatingworktypeassign")
    def put(self, request, pk):
        rotating_work_type_assign = object_check(RotatingWorkTypeAssign, pk)
        if rotating_work_type_assign is None:
            return Response(
                {"error": _("RotatingWorkTypeAssign not found")}, status=404
            )
        serializer = self.serializer_class(rotating_work_type_assign, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @manager_permission_required("base.delete_rotatingworktypeassign")
    def delete(self, request, pk):
        rotating_work_type_assign = object_check(RotatingWorkTypeAssign, pk)
        if rotating_work_type_assign is None:
            return Response(
                {"error": _("RotatingWorkTypeAssign not found")}, status=404
            )
        response, status_code = object_delete(RotatingWorkTypeAssign, pk)
        return Response(response, status=status_code)


class IndividualWorkTypeRequestView(APIView):
    serializer_class = WorkTypeRequestSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if individual_permssion_check(request) == False:
            return Response({"error": _("you have no permssion to view")}, status=400)

        # individual object workflow
        if pk:
            work_type_request = object_check(WorkTypeRequest, pk)
            if work_type_request is None:
                return Response({"error": _("WorkTypeRequest not found")}, status=404)
            serializer = self.serializer_class(work_type_request)
            return Response(serializer.data, status=200)
        employee_id = request.GET.get("employee_id", None)
        work_type_request = WorkTypeRequest.objects.filter(employee_id=employee_id)
        paginater = PageNumberPagination()
        page = paginater.paginate_queryset(work_type_request, request)
        serializer = self.serializer_class(page, many=True)
        return paginater.get_paginated_response(serializer.data)


class EmployeeShiftView(APIView):
    serializer_class = EmployeeShiftSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            employee_shift = object_check(EmployeeShift, pk)
            if employee_shift is None:
                return Response({"error": _("EmployeeShift not found")}, status=404)
            serializer = self.serializer_class(employee_shift)
            return Response(serializer.data, status=200)

        employee_shifts = EmployeeShift.objects.all()
        serializer = self.serializer_class(employee_shifts, many=True)
        return Response(serializer.data, status=200)

    @method_decorator(permission_required("base.add_employeeshift"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.change_employeeshift"), name="dispatch")
    def put(self, request, pk):
        employee_shift = object_check(EmployeeShift, pk)
        if employee_shift is None:
            return Response({"error": _("EmployeeShift not found")}, status=404)
        serializer = self.serializer_class(employee_shift, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_employeeshift"), name="dispatch")
    def delete(self, request, pk):
        employee_shift = object_check(EmployeeShift, pk)
        if employee_shift is None:
            return Response({"error": _("EmployeeShift not found")}, status=404)
        response, status_code = object_delete(EmployeeShift, pk)
        return Response(response, status=status_code)


class EmployeeShiftScheduleView(APIView):
    serializer_class = EmployeeShiftScheduleSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("base.view_employeeshiftschedule"), name="dispatch"
    )
    def get(self, request, pk=None):
        if pk:
            employee_shift_schedule = object_check(EmployeeShiftSchedule, pk)
            if employee_shift_schedule is None:
                return Response(
                    {"error": _("EmployeeShiftSchedule not found")}, status=404
                )
            serializer = self.serializer_class(employee_shift_schedule)
            return Response(serializer.data, status=200)

        employee_shift_schedules = EmployeeShiftSchedule.objects.all()
        serializer = self.serializer_class(employee_shift_schedules, many=True)
        return Response(serializer.data, status=200)

    @method_decorator(
        permission_required("base.add_employeeshiftschedule"), name="dispatch"
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.change_employeeshiftschedule"), name="dispatch"
    )
    def put(self, request, pk):
        employee_shift_schedule = object_check(EmployeeShiftSchedule, pk)
        if employee_shift_schedule is None:
            return Response({"error": _("EmployeeShiftSchedule not found")}, status=404)
        serializer = self.serializer_class(employee_shift_schedule, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.delete_employeeshiftschedule"), name="dispatch"
    )
    def delete(self, request, pk):
        employee_shift_schedule = object_check(EmployeeShiftSchedule, pk)
        if employee_shift_schedule is None:
            return Response({"error": _("EmployeeShiftSchedule not found")}, status=404)
        response, status_code = object_delete(EmployeeShiftSchedule, pk)
        return Response(response, status=status_code)


class RotatingShiftView(APIView):
    serializer_class = RotatingShiftSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_rotatingshift"), name="dispatch")
    def get(self, request, pk=None):

        if pk:
            rotating_shift = object_check(RotatingShift, pk)
            if rotating_shift is None:
                return Response({"error": _("RotatingShift not found")}, status=404)
            serializer = self.serializer_class(rotating_shift)
            return Response(serializer.data, status=200)

        employee_id = request.GET.get(
            "employee_id"
        )  # Get the employee_id from query parameters
        if employee_id:  # Check if employee_ids are present in the request
            rotating_shifts = RotatingShift.objects.filter(
                employee_id__in=[employee_id]
            )

        rotating_shifts = RotatingShift.objects.all()
        serializer = self.serializer_class(rotating_shifts, many=True)
        return Response(serializer.data, status=200)

    @method_decorator(permission_required("base.add_rotatingshift"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.change_rotatingshift"), name="dispatch")
    def put(self, request, pk):
        rotating_shift = object_check(RotatingShift, pk)
        if rotating_shift is None:
            return Response({"error": _("RotatingShift not found")}, status=404)
        serializer = self.serializer_class(rotating_shift, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("base.delete_rotatingshift"), name="dispatch")
    def delete(self, request, pk):
        rotating_shift = object_check(RotatingShift, pk)
        if rotating_shift is None:
            return Response({"error": _("RotatingShift not found")}, status=404)
        response, status_code = object_delete(RotatingShift, pk)
        return Response(response, status=status_code)


class IndividualRotatingShiftView(APIView):
    serializer_class = RotatingShiftAssignSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if individual_permssion_check(request) == False:
            return Response({"error": _("you have no permssion to view")}, status=400)

        if pk:
            rotating_shift_assign = object_check(RotatingShiftAssign, pk)
            if rotating_shift_assign is None:
                return Response(
                    {"error": _("RotatingShiftAssign not found")}, status=404
                )
            serializer = self.serializer_class(rotating_shift_assign)
            return Response(serializer.data, status=200)
        employee_id = request.GET.get("employee_id", None)
        rotating_shift_assigns = RotatingShiftAssign.objects.filter(
            employee_id=employee_id
        )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rotating_shift_assigns, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RotatingShiftAssignView(APIView):
    serializer_class = RotatingShiftAssignSerializer
    filterset_class = RotatingShiftAssignFilters
    permission_classes = [IsAuthenticated]
    queryset = RotatingShiftAssign.objects.none()  # For drf-yasg schema generation

    @manager_permission_required("base.view_rotatingshiftassign")
    def get(self, request, pk=None):
        if pk:
            rotating_shift_assign = object_check(RotatingShiftAssign, pk)
            if rotating_shift_assign is None:
                return Response(
                    {"error": _("RotatingShiftAssign not found")}, status=404
                )
            serializer = self.serializer_class(rotating_shift_assign)
            return Response(serializer.data, status=200)

        rotating_shift_assigns = RotatingShiftAssign.objects.all()
        rotating_shift_assigns_filter_queryset = self.filterset_class(
            request.GET, queryset=rotating_shift_assigns
        ).qs
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            # groupby workflow
            url = request.build_absolute_uri()
            return groupby_queryset(
                request, url, field_name, rotating_shift_assigns_filter_queryset
            )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(
            rotating_shift_assigns_filter_queryset, request
        )
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @manager_permission_required("base.add_rotatingshiftassign")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @manager_permission_required("base.change_rotatingshiftassign")
    def put(self, request, pk):
        rotating_shift_assign = object_check(RotatingShiftAssign, pk)
        if rotating_shift_assign is None:
            return Response({"error": _("RotatingShiftAssign not found")}, status=404)
        serializer = self.serializer_class(rotating_shift_assign, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @manager_permission_required("base.delete_rotatingshiftassign")
    def delete(self, request, pk):
        rotating_shift_assign = object_check(RotatingShiftAssign, pk)
        if rotating_shift_assign is None:
            return Response({"error": _("RotatingShiftAssign not found")}, status=404)
        response, status_code = object_delete(RotatingShiftAssign, pk)
        return Response(response, status=status_code)


class IndividualShiftRequestView(APIView):
    serializer_class = ShiftRequestSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if individual_permssion_check(request) == False:
            return Response({"error": _("you have no permssion to view")}, status=400)

        if pk:
            shift_request = object_check(ShiftRequest, pk)
            if shift_request is None:
                return Response({"error": _("EmployeeShift not found")}, status=404)
            serializer = self.serializer_class(shift_request)
            return Response(serializer.data, status=200)
        employee_id = request.GET.get("employee_id", None)
        shift_requests = ShiftRequest.objects.filter(employee_id=employee_id)
        paginater = PageNumberPagination()
        page = paginater.paginate_queryset(shift_requests, request)
        serializer = self.serializer_class(page, many=True)
        return paginater.get_paginated_response(serializer.data)


class ShiftRequestView(APIView):
    serializer_class = ShiftRequestSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ShiftRequestFilter
    permission_classes = [IsAuthenticated]
    queryset = ShiftRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self, request=None):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False) or request is None:
            return ShiftRequest.objects.none()
        queryset = ShiftRequest.objects.all()
        user = request.user
        # checking user level permissions
        perm = "base.view_shiftrequest"
        queryset = permission_based_queryset(user, perm, queryset, user_obj=True)
        return queryset

    def get(self, request, pk=None):
        # individual section
        if pk:
            shift_request = object_check(ShiftRequest, pk)
            if shift_request is None:
                return Response({"error": _("ShiftRequest not found")}, status=404)
            serializer = self.serializer_class(shift_request)
            return Response(serializer.data, status=200)
        # filter section
        shift_requests = self.get_queryset(request)
        shift_requests_filter_queryset = self.filterset_class(
            request.GET, queryset=shift_requests
        ).qs
        # groupby section
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(
                request, url, field_name, shift_requests_filter_queryset
            )
        # pagination section
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(shift_requests_filter_queryset, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if not request.user.has_perm("base.add_shiftrequest"):
            data["employee_id"] = request.user.employee_get.id
        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @check_approval_status(ShiftRequest, "base.change_shiftrequest")
    @manager_or_owner_permission_required(ShiftRequest, "base.change_shiftrequest")
    def put(self, request, pk):
        shift_request = object_check(ShiftRequest, pk)
        if shift_request is None:
            return Response({"error": _("ShiftRequest not found")}, status=404)
        serializer = self.serializer_class(shift_request, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @check_approval_status(ShiftRequest, "base.delete_shiftrequest")
    @manager_or_owner_permission_required(ShiftRequest, "base.delete_shiftrequest")
    def delete(self, request, pk):
        shift_request = object_check(ShiftRequest, pk)
        if shift_request is None:
            return Response({"error": _("ShiftRequest not found")}, status=404)
        response, status_code = object_delete(ShiftRequest, pk)
        return Response(response, status=status_code)


class RotatingWorkTypeView(APIView):
    serializer_class = RotatingWorkTypeSerializer
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.view_rotatingworktype"))
    def get(self, request, pk=None):
        if pk:
            rotating_work_type = object_check(RotatingWorkType, pk)
            if rotating_work_type is None:
                return Response({"error": _("RotatingWorkType not found")}, status=404)
            serializer = self.serializer_class(rotating_work_type)
            return Response(serializer.data, status=200)

        rotating_work_types = RotatingWorkType.objects.all()
        serializer = self.serializer_class(rotating_work_types, many=True)
        return Response(serializer.data, status=200)

    @method_decorator(permission_required("base.add_rotatingworktype"), name="dispatch")
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.change_rotatingworktype"), name="dispatch"
    )
    def put(self, request, pk):
        rotating_work_type = object_check(RotatingWorkType, pk)
        if rotating_work_type is None:
            return Response({"error": _("RotatingWorkType not found")}, status=404)
        serializer = self.serializer_class(rotating_work_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.delete_rotatingworktype"), name="dispatch"
    )
    def delete(self, request, pk):
        rotating_work_type = object_check(RotatingWorkType, pk)
        if rotating_work_type is None:
            return Response({"error": _("RotatingWorkType not found")}, status=404)
        response, status_code = object_delete(RotatingWorkType, pk)
        return Response(response, status=status_code)


class ShiftRequestApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        shift_request = ShiftRequest.objects.get(id=pk)
        if (
            is_reportingmanger(request, shift_request)
            or request.user.has_perm("base.approve_shiftrequest")
            or request.user.has_perm("base.change_shiftrequest")
        ) and not shift_request.approved:
            """
            here the request will be approved, can send mail right here
            """
            if not shift_request.is_any_request_exists():
                shift_request.approved = True
                shift_request.canceled = False
                shift_request.save()
                return Response({"status": "success"}, status=200)
            else:
                return Response(
                    {"error": _("Already request exits on same date")}, status=400
                )

        return Response({"error": _("No permission ")}, status=400)


class ShiftRequestBulkApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data["ids"]
        length = len(ids)
        count = 0
        for id in ids:
            shift_request = ShiftRequest.objects.get(id=id)
            if (
                is_reportingmanger(request, shift_request)
                or request.user.has_perm("base.approve_shiftrequest")
                or request.user.has_perm("base.change_shiftrequest")
            ) and not shift_request.approved:
                """
                here the request will be approved, can send mail right here
                """
                shift_request.approved = True
                shift_request.canceled = False
                employee_work_info = shift_request.employee_id.employee_work_info
                employee_work_info.shift_id = shift_request.shift_id
                employee_work_info.save()
                shift_request.save()
                count += 1
        if length == count:
            return Response({"status": "success"}, status=200)
        return Response({"status": "failed"}, status=400)


class ShiftRequestCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        shift_request = ShiftRequest.objects.get(id=pk)
        if (
            is_reportingmanger(request, shift_request)
            or request.user.has_perm("base.cancel_shiftrequest")
            or shift_request.employee_id == request.user.employee_get
            and shift_request.approved == False
        ):
            shift_request.canceled = True
            shift_request.approved = False
            shift_request.employee_id.employee_work_info.shift_id = (
                shift_request.previous_shift_id
            )
            shift_request.employee_id.employee_work_info.save()
            shift_request.save()
            return Response({"status": "success"}, status=200)
        return Response({"status": "failed"}, status=400)


class ShiftRequestBulkCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get("ids", None)
        length = len(ids)
        count = 0
        for id in ids:
            shift_request = ShiftRequest.objects.get(id=id)
            if (
                is_reportingmanger(request, shift_request)
                or request.user.has_perm("base.cancel_shiftrequest")
                or shift_request.employee_id == request.user.employee_get
                and shift_request.approved == False
            ):
                shift_request.canceled = True
                shift_request.approved = False
                shift_request.employee_id.employee_work_info.shift_id = (
                    shift_request.previous_shift_id
                )
                shift_request.employee_id.employee_work_info.save()
                shift_request.save()
                count += 1
        if length == count:
            return Response({"status": "success"}, status=200)
        return Response({"status": "failed"}, status=400)


class ShiftRequestDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.delete_shiftrequest"))
    def delete(self, request, pk=None):

        if pk is None:
            try:
                ids = request.data["ids"]
                shift_requests = ShiftRequest.objects.filter(id__in=ids)
                shift_requests.delete()
            except Exception as e:
                return Response({"status": "failed", "error": str(e)}, status=400)
            return Response({"status": "success"}, status=200)
        try:
            shift_request = ShiftRequest.objects.get(id=pk)
            if not shift_request.approved:
                raise
            shift_request.delete()

        except ShiftRequest.DoesNotExist:
            return Response(
                {"status": "failed", "error": _("Shift request does not exists")},
                status=400,
            )
        return Response({"status": "deleted"}, status=200)


class ShiftRequestExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return shift_request_export(request)


class ShiftRequestAllocationView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.change_shiftrequest"))
    def post(self, request, id):
        shift_request = ShiftRequest.objects.get(id=id)
        if not shift_request.is_any_request_exists():
            shift_request.reallocate_approved = True
            shift_request.reallocate_canceled = False
            shift_request.save()
            return Response({"status": "success"}, status=200)
        return Response({"status": "failed"}, status=400)


class RotatingShiftAssignExport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return rotating_work_type_assign_export(request)


class RotatingShiftAssignBulkArchive(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.change_rotatingshiftassign"))
    def put(self, request, status):
        ids = request.data.get("ids", None)
        try:
            rotating_shift_asssign = RotatingShiftAssign.objects.filter(id__in=ids)
            rotating_shift_asssign.update(is_active=status)
            return Response({"status": "success"}, status=200)
        except Exception as E:
            return Response({"error": str(E)}, status=400)


class RotatingShiftAssignBulkDelete(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("base.delete_rotatingshiftassign"))
    def delete(self, request):
        ids = request.data.get("ids", None)
        try:
            rotating_shift_asssign = RotatingShiftAssign.objects.filter(id__in=ids)
            rotating_shift_asssign.delete()
            return Response({"status": "success"}, status=200)
        except Exception as E:
            return Response({"error": str(E)}, status=400)


class RotatingWorKTypePermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        manager = Employee.objects.filter(id=id).first().get_reporting_manager()
        if (
            request.user.has_perm("base.add_rotatingworktypeassign")
            or request.user.employee_get == manager
        ):
            return Response(status=200)
        return Response(status=400)


class RotatingShiftPermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        manager = Employee.objects.filter(id=id).first().get_reporting_manager()
        if (
            request.user.has_perm("base.add_rotatingshiftassign")
            or request.user.employee_get == manager
        ):
            return Response(status=200)
        return Response(status=400)


class WorktypeRequestApprovePermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance = Employee.objects.filter(id=request.GET.get("employee_id")).first()
        if (
            _is_reportingmanger(request, instance)
            or request.user.has_perm("base.approve_worktyperequest")
            or request.user.has_perm("base.change_worktyperequest")
        ):
            return Response(status=200)
        return Response(status=400)


class ShiftRequestApprovePermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance = Employee.objects.filter(id=request.GET.get("employee_id")).first()
        if (
            _is_reportingmanger(request, instance)
            or request.user.has_perm("base.approve_shiftrequest")
            or request.user.has_perm("base.change_shiftrequest")
        ):
            return Response(status=200)
        return Response(status=400)


class EmployeeTabPermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        instance = Employee.objects.filter(id=request.GET.get("employee_id")).first()
        if _is_reportingmanger(request, instance) or request.user.has_perms(
            [
                "base.view_worktyperequest",
                "attendance.view_shiftrequest",
                "employee.change_employee",
            ]
        ):
            return Response(status=200)
        return Response({"message": _("No permission")}, status=400)


class CheckUserLevel(APIView):

    def get(self, request):
        perm = request.GET.get("perm")
        if request.user.has_perm(perm):
            return Response(status=200)
        return Response({"error": _("No permission")}, status=400)


from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from django.db.models import Q

from base.models import Announcement, AnnouncementExpire


class AnnouncementPagination(PageNumberPagination):
    page_size_query_param = "page_size"  # allow client to override
    max_page_size = 100  # prevent abuse


class AnnouncementListAPIView(APIView):
    """
    API endpoint to list announcements for the authenticated user.

    - Updates expire dates if missing.
    - Filters based on user permissions and validity.
    - Marks announcements with whether the user has viewed them.
    - Supports pagination.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = AnnouncementPagination

    def get(self, request, *args, **kwargs):
        # Update missing expire_date in bulk, using each announcement's
        # company-specific "Default Expire Days" setting (falling back to
        # the "All Companies" default, then 30, when unconfigured).
        announcements_to_update = (
            Announcement.objects.filter(expire_date__isnull=True)
            .only("id", "created_at")
            .prefetch_related("company_id")
        )
        expire_days_by_company = {}
        for ann in announcements_to_update:
            companies = list(ann.company_id.all())
            company = companies[0] if companies else None
            cache_key = company.id if company else None
            if cache_key not in expire_days_by_company:
                setting = AnnouncementExpire.objects.filter(company_id=company).first()
                if not setting and company is not None:
                    setting = AnnouncementExpire.objects.filter(company_id=None).first()
                expire_days_by_company[cache_key] = (
                    setting.days if setting and setting.days is not None else 30
                )
            ann.expire_date = ann.created_at + timedelta(
                days=expire_days_by_company[cache_key]
            )
        if announcements_to_update:
            Announcement.objects.bulk_update(announcements_to_update, ["expire_date"])

        # Base queryset: non-expired announcements
        announcements = Announcement.objects.filter(
            expire_date__gte=datetime.today().date()
        )

        # Permission filter
        if not request.user.has_perm("base.view_announcement"):
            announcements = announcements.filter(
                Q(employees=request.user.employee_get) | Q(employees__isnull=True)
            )

        # Prefetch related views for efficiency
        announcements = announcements.prefetch_related("announcementview_set").order_by(
            "-created_at"
        )

        # Build response data
        data = [
            {
                "id": ann.id,
                "title": ann.title,
                "content": self._parse_description(ann.description),
                "created_at": ann.created_at,
                "expire_date": ann.expire_date,
                "has_viewed": ann.announcementview_set.filter(
                    user=request.user, viewed=True
                ).exists(),
            }
            for ann in announcements
        ]

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)

    @staticmethod
    def _parse_description(description: str) -> list[dict]:
        """
        Parse HTML description into structured text (headings + paragraphs).
        """
        soup = BeautifulSoup(description or "", "html.parser")
        content = []

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
            tag_type = "heading" if tag.name.startswith("h") else "paragraph"
            content.append({"type": tag_type, "text": tag.get_text(" ", strip=True)})

        return content
