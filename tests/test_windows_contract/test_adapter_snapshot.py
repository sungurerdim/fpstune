"""The adapter snapshot must actually contain adapters.

#31 is the reason this file exists. `Get-NetAdapterAdvancedProperty` does not
expose `InterfaceIndex`, so every row of the snapshot query came back with a null
index, the parser dropped all of them, and the snapshot was permanently empty.
`get_adapter_property` answers `not_supported` on an empty snapshot — so roughly
fifteen settings per adapter reported "not available on this hardware" and never
appeared in the UI at all. The user applied "everything" and their NIC still had
Interrupt Moderation on.

Nothing caught it, and nothing could have: every test asserted the parser parses.
An empty snapshot is indistinguishable from hardware that genuinely exposes
nothing, unless a test says the machine it runs on has adapters.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.executors.ps_batch import (
    ADAPTER_PROPERTY_MISSING,
    _fetch_adapter_properties_snapshot,
    get_adapter_property,
    init_scan_cache,
    reset_scan_cache,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return _fetch_adapter_properties_snapshot()


def test_snapshot_is_not_empty(snapshot: dict) -> None:
    """Any Windows host running this suite has at least one network adapter."""
    assert snapshot, (
        "adapter snapshot is empty — every per-adapter setting will report "
        "'not supported' and silently vanish from the UI (#31)"
    )


def test_snapshot_keys_carry_a_real_interface_index(snapshot: dict) -> None:
    """The exact failure of #31 was a null index on every row."""
    indices = {key.split("|", 1)[0] for key in snapshot}
    assert indices, "snapshot has no interface indices"
    assert all(index.isdigit() for index in indices), (
        f"non-numeric interface index in snapshot keys: {sorted(indices)}"
    )


def test_a_standard_ndis_keyword_resolves(snapshot: dict) -> None:
    """`*FlowControl` is standardised; a host with Ethernet must publish it.

    Skipped rather than failed on a machine with no wired adapter, because that
    is a real configuration and not a defect.
    """
    wanted = "|*flowcontrol"
    matches = [key for key in snapshot if key.endswith(wanted)]
    if not matches:
        pytest.skip("no adapter on this host publishes *FlowControl")

    index = matches[0].split("|", 1)[0]
    cache, token = init_scan_cache()
    try:
        cache["adapter_properties"] = snapshot
        value = get_adapter_property(index, "*FlowControl")
    finally:
        reset_scan_cache(token)

    assert value != ADAPTER_PROPERTY_MISSING, (
        "the snapshot holds *FlowControl but the lookup could not find it"
    )


def test_lookup_answers_missing_for_a_keyword_no_driver_publishes(
    snapshot: dict,
) -> None:
    """The sentinel must still mean something — a guard that never fails is not one."""
    index = next(iter(snapshot)).split("|", 1)[0]
    cache, token = init_scan_cache()
    try:
        cache["adapter_properties"] = snapshot
        value = get_adapter_property(index, "*FpstuneNoSuchKeyword")
    finally:
        reset_scan_cache(token)

    assert value == ADAPTER_PROPERTY_MISSING
