// "No Available Leave": the alert the approve button raises when a leave does not fit the balance of its end
// date. The server sends the lines to show (leaveBalanceShort) and, when the approver may, a Reset Now & Approve
// button that posts back to the same address with reset_now set.
document.addEventListener("leaveBalanceShort", function (event) {
  var detail = (event && event.detail) || {};
  var table = document.createElement("div");
  table.style.cssText = "text-align:left;font-size:14px;margin-top:6px;";
  (detail.lines || []).forEach(function (line) {
    var row = document.createElement("div");
    row.style.cssText = "display:flex;justify-content:space-between;gap:16px;padding:5px 0;border-bottom:1px solid #eee;";
    var label = document.createElement("span");
    label.style.color = "#6b7280";
    label.textContent = line[0];
    var value = document.createElement("strong");
    value.textContent = line[1];
    row.appendChild(label);
    row.appendChild(value);
    table.appendChild(row);
  });
  var note = document.createElement("p");
  note.style.cssText = "margin:14px 0 0;font-weight:600;";
  note.textContent = detail.message || "";
  var body = document.createElement("div");
  body.appendChild(table);
  body.appendChild(note);

  Swal.fire({
    title: detail.title,
    html: body,
    icon: "warning",
    showCancelButton: !!detail.can_reset,
    showConfirmButton: true,
    confirmButtonText: detail.can_reset ? detail.confirm : detail.cancel,
    cancelButtonText: detail.cancel,
    confirmButtonColor: detail.can_reset ? "#008000" : "#6c757d",
    cancelButtonColor: "#6c757d",
  }).then(function (result) {
    if (!result.isConfirmed || !detail.can_reset) return;
    htmx.ajax("POST", detail.url, {
      target: "body",
      swap: "none",
      values: { reset_now: "1" },
    });
  });
});
