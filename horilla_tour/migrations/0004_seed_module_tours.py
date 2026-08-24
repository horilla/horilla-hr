from django.db import migrations


TOURS = [
    # -------------------------------------------------------------------------
    # 1. Employee Directory
    # -------------------------------------------------------------------------
    {
        "slug": "employee-directory",
        "title": "Employee Directory",
        "description": "A guided tour of the Employee directory — adding, searching and managing staff.",
        "page_match": "employee-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "people-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Your Employee Directory",
                "description": "This is where every person in your organisation lives. Add, filter, search and manage all your staff from one place.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Employee List",
                "description": "Each row or card shows an employee with their name, job position, department, work type and manager. Click any entry to open their full profile — personal info, documents, attendance, payslips and more.",
                "element_selector": "#listContainer",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Create Employee",
                "description": "Click Create to add a new employee. Fill in personal details, assign a job position, department, manager and work type. Once saved the employee appears in the directory immediately.",
                "element_selector": "a.bg-primary-600",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Actions",
                "description": "Click Actions to access bulk operations — Import employees from Excel or CSV, Export the current list, Archive or Un-archive employees, send Bulk Mail, perform Bulk Updates, or Delete selected records.",
                "element_selector": "button.border-primary-500",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "List & Card Views",
                "description": "Toggle between List view — a table of employees — and Card view — a grid of profile cards — using the view buttons. Both views support search and filter.",
                "element_selector": ".nav-view-btn",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 6,
                "title": "Toggle Columns",
                "description": "Click the column settings button at the top-right of the table to show or hide columns — Department, Job Position, Manager, Work Type and more — to focus on the data you need.",
                "element_selector": "button.oh-sticky-dropdown_btn",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 7,
                "title": "Search",
                "description": "Type in the search box to filter employees by name. The list updates as you type — useful when your directory is large and you need to locate someone quickly.",
                "element_selector": "input[name='search']",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 8,
                "title": "Filter",
                "description": "Click Filter to narrow the directory by department, job position, work type, manager, company or employment status. Use Group By to organise employees by department or reporting manager.",
                "element_selector": "#filterForm .dropdown-wrapper",
                "side": "bottom",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 2. ESS — My Dashboard
    # -------------------------------------------------------------------------
    {
        "slug": "ess-dashboard-tour",
        "title": "My Dashboard",
        "description": "A guided tour of the employee self-service dashboard.",
        "page_match": "ess-dashboard",
        "match_type": "url_name",
        "audience": "employees",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "person-circle-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Your personal dashboard",
                "description": "This is your HR self-service hub. View your attendance, leave balance, payslips and requests — all in one place.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Key metrics",
                "description": "Your attendance rate, leave balance and open requests are summarised here at a glance.",
                "element_selector": "#essKpiGrid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Leave balance",
                "description": "See your approved and remaining days for each leave type. Click the chart to apply for leave.",
                "element_selector": "#essLeaveBalanceChart",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Attendance calendar",
                "description": "Your attendance is plotted day by day. Green means present, amber means late, red means absent.",
                "element_selector": "#essAttendanceCalendar",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "My requests",
                "description": "Check the status of your leave applications, attendance corrections and other requests right here.",
                "element_selector": "#essLeaveRequestsList",
                "side": "top",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 3. Recruitment Pipeline
    # -------------------------------------------------------------------------
    {
        "slug": "recruitment-pipeline",
        "title": "Recruitment Pipeline",
        "description": "A guided tour of the recruitment pipeline — stages, candidates and hiring flow.",
        "page_match": "cbv-pipeline",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "git-merge-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "The Recruitment Pipeline",
                "description": "The Pipeline page is your central hiring workspace. Each active job opening is a tab, and within each tab the candidates move through stages — Applied, Shortlisted, Interview, Offer, Hired — represented as columns.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Pipeline Board",
                "description": "The pipeline board area displays all active recruitments as tabs. Switch between Card view (kanban) and List view using the toggle buttons in the top-right to change how stage columns are presented.",
                "element_selector": "#pipelineContainer",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Recruitment Tabs",
                "description": "Each tab represents one active job opening. Click a tab to focus on that recruitment's pipeline — its stage columns and candidate cards load below. The badge on each tab shows how many stages it contains.",
                "element_selector": ".oh-tabs__tab",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Recruitment Actions",
                "description": "Click the ellipsis (⋮) on any recruitment tab to access its actions — Add Stage, Edit the recruitment details, Resume Shortlisting to bulk-upload CVs, Manage Stage Order, or Close the recruitment.",
                "element_selector": ".oh-tabs__tab .oh-accordion-meta__btn",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Stage Column",
                "description": "Each column header shows the stage name. In list view, click the header to collapse or expand that stage. In card view, drag the header to reorder stages. Click the ellipsis on the header to add candidates, edit or delete the stage.",
                "element_selector": ".oh-tabs__movable-header",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 6,
                "title": "Create Recruitment",
                "description": "Click Create to open a new recruitment. Set the job position, hiring managers, vacancy count and pipeline stages. Once published, a public job listing page is generated automatically for applicants to apply.",
                "element_selector": "a.bg-primary-600",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 7,
                "title": "Search",
                "description": "Type in the search box to filter candidates across all stages by name. The pipeline updates as you type — useful when you have a large number of applicants and need to locate someone quickly.",
                "element_selector": "input[name='search']",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 8,
                "title": "Filter",
                "description": "Click Filter to narrow the pipeline by stage, candidate status, interview schedule, job position or recruitment manager. Combine filters to focus on exactly the subset of candidates you need to review.",
                "element_selector": "#filterForm .dropdown-wrapper",
                "side": "bottom",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 4. Leave Management
    # -------------------------------------------------------------------------
    {
        "slug": "leave-management",
        "title": "Leave Management",
        "description": "A guided tour of leave policies, requests and the team calendar.",
        "page_match": "leave-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "calendar-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Leave Management",
                "description": "Manage leave policies, approve requests and track who is absent — everything in one dashboard.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Leave metrics",
                "description": "Key indicators at the top: total leave taken, who's on leave today, upcoming requests and leave utilisation.",
                "element_selector": "#ld-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Who's on leave today",
                "description": "See a live list of employees currently on leave so you can plan around absences.",
                "element_selector": "#ld-on-leave",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Upcoming leave",
                "description": "Plan ahead with a list of approved leave that starts in the coming days.",
                "element_selector": "#ld-upcoming",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Customise the dashboard",
                "description": "Add, remove or rearrange the charts and panels to focus on what matters most to your team.",
                "element_selector": "#ld-open-customize",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 6,
                "title": "Leave Types & Assign Leave",
                "description": "Define your company's leave policy under Leave Types, then use Assign Leave to grant initial balances to employees.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 5. Attendance Tracking
    # -------------------------------------------------------------------------
    {
        "slug": "attendance-tracking",
        "title": "Attendance Tracking",
        "description": "A guided tour of attendance monitoring, records and correction requests.",
        "page_match": "attendance-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "finger-print-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Attendance Dashboard",
                "description": "Monitor punctuality, late arrivals, overtime and absenteeism across your whole team from here.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Live KPIs",
                "description": "Present employees, late arrivals, absences and overtime hours — all updated in real time.",
                "element_selector": "#am-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Customise the view",
                "description": "Add or remove charts — clock-in distribution, department attendance, weekly trends and more.",
                "element_selector": "#am-open-customize",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Attendance records",
                "description": "Browse, filter and export the complete attendance history for any date range or employee group.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Correction requests & overtime",
                "description": "Employees flag wrong punches — you approve corrections in one click. Overtime (Hour Account) tracks extra hours and compensatory leave.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 6. Payroll
    # -------------------------------------------------------------------------
    {
        "slug": "payroll-overview",
        "title": "Payroll",
        "description": "A guided tour of contracts, payroll runs and payslip management.",
        "page_match": "view-payroll-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "wallet-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Payroll",
                "description": "Manage employee contracts, run payroll, generate payslips, and handle loans and reimbursements.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Payroll KPIs",
                "description": "Total payroll cost, active contracts, pending payslips and reimbursements summarised at the top.",
                "element_selector": "#pd-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Payslip pipeline",
                "description": "Track payslips by status: draft, confirmed, sent, and paid — across the current pay period.",
                "element_selector": "#pd-pipeline",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Contracts & components",
                "description": "Set up each employee's contract with base salary. Then add allowances (HRA, travel) and deductions (PF, ESI) that apply automatically.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Run payroll",
                "description": "Generate payslips for a pay period in one click — Krew calculates gross pay, deductions and net pay automatically.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 7. Asset Management
    # -------------------------------------------------------------------------
    {
        "slug": "asset-management",
        "title": "Asset Management",
        "description": "A guided tour of company asset tracking, assignment and history.",
        "page_match": "asset-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "cube-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Asset Management",
                "description": "Track every company asset — laptops, phones, vehicles — and know exactly who holds each one.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Asset overview",
                "description": "Key metrics: total assets, allocated vs available, requests pending and assets due for return.",
                "element_selector": "#as-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Expiring & due for return",
                "description": "Stay on top of warranties and return deadlines — assets expiring soon appear here.",
                "element_selector": "#as-expiring",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Current allocations",
                "description": "See who currently holds each asset. Click to view full assignment history and transfer records.",
                "element_selector": "#as-allocations",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Assign & manage assets",
                "description": "Use the sidebar to add asset categories, create batches, and issue assets to employees via Request & Allocation.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 8. Performance Management (PMS)
    # -------------------------------------------------------------------------
    {
        "slug": "performance-management",
        "title": "Performance Management",
        "description": "A guided tour of OKRs, 360° feedback and appraisals.",
        "page_match": "dashboard-view",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "stats-chart-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Performance Management",
                "description": "Run OKRs, 360° feedback and appraisals — all from one connected performance platform.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Objectives overview",
                "description": "See the status of all objectives (on-track, at-risk, completed) across the current review period.",
                "element_selector": "#objectiveChart",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Key results",
                "description": "Drill into key results for each objective to track granular progress and update scores.",
                "element_selector": "#keyResultChart",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "360° Feedback",
                "description": "Gather structured feedback from peers, reports and managers. Employees see results after the review window closes.",
                "element_selector": "#feedbackChart",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Meetings & bonus points",
                "description": "Schedule 1:1s and team reviews from the Meetings menu. Reward outstanding performance with bonus points via the sidebar.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 9. Onboarding
    # -------------------------------------------------------------------------
    {
        "slug": "onboarding-pipeline",
        "title": "Onboarding",
        "description": "A guided tour of the employee onboarding pipeline and task management.",
        "page_match": "onboarding-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "rocket-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Onboarding",
                "description": "Guide new hires through their first days: document signing, task checklists, equipment requests and team introductions.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Onboarding metrics",
                "description": "Active onboardings, tasks completed, documents signed and time-to-productivity — tracked here.",
                "element_selector": "#on-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Stage pipeline",
                "description": "New joiners move through structured stages. The chart shows how many are at each stage right now.",
                "element_selector": "#chart-on-stages",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Tasks & documents",
                "description": "Assign tasks (e.g. 'Set up laptop') and attach documents to sign (offer letter, NDA). Employees complete these from their portal.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Convert to employee",
                "description": "Once onboarding is complete, one click converts the candidate record into a full employee profile — no double entry.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 10. Offboarding
    # -------------------------------------------------------------------------
    {
        "slug": "offboarding-process",
        "title": "Offboarding",
        "description": "A guided tour of the exit process, resignation letters and final settlement.",
        "page_match": "offboarding-dashboard",
        "match_type": "url_name",
        "audience": "managers",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "exit-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Offboarding",
                "description": "Manage resignations, notice periods and exit tasks for departing employees — fully tracked.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Offboarding metrics",
                "description": "Active exits, notice periods in progress, pending clearances and time-to-exit shown at a glance.",
                "element_selector": "#ob-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Exit pipeline",
                "description": "Departing employees move through stages: notice served, handover, clearance, final settlement.",
                "element_selector": "#ob-pipeline",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Notice period tracking",
                "description": "See who is currently serving their notice period and how many days remain.",
                "element_selector": "#ob-notice",
                "side": "left",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Asset returns & settlement",
                "description": "Track which company assets the employee needs to return. Once clearance is complete, trigger the final payslip.",
                "element_selector": "#ob-assets",
                "side": "left",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 11. Project Management
    # -------------------------------------------------------------------------
    {
        "slug": "project-management",
        "title": "Project Management",
        "description": "A guided tour of projects, tasks and time tracking.",
        "page_match": "project-dashboard-view",
        "match_type": "url_name",
        "audience": "all",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "briefcase-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Project Management",
                "description": "Create projects, assign tasks to team members, and track time with timesheets — all in one place.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Project health",
                "description": "Active projects, tasks in progress, overdue items and hours logged — your project KPIs at a glance.",
                "element_selector": "#pr-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Task status",
                "description": "A breakdown of tasks by status across all your projects — to-do, in progress and done.",
                "element_selector": "#pr-status-chart",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Projects & tasks",
                "description": "Create a project, set a deadline, add team members, then break it into tasks with owners and due dates.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "Timesheets",
                "description": "Team members log hours against tasks. Managers see a summary by project and employee for accurate billing or reporting.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
        ],
    },
    # -------------------------------------------------------------------------
    # 12. Help Desk
    # -------------------------------------------------------------------------
    {
        "slug": "helpdesk-overview",
        "title": "Help Desk",
        "description": "A guided tour of the ticket system, FAQs and SLA tracking.",
        "page_match": "helpdesk-dashboard",
        "match_type": "url_name",
        "audience": "all",
        "trigger": "auto_once",
        "is_published": True,
        "priority": 50,
        "icon": "headset-outline",
        "steps": [
            {
                "sequence": 1,
                "title": "Help Desk",
                "description": "A built-in support ticket system — employees raise issues, HR or IT resolves them, and everything is tracked.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 2,
                "title": "Ticket metrics",
                "description": "Open tickets, resolved today, average resolution time and SLA compliance — your support health dashboard.",
                "element_selector": "#hd-kpi-grid",
                "side": "bottom",
                "align": "start",
            },
            {
                "sequence": 3,
                "title": "Ticket charts",
                "description": "Visualise tickets by status, priority, type and department to spot recurring issues and allocate support resources.",
                "element_selector": "#chart-hd-status",
                "side": "top",
                "align": "start",
            },
            {
                "sequence": 4,
                "title": "Manage tickets",
                "description": "Browse all open tickets, assign owners, set priorities and respond — all from the Tickets list in the sidebar.",
                "element_selector": "",
                "side": "over",
                "align": "start",
            },
            {
                "sequence": 5,
                "title": "FAQs — reduce ticket volume",
                "description": "Pre-answer common questions in the FAQ section. Employees find answers instantly, reducing the number of tickets raised.",
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
        ("horilla_tour", "0003_seed_dashboard_highlights_tour"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
