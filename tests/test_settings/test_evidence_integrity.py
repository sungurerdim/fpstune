"""Evidence is a claim too: a source, a measured-sized claim, and risk copy.

A9's failure modes were all one shape: the row's label asserted more than the row
could support. These gates make the label mechanical:

* a `proven`/`likely` row names at least one source or a named fact (the domain's
  own default is a fact, not a fake URL);
* an `essential` row is `proven` — the conservative preset is proven-only;
* a numeric latency claim of 20 ms or more is not made without a measurement;
* an `experimental` row says "experimental" in the copy the user reads.
"""

from __future__ import annotations

from fpstune.settings.base import SettingScope
from tests.test_settings.dynamic_rows import all_settings


def test_proven_and_likely_rows_name_a_source() -> None:
    missing = sorted(
        setting.id
        for setting in all_settings()
        if setting.evidence_level in {"proven", "likely"} and not setting.sources
    )
    assert not missing, "rows claiming evidence with no source or named fact: " + ", ".join(missing)


def test_essential_is_proven_only() -> None:
    offenders = sorted(
        setting.id
        for setting in all_settings()
        if setting.scope is SettingScope.ESSENTIAL and setting.evidence_level != "proven"
    )
    assert not offenders, "essential preset rows that are not proven: " + ", ".join(offenders)


def test_no_large_unmeasured_latency_claim() -> None:
    offenders: list[str] = []
    for setting in all_settings():
        value = setting.impact_scores.get("latency_ms")
        if isinstance(value, int | float) and value <= -20:
            offenders.append(f"{setting.id}={value}")
    assert not offenders, "a >=20 ms latency claim needs a measurement: " + ", ".join(offenders)


def test_an_experimental_row_has_a_risk_warning() -> None:
    """The risk is the inline copy the row shows; a bare `experimental` tag is not enough."""
    offenders = sorted(
        setting.id
        for setting in all_settings()
        if setting.evidence_level == "experimental"
        and not (setting.risk_warning and setting.risk_warning.strip().endswith("."))
    )
    assert not offenders, "experimental rows without risk copy: " + ", ".join(offenders)
