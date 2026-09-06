"""
admin.py

This page is used to register PMS models with admins site.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    AnonymousFeedback,
    Answer,
    BonusPointSetting,
    Comment,
    EmployeeBonusPoint,
    EmployeeKeyResult,
    EmployeeObjective,
    Feedback,
    KeyResult,
    KeyResultFeedback,
    Meetings,
    Objective,
    Period,
    Question,
    QuestionOptions,
    QuestionTemplate,
)

# Register your models here.

objective = [Period]
feedback = [Question, QuestionTemplate, Feedback, Answer, QuestionOptions]
admin.site.register(EmployeeObjective, SimpleHistoryAdmin)
admin.site.register(EmployeeKeyResult, SimpleHistoryAdmin)
admin.site.register(objective)
admin.site.register(feedback)
admin.site.register(KeyResult)
admin.site.register(Objective)
admin.site.register(KeyResultFeedback)
admin.site.register(Meetings)
admin.site.register(Comment, SimpleHistoryAdmin)
admin.site.register(BonusPointSetting)
admin.site.register(EmployeeBonusPoint)
