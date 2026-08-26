"""Tests for ps_batch — scan-context cache and service lookup helpers."""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest

from fpstune.settings.executors.ps_batch import (
    DETECT_ERROR_PREFIX,
    DETECT_GROUP_SIZE,
    DETECT_JSON_MARKER,
    MAX_DETECT_SESSIONS,
    _fetch_services_snapshot,
    _partition,
    _run_detect_group,
    command_is_batchable,
    get_service_start_type,
    init_scan_cache,
    prefetch_services,
    reset_scan_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SERVICES_JSON = json.dumps(
    [
        {"Name": "SysMain", "StartType": 2},
        {"Name": "DiagTrack", "StartType": 4},
        {"Name": "wuauserv", "StartType": 3},
        {"Name": "AudioSrv", "StartType": 2},
    ]
)

_SINGLE_SERVICE_JSON = json.dumps({"Name": "OneSvc", "StartType": 3})


# ---------------------------------------------------------------------------
# init_scan_cache / reset_scan_cache
# ---------------------------------------------------------------------------


class TestScanCacheLifecycle:
    """Tests for init/reset scan cache context-var lifecycle."""

    def test_init_returns_empty_dict_and_token(self):
        cache, token = init_scan_cache()
        try:
            assert isinstance(cache, dict)
            assert len(cache) == 0
        finally:
            reset_scan_cache(token)

    def test_reset_restores_previous_state(self):
        # Outside any scan context, cache should be None (default)
        from fpstune.settings.executors.ps_batch import _get_cache

        assert _get_cache() is None

        cache, token = init_scan_cache()
        try:
            assert _get_cache() is not None
        finally:
            reset_scan_cache(token)

        assert _get_cache() is None

    def test_nested_contexts_are_independent(self):
        from fpstune.settings.executors.ps_batch import _get_cache

        outer_cache, outer_token = init_scan_cache()
        outer_cache["key1"] = "val1"
        try:
            inner_cache, inner_token = init_scan_cache()
            inner_cache["key2"] = "val2"
            try:
                # Inner cache is a fresh dict
                assert "key1" not in inner_cache
                assert "key2" in inner_cache
            finally:
                reset_scan_cache(inner_token)

            # After inner reset, outer cache is restored
            current = _get_cache()
            assert current is outer_cache
        finally:
            reset_scan_cache(outer_token)


# ---------------------------------------------------------------------------
# _fetch_services_snapshot
# ---------------------------------------------------------------------------


class TestFetchServicesSnapshot:
    """Tests for _fetch_services_snapshot() JSON parsing."""

    def test_returns_empty_dict_on_non_windows(self):
        with patch("sys.platform", "linux"):
            result = _fetch_services_snapshot()
        assert result == {}

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_parses_list_response(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            snapshot = _fetch_services_snapshot()

        assert "sysmain" in snapshot
        assert snapshot["sysmain"]["start_type"] == 2
        assert "diagtrack" in snapshot
        assert snapshot["diagtrack"]["start_type"] == 4

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_parses_single_object_response(self):
        """PS ConvertTo-Json returns a bare object (not array) for a single item."""
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SINGLE_SERVICE_JSON),
        ):
            snapshot = _fetch_services_snapshot()

        assert "onesvc" in snapshot
        assert snapshot["onesvc"]["start_type"] == 3

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_returns_empty_on_powershell_failure(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(False, "Error"),
        ):
            snapshot = _fetch_services_snapshot()

        assert snapshot == {}

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_returns_empty_on_malformed_json(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, "{ not valid json"),
        ):
            snapshot = _fetch_services_snapshot()

        assert snapshot == {}

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_keys_are_lowercased(self):
        data = json.dumps([{"Name": "WUAUSERV", "StartType": 3}])
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, data),
        ):
            snapshot = _fetch_services_snapshot()

        # All names must be lower-cased for case-insensitive lookup
        assert "wuauserv" in snapshot
        assert "WUAUSERV" not in snapshot

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_items_without_name_are_skipped(self):
        data = json.dumps([{"StartType": 2}, {"Name": "ValidSvc", "StartType": 3}])
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, data),
        ):
            snapshot = _fetch_services_snapshot()

        assert len(snapshot) == 1
        assert "validsvc" in snapshot


# ---------------------------------------------------------------------------
# get_service_start_type
# ---------------------------------------------------------------------------


class TestGetServiceStartType:
    """Tests for get_service_start_type() lookup logic."""

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_returns_start_type_as_string(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            result = get_service_start_type("SysMain")

        assert result == "2"

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_case_insensitive_lookup(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            result = get_service_start_type("SYSMAIN")

        assert result == "2"

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_returns_not_found_for_missing_service(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            result = get_service_start_type("NonExistentService")

        assert result == "not_found"

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_disabled_service_returns_4(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            result = get_service_start_type("DiagTrack")

        assert result == "4"

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_manual_service_returns_3(self):
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ):
            result = get_service_start_type("wuauserv")

        assert result == "3"

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_uses_scan_cache_when_available(self):
        """Inside a scan context, snapshot is read from cache — no extra PS call."""
        cache, token = init_scan_cache()
        try:
            # Pre-populate snapshot in cache
            cache["services_snapshot"] = {
                "myservice": {"start_type": 2},
            }

            with patch("fpstune.settings.executors.ps_batch.run_powershell") as mock_ps:
                result = get_service_start_type("myservice")

            # Should NOT have called run_powershell — snapshot already in cache
            mock_ps.assert_not_called()
            assert result == "2"
        finally:
            reset_scan_cache(token)

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_scan_cache_miss_fetches_snapshot(self):
        """Inside a scan context without services_snapshot, it fetches lazily."""
        cache, token = init_scan_cache()
        try:
            assert "services_snapshot" not in cache

            with patch(
                "fpstune.settings.executors.ps_batch.run_powershell",
                return_value=(True, _SERVICES_JSON),
            ):
                result = get_service_start_type("SysMain")

            assert result == "2"
            # Cache must now hold the snapshot for subsequent calls
            assert "services_snapshot" in cache
        finally:
            reset_scan_cache(token)


# ---------------------------------------------------------------------------
# prefetch_services
# ---------------------------------------------------------------------------


class TestPrefetchServices:
    """Tests for prefetch_services() idempotency and caching."""

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_idempotent_within_scan(self):
        """Second call inside same scan must not run powershell again."""
        cache, token = init_scan_cache()
        try:
            with patch(
                "fpstune.settings.executors.ps_batch.run_powershell",
                return_value=(True, _SERVICES_JSON),
            ) as mock_ps:
                prefetch_services()
                prefetch_services()

            assert mock_ps.call_count == 1
        finally:
            reset_scan_cache(token)

    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
    def test_outside_scan_always_fetches(self):
        """Outside a scan context, each call runs powershell (no caching)."""
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, _SERVICES_JSON),
        ) as mock_ps:
            prefetch_services()
            prefetch_services()

        assert mock_ps.call_count == 2


# ---------------------------------------------------------------------------
# Shared detect sessions
# ---------------------------------------------------------------------------


class TestBatchability:
    """What may share a session, and why the exclusions exist."""

    def test_exit_is_excluded(self):
        """`exit` at the top level of a -Command script kills the whole session."""
        assert not command_is_batchable("if (-not $p) { Write-Output 'no'; exit 0 }; 'yes'")

    def test_write_host_is_excluded(self):
        """Host output escapes the per-command capture and lands in the session's stdout.

        Measured on the dev machine: two such commands cost their entire group of
        twelve settings, every one of which then fell back to its own subprocess.
        """
        assert not command_is_batchable("Write-Host 'FPSTUNE_WARN: nope'; 'value'")

    def test_ordinary_command_is_batchable(self):
        assert command_is_batchable(r"(Get-ItemProperty -Path 'HKCU:\Control Panel' -Name 'Y').Y")

    def test_empty_command_is_not_batchable(self):
        assert not command_is_batchable("   ")


class TestGroupOutputParsing:
    """The group must survive output it did not expect."""

    def test_stray_host_output_does_not_cost_the_group(self):
        """One noisy command must not make the whole document unparseable."""
        payload = json.dumps({"a:one": "first", "a:two": "second"})
        noisy = f"WARNING: something chatty\n{DETECT_JSON_MARKER}\n{payload}"
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell", return_value=(True, noisy)
        ):
            results = _run_detect_group([("a:one", "cmd1"), ("a:two", "cmd2")])
        assert results == {"a:one": "first", "a:two": "second"}

    def test_failed_command_is_not_reported_as_a_value(self):
        """A raising command must fall back to a live run, not surface its message."""
        payload = json.dumps({"a:one": "fine", "a:two": DETECT_ERROR_PREFIX + "boom"})
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell",
            return_value=(True, f"{DETECT_JSON_MARKER}\n{payload}"),
        ):
            results = _run_detect_group([("a:one", "cmd1"), ("a:two", "cmd2")])
        assert results == {"a:one": "fine"}

    def test_unparseable_output_resolves_nothing(self):
        """Degrade to the per-setting path rather than invent values."""
        with patch(
            "fpstune.settings.executors.ps_batch.run_powershell", return_value=(True, "garbage")
        ):
            assert _run_detect_group([("a:one", "cmd1")]) == {}


class TestPartition:
    """Sessions are balanced, because an extra group waits for a free slot."""

    def _specs(self, n):
        return [(f"s:{i}", "cmd") for i in range(n)]

    def test_never_exceeds_the_session_cap_when_it_fits(self):
        """53 commands used to become five groups against four slots — one waited."""
        groups = _partition(self._specs(53))
        assert len(groups) <= MAX_DETECT_SESSIONS
        assert sum(len(g) for g in groups) == 53

    def test_groups_are_near_equal(self):
        """An oversized last group would decide the phase on its own."""
        groups = _partition(self._specs(53))
        assert max(len(g) for g in groups) - min(len(g) for g in groups) <= 1
        assert all(len(g) <= DETECT_GROUP_SIZE for g in groups)

    def test_group_size_stays_bounded_for_large_inputs(self):
        groups = _partition(self._specs(500))
        assert all(len(g) <= DETECT_GROUP_SIZE for g in groups)
        assert sum(len(g) for g in groups) == 500

    def test_empty_input_produces_no_sessions(self):
        assert _partition([]) == []


class TestShippedDefinitionsStayBatchable:
    """A definition that opts itself out of batching should do so on purpose."""

    def test_no_shipped_detect_command_uses_exit(self):
        """`exit` costs the setting its session slot and is never needed.

        Every guard clause in the shipped commands means "stop this command", not
        "stop the process", and `return` says exactly that — measured equivalent
        both standalone and inside the group's `& { }` wrapper. Thirty-one sites
        were converted; this pins that a new one cannot reintroduce the pattern
        and quietly cost a subprocess per scan.
        """
        from fpstune.settings.base import DetectType
        from fpstune.settings.registry import SettingsRegistry

        offenders = [
            s.id
            for s in SettingsRegistry(discover_dynamic=False).get_all()
            if s.detect_type == DetectType.POWERSHELL
            and re.search(r"(^|[;{(\s])exit\b", s.detect_command)
        ]
        assert offenders == []
