tickCheckboxes();
function makeListUnique(list) {
    return Array.from(new Set(list));
}

tickactivityCheckboxes();
function makeactivityListUnique(list) {
    return Array.from(new Set(list));
}

ticklatecomeCheckboxes();
function makelatecomeListUnique(list) {
    return Array.from(new Set(list));
}

function validateActivityIds(event) {
    event.preventDefault();

    var $selectedActivity = $("#selectedActivity");
    var idsRaw = $selectedActivity.attr("data-ids");

    if (!idsRaw) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
        return;
    }

    let ids;
    try {
        ids = JSON.parse(idsRaw);
    } catch (e) {
        console.error("Invalid JSON in data-ids:", e);
        Swal.fire({
            text: gettext("An unexpected error occurred. Please refresh the page."),
            icon: "error",
            confirmButtonText: i18nMessages.close,
        });
        return;
    }

    if (!Array.isArray(ids) || ids.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
        return;
    }

    $("#bulkDeleteIds").val(idsRaw);

    // Submit the form programmatically
    document.getElementById('bulkDeleteForm').dispatchEvent(
        new Event('submit', { bubbles: true, cancelable: true })
    );

}

$(".all-hour-account").change(function (e) {
    var is_checked = $(this).is(":checked");
    var closest = $(this)
        .closest(".oh-sticky-table__thead")
        .siblings(".oh-sticky-table__tbody");
    if (is_checked) {
        $(closest)
            .children()
            .find(".all-hour-account-row")
            .prop("checked", true)
            .closest(".oh-sticky-table__tr")
            .addClass("highlight-selected");
    } else {
        $(closest)
            .children()
            .find(".all-hour-account-row")
            .prop("checked", false)
            .closest(".oh-sticky-table__tr")
            .removeClass("highlight-selected");
    }
});

function tickCheckboxes() {
    var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    uniqueIds = makeListUnique(ids);
    toggleHighlight(uniqueIds);
    click = $("#selectedInstances").attr("data-clicked");
    if (click === "1") {
        $(".all-hour-account").prop("checked", true);
    }

    uniqueIds.forEach(function (id) {
        $("#" + id).prop("checked", true);
    });
    var selectedCount = uniqueIds.length;
    var message = i18nMessages.selected
    if (selectedCount > 0) {
        $("#unselectAllInstances").css("display", "inline-flex");
        $("#exportAccounts").css("display", "inline-flex");
        $("#selectedShow").css("display", "inline-flex");
        $("#selectedShow").text(selectedCount + " -" + message);
    } else {
        $("#unselectAllInstances").css("display", "none");
        $("#exportAccounts").css("display", "none");
        $("#selectedShow").css("display", "none");
    }

}

function tickactivityCheckboxes() {
    var ids = JSON.parse($("#selectedActivity").attr("data-ids") || "[]");
    uniqueIds = makeactivityListUnique(ids);
    toggleHighlight(uniqueIds);
    click = $("#selectedActivity").attr("data-clicked");
    if (click === "1") {
        $(".all-attendance-activity").prop("checked", true);
    }

    uniqueIds.forEach(function (id) {
        $("#" + id).prop("checked", true);
    });
    var selectedCount = uniqueIds.length;

    var message = i18nMessages.selected
    if (selectedCount > 0) {
        $("#unselectAllActivity").css("display", "inline-flex");
        $("#exportActivity").css("display", "inline-flex");
        $("#selectedShowActivity").css("display", "inline-flex");
        $("#selectedShowActivity").text(selectedCount + " -" + message);
    } else {
        $("#unselectAllActivity").css("display", "none");
        $("#exportActivity").css("display", "none");
        $("#selectedShowActivity").css("display", "none");
    }

}

function ticklatecomeCheckboxes() {
    var ids = JSON.parse($("#selectedLatecome").attr("data-ids") || "[]");
    uniqueIds = makelatecomeListUnique(ids);
    toggleHighlight(uniqueIds);
    click = $("#selectedLatecome").attr("data-clicked");
    if (click === "1") {
        $(".all-latecome").prop("checked", true);
    }
    uniqueIds.forEach(function (id) {
        $("#" + id).prop("checked", true);
    });
    var selectedCount = uniqueIds.length;

    var message = i18nMessages.selected
    if (selectedCount > 0) {
        $("#unselectAllLatecome").css("display", "inline-flex");
        $("#exportLatecome").css("display", "inline-flex");
        $("#selectedShowLatecome").css("display", "inline-flex");
        $("#selectedShowLatecome").text(selectedCount + " -" + message);
    } else {
        $("#selectedShowLatecome").css("display", "none");
        $("#exportLatecome").css("display", "none");
        $("#unselectAllLatecome").css("display", "none");
    }

}

function selectAllHourAcconts() {
    $("#unselectAllInstances").show();
    $("#exportAccounts").show();
    $("#selectedShow").show();

    $("#selectedInstances").attr("data-clicked", 1);
    $("#selectedShow").removeAttr("style");
    var savedFilters = JSON.parse(localStorage.getItem("savedFilters"));

    if (savedFilters && savedFilters["filterData"] !== null) {
        var filter = savedFilters["filterData"];

        $.ajax({
            url: "/attendance/hour-attendance-select-filter",
            data: { page: "all", filter: JSON.stringify(filter) },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedInstances").attr("data-ids", JSON.stringify(employeeIds));

                count = makeListUnique(employeeIds);
                tickCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    } else {
        $.ajax({
            url: "/attendance/hour-attendance-select",
            data: { page: "all" },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedInstances").attr("data-ids", JSON.stringify(employeeIds));
                var previousIds = $("#selectedInstances").attr("data-ids");
                $("#selectedInstances").attr(
                    "data-ids",
                    JSON.stringify(
                        Array.from(new Set([...employeeIds, ...JSON.parse(previousIds)]))
                    )
                );

                count = makeListUnique(employeeIds);
                tickCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    }
}

function addingHourAccountsIds() {
    var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    var selectedCount = 0;

    $(".all-hour-account-row").each(function () {
        if ($(this).is(":checked")) {
            ids.push(this.id);
        } else {
            var index = ids.indexOf(this.id);
            if (index > -1) {
                ids.splice(index, 1);
            }
        }
    });

    ids = makeListUnique(ids);
    selectedCount = ids.length;

    var message = i18nMessages.selected
    $("#selectedInstances").attr("data-ids", JSON.stringify(ids));

    if (selectedCount === 0) {
        $("#unselectAllInstances").css("display", "none");
        $("#exportAccounts").css("display", "none");
        $("#selectedShow").css("display", "none");
    } else {
        $("#unselectAllInstances").css("display", "inline-flex");
        $("#exportAccounts").css("display", "inline-flex");
        $("#selectedShow").css("display", "inline-flex");
        $("#selectedShow").text(selectedCount + " - " + message);
    }

}

function unselectAllHourAcconts() {
    $("#selectedInstances").attr("data-clicked", 0);

    $.ajax({
        url: "/attendance/hour-attendance-select",
        data: { page: "all", filter: "{}" },
        type: "GET",
        dataType: "json",
        success: function (response) {
            var employeeIds = response.employee_ids;

            if (Array.isArray(employeeIds)) {
                // Continue
            } else {
                console.error("employee_ids is not an array:", employeeIds);
            }

            for (var i = 0; i < employeeIds.length; i++) {
                var empId = employeeIds[i];
                $("#" + empId).prop("checked", false);
                $("#allHourAccount").prop("checked", false);
            }
            var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
            var uniqueIds = makeListUnique(ids);
            toggleHighlight(uniqueIds);

            $("#selectedInstances").attr("data-ids", JSON.stringify([]));

            count = [];
            $("#unselectAllInstances").hide();
            $("#exportAccounts").hide();
            tickCheckboxes(count);
        },
        error: function (xhr, status, error) {
            console.error("Error:", error);
        },
    });
}

function toggleTableAllRowIds(headerSelector, rowCheckboxClass) {
    $(headerSelector).change(function (e) {
        var is_checked = $(this).is(":checked");
        var closest = $(this)
            .closest(".oh-sticky-table__thead")
            .siblings(".oh-sticky-table__tbody");
        $(closest)
            .children()
            .find(rowCheckboxClass)
            .prop("checked", is_checked)
            .closest(".oh-sticky-table__tr")
            .toggleClass("highlight-selected", is_checked);
    });
}

function toggleTableHeaderCheckbox(rowCheckboxSelector, headerCheckboxSelector) {
    $(document).on("change", rowCheckboxSelector, function () {
        var parentTable = $(this).closest(".oh-sticky-table");
        var body = parentTable.find(".oh-sticky-table__tbody");
        var parentCheckbox = parentTable.find(headerCheckboxSelector);
        var totalRows = body.find(rowCheckboxSelector).length;
        var checkedRows = body.find(`${rowCheckboxSelector}:checked`).length;
        parentCheckbox.prop("checked", totalRows > 0 && totalRows === checkedRows);
    });
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

function addingActivityIds() {
    var ids = JSON.parse($("#selectedActivity").attr("data-ids") || "[]");
    var selectedCount = 0;

    $(".all-attendance-activity-row").each(function () {
        if ($(this).is(":checked")) {
            ids.push(this.id);
        } else {
            var index = ids.indexOf(this.id);
            if (index > -1) {
                ids.splice(index, 1);
            }
        }
    });

    ids = makeactivityListUnique(ids);
    selectedCount = ids.length;

    var message = i18nMessages.selected

    $("#selectedActivity").attr("data-ids", JSON.stringify(ids));

    if (selectedCount === 0) {
        $("#unselectAllActivity").css("display", "none");
        $("#exportActivity").css("display", "none");
        $("#selectedShowActivity").css("display", "none");
    } else {
        $("#unselectAllActivity").css("display", "inline-flex");
        $("#exportActivity").css("display", "inline-flex");
        $("#selectedShowActivity").css("display", "inline-flex");
        $("#selectedShowActivity").text(selectedCount + " - " + message);
    }

}

function addinglatecomeIds() {
    var ids = JSON.parse($("#selectedLatecome").attr("data-ids") || "[]");
    var selectedCount = 0;

    $(".all-latecome-row").each(function () {
        if ($(this).is(":checked")) {
            ids.push(this.id);
        } else {
            var index = ids.indexOf(this.id);
            if (index > -1) {
                ids.splice(index, 1);
            }
        }
    });

    ids = makelatecomeListUnique(ids);
    selectedCount = ids.length;


    var message = i18nMessages.selected

    $("#selectedLatecome").attr("data-ids", JSON.stringify(ids));

    if (selectedCount === 0) {
        $("#selectedShowLatecome").css("display", "none");
        $("#exportLatecome").css("display", "none");
        $("#unselectAllLatecome").css("display", "none");
    } else {
        $("#exportLatecome").css("display", "inline-flex");
        $("#unselectAllLatecome").css("display", "inline-flex");
        $("#selectedShowLatecome").css("display", "inline-flex");
        $("#selectedShowLatecome").text(selectedCount + " - " + message);
    }

}
function selectAllActivity() {
    $("#selectedActivity").attr("data-clicked", 0);
    $("#selectedShowActivity").removeAttr("style");
    var savedFilters = JSON.parse(localStorage.getItem("savedFilters"));

    if (savedFilters && savedFilters["filterData"] !== null) {
        var filter = savedFilters["filterData"];

        $.ajax({
            url: "/attendance/activity-attendance-select-filter",
            data: { page: "all", filter: JSON.stringify(filter) },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedActivity").attr("data-ids", JSON.stringify(employeeIds));

                count = makeactivityListUnique(employeeIds);
                tickactivityCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    } else {

        $("#selectedActivity").attr("data-clicked", 1);

        $.ajax({
            url: "/attendance/activity-attendance-select",
            data: { page: "all" },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                var previousIds = $("#selectedActivity").attr("data-ids");
                $("#selectedActivity").attr(
                    "data-ids",
                    JSON.stringify(
                        Array.from(new Set([...employeeIds, ...JSON.parse(previousIds)]))
                    )
                );

                count = makeactivityListUnique(employeeIds);
                tickactivityCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    }
}

function unselectAllActivity() {
    $("#selectedActivity").attr("data-clicked", 0);
    $.ajax({
        url: "/attendance/activity-attendance-select",
        data: { page: "all", filter: "{}" },
        type: "GET",
        dataType: "json",
        success: function (response) {
            var employeeIds = response.employee_ids;

            if (Array.isArray(employeeIds)) {
                // Continue
            } else {
                console.error("employee_ids is not an array:", employeeIds);
            }

            for (var i = 0; i < employeeIds.length; i++) {
                var empId = employeeIds[i];
                $("#" + empId).prop("checked", false);
                $(".all-attendance-activity").prop("checked", false);
            }
            var ids = JSON.parse($("#selectedActivity").attr("data-ids") || "[]");
            var uniqueIds = makeListUnique(ids);
            toggleHighlight(uniqueIds);
            $("#selectedActivity").attr("data-ids", JSON.stringify([]));

            count = [];
            tickactivityCheckboxes(count);
        },
        error: function (xhr, status, error) {
            console.error("Error:", error);
        },
    });
}

$(".attendance-info-import").click(function (e) {
    e.preventDefault();
    Swal.fire({
        text: i18nMessages.downloadTemplate,
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
                url: "/attendance/attendance-excel",
                dataType: "binary",
                xhrFields: {
                    responseType: "blob",
                },
                success: function (response) {
                    const file = new Blob([response], {
                        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    });
                    const url = URL.createObjectURL(file);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "attendance_excel.xlsx";
                    document.body.appendChild(link);
                    link.click();
                },
                error: function (xhr, textStatus, errorThrown) {
                    console.error("Error downloading file:", errorThrown);
                },
            });
        }
    });
});


function selectAllLatecome() {
    // $("#selectAllLatecome").click(function () {

    $("#selectedLatecome").attr("data-clicked", 0);
    $("#selectedShowLatecome").removeAttr("style");
    var savedFilters = JSON.parse(localStorage.getItem("savedFilters"));

    if (savedFilters && savedFilters["filterData"] !== null) {
        var filter = savedFilters["filterData"];

        $.ajax({
            url: "/attendance/latecome-attendance-select-filter",
            data: { page: "all", filter: JSON.stringify(filter) },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedLatecome").attr("data-ids", JSON.stringify(employeeIds));

                count = makelatecomeListUnique(employeeIds);
                ticklatecomeCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    } else {

        $("#selectedLatecome").attr("data-clicked", 1);

        $.ajax({
            url: "/attendance/latecome-attendance-select",
            data: { page: "all" },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                var previousIds = $("#selectedLatecome").attr("data-ids");
                $("#selectedLatecome").attr(
                    "data-ids",
                    JSON.stringify(
                        Array.from(new Set([...employeeIds, ...JSON.parse(previousIds)]))
                    )
                );

                count = makelatecomeListUnique(employeeIds);
                ticklatecomeCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    }
    // });
}

function unselectAllLatecome() {
    // $("#unselectAllLatecome").click(function () {
    $("#selectedLatecome").attr("data-clicked", 0);

    $.ajax({
        url: "/attendance/latecome-attendance-select",
        data: { page: "all", filter: "{}" },
        type: "GET",
        dataType: "json",
        success: function (response) {
            var employeeIds = response.employee_ids;

            if (Array.isArray(employeeIds)) {
                // Continue
            } else {
                console.error("employee_ids is not an array:", employeeIds);
            }

            for (var i = 0; i < employeeIds.length; i++) {
                var empId = employeeIds[i];
                $("#" + empId).prop("checked", false);
                $(".all-latecome").prop("checked", false);
            }
            var ids = JSON.parse($("#selectedLatecome").attr("data-ids") || "[]");
            var uniqueIds = makeListUnique(ids);
            toggleHighlight(uniqueIds);
            $("#selectedLatecome").attr("data-ids", JSON.stringify([]));

            count = [];
            ticklatecomeCheckboxes(count);
        },
        error: function (xhr, status, error) {
            console.error("Error:", error);
        },
    });
    // });
}

$("#select-all-fields").change(function () {
    const isChecked = $(this).prop("checked");
    $('[name="selected_fields"]').prop("checked", isChecked);
});

$(".all-latecome").change(function (e) {
    var is_checked = $(this).is(":checked");
    var closest = $(this)
        .closest(".oh-sticky-table__thead")
        .siblings(".oh-sticky-table__tbody");
    if (is_checked) {
        $(closest)
            .children()
            .find(".all-latecome-row")
            .prop("checked", true)
            .closest(".oh-sticky-table__tr")
            .addClass("highlight-selected");
    } else {
        $("#selectedLatecome").attr("data-clicked", 0);
        $(closest)
            .children()
            .find(".all-latecome-row")
            .prop("checked", false)
            .closest(".oh-sticky-table__tr")
            .removeClass("highlight-selected");
    }
});

$(".all-attendance-activity").change(function (e) {
    var is_checked = $(this).is(":checked");
    var closest = $(this)
        .closest(".oh-sticky-table__thead")
        .siblings(".oh-sticky-table__tbody");
    if (is_checked) {
        $(closest)
            .children()
            .find(".all-attendance-activity-row")
            .prop("checked", true)
            .closest(".oh-sticky-table__tr")
            .addClass("highlight-selected");
    } else {
        $("#selectedActivity").attr("data-clicked", 0);
        $(closest)
            .children()
            .find(".all-attendance-activity-row")
            .prop("checked", false)
            .closest(".oh-sticky-table__tr")
            .removeClass("highlight-selected");
    }
});

$("#validateAttendances").click(function (e) {
    e.preventDefault();
    var confirmMessage = gettext("Do you really want to validate all the selected attendances?")
    var textMessage = gettext("No rows are selected from Validate Attendances.")
    var checkedRows = $(".validate-row").filter(":checked");
    if (checkedRows.length === 0) {
        Swal.fire({
            text: textMessage,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: confirmMessage,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                checkedRows.each(function () {
                    ids.push($(this).attr("id"));
                });
                $.ajax({
                    type: "POST",
                    url: "/attendance/validate-bulk-attendance/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload();
                        } else {
                        }
                    },
                });
            }
        });
    }

});

$("#approveOt").click(function (e) {
    e.preventDefault();

    var confirmMessage = gettext("Do you really want to approve OT for all the selected attendances?")
    var textMessage = gettext("No rows are selected from OT Attendances.")
    var checkedRows = $(".ot-attendance-row").filter(":checked");
    if (checkedRows.length === 0) {
        Swal.fire({
            text: textMessage,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: confirmMessage,
            icon: "success",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = [];
                checkedRows.each(function () {
                    ids.push($(this).attr("id"));
                });
                $.ajax({
                    type: "POST",
                    url: "/attendance/approve-bulk-overtime/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload();
                        } else {
                        }
                    },
                });
            }
        });
    }

});

// -------------------------------------------Data Export Handlers---------------------------------------------------------------

$("#exportAccounts").click(function (e) {
    var currentDate = new Date().toISOString().slice(0, 10);
    ids = [];
    ids.push($("#selectedInstances").attr("data-ids"));
    ids = JSON.parse($("#selectedInstances").attr("data-ids"));

    Swal.fire({
        text: i18nMessages.downloadExcel,
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
                url: "/attendance/attendance-account-info-export",
                data: {
                    ids: JSON.stringify(ids),
                },
                dataType: "binary",
                xhrFields: {
                    responseType: "blob",
                },
                success: function (response) {
                    const file = new Blob([response], {
                        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    });
                    const url = URL.createObjectURL(file);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "Hour_account" + currentDate + ".xlsx";
                    document.body.appendChild(link);
                    link.click();
                },
                error: function (xhr, textStatus, errorThrown) {
                    console.error("Error downloading file:", errorThrown);
                },
            });
        }
    });
});

$("#exportActivity").click(function (e) {
    var currentDate = new Date().toISOString().slice(0, 10);
    ids = [];
    ids.push($("#selectedActivity").attr("data-ids"));
    ids = JSON.parse($("#selectedActivity").attr("data-ids"));

    Swal.fire({
        text: i18nMessages.downloadExcel,
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
                url: "/attendance/attendance-activity-info-export",
                data: {
                    ids: JSON.stringify(ids),
                },
                dataType: "binary",
                xhrFields: {
                    responseType: "blob",
                },
                success: function (response) {
                    const file = new Blob([response], {
                        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    });
                    const url = URL.createObjectURL(file);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "Attendance_activity" + currentDate + ".xlsx";
                    document.body.appendChild(link);
                    link.click();
                },
                error: function (xhr, textStatus, errorThrown) {
                    console.error("Error downloading file:", errorThrown);
                },
            });
        }
    });
});

$("#exportLatecome").click(function (e) {
    var currentDate = new Date().toISOString().slice(0, 10);

    ids = [];
    ids.push($("#selectedLatecome").attr("data-ids"));
    ids = JSON.parse($("#selectedLatecome").attr("data-ids"));

    Swal.fire({
        text: i18nMessages.downloadExcel,
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
                url: "/attendance/late-come-early-out-info-export",
                data: {
                    ids: JSON.stringify(ids),
                },
                dataType: "binary",
                xhrFields: {
                    responseType: "blob",
                },
                success: function (response) {
                    const file = new Blob([response], {
                        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    });
                    const url = URL.createObjectURL(file);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "Late_come" + currentDate + ".xlsx";
                    document.body.appendChild(link);
                    link.click();
                },
                error: function (xhr, textStatus, errorThrown) {
                    console.error("Error downloading file:", errorThrown);
                },
            });
        }
    });
});

// ------------------------------------------------------------------------------------------------------------------------------

// -------------------------------------------------Data Delete Handlers---------------------------------------------------------

$("#bulkDelete").click(function (e) {
    e.preventDefault();
    var checkedRows = $(".attendance-checkbox").filter(":checked");
    if (checkedRows.length === 0) {
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
                checkedRows.each(function () {
                    ids.push($(this).attr("id"));
                });
                var hxValue = JSON.stringify(ids);
                $("#bulkAttendanceDeleteSpan").attr("hx-vals", `{"ids":${hxValue}}`);
                $("#bulkAttendanceDeleteSpan").click();
            }
        });
    }
});

$("#attendanceAddToBatch").click(function (e) {
    e.preventDefault();
    var checkedRows = $(".attendance-checkbox").filter(":checked");
    if (checkedRows.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        ids = [];
        checkedRows.each(function () {
            ids.push($(this).attr("id"));
        });
        var hxValue = JSON.stringify(ids);
        $("#attendanceAddToBatchButton").attr("hx-vals", `{"ids":${hxValue}}`);
        $("#attendanceAddToBatchButton").click();
    }
});

$("#hourAccountbulkDelete").click(function (e) {
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
                    url: "/attendance/attendance-account-bulk-delete/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload();
                        }
                    },
                });
            }
        });
    }
});

// $("#attendanceActivityDelete").click(function (e) {
//     e.preventDefault();
//
//         var confirmMessage = gettext("Do you really want to delete all the selected attendances?");
//         var textMessage = gettext("No rows are selected for deleting attendances.");
//         ids = [];
//         ids.push($("#selectedActivity").attr("data-ids"));
//         ids = JSON.parse($("#selectedActivity").attr("data-ids"));
//         if (ids.length === 0) {
//             Swal.fire({
//                 text: textMessage,
//                 icon: "warning",
//                 confirmButtonText: i18nMessages.close,
//             });
//         } else {
//             Swal.fire({
//                 text: confirmMessage,
//                 icon: "error",
//                 showCancelButton: true,
//                 confirmButtonColor: "#008000",
//                 cancelButtonColor: "#d33",
//                 confirmButtonText: i18nMessages.confirm,
cancelButtonText: i18nMessages.cancel,
    //             }).then(function (result) {
    //                 if (result.isConfirmed) {
    //                     ids = [];
    //                     ids.push($("#selectedActivity").attr("data-ids"));
    //                     ids = JSON.parse($("#selectedActivity").attr("data-ids"));
    //                     $.ajax({
    //                         type: "POST",
    //                         url: "/attendance/attendance-activity-bulk-delete",
    //                         data: {
    //                             csrfmiddlewaretoken: getCookie("csrftoken"),
    //                             ids: JSON.stringify(ids),
    //                         },
    //                         success: function (response, textStatus, jqXHR) {
    //                             if (jqXHR.status === 200) {
    //                                 location.reload();
    //                             }
    //                         },
    //                     });
    //                 }
    //             });
    //         }
    //
    // });

    $("#lateComeBulkDelete").click(function (e) {
        e.preventDefault();

        ids = [];
        ids.push($("#selectedLatecome").attr("data-ids"));
        ids = JSON.parse($("#selectedLatecome").attr("data-ids"));
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
                    ids.push($("#selectedLatecome").attr("data-ids"));
                    ids = JSON.parse($("#selectedLatecome").attr("data-ids"));
                    $.ajax({
                        type: "POST",
                        url: "/attendance/late-come-early-out-bulk-delete/",
                        data: {
                            csrfmiddlewaretoken: getCookie("csrftoken"),
                            ids: JSON.stringify(ids),
                        },
                        success: function (response, textStatus, jqXHR) {
                            if (jqXHR.status === 200) {
                                location.reload();
                            }
                        },
                    });
                }
            });
        }
    });


// attendance requests select all functions

function requestedAttendanceTickCheckboxes() {
    var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    uniqueIds = makeListUnique(ids);
    toggleHighlight(uniqueIds);
    click = $("#selectedInstances").attr("data-clicked");
    if (click === "1") {
        $(".requested-attendances-select-all").prop("checked", true);
    }
    uniqueIds.forEach(function (id) {
        $("#" + id).prop("checked", true);
    });

    var selectedCount = uniqueIds.length;

    var message = i18nMessages.selected
    if (selectedCount > 0) {
        $("#unselectAllInstances").css("display", "inline-flex");
        $("#selectedShow").css("display", "inline-flex");
        $("#selectedShow").text(selectedCount + " -" + message);
    } else {
        $("#selectedShow").css("display", "none");
    }

}

function dictToQueryString(dict) {
    const queryString = Object.keys(dict).map(key => {
        const value = dict[key];
        if (Array.isArray(value)) {
            return value.map(val => `${encodeURIComponent(key)}=${encodeURIComponent(val)}`).join('&');
        } else {
            return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
        }
    }).join('&');
    return queryString;
}


function selectAllReqAttendance() {
    $("#unselectAllInstances").show();
    $("#selectedShow").show();

    $("#selectedInstances").attr("data-clicked", 1);
    $("#selectedShow").removeAttr("style");
    var savedFilters = JSON.parse(localStorage.getItem("savedFilters"));

    if (savedFilters && savedFilters["filterData"] !== null) {
        var filter = savedFilters["filterData"];
        // Convert the dictionary to a query string
        var queryString = dictToQueryString(filter);
        $.ajax({
            url: `/attendance/select-all-filter-attendance-request?${queryString}`,
            data: { page: "all", filter: JSON.stringify(filter) },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedInstances").attr("data-ids", JSON.stringify(employeeIds));

                count = makeListUnique(employeeIds);

                requestedAttendanceTickCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    } else {
        $.ajax({
            url: "/attendance/select-all-filter-attendance-request",
            data: { page: "all" },
            type: "GET",
            dataType: "json",
            success: function (response) {
                var employeeIds = response.employee_ids;

                if (Array.isArray(employeeIds)) {
                    // Continue
                } else {
                    console.error("employee_ids is not an array:", employeeIds);
                }

                var selectedCount = employeeIds.length;

                for (var i = 0; i < employeeIds.length; i++) {
                    var empId = employeeIds[i];
                    $("#" + empId).prop("checked", true);
                }
                $("#selectedInstances").attr("data-ids", JSON.stringify(employeeIds));
                var previousIds = $("#selectedInstances").attr("data-ids");
                $("#selectedInstances").attr(
                    "data-ids",
                    JSON.stringify(
                        Array.from(new Set([...employeeIds, ...JSON.parse(previousIds)]))
                    )
                );

                count = makeListUnique(employeeIds);
                requestedAttendanceTickCheckboxes(count);
            },
            error: function (xhr, status, error) {
                console.error("Error:", error);
            },
        });
    }
}

function unselectAllReqAttendance() {
    $("#selectedInstances").attr("data-clicked", 0);

    $.ajax({
        url: "/attendance/select-all-filter-attendance-request",
        data: { page: "all", filter: "{}" },
        type: "GET",
        dataType: "json",
        success: function (response) {
            var employeeIds = response.employee_ids;

            if (Array.isArray(employeeIds)) {
                // Continue
            } else {
                console.error("employee_ids is not an array:", employeeIds);
            }

            for (var i = 0; i < employeeIds.length; i++) {
                var empId = employeeIds[i];
                $("#" + empId).prop("checked", false);
                $(".requested-attendances-select-all").prop("checked", false);
            }
            var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
            var uniqueIds = makeListUnique(ids);
            toggleHighlight(uniqueIds);

            $("#selectedInstances").attr("data-ids", JSON.stringify([]));

            count = [];
            $("#unselectAllInstances").hide();
            requestedAttendanceTickCheckboxes(count);
        },
        error: function (xhr, status, error) {
            console.error("Error:", error);
        },
    });
}


$("#reqAttendanceBulkApprove").click(function (e) {
    e.preventDefault();

    var checkedRows = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    if (checkedRows.length === 0) {
        Swal.fire({
            text: i18nMessages.noRowsSelected,
            icon: "warning",
            confirmButtonText: i18nMessages.close,
        });
    } else {
        Swal.fire({
            text: i18nMessages.confirmBulkApprove,
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
                $.ajax({
                    type: "POST",
                    url: "/attendance/bulk-approve-attendance-request/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload();
                        }
                    },
                });
            }
        });
    }
});

$("#reqAttendanceBulkReject").click(function (e) {
    e.preventDefault();
    var checkedRows = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    if (checkedRows.length === 0) {
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
                ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
                $.ajax({
                    type: "POST",
                    url: "/attendance/bulk-reject-attendance-request/",
                    data: {
                        csrfmiddlewaretoken: getCookie("csrftoken"),
                        ids: JSON.stringify(ids),
                    },
                    success: function (response, textStatus, jqXHR) {
                        if (jqXHR.status === 200) {
                            location.reload();
                        }
                    },
                });
            }
        });
    }
});


function addingRequestAttendanceIds() {
    var ids = JSON.parse($("#selectedInstances").attr("data-ids") || "[]");
    var selectedCount = 0;
    $(".requested-attendance-row").each(function () {
        if ($(this).is(":checked")) {
            ids.push(this.id);
        } else {
            var index = ids.indexOf(this.id);
            if (index > -1) {
                ids.splice(index, 1);
            }
        }
    });

    ids = makeListUnique(ids);

    selectedCount = ids.length;

    var message = i18nMessages.selected
    $("#selectedInstances").attr("data-ids", JSON.stringify(ids));
    if (selectedCount === 0) {
        $("#unselectAllInstances").css("display", "none");
        $("#selectedShow").css("display", "none");
    } else {
        $("#unselectAllInstances").css("display", "inline-flex");
        $("#selectedShow").css("display", "inline-flex");
        $("#selectedShow").text(selectedCount + " - " + message);
    }

}

$(".requested-attendances-select-all").click(function (e) {
    var is_checked = $(this).is(":checked");
    var closest = $(this)
        .closest(".oh-sticky-table__thead")
        .siblings(".oh-sticky-table__tbody");
    if (is_checked) {
        $(closest)
            .children()
            .find(".requested-attendance-row")
            .prop("checked", true)
            .closest(".oh-sticky-table__tr")
            .addClass("highlight-selected");
    } else {
        $(closest)
            .children()
            .find(".requested-attendance-row")
            .prop("checked", false)
            .closest(".oh-sticky-table__tr")
            .removeClass("highlight-selected");
    }
    addingRequestAttendanceIds()
});
function checkReqAttentanceSelectAll() {
    var parentTable = $(this).closest(".oh-sticky-table");
    var body = parentTable.find(".oh-sticky-table__tbody");
    var parentCheckbox = parentTable.find(".requested-attendances-select-all");
    parentCheckbox.prop(
        "checked",
        body.find(".requested-attendance-row:checked").length ===
        body.find(".requested-attendance-row").length
    );
}
$(".requested-attendance-row").change(function () {
    var parentTable = $(this).closest(".oh-sticky-table");
    var body = parentTable.find(".oh-sticky-table__tbody");
    var parentCheckbox = parentTable.find(".requested-attendances-select-all");
    parentCheckbox.prop(
        "checked",
        body.find(".requested-attendance-row:checked").length ===
        body.find(".requested-attendance-row").length
    );
    $("#selectedInstances").attr("data-clicked", 0);
    addingRequestAttendanceIds();

});


// ------------------------------------------------------------------------------------------------------------------------------

// ******************************************************************
// *     THIS IS FOR SWITCHING THE DATE FORMAT IN THE ALL VIEWS     *
// ******************************************************************

// Iterate through all elements with the 'dateformat_changer' class and format their content

if (window.CURRENT_LANGUAGE != 'de') {

    $(".dateformat_changer").each(function (index, element) {
        // Some list tables (e.g. the Requested Attendances tab) wrap the cell's
        // text in a ".truncate" div so long dates ellipsize instead of wrapping
        // across lines. $(element).text(...) below replaces the WHOLE element's
        // contents, so writing straight to the ".dateformat_changer" cell itself
        // would delete that wrapper along with its truncation styling -- update
        // the wrapper's own text instead when one exists, and fall back to the
        // element itself everywhere else (plain, unwrapped usages).
        var $target = $(element).find(".truncate").first();
        if (!$target.length) $target = $(element);
        var currentDate = $target.text().trim();
        // Checking currentDate value is a date or None value.
        if (/[\.,\-\/]/.test(currentDate)) {
            var formattedDate = dateFormatter.getFormattedDate(currentDate);

        } else if (currentDate) {
            var formattedDate = currentDate;
        } else {
            var formattedDate = "None";
        }

        $target.text(formattedDate);

    });
}

for_mat = dateFormatter.dateFormat

if (window.CURRENT_LANGUAGE === 'de') {

    if (["DD-MM-YYYY", "DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "YYYY/MM/DD", "MMM. D, YYYY", "D MMM. YYYY"].includes(for_mat)) {

        $(".dateformat_changer").each(function (index, element) {
            var $target = $(element).find(".truncate").first();
            if (!$target.length) $target = $(element);
            var currentDate = $target.text().trim();
            let eng_date = '';  // Initialize eng_date at the start of each iteration

            // Check if currentDate is empty or equals "None"
            if (!currentDate || currentDate.toLowerCase() === "none") {
                eng_date = 'None';  // Reset the eng_date to 'None' if it's invalid
                $target.text(eng_date);  // Set to 'None' in the DOM
                return;
            }
            // Create a mapping of month names from different languages to English
            const monthMap = {
                "Januar": "January", "Februar": "February", "März": "March", "Mai": "May",
                "April": "April", "Juni": "June", "Juli": "July", "August": "August",
                "September": "September", "Oktober": "October", "November": "November", "Dezember": "December",
            };
            // Split the date string into day, month, and year
            let [day, month, year] = currentDate.split(' ');
            // Convert the month to English
            month = monthMap[month] || month;  // If no mapping is found, use the original month
            // Create a new date object
            let date = new Date(`${month} ${day}, ${year}`);

            // Check if the date is valid
            if (isNaN(date.getTime())) {
                $target.text(currentDate);  // Set to 'Invalid Date' in the DOM
                return;
            }
            // Format the date in English using Intl.DateTimeFormat
            eng_date = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
            // Apply the formatted date
            if (/[\.,\-\/]/.test(currentDate)) {
                var formattedDate = dateFormatter.getFormattedDate(eng_date);
            } else if (currentDate) {
                var formattedDate = eng_date;  // Use the formatted English date
            } else {
                var formattedDate = "None";
            }
            if (["MMM. D, YYYY", "D MMM. YYYY"].includes(for_mat)) {
                formattedDate = formattedDate.replace(/Mar. /g, ' Mär. ');
                formattedDate = formattedDate.replace(/May. /g, ' Mai. ');
                formattedDate = formattedDate.replace(/Oct. /g, ' Okt. ');
                formattedDate = formattedDate.replace(/Dec. /g, ' Dez. ');
            }
            $target.text(formattedDate);  // Set the formatted date in the DOM
        });
    }
    else {
        $(".dateformat_changer").each(function (index, element) {
            var $target = $(element).find(".truncate").first();
            if (!$target.length) $target = $(element);
            var currentDate = $target.text().trim();
            if (["MMMM D, YYYY", "DD MMMM, YYYY"].includes(for_mat) & window.CURRENT_LANGUAGE === 'de') {
                if (isNaN(currentDate)) {
                    $target.text(currentDate);
                    return;
                }
            }
            // Apply the formatted date
            if (/[\.,\-\/]/.test(currentDate)) {
                var formattedDate = dateFormatter.getFormattedDate(currentDate);
            } else if (currentDate) {
                var formattedDate = currentDate;  // Use the formatted English date
            } else {
                var formattedDate = "None";
            }
            $target.text(formattedDate);  // Set the formatted date in the DOM
        });
    }
}

// Display the formatted date wherever needed
var currentDate = $(".dateformat_changer").first().text();
var formattedDate = dateFormatter.getFormattedDate(currentDate);

// ******************************************************************
// *     THIS IS FOR SWITCHING THE TIME FORMAT IN THE ALL VIEWS     *
// ******************************************************************

// Iterate through all elements with the 'timeformat_changer' class and format their content
$(".timeformat_changer").each(function (index, element) {
    var $target = $(element).find(".truncate").first();
    if (!$target.length) $target = $(element);
    var currentTime = $target.text().trim();

    if (currentTime === 'midnight') {
        if (timeFormatter.timeFormat === 'hh:mm A') {
            formattedTime = '12:00 AM'
        } else {
            formattedTime = '00:00'
        }
    }
    else if (currentTime === 'noon') {
        if (timeFormatter.timeFormat === 'hh:mm A') {
            formattedTime = '12:00 PM'
        } else {
            formattedTime = '12:00'
        }
    }
    // Checking currentTime value is a valid time.
    else if (/[\.:]/.test(currentTime)) {
        var formattedTime = timeFormatter.getFormattedTime(currentTime);
    } else if (currentTime) {
        var formattedTime = currentTime;
    } else {
        var formattedTime = "None";
    }
    $target.text(formattedTime);
});

// Display the formatted time wherever needed
var currentTime = $(".timeformat_changer").first().text();
var formattedTime = timeFormatter.getFormattedTime(currentTime);
