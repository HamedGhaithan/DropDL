"""Access code and sign-in sessions for a private instance.

A private instance is protected by one access code. Signing in with it sets a random session token in an HttpOnly cookie;
the server keeps only a hash of each token, in memory, so restarting the server signs everyone out.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

COOKIE = "dropdl_session"
TTL = 30 * 24 * 3600


class Sessions:
    def __init__(self, code: str, ttl: int = TTL, max_sessions: int = 500):
        self._code = hashlib.sha256(code.encode()).digest()
        self.ttl = ttl
        self.max_sessions = max_sessions
        self._tokens: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_code(self, supplied: str) -> bool:
        """Compares fixed-length digests in constant time, so timing reveals nothing about the code."""
        return hmac.compare_digest(hashlib.sha256((supplied or "").encode()).digest(), self._code)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens = {k: v for k, v in self._tokens.items() if v > now}
            while len(self._tokens) >= self.max_sessions:
                self._tokens.pop(min(self._tokens, key=self._tokens.get))
            self._tokens[self._hash(token)] = now + self.ttl
        return token

    def valid(self, token: str | None, now: float | None = None) -> bool:
        if not token:
            return False
        now = time.time() if now is None else now
        key = self._hash(token)
        with self._lock:
            expires = self._tokens.get(key)
            if expires is None:
                return False
            if expires <= now:
                del self._tokens[key]
                return False
            return True

    def revoke(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._tokens.pop(self._hash(token), None)
