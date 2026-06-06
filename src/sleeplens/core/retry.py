"""Reusable retry helpers with exponential backoff and jitter."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def call_with_backoff(
    fn: Callable[[], T],
    *,
    attempts: int = 6,
    base_delay: float = 0.6,
    max_delay: float = 30.0,
    jitter: float = 0.25,
    retriable: Iterable[type[BaseException]] = (Exception,),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Invoke ``fn`` with exponential backoff and full jitter.

    Parameters
    ----------
    fn:
        Zero-arg callable to invoke.
    attempts:
        Total number of attempts (the first try counts as 1).
    base_delay:
        Delay before the second attempt, in seconds.
    max_delay:
        Hard cap on the backoff delay.
    jitter:
        Fraction of the computed delay to randomise around.
    retriable:
        Tuple of exception classes that should trigger a retry.
    on_retry:
        Optional callback invoked with ``(attempt, exception, next_delay)``.
    """
    retriable_tuple = tuple(retriable)
    last_error: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except retriable_tuple as exc:  # type: ignore[misc]
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = max(0.0, delay * (1.0 + random.uniform(-jitter, jitter)))
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            time.sleep(delay)
    assert last_error is not None
    raise last_error
