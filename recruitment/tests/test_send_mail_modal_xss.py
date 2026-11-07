"""
GHSA-fp49-5rww-88pv: the send-mail modal printed the candidate's string form
into a JavaScript string literal with the |safe filter, so a candidate name
containing a quote could break out of the literal and run script in the
recruiter's browser. Candidate names come from the public application form.

The modal only needs to know whether a candidate is present, so the template
now prints a boolean. These tests render it with a hostile name and check
that the name never reaches the script block, and that the employee sibling
template has the same protection.
"""

import re

from django.template.loader import render_to_string
from django.test import TestCase

from base.models import Company, Department
from recruitment.models import Candidate, JobPosition, Recruitment

PAYLOAD = '";window.pwned=1;//'


def _script_blocks(html):
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S))


class SendMailModalXssTests(TestCase):
    def setUp(self):
        Company.objects.create(
            company="XSS Co",
            hq=True,
            address="1 Test St",
            country="US",
            state="CA",
            city="LA",
            zip="90001",
        )
        department = Department.objects.create(department="Eng")
        job_position = JobPosition.objects.create(
            job_position="Engineer", department_id=department
        )
        recruitment = Recruitment.objects.create(
            title="XSS Recruitment", job_position_id=job_position, is_published=True
        )
        stage = recruitment.get_or_create_applied_stage()
        self.candidate = Candidate.objects.create(
            name=PAYLOAD,
            email="xss@example.test",
            recruitment_id=recruitment,
            job_position_id=job_position,
            stage_id=stage,
        )

    def test_candidate_name_never_reaches_script_block(self):
        html = render_to_string(
            "pipeline/pipeline_components/send_mail.html",
            {
                "cand": self.candidate,
                "templates": [],
                "candidates": [],
                "stage_id": None,
                "searchWords": [],
            },
        )
        self.assertNotIn("window.pwned", _script_blocks(html))
        self.assertIn("const hasCandidate = true;", html)

    def test_no_candidate_renders_false(self):
        html = render_to_string(
            "pipeline/pipeline_components/send_mail.html",
            {
                "templates": [],
                "candidates": [self.candidate],
                "stage_id": None,
                "searchWords": [],
            },
        )
        self.assertIn("const hasCandidate = false;", html)
        self.assertNotIn("window.pwned", _script_blocks(html))

    def test_employee_template_prints_boolean(self):
        class FakeEmployee:
            id = 1
            pk = 1

            def __str__(self):
                return PAYLOAD

        html = render_to_string(
            "employee/send_mail.html",
            {
                "employee": FakeEmployee(),
                "templates": [],
                "employees": [],
                "searchWords": [],
            },
        )
        self.assertNotIn("window.pwned", _script_blocks(html))
        self.assertIn("const hasEmployee = true;", html)
