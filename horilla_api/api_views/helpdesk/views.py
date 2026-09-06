"""
horilla_api/api_views/helpdesk/views.py
"""

from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.methods import filtersubordinates
from helpdesk.filter import FAQCategoryFilter, FAQFilter, TicketFilter
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
from horilla_api.api_serializers.helpdesk.serializers import (
    AttachmentSerializer,
    ClaimRequestSerializer,
    CommentSerializer,
    DepartmentManagerSerializer,
    FAQCategorySerializer,
    FAQSerializer,
    TicketSerializer,
    TicketTypeSerializer,
)

from ...api_decorators.base.decorators import (
    manager_permission_required,
    permission_required,
)
from ...api_methods.base.methods import groupby_queryset, permission_based_queryset


def object_check(cls, pk):
    try:
        obj = cls.objects.get(id=pk)
        return obj
    except cls.DoesNotExist:
        return None


def can_access_ticket(user, ticket):
    """Viewer perm, ticket owner, or an assignee."""
    employee = user.employee_get
    return (
        user.has_perm("helpdesk.view_ticket")
        or ticket.employee_id == employee
        or ticket.assigned_to.filter(id=employee.id).exists()
    )


# Ticket Type Views
class TicketTypeGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    queryset = TicketType.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return TicketType.objects.none()
        return TicketType.objects.all()

    def get(self, request):
        ticket_types = self.get_queryset()
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(ticket_types, request)
        serializer = TicketTypeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @permission_required("helpdesk.add_tickettype")
    def post(self, request):
        serializer = TicketTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketTypeGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        ticket_type = object_check(TicketType, pk)
        if ticket_type is None:
            return Response({"error": _("TicketType not found")}, status=404)
        serializer = TicketTypeSerializer(ticket_type)
        return Response(serializer.data, status=200)

    @permission_required("helpdesk.change_tickettype")
    def put(self, request, pk):
        ticket_type = object_check(TicketType, pk)
        if ticket_type is None:
            return Response({"error": _("TicketType not found")}, status=404)
        serializer = TicketTypeSerializer(ticket_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @permission_required("helpdesk.delete_tickettype")
    def delete(self, request, pk):
        ticket_type = object_check(TicketType, pk)
        if ticket_type is None:
            return Response({"error": _("TicketType not found")}, status=404)
        try:
            ticket_type.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# FAQ Category Views
class FAQCategoryGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FAQCategoryFilter
    queryset = FAQCategory.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return FAQCategory.objects.none()
        return FAQCategory.objects.all()

    def get(self, request):
        faq_categories = self.get_queryset()
        filterset = self.filterset_class(request.GET, queryset=faq_categories)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = FAQCategorySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @permission_required("helpdesk.add_faqcategory")
    def post(self, request):
        serializer = FAQCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FAQCategoryGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        faq_category = object_check(FAQCategory, pk)
        if faq_category is None:
            return Response({"error": _("FAQCategory not found")}, status=404)
        serializer = FAQCategorySerializer(faq_category)
        return Response(serializer.data, status=200)

    @permission_required("helpdesk.change_faqcategory")
    def put(self, request, pk):
        faq_category = object_check(FAQCategory, pk)
        if faq_category is None:
            return Response({"error": _("FAQCategory not found")}, status=404)
        serializer = FAQCategorySerializer(faq_category, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @permission_required("helpdesk.delete_faqcategory")
    def delete(self, request, pk):
        faq_category = object_check(FAQCategory, pk)
        if faq_category is None:
            return Response({"error": _("FAQCategory not found")}, status=404)
        try:
            faq_category.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# FAQ Views
class FAQGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FAQFilter
    queryset = FAQ.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return FAQ.objects.none()
        return FAQ.objects.all()

    def get(self, request, category_id=None):
        if category_id:
            faqs = FAQ.objects.filter(category_id=category_id)
        else:
            faqs = self.get_queryset()
        filterset = self.filterset_class(request.GET, queryset=faqs)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = FAQSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @permission_required("helpdesk.add_faq")
    def post(self, request):
        serializer = FAQSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FAQGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        faq = object_check(FAQ, pk)
        if faq is None:
            return Response({"error": _("FAQ not found")}, status=404)
        serializer = FAQSerializer(faq)
        return Response(serializer.data, status=200)

    @permission_required("helpdesk.change_faq")
    def put(self, request, pk):
        faq = object_check(FAQ, pk)
        if faq is None:
            return Response({"error": _("FAQ not found")}, status=404)
        serializer = FAQSerializer(faq, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @permission_required("helpdesk.delete_faq")
    def delete(self, request, pk):
        faq = object_check(FAQ, pk)
        if faq is None:
            return Response({"error": _("FAQ not found")}, status=404)
        try:
            faq.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# Ticket Views
class TicketGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TicketFilter
    queryset = Ticket.objects.none()  # For drf-yasg schema generation

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return Ticket.objects.none()
        if not self.request.user.is_authenticated:
            return Ticket.objects.none()
        user = self.request.user
        perm = "helpdesk.view_ticket"
        queryset = Ticket.objects.all()
        queryset = permission_based_queryset(user, perm, queryset, user_obj=True)
        return queryset

    def get(self, request):
        tickets = self.get_queryset()
        filterset = self.filterset_class(request.GET, queryset=tickets)
        field_name = request.GET.get("groupby_field", None)
        if field_name:
            url = request.build_absolute_uri()
            return groupby_queryset(request, url, field_name, filterset.qs)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(filterset.qs, request)
        serializer = TicketSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Set employee_id from request user if not provided
        data = request.data.copy()
        if not request.user.has_perm("helpdesk.add_ticket") or not (
            data.get("employee_id_write") or data.get("employee_id")
        ):
            data["employee_id_write"] = request.user.employee_get.id
        serializer = TicketSerializer(data=data)
        if serializer.is_valid():
            ticket = serializer.save()
            return Response(
                TicketSerializer(ticket).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        ticket = object_check(Ticket, pk)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        # Check permissions
        user = request.user
        if not (
            user.has_perm("helpdesk.view_ticket")
            or ticket.employee_id == user.employee_get
            or ticket.assigned_to.filter(id=user.employee_get.id).exists()
        ):
            return Response({"error": _("Permission denied")}, status=403)
        serializer = TicketSerializer(ticket)
        return Response(serializer.data, status=200)

    @permission_required("helpdesk.change_ticket")
    def put(self, request, pk):
        ticket = object_check(Ticket, pk)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        serializer = TicketSerializer(ticket, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @permission_required("helpdesk.delete_ticket")
    def delete(self, request, pk):
        ticket = object_check(Ticket, pk)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        try:
            ticket.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class TicketChangeStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @permission_required("helpdesk.change_ticket")
    def put(self, request, pk):
        ticket = object_check(Ticket, pk)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        status_value = request.data.get("status")
        if status_value not in [
            choice[0] for choice in Ticket._meta.get_field("status").choices
        ]:
            return Response({"error": _("Invalid status")}, status=400)
        ticket.status = status_value
        if status_value == "resolved":
            from datetime import date

            ticket.resolved_date = date.today()
        ticket.save()
        return Response(TicketSerializer(ticket).data, status=200)


class TicketArchiveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @permission_required("helpdesk.change_ticket")
    def put(self, request, pk):
        ticket = object_check(Ticket, pk)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        ticket.is_active = False
        ticket.save()
        return Response(TicketSerializer(ticket).data, status=200)


# Comment Views
class CommentGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):
        ticket = object_check(Ticket, ticket_id)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        comments = Comment.objects.filter(ticket_id=ticket_id)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(comments, request)
        serializer = CommentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, ticket_id):
        ticket = object_check(Ticket, ticket_id)
        if ticket is None:
            return Response({"error": _("Ticket not found")}, status=404)
        data = request.data.copy()
        data["ticket_id"] = ticket_id
        if not can_access_ticket(request.user, ticket):
            return Response({"error": _("Permission denied")}, status=403)
        data["employee_id_write"] = request.user.employee_get.id
        serializer = CommentSerializer(data=data)
        if serializer.is_valid():
            comment = serializer.save()
            return Response(
                CommentSerializer(comment).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        comment = object_check(Comment, pk)
        if comment is None:
            return Response({"error": _("Comment not found")}, status=404)
        serializer = CommentSerializer(comment)
        return Response(serializer.data, status=200)

    def put(self, request, pk):
        comment = object_check(Comment, pk)
        if comment is None:
            return Response({"error": _("Comment not found")}, status=404)
        # Check if user owns the comment
        if comment.employee_id != request.user.employee_get:
            return Response({"error": _("Permission denied")}, status=403)
        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        comment = object_check(Comment, pk)
        if comment is None:
            return Response({"error": _("Comment not found")}, status=404)
        # Check if user owns the comment or has permission
        if (
            comment.employee_id != request.user.employee_get
            and not request.user.has_perm("helpdesk.delete_comment")
        ):
            return Response({"error": _("Permission denied")}, status=403)
        try:
            comment.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# Attachment Views
class AttachmentGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id=None, comment_id=None):
        if ticket_id:
            attachments = Attachment.objects.filter(ticket_id=ticket_id)
        elif comment_id:
            attachments = Attachment.objects.filter(comment_id=comment_id)
        else:
            return Response(
                {"error": _("ticket_id or comment_id required")}, status=400
            )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(attachments, request)
        serializer = AttachmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = AttachmentSerializer(data=request.data)
        if serializer.is_valid():
            comment = serializer.validated_data.get("comment")
            ticket = serializer.validated_data.get("ticket") or (
                comment.ticket if comment else None
            )
            if ticket is None:
                return Response(
                    {"error": _("ticket_id or comment_id required")}, status=400
                )
            if not can_access_ticket(request.user, ticket):
                return Response({"error": _("Permission denied")}, status=403)
            attachment = serializer.save()
            return Response(
                AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AttachmentGetDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attachment = object_check(Attachment, pk)
        if attachment is None:
            return Response({"error": _("Attachment not found")}, status=404)
        serializer = AttachmentSerializer(attachment)
        return Response(serializer.data, status=200)

    def delete(self, request, pk):
        attachment = object_check(Attachment, pk)
        if attachment is None:
            return Response({"error": _("Attachment not found")}, status=404)
        ticket = attachment.ticket or (
            attachment.comment.ticket if attachment.comment else None
        )
        if not request.user.has_perm("helpdesk.delete_attachment") and not (
            ticket and can_access_ticket(request.user, ticket)
        ):
            return Response({"error": _("Permission denied")}, status=403)
        try:
            attachment.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# Claim Request Views
class ClaimRequestGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id=None):
        claim_requests = permission_based_queryset(
            request.user, "helpdesk.view_claimrequest", ClaimRequest.objects.all()
        )
        if ticket_id:
            claim_requests = claim_requests.filter(ticket_id=ticket_id)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(claim_requests, request)
        serializer = ClaimRequestSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data["employee_id_write"] = request.user.employee_get.id
        serializer = ClaimRequestSerializer(data=data)
        if serializer.is_valid():
            claim_request = serializer.save()
            return Response(
                ClaimRequestSerializer(claim_request).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClaimRequestApproveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @permission_required("helpdesk.change_ticket")
    def put(self, request, pk):
        claim_request = object_check(ClaimRequest, pk)
        if claim_request is None:
            return Response({"error": _("ClaimRequest not found")}, status=404)
        claim_request.is_approved = True
        claim_request.is_rejected = False
        claim_request.save()
        # Add employee to assigned_to
        ticket = claim_request.ticket_id
        ticket.assigned_to.add(claim_request.employee_id)
        return Response(ClaimRequestSerializer(claim_request).data, status=200)


class ClaimRequestRejectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @permission_required("helpdesk.change_ticket")
    def put(self, request, pk):
        claim_request = object_check(ClaimRequest, pk)
        if claim_request is None:
            return Response({"error": _("ClaimRequest not found")}, status=404)
        claim_request.is_approved = False
        claim_request.is_rejected = True
        claim_request.save()
        return Response(ClaimRequestSerializer(claim_request).data, status=200)


# Department Manager Views
class DepartmentManagerGetCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Handle schema generation for DRF-YASG
        if getattr(self, "swagger_fake_view", False):
            return DepartmentManager.objects.none()
        return DepartmentManager.objects.all()

    def get(self, request):
        department_managers = self.get_queryset()
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(department_managers, request)
        serializer = DepartmentManagerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @permission_required("helpdesk.add_departmentmanager")
    def post(self, request):
        serializer = DepartmentManagerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DepartmentManagerGetUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        department_manager = object_check(DepartmentManager, pk)
        if department_manager is None:
            return Response({"error": _("DepartmentManager not found")}, status=404)
        serializer = DepartmentManagerSerializer(department_manager)
        return Response(serializer.data, status=200)

    @permission_required("helpdesk.change_departmentmanager")
    def put(self, request, pk):
        department_manager = object_check(DepartmentManager, pk)
        if department_manager is None:
            return Response({"error": _("DepartmentManager not found")}, status=404)
        serializer = DepartmentManagerSerializer(department_manager, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)

    @permission_required("helpdesk.delete_departmentmanager")
    def delete(self, request, pk):
        department_manager = object_check(DepartmentManager, pk)
        if department_manager is None:
            return Response({"error": _("DepartmentManager not found")}, status=404)
        try:
            department_manager.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
