"""What the server is willing to fetch, and what it is willing to call a file.

The main risk of a public downloader is being used as an open proxy: asking the server to fetch internal
addresses (SSRF) or arbitrary URLs. Three layers cut that off:
  1. only http(s) links to real, public DNS names on the standard ports are accepted;
  2. every address the name resolves to must be globally routable;
  3. the runner turns yt-dlp's "generic" extractor off, so only sites yt-dlp has a dedicated extractor for work.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

from .errors import ApiError

MAX_URL = 2048
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_BAD_SUFFIXES = (".local", ".localhost", ".internal", ".localdomain", ".lan", ".home", ".corp", ".intranet", ".private", ".home.arpa")
_HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,63}|xn--[a-z0-9-]{2,59})$")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f-\x9f]")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_RESERVED_STEMS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class Checked:
    url: str
    host: str


def host_matches(host: str, domains: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def is_youtube(host: str) -> bool:
    return host_matches(host, YOUTUBE_DOMAINS)


def _embedded_v4(ip: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses hidden inside IPv6 forms (mapped, NAT64, 6to4, Teredo) that could point at private hosts."""
    found: list[ipaddress.IPv4Address] = []
    if ip.ipv4_mapped:
        found.append(ip.ipv4_mapped)
    if ip in _NAT64:
        found.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    if ip.sixtofour:
        found.append(ip.sixtofour)
    if ip.teredo:
        found.extend(ip.teredo)
    return found


def is_public_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6:
        for inner in _embedded_v4(ip):
            if not (inner.is_global and not inner.is_multicast):
                return False
    return ip.is_global and not ip.is_multicast


def _resolve(host: str, port: int) -> set[str]:
    return {row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}


def validate_url(
    raw: str,
    *,
    allowed: tuple[str, ...] = (),
    blocked: tuple[str, ...] = (),
    youtube: str = "on",
    resolver: Callable[[str, int], set[str]] | None = None,
) -> Checked:
    """Return the cleaned link or raise ApiError(400, code, message)."""
    url = (raw or "").strip()
    if not url or len(url) > MAX_URL or _CONTROL_RE.search(url):
        raise ApiError(400, "bad_url", "That doesn't look like a valid link.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ApiError(400, "bad_url", "That doesn't look like a valid link.") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise ApiError(400, "bad_scheme", "Only http:// and https:// links are supported.")
    if parts.username is not None or parts.password is not None:
        raise ApiError(400, "bad_url", "Links that contain a login aren't supported.")
    if port not in (None, 80, 443):
        raise ApiError(400, "bad_port", "That link uses a port that isn't supported.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise ApiError(400, "bad_url", "That doesn't look like a valid link.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ApiError(400, "ip_literal", "Use the address of the video page, not an IP address.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ApiError(400, "bad_url", "That doesn't look like a valid link.") from None
    if host == "localhost" or host.endswith(_BAD_SUFFIXES) or not _HOST_RE.match(host):
        raise ApiError(400, "bad_url", "That doesn't look like a valid link.")
    if allowed and not host_matches(host, allowed):
        raise ApiError(400, "site_blocked", "This site isn't available on this server.")
    if host_matches(host, blocked):
        raise ApiError(400, "site_blocked", "This site isn't available on this server.")
    if youtube == "off" and is_youtube(host):
        raise ApiError(400, "youtube_off", "YouTube isn't available in the web version. The desktop app supports it.")
    try:
        addresses = (resolver or _resolve)(host, port or (80 if parts.scheme.lower() == "http" else 443))
    except OSError:
        raise ApiError(400, "dns_failed", "That website couldn't be found.") from None
    if not addresses:
        raise ApiError(400, "dns_failed", "That website couldn't be found.")
    if any(not is_public_address(a) for a in addresses):
        raise ApiError(400, "bad_url", "That address isn't allowed.")
    return Checked(url=url, host=host)


def safe_stem(title: str, fallback: str = "download", max_len: int = 90) -> str:
    """A file name that is safe on every OS and can't spoof an extension (bidi overrides, separators, controls)."""
    text = unicodedata.normalize("NFC", title or "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = re.sub(r'[\\/:*?"<>|]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = text[:max_len].strip(" .")
    if not text:
        return fallback
    if text.split(".")[0].upper() in _RESERVED_STEMS:
        text = "_" + text
    return text
