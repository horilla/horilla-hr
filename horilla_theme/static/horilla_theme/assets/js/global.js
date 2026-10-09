// Shared by permission/group tab fragments (base/templates/base/auth/*, employee/templates/cbv/allocations/auth/*).
// Defined globally so it's available regardless of which htmx fragment loads first, since several of
// those fragments call checkSelected() without defining it themselves.
function checkSelected(names, target, initial = false) {
  names = JSON.parse(`${names}`);
  $.each(names, function (indexInArray, valueOfElement) {
    if (!initial) {
      $(target).find(`[value=${valueOfElement}]`).prop("checked", true).change();
    } else {
      $(target).find(`[value=${valueOfElement}]`).prop("checked", true);
    }
  });
  if (typeof refreshPermPicker === "function") {
    var $picker = $(target).closest("[data-perm-picker]");
    if (!$picker.length) {
      $picker = $(target).find("[data-perm-picker]");
    }
    if ($picker.length) {
      refreshPermPicker($picker);
    }
  }
}

// CUSTOM MODAL
document.addEventListener("DOMContentLoaded", () => {
  // Open modal
  document.querySelectorAll("[data-modal-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-modal-open");
      const modal = document.getElementById(modalId);
      const box = modal.querySelector(".modal-box");

      modal.classList.remove("hidden");
      modal.classList.add("modal-active"); // ✅ Add this
      setTimeout(() => {
        box.classList.remove("opacity-0", "scale-95");
        box.classList.add("opacity-100", "scale-100");
      }, 10);
    });
  });

  // Close modal
  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-modal-close");
      const modal = document.getElementById(modalId);
      const box = modal.querySelector(".modal-box");

      box.classList.remove("opacity-100", "scale-100");
      box.classList.add("opacity-0", "scale-95");

      setTimeout(() => {
        modal.classList.add("hidden");
        modal.classList.remove("modal-active"); // ✅ Remove here
      }, 300);
    });
  });
});


// CUSTOM DROPDOWN
document.addEventListener("DOMContentLoaded", () => {
  // Toggle dropdowns
  document.querySelectorAll(".dropdown-toggle").forEach((toggle) => {
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      // Close other dropdowns
      document.querySelectorAll(".dropdown-menu").forEach((menu) => {
        if (!menu.closest(".dropdown-wrapper").contains(this)) {
          menu.classList.add("hidden");
        }
      });
      // Toggle this one
      const menu =
        this.closest(".dropdown-wrapper").querySelector(".dropdown-menu");
      menu.classList.toggle("hidden");
    });
  });

  // Close dropdowns when clicking outside. Scoped to this component's own
  // ".dropdown-wrapper .dropdown-menu" convention (matching the toggle
  // logic above) — other components on the page reuse the bare
  // ".dropdown-menu" class name for their own, unrelated dropdowns (e.g.
  // the pipeline tab bar's "Actions" kebab uses ".dropdown-wrapper-tab"),
  // and closing those too on every click anywhere broke them.
  document.addEventListener("click", () => {
    document.querySelectorAll(".dropdown-wrapper .dropdown-menu").forEach((menu) => {
      menu.classList.add("hidden");
    });
  });
});

window.registerAutoRefresh = function (intervalId) {
  window._activeAutoRefreshTimers = window._activeAutoRefreshTimers || [];
  window._activeAutoRefreshTimers.push(intervalId);
};

// Skip a periodic refresh while the tab is hidden.
//
// Dashboard auto-refresh is on by default and each tick fans out to ~14
// endpoint calls, so a dashboard left open on a second monitor keeps issuing
// requests indefinitely with nobody reading them. That is wasted server work
// everywhere, and on per-second-billed hosting it also keeps the container
// from ever scaling to zero: the traffic looks like real usage.
//
// Callers still tick on their own schedule; this only decides whether the
// work runs. When the tab becomes visible again we refresh once immediately,
// so a returning user sees current data instead of waiting out the interval.
window.autoRefreshWhenVisible = function (fn) {
  var missedWhileHidden = false;

  if (!window._autoRefreshVisibilityBound) {
    window._autoRefreshVisibilityBound = true;
    window._autoRefreshOnVisible = [];
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible") return;
      var pending = window._autoRefreshOnVisible || [];
      for (var i = 0; i < pending.length; i++) {
        try {
          pending[i]();
        } catch (e) {
          /* one dashboard's refresh must not break the others */
        }
      }
    });
  }

  window._autoRefreshOnVisible.push(function () {
    if (!missedWhileHidden) return;
    missedWhileHidden = false;
    fn();
  });

  return function () {
    if (document.visibilityState === "hidden") {
      missedWhileHidden = true;
      return;
    }
    fn();
  };
};

$(function () {
  $("#ohMainContent").on("htmx:beforeSwap", function () {
    $.each(window._activeAutoRefreshTimers || [], function (i, id) {
      clearInterval(id);
    });
    window._activeAutoRefreshTimers = [];
  });
});

// SIDEBARModal DSESIGN
document.addEventListener("DOMContentLoaded", () => {
  // Toggle any sidebar based on data-sidebar attribute
  document.querySelectorAll(".toggleSidemenu").forEach((button) => {
    button.addEventListener("click", () => {
      const sidebarId = button.getAttribute("data-sidebar");
      const sidebar = document.getElementById(sidebarId);
      if (sidebar) {
        sidebar.classList.toggle("active");
        document.body.classList.toggle("overflow-hidden");
      }
    });
  });

  // Close any sidebar based on data-sidebar attribute
  document.querySelectorAll(".closeSidemenu").forEach((button) => {
    button.addEventListener("click", () => {
      const sidebarId = button.getAttribute("data-sidebar");
      const sidebar = document.getElementById(sidebarId);
      if (sidebar) {
        sidebar.classList.remove("active");
        document.body.classList.remove("overflow-hidden");
      }
    });
  });
});



// IMPORT DROP ZONES
// Every `.oh-dropdown__import-label` (the "Upload a File" box in the import
// modals across modules) becomes click-to-browse + drag-and-drop, and shows
// the chosen file name. Delegated, so it also covers htmx-loaded modals.
(function () {
  function findInput(label) {
    if (label.htmlFor) {
      var byId = document.getElementById(label.htmlFor);
      if (byId && byId.type === "file") return byId;
    }
    var scope = label.closest(".oh-dropdown__import-form") || label.parentElement;
    var input = scope && scope.querySelector('input[type="file"]');
    if (!input) {
      var form = label.closest("form");
      input = form && form.querySelector('input[type="file"]');
    }
    return input;
  }
  function labelFor(input) {
    var scope = input.closest(".oh-dropdown__import-form") || input.parentElement;
    var labels = scope ? scope.querySelectorAll(".oh-dropdown__import-label") : [];
    for (var i = 0; i < labels.length; i++) {
      if (findInput(labels[i]) === input) return labels[i];
    }
    return null;
  }
  function showFile(input) {
    var label = labelFor(input);
    if (!label) return;
    var title = label.querySelector(".oh-dropdown__import-form-title");
    var hint = label.querySelector(".oh-dropdown__import-form-text");
    if (!label._origTitle && title) {
      label._origTitle = title.textContent;
      label._origHint = hint ? hint.textContent : "";
    }
    var file = input.files && input.files[0];
    label.classList.toggle("oh-import-has-file", !!file);
    if (title) title.textContent = file ? file.name : label._origTitle;
    if (hint) hint.textContent = file ? "Click or drop another file to replace" : label._origHint;
  }
  document.addEventListener("click", function (e) {
    var label = e.target.closest && e.target.closest(".oh-dropdown__import-label");
    if (!label) return;
    var input = findInput(label);
    if (!input) return;
    e.preventDefault();
    input.click();
  });
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches('input[type="file"]')) showFile(e.target);
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var label = e.target.closest && e.target.closest(".oh-dropdown__import-label");
      if (!label) return;
      e.preventDefault();
      label.classList.add("oh-import-drag");
    });
  });
  document.addEventListener("dragleave", function (e) {
    var label = e.target.closest && e.target.closest(".oh-dropdown__import-label");
    if (label) label.classList.remove("oh-import-drag");
  });
  document.addEventListener("drop", function (e) {
    var label = e.target.closest && e.target.closest(".oh-dropdown__import-label");
    if (!label) return;
    e.preventDefault();
    label.classList.remove("oh-import-drag");
    var input = findInput(label);
    if (input && e.dataTransfer && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
})();
