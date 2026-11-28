/**
 * tourController.js
 *
 * Loads tours from the server for the current page, auto-starts any pending
 * auto-start tour, and exposes window.horillaTour.toggle() so the "?" navbar
 * button can open/close the launcher panel.
 *
 * Depends on:
 *   - driver.js  (already on window.driver.js.driver)
 *   - window.HORILLA_TOUR  set by footer_scripts.html (its optional `docs`
 *     entry adds a Documentation link below the tours)
 */
(function () {
  'use strict';

  var CFG = window.HORILLA_TOUR || {};
  if (!CFG.activeUrl) return;

  var driverFactory = window.driver && window.driver.js && window.driver.js.driver;
  if (!driverFactory) return;

  var _tours = [];
  var _driverInst = null;
  var _panel = null;
  var _fetched = false;

  // ── CSRF ──────────────────────────────────────────────────────────────────

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  // ── Progress reporting ────────────────────────────────────────────────────

  function postProgress(tourId, status, lastStep) {
    var fd = new FormData();
    fd.append('tour_id', tourId);
    fd.append('status', status);
    if (lastStep !== undefined) fd.append('last_step', lastStep);
    fd.append('csrfmiddlewaretoken', csrfToken());
    fetch(CFG.progressUrl, { method: 'POST', body: fd }).catch(function () {});
  }

  // ── Run a tour ────────────────────────────────────────────────────────────

  function runTour(tour) {
    if (_driverInst) {
      _driverInst.destroy();
      _driverInst = null;
    }
    closePanel();

    postProgress(tour.id, 'in_progress', 0);

    var steps = (tour.steps || []).map(function (s) {
      return {
        element: s.element || undefined,
        popover: {
          title: s.title,
          description: s.description,
          side: s.side || 'bottom',
          align: s.align || 'start',
        },
      };
    });

    if (!steps.length) return;

    _driverInst = driverFactory({
      animate: true,
      allowClose: tour.allow_close !== false,
      showProgress: tour.show_progress !== false,
      steps: steps,
      onDestroyStarted: function (el, step, opts) {
        var idx = opts.state.activeIndex;
        var isLast = typeof idx === 'number' && idx >= steps.length - 1;
        var status = isLast ? 'completed' : 'skipped';
        postProgress(tour.id, status, idx);
        if (_driverInst) {
          _driverInst.destroy();
          _driverInst = null;
        }
        if (isLast) {
          // Remove pending dot for this tour
          var dot = document.querySelector('#tourLauncherBtn span.absolute');
          if (dot) dot.remove();
        }
      },
    });

    _driverInst.drive(0);
  }

  // ── Fetch tours from API ──────────────────────────────────────────────────

  function fetchTours() {
    // Always use the live pathname so HTMX navigation is accounted for.
    // Send page='' so the server resolves the URL name from the path itself
    // (tour_active view already has that fallback via django.urls.resolve).
    var params = new URLSearchParams({
      page: '',
      path: window.location.pathname,
    });
    return fetch(CFG.activeUrl + '?' + params.toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.ok ? r.json() : { tours: [] }; })
      .then(function (data) {
        _tours = data.tours || [];
        _fetched = true;
        return _tours;
      })
      .catch(function () {
        _tours = [];
        _fetched = true;
        return [];
      });
  }

  // ── Launcher panel ────────────────────────────────────────────────────────

  function buildPanel() {
    if (_panel) return _panel;

    var btn = document.getElementById('tourLauncherBtn');
    if (!btn) return null;
    var wrapper = btn.closest('.dropdown-wrapper');
    if (!wrapper) return null;

    _panel = document.createElement('div');
    _panel.id = 'tourLauncherPanel';
    _panel.style.cssText = [
      'display:none',
      'position:absolute',
      'right:0',
      'top:calc(100% + 8px)',
      'min-width:220px',
      'max-width:280px',
      'background:#fff',
      'border:1px solid #e5e7eb',
      'border-radius:8px',
      'box-shadow:0 10px 25px rgba(0,0,0,.12)',
      'z-index:9999',
      'overflow:hidden',
    ].join(';');

    wrapper.style.position = 'relative';
    wrapper.appendChild(_panel);

    document.addEventListener('click', function (e) {
      if (!_panel) return;
      var btn2 = document.getElementById('tourLauncherBtn');
      if (btn2 && btn2.contains(e.target)) return;
      closePanel();
    });

    return _panel;
  }

  function renderPanel(tours) {
    var panel = buildPanel();
    if (!panel) return;
    panel.innerHTML = '';

    // Header
    var hdr = document.createElement('div');
    hdr.style.cssText = 'padding:10px 12px 8px;border-bottom:1px solid #f3f4f6;font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;';
    hdr.textContent = 'Product Tours';
    panel.appendChild(hdr);

    if (!tours.length) {
      var empty = document.createElement('div');
      empty.style.cssText = 'padding:20px 16px;font-size:12px;color:#9ca3af;text-align:center;';
      empty.textContent = 'No tours available for this page.';
      panel.appendChild(empty);
      renderDocs(panel);
      return;
    }

    var list = document.createElement('ul');
    list.style.cssText = 'list-style:none;margin:0;padding:4px 0;';

    tours.forEach(function (tour) {
      var li = document.createElement('li');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = [
        'width:100%',
        'text-align:left',
        'display:flex',
        'align-items:center',
        'gap:10px',
        'padding:9px 12px',
        'background:none',
        'border:none',
        'cursor:pointer',
        'font-size:13px',
        'color:#374151',
        'transition:background .15s',
      ].join(';');
      btn.onmouseover = function () { btn.style.background = '#f0f9ff'; };
      btn.onmouseout = function () { btn.style.background = 'none'; };

      var iconEl = document.createElement('ion-icon');
      iconEl.setAttribute('name', tour.icon || 'map-outline');
      iconEl.style.cssText = 'font-size:16px;color:#2563eb;flex-shrink:0;';

      var labelEl = document.createElement('span');
      labelEl.style.cssText = 'line-height:1.3;';
      labelEl.textContent = tour.title;

      btn.appendChild(iconEl);
      btn.appendChild(labelEl);

      // Pending dot
      if (tour.auto_start && tour.status !== 'completed' && tour.status !== 'skipped') {
        var dot = document.createElement('span');
        dot.style.cssText = 'width:7px;height:7px;border-radius:50%;background:#16a34a;margin-left:auto;flex-shrink:0;';
        btn.appendChild(dot);
      }

      btn.addEventListener('click', function () { runTour(tour); });
      li.appendChild(btn);
      list.appendChild(li);
    });

    panel.appendChild(list);
    renderDocs(panel);
  }

  // Link to the user guide, under its own header below the tours.
  function renderDocs(panel) {
    var docs = CFG.docs;
    if (!docs || !docs.url) return;

    var hdr = document.createElement('div');
    hdr.style.cssText = 'padding:10px 12px 8px;border-top:1px solid #f3f4f6;border-bottom:1px solid #f3f4f6;font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;';
    hdr.textContent = docs.heading;
    panel.appendChild(hdr);

    var link = document.createElement('a');
    link.href = docs.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.style.cssText = 'display:flex;align-items:center;gap:10px;margin:4px 0;padding:9px 12px;font-size:13px;color:#374151;text-decoration:none;transition:background .15s;';
    link.onmouseover = function () { link.style.background = '#f0f9ff'; };
    link.onmouseout = function () { link.style.background = 'none'; };

    var iconEl = document.createElement('ion-icon');
    iconEl.setAttribute('name', 'open-outline');
    iconEl.style.cssText = 'font-size:16px;color:#2563eb;flex-shrink:0;';

    var labelEl = document.createElement('span');
    labelEl.style.cssText = 'line-height:1.3;';
    labelEl.textContent = docs.label;

    link.appendChild(iconEl);
    link.appendChild(labelEl);
    panel.appendChild(link);
  }

  function openPanel() {
    var panel = buildPanel();
    if (!panel) return;
    panel.style.display = 'block';
    // Always re-fetch: path may have changed via HTMX since last open
    panel.innerHTML = '<div style="padding:16px;font-size:12px;color:#9ca3af;text-align:center;">Loading…</div>';
    fetchTours().then(function (tours) { renderPanel(tours); });
  }

  function closePanel() {
    if (_panel) _panel.style.display = 'none';
  }

  // ── Public API ────────────────────────────────────────────────────────────

  window.horillaTour = {
    toggle: function () {
      var panel = _panel;
      if (!panel || panel.style.display === 'none') {
        openPanel();
      } else {
        closePanel();
      }
    },
    start: function (tourIdOrSlug) {
      var t = _tours.find(function (x) { return x.id === tourIdOrSlug || x.slug === tourIdOrSlug; });
      if (t) runTour(t);
    },
  };

  // ── Boot ──────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    fetchTours().then(function (tours) {
      // Auto-start: first tour with auto_start flag set by the server
      var auto = tours.find(function (t) { return t.auto_start; });
      if (auto) {
        setTimeout(function () { runTour(auto); }, 500);
      }
    });
  });
})();
