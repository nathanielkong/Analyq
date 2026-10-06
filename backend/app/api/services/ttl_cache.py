from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Generic, Hashable, TypeVar


CacheKey = TypeVar("CacheKey", bound=Hashable)
CacheValue = TypeVar("CacheValue")


@dataclass(frozen=True)
class CacheEntry(Generic[CacheValue]):
    value: CacheValue
    expires_at: float


class TTLCache(Generic[CacheKey, CacheValue]):
    def __init__(
        self,
        ttl_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Cache TTL must be greater than zero.")

        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[CacheKey, CacheEntry[CacheValue]] = {}
        self._lock = RLock()

    def get(self, key: CacheKey) -> CacheValue | None:
        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                return None

            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None

            return entry.value

    def set(self, key: CacheKey, value: CacheValue) -> None:
        with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=self._clock() + self._ttl_seconds,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
