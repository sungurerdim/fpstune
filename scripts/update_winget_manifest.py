"""Point the winget manifests at a published release.

Everything a manifest says about a release — the version, the download URL, the
checksum — already exists in the release itself. Typing any of it again is a
chance to get it wrong, and a checksum copied by a person is a checksum nobody
verified: it will match whatever they pasted, including the wrong file.

So this reads the release and writes the manifests. The version comes from
``pyproject.toml``, which is where the tag comes from too, and the checksum is
computed from the bytes actually published.

    python scripts/update_winget_manifest.py                  # current version
    python scripts/update_winget_manifest.py --version 0.2.0
    python scripts/update_winget_manifest.py --exe dist/fpstune.exe   # local build

With neither ``--exe`` nor a local file it downloads the published asset, so the
checksum describes what a user would actually get rather than what this machine
happens to have lying in ``dist/``.

``ReleaseDate`` is written here for the same reason as everything else: it used
to be typed into the template by hand, and a hand-typed date is a date that
ships verbatim under every later version. It defaults to today in UTC, which is
correct when the release workflow calls this on the day it publishes, and
``--release-date`` covers the case of re-running against an older release.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import tomllib
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_ROOT = ROOT / "winget" / "manifests" / "s" / "sungurerdim" / "fpstune"
REPO = "sungurerdim/fpstune"
ASSET = "fpstune.exe"

# One template directory is copied per version rather than each being written by
# hand. Three files that must agree on PackageIdentifier, PackageVersion and
# ManifestVersion are three chances for them not to.
MANIFEST_FILES = (
    "sungurerdim.fpstune.yaml",
    "sungurerdim.fpstune.locale.en-US.yaml",
    "sungurerdim.fpstune.installer.yaml",
)


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


def _newest_manifest_dir() -> Path:
    """The version directory to copy from — the highest one already written."""
    candidates = (
        [p for p in MANIFEST_ROOT.iterdir() if p.is_dir()] if MANIFEST_ROOT.exists() else []
    )
    if not candidates:
        raise SystemExit(f"No manifest directory to copy from under {MANIFEST_ROOT}")

    def key(path: Path) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", path.name)) or (0,)

    return max(candidates, key=key)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(version: str, into: Path) -> Path:
    url = f"https://github.com/{REPO}/releases/download/v{version}/{ASSET}"
    target = into / ASSET
    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url, timeout=300) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
    except OSError as exc:
        raise SystemExit(
            f"Could not download {url}: {exc}\n"
            "Publish the release first, or pass --exe to checksum a local build."
        ) from exc
    return target


def today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def _set_release_date(text: str, release_date: str) -> str:
    """Write ``ReleaseDate`` into the installer manifest, adding it if absent.

    Only the installer manifest carries it — winget reads the field there, and
    putting a date in the version or locale file would be a second copy of the
    same fact with no one keeping them equal.

    The template ships without the line at all, so replacing is not enough: it
    is inserted directly under ``PackageVersion``, the field it is a fact about.
    """
    if "ManifestType: installer" not in text:
        return text

    line = f"ReleaseDate: {release_date}"
    if re.search(r"^ReleaseDate:.*$", text, flags=re.M):
        return re.sub(r"^ReleaseDate:.*$", lambda _: line, text, flags=re.M)
    return re.sub(
        r"^PackageVersion:.*$",
        lambda match: f"{match.group(0)}\n{line}",
        text,
        count=1,
        flags=re.M,
    )


def _drop_template_banner(text: str) -> str:
    """Remove the "TEMPLATE — NOT PUBLISHABLE" header once it stops being true.

    A new version directory is a copy of the previous one, banner included. Left
    in place it would sit above a real checksum telling the next person not to
    submit a manifest that is now exactly what should be submitted — and a
    warning that is wrong is a warning nobody reads the next time.
    """
    if not text.startswith("# TEMPLATE"):
        return text
    lines = text.splitlines(keepends=True)
    body = next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))
    return "".join(lines[body:])


def rewrite(path: Path, version: str, checksum: str, release_date: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^PackageVersion:.*$", f"PackageVersion: {version}", text, flags=re.M)
    text = _set_release_date(text, release_date)
    text = re.sub(
        r"^(\s*)InstallerUrl:.*$",
        rf"\1InstallerUrl: https://github.com/{REPO}/releases/download/v{version}/{ASSET}",
        text,
        flags=re.M,
    )
    text = re.sub(r"^(\s*)InstallerSha256:.*$", rf"\1InstallerSha256: {checksum}", text, flags=re.M)
    text = re.sub(
        r"^ReleaseNotesUrl:.*$",
        f"ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{version}",
        text,
        flags=re.M,
    )
    if checksum != "0" * 64:
        text = _drop_template_banner(text)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="defaults to the version in pyproject.toml")
    parser.add_argument("--exe", type=Path, help="checksum this file instead of downloading")
    parser.add_argument(
        "--release-date",
        help="YYYY-MM-DD; defaults to today in UTC, which is the publish date "
        "when the release workflow runs this",
    )
    args = parser.parse_args()

    release_date = args.release_date or today_utc()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
        raise SystemExit(f"--release-date must be YYYY-MM-DD, got {release_date!r}")

    version = args.version or project_version()
    target_dir = MANIFEST_ROOT / version

    if args.exe:
        if not args.exe.is_file():
            raise SystemExit(f"No such file: {args.exe}")
        checksum = sha256_of(args.exe)
        print(f"Checksummed local build {args.exe}")
    else:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            checksum = sha256_of(download_asset(version, Path(tmp)))

    if not target_dir.exists():
        source = _newest_manifest_dir()
        if source != target_dir:
            print(f"Creating {target_dir.relative_to(ROOT)} from {source.name}")
            shutil.copytree(source, target_dir)

    for name in MANIFEST_FILES:
        path = target_dir / name
        if not path.exists():
            raise SystemExit(f"Manifest missing: {path}")
        rewrite(path, version, checksum, release_date)
        print(f"Updated {path.relative_to(ROOT)}")

    print(f"\nVersion:  {version}")
    print(f"SHA256:   {checksum}")
    print(f"Released: {release_date}")
    print("\nValidate, then open the PR against microsoft/winget-pkgs:")
    print(f"  winget validate --manifest {target_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
