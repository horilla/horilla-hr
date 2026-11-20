"""Additional info: field definitions, bulk values, the employee tab and the settings tab."""

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from additional_info import services
from additional_info.cbv.section import can_edit
from additional_info.forms import AdditionalInfoFieldForm, build_values_form
from additional_info.models import (
    DATE,
    DROPDOWN,
    FILE,
    LONG_TEXT,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
    AdditionalInfoValue,
)
from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser

HX = {"HTTP_HX_REQUEST": "true"}


def settle():
    """New employees must change their password before anything else; these tests are not about that."""
    HorillaUser.objects.update(is_new_employee=False)


def make_field(label, field_type=TEXT, **extra):
    return AdditionalInfoField.objects.create(
        label=label, field_type=field_type, **extra
    )


def dropdown(label="Blood Group", options=("A+", "B+", "O-")):
    field = make_field(label, DROPDOWN)
    field.choices = [
        {"key": o.lower().replace("+", "_pos").replace("-", "_neg"), "label": o}
        for o in options
    ]
    field.save()
    return field


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Info Co")
        self.admin = make_user("info_admin", password="x", is_superuser=True)
        make_employee(company=self.company, email="info_admin@x.test", user=self.admin)
        self.ada = make_employee(
            company=self.company, email="ada@x.test", first_name="Ada"
        )
        self.bob = make_employee(
            company=self.company, email="bob@x.test", first_name="Bob"
        )
        settle()


class FieldTests(Fixture):
    def test_key_comes_from_the_label_and_never_changes(self):
        field = make_field("Passport No.")
        self.assertEqual(field.key, "passport_no")
        field.label = "Passport Number"
        field.save()
        self.assertEqual(
            AdditionalInfoField.objects.get(pk=field.pk).key, "passport_no"
        )

    def test_keys_are_unique(self):
        first, second = make_field("Id"), make_field("Id!")
        self.assertNotEqual(first.key, second.key)

    def test_new_field_applies_to_every_employee_without_any_rows(self):
        make_field("Hobby")
        self.assertEqual(AdditionalInfoValue.objects.count(), 0)
        for employee in (self.ada, self.bob):
            rows = services.rows_for(employee)
            self.assertEqual([r["field"].label for r in rows], ["Hobby"])
            self.assertEqual(rows[0]["display"], "")

    def test_inactive_field_is_hidden(self):
        make_field("Hidden", is_active=False)
        self.assertEqual(services.rows_for(self.ada), [])


class ValueTests(Fixture):
    def save(self, employee, fields, **data):
        form = build_values_form(fields)(data)
        self.assertTrue(form.is_valid(), form.errors)
        services.set_values(employee, fields, form.cleaned_data)

    def test_every_type_round_trips(self):
        text, long_, number = (
            make_field("T", TEXT),
            make_field("L", LONG_TEXT),
            make_field("N", NUMBER),
        )
        when, flag, pick = make_field("D", DATE), make_field("Y", YES_NO), dropdown()
        fields = [text, long_, number, when, flag, pick]
        self.save(
            self.ada,
            fields,
            t="hello",
            l="line one\nline two",
            n="12.50",
            d="2026-03-01",
            y="no",
            blood_group="a_pos",
        )
        got = services.values_for([self.ada.pk], fields)[self.ada.pk]
        self.assertEqual(got["t"], "hello")
        self.assertEqual(got["l"], "line one\nline two")
        self.assertEqual(got["n"], Decimal("12.5"))
        self.assertEqual(got["d"], date(2026, 3, 1))
        self.assertIs(got["y"], False)
        self.assertEqual(got["blood_group"], "a_pos")
        shown = {r["field"].key: r["display"] for r in services.rows_for(self.ada)}
        self.assertEqual(shown["n"], "12.5")
        self.assertEqual(shown["y"], "No")
        self.assertEqual(shown["blood_group"], "A+")

    def test_clearing_a_value_removes_its_row(self):
        text = make_field("T")
        self.save(self.ada, [text], t="x")
        self.assertEqual(AdditionalInfoValue.objects.count(), 1)
        self.save(self.ada, [text], t="")
        self.assertEqual(AdditionalInfoValue.objects.count(), 0)

    def test_one_row_per_employee_and_field(self):
        text = make_field("T")
        self.save(self.ada, [text], t="one")
        self.save(self.ada, [text], t="two")
        self.assertEqual(
            AdditionalInfoValue.objects.filter(employee_id=self.ada).count(), 1
        )
        self.assertEqual(
            services.values_for([self.ada.pk], [text])[self.ada.pk]["t"], "two"
        )

    def test_values_are_per_employee(self):
        text = make_field("T")
        self.save(self.ada, [text], t="ada")
        self.assertNotIn(
            self.bob.pk, services.values_for([self.ada.pk, self.bob.pk], [text])
        )

    def test_bulk_read_is_one_query_however_many_employees(self):
        text, number = make_field("T"), make_field("N", NUMBER)
        people = [
            make_employee(company=self.company, email=f"p{i}@x.test") for i in range(6)
        ]
        for person in people:
            self.save(person, [text, number], t="v", n="1")
        ids = [p.pk for p in people]
        with self.assertNumQueries(1):
            services.values_for(ids, [text, number])

    def test_file_upload_replace_and_clear(self):
        doc = make_field("Doc", FILE)
        upload = SimpleUploadedFile("a.pdf", b"%PDF-1", content_type="application/pdf")
        form = build_values_form([doc])({}, {"doc": upload})
        self.assertTrue(form.is_valid(), form.errors)
        services.set_values(self.ada, [doc], form.cleaned_data)
        row = AdditionalInfoValue.objects.get(employee_id=self.ada, field=doc)
        self.assertTrue(row.value_file.name.endswith(".pdf"))
        services.set_values(self.ada, [doc], {"doc": False})
        self.assertFalse(
            AdditionalInfoValue.objects.filter(employee_id=self.ada).exists()
        )

    def test_file_type_and_size_are_checked(self):
        doc = make_field("Doc", FILE)
        bad = SimpleUploadedFile("run.exe", b"MZ")
        self.assertFalse(build_values_form([doc])({}, {"doc": bad}).is_valid())
        big = SimpleUploadedFile("big.pdf", b"0" * (10 * 1024 * 1024 + 1))
        self.assertFalse(build_values_form([doc])({}, {"doc": big}).is_valid())

    def test_required_field_is_enforced_on_the_form(self):
        need = make_field("Need", is_required=True)
        self.assertFalse(build_values_form([need])({"need": ""}).is_valid())


class FilterTests(Fixture):
    def setUp(self):
        super().setUp()
        self.number, self.when, self.flag = (
            make_field("N", NUMBER),
            make_field("D", DATE),
            make_field("Y", YES_NO),
        )
        self.text, self.pick = make_field("T"), dropdown()
        self.fields = [self.number, self.when, self.flag, self.text, self.pick]
        for employee, n, d, y, t, p in [
            (self.ada, "5", "2026-01-10", "yes", "Alpha team", "a_pos"),
            (self.bob, "9", "2026-06-10", "no", "Beta team", "b_pos"),
        ]:
            form = build_values_form(self.fields)(
                {"n": n, "d": d, "y": y, "t": t, "blood_group": p}
            )
            assert form.is_valid(), form.errors
            services.set_values(employee, self.fields, form.cleaned_data)

    def names(self, key, lookup, value):
        qs = services.filter_employees(Employee.objects.entire(), key, lookup, value)
        return set(qs.values_list("employee_first_name", flat=True))

    def test_number_range(self):
        self.assertEqual(self.names("n", "gt", 6), {"Bob"})
        self.assertEqual(self.names("n", "lte", 5), {"Ada"})

    def test_date_range(self):
        self.assertEqual(self.names("d", "lt", date(2026, 3, 1)), {"Ada"})

    def test_yes_no(self):
        self.assertEqual(self.names("y", "exact", True), {"Ada"})

    def test_text_search_and_dropdown(self):
        self.assertEqual(self.names("t", "icontains", "beta"), {"Bob"})
        self.assertEqual(self.names("blood_group", "exact", "a_pos"), {"Ada"})

    def test_bad_field_or_lookup_is_refused(self):
        with self.assertRaises(ValueError):
            services.filter_employees(Employee.objects.entire(), "nope", "exact", 1)
        with self.assertRaises(ValueError):
            services.filter_employees(Employee.objects.entire(), "y", "icontains", "x")

    def test_export_helpers(self):
        self.assertEqual(
            [label for _, label in services.export_columns()],
            ["N", "D", "Y", "T", "Blood Group"],
        )
        values = services.values_for([self.ada.pk])[self.ada.pk]
        self.assertEqual(
            services.export_row(values), ["5", "2026-01-10", "Yes", "Alpha team", "A+"]
        )


class FieldFormTests(Fixture):
    def form(self, **data):
        base = {
            "label": "Blood Group",
            "field_type": DROPDOWN,
            "options": "A+\nB+",
            "sequence": 0,
            "is_active": "on",
        }
        base.update(data)
        return AdditionalInfoFieldForm(base)

    def test_dropdown_needs_options(self):
        self.assertFalse(self.form(options="").is_valid())

    def test_duplicate_options_refused(self):
        self.assertFalse(self.form(options="A+\na+").is_valid())

    def test_label_must_be_unique(self):
        make_field("Blood Group")
        self.assertFalse(self.form().is_valid())

    def test_saving_builds_option_keys_and_keeps_them_when_edited(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        field = form.save()
        keys = {o["label"]: o["key"] for o in field.choices}
        edit = AdditionalInfoFieldForm(
            {
                "label": "Blood Group",
                "field_type": DROPDOWN,
                "options": "B+\nAB+",
                "sequence": 0,
                "is_active": "on",
            },
            instance=field,
        )
        self.assertTrue(edit.is_valid(), edit.errors)
        field = edit.save()
        kept = {o["label"]: o["key"] for o in field.choices}
        self.assertEqual(kept["B+"], keys["B+"])
        self.assertIn("AB+", kept)

    def test_type_is_locked_once_values_exist(self):
        field = make_field("T")
        AdditionalInfoValue.objects.create(
            employee_id=self.ada, field=field, value_text="x"
        )
        form = AdditionalInfoFieldForm(instance=field)
        self.assertTrue(form.fields["field_type"].disabled)

    def test_non_dropdown_drops_options(self):
        form = self.form(field_type=TEXT)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().choices, [])


class FieldOrderTests(Fixture):
    """The second step of the field form: where the field sits among the others."""

    def setUp(self):
        super().setUp()
        self.a = make_field("Alpha", sequence=0)
        self.b = make_field("Beta", sequence=1)
        self.c = make_field("Gamma", sequence=2)

    def form(self, order=None, **data):
        base = {"label": "Delta", "field_type": TEXT, "options": "", "is_active": "on"}
        if order is not None:
            base["field_order"] = order
        base.update(data)
        return AdditionalInfoFieldForm(base)

    def saved_order(self):
        return list(AdditionalInfoField.objects.values_list("label", flat=True))

    def test_the_order_step_lists_every_field_with_a_new_one_last(self):
        rows = json.loads(AdditionalInfoFieldForm().order_json)
        self.assertEqual(
            [r["id"] for r in rows], [self.a.pk, self.b.pk, self.c.pk, "new"]
        )
        self.assertEqual([r["current"] for r in rows], [False, False, False, True])

    def test_the_order_step_marks_the_field_being_edited(self):
        rows = json.loads(AdditionalInfoFieldForm(instance=self.b).order_json)
        self.assertEqual([r["current"] for r in rows], [False, True, False])

    def test_a_form_coming_back_with_an_error_keeps_the_order_that_was_chosen(self):
        order = json.dumps(["new", self.c.pk, self.a.pk, self.b.pk])
        form = self.form(order, label="")
        self.assertFalse(form.is_valid())
        self.assertEqual(
            [r["id"] for r in json.loads(form.order_json)],
            ["new", self.c.pk, self.a.pk, self.b.pk],
        )

    def test_a_new_field_goes_where_it_was_dropped(self):
        form = self.form(json.dumps([self.a.pk, "new", self.b.pk, self.c.pk]))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.saved_order(), ["Alpha", "Delta", "Beta", "Gamma"])
        self.assertEqual(
            list(AdditionalInfoField.objects.values_list("sequence", flat=True)),
            [0, 1, 2, 3],
        )

    def test_a_new_field_without_an_order_goes_last(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        field = form.save()
        self.assertEqual(self.saved_order(), ["Alpha", "Beta", "Gamma", "Delta"])
        self.assertEqual(field.sequence, 3)

    def test_moving_a_field_renumbers_the_others(self):
        form = AdditionalInfoFieldForm(
            {
                "label": "Gamma",
                "field_type": TEXT,
                "options": "",
                "is_active": "on",
                "field_order": json.dumps([self.c.pk, self.a.pk, self.b.pk]),
            },
            instance=self.c,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.saved_order(), ["Gamma", "Alpha", "Beta"])

    def test_editing_without_an_order_leaves_the_order_alone(self):
        form = AdditionalInfoFieldForm(
            {
                "label": "Beta Renamed",
                "field_type": TEXT,
                "options": "",
                "is_active": "on",
            },
            instance=self.b,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.saved_order(), ["Alpha", "Beta Renamed", "Gamma"])

    def test_unknown_and_repeated_ids_are_skipped(self):
        form = self.form(json.dumps([9999, "new", self.c.pk, self.c.pk, self.a.pk]))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.saved_order(), ["Delta", "Gamma", "Alpha", "Beta"])

    def test_a_field_missing_from_the_order_keeps_its_place_after_the_listed_ones(self):
        form = self.form(json.dumps(["new", self.b.pk]))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.saved_order(), ["Delta", "Beta", "Alpha", "Gamma"])

    def test_an_order_that_cannot_be_read_is_refused(self):
        for bad in (
            "not json",
            "{}",
            '"new"',
            "[true]",
            '["x"]',
            "[1.5]",
            json.dumps(list(range(1001))),
        ):
            self.assertIn("field_order", self.form(bad).errors, bad)

    def test_the_form_has_two_steps_and_no_order_number(self):
        field = AdditionalInfoFieldForm()
        self.assertEqual(field.wizard_template, "additional_info/field_wizard.html")
        self.assertNotIn("sequence", field.fields)

    def test_saving_through_the_view_places_the_field_where_it_was_dropped(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["selected_company"] = "all"
        session.save()
        client.post(
            reverse("additional-info-field-create-form"),
            {
                "label": "Delta",
                "field_type": TEXT,
                "options": "",
                "is_active": "on",
                "field_order": json.dumps(["new", self.a.pk, self.b.pk, self.c.pk]),
            },
            **HX,
        )
        self.assertEqual(self.saved_order(), ["Delta", "Alpha", "Beta", "Gamma"])

    def test_the_form_page_carries_both_steps(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["selected_company"] = "all"
        session.save()
        page = client.get(reverse("additional-info-field-create-form"), **HX)
        self.assertContains(page, 'data-step-tab="details"')
        self.assertContains(page, 'data-step-tab="order"')
        self.assertContains(page, 'data-step-panel="order"')
        self.assertContains(page, 'name="field_order"')
        self.assertContains(page, "data-step-next")
        self.assertNotContains(page, 'name="sequence"')


class TabTests(Fixture):
    def setUp(self):
        super().setUp()
        self.text = make_field("Hobby")
        self.client = Client()

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def user_for(self, employee):
        return employee.employee_user_id

    def tab(self, employee):
        return self.client.get(
            reverse("additional-info-section", args=[employee.pk]), **HX
        )

    def can_edit(self, viewer, employee):
        request = RequestFactory().get("/")
        request.user = (
            viewer if isinstance(viewer, HorillaUser) else self.user_for(viewer)
        )
        return bool(can_edit(request, employee))

    def test_hr_sees_any_employee(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.ada, field=self.text, value_text="Chess"
        )
        self.login(self.admin)
        page = self.tab(self.ada)
        self.assertContains(page, "Hobby")
        self.assertContains(page, "Chess")

    def test_the_section_has_no_edit_button(self):
        self.login(self.admin)
        page = self.tab(self.ada)
        self.assertNotContains(page, "create-outline")
        self.assertNotContains(page, "hx-post")

    def test_employee_views_their_own_but_cannot_edit(self):
        AdditionalInfoValue.objects.create(
            employee_id=self.ada, field=self.text, value_text="Chess"
        )
        self.login(self.user_for(self.ada))
        self.assertContains(self.tab(self.ada), "Chess")
        self.assertFalse(self.can_edit(self.ada, self.ada))

    def test_unrelated_employee_cannot_view_another(self):
        self.login(self.user_for(self.bob))
        self.assertNotContains(self.tab(self.ada), "Hobby")

    def test_hr_and_the_reporting_manager_may_edit_the_values(self):
        manager = make_employee(
            company=self.company, email="boss@x.test", first_name="Boss"
        )
        settle()
        info = EmployeeWorkInformation.objects.get(employee_id=self.ada)
        info.reporting_manager_id = manager
        info.save()
        self.assertTrue(self.can_edit(manager, self.ada))
        self.assertFalse(self.can_edit(manager, self.bob))
        self.assertTrue(self.can_edit(self.admin, self.bob))

    def test_section_is_empty_when_no_field_is_set_up(self):
        AdditionalInfoField.objects.all().delete()
        self.login(self.admin)
        self.assertEqual(self.tab(self.ada).content, b"")

    def test_about_tab_loads_the_section(self):
        self.login(self.admin)
        page = self.client.get(reverse("about-tab", args=[self.ada.pk]), **HX)
        self.assertContains(
            page, reverse("additional-info-section", args=[self.ada.pk])
        )

    def test_there_is_no_separate_tab(self):
        from employee.cbv.employee_profile import EmployeeProfileView

        self.assertNotIn(
            "Additional Info", [str(t["title"]) for t in EmployeeProfileView.tabs]
        )


class SettingsTests(Fixture):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def test_manage_page_renders_for_admin(self):
        response = self.client.get(reverse("additional-info-fields-tab"), **HX)
        self.assertEqual(response.status_code, 200)

    def test_field_form_follows_the_type(self):
        """The form carries the script that shows Options for a Dropdown only and previews the input."""
        page = self.client.get(reverse("additional-info-field-create-form"), **HX)
        self.assertContains(page, 'name="options"')
        self.assertContains(page, "data-type-bound")
        self.assertContains(page, "optionLines")

    def test_field_form_script_also_comes_with_the_edit_form(self):
        field = dropdown()
        page = self.client.get(
            reverse("additional-info-field-update-form", args=[field.pk]), **HX
        )
        self.assertContains(page, "data-type-bound")
        self.assertContains(page, "A+")

    def test_create_edit_and_delete_a_field(self):
        response = self.client.post(
            reverse("additional-info-field-create-form"),
            {
                "label": "Passport No",
                "field_type": TEXT,
                "options": "",
                "sequence": 1,
                "is_active": "on",
            },
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        field = AdditionalInfoField.objects.get(label="Passport No")
        self.client.post(
            reverse("additional-info-field-update-form", args=[field.pk]),
            {
                "label": "Passport Number",
                "field_type": TEXT,
                "options": "",
                "sequence": 1,
                "is_active": "on",
            },
            **HX,
        )
        field.refresh_from_db()
        self.assertEqual((field.label, field.key), ("Passport Number", "passport_no"))
        AdditionalInfoValue.objects.create(
            employee_id=self.ada, field=field, value_text="X1"
        )
        self.client.post(reverse("additional-info-field-delete", args=[field.pk]), **HX)
        self.assertFalse(AdditionalInfoField.objects.filter(pk=field.pk).exists())
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_without_permission_nothing_works(self):
        user = make_user("plain_info", password="x")
        make_employee(company=self.company, email="plain_info@x.test", user=user)
        settle()
        client = Client()
        client.force_login(user)
        session = client.session
        session["selected_company"] = "all"
        session.save()
        field = make_field("Keep")
        client.post(reverse("additional-info-field-delete", args=[field.pk]), **HX)
        self.assertTrue(AdditionalInfoField.objects.filter(pk=field.pk).exists())
        client.post(
            reverse("additional-info-field-create-form"),
            {"label": "Sneaky", "field_type": TEXT, "options": "", "sequence": 0},
            **HX,
        )
        self.assertFalse(AdditionalInfoField.objects.filter(label="Sneaky").exists())

    def test_change_permission_alone_can_edit_but_not_create(self):
        user = make_user("changer", password="x")
        make_employee(company=self.company, email="changer@x.test", user=user)
        settle()
        user.user_permissions.add(
            Permission.objects.get(codename="change_additionalinfofield")
        )
        field = make_field("Old")
        client = Client()
        client.force_login(user)
        session = client.session
        session["selected_company"] = "all"
        session.save()
        client.post(
            reverse("additional-info-field-update-form", args=[field.pk]),
            {"label": "New", "field_type": TEXT, "options": "", "sequence": 0},
            **HX,
        )
        field.refresh_from_db()
        self.assertEqual(field.label, "New")
        client.post(
            reverse("additional-info-field-create-form"),
            {"label": "Extra", "field_type": TEXT, "options": "", "sequence": 0},
            **HX,
        )
        self.assertFalse(AdditionalInfoField.objects.filter(label="Extra").exists())

    def test_employee_settings_page_shows_the_tab_button(self):
        response = self.client.get(reverse("employee-settings-view"))
        self.assertContains(response, reverse("additional-info-fields-tab"))


class EmployeeFormStepTests(Fixture):
    """The Additional Information step on the employee create and edit pages."""

    def setUp(self):
        super().setUp()
        self.text = make_field("Hobby")
        self.client = Client()
        self.client.force_login(self.admin)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def edit_page(self, employee):
        return self.client.get(
            reverse("employee-view-update", args=[employee.pk]), **HX
        )

    def test_edit_page_has_the_fourth_step(self):
        page = self.edit_page(self.ada)
        self.assertContains(page, 'id="step-additional"')
        self.assertContains(page, 'id="employeeUpdateAdditionalForm"')
        self.assertContains(page, "Hobby")

    def test_saving_the_step_stores_values_and_stays_on_it(self):
        response = self.client.post(
            reverse("employee-view-update", args=[self.ada.pk]),
            {"form": "additional", "hobby": "Chess"},
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            services.values_for([self.ada.pk])[self.ada.pk]["hobby"], "Chess"
        )
        self.assertContains(response, 'value="Chess"')

    def test_invalid_step_shows_errors_and_saves_nothing(self):
        make_field("Need", is_required=True)
        response = self.client.post(
            reverse("employee-view-update", args=[self.ada.pk]),
            {"form": "additional", "hobby": "x"},
            **HX,
        )
        self.assertContains(response, "required")
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_script_in_a_value_is_refused(self):
        response = self.client.post(
            reverse("employee-view-update", args=[self.ada.pk]),
            {"form": "additional", "hobby": "<script>alert(1)</script>"},
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_no_step_without_fields(self):
        AdditionalInfoField.objects.all().delete()
        self.assertNotContains(self.edit_page(self.ada), 'id="step-additional"')

    def test_user_who_cannot_edit_values_gets_no_step_and_cannot_save(self):
        user = self.ada.employee_user_id
        self.client.force_login(user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        page = self.client.get(
            reverse("employee-view-update", args=[self.ada.pk]), **HX
        )
        self.assertNotContains(page, 'id="step-additional"')
        self.client.post(
            reverse("employee-view-update", args=[self.ada.pk]),
            {"form": "additional", "hobby": "Hack"},
            **HX,
        )
        self.assertFalse(AdditionalInfoValue.objects.exists())

    def test_create_page_shows_the_step_label(self):
        page = self.client.get(reverse("employee-view-new"))
        self.assertContains(page, "Additional Information")
