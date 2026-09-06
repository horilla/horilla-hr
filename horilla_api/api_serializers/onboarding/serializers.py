"""
horilla_api/api_serializers/onboarding/serializers.py
"""

from rest_framework import serializers

from employee.models import Employee
from onboarding.models import (
    CandidateStage,
    CandidateTask,
    OnboardingPortal,
    OnboardingStage,
    OnboardingTask,
)
from recruitment.models import Candidate, Recruitment


class OnboardingStageSerializer(serializers.ModelSerializer):
    recruitment_id = serializers.SerializerMethodField()
    recruitment_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Recruitment.objects.all(),
        source="recruitment_id",
        write_only=True,
        required=False,
    )
    employee_id = serializers.SerializerMethodField()
    employee_id_ids = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        many=True,
        source="employee_id",
        write_only=True,
        required=False,
    )
    onboarding_task = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingStage
        fields = "__all__"
        extra_kwargs = {
            "employee_id": {"read_only": True},
        }

    def get_recruitment_id(self, obj):
        if obj.recruitment_id:
            return {
                "id": obj.recruitment_id.id,
                "title": obj.recruitment_id.title,
            }
        return None

    def get_employee_id(self, obj):
        if obj.employee_id.exists():
            return [
                {
                    "id": emp.id,
                    "employee_first_name": emp.employee_first_name,
                    "employee_last_name": emp.employee_last_name,
                    "get_full_name": emp.get_full_name(),
                }
                for emp in obj.employee_id.all()
            ]
        return []

    def get_onboarding_task(self, obj):
        tasks = obj.onboarding_task.all()
        if tasks.exists():
            return [
                {
                    "id": task.id,
                    "task_title": task.task_title,
                }
                for task in tasks
            ]
        return []


class OnboardingTaskSerializer(serializers.ModelSerializer):
    stage_id = serializers.SerializerMethodField()
    stage_id_write = serializers.PrimaryKeyRelatedField(
        queryset=OnboardingStage.objects.all(),
        source="stage_id",
        write_only=True,
        required=False,
    )
    candidates = serializers.SerializerMethodField()
    candidates_ids = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        many=True,
        source="candidates",
        write_only=True,
        required=False,
    )
    employee_id = serializers.SerializerMethodField()
    employee_id_ids = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        many=True,
        source="employee_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = OnboardingTask
        fields = "__all__"
        extra_kwargs = {
            "candidates": {"read_only": True},
            "employee_id": {"read_only": True},
        }

    def get_stage_id(self, obj):
        if obj.stage_id:
            return {
                "id": obj.stage_id.id,
                "stage_title": obj.stage_id.stage_title,
            }
        return None

    def get_candidates(self, obj):
        if obj.candidates.exists():
            return [
                {
                    "id": cand.id,
                    "name": cand.name,
                    "email": cand.email,
                }
                for cand in obj.candidates.all()
            ]
        return []

    def get_employee_id(self, obj):
        if obj.employee_id.exists():
            return [
                {
                    "id": emp.id,
                    "employee_first_name": emp.employee_first_name,
                    "employee_last_name": emp.employee_last_name,
                    "get_full_name": emp.get_full_name(),
                }
                for emp in obj.employee_id.all()
            ]
        return []


class CandidateStageSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )
    onboarding_stage_id = serializers.SerializerMethodField()
    onboarding_stage_id_write = serializers.PrimaryKeyRelatedField(
        queryset=OnboardingStage.objects.all(),
        source="onboarding_stage_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = CandidateStage
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None

    def get_onboarding_stage_id(self, obj):
        if obj.onboarding_stage_id:
            return {
                "id": obj.onboarding_stage_id.id,
                "stage_title": obj.onboarding_stage_id.stage_title,
            }
        return None


class CandidateTaskSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )
    stage_id = serializers.SerializerMethodField()
    stage_id_write = serializers.PrimaryKeyRelatedField(
        queryset=OnboardingStage.objects.all(),
        source="stage_id",
        write_only=True,
        required=False,
    )
    onboarding_task_id = serializers.SerializerMethodField()
    onboarding_task_id_write = serializers.PrimaryKeyRelatedField(
        queryset=OnboardingTask.objects.all(),
        source="onboarding_task_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = CandidateTask
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None

    def get_stage_id(self, obj):
        if obj.stage_id:
            return {
                "id": obj.stage_id.id,
                "stage_title": obj.stage_id.stage_title,
            }
        return None

    def get_onboarding_task_id(self, obj):
        if obj.onboarding_task_id:
            return {
                "id": obj.onboarding_task_id.id,
                "task_title": obj.onboarding_task_id.task_title,
            }
        return None


class OnboardingPortalSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = OnboardingPortal
        fields = "__all__"
        # token is a credential, not data about the portal: onboarding/urls
        # routes user-creation, profile-view, employee-creation and
        # employee-bank-details on <str:token> alone, and those views carry
        # no authentication decorator -- holding the token is what grants
        # access. `fields = "__all__"` put it in every response body, where
        # it reaches request logs, proxies and browser history.
        #
        # write_only rather than excluding it: the field is populated
        # server-side with secrets.token_hex, so nothing needs to read it
        # back, but keeping it writable leaves the create path working.
        extra_kwargs = {"token": {"write_only": True}}

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None
