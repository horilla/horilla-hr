"""
Replace the floating-only settings tours (0006) with interactive ones that
anchor driver.js popovers to real page elements:
  - #company / #department / #jobPosition / #jobRole / #workType /
    #employeeType / #employeeShift  — sidebar links in settings.html
  - .oh-btn--secondary           — the Create button in the nav bar
  - #listContainer               — the list table area
  - .oh-inner-sidebar            — the settings left-nav panel
  - .oh-main__titlebar-title     — the page title
"""
from django.db import migrations


# Each entry: (slug, [(seq, title, description, element_selector, side, align), ...])
STEPS = {
    # ------------------------------------------------------------------
    # 1. Settings overview — highlight the sidebar items in setup order
    # ------------------------------------------------------------------
    "settings-overview": [
        (
            1,
            "Welcome to Settings",
            "Before adding employees you need a few building blocks. This tour highlights each one in the recommended setup order.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Settings navigation",
            "This left panel is your settings menu. All the configuration pages are listed here — we will walk through the ones you need first.",
            ".oh-inner-sidebar",
            "right",
            "start",
        ),
        (
            3,
            "Step 1 — Company",
            "Start with your Company. Click this link to create your company profile: name, logo, address and currency.",
            "#company",
            "right",
            "start",
        ),
        (
            4,
            "Step 2 — Departments",
            "Then Departments. Every employee belongs to a department, so create these before adding any staff.",
            "#department",
            "right",
            "start",
        ),
        (
            5,
            "Step 3 — Job Positions",
            "Job Positions are named roles inside a department (e.g. Software Engineer in Engineering). Create these next.",
            "#jobPosition",
            "right",
            "start",
        ),
        (
            6,
            "Step 4 — Job Roles",
            "Job Roles are seniority levels within a position (e.g. Junior, Senior, Lead). Optional, but useful for reports.",
            "#jobRole",
            "right",
            "start",
        ),
        (
            7,
            "Step 5 — Work Types",
            "Work Types define the contract arrangement: Full Time, Part Time, Contract, Freelance, etc.",
            "#workType",
            "right",
            "start",
        ),
        (
            8,
            "Step 6 — Employee Types",
            "Employee Types define the employment status: Permanent, Probation, Intern, etc.",
            "#employeeType",
            "right",
            "start",
        ),
        (
            9,
            "Step 7 — Shifts",
            "Finally, Shifts set the working hours: Morning, Evening, Night, or any custom schedule. Once this is done you are ready to add your first employee.",
            "#employeeShift",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 2. Company — company-view
    # ------------------------------------------------------------------
    "settings-company": [
        (
            1,
            "Company Settings",
            "This is the Company page. Everything in Krew — employees, leave, payroll — is scoped to a company, so you must create one first.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create your company",
            "Click this Create button to add your company. Fill in the name, logo, address and currency.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Company list",
            "Once saved, your company appears here. You can edit its details or add more companies at any time.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Next — Departments",
            "Company is done. Now click Department in the left menu to create the departments your employees will belong to.",
            "#department",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 3. Department — department-view
    # ------------------------------------------------------------------
    "settings-department": [
        (
            1,
            "Departments",
            "Departments are the top-level groups in your organisation: HR, Engineering, Finance, Sales, etc. Every employee must belong to one.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create a department",
            "Click Create, enter a name (e.g. 'Engineering') and optionally assign a manager. The manager can then approve leaves and view attendance for their team.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Your departments",
            "Departments you create appear in this list. Click the row to edit or delete one.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Next — Job Positions",
            "Departments are set up. Now click Job Positions in the left menu to define the roles that exist within each department.",
            "#jobPosition",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 4. Job Position — job-position-view
    # ------------------------------------------------------------------
    "settings-job-position": [
        (
            1,
            "Job Positions",
            "A Job Position is a named role within a department — for example 'Software Engineer' in Engineering or 'HR Manager' in HR. Every employee profile requires one.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create a job position",
            "Click Create. Select the department this position belongs to, then give it a name. Repeat for every role in your organisation.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Positions list",
            "All job positions appear here. When adding an employee, the position dropdown will automatically filter to only show positions in the selected department.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Next — Job Roles",
            "Job Positions done. Click Job Role in the left menu to add seniority levels (Junior, Senior, Lead) within each position.",
            "#jobRole",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 5. Job Role — job-role-view
    # ------------------------------------------------------------------
    "settings-job-role": [
        (
            1,
            "Job Roles",
            "Job Roles are the specialisation or seniority level within a position. Example: the 'Software Engineer' position could have roles Junior Engineer, Senior Engineer and Tech Lead.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create a job role",
            "Click Create. Select the job position this role belongs to, then name the role. This step is optional — skip it if your organisation does not use seniority levels.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Roles list",
            "Job Roles appear here. They show on employee profiles and can be used to filter reports.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Next — Work Types",
            "Organisation structure is complete. Now click Work Type in the left menu to define how employees are engaged (Full Time, Part Time, Contract, etc.).",
            "#workType",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 6. Work Type — work-type-view
    # ------------------------------------------------------------------
    "settings-work-type": [
        (
            1,
            "Work Types",
            "Work Types define how an employee is engaged: Full Time, Part Time, Contract, Freelance, and so on. Every employee profile must have one.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create a work type",
            "Click Create and give it a name. Add one for each arrangement your company uses (e.g. Full Time, Part Time, Contract).",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Work types list",
            "All work types appear here. You can edit or delete them at any time.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Next — Employee Types",
            "Work Types are done. Click Employee Type in the left menu to define employment status categories (Permanent, Probation, Intern, etc.).",
            "#employeeType",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 7. Employee Type — employee-type-view
    # ------------------------------------------------------------------
    "settings-employee-type": [
        (
            1,
            "Employee Types",
            "Employee Types describe an employee's employment status: Permanent, Probation, Intern, Contractor, and so on. Every employee profile must have one.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create an employee type",
            "Click Create and give it a name. Create one for each status your HR policy uses — for example: Permanent, 3-Month Probation, 6-Month Probation, Intern.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Employee types list",
            "All employee types appear here. They can also be used to apply different leave policies — probationary employees, for instance, may not be eligible for certain leave types.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "Last step — Shifts",
            "Almost there! Click Employee Shift in the left menu to set up the working schedules your employees follow.",
            "#employeeShift",
            "right",
            "start",
        ),
    ],
    # ------------------------------------------------------------------
    # 8. Employee Shift — employee-shift-view
    # ------------------------------------------------------------------
    "settings-employee-shift": [
        (
            1,
            "Work Shifts",
            "Shifts define when your employees work — for example, Morning (9 AM–5 PM), Evening (2 PM–10 PM) or Night (10 PM–6 AM). Every employee must be assigned a shift.",
            "",
            "over",
            "start",
        ),
        (
            2,
            "Create a shift",
            "Click Create. Give it a name, set the start time and end time, and configure grace periods for late arrivals. Repeat for every schedule in your organisation.",
            ".oh-btn--secondary",
            "bottom",
            "start",
        ),
        (
            3,
            "Shifts list",
            "Shifts appear here. Each shift can also have a per-day schedule, so Friday half-days or different weekend hours are fully supported.",
            "#listContainer",
            "top",
            "start",
        ),
        (
            4,
            "You are ready!",
            "Company ✓  Departments ✓  Job Positions ✓  Job Roles ✓  Work Types ✓  Employee Types ✓  Shifts ✓ — head to the Employee module now to add your first employee.",
            "",
            "over",
            "start",
        ),
    ],
}

SLUGS = list(STEPS.keys())


def update(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    TourStep = apps.get_model("horilla_tour", "TourStep")

    for slug, steps_data in STEPS.items():
        try:
            tour = Tour.objects.get(slug=slug)
        except Tour.DoesNotExist:
            continue

        # Replace all existing steps with the interactive ones
        TourStep.objects.filter(tour=tour).delete()

        for seq, title, description, element_selector, side, align in steps_data:
            TourStep.objects.create(
                tour=tour,
                sequence=seq,
                title=title,
                description=description,
                element_selector=element_selector,
                side=side,
                align=align,
            )


def revert(apps, schema_editor):
    """Revert to floating-only steps by clearing element selectors."""
    TourStep = apps.get_model("horilla_tour", "TourStep")
    Tour = apps.get_model("horilla_tour", "Tour")
    for slug in SLUGS:
        try:
            tour = Tour.objects.get(slug=slug)
            TourStep.objects.filter(tour=tour).update(
                element_selector="", side="over"
            )
        except Tour.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("horilla_tour", "0006_seed_settings_tours"),
    ]

    operations = [
        migrations.RunPython(update, revert),
    ]
