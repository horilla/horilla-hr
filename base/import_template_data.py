"""
Example data for the downloadable import templates.

Each entry holds the template's column headers (exactly what the matching
importer reads) and a couple of realistic rows showing the expected format.
Use `import_template_frame(key)` to get a ready DataFrame.
"""

import datetime

import pandas as pd

IMPORT_TEMPLATES = {
    "pay_adjustment": {
        "columns": [
            "Badge ID",
            "Type",
            "Title",
            "Amount",
            "Pay Date",
            "Taxable / Pre-Tax",
            "Reason",
        ],
        "rows": [
            [
                "EMP001",
                "Arrears",
                "Salary Revision Back Pay",
                12000,
                datetime.date(2026, 12, 5),
                "Yes",
                "Revised from 1 July",
            ],
            [
                "EMP002",
                "Recovery",
                "Excess Salary Paid",
                5000,
                datetime.date(2026, 12, 5),
                "Yes",
                "Overpaid in October",
            ],
        ],
    },
    "employee": {
        "columns": ["employee_full_name", "email", "phone"],
        "rows": [
            ["John Doe", "john.doe@example.com", "9876543210"],
            ["Jane Smith", "jane.smith@example.com", "9123456780"],
        ],
    },
    "project": {
        "columns": [
            "Title",
            "Manager Badge ID",
            "Status",
            "Start Date",
            "End Date",
            "Description",
            "Company",
        ],
        "rows": [
            [
                "Website Redesign",
                "DEMO001",
                "in_progress",
                datetime.date(2025, 1, 6),
                datetime.date(2025, 6, 30),
                "Redesign the corporate website",
                "Company name",
            ],
            [
                "Mobile App Launch",
                "DEMO001,DEMO002",
                "new",
                datetime.date(2025, 3, 1),
                datetime.date(2025, 9, 30),
                "Multiple managers are separated by commas",
                "Company name",
            ],
        ],
    },
    "holiday": {
        "columns": ["Holiday Name", "Start Date", "End Date", "Recurring", "Company"],
        "rows": [
            ["New Year's Day", "2025-01-01", "2025-01-01", "yes", ""],
            ["Annual Shutdown", "2025-12-24", "2025-12-26", "no", "Company name"],
        ],
    },
    "asset": {
        "columns": [
            "Asset name",
            "Description",
            "Serial No.",
            "Purchase date",
            "Purchase cost",
            "Category",
            "Status",
            "Batch number",
        ],
        "rows": [
            [
                "Dell Latitude 5420",
                "14-inch business laptop, 16GB RAM",
                "SN-DL5420-0001",
                "2024-02-15",
                65000,
                "Laptops",
                "Available",
                "BATCH-2024-01",
            ],
            [
                "Logitech MX Master 3",
                "Wireless mouse",
                "SN-LMX3-0042",
                "2024-03-10",
                8500,
                "Accessories",
                "In use",
                "BATCH-2024-02",
            ],
        ],
    },
    "assign_leave": {
        "columns": [
            "Employee Badge ID",
            "Leave Type",
            "Available Days",
            "Carryforward Days",
            "Total Leave Days",
            "Assigned Date",
        ],
        "rows": [
            ["DEMO001", "Annual Leave", 12, 2, 14, "2025-01-01"],
            ["DEMO002", "Sick Leave", 6, 0, 6, "2025-01-01"],
        ],
    },
    "leave_request": {
        "columns": [
            "Badge ID",
            "Leave Type",
            "Start Date",
            "Start Date Breakdown",
            "End Date",
            "End Date Breakdown",
            "Description",
        ],
        "rows": [
            [
                "DEMO001",
                "Annual Leave",
                "2025-02-03",
                "Full Day",
                "2025-02-04",
                "Full Day",
                "Family function",
            ],
            [
                "DEMO002",
                "Sick Leave",
                "2025-02-05",
                "First Half",
                "2025-02-05",
                "First Half",
                "Medical appointment",
            ],
        ],
    },
    "attendance": {
        "columns": [
            "Badge ID",
            "Shift",
            "Work type",
            "Attendance date",
            "Check-in date",
            "Check-in",
            "Check-out date",
            "Check-out",
            "Worked hour",
            "Minimum hour",
        ],
        "rows": [
            [
                "DEMO001",
                "Morning Shift",
                "Office",
                "2025-01-06",
                "2025-01-06",
                "09:00:00",
                "2025-01-06",
                "18:00:00",
                "09:00:00",
                "08:00:00",
            ],
            [
                "DEMO002",
                "Morning Shift",
                "Work From Home",
                "2025-01-06",
                "2025-01-06",
                "09:30:00",
                "2025-01-06",
                "17:30:00",
                "08:00:00",
                "08:00:00",
            ],
        ],
    },
    "attendance_activity": {
        "columns": [
            "Badge ID",
            "Employee",
            "Attendance Date",
            "In Date",
            "Check In",
            "Check Out",
            "Out Date",
        ],
        "rows": [
            [
                "DEMO001",
                "John Doe",
                "2025-01-06",
                "2025-01-06",
                "09:00:00",
                "18:00:00",
                "2025-01-06",
            ],
            [
                "DEMO002",
                "Jane Smith",
                "2025-01-06",
                "2025-01-06",
                "09:30:00",
                "17:30:00",
                "2025-01-06",
            ],
        ],
    },
}


def import_template_frame(key):
    """Return the example DataFrame for the given template key."""
    template = IMPORT_TEMPLATES[key]
    return pd.DataFrame(template["rows"], columns=template["columns"])


def write_import_xlsx(data_frame, response):
    """Write `data_frame` to `response` as xlsx with a bold, centred header.

    Shared by the import templates and the import error downloads so both
    look the same.
    """
    from openpyxl.styles import Alignment, Font

    response["Content-Type"] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    with pd.ExcelWriter(response, engine="openpyxl") as writer:
        data_frame.to_excel(writer, index=False, sheet_name="Sheet1")
        sheet = writer.sheets["Sheet1"]
        bold = Font(bold=True)
        center = Alignment(horizontal="center", vertical="center")
        for cell in sheet[1]:
            cell.font = bold
            cell.alignment = center
        for column in sheet.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(
                max(width + 4, 15), 50
            )
