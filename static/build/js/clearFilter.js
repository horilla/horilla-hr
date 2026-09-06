var formButton = "#applyFilter";

function clearFilterFromTag(element) {
	let form = $(formButton).closest('form');
	let search_url = form.attr("hx-get") || "";
	let urlParts = search_url.split('?');
	let baseUrl = urlParts[0];
	let field_id = element.attr("data-x-field");

	if (urlParts.length > 1) {
		let params = new URLSearchParams(urlParts[1]);
		let keysToRemove = [];
		for (let key of params.keys()) {
			let is_in_form = form.find('[name]').filter(function () { return this.name === key; }).length > 0;
			if (key === field_id || is_in_form) {
				keysToRemove.push(key);
			}
		}
		for (let key of keysToRemove) {
			params.delete(key);
		}
		let newParams = params.toString();
		form.attr("hx-get", newParams ? baseUrl + '?' + newParams : baseUrl);
	} else {
		form.attr("hx-get", baseUrl);
	}

	// field_id can match several elements at once (e.g. "nested_fields" with
	// multiple active grouping levels) -- .change() fires once per matched
	// element, and each one's own onchange handler self-submits via
	// formButton, so disable it here too so only the real click below runs
	// (see clearAllFilter's own comment for why this matters).
	$(formButton).prop("disabled", true);
	// val("") is a no-op on checkboxes/radios (it doesn't touch .checked) --
	// the modern filter panel's checkbox-list/segmented-toggle fields need
	// the checked state itself cleared, not just the value attribute.
	$(`[name=${field_id}]`).filter(':checkbox, :radio').prop('checked', false);
	$(`[name=${field_id}]`).not(':checkbox, :radio').val("");
	$(`[name=${field_id}]`).change();
	// horilla_nav.html's "N filters applied" badge (updateFilterCountBadge)
	// recomputes on most field-level change events already, but a cleared
	// text input fires "change" here while that badge listener only binds
	// "input" for text fields (to debounce the actual filter submit) --
	// called explicitly so a text-backed filter (Phone, a custom-filter
	// text row, ...) doesn't leave a stale count after being cleared this
	// way. Guarded since this file can load on pages without that panel.
	if (typeof updateFilterCountBadge === "function") updateFilterCountBadge();
	// Update all elements with the same ID to have null values
	let elementId = $(`[name=${field_id}]:last`).attr("id");
	let spanElement = $(
		`.oh-dropdown__filter-body:first #select2-id_${field_id}-container, #select2-${elementId}-container`
	);
	if (spanElement.length) {
		spanElement.attr("title", "---------");
		spanElement.text("---------");
	}
	$(formButton).prop("disabled", false);
	$(formButton).click();
}

function clearAllFilter(element) {
	$('[role="tooltip"]').remove();
	let form = $(formButton).closest('form');
	let search_url = form.attr("hx-get") || "";
	form.attr("hx-get", search_url.split('?')[0]);

	// Some fields (e.g. the nested group-by level selects) have their own
	// onchange handler that immediately clicks formButton to self-submit.
	// With several same-named fields active (multiple grouping levels),
	// each one's change below fires its OWN premature submit mid-loop,
	// before the rest of the fields have been cleared -- those requests
	// race the real, fully-cleared submit at the end of this function, and
	// whichever response lands last wins, which can leave stale filters
	// showing even though every field was in fact reset. Disabling the
	// button makes those premature clicks (and any others triggered by a
	// field's change handler) no-ops -- disabled form controls don't fire
	// click events, per the DOM spec -- so only the real submit below runs.
	$(formButton).prop("disabled", true);

	// Reset every field's value, not just strip a query string — the active
	// filter (e.g. a "group by" field) is saved server-side and reapplied
	// based on the form's OWN current values when it's actually submitted,
	// so a bare reload here left the fields (and the saved filter) unchanged.
	form.find('[name]').each(function () {
		// See clearFilterFromTag's comment: val("") doesn't uncheck
		// checkboxes/radios, so the checked state has to be reset directly.
		if ($(this).is(':checkbox, :radio')) {
			$(this).prop('checked', false);
		} else {
			$(this).val("");
		}
		$(this).change();
	});
	$('.oh-dropdown__filter-body [id^="select2-"][id$="-container"]').each(function () {
		$(this).attr("title", "---------");
		$(this).text("---------");
	});
	// See clearFilterFromTag's comment above -- cleared text inputs fire
	// "change" here, which the badge's own listener doesn't cover.
	if (typeof updateFilterCountBadge === "function") updateFilterCountBadge();

	$(formButton).prop("disabled", false);
	$(formButton).click();
	localStorage.removeItem("savedFilters");
}
