"""In-process login rate limiter.

Adequate for the single-instance free deployment. State resets when the free instance
sleeps or restarts, which only ever makes the limiter more lenient, never locks the owner out
permanently.
"""

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until another attempt is allowed; 0 when not blocked."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            if len(q) < self.max_attempts:
                return 0
            return max(1, int(self.window - (now - q[0])))

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
