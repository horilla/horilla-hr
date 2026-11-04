from django.test import TestCase

from employee.models import Employee, EmployeeWorkInformation
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser
from horilla_identity.services import provisioning
from horilla_identity.services.provisioning import ProvisioningError


class CreateEmployeeTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")

    def create(self, **overrides):
        values = {
            "company": self.company,
            "username": "Ann@Acme.test",
            "email": "Ann@Acme.test",
            "first_name": "Ann",
            "last_name": "Lee",
        }
        values.update(overrides)
        return provisioning.create_employee(**values)

    def test_creates_user_employee_and_work_info_in_company(self):
        employee = self.create()
        user = employee.employee_user_id
        self.assertEqual(user.username, "ann@acme.test")
        self.assertEqual(employee.email, "ann@acme.test")
        self.assertFalse(user.is_new_employee)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(
            user.user_permissions.filter(codename="view_ownprofile").exists()
        )
        self.assertTrue(
            user.user_permissions.filter(codename="change_ownprofile").exists()
        )
        info = EmployeeWorkInformation.objects.entire().get(employee_id=employee)
        self.assertEqual(info.company_id, self.company)

    def test_duplicate_email_in_any_company_is_rejected(self):
        make_employee(company=make_company("Other"), email="ann@acme.test")
        with self.assertRaises(ProvisioningError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, ProvisioningError.UNIQUENESS)

    def test_duplicate_username_is_rejected(self):
        make_user("ann@acme.test", email="someone@else.test")
        with self.assertRaises(ProvisioningError) as ctx:
            self.create(email="other@acme.test")
        self.assertEqual(ctx.exception.code, ProvisioningError.UNIQUENESS)


class DeactivateEmployeeTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.employee = make_employee(company=self.company, email="bob@acme.test")

    def refresh(self, employee):
        return (
            Employee.objects.entire()
            .select_related("employee_user_id")
            .get(pk=employee.pk)
        )

    def test_archives_and_cuts_login(self):
        self.assertTrue(provisioning.deactivate_employee(self.employee))
        employee = self.refresh(self.employee)
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)

    def test_manager_keeps_employee_but_loses_login(self):
        report = make_employee(company=self.company, email="report@acme.test")
        EmployeeWorkInformation.objects.entire().filter(employee_id=report).update(
            reporting_manager_id=self.employee
        )
        make_user("admin", is_superuser=True)

        self.assertFalse(provisioning.deactivate_employee(self.employee))
        employee = self.refresh(self.employee)
        self.assertTrue(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)

    def test_reactivate_restores_both_flags(self):
        provisioning.deactivate_employee(self.employee)
        provisioning.reactivate_employee(self.refresh(self.employee))
        employee = self.refresh(self.employee)
        self.assertTrue(employee.is_active)
        self.assertTrue(employee.employee_user_id.is_active)

    def test_superuser_is_never_touched(self):
        admin = make_user("root", is_superuser=True)
        employee = make_employee(
            company=self.company, email="root@acme.test", user=admin
        )
        with self.assertRaises(ProvisioningError) as ctx:
            provisioning.deactivate_employee(employee)
        self.assertEqual(ctx.exception.code, ProvisioningError.FORBIDDEN)
        self.assertTrue(HorillaUser.objects.get(pk=admin.pk).is_active)


class DeleteEmployeeTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")

    def test_deletes_user_and_employee(self):
        employee = make_employee(company=self.company, email="gone@acme.test")
        # The auto-created active payroll contract is protected, as in the UI.
        employee.contract_set.all().delete()
        user_id = employee.employee_user_id_id
        provisioning.delete_employee(employee)
        self.assertFalse(HorillaUser.objects.filter(pk=user_id).exists())
        self.assertFalse(Employee.objects.entire().filter(pk=employee.pk).exists())

    def test_protected_employee_raises(self):
        manager = make_employee(company=self.company, email="boss@acme.test")
        report = make_employee(company=self.company, email="report@acme.test")
        EmployeeWorkInformation.objects.entire().filter(employee_id=report).update(
            reporting_manager_id=manager
        )
        with self.assertRaises(ProvisioningError) as ctx:
            provisioning.delete_employee(manager)
        self.assertEqual(ctx.exception.code, ProvisioningError.PROTECTED)
