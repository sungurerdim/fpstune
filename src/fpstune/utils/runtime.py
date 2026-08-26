"""Where fpstune is running from, answered once.

A packaged build and a source checkout differ in two ways that matter, and both
of them were being guessed at separately:

* **Paths.** ``__file__`` inside a PyInstaller executable points into a temporary
  extraction directory, so climbing parents from it lands somewhere arbitrary.
  ``cli.serve`` did exactly that and reported *"Frontend not found at
  C:\\Users\\<name>\\AppData\\Local\\frontend"* — three levels up from a temp dir
  rather than anywhere fpstune had ever put anything.

* **Re-execution.** ``sys.executable`` is the Python interpreter from source and
  is ``fpstune.exe`` when frozen. ``cli.serve`` spawned
  ``[sys.executable, "-m", "uvicorn", ...]``, so a packaged build relaunched
  *itself* with arguments its own CLI does not accept, the child exited at once,
  and the parent printed "API process exited" on a loop.

Both are the same question — am I packaged, and where did my files go — so it is
answered here and imported, rather than re-derived at each call site.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The source tree's root, from this file: utils/ -> fpstune/ -> src/ -> repo.
_SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than a source tree."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path | None:
    """The directory a frozen build extracted its data files into, if any."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def frontend_dist() -> Path | None:
    """The built UI, wherever this build keeps it.

    Frozen builds carry it inside the executable; a source checkout has it under
    ``frontend/dist`` once ``npm run build`` has been run. Returns None when
    neither is present, which for a source checkout means "run the build" and
    for a frozen one means the executable was built wrong — the packaging spec
    refuses that case, so it should be unreachable there.
    """
    root = bundle_root()
    if root is not None:
        candidate = root / "frontend" / "dist"
        if candidate.is_dir():
            return candidate

    candidate = _SOURCE_ROOT / "frontend" / "dist"
    return candidate if candidate.is_dir() else None


def frontend_source() -> Path | None:
    """The UI's *source* directory, for the dev server. None when frozen.

    A packaged build has no ``package.json`` and no ``node_modules`` to run Vite
    from, and asking it to is how the "frontend not found" path was reached.
    """
    if is_frozen():
        return None
    candidate = _SOURCE_ROOT / "frontend"
    return candidate if (candidate / "package.json").is_file() else None
