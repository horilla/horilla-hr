from django.db import migrations


TOURS = [
    # -------------------------------------------------------------------------
    # 1. Settings overview — "Where to start"
    # -------------------------------------------------------------------------
    {
        "slug": "settings-overview",
        "title": "Settings Overview",
        "description": "A guided tour of the Settings area — the first place to visit before adding any employees.",
        "page_match": "settings",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 10,
        "icon": "settings-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Welcome to Settings",
                "description": "Before you can add employees, you need to set up a few building blocks: your company, departments, job positions, job roles, work types, employee types and shifts. This tour walks you through each one.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Recommended setup order",
                "description": "Set things up in this order: 1) Company → 2) Departments → 3) Job Positions → 4) Job Roles → 5) Work Types → 6) Employee Types → 7) Shifts. Each step depends on the one before it.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Company first",
                "description": "Start with your company profile — name, logo, address and contact details. Everything in Krew is scoped to a company, so this must exist before anything else.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Then structure",
                "description": "Once your company exists, add Departments, then Job Positions inside each department, then Job Roles inside each position. These form the organisation chart every employee profile will reference.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Finally, working conditions",
                "description": "Set up Work Types (full-time, part-time, contract), Employee Types (permanent, probation, intern) and Shifts (morning, evening, night). You are now ready to add your first employee.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 2. Company settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-company",
        "title": "Company Setup",
        "description": "How to add and configure your company profile in Krew.",
        "page_match": "company-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 11,
        "icon": "business-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Your Company Profile",
                "description": "This page lists all companies registered in Krew. Every employee, leave policy, payroll run and setting is scoped to a company — so you need at least one before you can do anything else.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Add your company",
                "description": "Click the Create button to add your first company. Fill in the name, logo, address, phone number and currency. The logo appears throughout the system and on payslips.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Multi-company support",
                "description": "Krew supports multiple companies in a single instance. Each company has its own employees, leave balances, payroll and reports — fully isolated from each other.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Switch company",
                "description": "Use the company switcher in the top navigation bar to move between companies at any time. Your view, filters and reports will update to reflect the selected company.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Next step: Departments",
                "description": "Once your company is saved, head to Settings → Departments to create the organisational structure your employees will belong to.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 3. Department settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-department",
        "title": "Department Setup",
        "description": "How to create and manage departments for your organisation.",
        "page_match": "department-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 12,
        "icon": "git-branch-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Departments",
                "description": "Departments are the top-level grouping for your employees — HR, Engineering, Finance, Sales and so on. Every employee profile requires a department.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create a department",
                "description": "Click Create and give the department a name. You can also assign a department manager — they will receive leave approvals and attendance alerts for their team automatically.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Department manager",
                "description": "Assigning a manager to a department means that manager can approve leaves, view attendance and run reports for their department without needing full admin access.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Edit or delete",
                "description": "Click the three-dot menu on any department card to rename it, change the manager, or delete it. Deleting a department that has employees assigned will prompt you to reassign them first.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Next step: Job Positions",
                "description": "With departments in place, go to Settings → Job Positions to define the roles that exist within each department.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 4. Job Position settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-job-position",
        "title": "Job Position Setup",
        "description": "How to create job positions and link them to departments.",
        "page_match": "job-position-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 13,
        "icon": "id-card-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Job Positions",
                "description": "A job position is a named role within a department — for example 'Software Engineer' in Engineering, or 'HR Manager' in Human Resources. Every employee profile must have a job position.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create a job position",
                "description": "Click Create, enter the position name and select which department it belongs to. A single department can have many positions — create as many as you need.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Linked to departments",
                "description": "Job positions always belong to a department. When you add an employee, the job position dropdown will filter automatically based on the department you select, so employees can only be placed in valid positions.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Used in recruitment",
                "description": "Job positions are also used in the Recruitment module — when you open a vacancy, you select the position you are hiring for. The hiring pipeline and candidate tracking are all linked to it.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Next step: Job Roles",
                "description": "Within each position you can define Job Roles — more specific responsibility levels such as Junior, Senior or Lead. Head to Settings → Job Roles to set these up.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 5. Job Role settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-job-role",
        "title": "Job Role Setup",
        "description": "How to create job roles within job positions.",
        "page_match": "job-role-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 14,
        "icon": "ribbon-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Job Roles",
                "description": "Job roles are the specialisations or seniority levels within a job position. For example, the 'Software Engineer' position might have roles: Junior Engineer, Senior Engineer and Tech Lead.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create a job role",
                "description": "Click Create, give the role a name and select which job position it belongs to. Job roles are optional — if your organisation does not use seniority levels, you can skip this step.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "How roles are used",
                "description": "When adding or editing an employee, after selecting their job position you can optionally specify their job role. Roles appear in reports and can be used to filter the employee directory.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Next step: Work Types",
                "description": "Once your org structure is set up (Company → Departments → Job Positions → Job Roles), configure how your employees work. Head to Settings → Work Types next.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 6. Work Type settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-work-type",
        "title": "Work Type Setup",
        "description": "How to configure work types — full-time, part-time, contract and so on.",
        "page_match": "work-type-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 15,
        "icon": "time-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Work Types",
                "description": "Work types define how an employee is engaged — Full Time, Part Time, Contract, Freelance, and so on. Every employee must have a work type assigned.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create a work type",
                "description": "Click Create and give the work type a name. Krew comes with common defaults — add any custom types your company uses.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Rotating work types",
                "description": "If employees rotate between work arrangements (for example, alternating between on-site and remote weeks), use the Rotating Work Type feature to automate the schedule.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Next step: Employee Types",
                "description": "Work type describes the contract arrangement. Employee type describes the employment status (Permanent, Probation, Intern, etc.). Head to Settings → Employee Types next.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 7. Employee Type settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-employee-type",
        "title": "Employee Type Setup",
        "description": "How to configure employee types — permanent, probation, intern and so on.",
        "page_match": "employee-type-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 16,
        "icon": "person-circle-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Employee Types",
                "description": "Employee types describe an employee's employment status — Permanent, Probation, Intern, Contractor, and so on. Every employee must have an employee type assigned.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create an employee type",
                "description": "Click Create and give the type a name. You can create as many types as your HR policy requires — for example, 'Permanent', '3-Month Probation', '6-Month Probation', 'Intern'.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "How employee types are used",
                "description": "Employee type appears on the employee profile and can be used to filter the directory, generate reports and apply different leave policies. For example, probationary employees may not be eligible for certain leave types.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Next step: Shifts",
                "description": "The last piece before adding employees is defining work shifts. Head to Settings → Shifts to create morning, afternoon, night or any custom shift schedule.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 8. Employee Shift settings
    # -------------------------------------------------------------------------
    {
        "slug": "settings-employee-shift",
        "title": "Shift Setup",
        "description": "How to create work shifts and assign them to employees.",
        "page_match": "employee-shift-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 17,
        "icon": "moon-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Work Shifts",
                "description": "Shifts define when your employees work — for example, Morning (9 AM–5 PM), Evening (2 PM–10 PM) or Night (10 PM–6 AM). Every employee profile requires a shift.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Create a shift",
                "description": "Click Create, give the shift a name and set the start and end times. You can also define grace periods for late arrivals and configure minimum working hours for attendance validation.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Shift schedule",
                "description": "Each shift can have different timings per day of the week — useful for organisations where Friday is a half-day, or weekends have different hours.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Rotating shifts",
                "description": "If employees rotate through different shifts (morning one week, evening the next), use the Rotating Shift feature to define the rotation schedule — Krew will automatically assign the correct shift each period.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "You're ready to add employees",
                "description": "With Company, Departments, Job Positions, Job Roles, Work Types, Employee Types and Shifts all set up — you now have everything you need. Head to the Employee module and add your first employee.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
]

SLUGS = [t["slug"] for t in TOURS]


def seed(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    TourStep = apps.get_model("horilla_tour", "TourStep")

    for tour_data in TOURS:
        steps_data = tour_data.pop("steps")
        tour, _ = Tour.objects.get_or_create(
            slug=tour_data["slug"],
            defaults=tour_data,
        )
        for step_data in steps_data:
            TourStep.objects.get_or_create(
                tour=tour,
                sequence=step_data["sequence"],
                defaults=step_data,
            )
        tour_data["steps"] = steps_data


def unseed(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    Tour.objects.filter(slug__in=SLUGS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("horilla_tour", "0005_fix_sidebar_step_selectors"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
