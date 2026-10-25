"""In-memory sliding-window limiter: per client, global per-minute, daily cap.

In-memory is a known limit (one Render instance; resets on restart), accepted
for a mini project and documented in the plan.
"""

import time
from collections import defaultdict, deque
from datetime import datetime, timezone


class RateLimiter:
    def __init__(self, per_ip_per_min: int, global_per_min: int, daily_cap: int, clock=time.time):
        self.per_ip_per_min = per_ip_per_min
        self.global_per_min = global_per_min
        self.daily_cap = daily_cap
        self._clock = clock
        self._ip: dict[str, deque] = defaultdict(deque)
        self._global: deque = deque()
        self._day: str = ""
        self._day_count = 0

    @staticmethod
    def _trim(q: deque, now: float) -> None:
        while q and now - q[0] >= 60:
            q.popleft()

    MAX_TRACKED_CLIENTS = 5000  # x-client-ip can be forged, so the table must not grow without bound

    def check(self, client: str) -> tuple[bool, str | None, int]:
        """Return (allowed, reason, retry_after_seconds) and record the hit if allowed."""
        now = self._clock()
        today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._day_count = today, 0
        if self._day_count >= self.daily_cap:
            return False, "daily", 3600
        if len(self._ip) >= self.MAX_TRACKED_CLIENTS and client not in self._ip:
            for key in [k for k, q in self._ip.items() if not q or now - q[-1] >= 60]:
                del self._ip[key]
        ip_q = self._ip[client]
        self._trim(ip_q, now)
        self._trim(self._global, now)
        if len(ip_q) >= self.per_ip_per_min:
            return False, "per_ip", max(1, int(60 - (now - ip_q[0])))
        if len(self._global) >= self.global_per_min:
            return False, "global", max(1, int(60 - (now - self._global[0])))
        ip_q.append(now)
        self._global.append(now)
        self._day_count += 1
        return True, None, 0
