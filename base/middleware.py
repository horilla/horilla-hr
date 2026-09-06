"""
middleware.py
"""

from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from base.backends import ConfiguredEmailBackend
from base.context_processors import AllCompany, AllMyCompanies
from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company, ShiftRequest, WorkTypeRequest
from employee.models import (
    DisciplinaryAction,
    Employee,
    EmployeeBankDetails,
    EmployeeWorkInformation,
)
from horilla.horilla_middlewares import _thread_locals, set_selected_company
from horilla.methods import get_horilla_model_class
from horilla_documents.models import DocumentRequest

CACHE_KEY = "horilla_company_models_cache_key"


# class CompanyMiddleware:
#     """
#     Middleware to handle company-specific filtering for models.
#     """

#     def __init__(self, get_response):
#         self.get_response = get_response

#     def _get_company_id(self, request):
#         """
#         Retrieve the company ID from the request or session.
#         """
#         if getattr(request, "user", False) and not request.user.is_anonymous:
#             try:
#                 if com_id := request.session.get("selected_company", None):
#                     return (
#                         Company.objects.filter(id=com_id).first()
#                         if com_id != "all"
#                         else None
#                     )
#                 else:
#                     return getattr(
#                         request.user.employee_get.employee_work_info, "company_id", None
#                     )
#             except AttributeError:
#                 pass
#         return None

#     def _set_company_session(self, request, company_id):
#         """
#         Set the company session data based on the company ID.
#         """
#         try:
#             user = request.user.employee_get
#         except Exception:
#             logout(request)
#             messages.error(
#                 request,
#                 _("An employee related to this user's credentials does not exist."),
#             )
#             return redirect("login")
#         user_company_id = getattr(
#             getattr(user, "employee_work_info", None), "company_id", None
#         )
#         if company_id and request.session.get("selected_company") != "all":
#             if company_id == "all":
#                 text = "All companies"
#             elif company_id == user_company_id:
#                 text = "My Company"
#             else:
#                 text = "Other Company"

#             request.selected_company_instance = company_id
#             request.session["selected_company"] = str(company_id.id)
#             request.session["selected_company_instance"] = {
#                 "company": company_id.company,
#                 "icon": company_id.icon.url,
#                 "text": text,
#                 "id": company_id.id,
#             }
#         else:
#             request.selected_company_instance = (
#                 user_company_id
#                 if not user_company_id
#                 else Company.objects.filter(hq=True).first()
#             )
#             request.session["selected_company"] = "all"
#             all_company = AllCompany()
#             request.session["selected_company_instance"] = {
#                 "company": all_company.company,
#                 "icon": all_company.icon.url,
#                 "text": all_company.text,
#                 "id": all_company.id,
#             }

#     def _add_company_filter(self, model, company_id):
#         """
#         Add company filter to the model if applicable.
#         """
#         is_company_model = model in self._get_company_models()
#         company_field = getattr(model, "company_id", None)
#         is_horilla_manager = isinstance(model.objects, HorillaCompanyManager)
#         related_company_field = getattr(model.objects, "related_company_field", None)

#         if is_company_model:
#             if company_field:
#                 model.add_to_class("company_filter", Q(company_id=company_id))
#             elif is_horilla_manager and related_company_field:
#                 model.add_to_class(
#                     "company_filter", Q(**{related_company_field: company_id})
#                 )
#         else:
#             if company_field:
#                 model.add_to_class(
#                     "company_filter",
#                     Q(company_id=company_id) | Q(company_id__isnull=True),
#                 )
#             elif is_horilla_manager and related_company_field:
#                 model.add_to_class(
#                     "company_filter",
#                     Q(**{related_company_field: company_id})
#                     | Q(**{f"{related_company_field}__isnull": True}),
#                 )

#     def _get_company_models(self):
#         """
#         Retrieve the list of models that are company-specific.
#         """
#         company_models = cache.get(CACHE_KEY)

#         if company_models is None:
#             company_models = [
#                 Employee,
#                 ShiftRequest,
#                 WorkTypeRequest,
#                 DocumentRequest,
#                 DisciplinaryAction,
#                 EmployeeBankDetails,
#                 EmployeeWorkInformation,
#             ]

#             app_model_mappings = {
#                 "recruitment": ["recruitment", "candidate"],
#                 "leave": [
#                     "leaverequest",
#                     "restrictleave",
#                     "availableleave",
#                     "leaveallocationrequest",
#                     "compensatoryleaverequest",
#                 ],
#                 "asset": ["assetassignment", "assetrequest"],
#                 "attendance": [
#                     "attendance",
#                     "attendanceactivity",
#                     "attendanceovertime",
#                     "workrecords",
#                 ],
#                 "payroll": [
#                     "contract",
#                     "loanaccount",
#                     "payslip",
#                     "reimbursement",
#                 ],
#                 "helpdesk": ["ticket"],
#                 "offboarding": ["offboarding"],
#                 "pms": ["employeeobjective"],
#             }

#             for app_label, models in app_model_mappings.items():
#                 if apps.is_installed(app_label):
#                     company_models.extend(
#                         [get_horilla_model_class(app_label, model) for model in models]
#                     )

#             cache.set(CACHE_KEY, company_models)

#         return company_models

#     def __call__(self, request):
#         if getattr(request, "user", False) and not request.user.is_anonymous:
#             company_id = self._get_company_id(request)
#             self._set_company_session(request, company_id)

#             app_models = [
#                 model for model in apps.get_models() if model._meta.app_label in settings.APPS
#             ]
#             for model in app_models:
#                 self._add_company_filter(model, company_id)

#         response = self.get_response(request)
#         return response


class CompanyMiddleware:
    """
    Responsible ONLY for:
    • setting request context
    • deciding current company
    • storing company in contextvar
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _get_user_default_company(self, request):
        """Fallback if session has no company selected"""
        try:
            return request.user.employee_get.employee_work_info.company_id
        except Exception:
            return None

    def _get_company_obj(self, request, com_id=None):
        """
        Retrieve the company ID from the request or session.
        """
        if getattr(request, "user", False) and not request.user.is_anonymous:
            try:
                if com_id:
                    return (
                        Company.objects.filter(id=com_id).first()
                        if com_id != "all"
                        else None
                    )
                else:
                    return getattr(
                        request.user.employee_get.employee_work_info, "company_id", None
                    )
            except AttributeError:
                pass
        return None

    def _set_company_session(self, request, company_id):
        """
        Set the company session data based on the company ID.
        """
        try:
            user = request.user.employee_get
        except Exception:
            logout(request)
            messages.error(
                request,
                _("An employee related to this user's credentials does not exist."),
            )
            return redirect("login/")
        user_company_id = getattr(
            getattr(user, "employee_work_info", None), "company_id", None
        )
        if company_id and request.session.get("selected_company") != "all":
            if company_id == "all":
                text = "All companies"
            elif company_id == user_company_id:
                text = "My Company"
            else:
                text = "Other Company"

            request.selected_company_instance = company_id
            request.session["selected_company"] = str(company_id.id)
            request.session["selected_company_instance"] = {
                "company": company_id.company,
                "icon": company_id.icon.url,
                "text": text,
                "id": company_id.id,
            }
        else:
            request.selected_company_instance = (
                user_company_id
                if not user_company_id
                else Company.objects.filter(hq=True).first()
            )
            request.session["selected_company"] = "all"
            from base.auth_backends import company_scoped_active

            all_company = (
                AllMyCompanies()
                if company_scoped_active() and not request.user.is_superuser
                else AllCompany()
            )
            request.session["selected_company_instance"] = {
                "company": all_company.company,
                "icon": all_company.icon.url,
                "text": all_company.text,
                "id": all_company.id,
            }

    def _clamp_to_allowed(self, request, company_id):
        """
        With COMPANY_SCOPED_PERMISSIONS on, non-superusers may only have:
        - one of their allowed companies (assignments ∪ work-info), or
        - "all" (= All my companies) when they have 2+ *assignment* companies.

        Stale sessions pointing at a company they lost self-heal to their
        default/first allowed company.
        """
        from base.auth_backends import (
            company_scoped_active,
            get_allowed_company_ids,
            get_assigned_company_ids,
        )

        if not company_scoped_active() or request.user.is_superuser:
            return company_id

        allowed = get_allowed_company_ids(request.user)
        assigned = get_assigned_company_ids(request.user)
        if company_id == "all" and len(assigned) >= 2:
            return "all"
        try:
            if company_id and company_id != "all" and int(company_id) in allowed:
                return company_id
        except (TypeError, ValueError):
            pass

        default_company = self._get_user_default_company(request)
        if default_company and default_company.id in allowed:
            clamped = default_company.id
        elif allowed:
            # Prefer an assignment company over work-only when clamping
            prefer = assigned or allowed
            clamped = sorted(prefer)[0]
        else:
            clamped = default_company.id if default_company else None
        request.session["selected_company"] = (
            str(clamped) if clamped is not None else "all"
        )
        return clamped if clamped is not None else "all"

    def __call__(self, request):
        # ✅ make request globally accessible (safe)
        _thread_locals.request = request
        try:
            return self._handle(request)
        finally:
            # Threads are reused across requests and across tests, so a request
            # left here outlives its own lifecycle. HorillaModel.save() reads it
            # to stamp created_by/modified_by, which then point at a stale user.
            _thread_locals.request = None
            # Same lifetime problem for the company ContextVar _handle() sets:
            # HorillaCompanyManager.get_queryset() reads it on every query, so a
            # value left behind scopes whatever runs next on this thread to the
            # previous request's company. Anonymous requests happen to reset it
            # (see _handle), but nothing guarantees one runs in between.
            set_selected_company(None)

    def _handle(self, request):
        if not request.user.is_authenticated:
            set_selected_company(None)
            return self.get_response(request)

        selected_company = request.session.get("selected_company")

        # --- Determine company ---
        if selected_company == "all":
            company_id = "all"

        elif selected_company:
            company_exists = Company.objects.filter(id=selected_company).exists()
            company_id = selected_company if company_exists else None

        else:
            # First login or session expired → set user's own company
            default_company = self._get_user_default_company(request)
            if default_company:
                request.session["selected_company"] = str(default_company.id)
                company_id = default_company.id
            else:
                request.session["selected_company"] = "all"
                company_id = "all"

        # Scoped mode: clamp to allowed companies, but permit "all"
        # (= All my companies) when the user has 2+ assignments.
        company_id = self._clamp_to_allowed(request, company_id)

        # Cache allowed / assigned ids on the request for queryset filtering / writes
        from base.auth_backends import (
            company_scoped_active,
            get_allowed_company_ids,
            get_assigned_company_ids,
            get_write_company_id,
        )

        if (
            company_scoped_active()
            and not request.user.is_superuser
            and request.user.is_authenticated
        ):
            allowed = get_allowed_company_ids(request.user)
            assigned = get_assigned_company_ids(request.user)
            request.allowed_company_ids = allowed
            request.assigned_company_ids = assigned
            # All my companies → filter to assignment companies only
            request.all_my_company_ids = assigned if len(assigned) >= 2 else allowed
            request.write_company_id = (
                get_write_company_id(request.user) if company_id == "all" else None
            )
        else:
            request.allowed_company_ids = None
            request.assigned_company_ids = None
            request.all_my_company_ids = None
            request.write_company_id = None

        # ✅ Store in context
        set_selected_company(company_id)
        company_obj = self._get_company_obj(request, company_id)
        self._set_company_session(request, company_obj)

        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """
    Middleware to force password change for new employees.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        excluded_paths = ["/change-password", "/login", "/logout"]
        if request.path.rstrip("/") in excluded_paths:
            return self.get_response(request)

        if hasattr(request, "user") and request.user.is_authenticated:
            if getattr(request.user, "is_new_employee", True):
                # HTMX sub-requests that originate from the change-password page
                # (e.g. the notification button's hx-trigger="load") must be allowed
                # through. Without this, the middleware redirects those sub-requests
                # back to /change-password/, HTMX swaps the full page HTML into the
                # notification container (which contains yet another notification
                # button), and the loop repeats indefinitely.
                hx_current_url = request.headers.get("HX-Current-URL", "")
                if request.headers.get("HX-Request") and hx_current_url:
                    current_path = urlparse(hx_current_url).path.rstrip("/")
                    if current_path in excluded_paths:
                        return self.get_response(request)

                # For HTMX navigation requests coming from other pages, respond with
                # HX-Redirect so the browser performs a proper full-page navigation
                # to /change-password/ instead of swapping partial content, which
                # would leave the URL and displayed content out of sync.
                messages.warning(
                    request,
                    _("You must change your password before continuing."),
                )
                if request.headers.get("HX-Request"):
                    response = HttpResponse(status=204)
                    response["HX-Redirect"] = "/change-password/"
                    return response

                return redirect("change-password")

        return self.get_response(request)


class TwoFactorAuthMiddleware:
    """
    Middleware to enforce two-factor authentication for specific users.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        excluded_paths = [
            "/change-password",
            "/login",
            "/logout",
            "/two-factor",
            "/send-otp",
        ]

        if request.path.rstrip("/") in excluded_paths:
            return self.get_response(request)

        if settings.TWO_FACTORS_AUTHENTICATION:
            try:
                if ConfiguredEmailBackend().configuration is not None:
                    if hasattr(request, "user") and request.user.is_authenticated:
                        if not request.session.get("otp_code_verified", False):
                            return redirect("/two-factor")
                else:
                    return self.get_response(request)
            except Exception as e:
                return self.get_response(request)

        return self.get_response(request)
