"""PowerShell utility functions for safe command execution.

This module provides functions for safely escaping and constructing
PowerShell commands with user-provided or dynamic values.
"""

from __future__ import annotations

import re
import subprocess
import sys
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


def run_powershell(
    command: str,
    timeout: int = 30,
    encoding: str = "utf-8",
    component: str = "powershell",
) -> tuple[bool, str]:
    """Run a PowerShell command and return (success, output).

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

    if sys.platform != "win32":
        return False, "PowerShell is only available on Windows"

    try:
        # Prefix command with UTF-8 encoding for international Windows
        utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        full_command = utf8_prefix + command

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                full_command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding=encoding,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,  # type: ignore[unused-ignore]
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            debug_powershell(command, output, True, component)
            return True, output
        else:
            error = result.stderr.strip() or result.stdout.strip()
            output = error or f"PowerShell exit code: {result.returncode}"
            debug_powershell(command, output, False, component)
            return False, output

    except subprocess.TimeoutExpired:
        error = f"PowerShell command timed out after {timeout}s"
        debug_powershell(command, error, False, component)
        return False, error
    except FileNotFoundError:
        error = "PowerShell executable not found"
        debug_powershell(command, error, False, component)
        return False, error
    except Exception as e:
        error = f"PowerShell execution error: {e}"
        debug_powershell(command, error, False, component)
        return False, error


# Common GUID constants used in Windows registry
# Pre-escaped for PowerShell usage
class RegistryGUIDs:
    """Common Windows registry GUIDs pre-escaped for PowerShell."""

    # Display adapter class GUID
    DISPLAY_ADAPTER = escape_guid("{4d36e968-e325-11ce-bfc1-08002be10318}")

    # Audio endpoint property GUIDs
    LOUDNESS_EQ_PROP = escape_guid("{fc52a749-4be9-4510-896e-966ba6525980},3")
    DEVICE_NAME_PROP = escape_guid("{a45c254e-df1c-4efd-8020-67d146a850e0},2")
