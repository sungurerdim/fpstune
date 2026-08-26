"""The bundled UI has to load, not merely respond.

Reported from a real run of the packaged executable: a blank white page, with
the server perfectly happy about it.

    [OK] GET /ui/                        -> 200
    [!!] GET /assets/index-DBPWLG0J.js   -> 404
    [!!] GET /assets/index-DQTIpbUl.css  -> 404
    [!!] GET /vite.svg                   -> 404

`index.html` was served correctly, so every check anyone had thought to make
passed. Vite's default `base` of `/` emits absolute asset URLs, and the app
mounts the bundle under `/ui`, so the browser dutifully asked for `/assets/...`
at the site root and got nothing. A 200 for the document says nothing about
whether the page can run.

So these ask for the assets the document actually references, which is the only
version of this check that could have failed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.utils.runtime import frontend_dist

DIST = frontend_dist()

needs_build = pytest.mark.skipif(
    DIST is None,
    reason="frontend/dist is not built; run `cd frontend && npm run build`",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _referenced_assets() -> list[str]:
    """Every URL index.html asks the browser to fetch."""
    assert DIST is not None
    html = (DIST / "index.html").read_text(encoding="utf-8")
    return [
        url
        for url in re.findall(r'(?:src|href)="([^"]+)"', html)
        # A data: URI is inline and never fetched.
        if not url.startswith("data:")
    ]


@needs_build
class TestTheDocumentAndItsAssets:
    def test_the_page_is_served(self, client: TestClient) -> None:
        assert client.get("/ui/").status_code == 200

    def test_every_asset_the_page_references_resolves(self, client: TestClient) -> None:
        """The check that would have caught the blank page.

        Each URL is resolved the way a browser resolves it: relative to the
        document at /ui/.
        """
        missing = []
        for url in _referenced_assets():
            resolved = url[2:] if url.startswith("./") else url.lstrip("/")
            response = client.get(f"/ui/{resolved}")
            if response.status_code != 200 or not response.content:
                missing.append(f"{url} -> {response.status_code}")

        assert not missing, (
            "the page loads and then cannot run, which renders as a blank white "
            "screen with a healthy 200 in the log:\n  " + "\n  ".join(missing)
        )

    def test_the_asset_urls_are_relative(self) -> None:
        """Absolute URLs only work at the site root, and this is mounted at /ui.

        Pinned at the source of the defect rather than only at its symptom: a
        future `base` change would break the page again, and this says why.
        """
        absolute = [url for url in _referenced_assets() if url.startswith("/")]
        assert not absolute, (
            f"index.html references {absolute} from the site root, but the bundle "
            "is served under /ui — set `base: './'` in vite.config.ts"
        )

    def test_it_asks_for_nothing_that_was_never_built(self) -> None:
        """`/vite.svg` was a 404 on every page load: there is no public/ dir."""
        assert DIST is not None
        for url in _referenced_assets():
            name = Path(url).name
            assert (DIST / name).exists() or (DIST / "assets" / name).exists(), (
                f"index.html references {url}, which the build does not produce"
            )


@needs_build
class TestTheVitePathConfiguration:
    def test_the_config_pins_a_relative_base(self) -> None:
        """The one line that decides whether the packaged UI can load at all."""
        config = Path(__file__).resolve().parents[2] / "frontend" / "vite.config.ts"
        source = config.read_text(encoding="utf-8")
        assert re.search(r"base:\s*['\"]\./['\"]", source), (
            "vite.config.ts no longer sets `base: './'`; the built UI will emit "
            "absolute asset URLs and render blank under /ui"
        )
