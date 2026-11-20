"""The additional info columns of the employee sheet, present only when the additional_info app is installed."""

from django.apps import apps


def installed():
    return apps.is_installed("additional_info")


def importing():
    from additional_info import importing as module

    return module


def columns(taken):
    """One column for each additional info field a sheet can fill; none without the app."""
    return importing().columns(taken) if installed() else []
