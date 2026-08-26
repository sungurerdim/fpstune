"""The update check must not become the telemetry fpstune promises it has none of.

SECURITY.md says fpstune sends nothing about you or your machine. A "check for
updates" is the obvious place for that promise to quietly stop being true — a
version string here, a hardware id there, all of it defensible one field at a
time — so the request is pinned here rather than trusted.

The second half is about honesty on failure. No network, GitHub down, rate
limited, a proxy in the way: none of those mean "you are up to date", and
answering that would be the same defect this codebase keeps fixing — a failure
reported as a result.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from fpstune import __version__
from fpstune.utils import updates


class _Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _captured_request(payload: object) -> urllib.request.Request:
    """Run a check and hand back the request it actually made."""
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request, **_kwargs):
        seen.append(request)
        return _Response(payload)

    with patch.object(urllib.request, "urlopen", fake_urlopen):
        updates.check_for_update()
    return seen[0]


class TestItSaysNothingAboutTheMachine:
    def test_the_url_is_a_constant_with_nothing_appended(self) -> None:
        """No query string is where a version or an id would go first."""
        request = _captured_request({"tag_name": "v0.2.0"})
        assert request.full_url == updates.RELEASES_API
        assert "?" not in request.full_url

    def test_it_is_a_plain_get_with_no_body(self) -> None:
        request = _captured_request({"tag_name": "v0.2.0"})
        assert request.get_method() == "GET"
        assert request.data is None

    def test_the_only_headers_are_the_ones_github_requires(self) -> None:
        """A User-Agent naming the software is not the same as naming the user."""
        request = _captured_request({"tag_name": "v0.2.0"})
        headers = {key.lower(): value for key, value in request.header_items()}
        assert set(headers) <= {"accept", "user-agent", "host"}
        assert headers["user-agent"] == "fpstune"

    def test_nothing_it_sends_mentions_this_machine(self) -> None:
        """The blunt version of the rule above, so a new header has to justify itself."""
        request = _captured_request({"tag_name": "v0.2.0"})
        sent = (request.full_url + str(dict(request.header_items()))).lower()
        for leak in ("version", __version__, "windows", "gpu", "cpu", "id="):
            assert leak not in sent, f"the update check is sending {leak!r}"


class TestComparingVersions:
    @pytest.mark.parametrize(
        ("current", "latest", "expected"),
        [
            ("0.1.0", "0.2.0", True),
            ("0.1.0", "0.1.0", False),
            ("0.2.0", "0.1.0", False),
            # The release where a string comparison starts lying: "0.10.0" sorts
            # before "0.9.0" as text and after it as a version.
            ("0.9.0", "0.10.0", True),
            ("0.10.0", "0.9.0", False),
            ("1.0.0", "1.0.1", True),
        ],
    )
    def test_numbers_are_compared_as_numbers(
        self, current: str, latest: str, expected: bool
    ) -> None:
        check = updates.UpdateCheck(current=current, latest=latest)
        assert check.update_available is expected

    def test_a_v_prefix_on_the_tag_is_stripped(self) -> None:
        with patch.object(
            urllib.request, "urlopen", lambda *_a, **_k: _Response({"tag_name": "v9.9.9"})
        ):
            assert updates.check_for_update().latest == "9.9.9"


class TestFailureIsNotAnAnswer:
    @pytest.mark.parametrize(
        "boom",
        [
            urllib.error.URLError("no network"),
            urllib.error.HTTPError(updates.RELEASES_API, 404, "Not Found", {}, None),
            TimeoutError("slow"),
            OSError("proxy refused"),
        ],
    )
    def test_it_never_raises(self, boom: Exception) -> None:
        with patch.object(urllib.request, "urlopen", side_effect=boom):
            check = updates.check_for_update()

        assert check.reachable is False
        assert check.error
        assert check.update_available is False

    def test_unreachable_is_not_reported_as_up_to_date(self) -> None:
        """The distinction the whole class exists for.

        A repository with no releases answers 404 — which is exactly today, and
        exactly when a check that guessed would be most confidently wrong.
        """
        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("down")):
            check = updates.check_for_update()

        assert check.reachable is False
        assert check.latest is None

    def test_a_malformed_response_is_not_a_version(self) -> None:
        class _Garbage:
            def read(self) -> bytes:
                return b"<html>rate limited</html>"

            def __enter__(self):
                return self

            def __exit__(self, *_exc: object) -> bool:
                return False

        with patch.object(urllib.request, "urlopen", lambda *_a, **_k: _Garbage()):
            check = updates.check_for_update()

        assert check.reachable is False

    def test_a_release_without_a_tag_is_refused(self) -> None:
        with patch.object(urllib.request, "urlopen", lambda *_a, **_k: _Response({"name": "x"})):
            check = updates.check_for_update()

        assert check.reachable is False
        assert "no version" in (check.error or "")


class TestItOnlyRunsWhenAsked:
    def test_nothing_checks_for_updates_on_import(self) -> None:
        """Reaching the network because the app started is not a check the user made.

        Asserted by construction: the module exposes a function and runs nothing
        at import, so importing it cannot make a request.
        """
        with patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("checked without being asked")
        ):
            import importlib

            importlib.reload(updates)

    def test_no_startup_path_calls_it(self) -> None:
        """The API's lifespan pre-warms the GPU and the registry, and nothing else."""
        from pathlib import Path

        main_source = Path(updates.__file__).parent.parent / "api" / "main.py"
        assert "check_for_update" not in main_source.read_text(encoding="utf-8")
