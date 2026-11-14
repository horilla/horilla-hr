"""Reading answers out of a posted form and checking them against the questions.

One place for the rules, used by the public form, the autosave endpoint and
the tests: what a question of each type accepts, what "required" means for it,
and how the raw POST turns into the JSON kept in SurveyAnswer.value.
"""

import math
from datetime import date

from django.utils.translation import gettext_lazy as _

from surveys.models import SurveyQuestion as Q


# A number answer is kept as JSON: it must be finite and short, because PostgreSQL's
# jsonb refuses NaN and Infinity and a 400-digit figure helps nobody
MAX_NUMBER_CHARS = 32
MAX_NUMBER = 10**15


class AnswerError(ValueError):
    """One question's answer is not acceptable; `message` is for the person."""

    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


def field_name(question):
    return f"q{question.pk}"


def read(question, data):
    """The posted value of one question, as it is stored: None when empty."""
    name = field_name(question)
    if question.type == Q.TYPE_MULTIPLE:
        values = [v.strip() for v in data.getlist(name) if v.strip()]
        return values or None
    value = (data.get(name) or "").strip()
    return value or None


def validate(question, value):
    """Return the stored form of `value` or raise AnswerError."""
    if value in (None, "", []):
        if question.is_required:
            raise AnswerError(_("This question is required."))
        return None

    # jsonb cannot hold a NUL character, so it never reaches the database
    if any("\x00" in str(v) for v in (value if isinstance(value, list) else [value])):
        raise AnswerError(_("Remove the unsupported characters and try again."))

    allowed = [v for v, _label in question.choices()]
    if question.type == Q.TYPE_MULTIPLE:
        if not isinstance(value, list):
            value = [value]
        bad = [v for v in value if v not in allowed]
        if bad:
            raise AnswerError(_("Choose from the given options."))
        # an option ticked twice (a hand-made request) counts once
        return list(dict.fromkeys(value))
    if question.type in (
        Q.TYPE_CHOICE,
        Q.TYPE_LIKERT,
        Q.TYPE_YES_NO,
        Q.TYPE_RATING,
        Q.TYPE_NPS,
    ):
        if str(value) not in allowed:
            raise AnswerError(_("Choose from the given options."))
        return str(value)
    if question.type == Q.TYPE_NUMBER:
        text = str(value).strip().replace(",", ".")
        if len(text) > MAX_NUMBER_CHARS:
            raise AnswerError(_("Enter a number of up to 15 digits."))
        try:
            number = float(text)
        except ValueError:
            raise AnswerError(_("Enter a number.")) from None
        if not math.isfinite(number) or abs(number) >= MAX_NUMBER:
            raise AnswerError(_("Enter a number of up to 15 digits."))
        return int(number) if number.is_integer() else number
    if question.type == Q.TYPE_DATE:
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise AnswerError(_("Enter a date.")) from None
    text = str(value).strip()
    limit = 4000 if question.type == Q.TYPE_TEXTAREA else 500
    if len(text) > limit:
        raise AnswerError(_("At most %(n)s characters.") % {"n": limit})
    return text


def collect(questions, data, *, strict):
    """{question: stored value} for every question, plus {question: error}.

    strict=True (a submission) applies every rule. strict=False (a draft) is the
    form as it stands: an emptied field comes back as None, which clears the saved
    answer, and a required question left empty is not an error yet. A wrong
    value is never stored, in either mode.
    """
    values, errors = {}, {}
    for question in questions:
        raw = read(question, data)
        if not strict and raw in (None, "", []):
            values[question] = None
            continue
        try:
            value = validate(question, raw)
        except AnswerError as error:
            errors[question] = error.message
            continue
        values[question] = value
    return values, errors


def label(question, value):
    """The value as a person reads it (a Likert code → its wording)."""
    if value is None:
        return ""
    labels = dict(question.choices())
    if isinstance(value, list):
        return ", ".join(str(labels.get(v, v)) for v in value)
    return str(labels.get(str(value), value))
