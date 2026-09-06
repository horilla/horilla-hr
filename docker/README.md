# Horilla HRMS — Docker Deployment Guide

A complete, step-by-step guide to running Horilla HR using Docker. Covers development setup, production deployment, customization, troubleshooting, and maintenance.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start (Development)](#2-quick-start-development)
3. [Architecture Overview](#3-architecture-overview)
4. [Configuration Reference](#4-configuration-reference)
5. [Development Workflow](#5-development-workflow)
6. [Production Deployment](#6-production-deployment)
7. [Database Management](#7-database-management)
8. [Static & Media Files](#8-static--media-files)
9. [Scaling & Performance](#9-scaling--performance)
10. [Backup & Restore](#10-backup--restore)
11. [Monitoring & Health Checks](#11-monitoring--health-checks)
12. [Troubleshooting](#12-troubleshooting)
13. [Security Checklist](#13-security-checklist)
14. [Make Commands](#14-make-commands)
15. [File Reference](#15-file-reference)

---

## 1. Prerequisites

### Required Software

| Software | Minimum Version | Check Command |
|----------|----------------|---------------|
| Docker | 24.0+ | `docker --version` |
| Docker Compose | 2.20+ (V2) | `docker compose version` |
| Git | 2.30+ | `git --version` |

### System Requirements

| Environment | CPU | RAM | Disk |
|-------------|-----|-----|------|
| Development | 2 cores | 4 GB | 10 GB |
| Production (small, <50 users) | 2 cores | 4 GB | 20 GB |
| Production (medium, 50–500 users) | 4 cores | 8 GB | 50 GB |
| Production (large, 500+ users) | 8 cores | 16 GB | 100 GB+ |

### Port Requirements

| Service | Port | Required For |
|---------|------|-------------|
| Web App | 8000 | Development access |
| Nginx | 80 | Production HTTP |
| PostgreSQL | 5432 | Internal only (not exposed in production) |
| Redis | 6379 | Internal only (not exposed in production) |

---

## 2. Quick Start (Development)

Get Horilla running in under 5 minutes:

```bash
# 1. Clone the repository (defaults to stable 2.0; contributors: use -b dev/v2.0)
git clone https://github.com/horilla/horilla-hr.git
cd horilla-hr

# 2. Start all services
make dev
# or: docker compose up --build

# 3. Wait for services to be healthy (~30–60 seconds on first run)
make status

# 4. Open in your browser
open http://localhost:8000
```

On first launch, Horilla will:
1. Wait for PostgreSQL to be ready (30s timeout)
2. Run database migrations automatically
3. Collect static files
4. Start the Gunicorn application server

You'll see the **Database Initialization** page where you can create your first admin user and company.

### Stopping & Starting

```bash
# Stop all services (preserves data)
make stop

# Stop and remove ALL data (fresh start)
make clean

# Restart only the web service (after code changes)
docker compose restart web

# View logs
make logs
```

---

## 3. Architecture Overview

```
                          ┌─────────────────────────────┐
                          │         Browser             │
                          └─────────┬───────────────────┘
                                    │ :8000 (dev) / :80 (prod)
               ┌────────────────────┼────────────────────┐
               │  Docker Network    │                    │
               │                    ▼                    │
               │  ┌──────────────────────────────────┐  │
               │  │  Nginx (production profile only)  │  │
               │  │  - Static files (/static/)       │  │
               │  │  - Reverse proxy to web:8000     │  │
               │  │    (incl. /media/ — see below)   │  │
               │  │  - Gzip + security headers       │  │
               │  └──────────────┬───────────────────┘  │
               │                 │                       │
               │                 ▼                       │
               │  ┌──────────────────────────────────┐  │
               │  │  Web (Django + Gunicorn)          │  │
               │  │  - protected_media for /media/   │  │
               │  │  - 2–8 workers (adaptive)        │  │
               │  │  - 4 threads per worker           │  │
               │  │  - Health check: /health/         │  │
               │  └───────┬──────────────┬──────────┘  │
               │          │              │              │
               │          ▼              ▼              │
               │  ┌──────────────┐ ┌──────────────┐    │
               │  │  PostgreSQL  │ │    Redis     │    │
               │  │  16-alpine   │ │  7-alpine    │    │
               │  │  Port: 5432  │ │  Port: 6379  │    │
               │  └──────────────┘ └──────────────┘    │
               │          │              │              │
               │          ▼              ▼              │
               │  [postgres_data]  [redis_data]         │
               │  [staticfiles]    [media]              │
               └────────────────────────────────────────┘
```

### Services

| Service | Image | Purpose |
|---------|-------|---------|
| **web** | Custom (Dockerfile) | Django application with Gunicorn WSGI server |
| **scheduler** | Custom (Dockerfile) | Single process running `manage.py run_scheduler`. Payroll, leave resets, backups and report subscriptions do **not** run inside gunicorn workers. |
| **db** | `postgres:16-alpine` | Primary database for all application data |
| **redis** | `redis:7-alpine` | Caching, session storage (password-protected, AOF persistence) |
| **nginx** | `nginx:alpine` | Reverse proxy and static file serving (production only). Does **not** serve `/media/` directly — that path is proxied to Django so `protected_media()` can enforce auth and content-type gates. |

> **Upgrade:** if you deploy without this Compose file, start **exactly one** `python manage.py run_scheduler` process. Missing it is silent — those jobs simply never fire. `GET /ready/` includes `"scheduler": "ok"|"missing"`. Set `HORILLA_REQUIRE_SCHEDULER=1` to make `/ready/` return 503 while jobs are unregistered — only where a failing readiness probe will not pull web out of the load balancer, since a stopped scheduler delays background jobs but does not stop the app serving requests.

### Volumes

| Volume | Mounted At | Purpose |
|--------|-----------|---------|
| `postgres_data` | `/var/lib/postgresql/data` | Persistent database storage |
| `redis_data` | `/data` | Redis AOF persistence |
| `staticfiles` | `/app/staticfiles` | Collected Django static files |
| `media` | `/app/media` | User-uploaded files (photos, documents, attachments) |

---

## 4. Configuration Reference

### Environment Variables (docker-compose.yml)

#### Django Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `1` | Set to `0` for production |
| `SECRET_KEY` | `dev-secret-key...` | **Change for production** — generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames. Add your domain for production |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8000` | Full URLs for CSRF validation. Must include protocol |
| `DATABASE_URL` | `postgres://...@db:5432/...` | PostgreSQL connection string. `db` is the Docker service name |
| `DB_INIT_PASSWORD` | `dev-init-password...` | Initial database setup password — **change for production** |
| `REDIS_URL` | `redis://:...@redis:6379/0` | Redis connection string (includes password) |

#### PostgreSQL Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `horilla_db` | Database name |
| `POSTGRES_USER` | `horilla_user` | Database user |
| `POSTGRES_PASSWORD` | `horilla_pass` | Database password — **change for production** |

#### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GUNICORN_WORKERS` | Auto (2–8) | Override worker count |
| `GUNICORN_LOG_LEVEL` | `info` | Logging verbosity: debug, info, warning, error |
| `GUNICORN_RELOAD` | `false` | Set to `true` for auto-reload during development |

### Using a .env File (Optional)

For cleaner configuration, create a `.env` file from the template:

```bash
cp .env.dist .env
# Edit .env with your values
```

Docker Compose automatically reads `.env` for variable substitution in the compose file itself (e.g., `${POSTGRES_PASSWORD}`).

---

## 5. Development Workflow

### Live Code Reloading

The development setup mounts your local code into the container (`.:/app`), so code changes are reflected immediately. To enable Gunicorn auto-reload:

```bash
# Option 1: Set environment variable
docker compose exec web env GUNICORN_RELOAD=true gunicorn horilla.wsgi:application --config docker/gunicorn.conf.py

# Option 2: Use Django's development server instead
docker compose exec web python manage.py runserver 0.0.0.0:8000
```

### Running Management Commands

```bash
# Run any Django management command
docker compose exec web python manage.py <command>

# Examples:
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py shell
docker compose exec web python manage.py collectstatic --noinput
```

### Installing New Python Packages

```bash
# 1. Add to requirements.txt
echo "new-package==1.0.0" >> requirements.txt

# 2. Rebuild the web image
make build

# 3. Restart
make dev
```

### Running Tests

```bash
docker compose exec web python manage.py test
```

### Accessing the Database Directly

```bash
# PostgreSQL shell
make db-shell

# Redis CLI
docker compose exec redis redis-cli -a horilla_pass
```

### Viewing Logs

```bash
# All services
make logs

# Web only
make logs-web

# Last 100 lines
docker compose logs --tail=100 web
```

---

## 6. Production Deployment

Production uses a Compose **overlay** so the zero-config `make dev` path stays intact.

### Step 1: Create a production `.env`

```bash
cp .env.dist .env
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set strong `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, DB/Redis passwords, and `DB_INIT_PASSWORD`.
With `DEBUG=False` (or `HORILLA_ENV=production`), Django refuses known-insecure secrets.

### Step 2: Start production overlay

```bash
make prod
# or: docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

This builds without bind-mounting source, forces `DEBUG=0`, and enables Nginx.

### Step 4: Set Up SSL/TLS

For HTTPS, add a `443` listener to `docker/nginx.conf`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # ... rest of config
}
```

Mount certificates in `docker-compose.yml`:

```yaml
nginx:
  volumes:
    - ./ssl/fullchain.pem:/etc/nginx/ssl/fullchain.pem:ro
    - ./ssl/privkey.pem:/etc/nginx/ssl/privkey.pem:ro
```

**Alternative:** Use [Caddy](https://caddyserver.com/) or [Traefik](https://traefik.io/) for automatic Let's Encrypt SSL.

### Step 5: Create Admin User

```bash
docker compose exec web python manage.py createsuperuser
```

### Step 6: Verify Deployment

```bash
# Check all services are healthy
make status

# Liveness
curl http://localhost:8000/health/
# Readiness (DB + Redis when REDIS_URL set; includes scheduler status)
curl http://localhost:8000/ready/

# Check logs for errors
docker compose logs --tail=50 web
```

---

## 7. Database Management

### Running Migrations

Migrations run automatically on container start via `entrypoint.sh`. To run manually:

```bash
docker compose exec web python manage.py migrate
```

### Creating Migrations (Development Only)

```bash
# After model changes
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

> **Important:** Never run `makemigrations` in production. Migration files should be created during development, committed to version control, and applied in production via `migrate` only.

### Database Shell

```bash
make db-shell
```

### Loading Demo Data

From the Horilla login page, click "Load Demo Data" to populate the system with sample employees, departments, and other test data.

---

## 8. Static & Media Files

### Static Files

Collected automatically during container startup via `collectstatic`. In production, Nginx serves them directly from the `staticfiles` volume.

```bash
# Force re-collect
docker compose exec web python manage.py collectstatic --noinput --clear
```

### Media Files

User uploads (employee photos, documents, attachments) are stored in the `media` volume on the **web** service (`/app/media`).

In production, nginx does **not** alias `/media/` to disk. Requests are proxied to Django’s `protected_media` view, which requires a session or valid JWT (except a small allowlist of public assets such as company icons) and forces HTML/SVG/XML/JS uploads to download instead of rendering inline. Do not re-add a `location /media/ { alias … }` block in `docker/nginx.conf` — that would bypass those checks.

```bash
# List media files
docker compose exec web ls -la /app/media/

# Copy media to host
docker cp $(docker compose ps -q web):/app/media ./media-backup
```

### Using Cloud Storage (S3/GCP)

Horilla supports AWS S3 and Google Cloud Storage. Add to your environment:

**AWS S3:**
```
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_STORAGE_BUCKET_NAME=your-bucket
DEFAULT_FILE_STORAGE=horilla.horilla_backends.PrivateMediaStorage
```

**Google Cloud Storage:**
```
GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-credentials.json
GS_BUCKET_NAME=your-bucket
DEFAULT_FILE_STORAGE=horilla.horilla_backends_gcp.PrivateMediaStorage
```

---

## 9. Scaling & Performance

### Gunicorn Tuning

The default configuration (`docker/gunicorn.conf.py`) auto-scales workers based on CPU count:

| Setting | Default | Description |
|---------|---------|-------------|
| Workers | `max(2, min(CPU*2+1, 8))` | Process count |
| Worker class | `gthread` | Threaded workers |
| Threads | `4` | Threads per worker |
| Max requests | `1000` | Restart worker after N requests (prevents memory leaks) |
| Timeout | `120s` | Request timeout |

Override via environment variables:

```yaml
environment:
  - GUNICORN_WORKERS=4
  - GUNICORN_LOG_LEVEL=warning
```

### PostgreSQL Tuning

For production workloads, add PostgreSQL configuration:

```yaml
db:
  image: postgres:16-alpine
  command: >
    postgres
    -c shared_buffers=256MB
    -c effective_cache_size=768MB
    -c work_mem=16MB
    -c maintenance_work_mem=128MB
    -c max_connections=100
```

### Redis Memory Limit

Add a memory limit to prevent Redis from consuming all available RAM:

```yaml
redis:
  command: redis-server --appendonly yes --requirepass horilla_pass --maxmemory 256mb --maxmemory-policy allkeys-lru
```

---

## 10. Backup & Restore

### Database Backup

```bash
# SQL backup
docker compose exec db pg_dump -U horilla_user horilla_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker compose exec db pg_dump -U horilla_user -F c horilla_db > backup_$(date +%Y%m%d).dump
```

### Database Restore

```bash
# From SQL file
cat backup.sql | docker compose exec -T db psql -U horilla_user -d horilla_db

# From compressed dump
docker compose exec -T db pg_restore -U horilla_user -d horilla_db --clean < backup.dump
```

### Media Backup

```bash
# Backup media volume
docker run --rm -v horilla_media:/data -v $(pwd):/backup alpine tar czf /backup/media_backup.tar.gz -C /data .

# Restore media volume
docker run --rm -v horilla_media:/data -v $(pwd):/backup alpine tar xzf /backup/media_backup.tar.gz -C /data
```

---

## 11. Monitoring & Health Checks

### Built-in Health Check

The Dockerfile includes a health check that pings `/health/` every 30 seconds:

```bash
# Check container health status
make status

# Manual health check
curl -f http://localhost:8000/health/
# Returns: {"status": "ok"}

# Readiness includes scheduler: "ok" or "missing"
curl -f http://localhost:8000/ready/
```

### Service Health Checks

All services have health checks configured:

| Service | Health Check | Interval |
|---------|-------------|----------|
| **web** | `curl /health/` | 30s (60s startup grace) |
| **db** | `pg_isready` | 5s |
| **redis** | `redis-cli -a <pass> ping` | 5s |

### Resource Monitoring

```bash
# Live resource usage
docker stats

# Disk usage by volumes
docker system df -v
```

---

## 12. Troubleshooting

### Common Issues

#### Container won't start — "PostgreSQL not available"

The web container waits up to 30 seconds for PostgreSQL. If it times out:

```bash
# Check if db container is running
docker compose ps db

# Check db logs
docker compose logs db

# Restart db and web
docker compose restart db
docker compose restart web
```

#### "Permission denied" errors

The container runs as `appuser` (UID 1000). If volumes have wrong permissions:

```bash
docker compose exec web chown -R appuser:appuser /app/staticfiles /app/media
```

#### Static files not loading (404)

```bash
# Re-collect static files
docker compose exec web python manage.py collectstatic --noinput --clear

# Verify files exist
docker compose exec web ls /app/staticfiles/
```

#### Database migration errors

```bash
# Check migration status
docker compose exec web python manage.py showmigrations

# Run specific app migration
docker compose exec web python manage.py migrate <app_name>
```

#### Out of disk space

```bash
# Clean unused Docker resources
docker system prune -a --volumes

# Check volume sizes
docker system df -v
```

#### Slow performance

1. Check worker count: `docker compose exec web ps aux | grep gunicorn`
2. Check database connections: `docker compose exec db psql -U horilla_user -c "SELECT count(*) FROM pg_stat_activity;"`
3. Check Redis memory: `docker compose exec redis redis-cli -a horilla_pass INFO memory`

### Resetting Everything

```bash
# Stop containers and remove ALL data (database, uploads, cache)
make clean

# Rebuild from scratch
docker compose build --no-cache
make dev
```

---

## 13. Security Checklist

Before going to production, verify the following:

- [ ] `.env` created from `.env.dist` (not committed to git)
- [ ] `DEBUG=False` — app refuses insecure defaults when False
- [ ] `SECRET_KEY` is a unique, random 50+ character string
- [ ] `ALLOWED_HOSTS` lists only your actual domain(s) (not `*`)
- [ ] `CSRF_TRUSTED_ORIGINS` uses `https://` URLs
- [ ] `DB_INIT_PASSWORD` is strong and unique (not the documented default)
- [ ] Database/Redis passwords are strong and unique
- [ ] SSL/TLS configured; set `SECURE_SSL_REDIRECT=True` behind TLS
- [ ] Database and Redis ports are NOT exposed to the host
- [ ] Started via `make prod` (Nginx on, no source bind-mount)
- [ ] `/health/` and `/ready/` both return OK
- [ ] Regular backups are configured
- [ ] Container images are kept up to date

---

## 14. Make Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start all services (web + db + redis) |
| `make prod` | Start production with nginx |
| `make build` | Build Docker images |
| `make stop` | Stop all services |
| `make logs` | Follow all service logs |
| `make logs-web` | Follow web server logs only |
| `make shell` | Open bash in web container |
| `make db-shell` | Open PostgreSQL shell |
| `make status` | Show status of all services |
| `make restart` | Restart all services |
| `make clean` | Remove volumes + prune (data loss!) |

---

## 15. File Reference

```
docker/
├── entrypoint.sh        # Container startup script
│                          - Waits for PostgreSQL (30 attempts, 1s interval)
│                          - Runs migrations
│                          - Collects static files
│                          - Starts Gunicorn via exec "$@"
│
├── gunicorn.conf.py     # Gunicorn WSGI server configuration
│                          - Adaptive worker count (2–8 based on CPU)
│                          - gthread worker class with 4 threads
│                          - 120s timeout, 1000 max requests
│                          - Access/error logging to stdout
│
├── nginx.conf           # Nginx reverse proxy configuration
│                          - Static files with 1-year cache
│                          - Gzip compression (9 MIME types)
│                          - Security headers + server_tokens off
│                          - Proxy to Django with proper headers
│
└── README.md            # This file

Dockerfile               # Multi-stage build
                           - Builder: compiles C extensions in venv
                           - Production: minimal runtime (no build tools)
                           - Non-root user (appuser, UID 1000)
                           - Health check: curl /health/ every 30s

docker-compose.yml       # Service orchestration
                           - web: Django + Gunicorn (healthchecked)
                           - db: PostgreSQL 16 (healthchecked)
                           - redis: Redis 7 with password (healthchecked)
                           - nginx: Production reverse proxy (profile)

Makefile                 # Developer convenience commands
                           - make dev/prod/build/stop/logs/shell/etc.

.env.dist             # Environment variable template
.dockerignore            # Files excluded from Docker build context
```
