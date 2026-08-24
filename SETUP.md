# krew-hrms — Local Development Setup (PostgreSQL + pgAdmin)

Step-by-step setup for running krew-hrms (Django 5.2 / Horilla HR) locally on
macOS or Linux, backed by **PostgreSQL** instead of the default SQLite, with
**pgAdmin** as the database viewer.

This guide covers the recommended hybrid setup: the Django app runs natively in
a virtualenv (fast reloads, easy debugging) while PostgreSQL and pgAdmin run in
Docker. Alternatives — Homebrew PostgreSQL, other GUI clients, or the full
Docker Compose stack — are covered at the end.

**What you end up with**

| Piece | Where |
| --- | --- |
| Django dev server | http://localhost:8000 |
| pgAdmin | http://localhost:5050 |
| PostgreSQL 16 | `localhost:5432`, database **`krew-dev-db`** |

---

## TL;DR

Already have Python 3.13 and Docker? The whole setup is five commands:

```bash
git clone https://github.com/greatkapitaltech/krew-hrms.git && cd krew-hrms
python3.13 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
make env                 # writes .env with generated secrets
make dev-db              # starts PostgreSQL + pgAdmin in Docker
python manage.py migrate && python manage.py collectstatic --noinput
```

Then create an admin user (step 8) and `python manage.py runserver`.

The rest of this document explains each step and how to recover when one fails.

---

## 1. Prerequisites

| Tool | Version | Check | Install (macOS) |
| --- | --- | --- | --- |
| Python | **3.12 or 3.13** (not 3.14) | `python3.13 --version` | `brew install python@3.13` |
| Docker | any recent | `docker --version` | Docker Desktop / OrbStack |
| gettext | any | `msgfmt --version` | `brew install gettext` |
| git | any | `git --version` | Xcode CLT |

> **Python version matters.** Django 5.2 supports Python 3.10–3.13, and the
> Dockerfile pins 3.12. Python 3.14 has no wheels for several pinned
> dependencies — use 3.13 or older.

`msgfmt` (gettext) is only needed for `compilemessages`. Homebrew installs it
keg-only on Apple Silicon; if it is not on your `PATH`:

```bash
export PATH="/opt/homebrew/opt/gettext/bin:$PATH"
```

---

## 2. Clone the repository

```bash
git clone https://github.com/greatkapitaltech/krew-hrms.git
cd krew-hrms
```

---

## 3. Start PostgreSQL and pgAdmin

Both services are defined in `docker-compose.dev.yml`, so this is one command:

```bash
make dev-db
```

That starts:

| Service | Container | Address |
| --- | --- | --- |
| PostgreSQL 16 | `krew-hrms-db` | `localhost:5432`, database `krew-dev-db` |
| pgAdmin | `krew-hrms-pgadmin` | <http://localhost:5050> |

It also creates `docker/pgadmin/pgpass` from `pgpass.example` on first run —
that file holds the database password so pgAdmin connects without prompting, and
it is gitignored rather than committed.

Data lives in the Docker volumes `krew_hrms_pgdata` and `krew_hrms_pgadmin`, so
it survives restarts. Other targets:

```bash
make dev-db-stop     # stop both (keeps data)
make dev-db-logs     # tail logs
make dev-db-shell    # psql into krew-dev-db
make dev-db-reset    # destroy both containers AND all data
```

**Port 5432 or 5050 already in use?** Set `LOCAL_DB_PORT=5433` /
`PGADMIN_PORT=5051` in `.env` (step 5) and re-run `make dev-db`. If you change
the database port, update `DATABASE_URL` to match.

Prefer plain Docker, or don't have `make`? The equivalent is:

```bash
docker compose -f docker-compose.dev.yml up -d
```

> The hyphens in `krew-dev-db` are fine — the Postgres image quotes the
> identifier when creating it, and Django quotes it in every query. You only
> need to quote it yourself in hand-written SQL: `... TO "krew-dev-db"`.

---

## 4. Create the virtualenv and install dependencies

```bash
python3.13 -m venv venv
source venv/bin/activate                 # Windows: venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

This installs `psycopg2-binary`, the PostgreSQL driver — no local libpq or
compiler needed.

> Every `python`/`pip`/`make` command below assumes the venv is active.
> Alternatively call `./venv/bin/python …` directly without activating.

---

## 5. Configure `.env`

Settings are read by `django-environ` from `.env` at the repo root
(`horilla/settings/base.py`). `.env` is gitignored — never commit it.

```bash
make env
```

That copies `.env.example` to `.env` and fills in a freshly generated
`SECRET_KEY` and `DB_INIT_PASSWORD`. It refuses to overwrite an existing `.env`.

The result works as-is against the step-3 database:

```ini
DEBUG=True
SECRET_KEY=<generated>
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
TIME_ZONE=Asia/Kolkata

DATABASE_URL=postgres://horilla_user:horilla_pass@localhost:5432/krew-dev-db

DB_INIT_PASSWORD=<generated>       # gates the in-app "Initialize Database" screens
```

Two things worth knowing:

- **Use `DATABASE_URL`, not the `DB_ENGINE`/`DB_NAME`/… variables.** The
  fallback branch in `horilla/settings/base.py:170` hardcodes
  `OPTIONS={"timeout": 30}`, a SQLite-only option that psycopg2 rejects with
  `invalid connection option "timeout"`. `DATABASE_URL` takes priority and skips
  that branch entirely.
- **Avoid a literal `$` in any `.env` value.** Docker Compose also reads this
  file for variable interpolation and treats `$` as a variable reference.
  `make env` already strips it from the generated `SECRET_KEY`.

`.env.dist` documents every other supported variable (GCP storage, LDAP, OAuth).

---

## 6. Verify the database connection

```bash
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','horilla.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
print('db:', connection.settings_dict['NAME'], '| vendor:', connection.vendor)
"
```

Expect `db: krew-dev-db | vendor: postgresql`. Warnings about `fitz` being
deprecated, app-init DB access, and `Database is empty. Using default LDAP
settings.` are normal on a fresh database.

---

## 7. Initialize the application

```bash
python manage.py migrate            # ~380 tables + default themes
python manage.py compilemessages    # compile .po -> .mo translations
python manage.py collectstatic --noinput
```

`collectstatic` prints two "Found another file with the destination path"
warnings (`pipeline/pipeline.js`, `recruitment/candidate.js`) — pre-existing and
harmless.

---

## 8. Create an admin user

Use the project's own command — it creates the `HorillaUser` superuser, the
linked `Employee` record, and the "Horilla Bot" system user together. A plain
`createsuperuser` leaves you without an Employee profile and most screens break.

```bash
python manage.py createhorillauser \
  --first_name Som --last_name Naskar \
  --username admin --password 'admin' \
  --email you@example.com --phone 0000000000
```

Omit all flags to be prompted interactively.

---

## 9. Run the development server

```bash
python manage.py runserver 8000
```

Open <http://localhost:8000/> and sign in. Useful URLs:

| URL | Purpose |
| --- | --- |
| `http://localhost:8000/` | App (redirects to login) |
| `http://localhost:8000/login/` | Login page |
| `http://localhost:8000/health/` | Health check → `{"status": "ok"}` |
| `http://localhost:8000/admin/` | Django admin |

The first request after boot can take a few seconds while apps warm up; a 500
during that window resolves on retry.

---

## 10. pgAdmin — the database viewer

pgAdmin is already running from step 3 at <http://localhost:5050>, with the
`krew-dev-db` server pre-registered — there is nothing to configure in the UI
and no password to type.

Expand **Servers → krew-hrms (local) → Databases → krew-dev-db → Schemas →
public → Tables** to browse the schema.

Common tasks:

- **Browse a table** — right-click it → *View/Edit Data* → *All Rows*
- **Run SQL** — select `krew-dev-db`, then *Tools → Query Tool* (⌥⇧Q), write the
  query and press the ▶ button or `F5`
- **Schema diagram** — right-click the database → *ERD For Database*

### How the pre-registration works

`docker-compose.dev.yml` mounts two files into the pgAdmin container:

| File | Committed? | Purpose |
| --- | --- | --- |
| `docker/pgadmin/servers.json` | yes | Registers the server (host, port, database, user) |
| `docker/pgadmin/pgpass` | **no** — gitignored | Supplies the password so there is no prompt |

`make dev-db` creates `pgpass` from `docker/pgadmin/pgpass.example` if it is
missing, with mode 600 (libpq silently ignores the file if permissions are
looser).

In `servers.json`, `Host` is `krew-hrms-db` — the *container* name, resolved
over the Compose network. It is deliberately not `localhost`, which inside the
pgAdmin container would point at pgAdmin itself.

pgAdmin runs in desktop mode (`PGADMIN_CONFIG_SERVER_MODE=False`): no login
screen, single local user. That is fine for a local instance bound to
localhost — do not expose this container to a network.

> `servers.json` is imported **only on first boot**, when pgAdmin's internal
> config database is created. After editing it, reset pgAdmin's own state:
>
> ```bash
> docker rm -f krew-hrms-pgadmin && docker volume rm krew_hrms_pgadmin
> make dev-db
> ```
>
> That wipes only pgAdmin's settings — never your Postgres data.

### Prefer a native app?

The connection details are the same for any client — host `localhost`, port
`5432`, database `krew-dev-db`, user `horilla_user`, password `horilla_pass`:

- **TablePlus** — `brew install --cask tableplus` (fastest, freemium)
- **DBeaver** — `brew install --cask dbeaver-community` (free, full-featured)
- **Postico 2** — `brew install --cask postico` (macOS-native, freemium)
- **psql** — `make dev-db-shell`

---

## 11. Optional — load demo data

Populates employees, attendance, payroll, recruitment, and other fixtures from
`load_data/`, with dates shifted relative to today.

```bash
python manage.py load_demo_data              # add to existing data
python manage.py load_demo_data --flush      # WIPE the database first, then load
```

`--flush` deletes everything, including the admin user from step 8 — re-run
`createhorillauser` afterwards. Add `--no-input` to skip the confirmation
prompt.

Demo data can also be loaded in-app while `DEBUG=True`; those screens ask for
the `DB_INIT_PASSWORD` value from your `.env`.

---

## Daily workflow

```bash
cd krew-hrms
make dev-db                                   # start db + pgAdmin if stopped
source venv/bin/activate
python manage.py migrate                      # after pulling changes
python manage.py runserver 8000
```

## Running tests

Tests create and drop a `test_krew-dev-db` database — `horilla_user` is a
superuser in the container, so this works out of the box.

```bash
make test-smoke                    # first-party app smoke suite
make test-unit                     # same labels, override with UNIT_LABELS=...
make test-cov                      # smoke suite under coverage
python manage.py test leave attendance payroll --verbosity=2   # specific apps
```

The `make` targets call bare `python`, so activate the venv first.

---

## Alternatives

### A. Homebrew PostgreSQL instead of Docker

```bash
brew install postgresql@16
brew services start postgresql@16
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

createuser -s horilla_user
psql -d postgres -c "ALTER USER horilla_user WITH PASSWORD 'horilla_pass';"
createdb -O horilla_user krew-dev-db
```

The `DATABASE_URL` in step 5 is unchanged. Skip step 3; steps 4 onward are
identical. To still use the containerised pgAdmin, start only that service
(`docker compose -f docker-compose.dev.yml up -d pgadmin`) and point `Host` at
`host.docker.internal` in both `servers.json` and `pgpass` — or just use a
native client on `localhost`.

### B. Full Docker Compose stack (web + Postgres + Redis)

No virtualenv, no local Python — everything runs in containers, and
`docker/entrypoint.sh` handles migrations, `collectstatic`, and SECRET_KEY
generation automatically.

```bash
make dev                 # docker compose up --build
make logs-web            # tail the web logs
make db-shell            # psql inside the db container
make shell               # bash inside the web container
make stop                # stop everything
make clean               # stop AND delete volumes (data loss)
```

Then create the admin user inside the container:

```bash
docker compose exec web python manage.py createhorillauser \
  --first_name Som --last_name Naskar --username admin --password 'admin' \
  --email you@example.com --phone 0000000000
```

> **Heads-up:** the Compose stack is upstream's and still uses the database name
> `horilla_db` (see `docker-compose.yml`), not `krew-dev-db`. It is a completely
> separate volume and dataset from the step-3 container, and the two cannot run
> at the same time if both claim host port 5432.

---

## Troubleshooting

**`invalid connection option "timeout"`**
You are on the `DB_ENGINE`/`DB_NAME` settings branch. Use `DATABASE_URL`
instead (step 5).

**`connection to server at "localhost" (::1), port 5432 failed`**
Postgres is not running or is on a different port: `docker start krew-hrms-db`,
then confirm with
`docker inspect --format='{{.State.Health.Status}}' krew-hrms-db`.

**`Ports are not available: 0.0.0.0:5432`**
Something else already owns 5432 (`lsof -nP -iTCP:5432 -sTCP:LISTEN`). Recreate
the container with `-p 5433:5432` and update `DATABASE_URL`.

**`django.db.utils.ProgrammingError: relation "..." does not exist`**
Migrations have not run: `python manage.py migrate`. Confirm with
`python manage.py migrate --check` (exit code 0 = up to date).

**Login succeeds but pages error out**
The user has no linked `Employee`. Create users with `createhorillauser`, not
`createsuperuser`.

**pgAdmin asks for a password, or shows no server**
`servers.json` was not imported, or `pgpass` was rejected. Check the file is
mode 600 (`docker exec krew-hrms-pgadmin ls -l /pgpass`), then reset pgAdmin's
config volume as described in step 10.

**pgAdmin: `could not translate host name "krew-hrms-db"`**
The two containers are not on the same Compose network. Bring the stack up
together with `make dev-db` rather than starting containers individually.

**`CommandError: Can't find msgfmt`**
Install gettext and put it on `PATH`:
`brew install gettext && export PATH="/opt/homebrew/opt/gettext/bin:$PATH"`.

**Wheel build failures during `pip install`**
Almost always Python 3.14. Rebuild the venv with 3.13:
`rm -rf venv && python3.13 -m venv venv`.

**Rename the database later**
Stop the app and pgAdmin first (an open connection blocks the rename):

```bash
docker stop krew-hrms-pgadmin
docker exec krew-hrms-db psql -U horilla_user -d postgres \
  -c 'ALTER DATABASE "krew-dev-db" RENAME TO "new-name";'
```

Then update `DATABASE_URL` in `.env`, `MaintenanceDB` in
`docker/pgadmin/servers.json`, both `docker/pgadmin/pgpass` and its `.example`,
and `LOCAL_DB_NAME` / the `dev-db-shell` target if you rely on them. Finally
reset pgAdmin's config volume (step 10).

**Start completely over**

```bash
make dev-db-reset      # removes both containers and both volumes
rm -f .env             # then re-run `make env`
```

Then repeat from step 3.
