"""Writing the events the ledger keeps beyond what the asset tables hold."""

from asset.models import AssetEvent


def log_event(
    asset,
    event_type,
    *,
    employee=None,
    assignment=None,
    service_request=None,
    description=""
):
    """Record one event on an asset. Who did it is stamped from the request by the model."""
    return AssetEvent.objects.create(
        asset_id=asset,
        event_type=event_type,
        employee_id=employee,
        assignment_id=assignment,
        service_request_id=service_request,
        description=description,
    )
