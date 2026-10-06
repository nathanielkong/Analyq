from app.api.services.ttl_cache import TTLCache


def test_ttl_cache_returns_value_until_it_expires() -> None:
    current_time = [100.0]
    cache: TTLCache[str, str] = TTLCache(
        ttl_seconds=30,
        clock=lambda: current_time[0],
    )

    cache.set("NVDA", "cached quote")

    assert cache.get("NVDA") == "cached quote"

    current_time[0] = 130.0

    assert cache.get("NVDA") is None


def test_ttl_cache_clear_removes_all_values() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30)
    cache.set("NVDA", 1)

    cache.clear()

    assert cache.get("NVDA") is None
