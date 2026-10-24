"""
The client's IP address, for login lockouts (django-axes) and the attendance
office-IP restriction.

X-Forwarded-For is written by whoever sends the request, so it is only
believed when the connection itself comes from a trusted reverse proxy
(settings.HORILLA_TRUSTED_PROXIES: IPs, CIDR ranges or hostnames such as the
Docker service name "nginx"). nginx's $proxy_add_x_forwarded_for appends the
address it saw, so the chain is read from the right: each trusted proxy hands
over to the entry before it, and the first address that is not a trusted
proxy is the client. Anything a client put in the header itself sits further
left and is never reached. With no trusted proxies configured (the default)
the header is ignored and REMOTE_ADDR is used, as for a direct connection.
"""

import ipaddress
import socket
import time

from django.conf import settings

# Hostnames are re-resolved at most this often, so a restarted proxy container
# with a new address is picked up without a restart of the app.
RESOLVE_SECONDS = 60

_resolved = {}  # hostname -> (time resolved, {addresses})


def _address(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _resolve(hostname):
    cached = _resolved.get(hostname)
    if cached and time.monotonic() - cached[0] < RESOLVE_SECONDS:
        return cached[1]
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except OSError:
        addresses = set()
    _resolved[hostname] = (time.monotonic(), addresses)
    return addresses


def is_trusted_proxy(address):
    """Whether `address` (an ip_address) is one of HORILLA_TRUSTED_PROXIES."""
    for entry in getattr(settings, "HORILLA_TRUSTED_PROXIES", []):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
            continue
        except ValueError:
            pass  # not an IP or range: a hostname
        if str(address) in _resolve(entry):
            return True
    return False


def client_ip(request):
    """The client's address (a string), or REMOTE_ADDR as given if unparseable."""
    remote = request.META.get("REMOTE_ADDR")
    address = _address(remote or "")
    if address is None:
        return remote
    hops = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    while is_trusted_proxy(address) and hops:
        previous = _address(hops.pop())
        if previous is None:
            break  # a malformed entry: stop at the last proxy we trust
        address = previous
    return str(address)
