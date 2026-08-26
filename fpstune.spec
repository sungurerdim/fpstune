# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for fpstune.
#
# The hidden-import list is collected, not written out. A hand-kept list drifts
# the moment a module is added or removed, and it drifts silently: PyInstaller
# only complains about names it cannot find, never about ones nobody listed. The
# version this replaced named `fpstune.safety.backup` and `fpstune.safety.revert`
# — neither has existed for some time — while missing `safety.originals`, every
# `api/routes/system_*` split, `settings_stream`, `impact_categories` and the
# whole `diagnostics` package. It also pointed `datas` at a `profiles/`
# directory the profile system took with it when it was removed, which is a hard
# build failure rather than a silent one.
#
# Almost everything here loads through a registry or a route table rather than a
# literal import, so the analyser cannot see it; collecting the package wholesale
# is both simpler and correct.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH)

frontend_dist = project_root / "frontend" / "dist"
if not frontend_dist.is_dir():
    raise SystemExit(
        f"frontend/dist not found at {frontend_dist}.\n"
        "The UI is served from inside the executable, so a build without it "
        "produces a binary that starts and then shows nothing.\n"
        "Run: cd frontend && npm ci && npm run build"
    )

datas = [(str(frontend_dist), "frontend/dist")]

hiddenimports = [
    # Settings definitions, executors, routes and diagnostics are reached through
    # registries and routers, so static analysis finds none of them.
    *collect_submodules("fpstune"),
    # Uvicorn picks its protocol implementations at runtime by name.
    "uvicorn.logging",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(project_root / "src" / "fpstune" / "cli.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="fpstune",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX shrinks the binary and raises SmartScreen friction on an unsigned one,
    # which is the wrong trade for a release nobody can code-sign yet.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    # fpstune writes to HKLM, service start types and power schemes. Without
    # this it launches unelevated and every write fails with access denied,
    # which reads to a user as "it did nothing".
    uac_admin=True,
    uac_uiaccess=False,
    version_file=None,
)
