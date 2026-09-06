import inspect
import json
from datetime import datetime

import requests
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.middleware.csrf import get_token
from django.test import RequestFactory
from django.utils.datastructures import MultiValueDict

from asset.models import AssetCategory
from base.models import Company, EmployeeShift, WorkType
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals
from whatsapp.models import WhatsappCredientials, WhatsappFlowDetails


class CustomRequestFactory(RequestFactory):
    """
    Custom request factory to create mock POST requests with session and messages enabled.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.FILES = MultiValueDict()

    def _add_session_and_messages(self, request):
        """
        Add session and messages middleware to the request.

        Args:
            request: Django HttpRequest object to add session and messages.

        Returns:
            Modified request with session and messages added.
        """

        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)


def get_meta_url(id, service):
    """
    return the meta grap API url
    """
    return f"https://graph.facebook.com/v24.0/{id}/{service}"


def get_meta_details_from_number(number):
    emp_company = Employee.objects.filter(phone=number).first().get_company()
    company = emp_company if emp_company else Company.objects.filter(hq=True).first()

    credentials = WhatsappCredientials.objects.filter(company_id=company)
    credentials = (
        credentials.get(is_primary=True)
        if credentials.get(is_primary=True)
        else credentials.first()
    )
    url = get_meta_url(credentials.meta_phone_number_id, "messages")
    data = {
        "token": credentials.meta_token,
        "url": url,
        "business_id": credentials.meta_business_id,
        "credentials": credentials,
    }

    return data


def get_meta_details_from_id(cred_id):
    credentials = WhatsappCredientials.objects.get(id=cred_id)
    url = get_meta_url(credentials.meta_phone_number_id, "messages")

    data = {
        "token": credentials.meta_token,
        "url": url,
        "business_id": credentials.meta_business_id,
    }

    return data


def create_template_buttons(cred_id):
    """
    Creates a message template with buttons for different request types.

    Sends a POST request to the WhatsApp Business API to create a new template
    that includes various quick reply buttons for the user to choose from.

    Returns:
        dict: The JSON response from the API containing the status of the request.
    """
    data = get_meta_details_from_id(cred_id)
    api_url = get_meta_url(data.get("business_id", ""), "message_templates")
    token = data.get("token", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    buttons = [
        "Asset Request",
        "Attendance Request",
        "Bonus Point Redeem",
        "Leave Request",
        "Reimbursement Request",
        "Shift Request",
        "Work Type Request",
    ]

    quick_reply_buttons = [{"type": "QUICK_REPLY", "text": btn} for btn in buttons]

    payload = {
        "name": "button_template",
        "language": "en_US",
        "category": "utility",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Create Request"},
            {
                "type": "BODY",
                "text": "Choose a button from below to create the requests",
            },
            {"type": "BUTTONS", "buttons": quick_reply_buttons},
        ],
    }
    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    data = response.json()
    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def create_welcome_message(cred_id):
    """
    Creates a welcome message template.

    Sends a POST request to the WhatsApp Business API to create a welcome message
    template that responds to users when they contact the business.

    Returns:
        dict: The JSON response from the API containing the status of the request.
    """
    data = get_meta_details_from_id(cred_id)
    api_url = get_meta_url(data.get("business_id", ""), "message_templates")
    token = data.get("token", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "name": "welcome_message",
        "language": "en_US",
        "category": "utility",
        "components": [
            {
                "type": "BODY",
                "text": "Thanks for conatcting us, For further help send *'help'*. Thank you",
            },
        ],
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def create_help_message(cred_id):
    """
    Creates a help message template.

    Sends a POST request to the WhatsApp Business API to create a help message template
    that provides users with instructions on how to create various forms.

    Returns:
        dict: The JSON response from the API containing the status of the request.
    """
    data = get_meta_details_from_id(cred_id)
    api_url = get_meta_url(data.get("business_id", ""), "message_templates")
    token = data.get("token", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    body_text = """
    To create a request, send any of the following keywords. You can use capital or small letters, and spaces can be included or excluded.

    Asset Request : Send *'asset'*
    Bonus Point Redeem : Send *'bonus'* or *'bonus point'*
    Attendance Request : Send *'attendance'*
    Leave Request : Send *'leave'*
    Reimbursement Request : Send *'reimbursement'*
    Shift Request : Send *'shift'*
    Work Type Request : Send *'work type'*
    """

    payload = {
        "name": "help_text",
        "language": "en_US",
        "category": "utility",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Keywords"},
            {"type": "BODY", "text": body_text},
        ],
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def send_image_message(number, link):
    """
    Sends an image message to a specific WhatsApp number.

    Args:
        number (str): The recipient's phone number.
        link (str): The URL link to the image to be sent.

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    data = get_meta_details_from_number(number)
    headers = {
        "Authorization": f'Bearer {data.get("token","")}',
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "image",
        "image": {
            "link": link,
        },
    }

    api_url = data.get("url", "")
    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def send_document_message(number, link):
    """
    Sends an image message to a specific WhatsApp number.

    Args:
        number (str): The recipient's phone number.
        link (str): The URL link to the image to be sent.

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """

    data = get_meta_details_from_number(number)
    headers = {
        "Authorization": f'Bearer {data.get("token","")}',
        "Content-Type": "application/json",
    }
    url = data.get("url", "")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "document",
        "document": {
            "link": link,
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def send_text_message(number, message, header=None):
    """
    Sends a text message to a specific WhatsApp number.

    Args:
        number (str): The recipient's phone number.
        message (str): The text message to be sent.

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    data = get_meta_details_from_number(number)
    headers = {
        "Authorization": f'Bearer {data.get("token","")}',
        "Content-Type": "application/json",
    }
    url = data.get("url", "")

    full_message = f"*{header}*\n\n{message}" if header else message

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "text",
        "text": {
            "body": full_message,
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def send_template_message(number, template_name, ln_code="en_US"):
    """
    Sends a template message to a specific WhatsApp number.

    Args:
        number (str): The recipient's phone number.
        template_name (str): The name of the template to be sent.
        ln_code (str): The language code for the message (default is "en_US").

    Returns:
        dict: The JSON response from the API containing the status of the request.
    """

    data = get_meta_details_from_number(number)
    headers = {
        "Authorization": f'Bearer {data.get("token","")}',
        "Content-Type": "application/json",
    }
    url = data.get("url", "")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": ln_code},
            "components": [],
        },
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def send_flow_message(to, template_name):
    """
    Sends an interactive flow message to a specific WhatsApp number.

    Args:
        to (str): The recipient's phone number.
        template_name (str): The name of the flow template to be sent.

    Returns:
        dict: The JSON response from the API containing the status of the request.
    """

    data = get_meta_details_from_number(to)
    headers = {
        "Authorization": f'Bearer {data.get("token","")}',
        "Content-Type": "application/json",
    }
    url = data.get("url", "")

    flow_id = (
        WhatsappFlowDetails.objects.filter(
            template=template_name, whatsapp_id=data.get("credentials").id
        )
        .first()
        .flow_id
    )
    employee = Employee.objects.get(phone=to)
    details = flow_message_details(template_name, employee)

    flow_paylod = {
        "screen": "screen_one",
    }
    if details.get("data"):
        flow_paylod["data"] = details.get("data")

    payload = {
        "recipient_type": "individual",
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": details.get("header", None)},
            "body": {"text": details.get("body", None)},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": "flow_token",
                    "flow_id": flow_id,
                    "flow_cta": details.get("button", {}),
                    "flow_action_payload": flow_paylod,
                },
            },
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(f"error: {data['error'].get('message')}")
    if response.status_code not in (200, 201):
        raise Exception(f"Request failed with status {response.status_code}: {data}")
    return data


def flow_message_details(template_name, employee):
    """
    Retrieves the flow message details for a specific template name.

    Args:
        template_name (str): The name of the flow template.
        employee (Employee): The employee object containing available leave and shift data.

    Returns:
        dict: A dictionary containing details like header, body, button, and associated data for the flow.
    """

    leave_types_data = [
        {
            "id": str(available_leave.leave_type_id.id),
            "title": available_leave.leave_type_id.name,
        }
        for available_leave in employee.available_leave.all()
    ]
    shift_data = [
        {"id": str(shift.id), "title": shift.employee_shift}
        for shift in EmployeeShift.objects.all()
    ]
    work_type_data = [
        {"id": str(work_type.id), "title": work_type.work_type}
        for work_type in WorkType.objects.all()
    ]
    asset_data = [
        {"id": str(asset.id), "title": asset.asset_category_name}
        for asset in AssetCategory.objects.all()
    ]

    details = {
        "leave": {
            "header": "Leave Request",
            "body": "To proceed with your leave request, Please fill out the following form",
            "button": "Add Leave Request",
            "data": {"leave_types": leave_types_data},
        },
        "asset": {
            "header": "Asset Request",
            "body": "To proceed with your asset request, Please fill out the following form",
            "button": "Add Asset Request",
            "data": {"asset_categories": asset_data},
        },
        "shift": {
            "header": "Shift Request",
            "body": "To proceed with your shift request, Please fill out the following form",
            "button": "Add Shift Request",
            "data": {"shift": shift_data},
        },
        "work_type": {
            "header": "Work Type Request",
            "body": "To proceed with your work type request, Please fill out the following form",
            "button": "Add Work Type Request",
            "data": {"work_type": work_type_data},
        },
        "attendance": {
            "header": "Attendnace Request",
            "body": "To proceed with your attendnace request, Please fill out the following form",
            "button": "Add Attendnace Request",
            "data": {"shift": shift_data, "work_type": work_type_data},
        },
        "bonus_point": {
            "header": "Bonus Point Redeem Request",
            "body": "To proceed with your bonus point redeem request, Please fill out the following form",
            "button": "Redeem Bonus point",
        },
        "reimbursement": {
            "header": "Reimbursement Request",
            "body": "To proceed with your reimbursement request, Please fill out the following form",
            "button": "Add Reimbursement Request",
        },
    }

    return details.get(template_name)


def create_request(
    employee,
    flow_response,
    data,
    form_class,
    view_function,
    message_header,
    attachments=None,
):
    """
    Generic function to create a request, populate form data, validate, and call a view.

    Args:
        employee: Employee instance, used for user and employee-specific data.
        flow_response: Dictionary containing specific data for the request.
        data: Form data dictionary specific to the request type.
        form_class: Form class to validate request data.
        view_function: View function to process the request.
        attachments: List of files (optional) to include in the request.

    Returns:
        Success or error message from form validation and view execution.
    """

    factory = CustomRequestFactory()
    request = factory.post("/")
    request.session = SessionStore()
    request.session.create()
    token = get_token(request)

    data["csrfmiddlewaretoken"] = token
    request.POST = QueryDict("", mutable=True)
    request.POST.update(data)
    request.user = employee.employee_user_id
    factory._add_session_and_messages(request)
    _thread_locals.request = request

    if attachments:
        for idx, attachment in enumerate(attachments):
            request.FILES.appendlist(
                "attachment",
                SimpleUploadedFile(
                    attachment.name,
                    attachment.read(),
                    content_type="application/octet-stream",
                ),
            )

    request.POST = data
    form = form_class(request.POST, files=request.FILES if attachments else None)
    if form.is_valid():
        message = f"{message_header} created successfully"
    else:
        form_errors = dict(form.errors)
        message = "\n".join(
            f"{message_header if field == '__all__' else field}: {', '.join(errors)}"
            for field, errors in form_errors.items()
        )
    try:
        function = inspect.unwrap(view_function)
        _response = function(request=request)
    except Exception as e:
        message = f"Error in {view_function.__name__}: {e}"

    return message


def shift_create(employee, flow_response):
    """
    Creates a shift request for the specified employee using the provided flow response data.

    Args:
        employee: Employee instance submitting the shift request.
        flow_response: Dictionary containing shift-specific data like shift ID and dates.

    Returns:
        Message indicating the success or failure of the request.
    """

    from base.forms import ShiftRequestForm
    from base.views import shift_request as shift_request_creation

    data = {
        "employee_id": employee.id,
        "shift_id": flow_response["shift"],
        "requested_date": flow_response["requested_date"],
        "requested_till": flow_response["requested_till"],
        "is_permanent_shift": flow_response.get("permenent_request", False),
        "description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        ShiftRequestForm,
        shift_request_creation,
        "Shift request",
    )


def work_type_create(employee, flow_response):
    """
    Creates a work type request for the specified employee.

    Args:
        employee: Employee instance submitting the work type request.
        flow_response: Dictionary with work type request data.

    Returns:
        Message indicating the success or failure of the request.
    """

    from base.forms import WorkTypeRequestForm
    from base.views import work_type_request as work_type_request_creation

    data = {
        "employee_id": employee.id,
        "work_type_id": flow_response["work_type"],
        "requested_date": flow_response["requested_date"],
        "requested_till": flow_response["requested_till"],
        "is_permanent_work_type": flow_response.get("permenent_request", False),
        "description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        WorkTypeRequestForm,
        work_type_request_creation,
        "Work type request",
    )


def leave_request_create(employee, flow_response):
    """
    Creates a leave request for the specified employee, optionally with an attachment.

    Args:
        employee: Employee instance submitting the leave request.
        flow_response: Dictionary with leave-specific data, including optional attachment info.

    Returns:
        Message indicating the success or failure of the request.
    """

    from leave.forms import UserLeaveRequestCreationForm
    from leave.views import leave_request_create as leave_req_creation

    media_id = (
        flow_response.get("document_picker")[0]["id"]
        if flow_response.get("document_picker")
        else None
    )
    file_name = (
        flow_response.get("document_picker")[0]["file_name"]
        if flow_response.get("document_picker")
        else None
    )

    data = get_meta_details_from_number(employee.phone)
    attachment_file = (
        get_whatsapp_media_file(media_id, file_name, data.get("token", ""))
        if media_id
        else None
    )

    data = {
        "employee_id": employee.id,
        "leave_type_id": flow_response["leave_type"],
        "start_date": flow_response["start_date"],
        "start_date_breakdown": flow_response["start_date_breakdown"],
        "end_date": flow_response["end_date"],
        "end_date_breakdown": flow_response["end_date_breakdown"],
        "description": flow_response["description"],
    }
    attachments = [attachment_file] if attachment_file else None
    return create_request(
        employee,
        flow_response,
        data,
        UserLeaveRequestCreationForm,
        leave_req_creation,
        "Leave request",
        attachments,
    )


def asset_request_create(employee, flow_response):
    """
    Creates an asset request for the specified employee.

    Args:
        employee: Employee instance submitting the asset request.
        flow_response: Dictionary with asset request data.

    Returns:
        Message indicating the success or failure of the request.
    """

    from asset.forms import AssetRequestForm
    from asset.views import asset_request_creation

    data = {
        "requested_employee_id": employee.id,
        "asset_category_id": flow_response["asset_category"],
        "description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        AssetRequestForm,
        asset_request_creation,
        "Asset request",
    )


def attendance_request_create(employee, flow_response):
    """
    Creates an attendance request for the specified employee.

    Args:
        employee: Employee instance submitting the attendance request.
        flow_response: Dictionary with attendance-specific data.

    Returns:
        Message indicating the success or failure of the request.
    """

    from attendance.forms import NewRequestForm
    from attendance.views.requests import request_new as attendance_request_creation

    for key in ["check_in_time", "check_out_time"]:
        value = flow_response.get(key)
        if isinstance(value, str):
            try:
                flow_response[key] = datetime.strptime(value, "%H:%M:%S").time()
            except ValueError:
                try:
                    flow_response[key] = datetime.strptime(value, "%H:%M").time()
                except ValueError:
                    flow_response[key] = None

    data = {
        "employee_id": employee.id,
        "attendance_date": flow_response["attendance_date"],
        "shift_id": flow_response["shift"],
        "work_type_id": flow_response["work_type"],
        "attendance_clock_in_date": flow_response["check_in_date"],
        "attendance_clock_in": flow_response["check_in_time"],
        "attendance_clock_out_date": flow_response["check_out_date"],
        "attendance_clock_out": flow_response["check_out_time"],
        "attendance_worked_hour": flow_response["worked_hours"],
        "minimum_hour": flow_response["minimum_hours"],
        "request_description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        NewRequestForm,
        attendance_request_creation,
        "Attendance request",
    )


def bonus_point_create(employee, flow_response):
    """
    Creates a bonus point redemption request for the specified employee.

    Args:
        employee: Employee instance submitting the bonus point redemption request.
        flow_response: Dictionary with bonus point redemption data.

    Returns:
        Message indicating the success or failure of the request.
    """

    from payroll.forms.component_forms import ReimbursementForm
    from payroll.views.component_views import create_reimbursement

    data = {
        "employee_id": employee.id,
        "title": flow_response["title"],
        "type": "bonus_encashment",
        "allowance_on": flow_response["allowance_on"],
        "bonus_to_encash": flow_response["bonus_point"],
        "description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        ReimbursementForm,
        create_reimbursement,
        "Bonus point redemption request",
    )


def reimbursement_create(employee, flow_response):
    """
    Creates a reimbursement request for the specified employee, including any attachments.

    Args:
        employee: Employee instance submitting the reimbursement request.
        flow_response: Dictionary with reimbursement data, including optional attachments.

    Returns:
        Message indicating the success or failure of the request.
    """

    from payroll.forms.component_forms import ReimbursementForm
    from payroll.views.component_views import create_reimbursement

    data = get_meta_details_from_number(employee.phone)
    attachments = [
        get_whatsapp_media_file(image["id"], image["file_name"], data.get("token", ""))
        for image in flow_response.get("document_picker", [])
        if image.get("id") and image.get("file_name")
    ]
    data = {
        "employee_id": employee.id,
        "title": flow_response["title"],
        "type": "reimbursement",
        "allowance_on": flow_response["allowance_date"],
        "amount": flow_response["amount"],
        "description": flow_response["description"],
    }
    return create_request(
        employee,
        flow_response,
        data,
        ReimbursementForm,
        create_reimbursement,
        "Reimbursment",
        attachments,
    )


def get_whatsapp_media_file(media_id, file_name, token):
    """
    Fetches a media file from WhatsApp using its media ID.

    Args:
        media_id (str): The ID of the media to fetch.
        file_name (str): The base name to use for saving the media file.

    Returns:
        ContentFile: A Django ContentFile object containing the media data, or None if the fetch fails.
    """

    url = f"https://graph.facebook.com/v24.0/{media_id}"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 200:
        media_data = response.json()
        media_url = media_data.get("url")
        file = download_whatsapp_media(media_url, file_name, token)
        return file
    else:
        print(f"Failed to fetch media: {response.text}")
        return None


def download_whatsapp_media(media_url, file_name, token):
    """
    Downloads media from a given URL and saves it as a ContentFile.

    Args:
        media_url (str): The URL of the media to download.
        file_name (str): The name to save the downloaded media file as.

    Returns:
        ContentFile: A Django ContentFile object containing the media data, or None if the download fails.
    """

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(media_url, headers=headers, timeout=30)
    if response.status_code == 200:
        content_type = response.headers.get("Content-Type")
        extension = content_type.split("/")[-1]
        file_name = f"{file_name[:50]}.{extension}"
        file_content = ContentFile(response.content)
        file_content.name = file_name
        return file_content
    else:
        print(f"Failed to download media: {response.status_code}")
        return None


def create_flow(flow_name, template_name, cred_id):
    """
    Creates a new flow in WhatsApp Business API.

    Args:
        flow_name (str): The name of the flow to create.
        template_name (str): The name of the template associated with the flow.

    Returns:
        Response: The JSON response from the API, or error details if the creation fails.
    """
    credential = WhatsappCredientials.objects.get(id=cred_id)

    headers = {
        "Authorization": f"Bearer {credential.meta_token}",
        "Content-Type": "application/json",
    }
    data = {"name": flow_name, "categories": "OTHER"}
    api_url = get_meta_url(credential.meta_business_id, "flows")

    response = requests.post(api_url, json=data, headers=headers, timeout=30)
    data = response.json()

    if response.status_code not in (200, 201):
        raise Exception(f"Flow creation failed: {data}")

    flow_id = data.get("id")
    if not flow_id:
        raise Exception(f"Flow creation failed: Missing flow ID in response: {data}")

    obj, created = WhatsappFlowDetails.objects.get_or_create(
        template=template_name,
        whatsapp_id=credential,
        defaults={"flow_id": flow_id},
    )
    if not created:
        obj.flow_id = flow_id
        obj.save()

    return data


def update_flow(flow_id, flow_json, token):
    """
    Updates an existing flow with new data.

    Args:
        flow_id (str): The ID of the flow to update.
        flow_json (dict): The JSON object containing the new flow data.

    Returns:
        Response: The JSON response from the API, or error details if the update fails.
    """
    url = get_meta_url(flow_id, "assets")
    headers = {"Authorization": f"Bearer {token}"}

    with open("flow.json", "w") as file:
        json.dump(flow_json, file, indent=2)

    with open("flow.json", "rb") as file:
        files = {
            "file": ("flow.json", file, "application/json"),
            "name": (None, "flow.json"),
            "asset_type": (None, "FLOW_JSON"),
        }
        response = requests.post(url, headers=headers, files=files, timeout=30)

    data = response.json()

    if response.status_code not in (200, 201):
        raise Exception(f"Flow update failed: {data}")

    if data.get("validation_error"):
        raise Exception(f"Flow validation error: {data['validation_error']}")

    return data


def publish_flow(flow_id, token):
    """
    Publishes a flow in WhatsApp Business API.

    Args:
        flow_id (str): The ID of the flow to publish.

    Returns:
        Response: The JSON response from the API, or error details if the publication fails.
    """

    headers = {"Authorization": f"Bearer {token}"}
    api_url = get_meta_url(flow_id, "publish")

    response = requests.post(api_url, headers=headers, timeout=30)
    data = response.json()

    if response.status_code not in (200, 201):
        raise Exception(f"Flow publish failed: {data}")

    if data.get("error"):
        raise Exception(f"Flow publish error: {data['error']}")

    return data
