"""An AMD adapter is reported as not judged, with the reason that is true on this machine.

ADLX reads a Radeon's temperature but publishes no throttle limit (its temperature
"ranges" are what the sensor can report, and are documented read-only), so there is
nothing to judge a reading against and fpstune guesses none. Two different reasons can
apply and the reader must say the one that is true: the library is not installed, or it
is and still publishes no limit.
"""

from __future__ import annotations

from fpstune.health.gpu_amd import NO_LIBRARY, NO_PUBLISHED_LIMIT, read
from fpstune.health.model import Gap


def test_an_amd_adapter_without_the_library_says_the_library_is_missing() -> None:
    snapshot = read(installed=False)

    assert snapshot.readings == ()
    assert snapshot.gaps == (Gap("amd_adlx", NO_LIBRARY),)


def test_with_the_library_installed_it_says_no_limit_is_published_and_none_is_guessed() -> None:
    snapshot = read(installed=True)

    assert snapshot.readings == ()
    assert snapshot.gaps == (Gap("amd_adlx", NO_PUBLISHED_LIMIT),)
    assert "no limit is guessed" in NO_PUBLISHED_LIMIT
