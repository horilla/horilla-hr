# Horilla HRMS

[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL%20v2.1-blue.svg)](https://www.gnu.org/licenses/lgpl-2.1)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-5.2-green.svg)](https://www.djangoproject.com/)
[![Stars](https://img.shields.io/github/stars/horilla/horilla-hr)](https://github.com/horilla/horilla-hr/stargazers)
[![Forks](https://img.shields.io/github/forks/horilla/horilla-hr)](https://github.com/horilla/horilla-hr/network/members)

> **A comprehensive, free, and open-source Human Resource Management System (HRMS) designed to streamline HR operations and enhance organizational efficiency.**

## 🚀 Features

### Core HR Modules
- 👥 **Employee Management** - Centralized workforce data with LDAP and SCIM 2.0 provisioning
- 🎯 **Recruitment** - End-to-end hiring process from job posting to onboarding
- 📋 **Onboarding & Offboarding** - Structured workflows for employee lifecycle
- ⏰ **Attendance & Time Tracking** - Biometric integration and automated check-in/out
- 🏖️ **Leave Management** - Policy enforcement, approvals, and balance tracking
- 💰 **Payroll** - Automated salary processing, tax calculations, and compliance
- 📊 **Performance Management** - Goal setting, reviews, and continuous feedback
- 🏢 **Asset Management** - Track and manage company resources
- 🎫 **Helpdesk** - Centralized HR support and ticketing system
- 🗂️ **Project Management** - Projects, tasks and timesheets
- 📄 **Documents** - Employee document requests and approvals
- 📈 **Dashboards & Reports** - Role-based dashboards, and reports you can export or schedule by email
- 📥 **Master Data Import** - Bring in employees, leave balances, assets and salary structures from spreadsheets

### Platform & Integrations
- 🔌 **REST API** - Token-based API used by the mobile app
- ✉️ **Automations** - Email and in-app notifications sent when records are created, updated or deleted
- 🔗 **Integrations** - LDAP, Google Meet, Google Drive backup and WhatsApp
- 🧩 **Optional add-on apps** - Geofencing, Face Detection and Outlook (Microsoft 365) mail ship in the repository but are not enabled by default


## 📋 Table of Contents

- [Which Branch Do I Want?](#-which-branch-do-i-want)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Deployment](#-deployment)
- [Upgrading](#-upgrading)
- [Contributing](#-contributing)
- [Security](#-security)
- [Support](#-support)
- [License](#-license)

## 🌳 Which Branch Do I Want?

- **`2.0`** (default) — the latest stable v2 snapshot. This is what a plain `git clone` gives you. Use it to run or deploy Horilla.
- **`dev/v2.0`** — the active integration branch. If you want to contribute code, branch from and open PRs against this, not `2.0`.
- **`1.0`/`master`** — v1, now deprioritized (fixes considered case-by-case, no guaranteed schedule). Not deleted, but no longer where active development happens.

See [Discussion #1127](https://github.com/horilla/horilla-hr/discussions/1127) for full background on this transition.

## ⚡ Quick Start

### Using the official Docker image (Recommended)

Published for `linux/amd64` and `linux/arm64` as
[`horilla/horilla-hr`](https://hub.docker.com/r/horilla/horilla-hr):

```bash
docker pull horilla/horilla-hr:2.2.1
```

Pin an exact version in production rather than `latest`, so a deploy cannot
pick up a new release unattended; see
[all tags](https://hub.docker.com/r/horilla/horilla-hr/tags) for the current
one. The
[repository overview](https://hub.docker.com/r/horilla/horilla-hr) documents
every environment variable, the volumes to back up, and a working Compose file.

First boot applies the full migration set before the web server binds, which
takes a few minutes on an empty database.

### Building from source with Docker

```bash
# Clone the repository (defaults to the stable 2.0 branch)
git clone https://github.com/horilla/horilla-hr.git
cd horilla-hr

# Start with Docker Compose
docker compose up -d

# Access the application
open http://localhost:8000
```

Full Docker guide, including production deployment: [docker/README.md](docker/README.md)

### Manual Installation

Requires **Python 3.12, 3.13 or 3.14**, and pip 21.3 or newer. Python 3.15 is
not usable yet: `spacy` declares `Requires-Python <3.15` and is imported at
module scope, so the app cannot start on it.

```bash
# Clone and setup (defaults to the stable 2.0 branch)
git clone https://github.com/horilla/horilla-hr.git
cd horilla-hr

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip FIRST. A venv inherits the system pip, and an older one does not
# recognise current manylinux wheel tags -- it then tries to compile packages
# like cryptography and PyMuPDF from source, which needs a C toolchain most
# machines do not have. The Docker build already does this; do the same here.
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.dist .env
# Edit .env with your configuration

# Initialize database
python manage.py migrate
python manage.py compilemessages
python manage.py collectstatic

# Run development server
python manage.py runserver

# In a second terminal: run the background scheduler
python manage.py run_scheduler
```

On a new database the sign-in page shows an **Initialize Database** button. It
asks for the `DB_INIT_PASSWORD` from your `.env`, then lets you create the first
administrator.

> **Run the scheduler.** Scheduled jobs (for example automatic payslips, leave resets, work
> records, shift rotation, contract expiry, document and asset reminders, clearing
> expired sessions, trimming old job-run history) only run while `run_scheduler` is running. The Docker Compose
> file starts it for you as the `scheduler` service.


## 🛠 Installation

For detailed installation instructions, configuration guides, and platform-specific setup instructions, please visit our comprehensive documentation:

### 📖 [Complete Installation Guide → docs.horilla.com/technical/v2.0/ ](https://docs.horilla.com/technical/v2.0/)

Our documentation includes:
- **Step-by-step installation** for all supported platforms
- **Database configuration** guides
- **Environment setup** instructions
- **Production deployment** best practices
- **Troubleshooting** common issues
- **Advanced configuration** options

<!-- Need help? Check out the [Installation FAQ](https://docs.horilla.com) or reach out to our [community support](#-support). -->

## 🚀 Deployment

For production deployment guides including Nginx, Apache, and cloud platforms:
### 📖 [Deployment Guide → docs.horilla.com/technical/v2.0/doc/deployment/nginx-gunicorn](https://docs.horilla.com/technical/v2.0/doc/deployment/nginx-gunicorn)


## 🔄 Upgrading

1. Read [CHANGELOG.md](CHANGELOG.md) and the [GitHub releases](https://github.com/horilla/horilla-hr/releases) for the versions you are skipping.
2. Back up the database and the media volume.
3. **Docker image:** change the pinned tag in your Compose file, then `docker compose pull && docker compose up -d`. Migrations are applied automatically when the container starts.
4. **Docker Compose from this repository** (it builds the image locally): `git pull`, then `docker compose up -d --build`.
5. **From source:** `git pull`, `pip install -r requirements.txt`, `python manage.py migrate`, `python manage.py compilemessages`, `python manage.py collectstatic`, then restart the web server and the scheduler.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Fork and clone your fork
git clone -b dev/v2.0 https://github.com/YOUR_USERNAME/horilla-hr.git
cd horilla-hr

# Add upstream remote
git remote add upstream https://github.com/horilla/horilla-hr.git

# Create feature branch
git checkout -b feature/your-feature-name

# Install development dependencies
pip install -r requirements.txt

# Enable the formatting and lint hooks (Black, isort, ruff)
pip install pre-commit
pre-commit install

# Run the tests for the app you changed
python manage.py test employee

# Submit pull request
```

> **Note:** `2.0` is the repo default, so GitHub pre-selects it as your PR base. Before submitting, change the base branch to `dev/v2.0` — that's where active development and reviews happen, not `2.0`.

### Code Standards

- Follow [PEP 8](https://pep8.org/) for Python code
- Format with [Black](https://black.readthedocs.io/) and sort imports with isort (`--profile black`); the pre-commit hooks above also run [ruff](https://docs.astral.sh/ruff/)
- Write tests for new features, and run the tests of the apps you changed (`make test-smoke` runs the full CI smoke set)
- New user-visible strings go through Django's translation functions
- Update documentation for user-facing changes

## 🔒 Security

### Security Features

- 🔐 **Authentication & Authorization** - Permission-based access control
- 🔑 **Two-Factor Login** - Optional one-time code sent by email
- 🛡️ **Brute-Force Protection** - Account lockout after repeated failed logins, and rate limiting on the API
- 🔍 **Audit Trails** - Change history on records across the modules
- 🚫 **Input Validation** - XSS checks on saved text

### Reporting Security Issues

Please report security vulnerabilities via [GitHub Private Vulnerability Reporting](https://github.com/horilla/horilla-hr/security/advisories/new), not email. Do not create public GitHub issues for security vulnerabilities. See [SECURITY.md](SECURITY.md) for full details.

### Security Best Practices

- Always use HTTPS in production
- Regularly update dependencies
- Use strong passwords and enable the optional two-factor login
- Monitor logs for suspicious activities

## 📞 Support

### Community Support

- 📖 **Documentation**: [docs.horilla.com](https://docs.horilla.com)
- 💬 **GitHub Discussions**: [GitHub Discussions](https://github.com/horilla/horilla-hr/discussions)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/horilla/horilla-hr/issues)
- ✨ **Feature Requests**: [GitHub Issues](https://github.com/horilla/horilla-hr/issues), or share an idea in [GitHub Discussions](https://github.com/horilla/horilla-hr/discussions/categories/ideas)

### Professional Support

For enterprise support, custom development, and consulting services:
- 📧 **Email**: support@horilla.com
- 🌐 **Website**: [www.horilla.com](https://www.horilla.com)


## 📄 License

This project is licensed under the [LGPL-2.1 License](LICENSE) - see the LICENSE file for details.

<div align="center">

**Made with ❤️ by the Horilla Team**

[⭐ Star us on GitHub](https://github.com/horilla/horilla-hr) | [🐛 Report Bug](https://github.com/horilla/horilla-hr/issues) | [💡 Request Feature](https://github.com/horilla/horilla-hr/issues)

</div>
