# Horilla HR

Free and open source HR software. Recruitment, onboarding, attendance, leave, payroll, performance, assets and helpdesk in one Django application.

- **Source:** https://github.com/horilla/horilla-hr
- **Docs:** https://docs.horilla.com
- **Website:** https://www.horilla.com
- **License:** LGPL-2.1

__NOTICE__

---

## Supported tags

| Tag | Meaning |
|---|---|
| `latest` | Newest stable release. Currently `__VERSION__`. |
| `X.Y.Z` | Exact release, immutable once published. Pin this in production. |
| `X.Y` | Newest patch within a minor line. Moves as patch releases ship. |

**Architectures:** `linux/amd64`, `linux/arm64` (single multi-arch manifest — Docker picks the right one).

```bash
docker pull horilla/horilla-hr
# or pin an exact version:
docker pull horilla/horilla-hr:__VERSION__
```

---

## Quick start

Horilla needs PostgreSQL. The fastest way to a working instance is Compose:

```yaml
# compose.yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: horilla_db
      POSTGRES_USER: horilla_user
      POSTGRES_PASSWORD: change-me-db-password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U horilla_user -d horilla_db"]
      interval: 5s
      retries: 10

  web:
    image: horilla/horilla-hr:__VERSION__
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      DEBUG: "0"
      SECRET_KEY: "replace-with-50-plus-random-characters"
      ALLOWED_HOSTS: "localhost,127.0.0.1"
      CSRF_TRUSTED_ORIGINS: "http://localhost:8000"
      DATABASE_URL: "postgres://horilla_user:change-me-db-password@db:5432/horilla_db"
      DB_HOST: db
      DB_PORT: "5432"
      DB_INIT_PASSWORD: "replace-with-your-own-init-password"
    volumes:
      - media:/app/media
      - staticfiles:/app/staticfiles

volumes:
  postgres_data:
  media:
  staticfiles:
```

```bash
docker compose up -d
```

Then open http://localhost:8000.

**First boot takes several minutes** (around 3-4 minutes on a typical runner). The container applies the full migration set against the empty database before the web server binds. Watch it with `docker compose logs -f web`; the app is ready when `/health/` responds.

Generate a real `SECRET_KEY`:

```bash
docker run --rm horilla/horilla-hr:__VERSION__ \
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Environment variables

### Required

The container refuses to start in production without these. There are no usable defaults — that is deliberate.

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Django signing key. 50+ random characters. Changing it invalidates all sessions. |
| `DEBUG` | `0` in production. `1` exposes tracebacks and disables security checks. |
| `ALLOWED_HOSTS` | Comma-separated hostnames. Do not use `*` in production. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated, **must include the scheme** (`https://hr.example.com`). |
| `DB_INIT_PASSWORD` | Gates the first-run database setup screen. Startup aborts if left at the shipped default. |

### Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Preferred. `postgres://user:pass@host:5432/dbname`. |
| `DB_HOST` | `db` | Used by the startup wait loop. Set it to your Postgres hostname. |
| `DB_PORT` | `5432` | |
| `DB_ENGINE` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | — | Discrete alternative when `DATABASE_URL` is unset. |

`DB_HOST` and `DB_PORT` are read separately from `DATABASE_URL`: the entrypoint waits on that host:port before running migrations. If they disagree, the container waits on the wrong address.

### Optional

| Variable | Default | Notes |
|---|---|---|
| `HORILLA_ENV` | — | Set to `production` to force security checks even if `DEBUG` is accidentally `1`. |
| `REDIS_URL` | unset | Enables Redis caching. |
| `SECURE_SSL_REDIRECT` | `False` | Turn on when TLS terminates in front of the app. |
| `TIME_ZONE` | `Asia/Kolkata` | |
| `GUNICORN_WORKERS` | auto | |

---

## What the container does at startup

1. Waits for `DB_HOST:DB_PORT` (30 attempts, 1s apart)
2. Generates and persists a random `SECRET_KEY` to `/app/media/.generated_secret_key` **if** the supplied one is empty or a known public default
3. Runs `migrate --noinput`
4. Runs `collectstatic --noinput --clear`
5. Starts gunicorn on port 8000

Step 4 uses `--clear` deliberately: `STATIC_ROOT` is a named volume that outlives the image, and stale pre-compressed `.gz`/`.br` files would otherwise be served to browsers after an upgrade.

---

## Volumes

| Path | Contents |
|---|---|
| `/app/media` | User uploads, and the generated `SECRET_KEY` if one was auto-created. **Back this up.** |
| `/app/staticfiles` | Collected static assets. Rebuilt on every start; safe to discard. |

---

## Health checks

| Endpoint | Returns |
|---|---|
| `/health/` | `{"status": "ok"}` once the web server is serving |
| `/ready/` | `{"status": "ok", "database": "ok"}` — also proves DB connectivity |

The image ships a `HEALTHCHECK` that polls `/health/` every 30s with a 10 minute start period. On a first boot the container reports `starting` for about five minutes while migrations and static files are prepared — that is expected, not a failure. Failed checks inside the start period are not counted, so a started container turns `healthy` at the first passing check.

---

## Creating the first user

```bash
docker compose exec web python manage.py createsuperuser
```

---

## Production notes

- **Run behind a reverse proxy** that terminates TLS. Set `CSRF_TRUSTED_ORIGINS` to the public `https://` origin and enable `SECURE_SSL_REDIRECT`.
- **Pin an exact version** (`horilla/horilla-hr:__VERSION__`), not `latest`, so a deploy cannot pick up a new major release unattended.
- **Back up `/app/media` and your database together.** The auto-generated `SECRET_KEY` lives in the media volume; losing it invalidates every session and signed token.
- **Migrations run on every container start.** With more than one replica, start one first and let it finish before scaling up — there is no advisory lock coordinating concurrent migrations.
- The image runs as a **non-root user** (`appuser`, uid 1000). Mounted volumes must be writable by uid 1000.

---

## Image details

- Base: `python:3.12-slim` (Debian), multi-stage build
- Python dependencies installed into `/opt/venv`; build toolchain is not present in the final image
- Runs as `appuser` (uid 1000), never root
- Exposes port 8000
- Locale catalogs (`.mo`) compiled at build time, so non-English UI languages work out of the box

Each image carries OCI labels — `org.opencontainers.image.version`, `.revision`, `.source` — so any published image traces back to the exact commit it was built from:

```bash
docker inspect horilla/horilla-hr:__VERSION__ \
  --format '{{json .Config.Labels}}' | python3 -m json.tool
```

---

## How these images are built

Built and published by GitHub Actions from [horilla/horilla-hr](https://github.com/horilla/horilla-hr) on every release tag. Before any image is pushed, the pipeline:

1. Asserts the code's `__version__` matches the release tag
2. Builds for amd64 and arm64
3. Boots the built image against a real PostgreSQL and waits for `/health/` **and** `/ready/`
4. Fails the release on any CRITICAL vulnerability found by Trivy

An image that builds but does not run cannot be published.

---

## Support

- Issues: https://github.com/horilla/horilla-hr/issues
- Documentation: https://docs.horilla.com
