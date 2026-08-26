"""What a release promises, checked here rather than discovered after a tag.

Three of these are version SSOT. `pyproject.toml` holds the version and
`scripts/sync_version.py` copies it into `__init__.py` and `package.json` — but
copying is only a single source of truth if something notices when a copy drifts.
Nothing did. A release whose binary reports a different number than the tag it
hangs under is the kind of thing nobody catches until they are trying to
reproduce a bug report against it.

The rest is the packaging contract. The PyInstaller spec used to name modules
that had not existed for months and a `profiles/` data directory that went away
with the profile system — a hard build failure that only a build would find, and
nobody built between releases because there were no releases.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


class TestOneVersion:
    """`pyproject.toml` is the source; the other two are copies of it."""

    def test_the_python_package_reports_the_pyproject_version(self) -> None:
        text = (ROOT / "src" / "fpstune" / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
        assert match, "fpstune.__version__ is gone; the CLI and the API both report it"
        assert match.group(1) == _pyproject_version(), (
            "run scripts/sync_version.py — the package reports a different version "
            "than the one a release tag is checked against"
        )

    def test_the_frontend_reports_the_pyproject_version(self) -> None:
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        assert package.get("version") == _pyproject_version(), (
            "run scripts/sync_version.py — the UI and the backend would ship "
            "claiming different versions"
        )

    def test_the_version_is_a_tag_shaped_string(self) -> None:
        """The release workflow compares it to a `vX.Y.Z` tag verbatim."""
        assert re.fullmatch(r"\d+\.\d+\.\d+([.-]\w+)?", _pyproject_version()), _pyproject_version()


class TestTheReleaseWorkflow:
    """The workflow is the only thing standing between a tag and the public.

    Written alongside the workflow and held back from `main` for a week because
    the OAuth token lacked `workflow` scope and could not push the file these
    assert against — which is why every one of them names a string the workflow
    must contain rather than a shape it must have. A test that passes against a
    workflow nobody can push is worth nothing.
    """

    @pytest.fixture(scope="class")
    def workflow(self) -> str:
        path = ROOT / ".github" / "workflows" / "release.yml"
        assert path.exists(), "there is no release workflow, so releases are hand-made"
        return path.read_text(encoding="utf-8")

    def test_it_runs_the_test_suite_before_publishing(self, workflow: str) -> None:
        """A release must not be the first place a check runs."""
        assert "uv run pytest" in workflow
        assert "uv run mypy src" in workflow
        assert "npm run test:run" in workflow

    def test_it_refuses_a_tag_that_disagrees_with_the_version(self, workflow: str) -> None:
        assert "does not match pyproject version" in workflow

    def test_it_publishes_a_checksum(self, workflow: str) -> None:
        """The binary is unsigned, so this is what a user can actually check."""
        assert "sha256" in workflow.lower()
        assert "fpstune.exe.sha256" in workflow

    def test_it_attests_where_the_binary_came_from(self, workflow: str) -> None:
        """Stronger than the checksum: it ties the binary to a source commit.

        A checksum only proves the file matches the one published beside it; it
        says nothing about what that file was built from.
        """
        assert "attest-build-provenance" in workflow
        assert "attestations: write" in workflow

    def test_a_rehearsal_run_keeps_its_build_even_when_provenance_cannot(
        self, workflow: str
    ) -> None:
        """The upload must come before the attestation, not after it.

        Measured, on run 32598698082: every packaging step passed — PyInstaller,
        the binary printing its own version, the size ceiling, the checksum — and
        then provenance failed with "Feature not available for user-owned private
        repositories". Because the upload sat behind it, the run that existed to
        rehearse packaging handed back no exe at all. The one step that cannot
        work on this repo took the artifact down with it.
        """
        upload = workflow.index("actions/upload-artifact")
        attest = workflow.index("actions/attest-build-provenance")
        assert upload < attest, "the build artifact is hostage to the attestation step"

    def test_provenance_is_reserved_for_something_actually_published(self, workflow: str) -> None:
        # Provenance is a claim about a published file, and a dispatch run
        # publishes nothing, so it is gated the same way Publish is.
        attest = workflow.index("actions/attest-build-provenance")
        preceding = workflow[:attest]
        assert "if: startsWith(github.ref, 'refs/tags/')" in preceding.rsplit("- name:", 1)[-1]

    def test_it_verifies_the_ui_is_inside_the_binary(self, workflow: str) -> None:
        assert "Bundled UI is missing" in workflow


class TestTheReadmeDescribesWhatShips:
    """Doc drift has now happened twice, so it gets a guard rather than a fix.

    The README advertised "225+ settings" against a real 284, was corrected, and
    drifted again to 284 against 293 the moment ten were added. It is the first
    thing anyone reads and the last thing anyone updates, and a hand-counted
    number in a document is a number that is wrong between every two commits.
    """

    @pytest.fixture(scope="class")
    def readme(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_the_headline_count_is_the_registry_count(self, readme: str) -> None:
        from fpstune.settings.registry import SettingsRegistry

        # discover_dynamic=False on purpose: the per-adapter settings depend on
        # the machine, and the README says so a line below the number.
        actual = len(SettingsRegistry(discover_dynamic=False).get_all())
        match = re.search(r"\*\*(\d+) settings across", readme)

        assert match, "the README no longer states a setting count"
        assert int(match.group(1)) == actual, (
            f"README says {match.group(1)} settings, the registry has {actual}"
        )

    def test_the_per_category_table_adds_up_to_the_headline(self, readme: str) -> None:
        """A correct total over a stale table is the drift that hides itself."""
        rows = re.findall(r"^\|\s*[\w /]+\s*\|\s*(\d+)\s*\|", readme, flags=re.MULTILINE)
        match = re.search(r"\*\*(\d+) settings across", readme)

        assert match and rows, "the README's overview table is gone"
        assert sum(int(row) for row in rows) == int(match.group(1)), (
            f"the category rows sum to {sum(int(r) for r in rows)}, "
            f"the headline says {match.group(1)}"
        )

    def test_it_does_not_document_a_command_that_no_longer_exists(self, readme: str) -> None:
        """`fpstune apply` and `fpstune revert --all` outlived themselves in here.

        A documented command that errors out is worse than an undocumented one:
        the reader concludes the tool is broken rather than that the page is.
        """
        from fpstune.cli import main

        # Only inside fenced blocks: prose says "fpstune reads registry keys",
        # which is a sentence and not an invocation.
        documented: set[str] = set()
        for block in re.findall(r"```[a-z]*\n(.*?)```", readme, flags=re.DOTALL):
            documented |= set(re.findall(r"^fpstune (?:-\w+ )*([a-z][\w-]*)", block, re.MULTILINE))
        unknown = sorted(documented - set(main.commands))

        assert not unknown, f"the README documents commands that are not registered: {unknown}"

    def test_it_documents_every_command_that_is_registered(self, readme: str) -> None:
        """The other direction, and the one that was missing.

        Only the implication above was asserted, so a command could be
        registered and never written down and nothing would notice. That is not
        hypothetical: the CLI section documented 5 of 11 commands for months,
        and the six missing ones were not broken — they were invisible, which on
        a tool nobody reads `--help` for first is the same thing.

        An inline code span counts, not only a fenced block: four of the
        commands are measurement trees introduced in a paragraph rather than in
        a shell example, and a sentence naming `fpstune gpu-bench` is how a
        reader finds it.
        """
        from fpstune.cli import main

        documented: set[str] = set()
        for block in re.findall(r"```[a-z]*\n(.*?)```", readme, flags=re.DOTALL):
            documented |= set(re.findall(r"^fpstune (?:-\w+ )*([a-z][\w-]*)", block, re.MULTILINE))
        documented |= set(re.findall(r"`fpstune (?:-\w+ )*([a-z][\w-]*)", readme))

        undocumented = sorted(set(main.commands) - documented)

        assert not undocumented, (
            f"these commands are registered and the README never names them: {undocumented} "
            "— add them to the CLI section, in a shell block or in prose"
        )


WINGET_ROOT = ROOT / "winget" / "manifests" / "s" / "sungurerdim" / "fpstune"
ZEROED_SHA = "0" * 64


def _installer_manifests() -> list[Path]:
    if not WINGET_ROOT.is_dir():
        return []
    return sorted(WINGET_ROOT.glob("*/*.installer.yaml"))


def _known_tags() -> set[str]:
    """Tags this checkout can see, which is not always all of them.

    A shallow CI checkout of a branch carries no tags at all, so the strict
    check below is vacuous there and meaningful in the two places that matter:
    a developer's clone, and the tag-triggered release run, where checkout
    fetches the tag it was told to build.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--list"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _tag_being_built() -> str | None:
    """The tag whose release workflow is running right now, if that is us.

    That one tag is exempt below, and only that one. Its manifest cannot be
    filled in yet by construction: the checksum describes a binary the workflow
    has not built at the point the suite runs. Every older tag stays strict, so
    a release whose manifest was never committed turns the next run red.
    """
    if os.environ.get("GITHUB_REF_TYPE") != "tag":
        return None
    return os.environ.get("GITHUB_REF_NAME") or None


class TestTheWingetManifests:
    """A manifest is a promise about bytes, and this one shipped promising none.

    `winget/manifests/.../sungurerdim.fpstune.installer.yaml` carries an
    all-zeros `InstallerSha256` and a download URL for a tag that was never
    published. As a template that is correct and deliberate. Submitted to
    winget-pkgs it would be a package whose checksum matches nothing, which is
    worse than no package — winget would refuse the install after the download,
    and the user would conclude the binary is corrupt.

    `scripts/update_winget_manifest.py` is what turns the template into a real
    manifest, and the release workflow runs it against the exe it just built.
    These check that the two never get out of order.
    """

    def test_there_is_a_manifest_at_all(self) -> None:
        assert _installer_manifests(), f"no installer manifest under {WINGET_ROOT}"

    def test_every_manifest_parses(self) -> None:
        """Unparseable YAML is rejected after submission rather than before."""
        for path in _installer_manifests():
            for sibling in path.parent.glob("*.yaml"):
                yaml.safe_load(sibling.read_text(encoding="utf-8"))

    def test_a_zeroed_checksum_never_sits_under_a_released_version(self) -> None:
        """The one the issue asked for: template plus tag equals publishable lie.

        Until a version is tagged, a zeroed checksum is a placeholder waiting for
        a build. The moment the tag exists the placeholder is a manifest for a
        release that is downloadable, and anyone — including a future
        maintainer reading the directory — could submit it.
        """
        tags = _known_tags() - {_tag_being_built()}

        offenders = []
        for path in _installer_manifests():
            version = path.parent.name
            text = path.read_text(encoding="utf-8")
            if ZEROED_SHA in text and f"v{version}" in tags:
                offenders.append(f"{path.relative_to(ROOT)} (tag v{version} exists)")

        assert not offenders, (
            "these manifests carry an all-zeros InstallerSha256 for a version that has "
            f"been tagged: {offenders} — run `task winget` against the published exe "
            "and commit the result before anything is submitted to winget-pkgs"
        )

    def test_a_zeroed_checksum_says_in_the_file_that_it_is_not_publishable(self) -> None:
        """The half of the guard that is never vacuous.

        A shallow checkout knows no tags, so the check above can pass by knowing
        nothing. This one holds everywhere: a placeholder checksum has to be
        labelled as one, in the file, where the person about to submit it looks.
        """
        for path in _installer_manifests():
            text = path.read_text(encoding="utf-8")
            if ZEROED_SHA in text:
                assert "TEMPLATE" in text and "NOT PUBLISHABLE" in text, (
                    f"{path.relative_to(ROOT)} has a placeholder checksum and does not say so"
                )
            else:
                # And the converse, because a warning that is wrong is a warning
                # nobody reads the next time. The update script strips the
                # banner when it writes a real checksum.
                assert "NOT PUBLISHABLE" not in text, (
                    f"{path.relative_to(ROOT)} has a real checksum and still calls "
                    "itself an unpublishable template"
                )

    def test_each_manifest_states_the_version_of_the_directory_it_is_in(self) -> None:
        """The update script copies a directory to make a new version.

        A copy whose `PackageVersion` was not rewritten installs the old release
        under the new number, and every file in the directory has to agree
        before winget accepts any of them.
        """
        for path in _installer_manifests():
            expected = path.parent.name
            for sibling in sorted(path.parent.glob("*.yaml")):
                data = yaml.safe_load(sibling.read_text(encoding="utf-8"))
                assert str(data["PackageVersion"]) == expected, (
                    f"{sibling.relative_to(ROOT)} says PackageVersion "
                    f"{data['PackageVersion']!r} inside the {expected} directory"
                )


class TestThePackagingSpec:
    """A spec that cannot build is only discovered by building."""

    @pytest.fixture(scope="class")
    def spec_source(self) -> str:
        return (ROOT / "fpstune.spec").read_text(encoding="utf-8")

    def test_it_parses(self, spec_source: str) -> None:
        ast.parse(spec_source)

    def test_it_collects_the_package_rather_than_listing_it(self, spec_source: str) -> None:
        """The hand-kept list is what rotted.

        It named `fpstune.safety.backup` and `fpstune.safety.revert`, neither of
        which existed, while missing `safety.originals`, every `system_*` route
        split, `settings_stream`, `impact_categories` and all of `diagnostics`.
        PyInstaller complains about names it cannot find and says nothing about
        the ones nobody listed, so half the drift was silent.
        """
        assert "collect_submodules" in spec_source
        assert 'collect_submodules("fpstune")' in spec_source

    def test_it_points_at_no_directory_that_does_not_exist(self, spec_source: str) -> None:
        """`profiles/` went away with the profile system and stayed in the spec.

        A data path PyInstaller cannot find is a hard build failure.
        """
        for referenced in re.findall(r'project_root\s*/\s*"([^"]+)"', spec_source):
            # frontend/dist is produced by the build, so its absence here is
            # expected and the spec fails loudly on it by design.
            if referenced == "frontend":
                continue
            assert (ROOT / referenced).exists(), f"fpstune.spec references a missing {referenced!r}"

    def test_it_refuses_to_build_without_the_bundled_ui(self, spec_source: str) -> None:
        """The UI is served from inside the executable.

        Building without it produces a binary that starts and shows nothing —
        a failure that looks like a runtime bug days later rather than a build
        error immediately.
        """
        assert "frontend_dist.is_dir()" in spec_source
        assert "SystemExit" in spec_source

    def test_it_asks_for_administrator(self, spec_source: str) -> None:
        """Unelevated, every write fails with access denied and fpstune looks
        like it did nothing."""
        assert "uac_admin=True" in spec_source

    def test_it_does_not_compress_with_upx(self, spec_source: str) -> None:
        """UPX raises SmartScreen friction, which an unsigned binary cannot afford."""
        assert "upx=False" in spec_source
