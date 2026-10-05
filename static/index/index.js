if (typeof i18nMessages === 'undefined') {
    var i18nMessages = {
        // General dialog buttons
        confirm: gettext("Confirm"),
        close: gettext("Close"),
        cancel: gettext("Cancel"),
        selected: gettext("Selected"),
        uploading: gettext("Uploading..."),
        emptyMessages: gettext("No Records found"),
        ok: gettext("Ok"),
        downloadExcel: gettext("Do you want to download the excel file?"),
        downloadTemplate: gettext("Do you want to download the template?"),
        noRowsSelected: gettext("No rows are selected from the records."),
        confirmBulkDelete: gettext("Do you really want to delete all the selected records?"),
        confirmBulkArchive: gettext("Do you really want to archive all the selected records?"),
        confirmBulkReject: gettext("Do you really want to approve all the selected requests?"),
        confirmBulkApprove: gettext("Do you really want to approve all the selected requests?"),
        confirmBulkUnArchive: gettext("Do you really want to unarchive all the selected records?"),
        confirmBulkResetPassword: gettext("Do you really want to reset the password for all selected employees? Their current password will stop working immediately."),
        confirmBulkInvite: gettext("Do you really want to send an invitation email to all selected employees?"),
        totalVacancy: gettext("Total vacancy is %(vacancy)s."),
        candidateStageChange: gettext(
            "Are you sure to change the candidate from %(from)s stage to %(to)s stage"
        ),
        retry: gettext("Retry"),
        loadFailed: gettext("Something went wrong while loading this data."),
        loadFailedStatus: gettext("Request failed (status %(status)s)."),
        loadTimeout: gettext("The request took too long to respond."),
    }
}

// Blanket safety net for every htmx request on the page, including
// programmatic htmx.ajax() calls (e.g. HorillaTabView's tab-content loads)
// that don't set their own hx-timeout. htmx's own default (0) never times
// out a hung request, so without this a stalled server response leaves
// the swap target empty indefinitely with no error ever surfacing.
if (typeof htmx !== "undefined" && !htmx.config.timeout) {
    htmx.config.timeout = 15000;
}

var confirmModal = {
    ar: "تأكيد",
    de: "Bestätigen",
    es: "Confirmar",
    en: "Confirm",
    fr: "Confirmer",
};

var cancelModal = {
    ar: "إلغاء",
    de: "Abbrechen",
    es: "Cancelar",
    en: "Cancel",
    fr: "Annuler",
};

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }
    return cookieValue;
}

function handleSidebarToggle() {
    // Delay the execution slightly to allow existing toggle logic to finish
    setTimeout(() => {
        const isOpen = !$('.oh-wrapper-main').hasClass('oh-wrapper-main--closed');
        localStorage.setItem('sidebarOpen', isOpen);
    }, 50);
}

function ensureSelectionStore(storeKey) {
    if (!storeKey) storeKey = "selectedInstances";
    var $store = $(`#${storeKey}`);
    if (!$store.length) {
        $("body").append(
            `<div id="${storeKey}" class="oh-checkpoint-badge mb-2" data-ids="[]" data-clicked="" style="display:none"></div>`
        );
        $store = $(`#${storeKey}`);
    }
    return $store;
}

function addToSelectedId(newIds, storeKey) {
    storeKey = storeKey || "selectedInstances";
    var $store = ensureSelectionStore(storeKey);
    if (!Array.isArray(newIds)) {
        try {
            newIds = JSON.parse(newIds || "[]");
        } catch (e) {
            newIds = [];
        }
    }
    ids = JSON.parse($store.attr("data-ids") || "[]").map(String);

    ids = [...ids, ...newIds.map(String)];
    ids = Array.from(new Set(ids));
    $store.attr("data-ids", JSON.stringify(ids));
    setStoredSelection(storeKey, ids);
}

/**
 * Select-all helper used by list toolbars. Prefer data-select-ids on the
 * button so huge id lists are not inlined as fragile onclick JS.
 */
function hlvSelectAllRecords(btn, viewSelector, storeKey) {
    storeKey = storeKey || "selectedInstances";
    var ids = [];
    try {
        ids = JSON.parse($(btn).attr("data-select-ids") || "[]");
    } catch (e) {
        ids = [];
    }
    addToSelectedId(ids, storeKey);
    selectSelected(viewSelector, storeKey);
    var viewId = (viewSelector || "").replace(/^#/, "");
    reloadSelectedCount($(`#count_${viewId}`), storeKey);
    reloadSelectedCount($(`.count_${viewId}`), storeKey);
    // Nested accordion panels lock max-height after the first load — grow
    // them so Unselect / Export chrome that appears after Select stays visible.
    var $panel = $(viewSelector).closest(".accordion-panel");
    if ($panel.length && $panel[0].style.maxHeight) {
        $panel[0].style.maxHeight = $panel[0].scrollHeight + "px";
    }
}

/**
 * Inverse of hlvSelectAllRecords: drop a specific set of ids (e.g. every
 * record in one group) out of the shared selection, not the whole store.
 * Selected ids can span pages/groups the DOM never rendered, so this can't
 * rely solely on unchecking on-page checkboxes -- it patches data-ids
 * directly first, then syncs whichever of those rows do happen to be
 * on-page (via a real checkbox uncheck + change event, so highlightRow and
 * every other change-bound handler still runs normally).
 */
function hlvUnselectRecords(btn, viewSelector, storeKey) {
    storeKey = storeKey || "selectedInstances";
    var idsToRemove = [];
    try {
        idsToRemove = JSON.parse($(btn).attr("data-select-ids") || "[]").map(String);
    } catch (e) {
        idsToRemove = [];
    }
    var removeSet = new Set(idsToRemove);

    var $store = ensureSelectionStore(storeKey);
    var ids = JSON.parse($store.attr("data-ids") || "[]")
        .map(String)
        .filter(function (id) { return !removeSet.has(id); });
    $store.attr("data-ids", JSON.stringify(ids));
    setStoredSelection(storeKey, ids);

    var $scope = $(viewSelector).filter(".hlv-container");
    if (!$scope.length) $scope = $(viewSelector).first();
    $scope.find(".list-table-row").each(function () {
        if (removeSet.has(String($(this).val())) && $(this).is(":checked")) {
            $(this).prop("checked", false).trigger("change");
        }
    });

    var viewId = (viewSelector || "").replace(/^#/, "");
    reloadSelectedCount($(`#count_${viewId}`), storeKey);
    reloadSelectedCount($(`.count_${viewId}`), storeKey);
}

// Used by the "Unselect"/"Unselect All Records" actions so the clear is
// persisted synchronously - the MutationObserver mirror below is async
// (fires on the next microtask), which left a window where hitting reload
// right after clicking Unselect could race ahead of the localStorage write
// and bring the old selection back.
function clearSelection(storeKey) {
    ensureSelectionStore(storeKey).attr("data-ids", "[]");
    setStoredSelection(storeKey, []);
}

/**
 * Clear list-row selections when switching Horilla tabs. Lists may use a
 * custom store (#selectedTickets, etc.) instead of #selectedInstances — the
 * generic tab onclick used to only clear selectedInstances, so selections
 * from one tab (e.g. My Tickets) leaked into another (Suggested Tickets).
 */
function clearSelectionsOnTabSwitch(viewRootId) {
    var keys = { selectedInstances: true };
    if (document.getElementById("selectedTickets")) {
        keys.selectedTickets = true;
    }
    var $root = viewRootId ? $(`#${viewRootId}`) : $(document);
    $root.find("[data-selected-instances-key]").each(function () {
        var key = $(this).attr("data-selected-instances-key");
        if (key) keys[key] = true;
    });
    Object.keys(keys).forEach(function (key) {
        clearSelection(key);
    });
    $root.find(".list-table-row, .bulk-list-table-row").prop("checked", false);
    $root.find(".highlight-selected").removeClass("highlight-selected");
    $root.find('[id^="unselect_"], [id^="bulk_udate_"], .hlv-export-trigger').addClass("d-none");
    $root.find('[id^="select_"]').removeClass("d-none");
    $root.find('[id^="count_"]').text("0");
    $root.find('[class*="count_"]').filter(function () {
        return /(?:^|\s)count_/.test(this.className);
    }).text("0");
}

// Row-selection checkboxes only ever lived in a DOM attribute, so a browser
// reload silently wiped out whatever the user had selected. Mirroring the
// attribute into localStorage (scoped per page + storeKey, since the same
// storeKey id like "selectedInstances" is reused across many unrelated list
// views) lets us restore it right after the page comes back.
function getSelectionStorageKey(storeKey) {
    return `hlv_selection:${window.location.pathname}:${storeKey}`;
}

function getStoredSelection(storeKey) {
    try {
        return JSON.parse(localStorage.getItem(getSelectionStorageKey(storeKey)) || "[]");
    } catch (e) {
        return [];
    }
}

function setStoredSelection(storeKey, ids) {
    try {
        localStorage.setItem(getSelectionStorageKey(storeKey), JSON.stringify(ids || []));
    } catch (e) {
        // localStorage unavailable (private browsing quota, etc.) - selection
        // simply won't survive a reload, same as before this change.
    }
}

// selectSelected() runs on every htmx reload, not just a fresh page load
// (e.g. it also runs right after the "Unselect" button intentionally clears
// data-ids). Only attempt the one-time restore-from-storage the first time
// each storeKey is seen this page load, so a deliberate clear doesn't get
// immediately undone by the very next selectSelected() call.
var _hlvSelectionRestored = {};

$(document).ready(function () {
    // Selection ids are written to the DOM in several places (inline template
    // onclick handlers, addToSelectedId, the checkbox .change() handler below) -
    // rather than hook every call site, watch the attribute itself so every path
    // stays mirrored into localStorage.
    var selectionObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            var el = mutation.target;
            if (el.id) {
                setStoredSelection(el.id, JSON.parse(el.getAttribute("data-ids") || "[]"));
            }
        });
    });
    selectionObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-ids"],
        subtree: true,
    });

    // Clear modal target contents when closed to prevent duplicate DOM IDs
    var modalObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            if (mutation.attributeName === "class") {
                var el = mutation.target;
                // If the modal was just closed (lost oh-modal--show class)
                if (!$(el).hasClass("oh-modal--show")) {
                    var clearableModals = [
                        "objectCreateModal",
                        "objectUpdateModal",
                        "dynamicCreateModal",
                        "objectDetailsModal",
                        "objectDetailsModalW25",
                        "genericModal"
                    ];
                    if (clearableModals.includes(el.id)) {
                        setTimeout(function() {
                            if (!$(el).hasClass("oh-modal--show")) {
                                $(el).find(".oh-modal__dialog").empty();
                            }
                        }, 200); // 200ms delay to allow any close transitions to finish
                    }
                }
            }
        });
    });

    $(".oh-modal").each(function () {
        modalObserver.observe(this, { attributes: true });
    });
});

// Row-title collapse toggle (the little count-span/oh-permission-table--collapsed
// expander used by, e.g., recruitment/cbv/stages/title.html). This used to be
// registered inline via a <script> tag repeated on every single row - besides
// re-binding the same document-level handler hundreds of times per page, that
// row HTML is reused elsewhere to build each row's hover tooltip (title="...",
// stripped through the `striptags` filter), and `striptags` only removes the
// <script>/</script> tags themselves, not their contents - so the JS source
// leaked into the tooltip text. Registering it once here, globally, fixes both.
$(document).on("htmx:afterSwap", function () {
    $("[data-toggle-count]")
        .off("click")
        .on("click", function (e) {
            e.stopPropagation();
            var recViewContainer = $(this).closest("tr");
            recViewContainer.find(".count-span").toggle();
            recViewContainer.toggleClass("oh-permission-table--collapsed");
        });
});

function togglePublicComments() {
    if ($('#id_disable_comments').is(':checked')) {
        $('#id_public_comments').prop('checked', false);
        $('#id_public_comments_parent_div').hide();
    } else {
        $('#id_public_comments_parent_div').show();
    }
}

function attendanceDateChange(selectElement) {
    var selectedDate = selectElement.val();
    let parentForm = selectElement.parents().closest("form");
    var shiftId = parentForm.find("[name=shift_id]").val();

    $.ajax({
        type: "post",
        url: "/attendance/update-date-details/",
        data: {
            csrfmiddlewaretoken: getCookie("csrftoken"),
            attendance_date: selectedDate,
            shift_id: shiftId,
        },
        success: function (response) {
            parentForm.find("[name=minimum_hour]").val(response.minimum_hour);
        },
    });
}

function getAssignedLeave(employeeElement) {
    var employeeId = employeeElement.val();
    $.ajax({
        type: "get",
        url: "/payroll/get-assigned-leaves",
        data: { employeeId: employeeId },
        dataType: "json",
        success: function (response) {
            let rows = "";
            for (let index = 0; index < response.length; index++) {
                const element = response[index];
                rows =
                    rows +
                    `<tr class="toggle-highlight">
                        <td class="text-sm p-3 text-[#666] rounded-lg">${element.leave_type_id__name}</td>
                        <td class="text-sm p-3 text-[#666] rounded-lg">${element.available_days}</td>
                        <td class="text-sm p-3 text-[#666] rounded-lg">${element.carryforward_days}</td>
                    </tr>`;
            }
            $("#availableTableBody").html($(rows));
            let newLeaves = "";
            for (let index = 0; index < response.length; index++) {
                const leave = response[index];
                newLeaves =
                    newLeaves +
                    `<option value="${leave.leave_type_id__id}">${leave.leave_type_id__name}</option>`;
            }
            $("#id_leave_type_id").html(newLeaves);
            removeHighlight();
        },
    });
}
// Keeps the header "select all" checkbox (.bulk-list-table-row) in sync with
// the individual row checkboxes (.list-table-row) for the given table/view.
// Used everywhere the "Select"/"Select All" quick action and per-row
// checkboxes exist, so this fixes the header checkbox not reflecting bulk
// selection across every module's list view, not just one page.
function syncBulkSelectAllCheckbox(viewId) {
    if (!viewId) return;
    // A view can contain multiple grouped tables (one .fixed-table per group),
    // each with its own "select all" checkbox — sync each table independently
    // instead of treating every group's rows as one combined set, otherwise a
    // fully-selected group gets marked indeterminate just because some other
    // group in the same view has a partial selection.
    $(`${viewId} .fixed-table, ${viewId} .oh-sticky-table`).each(function () {
        var $table = $(this);
        var rows = $table.find(".list-table-row");
        var bulkCheckbox = $table.find(".bulk-list-table-row");
        if (!rows.length || !bulkCheckbox.length) return;
        var checkedCount = rows.filter(":checked").length;
        bulkCheckbox.prop("checked", checkedCount > 0 && checkedCount === rows.length);
        bulkCheckbox.prop(
            "indeterminate",
            checkedCount > 0 && checkedCount < rows.length
        );
    });
}

// Toggling a column's visibility checkbox in the "..." column-picker dropdown
// used to always trigger a full reload of the entire list view (every group,
// every row) just to hide/show one column — slow, and it closed the dropdown
// since the reload replaces its DOM node (Alpine's open state resets).
// The preference is still persisted server-side via the existing hx-get
// (unchanged), but the visual change now applies instantly client-side, and
// the reload that follows is skipped (see window.__skipNextToggleReload,
// checked in horilla_list_table.html / group_by_table.html's
// hx-on::after-request). Column *reordering* (drag-and-drop) still reloads
// normally, since re-ordering actual table cells isn't a simple show/hide.
function toggleColumnVisibility(checkboxEl, fieldName, visible) {
    // Scope to this list only. HorillaTabView keeps visited tabs in the DOM,
    // so a global th[id$=...] lookup can match History (or any column) from
    // another tab and wrongly skip the reload this list needs.
    // Group-by tables also use .hlv-container; fall back to [data-list-path]
    // for any list markup that only has the path attribute.
    var $container = $(checkboxEl).closest(".hlv-container, [data-list-path]");
    var $th = $container.find(`th[id$="-${fieldName}-header"]`);
    if (!$th.length) {
        // This column was never rendered server-side in the first place —
        // it wasn't part of the page's current visible-column set, so
        // there's no existing <th>/<td> to un-hide client-side. Turning it
        // ON needs a real reload once the toggle is actually persisted (see
        // persistColumnToggle below); turning an already-absent column OFF
        // is a no-op either way.
        if (visible) {
            window.__hlvNeedsColumnReload =
                $container.attr("data-list-path") ||
                $container.closest("[data-list-path]").attr("data-list-path");
        }
        return;
    }
    $th.each(function () {
        var $header = $(this);
        var $table = $header.closest("table");
        var index = $header.parent().children("th").index($header);
        $header.toggleClass("d-none", !visible);
        $table.find("tbody tr").each(function () {
            $(this).children("td").eq(index).toggleClass("d-none", !visible);
        });
    });
    window.__skipNextToggleReload = true;
}

function toggleAllColumnsVisibility(formEl, visible) {
    // Scoped to .toggle-column-checkbox, not every checkbox in the form -
    // the "Select All" master checkbox itself is also an
    // input[type="checkbox"] in this same form but has no id to derive a
    // field name from, so including it here threw on `.attr("id").replace(...)`
    // and aborted the loop before any real column got toggled.
    // Skip the disabled primary column — it must stay visible.
    $(formEl)
        .find(".toggle-column-checkbox:not(:disabled)")
        .each(function () {
            toggleColumnVisibility(this, $(this).attr("id").replace("toggle_", ""), visible);
        });
}

// Persists the column show/hide preference in the background via a plain
// AJAX GET instead of submitting the htmx-enabled form. Clicking the form's
// real submit button (as column *reordering* still does) fires
// htmx:afterRequest, which bubbles up to the dropdown's hx-on::after-request
// and reloads/recreates the whole list (closing the dropdown, since Alpine's
// open state resets on the new DOM node). That reload is only meant to be
// skipped via window.__skipNextToggleReload, but the flag has to survive an
// async round trip shared with other unrelated htmx requests (e.g. the flash
// message refresher), which made it unreliable in practice. A plain AJAX call
// never fires any htmx event on the form, so the dropdown is never touched.
function persistColumnToggle(formEl) {
    var $form = $(formEl);
    $.get($form.attr("hx-get"), $form.find(":input").serialize()).done(function () {
        // Only reload once the newly-shown column's toggle is confirmed
        // saved — reloading any earlier would race the save and could
        // fetch the table before the server sees the updated preference.
        if (window.__hlvNeedsColumnReload) {
            var path = window.__hlvNeedsColumnReload;
            window.__hlvNeedsColumnReload = null;
            window.__hlvReopenDropdown = path;
            var $list = $(`.hlv-container[data-list-path="${path}"]`);
            if (!$list.length) {
                $list = $(`[data-list-path="${path}"]`);
            }
            $list.find(".reload-record").first().click();
        }
    });
}

function selectSelected(viewId, storeKey = "selectedInstances") {
    var $store = ensureSelectionStore(storeKey);
    if (!_hlvSelectionRestored[storeKey]) {
        _hlvSelectionRestored[storeKey] = true;
        if (!JSON.parse($store.attr("data-ids") || "[]").length) {
            var stored = getStoredSelection(storeKey);
            if (stored.length) {
                $store.attr("data-ids", JSON.stringify(stored));
            }
        }
    }

    // Selected ids can span every page of a filtered list (thousands, on a
    // large table), but only the current page's rows exist in the DOM. Loop
    // over the (small, bounded) set of on-page checkboxes and look each one
    // up in a Set - not the other way around, which re-queried the DOM twice
    // per selected id and made "Select All" scale with total selection size
    // instead of rows-per-page.
    // Prefer the .hlv-container node when view_id is duplicated (e.g. export
    // modal wrappers reused the same id historically).
    var $scope = $(viewId).filter(".hlv-container");
    if (!$scope.length) {
        $scope = $(viewId).has(".list-table-row");
    }
    if (!$scope.length) {
        $scope = $(viewId).first();
    }
    ids = JSON.parse($store.attr("data-ids") || "[]");
    var _hlvIdSet = new Set(ids.map(String));
    var $hlvRows = $scope.find(
        `.oh-sticky-table__tbody .list-table-row, tbody .list-table-row`
    );
    $hlvRows.each(function () {
        if (_hlvIdSet.has(String($(this).val()))) {
            $(this).prop("checked", true).change();
        }
    });

    // Reflect the row selection on the header "select all" checkbox: checked
    // when every row on this page is selected, otherwise unchecked (or
    // indeterminate when some, but not all, rows are selected).
    syncBulkSelectAllCheckbox(viewId);

    // Namespaced + re-bound (not stacked): selectSelected runs on every
    // select-all/unselect/page-load, and a plain .change(fn) here would
    // attach one more duplicate handler each time without ever removing the
    // old ones, so every row toggle re-ran all of them - the exact cause of
    // "Select All" getting slower the more it's used in a session.
    $hlvRows.off("change.hlvSelectSync").on("change.hlvSelectSync", function (e) {
        id = String($(this).val());
        ids = JSON.parse(
            ensureSelectionStore(storeKey).attr("data-ids") || "[]"
        ).map(String);

        // Convert to Set to ensure uniqueness, then back to array
        ids = Array.from(new Set(ids));

        if ($(this).is(":checked")) {
            // Checkbox is checked - add if not already present
            if (!ids.includes(id)) {
                ids.push(id);
            }
        } else {
            // Checkbox is unchecked - remove if present
            let index = ids.indexOf(id);
            if (index !== -1) {
                ids.splice(index, 1);
            }
        }

        // Update the data attribute with the modified array
        ensureSelectionStore(storeKey).attr("data-ids", JSON.stringify(ids));
        setStoredSelection(storeKey, ids);

        // Update count and show/hide buttons after every change. A grouped
        // view (group_by_table.html) renders one quick_actions.html copy per
        // group, each with its own count_<gvid> elements - not just one for
        // the outer viewId - so every one of them needs updating, or a
        // group's Unselect/Export/Update buttons never reflect a change made
        // via a row checkbox (only the group's own "Select" button, whose
        // onclick targets its own gvid directly, updated correctly).
        $scope.find('[id^="count_"]').each(function () {
            reloadSelectedCount($(this), storeKey);
        });
        $scope.find('[class*="count_"]').each(function () {
            reloadSelectedCount($(this), storeKey);
        });

        syncBulkSelectAllCheckbox(viewId);
    });

    $scope.find('[id^="count_"]').each(function () {
        reloadSelectedCount($(this), storeKey);
    });
    $scope.find('[class*="count_"]').each(function () {
        reloadSelectedCount($(this), storeKey);
    });
}

// Switch General Tab
function switchGeneralTab(e) {
    // DO NOT USE GENERAL TABS TWICE ON A SINGLE PAGE.
    e.preventDefault();
    e.stopPropagation();
    let clickedEl = e.target.closest(".oh-general__tab-link");
    let targetSelector = clickedEl.dataset.target;

    // Remove active class from all the tabs
    $(".oh-general__tab-link").removeClass("oh-general__tab-link--active");
    // Remove active class to the clicked tab
    clickedEl.classList.add("oh-general__tab-link--active");

    // Hide all the general tabs
    $(".oh-general__tab-target").addClass("d-none");
    // Show the tab with the chosen target
    $(`.oh-general__tab-target${targetSelector}`).removeClass("d-none");
}

function toggleReimbursmentType(element) {
    if (element.val() == "reimbursement") {
        $("#genericModalBody [name=attachment]").parent().show();
        $("#genericModalBody [name=attachment]").attr("required", true);
        $("#genericModalBody [name=leave_type_id]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=cfd_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=ad_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=amount]")
            .parent().parent()
            .show()
            .attr("required", true);
        $("#genericModalBody #availableTable")
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=bonus_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
    } else if (element.val() == "leave_encashment") {
        $("#genericModalBody [name=attachment]").parent().hide();
        $("#genericModalBody [name=attachment]").attr("required", false);
        $("#genericModalBody [name=leave_type_id]")
            .parent().parent()
            .show()
            .attr("required", true);
        $("#genericModalBody [name=cfd_to_encash]")
            .parent().parent()
            .show()
            .attr("required", true);
        $("#genericModalBody [name=ad_to_encash]")
            .parent().parent()
            .show()
            .attr("required", true);
        $("#genericModalBody [name=amount]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody #availableTable")
            .show()
            .attr("required", true);
        $("#genericModalBody [name=bonus_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
        // #819
        $("#objectCreateModalTarget [name=employee_id]").trigger("change");
    } else if (element.val() == "bonus_encashment") {
        $("#genericModalBody [name=attachment]").parent().hide();
        $("#genericModalBody [name=attachment]").attr("required", false);
        $("#genericModalBody [name=leave_type_id]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=cfd_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=ad_to_encash]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=amount]")
            .parent().parent()
            .hide()
            .attr("required", false);
        $("#genericModalBody #availableTable")
            .hide()
            .attr("required", false);
        $("#genericModalBody [name=bonus_to_encash]")
            .parent().parent()
            .show()
            .attr("required", true);
    }
}

function highlightRow(checkbox) {
    checkbox.closest(".oh-sticky-table__tr").removeClass("highlight-selected");
    checkbox.closest("tr").removeClass("highlight-selected");
    if (checkbox.is(":checked")) {
        checkbox.closest(".oh-sticky-table__tr").addClass("highlight-selected");
        checkbox.closest("tr").addClass("highlight-selected");
    }
}

function reloadSelectedCount(targetElement, storeKey = "selectedInstances") {
    var count = JSON.parse(
        ensureSelectionStore(storeKey).attr("data-ids") || "[]"
    ).length;
    id = targetElement.attr("id");
    if (id) {
        id = id.split("count_")[1];
    }
    if (count) {
        targetElement.html(count);
        targetElement.parent().removeClass("d-none");
        $(`#unselect_${id}, #export_${id}, #bulk_udate_${id}`).removeClass(
            "d-none"
        );
    } else {
        targetElement.parent().addClass("d-none");
        $(`#unselect_${id}, #export_${id}, #bulk_udate_${id}`).addClass(
            "d-none"
        );
    }

    // Hide "Select" once every record matching the current filter is already
    // selected - there's nothing left for it to do. It reappears as soon as
    // the count drops below the total again (Unselect, or deselecting a row).
    var $selectBtn = $(`#select_${id}`);
    if ($selectBtn.length) {
        var total = parseInt($selectBtn.attr("data-total-count"), 10) || 0;
        $selectBtn.toggleClass("d-none", total > 0 && count >= total);
    }
}

// Safety net for the "Select (N)" toolbar button: on a fresh load of a list
// that already has every row selected (a selection restored from
// localStorage by selectSelected()), the Select button was observed staying
// visible even though reloadSelectedCount() above had already hidden it a
// moment earlier -- something ~200-300ms after this same settle re-touches
// the button and puts it back to the server-rendered default (always
// visible when the list has rows). Root cause not pinned down (not this
// file's own afterSwap/afterSettle handlers, not a second
// /rotating-list-view/-style request, not htmxSelect2.js's unrelated
// .oh-select sweep) despite extensive tracing -- re-assert the correct
// state instead, both right away and again once that mystery window has
// passed. Cheap (one comparison per select_* button) and idempotent, so
// running it repeatedly is harmless.
function resyncSelectButtons() {
    $('[id^="select_"][data-total-count]').each(function () {
        var $btn = $(this);
        var viewId = $btn.attr("id").replace(/^select_/, "");
        // The button's real storeKey is not always "selectedInstances" (e.g.
        // the roster grid uses "rosterEmployeeInstances"), so read it from
        // data-store-key rather than assuming the default -- which silently
        // no-ops this whole resync for any view with a custom store key.
        // Fall back to scraping onclick for older/custom markup that predates
        // the attribute.
        var storeKey = $btn.attr("data-store-key");
        if (!storeKey) {
            storeKey = "selectedInstances";
            var onclick = $btn.attr("onclick") || "";
            var match = onclick.match(/reloadSelectedCount\([^,]+,\s*['"]([^'"]+)['"]/)
                || onclick.match(/hlvSelectAllRecords\([^,]+,[^,]+,\s*['"]([^'"]+)['"]/);
            if (match) {
                storeKey = match[1];
            }
        }
        var count = JSON.parse(
            ensureSelectionStore(storeKey).attr("data-ids") || "[]"
        ).length;
        var total = parseInt($btn.attr("data-total-count"), 10) || 0;
        $btn.toggleClass("d-none", total > 0 && count >= total);
        if (count) {
            $(`#unselect_${viewId}, #export_${viewId}, #bulk_udate_${viewId}`).removeClass("d-none");
            $(`#count_${viewId}`).html(count);
        }
    });
}
$(document).on("htmx:afterSettle", function () {
    resyncSelectButtons();
    setTimeout(resyncSelectButtons, 400);
});

function removeHighlight() {
    setTimeout(function () {
        $(".toggle-highlight").removeClass("toggle-highlight");
    }, 200);
}

function removeId(element, storeKey = "selectedInstances") {
    id = String(element.val());
    ids = JSON.parse(
        ensureSelectionStore(storeKey).attr("data-ids") || "[]"
    ).map(String);
    var index = ids.indexOf(id);
    if (index > -1) {
        ids.splice(index, 1);
    }
    ensureSelectionStore(storeKey).attr("data-ids", JSON.stringify(ids));
    setStoredSelection(storeKey, ids);
}

function addId(element, storeKey = "selectedInstances") {
    id = String(element.val());
    ids = JSON.parse(
        ensureSelectionStore(storeKey).attr("data-ids") || "[]"
    ).map(String);
    if (!ids.includes(id)) {
        ids.push(id);
    }
    ensureSelectionStore(storeKey).attr("data-ids", JSON.stringify(ids));
    setStoredSelection(storeKey, ids);
}
function bulkStageUpdate(canIds, stageId, preStageId) {
    $.ajax({
        type: "POST",
        url: "/recruitment/candidate-stage-change?bulk=True",
        data: {
            csrfmiddlewaretoken: getCookie("csrftoken"),
            canIds: JSON.stringify(canIds),
            stageId: stageId,
        },
        success: function (response, textStatus, jqXHR) {
            if (jqXHR.status === 200) {
                $(`#stageLoad` + preStageId).click();
                $(`#stageLoad` + stageId).click();
            }
            if (response.message) {
                Swal.fire({
                    title: response.message,
                    text: interpolate(
                        i18nMessages.totalVacancy,
                        { vacancy: response.vacancy },
                        true
                    ),
                    icon: "info",
                    confirmButtonText: i18nMessages.ok,
                });
            }
        },
    });
}

function updateCandStage(canIds, stageId, preStageId) {
    $.ajax({
        type: "POST",
        url: "/recruitment/candidate-stage-change?bulk=false",
        data: {
            csrfmiddlewaretoken: getCookie("csrftoken"),
            canIds: canIds,
            stageId: stageId,
        },
        success: function (response, textStatus, jqXHR) {
            if (jqXHR.status === 200) {
                $(`#stageLoad` + preStageId).click();
                $(`#stageLoad` + stageId).click();
            }
            if (response.message) {
                Swal.fire({
                    title: response.message,
                    text: interpolate(
                        i18nMessages.totalVacancy,
                        { vacancy: response.vacancy },
                        true
                    ),
                    icon: "info",
                    confirmButtonText: i18nMessages.ok,
                });
            }
        },
    });
}

function checkSequence(element) {
    var preStageId = $(element).data("stage_id");
    var canIds = $(element).data("cand_id");
    var stageOrderJson = $(element).attr("data-stage_order");
    var stageId = $(element).val();

    var parsedStageOrder = JSON.parse(stageOrderJson);

    var stage = parsedStageOrder.find((stage) => stage.id == stageId);
    var preStage = parsedStageOrder.find((stage) => stage.id == preStageId);
    var stageOrder = parsedStageOrder.map((stage) => stage.id);

    if (
        stageOrder.indexOf(parseInt(stageId)) !=
        stageOrder.indexOf(parseInt(preStageId)) + 1 &&
        stage.type != "cancelled"
    ) {
        Swal.fire({
            title: i18nMessages.confirm,
            text: interpolate(
                i18nMessages.candidateStageChange,
                { from: preStage.stage, to: stage.stage },
                true
            ),
            icon: "info",
            showCancelButton: true,
            confirmButtonColor: "#008000",
            cancelButtonColor: "#6c757d",
            confirmButtonText: i18nMessages.confirm,
            cancelButtonText: i18nMessages.cancel,
        }).then(function (result) {
            if (result.isConfirmed) {
                updateCandStage(canIds, stageId, preStageId);
            }
        });
    } else {
        updateCandStage(canIds, stageId, preStageId);
    }
}

function reloadMessage(e) {
    $("#reloadMessagesButton").click();
}

// Star-rating widgets (e.g. helpdesk ticket priority) submit their form on
// the radio's own "change" event rather than a click handler on an ancestor
// element. A click on the <label> that visually draws the star fires TWO
// bubbling click events (one on the label itself, one the browser forwards
// to its associated radio input as label-activation behavior), so an
// ancestor onclick submits the form twice. "change" fires exactly once per
// actual value change regardless of how many click events led to it.
$(document).on("change", ".rating-radio", function () {
    $(this).closest("form").find("button[type=submit]").click();
});

// Intentionally a no-op: the loading skeleton/placeholder animation has
// been removed project-wide. Kept as a function (rather than deleted)
// because it's still wired up via hx-on:submit="htmxLoadIndicator(this);"
// across many templates -- removing the function entirely would throw a
// ReferenceError on every one of those pages. The swap target is simply
// left as whatever it already showed until the real response replaces it.
function htmxLoadIndicator(e) {}

/**
 * Shared failure fallback for any lazy-loaded swap target (the nav filter
 * form's hx-get for list/card views, and HorillaTabView's own tab-content
 * htmx.ajax() loads). Without this, a non-2xx response, a network failure,
 * or a hung request leaves the swap target exactly as it was (empty, on
 * first load) with no indication anything went wrong, indistinguishable
 * from "still loading".
 *
 * @param {string} targetSelector - CSS selector for the swap target.
 * @param {Event} [evt] - the htmx:responseError/sendError/timeout event, if any.
 * @param {string} [retryOnClick] - JS to run when the Retry button is clicked;
 *        defaults to re-submitting the shared nav filter form.
 */
function renderLoadFailure(targetSelector, evt, retryOnClick) {
    var $target = $(targetSelector);
    if (!$target.length) {
        return;
    }
    var reason = "";
    if (evt && evt.type === "htmx:timeout") {
        reason = i18nMessages.loadTimeout || "The request took too long to respond.";
    } else if (evt && evt.detail && evt.detail.xhr && evt.detail.xhr.status) {
        reason = (i18nMessages.loadFailedStatus || "Request failed (status %(status)s).").replace(
            "%(status)s",
            evt.detail.xhr.status
        );
    } else {
        reason = i18nMessages.loadFailed || "Something went wrong while loading this data.";
    }
    $target.html(
        `<div class="oh-load-error d-flex flex-column align-items-center justify-content-center text-center p-4">
            <p class="mb-2">${reason}</p>
            <button type="button" class="oh-btn oh-btn--secondary oh-btn--small" onclick="${retryOnClick || "$('#applyFilter').click();"}">
                ${i18nMessages.retry || "Retry"}
            </button>
        </div>`
    );
}

/** hx-on::response-error / hx-on::send-error / hx-on::timeout handler for
 * the nav filter form -- `e` is the form element, its hx-target names the
 * swap target that would otherwise be left showing the skeleton forever. */
function htmxLoadFailIndicator(e, evt) {
    renderLoadFailure($(e).attr("hx-target"), evt);
}

function hxConfirm(element, messageText) {
    Swal.fire({
        html: messageText,
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#008000",
        cancelButtonColor: "#6c757d",
        confirmButtonText: i18nMessages.confirm,
        cancelButtonText: i18nMessages.cancel,
        reverseButtons: true,
    }).then((result) => {
        if (result.isConfirmed) {
            htmx.trigger(element, 'confirmed');
        }
        else {
            element.checked = false
            return false
        }

    });
}

function handleDownloadAndRefresh(event, url) {
    // Use in import_popup.html file
    event.preventDefault();

    // Create a temporary hidden iframe to trigger the download
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.src = url;
    document.body.appendChild(iframe);

    // Refresh the page after a short delay
    setTimeout(function () {
        document.body.removeChild(iframe); // Clean up the iframe
        window.location.reload(); // Refresh the page
    }, 500); // Adjust the delay as needed
}

function toggleCommentButton(e) {
    const $button = $(e).closest("form").find("#commentButton");
    $button.toggle($(e).val().trim() !== "");
}

function updateUserPanelCount(e) {
    var count = $(e)
        .closest(".oh-sticky-table__tr")
        .find(".oh-user-panel").length;
    setTimeout(() => {
        var $permissionCountSpan = $(e)
            .closest(".oh-permission-table--toggle")
            .parent()
            .find(".oh-permission-count");
        var currentText = $permissionCountSpan.text();

        var firstSpaceIndex = currentText.indexOf(" ");
        var textAfterNumber = currentText.slice(firstSpaceIndex + 1);
        var newText = count + " " + textAfterNumber;

        $permissionCountSpan.text(newText);
    }, 100);
}

function enlargeImage(src, $element) {
    $(".enlargeImageContainer").empty();
    var enlargeImageContainer = $element
        .parents()
        .closest("li")
        .find(".enlargeImageContainer");
    enlargeImageContainer.empty();
    style =
        "width:100%; height:90%; box-shadow: 0 10px 10px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.2); background:white";
    var enlargedImage = $("<iframe>").attr({ src: src, style: style });
    var name = $("<span>").text(src.split("/").pop().replace(/_/g, " "));
    enlargeImageContainer.append(enlargedImage);
    enlargeImageContainer.append(name);
    setTimeout(function () {
        enlargeImageContainer.show();

        const iframe = document.querySelector("iframe").contentWindow;
        var iframe_document = iframe.document;
        iframe_image = iframe_document.getElementsByTagName("img")[0];
        $(iframe_image).attr("style", "width:100%; height:100%;");
    }, 100);
}

function hideEnlargeImage() {
    var enlargeImageContainer = $(".enlargeImageContainer");
    enlargeImageContainer.empty();
}

function submitForm(elem) {
    $(elem).siblings(".add_more_submit").click();
}

function show_answer(element) {
    const $parentItem = $(element).closest(".oh-faq__item");
    const isShown = $parentItem.hasClass("oh-faq__item--show");

    $(".oh-faq__item--show").removeClass("oh-faq__item--show");

    if (!isShown) {
        $parentItem.addClass("oh-faq__item--show");
    }
}

// var originalConfirm = window.confirm;
// // Override the default confirm function with SweetAlert
// window.confirm = function (message) {
//     var event = window.event || {};
//     event.preventDefault();

//     $("#confirmModalBody").html(message);
//     var submit = false;

//     Swal.fire({
//         text: message,
//         icon: "question",
//         showCancelButton: true,
//         confirmButtonColor: "#008000",
//         cancelButtonColor: "#d33",
//         confirmButtonText: i18nMessages.confirm,
//         cancelButtonText: i18nMessages.cancel,
//     }).then((result) => {
//         if (result.isConfirmed) {
//             var path = event.target["htmx-internal-data"]?.path;
//             var verb = event.target["htmx-internal-data"]?.verb;
//             var hxTarget = handleHtmxTarget(event, path, verb);
//             var hxVals = $(event.target).attr("hx-vals")
//                 ? JSON.parse($(event.target).attr("hx-vals"))
//                 : {};
//             var hxSwap = $(event.target).attr("hx-swap");
//             $(event.target).each(function () {
//                 $.each(this.attributes, function () {
//                     if (
//                         this.specified &&
//                         this.name === "hx-on-htmx-before-request"
//                     ) {
//                         eval(this.value);
//                     }
//                 });
//             });
//             if (event.target.tagName.toLowerCase() === "form") {
//                 if (path && verb) {
//                     // Collect all form values
//                     const formData = new FormData(event.target);
//                     const values = {};
//                     formData.forEach((value, key) => {
//                         values[key] = value;
//                     });

//                     // Merge with hx-vals, if any
//                     Object.assign(values, hxVals);

//                     htmx.ajax(verb.toUpperCase(), path, {
//                         target: hxTarget,
//                         swap: hxSwap,
//                         values: values,
//                     }).then((response) => {
//                         ajaxWithResponseHandler(event);
//                     });
//                 } else {
//                     event.target.submit();  // fallback
//                 }
//             }
//             else if (event.target.tagName.toLowerCase() === "a") {
//                 if (event.target.href) {
//                     window.location.href = event.target.href;
//                 } else {
//                     if (verb === "post") {
//                         htmx.ajax("POST", path, {
//                             target: hxTarget,
//                             swap: hxSwap,
//                             values: hxVals,
//                         }).then((response) => {
//                             ajaxWithResponseHandler(event);
//                         });
//                     } else {
//                         htmx.ajax("GET", path, {
//                             target: hxTarget,
//                             swap: hxSwap,
//                             values: hxVals,
//                         }).then((response) => {
//                             ajaxWithResponseHandler(event);
//                         });
//                     }
//                 }
//             } else {
//                 if (verb === "post") {
//                     htmx.ajax("POST", path, {
//                         target: hxTarget,
//                         swap: hxSwap,
//                         values: hxVals,
//                     }).then((response) => {
//                         ajaxWithResponseHandler(event);
//                     });
//                 } else {
//                     htmx.ajax("GET", path, {
//                         target: hxTarget,
//                         swap: hxSwap,
//                         values: hxVals,
//                     }).then((response) => {
//                         ajaxWithResponseHandler(event);
//                     });
//                 }
//             }
//         }
//     });
// };


function ajaxWithResponseHandler(elm) {
    $(elm).each(function () {
        $.each(this.attributes, function () {
            if (this.specified && this.name === "hx-on-htmx-after-request") {
                eval(this.value);
            }
        });
    });
}

function handleHtmxTarget(elm, path, verb) {
    var targetElement;
    var hxTarget = $(elm).attr("hx-target");
    if (hxTarget) {
        if (hxTarget === "this") {
            targetElement = $(elm);
        } else if (hxTarget.startsWith("closest ")) {
            var selector = hxTarget.replace("closest ", "").trim();
            targetElement = $(elm).closest(selector);
        } else if (hxTarget.startsWith("find ")) {
            var selector = hxTarget.replace("find ", "").trim();
            targetElement = $(elm).find(selector).first();
        } else if (hxTarget === "next") {
            targetElement = $(elm).next();
        } else if (hxTarget.startsWith("next ")) {
            var selector = hxTarget.replace("next ", "").trim();
            targetElement = $(elm).nextAll(selector).first();
        } else if (hxTarget === "previous") {
            targetElement = $(elm).prev();
        } else if (hxTarget.startsWith("previous ")) {
            var selector = hxTarget.replace("previous ", "").trim();
            targetElement = $(elm).prevAll(selector).first();
        } else {
            targetElement = $(hxTarget);
        }
        hxTarget = targetElement.length ? targetElement[0] : null;
    } else if (path && verb) {
        hxTarget = elm;
    }
    return hxTarget;
}

var originalConfirm = window.confirm;
// Override the default confirm function with SweetAlert
window.confirm = function (message) {
    var event = window.event || {};
    event.preventDefault();

    const triggerEl = event.target.closest(
        "form, a, [hx-post], [hx-get], [hx-delete], [hx-put]"
    );
    if (!triggerEl) return;

    Swal.fire({
        text: message,
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#008000",
        cancelButtonColor: "#6c757d",
        confirmButtonText: i18nMessages.confirm,
        cancelButtonText: i18nMessages.cancel,
    }).then((result) => {
        if (result.isConfirmed) {
            // Read HTMX data from the trigger element
            var path = triggerEl["htmx-internal-data"]?.path;
            var verb = triggerEl["htmx-internal-data"]?.verb;
            var hxTarget = handleHtmxTarget(triggerEl, path, verb);
            var hxVals = $(triggerEl).attr("hx-vals")
                ? JSON.parse($(triggerEl).attr("hx-vals"))
                : {};
            var hxSwap = $(triggerEl).attr("hx-swap");

            // Evaluate hx-on-htmx-before-request if present
            $(triggerEl).each(function () {
                $.each(this.attributes, function () {
                    if (
                        this.specified &&
                        this.name === "hx-on-htmx-before-request"
                    ) {
                        eval(this.value);
                    }
                });
            });

            // Handle <form>
            if (triggerEl.tagName.toLowerCase() === "form") {
                if (path && verb) {
                    // Collect all form values
                    const formData = new FormData(triggerEl);
                    const values = {};
                    formData.forEach((value, key) => {
                        values[key] = value;
                    });

                    // Merge with hx-vals, if any
                    Object.assign(values, hxVals);

                    htmx.ajax(verb.toUpperCase(), path, {
                        target: hxTarget,
                        swap: hxSwap,
                        values: values,
                    }).then((response) => {
                        ajaxWithResponseHandler(triggerEl);
                    });
                } else {
                    triggerEl.submit();
                }

                // Handle <a>
            } else if (triggerEl.tagName.toLowerCase() === "a") {
                const rawHref = triggerEl.getAttribute("href");
                const hasRealHref = rawHref && rawHref !== "#" && !rawHref.startsWith("#");
                if (hasRealHref && !path) {
                    window.location.href = triggerEl.href;
                } else {
                    if (verb === "post") {
                        htmx.ajax("POST", path, {
                            target: hxTarget,
                            swap: hxSwap,
                            values: hxVals,
                        }).then((response) => {
                            ajaxWithResponseHandler(triggerEl);
                        });
                    } else {
                        htmx.ajax("GET", path, {
                            target: hxTarget,
                            swap: hxSwap,
                            values: hxVals,
                        }).then((response) => {
                            ajaxWithResponseHandler(triggerEl);
                        });
                    }
                }
            } else if (triggerEl.tagName.toLowerCase() === "button") {
                if (verb === "post") {
                    htmx.ajax("POST", path, {
                        target: hxTarget,
                        swap: hxSwap,
                        values: hxVals,
                    }).then((response) => {
                        ajaxWithResponseHandler(triggerEl);
                    });
                } else {
                    htmx.ajax("GET", path, {
                        target: hxTarget,
                        swap: hxSwap,
                        values: hxVals,
                    }).then((response) => {
                        ajaxWithResponseHandler(triggerEl);
                    });
                }
                // Handle other HTMX triggers
            } else {
                if (verb === "post") {
                    htmx.ajax("POST", path, {
                        target: hxTarget,
                        swap: hxSwap,
                        values: hxVals,
                    }).then((response) => {
                        ajaxWithResponseHandler(event);
                    });
                } else {
                    htmx.ajax("GET", path, {
                        target: hxTarget,
                        swap: hxSwap,
                        values: hxVals,
                    }).then((response) => {
                        ajaxWithResponseHandler(event);
                    });
                }
            }
        }
    });
};

var excludeIds = "#employeeSearch";
// To exclude more elements, add their IDs (prefixed with '#') or class names (prefixed with '.'), separated by commas to 'excludeIds'.
setTimeout(() => {
    $("[name='search']").not(excludeIds).focus();
}, 100);

$("#close").attr(
    "class",
    "oh-activity-sidebar__header-icon me-2 oh-activity-sidebar__close md hydrated"
);

$("body").on("click", ".select2-search__field", function (e) {
    //When click on Select2 fields in filter form,Auto close issue
    e.stopPropagation();
});

var nav = $("section.oh-wrapper.oh-main__topbar");
nav.after(
    $(
        `
  <div id="filterTagContainerSectionNav" class="oh-titlebar-container__filters mb-2 mt-0 oh-wrapper"></div>
  `
    )
);

$(function () {
    const $wrapper = $('.oh-wrapper-main');
    const sidebarOpen = localStorage.getItem('sidebarOpen');

    if (sidebarOpen === 'false') {
        $wrapper.addClass('oh-wrapper-main--closed');
    } else {
        $wrapper.removeClass('oh-wrapper-main--closed');
    }

    $('#sidebar').on('mouseleave', () => {
        if (localStorage.getItem('sidebarOpen') === 'false') {
            $wrapper.addClass('oh-wrapper-main--closed');
        }
    });
});

$(document).on('click', '.oh-kanban__card-body-collapse', function (e) {
    e.preventDefault();

    var $cardBody = $(this).closest('.oh-kanban__card-body');

    $cardBody.find('.oh-kanban__card-content').toggleClass('oh-kanban__card-content--hide');

    $(this).toggleClass('oh-kanban__card-collapse--down');
});



$(document).on("click", ".select2-selection__choice__remove", function (event) {
    if ($('[role="tooltip"]:not(.apexcharts-tooltip):visible').length) {
        $('[role="tooltip"]:not(.apexcharts-tooltip)').hide();
    }
});

$(document).on("keydown", function (event) {
    // Check if the cursor is not focused on an input field
    var isInputFocused = $(document.activeElement).is(
        "input, textarea, select"
    );

    if (event.keyCode === 27) {
        // Key code 27 for Esc in keypad
        $(".oh-modal--show").removeClass("oh-modal--show");
        $(".oh-activity-sidebar--show").removeClass(
            "oh-activity-sidebar--show"
        );
    }

    if (event.keyCode === 46) {
        // Key code 46 for delete in keypad
        // If there have any objectDetailsModal with oh-modal--show
        // take delete button inside that else take the delete button from navbar Actions
        if (!isInputFocused) {
            var $modal = $(".oh-modal--show");
            var $deleteButton = $modal.length
                ? $modal.find('[data-action="delete"]')
                : $(".oh-dropdown").find('[data-action="delete"]');
            if ($deleteButton.length) {
                $deleteButton.click();
                $deleteButton[0].click();
            }
        }
    } else if (event.keyCode === 107) {
        // Key code for the + key on the numeric keypad
        if (!isInputFocused) {
            // Click the create option from navbar of current page
            $('[data-action="create"]').click();
        }
    } else if (event.keyCode === 39) {
        // Key code for the right arrow key
        if (!isInputFocused) {
            var $modal = $(".oh-modal--show");
            var $nextButton = $modal.length
                ? $modal.find('[data-action="next"]')
                : $('[data-action="next"]'); // Click on the next button in detail view modal
            if ($nextButton.length) {
                $nextButton[0].click();
            }
        }
    } else if (event.keyCode === 37) {
        // Key code for the left arrow key
        if (!isInputFocused) {
            // Click on the previous button in detail view modal
            var $modal = $(".oh-modal--show");
            var $previousButton = $modal.length
                ? $modal.find('[data-action="previous"]')
                : $('[data-action="previous"]');
            if ($previousButton.length) {
                $previousButton[0].click();
            }
        }
    }
});

$(document).on("click", function (event) {
    if (!$(event.target).closest("#enlargeImageContainer").length) {
        hideEnlargeImage();
    }
});

$(document).on("htmx:afterSwap", function () {
    // Only initialize elements that aren't already a live Summernote editor.
    // Re-calling .summernote(options) on one that already is can leave the
    // original textarea visible again alongside the rich editor UI (see
    // initializeSummernote() below, which guards the same way for the same
    // reason) -- this handler fires on EVERY htmx swap anywhere on the page,
    // so a modal reopened more than once was hitting this repeatedly.
    $("[data-summernote]").each(function () {
        var $source = $(this);
        if ($source.next(".note-editor").length > 0) {
            return;
        }
        // Summernote hides the field it is attached to. The browser cannot
        // focus a hidden control to report a constraint violation, so a
        // `required` one aborts the whole submit ("An invalid form control
        // ... is not focusable") — no submit event, no request, and the Save
        // button appears dead. Leave the required check to the server, which
        // renders its error inline under the field.
        this.removeAttribute("required");
        $source.summernote({
            height: 300,
            codeviewFilter: false,
            codeviewIframeFilter: false,
            callbacks: {
                onChange: function (contents) {
                    // Write back to the edited field itself — targeting
                    // [name="body"] pushed the text into an unrelated field
                    // whenever the editor was attached to anything else.
                    $source.val(contents);
                },
            },
        });
    });
});

// Global "type '{' for sender/receiver data" mail-body hint, called by
// send-mail forms (employee, recruitment candidate, etc.) after their own
// searchWords-aware Summernote init. Previously lived only in the legacy
// templates/sidebar.html, which the active theme's index.html no longer
// includes -- every caller's `typeof initializeSummernote === 'function'`
// check silently failed, so the hint dropdown never appeared even though
// the base editor (initialized above) still worked.
function preloadData(item, candId, preloadedData, callback) {
    $.ajax({
        type: "get",
        url: `/recruitment/get-template-hint/`,
        data: { "candidate_id": candId, 'word': item },
        success: function (response) {
            preloadedData[item] = response.body;
            callback();
            $('.note-hint-popover').hide()
        }
    });
}

function initializeSummernote(candId, searchWords) {
    var preloadedData = {};
    var mentions = Object.keys(searchWords);
    var $body = $("[name='body']");
    // A caller invoked more than once for the same open (e.g. a stale,
    // re-accumulated event listener) would otherwise re-call .summernote()
    // on an already-live editor, which can leave the source textarea
    // visible again alongside the rich editor UI. Destroy any existing
    // instance first so exactly one clean editor (with hint) results
    // regardless of how many times this runs.
    if ($body.next(".note-editor").length > 0) {
        $body.summernote("destroy");
    }
    // Same hidden-required trap as the [data-summernote] init above: the
    // browser cannot report a violation on the hidden source field, so a
    // `required` mail body silently blocks the whole form submit.
    $body.each(function () {
        this.removeAttribute("required");
    });
    $body.summernote({
        hint: {
            mentions: mentions,
            match: /\B\{(\w*)$/,
            search: function (keyword, callback) {
                var pattern = new RegExp(keyword, "i"); // Case-insensitive search
                callback($.grep(this.mentions, function (item) {
                    return pattern.test(item);
                }));
            },
            content: function (item) {
                var word = searchWords[item];
                var insertText = `{{${word}}}`;

                if (preloadedData[word]) {
                    $("[name='body']").summernote('pasteHTML', insertText);
                    $('.note-hint-popover').hide();
                } else {
                    preloadData(word, candId, preloadedData, function () {
                        $("[name='body']").summernote('pasteHTML', insertText);
                        $('.note-hint-popover').hide();
                    });
                }
            }
        }
    });
}

function offboardingUpdateStage($element) {
    submitButton = $element.closest("form").find("input[type=submit]")
    submitButton.click()
}

const ChartTheme = {
    getColors() {
        const isDark = document.body?.classList.contains("dark");
        return {
            tickColor: isDark ? "#dddddd" : "#374151",
            gridColor: isDark ? "rgba(255,255,255,0.06)" : "rgba(55,65,81,0.06)",
        };
    },

    // Call this when building chart options to get pre-filled scale/plugin options
    getThemedOptions() {
        const { tickColor, gridColor } = this.getColors();
        return {
            scales: {
                x: {
                    ticks: { color: tickColor },
                    grid: { color: gridColor },
                },
                y: {
                    ticks: { color: tickColor },
                    grid: { color: gridColor },
                },
            },
            plugins: {
                legend: { labels: { color: tickColor } },
            },
        };
    },

    applyTheme(chart) {
        if (!chart?.options) return;

        const { tickColor, gridColor } = this.getColors();

        // ---- Update scales (if exist)
        if (chart.options.scales) {
            Object.keys(chart.options.scales).forEach((axis) => {
                const scale = chart.options.scales[axis];

                // ticks
                if (scale.ticks) {
                    scale.ticks.color = tickColor;
                }

                // grid
                if (scale.grid) {
                    scale.grid.color = gridColor;
                }

                // title (optional)
                if (scale.title) {
                    scale.title.color = tickColor;
                }
            });
        }

        // ---- Update legend
        if (chart.options.plugins?.legend?.labels) {
            chart.options.plugins.legend.labels.color = tickColor;
        }

        chart.update('none');
    },

    // Register a chart instance to auto-update on dark mode toggle
    // Pass the window key (string) where the chart is stored, e.g. "pendingHoursCanvas"
    observe(chartWindowKey) {

        if (!window._chartThemeObserver) {
            window._chartThemeObserver = new MutationObserver(() => {
                (window._chartThemeRegistry || []).forEach((key) => {
                    if (window[key]) ChartTheme.applyTheme(window[key]);
                });
            });
            window._chartThemeObserver.observe(document.body, {
                attributes: true,
                attributeFilter: ["class"],
            });
        }

        window._chartThemeRegistry = window._chartThemeRegistry || [];
        if (!window._chartThemeRegistry.includes(chartWindowKey)) {
            window._chartThemeRegistry.push(chartWindowKey);
        }
    },
};
