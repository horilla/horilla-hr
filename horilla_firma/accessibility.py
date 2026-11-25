"""Who may see and use the Firma e-signature screens."""

SETTINGS_PERMISSION = "horilla_firma.change_firmasettings"
SEND_PERMISSION = "recruitment.change_candidate"


def settings_accessibility(request, submenu=None, user_perms=None, *args, **kwargs):
    """The settings page: administrators with the Firma settings permission."""
    return request.user.has_perm(SETTINGS_PERMISSION)


def can_view_requests(request, candidate=None):
    """The candidate's signature requests: whoever may view the candidate."""
    from recruitment.cbv.accessibility import if_manager_accessibility

    return bool(if_manager_accessibility(request, candidate))


def can_send(user):
    """Sending a document to a candidate needs the change permission on candidates."""
    return user.has_perm(SEND_PERMISSION)


def can_link(user):
    """Linking an existing Firma request is an administrator action."""
    return user.has_perm(SETTINGS_PERMISSION)


def signature_tab_accessibility(request, instance=None, user_perms=None, **kwargs):
    """The E-Signatures tab on the candidate profile, shown once Firma is set up."""
    from horilla_firma.models import FirmaSettings

    return bool(FirmaSettings.ready()) and can_view_requests(request, instance)
