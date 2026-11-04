"""
End-to-end tests of the SCIM API through the full middleware stack, using
the request shapes Okta and Microsoft Entra ID actually send.
"""

import json
from datetime import timedelta
from unittest import mock
from urllib.parse import quote

from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone

from base.models import Department, JobPosition
from employee.models import Employee, EmployeeWorkInformation
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser
from horilla_identity.models import ExternalIdentity
from horilla_scim.api import _MAX_LOGGED_QUERY
from horilla_scim.filters import MAX_FILTER_LENGTH
from horilla_scim.models import ScimEvent, ScimProvider, ScimToken, hash_token
from horilla_scim.scheduler import purge_old_events
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

    def test_reset_invalidates_old_token(self):
        old_raw = self.raw_token
        _token, new_raw = ScimToken.issue(self.provider)
        self.assertEqual(ScimToken.objects.filter(provider=self.provider).count(), 1)
        self.assertEqual(self.call("get", "/Users", token=old_raw).status_code, 401)
        self.assertEqual(self.call("get", "/Users", token=new_raw).status_code, 200)

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

    def test_scheduled_purge_removes_only_old_events(self):
        self.call("get", "/Users")
        old = ScimEvent.objects.create(
            provider=self.provider, method="GET", path="/old", status=200
        )
        ScimEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        purge_old_events()
        self.assertEqual(
            list(ScimEvent.objects.values_list("path", flat=True)), ["/scim/v2/Users"]
        )

    def test_logged_filter_values_are_redacted(self):
        self.client.get(
            BASE + '/Users?filter=userName eq "ann@acme.test"&count=1',
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        path = ScimEvent.objects.get().path
        self.assertNotIn("ann@acme.test", path)
        self.assertEqual(path, '/scim/v2/Users?filter=userName eq "***"&count=1')

    def test_logged_query_is_capped_and_redacted(self):
        # An unclosed run of \" pairs made the old redaction regex quadratic.
        self.client.get(
            BASE + "/Users?filter=" + quote('"' + '\\"' * 4000),
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        path = ScimEvent.objects.get().path
        self.assertLessEqual(len(path), 255)
        self.assertEqual(path, '/scim/v2/Users?filter="***"')

    def test_only_capped_query_is_redacted(self):
        with mock.patch(
            "horilla_scim.api._redact_quoted", side_effect=lambda text: text
        ) as redact:
            self.client.get(
                BASE + "/Users?filter=" + "a" * 10000,
                HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
            )
        self.assertEqual(len(redact.call_args.args[0]), _MAX_LOGGED_QUERY)


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

    def test_filter_by_work_email_path(self):
        created = self.create_user()
        expression = 'emails[type eq "work"].value eq "ann@acme.test"'
        body = self.call("get", "/Users?filter=" + quote(expression)).json()
        self.assertEqual(body["totalResults"], 1)
        self.assertEqual(body["Resources"][0]["id"], created["id"])

    def test_filter_at_length_limit_is_parsed(self):
        self.create_user()
        expression = 'userName eq "ann@acme.test"'
        expression = " " * (MAX_FILTER_LENGTH - len(expression)) + expression
        body = self.call("get", "/Users?filter=" + quote(expression)).json()
        self.assertEqual(body["totalResults"], 1)

    def test_overlong_filter_is_400(self):
        # Long runs of spaces made the filter regex quadratic.
        expression = 'userName eq "' + " " * MAX_FILTER_LENGTH + 'x"'
        response = self.call("get", "/Users?filter=" + quote(expression))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidFilter")

    def test_filter_with_long_space_run_is_400(self):
        response = self.call("get", "/Users?filter=" + quote("a" + " " * 500 + "b"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidFilter")

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

    def test_permanent_delete_warning_follows_delete_mode(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["selected_company"] = str(self.company.pk)
        session.save()
        provider = ScimProvider.objects.create(company=self.company, name="Okta")
        warning = '<div id="scimHardDeleteWarning" class="mb-4 p-3 rounded-md bg-[#fdecec] border border-[#f1a9a9]"'

        page = self.client.get("/settings/scim-settings/")
        self.assertContains(page, warning + " hidden>")

        provider.delete_mode = ScimProvider.DELETE_HARD
        provider.save()
        page = self.client.get("/settings/scim-settings/")
        self.assertContains(page, warning + ">")
        self.assertContains(page, "Permanent delete cannot be undone")

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

        response = self.client.post("/settings/scim-settings/tokens/")
        raw = response.context["new_token"]
        self.assertContains(response, raw)
        self.assertEqual(
            ScimToken.objects.get(provider=provider).token_hash, hash_token(raw)
        )
        # Shown in the response only, never kept in the session.
        self.assertNotIn(raw, json.dumps(dict(self.client.session.items())))

        # After a reload the token is masked.
        page = self.client.get("/settings/scim-settings/")
        self.assertNotContains(page, raw)
        self.assertContains(page, "********")
        self.assertContains(page, "Reset token")

        # Reset replaces the token; there is still only one.
        reset = self.client.post("/settings/scim-settings/tokens/")
        self.assertNotEqual(reset.context["new_token"], raw)
        self.assertEqual(ScimToken.objects.filter(provider=provider).count(), 1)


class ValidationTests(ScimTestCase):
    """PostgreSQL raises DataError on over-long values, which used to be a
    500. Each case must be a SCIM 400 and leave nothing behind."""

    def assert_invalid(self, response):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["scimType"], "invalidValue")

    def assert_rejected_on_create(self, doc):
        users_before = HorillaUser.objects.count()
        self.assert_invalid(self.call("post", "/Users", doc))
        self.assertFalse(
            Employee.objects.entire().filter(email="ann@acme.test").exists()
        )
        self.assertEqual(HorillaUser.objects.count(), users_before)

    def test_long_username(self):
        self.assert_rejected_on_create(
            user_doc(
                user_name="a" * 151 + "@acme.test",
                emails=[{"value": "ann@acme.test"}],
            )
        )

    def test_long_first_name(self):
        self.assert_rejected_on_create(
            user_doc(name={"givenName": "A" * 201, "familyName": "Lee"})
        )

    def test_long_last_name(self):
        self.assert_rejected_on_create(
            user_doc(name={"givenName": "Ann", "familyName": "L" * 201})
        )

    def test_long_phone(self):
        self.assert_rejected_on_create(
            user_doc(phoneNumbers=[{"value": "1" * 26, "type": "work"}])
        )

    def test_long_employee_number(self):
        self.assert_rejected_on_create(
            user_doc(**{ENTERPRISE_USER: {"employeeNumber": "9" * 51}})
        )

    def test_long_external_id(self):
        self.assert_rejected_on_create(user_doc(externalId="x" * 256))

    def test_invalid_email(self):
        self.assert_rejected_on_create(
            user_doc(user_name="ann", emails=[{"value": "not-an-email"}])
        )

    def test_patch_with_long_name_or_bad_email(self):
        created = self.create_user()
        path = f"/Users/{created['id']}"
        self.assert_invalid(
            self.call(
                "patch",
                path,
                patch_doc(
                    {"op": "replace", "path": "name.givenName", "value": "A" * 201}
                ),
            )
        )
        self.assert_invalid(
            self.call(
                "patch",
                path,
                patch_doc(
                    {
                        "op": "replace",
                        "path": 'emails[type eq "work"].value',
                        "value": "nope",
                    }
                ),
            )
        )
        employee = self.employee()
        self.assertEqual(employee.employee_first_name, "Ann")
        self.assertEqual(employee.email, "ann@acme.test")


class ReactivationTests(ScimTestCase):
    """By default the provider only reactivates employees it deactivated."""

    def archive_in_horilla(self, employee):
        # What the employee archive view does.
        employee.is_active = False
        employee.save()
        employee.sync_login_access()

    def activate(self, scim_id):
        return self.call(
            "patch",
            f"/Users/{scim_id}",
            patch_doc({"op": "replace", "path": "active", "value": True}),
        )

    def test_patch_does_not_reactivate_employee_archived_by_hr(self):
        created = self.create_user()
        self.archive_in_horilla(self.employee())
        self.assertEqual(self.activate(created["id"]).status_code, 200)
        employee = self.employee()
        self.assertFalse(employee.is_active)
        self.assertFalse(employee.employee_user_id.is_active)

    def test_put_does_not_reactivate_employee_archived_by_hr(self):
        created = self.create_user()
        self.archive_in_horilla(self.employee())
        self.call("put", f"/Users/{created['id']}", user_doc())
        self.assertFalse(self.employee().is_active)

    def test_adopting_archived_employee_keeps_them_archived(self):
        employee = make_employee(company=self.company, email="ann@acme.test")
        self.archive_in_horilla(employee)
        self.create_user()
        self.assertFalse(self.employee().is_active)

    def test_setting_allows_reactivating_employee_archived_by_hr(self):
        self.provider.reactivate_archived_employees = True
        self.provider.save()
        created = self.create_user()
        self.archive_in_horilla(self.employee())
        self.activate(created["id"])
        employee = self.employee()
        self.assertTrue(employee.is_active)
        self.assertTrue(employee.employee_user_id.is_active)

    def test_login_disabled_in_horilla_is_not_re_enabled(self):
        created = self.create_user()
        HorillaUser.objects.filter(email="ann@acme.test").update(is_active=False)
        self.activate(created["id"])
        self.assertFalse(self.employee().employee_user_id.is_active)

    def test_setting_allows_re_enabling_login_disabled_in_horilla(self):
        self.provider.reactivate_archived_employees = True
        self.provider.save()
        created = self.create_user()
        HorillaUser.objects.filter(email="ann@acme.test").update(is_active=False)
        self.activate(created["id"])
        self.assertTrue(self.employee().employee_user_id.is_active)

    def test_hr_archive_after_hr_reactivation_is_respected(self):
        created = self.create_user()
        off = patch_doc({"op": "replace", "path": "active", "value": False})
        # The provider deactivates, HR reactivates in Horilla, the provider
        # syncs, then HR archives again: that archive is HR's, not the
        # provider's.
        self.call("patch", f"/Users/{created['id']}", off)
        employee = self.employee()
        employee.is_active = True
        employee.save()
        employee.sync_login_access()
        self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc({"op": "replace", "path": "name.givenName", "value": "Annie"}),
        )
        self.archive_in_horilla(self.employee())
        self.activate(created["id"])
        self.assertFalse(self.employee().is_active)


class AdminTests(TestCase):
    """The Django admin shows SCIM models read-only, to superusers only."""

    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.provider = ScimProvider.objects.create(company=self.company, name="Okta")
        ScimToken.issue(self.provider)
        self.client = Client()

    def test_superuser_can_view_but_not_change(self):
        admin_user = make_user("root", is_superuser=True)
        make_employee(company=self.company, email="root@acme.test", user=admin_user)
        self.client.force_login(admin_user)
        token = ScimToken.objects.get()
        base = "/admin/horilla_scim/"
        self.assertEqual(self.client.get(base + "scimprovider/").status_code, 200)
        self.assertEqual(self.client.get(base + "scimtoken/").status_code, 200)
        self.assertEqual(self.client.get(base + "scimtoken/add/").status_code, 403)
        page = self.client.get(f"{base}scimtoken/{token.pk}/change/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, token.token_hash)
        self.client.post(
            f"{base}scimprovider/{self.provider.pk}/change/", {"name": "X"}
        )
        self.assertEqual(ScimProvider.objects.get().name, "Okta")
        self.client.post(f"{base}scimtoken/{token.pk}/delete/", {"post": "yes"})
        self.assertTrue(ScimToken.objects.exists())

    def test_staff_with_view_permission_is_refused(self):
        staff = make_user("staff")
        make_employee(company=self.company, email="staff@acme.test", user=staff)
        staff.is_staff = True
        staff.save()
        staff.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_scimprovider", "view_scimtoken"]
            )
        )
        self.client.force_login(staff)
        self.assertEqual(
            self.client.get("/admin/horilla_scim/scimtoken/").status_code, 403
        )


class RobustnessTests(ScimTestCase):
    """Input PostgreSQL refuses, and unexpected errors, must come back as SCIM
    errors: IdPs read an HTML 500 as an outage."""

    def assert_scim_error(self, response, status, scim_type=None):
        self.assertEqual(response.status_code, status, response.content)
        body = response.json()
        self.assertIn("urn:ietf:params:scim:api:messages:2.0:Error", body["schemas"])
        if scim_type:
            self.assertEqual(body["scimType"], scim_type)

    def test_nul_in_username_is_400(self):
        doc = user_doc(
            user_name="ann\x00@acme.test", emails=[{"value": "ann@acme.test"}]
        )
        self.assert_scim_error(self.call("post", "/Users", doc), 400, "invalidValue")
        self.assertFalse(
            Employee.objects.entire().filter(email="ann@acme.test").exists()
        )

    def test_nul_in_name_is_400(self):
        doc = user_doc(name={"givenName": "A\x00nn", "familyName": "Lee"})
        self.assert_scim_error(self.call("post", "/Users", doc), 400, "invalidValue")

    def test_nul_in_patched_name_is_400(self):
        created = self.create_user()
        response = self.call(
            "patch",
            f"/Users/{created['id']}",
            patch_doc({"op": "replace", "path": "name.familyName", "value": "L\x00"}),
        )
        self.assert_scim_error(response, 400, "invalidValue")
        self.assertEqual(self.employee().employee_last_name, "Lee")

    def test_nul_in_filter_is_400(self):
        response = self.call("get", "/Users?filter=userName%20eq%20%22a%00b%22")
        self.assert_scim_error(response, 400, "invalidFilter")
        self.assertEqual(ScimEvent.objects.filter(status=400).count(), 1)

    def test_nul_in_id_is_404(self):
        self.assert_scim_error(self.call("get", "/Users/a%00b"), 404)

    def test_huge_start_index_is_an_empty_page(self):
        self.create_user()
        response = self.call("get", "/Users?startIndex=99999999999999999999")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["totalResults"], 1)
        self.assertEqual(body["Resources"], [])

    def test_concurrent_create_integrity_error_is_409(self):
        with mock.patch(
            "horilla_scim.api.provisioning.create_employee",
            side_effect=IntegrityError("duplicate key"),
        ):
            response = self.call("post", "/Users", user_doc())
        self.assert_scim_error(response, 409, "uniqueness")

    def test_unexpected_error_is_scim_500(self):
        with mock.patch(
            "horilla_scim.api.provisioning.create_employee",
            side_effect=RuntimeError("boom"),
        ), self.assertLogs("horilla_scim.api", level="ERROR"):
            response = self.call("post", "/Users", user_doc())
        self.assert_scim_error(response, 500)
        self.assertNotIn("boom", response.json()["detail"])


class MalformedShapeTests(ScimTestCase):
    def assert_invalid(self, doc, method="post", path="/Users"):
        response = self.call(method, path, doc)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["scimType"], "invalidValue")

    def test_name_as_string(self):
        self.assert_invalid(user_doc(name="Ann Lee"))

    def test_emails_as_object(self):
        self.assert_invalid(user_doc(emails={"value": "ann@acme.test"}))

    def test_phone_numbers_as_number(self):
        self.assert_invalid(user_doc(phoneNumbers=5551234))

    def test_enterprise_extension_as_string(self):
        self.assert_invalid(user_doc(**{ENTERPRISE_USER: "Engineering"}))

    def test_manager_as_number(self):
        self.assert_invalid(user_doc(**{ENTERPRISE_USER: {"manager": 7}}))

    def test_malformed_put_changes_nothing(self):
        created = self.create_user()
        self.assert_invalid(
            user_doc(name="Annie"), method="put", path=f"/Users/{created['id']}"
        )
        self.assertEqual(self.employee().employee_first_name, "Ann")


class PatchRemoveTests(ScimTestCase):
    """RFC 7644 §3.5.2.2: "remove" clears the attribute."""

    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(department="Engineering")
        self.department.company_id.add(self.company)
        self.position = JobPosition.objects.create(
            job_position="Engineer", department_id=self.department
        )
        self.position.company_id.add(self.company)
        self.boss = self.create_user(user_name="boss@acme.test", externalId="m")
        self.user = self.create_user(
            title="Engineer",
            phoneNumbers=[{"value": "5551234", "type": "work"}],
            **{
                ENTERPRISE_USER: {
                    "department": "Engineering",
                    "employeeNumber": "E-1",
                    "manager": {"value": self.boss["id"]},
                }
            },
        )
        self.path = f"/Users/{self.user['id']}"

    def remove(self, path):
        return self.call("patch", self.path, patch_doc({"op": "remove", "path": path}))

    def work_info(self):
        return EmployeeWorkInformation.objects.entire().get(employee_id=self.employee())

    def test_setup_values(self):
        info = self.work_info()
        self.assertEqual(info.department_id, self.department)
        self.assertEqual(info.job_position_id, self.position)
        self.assertEqual(info.reporting_manager_id, self.employee("boss@acme.test"))
        self.assertEqual(self.employee().phone, "5551234")

    def test_remove_manager(self):
        response = self.remove(f"{ENTERPRISE_USER}:manager")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(self.work_info().reporting_manager_id)
        self.assertNotIn("manager", response.json()[ENTERPRISE_USER])

    def test_remove_phone_numbers(self):
        self.assertEqual(self.remove("phoneNumbers").status_code, 200)
        self.assertEqual(self.employee().phone, "")

    def test_remove_phone_number_by_filter(self):
        self.assertEqual(self.remove('phoneNumbers[type eq "work"]').status_code, 200)
        self.assertEqual(self.employee().phone, "")

    def test_remove_title_and_department(self):
        self.assertEqual(self.remove("title").status_code, 200)
        self.assertEqual(self.remove(f"{ENTERPRISE_USER}:department").status_code, 200)
        info = self.work_info()
        self.assertIsNone(info.job_position_id)
        self.assertIsNone(info.department_id)

    def test_remove_employee_number(self):
        self.assertEqual(
            self.remove(f"{ENTERPRISE_USER}:employeeNumber").status_code, 200
        )
        self.assertIsNone(self.employee().badge_id)

    def test_remove_required_attribute_is_400(self):
        for path in ("userName", "emails", "name.givenName", "active"):
            response = self.remove(path)
            self.assertEqual(response.status_code, 400, path)
            self.assertEqual(response.json()["scimType"], "mutability")
        self.assertEqual(self.employee().employee_first_name, "Ann")

    def test_put_keeps_omitted_attributes(self):
        # Documented: PUT merges, so an IdP that does not map an attribute
        # cannot wipe what HR maintains in Horilla.
        response = self.call("put", self.path, user_doc())
        self.assertEqual(response.status_code, 200, response.content)
        info = self.work_info()
        self.assertEqual(info.job_position_id, self.position)
        self.assertEqual(info.reporting_manager_id, self.employee("boss@acme.test"))
        self.assertEqual(self.employee().phone, "5551234")


class CompanyMoveTests(ScimTestCase):
    def test_employee_moved_to_another_company_is_hidden(self):
        created = self.create_user()
        EmployeeWorkInformation.objects.entire().filter(
            employee_id=self.employee()
        ).update(company_id=make_company("Globex"))
        path = f"/Users/{created['id']}"
        self.assertEqual(self.call("get", path).status_code, 404)
        self.assertEqual(self.call("get", "/Users").json()["totalResults"], 0)
        response = self.call(
            "patch",
            path,
            patch_doc({"op": "replace", "path": "name.givenName", "value": "X"}),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.call("delete", path).status_code, 404)
        self.assertEqual(self.employee().employee_first_name, "Ann")


class ManagerTests(ScimTestCase):
    def set_manager(self, user, manager):
        return self.call(
            "patch",
            f"/Users/{user['id']}",
            patch_doc(
                {
                    "op": "replace",
                    "path": f"{ENTERPRISE_USER}:manager",
                    "value": {"value": manager["id"]},
                }
            ),
        )

    def test_self_manager_is_400(self):
        created = self.create_user()
        response = self.set_manager(created, created)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidValue")

    def test_manager_loop_is_400(self):
        ann = self.create_user()
        bob = self.create_user(user_name="bob@acme.test", externalId="b")
        cat = self.create_user(user_name="cat@acme.test", externalId="c")
        self.assertEqual(self.set_manager(ann, bob).status_code, 200)
        self.assertEqual(self.set_manager(bob, cat).status_code, 200)
        self.assertEqual(self.set_manager(cat, ann).status_code, 400)
        info = EmployeeWorkInformation.objects.entire().get(
            employee_id=self.employee("cat@acme.test")
        )
        self.assertIsNone(info.reporting_manager_id)
