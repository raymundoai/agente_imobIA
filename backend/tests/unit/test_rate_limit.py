import pytest

from app.shared.errors.exceptions import TooManyRequestsError
from app.shared.security.rate_limit import AuthRateLimiter, LimitPolicy


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_window_expires_and_keys_are_case_insensitive() -> None:
    clock = Clock()
    limiter = AuthRateLimiter({"p": LimitPolicy(limit=2, window_seconds=60)}, clock=clock)
    limiter.check_and_hit("p", "Ana@Example.com")
    limiter.check_and_hit("p", "ana@example.com")
    with pytest.raises(TooManyRequestsError) as blocked:
        limiter.check("p", "ANA@example.com")
    assert 1 <= blocked.value.retry_after_seconds <= 61

    clock.now += 61
    limiter.check_and_hit("p", "ana@example.com")


def test_disabled_limiter_never_blocks() -> None:
    limiter = AuthRateLimiter({"p": LimitPolicy(limit=1, window_seconds=60)}, enabled=False)
    for _ in range(5):
        limiter.check_and_hit("p", "key")


def test_reset_clears_the_key() -> None:
    limiter = AuthRateLimiter({"p": LimitPolicy(limit=1, window_seconds=60)})
    limiter.hit("p", "key")
    limiter.reset("p", "key")
    limiter.check("p", "key")
