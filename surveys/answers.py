"""Reading answers out of a posted form and checking them against the questions.

One place for the rules, used by the public form, the autosave endpoint and
the tests: what a question of each type accepts, what "required" means for it,
and how the raw POST turns into the JSON kept in SurveyAnswer.value.
"""

from datetime import date

from django.utils.translation import gettext_lazy as _

from surveys.models import SurveyQuestion as Q


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

    allowed = [v for v, _label in question.choices()]
    if question.type == Q.TYPE_MULTIPLE:
        if not isinstance(value, list):
            value = [value]
        bad = [v for v in value if v not in allowed]
        if bad:
            raise AnswerError(_("Choose from the given options."))
        return value
    if question.type in (Q.TYPE_CHOICE, Q.TYPE_LIKERT, Q.TYPE_YES_NO, Q.TYPE_RATING):
        if str(value) not in allowed:
            raise AnswerError(_("Choose from the given options."))
        return str(value)
    if question.type == Q.TYPE_NUMBER:
        try:
            number = float(str(value).replace(",", "."))
        except ValueError:
            raise AnswerError(_("Enter a number.")) from None
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

    strict=False (a draft) keeps whatever can be stored and never complains
    about an empty required question; strict=True (a submission) applies every
    rule.
    """
    values, errors = {}, {}
    for question in questions:
        raw = read(question, data)
        try:
            value = validate(question, raw)
        except AnswerError as error:
            if strict or raw not in (None, "", []):
                errors[question] = error.message
            # A wrong value is not stored, neither in a draft nor in a submission.
            continue
        if strict or value is not None:
            values[
                question
            ] = value  # a draft does not write "nothing" over an earlier answer
    return values, errors


def label(question, value):
    """The value as a person reads it (a Likert code → its wording)."""
    if value is None:
        return ""
    labels = dict(question.choices())
    if isinstance(value, list):
        return ", ".join(str(labels.get(v, v)) for v in value)
    return str(labels.get(str(value), value))
