"""
Seed global (company-agnostic) default tours.

These ship enabled out of the box so a brand-new tenant gets guided onboarding
immediately — directly addressing the "empty system, no guidance" churn problem.
Tours are global (company_id=None) and therefore visible to every company;
admins can edit, unpublish or clone them from Settings → Product Tours.
"""

from django.db import migrations

GETTING_STARTED = {
    "slug": "getting-started",
    "title": "Getting Started",
    "description": "A 3-minute setup walkthrough for new admins.",
    "page_match": "dashboard",
    "match_type": "url_name",
    "audience": "admins",
    "trigger": "auto_once",
    "priority": 100,
    "icon": "rocket-outline",
    "steps": [
        {
            "title": "Welcome to Krew 👋",
            "description": "Let's get your HR system ready in a few quick steps. "
            "This takes about three minutes — you can skip and resume anytime.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "Step 1 — Add your company details",
            "description": "Open Settings → Companies to set your company name, "
            "logo, address and timezone. This personalises the whole workspace.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "Step 2 — Create departments & job positions",
            "description": "Under Settings → Base, add your Departments and Job "
            "Positions so employees can be placed correctly and reports make sense.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "Step 3 — Configure email (important)",
            "description": "Open Settings → Mail Server Configuration. Without it, "
            "password resets, employee invites and notifications cannot be delivered.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "Step 4 — Add your team",
            "description": "Go to Employees to add people one by one or import them in "
            "bulk. Each employee gets their own login and self-service portal.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "You're all set!",
            "description": "Click this help button any time to replay a tour or start "
            "another one.",
            "element_selector": "#tourLauncherBtn",
            "side": "bottom",
        },
    ],
}

DASHBOARD_OVERVIEW = {
    "slug": "dashboard-overview",
    "title": "Dashboard Overview",
    "description": "A quick look at your Krew home dashboard.",
    "page_match": "dashboard",
    "match_type": "url_name",
    "audience": "all",
    "trigger": "auto_once",
    "priority": 10,
    "icon": "speedometer-outline",
    "steps": [
        {
            "title": "Your dashboard",
            "description": "This is your home base. KPIs, charts and quick actions "
            "update automatically as your team uses Krew.",
            "element_selector": "",
            "side": "over",
        },
        {
            "title": "Take a tour anytime",
            "description": "Open guided tours from this help button whenever you need "
            "a refresher on a feature.",
            "element_selector": "#tourLauncherBtn",
            "side": "bottom",
        },
    ],
}

SEED_TOURS = [GETTING_STARTED, DASHBOARD_OVERVIEW]


def seed(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    TourStep = apps.get_model("horilla_tour", "TourStep")
    for data in SEED_TOURS:
        steps = data["steps"]
        tour, created = Tour.objects.get_or_create(
            slug=data["slug"],
            company_id=None,
            defaults={
                "title": data["title"],
                "description": data["description"],
                "page_match": data["page_match"],
                "match_type": data["match_type"],
                "audience": data["audience"],
                "trigger": data["trigger"],
                "priority": data["priority"],
                "icon": data["icon"],
                "is_published": True,
            },
        )
        if not created:
            continue
        for i, step in enumerate(steps, start=1):
            TourStep.objects.create(
                tour=tour,
                sequence=i,
                title=step["title"],
                description=step["description"],
                element_selector=step["element_selector"],
                side=step["side"],
                align="start",
            )


def unseed(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    Tour.objects.filter(
        slug__in=[d["slug"] for d in SEED_TOURS], company_id=None
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("horilla_tour", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
