from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from asset.models import *


class AssetCategorySerializer(serializers.ModelSerializer):
    asset_count = serializers.SerializerMethodField()

    class Meta:
        model = AssetCategory
        exclude = ["created_at", "created_by", "company_id", "is_active"]

    def get_asset_count(self, obj):
        return obj.asset_set.all().count()


class AssetCategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = ["id", "asset_category_name"]

    def get_asset_count(self, obj):
        return obj.asset_set.all().count()


class AssetLotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetLot
        fields = "__all__"


class AssetGetAllSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["id", "asset_name", "asset_status"]


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = "__all__"


class AssetAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetAssignment
        fields = "__all__"


class AssetAssignmentGetSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    asset_category = serializers.SerializerMethodField()
    allocated_user = serializers.SerializerMethodField()

    class Meta:
        model = AssetAssignment
        fields = [
            "id",
            "asset",
            "asset_category",
            "allocated_user",
            "assigned_date",
            "return_status",
        ]

    def get_asset(self, obj):
        return obj.asset_id.asset_name

    def get_asset_category(self, obj):
        return obj.asset_id.asset_category_id.asset_category_name

    def get_allocated_user(self, obj):
        return EmployeeGetSerializer(obj.assigned_to_employee_id).data


class AssetRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetRequest
        fields = "__all__"
        read_only_fields = ("asset_request_status",)


class AssetRequestGetSerializer(serializers.ModelSerializer):
    asset_category_id = serializers.SerializerMethodField()
    requested_employee_id = serializers.SerializerMethodField()

    class Meta:
        model = AssetRequest
        fields = "__all__"

    def get_asset_category_id(self, obj):
        return AssetCategoryMiniSerializer(obj.asset_category_id).data

    def get_requested_employee_id(self, obj):
        return EmployeeGetSerializer(obj.requested_employee_id).data


class EmployeeGetSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "full_name", "employee_profile", "badge_id"]

    def get_full_name(self, obj):
        return obj.get_full_name()


class AssetApproveSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetAssignment
        fields = [
            "id",
            "asset_id",
            "assigned_to_employee_id",
            "assigned_by_employee_id",
            "assign_images",
        ]

    def validate_asset_id(self, value):
        asset_request = self.context.get("asset_request")
        asset_category = asset_request.asset_category_id
        if value.asset_category_id != asset_category:
            raise serializers.ValidationError(_("Invalid asset."))
        return value


class AssetReturnSerializer(serializers.ModelSerializer):
    return_status = serializers.CharField(required=True)
    image = serializers.FileField(required=True)

    class Meta:
        model = AssetAssignment
        fields = ["return_status", "return_condition", "image"]

    def validate_return_status(self, value):
        if value not in [status[0] for status in AssetAssignment.STATUS]:
            raise serializers.ValidationError(_("Invalid Choice"))
        return value

    def validate(self, data):
        if self.instance.return_date:
            raise serializers.ValidationError(_("Already Returned"))
        return data


# class ReturnImageSerializer(serializers.ModelSerializer):
#     image = serializers.FileField(required=True)
#     class Meta:
#         model = ReturnImages
#         fields = '__all__'
