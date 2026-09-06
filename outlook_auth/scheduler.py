"""
outlook_auth/scheduler.py

"""

import logging
import sys

from horilla.scheduling import register_job

logger = logging.getLogger(__name__)


def refresh_outlook_auth_token():
    """
    scheduler method to refresh token
    """
    from outlook_auth.models import AzureApi
    from outlook_auth.views import refresh_outlook_token

    apis = AzureApi.objects.filter(token__isnull=False)
    for api in apis:
        try:
            refresh_outlook_token(api)
            logger.info(f"Updated token for {api} outlook auth")
            print(f"Updated token for {api} outlook auth")
        except Exception as e:
            logger.error(e)


register_job(
    refresh_outlook_auth_token,
    "interval",
    job_id="refresh_outlook_auth_token",
    minutes=50,
)
