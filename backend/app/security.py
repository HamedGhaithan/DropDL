from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_remote_url(url: str, resolved_hosts: dict | None = None) -> str:
    """Allow only public HTTP(S) destinations to reduce SSRF risk."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only http:// and https:// URLs are supported.")
    if not parsed.hostname:
        raise UnsafeUrlError("The URL has no valid hostname.")

    host = parsed.hostname
    try:
        # Literal IPs are easy to validate directly.
        ipaddress.ip_address(host)
        if not _is_public_ip(host):
            raise UnsafeUrlError("Local/private network URLs are not allowed.")
    except ValueError:
        # Hostname: resolve every address and reject the destination if any result
        # points at a private/local range.
        try:
            if resolved_hosts is not None and host in resolved_hosts:
                addresses = resolved_hosts[host]
            else:
                addresses = {row[4][0] for row in socket.getaddrinfo(host, None)}
        except socket.gaierror as exc:
            raise UnsafeUrlError("The hostname could not be resolved.") from exc
        if not addresses or any(not _is_public_ip(addr) for addr in addresses):
            raise UnsafeUrlError("Local/private network URLs are not allowed.")
        if resolved_hosts is not None:
            resolved_hosts[host] = addresses

    return url.strip()
