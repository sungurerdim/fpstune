"""PowerShell utility functions for safe command execution.

This module provides functions for safely escaping and constructing
PowerShell commands with user-provided or dynamic values.
"""

from __future__ import annotations

import codecs
import contextlib
import io
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

_PLACEHOLDER = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")

# A value substituted outside any quotes becomes its own token of the generated
# command (a netsh argument, a cmdlet parameter value, an [int] cast operand).
# There is no quoting layer to escape into, so the only safe policy is an
# allowlist. Every unquoted substitution the shipped templates make today is an
# English keyword (enabled, CTCP), an integer (interface index, MTU) or a
# dotted/colon-joined variant of those; anything wider — a space, a quote, ';',
# '$(' — would append attacker-chosen tokens to an elevated command line.
_BARE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _escape_for_context(name: str, value: str, quote: str | None) -> str:
    """Escape a substituted value for the quoting context it lands in."""
    if quote == "'":
        return value.replace("'", "''")
    if quote == '"':
        # Backtick first, so the backticks introduced below are not doubled.
        escaped = value.replace("`", "``")
        return escaped.replace('"', '`"').replace("$", "`$")
    if not _BARE_TOKEN.match(value):
        raise ValueError(
            f"Placeholder %{name}% lands outside any quotes, where value {value!r} "
            "would become extra command tokens; only plain keyword/number values "
            "are allowed there"
        )
    return value


def substitute_placeholders(template: str, **kwargs: Any) -> str:
    """Replace %key% placeholders with values, escaped for where they land.

    Uses %key% syntax to avoid conflicts with:
    - Python .format() braces {}
    - PowerShell script blocks {}
    - Regex quantifiers {n,m}

    Every placeholder value is treated as *data*, never as script: the template
    is scanned with a PowerShell quoting state machine, and each value is
    escaped for the context its placeholder sits in — `'` doubled inside a
    single-quoted literal, backtick-escaped inside a double-quoted one, and
    restricted to a plain keyword/number token when unquoted. A value
    containing `'; Remove-Item ...` therefore stays inside its literal instead
    of running. No call site substitutes a command *fragment* (verified across
    the registry), so there is deliberately no raw/opt-out path; a future
    fragment need must add an explicit one rather than weaken this default.

    Args:
        template: String with %key% placeholders.
        **kwargs: Key-value pairs for substitution.

    Returns:
        String with placeholders replaced and escaped per context.

    Raises:
        ValueError: If a value substituted outside any quotes is not a plain
            keyword/number token.

    Example:
        >>> substitute_placeholders("$action = '%value%'", value="it's")
        "$action = 'it''s'"
    """
    values = {key: str(value) for key, value in kwargs.items()}
    out: list[str] = []
    i = 0
    n = len(template)
    # None = outside any string; "'" / '"' = inside that kind of PS literal.
    quote: str | None = None
    while i < n:
        ch = template[i]
        if ch == "%":
            match = _PLACEHOLDER.match(template, i)
            if match and match.group(1) in values:
                out.append(_escape_for_context(match.group(1), values[match.group(1)], quote))
                i = match.end()
                continue
        if quote == "'":
            if ch == "'":
                if template.startswith("''", i):
                    out.append("''")
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == "`" and i + 1 < n:
                out.append(template[i : i + 2])
                i += 2
                continue
            if ch == '"':
                if template.startswith('""', i):
                    out.append('""')
                    i += 2
                    continue
                quote = None
        else:
            if ch == "'":
                quote = "'"
            elif ch == '"':
                quote = '"'
            elif ch == "`" and i + 1 < n:
                out.append(template[i : i + 2])
                i += 2
                continue
            elif ch == "#":
                # Comments may contain apostrophes (several shipped scripts do);
                # counting those as string delimiters would corrupt the state.
                end = template.find("\n", i)
                end = n if end == -1 else end
                out.append(template[i:end])
                i = end
                continue
            elif ch == "<" and template.startswith("<#", i):
                end = template.find("#>", i + 2)
                end = n if end == -1 else end + 2
                out.append(template[i:end])
                i = end
                continue
        out.append(ch)
        i += 1
    return _rewrite_netadapter_interface_index("".join(out))


# Only the bare Get-NetAdapter accepts -InterfaceIndex. Every other NetAdapter*
# cmdlet (AdvancedProperty, Lso, ChecksumOffload, Rss, PowerManagement, Binding,
# Restart) takes -Name and rejects -InterfaceIndex outright with
# "A parameter cannot be found that matches parameter name 'InterfaceIndex'".
# The suffix group below is what excludes bare Get-NetAdapter: it requires at
# least one more letter after "NetAdapter".
_NETADAPTER_BY_INDEX = re.compile(
    r"\b((?:Get|Set|Enable|Disable|Restart|New|Remove)-NetAdapter[A-Za-z]+)"
    r"\s+-InterfaceIndex\s+(\d+)"
)

_ADAPTER_NAME_VAR = "$fpstuneAdapterName"


def _rewrite_netadapter_interface_index(command: str) -> str:
    """Rewrite NetAdapter* cmdlet calls that pass an unsupported -InterfaceIndex.

    fpstune deliberately keys per-adapter settings by InterfaceIndex, because an
    adapter name can be localised and contain characters that are awkward to
    quote. That is the right identifier to *store* — but it is not a parameter
    these cmdlets accept, so every generated command failed at parameter binding.
    Detection returned nothing and, worse, ``Set-NetAdapterAdvancedProperty``
    silently wrote nothing while the apply path reported success.

    The index is resolved to a name once, up front, and the calls are rewritten
    to ``-Name``. Quoting the variable keeps names with spaces intact.
    """
    matches = _NETADAPTER_BY_INDEX.findall(command)
    if not matches:
        return command

    index = matches[0][1]
    rewritten = _NETADAPTER_BY_INDEX.sub(rf"\1 -Name {_ADAPTER_NAME_VAR}", command)
    preamble = (
        f"{_ADAPTER_NAME_VAR} = (Get-NetAdapter -InterfaceIndex {index} "
        f"-ErrorAction SilentlyContinue).Name; "
    )
    return preamble + rewritten


def escape_single_quoted(value: str) -> str:
    """Escape a string for use in PowerShell single-quoted strings.

    In PowerShell single-quoted strings, only single quotes need escaping
    by doubling them: ' -> ''

    Args:
        value: The string to escape.

    Returns:
        Escaped string safe for single-quoted PowerShell strings.

    Example:
        >>> escape_single_quoted("It's a test")
        "It''s a test"
    """
    if not value:
        return value
    return value.replace("'", "''")


def escape_guid(guid: str) -> str:
    """Convert a GUID string to a PowerShell-safe format.

    PowerShell interprets {} as script blocks. To use GUIDs safely,
    we construct them using [char] codes:
    - [char]123 = {
    - [char]125 = }

    Args:
        guid: GUID string like "{fc52a749-4be9-4510-896e-966ba6525980}"
              or "fc52a749-4be9-4510-896e-966ba6525980"

    Returns:
        PowerShell expression that constructs the GUID safely.

    Example:
        >>> escape_guid("{fc52a749-4be9-4510-896e-966ba6525980},3")
        "[char]123 + 'fc52a749-4be9-4510-896e-966ba6525980' + [char]125 + ',3'"
    """
    if not guid:
        return "''"

    # Check if it's already in the escaped format
    if "[char]123" in guid:
        return guid

    # Split into parts: before {, inside {}, after }
    # Pattern: optional prefix + {GUID} + optional suffix
    match = re.match(r"^([^{]*)\{([^}]+)\}(.*)$", guid)
    if match:
        prefix, inner, suffix = match.groups()
        parts = []
        if prefix:
            parts.append(f"'{escape_single_quoted(prefix)}'")
        parts.append("[char]123")
        parts.append(f"'{escape_single_quoted(inner)}'")
        parts.append("[char]125")
        if suffix:
            parts.append(f"'{escape_single_quoted(suffix)}'")
        return " + ".join(parts)

    # No braces, just escape single quotes
    return f"'{escape_single_quoted(guid)}'"


def build_ps_variable(name: str, value: str, escape_braces: bool = False) -> str:
    """Build a PowerShell variable assignment with proper escaping.

    Args:
        name: Variable name (without $).
        value: Value to assign.
        escape_braces: If True, escape {} using [char] codes.

    Returns:
        PowerShell variable assignment statement.

    Example:
        >>> build_ps_variable("deviceId", "My Device's Name")
        "$deviceId = 'My Device''s Name'"
    """
    if escape_braces and ("{" in value or "}" in value):
        escaped = escape_guid(value)
        return f"${name} = {escaped}"
    else:
        escaped = escape_single_quoted(value)
        return f"${name} = '{escaped}'"


def _reap_in_background(process: subprocess.Popen[str]) -> None:
    """Drain a killed child's pipes off the calling thread, however long it takes.

    Killing PowerShell does not close the pipe handles it handed to whatever it
    started, and ``subprocess.run`` reaps a timed-out child with a
    ``communicate()`` that takes no timeout — so the timeout it promises is only
    honoured when the child leaves no grandchild behind. It does here: the
    cleanup-size scan runs ``dism.exe``, which keeps the pipe open long after
    PowerShell is gone.

    Measured on 2026-09-03: the DISM size scan started 02:34:30, its PowerShell
    was killed at the 90 s timeout, and ``Dism.exe`` was still running — parent
    dead, pipe held — twenty minutes later, with ``run_powershell`` still inside
    that reaping ``communicate()``. The caller never returned, so
    ``cleanup:dism_cleanup`` never left "calculating", the freed-space number
    never arrived, and the UI polled for it every three seconds for the life of
    the process.

    The orphan is deliberately left alone rather than tree-killed: the same
    runner carries ``dism /StartComponentCleanup``, and interrupting servicing
    mid-write is a bigger risk than an analysis that finishes unread (C1).
    """

    def _drain() -> None:
        with contextlib.suppress(Exception):
            process.communicate()

    threading.Thread(target=_drain, daemon=True, name="powershell-reap").start()


def _powershell_argv(command: str) -> list[str]:
    """The argument vector both runners start, so they cannot drift apart."""
    # Prefix command with UTF-8 encoding for international Windows
    utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        utf8_prefix + command,
    ]


class _LineSplitter:
    """Turn a byte stream into the lines a terminal would show.

    A console progress bar is not a sequence of lines. DISM prints its bar,
    returns the carriage without a line feed, and prints the next one over the
    top; SFC does the same. Appending each of those as its own line turns one
    bar into hundreds of near-identical rows, which is why the raw output of a
    long repair is unreadable rather than informative.

    So each emitted line says whether it *replaces* the one before it: carriage
    return without line feed means redraw, CRLF and LF mean a new line. A CR is
    held until the next character decides which of the two it was, and flushed
    at end of stream.
    """

    def __init__(self, on_line: Callable[[str, bool], None]) -> None:
        self._on_line = on_line
        self._pending = ""
        self._held_cr = False

    def feed(self, text: str) -> None:
        for ch in text:
            if self._held_cr:
                self._held_cr = False
                if ch == "\n":
                    # The pair was CRLF: an ordinary line ending after all.
                    self._emit(replaces=False)
                    continue
                # A bare carriage return: what came before it was a redraw.
                self._emit(replaces=True)
            if ch == "\r":
                self._held_cr = True
            elif ch == "\n":
                self._emit(replaces=False)
            else:
                self._pending += ch

    def close(self) -> None:
        """Flush whatever the stream ended on."""
        if self._pending or self._held_cr:
            self._emit(replaces=self._held_cr)
        self._held_cr = False

    def _emit(self, *, replaces: bool) -> None:
        line = self._pending
        self._pending = ""
        # An empty redraw is the carriage return that *precedes* a bar rather
        # than following one; it carries nothing to show.
        if not line and replaces:
            return
        self._on_line(line, replaces)


def run_powershell_stream(
    command: str,
    on_line: Callable[[str, bool], None],
    timeout: int = 30,
    encoding: str = "utf-8",
    component: str = "powershell",
) -> tuple[bool, str]:
    """Run a PowerShell command, handing each line over as it is printed.

    Same contract as :func:`run_powershell` — same argv, same hive rewrite, same
    timeout promise, same ``(success, output)`` answer — with the output
    delivered while the command is still running rather than only at the end.
    That is the whole point: a thirty-minute repair that reports nothing until it
    finishes is indistinguishable from one that has hung.

    ``on_line(text, replaces_previous)`` is called on a reader thread.
    ``replaces_previous`` is True when the line ended in a carriage return, i.e.
    a progress bar redrawing itself in place (see :class:`_LineSplitter`).

    stderr is merged into stdout so the order matches what a terminal shows: a
    warning printed between two progress lines belongs between them.
    """
    from fpstune.utils.debug import debug_powershell
    from fpstune.utils.winapi.session import redirect_hkcu

    if sys.platform != "win32":
        return False, "PowerShell is only available on Windows"

    command = redirect_hkcu(command)

    try:
        process = subprocess.Popen(
            _powershell_argv(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[unused-ignore]
        )
    except FileNotFoundError:
        error = "PowerShell executable not found"
        debug_powershell(command, error, False, component)
        return False, error
    except Exception as e:
        error = f"PowerShell execution error: {e}"
        debug_powershell(command, error, False, component)
        return False, error

    collected: list[str] = []

    def _record(line: str, replaces: bool) -> None:
        if replaces and collected:
            collected[-1] = line
        else:
            collected.append(line)
        on_line(line, replaces)

    def _pump() -> None:
        splitter = _LineSplitter(_record)
        decoder = codecs.getincrementaldecoder(encoding)("replace")
        stream = process.stdout
        # Narrowed rather than cast: `read1` is what makes this incremental, and
        # it lives on the buffered reader Popen actually hands back, not on the
        # IO[bytes] the type stubs promise.
        if not isinstance(stream, io.BufferedReader):  # pragma: no cover
            return
        try:
            while True:
                # `read1` hands back whatever has arrived instead of waiting for
                # a full buffer, which is what makes a bar redrawn every few
                # seconds visible every few seconds.
                chunk = stream.read1(4096)
                if not chunk:
                    break
                splitter.feed(decoder.decode(chunk))
            splitter.feed(decoder.decode(b"", final=True))
            splitter.close()
        except Exception:  # pragma: no cover - the pipe died with the process
            pass

    # A daemon, because a grandchild holding the pipe keeps this read blocked
    # exactly as it kept `communicate` blocked; the caller must not wait on it.
    reader = threading.Thread(target=_pump, daemon=True, name="powershell-stream")
    reader.start()
    reader.join(timeout)

    if reader.is_alive():
        process.kill()
        error = f"PowerShell command timed out after {timeout}s"
        debug_powershell(command, error, False, component)
        return False, error

    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - EOF without exit
        process.kill()
        returncode = -1

    output = "\n".join(collected).strip()
    if returncode == 0:
        debug_powershell(command, output, True, component)
        return True, output

    message = output or f"PowerShell exit code: {returncode}"
    debug_powershell(command, message, False, component)
    return False, message


def run_powershell(
    command: str,
    timeout: int = 30,
    encoding: str = "utf-8",
    component: str = "powershell",
) -> tuple[bool, str]:
    """Run a PowerShell command and return (success, output).

    The timeout is a promise: this returns within it whatever the command
    started (see :func:`_reap_in_background`).

    Args:
        command: PowerShell command to execute.
        timeout: Maximum execution time in seconds.
        encoding: Output encoding (default: utf-8).
        component: Component name for debug logging.

    Returns:
        Tuple of (success: bool, output: str).
        On success, output contains stdout.
        On failure, output contains error message.
    """
    from fpstune.utils.debug import debug_powershell
    from fpstune.utils.winapi.session import redirect_hkcu

    if sys.platform != "win32":
        return False, "PowerShell is only available on Windows"

    # `HKCU:` means the person at the keyboard, not the elevated token's owner.
    # Rewritten here, in the one runner, so every shipped script — executors,
    # batches, hardware inventory — addresses the same hive the winreg
    # executor does (see winapi.session).
    command = redirect_hkcu(command)

    try:
        # Prefix command with UTF-8 encoding for international Windows
        utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        full_command = utf8_prefix + command

        process = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                full_command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=encoding,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[unused-ignore]
        )
    except FileNotFoundError:
        error = "PowerShell executable not found"
        debug_powershell(command, error, False, component)
        return False, error
    except Exception as e:
        error = f"PowerShell execution error: {e}"
        debug_powershell(command, error, False, component)
        return False, error

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        _reap_in_background(process)
        error = f"PowerShell command timed out after {timeout}s"
        debug_powershell(command, error, False, component)
        return False, error
    except Exception as e:
        process.kill()
        _reap_in_background(process)
        error = f"PowerShell execution error: {e}"
        debug_powershell(command, error, False, component)
        return False, error

    if process.returncode == 0:
        output = (stdout or "").strip()
        debug_powershell(command, output, True, component)
        return True, output

    error = (stderr or "").strip() or (stdout or "").strip()
    output = error or f"PowerShell exit code: {process.returncode}"
    debug_powershell(command, output, False, component)
    return False, output


# Common GUID constants used in Windows registry
# Pre-escaped for PowerShell usage
class RegistryGUIDs:
    """Common Windows registry GUIDs pre-escaped for PowerShell."""

    # Display adapter class GUID
    DISPLAY_ADAPTER = escape_guid("{4d36e968-e325-11ce-bfc1-08002be10318}")

    # Audio endpoint property GUIDs
    LOUDNESS_EQ_PROP = escape_guid("{fc52a749-4be9-4510-896e-966ba6525980},3")
    DEVICE_NAME_PROP = escape_guid("{a45c254e-df1c-4efd-8020-67d146a850e0},2")
