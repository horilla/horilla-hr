"""
Models for the horilla_theme app
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# Create your horilla_theme models here.
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from base.models import Company
from horilla.models import HorillaModel

THEMES_DATA = [
    {
        "name": "Coral Red Theme (Default)",
        "description": "Warm coral-red based theme",
        "is_default": True,
        "primary_50": "#f6f6f6",
        "primary_100": "#FFF5F1",  # f0f0f0
        "primary_200": "#FEF6F5",
        "primary_300": "#FCEDEB",
        "primary_400": "#FBE5E1",
        "primary_500": "#F7C8C1",
        "primary_600": "#E54F38",
        "primary_700": "#ce4732",
        "primary_800": "#AC3B2A",
        "primary_900": "#672419",
        "dark_50": "#E6E6E6",
        "dark_100": "#A8A8A8",
        "dark_200": "#515151",
        "dark_300": "#501C14",
        "dark_400": "#64748B",
        "dark_500": "#190906",
        "dark_600": "#000000",
        "secondary_50": "#f8fafc",
        "secondary_100": "#f1f5f9",
        "secondary_200": "#e2e8f0",
        "secondary_300": "#cbd5e1",
        "secondary_400": "#FBE5E1",
        "secondary_500": "#F7C8C1",
        "secondary_600": "#E54F38",
        "secondary_700": "#334155",
        "secondary_800": "#1e293b",
        "secondary_900": "#0f172a",
    },
    {
        "name": "Ocean Blue Theme",
        "description": "Professional and trustworthy feel with ocean-inspired blues",
        "primary_50": "#eff6ff",
        "primary_100": "#eff6ff",
        "primary_200": "#dbeafe",
        "primary_300": "#bfdbfe",
        "primary_400": "#93c5fd",
        "primary_500": "#60a5fa",
        "primary_600": "#3b82f6",
        "primary_700": "#0c4a6e",
        "primary_800": "#1e3a8a",
        "primary_900": "#1e40af",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#1e3a5f",
        "dark_500": "#64748B",
        "dark_600": "#0a1929",
        "secondary_50": "#ecfeff",
        "secondary_100": "#ecfeff",
        "secondary_200": "#cffafe",
        "secondary_300": "#a5f3fc",
        "secondary_400": "#93c5fd",
        "secondary_500": "#60a5fa",
        "secondary_600": "#3b82f6",
        "secondary_700": "#0891b2",
        "secondary_800": "#0e7490",
        "secondary_900": "#155e75",
    },
    {
        "name": "Forest Green Theme",
        "description": "Calm and growth-oriented with natural green tones",
        "primary_50": "#f0fdf4",
        "primary_100": "#f0fdf4",
        "primary_200": "#dcfce7",
        "primary_300": "#bbf7d0",
        "primary_400": "#86efac",
        "primary_500": "#4ade80",
        "primary_600": "#22c55e",
        "primary_700": "#16a34a",
        "primary_800": "#15803d",
        "primary_900": "#166534",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#1e4620",
        "dark_500": "#64748B",
        "dark_600": "#0a2f0c",
        "secondary_50": "#f7fee7",
        "secondary_100": "#f7fee7",
        "secondary_200": "#ecfccb",
        "secondary_300": "#d9f99d",
        "secondary_400": "#86efac",
        "secondary_500": "#4ade80",
        "secondary_600": "#22c55e",
        "secondary_700": "#65a30d",
        "secondary_800": "#4d7c0f",
        "secondary_900": "#3f6212",
    },
    {
        "name": "Purple Professional Theme",
        "description": "Creative and distinctive with vibrant purple accents",
        "primary_50": "#faf5ff",
        "primary_100": "#faf5ff",
        "primary_200": "#f3e8ff",
        "primary_300": "#e9d5ff",
        "primary_400": "#d8b4fe",
        "primary_500": "#c084fc",
        "primary_600": "#a855f7",
        "primary_700": "#9333ea",
        "primary_800": "#670ab8",
        "primary_900": "#450e71",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#3d1a5c",
        "dark_500": "#64748B",
        "dark_600": "#1e0a33",
        "secondary_50": "#fdf4ff",
        "secondary_100": "#fdf4ff",
        "secondary_200": "#fae8ff",
        "secondary_300": "#f5d0fe",
        "secondary_400": "#d8b4fe",
        "secondary_500": "#c084fc",
        "secondary_600": "#a855f7",
        "secondary_700": "#c026d3",
        "secondary_800": "#a21caf",
        "secondary_900": "#86198f",
    },
    {
        "name": "Slate Gray Theme",
        "description": "Minimalist and sophisticated with neutral tones",
        "primary_50": "#f8fafc",
        "primary_100": "#f8fafc",
        "primary_200": "#f1f5f9",
        "primary_300": "#e2e8f0",
        "primary_400": "#cbd5e1",
        "primary_500": "#94a3b8",
        "primary_600": "#64748b",
        "primary_700": "#475569",
        "primary_800": "#334155",
        "primary_900": "#1e293b",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#2d3748",
        "dark_500": "#64748B",
        "dark_600": "#0f172a",
        "secondary_50": "#fff7ed",
        "secondary_100": "#fff7ed",
        "secondary_200": "#ffedd5",
        "secondary_300": "#fed7aa",
        "secondary_400": "#cbd5e1",
        "secondary_500": "#94a3b8",
        "secondary_600": "#64748b",
        "secondary_700": "#ea580c",
        "secondary_800": "#c2410c",
        "secondary_900": "#9a3412",
    },
    {
        "name": "Indigo Night Theme",
        "description": "Deep and sophisticated with indigo blues",
        "primary_50": "#eef2ff",
        "primary_100": "#eef2ff",
        "primary_200": "#e0e7ff",
        "primary_300": "#c7d2fe",
        "primary_400": "#a5b4fc",
        "primary_500": "#818cf8",
        "primary_600": "#6366f1",
        "primary_700": "#4f46e5",
        "primary_800": "#4338ca",
        "primary_900": "#3730a3",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#1e1b4b",
        "dark_500": "#64748B",
        "dark_600": "#0f0d2e",
        "secondary_50": "#faf5ff",
        "secondary_100": "#faf5ff",
        "secondary_200": "#f3e8ff",
        "secondary_300": "#e9d5ff",
        "secondary_400": "#a5b4fc",
        "secondary_500": "#818cf8",
        "secondary_600": "#6366f1",
        "secondary_700": "#9333ea",
        "secondary_800": "#7e22ce",
        "secondary_900": "#6b21a8",
    },
    {
        "name": "Sunset Orange Theme",
        "description": "Energetic and warm with sunset-inspired oranges",
        "primary_50": "#fff7ed",
        "primary_100": "#fff7ed",
        "primary_200": "#ffedd5",
        "primary_300": "#fed7aa",
        "primary_400": "#fdba74",
        "primary_500": "#fb923c",
        "primary_600": "#f97316",
        "primary_700": "#ea580c",
        "primary_800": "#c2410c",
        "primary_900": "#9a3412",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#4a1c08",
        "dark_500": "#64748B",
        "dark_600": "#1a0a04",
        "secondary_50": "#fefce8",
        "secondary_100": "#fefce8",
        "secondary_200": "#fef9c3",
        "secondary_300": "#fef08a",
        "secondary_400": "#fdba74",
        "secondary_500": "#fb923c",
        "secondary_600": "#f97316",
        "secondary_700": "#ca8a04",
        "secondary_800": "#a16207",
        "secondary_900": "#854d0e",
    },
    {
        "name": "Crimson Wine Theme",
        "description": "Bold and sophisticated with deep crimson tones",
        "primary_50": "#fef2f2",
        "primary_100": "#fde8e8",
        "primary_200": "#fbd5d5",
        "primary_300": "#f8b4b4",
        "primary_400": "#f38787",
        "primary_500": "#e63946",
        "primary_600": "#c92a2a",
        "primary_700": "#a61e1e",
        "primary_800": "#7d1515",
        "primary_900": "#5c0f0f",
        "dark_50": "#E6E6E6",
        "dark_100": "#d4d4d4",
        "dark_200": "#737373",
        "dark_300": "#404040",
        "dark_400": "#262626",
        "dark_500": "#171717",
        "dark_600": "#0a0a0a",
        "secondary_50": "#fdf4ff",
        "secondary_100": "#fae8ff",
        "secondary_200": "#f5d0fe",
        "secondary_300": "#f0abfc",
        "secondary_400": "#e879f9",
        "secondary_500": "#d946ef",
        "secondary_600": "#c026d3",
        "secondary_700": "#a21caf",
        "secondary_800": "#86198f",
        "secondary_900": "#701a75",
    },
    {
        "name": "Teal Corporate Theme",
        "description": "Fresh and modern with teal and cyan accents",
        "primary_50": "#f0fdfa",
        "primary_100": "#f0fdfa",
        "primary_200": "#ccfbf1",
        "primary_300": "#99f6e4",
        "primary_400": "#5eead4",
        "primary_500": "#2dd4bf",
        "primary_600": "#14b8a6",
        "primary_700": "#0d9488",
        "primary_800": "#0f766e",
        "primary_900": "#115e59",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#134e4a",
        "dark_500": "#64748B",
        "dark_600": "#042f2e",
        "secondary_50": "#ecfeff",
        "secondary_100": "#ecfeff",
        "secondary_200": "#cffafe",
        "secondary_300": "#a5f3fc",
        "secondary_400": "#5eead4",
        "secondary_500": "#2dd4bf",
        "secondary_600": "#14b8a6",
        "secondary_700": "#0891b2",
        "secondary_800": "#0e7490",
        "secondary_900": "#155e75",
    },
    {
        "name": "Amber Glow Theme",
        "description": "Warm and inviting with golden amber tones",
        "primary_50": "#fffbeb",
        "primary_100": "#fffbeb",
        "primary_200": "#fef3c7",
        "primary_300": "#fde68a",
        "primary_400": "#fcd34d",
        "primary_500": "#fbbf24",
        "primary_600": "#f59e0b",
        "primary_700": "#d97706",
        "primary_800": "#b45309",
        "primary_900": "#92400e",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#451a03",
        "dark_500": "#64748B",
        "dark_600": "#1c0a00",
        "secondary_50": "#fef2f2",
        "secondary_100": "#fef2f2",
        "secondary_200": "#fecaca",
        "secondary_300": "#fca5a5",
        "secondary_400": "#fcd34d",
        "secondary_500": "#fbbf24",
        "secondary_600": "#f59e0b",
        "secondary_700": "#b91c1c",
        "secondary_800": "#991b1b",
        "secondary_900": "#7f1d1d",
    },
    {
        "name": "Navy Steel Theme",
        "description": "Professional and strong with navy and steel blues",
        "primary_50": "#f0f9ff",
        "primary_100": "#f0f9ff",
        "primary_200": "#e0f2fe",
        "primary_300": "#bae6fd",
        "primary_400": "#7dd3fc",
        "primary_500": "#38bdf8",
        "primary_600": "#0ea5e9",
        "primary_700": "#0284c7",
        "primary_800": "#0369a1",
        "primary_900": "#075985",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#1e3a5f",
        "dark_500": "#64748B",
        "dark_600": "#0c1821",
        "secondary_50": "#f8fafc",
        "secondary_100": "#f8fafc",
        "secondary_200": "#f1f5f9",
        "secondary_300": "#e2e8f0",
        "secondary_400": "#7dd3fc",
        "secondary_500": "#38bdf8",
        "secondary_600": "#0ea5e9",
        "secondary_700": "#475569",
        "secondary_800": "#334155",
        "secondary_900": "#1e293b",
    },
    {
        "name": "Rose Gold Theme",
        "description": "Elegant and luxurious with rose gold accents",
        "primary_50": "#fdf2f8",
        "primary_100": "#fdf2f8",
        "primary_200": "#fce7f3",
        "primary_300": "#fbcfe8",
        "primary_400": "#f9a8d4",
        "primary_500": "#f472b6",
        "primary_600": "#ec4899",
        "primary_700": "#db2777",
        "primary_800": "#be185d",
        "primary_900": "#9f1239",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#500724",
        "dark_500": "#64748B",
        "dark_600": "#1f0410",
        "secondary_50": "#fff1f2",
        "secondary_100": "#fff1f2",
        "secondary_200": "#ffe4e6",
        "secondary_300": "#fecdd3",
        "secondary_400": "#f9a8d4",
        "secondary_500": "#f472b6",
        "secondary_600": "#ec4899",
        "secondary_700": "#e11d48",
        "secondary_800": "#be123c",
        "secondary_900": "#9f1239",
    },
    {
        "name": "Emerald Mint Theme",
        "description": "Fresh and vibrant with emerald and mint greens",
        "primary_50": "#ecfdf5",
        "primary_100": "#ecfdf5",
        "primary_200": "#d1fae5",
        "primary_300": "#a7f3d0",
        "primary_400": "#6ee7b7",
        "primary_500": "#34d399",
        "primary_600": "#10b981",
        "primary_700": "#059669",
        "primary_800": "#047857",
        "primary_900": "#065f46",
        "dark_50": "#E6E6E6",
        "dark_100": "#E6E6E6",
        "dark_200": "#515151",
        "dark_300": "#515151",
        "dark_400": "#064e3b",
        "dark_500": "#64748B",
        "dark_600": "#022c22",
        "secondary_50": "#f0fdf4",
        "secondary_100": "#f0fdf4",
        "secondary_200": "#dcfce7",
        "secondary_300": "#bbf7d0",
        "secondary_400": "#6ee7b7",
        "secondary_500": "#34d399",
        "secondary_600": "#10b981",
        "secondary_700": "#16a34a",
        "secondary_800": "#15803d",
        "secondary_900": "#166534",
    },
]


class HorillaColorTheme(HorillaModel):
    """
    Model to store predefined color themes for Horilla
    """

    name = models.CharField(max_length=100, unique=True, verbose_name=_("Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))

    # Primary Colors
    primary_50 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_100 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_200 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_300 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_400 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_500 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_600 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_700 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_800 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    primary_900 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )

    # Dark Colors
    dark_50 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_100 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_200 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_300 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_400 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_500 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    dark_600 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )

    # Secondary Colors
    secondary_50 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_100 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_200 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_300 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_400 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_500 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_600 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_700 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_800 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )
    secondary_900 = models.CharField(
        max_length=7, validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")]
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name=_("Is Default"),
        help_text=_(
            "Set as default theme for login page. Only one theme can be default across all companies."
        ),
    )

    class Meta:
        """
        Meta option for HorillaColorTheme model
        """

        ordering = ["name"]
        verbose_name = _("Color Theme")
        verbose_name_plural = _("Color Themes")

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        """
        Override save to ensure only one default theme exists.
        Uses a transaction to ensure atomicity.
        """
        with transaction.atomic():
            if self.is_default:
                query = HorillaColorTheme.objects.filter(is_default=True)
                if self.pk:
                    query = query.exclude(pk=self.pk)
                query.update(is_default=False)
            super().save(*args, **kwargs)
            if self.is_default and self.pk:
                HorillaColorTheme.objects.filter(is_default=True).exclude(
                    pk=self.pk
                ).update(is_default=False)

    @classmethod
    def ensure_single_default(cls):
        """
        Ensure only one default theme exists. Fixes any duplicate defaults.
        Keeps the most recently updated one as default.
        """
        defaults = cls.objects.filter(is_default=True).order_by("-id")
        if defaults.count() > 1:
            keep_default = defaults.first()
            defaults.exclude(pk=keep_default.pk).update(is_default=False)
            return keep_default
        return defaults.first()

    @classmethod
    def get_default_theme(cls):
        """
        Get the default theme for login page
        Returns the theme object or None
        """
        cls.ensure_single_default()

        default_theme = cls.objects.filter(is_default=True).first()
        if default_theme:
            return default_theme
        return cls.objects.filter(name="Coral Red Theme (Default)").first()


class CompanyTheme(HorillaModel):
    """
    Model to store company-wide theme settings
    """

    theme = models.ForeignKey(
        HorillaColorTheme,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organizations",
        verbose_name=_("Theme"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Company"),
        # related_name="theme"
    )

    class Meta:
        """
        Meta option for CompanyTheme model
        """

        verbose_name = _("Company Theme")
        verbose_name_plural = _("Company Themes")

    def __str__(self):
        return f"{self.theme} - {self.company}"

    @classmethod
    def get_default_theme(cls):
        """
        Get the default theme for login page
        Returns the theme object or None
        """
        return HorillaColorTheme.get_default_theme()

    @classmethod
    def get_theme_for_company(cls, company):
        """
        Get the theme for a specific company
        Returns the theme object or default theme
        """
        if not company:
            return cls.get_default_theme()

        company_theme = (
            cls.objects.filter(company=company).select_related("theme").first()
        )
        if company_theme and company_theme.theme:
            return company_theme.theme

        # return HorillaColorTheme.objects.filter(
        #     name="Coral Red Theme (Default)"
        # ).first()
        return HorillaColorTheme.objects.filter(is_default=True).first()
