"""Module for handling attendance error data."""

import uuid

import pandas as pd
from django.conf import settings
from django.http import HttpResponse

from horilla.methods import remove_dynamic_url


def handle_attendance_errors(error_list):
    """
    Reorganize a list of error dictionaries into a structured error data dictionary
    and remove keys with all None values.

    Parameters:
        error_list (list of dict): A list of dictionaries containing error details.

    Returns:
        dict: A structured dictionary where keys represent error types and values are lists
              of error details for each type.
    """
    keys_to_remove = []
    error_data = {
        "Badge ID": [],
        "Shift": [],
        "Work type": [],
        "Attendance date": [],
        "Check-in date": [],
        "Check-in": [],
        "Check-out date": [],
        "Check-out": [],
        "Worked hour": [],
        "Minimum hour": [],
        "Badge ID Error": [],
        "Shift Error": [],
        "Work Type Error": [],
        "Check-in Validation Error": [],
        "Check-out Validation Error": [],
        "Attendance Error": [],
        "Attendance Date Validation Error": [],
        "Check-in Error": [],
        "Check-out Error": [],
        "Worked Hours Error": [],
        "Minimum Hour Error": [],
        "Attendance Date Error": [],
        "Check-out Date Error": [],
        "Other Errors": [],
    }
    for item in error_list:
        for key, value in error_data.items():
            if key in item:
                value.append(item[key])
            else:
                value.append(None)

    keys_to_remove = [
        key for key, value in error_data.items() if all(v is None for v in value)
    ]

    for key in keys_to_remove:
        del error_data[key]
    data_frame = pd.DataFrame(error_data, columns=error_data.keys())
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="ImportError.xlsx"'
    data_frame.to_excel(response, index=False)

    def get_error_sheet(request):
        remove_dynamic_url(path_info)
        return response

    from attendance.urls import path, urlpatterns

    # Create a unique path for the error file download
    path_info = f"error-sheet-{uuid.uuid4()}"
    urlpatterns.append(path(path_info, get_error_sheet, name=path_info))
    settings.DYNAMIC_URL_PATTERNS.append(path_info)
    path_info = f"attendance/{path_info}"
    return path_info
