"""One place where a benchmark result becomes a file, and back.

Five benches — timing, DPC, network, FurMark, PresentMon — each carried their
own byte-identical ``save``/``load``/``list`` trio. They had already drifted
twice, which is the argument for extracting them rather than leaving them:

* the traversal fix landed in ``runner.py`` alone, so a result name became a
  filename verbatim in the other four;
* one of them swallowed a failed load in silence while the others logged it.

Neither divergence is a matter of taste, and both are settled here: a name is
squashed to one safe filename component wherever it comes from, and a result
that could not be read says so (C11 rule 3 — what could not be measured names
the reason, and that includes a measurement that cannot be read back).

This module owns files, never numbers. Nothing here interprets, summarises or
derives a reading; the benches keep their own dataclasses and their own
``from_dict``, and the store hands them the parsed JSON and stays out of it.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

# Anything that is not a plain filename character becomes one underscore. A run
# of them collapses so that `../../etc/passwd` cannot expand into a long trail
# of separators.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

# Long enough for any name a bench or a route supplies, short enough that the
# name plus its timestamp stays well inside the path limit.
_MAX_NAME_LENGTH = 64

# Win32 resolves these as devices, not files, whatever directory they are in and
# whatever extension follows. None can be reached through `save` today because a
# timestamp is always appended, but a component that is safe only because of
# what its caller appends is not a safe component.
_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{digit}" for digit in range(1, 10)}
    | {f"LPT{digit}" for digit in range(1, 10)}
)


def safe_filename_component(*parts: str, fallback: str = "benchmark") -> str:
    """Squash caller-supplied names into one safe filename component.

    The name reaching here is not always internal: ``/api/benchmark/run`` takes
    it from the request, and a capture takes half of it from a detected game's
    title. So it is treated as data — separators, colons, wildcards and quotes
    all become underscores, the result is bounded, and a name that reduces to
    nothing (dots only, empty) falls back rather than producing a hidden or
    empty filename.
    """
    squashed = "_".join(_UNSAFE_FILENAME_CHARS.sub("_", part) for part in parts if part)
    squashed = squashed[:_MAX_NAME_LENGTH].strip("._")
    if not squashed:
        return fallback
    if squashed.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        return f"{fallback}_{squashed}"
    return squashed


class ResultStore:
    """Read and write one benchmark's JSON results under one directory."""

    def __init__(self, directory: Path, logger: logging.Logger) -> None:
        self._directory = directory
        self._logger = logger

    @property
    def directory(self) -> Path:
        """The directory every result of this bench is written to."""
        return self._directory

    def save(self, payload: Mapping[str, Any], *name_parts: str) -> Path:
        """Write one result and return where it landed.

        Raises:
            ValueError: If the sanitised name still resolves outside the
                directory. The squash above makes that unreachable, so the check
                is there to fail loudly if it ever stops being.
        """
        component = safe_filename_component(*name_parts)
        filename = f"{component}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        directory = self._directory.resolve()
        path = (directory / filename).resolve()
        if path.parent != directory:
            raise ValueError(f"Benchmark result name {name_parts!r} escapes {directory}")

        directory.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2)

        return path

    def load(self, path: Path, build: Callable[[dict[str, Any]], T]) -> T | None:
        """Read one result file and rebuild it, or say why it could not be read.

        Never silent: a result that cannot be parsed is a measurement the user
        will not see, and a bench that drops one without a word is exactly what
        C11 forbids.
        """
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise TypeError(f"expected a JSON object, got {type(data).__name__}")
            return build(data)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._logger.error("Failed to load benchmark result %s: %s", path, exc)
            return None

    def list_files(self) -> list[Path]:
        """Every saved result, newest first.

        By modification time rather than by filename: the timestamp in a name
        only orders results that share a prefix, so a directory holding two
        differently named benches sorted alphabetically and called it recency.
        """
        if not self._directory.is_dir():
            return []
        results = list(self._directory.glob("*.json"))
        results.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return results
