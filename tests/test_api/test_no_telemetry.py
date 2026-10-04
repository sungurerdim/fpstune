"""fpstune sends nothing off the machine, whatever the environment says.

FastAPI 0.142 added OpenTelemetry that auto-configures an OTLP exporter as soon
as ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set — by another tool, a corporate image,
a developer shell. Left at its defaults, request spans, metrics and logs of a
local admin tool would start leaving the machine without anyone asking.
"""

from __future__ import annotations

import pytest

from fpstune.api.main import create_app


def test_every_telemetry_signal_and_auto_configuration_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example.com")
    app = create_app()

    config = app._telemetry  # FastAPI keeps the merged config only here
    assert config["auto_configure"] is False
    assert config["tracing"] is False
    assert config["metrics"] is False
    assert config["logs"] is False
    assert config["operation_spans"] is False
