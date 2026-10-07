"""Files earlier releases wrote and this one never writes again.

fpstune keeps no previous values and no history on disk (decided 2026-10-06,
#103; the in-memory change journal that remained was removed with the History
tab, #107): a reset is an apply of the setting's own default, and nothing
remembers what a setting held before. Earlier releases wrote `history.json` and
`originals.json` under the config directory; `remove_retired_files` deletes
what they left behind, once, at start-up.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fpstune.utils.config import get_config_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

#: What earlier releases left in the config directory. Globs, because a write
#: interrupted mid-replace leaves its `.tmp`, and an unreadable history was set
#: aside under a timestamped name rather than overwritten.
RETIRED_FILE_PATTERNS = (
    "originals.json",
    "originals.json.tmp",
    "history.json",
    "history.json.tmp",
    "history.unreadable-*.json",
)


def remove_retired_files(config_dir: Path | None = None) -> list[Path]:
    """Delete the stored previous values and history earlier releases wrote.

    Returns the files removed. A file that cannot be deleted is logged and left
    for the next start; it never stops the application from starting. The
    directory defaults to `get_config_dir()` and is never a literal path (C9).
    """
    directory = config_dir if config_dir is not None else get_config_dir()
    removed: list[Path] = []
    for pattern in RETIRED_FILE_PATTERNS:
        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("could not remove retired file %s: %s", path, exc)
                continue
            removed.append(path)
    if removed:
        logger.info("removed %d retired state file(s) from %s", len(removed), directory)
    return removed
