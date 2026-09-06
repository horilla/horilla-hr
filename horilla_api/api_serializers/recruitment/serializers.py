"""
horilla_api/api_serializers/recruitment/serializers.py
"""

from rest_framework import serializers

from base.models import Company, JobPosition
from employee.models import Employee
from recruitment.models import (
    Candidate,
    CandidateDocument,
    CandidateDocumentRequest,
    CandidateRating,
    InterviewSchedule,
    LinkedInAccount,
    Recruitment,
    RecruitmentSurvey,
    RecruitmentSurveyAnswer,
    RejectedCandidate,
    RejectReason,
    Skill,
    SkillZone,
    SkillZoneCandidate,
    Stage,
    SurveyTemplate,
)


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = "__all__"


class SurveyTemplateSerializer(serializers.ModelSerializer):
    company_id = serializers.SerializerMethodField()
    company_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(),
        source="company_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = SurveyTemplate
        fields = "__all__"

    def get_company_id(self, obj):
        if obj.company_id:
            return {
                "id": obj.company_id.id,
                "company": obj.company_id.company,
            }
        return None


class RecruitmentSerializer(serializers.ModelSerializer):
    recruitment_managers = serializers.SerializerMethodField()
    recruitment_managers_ids = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        many=True,
        source="recruitment_managers",
        write_only=True,
        required=False,
    )
    open_positions = serializers.SerializerMethodField()
    open_positions_ids = serializers.PrimaryKeyRelatedField(
        queryset=JobPosition.objects.all(),
        many=True,
        source="open_positions",
        write_only=True,
        required=False,
    )
    company_id = serializers.SerializerMethodField()
    company_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(),
        source="company_id",
        write_only=True,
        required=False,
    )
    job_position_id = serializers.SerializerMethodField()
    job_position_id_write = serializers.PrimaryKeyRelatedField(
        queryset=JobPosition.objects.all(),
        source="job_position_id",
        write_only=True,
        required=False,
    )
    skills = serializers.SerializerMethodField()
    skills_ids = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.all(),
        many=True,
        source="skills",
        write_only=True,
        required=False,
    )
    survey_templates = serializers.SerializerMethodField()
    survey_templates_ids = serializers.PrimaryKeyRelatedField(
        queryset=SurveyTemplate.objects.all(),
        many=True,
        source="survey_templates",
        write_only=True,
        required=False,
    )
    linkedin_account_id = serializers.SerializerMethodField()
    linkedin_account_id_write = serializers.PrimaryKeyRelatedField(
        queryset=LinkedInAccount.objects.all(),
        source="linkedin_account_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Recruitment
        fields = "__all__"
        extra_kwargs = {
            "recruitment_managers": {"read_only": True},
            "open_positions": {"read_only": True},
            "skills": {"read_only": True},
            "survey_templates": {"read_only": True},
        }

    def get_recruitment_managers(self, obj):
        if obj.recruitment_managers.exists():
            return [
                {
                    "id": emp.id,
                    "employee_first_name": emp.employee_first_name,
                    "employee_last_name": emp.employee_last_name,
                    "get_full_name": emp.get_full_name(),
                }
                for emp in obj.recruitment_managers.all()
            ]
        return []

    def get_open_positions(self, obj):
        if obj.open_positions.exists():
            return [
                {
                    "id": pos.id,
                    "job_position": pos.job_position,
                }
                for pos in obj.open_positions.all()
            ]
        return []

    def get_company_id(self, obj):
        if obj.company_id:
            return {
                "id": obj.company_id.id,
                "company": obj.company_id.company,
            }
        return None

    def get_job_position_id(self, obj):
        if obj.job_position_id:
            return {
                "id": obj.job_position_id.id,
                "job_position": obj.job_position_id.job_position,
            }
        return None

    def get_skills(self, obj):
        if obj.skills.exists():
            return [
                {
                    "id": skill.id,
                    "title": skill.title,
                }
                for skill in obj.skills.all()
            ]
        return []

    def get_survey_templates(self, obj):
        if obj.survey_templates.exists():
            return [
                {
                    "id": template.id,
                    "title": template.title,
                }
                for template in obj.survey_templates.all()
            ]
        return []

    def get_linkedin_account_id(self, obj):
        if obj.linkedin_account_id:
            return {
                "id": obj.linkedin_account_id.id,
                "username": obj.linkedin_account_id.username,
            }
        return None


class StageSerializer(serializers.ModelSerializer):
    recruitment_id = serializers.SerializerMethodField()
    recruitment_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Recruitment.objects.all(),
        source="recruitment_id",
        write_only=True,
        required=False,
    )
    stage_managers = serializers.SerializerMethodField()
    stage_managers_ids = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        many=True,
        source="stage_managers",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Stage
        fields = "__all__"
        extra_kwargs = {
            "stage_managers": {"read_only": True},
        }

    def get_recruitment_id(self, obj):
        if obj.recruitment_id:
            return {
                "id": obj.recruitment_id.id,
                "title": obj.recruitment_id.title,
            }
        return None

    def get_stage_managers(self, obj):
        if obj.stage_managers.exists():
            return [
                {
                    "id": emp.id,
                    "employee_first_name": emp.employee_first_name,
                    "employee_last_name": emp.employee_last_name,
                    "get_full_name": emp.get_full_name(),
                }
                for emp in obj.stage_managers.all()
            ]
        return []


class CandidateSerializer(serializers.ModelSerializer):
    recruitment_id = serializers.SerializerMethodField()
    recruitment_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Recruitment.objects.all(),
        source="recruitment_id",
        write_only=True,
        required=False,
    )
    job_position_id = serializers.SerializerMethodField()
    job_position_id_write = serializers.PrimaryKeyRelatedField(
        queryset=JobPosition.objects.all(),
        source="job_position_id",
        write_only=True,
        required=False,
    )
    stage_id = serializers.SerializerMethodField()
    stage_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Stage.objects.all(), source="stage_id", write_only=True, required=False
    )
    converted_employee_id = serializers.SerializerMethodField()
    converted_employee_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        source="converted_employee_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Candidate
        fields = "__all__"

    def get_recruitment_id(self, obj):
        if obj.recruitment_id:
            return {
                "id": obj.recruitment_id.id,
                "title": obj.recruitment_id.title,
            }
        return None

    def get_job_position_id(self, obj):
        if obj.job_position_id:
            return {
                "id": obj.job_position_id.id,
                "job_position": obj.job_position_id.job_position,
            }
        return None

    def get_stage_id(self, obj):
        if obj.stage_id:
            return {
                "id": obj.stage_id.id,
                "stage": obj.stage_id.stage,
                "stage_type": obj.stage_id.stage_type,
            }
        return None

    def get_converted_employee_id(self, obj):
        if obj.converted_employee_id:
            return {
                "id": obj.converted_employee_id.id,
                "employee_first_name": obj.converted_employee_id.employee_first_name,
                "employee_last_name": obj.converted_employee_id.employee_last_name,
                "get_full_name": obj.converted_employee_id.get_full_name(),
            }
        return None


class InterviewScheduleSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
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
        model = InterviewSchedule
        fields = "__all__"
        extra_kwargs = {
            "employee_id": {"read_only": True},
        }

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
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


class SkillZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillZone
        fields = "__all__"


class SkillZoneCandidateSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )
    skill_zone_id = serializers.SerializerMethodField()
    skill_zone_id_write = serializers.PrimaryKeyRelatedField(
        queryset=SkillZone.objects.all(),
        source="skill_zone_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = SkillZoneCandidate
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None

    def get_skill_zone_id(self, obj):
        if obj.skill_zone_id:
            return {
                "id": obj.skill_zone_id.id,
                "title": obj.skill_zone_id.title,
            }
        return None


class CandidateRatingSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = CandidateRating
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None


class RejectReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = RejectReason
        fields = "__all__"


class RejectedCandidateSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )
    reject_reason_id = serializers.SerializerMethodField()
    reject_reason_id_ids = serializers.PrimaryKeyRelatedField(
        queryset=RejectReason.objects.all(),
        many=True,
        source="reject_reason_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = RejectedCandidate
        fields = "__all__"
        extra_kwargs = {
            "reject_reason_id": {"read_only": True},
        }

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None

    def get_reject_reason_id(self, obj):
        if obj.reject_reason_id.exists():
            return [
                {
                    "id": reason.id,
                    "title": reason.title,
                }
                for reason in obj.reject_reason_id.all()
            ]
        return []


class CandidateDocumentRequestSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = CandidateDocumentRequest
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None


class CandidateDocumentSerializer(serializers.ModelSerializer):
    candidate_id = serializers.SerializerMethodField()
    candidate_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Candidate.objects.all(),
        source="candidate_id",
        write_only=True,
        required=False,
    )
    document_request_id = serializers.SerializerMethodField()
    document_request_id_write = serializers.PrimaryKeyRelatedField(
        queryset=CandidateDocumentRequest.objects.all(),
        source="document_request_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = CandidateDocument
        fields = "__all__"

    def get_candidate_id(self, obj):
        if obj.candidate_id:
            return {
                "id": obj.candidate_id.id,
                "name": obj.candidate_id.name,
                "email": obj.candidate_id.email,
            }
        return None

    def get_document_request_id(self, obj):
        if obj.document_request_id:
            return {
                "id": obj.document_request_id.id,
                "title": obj.document_request_id.title,
            }
        return None


class LinkedInAccountSerializer(serializers.ModelSerializer):
    company_id = serializers.SerializerMethodField()
    company_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(),
        source="company_id",
        write_only=True,
        required=False,
    )

    class Meta:
        model = LinkedInAccount
        fields = "__all__"
        # api_token is a credential. `fields = "__all__"` put it in every
        # response body, where it reaches request logs, proxies and browser
        # history. write_only keeps it settable through this serializer --
        # which the create/update routes rely on -- while never emitting it.
        extra_kwargs = {"api_token": {"write_only": True}}

    def get_company_id(self, obj):
        if obj.company_id:
            return {
                "id": obj.company_id.id,
                "company": obj.company_id.company,
            }
        return None
