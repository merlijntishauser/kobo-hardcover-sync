"""Who may tell the server who the reader is.

The page has no login of its own: a sign-in proxy in front of it passes the
reader on in the Remote-User / Remote-Email headers. Anyone who can reach
the port can send those headers too, so they only count when the request
comes from an address in KHS_TRUSTED_PROXIES (addresses or networks,
comma-separated). Everything else gets a 403, and without the setting the
server does not start at all.
"""

from __future__ import annotations

import ipaddress


class BadSetting(ValueError):
    pass


def parse(text: str | None) -> list:
    """The networks in a KHS_TRUSTED_PROXIES value. Raises BadSetting on an
    entry that is not an address or a network."""
    nets = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError as ex:
            raise BadSetting(f"KHS_TRUSTED_PROXIES: '{part}' is not an address or a network") from ex
    return nets


def trusted(host: str | None, nets: list) -> bool:
    """Is this peer address one of the proxies?"""
    try:
        addr = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):  # ::ffff:192.0.2.10
        addr = addr.ipv4_mapped
    return any(addr.version == n.version and addr in n for n in nets)


HOW = (
    "Set KHS_TRUSTED_PROXIES to the address of the sign-in proxy in front of this server "
    "(for example KHS_TRUSTED_PROXIES=192.0.2.10). The page has no login of its own: it believes "
    "the Remote-User header, so only the proxy may be allowed to send it."
)
