"""Per-visitor rate limits. Visitors are identified by a salted hash of their address, kept only in memory."""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
import threading
import time

_SALT = secrets.token_bytes(16)


class Limiter:
    """Token bucket: `capacity` actions per `window` seconds, refilled continuously."""

    def __init__(self, capacity: int, window: float, max_keys: int = 20000):
        self.capacity = max(1, int(capacity))
        self.rate = self.capacity / float(window)
        self.max_keys = max_keys
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, cost: float = 1.0, now: float | None = None) -> tuple[bool, float]:
        """Returns (allowed, seconds_until_allowed)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            tokens = min(float(self.capacity), tokens + (now - last) * self.rate)
            if tokens >= cost:
                self._buckets[key] = (tokens - cost, now)
                allowed, wait = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed, wait = False, (cost - tokens) / self.rate
            if len(self._buckets) > self.max_keys:
                self._prune(now)
        return allowed, wait

    def _prune(self, now: float) -> None:
        full = [k for k, (t, last) in self._buckets.items() if t + (now - last) * self.rate >= self.capacity]
        for k in full:
            del self._buckets[k]
        if len(self._buckets) > self.max_keys:                 # still too many distinct visitors: drop the oldest tenth
            oldest = sorted(self._buckets, key=lambda k: self._buckets[k][1])[: self.max_keys // 10 + 1]
            for k in oldest:
                del self._buckets[k]


def _network_key(addr: str) -> str:
    """IPv6 visitors are grouped by /64 so rotating addresses inside one network doesn't dodge the limits."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    return str(ip)


def client_address(headers, peer: str | None, hops: int) -> str:
    """The visitor's address behind `hops` trusted reverse proxies.

    A proxy appends the address it saw to X-Forwarded-For, so with N trusted proxies the Nth entry from the right is the
    real visitor; anything to its left was typed by the client and is ignored.
    """
    addr = peer or "unknown"
    if hops > 0:
        entries = [p.strip() for p in headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(entries) >= hops:
            candidate = entries[-hops]
            try:
                ipaddress.ip_address(candidate)
                addr = candidate
            except ValueError:
                pass
    return addr


def client_key(headers, peer: str | None, hops: int) -> str:
    """A salted hash of the visitor's network, so addresses are never stored or logged."""
    return hashlib.blake2b(_network_key(client_address(headers, peer, hops)).encode(), key=_SALT, digest_size=8).hexdigest()
