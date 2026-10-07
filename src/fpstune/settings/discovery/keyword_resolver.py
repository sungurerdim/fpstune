"""One resolver for a network adapter's advanced properties.

A driver publishes each advanced property under a ``RegistryKeyword``: the name its
INF declares, which no Windows language changes. The text beside it —
``DisplayName``, the label the control panel shows — is translated, so a search
that reaches for it finds the property on an English machine and silently misses
it on a Turkish or German one. This module is the only place that knows which
keywords name which concept, and it never reads a display name.

Drivers spell the same concept differently: the standardised NDIS keyword carries
a ``*`` (Intel ``*EEE``) where a vendor keyword is bare (Realtek ``EEE``,
Broadcom ``EEEControl``). A concept therefore lists every spelling it is known
under, preferred first, and may add a *stem* for a vendor family whose keyword
varies around a fixed core (``...APSD...``). Both halves match the keyword only.

Whether a keyword is found is half the question. The other half is whether the
driver accepts the value fpstune wants to write: an enum property publishes
``ValidRegistryValues``, a numeric one ``NumericParameterMinValue`` /
``NumericParameterMaxValue``. A value outside what the driver itself publishes is
refused here instead of being written and misread (C1, C10) — the same answer in
Python for discovery and in the PowerShell the apply command runs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from fpstune.settings.applicability import NOT_SUPPORTED

# A keyword lands inside a single-quoted PowerShell string: only the characters a
# driver INF actually uses may reach one, so a hostile or malformed spelling can
# never close the quote.
_SPELLING = re.compile(r"^\*?[A-Za-z0-9_]+$")
_STEM = re.compile(r"^[A-Za-z0-9_]+$")


class AdapterProperty(NamedTuple):
    """What one adapter's driver publishes about one advanced property.

    ``valid`` is the enum's own list (``ValidRegistryValues``, as the driver prints
    the numbers); ``minimum`` / ``maximum`` are the numeric bounds. A property that
    publishes neither accepts what the driver accepts, which is not knowable here.
    """

    keyword: str
    valid: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class KeywordConcept:
    """One thing a driver can expose, and every ``RegistryKeyword`` it is known by."""

    name: str
    spellings: tuple[str, ...] = ()
    stems: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.spellings and not self.stems:
            raise ValueError(f"concept {self.name!r} names no keyword")
        for spelling in self.spellings:
            if not _SPELLING.match(spelling):
                raise ValueError(f"concept {self.name!r}: {spelling!r} is not a keyword")
        for stem in self.stems:
            if not _STEM.match(stem):
                raise ValueError(f"concept {self.name!r}: {stem!r} is not a keyword stem")

    def matches(self, keyword: str) -> bool:
        """Whether ``keyword`` (as the driver spells it, any case) names this concept."""
        wanted = keyword.strip().lower()
        if wanted in {spelling.lower() for spelling in self.spellings}:
            return True
        return any(re.search(stem, wanted, re.IGNORECASE) for stem in self.stems)

    # --- PowerShell, generated from the same table the Python side reads -------

    def ps_spellings(self) -> str:
        """The listed spellings as a PowerShell argument list: ``'*EEE','EEE'``."""
        return ",".join(f"'{spelling}'" for spelling in self.spellings)

    def ps_stems(self) -> str:
        """The stems as one pattern over the keyword: ``APSD`` or ``A|B``."""
        return "|".join(self.stems)

    def ps_select(self, target: str = "$prop") -> str:
        """PowerShell leaving the adapter's property for this concept in ``target``.

        Chosen out of the adapter's own property list, never by asking for a
        keyword the driver may not have: that raises a terminating CIM error.
        Listed spellings are tried in their listed order and win over a stem hit,
        which is the order the scan's snapshot reads them in — so detect and apply
        meet on one property even when a driver publishes two spellings. Two stem
        hits are broken by name. ``target`` is ``$null`` when the driver does not
        expose the concept.
        """
        script = (
            "$all = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            f"-AllProperties -ErrorAction SilentlyContinue; {target} = $null; "
        )
        if self.spellings:
            script += (
                f"foreach ($kw in @({self.ps_spellings()})) {{ "
                f"{target} = $all | Where-Object {{ $_.RegistryKeyword -eq $kw }} "
                "| Select-Object -First 1; "
                f"if ({target}) {{ break }} }}; "
            )
        if self.stems:
            script += (
                f"if (-not {target}) {{ {target} = $all "
                f"| Where-Object {{ $_.RegistryKeyword -match '{self.ps_stems()}' }} "
                "| Sort-Object { $_.RegistryKeyword.ToLowerInvariant() } "
                "| Select-Object -First 1 }; "
            )
        return script

    def ps_detect(self, result: str = "[int](@($prop.RegistryValue)[0])") -> str:
        """A detect command: ``result`` for the found property, else ``not_supported``."""
        return f"{self.ps_select()}if ($prop) {{ {result} }} else {{ '{NOT_SUPPORTED}' }}"

    def ps_apply(self, label: str) -> str:
        """An apply command writing ``%value%`` to the property this concept finds.

        The number is checked against what the driver itself publishes before it
        is written: its enum list when it has one, its numeric bounds otherwise. A
        refusal is an ``error:`` line quoting the driver's own list, so it reads
        back as a failed apply rather than a write the hardware misreads.
        ``label`` names the setting inside that message.
        """
        refusal = f"'error: this driver does not accept {label} value ' + $want + "
        return (
            "try { " + self.ps_select() + f"if (-not $prop) {{ '{NOT_SUPPORTED}' }} else {{ "
            "$want = [int]%value%; "
            # `@($null)` has one element, so an unpublished list is filtered, not counted.
            "$valid = @($prop.ValidRegistryValues "
            "| Where-Object { $null -ne $_ -and [string]$_ -ne '' }); "
            "$lo = $prop.NumericParameterMinValue; $hi = $prop.NumericParameterMaxValue; "
            "if ($valid.Count -gt 0 -and -not ($valid -contains [string]$want)) { "
            + refusal
            + "'; its own list is ' + ($valid -join ',') "
            "} elseif ($valid.Count -eq 0 -and $null -ne $hi -and $hi -gt $lo "
            "-and ($want -lt $lo -or $want -gt $hi)) { "
            + refusal
            + "'; its own range is ' + $lo + '..' + $hi "
            "} else { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% -NoRestart "
            "-RegistryKeyword $prop.RegistryKeyword -RegistryValue $want -ErrorAction Stop; "
            "'ok' } } "
            "} catch { 'error:' + $_.Exception.Message }"
        )


CONCEPTS: dict[str, KeywordConcept] = {
    concept.name: concept
    for concept in (
        KeywordConcept("interrupt_moderation", ("*InterruptModeration", "InterruptModeration")),
        KeywordConcept("flow_control", ("*FlowControl", "FlowControl")),
        # Intel publishes *EEE, Realtek EEE, Broadcom EEEControl.
        KeywordConcept("eee", ("*EEE", "EEE", "EEEControl", "EnergyEfficientEthernet")),
        # Intel publishes *AdvancedEEE, Realtek AdvancedEEE.
        KeywordConcept("advanced_eee", ("*AdvancedEEE", "AdvancedEEE")),
        KeywordConcept("roaming_aggressiveness", ("*RoamAggressiveness", "RoamAggressiveness")),
        # Intel's own spelling first; any other vendor's carries the stem.
        KeywordConcept("uapsd", ("uAPSDSupport",), ("APSD",)),
        KeywordConcept("throughput_booster", stems=("ThroughputBoost",)),
    )
}


def concept(name: str) -> KeywordConcept:
    """The concept called ``name``; an unknown name is a bug in the definition."""
    try:
        return CONCEPTS[name]
    except KeyError:
        raise KeyError(f"no keyword concept named {name!r}") from None


def find(
    concept_: KeywordConcept, properties: Mapping[str, AdapterProperty]
) -> AdapterProperty | None:
    """The adapter's property for ``concept_``, or ``None`` when it publishes none.

    ``properties`` is the adapter's own table, ``{lowercase keyword: property}``.
    A listed spelling beats a stem hit, and listed spellings win in their listed
    order, so the answer does not depend on how the driver happens to order its
    table.
    """
    for spelling in concept_.spellings:
        found = properties.get(spelling.lower())
        if found is not None:
            return found
    for key in sorted(properties):
        if concept_.matches(key):
            return properties[key]
    return None


def _as_int(text: object) -> int | None:
    try:
        return int(str(text).strip())
    except ValueError:
        return None


def accepts(prop: AdapterProperty, value: int) -> bool:
    """Whether the driver's own list or range allows ``value``.

    An enum list is the whole truth when the driver publishes one. Otherwise a
    numeric range decides, but only a *real* range: ``NumericParameterMaxValue``
    reads 0 on properties that are not numeric at all, and treating that as "only 0
    is accepted" would refuse every value the driver takes. A property that
    publishes neither list nor range gives nothing to contradict.
    """
    if prop.valid:
        return any(_as_int(item) == value for item in prop.valid)
    if prop.maximum is not None and prop.maximum > (prop.minimum or 0):
        low = prop.minimum or 0
        return low <= value <= prop.maximum
    return True


@dataclass(frozen=True)
class Resolution:
    """The outcome of asking one adapter for one concept.

    ``keyword`` is the driver's own spelling, or ``None`` when it publishes
    nothing for the concept. ``refused`` holds the wanted values its own list or
    range rejects.
    """

    keyword: str | None
    refused: tuple[int, ...] = ()

    @property
    def reading(self) -> str:
        """The driver's spelling, or the ``ABSENT_READINGS`` sentinel.

        Absent and refused read alike: either way there is nothing on this
        adapter fpstune can write (C10).
        """
        if self.keyword is None or self.refused:
            return NOT_SUPPORTED
        return self.keyword


def resolve(
    concept_: KeywordConcept,
    properties: Mapping[str, AdapterProperty],
    values: Iterable[int],
) -> Resolution:
    """Find ``concept_`` on one adapter and check ``values`` against its driver."""
    found = find(concept_, properties)
    if found is None:
        return Resolution(None)
    return Resolution(
        found.keyword, tuple(v for v in dict.fromkeys(values) if not accepts(found, v))
    )
