# Demo data

Enterprise demo fixtures and the post-load seeder used by Horilla HR.

## Load

```bash
# Full reset (destructive)
python manage.py load_demo_data --flush --no-input

# Gap register: SIDEBAR list models with zero rows
python manage.py demo_data_inventory --fail-on-empty

# Or from the login screen: "Load Demo Data"
```

## What happens

1. Copies icons (`load_data/icons/`) and avatars (`load_data/avatars/`) into `MEDIA_ROOT`
2. Loads JSON fixtures in dependency order with dates shifted so snapshot day `2025-08-01` becomes the load day (DOBs stay put). Also loads `tags.json`, `mail_templates.json`, and `mail_automations.json`.
3. Runs `run_enterprise_demo_seeder()`:
   - Activates `Your Company` / `Your Company Inc.` / `Your Company Ltd.`
   - Renames departments and job titles to standard enterprise names (PKs preserved)
   - Spreads transactional rows over the trailing 180 days; pending requests sit around today / a few weeks ahead
   - Final A/B date clamp: historical facts never after today; holidays re-anchor to the current year
   - Scrubs vendor-specific labels (e.g. Odoo/Cybrosys leftovers)
4. Re-anchors demo payslips (`Demo Payroll M-n`). Current month is never `paid`/`confirmed`.
5. Assigns demo role memberships (`base/demo_roles.py`)

## People layer

`user_data.json`, `employee_info_data.json`, and avatars are the source of truth for
employees. The seeder does **not** recreate people — it only standardizes org
taxonomy and module catalogs around them.

## Fixture hygiene

Catalog fixtures (`base_data`, `recruitment_data`, `project_data`, `leave_data`,
`pms_data`) already ship with enterprise-standard labels and active companies.
The seeder remains as an idempotent safety net and for **dynamic** steps
(relative dates, payslip month re-anchor, media copy, demo roles).
`faq.json` is not loaded (invalid JSON); helpdesk expansion seeds FAQs instead.

## Sample company for the user guide

`seed_docs_sample` creates **Lakeside Works Ltd**, the one fictional company that every
example and screenshot of the user guide comes from, so that a name in a sentence is the
name in the picture. It is separate from the demo data above and meant for a throwaway
database.

```bash
# Reset the database and seed the sample company
python manage.py seed_docs_sample --flush --noinput
```

- 38 employees, five departments, a cast of eight with logins (`first.last@lakesideworks.example`,
  password `Lakeside-docs-1`, change it with `--password`). Maya Chen is the administrator.
- Everything is built around today's date, so the scenarios happen in the current month.
- First slice: people, roles, and leave (types, balances, holidays, requests in each state).
  Attendance, payroll and the other modules are added in later slices.
- The colleagues have no login. A second run does nothing; reset with `--flush`.
