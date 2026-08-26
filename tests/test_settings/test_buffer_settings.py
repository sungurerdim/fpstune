"""The buffer settings' copy may not carry numbers no instrument produced.

The defect this file exists for: the copy promised "Maximum (1024)" — stale
from the era when 1024 was hardcoded. The code has derived the maximum from
the adapter's own ``NumericParameterMaxValue`` since the #45 fix (a Realtek
part reports 512, and the 1024 write was clamped and then failed verification
forever), but the promise kept shipping. A number shown to the user is either
something read from this machine or it is not shown (C11).
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.network import (
    create_receive_buffers_setting,
    create_transmit_buffers_setting,
)


@pytest.mark.parametrize(
    "factory", [create_receive_buffers_setting, create_transmit_buffers_setting]
)
class TestTheCopyClaimsNoNumberNothingRead:
    def test_no_1024_reaches_the_user(self, factory) -> None:
        setting = factory(5, "Ethernet")
        user_facing = " ".join(
            [
                setting.description,
                setting.current_impact,
                setting.recommended_impact,
                setting.effect,
                *setting.value_hints.values(),
            ]
        )
        assert "1024" not in user_facing

    def test_the_maximum_is_named_as_the_adapters_own(self, factory) -> None:
        setting = factory(5, "Ethernet")
        assert "adapter" in setting.recommended_impact.lower()

    def test_the_command_still_derives_the_maximum_from_the_driver(self, factory) -> None:
        setting = factory(5, "Ethernet")
        assert "NumericParameterMaxValue" in setting.apply_command
