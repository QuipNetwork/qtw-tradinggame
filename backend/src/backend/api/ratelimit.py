"""In-memory signup rate limiting.

Bounds scripted agent-creation floods (each new agent grants a fresh QPU budget,
so unbounded creation = unbounded QPU spend). Process-local sliding windows — the
deploy is a single worker, so this is correct without shared state. One limiter is
created per app (see api/app.create_app) so tests get a fresh one each time.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from .. import config


class SignupRateLimiter:
    def __init__(self) -> None:
        self._per_ip: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()
        self._lock = Lock()

    def check(self, ip: str, *, now: float | None = None, trusted: bool = False) -> int | None:
        """Record a signup from ``ip``. Returns None if allowed, else retry-after seconds.

        ``trusted`` (a valid booth kiosk) skips the per-IP limit so the single
        tablet IP / shared conference WiFi is never throttled; the booth-wide hourly
        ceiling still applies as a DoS backstop. Limits are read from config at call
        time so they can be tuned (or patched in tests) without rebuilding the limiter.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(self._global, now - 3600)
            if len(self._global) >= config.SIGNUP_RATE_GLOBAL_PER_HOUR:
                return 3600
            if not trusted:
                bucket = self._per_ip.setdefault(ip, deque())
                self._prune(bucket, now - config.SIGNUP_RATE_WINDOW_S)
                if len(bucket) >= config.SIGNUP_RATE_PER_IP:
                    return config.SIGNUP_RATE_WINDOW_S
                bucket.append(now)
            self._global.append(now)
            return None

    @staticmethod
    def _prune(bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
