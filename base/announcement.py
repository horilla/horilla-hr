"""
Module for managing announcements, including creation, updates, comments, and views.
"""

import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.forms import AnnouncementCommentForm, AnnouncementForm
from base.methods import closest_numbers, filter_own_records
from base.models import (
    Announcement,
    AnnouncementComment,
    AnnouncementExpire,
    AnnouncementView,
    Attachment,
)
from employee.models import Employee
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http.response import HorillaRedirect
from horilla_auth.models import HorillaUser
from notifications.signals import notify


@login_required
@hx_request_required
def announcement_list(request):
    """
    Renders a list of announcements for the authenticated user.

    This view fetches all announcements and updates their expiration dates if not already set.
    It filters announcements based on the user's permissions and whether the announcements
    are still valid (not expired). Additionally, it checks if the user has viewed each announcement.
    """
    general_expire_date = (
        AnnouncementExpire.objects.values_list("days", flat=True).first() or 30
    )
    announcements = Announcement.objects.all()
    announcements_to_update = []

    for announcement in announcements.filter(expire_date__isnull=True):
        announcement.expire_date = announcement.created_at + timedelta(
            days=general_expire_date
        )
        announcements_to_update.append(announcement)

    if announcements_to_update:
        Announcement.objects.bulk_update(announcements_to_update, ["expire_date"])

    has_view_permission = request.user.has_perm("base.view_announcement")
    announcements = announcements.filter(expire_date__gte=datetime.today().date())
    announcement_items = (
        announcements
        if has_view_permission
        else announcements.filter(
            Q(employees=request.user.employee_get) | Q(employees__isnull=True)
        )
    )

    filtered_announcements = announcement_items.prefetch_related(
        "announcementview_set"
    ).order_by("-created_at")
    for announcement in filtered_announcements:
        announcement.has_viewed = announcement.announcementview_set.filter(
            user=request.user, viewed=True
        ).exists()
    instance_ids = json.dumps([instance.id for instance in filtered_announcements])
    context = {
        "announcements": filtered_announcements,
        "general_expire_date": general_expire_date,
        "instance_ids": instance_ids,
    }
    return render(request, "announcement/announcements_list.html", context)


@login_required
@hx_request_required
def create_announcement(request):
    """
    Create a new announcement and notify relevant users.
    """
    form = AnnouncementForm()
    if request.method == "POST":
        form = AnnouncementForm(request.POST, request.FILES)
        if form.is_valid():
            announcement, attachment_ids = form.save(commit=False)
            announcement.save()
            announcement.attachments.set(attachment_ids)

            employees = form.cleaned_data["employees"]
            departments = form.cleaned_data["department"]
            job_positions = form.cleaned_data["job_position"]
            company = form.cleaned_data["company_id"]

            announcement.department.set(departments)
            announcement.job_position.set(job_positions)
            announcement.company_id.set(company)

            dept_ids = departments.values_list("id", flat=True)
            job_ids = job_positions.values_list("id", flat=True)

            employees_from_dept = Employee.objects.filter(
                employee_work_info__department_id__in=dept_ids
            )
            employees_from_job = Employee.objects.filter(
                employee_work_info__job_position_id__in=job_ids
            )

            all_employees = (
                employees | employees_from_dept | employees_from_job
            ).distinct()
            announcement.employees.add(*all_employees)

            all_emps = employees_from_dept | employees_from_job | employees
            user_map = HorillaUser.objects.filter(employee_get__in=all_emps).distinct()

            dept_emp_ids = set(employees_from_dept.values_list("id", flat=True))
            job_emp_ids = set(employees_from_job.values_list("id", flat=True))
            direct_emp_ids = set(employees.values_list("id", flat=True))

            notified_ids = dept_emp_ids.union(job_emp_ids)
            direct_only_ids = direct_emp_ids - notified_ids

            sender = request.user.employee_get

            def send_notification(users, verb):
                if users.exists():
                    notify.send(
                        sender,
                        recipient=users,
                        verb=verb,
                        verb_ar="لقد تم ذكرك في إعلان.",
                        verb_de="Sie wurden in einer Ankündigung erwähnt.",
                        verb_es="Has sido mencionado en un anuncio.",
                        verb_fr="Vous avez été mentionné dans une annonce.",
                        redirect="/",
                        icon="chatbox-ellipses",
                    )

            send_notification(
                user_map.filter(employee_get__id__in=dept_emp_ids),
                _("Your department was mentioned in an announcement."),
            )
            send_notification(
                user_map.filter(employee_get__id__in=job_emp_ids),
                _("Your job position was mentioned in an announcement."),
            )
            send_notification(
                user_map.filter(employee_get__id__in=direct_only_ids),
                _("You have been mentioned in an announcement."),
            )

            messages.success(request, _("Announcement created successfully."))
            form = AnnouncementForm()  # Reset the form

            emp_dep = HorillaUser.objects.filter(
                employee_get__employee_work_info__department_id__in=departments
            )
            emp_jobs = HorillaUser.objects.filter(
                employee_get__employee_work_info__job_position_id__in=job_positions
            )
            employees = employees | Employee.objects.filter(
                employee_work_info__department_id__in=departments
            )
            employees = employees | Employee.objects.filter(
                employee_work_info__job_position_id__in=job_positions
            )
            announcement.employees.add(*employees)
            announcement.save()

            notify.send(
                request.user.employee_get,
                recipient=emp_dep,
                verb="Your department was mentioned in a post.",
                verb_ar="تم ذكر قسمك في منشور.",
                verb_de="Ihr Abteilung wurde in einem Beitrag erwähnt.",
                verb_es="Tu departamento fue mencionado en una publicación.",
                verb_fr="Votre département a été mentionné dans un post.",
                redirect="/",
                icon="chatbox-ellipses",
            )

            notify.send(
                request.user.employee_get,
                recipient=emp_jobs,
                verb="Your job position was mentioned in a post.",
                verb_ar="تم ذكر وظيفتك في منشور.",
                verb_de="Ihre Arbeitsposition wurde in einem Beitrag erwähnt.",
                verb_es="Tu puesto de trabajo fue mencionado en una publicación.",
                verb_fr="Votre poste de travail a été mentionné dans un post.",
                redirect="/",
                icon="chatbox-ellipses",
            )
            form = AnnouncementForm()
    return render(request, "announcement/announcement_form.html", {"form": form})


@login_required
@hx_request_required
@permission_required("base.delete_announcement")
def delete_announcement(request, anoun_id):
    """
    This method is used to delete announcements.
    """
    from horilla.horilla_middlewares import _thread_locals

    announcement = Announcement.find(anoun_id)
    if announcement:
        announcement.delete()
        messages.success(request, _("Announcement deleted successfully."))

    instance_ids = request.GET.get("instance_ids", "[]")
    try:
        instance_ids_list = json.loads(instance_ids) if instance_ids else []
    except (json.JSONDecodeError, TypeError):
        instance_ids_list = []

    __, next_instance_id = closest_numbers(instance_ids_list, anoun_id)
    if anoun_id in instance_ids_list:
        instance_ids_list.remove(anoun_id)

    if not instance_ids_list:
        # Last announcement deleted — refresh the page to show empty state
        return HorillaRedirect(request)

    if next_instance_id and next_instance_id != anoun_id:
        url = reverse("announcement-single-view", kwargs={"pk": next_instance_id})
        return redirect(f"{url}?instance_ids={json.dumps(instance_ids_list)}")

    return HorillaRedirect(request)


@login_required
@hx_request_required
def update_announcement(request, anoun_id):
    """
    This method renders form and template to update Announcement
    """

    announcement = Announcement.objects.get(id=anoun_id)
    form = AnnouncementForm(instance=announcement)
    existing_attachments = list(announcement.attachments.all())

    instance_ids = request.GET.get("instance_ids")

    if request.method == "POST":
        form = AnnouncementForm(request.POST, request.FILES, instance=announcement)
        if form.is_valid():
            anou, attachment_ids = form.save(commit=False)
            anou.save()
            if attachment_ids:
                all_attachments = set(existing_attachments) | set(
                    Attachment.objects.filter(id__in=attachment_ids)
                )
                anou.attachments.set(all_attachments)
            else:
                anou.attachments.set(existing_attachments)

            employees = form.cleaned_data["employees"]
            departments = form.cleaned_data["department"]
            job_positions = form.cleaned_data["job_position"]
            company = form.cleaned_data["company_id"]
            anou.department.set(departments)
            anou.job_position.set(job_positions)
            anou.company_id.set(company)
            messages.success(request, _("Announcement updated successfully."))

            emp_dep = HorillaUser.objects.filter(
                employee_get__employee_work_info__department_id__in=departments
            )
            emp_jobs = HorillaUser.objects.filter(
                employee_get__employee_work_info__job_position_id__in=job_positions
            )
            employees = employees | Employee.objects.filter(
                employee_work_info__department_id__in=departments
            )
            employees = employees | Employee.objects.filter(
                employee_work_info__job_position_id__in=job_positions
            )
            anou.employees.add(*employees)

            notify.send(
                request.user.employee_get,
                recipient=emp_dep,
                verb="Your department was mentioned in a post.",
                verb_ar="تم ذكر قسمك في منشور.",
                verb_de="Ihr Abteilung wurde in einem Beitrag erwähnt.",
                verb_es="Tu departamento fue mencionado en una publicación.",
                verb_fr="Votre département a été mentionné dans un post.",
                redirect="/",
                icon="chatbox-ellipses",
            )

            notify.send(
                request.user.employee_get,
                recipient=emp_jobs,
                verb="Your job position was mentioned in a post.",
                verb_ar="تم ذكر وظيفتك في منشور.",
                verb_de="Ihre Arbeitsposition wurde in einem Beitrag erwähnt.",
                verb_es="Tu puesto de trabajo fue mencionado en una publicación.",
                verb_fr="Votre poste de travail a été mentionné dans un post.",
                redirect="/",
                icon="chatbox-ellipses",
            )
    return render(
        request,
        "announcement/announcement_update_form.html",
        {
            "form": form,
            "instance_ids": instance_ids,
            "hx_target": request.META.get("HTTP_HX_TARGET", ""),
        },
    )


@login_required
@hx_request_required
@permission_required("base.change_announcement")
def remove_announcement_file(request, obj_id, attachment_id):
    announcement = get_object_or_404(Announcement, id=obj_id)
    attachment = get_object_or_404(Attachment, id=attachment_id)

    announcement.attachments.remove(attachment)
    messages.success(request, _("The file has been successfully deleted."))
    return HttpResponse("<script>reloadMessage();</script>")


@login_required
@hx_request_required
def create_announcement_comment(request, anoun_id):
    """
    This method renders form and template to create Announcement comments
    """
    anoun = Announcement.objects.filter(id=anoun_id).first()
    emp = request.user.employee_get
    form = AnnouncementCommentForm(
        initial={"employee_id": emp.id, "request_id": anoun_id}
    )
    comments = AnnouncementComment.objects.filter(announcement_id=anoun_id)
    commentators = []
    if comments:
        for i in comments:
            commentators.append(i.employee_id.employee_user_id)
    unique_users = list(set(commentators))

    if request.method == "POST":
        form = AnnouncementCommentForm(request.POST)
        if form.is_valid():
            form.instance.employee_id = emp
            form.instance.announcement_id = anoun
            form.save()
            form = AnnouncementCommentForm(
                initial={"employee_id": emp.id, "request_id": anoun_id}
            )
            messages.success(request, _("You commented a post."))
            notify.send(
                request.user.employee_get,
                recipient=unique_users,
                verb=f"Comment under the announcement {anoun.title}.",
                verb_ar=f"تعليق تحت الإعلان {anoun.title}.",
                verb_de=f"Kommentar unter der Ankündigung {anoun.title}.",
                verb_es=f"Comentario bajo el anuncio {anoun.title}.",
                verb_fr=f"Commentaire sous l'annonce {anoun.title}.",
                redirect="/",
                icon="chatbox-ellipses",
            )
        return redirect("announcement-view-comment", anoun_id=anoun_id)

    return render(
        request,
        "announcement/comment_view.html",
        {"form": form, "request_id": anoun_id},
    )


@login_required
@hx_request_required
def comment_view(request, anoun_id):
    """
    This method is used to view all comments in the announcements
    """
    announcement = Announcement.objects.filter(id=anoun_id).first()
    if not announcement:
        messages.error(request, _("Announcement not found."))
        return HorillaRedirect(request)
    comments = AnnouncementComment.objects.filter(announcement_id=anoun_id).order_by(
        "-created_at"
    )
    if not announcement.public_comments:
        comments = filter_own_records(request, comments, "base.view_announcement")
    no_comments = not comments.exists()

    return render(
        request,
        "announcement/comment_view.html",
        {
            "comments": comments,
            "no_comments": no_comments,
            "request_id": anoun_id,
            "announcement": announcement,
        },
    )


@login_required
@hx_request_required
def delete_announcement_comment(request, comment_id):
    """
    This method is used to delete announcement comments
    """
    comment = get_object_or_404(AnnouncementComment, id=comment_id)

    if not (
        request.user.has_perm("base.delete_announcementcomment")
        or comment.created_by == request.user
    ):
        messages.error(request, _("You don't have permission to delete this comment."))
        return HttpResponse(status=403)
    comment.delete()
    messages.success(request, _("Comment deleted successfully!"))
    return HttpResponse()


@login_required
@hx_request_required
def announcement_single_view(request, anoun_id=None):
    """
    This method is used to render single announcements.
    """
    announcement_instance = Announcement.find(anoun_id)
    if not announcement_instance:
        # No id in the URL (the bare "announcement-single-view/" pattern)
        # or an id that doesn't match any record -- the template assumes a
        # real announcement (e.g. {% url 'update-announcement'
        # announcement.id %}), which fails with NoReverseMatch on an empty
        # id rather than rendering blank.
        messages.error(request, _("Announcement not found."))
        return HorillaRedirect(request)
    instance_ids = request.GET.get("instance_ids")
    instance_ids_list = json.loads(instance_ids) if instance_ids else []
    previous_instance_id, next_instance_id = (
        closest_numbers(instance_ids_list, anoun_id)
        if instance_ids_list
        else (None, None)
    )
    if announcement_instance:
        announcement_view_obj, _created = AnnouncementView.objects.get_or_create(
            user=request.user, announcement=announcement_instance
        )
        announcement_view_obj.viewed = True
        announcement_view_obj.save()

    context = {
        "announcement": announcement_instance,
        "instance_ids": instance_ids,
        "previous_instance_id": previous_instance_id,
        "next_instance_id": next_instance_id,
    }

    return render(request, "announcement/announcement_one.html", context)


@login_required
@hx_request_required
@permission_required("base.view_announcement")
def viewed_by(request):
    """
    This method is used to view the employees
    """
    announcement_id = request.GET.get("announcement_id")
    viewed_users = AnnouncementView.objects.filter(
        announcement_id__id=announcement_id, viewed=True
    )
    return render(request, "announcement/viewed_by.html", {"viewed_by": viewed_users})
