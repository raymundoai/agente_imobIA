"""In-process attempt limits for authentication endpoints.

Counters live in memory, which is enough for a single API instance. Running several
API replicas would need a shared store (database or Redis) instead.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.shared.errors.exceptions import TooManyRequestsError


@dataclass(frozen=True, slots=True)
class LimitPolicy:
    limit: int
    window_seconds: int


# Per IP every attempt counts; per account only failures count, so a user who
# types the right password is never locked out by the account limit.
AUTH_POLICIES = {
    "login_ip": LimitPolicy(limit=30, window_seconds=15 * 60),
    "login_account": LimitPolicy(limit=10, window_seconds=15 * 60),
    "platform_ip": LimitPolicy(limit=20, window_seconds=15 * 60),
    "platform_account": LimitPolicy(limit=5, window_seconds=15 * 60),
    "signup_ip": LimitPolicy(limit=5, window_seconds=60 * 60),
}


class AuthRateLimiter:
    def __init__(
        self,
        policies: dict[str, LimitPolicy] | None = None,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policies = policies or AUTH_POLICIES
        self._enabled = enabled
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, policy: str, key: str) -> None:
        """Refuse when the key already used up its window; does not count an attempt."""

        if not self._enabled:
            return
        retry_after = self._retry_after(policy, key)
        if retry_after is not None:
            raise TooManyRequestsError(
                "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                retry_after_seconds=retry_after,
            )

    def hit(self, policy: str, key: str) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._window(policy, key).append(self._clock())

    def check_and_hit(self, policy: str, key: str) -> None:
        self.check(policy, key)
        self.hit(policy, key)

    def reset(self, policy: str, key: str) -> None:
        with self._lock:
            self._hits.pop((policy, key.lower()), None)

    def _retry_after(self, policy: str, key: str) -> int | None:
        rule = self._policies[policy]
        with self._lock:
            window = self._window(policy, key)
            if len(window) < rule.limit:
                return None
            return max(1, int(window[0] + rule.window_seconds - self._clock()) + 1)

    def _window(self, policy: str, key: str) -> deque[float]:
        rule = self._policies[policy]
        bucket = self._hits.setdefault((policy, key.lower()), deque())
        expires_before = self._clock() - rule.window_seconds
        while bucket and bucket[0] <= expires_before:
            bucket.popleft()
        return bucket


def client_ip(request: object) -> str:
    """Address of the caller; behind a proxy uvicorn's --proxy-headers fills it in."""

    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"
