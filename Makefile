.PHONY: help dev prod build stop logs logs-web shell clean db-shell status restart makemessages compilemessages test-smoke test-unit test-cov

COMPOSE ?= docker compose
COMPOSE_PROD ?= $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml
I18N_EXCLUDES ?= --ignore=static/build/* --ignore=static/images/ionicons/*

help: ## Show help
	@echo 'Available commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

dev: ## Start development stack (web + db + redis; bind-mount source)
	$(COMPOSE) up --build

prod: ## Start production overlay (no source bind-mount; requires .env)
	@test -f .env || (echo "Missing .env — copy .env.dist and set production secrets:" && echo "  cp .env.dist .env" && exit 1)
	$(COMPOSE_PROD) up --build -d

build: ## Build images
	$(COMPOSE) build

stop: ## Stop services (includes prod overlay / nginx)
	$(COMPOSE_PROD) down

logs: ## Show logs (all services)
	$(COMPOSE) logs -f

logs-web: ## Show web server logs
	$(COMPOSE) logs -f web

shell: ## Open shell in web container
	$(COMPOSE) exec web bash

db-shell: ## Open PostgreSQL shell
	$(COMPOSE) exec db psql -U horilla_user -d horilla_db

status: ## Show status of all services
	$(COMPOSE) ps

restart: ## Restart all services
	$(COMPOSE) restart

makemessages: ## Refresh catalogs without extracting vendored JavaScript identifiers
	python manage.py makemessages -a $(I18N_EXCLUDES)

compilemessages: ## Compile all gettext catalogs
	python manage.py compilemessages

clean: ## Clean up (removes volumes — data loss!)
	$(COMPOSE_PROD) down -v
	docker system prune -f


# Unit-test coverage program (feature/unit-test-coverage)
# Smoke = Phases 0–3 first-party app minimum bar.
SMOKE_LABELS ?= leave attendance base horilla_auth employee accessibility payroll horilla_api biometric asset recruitment onboarding offboarding pms project helpdesk report whatsapp facedetection geofencing horilla_documents horilla_automations horilla_backup horilla_crumbs horilla_ldap horilla_meet horilla_theme horilla_widgets horilla_views horilla_audit
UNIT_LABELS ?= $(SMOKE_LABELS)

test-smoke: ## Run CI smoke unit tests (min bar across first-party apps)
	python manage.py test $(SMOKE_LABELS) --verbosity=1

test-unit: ## Run unit-test labels (override UNIT_LABELS=...)
	python manage.py test $(UNIT_LABELS) --verbosity=1

# Measured 27.6% on 2026-09-01 with branch coverage on (.coveragerc). It
# reads lower than statement coverage because untaken branches count, which
# is the more honest number. The floor was 5 while real coverage was far
# above it -- a gate that cannot fail is worse than none, because it reads
# as one. Ratchet this up as suites land; never down to make a build pass.
COV_FAIL_UNDER ?= 26
COV_SOURCE ?= leave,attendance,base,payroll,recruitment,report,horilla_auth,employee,accessibility,horilla_api

test-cov: ## Smoke suite under coverage (low fail-under floor)
	python -m coverage erase
	python -m coverage run --source=$(COV_SOURCE) manage.py test $(SMOKE_LABELS) --verbosity=1
	python -m coverage report --fail-under=$(COV_FAIL_UNDER)
