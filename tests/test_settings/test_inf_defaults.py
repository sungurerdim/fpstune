"""A device's driver default is what its installed INF section writes, not any MSI line in the file.

The failure these guard: a reset that restores the wrong number. Real INFs carry
several MSI sections (a Realtek one has ``MSI.00`` writing 0 beside ``MSI.16``
writing 1), so grepping the file for ``MSISupported`` answers for the wrong
device. Every fixture below is modelled on an INF measured on a real machine
(2026-10-06): the Realtek 2.5GbE one is UTF-16 with ``Include=pci.inf``, the
NVIDIA one is ANSI and names its flags and value through ``%strings%``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpstune.settings import inf_defaults
from fpstune.settings.inf_defaults import (
    InfUnresolved,
    InterruptDefaults,
    decode_inf,
    interrupt_defaults,
    interrupt_defaults_from_inf,
    split_fields,
)

MSI = r'"Interrupt Management\MessageSignaledInterruptProperties"'

PCI_INF = """\
[Version]
Signature="$Windows NT$"

[PciIoSpaceNotRequired.HW]
AddReg=PciIoSpaceNotRequired.AddReg

[PciIoSpaceNotRequired.AddReg]
HKR,,PciIoSpaceNotRequired,0x00010001,1
"""

# UTF-16 with a BOM, like oem76.inf: two install sections, five MSI AddReg sections.
REALTEK_INF = f"""\
[Version]
Signature="$Windows NT$"

[RTL8125BG.ndi.NT]
Characteristics = 0x84
AddReg = ndi.reg

[RTL8125BG.ndi.NT.HW]
Include = pci.inf
Needs   = PciIoSpaceNotRequired.HW
AddReg  = MSI.16.AddReg

[RTL8168.ndi.NT]
Characteristics = 0x84

[RTL8168.ndi.NT.HW]
AddReg = MSI.00.AddReg

[MSI.00.AddReg]
HKR, {MSI}, MSISupported, 0x00010001, 0

[MSI.01.AddReg]
HKR, {MSI}, MSISupported, 0x00010001, 1
HKR, {MSI}, MessageNumberLimit, 0x00010001, 1

[MSI.16.AddReg]
HKR, {MSI}, MSISupported, 0x00010001, 1
HKR, {MSI}, MessageNumberLimit, 0x00010001, 16
"""

# ANSI, like oem9.inf: values through [Strings], a comment-laden multi-line AddReg list.
NVIDIA_INF = f"""\
; NVIDIA display driver (fixture)
[Version]
Signature="$Windows NT$"

[Section057]
CopyFiles = nv_copy ; not read

[Section057.HW]
AddReg = nv_other_addreg, \\
         nv_msiSupport_addreg
AddReg = nv_late_addreg

[nv_other_addreg]
HKR,,NVRegistrySetting,%REG_DWORD%,3

[nv_msiSupport_addreg]
HKR,{MSI},MSISupported,%REG_DWORD%,%MSI_ON%
HKR,{MSI},MessageNumberLimit,%REG_DWORD%,1

[nv_late_addreg]
HKR,,SomethingElse,%REG_SZ%,"a;b"

[Strings]
REG_DWORD = 0x00010001
REG_SZ    = 0x00000000
MSI_ON    = 1
"""

NO_MSI_INF = """\
[Version]
Signature="$Windows NT$"

[Quiet.ndi.NT]
AddReg = ndi.reg

[Quiet.ndi.NT.HW]
AddReg = Quiet.hw.reg

[Quiet.hw.reg]
HKR,,SomeOtherValue,0x00010001,7

[Bare.ndi.NT]
AddReg = ndi.reg
"""


def write_inf(directory: Path, name: str, text: str, encoding: str) -> None:
    data = text.encode(encoding)
    if encoding == "utf-16-le":
        data = b"\xff\xfe" + data
    (directory / name).write_bytes(data)


@pytest.fixture
def inf_dir(tmp_path: Path) -> Path:
    write_inf(tmp_path, "pci.inf", PCI_INF, "utf-16-le")
    write_inf(tmp_path, "oem76.inf", REALTEK_INF, "utf-16-le")
    write_inf(tmp_path, "oem9.inf", NVIDIA_INF, "cp1252")
    write_inf(tmp_path, "quiet.inf", NO_MSI_INF, "cp1252")
    return tmp_path


def read(inf_dir: Path, name: str, section: str, ext: str = "") -> InterruptDefaults:
    return interrupt_defaults_from_inf(name, section, ext, inf_dir)


class TestTheInstalledSectionDecidesNotTheFile:
    def test_utf16_inf_resolves_the_bound_sections_msi_list_not_the_decoy(
        self, inf_dir: Path
    ) -> None:
        """MSI.00 (0) and MSI.01 sit in the same file; the bound section names MSI.16."""
        assert read(inf_dir, "oem76.inf", "RTL8125BG.ndi.NT") == InterruptDefaults(1, 16)

    def test_the_other_install_section_of_the_same_file_gets_its_own_answer(
        self, inf_dir: Path
    ) -> None:
        assert read(inf_dir, "oem76.inf", "RTL8168.ndi.NT") == InterruptDefaults(0, None)

    def test_ansi_inf_resolves_strings_and_multi_line_addreg_lists(self, inf_dir: Path) -> None:
        """Flags and value come from [Strings]; the list is split across two lines and a
        backslash continuation, and a later AddReg= line appends rather than replaces."""
        assert read(inf_dir, "oem9.inf", "Section057") == InterruptDefaults(1, 1)

    def test_a_semicolon_inside_quotes_is_not_a_comment(self) -> None:
        line = 'HKR,,Name,0x0,"a;b" ; trailing comment'
        assert inf_defaults._strip_comment(line) == 'HKR,,Name,0x0,"a;b" '


class TestAbsenceIsAnAnswer:
    def test_a_hardware_section_without_an_msi_line_leaves_both_unset(self, inf_dir: Path) -> None:
        """Reset then deletes the value; it must not invent 0 or 1."""
        assert read(inf_dir, "quiet.inf", "Quiet.ndi.NT") == InterruptDefaults(None, None)

    def test_an_install_section_with_no_hardware_section_leaves_both_unset(
        self, inf_dir: Path
    ) -> None:
        assert read(inf_dir, "quiet.inf", "Bare.ndi.NT") == InterruptDefaults(None, None)


class TestIncludeAndNeeds:
    def test_a_needs_section_in_the_included_inf_supplies_the_line(self, tmp_path: Path) -> None:
        write_inf(
            tmp_path,
            "system.inf",
            f"[Gen.HW]\nAddReg=Gen.msi\n[Gen.msi]\nHKR,{MSI},MSISupported,0x10001,1\n",
            "utf-16-le",
        )
        write_inf(
            tmp_path,
            "vendor.inf",
            "[Dev]\nAddReg=x\n[Dev.HW]\nInclude=system.inf\nNeeds=Gen.HW\n",
            "cp1252",
        )
        assert read(tmp_path, "vendor.inf", "Dev") == InterruptDefaults(1, None)

    def test_the_drivers_own_line_wins_over_a_needed_one(self, tmp_path: Path) -> None:
        write_inf(
            tmp_path,
            "system.inf",
            f"[Gen.HW]\nAddReg=Gen.msi\n[Gen.msi]\nHKR,{MSI},MSISupported,0x10001,1\n",
            "cp1252",
        )
        write_inf(
            tmp_path,
            "vendor.inf",
            f"[Dev]\n[Dev.HW]\nInclude=system.inf\nNeeds=Gen.HW\nAddReg=Own\n"
            f"[Own]\nHKR,{MSI},MSISupported,0x10001,0\n",
            "cp1252",
        )
        assert read(tmp_path, "vendor.inf", "Dev").msi_supported == 0

    def test_a_decorated_needs_section_is_preferred(self, tmp_path: Path) -> None:
        write_inf(
            tmp_path,
            "system.inf",
            f"[Gen.HW]\nAddReg=Plain\n[Gen.NTamd64.HW]\nAddReg=Dec\n"
            f"[Plain]\nHKR,{MSI},MSISupported,0x10001,0\n"
            f"[Dec]\nHKR,{MSI},MSISupported,0x10001,1\n",
            "cp1252",
        )
        write_inf(
            tmp_path,
            "vendor.inf",
            "[Dev.NTamd64]\n[Dev.NTamd64.HW]\nInclude=system.inf\nNeeds=Gen.HW\n",
            "cp1252",
        )
        assert read(tmp_path, "vendor.inf", "Dev", ".NTamd64").msi_supported == 1


class TestDecoration:
    @pytest.fixture
    def decorated(self, tmp_path: Path) -> Path:
        write_inf(
            tmp_path,
            "d.inf",
            f"[Sec.NTamd64]\n[Sec.NTamd64.HW]\nAddReg=Amd\n[Sec.HW]\nAddReg=Plain\n"
            f"[Amd]\nHKR,{MSI},MSISupported,0x10001,1\n"
            f"[Plain]\nHKR,{MSI},MSISupported,0x10001,0\n"
            "[Only]\n[Only.HW]\nAddReg=Plain\n",
            "cp1252",
        )
        return tmp_path

    def test_the_decorated_hardware_section_is_the_installed_one(self, decorated: Path) -> None:
        assert read(decorated, "d.inf", "Sec", ".NTamd64").msi_supported == 1

    def test_an_undecorated_section_is_found_when_no_decorated_one_exists(
        self, decorated: Path
    ) -> None:
        assert read(decorated, "d.inf", "Only", ".NTamd64").msi_supported == 0


class TestAddRegFlags:
    def _single(self, tmp_path: Path, lines: str) -> InterruptDefaults:
        write_inf(tmp_path, "f.inf", f"[S]\n[S.HW]\nAddReg=A\n[A]\n{lines}\n", "cp1252")
        return read(tmp_path, "f.inf", "S")

    def test_a_delete_flag_unsets_an_earlier_value(self, tmp_path: Path) -> None:
        lines = f"HKR,{MSI},MSISupported,0x10001,1\nHKR,{MSI},MSISupported,0x4,0"
        assert self._single(tmp_path, lines).msi_supported is None

    def test_noclobber_keeps_the_first_value(self, tmp_path: Path) -> None:
        lines = f"HKR,{MSI},MSISupported,0x10001,1\nHKR,{MSI},MSISupported,0x10003,0"
        assert self._single(tmp_path, lines).msi_supported == 1

    def test_a_key_only_line_writes_no_value(self, tmp_path: Path) -> None:
        assert self._single(tmp_path, f"HKR,{MSI},MSISupported,0x10,").msi_supported is None

    def test_a_decimal_value_with_a_leading_zero_is_read_as_decimal(self, tmp_path: Path) -> None:
        lines = f"HKR,{MSI},MessageNumberLimit,0x10001,016"
        assert self._single(tmp_path, lines).message_number_limit == 16

    def test_another_hive_root_is_not_the_device_key(self, tmp_path: Path) -> None:
        lines = f"HKLM,{MSI},MSISupported,0x10001,1"
        assert self._single(tmp_path, lines).msi_supported is None


class TestWhatCannotBeResolvedIsNotGuessed:
    def test_a_missing_inf_file(self, inf_dir: Path) -> None:
        with pytest.raises(InfUnresolved, match="cannot read"):
            read(inf_dir, "oem999.inf", "Anything")

    def test_an_install_section_the_inf_does_not_have(self, inf_dir: Path) -> None:
        with pytest.raises(InfUnresolved, match="install section"):
            read(inf_dir, "oem76.inf", "NotThere")

    def test_an_included_inf_that_is_not_installed(self, tmp_path: Path) -> None:
        write_inf(tmp_path, "v.inf", "[D]\n[D.HW]\nInclude=gone.inf\nNeeds=X.HW\n", "cp1252")
        with pytest.raises(InfUnresolved, match="cannot read"):
            read(tmp_path, "v.inf", "D")

    def test_a_needs_section_no_included_inf_has(self, tmp_path: Path) -> None:
        write_inf(tmp_path, "s.inf", "[Other.HW]\n", "cp1252")
        write_inf(tmp_path, "v.inf", "[D]\n[D.HW]\nInclude=s.inf\nNeeds=X.HW\n", "cp1252")
        with pytest.raises(InfUnresolved, match="Needs=X.HW"):
            read(tmp_path, "v.inf", "D")

    def test_an_addreg_section_the_inf_does_not_have(self, tmp_path: Path) -> None:
        write_inf(tmp_path, "v.inf", "[D]\n[D.HW]\nAddReg=Missing\n", "cp1252")
        with pytest.raises(InfUnresolved, match=r"\[missing\]"):
            read(tmp_path, "v.inf", "D")

    def test_a_value_that_is_not_a_number(self, tmp_path: Path) -> None:
        write_inf(
            tmp_path,
            "v.inf",
            f"[D]\n[D.HW]\nAddReg=A\n[A]\nHKR,{MSI},MSISupported,0x10001,%UNDEFINED%\n",
            "cp1252",
        )
        with pytest.raises(InfUnresolved, match="not a number"):
            read(tmp_path, "v.inf", "D")

    def test_an_msi_value_that_is_not_a_dword(self, tmp_path: Path) -> None:
        write_inf(
            tmp_path,
            "v.inf",
            f'[D]\n[D.HW]\nAddReg=A\n[A]\nHKR,{MSI},MSISupported,0x0,"1"\n',
            "cp1252",
        )
        with pytest.raises(InfUnresolved, match="not as a DWORD"):
            read(tmp_path, "v.inf", "D")


class TestTextHandling:
    def test_encodings_are_told_apart_by_their_bom(self) -> None:
        text = '[Strings]\nName = "café"\n'
        assert decode_inf(b"\xff\xfe" + text.encode("utf-16-le")) == text
        assert decode_inf(b"\xfe\xff" + text.encode("utf-16-be")) == text
        assert decode_inf(b"\xef\xbb\xbf" + text.encode("utf-8")) == text
        assert decode_inf(text.encode("cp1252")) == text

    def test_fields_split_on_commas_outside_quotes_only(self) -> None:
        assert split_fields('HKR, "a,b", Name,, "say ""hi"""') == [
            "HKR",
            "a,b",
            "Name",
            "",
            'say "hi"',
        ]


class TestTheDeviceFacingEntryPoint:
    @pytest.fixture(autouse=True)
    def fresh_cache(self) -> None:
        inf_defaults.clear_cache()

    def test_a_derived_default_is_cached_per_instance_not_re_read(
        self, inf_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.utils.winapi import devnode

        calls: list[str] = []

        def fake_binding(instance_id: str) -> devnode.DriverInf:
            calls.append(instance_id)
            return devnode.DriverInf("oem76.inf", "RTL8125BG.ndi.NT", "")

        monkeypatch.setattr(devnode, "driver_inf", fake_binding)
        monkeypatch.setattr(inf_defaults, "_inf_dir", lambda: inf_dir)
        first = interrupt_defaults(r"PCI\VEN_10EC&DEV_8125\1")
        second = interrupt_defaults(r"PCI\VEN_10EC&DEV_8125\1")
        assert first == second == InterruptDefaults(1, 16)
        assert calls == [r"PCI\VEN_10EC&DEV_8125\1"]

    def test_a_device_with_no_inf_binding_has_no_derivable_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.utils.winapi import devnode

        monkeypatch.setattr(devnode, "driver_inf", lambda _id: None)
        assert interrupt_defaults(r"ROOT\NOTHING\0") is None

    def test_an_unreadable_inf_is_none_and_is_retried_not_remembered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.utils.winapi import devnode

        monkeypatch.setattr(
            devnode, "driver_inf", lambda _id: devnode.DriverInf("oem1.inf", "S", "")
        )
        monkeypatch.setattr(inf_defaults, "_inf_dir", lambda: tmp_path)
        assert interrupt_defaults(r"PCI\X\1") is None
        write_inf(
            tmp_path,
            "oem1.inf",
            f"[S]\n[S.HW]\nAddReg=A\n[A]\nHKR,{MSI},MSISupported,0x10001,1\n",
            "cp1252",
        )
        assert interrupt_defaults(r"PCI\X\1") == InterruptDefaults(1, None)
