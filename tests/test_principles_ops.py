"""Catalogue section E, P-REPRO and P-HYRUM, bound to this repository.

These are the gates about *operating* fpstune rather than about what it tweaks:

* P-LEASTPRIV — what the GitHub workflows are allowed to do. Every action is a
  full commit SHA (a tag is mutable, so `@v7` lets its owner change what runs
  with this repository's token), every workflow starts from read-only
  permissions, the one job that publishes asks for its write scopes itself, and
  the job that produces the artifact users download does not consume a cache.
* P-FAILFAST — invalid configuration is refused where it is read. `serve` used
  to hand a negative port to `socket.bind`, which answers `OverflowError`, so
  the user got a traceback instead of a sentence.
* P-FAILCLOSED — a failed elevation or admin check refuses the write; it never
  proceeds and hopes for the best.
* P-REPRO — a commit rebuilds the same artifacts: lock files are tracked, CI
  installs from them (`uv sync --locked`, `npm ci`), and no workflow installs a
  floating package version.
* P-HYRUM — the public API contract is pinned: a route's path, method and
  response model are what a client may depend on, so changing one is a
  deliberate edit to this file rather than a silent break.

P-DEPTH, P-SIGNALS, P-ERRBUDGET, P-RPORTO and P-321 are N/A for a local-only
desktop tool; the evidence for each is recorded in the task report and belongs
in docs/PRINCIPLES.md, not here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

#: `owner/repo[/subpath]@<40 hex>` — a pinned action, the only form allowed.
_SHA_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}$")

#: The tag a SHA came from, written beside it so a bump is a readable diff.
_TAG_COMMENT = re.compile(r"#\s*v?\d")

_USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$")


def _workflows() -> dict[str, dict[str, Any]]:
    """Every workflow, parsed. GitHub reads YAML 1.2; the only key PyYAML 1.1
    rewrites is `on:`, which no gate here reads."""
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOW_DIR.glob("*.yml"))
    }


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step for job in (workflow.get("jobs") or {}).values() for step in (job.get("steps") or [])
    ]


def _run_steps(workflow: dict[str, Any]) -> list[str]:
    return [str(step["run"]) for step in _steps(workflow) if step.get("run")]


def _git_tracked() -> set[str]:
    """Every path git tracks, as posix relative paths.

    Skipped when there is no checkout to ask (a wheel-installed test run): the
    repository is the thing under audit here, so there is nothing to judge.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=False
    )
    if result.returncode != 0:
        pytest.skip("git is not available to enumerate the tracked tree")
    return {
        name.replace("\\", "/")
        for name in result.stdout.decode("utf-8", "replace").split("\0")
        if name
    }


class TestPLeastPriv:
    """P-LEASTPRIV: every process, token and job gets only what it needs."""

    def test_every_action_reference_is_a_full_commit_sha(self) -> None:
        unpinned = [
            f"{name}: {step['uses']}"
            for name, workflow in _workflows().items()
            for step in _steps(workflow)
            if (uses := str(step.get("uses") or ""))
            and not uses.startswith("$/")
            and not _SHA_PIN.match(uses)
        ]

        assert not unpinned, "actions are not pinned to a commit SHA: " + ", ".join(unpinned)

    def test_every_pinned_action_names_the_tag_it_came_from(self) -> None:
        missing: list[str] = []
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = _USES_LINE.match(line)
                if match is None:
                    continue
                reference, rest = match.groups()
                if reference.startswith("$/") or not _SHA_PIN.match(reference):
                    continue
                if not _TAG_COMMENT.search(rest):
                    missing.append(f"{path.name}:{lineno} {reference}")

        assert not missing, "a pinned SHA with no tag comment cannot be bumped: " + ", ".join(
            missing
        )

    def test_every_workflow_declares_read_only_permissions(self) -> None:
        for name, workflow in _workflows().items():
            permissions = workflow.get("permissions")
            assert isinstance(permissions, dict), f"{name} declares no permissions: block"
            for scope, level in permissions.items():
                assert level in ("read", "none"), (
                    f"{name} grants {scope}: {level} at workflow level; a job that needs "
                    "more must ask for it itself"
                )

    def test_write_is_asked_for_by_the_one_job_that_publishes(self) -> None:
        release = _workflows()["release.yml"]

        assert release["jobs"]["publish"]["permissions"] == {
            "contents": "write",
            "id-token": "write",
            "attestations": "write",
        }
        for job_name, job in release["jobs"].items():
            if job_name == "publish":
                continue
            for scope, level in (job.get("permissions") or {}).items():
                assert level == "read", f"{job_name} asks for {scope}: {level}"

    def test_the_publishing_job_does_not_consume_a_cache(self) -> None:
        """cache-poisoning: the job that publishes the artifact users download
        must not read a cache anyone else could have written."""
        release = _workflows()["release.yml"]
        uv_steps = [
            step
            for step in _steps(release)
            if str(step.get("uses") or "").startswith("astral-sh/setup-uv")
        ]

        assert uv_steps, "release.yml no longer installs uv; update this gate"
        for step in uv_steps:
            assert (step.get("with") or {}).get("enable-cache") is False

    def test_no_checkout_leaves_the_job_token_on_disk(self) -> None:
        """artipacked: nothing here pushes with git, so the token is not persisted."""
        offenders = [
            name
            for name, workflow in _workflows().items()
            for step in _steps(workflow)
            if str(step.get("uses") or "").startswith("actions/checkout")
            and (step.get("with") or {}).get("persist-credentials") is not False
        ]

        assert not offenders, f"checkout persists credentials in: {offenders}"

    def test_the_ci_workflow_is_called_by_its_self_repository_form(self) -> None:
        """`./` can load a workflow cloned at runtime; `$/` cannot (zizmor)."""
        assert _workflows()["release.yml"]["jobs"]["ci"]["uses"] == "$/.github/workflows/ci.yml"

    def test_each_accepted_zizmor_finding_is_an_inline_ignore_with_a_reason(self) -> None:
        """Shrink-only allowlist: fix one, delete its entry, or this fails.

        A finding is accepted only when it is written down in the workflow as an
        inline `# zizmor: ignore[rule]` with the reason beside it.
        """
        accepted = {
            (
                "release.yml",
                "superfluous-actions",
            ): "refuses a tag whose release already exists",
        }

        for (filename, rule), reason in accepted.items():
            text = (WORKFLOW_DIR / filename).read_text(encoding="utf-8")
            assert f"zizmor: ignore[{rule}]" in text, f"{filename}: no inline ignore for {rule}"
            assert reason in text, f"{filename}: the {rule} ignore carries no reason"

    def test_zizmor_reports_no_findings(self) -> None:
        zizmor = shutil.which("zizmor")
        if zizmor is None:
            pytest.skip("zizmor is not on PATH; `uv sync --extra dev` installs it")

        result = subprocess.run(
            [zizmor, "--offline", "--no-progress", str(WORKFLOW_DIR)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr


class TestPFailFast:
    """P-FAILFAST: a bad value is refused where it is read, before serving."""

    def test_an_out_of_range_port_is_refused_before_anything_starts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from fpstune import cli

        started: list[dict[str, Any]] = []
        monkeypatch.setattr(cli, "_serve_in_process", lambda **kwargs: started.append(kwargs))
        monkeypatch.setattr(cli, "_serve_from_source", lambda **kwargs: started.append(kwargs))

        for bad in ("-1", "0", "65536"):
            result = CliRunner().invoke(cli.serve, ["--port", bad])

            assert result.exit_code == 2, f"--port {bad}: {result.output}"
            assert "1 to 65535" in result.output

        assert started == [], "a refused port still reached the server"

    def test_an_out_of_range_dev_ui_port_is_refused_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from fpstune import cli

        started: list[dict[str, Any]] = []
        monkeypatch.setattr(cli, "_serve_from_source", lambda **kwargs: started.append(kwargs))

        result = CliRunner().invoke(cli.serve, ["--port", "8123", "--ui-port", "70000"])

        assert result.exit_code == 2
        assert "1 to 65535" in result.output
        assert started == []

    def test_the_api_entry_point_refuses_the_same_ports(self) -> None:
        from fpstune.api import serving

        for bad in (0, -1, 70000):
            with pytest.raises(ValueError, match="1 to 65535"):
                serving.run_api(port=bad)

    def test_the_serving_module_parser_names_the_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.api import serving

        monkeypatch.setattr(sys, "argv", ["fpstune.api.serving", "--port", "-1"])

        with pytest.raises(SystemExit) as exited:
            serving.main()

        assert exited.value.code == 2


class TestPFailClosed:
    """P-FAILCLOSED: a failed privilege check refuses; it never proceeds."""

    def test_the_admin_decorator_refuses_before_the_function_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.utils import admin

        calls: list[str] = []

        @admin.require_admin
        def write(value: str) -> None:
            calls.append(value)

        monkeypatch.setattr(admin, "is_admin", lambda: False)

        with pytest.raises(PermissionError, match="Administrator privileges required"):
            write("Enabled")

        assert calls == []

    def test_the_cli_refuses_to_run_when_elevation_is_declined(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from fpstune.commands import utils

        monkeypatch.setattr(utils, "is_admin", lambda: False)
        monkeypatch.setattr(utils, "elevate_if_needed", lambda: False)

        with pytest.raises(SystemExit) as exited:
            utils.require_admin_or_elevate()

        assert exited.value.code == 1
        assert "requires administrator privileges" in capsys.readouterr().out.lower()

    def test_serve_refuses_when_elevation_is_declined(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune import cli

        started: list[dict[str, Any]] = []
        monkeypatch.setattr(cli, "is_admin", lambda: False)
        monkeypatch.setattr(cli, "elevate_if_needed", lambda: False)
        monkeypatch.setattr(cli, "_claim_single_instance", lambda **_kwargs: None)
        monkeypatch.setattr(cli, "_find_free_port", lambda port, **_kwargs: port)
        monkeypatch.setattr(cli, "_write_pid_file", lambda *_args: None)
        monkeypatch.setattr(cli, "_serve_in_process", lambda **kwargs: started.append(kwargs))

        with pytest.raises(SystemExit) as exited:
            cli.serve.callback(port=8123, no_browser=True, dev=False, ui_port=5173, api_only=False)

        assert exited.value.code == 1
        assert started == [], "serve started without the elevation it needs"

    def test_a_state_changing_route_refuses_without_elevation(self) -> None:
        from fastapi.testclient import TestClient

        from fpstune.api.main import app
        from fpstune.api.routes import system_network, system_storage

        client = TestClient(app)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(system_network, "is_admin", lambda: False)
            network = client.post(
                "/api/network/adapter/disable", params={"instance_id": "PCI\\VEN_0000"}
            )

        assert network.status_code == 403
        assert "Administrator" in network.json()["detail"]

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(system_storage, "is_admin", lambda: False)
            storage = client.post("/api/storage/C/optimize")

        assert storage.status_code == 403
        assert "Administrator" in storage.json()["detail"]


class TestPRepro:
    """P-REPRO: the same commit produces the same artifacts."""

    def test_both_lockfiles_are_tracked(self) -> None:
        tracked = _git_tracked()

        for relative in ("uv.lock", "frontend/package-lock.json"):
            assert relative in tracked, f"{relative} is not tracked, so a rebuild can drift"
            assert (REPO_ROOT / relative).stat().st_size > 0

    def test_ci_installs_only_from_the_lockfiles(self) -> None:
        text = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")

        assert "uv sync --locked" in text
        assert text.count("npm ci") >= 2, "a job installs node packages without the lockfile"

    def test_no_workflow_installs_a_floating_package(self) -> None:
        floating: list[str] = []
        for name, workflow in _workflows().items():
            for command in _run_steps(workflow):
                for pattern in (
                    r"\bpip\s+install\b",
                    r"\buv\s+pip\s+install\b",
                    r"\bpipx\s+install\b",
                ):
                    if re.search(pattern, command):
                        floating.append(f"{name}: {command.splitlines()[0]}")
                for match in re.finditer(r"--with\s+(\S+)", command):
                    requirement = match.group(1)
                    if "==" not in requirement:
                        floating.append(f"{name}: unpinned --with {requirement}")

        assert not floating, "a workflow installs a floating package: " + "; ".join(floating)

    def test_a_pinned_ad_hoc_tool_matches_the_lockfile(self) -> None:
        """`--with pyyaml==X` in release.yml must name the version uv.lock resolves,
        so the release toolchain has one source of truth (P-SSOT behind P-REPRO)."""
        release = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")
        pinned = re.findall(r"--with\s+pyyaml==([0-9][0-9.]*)", release)

        assert pinned, "release.yml no longer pins pyyaml; update this gate"
        lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
        locked = {
            package["version"]
            for package in lock.get("package", [])
            if package.get("name") == "pyyaml"
        }

        assert set(pinned) <= locked, f"release.yml pins pyyaml {pinned}, uv.lock has {locked}"


#: The public contract a client may depend on (P-HYRUM). Keys are
#: ``METHOD /path``; values are the declared response model, or the OpenAPI
#: shape for the endpoints that return a plain object. Changing a route, its
#: method or its response model is a breaking change for the bundled UI and for
#: anything scripted against the API, so it must edit this table deliberately.
_API_CONTRACT: dict[str, str] = {
    "GET /": "object<string>",
    "GET /api/activity": "ActivityLogResponse",
    "GET /api/benchmark/gpu-scene": "GpuSceneStatusResponse",
    "GET /api/benchmark/headroom": "HeadroomResponse",
    "GET /api/benchmark/ledger": "BenchLedgerResponse",
    "GET /api/benchmark/ledger/runs": "LedgerRunsResponse",
    "GET /api/benchmark/suite": "SuiteCatalogueResponse",
    "GET /api/benchmark/verify/sources": "VerifySourcesResponse",
    "GET /api/display/pending": "DisplayPendingResponse",
    "GET /api/hardware": "HardwareInfo",
    "GET /api/health/findings": "HealthFindingsResponse",
    "GET /api/os-build": "OsBuildChangeResponse",
    "GET /api/self-check": "SelfCheckResponse",
    "GET /api/settings/categories/metadata": "array<CategoryMetadataResponse>",
    "GET /api/settings/cleanup-sizes": "object<CleanupSizeEntry>",
    "GET /api/settings/definitions": "array<SettingDefinitionResponse>",
    "GET /api/settings/modules/metadata": "array<ModuleMetadataResponse>",
    "GET /api/system": "SystemInfo",
    "GET /api/system/diagnostics": "DiagnosticsResponse",
    "GET /api/update/check": "UpdateStatus",
    "GET /health": "object",
    "POST /api/audio/device/{device_id}/enabled": "AudioToggleResponse",
    "POST /api/audio/device/{device_id}/loudness-eq": "AudioToggleResponse",
    "POST /api/audio/refresh": "AudioRefreshResponse",
    "POST /api/benchmark/gpu-scene/install": "GpuSceneInstallResponse",
    "POST /api/benchmark/headroom/measure": "MeasureResultResponse",
    "POST /api/benchmark/ledger/run": "LedgerRunQueuedResponse",
    "POST /api/benchmark/suite/compare": "SuiteComparisonResponse",
    "POST /api/benchmark/suite/run": "none",
    "POST /api/benchmark/verify/coverage": "VerifyCoverageResponse",
    "POST /api/benchmark/verify/round": "VerifyReportResponse",
    "POST /api/benchmark/verify/sample": "VerifySampleResponse",
    "POST /api/display/keep-all": "DisplayConfirmResponse",
    "POST /api/display/refresh": "RefreshDisplaysResponse",
    "POST /api/display/{display_index}/auto": "DisplayAutoResponse",
    "POST /api/display/{display_index}/confirm": "DisplayConfirmResponse",
    "POST /api/network/adapter/{action}": "object",
    "POST /api/network/adapter/{adapter_name}/connection/{action}": "NetworkConnectionResponse",
    "POST /api/network/refresh": "NetworkRefreshResponse",
    "POST /api/restore-point": "RestorePointResponse",
    "POST /api/settings/bulk/stream-apply": "none",
    "POST /api/settings/detect": "DetectResponse",
    "POST /api/settings/{setting_id}/apply": "ApplyResponse",
    "POST /api/storage/{drive_letter}/optimize": "StorageOptimizeResponse",
    "POST /api/system/shutdown": "object",
    "POST /api/update/install": "UpdateInstallResult",
}

#: Routes whose body is an event stream rather than a response model. Both are
#: SSE, so there is no schema to declare; the event vocabulary is their contract
#: and is pinned by the stream tests.
_STREAMING_ROUTES: dict[str, str] = {
    "POST /api/benchmark/suite/run": "Server-Sent Events: one event per suite step",
    "POST /api/settings/bulk/stream-apply": "Server-Sent Events: started/applied/verified/failed/done",
}

_REF_KEY = "$ref"


def _describe_schema(schema: dict[str, Any]) -> str:
    """The OpenAPI schema as one readable token: a model name, array<model>, object."""
    if not schema:
        return "none"
    if _REF_KEY in schema:
        return str(schema[_REF_KEY]).rsplit("/", 1)[-1]
    kind = schema.get("type")
    if kind == "array":
        return f"array<{_describe_schema(schema.get('items') or {})}>"
    if kind == "object":
        properties = schema.get("additionalProperties")
        if isinstance(properties, dict) and _REF_KEY in properties:
            return f"object<{_describe_schema(properties)}>"
        if isinstance(properties, dict) and properties.get("type") == "string":
            return "object<string>"
        return "object"
    return str(kind or "unknown")


def _api_contract() -> dict[str, str]:
    from fpstune.api.main import app

    contract: dict[str, str] = {}
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            body = "none"
            for code, response in operation.get("responses", {}).items():
                if not str(code).startswith("2"):
                    continue
                content = response.get("content") or {}
                body = (
                    _describe_schema(next(iter(content.values())).get("schema") or {})
                    if content
                    else "no-content"
                )
                break
            contract[f"{method.upper()} {path}"] = body
    return contract


class TestPHyrum:
    """P-HYRUM: what a client can observe is pinned before it changes."""

    def test_the_public_route_and_response_contract_is_pinned(self) -> None:
        assert _api_contract() == _API_CONTRACT

    def test_every_api_route_answers_with_a_declared_shape(self) -> None:
        """No route may answer with an undeclared body unless it is on the record."""
        undeclared = {
            key: shape
            for key, shape in _api_contract().items()
            if key.startswith(("GET /api", "POST /api", "PUT /api", "DELETE /api"))
            and shape == "none"
            and key not in _STREAMING_ROUTES
        }

        assert not undeclared, f"API routes with no response model: {undeclared}"

    def test_the_streaming_routes_are_the_ones_on_the_record(self) -> None:
        streamed = {key for key, shape in _api_contract().items() if shape == "none"}

        assert streamed == set(_STREAMING_ROUTES)

    def test_every_named_response_model_is_in_the_openapi_components(self) -> None:
        from fpstune.api.main import app

        components = set((app.openapi().get("components") or {}).get("schemas") or {})
        named = {
            re.sub(r"^(array|object)<(.*)>$", r"\2", shape)
            for shape in _API_CONTRACT.values()
            if shape not in ("object", "object<string>", "none", "no-content")
        }

        assert named <= components, f"models missing from the schema: {sorted(named - components)}"
