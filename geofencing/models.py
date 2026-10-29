from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from geopy.geocoders import Nominatim


class GeoFencing(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()
    radius_in_meters = models.IntegerField()
    company_id = models.OneToOneField(
        "base.Company",
        related_name="geo_fencing",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    start = models.BooleanField(default=False)

    @classmethod
    def for_company(cls, company):
        """
        The fence that applies to ``company``: its own, else the global one (the row with no
        company), else None. A company-specific fence overrides the global one - including a
        company fence that is switched off (``start=False``), which turns the fence off for
        that company even while the global one is on.
        """
        fence = None
        if company is not None:
            fence = cls.objects.filter(company_id=company).first()
        if fence is None:
            fence = cls.objects.filter(company_id__isnull=True).first()
        return fence

    def clean(self):
        if self.company_id is None:
            qs = GeoFencing.objects.filter(company_id__isnull=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _("Only one GeoFencing can have a null company_id.")
                )

        geolocator = Nominatim(
            user_agent="geo_checker_unique"
        )  # Unique user-agent is important
        try:
            location = geolocator.reverse(
                (self.latitude, self.longitude), exactly_one=True
            )
            if not location:
                raise ValidationError(_("Invalid location coordinates."))
        except Exception as e:
            raise ValidationError(f"Geolocation error: {e}")

        return super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()  # Run clean before save
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company_id"],
                name="unique_company_id_when_not_null_geofencing",
                condition=~Q(company_id=None),
            )
        ]
