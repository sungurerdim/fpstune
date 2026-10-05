"""PowerShell utility functions for safe command execution.

This module provides functions for safely escaping and constructing
PowerShell commands with user-provided or dynamic values.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from typing import Any

from fpstune.utils.process_watch import CHANGE, QUERY, StallPolicy, no_window_flags, run_watched
from fpstune.utils.system_tools import powershell_exe

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


def _powershell_argv(command: str) -> list[str]:
    """The argument vector both runners start, so they cannot drift apart."""
    # Prefix command with UTF-8 encoding for international Windows
    utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    return [
        powershell_exe(),
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
    policy: StallPolicy = CHANGE,
    encoding: str = "utf-8",
    component: str = "powershell",
) -> tuple[bool, str]:
    """Run a PowerShell command, handing each line over as it is printed.

    Same contract as :func:`run_powershell` — same argv, same hive rewrite, same
    stall rule, same ``(success, output)`` answer — with the output delivered
    while the command is still running rather than only at the end. A
    thirty-minute repair that reports nothing until it finishes is
    indistinguishable from one that has hung.

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
    collected: list[str] = []

    def _record(line: str, replaces: bool) -> None:
        if replaces and collected:
            collected[-1] = line
        else:
            collected.append(line)
        on_line(line, replaces)

    splitter = _LineSplitter(_record)
    try:
        result = run_watched(
            _powershell_argv(command),
            policy,
            on_text=splitter.feed,
            merge_stderr=True,
            encoding=encoding,
            creationflags=no_window_flags(),
        )
    except OSError as e:
        error = _start_error(e)
        debug_powershell(command, error, False, component)
        return False, error
    splitter.close()

    if result.timed_out:
        error = f"PowerShell command stopped: {result.reason}"
        debug_powershell(command, error, False, component)
        return False, error

    output = "\n".join(collected).strip()
    if result.returncode == 0:
        debug_powershell(command, output, True, component)
        return True, output

    message = output or f"PowerShell exit code: {result.returncode}"
    debug_powershell(command, message, False, component)
    return False, message


def run_powershell(
    command: str,
    policy: StallPolicy = QUERY,
    encoding: str = "utf-8",
    component: str = "powershell",
) -> tuple[bool, str]:
    """Run a PowerShell command and return (success, output).

    Runs until the command finishes or stops making progress — the stall rule in
    ``utils.process_watch``, which watches PowerShell and everything it starts.
    A long command that keeps working is never cut off; a stuck one ends with
    ``"PowerShell command stopped: no progress for ..."``.

    Args:
        command: PowerShell command to execute.
        policy: The named stall policy (``QUERY`` for reads, ``CHANGE`` for
            writes, ``SERVICING`` for DISM/SFC).
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
        result = run_watched(
            _powershell_argv(command),
            policy,
            encoding=encoding,
            creationflags=no_window_flags(),
        )
    except OSError as e:
        error = _start_error(e)
        debug_powershell(command, error, False, component)
        return False, error

    if result.timed_out:
        error = f"PowerShell command stopped: {result.reason}"
        debug_powershell(command, error, False, component)
        return False, error

    if result.returncode == 0:
        output = result.stdout.strip()
        debug_powershell(command, output, True, component)
        return True, output

    error = result.stderr.strip() or result.stdout.strip()
    output = error or f"PowerShell exit code: {result.returncode}"
    debug_powershell(command, output, False, component)
    return False, output


def _start_error(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "PowerShell executable not found"
    return f"PowerShell execution error: {exc}"
