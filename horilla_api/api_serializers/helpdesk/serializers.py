"""
horilla_api/api_serializers/helpdesk/serializers.py
"""

from rest_framework import serializers

from base.models import Tags
from employee.models import Employee
from helpdesk.models import (
    FAQ,
    Attachment,
    ClaimRequest,
    Comment,
    DepartmentManager,
    FAQCategory,
    Ticket,
    TicketType,
)


class TicketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketType
        fields = "__all__"


class FAQCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQCategory
        fields = "__all__"


class FAQSerializer(serializers.ModelSerializer):
    category = FAQCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=FAQCategory.objects.all(), source="category", write_only=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tags.objects.all(), many=True, required=False
    )

    class Meta:
        model = FAQ
        fields = "__all__"


class DepartmentManagerSerializer(serializers.ModelSerializer):
    manager = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentManager
        fields = "__all__"

    def get_manager(self, obj):
        if obj.manager:
            return {
                "id": obj.manager.id,
                "employee_first_name": obj.manager.employee_first_name,
                "employee_last_name": obj.manager.employee_last_name,
                "get_full_name": obj.manager.get_full_name(),
            }
        return None

    def get_department(self, obj):
        if obj.department:
            return {
                "id": obj.department.id,
                "department": obj.department.department,
            }
        return None


class CommentSerializer(serializers.ModelSerializer):
    employee_id = serializers.SerializerMethodField()
    employee_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        source="employee_id",
        write_only=True,
        required=False,
    )
    ticket_id = serializers.PrimaryKeyRelatedField(
        queryset=Ticket.objects.all(), source="ticket", write_only=True
    )

    class Meta:
        model = Comment
        fields = "__all__"

    def get_employee_id(self, obj):
        if obj.employee_id:
            return {
                "id": obj.employee_id.id,
                "employee_first_name": obj.employee_id.employee_first_name,
                "employee_last_name": obj.employee_id.employee_last_name,
                "get_full_name": obj.employee_id.get_full_name(),
            }
        return None


class AttachmentSerializer(serializers.ModelSerializer):
    ticket_id = serializers.PrimaryKeyRelatedField(
        queryset=Ticket.objects.all(), source="ticket", write_only=True, required=False
    )
    comment_id = serializers.PrimaryKeyRelatedField(
        queryset=Comment.objects.all(),
        source="comment",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Attachment
        fields = "__all__"


class ClaimRequestSerializer(serializers.ModelSerializer):
    ticket_id = serializers.SerializerMethodField()
    ticket_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Ticket.objects.all(), source="ticket_id", write_only=True
    )
    employee_id = serializers.SerializerMethodField()
    employee_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), source="employee_id", write_only=True
    )

    class Meta:
        model = ClaimRequest
        fields = "__all__"
        read_only_fields = ("is_approved",)

    def get_ticket_id(self, obj):
        if obj.ticket_id:
            return {
                "id": obj.ticket_id.id,
                "title": obj.ticket_id.title,
            }
        return None

    def get_employee_id(self, obj):
        if obj.employee_id:
            return {
                "id": obj.employee_id.id,
                "employee_first_name": obj.employee_id.employee_first_name,
                "employee_last_name": obj.employee_id.employee_last_name,
                "get_full_name": obj.employee_id.get_full_name(),
            }
        return None


class TicketSerializer(serializers.ModelSerializer):
    employee_id = serializers.SerializerMethodField()
    employee_id_write = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        source="employee_id",
        write_only=True,
        required=False,
    )
    ticket_type = TicketTypeSerializer(read_only=True)
    ticket_type_id = serializers.PrimaryKeyRelatedField(
        queryset=TicketType.objects.all(), source="ticket_type", write_only=True
    )
    assigned_to = serializers.SerializerMethodField()
    assigned_to_ids = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        many=True,
        source="assigned_to",
        write_only=True,
        required=False,
    )
    tags = serializers.SerializerMethodField()
    tags_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tags.objects.all(),
        many=True,
        source="tags",
        write_only=True,
        required=False,
    )
    raised_on_display = serializers.SerializerMethodField()
    comments = CommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = "__all__"
        extra_kwargs = {
            "assigned_to": {"read_only": True},
            "tags": {"read_only": True},
            "status": {"read_only": True},
        }

    def get_employee_id(self, obj):
        if obj.employee_id:
            return {
                "id": obj.employee_id.id,
                "employee_first_name": obj.employee_id.employee_first_name,
                "employee_last_name": obj.employee_id.employee_last_name,
                "get_full_name": obj.employee_id.get_full_name(),
            }
        return None

    def get_assigned_to(self, obj):
        if obj.assigned_to.exists():
            return [
                {
                    "id": emp.id,
                    "employee_first_name": emp.employee_first_name,
                    "employee_last_name": emp.employee_last_name,
                    "get_full_name": emp.get_full_name(),
                }
                for emp in obj.assigned_to.all()
            ]
        return []

    def get_tags(self, obj):
        if obj.tags.exists():
            return [{"id": tag.id, "name": tag.name} for tag in obj.tags.all()]
        return []

    def get_raised_on_display(self, obj):
        try:
            return obj.get_raised_on()
        except:
            return obj.raised_on
