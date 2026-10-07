"""The findings route: its shape is a contract, and it never blocks the event loop.

`GET /api/health/findings` is what the Optimize tab's problem count and the rows
under each device read (#107, H2/H3). What this file pins is what those readers
depend on and could not see break: the exact fields of a finding, that a healthy
machine is `findings: []` and not an error, that a gap is reported beside the list,
and that the instruments — which start PowerShell — run on a worker thread.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.health.findings import Finding, Gap, HealthReport, Quantity

ROUTE = "/api/health/findings"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _report(findings: tuple[Finding, ...] = (), unmeasured: tuple[Gap, ...] = ()) -> HealthReport:
    return HealthReport(findings=findings, unmeasured=unmeasured, measured_at=1_790_000_000.0)


class TestShape:
    def test_a_healthy_machine_is_an_empty_list_not_an_error(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.health.collect", return_value=_report()):
            response = client.get(ROUTE)

        assert response.status_code == 200
        assert response.json() == {
            "findings": [],
            "unmeasured": [],
            "measured_at": 1_790_000_000.0,
        }

    def test_a_finding_carries_exactly_the_fields_the_ui_reads(self, client: TestClient) -> None:
        finding = Finding(
            component="gpu",
            device_id="PCI\\VEN_10DE&DEV_249D",
            severity="warning",
            title_key="health.gpu.pcie_link_width",
            reading=Quantity(8.0, "lanes"),
            limit=Quantity(16.0, "lanes"),
            source="pcie_link",
        )
        with patch("fpstune.api.routes.health.collect", return_value=_report((finding,))):
            body: dict[str, Any] = client.get(ROUTE).json()

        assert body["findings"] == [
            {
                "component": "gpu",
                "device_id": "PCI\\VEN_10DE&DEV_249D",
                "severity": "warning",
                "title_key": "health.gpu.pcie_link_width",
                "reading": {"value": 8.0, "unit": "lanes"},
                "limit": {"value": 16.0, "unit": "lanes"},
                "source": "pcie_link",
            }
        ]

    def test_an_event_finding_has_no_device_and_no_limit_as_nulls(self, client: TestClient) -> None:
        finding = Finding(
            "system",
            None,
            "warning",
            "health.system.hardware_errors",
            Quantity(3.0, "events"),
            None,
            "event_scan",
        )
        with patch("fpstune.api.routes.health.collect", return_value=_report((finding,))):
            row = client.get(ROUTE).json()["findings"][0]

        assert row["device_id"] is None
        assert row["limit"] is None

    def test_a_gap_is_reported_beside_the_list(self, client: TestClient) -> None:
        gap = Gap("storage_health", "needs administrator")
        with patch("fpstune.api.routes.health.collect", return_value=_report(unmeasured=(gap,))):
            body = client.get(ROUTE).json()

        assert body["findings"] == []
        assert body["unmeasured"] == [{"source": "storage_health", "reason": "needs administrator"}]

    def test_the_schema_names_a_response_model_not_a_bare_object(self) -> None:
        operation = create_app().openapi()["paths"][ROUTE]["get"]

        reference = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert reference.endswith("/HealthFindingsResponse")


class TestRefresh:
    def test_refresh_is_passed_through_and_defaults_to_the_cache(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.health.collect", return_value=_report()) as collect:
            client.get(ROUTE)
            client.get(ROUTE, params={"refresh": "true"})

        assert [call.kwargs for call in collect.call_args_list] == [
            {"refresh": False},
            {"refresh": True},
        ]


class TestOffTheEventLoop:
    def test_the_instruments_run_on_a_worker_thread(self, client: TestClient) -> None:
        """They start PowerShell: on the loop they would freeze every other request."""
        on_loop: list[bool] = []

        def _collect(**_kwargs: Any) -> HealthReport:
            try:
                asyncio.get_running_loop()
                on_loop.append(True)
            except RuntimeError:
                on_loop.append(False)
            return _report()

        with patch("fpstune.api.routes.health.collect", side_effect=_collect):
            client.get(ROUTE)

        assert on_loop == [False]
