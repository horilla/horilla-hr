"""Give every demo company its own, genuinely scoped asset inventory.

AssetCategory/AssetLot ship with an empty company_id (the "visible to every
company" convention HorillaCompanyManager treats as shared), and Asset has
no company field of its own -- it only derives one transitively through
asset_category_id__company_id. Since every category is unscoped, all 200
demo Asset rows are visible under every company simultaneously: switching
company context never changes what asset inventory is shown.

Existing categories/assets are deliberately left untouched here rather than
re-scoped -- some are already referenced by AssetAssignment rows for
employees across all 3 companies, and narrowing an existing category to one
company would make those assets invisible under their own current holder's
company filter. Instead this adds one company-exclusive category per
additional company, with its own small, headcount-proportional asset pool.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

# (company_id, category name, asset name prefix, tracking id prefix, count)
NEW_COMPANY_ASSET_POOLS = [
    (2, "Field Equipment", "Field Laptop", "IN-AST", 10),
    (3, "Regional Office Equipment", "Office Laptop", "UK-AST", 10),
]


@transaction.atomic
def backfill_company_asset_pools(today: date | None = None) -> int:
    """Ensure each entry in NEW_COMPANY_ASSET_POOLS has a company-exclusive
    AssetCategory with COUNT Asset (+ matching AssetItem) rows."""
    if not apps.is_installed("asset"):
        return 0

    today = today or date.today()

    from asset.models import Asset, AssetCategory, AssetItem
    from base.models import Company

    created = 0
    for (
        company_id,
        category_name,
        asset_prefix,
        tracking_prefix,
        count,
    ) in NEW_COMPANY_ASSET_POOLS:
        category, _ = AssetCategory.objects.get_or_create(
            asset_category_name=category_name,
            defaults={"asset_category_description": "Assets issued to employees."},
        )
        if set(category.company_id.values_list("pk", flat=True)) != {company_id}:
            category.company_id.set(Company.objects.filter(pk=company_id))

        for i in range(1, count + 1):
            tracking_id = f"{tracking_prefix}{i:04d}"
            asset, was_created = Asset._base_manager.get_or_create(
                asset_tracking_id=tracking_id,
                defaults={
                    "asset_name": f"{asset_prefix} {i}",
                    "asset_purchase_date": today - timedelta(days=30 * i),
                    "asset_purchase_cost": 1000.00,
                    "asset_category_id": category,
                    "asset_status": "Available",
                },
            )
            if not was_created:
                continue

            AssetItem._base_manager.get_or_create(
                tracking_id=tracking_id,
                defaults={"asset_id": asset, "status": "Available"},
            )
            created += 1

    logger.info(
        "Asset backfill: created %s asset(s) across %s new company categor(ies)",
        created,
        len(NEW_COMPANY_ASSET_POOLS),
    )
    return created
