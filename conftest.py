"""Shared pytest fixtures.

Both of these exist because the cache is process-global. Locmem outlives an
individual test, so throttle counters and cached brews leak from one test into
the next, and the resulting failure looks like a flake rather than a cause.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def disable_throttling():
    """Throttling off unless a test opts back in.

    A test class that makes twenty brew requests is testing the solver, not
    the rate limiter, and should not start failing at request twenty-one.

    Patches the class attribute rather than using `override_settings`:
    DRF binds `SimpleRateThrottle.THROTTLE_RATES` to the settings dict at
    import time, so overriding REST_FRAMEWORK does nothing to an
    already-imported throttle class. Tests that do cover throttling re-enable
    it with `cards.tests.test_throttling_and_cache.throttled`.
    """
    with patch.object(
        SimpleRateThrottle, "THROTTLE_RATES", {"brew": None, "read": None}
    ):
        yield
