"""The per-drive optimize action runs the pass the drive's own media type calls for.

The defect class this guards (D3, C1): the UI's first storage mutation must
never guess the pass. A defrag on an SSD schedules pointless wear; a retrim on
an HDD is a no-op reported as maintenance. The drive's `MediaType` picks —
SSD → ReTrim, HDD → Defrag, anything else → refusal — and a drive letter that
is not a single ASCII letter never reaches the shell.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _drive(letter: str, media_type: str) -> SimpleNamespace:
    return SimpleNamespace(drive_letter=letter, media_type=media_type)


def _post(client: TestClient, letter: str, *, drives, ps=(True, ""), admin=True):
    """Call the route with every collaborator patched; return (response, ps_mock)."""
    with (
        patch("fpstune.api.routes.system_storage.is_admin", return_value=admin),
        patch("fpstune.api.routes.system_storage.sys") as sys_mock,
        patch(
            "fpstune.api.routes.system_storage.get_detailed_storage_drives",
            return_value=drives,
        ),
        patch("fpstune.api.routes.system_storage.run_powershell", return_value=ps) as ps_mock,
    ):
        sys_mock.platform = "win32"
        response = client.post(f"/api/storage/{letter}/optimize")
    return response, ps_mock


class TestOptimizeDrive:
    def test_ssd_gets_a_retrim_never_a_defrag(self, client) -> None:
        response, ps_mock = _post(client, "C", drives=[_drive("C", "SSD")])
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "retrim"
        command = ps_mock.call_args.args[0]
        assert "-ReTrim" in command
        assert "-Defrag" not in command
        assert "-DriveLetter C" in command

    def test_hdd_gets_a_defrag_never_a_retrim(self, client) -> None:
        response, ps_mock = _post(client, "d", drives=[_drive("D", "HDD")])
        assert response.status_code == 200
        assert response.json()["action"] == "defrag"
        command = ps_mock.call_args.args[0]
        assert "-Defrag" in command
        assert "-ReTrim" not in command

    def test_unknown_media_is_a_refusal_not_a_guess(self, client) -> None:
        response, ps_mock = _post(client, "E", drives=[_drive("E", "Unknown")])
        assert response.status_code == 409
        ps_mock.assert_not_called()

    def test_a_drive_letter_that_is_not_a_letter_never_reaches_the_shell(self, client) -> None:
        # ');' would end the PowerShell argument — the boundary check is the
        # injection guard, so it must fire before any collaborator runs.
        response, ps_mock = _post(client, "C%29%3B", drives=[_drive("C", "SSD")])
        assert response.status_code == 400
        ps_mock.assert_not_called()

    def test_an_undetected_drive_is_404(self, client) -> None:
        response, ps_mock = _post(client, "Z", drives=[_drive("C", "SSD")])
        assert response.status_code == 404
        ps_mock.assert_not_called()

    def test_without_admin_nothing_runs(self, client) -> None:
        response, ps_mock = _post(client, "C", drives=[_drive("C", "SSD")], admin=False)
        assert response.status_code == 403
        ps_mock.assert_not_called()

    def test_a_failed_pass_is_reported_failed(self, client) -> None:
        # Verify half of apply/verify: success is PowerShell's exit, never
        # assumed from having launched it.
        response, _ = _post(client, "C", drives=[_drive("C", "SSD")], ps=(False, "access denied"))
        assert response.status_code == 500
        assert "access denied" in response.json()["detail"]
