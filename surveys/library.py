"""The standard questionnaires of the survey library.

Three surveys most HR teams run - eNPS, an engagement pulse and a new hire
check-in - loaded on request (the "Load standard questionnaires" button, or
`manage.py seed_survey_library`) into the library, where they are
Questionnaire rows like those HR saves itself. The wording is our own. The
texts are translatable, and are stored in the language active at loading.
"""

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from surveys.models import Questionnaire
from surveys.models import SurveyQuestion as Q


def _agree(text):
    return {"type": Q.TYPE_LIKERT, "question": text, "is_required": True}


def _open(text):
    return {"type": Q.TYPE_TEXTAREA, "question": text}


STANDARD = [
    {
        "code": "enps",
        "title": _("Employee Net Promoter Score (eNPS)"),
        "description": _(
            "One question that shows how willing people are to recommend the "
            "company as a place to work, and two open ones about why. "
            "Takes two minutes; the answers are anonymous."
        ),
        "is_anonymous": True,
        "questions": [
            {
                "type": Q.TYPE_NPS,
                "question": _(
                    "How likely are you to recommend our company as a place to "
                    "work to a friend or an acquaintance? "
                    "(0 - not at all likely, 10 - extremely likely)"
                ),
                "is_required": True,
            },
            _open(_("What is the main reason for your score?")),
            _open(
                _(
                    "What is the one thing we should change to make the company "
                    "a better place to work?"
                )
            ),
        ],
    },
    {
        "code": "engagement",
        "title": _("Employee engagement pulse"),
        "description": _(
            "Ten statements about everyday work: clarity, resources, feedback, "
            "recognition, growth and the team. Say how much you agree with "
            "each. The answers are anonymous."
        ),
        "is_anonymous": True,
        "questions": [
            _agree(_("I understand what results are expected from me in my role.")),
            _agree(
                _(
                    "I have the tools, access and information I need to do my "
                    "work well."
                )
            ),
            _agree(
                _(
                    "My manager regularly tells me what I do well and what I "
                    "could do better."
                )
            ),
            _agree(_("When I do good work, it gets noticed.")),
            _agree(
                _(
                    "In the last six months I have gained knowledge or skills "
                    "that help me in my work."
                )
            ),
            _agree(
                _("My opinion is taken into account when decisions affect " "my work.")
            ),
            _agree(_("I can see how my work contributes to the company's goals.")),
            _agree(_("My workload lets me do quality work without constant overtime.")),
            _agree(
                _(
                    "People in my team help each other and treat each other "
                    "with respect."
                )
            ),
            _agree(_("I expect to be working here a year from now.")),
            _open(_("What would improve your work here the most?")),
        ],
    },
    {
        "code": "new_hire_30",
        "title": _("New hire check-in: the first 30 days"),
        "description": _(
            "For employees who joined about a month ago: how the first weeks "
            "went and what was missing. The survey is not anonymous, so that HR "
            "can help with what you name."
        ),
        "is_anonymous": False,
        "questions": [
            {
                "type": Q.TYPE_RATING,
                "question": _(
                    "Overall, how would you rate your first month with us? "
                    "(1 - poor, 5 - excellent)"
                ),
                "is_required": True,
            },
            _agree(_("The job matches what I was told during hiring.")),
            _agree(
                _(
                    "My first day was well organised: it was clear where to go "
                    "and who would meet me."
                )
            ),
            _agree(
                _(
                    "In the first days I received the equipment, accounts and "
                    "access I need for my work."
                )
            ),
            _agree(_("I have someone to turn to with questions about my work.")),
            _agree(
                _(
                    "I understand my tasks and what is expected of me in the "
                    "coming months."
                )
            ),
            _agree(_("I feel welcome in my team.")),
            {
                "type": Q.TYPE_YES_NO,
                "question": _(
                    "Did you get all the information you needed about the "
                    "company's rules and processes?"
                ),
                "is_required": True,
            },
            _open(_("What was missing or unclear during your first weeks?")),
            _open(
                _(
                    "What should we keep, and what should we do differently for the "
                    "next new hires?"
                )
            ),
        ],
    },
]


def load_standard():
    """Add the standard questionnaires the library lacks; the ones added.

    One that is already there is left alone, whatever HR has changed in it; a
    deleted one comes back.
    """
    present = set(
        Questionnaire._base_manager.exclude(code="").values_list("code", flat=True)
    )
    added = []
    for item in STANDARD:
        if item["code"] in present:
            continue
        questionnaire = Questionnaire(
            code=item["code"],
            title=str(item["title"]),
            description=str(item["description"]),
            is_anonymous=item["is_anonymous"],
            questions=[
                {
                    "type": q["type"],
                    "question": str(q["question"]),
                    "options": [str(o) for o in q.get("options", [])],
                    "is_required": q.get("is_required", False),
                }
                for q in item["questions"]
            ],
        )
        try:
            with transaction.atomic():
                questionnaire.save()
        except IntegrityError:  # another request added it a moment ago
            continue
        added.append(questionnaire)
    return added
