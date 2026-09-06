"""
Resolve company letterhead details for standard reports (UI + exports).

Matches explorer reports: full address block + logo when a company is
selected; a simple "All companies" label when the session is unscoped.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from django.utils.translation import gettext as _

from base.models import Company


def _empty_all() -> dict[str, Any]:
    return {
        "id": None,
        "name": str(_("All companies")),
        "address": "",
        "country": "",
        "state": "",
        "city": "",
        "zip": "",
        "logo_path": None,
        "logo_url": None,
        "is_all": True,
        "location_line": "",
        "address_lines": [str(_("All companies"))],
    }


def _from_company(company: Company) -> dict[str, Any]:
    location_parts = [p for p in (company.city, company.state, company.country) if p]
    location_line = ", ".join(location_parts)
    address_lines = [company.company]
    if company.address:
        address_lines.append(company.address)
    if location_line:
        address_lines.append(location_line)
    if company.zip:
        address_lines.append(f"ZIP: {company.zip}")

    logo_path = None
    logo_url = None
    if company.icon:
        try:
            logo_url = company.icon.url
        except Exception:
            logo_url = None
        try:
            path = company.icon.path
            if path and os.path.exists(path):
                logo_path = path
        except Exception:
            logo_path = None

    return {
        "id": company.id,
        "name": company.company,
        "address": company.address or "",
        "country": company.country or "",
        "state": company.state or "",
        "city": company.city or "",
        "zip": company.zip or "",
        "logo_path": logo_path,
        "logo_url": logo_url,
        "is_all": False,
        "location_line": location_line,
        "address_lines": address_lines,
    }


def company_letterhead(
    request=None,
    company_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Return a normalized company block for report headers / exports.
    """
    company = _pick_company(request, company_id)
    if company is None:
        return _empty_all()
    return _from_company(company)


def _pick_company(request, company_id: Optional[int]) -> Optional[Company]:
    if company_id:
        try:
            return Company.objects.filter(id=int(company_id)).first()
        except (TypeError, ValueError, Exception):
            return None

    if request is None:
        return None

    session_selected = None
    try:
        session_selected = request.session.get("selected_company")
    except Exception:
        session_selected = None

    # Explicit company filter / session company (not "all")
    if session_selected and session_selected != "all":
        try:
            return Company.objects.filter(id=int(session_selected)).first()
        except (TypeError, ValueError, Exception):
            try:
                return Company.find(session_selected)
            except Exception:
                pass

    selected = getattr(request, "selected_company_instance", None)
    if (
        selected is not None
        and hasattr(selected, "company")
        and session_selected
        and session_selected != "all"
    ):
        return selected

    return None
