"""Catalogue section C, bound to this repository: secrets, configuration, privacy, Postel.

fpstune is a local-only Windows desktop tool, so the security principles that
apply are the ones about what a local tool must not leak or trust:

* P-SECRETS — no secret in the tree. The scanner is dependency-free (gitleaks is
  not installed here) and the same rule set is described in ``.gitleaks.toml``,
  which is what the pre-commit hook and CI run. Every pattern is assembled from
  fragments, so this file never contains the thing it searches for and needs no
  allowlist of its own.
* P-12FACTOR — configuration that varies by machine is an environment variable,
  every ``FPSTUNE_*`` variable is documented, and no machine-specific endpoint,
  port, credential or profile path is carried in the source (C9).
* P-PRIVACY — the support log (``~/.fpstune/logs/operations.log``, the one log
  that survives the process) carries the setting id, phase, outcome, duration and
  a classified reason, never a previous value, a command line or a path under
  the user's profile.
* P-POSTEL — the one outbound protocol (the GitHub release check) is strict when
  it sends and tolerant when it receives: no machine data in the request, and
  unknown, missing or unreadable fields are answers rather than crashes.

P-DEPTH, P-SIGNALS, P-ERRBUDGET, P-RPORTO and P-321 are N/A for a local-only
desktop tool; the evidence for each is recorded in the task report and belongs in
docs/PRINCIPLES.md, not here.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "fpstune"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"


def _read(path: Path) -> str:
    """A file's text, or "" for a binary one (a compiled artifact carries no text secret)."""
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return ""
    return data.decode("utf-8", "replace")


def _tracked_files() -> list[Path]:
    """Every file git tracks, plus the files this change adds before it is committed."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=False
    )
    if result.returncode != 0:
        pytest.skip("git is not available to enumerate the tracked tree")
    targets = {
        REPO_ROOT / name for name in result.stdout.decode("utf-8", "replace").split("\0") if name
    }
    targets.update({GITLEAKS_CONFIG, Path(__file__)})
    return sorted(path for path in targets if path.is_file())


def _fragments(*parts: str) -> str:
    """Join a pattern from parts, so this file never contains what it searches for."""
    return "".join(parts)


#: Secret shapes worth a gate. Provider tokens and private keys are unambiguous;
#: the last entry is the shape a hardcoded credential takes in ordinary code.
_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "private key block": re.compile(_fragments("-----BEGIN ", "[A-Z ]*", "PRIVATE KEY-----")),
    "GitHub token": re.compile(_fragments(r"\bgh", r"[pousr]_[A-Za-z0-9]{30,}")),
    "GitHub fine-grained token": re.compile(_fragments(r"\bgithub", r"_pat_[A-Za-z0-9_]{30,}")),
    "AWS access key id": re.compile(_fragments(r"\bAKIA", r"[0-9A-Z]{16}\b")),
    "Slack token": re.compile(_fragments(r"\bxox", r"[abprs]-[A-Za-z0-9-]{10,}")),
    "OpenAI-style key": re.compile(_fragments(r"\bsk", r"-[A-Za-z0-9]{32,}")),
    "Google API key": re.compile(_fragments(r"\bAIza", r"[0-9A-Za-z_-]{35}")),
    "Stripe live key": re.compile(_fragments(r"\b[sr]k", r"_live_[0-9A-Za-z]{20,}")),
    "password in a connection URL": re.compile(
        _fragments(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:/@]+:",
            r"[^\s@/]{6,}@",
        )
    ),
    "secret-looking assignment": re.compile(
        _fragments(
            r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|"
            r"auth[_-]?token|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*",
            r"['\"]([A-Za-z0-9+/=_\-]{24,})['\"]",
        )
    ),
}

#: Values that are deliberately not secrets: placeholders, examples and variables.
_PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "change-me",
        "your_token",
        "your-token",
        "your_token_here",
        "placeholder",
        "dummy",
        "example",
        "example-token",
        "test",
        "testing",
        "secret",
        "password",
        "token",
        "redacted",
        "not-a-real-token",
    }
)
_PLACEHOLDER_SHAPES = re.compile(
    r"(?i)^(?:\$\{.*\}|\{\{.*\}\}|<.*>|%.*%|x{4,}|\*{4,}|0{4,}|\.{4,}|_+)$"
)


def _is_placeholder(value: str) -> bool:
    return value.lower() in _PLACEHOLDER_VALUES or bool(_PLACEHOLDER_SHAPES.match(value))


class TestPSecrets:
    """P-SECRETS: a secret lives in the environment or a vault, never in the tree."""

    def test_no_tracked_file_carries_a_secret(self) -> None:
        hits: list[str] = []
        for path in _tracked_files():
            text = _read(path)
            if not text:
                continue
            for name, pattern in _SECRET_PATTERNS.items():
                for match in pattern.finditer(text):
                    value = match.group(1) if match.groups() else match.group(0)
                    if _is_placeholder(value):
                        continue
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {name}: {match.group(0)[:48]!r}")

        assert not hits, "a secret-shaped value is in the tree:\n" + "\n".join(hits)

    def test_the_detector_would_catch_a_planted_secret(self) -> None:
        """A scan that cannot fail is not a gate, so the patterns are proven here."""
        planted = {
            "private key block": _fragments("-----BEGIN ", "RSA ", "PRIVATE KEY-----"),
            "GitHub token": _fragments("gh", "p_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"),
            "AWS access key id": _fragments("AKIA", "IOSFODNN7EXAMPLE"),
            "Slack token": _fragments("xox", "b-1234567890-abcdefghij"),
            "OpenAI-style key": _fragments("sk", "-", "a" * 40),
            "password in a connection URL": _fragments("postgres://user:", "hunter2@host/db"),
            "secret-looking assignment": _fragments(
                "api_key = '", "0123456789abcdef0123456789abcdef", "'"
            ),
        }

        for name, sample in planted.items():
            assert _SECRET_PATTERNS[name].search(sample), f"{name} would not be caught"

        prose = "A setting's recommended value is the driver's own default."
        assert not any(pattern.search(prose) for pattern in _SECRET_PATTERNS.values())

    def test_no_environment_file_is_tracked(self) -> None:
        offenders = [
            path.relative_to(REPO_ROOT)
            for path in _tracked_files()
            if re.fullmatch(r"\.env(\..+)?", path.name) and path.name != ".env.example"
        ]

        assert not offenders, f"an environment file is tracked: {offenders}"

    def test_git_ignores_environment_files(self) -> None:
        ignore = _read(REPO_ROOT / ".gitignore")

        # CRLF: the file is checked out with Windows line endings.
        assert re.search(r"(?m)^\.env\r?$", ignore)
        assert re.search(r"(?m)^\.env\.\*\.local\r?$", ignore)

    def test_the_gitleaks_config_extends_the_default_rules(self) -> None:
        config = tomllib.loads(_read(GITLEAKS_CONFIG))

        assert (config.get("extend") or {}).get("useDefault") is True

    def test_every_gitleaks_allowlist_entry_says_why(self) -> None:
        """An allowlist entry without a reason is a silent hole in the scanner."""
        config = tomllib.loads(_read(GITLEAKS_CONFIG))
        entries = list(config.get("allowlists") or [])
        if isinstance(config.get("allowlist"), dict):
            entries.append(config["allowlist"])

        for entry in entries:
            assert entry.get("description"), f"allowlist entry with no reason: {entry}"


class TestP12Factor:
    """P-12FACTOR: configuration is environment, and nothing machine-specific is code."""

    def test_every_fpstune_variable_in_the_source_is_documented(self) -> None:
        found: set[str] = set()
        for path in SRC.rglob("*.py"):
            for node in ast.walk(ast.parse(_read(path))):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and re.fullmatch(r"FPSTUNE_[A-Z0-9_]+", node.value)
                ):
                    found.add(node.value)
        documented = set(re.findall(r"FPSTUNE_[A-Z0-9_]+", _read(ENV_EXAMPLE)))

        assert found, "no FPSTUNE_* variable is read at all; this gate has gone stale"
        assert found == documented, (
            f"undocumented: {sorted(found - documented)}; "
            f"documented but unread: {sorted(documented - found)}"
        )

    def test_no_machine_specific_endpoint_is_hardcoded(self) -> None:
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            for text, lineno in _code_strings(path):
                for match in re.finditer(r"https?://[^\s'\"<>]+", text):
                    url = match.group(0)
                    parts = urlsplit(url)
                    host = parts.hostname or ""
                    if host not in _ALLOWED_ENDPOINT_HOSTS:
                        offenders.append(f"{path.relative_to(SRC)}:{lineno} {url}")
                    if parts.username is not None or parts.password is not None:
                        offenders.append(f"{path.relative_to(SRC)}:{lineno} credentials in {url}")
                    if parts.scheme == "http" and host not in ("127.0.0.1", "localhost"):
                        offenders.append(f"{path.relative_to(SRC)}:{lineno} plain http to {host}")

        assert not offenders, "an endpoint is not on the record:\n" + "\n".join(offenders)

    def test_no_machine_specific_address_is_hardcoded(self) -> None:
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            for text, lineno in _code_strings(path):
                for match in re.finditer(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
                    if match.group(0) not in _ALLOWED_IP_LITERALS:
                        offenders.append(f"{path.relative_to(SRC)}:{lineno} {match.group(0)}")

        assert not offenders, "an IP literal is not on the record:\n" + "\n".join(offenders)

    def test_only_the_one_resolver_reads_a_user_profile_root(self) -> None:
        """`Path.home()`/`expanduser()` outside the resolver cannot be redirected."""
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            if path == SRC / "utils" / "user_paths.py":
                continue
            for node in ast.walk(ast.parse(_read(path))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr == "expanduser" or (
                    node.func.attr == "home"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "Path"
                ):
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")

        assert not offenders, (
            "a profile root is resolved outside utils/user_paths.py (C9): " + ", ".join(offenders)
        )

    def test_no_profile_path_literal_is_carried_in_the_source(self) -> None:
        pattern = re.compile(
            r"(?i)[a-z]:[\\/]users[\\/]|(?<![a-z0-9])/(?:home|users)/[^/\s'\"{}]+/"
        )
        offenders = [
            f"{path.relative_to(SRC)}:{lineno} {text[:60]!r}"
            for path in SRC.rglob("*.py")
            for text, lineno in _code_strings(path)
            if pattern.search(text)
        ]

        assert not offenders, "a user-profile path is in the source (C9):\n" + "\n".join(offenders)

    def test_the_state_directory_is_only_built_by_the_resolver(self) -> None:
        # The directory itself, not a temp-file suffix: `.fpstune-tmp` beside a
        # game config is a file name, not a path under the state directory.
        state_directory = re.compile(r"\.fpstune(?:[\\/]|$)")
        offenders = [
            f"{path.relative_to(SRC)}:{lineno} {text[:60]!r}"
            for path in SRC.rglob("*.py")
            if path != SRC / "utils" / "user_paths.py"
            for text, lineno in _code_strings(path)
            if state_directory.search(text)
        ]

        assert not offenders, (
            "a state path is built outside utils/user_paths.py (C9): " + ", ".join(offenders)
        )


class TestPPrivacy:
    """P-PRIVACY: the one on-disk log carries no personal data and no value history."""

    @staticmethod
    def _last_line(tmp_path: Path, response: Any) -> str:
        from fpstune.utils.operation_log import OperationLog

        log = OperationLog()
        path = log.start_session(tmp_path / "operations.log", header="test")
        log.record_apply(SimpleNamespace(id="game_config:mw4:dof_weapon"), response, 12)
        return path.read_text(encoding="utf-8").splitlines()[-1]

    @staticmethod
    def _response(**overrides: Any) -> SimpleNamespace:
        values: dict[str, Any] = {
            "success": False,
            "error": None,
            "skipped": False,
            "verified": False,
            "requires_reboot": False,
            "freed_bytes": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_a_failure_reason_never_carries_the_users_profile_path(self, tmp_path: Path) -> None:
        from fpstune.utils import user_paths

        local_appdata = user_paths.local_appdata()
        assert local_appdata is not None, "the test needs a profile root to leak"
        local = str(local_appdata)
        error = f"[Errno 13] Permission denied: '{local}\\Activision\\players\\settings.cod26.txt'"

        line = self._last_line(tmp_path, self._response(error=error))

        assert local not in line
        # The most specific root wins: %LOCALAPPDATA% says more than %USERPROFILE%.
        assert "%LOCALAPPDATA%\\Activision\\players\\settings.cod26.txt" in line
        # The line must still answer "why did this apply fail?": the cause, the
        # target and the outcome survive the masking.
        assert "Permission denied" in line
        assert "game_config:mw4:dof_weapon" in line
        assert "| failed |" in line

    def test_a_path_under_the_home_directory_is_masked_too(self, tmp_path: Path) -> None:
        from fpstune.utils import user_paths

        home = str(user_paths.home())
        error = f"[Errno 13] Permission denied: '{home}\\Saved Games\\Apex\\videoconfig.txt'"

        line = self._last_line(tmp_path, self._response(error=error))

        assert home not in line
        assert "%USERPROFILE%\\Saved Games\\Apex\\videoconfig.txt" in line

    def test_another_accounts_profile_path_is_masked_too(self, tmp_path: Path) -> None:
        error = "[Errno 13] Permission denied: 'C:\\Users\\SomeoneElse\\Saved Games\\a.txt'"

        line = self._last_line(tmp_path, self._response(error=error))

        assert "SomeoneElse" not in line
        assert "%USERPROFILE%\\Saved Games\\a.txt" in line

    def test_a_non_profile_path_stays_legible(self, tmp_path: Path) -> None:
        error = (
            "Windows refused writing HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters"
        )

        line = self._last_line(tmp_path, self._response(error=error))

        assert "HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters" in line

    def test_the_log_never_records_a_previous_value(self, tmp_path: Path) -> None:
        """C6: there is no undo history, so a log line may not become one."""
        response = self._response(
            error="Verification failed: expected 'Enabled', got 'Disabled'",
            previous_value="Disabled",
            current_value="Enabled",
            default_value="Enabled",
        )

        line = self._last_line(tmp_path, response)

        for forbidden in ("previous_value", "current_value", "default_value", "previous=", "old="):
            assert forbidden not in line

    def test_the_log_never_records_a_command_line(self, tmp_path: Path) -> None:
        response = self._response(
            error="Access is denied",
            command="powershell -Command Set-ItemProperty -Path HKLM:\\X -Name Y",
            stdout="Set-ItemProperty : Access is denied",
        )

        line = self._last_line(tmp_path, response)

        assert "Set-ItemProperty" not in line
        assert "powershell" not in line.lower()

    def test_no_operation_log_call_passes_command_text(self) -> None:
        """A static half: the call sites themselves cannot start carrying it."""
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "operation_log"
                ):
                    continue
                for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                    for inner in ast.walk(argument):
                        if isinstance(inner, ast.Name) and re.search(
                            r"(?i)command|cmd|script|argv|stdout|stderr", inner.id
                        ):
                            offenders.append(
                                f"{path.relative_to(REPO_ROOT)}:{node.lineno} passes {inner.id}"
                            )

        assert not offenders, "the support log would carry command text: " + ", ".join(offenders)

    def test_the_support_log_is_bounded_and_lives_under_the_state_directory(self) -> None:
        from fpstune.utils import operation_log, user_paths

        log = operation_log.OperationLog()
        path = log.start_session()

        assert operation_log._MAX_BACKUPS == 5
        assert path.name == "operations.log"
        assert path.parent == user_paths.fpstune_home() / "logs"
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert header.startswith("# fpstune operations |")
        assert str(user_paths.home()) not in header

    def test_the_opt_in_debug_log_is_the_one_place_command_text_is_written(self) -> None:
        """The exception is recorded where it lives: opt-in and cleared at start.

        With FPSTUNE_DEBUG set, four rotating files carry raw command text and
        identifiers. That is deliberate (it is how a detection is diagnosed) and
        bounded: it only exists when the user asked for it, and every file is
        cleared at process start, so it never becomes the durable record the
        support log is.
        """
        debug = _read(SRC / "utils" / "debug.py")

        assert "FPSTUNE_DEBUG" in debug
        assert "cleared at process start" in debug or "clear on startup" in debug.lower()


#: Hosts a shipped URL may name, each with the reason it is the same on every machine.
_ALLOWED_ENDPOINT_HOSTS: dict[str, str] = {
    "127.0.0.1": "loopback: the address this process serves on (api/main.py binds it)",
    "localhost": "loopback, for the Vite dev server's origins in a source checkout",
    "api.github.com": "the release check: the product's own public endpoint",
    "github.com": "the product's release page and the pinned PresentMon download",
    "assets.unigine.com": "the fixed GPU-scene installer, downloaded only when asked",
    "speed.cloudflare.com": "the network-load bench's public endpoint, run only when asked",
    "cloudflare-dns.com": "a DoH template written to the registry as a value; never contacted",
    "security.cloudflare-dns.com": "a DoH template written to the registry; never contacted",
    "family.cloudflare-dns.com": "a DoH template written to the registry; never contacted",
    "dns.google": "a DoH template written to the registry; never contacted",
    "dns.quad9.net": "a DoH template written to the registry; never contacted",
}

#: IP literals a shipped string may contain, each with the reason.
_ALLOWED_IP_LITERALS: dict[str, str] = {
    "127.0.0.1": "loopback: the API binds it and asks its own /health through it",
    "0.0.0.0": "the wildcard an address parser reports for 'not bound'; never contacted",
    "1.1.1.1": "Cloudflare's public resolver: the DoH table keys on the detected DNS address",
    "1.0.0.1": "Cloudflare's public resolver, same table",
    "1.1.1.2": "Cloudflare's malware-blocking resolver, same table",
    "1.0.0.2": "Cloudflare's malware-blocking resolver, same table",
    "1.1.1.3": "Cloudflare's family resolver, same table",
    "1.0.0.3": "Cloudflare's family resolver, same table",
    "8.8.8.8": "Google's public resolver, same table and the user-started network bench",
    "8.8.4.4": "Google's public resolver, same table",
    "9.9.9.9": "Quad9's public resolver, same table",
    "149.112.112.112": "Quad9's public resolver, same table",
}

#: Module-level names whose value is evidence for a setting, not an endpoint.
_EVIDENCE_NAME = re.compile(r"(?i)source|doc|guide|reference|evidence|research|measured")


def _documentation_ids(tree: ast.Module) -> set[int]:
    """String constants that are documentation: docstrings and evidence lists.

    A URL a setting cites as its evidence is not an endpoint fpstune contacts;
    counting it here would drown the endpoint gate in hundreds of blog links.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in ("sources", "evidence", "research"):
                    ids.update(id(inner) for inner in ast.walk(keyword.value))
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if names and any(_EVIDENCE_NAME.search(name) for name in names):
            ids.update(id(inner) for inner in ast.walk(node.value))
    return ids


def _code_strings(path: Path) -> list[tuple[str, int]]:
    """Every string literal in shipped code that is not documentation."""
    tree = ast.parse(_read(path))
    documentation = _documentation_ids(tree)
    return [
        (node.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in documentation
    ]


class _FakeResponse:
    """The minimum ``urlopen`` context manager a check reads from."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class TestPPostel:
    """P-POSTEL: strict when sending, tolerant when receiving (the inner boundary
    is P-FAILFAST, and this is the one outbound protocol)."""

    @staticmethod
    def _serve(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> tuple[Any, dict[str, Any]]:
        from fpstune.utils import updates

        captured: dict[str, Any] = {}

        def fake_urlopen(request: Any, timeout: float | None = None) -> _FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(payload)

        monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
        return updates, captured

    @staticmethod
    def _fail(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> Any:
        from fpstune.utils import updates

        def fake_urlopen(_request: Any, **_kwargs: Any) -> Any:
            raise error

        monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
        return updates

    def test_the_request_is_one_fixed_get_with_no_machine_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        updates, captured = self._serve(monkeypatch, json.dumps({"tag_name": "v1.2.3"}).encode())

        check = updates.check_for_update()

        request = captured["request"]
        assert request.full_url == updates.RELEASES_API
        assert request.get_method() == "GET"
        assert request.data is None, "the check sends no body, so it identifies nobody"
        headers = {name.lower(): value for name, value in request.header_items()}
        assert set(headers) == {"accept", "user-agent"}
        assert headers["user-agent"] == "fpstune"
        assert check.latest == "1.2.3"
        assert check.error is None

    @pytest.mark.parametrize(
        "payload",
        [
            b'{"tag_name": "v1.0.0", "unknown_field": {"nested": true}, "assets": []}',
            b'{"tag_name": "1.0.0", "html_url": null, "assets": null}',
            b'{"tag_name": "v1.0.0", "assets": [{"name": "fpstune.exe", '
            b'"browser_download_url": "https://example.invalid/x"}, "not-a-dict", '
            b'{"name": "fpstune.exe.sha256", "browser_download_url": "https://example.invalid/y"}]}',
        ],
    )
    def test_unknown_and_odd_fields_are_tolerated(
        self, monkeypatch: pytest.MonkeyPatch, payload: bytes
    ) -> None:
        updates, _ = self._serve(monkeypatch, payload)

        check = updates.check_for_update()

        assert check.error is None
        assert check.latest == "1.0.0"
        assert check.url.startswith("https://")

    def test_a_release_with_no_tag_is_an_answer_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        updates, _ = self._serve(monkeypatch, b'{"name": "a release with no tag"}')

        check = updates.check_for_update()

        assert check.latest is None
        assert check.update_available is False
        assert "no version" in (check.error or "")

    @pytest.mark.parametrize(
        "error",
        [
            HTTPError("https://api.github.com", 403, "rate limited", None, None),
            HTTPError("https://api.github.com", 404, "not found", None, None),
            URLError("no network"),
            TimeoutError("timed out"),
        ],
    )
    def test_a_failed_check_is_reported_and_never_raised(
        self, monkeypatch: pytest.MonkeyPatch, error: BaseException
    ) -> None:
        updates = self._fail(monkeypatch, error)

        check = updates.check_for_update()

        assert check.latest is None
        assert check.error
        assert "could not reach GitHub" in check.error

    def test_an_unreadable_response_is_reported_and_never_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        updates, _ = self._serve(monkeypatch, b"<html>not json</html>")

        check = updates.check_for_update()

        assert check.latest is None
        assert "unreadable response" in (check.error or "")

    def test_versions_compare_as_numbers_not_text(self) -> None:
        from fpstune.utils import updates

        assert updates._as_tuple("0.10.0") > updates._as_tuple("0.9.0")
        assert updates.UpdateCheck(current="0.9.0", latest="0.10.0").update_available is True
        assert updates.UpdateCheck(current="1.2.3", latest="1.2.3").update_available is False
        assert updates.UpdateCheck(current="1.2.3", latest="v1.2.4").update_available is True

    def test_the_protocol_does_no_locale_dependent_parsing(self) -> None:
        source = _read(SRC / "utils" / "updates.py")

        for banned in ("strptime", "strftime", "locale.", "gettext(", "locale,"):
            assert banned not in source

    def test_a_checksum_mismatch_refuses_the_install(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from fpstune.utils import updates

        target = tmp_path / "fpstune.exe"
        target.write_bytes(b"the running build")
        check = updates.UpdateCheck(
            current="1.0.0",
            latest="1.1.0",
            exe_url="https://example.invalid/fpstune.exe",
            sha256_url="https://example.invalid/fpstune.exe.sha256",
        )

        def fake_fetch(url: str, _limit: int) -> bytes:
            return b"0" * 64 if url.endswith(".sha256") else b"a different binary"

        monkeypatch.setattr(updates, "_fetch", fake_fetch)

        installed, message = updates.install_update(check, executable=target)

        assert installed is False
        assert "checksum" in message.lower()
        assert target.read_bytes() == b"the running build", "a refused install changed the target"

    def test_a_release_without_a_checksum_is_not_installed(self, tmp_path: Path) -> None:
        from fpstune.utils import updates

        check = updates.UpdateCheck(
            current="1.0.0",
            latest="1.1.0",
            exe_url="https://example.invalid/fpstune.exe",
            sha256_url=None,
        )

        installed, message = updates.install_update(check, executable=tmp_path / "fpstune.exe")

        assert installed is False
        assert "checksum" in message

    def test_a_source_checkout_does_not_replace_its_interpreter(self) -> None:
        from fpstune.utils import updates

        check = updates.UpdateCheck(
            current="1.0.0",
            latest="1.1.0",
            exe_url="https://example.invalid/fpstune.exe",
            sha256_url="https://example.invalid/fpstune.exe.sha256",
        )

        installed, message = updates.install_update(check)

        assert installed is False
        assert "source checkout" in message
