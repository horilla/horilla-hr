# Changelog

All notable changes to Horilla HR are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file starts at **2.1.1**, the first release maintained in this format. Releases
before it are documented on the
[releases page](https://github.com/horilla/horilla-hr/releases) and are not reproduced
here — they predate this convention and back-filling them would misrepresent how they
were recorded at the time.

Each released version corresponds to a git tag of the same name (bare semver, no `v`
prefix) and to the Docker tag `horilla/horilla-hr:<version>`. `horilla/__version__.py`
is the single source of truth; the release workflow refuses to publish an image whose
tag disagrees with it.

## [Unreleased]

<!--
Add entries here as you merge, under the headings below. Drop any heading you
do not use. At release time, rename this section to the new version with its
date and open a fresh Unreleased above it.

### Breaking      — requires action from an existing installation before or on upgrade
### Added         — new features
### Changed       — changes to existing behaviour
### Deprecated    — soon-to-be-removed features
### Removed        — features removed in this release
### Fixed         — bug fixes
### Security      — vulnerabilities fixed; link the advisory and credit the reporter
-->

## [2.1.8] — 2026-09-26

Security release. **Upgrade from any 2.x — this closes an unauthenticated
remote code execution flaw.** All five issues below are reachable without
administrative privileges; the RCE needs no account at all.

### Security

| Advisory | Severity | Issue |
|---|---|---|
| [GHSA-x567-v324-7mr2](https://github.com/horilla/horilla-hr/security/advisories/GHSA-x567-v324-7mr2) | High | Unauthenticated remote code execution: the public recruitment application/survey flow let an anonymous visitor upload a `.py` file into an importable path, and the automation `get-to-mail-field` endpoint `__import__()`-ed a request-supplied module path, so a stored `<img>` auto-fetched by any recruiter's browser executed it as the server process |
| [GHSA-23vp-5g5x-mh2x](https://github.com/horilla/horilla-hr/security/advisories/GHSA-23vp-5g5x-mh2x) | High | Three `/api/attendance/` mail endpoints took the target `employee_id` from the request body under an unscoped "manages anyone" check, letting any reporting manager read any employee's PII, list every mail template, and send attacker-controlled HTML from the company SMTP identity to any employee |
| [GHSA-j3hc-6v4r-j658](https://github.com/horilla/horilla-hr/security/advisories/GHSA-j3hc-6v4r-j658) | Medium | The web check-in/out views did not enforce the configured geofence that the mobile/API flow already applied, so an employee outside the permitted area could punch in from a browser |
| [GHSA-r59f-4xh4-58cf](https://github.com/horilla/horilla-hr/security/advisories/GHSA-r59f-4xh4-58cf) | Medium | The web attendance office-IP restriction trusted the first `X-Forwarded-For` value, which the client controls, so an employee off the office network could spoof an allowed address |

With thanks to **@AlbertoFDR**, **@Ntn10** (with **@CARLOS1994ROMERO**), and
**@nanuzn** for reporting these responsibly.

**The RCE chain is cut at two independent points.** The candidate-survey upload
now rejects executable Python extensions (`.py`/`.pyc`/…), and the automation
model resolver no longer imports a caller-supplied path — it matches only
against Django's already-registered models, so a file placed on disk can never
be imported or executed through it.

**The attendance mail endpoints now name their target.**
`converted-mail-template` and `offline-employee-mail-send` use the
instance-scoped `manager_or_owner_permission_required` (the decorator the
pk-routed attendance endpoints already use), and `mail-templates` requires
`base.view_horillamailtemplate` — the same permission its web list view uses —
instead of "manages anyone".

**Web attendance enforces the same controls as the API.** Check-in/out now
apply the configured geofence (failing closed when the fence is enabled but the
location cannot be verified) and resolve the client IP with the trusted-proxy
bound `django-axes` already uses, honoring `X-Forwarded-For` only up to the
configured proxy count.

Also hardened: manager-only leave views (approve/reject/edit/delete/read) are
now scoped to the employee the caller actually manages rather than to any
reporting manager.

### Added

- REST: a `pending_approvals` count in the mobile home aggregate, reject-reason
  storage on request rejections, and a reimbursement `status` filter.
- REST: line managers can approve/reject reimbursements and reject asset
  requests for their own reports.
- REST: announcement list now respects its audience and gained a detail endpoint.
- Attendance dashboard: a tile for employees who missed a punch, and an
  "On Time" KPI filter.

### Fixed

- Work-type request create/approve no longer return `400` after saving the record.
- Leave ledger entries are dated by the local calendar rather than UTC.
- `Reimbursement.delete()` no longer raises `UnboundLocalError` on a pending claim.
- `EmployeeWorkInformationAPIView` no longer `500`s on its own list route.
- Leave overlap check ignores cancelled and rejected requests.
- Asset return-fine action is gated by configuration and permission.

### Changed

- Modern dashboard styling refresh (badge colors, KPI cards); the Open
  Recruitments KPI card was removed.
- PMS objective, meeting and task views restyled; objective templates excluded
  from the Assigned/All Objectives lists.

## [2.1.7] — 2026-09-16

Bug-fix release, and the first to carry a **security fix**: archiving an
employee did not revoke their login. Anyone offboarded by archiving since 2.1.x
kept working credentials — see below for what to check after upgrading.

One migration, `notifications.0003`, **drops five columns**. Read the Changed
section before upgrading.

### Security

- **Archiving an employee did not revoke their login.**
  ([#1239](https://github.com/horilla/horilla-hr/issues/1239), reported by
  **@Safeer1877**) Archiving removed the employee from every list and left the
  linked user account active, so an offboarded person could still sign in with
  every permission they held. Two faults masked each other: the user's flag was
  assigned the employee's *previous* value, and the user object was never saved
  — so nothing was written either way. The login gate is
  `HorillaUser.is_active`, which `CompanyScopedBackend` inherits from
  `ModelBackend` and which knows nothing about `Employee.is_active`.

  Affected the three archive views **and both REST API archive endpoints**
  (`EmployeeBulkArchiveView`, `EmployeeArchiveView`), which were outside the
  original report.

  **After upgrading**, check for user accounts that are still active while
  their employee record is archived — the fix corrects future archives but
  does not retroactively disable accounts archived before it. Clearing
  `is_active` also stops future logins without invalidating a session already
  in flight.

- **Three CRITICAL CVEs in the container's `perl-base`**
  (CVE-2026-13221, CVE-2026-42496, CVE-2026-8376). The image installed
  packages without first upgrading what the base image already carried, so a
  published Debian security patch was never picked up. The build now upgrades
  before installing.

### Fixed

- **Password reset emails linked to `example.com`.**
  ([#1241](https://github.com/horilla/horilla-hr/issues/1241), reported by
  **@KerelOlivier**) The link was built from `django.contrib.sites`, whose only
  row on a normal install is the framework's own default — and which Horilla
  never updates. Reset links now use the request host, matching what
  leave-request mail already did. The host is taken from `request.get_host()`,
  which is validated against `ALLOWED_HOSTS`; deployments behind a proxy should
  set `USE_X_FORWARDED_HOST` rather than have an unvalidated forwarded header
  steer a link that grants account access.

- **Creating a payslip returned a 500 after the payslip had been saved.**
  ([#1238](https://github.com/horilla/horilla-hr/issues/1238), reported by
  **@Safeer1877**) The redirect used a URL name belonging to an argument-less
  list view, so it raised `NoReverseMatch` *after* the payslip was committed.
  The obvious response — clicking Create again — produced a duplicate for the
  same employee and period. Also affected adding a bonus and a deduction.

- **Unpaid leave was deducted twice** when `deduct_leave_from_basic_pay` is
  enabled, which is the model default.
  ([#1225](https://github.com/horilla/horilla-hr/issues/1225), reported by
  **@Safeer1877**) The loss of pay came out of basic pay and again out of net
  pay, so the employee was underpaid by exactly the LOP amount.

- **The version shown in the UI said 2.1.5** on installs built from `2.0`
  after 2.1.6, because an unrelated commit reverted the version module.

- Numerous URL, HTMX-request and error-handling fixes across Asset,
  Attendance, Base, Leave, Offboarding, PMS and Project, including a
  `RelatedObjectDoesNotExist` when work information is absent and a duplicate
  key error on some URLs.

### Changed

- **Notification text now uses Django's native i18n** rather than storing one
  column per language. `notifications.0003` **removes the `verb_ar`,
  `verb_de`, `verb_en`, `verb_es` and `verb_fr` columns**, and that is not
  reversible: any text stored in them is dropped. Notifications are translated
  at render time from the base `verb` instead. Take a database backup before
  upgrading if those columns matter to you.

- Dependency updates, including `djangorestframework` 3.17.2 → 3.18.1 and
  `sentry-sdk` 2.20.0 → 2.69.1.

## [2.1.6] — 2026-09-11

Bug-fix release. No security content. One migration, `employee.0006`, which
alters only a field's `choices` and therefore emits no DDL on PostgreSQL — it
exists to put migration state back in step with the models.

### Fixed

- **An internal developer note rendered onto every report page, and into
  generated PDFs.** Django's template lexer is compiled without `re.DOTALL`, so
  a `{# #}` comment spanning lines is not recognised as a comment at all and is
  emitted as literal text. Nine templates shipped that way: all seven explorer
  reports, the standard report letterhead, and `standard_report_pdf.html` —
  the last of which put the note inside the PDFs that get circulated outside
  the company. A repo-wide check now rejects any `{#` left unterminated on its
  own line.

- **The Employee dashboard never loaded its KPIs or charts.**

- **A 500 on the attendance response endpoint.**

- **The self-onboarding portal crashed on its final step.** The account it
  creates is built directly from the portal form rather than through
  `authenticate()`, so it carries no `.backend`. `login()` requires one
  whenever several authentication backends are configured — always true here —
  and raised `ValueError` instead of completing onboarding.

- **Filters bled between lists that share a URL.** The saved-filter cache was
  keyed on path alone, so every pipeline stage embedded at the same path
  (candidate lists, offboarding employees) shared one entry: whichever stage
  wrote last had its filter served back to the others, which then rendered "No
  records found" while their own tab badge showed the correct count. The key
  now includes the params that identify the individual list.

- **Recruitment pipeline loading**, including N+1 queries, tab persistence,
  mail preview, column-toggle labels, and notification links that pointed at a
  stale pipeline.

- **Onboarding**: a missing active view-toggle, the wrong pagination size, a
  stage cache miss, and a two-column layout bug in the Create/Update Task
  modals.

- **The scheduler container reported itself unhealthy forever.** It reuses the
  web image and inherited a `HEALTHCHECK` that curls `localhost:8000/health/`,
  but it runs `run_scheduler` and binds no port, so the check could never pass.
  Harmless under Compose; an orchestrator gating on health would have
  restart-looped a service that was working correctly.

- **`pip install -r requirements.txt` behaved differently across machines.**
  Four packages had no version floor at all, and `pandas` asks for a different
  `numpy` major above and below Python 3.14 — so the same file resolved
  differently depending on the interpreter. Packages that ship compiled
  artifacts now carry a floor and a major cap, so pip can select a build that
  has a wheel for the interpreter in front of it instead of falling back to a
  source compile. Every pure-Python pin, and so every advisory pin, is
  unchanged. The README now also upgrades pip before installing, which the
  Dockerfile always did and the manual instructions never mentioned.

- **PMS**: nested scrollbars in the OKR detailed view.

- **A duplicate Status column** on the work type and shift request tabs.

- Requested Attendances now renders through the shared list table.

### Changed

- The Leave assign form and the Offboarding Exit Process pipeline follow the v2
  layout, the latter using per-tab navigation to match Recruitment.
- Filter, nav and pagination borders and accents follow the selected theme
  colour, including the per-app quick-action panels.
- Action button styling is consistent between detail and list views.
- Translations updated for Arabic, German, English, Spanish and French,
  including strings in JavaScript that were never marked for translation.

## [2.1.5] — 2026-09-09

Bug-fix release. No security content and no migration — but it carries fixes
for two problems that were reported by users and have been unavailable to them
until now.

### Fixed

- **Dashboard panels stuck on "Loading…" forever.** `HorillaFilterSet` called
  `self.data.getlist(...)`, which assumes a `QueryDict`. django-filter accepts
  any mapping, and eight call sites pass a plain dict — the offline/online and
  not-checked-in cards, their API equivalents, asset history and
  reimbursements. Every one raised `AttributeError`, returned a 500, and left
  the card it feeds spinning. Reported independently by **@owino600** in
  [#1216](https://github.com/horilla/horilla-hr/issues/1216) and by a customer
  after a v1→v2 migration; it affects every 2.1.x install, migrated or not.

- **Horilla would not start on a Windows console.** A warning in
  `horilla/config.py` contained an emoji, printed during `django.setup()` from
  `horilla_ldap`'s `AppConfig.ready()`. On a cp1252 console — the Windows
  default — encoding it raised `UnicodeEncodeError`, which propagated out of
  startup and killed the process. Any database predating the LDAP app triggers
  the warning path, so a v1→v2 migration hit it every time. Startup
  diagnostics are now ASCII and go through `logging`, which absorbs an encoding
  failure rather than letting it become fatal.

- **A full table load and a session write on every page view.** The breadcrumb
  context processor read every employee and every active candidate on every
  request and rewrote their ids into the session each time. It is now scoped,
  lazy, and writes only when the ids change. Reported and fixed by
  **@Roshan931** ([#1180](https://github.com/horilla/horilla-hr/pull/1180)).

- **The organisation chart showed a single node** for anyone with no direct
  reports, which read as a page that had failed to load. It now roots at the
  top of the viewer's reporting chain, stopping at a company boundary so a
  cross-company reporting line cannot expose another company's tree. By
  **@yuri-val** ([#1168](https://github.com/horilla/horilla-hr/pull/1168)).

- **Every employee showed as "Offline", permanently,** when check-in/check-out
  was disabled for the company. The indicator is now hidden rather than
  asserting something false. By **@yuri-val**
  ([#1169](https://github.com/horilla/horilla-hr/pull/1169)).

- **Survey template descriptions were saved but never displayed** anywhere a
  user could see them. By **@yuri-val**
  ([#1171](https://github.com/horilla/horilla-hr/pull/1171)).

- Candidate cards fall back to initials when a profile image is missing,
  instead of showing a broken image.

- Two `pre-commit` hooks failed on a clean checkout: a `ruff` B023 warning, and
  `check-yaml` on Compose's `!override` merge tag.

### Added

- **The running version is now visible in the UI** — in the sidebar footer and
  under Settings → System Preferences → About, with a link to that release's
  notes. Until now the version existed only in build metadata, so "which
  version are you on?" could not be answered from the screen. It is
  deliberately *not* exposed on `/health/` or `/ready/`, which are
  unauthenticated.

- Policy documents with an uploaded file now preview inline rather than
  offering a download. By **@yuri-val**
  ([#1175](https://github.com/horilla/horilla-hr/pull/1175)).

### Changed

- Eighteen commits adding `escapejs` to translated strings used inside
  JavaScript, plus missing `trans` tags and an i18n context processor.
  Apostrophes in translations no longer break the scripts they appear in.

### Upgrading

No migration or configuration change is required.

```bash
docker pull horilla/horilla-hr:2.1.5
```

## [2.1.4] — 2026-09-08

Security release. **Upgrade from any 2.x.** Both flaws below are reachable by an
ordinary employee holding no permission over the data they reach.

### Security

| Advisory | Severity | Issue |
|---|---|---|
| [GHSA-6fxh-v24c-4cmx](https://github.com/horilla/horilla-hr/security/advisories/GHSA-6fxh-v24c-4cmx) | Medium | The mail-template sanitizer's denylist was bypassable, leaving the server-side template injection that CVE-2026-63432 was meant to close reachable — any account in the stock `HR Manager` role could read any user's password hash, the superuser's included |
| [GHSA-97wm-28fj-g4pj](https://github.com/horilla/horilla-hr/security/advisories/GHSA-97wm-28fj-g4pj) | Critical | The API's manager check asked whether anybody at all reported to the caller, never which employee the record belonged to, so any employee who managed one person could approve, edit and delete other employees' leave, attendance, overtime, rotating assignments and documents |

With thanks to **@Ntn10** and **@lighthousekeeper1212** for reporting these
responsibly.

**The mail-template sanitizer is no longer a denylist.** `{{ }}` expressions
were checked only up to the first `|`, so a filter argument carried the path the
check rejected, and `{% %}` tags were checked only by name, so `{% with %}`,
`{% firstof %}` and every other tag carried it too. The body is now tokenized
with Django's own lexer — the same one that parses the result, so no construct
can be read differently by the check and the renderer — every part of a
construct is inspected rather than a prefix, and template tags are allow-listed
instead of denied two at a time. `{% include %}` and `{% extends %}`, which read
from disk and were on nobody's denylist, are shut with the same change. Eighteen
call sites share this function and only two of them added the strict allow-list,
so the fix is at the function, not at the endpoints that were reported.

**API manager checks now name their target.** `manager_permission_required`
established only that the caller managed *somebody*; the record was then loaded
straight from the URL. Seventeen record-specific handlers were on it. They now
use the target-scoped decorators introduced for
[GHSA-39gq-9wwx-p8hx](https://github.com/horilla/horilla-hr/security/advisories/GHSA-39gq-9wwx-p8hx)
and [GHSA-gc35-jfv9-r3cm](https://github.com/horilla/horilla-hr/security/advisories/GHSA-gc35-jfv9-r3cm),
with approve and reject endpoints refusing self-approval independently of the
manager test. The two bulk endpoints take their ids from the request body rather
than the URL and were not in the report; they apply the same rule per record,
since scoping only the by-id routes would have left their unscoped twins in
place.

Multiple-approval chains are unaffected: an approver a leave condition nominates
is admitted explicitly, because such an approver is frequently neither the
requester's reporting manager nor a permission holder.

### Fixed

- `PUT /api/attendance/converted-mail-template` and
  `POST /api/attendance/offline-employee-mail-send` returned a 500 instead of a
  404 for a template or employee id that does not exist.
- Removed an owner-or-manager permission helper on the rotating work-type
  assignment API that was written but never wired to a handler. The decorator
  now applied enforces the same rule.

### Added

- Regression tests for both advisories, including the allow cases — a scoped
  permission check is only correct if the people who legitimately held it still
  get through.

## [2.1.3] — 2026-09-07

Bug-fix and security release. **Upgrade if you are on 2.1.0, 2.1.1 or 2.1.2** —
three pages return a server error on all three, and the leave-allocation
authorization flaw below affects every 2.x release.

### Security

| Advisory | Severity | Issue |
|---|---|---|
| [GHSA-gc35-jfv9-r3cm](https://github.com/horilla/horilla-hr/security/advisories/GHSA-gc35-jfv9-r3cm) | Medium | Any employee who was the reporting manager of one person could approve their own leave allocation and credit an arbitrary number of days to their own balance |

With thanks to **@je-lv** for reporting it responsibly.

Approval now requires a second person who actually manages the requester, and
the approver may never be the requester — the two checks are independent, since
an employee can be recorded as their own reporting manager. The fix is at the
shared authorization gate, so the reject, read, edit and delete endpoints on the
same model are covered too: rejecting an approved allocation subtracts the days
again, and the edit endpoint accepts `requested_days`. Neither was in the report.

### Fixed

- **Attendance work records, the skill zone view and the attendance monthly
  summary returned a 500.** A documentation comment in the modern filter panel
  described where the filter body is included, and wrote that description using
  real template syntax. Django's lexer does not recognise CSS comments, so the
  `{% include %}` inside the comment was executed on every render; on the pages
  that include the panel directly — rather than through the generic nav, where
  the list views supply `filter_body_template` — the variable resolved empty and
  the include raised `TemplateDoesNotExist: No template names provided`.

  Reported by **@owino600** in
  [#1216](https://github.com/horilla/horilla-hr/issues/1216), with an accurate
  diagnosis of the cause.

- Two `{% url %}` tags in a disabled block of jQuery in the grace-time template
  were being resolved on every render for the same reason. They resolved, so
  nothing broke, but removing the routes they name would have 500ed the page
  from inside a comment. The block was already marked unused and has been
  removed.

### Added

- A test that fails the build if `{% include %}`, `{% extends %}`, `{% url %}` or
  `{% ssi %}` appears inside a CSS or JavaScript comment in any template. The
  defect above shipped in three consecutive releases without being noticed, so
  the class is now checked rather than the instance.

### Upgrading

No migration or configuration change is required.

```bash
docker pull horilla/horilla-hr:2.1.3
```

## [2.1.2] — 2026-09-07

Security patch release. **Upgrading is recommended for all installations.**

### Security

Three access-control issues, all exploitable by an ordinary low-privilege
account and none dependent on `DEBUG` or any operator setting.

| Advisory | Severity | Issue |
|---|---|---|
| [GHSA-39gq-9wwx-p8hx](https://github.com/horilla/horilla-hr/security/advisories/GHSA-39gq-9wwx-p8hx) | High | Any employee who managed one person could overwrite — or delete — any other employee's bank account details, redirecting salary payments |
| [GHSA-x72c-5gf7-97g3](https://github.com/horilla/horilla-hr/security/advisories/GHSA-x72c-5gf7-97g3) | Medium | Any authenticated employee could delete any other employee's documents, including contracts and identity documents |
| [GHSA-v963-hrfx-34mw](https://github.com/horilla/horilla-hr/security/advisories/GHSA-v963-hrfx-34mw) | Medium | Any candidate could write notes onto any other candidate's hiring record, across companies, and read that candidate's tracking page |

With thanks to **@je-lv** for reporting all three responsibly.

Each fix was made at the shared authorization gate rather than the reported
endpoint, so sibling endpoints on the same gate are covered too. The bank-detail
`DELETE` and the document `GET`/`PUT` were not in the reports and were reachable
the same way.

### Changed

- Editing a document through `PUT /api/employee/documents/<pk>/` now authorizes
  against `horilla_documents.change_document` rather than
  `horilla_documents.view_document`. Owners and reporting managers are
  unaffected; an integration that held only the view permission and relied on it
  to write will now be refused.
- `DELETE /api/employee/employee-bank-details/<pk>/` now also admits the record's
  owner, and restricts managers to their own reports rather than any manager of
  anyone.

### Upgrading

No migration or configuration change is required.

If you drive Horilla through the REST API, check the two permission changes
above before upgrading — an integration that wrote documents using only
`horilla_documents.view_document` will start receiving 403.

```bash
docker pull horilla/horilla-hr:2.1.2
```

## [2.1.1] — 2026-09-06

Security patch release. **Upgrading is recommended for all installations.**

### Security

| Advisory | Severity | Issue |
|---|---|---|
| [GHSA-rf47-2qgf-qq4j](https://github.com/horilla/horilla-hr/security/advisories/GHSA-rf47-2qgf-qq4j) | High | Stored XSS leading to credential theft — XSS validation was bypassed on every REST and direct write |
| [GHSA-cjr4-rrp6-g72j](https://github.com/horilla/horilla-hr/security/advisories/GHSA-cjr4-rrp6-g72j) | High | Local file read through PDF generation, via an XSS-filter bypass |
| [GHSA-56x4-6268-vg4f](https://github.com/horilla/horilla-hr/security/advisories/GHSA-56x4-6268-vg4f) | High | Reimbursement approval could rewrite the claimed payout amount |
| [GHSA-p745-9729-g8jw](https://github.com/horilla/horilla-hr/security/advisories/GHSA-p745-9729-g8jw) | Medium | A candidate could read any other candidate's uploaded documents |
| [GHSA-mpw3-7c6v-vfjp](https://github.com/horilla/horilla-hr/security/advisories/GHSA-mpw3-7c6v-vfjp) | Medium | An employee could read any other employee's leave requests |

With thanks to **@je-lv** and **@Pig-Tail** for reporting these responsibly.

### Changed

- Rich text (ticket descriptions and comments, recruitment descriptions, policy bodies,
  OKR comments) is sanitised on output with an allow-list rather than a blocklist. Images
  and inline colour are preserved; scripts, event handlers and `javascript:`/`data:` URLs
  are removed.
- "Default Export Access" is now an explicit per-company setting rather than
  permissive-by-absence.
- API rate limiting added; outstanding tokens are revoked when a password changes.

### Upgrading

No migration or configuration change is required by this release.

If you are upgrading from **2.0.x** and use the WhatsApp integration, note that
[2.1.0](https://github.com/horilla/horilla-hr/releases/tag/2.1.0) requires a Meta App
Secret — message delivery stops until it is set.

```bash
docker pull horilla/horilla-hr:2.1.1
```

[Unreleased]: https://github.com/horilla/horilla-hr/compare/2.1.8...HEAD
[2.1.8]: https://github.com/horilla/horilla-hr/compare/2.1.7...2.1.8
[2.1.7]: https://github.com/horilla/horilla-hr/compare/2.1.6...2.1.7
[2.1.6]: https://github.com/horilla/horilla-hr/compare/2.1.5...2.1.6
[2.1.5]: https://github.com/horilla/horilla-hr/compare/2.1.4...2.1.5
[2.1.4]: https://github.com/horilla/horilla-hr/compare/2.1.3...2.1.4
[2.1.3]: https://github.com/horilla/horilla-hr/compare/2.1.2...2.1.3
[2.1.2]: https://github.com/horilla/horilla-hr/compare/2.1.1...2.1.2
[2.1.1]: https://github.com/horilla/horilla-hr/releases/tag/2.1.1
