/*
 * File drop zones
 *
 * Every plain <input type="file"> in a form is upgraded to the dashed
 * "Choose or Drop Files Here" box, so every upload field in the app looks and
 * behaves the same. It is progressive enhancement -- no template needs to opt
 * in -- and it also covers forms that htmx swaps in later (modals, tabs).
 *
 * The real input stays in the DOM, stretched invisibly over the box. That keeps
 * everything native: click-to-browse, drag-and-drop, `required` validation,
 * `accept`, `multiple`, hx-* attributes and form submission are untouched.
 *
 * Inputs that already have their own picker are left alone: ones hidden by the
 * page (display:none / opacity:0 / positioned overlays), the import dialogs'
 * `.oh-dropdown__import-label` zone, Summernote's dialogs, and anything marked
 * with `data-hz-nodz`.
 */
(function () {
  "use strict";

  var I18N = {
    single: "Choose or Drop a File Here",
    multiple: "Choose or Drop Files Here",
    remove: "Remove",
  };
  var custom = window.HZ_FILE_DROP_I18N || {};
  Object.keys(custom).forEach(function (key) {
    if (custom[key]) I18N[key] = custom[key];
  });

  var SKIP_INSIDE =
    ".hz-file-drop, .oh-dropdown__import-form, .oh-dropdown__import-label, " +
    ".note-modal, .note-editor, .note-dialog, [data-hz-nodz]";

  var ICON =
    '<svg class="hz-file-drop__icon" fill="none" stroke="currentColor" stroke-width="2" ' +
    'viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" ' +
    'stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1M12 12V4m0 0l4 4m-4-4L8 8"/></svg>';

  function shouldSkip(input) {
    if (input.dataset.hzDz) return true;
    if (input.hidden || input.hasAttribute("data-hz-nodz")) return true;
    if (input.closest(SKIP_INSIDE)) return true;
    // An input already inside a <label> is the label's own custom trigger.
    if (input.closest("label")) return true;
    var cs = window.getComputedStyle(input);
    // The page hides the real input and draws its own picker.
    if (cs.display === "none" || parseFloat(cs.opacity) === 0) return true;
    if (cs.position === "absolute" || cs.position === "fixed") return true;
    return false;
  }

  function sizeLabel(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return Math.round(bytes / 1024) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function enhance(input) {
    if (shouldSkip(input)) return;
    input.dataset.hzDz = "1";

    var wrap = document.createElement("div");
    wrap.className = "hz-file-drop-wrap";
    var zone = document.createElement("div");
    zone.className = "hz-file-drop";
    var text = document.createElement("span");
    text.className = "hz-file-drop__text";
    text.textContent = input.multiple ? I18N.multiple : I18N.single;
    var files = document.createElement("div");
    files.className = "hz-file-drop__files";

    input.parentNode.insertBefore(wrap, input);
    zone.insertAdjacentHTML("beforeend", ICON);
    zone.appendChild(text);
    zone.appendChild(input);
    wrap.appendChild(zone);
    wrap.appendChild(files);
    if (input.disabled) zone.classList.add("is-disabled");

    function render() {
      files.textContent = "";
      var list = input.files ? Array.prototype.slice.call(input.files) : [];
      zone.classList.toggle("has-files", list.length > 0);
      list.forEach(function (file, index) {
        var chip = document.createElement("span");
        chip.className = "hz-file-drop__file";
        var name = document.createElement("span");
        name.className = "hz-file-drop__name";
        name.textContent = file.name;
        name.title = file.name + " (" + sizeLabel(file.size) + ")";
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "hz-file-drop__remove";
        remove.setAttribute("aria-label", I18N.remove + " " + file.name);
        remove.innerHTML = "&times;";
        remove.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          if (typeof DataTransfer === "undefined") {
            input.value = "";
          } else {
            var keep = new DataTransfer();
            list.forEach(function (f, i) {
              if (i !== index) keep.items.add(f);
            });
            input.files = keep.files;
          }
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
        chip.appendChild(name);
        chip.appendChild(remove);
        files.appendChild(chip);
      });
    }

    input.addEventListener("change", render);
    if (input.form) {
      input.form.addEventListener("reset", function () {
        setTimeout(render, 0);
      });
    }
    // Other scripts that clear the input programmatically can ask for a redraw.
    input.addEventListener("hz:filedrop-refresh", render);

    // The input itself receives the drop (it covers the box); these only
    // drive the highlight.
    ["dragenter", "dragover"].forEach(function (name) {
      zone.addEventListener(name, function () {
        if (!input.disabled) zone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      zone.addEventListener(name, function () {
        zone.classList.remove("is-dragover");
      });
    });

    render();
  }

  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    if (root.matches && root.matches('input[type="file"]')) enhance(root);
    var inputs = root.querySelectorAll
      ? root.querySelectorAll('input[type="file"]:not([data-hz-dz])')
      : [];
    Array.prototype.forEach.call(inputs, enhance);
  }

  function start() {
    scan(document.body);
    new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        Array.prototype.forEach.call(mutation.addedNodes, scan);
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
