"""
End-to-end tests of the SCIM API through the full middleware stack, using
the request shapes Okta and Microsoft Entra ID actually send.
"""

import json

from django.test import Client, TestCase

from base.models import Department
from employee.models import Employee, EmployeeWorkInformation
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser
from horilla_identity.models import ExternalIdentity
from horilla_scim.models import ScimEvent, ScimProvider, ScimToken
from horilla_scim.schemas import CORE_USER, ENTERPRISE_USER, PATCH_OP

BASE = "/scim/v2"


def user_doc(user_name="ann@acme.test", **overrides):
    doc = {
        "schemas": [CORE_USER, ENTERPRISE_USER],
        "userName": user_name,
        "externalId": "okta-123",
        "name": {"givenName": "Ann", "familyName": "Lee"},
        "emails": [{"value": user_name, "type": "work", "primary": True}],
        "active": True,
    }
    doc.update(overrides)
    return doc


def patch_doc(*operations):
    return {"schemas": [PATCH_OP], "Operations": list(operations)}


class ScimTestCase(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.provider = ScimProvider.objects.create(company=self.company, name="Okta")
        _token, self.raw_token = ScimToken.issue(self.provider)
        self.client = Client()

    def call(
        self, method, path, body=None, token=None, content_type="application/scim+json"
    ):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token or self.raw_token}"}
        kwargs = {}
        if body is not None:
            kwargs = {"data": json.dumps(body), "content_type": content_type}
        return getattr(self.client, method)(BASE + path, **kwargs, **headers)

    def create_user(self, **overrides):
        response = self.call("post", "/Users", user_doc(**overrides))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def employee(self, email="ann@acme.test"):
        return (
            Employee.objects.entire()
            .select_related("employee_user_id")
            .get(email=email)
        )


class AuthTests(ScimTestCase):
    def test_missing_token_is_401(self):
        response = self.client.get(BASE + "/Users")
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_is_401(self):
        response = self.call("get", "/Users", token="hscim_nope")
        self.assertEqual(response.status_code, 401)

    def test_revoked_token_is_401(self):
        token = ScimToken.objects.get()
        token.revoked_at = token.created_at
        token.save()
        self.assertEqual(self.call("get", "/Users").status_code, 401)

    def test_disabled_provider_is_401(self):
        self.provider.is_enabled = False
        self.provider.save()
        self.assertEqual(self.call("get", "/Users").status_code, 401)

    def test_other_company_token_cannot_see_users(self):
        created = self.create_user()
        other = ScimProvider.objects.create(
            company=make_company("Globex"), name="Entra"
        )
        _t, other_raw = ScimToken.issue(other)
        response = self.call("get", f"/Users/{created['id']}", token=other_raw)
        self.assertEqual(response.status_code, 404)
        listing = self.call("get", "/Users", token=other_raw).json()
        self.assertEqual(listing["totalResults"], 0)

    def test_requests_are_logged(self):
        self.call("get", "/Users")
        self.assertEqual(ScimEvent.objects.filter(provider=self.provider).count(), 1)


class DiscoveryTests(ScimTestCase):
    def test_service_provider_config(self):
        body = self.call("get", "/ServiceProviderConfig").json()
        self.assertTrue(body["patch"]["supported"])
        self.assertFalse(body["bulk"]["supported"])

    def test_resource_types_and_schemas(self):
        self.assertEqual(self.call("get", "/ResourceTypes").json()["totalResults"], 1)
        self.assertEqual(self.call("get", "/Schemas").json()["totalResults"], 2)
        self.assertEqual(self.call("get", f"/Schemas/{CORE_USER}").status_code, 200)


class CreateTests(ScimTestCase):
    def test_creates_employee_in_provider_company(self):
        body = self.create_user()
        employee = self.employee()
        self.assertEqual(employee.employee_first_name, "Ann")
        self.assertEqual(employee.employee_last_name, "Lee")
        self.assertFalse(employee.employee_user_id.is_new_employee)
        info = EmployeeWorkInformation.objects.entire().get(employee_id=employee)
        self.assertEqual(info.company_id, self.company)
        self.assertEqual(body["userName"], "ann@acme.test")
        self.assertEqual(body["externalId"], "okta-123")
        self.assertTrue(body["active"])
        self.assertTrue(body["meta"]["location"].endswith(f"/Users/{body['id']}"))

    def test_accepts_plain_json_content_type(self):
        response = self.call(
            "post", "/Users", user_doc(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)

    def test_duplicate_is_409(self):
        self.create_user()
        response = self.call("post", "/Users", user_doc())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["scimType"], "uniqueness")

    def test_existing_employee_of_same_company_is_adopted(self):
        existing = make_employee(company=self.company, email="ann@acme.test")
        body = self.create_user()
        self.assertEqual(
            Employee.objects.entire().filter(email="ann@acme.test").count(), 1
        )
        identity = ExternalIdentity.objects.get(subject=body["id"])
        self.assertEqual(identity.user_id, existing.employee_user_id_id)
        self.assertEqual(self.employee().employee_user_id.username, "ann@acme.test")

    def test_existing_employee_of_other_company_is_409(self):
        make_employee(company=make_company("Globex"), email="ann@acme.test")
        response = self.call("post", "/Users", user_doc())
        self.assertEqual(response.status_code, 409)

    def test_adoption_can_be_switched_off(self):
        self.provider.match_existing_by_email = False
        self.provider.save()
        make_employee(company=self.company, email="ann@acme.test")
        self.assertEqual(self.call("post", "/Users", user_doc()).status_code, 409)

    def test_superuser_cannot_be_adopted(self):
        admin = make_user("root", email="root@acme.test", is_superuser=True)
        make_employee(company=self.company, email="root@acme.test", user=admin)
        response = self.call("post", "/Users", user_doc("root@acme.test"))
        self.assertEqual(response.status_code, 403)

    def test_missing_username_is_400(self):
        doc = user_doc()
        del doc["userName"]
        self.assertEqual(self.call("post", "/Users", doc).status_code, 400)

    def test_department_and_title_resolved_by_name(self):
        department = Department.objects.create(department="Engineering")
        department.company_id.add(self.company)
        doc = user_doc(
            **{ENTERPRISE_USER: {"department": "engineering", "employeeNumber": "E-1"}}
        )
        self.call("post", "/Users", doc)
        employee = self.employee()
        self.assertEqual(employee.badge_id, "E-1")
        info = EmployeeWorkInformation.objects.entire().get(employee_id=employee)
        self.assertEqual(info.department_id, department)


class ReadTests(ScimTestCase):
    def test_filter_by_username(self):
        created = self.create_user()
        self.create_user(user_name="bob@acme.test", externalId="okta-456")
        body = self.call(
            "get", "/Users?filter=userName%20eq%20%22ANN@acme.test%22"
        ).json()
        self.assertEqual(body["totalResults"], 1)
        self.assertEqual(body["Resources"][0]["id"], created["id"])

    def test_filter_by_external_id(self):
        self.create_user()
        body = self.call("get", "/Users?filter=externalId%20eq%20%22okta-123%22").json()
        self.assertEqual(body["totalResults"], 1)

    def test_unsupported_filter_is_400(self):
        response = self.call("get", "/Users?filter=name.givenName%20co%20%22A%22")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidFilter")

    def test_pagination(self):
        for index in range(3):
            self.create_user(user_name=f"u{index}@acme.test", externalId=str(index))
        body = self.call("get", "/Users?startIndex=2&count=1").json()
        self.assertEqual(body["totalResults"], 3)
        self.assertEqual(body["itemsPerPage"], 1)
        self.assertEqual(body["startIndex"], 2)

    def test_unknown_id_is_404(self):
        self.assertEqual(self.call("get", "/Users/nope").status_code, 404)


class UpdateTests(ScimTestCase):
    def test_okta_deactivate_cuts_login_and_archives(self):
        created = self.create_user()
        response = self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc({"op": "replace", "value": {"active": False}}),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["active"])
        employee = self.employee()
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)

    def test_entra_deactivate_with_string_boolean(self):
        created = self.create_user()
        self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc({"op": "Replace", "path": "active", "value": "False"}),
        )
        self.assertFalse(self.employee().employee_user_id.is_active)

    def test_deactivated_user_cannot_log_in(self):
        created = self.create_user()
        user = self.employee().employee_user_id
        user.set_password("pw-123456")
        user.save()
        before = Client()
        before.post("/login/", {"username": "ann@acme.test", "password": "pw-123456"})
        self.assertIn("_auth_user_id", before.session)

        self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc({"op": "replace", "path": "active", "value": False}),
        )
        # The session opened before deactivation no longer gets in.
        self.assertIn("/login", before.get("/").url)
        browser = Client()
        browser.post("/login/", {"username": "ann@acme.test", "password": "pw-123456"})
        self.assertNotIn("_auth_user_id", browser.session)

    def test_reactivate(self):
        created = self.create_user()
        path = f"/Users/{created['id']}"
        self.call(
            "patch",
            path,
            patch_doc({"op": "replace", "path": "active", "value": False}),
        )
        self.call(
            "patch", path, patch_doc({"op": "replace", "path": "active", "value": True})
        )
        employee = self.employee()
        self.assertTrue(employee.is_active)
        self.assertTrue(employee.employee_user_id.is_active)

    def test_manager_deactivation_keeps_employee_active(self):
        manager = self.create_user(user_name="boss@acme.test", externalId="m")
        report = make_employee(company=self.company, email="r@acme.test")
        EmployeeWorkInformation.objects.entire().filter(employee_id=report).update(
            reporting_manager_id=self.employee("boss@acme.test")
        )
        self.call(
            "patch",
            f"/Users/{manager['id']}",
            patch_doc({"op": "replace", "path": "active", "value": False}),
        )
        employee = self.employee("boss@acme.test")
        self.assertTrue(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)
        self.assertTrue(
            ExternalIdentity.objects.get(subject=manager["id"]).pending_offboarding
        )

    def test_patch_name_and_email_with_filter_path(self):
        created = self.create_user()
        self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc(
                {"op": "replace", "path": "name.givenName", "value": "Annie"},
                {
                    "op": "replace",
                    "path": 'emails[type eq "work"].value',
                    "value": "annie@acme.test",
                },
            ),
        )
        employee = self.employee("annie@acme.test")
        self.assertEqual(employee.employee_first_name, "Annie")
        self.assertEqual(employee.employee_user_id.email, "annie@acme.test")

    def test_patch_enterprise_manager(self):
        boss = self.create_user(user_name="boss@acme.test", externalId="m")
        created = self.create_user()
        self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc(
                {
                    "op": "add",
                    "path": f"{ENTERPRISE_USER}:manager",
                    "value": {"value": boss["id"]},
                }
            ),
        )
        info = EmployeeWorkInformation.objects.entire().get(employee_id=self.employee())
        self.assertEqual(info.reporting_manager_id, self.employee("boss@acme.test"))
        body = self.call("get", f"/Users/{created['id']}").json()
        self.assertEqual(body[ENTERPRISE_USER]["manager"]["value"], boss["id"])

    def test_put_replaces_attributes(self):
        created = self.create_user()
        doc = user_doc(name={"givenName": "Ann", "familyName": "Smith"})
        response = self.call("put", f"/Users/{created['id']}", doc)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.employee().employee_last_name, "Smith")

    def test_patch_to_taken_email_is_409(self):
        make_employee(company=self.company, email="taken@acme.test")
        created = self.create_user()
        response = self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc(
                {"op": "replace", "path": "userName", "value": "taken@acme.test"},
                {
                    "op": "replace",
                    "path": 'emails[type eq "work"].value',
                    "value": "taken@acme.test",
                },
            ),
        )
        self.assertEqual(response.status_code, 409)

    def test_invalid_patch_is_400(self):
        created = self.create_user()
        response = self.call("patch", f"/Users/{created['id']}", {"Operations": []})
        self.assertEqual(response.status_code, 400)


class DeleteTests(ScimTestCase):
    def test_soft_delete_archives_and_hides_resource(self):
        created = self.create_user()
        response = self.call("delete", f"/Users/{created['id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.call("get", f"/Users/{created['id']}").status_code, 404)
        employee = self.employee()
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)

    def test_recreate_after_soft_delete_relinks_and_reactivates(self):
        created = self.create_user()
        self.call("delete", f"/Users/{created['id']}")
        again = self.create_user()
        self.assertEqual(again["id"], created["id"])
        self.assertTrue(self.employee().employee_user_id.is_active)

    def test_hard_delete_removes_employee(self):
        self.provider.delete_mode = ScimProvider.DELETE_HARD
        self.provider.save()
        created = self.create_user()
        employee = self.employee()
        # Payroll auto-creates an active contract, which (like the UI's
        # employee_delete) blocks a permanent delete.
        employee.contract_set.all().delete()
        user_id = employee.employee_user_id_id
        self.assertEqual(
            self.call("delete", f"/Users/{created['id']}").status_code, 204
        )
        self.assertFalse(HorillaUser.objects.filter(pk=user_id).exists())
        self.assertFalse(
            Employee.objects.entire().filter(email="ann@acme.test").exists()
        )

    def test_hard_delete_of_protected_employee_falls_back_to_archive(self):
        self.provider.delete_mode = ScimProvider.DELETE_HARD
        self.provider.save()
        created = self.create_user()
        self.assertTrue(
            self.employee().contract_set.filter(contract_status="active").exists()
        )
        self.assertEqual(
            self.call("delete", f"/Users/{created['id']}").status_code, 204
        )
        employee = self.employee()
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)
        self.assertEqual(self.call("get", f"/Users/{created['id']}").status_code, 404)


class SettingsViewTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.admin = make_user("root", is_superuser=True)
        make_employee(company=self.company, email="root@acme.test", user=self.admin)
        self.client = Client()

    def test_non_superuser_is_refused(self):
        user = make_user("plain")
        make_employee(company=self.company, email="plain@acme.test", user=user)
        self.client.force_login(user)
        response = self.client.get("/settings/scim-settings/")
        self.assertNotEqual(response.status_code, 200)

    def test_superuser_can_save_and_generate_token(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["selected_company"] = str(self.company.pk)
        session.save()
        response = self.client.post(
            "/settings/scim-settings/",
            {"is_enabled": "on", "name": "Okta", "delete_mode": "soft"},
        )
        self.assertEqual(response.status_code, 302)
        provider = ScimProvider.objects.get(company=self.company)

        self.client.post("/settings/scim-settings/tokens/")
        token = ScimToken.objects.get(provider=provider)
        page = self.client.get("/settings/scim-settings/")
        self.assertContains(page, token.prefix)
        # The raw token is shown exactly once.
        self.assertNotContains(
            self.client.get("/settings/scim-settings/"), "Copy it into"
        )
