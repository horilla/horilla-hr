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

// Approving a forecasted leave brings the balance forward, so the server first asks for this summary (the forecast
// of the request) and the approver approves from it. The summary is loaded into one modal kept on the page body.
document.addEventListener("leaveForecastSummary", function (event) {
  var detail = (event && event.detail) || {};
  var modal = document.getElementById("forecastApproveModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "oh-modal";
    modal.id = "forecastApproveModal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-hidden", "true");
    modal.style.zIndex = 1030;
    modal.innerHTML =
      '<div class="oh-modal__dialog" style="max-width: 720px">' +
      '<div class="oh-modal__dialog-header">' +
      '<h2 class="oh-modal__dialog-title"></h2>' +
      '<button type="button" class="oh-modal__close--custom" aria-label="Close">' +
      '<ion-icon name="close-outline"></ion-icon></button></div>' +
      '<div class="oh-modal__dialog-body"></div></div>';
    document.body.appendChild(modal);
    modal.querySelector("button").addEventListener("click", function () {
      modal.classList.remove("oh-modal--show");
    });
    modal.addEventListener("click", function (e) {
      if (e.target === modal) modal.classList.remove("oh-modal--show");
    });
  }
  var body = modal.querySelector(".oh-modal__dialog-body");
  modal.querySelector(".oh-modal__dialog-title").textContent = detail.title || "";
  body.innerHTML = "";
  htmx.ajax("GET", detail.url, { target: body, swap: "innerHTML" }).then(function () {
    modal.classList.add("oh-modal--show");
  });
});
