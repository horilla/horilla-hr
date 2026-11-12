"""Filters of the surveys list and the library."""

import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from horilla.filters import HorillaFilterSet
from surveys.models import Questionnaire, Survey


class SurveyFilter(HorillaFilterSet):
    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    status = django_filters.ChoiceFilter(choices=Survey.STATUSES, label=_("Status"))
    is_anonymous = django_filters.BooleanFilter(label=_("Anonymous"))
    closes_at_from = django_filters.DateFilter(
        field_name="closes_at",
        lookup_expr="gte",
        label=_("Closes from"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    closes_at_till = django_filters.DateFilter(
        field_name="closes_at",
        lookup_expr="lte",
        label=_("Closes till"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Survey
        fields = ["status", "is_anonymous", "audience"]


class QuestionnaireFilter(HorillaFilterSet):
    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    is_anonymous = django_filters.BooleanFilter(label=_("Anonymous"))

    class Meta:
        model = Questionnaire
        fields = ["is_anonymous"]
