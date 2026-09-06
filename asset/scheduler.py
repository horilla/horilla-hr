"""
scheduler.py

This module is used to register scheduled tasks
"""

from datetime import date, timedelta

from django.urls import reverse

from horilla.scheduling import register_job
from notifications.signals import notify


def notify_expiring_assets():
    """
    Finds all Expiring Assets and send a notification on the notify_before date.
    """
    from asset.models import Asset
    from horilla_auth.models import HorillaUser

    today = date.today()
    assets = Asset.objects.all()

    # Cache bot & superuser once
    bot = HorillaUser.objects.filter(username="Horilla Bot").only("id").first()
    superuser = HorillaUser.objects.filter(is_superuser=True).only("id").first()

    # Query only assets that are expiring today
    assets = Asset.objects.filter(
        expiry_date__isnull=False,
        expiry_date__gte=today,
    )

    for asset in assets:
        if asset.expiry_date:
            expiry_date = asset.expiry_date
            notify_date = expiry_date - timedelta(days=asset.notify_before)
            recipient = getattr(asset.owner, "employee_user_id", None) or superuser
            if notify_date == today and recipient:
                notify.send(
                    bot,
                    recipient=recipient,
                    verb=f"The Asset '{asset.asset_name}' expires in {asset.notify_before} days",
                    verb_ar=f"تنتهي صلاحية الأصل '{asset.asset_name}' خلال {asset.notify_before} من الأيام",
                    verb_de=f"Das Asset {asset.asset_name} läuft in {asset.notify_before} Tagen ab.",
                    verb_es=f"El activo {asset.asset_name} caduca en {asset.notify_before} días.",
                    verb_fr=f"L'actif {asset.asset_name} expire dans {asset.notify_before} jours.",
                    redirect=reverse("asset-category-view"),
                    label="System",
                    icon="information",
                )


def mark_expired_assets():
    """
    Finds all assets past their expiry date and sets their status to Not-Available.
    """
    from asset.models import Asset

    today = date.today()
    expired = Asset.objects.filter(
        expiry_date__isnull=False,
        expiry_date__lt=today,
    ).exclude(asset_status="Not-Available")
    for asset in expired:
        asset.asset_status = "Not-Available"
        asset.save()


def notify_expiring_documents():
    """
    Finds all Expiring Documents and send a notification on the notify_before date.
    """
    from horilla_auth.models import HorillaUser
    from horilla_documents.models import Document

    today = date.today()
    documents = Document.objects.all()
    bot = HorillaUser.objects.filter(username="Horilla Bot").first()
    for document in documents:
        if document.expiry_date:
            expiry_date = document.expiry_date
            notify_date = expiry_date - timedelta(days=document.notify_before)

            if notify_date == today:
                notify.send(
                    bot,
                    recipient=document.employee_id.employee_user_id,
                    verb=f"The document ' {document.title} ' expires in {document.notify_before}\
                        days",
                    verb_ar=f"تنتهي صلاحية المستند '{document.title}' خلال {document.notify_before}\
                    يوم",
                    verb_de=f"Das Dokument '{document.title}' läuft in {document.notify_before}\
                        Tagen ab.",
                    verb_es=f"El documento '{document.title}' caduca en {document.notify_before}\
                        días",
                    verb_fr=f"Le document '{document.title}' expire dans {document.notify_before}\
                        jours",
                    redirect=reverse("asset-category-view"),
                    label="System",
                    icon="information",
                )
            if today >= expiry_date:
                document.is_active = False


register_job(notify_expiring_assets, "interval", days=1)
register_job(notify_expiring_documents, "interval", hours=4)
register_job(mark_expired_assets, "interval", days=1)
