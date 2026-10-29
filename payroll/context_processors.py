"""
context_processor.py

This module is used to register context processor`
"""

from employee.models import Employee
from payroll.models import tax_models as models
from payroll.models.models import Deduction


def default_currency(request):
    """
    This method will return the currency
    """
    settings = models.PayrollSettings.for_selected_company()
    if settings is None:
        # HorillaCompanyManager scopes .objects.first() to the request's
        # current company -- a freshly created row here isn't guaranteed to
        # be visible on an immediate re-query (e.g. no company selected yet
        # for a brand new employee's very first request), so reuse this
        # instance directly instead of re-querying for it.
        settings = models.PayrollSettings()
        settings.currency_symbol = "$"
        settings.company_id = getattr(request, "selected_company_instance", None)
        settings.save()
    symbol = settings.currency_symbol
    position = settings.position
    return {
        "currency": request.session.get("currency", symbol),
        "position": request.session.get("position", position),
    }


def host(request):
    """
    This method will return the host
    """
    protocol = "https" if request.is_secure() else "http"
    return {"host": request.get_host(), "protocol": protocol}


def get_deductions(request):
    """
    This method used to return the deduction
    """
    deductions = Deduction.objects.filter(
        only_show_under_employee=False, employer_rate__gt=0
    )
    return {"get_deductions": deductions}


def get_active_employees(request):
    """
    This method used to return the deduction
    """
    employees = Employee.objects.filter(
        is_active=True, contract_set__isnull=False, payslip__isnull=False
    ).distinct()
    return {"get_active_employees": employees}
