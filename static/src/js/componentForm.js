/*
 * Allowance / Deduction form behaviour.
 *
 * Replaces static/build/js/allowanceWidget.js and deductionWidget.js on these
 * two forms. Those are checked-in build artefacts with no source file, so every
 * new amount type meant hand-editing generated jQuery — and because they only
 * recognised the amount types that existed when they were generated, anything
 * added since fell into an `else` branch that hid the rate box. Selecting
 * "Percentage of another component" left nowhere to type the percentage.
 *
 * Three jobs:
 *   1. progressive disclosure, declared in markup as data-show-if
 *   2. the repeating condition rows
 *   3. the formula builder popover
 *
 * Everything is resolved against the field's own <form>. The list page renders
 * a filter panel whose inputs carry the same names as the form's (based_on,
 * is_fixed), and it comes first in the document, so a document-wide lookup
 * reads the filter instead.
 */
(function () {
  "use strict";

  // The form is swapped in by HTMX, which re-runs this file's <script src> on
  // every open. Without this, each open adds another set of document
  // listeners and one click on "Add condition" appends a row per open.
  if (window.horillaComponentForm) {
    window.horillaComponentForm();
    return;
  }

  var SHOW_IF = "[data-show-if]";

  function formOf(el) {
    return (el && el.closest && el.closest("form")) || document;
  }

  // The token lives on <body hx-headers>, which is how this app hands it to
  // HTMX — there is no csrfmiddlewaretoken input in these forms to read, so
  // looking for one silently produced a 403 and an empty panel.
  function csrfToken() {
    try {
      var headers = JSON.parse(document.body.getAttribute("hx-headers") || "{}");
      if (headers["X-CSRFToken"]) return headers["X-CSRFToken"];
    } catch (err) {
      /* not JSON; fall through to the cookie */
    }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
  }


  function valueOf(field) {
    if (!field) return null;
    if (field.type === "checkbox") return field.checked ? "on" : "off";
    if (field.type === "radio") {
      var picked = (field.form || document).querySelector(
        "[name='" + field.name + "']:checked"
      );
      return picked ? picked.value : "";
    }
    return field.value;
  }

  // "is_fixed=off based_on=component|formula" — every clause must hold.
  function satisfied(form, spec) {
    return spec
      .split(/\s+/)
      .filter(Boolean)
      .every(function (clause) {
        var split = clause.indexOf("=");
        if (split === -1) return true;
        var name = clause.slice(0, split);
        var wanted = clause.slice(split + 1).split("|");
        var field = form.querySelector("[name='" + name + "']");
        // One layout serves both forms, so a rule can name a field only one of
        // them has. Treat that clause as inapplicable rather than false: the
        // condition rows are gated on include_active_employees, which exists on
        // Allowance and not on Deduction, and returning false here hid them on
        // every deduction.
        if (!field) return true;
        return wanted.indexOf(valueOf(field)) !== -1;
      });
  }

  function sync(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(SHOW_IF).forEach(function (el) {
      // A rule inside a repeating row has to read that row's own inputs. Every
      // row carries the same field names, so resolving against the form would
      // make all of them follow whichever row came first.
      var within =
        el.dataset.showScope === "row"
          ? el.closest("[data-apply-row]") || formOf(el)
          : formOf(el);
      el.hidden = !satisfied(within, el.dataset.showIf);
    });
    // A heading with nothing visible under it is noise: "Upper limit" sat
    // alone above the next section whenever the amount was fixed.
    //
    // The rows are the heading's SIBLINGS, not its children — everything has to
    // be a direct child of the Bootstrap .row — so they are matched by key. The
    // first version queried inside the heading, found nothing, and therefore
    // never hid anything.
    scope.querySelectorAll("[data-section]").forEach(function (heading) {
      var key = heading.dataset.section;
      if (!key) return;
      var rows = formOf(heading).querySelectorAll(
        '[data-section-of="' + key + '"]'
      );
      var anyVisible = Array.prototype.some.call(rows, function (row) {
        return !row.hidden;
      });
      heading.hidden = rows.length > 0 && !anyVisible;
    });
  }

  /* --------------------------------------------------------------- steps */

  function stepKeys(form) {
    return Array.prototype.map.call(
      form.querySelectorAll("[data-step-panel]"),
      function (panel) { return panel.dataset.stepPanel; }
    );
  }

  function currentStep(form) {
    var open = form.querySelector("[data-step-panel]:not([hidden])");
    return open ? open.dataset.stepPanel : stepKeys(form)[0];
  }

  function showStep(form, key) {
    var keys = stepKeys(form);
    if (keys.indexOf(key) === -1) return;
    var position = keys.indexOf(key);

    form.querySelectorAll("[data-step-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.stepPanel !== key;
    });
    form.querySelectorAll("[data-step-tab]").forEach(function (tab) {
      var at = keys.indexOf(tab.dataset.stepTab);
      tab.classList.toggle("is-current", tab.dataset.stepTab === key);
      // "Done" means walked past, not validated — the form is checked on the
      // server in one go, so claiming a step is complete would be a guess.
      tab.classList.toggle("is-done", at < position);
      tab.setAttribute("aria-selected", tab.dataset.stepTab === key);
    });

    var back = form.querySelector("[data-step-back]");
    var next = form.querySelector("[data-step-next]");
    if (back) back.hidden = position === 0;
    if (next) next.hidden = position === keys.length - 1;

    // The modal scrolls, not the panel, so a step change has to bring the top
    // of the form back into view or step two opens halfway down.
    var body = form.closest(".oh-modal__dialog-body") || form;
    if (body.scrollTo) body.scrollTo({top: 0, behavior: "smooth"});
  }

  function moveStep(form, delta) {
    var keys = stepKeys(form);
    var position = keys.indexOf(currentStep(form));
    showStep(form, keys[Math.min(Math.max(position + delta, 0), keys.length - 1)]);
  }

  // Errors come back from the server against fields that may be on a step that
  // is not showing, so the form would look unchanged and simply not save.
  function flagStepsWithErrors(form) {
    var firstBad = null;
    form.querySelectorAll("[data-step-panel]").forEach(function (panel) {
      var bad = panel.querySelector(".errorlist, .error, [id$='_error']");
      var tab = form.querySelector(
        '[data-step-tab="' + panel.dataset.stepPanel + '"]'
      );
      var flag = tab && tab.querySelector("[data-step-flag]");
      if (flag) flag.hidden = !bad;
      if (bad && !firstBad) firstBad = panel.dataset.stepPanel;
    });
    return firstBad;
  }

  function startSteps(form) {
    if (!form.querySelector("[data-step-panel]")) return;
    var bad = flagStepsWithErrors(form);
    showStep(form, bad || currentStep(form) || stepKeys(form)[0]);
  }

  /* ---------------------------------------------------------------- rows */

  function addRow(button, templateSelector, containerSelector) {
    var form = formOf(button);
    var template = form.querySelector(templateSelector);
    var container = form.querySelector(containerSelector);
    if (!template || !container) return;

    var row = template.content.firstElementChild.cloneNode(true);
    container.appendChild(row);
    initSelect2(row);
    // A fresh row starts with whatever its own selects default to, so its
    // amount and range boxes have to be resolved before it is shown.
    sync(row);
  }

  function addConditionRow(button) {
    addRow(button, "[data-condition-template]", "[data-condition-rows]");
  }

  function initSelect2(scope) {
    if (!window.jQuery || !window.jQuery.fn.select2) return;
    window.jQuery(scope)
      .find("select")
      .each(function () {
        var $select = window.jQuery(this);
        if ($select.data("select2")) return;
        $select.select2({ dropdownParent: $select.parent(), width: "100%" });
      });
  }

  /* ------------------------------------------------------------- formula */

  function openFormula(button) {
    // Which builder, by the field it writes to. The Deduction form carries
    // two -- the component's own amount and the employer's share -- so the
    // first popover in the form is no longer the right answer.
    var name = button.getAttribute("data-open-formula") || "formula";
    var popover = formOf(button).querySelector(
      '[data-formula-popover="' + name + '"]'
    );
    if (!popover) return;
    popover.dataset.opened = "1";
    popover.hidden = false;
    var search = popover.querySelector("[data-formula-search]");
    if (search) search.focus();
  }

  function closeFormula(el) {
    var popover = el.closest && el.closest("[data-formula-popover]");
    if (!popover) return;
    popover.hidden = true;
    describeFormula(formOf(popover));
  }

  function closeAnyOpenFormula() {
    document
      .querySelectorAll("[data-formula-popover]:not([hidden])")
      .forEach(function (popover) {
        popover.hidden = true;
        describeFormula(formOf(popover));
      });
  }

  // The one-line summary shown on the form itself while the popover is shut.
  // One per formula field, each reading its own.
  function describeFormula(form) {
    form.querySelectorAll("[data-formula-summary]").forEach(function (summary) {
      var name = summary.getAttribute("data-formula-summary") || "formula";
      var field = form.querySelector("[name='" + name + "']");
      if (!field) return;
      var text = (field.value || "").trim();
      summary.textContent = text || summary.dataset.empty || "";
      summary.classList.toggle("is-empty", !text);
    });
  }

  /* ---------------------------------------------------------- limit note */

  // The worked figures come from the server, which runs the same period_factor
  // a payslip runs. Repeating the arithmetic here would produce a note that
  // agrees with payroll right up until the day it does not.
  var noteTimers = new WeakMap();

  function refreshLimitNote(form) {
    var note = form.querySelector("[data-limit-note]");
    var body = form.querySelector("[data-limit-note-body]");
    if (!note || !body) return;

    var unit = form.querySelector("[name='maximum_unit']");
    var url = note.dataset.url;
    if (!unit || !url) return;

    // Which figure the basis actually applies to. A fixed amount is scaled
    // directly; otherwise only a ceiling is, because a percentage already
    // follows the period through whatever it is a percentage of.
    var fixed = form.querySelector("[name='is_fixed']");
    var capped = form.querySelector("[name='has_max_limit']");
    var source = null;
    if (fixed && fixed.checked) {
      source = form.querySelector("[name='amount']");
    } else if (capped && capped.checked) {
      source = form.querySelector("[name='maximum_amount']");
    }

    if (!source) {
      body.innerHTML =
        '<span class="oh-limit-note__muted">' + (note.dataset.nothing || "") + "</span>";
      return;
    }

    var value = (source.value || "").trim();
    if (value === "") {
      body.innerHTML =
        '<span class="oh-limit-note__muted">' + (note.dataset.empty || "") + "</span>";
      return;
    }

    var payload = new FormData();
    payload.append("maximum_amount", value);
    payload.append("maximum_unit", unit.value || "");

    fetch(url, {
      method: "POST",
      body: payload,
      headers: {
        "X-CSRFToken": csrfToken(),
        "HX-Request": "true"
      }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          body.innerHTML =
            '<span class="oh-limit-note__muted">' + (data.error || "") + "</span>";
          return;
        }
        body.innerHTML = data.rows
          .map(function (row) {
            var share =
              data.flat || row.factor === 1
                ? ""
                : ' <span class="oh-limit-note__share">(&times;' +
                  row.factor.toLocaleString(undefined, {maximumFractionDigits: 4}) +
                  ")</span>";
            return (
              '<div class="oh-limit-note__row">' +
              '<span class="oh-limit-note__label">' + row.label + "</span>" +
              '<span class="oh-limit-note__dots"></span>' +
              '<span class="oh-limit-note__value">' +
              row.amount.toLocaleString(undefined, {
                minimumFractionDigits: 2, maximumFractionDigits: 2
              }) +
              "</span>" + share +
              "</div>"
            );
          })
          .join("");
      })
      .catch(function () { /* the note is an aid, not a gate */ });
  }

  function scheduleLimitNote(form) {
    clearTimeout(noteTimers.get(form));
    noteTimers.set(form, setTimeout(function () { refreshLimitNote(form); }, 300));
  }

  /* --------------------------------------------------------------- wiring */

  function wire() {
    sync();
    document.querySelectorAll("[data-steps]").forEach(function (rail) {
      startSteps(formOf(rail));
    });
    // Belt and braces for the builder starting open: the panel's display:flex
    // beats the [hidden] attribute unless the stylesheet overrides it, and a
    // builder covering the form is worse than one that takes a click to reach.
    document.querySelectorAll("[data-formula-popover]").forEach(function (popover) {
      if (!popover.dataset.opened) popover.hidden = true;
    });
    // Not "form:has(...)": :has() is recent enough that a browser without it
    // would throw here and take the whole file down with it.
    document.querySelectorAll("[data-formula-summary]").forEach(function (el) {
      describeFormula(formOf(el));
    });
    document.querySelectorAll("[data-limit-note]").forEach(function (el) {
      refreshLimitNote(formOf(el));
    });
  }

  var LIMIT_FIELDS = [
    "amount", "maximum_amount", "maximum_unit", "has_max_limit", "is_fixed"
  ];

  document.addEventListener("change", function (e) {
    if (!e.target || !e.target.form) return;
    sync(e.target.form);
    if (LIMIT_FIELDS.indexOf(e.target.name) !== -1) {
      scheduleLimitNote(e.target.form);
    }
  });
  document.addEventListener("input", function (e) {
    if (
      e.target &&
      (e.target.name === "maximum_amount" || e.target.name === "amount") &&
      e.target.form
    ) {
      scheduleLimitNote(e.target.form);
    }
  });
  document.addEventListener("input", function (e) {
    if (
      e.target &&
      (e.target.name === "formula" || e.target.name === "employer_formula")
    ) {
      describeFormula(formOf(e.target));
    }
  });

  document.addEventListener("click", function (e) {
    var reset = e.target.closest("[data-reset-after-save]");
    if (reset) pendingReset = reset.form;

    var tab = e.target.closest("[data-step-tab]");
    if (tab) {
      e.preventDefault();
      showStep(formOf(tab), tab.dataset.stepTab);
      return;
    }
    var next = e.target.closest("[data-step-next]");
    if (next) {
      e.preventDefault();
      moveStep(formOf(next), 1);
      return;
    }
    var back = e.target.closest("[data-step-back]");
    if (back) {
      e.preventDefault();
      moveStep(formOf(back), -1);
      return;
    }

    var addApply = e.target.closest("[data-add-apply]");
    if (addApply) {
      e.preventDefault();
      addRow(addApply, "[data-apply-template]", "[data-apply-rows]");
      return;
    }
    var removeApply = e.target.closest("[data-remove-apply]");
    if (removeApply) {
      e.preventDefault();
      var applyRow = removeApply.closest("[data-apply-row]");
      if (applyRow) applyRow.remove();
      return;
    }

    var add = e.target.closest("[data-add-condition]");
    if (add) {
      e.preventDefault();
      addConditionRow(add);
      return;
    }
    var remove = e.target.closest("[data-remove-condition]");
    if (remove) {
      e.preventDefault();
      var row = remove.closest("[data-condition-row]");
      if (row) row.remove();
      return;
    }
    var open = e.target.closest("[data-open-formula]");
    if (open) {
      e.preventDefault();
      openFormula(open);
      return;
    }
    var close = e.target.closest("[data-close-formula]");
    if (close) {
      e.preventDefault();
      closeFormula(close);
      return;
    }
    // Clicking the dimmed area outside the panel closes it too.
    if (e.target.hasAttribute && e.target.hasAttribute("data-formula-backdrop")) {
      e.preventDefault();
      closeFormula(e.target);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAnyOpenFormula();
  });

  // select2 and the oh-switch toggle change fields through jQuery, whose
  // .trigger("change") never reaches a native listener.
  if (window.jQuery) {
    window
      .jQuery(document)
      .on("change select2:select", "form :input", function () {
        sync(formOf(this));
      });
  }

  // "Save and add another" clears the form for the next one. This lived in an
  // hx-on attribute on the button, where it could not be read or reused.
  //
  // Recorded on click rather than read off the afterRequest event: the form
  // carries hx-post, so htmx fires the event on the form and the submitting
  // button is not reachable from it.
  var pendingReset = null;

  document.body.addEventListener("htmx:afterRequest", function (e) {
    var form = pendingReset;
    pendingReset = null;
    if (!form || !e.detail || !e.detail.successful) return;
    form.reset();
    if (window.jQuery) window.jQuery(form).find("select").val(null).trigger("change");
    sync(form);
    describeFormula(form);
    ["#reloadMessagesButton", ".reload-record", ".reload-field"].forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (el) { el.click(); });
    });
  });

  window.horillaComponentForm = wire;

  document.addEventListener("htmx:afterSettle", wire);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
