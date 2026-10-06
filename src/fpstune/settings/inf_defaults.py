"""What a device's own driver INF installs for message-signaled interrupts.

A driver ships its stock interrupt mode as a registry value its INF writes into the
device's hardware key at install time:

    HKR,"Interrupt Management\\MessageSignaledInterruptProperties",MSISupported,0x00010001,1

That line is the device's *driver default*, and it is the only honest answer to
"what does reset restore" — fpstune never records what it overwrote (C6: one way
back, reset to default). Three things make the answer non-trivial:

* An INF carries several MSI sections (a Realtek one has ``MSI.00`` writing 0 and
  ``MSI.16`` writing 1), and which one applies is decided by the install section
  the device was bound to — so the INF is walked from that section, never grepped.
* The hardware section's ``AddReg`` lists are comma lists over several lines, its
  numbers and names may be ``%strkey%`` references into ``[Strings]``, and an
  ``Include=``/``Needs=`` pair pulls sections from another system INF (``pci.inf``).
* No line at all is an answer too: the driver left the value unset, and stock is
  "absent" — reset deletes it rather than writing a number nobody chose.

What cannot be resolved (INF unreadable, install section missing, an included INF
or ``Needs`` section not found, a value that is not a number) is reported as
``None``, never guessed: the caller must not offer a reset it cannot derive.

``Needs`` sections are walked before the section's own ``AddReg`` lists, so the
driver's own line wins a conflict. ``DelReg`` is not read: no INF seen writes the
MSI key through it.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from fpstune.utils.logger import get_logger

logger = get_logger()

_MSI_SUBKEY = "interrupt management\\messagesignaledinterruptproperties"
_MSI_SUPPORTED = "msisupported"
_MESSAGE_NUMBER_LIMIT = "messagenumberlimit"

# AddReg flag bits (setupapi). The type lives in the high word.
_FLG_NOCLOBBER = 0x2
_FLG_DELVAL = 0x4
_FLG_KEYONLY = 0x10
_FLG_OVERWRITEONLY = 0x20
_FLG_TYPE_DWORD = 0x10001
_FLG_TYPE_MASK = 0xFFFF0001

_MAX_DEPTH = 8


@dataclass(frozen=True)
class InterruptDefaults:
    """The values a driver INF installs; None = the INF leaves that value unset."""

    msi_supported: int | None
    message_number_limit: int | None


class InfUnresolved(Exception):
    """The INF could not be walked to an answer; the message says where it stopped."""


# --- reading the file ----------------------------------------------------------------


def decode_inf(data: bytes) -> str:
    """INF text from bytes: UTF-16 with a BOM, UTF-8 with a BOM, else ANSI.

    Both encodings ship side by side in ``%WINDIR%\\INF``. Only ASCII tokens matter
    here, so the ANSI fallback is cp1252 with replacement.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    return data.decode("cp1252", errors="replace")


def _strip_comment(line: str) -> str:
    """``;`` starts a comment unless it sits inside a double-quoted string."""
    in_quotes = False
    for position, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ";" and not in_quotes:
            return line[:position]
    return line


def _logical_lines(text: str) -> list[str]:
    """Lines with comments dropped and trailing-backslash continuations joined."""
    joined: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if line.endswith("\\") and line.count('"') % 2 == 0:
            pending += line[:-1]
            continue
        line = pending + line
        pending = ""
        if line.strip():
            joined.append(line.strip())
    if pending.strip():
        joined.append(pending.strip())
    return joined


def split_fields(text: str) -> list[str]:
    """Comma-separated INF fields, quotes removed, ``""`` read as one quote."""
    fields: list[str] = []
    current: list[str] = []
    in_quotes = False
    position = 0
    while position < len(text):
        char = text[position]
        if char == '"':
            if in_quotes and text[position + 1 : position + 2] == '"':
                current.append('"')
                position += 1
            else:
                in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        position += 1
    fields.append("".join(current).strip())
    return fields


_DIRECTIVE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*=\s*(.*)$")
_STRING_TOKEN = re.compile(r"%([^%\s]*)%")


class Inf:
    """A parsed INF: sections as lists of logical lines, plus its string table."""

    def __init__(self, text: str) -> None:
        self.sections: dict[str, list[str]] = {}
        name: str | None = None
        for line in _logical_lines(text):
            if line.startswith("[") and "]" in line:
                name = line[1 : line.index("]")].strip().lower()
                self.sections.setdefault(name, [])
            elif name is not None:
                self.sections[name].append(line)
        self.strings: dict[str, str] = {}
        # [Strings] first, then localised tables ([Strings.0409]) as fallback.
        for table in sorted(
            (n for n in self.sections if n == "strings" or n.startswith("strings.")),
            key=lambda n: n != "strings",
        ):
            for line in self.sections[table]:
                match = _DIRECTIVE.match(line)
                if match:
                    value = split_fields(match.group(2))[0]
                    self.strings.setdefault(match.group(1).lower(), value)

    def expand(self, field: str) -> str:
        """Replace ``%key%`` with its [Strings] value and ``%%`` with ``%``."""

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key == "":
                return "%"
            return self.strings.get(key.lower(), match.group(0))

        return _STRING_TOKEN.sub(replace, field)

    def directives(self, section: str, wanted: tuple[str, ...]) -> dict[str, list[str]]:
        """Every ``key = a, b`` list in a section for the wanted keys, repeats appended."""
        found: dict[str, list[str]] = {key: [] for key in wanted}
        for line in self.sections.get(section, []):
            match = _DIRECTIVE.match(line)
            if match and match.group(1).lower() in found:
                found[match.group(1).lower()].extend(
                    self.expand(item) for item in split_fields(match.group(2)) if item
                )
        return found


# --- walking from the install section to the MSI lines -------------------------------


def _parse_number(text: str) -> int:
    text = text.strip()
    try:
        return int(text, 0)
    except ValueError:
        pass
    try:
        return int(text, 10)  # "010": decimal in an INF, a syntax error to int(.., 0)
    except ValueError as exc:
        raise InfUnresolved(f"not a number: {text!r}") from exc


def _apply_addreg(inf: Inf, section: str, state: dict[str, int | None]) -> None:
    """Replay one AddReg section's MSI lines onto ``state`` (value name -> number or None)."""
    if section not in inf.sections:
        raise InfUnresolved(f"AddReg section [{section}] is not in the INF")
    for line in inf.sections[section]:
        fields = [inf.expand(f) for f in split_fields(line)]
        if len(fields) < 3 or fields[0].upper() != "HKR":
            continue
        subkey = fields[1].replace("/", "\\").strip("\\ ").lower()
        name = fields[2].lower()
        if subkey != _MSI_SUBKEY or name not in (_MSI_SUPPORTED, _MESSAGE_NUMBER_LIMIT):
            continue
        flags = _parse_number(fields[3]) if len(fields) > 3 and fields[3] else 0
        if flags & _FLG_KEYONLY:
            continue
        if flags & _FLG_DELVAL:
            state[name] = None
            continue
        if flags & _FLG_TYPE_MASK != _FLG_TYPE_DWORD:
            raise InfUnresolved(f"{fields[2]} is written with flags {flags:#x}, not as a DWORD")
        if len(fields) < 5 or not fields[4]:
            raise InfUnresolved(f"{fields[2]} has no value")
        if flags & _FLG_NOCLOBBER and state.get(name) is not None:
            continue
        if flags & _FLG_OVERWRITEONLY and state.get(name) is None:
            continue
        state[name] = _parse_number(fields[4])


def _needs_candidates(needs: str, ext: str) -> list[str]:
    """Section names a ``Needs=`` entry may mean, decorated first."""
    lowered = needs.lower()
    if lowered.endswith(".hw"):
        return [lowered[:-3] + ext.lower() + ".hw", lowered]
    return [lowered + ext.lower(), lowered]


@dataclass
class _Walk:
    inf_dir: Path
    ext: str
    loaded: dict[str, Inf]

    def load(self, name: str) -> Inf:
        key = name.lower()
        if key not in self.loaded:
            path = self.inf_dir / name
            try:
                self.loaded[key] = Inf(decode_inf(path.read_bytes()))
            except OSError as exc:
                raise InfUnresolved(f"cannot read {path}: {exc.__class__.__name__}") from exc
        return self.loaded[key]


def _walk_section(
    walk: _Walk,
    inf: Inf,
    section: str,
    state: dict[str, int | None],
    seen: set[tuple[int, str]],
    depth: int,
) -> None:
    if depth > _MAX_DEPTH:
        raise InfUnresolved("Include/Needs nest deeper than any real INF")
    if (id(inf), section) in seen:
        return
    seen.add((id(inf), section))
    lists = inf.directives(section, ("include", "needs", "addreg"))
    for needed in lists["needs"]:
        for included in lists["include"]:
            other = walk.load(included)
            target = next(
                (c for c in _needs_candidates(needed, walk.ext) if c in other.sections), None
            )
            if target is not None:
                _walk_section(walk, other, target, state, seen, depth + 1)
                break
        else:
            raise InfUnresolved(f"Needs={needed} is in none of the included INFs")
    for addreg in lists["addreg"]:
        _apply_addreg(inf, addreg.lower(), state)


def interrupt_defaults_from_inf(
    inf_name: str, section: str, section_ext: str, inf_dir: Path
) -> InterruptDefaults:
    """The interrupt values the install section ``section``+``section_ext`` writes.

    Raises ``InfUnresolved`` when the INF cannot be walked to an answer.
    """
    walk = _Walk(inf_dir=inf_dir, ext=section_ext, loaded={})
    inf = walk.load(inf_name)
    install = [c for c in ((section + section_ext).lower(), section.lower()) if c in inf.sections]
    if not install:
        raise InfUnresolved(f"install section [{section}{section_ext}] is not in {inf_name}")
    hardware = next(
        (
            c
            for c in ((section + section_ext + ".hw").lower(), (section + ".hw").lower())
            if c in inf.sections
        ),
        None,
    )
    state: dict[str, int | None] = {}
    if hardware is not None:
        _walk_section(walk, inf, hardware, state, set(), 0)
    return InterruptDefaults(state.get(_MSI_SUPPORTED), state.get(_MESSAGE_NUMBER_LIMIT))


# --- the device-facing entry point ---------------------------------------------------

_cache: dict[str, InterruptDefaults] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _inf_dir() -> Path:
    return Path(os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows") / "INF"


def interrupt_defaults(instance_id: str) -> InterruptDefaults | None:
    """The driver default for a PnP instance id, or None when it cannot be derived.

    Cached per instance for the life of the process and never persisted: a driver
    update replaces the INF, and the next start must read the new one.
    """
    with _cache_lock:
        cached = _cache.get(instance_id)
    if cached is not None:
        return cached
    from fpstune.utils.winapi.devnode import driver_inf

    binding = driver_inf(instance_id)
    if binding is None:
        logger.warning(
            "No driver INF is bound to %s; its interrupt default is unknown", instance_id
        )
        return None
    try:
        result = interrupt_defaults_from_inf(
            binding.path, binding.section, binding.section_ext, _inf_dir()
        )
    except InfUnresolved as exc:
        logger.warning(
            "Could not derive the interrupt default of %s from %s: %s",
            instance_id,
            binding.path,
            exc,
        )
        return None
    with _cache_lock:
        _cache[instance_id] = result
    return result
