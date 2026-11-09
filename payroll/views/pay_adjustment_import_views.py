"""The Arrears & Recovery import: the template, the upload with its preview, the confirmation, and the error file."""

import json
import uuid

import pandas as pd
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods

from base.import_template_data import import_template_frame, write_import_xlsx
from horilla.decorators import login_required, permission_required
from payroll.methods.pay_adjustment_import import (
    HEADERS,
    SheetProblem,
    check_sheet,
    create_entries,
    read_sheet,
)

SESSION_KEY = "pay_adjustment_import"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _state(request, token):
    state = request.session.get(SESSION_KEY)
    if not state or not token or state.get("token") != token:
        return None
    return state


@login_required
@permission_required("payroll.add_payadjustment")
@require_http_methods(["GET"])
def pay_adjustment_import_template(request):
    """The sheet to fill in: the columns, and two example rows."""
    response = HttpResponse(content_type=XLSX)
    response["Content-Disposition"] = (
        'attachment; filename="arrears_recovery_import_template.xlsx"'
    )
    write_import_xlsx(import_template_frame("pay_adjustment"), response)
    return response


@login_required
@permission_required("payroll.add_payadjustment")
@require_http_methods(["GET", "POST"])
def pay_adjustment_import(request):
    """GET the upload step; POST the file to read it and show every row checked, writing nothing."""
    if request.method == "GET":
        request.session.pop(SESSION_KEY, None)
        # "Upload Another File" asks for just the upload step; opening the modal asks for all of it.
        page = (
            "import_upload" if request.GET.get("step") == "upload" else "import_modal"
        )
        return render(
            request, f"payroll/pay_adjustment/{page}.html", {"headers": HEADERS}
        )

    file = request.FILES.get("file")
    if file is None:
        return render(
            request,
            "payroll/pay_adjustment/import_upload.html",
            {"headers": HEADERS, "problem": str(_("Choose A File To Import."))},
        )
    try:
        rows, table = check_sheet(read_sheet(file))
    except SheetProblem as problem:
        return render(
            request,
            "payroll/pay_adjustment/import_upload.html",
            {"headers": HEADERS, "problem": str(problem)},
        )
    failed = [row for row in table if row["errors"]]
    token = uuid.uuid4().hex
    request.session[SESSION_KEY] = {
        "token": token,
        "rows": rows,
        "failed": failed,
        "name": file.name,
    }
    return render(
        request,
        "payroll/pay_adjustment/import_preview.html",
        {
            "token": token,
            "table": table[:300],
            "hidden_rows": max(0, len(table) - 300),
            "valid_count": len(rows),
            "failed_count": len(failed),
            "file_name": file.name,
        },
    )


@login_required
@permission_required("payroll.add_payadjustment")
@require_http_methods(["POST"])
def pay_adjustment_import_confirm(request):
    """Create the rows that passed, as Drafts, and say how it went."""
    state = _state(request, request.POST.get("token"))
    if state is None:
        return render(
            request,
            "payroll/pay_adjustment/import_upload.html",
            {
                "headers": HEADERS,
                "problem": str(_("That Import Has Expired. Upload The File Again.")),
            },
        )
    created, skipped = create_entries(state["rows"])
    request.session.pop(SESSION_KEY, None)
    messages.success(
        request,
        ngettext(
            "%(n)d Entry Saved As A Draft.", "%(n)d Entries Saved As Drafts.", created
        )
        % {"n": created},
    )
    if state["failed"]:
        messages.warning(
            request,
            _("%(n)d Row(s) With Problems Were Left Out.")
            % {"n": len(state["failed"])},
        )
    for row, reason in skipped:
        messages.warning(
            request, _("Row %(row)s: %(reason)s") % {"row": row, "reason": reason}
        )
    # Close the modal and show the messages as a toast, as the other forms do.
    response = HttpResponse(
        """<script id="payAdjustmentImportDone">
            $("#payAdjustmentImportDone").closest(".oh-modal--show").removeClass("oh-modal--show");
            $("#reloadMessagesButton").click();
        </script>"""
    )
    response["HX-Trigger"] = json.dumps({"reloadPayAdjustments": {"target": "body"}})
    return response


@login_required
@permission_required("payroll.add_payadjustment")
@require_http_methods(["GET"])
def pay_adjustment_import_errors(request):
    """The rows that failed, with what was wrong with each, as a sheet to correct and upload again."""
    state = _state(request, request.GET.get("token"))
    if state is None or not state["failed"]:
        return HttpResponse(str(_("There Are No Failed Rows To Download.")), status=404)
    frame = pd.DataFrame(
        [
            [
                row["badge"],
                row["kind"],
                row["title"],
                row["amount"],
                row["pay_date"],
                {"Yes": "Yes", "No": "No"}.get(str(row["tax"]), ""),
                row["reason"],
                "; ".join(row["errors"]),
            ]
            for row in state["failed"]
        ],
        columns=HEADERS + ["Errors"],
    )
    response = HttpResponse(content_type=XLSX)
    response["Content-Disposition"] = (
        'attachment; filename="arrears_recovery_import_errors.xlsx"'
    )
    write_import_xlsx(frame, response)
    return response
