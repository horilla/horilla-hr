import gettext
from collections import defaultdict

from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.backends import ConfiguredEmailBackend
from base.methods import eval_validate
from payroll.filters import (
    AllowanceFilter,
    ContractFilter,
    DeductionFilter,
    PayslipFilter,
)
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    LoanAccount,
    Payslip,
    Reimbursement,
)
from payroll.models.tax_models import TaxBracket
from payroll.threadings.mail import MailSendThread
from payroll.views.views import payslip_pdf

from ...api_methods.base.methods import groupby_queryset
from ...api_serializers.payroll.serializers import (
    AllowanceSerializer,
    ContractSerializer,
    DeductionSerializer,
    LoanAccountSerializer,
    PayslipSerializer,
    ReimbursementSerializer,
    TaxBracketSerializer,
)


class PayslipView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None):
        if id:
            payslip = Payslip.objects.filter(id=id).first()
            if payslip is None:
                return Response({"detail": "Not found."}, status=404)
            if (
                request.user.has_perm("payroll.view_payslip")
                or payslip.employee_id == request.user.employee_get
            ):
                serializer = PayslipSerializer(payslip)
                return Response(serializer.data, status=200)
            return Response({"detail": _("Permission denied.")}, status=403)
        if request.user.has_perm("payroll.view_payslip"):
            payslips = Payslip.objects.all()
        else:
            payslips = Payslip.objects.filter(
                employee_id__employee_user_id=request.user
            )

        payslip_filter_queryset = PayslipFilter(request.GET, payslips).qs
        # groupby workflow
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, payslip_filter_queryset)
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(payslip_filter_queryset, request)
        serializer = PayslipSerializer(page, many=True)
        return pagination.get_paginated_response(serializer.data)


class PayslipDownloadView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        if request.user.has_perm("payroll.view_payslip"):
            return payslip_pdf(request, id)

        if Payslip.objects.filter(id=id, employee_id=request.user.employee_get):
            return payslip_pdf(request, id)
        else:
            raise Response({"error": _("You don't have permission")})


class PayslipSendMailView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.add_payslip"))
    def post(self, request):
        email_backend = ConfiguredEmailBackend()
        if not getattr(
            email_backend, "dynamic_username_with_display_name", None
        ) or not len(email_backend.dynamic_username_with_display_name):
            return Response({"error": _("Email server is not configured")}, status=400)

        payslip_ids = request.data.get("id", [])
        payslips = Payslip.objects.filter(id__in=payslip_ids)
        result_dict = defaultdict(
            lambda: {"employee_id": None, "instances": [], "count": 0}
        )

        for payslip in payslips:
            employee_id = payslip.employee_id
            result_dict[employee_id]["employee_id"] = employee_id
            result_dict[employee_id]["instances"].append(payslip)
            result_dict[employee_id]["count"] += 1
        mail_thread = MailSendThread(request, result_dict=result_dict, ids=payslip_ids)
        mail_thread.start()
        return Response({"status": "success"}, status=200)


class ContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None):
        if id:
            if request.user.has_perm("payroll.view_contract"):
                contract = Contract.objects.filter(id=id).first()
            else:
                contract = Contract.objects.filter(
                    id=id, employee_id=request.user.employee_get
                ).first()
            if not contract:
                return Response({"error": _("Contract not found.")}, status=404)
            serializer = ContractSerializer(contract)
            return Response(serializer.data, status=200)
        if request.user.has_perm("payroll.view_contract"):
            contracts = Contract.objects.all()
        else:
            contracts = Contract.objects.filter(employee_id=request.user.employee_get)
        filter_queryset = ContractFilter(request.GET, contracts).qs
        # groupby workflow
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filter_queryset)
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(filter_queryset, request)
        serializer = ContractSerializer(page, many=True)
        return pagination.get_paginated_response(serializer.data)

    @method_decorator(permission_required("payroll.add_contract"))
    def post(self, request):
        serializer = ContractSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.change_contract"))
    def put(self, request, pk):
        contract = Contract.objects.get(id=pk)
        serializer = ContractSerializer(instance=contract, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_contract"))
    def delete(self, request, pk):
        contract = Contract.objects.get(id=pk)
        contract.delete()
        return Response({"status": "deleted"}, status=200)


class AllowanceView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.view_allowance"))
    def get(self, request, pk=None):
        if pk:
            allowance = Allowance.objects.get(id=pk)
            serializer = AllowanceSerializer(instance=allowance)
            return Response(serializer.data, status=200)
        allowance = Allowance.objects.all()
        filter_queryset = AllowanceFilter(request.GET, allowance).qs
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(filter_queryset, request)
        serializer = AllowanceSerializer(page, many=True)
        return pagination.get_paginated_response(serializer.data)

    @method_decorator(permission_required("payroll.add_allowance"))
    def post(self, request):
        serializer = AllowanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.change_allowance"))
    def put(self, request, pk):
        contract = Allowance.objects.get(id=pk)
        serializer = AllowanceSerializer(instance=contract, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_allowance"))
    def delete(self, request, pk):
        contract = Allowance.objects.get(id=pk)
        contract.delete()
        return Response({"status": "deleted"}, status=200)


class DeductionView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.view_deduction"))
    def get(self, request, pk=None):
        if pk:
            deduction = Deduction.objects.get(id=pk)
            serializer = DeductionSerializer(instance=deduction)
            return Response(serializer.data, status=200)
        deduction = Deduction.objects.all()
        filter_queryset = DeductionFilter(request.GET, deduction).qs
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(filter_queryset, request)
        serializer = DeductionSerializer(page, many=True)
        return pagination.get_paginated_response(serializer.data)

    @method_decorator(permission_required("payroll.add_deduction"))
    def post(self, request):
        serializer = DeductionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.change_deduction"))
    def put(self, request, pk):
        contract = Deduction.objects.get(id=pk)
        serializer = DeductionSerializer(instance=contract, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_deduction"))
    def delete(self, request, pk):
        contract = Deduction.objects.get(id=pk)
        contract.delete()
        return Response({"status": "deleted"}, status=200)


class LoanAccountView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.add_loanaccount"))
    def post(self, request):
        serializer = LoanAccountSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.view_loanaccount"))
    def get(self, request, pk=None):
        if pk:
            loan_account = LoanAccount.objects.get(id=pk)
            serializer = LoanAccountSerializer(instance=loan_account)
            return Response(serializer.data, status=200)
        loan_accounts = LoanAccount.objects.all()
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(loan_accounts, request)
        serializer = LoanAccountSerializer(page, many=True)
        return pagination.get_paginated_response(serializer.data)

    @method_decorator(permission_required("payroll.change_loanaccount"))
    def put(self, request, pk):
        loan_account = LoanAccount.objects.get(id=pk)
        serializer = LoanAccountSerializer(loan_account, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_loanaccount"))
    def delete(self, request, pk):
        loan_account = LoanAccount.objects.get(id=pk)
        loan_account.delete()
        return Response(status=200)


class ReimbursementView(APIView):
    serializer_class = ReimbursementSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            if request.user.has_perm("payroll.view_reimbursement"):
                reimbursement = Reimbursement.objects.filter(id=pk).first()
            else:
                reimbursement = Reimbursement.objects.filter(
                    id=pk, employee_id=request.user.employee_get
                ).first()
            if not reimbursement:
                return Response({"error": _("Reimbursement not found.")}, status=404)
            serializer = self.serializer_class(reimbursement)
            return Response(serializer.data, status=200)
        reimbursements = Reimbursement.objects.all()

        if request.user.has_perm("payroll.view_reimbursement"):
            reimbursements = Reimbursement.objects.all()
        else:
            reimbursements = Reimbursement.objects.filter(
                employee_id=request.user.employee_get
            )
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(reimbursements, request)
        serializer = self.serializer_class(page, many=True)
        return pagination.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if not request.user.has_perm("payroll.add_reimbursement"):
            data["employee_id"] = request.user.employee_get.id
        serializer = self.serializer_class(data=data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.change_reimbursement"))
    def put(self, request, pk):
        reimbursement = Reimbursement.objects.get(id=pk)
        serializer = self.serializer_class(instance=reimbursement, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_reimbursement"))
    def delete(self, request, pk):
        reimbursement = Reimbursement.objects.get(id=pk)
        reimbursement.delete()
        return Response(status=200)


class ReimbusementApproveRejectView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.change_reimbursement"))
    def post(self, request, pk):
        reimbursement = Reimbursement.objects.filter(id=pk).first()
        if reimbursement is None:
            return Response({"error": "Not found"}, status=404)

        # Validated against the model's own choices. The previous version wrote
        # request.data["status"] through queryset.update(), which skips model
        # validation entirely, so any string could be stored in the status
        # column -- including one no view knows how to display. Read off the
        # field rather than a constant so this cannot drift from the model.
        status = request.data.get("status")
        valid_statuses = dict(Reimbursement._meta.get_field("status").choices)
        if status not in valid_statuses:
            return Response(
                {"error": f"status must be one of {sorted(valid_statuses)}"},
                status=400,
            )

        # The claimed amount is NOT taken from the approval request for an
        # ordinary reimbursement. It is set when the claim is filed and is what
        # the approver is reviewing; letting the approve call rewrite it means
        # an approved claim need not resemble the one submitted, and nothing
        # records the original figure. Reported alongside GHSA-56x4-6268-vg4f,
        # whose primary finding -- no permission check here at all -- was fixed
        # separately.
        #
        # Encashments are the deliberate exception: their payout is computed at
        # approval time rather than claimed up front. This mirrors
        # payroll.views.component_views.approve_reimbursements, which applies
        # the same rule to the web flow.
        if reimbursement.type in ("leave_encashment", "bonus_encashment"):
            raw_amount = request.data.get("amount")
            if raw_amount:
                try:
                    reimbursement.amount = max(0, eval_validate(raw_amount))
                except (ValueError, SyntaxError):
                    return Response({"error": "amount must be a number"}, status=400)

        reimbursement.status = status
        # save(), not queryset.update(): update() bypasses model validation and
        # the modified_by bookkeeping in HorillaModel.save().
        reimbursement.save()
        return Response({"status": reimbursement.status}, status=200)


class TaxBracketView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(permission_required("payroll.view_taxbracket"))
    def get(self, request, pk=None):
        if pk:
            tax_bracket = TaxBracket.find(pk)
            serializer = TaxBracketSerializer(tax_bracket)
            return Response(serializer.data, status=200)
        tax_brackets = TaxBracket.objects.all()
        serializer = TaxBracketSerializer(instance=tax_brackets, many=True)
        return Response(serializer.data, status=200)

    @method_decorator(permission_required("payroll.add_taxbracket"))
    def post(self, request):
        serializer = TaxBracketSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.change_taxbracket"))
    def put(self, request, pk):
        tax_bracket = TaxBracket.objects.get(id=pk)
        serializer = TaxBracketSerializer(
            instance=tax_bracket, data=request.data, partial=True
        )
        if serializer.save():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @method_decorator(permission_required("payroll.delete_taxbracket"))
    def delete(self, request, pk):
        tax_bracket = TaxBracket.objects.get(id=pk)
        tax_bracket.delete()
        return Response(status=200)


from datetime import datetime

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.authentication import SessionAuthentication

# DRF / Simple JWT imports
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from horilla_api.authentication import TenantScopedJWTAuthentication

# Your models / helpers
from payroll.models.models import Company, EmployeeWorkInformation
from payroll.models.tax_models import PayrollSettings
from payroll.views.component_views import filter_payslip
from payroll.views.views import equalize_lists_length

try:
    import pdfkit

    HAVE_PDFKIT = True
except Exception:
    HAVE_PDFKIT = False


class PayslipPDFAPIView(APIView):
    """
    GET /api/payslip/<payslip_id>/?format=pdf
    Auth:
      - Accepts SimpleJWT Bearer token (Authorization: Bearer <token>)
      - Also accepts session auth (browser) when available
    """

    authentication_classes = (TenantScopedJWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request, id, format=None):
        # get payslip or 404
        payslip = get_object_or_404(Payslip, id=id)

        # authorization: same logic as your view
        user = request.user
        if not (
            user.has_perm("payroll.view_payslip")
            or payslip.employee_id.employee_user_id == user
        ):
            return Response(
                {"detail": _("You do not have permission to view this payslip.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        # employee & company date format resolution
        employee = user.employee_get  # keep same accessor you used
        info = EmployeeWorkInformation.objects.filter(employee_id=employee)
        if info.exists():
            # take the last one (mirrors your loop behavior)
            employee_company = info.last().company_id
            emp_company = Company.objects.filter(company=employee_company).first()
            date_format = (
                emp_company.date_format
                if emp_company and emp_company.date_format
                else "MMM. D, YYYY"
            )
        else:
            date_format = "MMM. D, YYYY"

        # compose data from payslip (same as original)
        data = (
            payslip.pay_head_data.copy()
            if isinstance(payslip.pay_head_data, dict)
            else {}
        )
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")

        if not start_date_str or not end_date_str:
            return Response(
                {"detail": _("Payslip missing start_date or end_date")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # parse dates
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        month_start_name = start_date.strftime("%B %d, %Y")
        month_end_name = end_date.strftime("%B %d, %Y")

        # formatted date for chosen company format (safe default if not found)
        formatted_start_date = start_date.strftime(
            settings.HORILLA_DATE_FORMATS.get(date_format, "%b. %d, %Y")
        )
        formatted_end_date = end_date.strftime(
            settings.HORILLA_DATE_FORMATS.get(date_format, "%b. %d, %Y")
        )

        # fill template context like original view
        data["month_start_name"] = month_start_name
        data["month_end_name"] = month_end_name
        data["formatted_start_date"] = formatted_start_date
        data["formatted_end_date"] = formatted_end_date
        data["employee"] = payslip.employee_id
        data["payslip"] = payslip
        data["json_data"] = data.copy()
        data["json_data"]["employee"] = payslip.employee_id.id
        data["json_data"]["payslip"] = payslip.id
        data["instance"] = payslip
        data["currency"] = (
            PayrollSettings.objects.first().currency_symbol
            if PayrollSettings.objects.exists()
            else "₹"
        )
        data["all_deductions"] = []
        for deduction_list in [
            data.get("basic_pay_deductions", []),
            data.get("gross_pay_deductions", []),
            data.get("pretax_deductions", []),
            data.get("post_tax_deductions", []),
            data.get("tax_deductions", []),
            data.get("net_deductions", []),
        ]:
            data["all_deductions"].extend(deduction_list)

        data["all_allowances"] = data.get("allowances", []).copy()
        # equalize lengths (your helper)
        equalize_lists_length(data.setdefault("allowances", []), data["all_deductions"])
        data["zipped_data"] = zip(data["allowances"], data["all_deductions"])
        data["host"] = request.get_host()
        data["protocol"] = "https" if request.is_secure() else "http"
        data["company"] = Company.objects.filter(hq=True).first()

        # render HTML string using template
        html = render_to_string(
            "payroll/payslip/payslip_pdf.html", context=data, request=request
        )

        # If client asked for PDF and pdfkit is available -> return PDF
        requested_format = request.GET.get("format", "").lower()
        if requested_format == "pdf":
            if not HAVE_PDFKIT:
                return Response(
                    {
                        "detail": _(
                            "PDF generation not available on server. Install pdfkit/wkhtmltopdf."
                        )
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            try:
                # optional: configure pdfkit with path if needed
                pdf_options = {
                    "enable-local-file-access": None,  # if your template references local CSS
                }
                pdf_bytes = pdfkit.from_string(html, False, options=pdf_options)
                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = f'inline; filename="payslip-{id}.pdf"'
                return response
            except Exception as e:
                return Response(
                    {"detail": f"PDF generation failed: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # default: return rendered HTML (use HttpResponse so browser sees it nicely)
        return HttpResponse(html)
