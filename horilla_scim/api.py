"""
api.py

SCIM 2.0 endpoints (RFC 7644) for provisioning employees from an identity
provider. Mounted at /scim/v2/.

Tenancy: every lookup goes through ExternalIdentity rows of the calling
provider, and new employees are always placed in the provider's company.
A token can never see or change another company's employees.
"""

import logging
import re
import uuid
from urllib.parse import unquote_plus

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from base.models import Department, JobPosition
from employee.models import Employee, EmployeeWorkInformation
from horilla_identity.models import ExternalIdentity
from horilla_identity.services import provisioning
from horilla_identity.services.provisioning import ProvisioningError

from . import schemas
from .authentication import IsScimClient, ScimBearerAuthentication
from .errors import ScimError
from .filters import parse_filter
from .mapping import UNSET, parse_user, to_scim
from .models import ScimEvent, ScimProvider
from .patch import apply_patch

logger = logging.getLogger(__name__)

SCIM_MEDIA_TYPE = "application/scim+json"

_PROVISIONING_STATUS = {
    ProvisioningError.UNIQUENESS: (409, "uniqueness"),
    ProvisioningError.FORBIDDEN: (403, None),
    ProvisioningError.INVALID: (400, "invalidValue"),
    ProvisioningError.PROTECTED: (409, None),
}


# Quoted filter values (e-mails, names) are personal data; keep them out of
# the request log.
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


def _redacted_path(request):
    query = request.META.get("QUERY_STRING", "")
    if not query:
        return request.path
    return request.path + "?" + _QUOTED.sub('"***"', unquote_plus(query))


def _loggable(text):
    # PostgreSQL refuses NUL in text columns; the event must still be logged.
    return text.replace("\x00", "")


def _check_external_id(value):
    limit = ExternalIdentity._meta.get_field("external_id").max_length
    if value not in (UNSET, None) and len(value) > limit:
        raise ScimError(
            400, "invalidValue", f"'externalId' must be at most {limit} characters."
        )


class ScimJSONParser(JSONParser):
    media_type = SCIM_MEDIA_TYPE


class ScimJSONRenderer(JSONRenderer):
    media_type = SCIM_MEDIA_TYPE


class ScimView(APIView):
    authentication_classes = [ScimBearerAuthentication]
    permission_classes = [IsScimClient]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "scim"
    parser_classes = [ScimJSONParser, JSONParser]
    renderer_classes = [ScimJSONRenderer, JSONRenderer]
    # SCIM is described by its own discovery endpoints (RFC 7644 §4), not
    # the Horilla REST API's Swagger document.
    swagger_schema = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # DRF mirrors the authenticated principal onto the Django request,
        # which HorillaModel.save() reads (via thread locals) to stamp
        # created_by. A ScimClient is not a HorillaUser, so keep the Django
        # request anonymous; DRF's own request.user stays the ScimClient.
        request._request.user = AnonymousUser()

    @property
    def provider(self) -> ScimProvider:
        return self.request.user.provider

    def base_url(self):
        return self.request.build_absolute_uri("/scim/v2").rstrip("/")

    def handle_exception(self, exc):
        if isinstance(exc, ProvisioningError):
            code, scim_type = _PROVISIONING_STATUS[exc.code]
            exc = ScimError(code, scim_type, exc.message)
        elif isinstance(exc, ValidationError):
            exc = ScimError(400, "invalidValue", "; ".join(exc.messages))
        elif isinstance(exc, Http404):
            exc = ScimError(404, None, "Resource not found.")
        elif isinstance(exc, IntegrityError):
            # Two simultaneous creates of the same user pass the uniqueness
            # check together; the database refuses the second one.
            exc = ScimError(
                409, "uniqueness", "A user with this userName or e-mail already exists."
            )
        elif isinstance(exc, exceptions.ParseError):
            exc = ScimError(400, "invalidSyntax", str(exc.detail))
        elif isinstance(
            exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)
        ):
            response = super().handle_exception(exc)
            response.data = ScimError(401, None, str(exc.detail)).as_dict()
            return response
        elif isinstance(exc, exceptions.APIException):
            response = super().handle_exception(exc)
            response.data = ScimError(
                response.status_code, None, str(exc.detail)
            ).as_dict()
            return response

        if isinstance(exc, ScimError):
            return Response(exc.as_dict(), status=exc.status)
        # Anything else is a bug, but the IdP still gets a SCIM error body
        # rather than Django's HTML 500 page.
        logger.exception("Unexpected error in SCIM request")
        return Response(
            ScimError(500, None, "Internal server error.").as_dict(), status=500
        )

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        user = getattr(request, "_user", None)
        provider = getattr(user, "provider", None)
        if provider is not None:
            detail = ""
            if response.status_code >= 400 and isinstance(response.data, dict):
                detail = str(response.data.get("detail", ""))[:255]
            try:
                ScimEvent.objects.create(
                    provider=provider,
                    method=request.method,
                    path=_loggable(_redacted_path(request))[:255],
                    status=response.status_code,
                    detail=_loggable(detail),
                )
            except Exception:
                logger.exception("Could not record SCIM event")
        return response


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class ServiceProviderConfigView(ScimView):
    def get(self, request):
        return Response(schemas.service_provider_config(self.base_url()))


class ResourceTypesView(ScimView):
    def get(self, request, name=None):
        resource = schemas.user_resource_type(self.base_url())
        if name is None:
            return Response(schemas.list_response([resource], 1, 1))
        if name != "User":
            raise Http404
        return Response(resource)


class SchemasView(ScimView):
    def get(self, request, urn=None):
        documents = schemas.schemas(self.base_url())
        if urn is None:
            return Response(schemas.list_response(documents, len(documents), 1))
        for document in documents:
            if document["id"] == urn:
                return Response(document)
        raise Http404


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserMixin:
    def identities(self):
        # The identity link alone is not enough: an employee HR moved to
        # another company is no longer this provider's to see or change.
        return ExternalIdentity.objects.filter(
            source=ExternalIdentity.SOURCE_SCIM,
            provider_id=self.provider.pk,
            company_id=self.provider.company_id,
            unlinked_at__isnull=True,
            user__employee_get__employee_work_info__company_id=self.provider.company_id,
        ).select_related("user")

    def get_identity(self, scim_id):
        if "\x00" in scim_id:
            raise Http404
        identity = self.identities().filter(subject=scim_id).first()
        if identity is None:
            raise Http404
        return identity

    def employee_of(self, identity):
        employee = (
            Employee.objects.entire()
            .select_related(
                "employee_user_id",
                "employee_work_info__department_id",
                "employee_work_info__job_position_id",
                "employee_work_info__reporting_manager_id",
            )
            .filter(employee_user_id=identity.user_id)
            .first()
        )
        work_info = getattr(employee, "employee_work_info", None)
        if work_info is None or work_info.company_id_id != self.provider.company_id:
            raise Http404
        return employee

    def render_user(self, identity, employee=None):
        employee = employee or self.employee_of(identity)
        location = f"{self.base_url()}/Users/{identity.subject}"
        return to_scim(identity, employee, location)

    # -- attribute -> work info --------------------------------------------

    def resolve_work_info(self, attrs, creating, employee=None):
        company = self.provider.company
        work_info = {}

        department = None
        if attrs.department not in (UNSET, None, ""):
            department = (
                Department.objects.entire()
                .filter(department__iexact=attrs.department)
                .filter(Q(company_id=company) | Q(company_id__isnull=True))
                .first()
            )
        if department is None and creating:
            department = self.provider.default_department
        if department is not None:
            work_info["department_id"] = department
        elif not creating and attrs.department in (None, ""):
            # Explicitly cleared (PATCH remove, or replace with "").
            work_info["department_id"] = None

        position = None
        if attrs.title not in (UNSET, None, ""):
            positions = (
                JobPosition.objects.entire()
                .filter(job_position__iexact=attrs.title)
                .filter(Q(company_id=company) | Q(company_id__isnull=True))
            )
            if department is not None:
                position = positions.filter(department_id=department).first()
            position = position or positions.first()
        if position is None and creating:
            position = self.provider.default_job_position
        if position is not None:
            work_info["job_position_id"] = position
        elif not creating and attrs.title in (None, ""):
            work_info["job_position_id"] = None

        if creating:
            if self.provider.default_shift_id:
                work_info["shift_id"] = self.provider.default_shift
            if self.provider.default_employee_type_id:
                work_info["employee_type_id"] = self.provider.default_employee_type

        if attrs.manager_id is not UNSET:
            manager = None
            if attrs.manager_id:
                manager_identity = (
                    self.identities().filter(subject=attrs.manager_id).first()
                )
                if manager_identity is not None:
                    manager = (
                        Employee.objects.entire()
                        .filter(employee_user_id=manager_identity.user_id)
                        .first()
                    )
            if manager is not None and employee is not None:
                self.check_manager(employee, manager)
            # An unknown manager is ignored: IdPs often send the report
            # before the manager exists here, and resend it later.
            if manager is not None or not attrs.manager_id:
                work_info["reporting_manager_id"] = manager
        return work_info

    @staticmethod
    def check_manager(employee, manager):
        if manager.pk == employee.pk:
            raise ScimError(400, "invalidValue", "A user cannot be their own manager.")
        # Walk up from the new manager; reaching the employee means a loop.
        seen = set()
        current = manager
        while current is not None and current.pk not in seen and len(seen) < 100:
            seen.add(current.pk)
            info = (
                EmployeeWorkInformation.objects.entire()
                .filter(employee_id=current)
                .select_related("reporting_manager_id")
                .first()
            )
            current = info.reporting_manager_id if info else None
            if current is not None and current.pk == employee.pk:
                raise ScimError(
                    400,
                    "invalidValue",
                    "This manager assignment would create a reporting loop.",
                )

    def deactivate(self, identity, employee):
        # An employee HR already archived is not marked, so a later
        # "active: true" from the provider does not bring them back
        # (unless the provider is allowed to reactivate archived employees).
        if employee.is_active:
            identity.deactivated_by_provider = True
        archived = provisioning.deactivate_employee(employee)
        identity.pending_offboarding = not archived

    def apply_active(self, identity, employee, active):
        user = employee.employee_user_id
        inactive = not user.is_active or not employee.is_active
        if not inactive:
            # Someone in Horilla reactivated them since the provider
            # deactivated them, so a later archive is no longer the provider's.
            identity.deactivated_by_provider = False
        if active is UNSET:
            return
        if active is False and (user.is_active or employee.is_active):
            self.deactivate(identity, employee)
        elif active is True and (
            identity.deactivated_by_provider
            or (self.provider.reactivate_archived_employees and inactive)
        ):
            provisioning.reactivate_employee(employee)
            identity.deactivated_by_provider = False
            identity.pending_offboarding = False

    def update_from(self, identity, employee, attrs):
        _check_external_id(attrs.external_id)
        provisioning.update_employee(
            employee,
            username=None if attrs.user_name is UNSET else attrs.user_name,
            email=None if attrs.email in (UNSET, None) else attrs.email,
            first_name=(
                None if attrs.given_name in (UNSET, None, "") else attrs.given_name
            ),
            last_name=None if attrs.family_name is UNSET else (attrs.family_name or ""),
            phone=None if attrs.phone is UNSET else (attrs.phone or ""),
            badge_id=(
                None
                if attrs.employee_number is UNSET
                else (attrs.employee_number or "")
            ),
            work_info=self.resolve_work_info(attrs, creating=False, employee=employee),
        )
        if attrs.external_id is not UNSET:
            identity.external_id = attrs.external_id or ""
        self.apply_active(identity, employee, attrs.active)
        identity.save()


class UsersView(UserMixin, ScimView):
    def get(self, request):
        queryset = self.identities()
        expression = request.query_params.get("filter")
        if expression:
            queryset = queryset.filter(**parse_filter(expression))
        queryset = queryset.order_by("pk")

        try:
            start_index = max(int(request.query_params.get("startIndex", 1)), 1)
            count = int(request.query_params.get("count", schemas.MAX_RESULTS))
        except ValueError:
            raise ScimError(
                400, "invalidValue", "startIndex and count must be integers."
            )
        count = min(max(count, 0), schemas.MAX_RESULTS)

        total = queryset.count()
        # Past the end there is nothing to fetch; skipping the query also
        # keeps a huge startIndex from overflowing PostgreSQL's OFFSET.
        page = (
            list(queryset[start_index - 1 : start_index - 1 + count])
            if count and start_index <= total
            else []
        )
        resources = [self.render_user(identity) for identity in page]
        return Response(schemas.list_response(resources, total, start_index))

    @transaction.atomic
    def post(self, request):
        attrs = parse_user(request.data)
        if attrs.user_name in (UNSET, None, ""):
            raise ScimError(400, "invalidValue", "'userName' is required.")
        email = attrs.email if attrs.email not in (UNSET, None) else None
        if not email and "@" in attrs.user_name:
            email = attrs.user_name
        if not email:
            raise ScimError(400, "invalidValue", "An e-mail address is required.")
        first_name = attrs.first_name()
        _check_external_id(attrs.external_id)

        existing = Employee.objects.entire().filter(email__iexact=email).first()
        if existing is not None:
            identity, employee = self.adopt(existing, attrs)
            created = False
        else:
            employee = provisioning.create_employee(
                company=self.provider.company,
                username=attrs.user_name,
                email=email,
                first_name=first_name,
                last_name=(
                    "" if attrs.family_name in (UNSET, None) else attrs.family_name
                ),
                phone="" if attrs.phone in (UNSET, None) else attrs.phone,
                badge_id=(
                    None
                    if attrs.employee_number in (UNSET, None, "")
                    else attrs.employee_number
                ),
                work_info=self.resolve_work_info(attrs, creating=True),
            )
            identity = ExternalIdentity.objects.create(
                source=ExternalIdentity.SOURCE_SCIM,
                provider_id=self.provider.pk,
                company_id=self.provider.company_id,
                subject=str(uuid.uuid4()),
                external_id=(
                    "" if attrs.external_id in (UNSET, None) else attrs.external_id
                ),
                user=employee.employee_user_id,
            )
            self.apply_active(identity, employee, attrs.active)
            identity.save()
            created = True

        if (
            created
            and self.provider.send_invitation_email
            and attrs.active is not False
        ):
            from employee.methods.methods import send_employee_invitation

            send_employee_invitation(employee, request.get_host(), request.is_secure())

        body = self.render_user(identity)
        return Response(
            body,
            status=status.HTTP_201_CREATED,
            headers={"Location": body["meta"]["location"]},
        )

    def adopt(self, employee, attrs):
        """Link an employee that already exists in this company to the IdP."""
        work_info = getattr(employee, "employee_work_info", None)
        same_company = (
            work_info is not None
            and work_info.company_id_id == self.provider.company_id
        )
        if not (self.provider.match_existing_by_email and same_company):
            raise ScimError(
                409, "uniqueness", "An employee with this e-mail already exists."
            )
        if employee.employee_user_id is None:
            raise ScimError(
                409, "uniqueness", "The existing employee has no login account."
            )

        identity = ExternalIdentity.objects.filter(
            source=ExternalIdentity.SOURCE_SCIM,
            provider_id=self.provider.pk,
            user=employee.employee_user_id,
        ).first()
        if identity is not None and identity.unlinked_at is None:
            raise ScimError(409, "uniqueness", "This user is already provisioned.")
        if identity is None:
            identity = ExternalIdentity(
                source=ExternalIdentity.SOURCE_SCIM,
                provider_id=self.provider.pk,
                company_id=self.provider.company_id,
                subject=str(uuid.uuid4()),
                user=employee.employee_user_id,
            )
        identity.unlinked_at = None
        identity.save()

        # A user re-created after a soft delete comes back active unless the
        # IdP says otherwise. apply_active decides whether an archived
        # employee may be reactivated.
        if attrs.active is UNSET:
            attrs.active = True
        self.update_from(identity, employee, attrs)
        return identity, employee


# Attributes a PATCH "remove" may not take away.
_REQUIRED = {
    "user_name": "userName",
    "email": "emails",
    "given_name": "name.givenName",
    "active": "active",
}


class UserDetailView(UserMixin, ScimView):
    def get(self, request, scim_id):
        return Response(self.render_user(self.get_identity(scim_id)))

    @transaction.atomic
    def put(self, request, scim_id):
        """
        Update the user from a full document.

        Attributes the document leaves out are kept, not cleared. RFC 7644
        §3.5.1 describes PUT as a replacement, but Okta's PUT only carries the
        attributes mapped in the provider, so a replacement would wipe the
        title, department or manager HR maintains in Horilla. To clear an
        attribute, send it empty (or null), or PATCH "remove" it.
        """
        identity = self.get_identity(scim_id)
        employee = self.employee_of(identity)
        attrs = parse_user(request.data)
        if attrs.user_name in (UNSET, None, ""):
            raise ScimError(400, "invalidValue", "'userName' is required.")
        self.update_from(identity, employee, attrs)
        return Response(self.render_user(identity))

    @transaction.atomic
    def patch(self, request, scim_id):
        identity = self.get_identity(scim_id)
        employee = self.employee_of(identity)
        current = self.render_user(identity, employee)
        patched = apply_patch(current, request.data)

        before, after = parse_user(current), parse_user(patched)
        for name in vars(after):
            if name in ("extra", "display_name"):
                continue
            old, new = getattr(before, name), getattr(after, name)
            if name in _REQUIRED and new in (UNSET, None, ""):
                if old not in (UNSET, None, ""):
                    raise ScimError(
                        400,
                        "mutability",
                        f"'{_REQUIRED[name]}' is required and cannot be removed.",
                    )
                setattr(after, name, UNSET)
            elif new is UNSET and old is not UNSET:
                # Removed by the PATCH (RFC 7644 §3.5.2.2): clear it.
                setattr(after, name, None)
            elif new == old:
                # Only hand changed attributes to the update, so a PATCH of
                # one field cannot trip uniqueness checks or rewrite work
                # info it did not touch.
                setattr(after, name, UNSET)
        self.update_from(identity, employee, after)
        return Response(self.render_user(identity))

    @transaction.atomic
    def delete(self, request, scim_id):
        identity = self.get_identity(scim_id)
        employee = self.employee_of(identity)
        if self.provider.delete_mode == ScimProvider.DELETE_HARD:
            try:
                provisioning.delete_employee(employee)
                return Response(status=status.HTTP_204_NO_CONTENT)
            except ProvisioningError as exc:
                if exc.code != ProvisioningError.PROTECTED:
                    raise
                logger.warning(
                    "SCIM hard delete of employee %s fell back to archive: %s",
                    employee.pk,
                    exc.message,
                )
        self.deactivate(identity, employee)
        identity.unlinked_at = timezone.now()
        identity.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
