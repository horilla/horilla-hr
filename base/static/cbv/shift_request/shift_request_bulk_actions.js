if (typeof tickShiftCheckboxes === "function") {
    tickShiftCheckboxes();
}
function makeShiftListUnique(list) {
    return Array.from(new Set(list));
}

if (typeof tickWorktypeCheckboxes === "function") {
    tickWorktypeCheckboxes();
}
function makeWorktypeListUnique(list) {
    return Array.from(new Set(list));
}

if (typeof tickRShiftCheckboxes === "function") {
    tickRShiftCheckboxes();
}
function makeRShiftListUnique(list) {
    return Array.from(new Set(list));
}

if (typeof tickRWorktypeCheckboxes === "function") {
    tickRWorktypeCheckboxes();
}
function makeRWorktypeListUnique(list) {
    return Array.from(new Set(list));
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function openShiftRequestTabAfterInject(container) {
    var scope = container.querySelector("#shift-tab") || container;
    setTimeout(function () {
        var preferred =
            scope.querySelector(".oh-tabs__tab--active") ||
            scope.querySelector(".oh-tabs__tab");
        if (preferred) {
            preferred.click();
        }
    }, 120);
}

function refreshShiftRequestList() {
    var doneMessages = function () {
        if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
            $("#reloadMessagesButton").click();
        }
    };

    // "/shift-request-tab/" is the standalone Shift Request page's own tab
    // endpoint. This script is also loaded on pages that embed the shift
    // request list elsewhere (e.g. the "Work Requests" page at
    // /employee/requests/, whose tab endpoint is
    // /employee/requests/shift-request-tab/) - hitting the hardcoded
    // absolute URL there replaced #listContainer with the wrong (unrelated,
    // always-empty) tab markup and broke the view. The list itself already
    // renders a hidden "reload-record" button whose hx-get is baked in with
    // the correct current request.path, so reuse that instead of guessing
    // the endpoint - it reloads just the list, which is all a single
    // approve/reject/delete actually needs to refresh.
    // Embedded in the employee detail "Work Type & Shift" tab: reload that
    // tab's own list, not the employee list that owns #listContainer there.
    var $reloadBtn = $("#shift-reques-individual-divReload");
    if (!$reloadBtn.length) {
        $reloadBtn = $("#listContainer .reload-record").first();
    }
    if ($reloadBtn.length) {
        $reloadBtn.one("htmx:afterRequest", doneMessages);
        $reloadBtn.trigger("click");
        return;
    }

    if (typeof htmx !== "undefined" && typeof htmx.ajax === "function") {
        htmx
            .ajax("GET", "/list-shift-request/", {
                target: "#listContainer",
                swap: "innerHTML",
                headers: {
                    "HX-Current-URL": window.location.href,
                },
            })
            .then(doneMessages)
            .catch(doneMessages);
        return;
    }

    $.ajax({
        type: "GET",
        url: "/employee/requests/shift-request-tab/",
        headers: {
            "HX-Request": "true",
            "HX-Current-URL": window.location.href,
            "HX-Target": "listContainer",
        },
        success: function (html) {
            var container = document.getElementById("listContainer");
            if (container) {
                container.innerHTML = html;
                if (typeof htmx !== "undefined") {
                    htmx.process(container);
                }
                openShiftRequestTabAfterInject(container);
            }
            doneMessages();
        },
    });
}

function shiftRequestRowApprove(url, confirmText) {
    Swal.fire({
        text: confirmText,
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#008000",
        cancelButtonColor: "#6c757d",
        confirmButtonText: i18nMessages.confirm,
        cancelButtonText: i18nMessages.cancel,
    }).then(function (result) {
        if (result.isConfirmed) {
            $.ajax({
                type: "GET",
                url: url,
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                dataType: "json",
                success: function () {
                    refreshShiftRequestList();
                },
                error: function () {
                    if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
                        $("#reloadMessagesButton").click();
                    }
                },
            });
        }
    });
}

function shiftRequestApprove() {
  ids = [];
    // function addIdsTab(tabId){
    //   var dataIds = $("#"+tabId).attr("data-ids");
    //   if (dataIds){
    //     ids = ids.concat(JSON.parse(dataIds));
    //   }
    // }
    // addIdsTab("shiftselectedInstances");
    // addIdsTab("allocatedselectedInstances");
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        // Use SweetAlert for the confirmation dialog
        Swal.fire({
            text: i18nMessages.confirmBulkApprove,
            icon: "success",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                // ids = [];
                // ids.push($("#selectedInstances").attr("data-ids"));
                // ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/shift-request-bulk-approve/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshShiftRequestList();
                    },
                });
            }
        });
    }
}

function shiftRequestReject() {
    ids = [];
    // function addIdsTab(tabId){
    //   var dataIds = $("#"+tabId).attr("data-ids");
    //   if (dataIds){
    //     ids = ids.concat(JSON.parse(dataIds));
    //   }
    // }
    // addIdsTab("shiftselectedInstances");
    // addIdsTab("allocatedselectedInstances");
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkReject,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                $.ajax({
                    type: "POST",
                    url: "/shift-request-bulk-cancel/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshShiftRequestList();
                    },
                });
            }
        });
    }
}

function shiftRequestDelete() {
    ids = [];
    // function addIdsTab(tabId){
    //   var dataIds = $("#"+tabId).attr("data-ids");
    //   if (dataIds){
    //     ids = ids.concat(JSON.parse(dataIds));
    //   }
    // }
    // addIdsTab("shiftselectedInstances");
    // addIdsTab("allocatedselectedInstances");
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkDelete,
            icon: "error",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                $.ajax({
                    type: "POST",
                    url: "/shift-request-bulk-delete/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshShiftRequestList();
                    },
                });
            }
        });
    }
}


function archiveRotateShift() {
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkArchive,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/rotating-shift-assign-bulk-archive/?is_active=False",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload(); // Reload the current page
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
};

function un_archiveRotateShift() {
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkUnArchive,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/rotating-shift-assign-bulk-archive/?is_active=True",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload(); // Reload the current page
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
};

function deleteRotatingShift() {
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));
    if (ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkDelete,
            icon: "error",
            showCancelButton: true,
            confirmButtonColor: "#d33",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                ids.push($("#selectedInstances").attr("data-ids"));
                ids = JSON.parse($("#selectedInstances").attr("data-ids"));
                $.ajax({
                    type: "POST",
                    url: "/rotating-shift-assign-bulk-delete/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload(); // Reload the current page
                        } else {
                            // console.log("Unexpected HTTP status:", jqXHR.status);
                        }
                    },
                });
            }
        });
    }
};
