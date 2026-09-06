from django.db.models import ProtectedError, Q
from django.http import Http404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from employee.filters import (
    DisciplinaryActionFilter,
    DocumentRequestFilter,
    EmployeeFilter,
)
from employee.models import (
    Actiontype,
    DisciplinaryAction,
    Employee,
    EmployeeBankDetails,
    EmployeeType,
    EmployeeWorkInformation,
    Policy,
)
from employee.views import can_access_document, work_info_export, work_info_import
from horilla.decorators import owner_can_enter
from horilla_api.api_decorators.base.decorators import permission_required
from horilla_api.api_methods.employee.methods import get_next_badge_id
from horilla_documents.models import Document, DocumentRequest
from notifications.signals import notify

from ...api_decorators.base.decorators import (
    manager_or_owner_permission_required,
    manager_permission_required,
)
from ...api_decorators.employee.decorators import or_condition
from ...api_methods.base.methods import groupby_queryset, permission_based_queryset
from ...api_serializers.employee.serializers import (
    ActiontypeSerializer,
    DisciplinaryActionSerializer,
    DocumentRequestSerializer,
    DocumentSerializer,
    EmployeeBankDetailsSerializer,
    EmployeeListSerializer,
    EmployeeSelectorSerializer,
    EmployeeSerializer,
    EmployeeTypeSerializer,
    EmployeeWorkInformationSerializer,
    PolicySerializer,
)


def permission_check(request, perm):
    return request.user.has_perm(perm)


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


class EmployeeTypeAPIView(APIView):
    """
    Retrieves employee types.

    Methods:
        get(request, pk=None): Returns a single employee type if pk is provided, otherwise returns all employee types.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            employee_type = EmployeeType.objects.get(id=pk)
            serializer = EmployeeTypeSerializer(employee_type)
            return Response(serializer.data, status=200)
        employee_type = EmployeeType.objects.all()
        serializer = EmployeeTypeSerializer(employee_type, many=True)
        return Response(serializer.data, status=200)


class EmployeeAPIView(APIView):
    """
    Handles CRUD operations for employees.
    """

    filter_backends = [DjangoFilterBackend]
    filterset_class = EmployeeFilter
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        try:
            employee = Employee.objects.only(
                "id",
                "employee_first_name",
                "employee_last_name",  # include only needed fields
            ).get(pk=pk)
        except Employee.DoesNotExist:
            return Response(
                {"error": _("Employee does not exist")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # If user has global view permission
        if user.has_perm("employee.view_employee"):
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)

        # If employee is in user's subordinates
        subordinates = user.employee_get.get_subordinate_employees()
        if subordinates.filter(pk=pk).exists():
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)

        # If requesting own data
        if employee.pk == user.employee_get.id:
            serializer = EmployeeSerializer(employee)
            return Response(serializer.data)

        return Response(
            {"error": _("Permission denied")}, status=status.HTTP_403_FORBIDDEN
        )

        # paginator = PageNumberPagination()
        # if request.user.has_perm('employee.view_employee'):
        #     employees_queryset = Employee.objects.all()
        # elif request.user.employee_get.get_subordinate_employees():
        #     employees_queryset = request.user.employee_get.get_subordinate_employees()
        # else:
        #     employees_queryset = [request.user.employee_get]
        # employees_filter_queryset = self.filterset_class(
        #     request.GET, queryset=employees_queryset).qs
        # field_name = request.GET.get("groupby_field", None)
        # if field_name:
        #     url = request.build_absolute_uri()
        #     return groupby_queryset(request, url, field_name, employees_filter_queryset)
        # page = paginator.paginate_queryset(employees_filter_queryset, request)
        # serializer = EmployeeSerializer(page, many=True)
        # return paginator.get_paginated_response(serializer.data)

    @method_decorator(permission_required("employee.add_employee"))
    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        user = request.user
        employee = Employee.objects.get(pk=pk)
        if (
            employee == user.employee_get
            or employee.get_reporting_manager() == user.employee_get
            or user.has_perm("employee.change_employee")
        ):
            serializer = EmployeeSerializer(employee, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"error": _("You don't have permission")}, status=400)

    @method_decorator(permission_required("employee.delete_employee"))
    def delete(self, request, pk):
        try:
            employee = Employee.objects.get(pk=pk)
            employee.delete()
        except Employee.DoesNotExist:
            return Response(
                {"error": _("Employee does not exist")},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ProtectedError as e:
            return Response({"error": str(e)}, status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeListAPIView(APIView):
    """
    Retrieves a paginated list of employees with optional search functionality.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        search = request.query_params.get("search")

        # Start with a base queryset with only required fields
        employees_queryset = Employee.objects.only(
            "id", "employee_first_name", "employee_last_name"
        )

        # Permission-based filtering
        if user.has_perm("employee.view_employee"):
            pass  # employees_queryset is already all employees
        else:
            subordinate_qs = user.employee_get.get_subordinate_employees()
            if subordinate_qs.exists():
                employees_queryset = subordinate_qs.only(
                    "id", "employee_first_name", "employee_last_name"
                )
            else:
                employees_queryset = employees_queryset.filter(id=user.employee_get.id)

        # Apply search filter if provided
        if search:
            employees_queryset = employees_queryset.filter(
                Q(employee_first_name__icontains=search)
                | Q(employee_last_name__icontains=search)
            )

        # Paginate
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(employees_queryset, request)

        serializer = EmployeeListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class EmployeeBankDetailsAPIView(APIView):
    """
    Manage employee bank details with CRUD operations.

    Methods:
        get(request, pk=None):
            - Retrieves bank details for a specific employee if `pk` is provided.
            - Returns a paginated list of all employee bank details if `pk` is not provided.

        post(request):
            - Creates a new bank detail entry for an employee.

        put(request, pk):
            - Updates existing bank details for an employee identified by `pk`.

        delete(request, pk):
            - Deletes bank details for an employee identified by `pk`.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return EmployeeBankDetails.objects.none()
        queryset = EmployeeBankDetails.objects.all()
        user = self.request.user
        # Handle AnonymousUser during schema generation
        if not user.is_authenticated:
            return EmployeeBankDetails.objects.none()
        # checking user level permissions
        perm = "base.view_employeebankdetails"
        queryset = permission_based_queryset(user, perm, queryset)
        return queryset

    def get(self, request, pk=None):
        bank_detail = EmployeeBankDetails.objects.get(pk=pk)
        if (
            request.user.employee_get
            in [
                bank_detail.employee_id,
                bank_detail.employee_id.get_reporting_manager(),
            ]
        ) or request.user.has_perm("employee.view_employeebankdetails"):
            serializer = EmployeeBankDetailsSerializer(bank_detail)
            return Response(serializer.data)

        return Response({"message": _("No permission")}, status=400)

    @manager_or_owner_permission_required(
        EmployeeBankDetails, "employee.add_employeebankdetails"
    )
    def post(self, request):
        serializer = EmployeeBankDetailsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @manager_or_owner_permission_required(
        EmployeeBankDetails, "employee.add_employeebankdetails"
    )
    def put(self, request, pk):
        try:
            bank_detail = EmployeeBankDetails.objects.get(pk=pk)
        except EmployeeBankDetails.DoesNotExist:
            return Response(
                {"error": _("Bank details do not exist")},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = EmployeeBankDetailsSerializer(bank_detail, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @manager_permission_required("employee.change_employeebankdetails")
    def delete(self, request, pk):
        try:
            bank_detail = EmployeeBankDetails.objects.get(pk=pk)
            bank_detail.delete()
        except EmployeeBankDetails.DoesNotExist:
            return Response(
                {"error": _("Bank details do not exist")},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as E:
            return Response({"error": str(E)}, status=400)

        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeWorkInformationAPIView(APIView):
    """
    Manage employee work information with CRUD operations.

    Methods:
        get(request, pk):
            - Retrieves work information for a specific employee identified by `pk`.

        post(request):
            - Creates a new work information entry for an employee.

        put(request, pk):
            - Updates existing work information for an employee identified by `pk`.

        delete(request, pk):
            - Deletes work information for an employee identified by `pk`.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        work_info = EmployeeWorkInformation.objects.get(pk=pk)
        if (
            request.user.employee_get
            in [work_info.employee_id, work_info.reporting_manager_id]
        ) or request.user.has_perm("employee.view_employeeworkinformation"):
            serializer = EmployeeWorkInformationSerializer(work_info)
            return Response(serializer.data, status=200)
        return Response({"message": _("No permission")}, status=400)

    @manager_permission_required("employee.add_employeeworkinformation")
    def post(self, request):
        serializer = EmployeeWorkInformationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @manager_permission_required("employee.change_employeeworkinformation")
    def put(self, request, pk):
        work_info = EmployeeWorkInformation.objects.get(pk=pk)
        if (
            request.user.employee_get == work_info.reporting_manager_id
            or request.user.has_perm("employee.change_employeeworkinformation")
        ):
            serializer = EmployeeWorkInformationSerializer(
                work_info, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": _("No permission")}, status=400)

    @method_decorator(
        permission_required("employee.delete_employeeworkinformation"), name="dispatch"
    )
    def delete(self, request, pk):
        try:
            work_info = EmployeeWorkInformation.objects.get(pk=pk)
        except EmployeeWorkInformation.DoesNotExist:
            raise Http404
        work_info.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeWorkInfoExportView(APIView):
    """
    Endpoint for exporting employee work information.

    Methods:
        get(request):
            - Exports work information data based on user permissions.
    """

    permission_classes = [IsAuthenticated]

    @manager_permission_required("employee.add_employeeworkinformation")
    def get(self, request):
        return work_info_export(request)


class EmployeeWorkInfoImportView(APIView):
    """
    Endpoint for importing employee work information.

    Methods:
        get(request):
            - Handles the importing of work information data based on user permissions.
    """

    permission_classes = [IsAuthenticated]

    @manager_permission_required("employee.add_employeeworkinformation")
    def get(self, request):
        return work_info_import(request)


class EmployeeBulkUpdateView(APIView):
    """
    Endpoint for bulk updating employee and work information.

    Permissions:
        - Requires authentication and "change_employee" permission.

    Methods:
        put(request):
            - Updates multiple employees and their work information.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("employee.change_employee"), name="dispatch")
    def put(self, request):
        employee_ids = request.data.get("ids", [])
        employees = Employee.objects.filter(id__in=employee_ids)
        employee_work_info = EmployeeWorkInformation.objects.filter(
            employee_id__in=employees
        )
        employee_data = request.data.get("employee_data", {})
        work_info_data = request.data.get("employee_work_info", {})
        fields_to_remove = [
            "badge_id",
            "employee_first_name",
            "employee_last_name",
            "is_active",
            "email",
            "phone",
            "employee_bank_details__account_number",
        ]
        for field in fields_to_remove:
            employee_data.pop(field, None)
            work_info_data.pop(field, None)

        try:
            employees.update(**employee_data)
            employee_work_info.update(**work_info_data)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
        return Response({"status": "success"}, status=200)


class ActiontypeView(APIView):
    serializer_class = ActiontypeSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            action_type = object_check(Actiontype, pk)
            if action_type is None:
                return Response({"error": _("Actiontype not found")}, status=404)
            serializer = self.serializer_class(action_type)
            return Response(serializer.data, status=200)
        action_types = Actiontype.objects.all()
        paginater = PageNumberPagination()
        page = paginater.paginate_queryset(action_types, request)
        serializer = self.serializer_class(page, many=True)
        return paginater.get_paginated_response(serializer.data)

    def post(self, request):
        if permission_check(request, "employee.add_actiontype") is False:
            return Response({"error": _("No permission")}, status=401)
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def put(self, request, pk):
        if permission_check(request, "employee.change_actiontype") is False:
            return Response({"error": _("No permission")}, status=401)
        action_type = object_check(Actiontype, pk)
        if action_type is None:
            return Response({"error": _("Actiontype not found")}, status=404)
        serializer = self.serializer_class(action_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        if permission_check(request, "employee.delete_actiontype") is False:
            return Response({"error": _("No permission")}, status=401)
        action_type = object_check(Actiontype, pk)
        if action_type is None:
            return Response({"error": _("Actiontype not found")}, status=404)
        response, status_code = object_delete(Actiontype, pk)
        return Response(response, status=status_code)


class DisciplinaryActionAPIView(APIView):
    """
    Endpoint for managing disciplinary actions.

    Permissions:
        - Requires authentication.

    Methods:
        get(request, pk=None):
            - Retrieves a specific disciplinary action by `pk` or lists all disciplinary actions with optional filtering.

        post(request):
            - Creates a new disciplinary action.

        put(request, pk):
            - Updates an existing disciplinary action by `pk`.

        delete(request, pk):
            - Deletes a specific disciplinary action by `pk`.
    """

    filterset_class = DisciplinaryActionFilter
    permission_classes = [IsAuthenticated]
    queryset = DisciplinaryAction.objects.none()  # For drf-yasg schema generation

    def get_object(self, pk):
        try:
            return DisciplinaryAction.objects.get(pk=pk)
        except DisciplinaryAction.DoesNotExist:
            raise Http404

    def get(self, request, pk=None):
        if pk:
            employee = request.user.employee_get
            disciplinary_action = self.get_object(pk)
            is_manager = (
                True
                if employee.get_subordinate_employees()
                & disciplinary_action.employee_id.all()
                else False
            )
            if (
                (employee == disciplinary_action.employee_id)
                or is_manager
                or request.user.has_perm("employee.view_disciplinaryaction")
            ):
                serializer = DisciplinaryActionSerializer(disciplinary_action)
                return Response(serializer.data, status=200)
            return Response({"error": _("No permission")}, status=400)
        else:
            employee = request.user.employee_get
            is_manager = EmployeeWorkInformation.objects.filter(
                reporting_manager_id=employee
            ).exists()
            subordinates = employee.get_subordinate_employees()

            if request.user.has_perm("employee.view_disciplinaryaction"):
                queryset = DisciplinaryAction.objects.all()
            elif is_manager:
                queryset_subordinates = DisciplinaryAction.objects.filter(
                    employee_id__in=subordinates
                )
                queryset_employee = DisciplinaryAction.objects.filter(
                    employee_id=employee
                )
                queryset = queryset_subordinates | queryset_employee
            else:
                queryset = DisciplinaryAction.objects.filter(employee_id=employee)

            paginator = PageNumberPagination()
            disciplinary_actions = queryset
            disciplinary_action_filter_queryset = self.filterset_class(
                request.GET, queryset=disciplinary_actions
            ).qs
            page = paginator.paginate_queryset(
                disciplinary_action_filter_queryset, request
            )
            serializer = DisciplinaryActionSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        if permission_check(request, "employee.add_disciplinaryaction") is False:
            return Response({"error": _("No permission")}, status=401)
        serializer = DisciplinaryActionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        if permission_check(request, "employee.add_disciplinaryaction") is False:
            return Response({"error": _("No permission")}, status=401)
        disciplinary_action = self.get_object(pk)
        serializer = DisciplinaryActionSerializer(
            disciplinary_action, data=request.data
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if permission_check(request, "employee.add_disciplinaryaction") is False:
            return Response({"error": _("No permission")}, status=401)
        disciplinary_action = self.get_object(pk)
        disciplinary_action.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PolicyAPIView(APIView):
    """
    Endpoint for managing policies.

    Permissions:
        - Requires authentication.

    Methods:
        get(request, pk=None):
            - Retrieves a specific policy by `pk` or lists all policies with optional search functionality.

        post(request):
            - Creates a new policy.

        put(request, pk):
            - Updates an existing policy by `pk`.

        delete(request, pk):
            - Deletes a specific policy by `pk`.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Policy.objects.get(pk=pk)
        except Policy.DoesNotExist:
            raise Http404

    def get(self, request, pk=None):
        if pk:
            policy = self.get_object(pk)
            serializer = PolicySerializer(policy)
            return Response(serializer.data)
        else:
            search = request.GET.get("search", None)
            if search:
                policies = Policy.objects.filter(title__icontains=search)
            else:
                policies = Policy.objects.all()
            serializer = PolicySerializer(policies, many=True)
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(policies, request)
            serializer = PolicySerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        if permission_check(request, "employee.add_policy") is False:
            return Response({"error": _("No permission")}, status=401)

        serializer = PolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def put(self, request, pk):
        if permission_check(request, "employee.change_policy") is False:
            return Response({"error": _("No permission")}, status=401)
        policy = self.get_object(pk)
        serializer = PolicySerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        if permission_check(request, "employee.delete_policy") is False:
            return Response({"error": _("No permission")}, status=401)
        policy = self.get_object(pk)
        policy.delete()
        return Response(status=204)


class DocumentRequestAPIView(APIView):
    """
    Endpoint for managing document requests.

    Permissions:
        - Requires authentication.
        - Specific actions require manager-level permissions.

    Methods:
        get(request, pk=None):
            - Retrieves a specific document request by `pk` or lists all document requests with pagination.

        post(request):
            - Creates a new document request and notifies relevant employees.

        put(request, pk):
            - Updates an existing document request by `pk`.

        delete(request, pk):
            - Deletes a specific document request by `pk`.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return DocumentRequest.objects.get(pk=pk)
        except DocumentRequest.DoesNotExist:
            raise Http404

    def get(self, request, pk=None):
        if pk:
            document_request = self.get_object(pk)
            has_perm = request.user.has_perm("horilla_documents.view_documentrequest")
            is_addressee = document_request.employee_id.filter(
                id=getattr(request.user.employee_get, "id", None)
            ).exists()
            if not (has_perm or is_addressee):
                return Response(
                    {
                        "error": _(
                            "You do not have permission to view this document request."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            serializer = DocumentRequestSerializer(document_request)
            return Response(serializer.data)
        else:
            if request.user.has_perm("horilla_documents.view_documentrequest"):
                document_requests = DocumentRequest.objects.all()
            else:
                document_requests = DocumentRequest.objects.filter(
                    employee_id=request.user.employee_get
                )
            pagination = PageNumberPagination()
            page = pagination.paginate_queryset(document_requests, request)
            serializer = DocumentRequestSerializer(page, many=True)
            return pagination.get_paginated_response(serializer.data)

    @manager_permission_required("horilla_documents.add_documentrequest")
    def post(self, request):
        serializer = DocumentRequestSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            try:
                employees = [user.employee_user_id for user in obj.employee_id.all()]

                notify.send(
                    request.user.employee_get,
                    recipient=employees,
                    verb=f"{request.user.employee_get} requested a document.",
                    verb_ar=f"طلب {request.user.employee_get} مستنداً.",
                    verb_de=f"{request.user.employee_get} hat ein Dokument angefordert.",
                    verb_es=f"{request.user.employee_get} solicitó un documento.",
                    verb_fr=f"{request.user.employee_get} a demandé un document.",
                    redirect="/employee/employee-profile",
                    icon="chatbox-ellipses",
                    api_redirect=f"/api/employee/document-request/{obj.id}",
                )
            except:
                pass
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @manager_permission_required("horilla_documents.change_documentrequests")
    def put(self, request, pk):
        document_request = self.get_object(pk)
        serializer = DocumentRequestSerializer(document_request, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(permission_required("employee.delete_employee"))
    def delete(self, request, pk):
        document_request = self.get_object(pk)
        document_request.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentAPIView(APIView):
    filterset_class = DocumentRequestFilter
    permission_classes = [IsAuthenticated]
    queryset = Document.objects.none()  # For drf-yasg schema generation

    def get_object(self, pk, request=None):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            raise Http404
        if request is not None and not can_access_document(
            request, document, "horilla_documents.view_document"
        ):
            raise PermissionDenied
        return document

    def get(self, request, pk=None):
        if pk:
            document = self.get_object(pk, request)
            serializer = DocumentSerializer(document)
            return Response(serializer.data)
        else:
            employee = request.user.employee_get
            if request.user.has_perm("horilla_documents.view_document"):
                documents = Document.objects.all()
            else:
                managed_ids = Employee.objects.filter(
                    employee_work_info__reporting_manager_id=employee
                ).values_list("id", flat=True)
                documents = Document.objects.filter(
                    employee_id__in=list(managed_ids) + [employee.id]
                )
            document_requests_filtered = self.filterset_class(
                request.GET, queryset=documents
            ).qs
            paginator = PageNumberPagination()
            page = paginator.paginate_queryset(document_requests_filtered, request)
            serializer = DocumentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

    @manager_or_owner_permission_required(
        DocumentRequest, "horilla_documents.add_document"
    )
    def post(self, request):
        serializer = DocumentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            try:
                notify.send(
                    request.user.employee_get,
                    recipient=request.user.employee_get.get_reporting_manager().employee_user_id,
                    verb=f"{request.user.employee_get} uploaded a document",
                    verb_ar=f"قام {request.user.employee_get} بتحميل مستند",
                    verb_de=f"{request.user.employee_get} hat ein Dokument hochgeladen",
                    verb_es=f"{request.user.employee_get} subió un documento",
                    verb_fr=f"{request.user.employee_get} a téléchargé un document",
                    redirect=f"/employee/employee-view/{request.user.employee_get.id}/",
                    icon="chatbox-ellipses",
                    api_redirect=f"/api/employee/documents/",
                )
            except:
                pass
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(owner_can_enter("horilla_documents.change_document", Employee))
    def put(self, request, pk):
        document = self.get_object(pk, request)
        serializer = DocumentSerializer(document, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(owner_can_enter("horilla_documents.delete_document", Employee))
    def delete(self, request, pk):
        document = self.get_object(pk)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentRequestApproveRejectView(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("horilla_documents.add_document")
    def post(self, request, id, status):
        document = Document.objects.filter(id=id).first()
        document.status = status
        document.save()
        return Response({"status": "success"}, status=200)


class DocumentBulkApproveRejectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("horilla_documents.add_document")
    def put(self, request):
        ids = request.data.get("ids", None)
        status = request.data.get("status", None)
        status_code = 200

        if ids:
            documents = Document.objects.filter(id__in=ids)
            response = []
            for document in documents:
                if not document.document:
                    status_code = 400
                    response.append({"id": document.id, "error": _("No documents")})
                    continue
                response.append({"id": document.id, "status": "success"})
                document.status = status
                document.save()
        return Response(response, status=status_code)


class EmployeeBulkArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("employee.delete_employee"))
    def post(self, request, is_active):
        ids = request.data.get("ids")
        error = []
        for employee_id in ids:
            employee = Employee.objects.get(id=employee_id)
            employee.is_active = is_active
            employee.employee_user_id.is_active = is_active
            if employee.get_archive_condition() is False:
                employee.save()
            error.append(
                {
                    "employee": str(employee),
                    "error": _("Related model found for this employee. "),
                }
            )
        return Response(error, status=200)


class EmployeeArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("employee.delete_employee"))
    def post(self, request, id, is_active):
        employee = Employee.objects.get(id=id)
        employee.is_active = is_active
        employee.employee_user_id.is_active = is_active
        response = None
        if employee.get_archive_condition() is False:
            employee.save()
        else:
            response = {
                "employee": str(employee),
                "error": employee.get_archive_condition(),
            }
        return Response(response, status=200)


class EmployeeSelectorView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = request.user.employee_get
        employees = Employee.objects.filter(employee_user_id=request.user)

        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()

        if is_manager:
            employees = Employee.objects.filter(
                Q(pk=employee.pk) | Q(employee_work_info__reporting_manager_id=employee)
            )
        if request.user.has_perm("employee.view_employee"):
            employees = Employee.objects.all()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(employees, request)
        serializer = EmployeeSelectorSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ReportingManagerCheck(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if Employee.objects.filter(
            employee_work_info__reporting_manager_id=request.user.employee_get
        ):
            return Response(status=200)
        return Response(status=404)
