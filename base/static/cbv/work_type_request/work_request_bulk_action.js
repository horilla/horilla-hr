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

function workTypeRequestListUrl() {
    var url = "/work-list-view/";
    var form = document.getElementById("filterForm");
    if (form && typeof jQuery !== "undefined") {
        var params = jQuery(form).serialize();
        if (params) {
            url = "/work-list-view/?" + params;
        }
    }
    return url;
}

function refreshWorkTypeRequestList() {
    var doneMessages = function () {
        if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
            $("#reloadMessagesButton").click();
        }
    };
    // Embedded in the employee detail "Work Type & Shift" tab: reload just
    // that tab's own list through its hidden reload button. The standalone
    // page's "/work-list-view/" + "#listContainer" below would instead pull
    // the whole requests page into the employee list container.
    var $profileReload = $("#work_targetReload");
    if ($profileReload.length) {
        $profileReload.one("htmx:afterRequest", doneMessages);
        $profileReload.trigger("click");
        return;
    }

    var listUrl = workTypeRequestListUrl();

    if (typeof htmx !== "undefined" && typeof htmx.ajax === "function") {
        htmx
            .ajax("GET", listUrl, {
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
        url: listUrl,
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
            }
            doneMessages();
        },
    });
}

function workTypeRequestRowApprove(url, confirmText) {
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
                success: function (response) {
                    // Approved/rejected from the employee detail view: click
                    // its "Work Type & Shift" tab button so the tab content
                    // reloads in place, instead of loading the standalone
                    // requests list over the page.
                    var $profileTab = $('[data-target="#work-shift1"]');
                    if (response && response.result === true && $profileTab.length) {
                        // The tab only refetches when it isn't marked loaded.
                        $profileTab.first().removeAttr("data-loaded").click();
                        if (typeof jQuery !== "undefined" && $("#reloadMessagesButton").length) {
                            $("#reloadMessagesButton").click();
                        }
                        return;
                    }
                    refreshWorkTypeRequestList();
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

function handleApproveRequestsClick() {
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
            text: i18nMessages.confirmBulkApprove,
            icon: "success",
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
                    url: "/work-type-request-bulk-approve/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshWorkTypeRequestList();
                    },
                });
            }
        });
    }
}


function handleRejectRequestsClick() {
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
            text: i18nMessages.confirmBulkReject,
            icon: "warning",
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
                    url: "/work-type-request-bulk-cancel/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshWorkTypeRequestList();
                    },
                });
            }
        });
    }
}

function handleDeleteRequestsClick() {
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
                    url: "/work-type-request-bulk-delete/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    complete: function () {
                        refreshWorkTypeRequestList();
                    },
                });
            }
        });
    }
}

//scripts for rotating work type page
//bulk archive in rotate work type
$(document).on('click', '#archiveWorkRotateNav', function (e) {
    e.preventDefault();
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
                    url: "/rotating-work-type-assign-bulk-archive/?is_active=False",
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
});


function UnarchiveWorkRotateNav() {
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
                    url: "/rotating-work-type-assign-bulk-archive/?is_active=True",
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
}

function deleteWorkRotateNav() {
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
                    url: "/rotating-work-type-assign-bulk-delete/",
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
}
