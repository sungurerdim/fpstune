"""A setting that leaves the registry leaves a recorded decision behind.

Product Goal consequence 6: retiring a harmful tweak means guaranteeing its
harmless value, because a machine that already carries the old value keeps
carrying it. Ten fix commits in the history repaired exactly that after the
fact (a Wi-Fi radio left disabled, 2 s shutdown timeouts left on a volume), and
nothing caught the class mechanically. Three bindings close it:

* every ``guard`` entry points at a registered row whose recommended value is its
  default (the guard semantics: it only ever puts the harmless state back);
* every other entry carries a reason, and ``no_op`` / ``mitigation`` name limit 1
  or limit 2 of consequence 6 instead of a bare "removed";
* the registered id set is pinned in ``registered_ids.txt``, so an id that
  disappears without an entry in ``fpstune.settings.retired`` fails here.

An id *added* to the registry also fails until the snapshot is refreshed, because
an unpinned id could later be removed unseen::

    FPSTUNE_UPDATE_REGISTERED_IDS=1 .venv/Scripts/python -m pytest \
        tests/test_settings/test_retired.py -q

The refresh never forgives a removal: ids missing from the registry must already
have a ``RETIRED`` entry, and the file is rewritten only after that check.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.retired import RETIRED

SNAPSHOT = Path(__file__).with_name("registered_ids.txt")
UPDATE_ENV = "FPSTUNE_UPDATE_REGISTERED_IDS"


@pytest.fixture(scope="module")
def registered() -> dict[str, SettingExecutor]:
    return {s.id: s for s in get_all_static_settings()}


def _snapshot_ids() -> set[str]:
    return {line for line in SNAPSHOT.read_text(encoding="utf-8").splitlines() if line}


def test_the_snapshot_is_parsed() -> None:
    # An empty or unreadable snapshot would make every comparison below vacuous.
    assert len(_snapshot_ids()) > 300


def test_no_id_leaves_the_registry_without_a_decision(
    registered: dict[str, SettingExecutor],
) -> None:
    undecided = sorted(_snapshot_ids() - registered.keys() - RETIRED.keys())
    assert not undecided, (
        f"{undecided} left the registry with no entry in fpstune.settings.retired. "
        "Consequence 6: a machine that already carries the old value keeps carrying "
        "it. Record a guard row, a replacement, or the no-op / mitigation reason."
    )


def test_the_snapshot_matches_the_registry(registered: dict[str, SettingExecutor]) -> None:
    current = set(registered)
    pinned = _snapshot_ids()
    leaving = pinned - current - RETIRED.keys()
    assert not leaving  # a removal is never forgiven by a refresh
    if current != pinned and os.environ.get(UPDATE_ENV) == "1":
        SNAPSHOT.write_text("".join(f"{i}\n" for i in sorted(current)), encoding="utf-8")
        pinned = current
    assert current == pinned, (
        f"added: {sorted(current - pinned)}, removed: {sorted(pinned - current)}. "
        f"Refresh with {UPDATE_ENV}=1 (see this module's docstring)."
    )


def test_a_retired_id_is_not_registered(registered: dict[str, SettingExecutor]) -> None:
    # An id that came back makes its entry a lie about the registry.
    assert sorted(RETIRED.keys() & registered.keys()) == []


def test_every_entry_says_why() -> None:
    bare = [i for i, r in RETIRED.items() if len(r.reason.strip()) < 25]
    assert not bare, f"{bare}: a reason that does not name the evidence is not a reason"


@pytest.mark.parametrize("kind", ["guard", "replaced", "mitigation"])
def test_a_target_is_a_registered_row(kind: str, registered: dict[str, SettingExecutor]) -> None:
    for retired_id, entry in RETIRED.items():
        if entry.kind == kind:
            assert entry.target in registered, f"{retired_id} -> {entry.target} is not registered"


def test_a_no_op_entry_names_no_target() -> None:
    wrong = [i for i, r in RETIRED.items() if r.kind == "no_op" and r.target]
    assert not wrong, f"{wrong}: a row that does not exist as a guard has no target"


def test_a_guard_only_ever_puts_the_harmless_state_back(
    registered: dict[str, SettingExecutor],
) -> None:
    for retired_id, entry in RETIRED.items():
        if entry.kind in ("guard", "mitigation"):
            assert entry.target is not None
            row = registered[entry.target]
            assert values_equal(row.recommended_value, row.default_value), (
                f"{retired_id}: guard {entry.target} recommends {row.recommended_value!r} "
                f"over default {row.default_value!r}; a guard's recommendation IS the default"
            )


def test_a_retired_tweak_that_wrote_a_value_has_a_guard_not_an_open_question() -> None:
    """TcpTimedWaitDelay (30 s against the stock 120 s) is honoured by Windows 11: the
    machines old fpstune wrote it to keep carrying it, so its record is a guard."""
    entry = RETIRED["network:tcp_timed_wait_delay"]
    assert (entry.kind, entry.target) == ("guard", "network:time_wait_delay")


def test_a_security_cost_switch_is_never_a_guard_free_removal() -> None:
    # Limit 2: a mitigation-costing switch stays retired AND a guard restores the
    # mitigation. A "mitigation" entry without a target would drop the second half.
    wrong = [i for i, r in RETIRED.items() if r.kind == "mitigation" and not r.target]
    assert not wrong
