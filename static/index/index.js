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
        confirmBulkReject: gettext("Do you really want to reject all the selected requests?"),
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

function hlvSelectAllRecords(btn, viewSelector, storeKey) {
    storeKey = storeKey || "selectedInstances";
    var $btn = $(btn);

    function applySelection(ids) {
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

    var inlineIds = $btn.attr("data-select-ids");
    if (inlineIds !== undefined) {
        var ids = [];
        try {
            ids = JSON.parse(inlineIds || "[]");
        } catch (e) {
            ids = [];
        }
        applySelection(ids);
        return;
    }

    var selectUrl = $btn.attr("data-select-url");
    if (!selectUrl || $btn.prop("disabled")) return;
    var url = new URL(selectUrl, window.location.origin);
    url.searchParams.set("select_all", "true");
    $btn.prop("disabled", true);
    $.ajax({
        url: url.pathname + url.search,
        dataType: "json",
        headers: { "HX-Request": "true" },
    })
        .done(applySelection)
        .fail(function () {
            console.error(i18nMessages.loadFailed);
        })
        .always(function () {
            $btn.prop("disabled", false);
        });
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

/**
 * Select-all checkbox in a group's header (.hlv-group-select): selects (or
 * drops) every record of that group -- all its pages, loaded or not -- in the
 * shared selection, leaving the other groups' selection alone.
 */
function hlvToggleGroupSelect(cb, viewSelector, storeKey) {
    storeKey = storeKey || "selectedInstances";
    if (cb.checked) {
        addToSelectedId($(cb).attr("data-select-ids"), storeKey);
        selectSelected(viewSelector, storeKey);
        var viewId = (viewSelector || "").replace(/^#/, "");
        reloadSelectedCount($(`#count_${viewId}`), storeKey);
        reloadSelectedCount($(`.count_${viewId}`), storeKey);
    } else {
        hlvUnselectRecords(cb, viewSelector, storeKey);
    }
    hlvSyncGroupSelectBoxes(storeKey);
}

// Group header checkboxes mirror the selection: checked when every record of
// the group is selected, indeterminate when only some are.
function hlvSyncGroupSelectBoxes(storeKey) {
    storeKey = storeKey || "selectedInstances";
    var $boxes = $(".hlv-group-select");
    if (!$boxes.length) return;
    var selected = new Set(
        JSON.parse(ensureSelectionStore(storeKey).attr("data-ids") || "[]").map(String)
    );
    $boxes.each(function () {
        if ((this.getAttribute("data-store-key") || "selectedInstances") !== storeKey) return;
        var ids = [];
        try {
            ids = JSON.parse(this.getAttribute("data-select-ids") || "[]");
        } catch (e) {}
        var n = 0;
        ids.forEach(function (id) {
            if (selected.has(String(id))) n++;
        });
        this.checked = ids.length > 0 && n === ids.length;
        this.indeterminate = n > 0 && n < ids.length;
    });
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
    hlvSyncGroupSelectBoxes(storeKey);
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
    // afterSettle fires once per swapped fragment; one check per burst is enough.
    clearTimeout(window.__hlvPruneTimer);
    window.__hlvPruneTimer = setTimeout(pruneDeletedSelections, 600);
});

// Refresh the current list in place (no full page reload): re-run the nav's
// search / filter form, which swaps a fresh list into the container. Falls back
// to a reload on pages without one.
function hlvReloadListInPlace() {
    // Pages with tabs carry one nav (and so one #applyFilter) per tab; use the
    // active tab's, not whichever sits first in the DOM.
    var activeTab = document.querySelector(".oh-tabs__content--active");
    var apply =
        (activeTab && activeTab.querySelector("#applyFilter")) ||
        document.getElementById("applyFilter");
    if (apply) {
        apply.click();
    } else {
        location.reload();
    }
}

// A bulk archive / un-archive / approve / reject / delete / validate acts on the
// selected rows, so those rows must leave the selection once it has run -
// otherwise "Unselect (N)" / "Update (N)" keep counting rows that are no longer
// in the list (e.g. archived ones). Matched by URL convention so it covers every
// list without a registry: the last segment has "bulk" plus an action word.
function hlvIsBulkSelectionAction(url) {
    var path = String(url || "").split("?")[0].replace(/\/+$/, "");
    var segment = path.substring(path.lastIndexOf("/") + 1);
    return (
        /bulk/.test(segment) &&
        /archive|approve|reject|cancel|delete|validate/.test(segment) &&
        !/export|invitation|password/.test(segment)
    );
}

function hlvDropSelectedIds(ids) {
    if (!ids || !ids.length) return;
    var gone = {};
    ids.forEach(function (id) { gone[String(id)] = true; });
    var without = function (list) {
        return list.filter(function (id) { return !gone[String(id)]; });
    };
    var changed = false;
    // Selection stores on this page ...
    $("[data-ids]").each(function () {
        if (!this.id) return;
        var current;
        try { current = JSON.parse(this.getAttribute("data-ids") || "[]"); } catch (e) { return; }
        var kept = without(current);
        if (kept.length === current.length) return;
        changed = true;
        this.setAttribute("data-ids", JSON.stringify(kept));
        setStoredSelection(this.id, kept);
    });
    // ... and the ones only remembered in localStorage (restored after a reload).
    try {
        var prefix = "hlv_selection:" + window.location.pathname + ":";
        Object.keys(localStorage).forEach(function (key) {
            if (key.indexOf(prefix) !== 0) return;
            var current = JSON.parse(localStorage.getItem(key) || "[]");
            var kept = without(current);
            if (kept.length !== current.length) {
                changed = true;
                localStorage.setItem(key, JSON.stringify(kept));
            }
        });
    } catch (e) {
        // localStorage unavailable - nothing remembered to clean up.
    }
    if (!changed) return;
    $(".list-table-row, .bulk-list-table-row").each(function () {
        if (gone[String($(this).val())]) {
            $(this).prop("checked", false);
            highlightRow($(this));
        }
    });
    $('[id^="count_"], [class*="count_"]').each(function () {
        var $count = $(this);
        var $container = $count.closest(".hlv-container[data-selected-instances-key]");
        reloadSelectedCount($count, $container.attr("data-selected-instances-key") || "selectedInstances");
    });
    resyncSelectButtons();
}

// The selection lives in the browser (data-ids on the store), so deleting
// records leaves their ids behind and "Unselect (N)" / "Update (N)" keep
// counting them. After a list (re)loads, ask the server which selected ids
// still exist and drop the rest. Only ids that no longer exist are removed -
// ones merely filtered out of view stay selected.
function pruneDeletedSelections() {
    var seen = {};
    $(".hlv-container[data-model]").each(function () {
        var $container = $(this);
        var model = $container.attr("data-model");
        var storeKey = $container.attr("data-selected-instances-key") || "selectedInstances";
        var key = model + "|" + storeKey;
        if (!model || seen[key]) return;
        seen[key] = true;
        var ids = JSON.parse(ensureSelectionStore(storeKey).attr("data-ids") || "[]").map(String);
        if (!ids.length) return;
        $.ajax({
            type: "POST",
            url: "/existing-ids/",
            data: {
                csrfmiddlewaretoken: getCookie("csrftoken"),
                model: model,
                ids: JSON.stringify(ids),
            },
            success: function (response) {
                var alive = new Set(response.ids || []);
                // Ids may have changed while the request was in flight.
                var current = JSON.parse(ensureSelectionStore(storeKey).attr("data-ids") || "[]").map(String);
                var kept = current.filter(function (id) { return alive.has(id) || ids.indexOf(id) === -1; });
                if (kept.length === current.length) return;
                ensureSelectionStore(storeKey).attr("data-ids", JSON.stringify(kept));
                setStoredSelection(storeKey, kept);
                $('[id^="count_"]').each(function () {
                    reloadSelectedCount($(this), storeKey);
                });
                $('[class*="count_"]').each(function () {
                    reloadSelectedCount($(this), storeKey);
                });
                resyncSelectButtons();
            },
        });
    });
}

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

/**
 * Guard for an `hx-trigger="load[...]"` conditional: htmx's history restore
 * (the browser Back button, after an hx-push-url navigation) reinserts the
 * whole previous page -- as a cache hit from its own localStorage snapshot,
 * or as a fresh server refetch when that snapshot was evicted -- and
 * reprocesses every node in it exactly like a first render. A swap target
 * that was already fully loaded before the user navigated away gets
 * reinserted already populated, but its own `hx-trigger="load"` loader fires
 * again anyway and immediately refetches over it, which looks and feels
 * exactly like the whole page reloading. This only returns true the first
 * time a given target is genuinely empty, so the real first load is
 * unaffected and only the redundant refetch-on-restore is skipped.
 *
 * `selector` (e.g. "#listContainer") is reused verbatim by every
 * HorillaNavView/HorillaListView pair in the app, so a HorillaTabView page
 * with more than one tab already loaded has several elements answering to it
 * at once -- a bare `document.querySelector` always grabs the FIRST one,
 * which belongs to whichever tab loaded earliest, not the tab this call is
 * actually guarding. That earlier tab's target is never empty, so every
 * later tab's own genuinely-empty target was wrongly read as "already
 * loaded" and skipped its load entirely, leaving it blank. `scopeEl` -- an
 * element that lives inside the SAME tab pane as the nav instance making
 * this call (`this` from the hx-trigger expression, or a `<script>` element
 * captured via `document.currentScript` before any async callback) -- lets
 * this look inside that one pane (its nearest `.oh-tabs__content` ancestor)
 * instead of the whole document, so each tab resolves its own target.
 *
 * A per-tab shell (generic/horilla_tab_content_shell.html,
 * cbv/work_shift_tab/profile_tab_shell.html) renders `selector`'s container
 * with a ".animated-background" skeleton div already inside it, before its
 * Nav has even loaded -- so on a genuine first load the container already
 * has one child, and a plain child-count check reads that as "already
 * loaded" and never fires the real request at all. Skeleton-only content
 * doesn't count as "loaded" here for that reason.
 *
 * @param {string} selector - CSS selector for the element being loaded into
 *        (its own hx-target, or itself when none is set).
 * @param {Element} [scopeEl] - an element inside this call's own tab pane,
 *        if this nav instance might be one of several tabs on the page.
 */
function htmxShouldLoadOnce(selector, scopeEl) {
    var scope = document;
    if (scopeEl && typeof scopeEl.closest === "function") {
        var pane = scopeEl.closest(".oh-tabs__content");
        if (pane) scope = pane;
    }
    var el = selector && scope.querySelector(selector);
    if (!el) return true;
    var realChildren = Array.prototype.filter.call(el.children, function (child) {
        return !child.classList.contains("animated-background");
    });
    return realChildren.length === 0;
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
    $("[data-summernote]").each(function () {
        var $source = $(this);
        // Skip editors that are already initialized.
        if ($source.next(".note-editor").length > 0) {
            return;
        }
        // Hidden required fields block form submit; the server validates instead.
        this.removeAttribute("required");
        $source.summernote({
            height: 200,
            codeviewFilter: false,
            codeviewIframeFilter: false,
            callbacks: {
                onChange: function (contents) {
                    $source.val(contents);
                },
            },
        });
    });
});

// Mail-body "{" hint used by the send-mail forms.
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
    // Destroy any existing editor so repeated calls leave exactly one.
    if ($body.next(".note-editor").length > 0) {
        $body.summernote("destroy");
    }
    // Hidden required fields block form submit; the server validates instead.
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


/* ---------------------------------------------------------------------------
 * Bulk delete workflow, shared by every list: progress dialog while the request
 * runs, then a Total / Deleted / Failed result dialog.
 *
 * The existing per-page handlers keep their own confirm dialog and $.ajax call.
 * $.ajax / htmx are wrapped below for the bulk-delete URLs in
 * HLV_BULK_DELETE_MODELS, so none of those handlers had to change. The numbers
 * come from asking the server which of the posted ids still exist
 * (/existing-ids/), which works for any endpoint whatever it returns. The
 * handler's own success / complete callback (often a reload) only runs after the
 * result dialog is closed, and the server drops the per-record toasts for these
 * requests (BulkDeleteSummaryMiddleware).
 * ------------------------------------------------------------------------- */

// Last URL segment of each bulk-delete endpoint -> model whose ids it posts.
var HLV_BULK_DELETE_MODELS = {
    "attendance-bulk-delete": "attendance.attendance",
    "attendance-activity-bulk-delete": "attendance.attendanceactivity",
    "attendance-account-bulk-delete": "attendance.attendanceovertime",
    "late-come-early-out-bulk-delete": "attendance.attendancelatecomeearlyout",
    "rotating-work-type-assign-bulk-delete": "base.rotatingworktypeassign",
    "rotating-shift-assign-bulk-delete": "base.rotatingshiftassign",
    "work-type-request-bulk-delete": "base.worktyperequest",
    "shift-request-bulk-delete": "base.shiftrequest",
    "holidays-bulk-delete": "base.holidays",
    "biometric-users-bulk-delete": "biometric.biometricemployees",
    "cosec-users-bulk-delete": "biometric.biometricemployees",
    "tickets-bulk-delete": "helpdesk.ticket",
    "assigned-leave-bulk-delete": "leave.availableleave",
    "restrict-days-bulk-delete": "leave.restrictleave",
    "leave-request-bulk-delete": "leave.leaverequest",
    "leave-allocation-request-bulk-delete": "leave.leaveallocationrequest",
    "user-request-bulk-delete": "leave.leaverequest",
    "onboarding-candidate-bulk-delete": "recruitment.candidate",
    "candidate-bulk-delete": "recruitment.candidate",
    "payslip-bulk-delete": "payroll.payslip",
    "contract-bulk-delete": "payroll.contract",
    "objective-bulk-delete": "pms.employeeobjective",
    "feedback-bulk-delete": "pms.feedback",
    "project-bulk-delete": "project.project",
    "task-all-bulk-delete": "project.task",
    "time-sheet-bulk-delete": "project.timesheet",
};

function hlvBulkDeleteModel(url) {
    var path = String(url || "").split("?")[0].replace(/\/+$/, "");
    return HLV_BULK_DELETE_MODELS[path.substring(path.lastIndexOf("/") + 1)] || null;
}

// Bulk approve / reject endpoints: progress dialog only (their per-record toasts
// are the result). Last URL segment -> action.
var HLV_BULK_ACTIONS = {
    "shift-request-bulk-approve": "approve",
    "shift-request-bulk-cancel": "reject",
    "work-type-request-bulk-approve": "approve",
    "work-type-request-bulk-cancel": "reject",
    "document-bulk-approve": "approve",
    "document-bulk-reject": "reject",
    "leave-requests-bulk-approve": "approve",
    "leave-requests-bulk-reject": "reject",
    "bulk-approve-attendance-request": "approve",
    "bulk-reject-attendance-request": "reject",
    "validate-bulk-attendance": "validate",
    "approve-bulk-overtime": "approveot",
    "leave-allocation-request-bulk-approve": "approve",
    "leave-allocation-request-bulk-reject": "reject",
};

// Bulk archive endpoints that take ?is_active=False (archive) / =True (un-archive).
// (Case-insensitive: some endpoints are called with is_active=false.)
var HLV_BULK_ARCHIVES = {
    "rotating-shift-assign-bulk-archive": true,
    "rotating-work-type-assign-bulk-archive": true,
    "candidate-bulk-archive": true,
    "task-all-bulk-archive": true,
    "project-bulk-archive": true,
    "feedback-bulk-archive": true,
    "objective-bulk-archive": true,
    "tickets-bulk-archive": true,
    "employee-bulk-archive": true,
};

function hlvBulkActionKind(url) {
    var parts = String(url || "").split("?");
    var path = parts[0].replace(/\/+$/, "");
    var segment = path.substring(path.lastIndexOf("/") + 1);
    if (HLV_BULK_ARCHIVES[segment]) {
        var flag = new URLSearchParams(parts[1] || "").get("is_active");
        return String(flag).toLowerCase() === "false" ? "archive" : "unarchive";
    }
    return HLV_BULK_ACTIONS[segment] || null;
}

// ids may be a JSON string, an array, or repeated "ids" params, depending on
// the caller (jQuery data object / query string, htmx parameters).
function hlvBulkDeleteIds(data) {
    var raw = null;
    if (!data) return [];
    if (typeof data === "string") {
        var all = new URLSearchParams(data).getAll("ids");
        raw = all.length > 1 ? all : all[0];
    } else if (typeof FormData !== "undefined" && data instanceof FormData) {
        var fd = data.getAll("ids");
        raw = fd.length > 1 ? fd : fd[0];
    } else {
        raw = data.ids;
    }
    if (typeof raw === "string") {
        try {
            raw = JSON.parse(raw);
        } catch (e) {
            raw = raw ? [raw] : [];
        }
    }
    if (!Array.isArray(raw)) raw = raw === undefined || raw === null ? [] : [raw];
    return raw.map(String);
}

function hlvMessages() {
    return typeof i18nMessages !== "undefined" ? i18nMessages : {};
}

// Compact layout comes from the global .swal2-popup rules in the stylesheet.
function hlvBulkDeleteProgress(count, title) {
    var m = hlvMessages();
    Swal.fire({
        title: title || m.deletingRecords || "Deleting records",
        width: "24rem",
        html:
            '<style>@keyframes hlvSlide{0%{margin-left:-40%}100%{margin-left:100%}}</style>' +
            (count
                ? '<div style="margin:0 0 6px;color:#6b7280;font-size:13px">' + count + " " +
                  (m.recordsCount || "record(s)") + "</div>"
                : "") +
            '<div style="height:6px;border-radius:6px;background:#eceef2;overflow:hidden;margin-bottom:18px">' +
            '<div style="width:40%;height:100%;border-radius:6px;background:#e54f38;animation:hlvSlide 1.1s ease-in-out infinite"></div></div>',
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
    });
}

function hlvBulkActionProgress(kind, count) {
    var m = hlvMessages();
    var titles = {
        approve: m.approvingRequests || "Approving requests",
        reject: m.rejectingRequests || "Rejecting requests",
        archive: m.archivingRecords || "Archiving records",
        unarchive: m.unarchivingRecords || "Un-archiving records",
        validate: m.validatingRecords || "Validating attendances",
        approveot: m.approvingOvertime || "Approving overtime",
    };
    hlvBulkDeleteProgress(count, titles[kind]);
}

// Result dialog laid out like the import result. `kind` is "approve", "reject",
// "archive" or "unarchive" for those bulk actions, anything else for a delete. Returns the
// Swal promise, so callers can wait for it to be closed.
function hlvShowBulkDeleteSummary(r, kind) {
    var m = hlvMessages();
    var words = {
        approve: {
            result: m.approveResult || "Approve Result",
            warnings: m.approveWarnings || "Approve Completed with Warnings",
            success: m.approveSuccessful || "Approve Successful",
            none: m.noneApproved || "Nothing was approved. They were already approved or rejected.",
            some: m.someNotApproved || "Some requests were skipped (already approved or rejected).",
            all: m.allApproved || "All selected requests were approved.",
            done: m.approved || "Approved",
        },
        reject: {
            result: m.rejectResult || "Reject Result",
            warnings: m.rejectWarnings || "Reject Completed with Warnings",
            success: m.rejectSuccessful || "Reject Successful",
            none: m.noneRejected || "Nothing was rejected. They were already rejected.",
            some: m.someNotRejected || "Some requests were skipped (already rejected).",
            all: m.allRejected || "All selected requests were rejected.",
            done: m.rejected || "Rejected",
        },
        approveot: {
            result: m.approveOtResult || "Approve OT Result",
            warnings: m.approveOtWarnings || "Approve OT Completed with Warnings",
            success: m.approveOtSuccessful || "Approve OT Successful",
            none: m.noneOtApproved || "Nothing was approved. The overtime was already approved or can't be approved by you.",
            some: m.someOtNotApproved || "Some attendances were skipped (overtime already approved).",
            all: m.allOtApproved || "Overtime was approved for all selected attendances.",
            done: m.approved || "Approved",
        },
        validate: {
            result: m.validateResult || "Validate Result",
            warnings: m.validateWarnings || "Validate Completed with Warnings",
            success: m.validateSuccessful || "Validate Successful",
            none: m.noneValidated || "Nothing was validated. They have a pending update request or can't be validated.",
            some: m.someNotValidated || "Some attendances were skipped (pending update request).",
            all: m.allValidated || "All selected attendances were validated.",
            done: m.validated || "Validated",
        },
        archive: {
            result: m.archiveResult || "Archive Result",
            warnings: m.archiveWarnings || "Archive Completed with Warnings",
            success: m.archiveSuccessful || "Archive Successful",
            none: m.noneArchived || "Nothing was archived. They could not be archived.",
            some: m.someNotArchived || "Some records could not be archived (in use or not allowed).",
            all: m.allArchived || "All selected records were archived.",
            done: m.archived || "Archived",
        },
        unarchive: {
            result: m.unarchiveResult || "Un-archive Result",
            warnings: m.unarchiveWarnings || "Un-archive Completed with Warnings",
            success: m.unarchiveSuccessful || "Un-archive Successful",
            none: m.noneUnarchived || "Nothing was un-archived. They are already active or could not be restored.",
            some: m.someNotUnarchived || "Some records were skipped (already active or could not be restored).",
            all: m.allUnarchived || "All selected records were un-archived.",
            done: m.unarchived || "Un-archived",
        },
    }[kind] || {
        result: m.deleteResult || "Delete Result",
        warnings: m.deleteWarnings || "Delete Completed with Warnings",
        success: m.deleteSuccessful || "Delete Successful",
        none: m.noneDeleted || "Nothing was deleted. They have related data.",
        some: m.someNotDeleted || "Some records have related data and were not deleted.",
        all: m.allDeleted || "All selected records were deleted.",
        done: m.deleted || "Deleted",
    };
    var total = r.deleted + r.failed;
    var icon, title, text;
    if (total === 0) {
        icon = "info";
        title = words.result;
        text = m.nothingToDelete || "No records were selected.";
    } else if (r.deleted === 0) {
        icon = "warning";
        title = words.result;
        text = words.none;
    } else if (r.failed) {
        icon = "warning";
        title = words.warnings;
        text = words.some;
    } else {
        icon = "success";
        title = words.success;
        text = words.all;
    }
    var card = function (value, label, border, bg, color) {
        return (
            '<div style="flex:1;border:1px solid ' + border + ";background:" + bg +
            ';border-radius:8px;padding:8px 0"><div style="font-size:18px;font-weight:600;color:' + color + '">' +
            value + '</div><div style="font-size:10px;font-weight:500;letter-spacing:.05em;text-transform:uppercase;color:' +
            color + '">' + label + "</div></div>"
        );
    };
    var failedOn = r.failed > 0;
    return Swal.fire({
        title: title,
        icon: icon,
        width: "24rem",
        customClass: { icon: "oh-hlv-result-icon" },
        html:
            '<p style="color:#6b7280;font-size:13px;margin:0">' + text + "</p>" +
            '<div style="display:flex;gap:8px;margin-top:12px">' +
            card(total, m.total || "Total", "#e5e7eb", "#f9fafb", "#1f2937") +
            card(r.deleted, words.done, "#bbf7d0", "#f0fdf4", "#15803d") +
            card(
                r.failed,
                m.failed || "Failed",
                failedOn ? "#fecaca" : "#e5e7eb",
                failedOn ? "#fef2f2" : "#f9fafb",
                failedOn ? "#dc2626" : "#9ca3af"
            ) +
            "</div>",
        confirmButtonText: m.close || "Close",
    });
}

// The outcome a bulk approve / reject view reports in X-Hlv-Bulk-Result, or
// null when it doesn't (those still rely on their own toasts).
function hlvBulkActionResult(xhr) {
    var raw = xhr && xhr.getResponseHeader && xhr.getResponseHeader("X-Hlv-Bulk-Result");
    if (!raw) return null;
    try {
        var r = JSON.parse(raw);
        return { deleted: r.done || 0, failed: r.failed || 0 };
    } catch (e) {
        return null;
    }
}

// Which of `ids` are gone now -> summary dialog. Calls done() once it is
// closed, or straight away if the check itself fails (progress dialog closed).
function hlvBulkDeleteFinish(model, ids, done) {
    var settle = function () {
        if (done) done();
    };
    hlvNativeAjax.call($, {
        type: "POST",
        url: "/existing-ids/",
        data: {
            csrfmiddlewaretoken: getCookie("csrftoken"),
            model: model,
            ids: JSON.stringify(ids),
        },
        success: function (response) {
            var alive = (response.ids || []).length;
            hlvShowBulkDeleteSummary({
                deleted: Math.max(ids.length - alive, 0),
                failed: Math.min(alive, ids.length),
            }).then(settle);
        },
        error: function () {
            Swal.close();
            settle();
        },
    });
}


// ---------------------------------------------------------------------------
// Export progress.
//
// Every export in the project (the export forms, the exports fetched through
// $.ajax as a blob, and the odd direct download link) gets the same
// "Exporting..." dialog, so the user can see something is happening while the
// file is built. Export forms submit natively, so completion is signalled by
// the server: ExportDownloadCookieMiddleware echoes the request's
// `hlv_export_token` back in the `hlv_export_done` cookie once the response is
// a file. Blob requests simply finish with their ajax call.
// ---------------------------------------------------------------------------
var HLV_EXPORT_PATH = /export/i;
var hlvExportTimer = null;

function hlvExportText(msgid, fallback) {
    return typeof gettext === "function" ? gettext(msgid) : fallback;
}

function hlvReadCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
}

// Export forms and links download into a hidden iframe, so the page stays put
// and an error page the server answers with can be told apart from a file: a
// file never fires the iframe's load event (the cookie reports it instead), an
// HTML response does.
var hlvExportFrame = null;
var hlvExportPending = false;

function hlvExportFrameEl() {
    if (!hlvExportFrame && document.body) {
        var frame = document.createElement("iframe");
        frame.name = "hlvExportFrame";
        frame.setAttribute("aria-hidden", "true");
        frame.style.display = "none";
        frame.addEventListener("load", function () {
            if (!hlvExportPending) return;
            var doc = null;
            try {
                doc = frame.contentDocument;
            } catch (err) {
                doc = null;
            }
            if (!doc || !doc.location || doc.location.href === "about:blank") return;
            // A PDF shown inline is still a file; the cookie reports it.
            if (/pdf/i.test(doc.contentType || "")) return;
            var alert = doc.querySelector(".oh-alert-container .oh-alert, .oh-alert");
            var text = alert && alert.textContent.replace(/\s+/g, " ").trim();
            hlvExportFinish();
            hlvExportResult(false, text);
        });
        document.body.appendChild(frame);
        hlvExportFrame = frame;
    }
    return hlvExportFrame;
}
$(hlvExportFrameEl);

// The result dialog, laid out like the bulk delete one. `text` is the reason
// shown on failure (a generic one when the server gave none).
function hlvExportResult(ok, text) {
    if (typeof Swal === "undefined") return;
    var m = hlvMessages();
    Swal.fire({
        title: ok
            ? m.exportSuccessful || hlvExportText("Export Successful", "Export Successful")
            : m.exportFailed || hlvExportText("Export Failed", "Export Failed"),
        icon: ok ? "success" : "error",
        width: "24rem",
        customClass: { icon: "oh-hlv-result-icon" },
        html:
            '<p style="color:#6b7280;font-size:13px;margin:0">' +
            hlvEscape(
                text ||
                    (ok
                        ? hlvExportText("Your file has been exported.", "Your file has been exported.")
                        : hlvExportText("The export failed. Please try again.", "The export failed. Please try again."))
            ) +
            "</p>",
        confirmButtonText: m.close || "Close",
    });
}

function hlvExportFinish() {
    if (hlvExportTimer) {
        clearInterval(hlvExportTimer);
        hlvExportTimer = null;
    }
    hlvExportPending = false;
    document.cookie = "hlv_export_done=; Max-Age=0; path=/";
    if (typeof Swal !== "undefined") {
        var popup = Swal.getPopup && Swal.getPopup();
        if (popup && popup.classList.contains("hlv-export-popup")) Swal.close();
    }
}

// token: the value the server will echo back, or null when the caller ends the
// dialog itself (ajax). The dialog also gives up after three minutes.
function hlvExportStart(token) {
    if (typeof Swal === "undefined") return;
    hlvExportFinish();
    Swal.fire({
        title: hlvExportText("Exporting data", "Exporting data"),
        width: "24rem",
        customClass: { popup: "hlv-export-popup" },
        html:
            '<style>@keyframes hlvSlide{0%{margin-left:-40%}100%{margin-left:100%}}</style>' +
            '<div style="margin:0 0 6px;color:#6b7280;font-size:13px">' +
            hlvExportText("Preparing your file, please wait...", "Preparing your file, please wait...") +
            "</div>" +
            '<div style="height:6px;border-radius:6px;background:#eceef2;overflow:hidden;margin-bottom:18px">' +
            '<div style="width:40%;height:100%;border-radius:6px;background:#e54f38;animation:hlvSlide 1.1s ease-in-out infinite"></div></div>',
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
    });
    hlvExportPending = !!token;
    var started = Date.now();
    hlvExportTimer = setInterval(function () {
        var done = token && hlvReadCookie("hlv_export_done") === token;
        if (done || Date.now() - started > 180000) hlvExportFinish();
        if (done) hlvExportResult(true);
    }, 300);
}

function hlvExportToken() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

// For links / buttons that navigate straight to an export URL.
function hlvDownloadWithProgress(url) {
    var token = hlvExportToken();
    hlvExportStart(token);
    var target = url + (url.indexOf("?") === -1 ? "?" : "&") + "hlv_export_token=" + token;
    var frame = hlvExportFrameEl();
    if (frame) frame.src = target;
    else window.location.href = target;
}

// Capture phase, so this runs before inline onsubmit handlers (some of which
// stop propagation). The token input is only added here; whether the submit
// goes ahead is known once every handler has run.
document.addEventListener(
    "submit",
    function (e) {
        var form = e.target;
        if (!form || form.tagName !== "FORM") return;
        if (form.hasAttribute("data-hlv-quick")) return;
        var action = (form.getAttribute("action") || "").split("?")[0];
        if (!HLV_EXPORT_PATH.test(action)) return;
        if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get")) return;
        if (form.target && form.target !== "_self") return;
        var token = hlvExportToken();
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "hlv_export_token";
        input.value = token;
        form.appendChild(input);
        // Submit into the hidden iframe; the target goes back once every handler
        // has had its say (a native submit happens right after this event).
        var frame = hlvExportFrameEl();
        var oldTarget = form.getAttribute("target");
        if (frame) form.setAttribute("target", frame.name);
        setTimeout(function () {
            input.remove();
            if (frame) {
                if (oldTarget === null) form.removeAttribute("target");
                else form.setAttribute("target", oldTarget);
            }
            if (!e.defaultPrevented) hlvExportStart(token);
        }, 0);
    },
    true
);

// ---------------------------------------------------------------------------
// Export options.
//
// Every export modal gets a "File name" and a "Format" (Excel / CSV / PDF)
// field, and the ones that bundle their filters with the column picker lose the
// filter sections and open the column list. The server side is
// ExportOptionsMiddleware, which renames / converts whatever file the export
// view produced, so no view needs to know about these fields.
// ---------------------------------------------------------------------------
var HLV_EXPORT_OWN_OPTIONS = "[name=format],[name=export_format],[name=export_file_name],[name=file_name],[name=hlv_export_name]";

function hlvExportOptionsHtml(id) {
    // box-sizing + an explicit height: a <select> doesn't reliably honor the
    // same vertical padding as a plain <input> across browsers (its native
    // widget chrome can ignore it), so identical padding alone leaves it
    // visibly shorter than the file name field next to it.
    var field = "width:100%;box-sizing:border-box;height:38px;border:1px solid #e5e7eb;border-radius:6px;padding:8px 10px;font-size:14px;background:#fff;color:#374151;outline:none;";
    var label = "display:block;margin-bottom:4px;font-size:13px;color:#6b7280;";
    return (
        '<div class="hlv-export-options" style="display:grid;grid-template-columns:2fr 1fr;gap:16px;margin:0 0 16px">' +
        "<div>" +
        '<label for="' + id + 'Name" style="' + label + '">' + hlvExportText("File name", "File name") + "</label>" +
        '<input type="text" id="' + id + 'Name" name="hlv_export_name" maxlength="100" autocomplete="off" ' +
        'placeholder="' + hlvExportText("Leave blank for the default name", "Leave blank for the default name") + '" style="' + field + '">' +
        "</div><div>" +
        '<label for="' + id + 'Format" style="' + label + '">' + hlvExportText("Format", "Format") + "</label>" +
        '<select id="' + id + 'Format" name="hlv_export_format" style="' + field + '">' +
        '<option value="xlsx">Excel (.xlsx)</option><option value="csv">CSV (.csv)</option><option value="pdf">PDF (.pdf)</option>' +
        "</select></div></div>"
    );
}

var hlvExportFormSeq = 0;

function hlvEnhanceExportForms(forms) {
    // Idempotent: modal contents are often swapped in after the form itself
    // exists (and swapped again on reopen), so every pass looks at what is
    // there now instead of remembering that a form was already handled.
    $(forms)
        .each(function () {
            var form = this;
            var action = (form.getAttribute("action") || "").split("?")[0];
            if (!HLV_EXPORT_PATH.test(action)) return;
            if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get")) return;
            if (form.target && form.target !== "_self") return;
            var $form = $(form);
            var $submit = $form.find("button:not([type=button]), input[type=submit]").last();
            if (!$submit.length) return;
            // Forms that already ask for a format / file name (the generic list
            // export, the report print dialog, ...) keep their own; they still
            // get the drag-to-reorder handles and hint, just not the injected
            // options row or the accordion/footer restyling below.
            if ($form.find(HLV_EXPORT_OWN_OPTIONS).not("[name=hlv_export_name]").length) {
                hlvAddExportDragHandles(form);
                hlvInitExportSortable(form);
                hlvAddExportHint(form);
                return;
            }

            // Columns only: drop the filter sections that sit next to the column
            // picker and open the picker. (Some forms fill the column list in
            // later, so an accordion with a "select all" box counts too, and
            // failing that the first one.)
            var $sections = $form.find(".oh-accordion");
            var $columns = $sections.filter(function () {
                return $(this).find("input[name=selected_fields], input[id^=select-all]").length > 0;
            });
            if (!$columns.length && $sections.length > 1) $columns = $sections.first();
            // Filter fields are never shown, so they must not block the submit
            // (this includes forms that have filters but no column list).
            if (action.indexOf("work-record") === -1) {
                $sections.not($columns).each(function () {
                    $(this).find("[required]").removeAttr("required");
                });
            }
            if ($columns.length && action.indexOf("work-record") === -1) {
                $sections.not($columns).each(function () {
                    $(this).hide();
                });
                // The column list is all that is left, so show it outright: no
                // "Excel columns" header to fold it away.
                $columns.addClass("oh-accordion--show").children(".oh-accordion-header").hide();
            }

            // Every export ends in the same bottom-right Export button. Some
            // forms leave it loose (or full width); give it the standard footer
            // unless it shares a row with inputs of its own.
            if (!$submit.closest(".oh-dropdown__filter-footer, .oh-modal__dialog-footer").length) {
                if (!$submit.parent().find("input:not([type=hidden]), select, textarea").length) {
                    $submit.wrap('<div class="oh-modal__dialog-footer hlv-export-footer"></div>');
                } else {
                    $submit.addClass("hlv-export-submit");
                }
            }

            // File name + format, above the column list when there is one,
            // otherwise just above the submit button (once per form content).
            if ($form.find("[name=hlv_export_name]").length) {
                hlvAddExportDragHandles(form);
                hlvInitExportSortable(form);
                hlvAddExportHint(form);
                return;
            }
            var id = "hlvExport" + ++hlvExportFormSeq;
            var html = hlvExportOptionsHtml(id);
            var $body = $form.find(".oh-dropdown__filter-body").first();
            if ($body.length) {
                $body.prepend(html);
            } else if ($sections.length) {
                // Before everything the form shows, not just before the first section.
                var $top = $sections.first().parentsUntil($form).last();
                ($top.length ? $top : $sections.first()).before(html);
            } else {
                var $footer = $submit.closest(".oh-dropdown__filter-footer, .oh-modal__dialog-footer");
                ($footer.length ? $footer : $submit).first().before(html);
            }
            hlvAddExportDragHandles(form);
            hlvInitExportSortable(form);
            hlvAddExportHint(form);
        });
}

function hlvColumnPickerRow(form) {
    var row = $(form).find(".row").filter(function () {
        return $(this).find("input[name=selected_fields]").length > 0;
    }).first();
    return row.length ? row : null;
}

// Fields that are selected by default (department, email, ...) belong at the
// top of the list, ahead of the ones the user would have to opt into, so the
// export order (and the picker itself) reads as "what's included" first. Only
// worth doing before any drag handle exists: once the row has been through
// the enhancer, its order is either that default or something the user
// dragged, and either way a later pass must leave it alone.
function hlvSortExportFieldsBySelected(form) {
    var $row = hlvColumnPickerRow(form);
    if (!$row || $row.find(".hlv-export-drag-handle").length) return;
    var checked = [];
    var unchecked = [];
    $row.children().each(function () {
        var $checkbox = $(this).find("input[name=selected_fields]");
        if (!$checkbox.length) return;
        if ($checkbox.is(":checked")) checked.push(this);
        else unchecked.push(this);
    });
    if (checked.length && unchecked.length) {
        $row.append(checked);
        $row.append(unchecked);
    }
}

function hlvAddExportDragHandles(form) {
    var $row = hlvColumnPickerRow(form);
    if (!$row) return;
    hlvSortExportFieldsBySelected(form);
    $row.children().each(function () {
        var $item = $(this);
        if (!$item.find("input[name=selected_fields]").length) return;
        if ($item.find(".hlv-export-drag-handle").length) return;
        var $target = $item.find(".oh-input-group").first();
        if (!$target.length) $target = $item;
        $target.prepend(
            '<span class="hlv-export-drag-handle" title="' +
            hlvExportText("Drag to reorder", "Drag to reorder") +
            '"><ion-icon name="reorder-two-outline"></ion-icon></span>'
        );
    });
    hlvUpdateExportOrder(form);
}

// Numbers each checked field with its position in the export (1, 2, 3, ...),
// in the current drag order, so dragging doesn't leave the user guessing
// where a field landed relative to the others. Unchecked fields -- not part
// of the export -- get no number.
function hlvUpdateExportOrder(form) {
    var $row = hlvColumnPickerRow(form);
    if (!$row) return;
    var n = 0;
    $row.children().each(function () {
        var $item = $(this);
        var $checkbox = $item.find("input[name=selected_fields]");
        if (!$checkbox.length) return;
        var $group = $item.find(".oh-input-group").first();
        if (!$group.length) $group = $item;
        var $badge = $group.find(".hlv-export-order-badge");
        if (!$badge.length) {
            $badge = $('<span class="hlv-export-order-badge"></span>');
            var $handle = $group.find(".hlv-export-drag-handle").first();
            if ($handle.length) $badge.insertAfter($handle);
            else $group.prepend($badge);
        }
        if ($checkbox.is(":checked")) {
            n += 1;
            $badge.text(n).css("display", "");
        } else {
            $badge.css("display", "none");
        }
    });
}

function hlvInitExportSortable(form) {
    var $row = hlvColumnPickerRow(form);
    if (!$row || !$row.is(":visible") || !$.fn.sortable) return;
    if ($row.data("ui-sortable")) {
        $row.sortable("refresh");
        return;
    }
    $row.sortable({
        handle: ".hlv-export-drag-handle",
        items: "> div:has(input[name=selected_fields])",
        placeholder: "hlv-export-drag-placeholder",
        tolerance: "pointer",
        update: function () {
            hlvUpdateExportOrder(form);
        },
    }).disableSelection();
}

$(document).on("change", "input[name=selected_fields]", function () {
    hlvUpdateExportOrder(this.form);
});

function hlvAddExportHint(form) {
    var $form = $(form);
    if ($form.find(".hlv-export-hint").length) return;
    if (!hlvColumnPickerRow(form)) return;
    var $anchor = $form.find("input[id^=select-all]").first().closest(".row");
    if (!$anchor.length) $anchor = hlvColumnPickerRow(form);
    $anchor.before(
        '<p class="hlv-export-hint"><ion-icon name="reorder-two-outline"></ion-icon><span>' +
        hlvExportText("Drag the fields to rearrange the column order before exporting", "Drag the fields to rearrange the column order before exporting") +
        "</span></p>"
    );
}


$(document).on("click", "[data-toggle='oh-modal-toggle']", function () {
    setTimeout(function () {
        $("form[action*='export' i]").each(function () {
            hlvAddExportDragHandles(this);
            hlvInitExportSortable(this);
            hlvAddExportHint(this);
        });
    }, 0);
});

// Hide the filter sections and the "Excel columns" header from the first paint
// (the enhancer below also does it, but this needs no script round trip).
// :has() keeps the column list itself, which is the accordion holding the
// column checkboxes.
(function () {
    var cols = 'input[name="selected_fields"], input[id^="select-all"]';
    var form = 'form[action*="export" i]';
    // The work-record export's "Date Range" is the thing being exported, not an
    // optional filter, so its section is never hidden.
    var hideForm = form + ':not([action*="work-record"])';
    var style = document.createElement("style");
    var picker = ".row:has(input[name=selected_fields])";
    style.id = "hlv-uniform-export";
    style.textContent =
        // filters and the "Excel columns" header go; the column list stays
        hideForm + " .oh-accordion:not(:has(" + cols + ")){display:none!important}" +
        hideForm + " .oh-accordion:has(" + cols + ")>.oh-accordion-header{display:none!important}" +
        hideForm + " .oh-accordion:has(" + cols + ")>.oh-accordion-body{display:block!important}" +
        // one look for every export modal: same width, three-column picker,
        // Export button bottom right
        ".oh-modal__dialog:has(.hlv-export-options){max-width:880px!important;width:100%}" +
        form + " " + picker + "{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 16px;margin:0!important}" +
        form + " " + picker + ">[class*=col-]{width:auto!important;max-width:none!important;flex:none!important;padding:0!important}" +
        form + " .oh-dropdown__filter-footer," + form + " .oh-modal__dialog-footer{display:flex!important;justify-content:flex-end;padding:0!important;margin:16px 0 0!important;border:0!important}" +
        form + " .oh-dropdown__filter-footer button:not([type=button])," + form + " .oh-modal__dialog-footer button:not([type=button]){width:auto!important;min-width:110px;margin:0!important}" +
        form + " button.hlv-export-submit{display:block!important;width:auto!important;min-width:110px;margin:16px 0 0 auto!important}" +
        "@media (max-width:640px){" + form + " " + picker + "{grid-template-columns:minmax(0,1fr)}" +
        ".hlv-export-options{grid-template-columns:minmax(0,1fr)!important}}" +

        form + " " + picker + ">div .oh-input-group{display:flex!important;align-items:center;gap:6px}" +
        ".hlv-export-drag-handle{cursor:grab;color:#9ca3af;display:inline-flex;flex-shrink:0}" +
        ".hlv-export-order-badge{flex-shrink:0;min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:#e5e7eb;color:#4b5563;font-size:11px;line-height:18px;text-align:center;font-weight:600}" +
        ".hlv-export-hint{display:flex;align-items:center;gap:6px;margin:0 0 8px;font-size:12px;color:#9ca3af}" +
        ".hlv-export-hint ion-icon{font-size:14px;flex-shrink:0}" +
        ".hlv-export-drag-placeholder{border:1px dashed #d1d5db;border-radius:6px;visibility:visible!important}" +
        picker + ">div.ui-sortable-helper{background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.12);border-radius:6px}";
    document.head.appendChild(style);
})();

// Export forms arrive later (htmx modals, tab content) and are rebuilt when a
// modal is reopened. A MutationObserver callback runs right after the swap and
// before the browser paints, so the options are in place before anything shows.
function hlvExportFormsIn(node) {
    var found = [];
    if (node.nodeType !== 1) return found;
    var own = node.closest && node.closest("form");
    if (own) found.push(own);
    if (node.querySelectorAll) found.push.apply(found, node.querySelectorAll("form"));
    return found;
}
$(function () {
    hlvEnhanceExportForms(document.querySelectorAll("form"));
    new MutationObserver(function (mutations) {
        var forms = [];
        mutations.forEach(function (m) {
            Array.prototype.forEach.call(m.addedNodes, function (n) {
                forms.push.apply(forms, hlvExportFormsIn(n));
            });
        });
        if (forms.length) hlvEnhanceExportForms(forms.filter(function (f, i) { return forms.indexOf(f) === i; }));
    }).observe(document.body, { childList: true, subtree: true });
});

// ---------------------------------------------------------------------------
// Quick exports.
//
// Many list pages export with a "Do you want to download the excel file?"
// prompt followed by an ajax request for a blob, and name the downloaded file
// themselves. Those get the same export dialog as the export modals (file name,
// format, column picker) without touching each page:
//   * the prompt is answered automatically (the dialog below replaces it),
//   * the blob request is first sent with `hlv_export_probe`, which makes
//     ExportOptionsMiddleware answer with the file's column headings (and keep
//     the file for a few minutes),
//   * after the user picks, the same request is repeated with the choices
//     (`hlv_export_use` picks the kept file up, so the export isn't run twice),
//   * and the download is saved here, under the chosen name, instead of by the
//     page's own success handler (which would use its own name and format).
// Anything the probe can't describe (not an xlsx) runs the old way.
// ---------------------------------------------------------------------------
function hlvAddParams(data, extra) {
    if (typeof data === "string") {
        return data + (data ? "&" : "") + $.param(extra);
    }
    if (typeof FormData !== "undefined" && data instanceof FormData) {
        var copy = new FormData();
        data.forEach(function (value, key) { copy.append(key, value); });
        Object.keys(extra).forEach(function (key) { copy.append(key, extra[key]); });
        return copy;
    }
    return $.extend({}, data, extra);
}

function hlvEscape(text) {
    return $("<div>").text(text).html();
}

function hlvDownloadName(xhr, fallback) {
    var header = (xhr && xhr.getResponseHeader && xhr.getResponseHeader("Content-Disposition")) || "";
    var match = header.match(/filename\*=UTF-8''([^;]+)/i) || header.match(/filename="?([^";]+)"?/i);
    if (!match) return fallback;
    try {
        return decodeURIComponent(match[1]);
    } catch (e) {
        return match[1];
    }
}

function hlvSaveBlob(blob, xhr, fallbackName) {
    var type = (xhr && xhr.getResponseHeader && xhr.getResponseHeader("Content-Type")) || blob.type;
    var url = URL.createObjectURL(new Blob([blob], { type: type }));
    var link = document.createElement("a");
    link.href = url;
    link.download = hlvDownloadName(xhr, fallbackName);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
}

// The same markup as the export modals (an .oh-modal with a form), so it sits in
// the same place and the shared export styling applies. Resolves with
// {name, format, columns: [positions]} or null when closed.
function hlvExportDialog(info) {
    return new Promise(function (resolve) {
        var id = "hlvQuick" + ++hlvExportFormSeq;
        var boxes = info.columns
            .map(function (label, index) {
                return (
                    '<div class="col-sm-12 col-md-6 col-lg-4"><div class="oh-input-group"><label class="oh-label">' +
                    '<input type="checkbox" class="hlv-quick-col" name="selected_fields" value="' + index + '" checked> ' +
                    hlvEscape(label) + "</label></div></div>"
                );
            })
            .join("");
        var $modal = $(
            '<div class="oh-modal oh-modal--show" id="' + id + 'Modal" role="dialog" aria-hidden="false">' +
            '<div class="oh-modal__dialog">' +
            '<div class="oh-modal__dialog-header">' +
            '<h2 class="oh-modal__dialog-title">' + hlvExportText("Export", "Export") + "</h2>" +
            '<button type="button" class="oh-modal__close" aria-label="' + hlvExportText("Close", "Close") + '"><ion-icon name="close-outline"></ion-icon></button>' +
            "</div>" +
            '<div class="oh-modal__dialog-body">' +
            // data-hlv-quick: never submitted, the handler below takes over
            '<form action="#export" data-hlv-quick="1">' +
            hlvExportOptionsHtml(id) +
            '<div class="row"><div class="col-sm-12 col-md-12 col-lg-12"><div class="oh-input-group"><label class="oh-label">' +
            '<input type="checkbox" id="select-all-' + id + '" checked> ' + hlvExportText("Select All", "Select All") + "</label></div></div></div>" +
            '<div class="row">' + boxes + "</div>" +
            '<div class="oh-dropdown__filter-footer"><button type="submit" class="oh-btn oh-btn--secondary oh-btn--small">' +
            hlvExportText("Export", "Export") + "</button></div>" +
            "</form></div></div></div>"
        );
        var finish = function (value) {
            $modal.remove();
            $(document).off("keydown.hlvQuick");
            resolve(value);
        };
        $modal.find(".oh-modal__close").on("click", function () { finish(null); });
        $modal.on("mousedown", function (e) { if (e.target === this) finish(null); });
        $(document).on("keydown.hlvQuick", function (e) { if (e.key === "Escape") finish(null); });
        $modal.find("#select-all-" + id).on("change", function () {
            $modal.find(".hlv-quick-col").prop("checked", this.checked);
        });
        $modal.find("[name=hlv_export_name]").val(info.filename || "");
        $modal.find("form").on("submit", function (e) {
            e.preventDefault();
            var columns = $modal.find(".hlv-quick-col:checked").map(function () { return parseInt(this.value, 10); }).get();
            if (!columns.length) {
                $modal.find("#select-all-" + id).closest(".row").after(
                    '<p class="hlv-quick-error" style="color:#dc2626;font-size:13px;margin:0 0 8px">' +
                    hlvExportText("Select at least one column", "Select at least one column") + "</p>"
                );
                $modal.find(".hlv-quick-error").slice(1).remove();
                return;
            }
            finish({
                name: $modal.find("[name=hlv_export_name]").val(),
                format: $modal.find("[name=hlv_export_format]").val(),
                columns: columns,
                all: columns.length === info.columns.length,
            });
        });
        $("body").append($modal);
    });
}

function hlvQuickExport(opts) {
    var base = $.extend({}, opts);
    delete base.success;
    delete base.error;
    delete base.complete;
    delete base.xhrFields;
    var plain = function () {
        // The old behaviour: the page's own handlers, with just the progress dialog.
        hlvExportStart(null);
        return hlvNativeAjax.call($, $.extend({}, opts, {
            __hlvPlain: true,
            complete: [function (xhr, status) {
                hlvExportFinish();
                if (status !== "abort") hlvExportResult(status === "success");
            }].concat(opts.complete || []),
        }));
    };
    hlvExportStart(null);
    return hlvNativeAjax
        .call($, $.extend({}, base, { data: hlvAddParams(opts.data, { hlv_export_probe: 1 }), dataType: "json" }))
        .then(
            function (info) {
                hlvExportFinish();
                if (!info || !info.columns || !info.columns.length) return plain();
                return hlvExportDialog(info).then(function (choice) {
                    if (!choice) return;
                    hlvExportStart(null);
                    var extra = {
                        hlv_export_use: info.token,
                        hlv_export_name: choice.name,
                        hlv_export_format: choice.format,
                    };
                    if (!choice.all) extra.hlv_export_columns = JSON.stringify(choice.columns);
                    hlvNativeAjax.call($, $.extend({}, base, {
                        __hlvPlain: true,
                        data: hlvAddParams(opts.data, extra),
                        dataType: opts.dataType,
                        xhrFields: opts.xhrFields,
                        success: function (blob, status, xhr) {
                            hlvSaveBlob(blob, xhr, (choice.name || info.filename || "export") + "." + choice.format);
                            hlvExportResult(true);
                        },
                        error: function () {
                            hlvExportResult(false);
                        },
                        complete: [function () { hlvExportFinish(); }].concat(opts.complete || []),
                    }));
                });
            },
            function () {
                hlvExportFinish();
                return plain();
            }
        );
}

// The prompt the quick exports start with is answered for them; see above.
$(function () {
    if (typeof Swal === "undefined" || Swal.__hlvQuickExportHook) return;
    var original = Swal.fire;
    Swal.__hlvQuickExportHook = true;
    Swal.fire = function (options) {
        var prompt = hlvMessages().downloadExcel;
        if (prompt && options && typeof options === "object" && options.text === prompt) {
            return Promise.resolve({ isConfirmed: true, isDenied: false, isDismissed: false, value: true });
        }
        return original.apply(this, arguments);
    };
});

// Disabled action buttons do nothing. A disabled <button> already swallows its
// click; links styled as disabled (.oh-btn--disabled / aria-disabled) would
// otherwise navigate (href="#" jumps / reloads) or let the click reach the
// row behind them (which opens its detail modal).
document.addEventListener(
    "click",
    function (e) {
        var el = e.target && e.target.closest && e.target.closest(".oh-btn--disabled, a[aria-disabled='true']");
        if (!el) return;
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
    },
    true
);

var hlvNativeAjax = $.ajax;
$.ajax = function (url, settings) {
    var opts = url && typeof url === "object" ? url : $.extend({}, settings, { url: url });
    var type = String(opts.type || opts.method || "GET").toUpperCase();
    if (type === "POST" && hlvIsBulkSelectionAction(opts.url)) {
        var postedIds = hlvBulkDeleteIds(opts.data);
        var pageSuccess = opts.success;
        // Runs ahead of the page's own success callback (often a reload).
        opts = $.extend({}, opts, {
            success: [function () { hlvDropSelectedIds(postedIds); }].concat(pageSuccess || []),
        });
    }
    // Exports fetched as a blob get the shared export dialog (see "Quick exports").
    var isBlobRequest =
        (opts.xhrFields && opts.xhrFields.responseType === "blob") || opts.dataType === "binary";
    if (isBlobRequest && HLV_EXPORT_PATH.test(String(opts.url || "").split("?")[0])) {
        if (opts.__hlvPlain) return hlvNativeAjax.call($, opts);
        return hlvQuickExport(opts);
    }
    var kind = type === "POST" ? hlvBulkActionKind(opts.url) : null;
    if (kind) {
        // Progress dialog, then the result dialog when the view reports counts
        // (X-Hlv-Bulk-Result). All of the page's own callbacks (success, error,
        // complete) wait until that dialog is closed, in their usual order, so
        // a reload or dialog they trigger doesn't cut it short.
        var ready = null;
        var wrap = function (fns, xhrIndex) {
            return function () {
                var self = this, args = arguments;
                if (!ready) {
                    var result = hlvBulkActionResult(args[xhrIndex]);
                    if (result) {
                        ready = hlvShowBulkDeleteSummary(result, kind);
                    } else {
                        Swal.close();
                        ready = Promise.resolve();
                    }
                }
                ready.then(function () {
                    [].concat(fns || []).forEach(function (f) {
                        if (typeof f === "function") f.apply(self, args);
                    });
                });
            };
        };
        hlvBulkActionProgress(kind, hlvBulkDeleteIds(opts.data).length);
        return hlvNativeAjax.call(
            $,
            $.extend({}, opts, {
                success: wrap(opts.success, 2), // (data, status, xhr)
                error: wrap(opts.error, 0), // (xhr, status, err)
                complete: wrap(opts.complete, 0), // (xhr, status)
            })
        );
    }
    var model = type === "POST" ? hlvBulkDeleteModel(opts.url) : null;
    var ids = model ? hlvBulkDeleteIds(opts.data) : [];
    if (!model || !ids.length) return hlvNativeAjax.apply(this, arguments);

    var ctx = opts.context || opts;
    var call = function (fns, args) {
        [].concat(fns || []).forEach(function (fn) {
            if (typeof fn === "function") fn.apply(ctx, args);
        });
    };
    // The page's own callbacks run later, once the result dialog is closed.
    // They must be deleted, not set to undefined: $.extend skips undefined
    // values, so the originals would otherwise stay and fire straight away
    // (typically a location.reload() that cuts the dialogs short).
    var wrapped = $.extend({}, opts, {
        headers: $.extend({}, opts.headers, { "X-Hlv-Bulk-Delete": "1" }),
    });
    delete wrapped.success;
    delete wrapped.error;
    delete wrapped.complete;
    hlvBulkDeleteProgress(ids.length);
    var jq = hlvNativeAjax.call($, wrapped);
    jq.then(
        function (data, status, xhr) {
            hlvBulkDeleteFinish(model, ids, function () {
                call(opts.success, [data, status, xhr]);
                call(opts.complete, [xhr, status]);
            });
        },
        function (xhr, status, err) {
            hlvBulkDeleteFinish(model, ids, function () {
                call(opts.error, [xhr, status, err]);
                call(opts.complete, [xhr, status]);
            });
        }
    );
    return jq;
};

// The same for htmx-driven bulk deletes (hx-post on a form / span).
document.addEventListener("htmx:configRequest", function (e) {
    var cfg = e.detail;
    if (String(cfg.verb).toLowerCase() === "post" && hlvBulkDeleteModel(cfg.path)) {
        cfg.headers["X-Hlv-Bulk-Delete"] = "1";
    }
});
document.addEventListener("htmx:beforeRequest", function (e) {
    var cfg = e.detail.requestConfig || {};
    var kind = String(cfg.verb).toLowerCase() === "post" ? hlvBulkActionKind(cfg.path) : null;
    if (kind) {
        e.detail.xhr.__hlvProgress = kind;
        hlvBulkActionProgress(kind, hlvBulkDeleteIds(cfg.parameters).length);
        return;
    }
    var model = String(cfg.verb).toLowerCase() === "post" ? hlvBulkDeleteModel(cfg.path) : null;
    var ids = model ? hlvBulkDeleteIds(cfg.parameters) : [];
    if (!model || !ids.length) return;
    e.detail.xhr.__hlvBulkDelete = { model: model, ids: ids };
    hlvBulkDeleteProgress(ids.length);
});
document.addEventListener("htmx:afterRequest", function (e) {
    var req = e.detail.requestConfig || {};
    if (
        e.detail.successful &&
        String(req.verb).toLowerCase() === "post" &&
        hlvIsBulkSelectionAction(req.path)
    ) {
        hlvDropSelectedIds(hlvBulkDeleteIds(req.parameters));
    }
    if (e.detail.xhr && e.detail.xhr.__hlvProgress) {
        var result = hlvBulkActionResult(e.detail.xhr);
        if (result) hlvShowBulkDeleteSummary(result, e.detail.xhr.__hlvProgress);
        else Swal.close();
    }
    var job = e.detail.xhr && e.detail.xhr.__hlvBulkDelete;
    if (job) hlvBulkDeleteFinish(job.model, job.ids);
});
