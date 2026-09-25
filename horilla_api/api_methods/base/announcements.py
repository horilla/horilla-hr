"""
Who sees which announcement, and how one is shaped for API clients.

Shared by the announcement list and detail endpoints and the mobile home
aggregate, so the three agree on the audience -- previously the list honoured
only the ``employees`` field and showed department- or job-position-targeted
announcements to everyone in the company.
"""

import os
from datetime import date

from bs4 import BeautifulSoup
from django.db.models import Exists, OuterRef, Q

from base.models import Announcement, AnnouncementView

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic"}


def announcements_for(employee):
    """
    Unexpired announcements whose audience includes ``employee``.

    Mirrors the predicate the web self-service dashboard uses
    (``base/ess_dashboard.py``): the denormalised ``filtered_employees`` wins
    when present; otherwise the employee, their department or job position
    must be targeted, or the announcement must target no one (a broadcast).
    """
    today = date.today()
    not_expired = Q(expire_date__gte=today) | Q(expire_date__isnull=True)

    if Announcement.objects.filter(filtered_employees=employee).exists():
        qs = Announcement.objects.filter(not_expired, filtered_employees=employee)
    else:
        work_info = getattr(employee, "employee_work_info", None)
        department = getattr(work_info, "department_id", None)
        job_position = getattr(work_info, "job_position_id", None)
        targeted = (
            Q(employees=employee)
            | (Q(department=department) if department else Q())
            | (Q(job_position=job_position) if job_position else Q())
        )
        broadcast = (
            Q(employees__isnull=True)
            & Q(department__isnull=True)
            & Q(job_position__isnull=True)
        )
        qs = Announcement.objects.filter(not_expired).filter(targeted | broadcast)
    # distinct(): the targeting filters join three many-to-many tables, so a
    # row matching on more than one comes back more than once.
    return qs.distinct()


def visible_announcements(request):
    """
    What ``request.user`` may read: everything unexpired for a holder of
    ``base.view_announcement`` (the management view), otherwise their own
    audience. Annotated with ``has_viewed`` for the caller.
    """
    if request.user.has_perm("base.view_announcement"):
        today = date.today()
        qs = Announcement.objects.filter(
            Q(expire_date__gte=today) | Q(expire_date__isnull=True)
        )
    else:
        qs = announcements_for(request.user.employee_get)
    viewed = AnnouncementView.objects.filter(
        announcement=OuterRef("pk"), user=request.user, viewed=True
    )
    return qs.annotate(has_viewed=Exists(viewed)).order_by("-created_at")


def parse_description(description):
    """
    The HTML body as a flat list of ``{"type", "text"}`` blocks: ``heading``,
    ``paragraph`` or ``bullet``. List items used to be dropped entirely, and
    a plain-text body with no tags came back empty.
    """
    soup = BeautifulSoup(description or "", "html.parser")
    content = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        # A <p> inside an <li> would otherwise be emitted twice.
        if tag.name == "p" and tag.find_parent("li"):
            continue
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if tag.name == "li":
            kind = "bullet"
        elif tag.name.startswith("h"):
            kind = "heading"
        else:
            kind = "paragraph"
        content.append({"type": kind, "text": text})
    if not content:
        text = soup.get_text(" ", strip=True)
        if text:
            content.append({"type": "paragraph", "text": text})
    return content


def serialize_announcement(announcement, has_viewed, detail=False):
    data = {
        "id": announcement.id,
        "title": announcement.title,
        "content": parse_description(announcement.description),
        "created_at": announcement.created_at,
        "expire_date": announcement.expire_date,
        "has_viewed": bool(has_viewed),
    }
    if detail:
        data["attachments"] = [
            {
                "name": os.path.basename(attachment.file.name),
                "url": attachment.file.url,
                "is_image": os.path.splitext(attachment.file.name)[1].lower()
                in _IMAGE_EXTENSIONS,
            }
            for attachment in announcement.attachments.all()
            if attachment.file
        ]
        author = getattr(announcement, "created_by", None)
        employee = getattr(author, "employee_get", None) if author else None
        data["author"] = employee.get_full_name() if employee else None
    return data
