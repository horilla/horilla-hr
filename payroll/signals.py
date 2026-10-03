from datetime import datetime

from django.apps import apps
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from employee.models import Employee, EmployeeWorkInformation
from payroll.methods.deductions import create_deductions
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    EncashmentGeneralSettings,
    LoanAccount,
    Payslip,
)


@receiver(m2m_changed, sender=EncashmentGeneralSettings.employees.through)
@receiver(m2m_changed, sender=EncashmentGeneralSettings.department.through)
@receiver(m2m_changed, sender=EncashmentGeneralSettings.job_position.through)
def encashment_settings_filtered_employees(sender, instance, action, **kwargs):
    """
    Recompute EncashmentGeneralSettings.filtered_employees whenever the
    employees/department/job_position eligibility selection changes --
    mirrors Policy's targeting in base/signals.py.
    """
    if action not in ["post_add", "post_remove", "post_clear"]:
        return
    employee_ids = list(instance.employees.values_list("id", flat=True))
    department_ids = list(instance.department.values_list("id", flat=True))
    job_position_ids = list(instance.job_position.values_list("id", flat=True))

    employees = Employee.objects.filter(
        Q(id__in=employee_ids)
        | Q(employee_work_info__department_id__in=department_ids)
        | Q(employee_work_info__job_position_id__in=job_position_ids)
    )

    instance.filtered_employees.set(employees)


@receiver(post_save, sender=EmployeeWorkInformation)
def employeeworkinformation_post_save(sender, instance, **_kwargs):
    """
    This method is used to override the save method for EmployeeWorkInformation Model
    """
    # Skip during fixture load — demo contracts come from payroll_data.json
    if _kwargs.get("raw"):
        return

    active_employee = (
        instance.employee_id
        if instance.employee_id and instance.employee_id.is_active == True
        else None
    )
    if active_employee is not None:
        all_contracts = Contract.objects.entire()
        contract_exists = all_contracts.filter(employee_id_id=active_employee).exists()
        if not contract_exists:
            contract = Contract()
            contract.contract_name = f"{active_employee}'s Contract"
            contract.employee_id = active_employee
            contract.contract_start_date = (
                instance.date_joining if instance.date_joining else datetime.today()
            )
            contract.wage = (
                instance.basic_salary if instance.basic_salary is not None else 0
            )
            contract.contract_status = "active"
            contract.save()


@receiver(post_save, sender=LoanAccount)
def create_installments(sender, instance, created, **kwargs):
    """
    Post save method for loan account
    """
    # Demo fixtures carry pre-built allowance and installment relationships.
    # Rebuilding them while loaddata is running duplicates the allowance and
    # replaces the curated schedule with signal-generated records.
    if kwargs.get("raw"):
        return

    installments = []
    asset = True
    if apps.is_installed("asset"):
        asset = True if instance.asset_id is None else False

    if created and asset and instance.type != "fine":
        from payroll.methods.deductions import LOAN_PAYOUT_KEYS
        from payroll.system_components import policy_fields

        loan = Allowance()
        loan.title = instance.title
        loan.amount = instance.loan_amount
        loan.include_active_employees = False
        loan.only_show_under_employee = True
        loan.is_fixed = True
        loan.one_time_date = instance.provided_date
        loan.is_loan = True

        # Whether the payout is taxed, and whether it prorates, comes from the
        # standard component for this kind. The defaults it used to inherit
        # made a loan taxable income and prorated it by calendar days -- so a
        # mid-month joiner received a fraction of the loan they were granted.
        for field, value in policy_fields(
            LOAN_PAYOUT_KEYS.get(instance.type, "loan_payout")
        ).items():
            setattr(loan, field, value)

        loan.save()
        loan.specific_employees.add(instance.employee_id)
        instance.allowance_id = loan
        super(LoanAccount, instance).save()
    else:
        deductions = instance.deduction_ids.values_list("id", flat=True)
        payslips_with_deductions = Payslip.objects.filter(
            installment_ids__in=deductions
        )
        balance_deduction = [
            deduction_id
            for deduction_id in deductions
            if not payslips_with_deductions.filter(
                installment_ids=deduction_id
            ).exists()
        ]
        installment_dict = instance.get_installments()

        if not payslips_with_deductions and not instance.settled:
            # Nothing is paid yet, so the whole loan is still editable -
            # keep the one-time payout allowance in sync with the (possibly
            # changed) employee/amount/date/title before regenerating the
            # installment deductions below, which already follow
            # instance.employee_id via create_deductions().
            if instance.allowance_id:
                allowance = instance.allowance_id
                allowance.title = instance.title
                allowance.amount = instance.loan_amount
                allowance.one_time_date = instance.provided_date
                allowance.save()
                allowance.specific_employees.set([instance.employee_id])
            Deduction.objects.filter(id__in=deductions).delete()
            for (
                installment_date,
                installment_amount,
            ) in installment_dict.items():
                installment = create_deductions(
                    instance, installment_amount, installment_date
                )

                installments.append(installment)

            instance.deduction_ids.add(*installments)
            return

        if instance.settled:
            Deduction.objects.filter(id__in=balance_deduction).delete()

        else:
            if not balance_deduction:
                for (
                    installment_date,
                    installment_amount,
                ) in installment_dict.items():
                    if not Deduction.objects.filter(
                        one_time_date=installment_date,
                        specific_employees=instance.employee_id,
                        is_installment=True,
                        title=instance.title,
                    ).exists():
                        installment = create_deductions(
                            instance, installment_amount, installment_date
                        )

                        installments.append(installment)

                instance.deduction_ids.add(*installments)
