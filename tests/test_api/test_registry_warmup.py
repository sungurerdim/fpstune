"""The first screen must not pay for hardware discovery.

``/settings/definitions`` is documented as static and instant. It was not:
building the registry enumerates network adapters, reads their driver metadata
and detects monitors, and the first request paid all of it. Measured, 1.80 s for
the first call and 0.01 s for every one after — landing squarely on the first
screen a user ever sees.

The work is now started at app startup in a daemon thread, so it overlaps the
browser's own bundle fetch. Measured in a fresh process per row, so no row is
reading the registry the previous one built:

    browser window 0.0s -> 1.67s      1.5s -> 0.05s
    browser window 0.5s -> 1.08s      2.0s -> 0.01s
    browser window 1.0s -> 0.56s

Nothing got faster; the cost moved off the request path. A request that still
arrives first blocks on the lock and receives the answer the warm-up was already
computing — which is the point of the lock, and why it had to be added in the
same change.

The singleton lives in ``fpstune.settings.registry_cache`` (H1): a route module
was the only place anything could ask for the registry, and the benchmark and
debug routes were reaching into a sibling route's privates to get it. These
tests exercise the owning module; the route module keeps a one-line delegate as
the seam its own tests patch.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import fpstune.settings.registry_cache as registry_cache


@pytest.fixture(autouse=True)
def cold_registry():
    """Every test here starts from an unbuilt registry and leaves one behind.

    The cache is a module global, so a test that forgot this would measure
    whatever an earlier test built and pass without exercising anything.
    """
    original = registry_cache._registry
    registry_cache._registry = None
    yield
    registry_cache._registry = original


class TestTheRegistryIsBuiltOnce:
    def test_two_callers_arriving_together_share_one_build(self) -> None:
        """A bare check-then-build lets both run the whole hardware discovery.

        The warm-up makes a second caller likely rather than rare, so this
        stopped being theoretical the moment the warm-up existed.
        """
        builds: list[int] = []
        start = threading.Barrier(8, timeout=10)

        class _Slow:
            def __init__(self, *_a: object, **_k: object) -> None:
                builds.append(1)
                time.sleep(0.05)

        def ask() -> None:
            start.wait(timeout=10)
            registry_cache.get_registry()

        with patch.object(registry_cache, "SettingsRegistry", _Slow):
            threads = [threading.Thread(target=ask) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

        assert len(builds) == 1, (
            f"{len(builds)} threads each enumerated the machine's hardware; "
            "one build is the whole point of the cache"
        )

    def test_everyone_gets_the_same_instance(self) -> None:
        with patch.object(registry_cache, "SettingsRegistry", lambda *_a, **_k: object()):
            first = registry_cache.get_registry()
            second = registry_cache.get_registry()
        assert first is second

    def test_the_route_delegate_serves_the_same_singleton(self) -> None:
        """The route module's `_get_registry` is a seam, not a second cache."""
        from fpstune.api.routes import settings as settings_routes

        with patch.object(registry_cache, "SettingsRegistry", lambda *_a, **_k: object()):
            assert settings_routes._get_registry() is registry_cache.get_registry()


class TestTheWarmUpIsNotLoadBearing:
    def test_a_failing_warm_up_does_not_raise(self) -> None:
        """It is an optimisation. The next real request rebuilds.

        Raising here would take the API down at startup over a hardware probe
        that the request path already knows how to retry.
        """
        with patch.object(registry_cache, "SettingsRegistry", side_effect=OSError("no hardware")):
            registry_cache.warm_registry()  # must not raise

    def test_it_leaves_nothing_half_built_behind(self) -> None:
        """A failed build must not cache a broken registry for every later call."""
        with patch.object(registry_cache, "SettingsRegistry", side_effect=OSError("no hardware")):
            registry_cache.warm_registry()

        assert registry_cache._registry is None

    def test_a_successful_warm_up_is_what_the_next_request_gets(self) -> None:
        sentinel = object()
        with patch.object(registry_cache, "SettingsRegistry", lambda *_a, **_k: sentinel):
            registry_cache.warm_registry()
            assert registry_cache.get_registry() is sentinel


class TestStartupSchedulesIt:
    def test_the_app_starts_the_warm_up(self) -> None:
        """Off the request path, or it is not a warm-up at all."""
        from fpstune.api.main import create_app

        warmed = threading.Event()

        with (
            patch.object(registry_cache, "SettingsRegistry", lambda *_a, **_k: object()),
            patch.object(registry_cache, "warm_registry", side_effect=lambda: warmed.set()),
            TestClient(create_app()),
        ):
            assert warmed.wait(timeout=10), "startup never scheduled the registry warm-up"
