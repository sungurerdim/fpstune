"""What a timestamp promises the UI: the same string in every locale, the machine's
own clock rather than UTC, and nothing that survives a DST boundary.

Nothing tested either half of this before. The activity log is the one timestamp
that crosses the wire to the UI: ``ActivityLog.add()`` renders the local wall clock
as ``HH:MM:SS``, and ``frontend/src/components/ActivityLog.tsx`` prints that string
verbatim into a fixed-width monospace column. So this is a *display* contract, and
every way of breaking it is invisible on the machine that wrote the code and visible
on somebody else's -- a different locale, a different UTC offset, one Sunday morning
a year.

The frontend half of the same contract is
``frontend/src/components/__tests__/ActivityLogTimestamp.test.tsx``, which pins that
the string is printed rather than re-parsed. The two halves have to be read together:
this file says what is emitted, that one says nothing reinterprets it.

Fixed UTC offsets rather than ``zoneinfo`` names on purpose -- ``tzdata`` is not a
declared dependency of this project, and a DST boundary is exactly a pair of offsets
either side of an instant. -05:00 and -04:00 are US Eastern's two offsets; +03:00 is
Istanbul, a useful non-UTC zone precisely because it has had no DST since 2016.
"""

from __future__ import annotations

import locale
import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest

import fpstune.utils.logger as logger_module
from fpstune.utils.logger import ActivityLog

# US Eastern's two offsets. The zone is not a constant; these are.
EST = timezone(timedelta(hours=-5))
EDT = timezone(timedelta(hours=-4))
# Istanbul: permanently +03:00, so it separates "not UTC" from "has DST".
ISTANBUL = timezone(timedelta(hours=3))

HH_MM_SS = re.compile(r"[0-9]{2}:[0-9]{2}:[0-9]{2}")

# Tried in order; whichever the machine actually has get exercised. Both the
# POSIX and the Windows NLS spellings are listed because the suite runs on
# Windows and the release workflow does not.
NON_ENGLISH_LC_TIME = (
    "tr_TR.UTF-8",
    "Turkish_Turkey.1254",
    "de_DE.UTF-8",
    "German_Germany.1252",
    "ja_JP.UTF-8",
    "Japanese_Japan.932",
    "fr_FR.UTF-8",
    "French_France.1252",
)


class _FrozenClock:
    """Stands in for the ``datetime`` class, answering ``now()`` from one instant.

    ``now(tz)`` is honoured rather than ignored, which is the whole point. The
    reflex fix when someone notices these timestamps are naive is to write
    ``datetime.now(timezone.utc)``; against a stub that ignored its argument that
    change would still produce the expected string and the test would wave it
    through. Here it produces a genuinely different string, so the test that says
    "the panel shows the user's own clock" actually fails.
    """

    def __init__(self, instant: datetime, local: tzinfo) -> None:
        self._instant = instant
        self._local = local

    def now(self, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            # What a naive `datetime.now()` returns: local civil time, no offset.
            return self._instant.astimezone(self._local).replace(tzinfo=None)
        return self._instant.astimezone(tz)


def _stamp_at(monkeypatch: pytest.MonkeyPatch, instant: datetime, local: tzinfo) -> str:
    """The timestamp the activity log writes for `instant` on a machine in `local`."""
    monkeypatch.setattr(logger_module, "datetime", _FrozenClock(instant, local))
    log = ActivityLog()
    log.add("Applied network:nagle_algorithm", level="success")
    return log.get_entries()[0]["timestamp"]


class TestTheTimestampReadsTheSameInEveryLocale:
    """The UI sizes a fixed-width column for it, so its width is part of the contract."""

    def test_every_locale_this_machine_has_renders_the_same_eight_characters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`%H:%M:%S` is locale-independent. Several of its neighbours are not, and
        the difference is invisible in a diff.

        Measured on this machine, same instant, `LC_TIME` varied over the seven
        locales below: `%H:%M:%S` gave `17:05:03` in every one of them, while `%p`
        gave `PM` under C, `OS` under `tr_TR` -- non-ASCII, in a column the panel
        sizes for eight characters -- Japanese text under `ja_JP`, and the empty
        string under `de_DE` and `fr_FR`, which drops the marker with no error at
        all. So a format that reaches for `%p`, `%X`, `%c` or `%x` renders
        differently on machines the author will never run, and this is what
        notices.

        Deliberately a comparison between locales rather than against a fixed
        expected string: `%X` happens to match `%H:%M:%S` in the Windows CRT this
        was measured on, so an assertion written against one platform's `%X` would
        prove nothing. Any directive whose output depends on `LC_TIME` breaks the
        equality below, whichever directive and whichever platform.

        The instant is frozen so the locales are compared against each other and
        not against the clock, and "C" is always present so this never degenerates
        into a test that asserts nothing on a machine with one locale installed.
        """
        instant = datetime(2026, 8, 25, 14, 5, 3, tzinfo=UTC)
        original = locale.setlocale(locale.LC_TIME)
        rendered: dict[str, str] = {}
        try:
            for name in ("C", *NON_ENGLISH_LC_TIME):
                try:
                    locale.setlocale(locale.LC_TIME, name)
                except locale.Error:
                    continue  # not installed here; whichever are get exercised
                rendered[name] = _stamp_at(monkeypatch, instant, ISTANBUL)
        finally:
            locale.setlocale(locale.LC_TIME, original)

        assert "C" in rendered, "the C locale is always available; setlocale is broken"
        for name, stamp in rendered.items():
            assert HH_MM_SS.fullmatch(stamp), (
                f"LC_TIME={name} rendered {stamp!r}, which is not the fixed-width "
                "HH:MM:SS the activity panel reserves room for"
            )
        assert len(set(rendered.values())) == 1, (
            f"the same instant rendered differently per locale: {rendered}"
        )


class TestTheTimestampIsTheMachinesOwnClock:
    """Local wall clock, because there is nothing in the string to say otherwise."""

    def test_it_shows_local_time_rather_than_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bare `HH:MM:SS` with no offset is only readable as the user's own clock.

        14:05:03Z is 17:05:03 in Istanbul. If this ever emits UTC, the panel shows
        17:05 activity stamped 14:05 with nothing in the string to reveal the
        shift -- the user reads three-hour-old events as current, and the only
        symptom is that the log looks stale.
        """
        instant = datetime(2026, 8, 25, 14, 5, 3, tzinfo=UTC)

        assert _stamp_at(monkeypatch, instant, ISTANBUL) == "17:05:03"

    def test_two_machines_in_different_zones_stamp_the_same_instant_differently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The corollary, and the reason the string can never leave the machine.

        The same instant is 17:05:03 in Istanbul and 10:05:03 in New York. That is
        correct for a local desktop app and wrong for anything that ships a log
        somewhere else, so it is pinned here rather than discovered by whoever
        first attaches an activity log to a bug report.
        """
        instant = datetime(2026, 8, 25, 14, 5, 3, tzinfo=UTC)

        assert _stamp_at(monkeypatch, instant, ISTANBUL) == "17:05:03"
        assert _stamp_at(monkeypatch, instant, EDT) == "10:05:03"


class TestTheTimestampAtADstBoundary:
    """One Sunday morning a year, local wall clock is not a function of elapsed time."""

    def test_it_follows_the_spring_forward_jump(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One second of activity crosses an hour that does not exist.

        US Eastern jumps 02:00 -> 03:00 on 2026-03-08. The log must print the
        civil times the platform reports, 01:59:59 then 03:00:00. Anything that
        computes its own offset -- `utcnow()` plus a remembered constant, the
        other reflex fix -- prints 02:00:00, a reading that never appeared on any
        clock in the zone.
        """
        before = _stamp_at(monkeypatch, datetime(2026, 3, 8, 6, 59, 59, tzinfo=UTC), EST)
        after = _stamp_at(monkeypatch, datetime(2026, 3, 8, 7, 0, 0, tzinfo=UTC), EDT)

        assert before == "01:59:59"
        assert after == "03:00:00"

    def test_an_hour_apart_at_the_fall_back_renders_identically(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Which is why this string is printed and never computed with.

        US Eastern repeats 01:00-02:00 on 2026-11-01. Two entries a full hour
        apart both render 01:30:00, because the format carries no date and no
        offset. So the timestamp cannot order two entries, cannot yield a
        duration, and cannot be parsed into an instant -- and this test is the
        record of that, so that a future "sort the activity log by time" is
        recognised as impossible against this field rather than shipped as a
        subtle one-hour reordering that only appears one night a year.

        Widening the format to carry a date and an offset would fail here. That is
        the intended way to find this test: it is a limit worth revisiting, not a
        limit worth being surprised by.
        """
        earlier = _stamp_at(monkeypatch, datetime(2026, 11, 1, 5, 30, 0, tzinfo=UTC), EDT)
        later = _stamp_at(monkeypatch, datetime(2026, 11, 1, 6, 30, 0, tzinfo=UTC), EST)

        assert earlier == later == "01:30:00", (
            "if these now differ the format grew a date or an offset, which is an "
            "improvement -- update this test deliberately rather than deleting it"
        )
