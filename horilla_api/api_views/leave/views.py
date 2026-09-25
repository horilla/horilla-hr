import contextlib

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import AnonymousUser
from django.db.models import Count
from django.http import Http404, QueryDict
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.methods import filtersubordinates
from horilla.decorators import check_manager
from horilla_api.api_methods.base.methods import reject_reason_from
from horilla_api.api_methods.base.pagination import HorillaPageNumberPagination
from horilla_api.api_serializers.leave.serializers import *
from leave.filters import *
from leave.methods import filter_conditional_leave_request
from leave.models import AvailableLeave, LeaveAllocationRequest, LeaveRequest, LeaveType
from notifications.signals import notify

from ...api_decorators.base.decorators import (
    approver_permission_required,
    manager_or_owner_permission_required,
    manager_permission_required,
)
from ...api_methods.base.methods import groupby_queryset


class EmployeeAvailableLeaveGetAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = request.user.employee_get
        available_leave = employee.available_leave.all()
        paginator = HorillaPageNumberPagination()
        page = paginator.paginate_queryset(available_leave, request)
        serializer = GetAvailableLeaveTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class EmployeeLeaveRequestGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserLeaveRequestFilter
    queryset = LeaveRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return LeaveRequest.objects.none()
        if not self.request.user.is_authenticated:
            return LeaveRequest.objects.none()
        employee = self.request.user.employee_get
        return employee.leaverequest_set.all().order_by("-id")

    def get(self, request):
        employee = request.user.employee_get
        leave_request = employee.leaverequest_set.all().order_by("-id")
        filterset = self.filterset_class(request.GET, queryset=leave_request)
        paginator = HorillaPageNumberPagination()
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = userLeaveRequestGetAllSerilaizer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        employee_id = request.user.employee_get.id
        data = request.data
        if isinstance(data, QueryDict):
            data = data.dict()
        data["employee_id"] = employee_id
        data["end_date"] = (
            data.get("start_date") if not data.get("end_date") else data.get("end_date")
        )
        serializer = LeaveRequestCreateUpdateSerializer(data=data)
        if serializer.is_valid():
            leave_request = serializer.save()
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=leave_request.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                    verb=gettext_noop("You have a new leave request to validate."),
                    icon="people-circle",
                    redirect=f"/leave/request-view?id={leave_request.id}",
                    api_redirect=f"/api/leave/request/{leave_request.id}/",
                )
            return Response(
                userLeaveRequestGetAllSerilaizer(leave_request).data, status=201
            )
        return Response(serializer.errors, status=400)


class EmployeeLeaveRequestUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_request(self, request, pk):
        try:
            return LeaveRequest.objects.get(
                pk=pk, employee_id=request.user.employee_get
            )
        except LeaveRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def get(self, request, pk):
        leave_request = self.get_leave_request(request, pk)
        serializer = UserLeaveRequestGetSerilaizer(leave_request)
        return Response(serializer.data, status=200)

    def put(self, request, pk):
        leave_request = self.get_leave_request(request, pk)
        employee_id = request.user.employee_get
        if (
            leave_request.status == "requested"
            and leave_request.employee_id == employee_id
        ):
            data = request.data
            if isinstance(data, QueryDict):
                data = data.dict()
            data["employee_id"] = employee_id.id
            data["end_date"] = (
                data.get("start_date")
                if not data.get("end_date")
                else data.get("end_date")
            )
            serializer = LeaveRequestCreateUpdateSerializer(leave_request, data=data)
            if serializer.is_valid():
                leave_request = serializer.save()
                return Response(
                    UserLeaveRequestGetSerilaizer(leave_request).data, status=201
                )
            return Response(serializer.errors, status=400)
        raise serializers.ValidationError({"error": _("Access Denied..")})

    def delete(self, request, pk):
        leave_request = self.get_leave_request(request, pk)
        employee_id = request.user.employee_get
        if (
            leave_request.status == "requested"
            and leave_request.employee_id == employee_id
        ):
            leave_request.delete()
            return Response(
                {"message": "Leave request deleted successfully.."}, status=200
            )
        raise serializers.ValidationError({"error": _("Access Denied..")})


class LeaveTypeGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeaveTypeFilter
    queryset = LeaveType.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return LeaveType.objects.none()
        return LeaveType.objects.all()

    # @method_decorator(permission_required('leave.view_leavetype', raise_exception=True), name='dispatch')
    def get(self, request):
        leave_type = LeaveType.objects.all()
        filterset = self.filterset_class(request.GET, queryset=leave_type)
        paginator = HorillaPageNumberPagination()
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = LeaveTypeAllGetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(
        permission_required("leave.add_leavetype", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        serializer = LeaveTypeGetCreateSerilaizer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class LeaveTypeGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_type(self, pk):
        try:
            return LeaveType.objects.get(pk=pk)
        except LeaveType.DoesNotExist as e:
            raise serializers.ValidationError(e)

    @method_decorator(
        permission_required("leave.view_leavetype", raise_exception=True),
        name="dispatch",
    )
    def get(self, request, pk):
        leave_type = self.get_leave_type(pk)
        serializer = LeaveTypeGetCreateSerilaizer(leave_type)
        return Response(serializer.data, status=200)

    @method_decorator(
        permission_required("leave.change_leavetype", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        leave_type = self.get_leave_type(pk)
        serializer = LeaveTypeGetCreateSerilaizer(leave_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("leave.delete_leavetype", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        leave_type = self.get_leave_type(pk)
        leave_type.delete()
        return Response(status=201)


class LeaveAllocationRequestGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeaveAllocationRequestFilter
    queryset = LeaveAllocationRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return LeaveAllocationRequest.objects.none()
        if not self.request.user.is_authenticated:
            return LeaveAllocationRequest.objects.none()
        allocation_requests = LeaveAllocationRequest.objects.all().order_by("-id")
        return filtersubordinates(
            self.request, allocation_requests, "leave.view_leaveallocationrequest"
        )

    def get_user(self, request):
        user = request.user
        if isinstance(user, AnonymousUser):
            raise Http404("AnonymousUser")
        return user

    @manager_permission_required("leave.view_leaveallocationrequest")
    def get(self, request):
        allocation_requests = LeaveAllocationRequest.objects.all().order_by("-id")
        queryset = filtersubordinates(
            request, allocation_requests, "leave.view_leaveallocationrequest"
        )
        filterset = self.filterset_class(request.GET, queryset=queryset)
        paginator = HorillaPageNumberPagination()
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = LeaveAllocationRequestGetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data
        employee_id = self.get_user(request).employee_get.id
        if isinstance(data, QueryDict):
            data = data.dict()
        data["created_by"] = employee_id
        serializer = LeaveAllocationRequestCreateSerializer(data=data)
        if serializer.is_valid():
            allocation_request = serializer.save()
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=allocation_request.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                    verb=gettext_noop(
                        "New leave allocation request created for %(employee)s."
                    ),
                    verb_params={"employee": str(allocation_request.employee_id)},
                    icon="people-cicle",
                    redirect=f"/leave/leave-allocation-request-view?id={allocation_request.id}",
                    api_redirect=f"/api/leave/allocation-request/{allocation_request.id}/",
                )
            return Response(
                LeaveAllocationRequestGetSerializer(allocation_request).data, status=201
            )
        return Response(serializer.errors, status=400)


class LeaveAllocationRequestGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_allocation_request(self, pk):
        try:
            return LeaveAllocationRequest.objects.get(pk=pk)
        except LeaveAllocationRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    # Reading and editing your own pending request is legitimate, so these keep
    # an owner path -- but the manager branch has to name the requester rather
    # than accept anyone who manages somebody (GHSA-gc35-jfv9-r3cm). Without
    # this, any manager could read and rewrite another employee's allocation,
    # requested_days included.
    @manager_or_owner_permission_required(
        LeaveAllocationRequest, "leave.view_leaveallocationrequest"
    )
    def get(self, request, pk):
        allocation_request = self.get_leave_allocation_request(pk)
        serializer = LeaveAllocationRequestGetSerializer(allocation_request)
        return Response(serializer.data, status=200)

    @manager_or_owner_permission_required(
        LeaveAllocationRequest, "leave.change_leaveallocationrequest"
    )
    def put(self, request, pk):
        allocation_request = self.get_leave_allocation_request(pk)
        if allocation_request.status == "requested":
            serializer = LeaveAllocationRequestSerilaizer(
                allocation_request, data=request.data
            )
            if serializer.is_valid():
                allocation_request = serializer.save()
                return Response(
                    LeaveAllocationRequestGetSerializer(allocation_request).data,
                    status=201,
                )
            return Response(serializer.errors, status=400)
        raise serializers.ValidationError({"error": _("Access Denied..")})

    # Withdrawing your own request is legitimate; deleting someone else's needs
    # the permission or actually managing them.
    @manager_or_owner_permission_required(
        LeaveAllocationRequest, "leave.delete_leaveallocationrequest"
    )
    def delete(self, request, pk):
        allocation_request = self.get_leave_allocation_request(pk)
        if allocation_request.status == "requested":
            allocation_request.delete()
            return Response(status=200)
        raise serializers.ValidationError({"error": _("Access Denied..")})


class AssignLeaveGetCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AssignedLeaveFilter
    queryset = AvailableLeave.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return AvailableLeave.objects.none()
        if not self.request.user.is_authenticated:
            return AvailableLeave.objects.none()
        available_leave = AvailableLeave.objects.all().order_by("-id")
        return filtersubordinates(
            self.request, available_leave, "leave.view_availableleave"
        )

    @method_decorator(
        permission_required("leave.view_availableleave", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        available_leave = AvailableLeave.objects.all().order_by("-id")
        queryset = filtersubordinates(
            request, available_leave, "leave.view_availableleave"
        )
        filterset = self.filterset_class(request.GET, queryset=queryset)
        paginator = HorillaPageNumberPagination()
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = AssignLeaveGetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(
        permission_required("leave.add_availableleave", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        serializer = AssignLeaveCreateSerializer(data=request.data)
        if serializer.is_valid():
            employee_ids = serializer.validated_data.get("employee_ids")
            leave_type_ids = serializer.validated_data.get("leave_type_ids")
            for employee_id in employee_ids:
                for leave_type_id in leave_type_ids:
                    if not AvailableLeave.objects.filter(
                        employee_id=employee_id, leave_type_id=leave_type_id
                    ).exists():
                        AvailableLeave.objects.create(
                            employee_id=employee_id,
                            leave_type_id=leave_type_id,
                            available_days=leave_type_id.total_days,
                        )
                        with contextlib.suppress(Exception):
                            notify.send(
                                request.user.employee_get,
                                recipient=employee_id.employee_user_id,
                                verb=gettext_noop("New leave type is assigned to you"),
                                icon="people-circle",
                                redirect="/leave/user-request-view",
                                api_redirect="/api/leave/user-request/",
                            )
            return Response(status=201)
        return Response(serializer.errors, status=400)


class AssignLeaveGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_available_leave(self, pk):
        try:
            return AvailableLeave.objects.get(pk=pk)
        except AvailableLeave.DoesNotExist as e:
            raise serializers.ValidationError(e)

    @method_decorator(
        permission_required("leave.view_availableleave", raise_exception=True),
        name="dispatch",
    )
    def get(self, request, pk):
        available_leave = self.get_available_leave(pk)
        serializer = AssignLeaveGetSerializer(available_leave)
        return Response(serializer.data, status=200)

    @method_decorator(
        permission_required("leave.change_availableleave", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        available_leave = self.get_available_leave(pk)
        serializer = AvailableLeaveUpdateSerializer(available_leave, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("leave.delete_availableleave", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        available_leave = self.get_available_leave(pk)
        available_leave.delete()
        return Response(status=200)


class LeaveRequestGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeaveRequestFilter
    queryset = LeaveRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return LeaveRequest.objects.none()
        if not self.request.user.is_authenticated:
            return LeaveRequest.objects.none()
        leave_request = LeaveRequest.objects.all().order_by("-id")
        multiple_approvals = filter_conditional_leave_request(self.request)
        return (
            filtersubordinates(self.request, leave_request, "leave.view_leaverequest")
            | multiple_approvals
        )

    @manager_permission_required("leave.view_leaverequest")
    def get(self, request):
        leave_request = LeaveRequest.objects.all().order_by("-id")
        multiple_approvals = filter_conditional_leave_request(request)
        queryset = (
            filtersubordinates(request, leave_request, "leave.view_leaverequest")
            | multiple_approvals
        )
        filterset = self.filterset_class(request.GET, queryset=queryset)
        paginator = HorillaPageNumberPagination()
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = LeaveRequestGetAllSerilaizer(
            page, context={"request": request}, many=True
        )
        return paginator.get_paginated_response(serializer.data)

    @manager_permission_required("leave.add_leaverequest")
    def post(self, request):
        data = request.data
        if isinstance(data, QueryDict):
            data = data.dict()
        data["end_date"] = (
            data.get("start_date") if not data.get("end_date") else data.get("end_date")
        )
        serializer = LeaveRequestCreateUpdateSerializer(data=data)
        if serializer.is_valid():
            leave_request = serializer.save()
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=leave_request.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                    verb=gettext_noop("New leave request created for %(employee)s."),
                    verb_params={"employee": str(leave_request.employee_id)},
                    icon="people-circle",
                    redirect=f"/leave/request-view?id={leave_request.id}",
                    api_redirect=f"/api/leave/request/{leave_request.id}/",
                )
            return Response(
                LeaveRequestGetSerilaizer(
                    leave_request, context={"request": request}
                ).data,
                status=201,
            )
        return Response(serializer.errors, status=400)


class LeaveRequestGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_request(self, pk):
        try:
            return LeaveRequest.objects.get(pk=pk)
        except LeaveRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    @manager_or_owner_permission_required(LeaveRequest, "leave.view_leaverequest")
    def get(self, request, pk):
        leave_request = self.get_leave_request(pk)
        serializer = LeaveRequestGetSerilaizer(
            leave_request, context={"request": request}
        )
        return Response(serializer.data, status=200)

    @manager_or_owner_permission_required(LeaveRequest, "leave.change_leaverequest")
    def put(self, request, pk):
        leave_request = self.get_leave_request(pk)
        if leave_request.status == "requested":
            data = request.data
            if isinstance(data, QueryDict):
                data = data.dict()
            data["end_date"] = (
                data.get("start_date")
                if not data.get("end_date")
                else data.get("end_date")
            )
            serializer = LeaveRequestCreateUpdateSerializer(leave_request, data=data)
            if serializer.is_valid():
                leave_request = serializer.save()
                with contextlib.suppress(Exception):
                    notify.send(
                        request.user.employee_get,
                        recipient=leave_request.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        verb=gettext_noop("Leave request updated for %(employee)s."),
                        verb_params={"employee": str(leave_request.employee_id)},
                        icon="people-circle",
                        redirect=f"/leave/request-view?id={leave_request.id}",
                        api_redirect=f"/api/leave/request/{leave_request.id}/",
                    )
                return Response(
                    UserLeaveRequestGetSerilaizer(
                        leave_request, context={"request": request}
                    ).data,
                    status=201,
                )
            return Response(serializer.errors, status=400)
        raise serializers.ValidationError({"error": _("Access Denied..")})

    @manager_or_owner_permission_required(LeaveRequest, "leave.delete_leaverequest")
    def delete(self, request, pk):
        leave_request = self.get_leave_request(pk)
        if leave_request.status == "requested":
            leave_request.delete()
            return Response(status=200)
        raise serializers.ValidationError({"error": _("Access Denied..")})


class CompanyLeaveGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("base.view_companyleaves", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        company_leave = CompanyLeaves.objects.all().order_by("-id")
        paginator = HorillaPageNumberPagination()
        page = paginator.paginate_queryset(company_leave, request)
        serializer = CompanyLeaveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(
        permission_required("leave.add_companyleave", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        serializer = CompanyLeaveSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class CompanyLeaveGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_company_leave(self, pk):
        try:
            return CompanyLeaves.objects.get(pk=pk)
        except CompanyLeaves.DoesNotExist as e:
            raise serializers.ValidationError(e)

    @method_decorator(
        permission_required("base.view_companyleaves", raise_exception=True),
        name="dispatch",
    )
    def get(self, request, pk):
        company_leave = self.get_company_leave(pk)
        serializer = CompanyLeaveSerializer(company_leave)
        return Response(serializer.data, status=200)

    @method_decorator(
        permission_required("base.change_companyleaves", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        company_leave = self.get_company_leave(pk)
        serializer = CompanyLeaveSerializer(company_leave, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.delete_companyleaves", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        company_leave = self.get_company_leave(pk)
        company_leave.delete()
        return Response(status=200)


class HolidayGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("base.view_holidays", raise_exception=True), name="dispatch"
    )
    def get(self, request):
        holiday = Holidays.objects.all().order_by("-id")
        paginator = HorillaPageNumberPagination()
        page = paginator.paginate_queryset(holiday, request)
        serializer = HoildaySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @method_decorator(
        permission_required("base.add_holidays", raise_exception=True), name="dispatch"
    )
    def post(self, request):
        serializer = HoildaySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class HolidayGetUpdateDeleteAPIView(APIView):

    def get_holiday(self, pk):
        try:
            return Holidays.objects.get(pk=pk)
        except Holidays.DoesNotExist as e:
            raise serializers.ValidationError(e)

    @method_decorator(
        permission_required("base.view_holidays", raise_exception=True), name="dispatch"
    )
    def get(self, request, pk):
        holiday = self.get_holiday(pk)
        serializer = HoildaySerializer(holiday)
        return Response(serializer.data, status=200)

    @method_decorator(
        permission_required("base.change_holidays", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        holiday = self.get_holiday(pk)
        serializer = HoildaySerializer(holiday, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @method_decorator(
        permission_required("base.delete_holidays", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        holiday = self.get_holiday(pk)
        holiday.delete()
        return Response(status=200)


def _leave_condition_approvers(leave_request):
    """
    The managers a multiple-approval condition nominated for this request.

    They approve in sequence and are frequently neither the requester's
    reporting manager nor holders of ``leave.change_leaverequest``, so the
    scoped manager test on its own would shut the chain out.
    """
    conditional = leave_request.multiple_approvals()
    return conditional["managers"] if conditional else []


class LeaveRequestApproveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_request(self, pk):
        try:
            return LeaveRequest.objects.get(pk=pk)
        except LeaveRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def leave_approve_calculation(self, leave_request, available_leave):
        if leave_request.requested_days > available_leave.available_days:
            leave = leave_request.requested_days - available_leave.available_days
            leave_request.approved_available_days = available_leave.available_days
            available_leave.available_days = 0
            available_leave.carryforward_days = (
                available_leave.carryforward_days - leave
            )

            leave_request.approved_carryforward_days = leave
        else:
            temp = available_leave.available_days
            available_leave.available_days = temp - leave_request.requested_days
            leave_request.approved_available_days = leave_request.requested_days
        available_leave.save()

    def leave_multiple_approve(self, request, leave_request, available_leave):
        if request.user.is_superuser:
            LeaveRequestConditionApproval.objects.filter(
                leave_request_id=leave_request
            ).update(is_approved=True)
            self.leave_approve_calculation(leave_request, available_leave)
            leave_request.status = "approved"
            leave_request.save()
        else:
            conditional_requests = leave_request.multiple_approvals()
            approver = [
                manager
                for manager in conditional_requests["managers"]
                if manager.employee_user_id == request.user
            ]
            condition_approval = LeaveRequestConditionApproval.objects.filter(
                manager_id=approver[0], leave_request_id=leave_request
            ).first()
            condition_approval.is_approved = True
            condition_approval.save()
            if approver[0] == conditional_requests["managers"][-1]:
                self.leave_approve_calculation(leave_request, available_leave)
                leave_request.status = "approved"
                leave_request.save()

    @approver_permission_required(
        LeaveRequest,
        "leave.change_leaverequest",
        designated_approvers=_leave_condition_approvers,
    )
    def put(self, request, pk):
        leave_request = self.get_leave_request(pk)
        serializer = LeaveRequestApproveSerializer(leave_request, data=request.data)
        if serializer.is_valid():
            available_leave = serializer.validated_data.get("available_leave")
            if not leave_request.multiple_approvals():
                self.leave_approve_calculation(leave_request, available_leave)
                leave_request.status = "approved"
                leave_request.save()
            else:
                self.leave_multiple_approve(request, leave_request, available_leave)
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=leave_request.employee_id.employee_user_id,
                    verb=gettext_noop("Your Leave request has been approved"),
                    icon="people-circle",
                    redirect=f"/leave/user-request-view?id={leave_request.id}",
                    api_redirect=f"/api/leave/user-request/{leave_request.id}",
                )
            return Response(status=200)
        return Response(serializer.errors, status=400)


class LeaveRequestRejectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_request(self, pk):
        try:
            return LeaveRequest.objects.get(pk=pk)
        except LeaveRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def leave_calculation(self, leave_request, employee_id):
        leave_type_id = leave_request.leave_type_id
        available_leave = AvailableLeave.objects.get(
            leave_type_id=leave_type_id, employee_id=employee_id
        )
        available_leave.available_days += leave_request.approved_available_days
        available_leave.carryforward_days += leave_request.approved_carryforward_days
        available_leave.save()
        leave_request.approved_available_days = 0
        leave_request.approved_carryforward_days = 0
        leave_request.status = "rejected"
        leave_request.save()

    @approver_permission_required(
        LeaveRequest,
        "leave.change_leaverequest",
        designated_approvers=_leave_condition_approvers,
    )
    def put(self, request, pk):
        leave_request = self.get_leave_request(pk)
        employee_id = request.user.employee_get
        if leave_request.status != "rejected":
            reason = reject_reason_from(request)
            if reason:
                # The field the web reject form fills; saved by
                # leave_calculation below.
                leave_request.reject_reason = reason
            self.leave_calculation(leave_request, employee_id)
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=leave_request.employee_id.employee_user_id,
                    verb=gettext_noop("Your Leave request has been rejected"),
                    icon="people-circle",
                    redirect=f"/leave/user-request-view?id={leave_request.id}",
                    api_redirect=f"/api/leave/user-request/{leave_request.id}/",
                )
            return Response(status=200)
        raise serializers.ValidationError(_("Nothing to reject."))


class LeaveRequestCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_request(self, pk):
        try:
            return LeaveRequest.objects.get(pk=pk)
        except LeaveRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def put(self, request, pk):
        leave_request = self.get_leave_request(pk)
        if (
            leave_request.employee_id == request.user.employee_get
            and leave_request.status == "approved"
        ):
            start_date = leave_request.start_date
            curr_date = datetime.now().date()
            if start_date >= curr_date:
                leave_request.status = "cancelled"
                leave_request.save()
                return Response(status=200)
            raise serializers.ValidationError(_("Nothing to cancel."))
        raise serializers.ValidationError(_("Access Denied."))


class LeaveAllocationApproveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_allocation_request(self, pk):
        try:
            return LeaveAllocationRequest.objects.get(pk=pk)
        except LeaveAllocationRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def approve_calculations(self, leave_allocation_request):
        available_leave = AvailableLeave.objects.get_or_create(
            employee_id=leave_allocation_request.employee_id,
            leave_type_id=leave_allocation_request.leave_type_id,
        )[0]
        available_leave.available_days += leave_allocation_request.requested_days
        available_leave.save()

    # Approving credits requested_days straight onto the requester's balance,
    # so this needs a second person who actually manages them -- not
    # manager_permission_required, which passes anyone who manages anybody and
    # let a manager approve their own allocation (GHSA-gc35-jfv9-r3cm).
    @approver_permission_required(
        LeaveAllocationRequest, "leave.change_leaveallocationrequest"
    )
    def put(self, request, pk):
        leave_allocation_request = self.get_leave_allocation_request(pk)
        if leave_allocation_request.status == "requested":
            self.approve_calculations(leave_allocation_request)
            leave_allocation_request.status = "approved"
            leave_allocation_request.save()
            return Response(status=200)
        raise serializers.ValidationError(_("Access Denied."))


class LeaveAllocationRequestRejectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_allocation_request(self, pk):
        try:
            return LeaveAllocationRequest.objects.get(pk=pk)
        except LeaveAllocationRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def reject_calculation(self, leave_allocation_request):
        if leave_allocation_request.status == "approved":
            leave_type = leave_allocation_request.leave_type_id
            requested_days = leave_allocation_request.requested_days
            available_leave = AvailableLeave.objects.filter(
                leave_type_id=leave_type,
                employee_id=leave_allocation_request.employee_id,
            ).first()
            available_leave.available_days = max(
                0, available_leave.available_days - requested_days
            )
            available_leave.save()

    # Rejecting an already-approved allocation subtracts the days again, so the
    # same gate applies: an unscoped manager could zero out another employee's
    # balance. Not in the report, same decorator, same reach.
    @approver_permission_required(
        LeaveAllocationRequest, "leave.change_leaveallocationrequest"
    )
    def put(self, request, pk):
        leave_allocation_request = self.get_leave_allocation_request(pk)
        if leave_allocation_request.status != "rejected":
            self.reject_calculation(leave_allocation_request)
            leave_allocation_request.status = "rejected"
            reason = reject_reason_from(request)
            if reason:
                leave_allocation_request.reject_reason = reason
            leave_allocation_request.save()
            return Response(status=200)
        raise serializers.ValidationError(_("Access Denied."))


class LeaveRequestBulkApproveDeleteAPIview(APIView):
    permission_classes = [IsAuthenticated]

    def get_leave_requests(self, request):
        try:
            leave_request_ids = request.data.getlist("leave_request_id")
        except Exception as e:
            raise serializers.ValidationError(
                {"leave_request_id": [_("This field is required")]}
            )
        leave_requests = LeaveRequest.objects.filter(id__in=leave_request_ids).exclude(
            status__in=["reject", "cancelled", "approved"]
        )
        if leave_requests:
            return leave_requests
        raise serializers.ValidationError(_("Nothing to approve"))

    def scoped_to_caller(self, request, leave_requests, approving):
        """
        Narrow a bulk action to the requests this caller may actually act on.

        The by-pk approve and reject endpoints name their target and are scoped
        by decorator; this one takes a list of ids from the body, so the same
        rule has to be applied per record or the bulk route is simply the
        unscoped version of the endpoint next door (GHSA-97wm-28fj-g4pj).
        """
        employee = request.user.employee_get
        perm = "leave.change_leaverequest" if approving else "leave.delete_leaverequest"
        if request.user.has_perm(perm):
            return leave_requests

        allowed = []
        for leave_request in leave_requests:
            own = leave_request.employee_id == employee
            if approving:
                # Never your own, exactly as the single-record endpoint.
                if own:
                    continue
                if check_manager(
                    employee, leave_request
                ) or employee in _leave_condition_approvers(leave_request):
                    allowed.append(leave_request.pk)
            elif own or check_manager(employee, leave_request):
                allowed.append(leave_request.pk)
        return leave_requests.filter(pk__in=allowed)

    def leave_approve_calculation(self, leave_request, available_leave):
        if leave_request.requested_days > available_leave.available_days:
            leave = leave_request.requested_days - available_leave.available_days
            leave_request.approved_available_days = available_leave.available_days
            available_leave.available_days = 0
            available_leave.carryforward_days = (
                available_leave.carryforward_days - leave
            )
            leave_request.approved_carryforward_days = leave
        else:
            temp = available_leave.available_days
            available_leave.available_days = temp - leave_request.requested_days
            leave_request.approved_available_days = leave_request.requested_days
        available_leave.save()

    @manager_permission_required("leave.change_leaverequest")
    def put(self, request):
        leave_requests = self.scoped_to_caller(
            request, self.get_leave_requests(request), approving=True
        )
        for leave_request in leave_requests:
            employee_id = leave_request.employee_id
            leave_type_id = leave_request.leave_type_id
            available_leave = AvailableLeave.objects.get(
                leave_type_id=leave_type_id, employee_id=employee_id
            )
            total_available_leave = (
                available_leave.available_days + available_leave.carryforward_days
            )
            if total_available_leave >= leave_request.requested_days:
                self.leave_approve_calculation(leave_request, available_leave)
                leave_request.status = "approved"
                leave_request.save()
        return Response(status=200)

    @manager_permission_required("leave.delete_leaverequest")
    def delete(self, request):
        leave_requests = self.scoped_to_caller(
            request, self.get_leave_requests(request), approving=False
        )
        leave_requests.delete()
        return Response(status=200)


class EmployeeLeaveAllocationGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeaveAllocationRequestFilter
    queryset = LeaveAllocationRequest.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return LeaveAllocationRequest.objects.none()
        if not self.request.user.is_authenticated:
            return LeaveAllocationRequest.objects.none()
        employee = self.request.user.employee_get
        return employee.leaveallocationrequest_set.all().order_by("-id")

    def get_user(self, request):
        user = request.user
        if isinstance(user, AnonymousUser):
            raise Http404("AnonymousUser")
        return user

    def get(self, request):
        employee = self.get_user(request).employee_get
        allocation_requests = employee.leaveallocationrequest_set.all().order_by("-id")
        filterset = self.filterset_class(request.GET, queryset=allocation_requests)
        paginator = HorillaPageNumberPagination()
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = LeaveAllocationRequestGetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data
        employee_id = self.get_user(request).employee_get.id
        if isinstance(data, QueryDict):
            data = data.dict()
        data["employee_id"] = employee_id
        data["created_by"] = employee_id
        serializer = LeaveAllocationRequestCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(status=200)
        return Response(serializer.errors, status=400)


class EmployeeLeaveAllocationUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_allocation_request(self, request, pk):
        user = request.user
        if isinstance(user, AnonymousUser):
            raise Http404("AnonymousUser")
        try:
            allocation_request = LeaveAllocationRequest.objects.get(id=pk)
            if allocation_request.employee_id == user.employee_get:
                return allocation_request
        except LeaveAllocationRequest.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def put(self, request, pk):
        allocation_request = self.get_allocation_request(request, pk)
        if allocation_request.status == "requested":
            data = request.data
            employee_id = request.user.employee_get.id
            if isinstance(data, QueryDict):
                data = data.dict()
            data["employee_id"] = employee_id
            data["created_by"] = employee_id
            serializer = LeaveAllocationRequestSerilaizer(allocation_request, data=data)
            if serializer.is_valid():
                allocation_request = serializer.save()
                return Response(
                    LeaveAllocationRequestGetSerializer(allocation_request).data,
                    status=201,
                )
            return Response(serializer.errors, status=400)
        raise serializers.ValidationError({"error": _("Access Denied..")})
        return Response(status=200)

    def delete(self, request, pk):
        allocation_request = self.get_allocation_request(request, pk)
        if allocation_request.status == "requested":
            allocation_request.delete()
            return Response(status=200)
        raise serializers.ValidationError({"error": _("Access Denied..")})


class LeaveRequestedApprovedCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("leave.view_leaverequest")
    def get(self, request):
        leave_requests = LeaveRequest.objects.all()
        multiple_approvals = filter_conditional_leave_request(request)
        queryset = (
            filtersubordinates(request, leave_requests, "leave.view_leaverequest")
            | multiple_approvals
        )
        requested = queryset.filter(status="requested").count()
        approved = queryset.filter(status="approved").count()
        data = {"requested": requested, "approved": approved}
        return Response(data, status=200)


class EmployeeAvailableLeaveTypeGetAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_employee(self, pk):
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist as e:
            raise serializers.ValidationError(e)

    def get(self, request, pk):
        employee = self.get_employee(pk)
        available_leave = employee.available_leave.all()
        leave_type_ids = available_leave.values_list("leave_type_id", flat=True)
        leave_types = LeaveType.objects.filter(id__in=leave_type_ids)
        paginator = HorillaPageNumberPagination()
        page = paginator.paginate_queryset(leave_types, request)
        serializer = LeaveTypeAllGetSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class LeaveTypeGetPermissionCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("leave.add_leavetype", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        return Response(status=200)


class LeaveAllocationGetPermissionCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("leave.view_leaveallocationrequest")
    def get(self, request):
        return Response(status=200)


class LeaveRequestGetPermissionCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("leave.view_leaverequest")
    def get(self, request):
        return Response(status=200)


class LeaveAssignGetPermissionCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("leave.view_availableleave", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        return Response(status=200)


class LeavePermissionCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        leave_type = LeaveTypeGetPermissionCheckAPIView()
        leave_allocation = LeaveAllocationGetPermissionCheckAPIView()
        leave_request = LeaveRequestGetPermissionCheckAPIView()
        leave_assign = LeaveAssignGetPermissionCheckAPIView()
        perm_list = []
        try:
            if leave_type.get(request).status_code == 200:
                perm_list.append("leave_type")
        except:
            pass
        try:
            if leave_allocation.get(request).status_code == 200:
                perm_list.append("leave_allocation")
        except:
            pass
        try:
            if leave_request.get(request).status_code == 200:
                perm_list.append("leave_request")
                perm_list.append("leave_overview")
        except:
            pass
        try:
            if leave_assign.get(request).status_code == 200:
                perm_list.append("leave_assign")
        except:
            pass
        return Response({"perm_list": perm_list}, status=200)
