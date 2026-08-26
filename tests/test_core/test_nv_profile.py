"""Tests for fpstune.core.nv_profile.

Tests cover pure logic: value maps, command argument builders, XML
generation, XML parsing (read_applied_settings), profile hashing,
and error paths.  All subprocess / filesystem mutations are mocked.
Windows-only code paths that require a live NVIDIA binary are skipped
on non-win32 platforms.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest

from fpstune.core.nv_profile import (
    SETTING_NAMES,
    NvApiSettings,
    NvidiaProfile,
    NvidiaProfileInspector,
)

# ---------------------------------------------------------------------------
# NvApiSettings constants
# ---------------------------------------------------------------------------


class TestNvApiSettingConstants:
    def test_power_management_mode_id(self) -> None:
        assert NvApiSettings.POWER_MANAGEMENT_MODE == 0x1057EB71

    def test_low_latency_mode_id(self) -> None:
        assert NvApiSettings.LOW_LATENCY_MODE == 0x00707011

    def test_threaded_optimization_id(self) -> None:
        assert NvApiSettings.THREADED_OPTIMIZATION == 0x00707010

    def test_vsync_mode_id(self) -> None:
        assert NvApiSettings.VSYNC_MODE == 0x00707018

    def test_frl_fps_id(self) -> None:
        assert NvApiSettings.FRL_FPS == 0x10835002

    def test_vrr_mode_id(self) -> None:
        assert NvApiSettings.VRR_MODE == 0x1194F158

    def test_bg_app_max_fps_id(self) -> None:
        assert NvApiSettings.BG_APP_MAX_FPS == 0x10835004

    def test_max_prerendered_frames_id(self) -> None:
        assert NvApiSettings.MAX_PRERENDERED_FRAMES == 0x00707008

    def test_vrr_app_override_id(self) -> None:
        assert NvApiSettings.VRR_APP_OVERRIDE == 0x10A879CF

    def test_ogl_thread_control_id(self) -> None:
        assert NvApiSettings.OGL_THREAD_CONTROL == 0x20C1221E

    def test_cuda_force_p2_id(self) -> None:
        assert NvApiSettings.CUDA_FORCE_P2 == 0x0070701C

    def test_aniso_sample_opt_id(self) -> None:
        assert NvApiSettings.ANISO_SAMPLE_OPT == 0x00707019

    def test_texture_lod_bias_id(self) -> None:
        assert NvApiSettings.TEXTURE_LOD_BIAS == 0x0070701B

    def test_power_optimal_value(self) -> None:
        assert NvApiSettings.POWER_OPTIMAL == 0x00000005

    def test_power_prefer_max_value(self) -> None:
        assert NvApiSettings.POWER_PREFER_MAX == 0x00000001

    def test_latency_ultra_value(self) -> None:
        assert NvApiSettings.LATENCY_ULTRA == 0x00000002


# ---------------------------------------------------------------------------
# SETTING_NAMES mapping
# ---------------------------------------------------------------------------


class TestSettingNames:
    def test_all_nvapi_ids_have_names(self) -> None:
        expected_ids = {
            NvApiSettings.POWER_MANAGEMENT_MODE,
            NvApiSettings.LOW_LATENCY_MODE,
            NvApiSettings.THREADED_OPTIMIZATION,
            NvApiSettings.VSYNC_MODE,
            NvApiSettings.SHADER_CACHE,
            NvApiSettings.TEXTURE_QUALITY,
            NvApiSettings.TRIPLE_BUFFER,
            NvApiSettings.ANISO_FILTER,
            NvApiSettings.AA_MODE,
            NvApiSettings.FRL_FPS,
            NvApiSettings.VRR_MODE,
            NvApiSettings.BG_APP_MAX_FPS,
            NvApiSettings.ANISO_SAMPLE_OPT,
            NvApiSettings.TEXTURE_LOD_BIAS,
            NvApiSettings.OGL_THREAD_CONTROL,
            NvApiSettings.CUDA_FORCE_P2,
            NvApiSettings.MAX_PRERENDERED_FRAMES,
            NvApiSettings.VRR_APP_OVERRIDE,
        }
        assert expected_ids == set(SETTING_NAMES.keys())

    def test_names_are_nonempty_strings(self) -> None:
        for setting_id, name in SETTING_NAMES.items():
            assert isinstance(name, str) and name, f"Empty name for setting 0x{setting_id:08X}"


# ---------------------------------------------------------------------------
# NvidiaProfile.to_settings_dict — value mapping
# ---------------------------------------------------------------------------


class TestNvidiaProfileToSettingsDict:
    """Verify every enum-style field maps to the correct NVAPI integer."""

    def _make(self, **kwargs: object) -> dict[int, int]:
        return NvidiaProfile(**kwargs).to_settings_dict()  # type: ignore[arg-type]

    # Power mode
    def test_power_mode_optimal(self) -> None:
        d = self._make(power_mode="optimal")
        assert d[NvApiSettings.POWER_MANAGEMENT_MODE] == NvApiSettings.POWER_OPTIMAL

    def test_power_mode_maximum(self) -> None:
        d = self._make(power_mode="maximum")
        assert d[NvApiSettings.POWER_MANAGEMENT_MODE] == NvApiSettings.POWER_PREFER_MAX

    def test_power_mode_adaptive(self) -> None:
        d = self._make(power_mode="adaptive")
        assert d[NvApiSettings.POWER_MANAGEMENT_MODE] == NvApiSettings.POWER_ADAPTIVE

    def test_power_mode_consistent(self) -> None:
        d = self._make(power_mode="consistent")
        assert d[NvApiSettings.POWER_MANAGEMENT_MODE] == NvApiSettings.POWER_CONSISTENT_PERFORMANCE

    def test_power_mode_unknown_falls_back_to_max(self) -> None:
        # dict.get default for unknown key is POWER_PREFER_MAX
        d = self._make(power_mode="turbo_ultra")
        assert d[NvApiSettings.POWER_MANAGEMENT_MODE] == NvApiSettings.POWER_PREFER_MAX

    # Low latency
    def test_low_latency_off(self) -> None:
        d = self._make(low_latency="off")
        assert d[NvApiSettings.LOW_LATENCY_MODE] == NvApiSettings.LATENCY_OFF

    def test_low_latency_on(self) -> None:
        d = self._make(low_latency="on")
        assert d[NvApiSettings.LOW_LATENCY_MODE] == NvApiSettings.LATENCY_ON

    def test_low_latency_ultra(self) -> None:
        d = self._make(low_latency="ultra")
        assert d[NvApiSettings.LOW_LATENCY_MODE] == NvApiSettings.LATENCY_ULTRA

    def test_low_latency_unknown_falls_back_to_ultra(self) -> None:
        d = self._make(low_latency="hyperspeed")
        assert d[NvApiSettings.LOW_LATENCY_MODE] == NvApiSettings.LATENCY_ULTRA

    # Threaded optimization
    def test_threaded_opt_auto(self) -> None:
        d = self._make(threaded_opt="auto")
        assert d[NvApiSettings.THREADED_OPTIMIZATION] == NvApiSettings.THREADED_AUTO

    def test_threaded_opt_on(self) -> None:
        d = self._make(threaded_opt="on")
        assert d[NvApiSettings.THREADED_OPTIMIZATION] == NvApiSettings.THREADED_ON

    def test_threaded_opt_off(self) -> None:
        d = self._make(threaded_opt="off")
        assert d[NvApiSettings.THREADED_OPTIMIZATION] == NvApiSettings.THREADED_OFF

    def test_threaded_opt_unknown_falls_back_to_on(self) -> None:
        d = self._make(threaded_opt="maybe")
        assert d[NvApiSettings.THREADED_OPTIMIZATION] == NvApiSettings.THREADED_ON

    # VSync
    def test_vsync_off(self) -> None:
        d = self._make(vsync="off")
        assert d[NvApiSettings.VSYNC_MODE] == NvApiSettings.VSYNC_OFF

    def test_vsync_on(self) -> None:
        d = self._make(vsync="on")
        assert d[NvApiSettings.VSYNC_MODE] == NvApiSettings.VSYNC_ON

    def test_vsync_adaptive(self) -> None:
        d = self._make(vsync="adaptive")
        assert d[NvApiSettings.VSYNC_MODE] == NvApiSettings.VSYNC_ADAPTIVE

    def test_vsync_unknown_falls_back_to_off(self) -> None:
        d = self._make(vsync="turbo")
        assert d[NvApiSettings.VSYNC_MODE] == NvApiSettings.VSYNC_OFF

    # Shader cache
    def test_shader_cache_on(self) -> None:
        d = self._make(shader_cache="on")
        assert d[NvApiSettings.SHADER_CACHE] == NvApiSettings.SHADER_CACHE_ON

    def test_shader_cache_off(self) -> None:
        d = self._make(shader_cache="off")
        assert d[NvApiSettings.SHADER_CACHE] == NvApiSettings.SHADER_CACHE_OFF

    # Texture quality
    def test_texture_quality_high_quality(self) -> None:
        d = self._make(texture_quality="high_quality")
        assert d[NvApiSettings.TEXTURE_QUALITY] == NvApiSettings.TEXTURE_HIGH_QUALITY

    def test_texture_quality_quality(self) -> None:
        d = self._make(texture_quality="quality")
        assert d[NvApiSettings.TEXTURE_QUALITY] == NvApiSettings.TEXTURE_QUALITY_DEFAULT

    def test_texture_quality_performance(self) -> None:
        d = self._make(texture_quality="performance")
        assert d[NvApiSettings.TEXTURE_QUALITY] == NvApiSettings.TEXTURE_PERFORMANCE

    def test_texture_quality_high_performance(self) -> None:
        d = self._make(texture_quality="high_performance")
        assert d[NvApiSettings.TEXTURE_QUALITY] == NvApiSettings.TEXTURE_HIGH_PERFORMANCE

    def test_texture_quality_unknown_falls_back_to_performance(self) -> None:
        d = self._make(texture_quality="ultra_blurry")
        assert d[NvApiSettings.TEXTURE_QUALITY] == NvApiSettings.TEXTURE_PERFORMANCE

    # Triple buffer
    def test_triple_buffer_off(self) -> None:
        d = self._make(triple_buffer="off")
        assert d[NvApiSettings.TRIPLE_BUFFER] == NvApiSettings.TRIPLE_BUFFER_OFF

    def test_triple_buffer_on(self) -> None:
        d = self._make(triple_buffer="on")
        assert d[NvApiSettings.TRIPLE_BUFFER] == NvApiSettings.TRIPLE_BUFFER_ON

    # FPS limit
    def test_fps_limit_zero_maps_to_off(self) -> None:
        d = self._make(fps_limit=0)
        assert d[NvApiSettings.FRL_FPS] == NvApiSettings.FRL_OFF

    def test_fps_limit_positive_stored_as_integer(self) -> None:
        d = self._make(fps_limit=165)
        assert d[NvApiSettings.FRL_FPS] == 165

    def test_fps_limit_30(self) -> None:
        d = self._make(fps_limit=30)
        assert d[NvApiSettings.FRL_FPS] == 30

    def test_fps_limit_500(self) -> None:
        d = self._make(fps_limit=500)
        assert d[NvApiSettings.FRL_FPS] == 500

    # VRR mode
    def test_vrr_mode_off(self) -> None:
        d = self._make(vrr_mode="off")
        assert d[NvApiSettings.VRR_MODE] == NvApiSettings.VRR_OFF

    def test_vrr_mode_on(self) -> None:
        d = self._make(vrr_mode="on")
        assert d[NvApiSettings.VRR_MODE] == NvApiSettings.VRR_ON

    def test_vrr_mode_fullscreen(self) -> None:
        d = self._make(vrr_mode="fullscreen")
        assert d[NvApiSettings.VRR_MODE] == NvApiSettings.VRR_FULLSCREEN

    # Background app FPS
    def test_bg_app_fps_zero_maps_to_off(self) -> None:
        d = self._make(bg_app_fps=0)
        assert d[NvApiSettings.BG_APP_MAX_FPS] == NvApiSettings.BG_APP_FPS_OFF

    def test_bg_app_fps_positive_stored_as_integer(self) -> None:
        d = self._make(bg_app_fps=30)
        assert d[NvApiSettings.BG_APP_MAX_FPS] == 30

    # Aniso sample opt
    def test_aniso_sample_opt_on(self) -> None:
        d = self._make(aniso_sample_opt="on")
        assert d[NvApiSettings.ANISO_SAMPLE_OPT] == NvApiSettings.ANISO_SAMPLE_OPT_ON

    def test_aniso_sample_opt_off(self) -> None:
        d = self._make(aniso_sample_opt="off")
        assert d[NvApiSettings.ANISO_SAMPLE_OPT] == NvApiSettings.ANISO_SAMPLE_OPT_OFF

    # Texture LOD bias
    def test_texture_lod_bias_clamp(self) -> None:
        d = self._make(texture_lod_bias="clamp")
        assert d[NvApiSettings.TEXTURE_LOD_BIAS] == NvApiSettings.TEXTURE_LOD_CLAMP

    def test_texture_lod_bias_allow(self) -> None:
        d = self._make(texture_lod_bias="allow")
        assert d[NvApiSettings.TEXTURE_LOD_BIAS] == NvApiSettings.TEXTURE_LOD_ALLOW

    # OGL thread control
    def test_ogl_thread_on(self) -> None:
        d = self._make(ogl_thread_opt="on")
        assert d[NvApiSettings.OGL_THREAD_CONTROL] == NvApiSettings.OGL_THREAD_ON

    def test_ogl_thread_off(self) -> None:
        d = self._make(ogl_thread_opt="off")
        assert d[NvApiSettings.OGL_THREAD_CONTROL] == NvApiSettings.OGL_THREAD_OFF

    def test_ogl_thread_auto(self) -> None:
        d = self._make(ogl_thread_opt="auto")
        assert d[NvApiSettings.OGL_THREAD_CONTROL] == NvApiSettings.OGL_THREAD_AUTO

    def test_ogl_thread_unknown_falls_back_to_on(self) -> None:
        d = self._make(ogl_thread_opt="fast")
        assert d[NvApiSettings.OGL_THREAD_CONTROL] == NvApiSettings.OGL_THREAD_ON

    # CUDA P2
    def test_cuda_force_p2_on(self) -> None:
        d = self._make(cuda_force_p2="on")
        assert d[NvApiSettings.CUDA_FORCE_P2] == NvApiSettings.CUDA_P2_ON

    def test_cuda_force_p2_off(self) -> None:
        d = self._make(cuda_force_p2="off")
        assert d[NvApiSettings.CUDA_FORCE_P2] == NvApiSettings.CUDA_P2_OFF

    # Max prerendered frames — clamped to 1-4
    def test_max_prerendered_clamped_min(self) -> None:
        d = self._make(max_prerendered=0)
        assert d[NvApiSettings.MAX_PRERENDERED_FRAMES] == 1

    def test_max_prerendered_clamped_max(self) -> None:
        d = self._make(max_prerendered=10)
        assert d[NvApiSettings.MAX_PRERENDERED_FRAMES] == 4

    def test_max_prerendered_valid_value(self) -> None:
        d = self._make(max_prerendered=2)
        assert d[NvApiSettings.MAX_PRERENDERED_FRAMES] == 2

    def test_max_prerendered_boundary_1(self) -> None:
        d = self._make(max_prerendered=1)
        assert d[NvApiSettings.MAX_PRERENDERED_FRAMES] == 1

    def test_max_prerendered_boundary_4(self) -> None:
        d = self._make(max_prerendered=4)
        assert d[NvApiSettings.MAX_PRERENDERED_FRAMES] == 4

    # VRR app override
    def test_vrr_app_override_driver_default(self) -> None:
        d = self._make(vrr_app_override="driver_default")
        assert d[NvApiSettings.VRR_APP_OVERRIDE] == NvApiSettings.VRR_APP_DRIVER

    def test_vrr_app_override_force_on(self) -> None:
        d = self._make(vrr_app_override="force_on")
        assert d[NvApiSettings.VRR_APP_OVERRIDE] == NvApiSettings.VRR_APP_ON

    def test_vrr_app_override_off(self) -> None:
        d = self._make(vrr_app_override="off")
        assert d[NvApiSettings.VRR_APP_OVERRIDE] == NvApiSettings.VRR_APP_OFF

    def test_vrr_app_override_unknown_falls_back_to_driver(self) -> None:
        d = self._make(vrr_app_override="random")
        assert d[NvApiSettings.VRR_APP_OVERRIDE] == NvApiSettings.VRR_APP_DRIVER

    def test_default_profile_has_all_expected_keys(self) -> None:
        d = NvidiaProfile().to_settings_dict()
        expected_keys = {
            NvApiSettings.POWER_MANAGEMENT_MODE,
            NvApiSettings.LOW_LATENCY_MODE,
            NvApiSettings.THREADED_OPTIMIZATION,
            NvApiSettings.VSYNC_MODE,
            NvApiSettings.SHADER_CACHE,
            NvApiSettings.TEXTURE_QUALITY,
            NvApiSettings.TRIPLE_BUFFER,
            NvApiSettings.FRL_FPS,
            NvApiSettings.VRR_MODE,
            NvApiSettings.BG_APP_MAX_FPS,
            NvApiSettings.ANISO_SAMPLE_OPT,
            NvApiSettings.TEXTURE_LOD_BIAS,
            NvApiSettings.OGL_THREAD_CONTROL,
            NvApiSettings.CUDA_FORCE_P2,
            NvApiSettings.MAX_PRERENDERED_FRAMES,
            NvApiSettings.VRR_APP_OVERRIDE,
        }
        assert expected_keys == set(d.keys())


# ---------------------------------------------------------------------------
# XML generation (generate_profile_xml)
# ---------------------------------------------------------------------------


class TestGenerateProfileXml:
    """generate_profile_xml is pure (no subprocess, no filesystem)."""

    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    def test_xml_declaration_present(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile())
        assert xml.startswith('<?xml version="1.0" encoding="utf-16"?>')

    def test_root_element_is_array_of_profile(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile())
        # Strip declaration before parsing
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        assert root.tag == "ArrayOfProfile"

    def test_profile_name_in_xml(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile(name="Base Profile"))
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        name_elem = root.find(".//ProfileName")
        assert name_elem is not None
        assert name_elem.text == "Base Profile"

    def test_settings_are_decimal_not_hex(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile())
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        for setting in root.findall(".//ProfileSetting"):
            sid = setting.find("SettingID")
            sval = setting.find("SettingValue")
            assert sid is not None and sval is not None
            # Must be parseable as decimal int
            int(sid.text or "")  # raises ValueError if hex/garbage
            int(sval.text or "")

    def test_global_profile_has_empty_executeables(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile(executables=None))
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        exec_elem = root.find(".//Executeables")
        assert exec_elem is not None
        assert len(list(exec_elem)) == 0

    def test_executables_added_to_xml(self, inspector: NvidiaProfileInspector) -> None:
        profile = NvidiaProfile(executables=["game.exe", "launcher.exe"])
        xml = inspector.generate_profile_xml(profile)
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        strings = [e.text for e in root.findall(".//Executeables/string")]
        assert strings == ["game.exe", "launcher.exe"]

    def test_setting_count_matches_to_settings_dict(
        self, inspector: NvidiaProfileInspector
    ) -> None:
        profile = NvidiaProfile()
        xml = inspector.generate_profile_xml(profile)
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        setting_elems = root.findall(".//ProfileSetting")
        assert len(setting_elems) == len(profile.to_settings_dict())

    def test_power_management_setting_id_in_xml(self, inspector: NvidiaProfileInspector) -> None:
        """Verify power management mode ID appears in generated XML as decimal."""
        xml = inspector.generate_profile_xml(NvidiaProfile(power_mode="maximum"))
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        ids = {int(e.text or "0") for e in root.findall(".//SettingID")}
        assert NvApiSettings.POWER_MANAGEMENT_MODE in ids

    def test_fps_limit_setting_value_in_xml(self, inspector: NvidiaProfileInspector) -> None:
        """fps_limit=144 should appear as the raw integer 144 in XML."""
        xml = inspector.generate_profile_xml(NvidiaProfile(fps_limit=144))
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        frl_id = str(NvApiSettings.FRL_FPS)
        for setting in root.findall(".//ProfileSetting"):
            sid = setting.find("SettingID")
            if sid is not None and sid.text == frl_id:
                val_elem = setting.find("SettingValue")
                assert val_elem is not None
                assert int(val_elem.text or "-1") == 144
                return
        pytest.fail("FRL_FPS setting not found in XML")

    def test_custom_profile_name(self, inspector: NvidiaProfileInspector) -> None:
        xml = inspector.generate_profile_xml(NvidiaProfile(name="CS2_Gaming"))
        body = xml.split("\n", 1)[1]
        root = ET.fromstring(body)
        assert root.find(".//ProfileName").text == "CS2_Gaming"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# NvidiaProfileInspector — is_installed, exe_path, list_saved_profiles
# ---------------------------------------------------------------------------


class TestNvidiaProfileInspectorFileOps:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    def test_is_installed_false_when_exe_absent(self, inspector: NvidiaProfileInspector) -> None:
        assert inspector.is_installed() is False

    def test_is_installed_true_when_exe_present(self, inspector: NvidiaProfileInspector) -> None:
        inspector.exe_path.parent.mkdir(parents=True, exist_ok=True)
        inspector.exe_path.touch()
        assert inspector.is_installed() is True

    def test_exe_path_ends_with_correct_name(self, inspector: NvidiaProfileInspector) -> None:
        assert inspector.exe_path.name == "nvidiaProfileInspector.exe"

    def test_list_saved_profiles_empty_initially(self, inspector: NvidiaProfileInspector) -> None:
        assert inspector.list_saved_profiles() == []

    def test_list_saved_profiles_returns_nip_files(self, inspector: NvidiaProfileInspector) -> None:
        profiles_dir = inspector.get_profiles_dir()
        (profiles_dir / "gaming.nip").write_text("x", encoding="utf-8")
        (profiles_dir / "notes.txt").write_text("y", encoding="utf-8")
        result = inspector.list_saved_profiles()
        names = {p.name for p in result}
        assert "gaming.nip" in names
        assert "notes.txt" not in names

    def test_get_profiles_dir_exists(self, inspector: NvidiaProfileInspector) -> None:
        d = inspector.get_profiles_dir()
        assert d.is_dir()


# ---------------------------------------------------------------------------
# save_profile
# ---------------------------------------------------------------------------


class TestSaveProfile:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    def test_save_profile_creates_nip_file(self, inspector: NvidiaProfileInspector) -> None:
        profile = NvidiaProfile(name="Base Profile")
        path = inspector.save_profile(profile)
        assert path.exists()
        assert path.suffix == ".nip"

    def test_save_profile_custom_filename(self, inspector: NvidiaProfileInspector) -> None:
        profile = NvidiaProfile(name="Base Profile")
        path = inspector.save_profile(profile, filename="custom_name")
        assert path.name == "custom_name.nip"

    def test_save_profile_default_filename_uses_profile_name(
        self, inspector: NvidiaProfileInspector
    ) -> None:
        profile = NvidiaProfile(name="MyGame")
        path = inspector.save_profile(profile)
        assert path.name == "MyGame.nip"

    def test_save_profile_content_is_valid_xml(self, inspector: NvidiaProfileInspector) -> None:
        profile = NvidiaProfile(name="TestProfile")
        path = inspector.save_profile(profile)
        with open(path, encoding="utf-16") as f:
            content = f.read()
        # Strip declaration and parse
        body = content.split("\n", 1)[1]
        root = ET.fromstring(body)
        assert root.tag == "ArrayOfProfile"

    def test_save_profile_written_as_utf16(self, inspector: NvidiaProfileInspector) -> None:
        profile = NvidiaProfile(name="EncTest")
        path = inspector.save_profile(profile)
        # UTF-16 files start with BOM (0xFF 0xFE or 0xFE 0xFF)
        raw = path.read_bytes()
        assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")


# ---------------------------------------------------------------------------
# read_applied_settings — XML parsing (pure filesystem, no subprocess)
# ---------------------------------------------------------------------------


def _build_nip_xml(settings: dict[int, int], profile_name: str = "fpstune_gaming") -> str:
    """Build a minimal NIP XML string with the given setting ID → value pairs."""
    root = ET.Element("ArrayOfProfile")
    profile_elem = ET.SubElement(root, "Profile")
    ET.SubElement(profile_elem, "ProfileName").text = profile_name
    ET.SubElement(profile_elem, "Executeables")
    settings_elem = ET.SubElement(profile_elem, "Settings")
    for sid, val in settings.items():
        s = ET.SubElement(settings_elem, "ProfileSetting")
        ET.SubElement(s, "SettingID").text = str(sid)
        ET.SubElement(s, "SettingValue").text = str(val)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-16"?>\n{body}'


class TestReadAppliedSettings:
    """read_applied_settings parses a saved .nip XML file — no subprocess."""

    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    def _write_profile(self, inspector: NvidiaProfileInspector, xml: str) -> None:
        path = inspector.get_profiles_dir() / "fpstune_gaming.nip"
        with open(path, "w", encoding="utf-16") as f:
            f.write(xml)

    def test_returns_none_when_no_profile_file(self, inspector: NvidiaProfileInspector) -> None:
        assert inspector.read_applied_settings() is None

    def test_reads_power_mode_optimal(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.POWER_MANAGEMENT_MODE: NvApiSettings.POWER_OPTIMAL})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["power_mode"] == "optimal"

    def test_reads_power_mode_maximum(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.POWER_MANAGEMENT_MODE: NvApiSettings.POWER_PREFER_MAX})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["power_mode"] == "maximum"

    def test_reads_low_latency_ultra(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.LOW_LATENCY_MODE: NvApiSettings.LATENCY_ULTRA})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["low_latency"] == "ultra"

    def test_reads_low_latency_off(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.LOW_LATENCY_MODE: NvApiSettings.LATENCY_OFF})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["low_latency"] == "off"

    def test_reads_threaded_opt_auto(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.THREADED_OPTIMIZATION: NvApiSettings.THREADED_AUTO})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["threaded_opt"] == "auto"

    def test_reads_vsync_off(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.VSYNC_MODE: NvApiSettings.VSYNC_OFF})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["vsync"] == "off"

    def test_reads_vsync_adaptive(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.VSYNC_MODE: NvApiSettings.VSYNC_ADAPTIVE})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["vsync"] == "adaptive"

    def test_reads_shader_cache_on(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.SHADER_CACHE: NvApiSettings.SHADER_CACHE_ON})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["shader_cache"] == "on"

    def test_reads_texture_quality_performance(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.TEXTURE_QUALITY: NvApiSettings.TEXTURE_PERFORMANCE})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["texture_quality"] == "performance"

    def test_reads_triple_buffer_off(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.TRIPLE_BUFFER: NvApiSettings.TRIPLE_BUFFER_OFF})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["triple_buffer"] == "off"

    def test_reads_fps_limit_as_integer(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.FRL_FPS: 165})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["fps_limit"] == 165

    def test_reads_fps_limit_zero(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.FRL_FPS: 0})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["fps_limit"] == 0

    def test_reads_vrr_mode_fullscreen(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.VRR_MODE: NvApiSettings.VRR_FULLSCREEN})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["vrr_mode"] == "fullscreen"

    def test_reads_bg_app_fps_as_integer(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.BG_APP_MAX_FPS: 30})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["bg_app_fps"] == 30

    def test_reads_aniso_sample_opt_on(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.ANISO_SAMPLE_OPT: NvApiSettings.ANISO_SAMPLE_OPT_ON})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["aniso_sample_opt"] == "on"

    def test_reads_texture_lod_bias_clamp(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.TEXTURE_LOD_BIAS: NvApiSettings.TEXTURE_LOD_CLAMP})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["texture_lod_bias"] == "clamp"

    def test_reads_ogl_thread_on(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.OGL_THREAD_CONTROL: NvApiSettings.OGL_THREAD_ON})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["ogl_thread_opt"] == "on"

    def test_reads_cuda_force_p2_on(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.CUDA_FORCE_P2: NvApiSettings.CUDA_P2_ON})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["cuda_force_p2"] == "on"

    def test_reads_max_prerendered_as_integer(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.MAX_PRERENDERED_FRAMES: 2})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["max_prerendered"] == 2

    def test_reads_vrr_app_override_driver_default(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.VRR_APP_OVERRIDE: NvApiSettings.VRR_APP_DRIVER})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["vrr_app_override"] == "driver_default"

    def test_reads_vrr_app_override_force_on(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.VRR_APP_OVERRIDE: NvApiSettings.VRR_APP_ON})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["vrr_app_override"] == "force_on"

    def test_reads_unknown_value_as_unknown_string(self, inspector: NvidiaProfileInspector) -> None:
        xml = _build_nip_xml({NvApiSettings.POWER_MANAGEMENT_MODE: 0xDEAD})
        self._write_profile(inspector, xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["power_mode"] == "unknown"

    def test_returns_none_on_malformed_xml(self, inspector: NvidiaProfileInspector) -> None:
        path = inspector.get_profiles_dir() / "fpstune_gaming.nip"
        with open(path, "w", encoding="utf-16") as f:
            f.write("not valid xml at all <<<")
        assert inspector.read_applied_settings() is None

    def test_ignores_setting_with_missing_id_or_value(
        self, inspector: NvidiaProfileInspector
    ) -> None:
        # Build XML with one incomplete ProfileSetting (missing SettingValue)
        root = ET.Element("ArrayOfProfile")
        profile_elem = ET.SubElement(root, "Profile")
        ET.SubElement(profile_elem, "ProfileName").text = "fpstune_gaming"
        ET.SubElement(profile_elem, "Executeables")
        settings_elem = ET.SubElement(profile_elem, "Settings")
        # Good setting
        good = ET.SubElement(settings_elem, "ProfileSetting")
        ET.SubElement(good, "SettingID").text = str(NvApiSettings.SHADER_CACHE)
        ET.SubElement(good, "SettingValue").text = str(NvApiSettings.SHADER_CACHE_ON)
        # Bad setting: no SettingValue
        bad = ET.SubElement(settings_elem, "ProfileSetting")
        ET.SubElement(bad, "SettingID").text = "99999"
        body = ET.tostring(root, encoding="unicode")
        xml = f'<?xml version="1.0" encoding="utf-16"?>\n{body}'
        path = inspector.get_profiles_dir() / "fpstune_gaming.nip"
        with open(path, "w", encoding="utf-16") as f:
            f.write(xml)
        result = inspector.read_applied_settings()
        assert result is not None
        assert result.get("shader_cache") == "on"

    def test_roundtrip_full_profile(self, inspector: NvidiaProfileInspector) -> None:
        """save_profile then read_applied_settings returns consistent values."""
        profile = NvidiaProfile(
            name="fpstune_gaming",
            power_mode="maximum",
            low_latency="ultra",
            threaded_opt="on",
            vsync="off",
            shader_cache="on",
            texture_quality="performance",
            triple_buffer="off",
            fps_limit=0,
            bg_app_fps=30,
            vrr_mode="off",
            aniso_sample_opt="on",
            texture_lod_bias="clamp",
            ogl_thread_opt="on",
            cuda_force_p2="off",
            max_prerendered=1,
            vrr_app_override="driver_default",
        )
        inspector.save_profile(profile, filename="fpstune_gaming")
        result = inspector.read_applied_settings()
        assert result is not None
        assert result["power_mode"] == "maximum"
        assert result["low_latency"] == "ultra"
        assert result["vsync"] == "off"
        assert result["fps_limit"] == 0
        assert result["bg_app_fps"] == 30
        assert result["max_prerendered"] == 1


# ---------------------------------------------------------------------------
# apply_profile — command builder (mocked subprocess.Popen)
# ---------------------------------------------------------------------------


class TestApplyProfile:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        insp = NvidiaProfileInspector(data_dir=tmp_path)
        # Place a fake exe so is_installed() returns True
        insp.exe_path.parent.mkdir(parents=True, exist_ok=True)
        insp.exe_path.touch()
        return insp

    @pytest.fixture()
    def nip_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "test.nip"
        p.write_text("xml", encoding="utf-8")
        return p

    def _mock_popen(
        self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
    ) -> MagicMock:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (stdout, stderr)
        mock_proc.returncode = returncode
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        return mock_proc

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_silent_flags_in_command(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        """When silent=True the command includes -silentImport and -silent."""
        mock_proc = self._mock_popen(returncode=0)
        with (
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch.object(inspector, "check_nvapi_access", return_value=(True, None)),
        ):
            success, error = inspector.apply_profile(nip_file, silent=True)
        assert success is True
        assert error is None
        called_cmd = mock_popen.call_args[0][0]
        assert "-silentImport" in called_cmd
        assert "-silent" in called_cmd
        assert str(nip_file) == called_cmd[-1]

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_no_silent_flags_when_disabled(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        mock_proc = self._mock_popen(returncode=0)
        with (
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch.object(inspector, "check_nvapi_access", return_value=(True, None)),
        ):
            success, _ = inspector.apply_profile(nip_file, silent=False)
        assert success is True
        called_cmd = mock_popen.call_args[0][0]
        assert "-silentImport" not in called_cmd
        assert "-silent" not in called_cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_returns_false_on_nonzero_returncode(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        mock_proc = self._mock_popen(returncode=1, stderr=b"NVAPI error")
        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch.object(inspector, "check_nvapi_access", return_value=(True, None)),
        ):
            success, error = inspector.apply_profile(nip_file)
        assert success is False
        assert error is not None

    def test_apply_profile_returns_false_when_profile_missing(
        self, inspector: NvidiaProfileInspector, tmp_path: Path
    ) -> None:
        missing = tmp_path / "ghost.nip"
        with patch.object(inspector, "check_nvapi_access", return_value=(True, None)):
            success, error = inspector.apply_profile(missing)
        assert success is False
        assert error is not None
        assert "not found" in error.lower() or "Profile" in error

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_nvapi_precheck_failure_short_circuits(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        """If check_nvapi_access returns False, Popen should never be called."""
        with (
            patch("subprocess.Popen") as mock_popen,
            patch.object(
                inspector,
                "check_nvapi_access",
                return_value=(False, "NVIDIA Control Panel is open"),
            ),
        ):
            success, error = inspector.apply_profile(nip_file)
        assert success is False
        assert "NVIDIA Control Panel" in (error or "")
        mock_popen.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_timeout_kills_process(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="npi", timeout=60)
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch.object(inspector, "check_nvapi_access", return_value=(True, None)),
        ):
            success, error = inspector.apply_profile(nip_file, timeout=60)
        assert success is False
        assert "timed out" in (error or "").lower()
        mock_proc.kill.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only on win32")
    def test_apply_profile_nvapi_error_in_stderr_message(
        self, inspector: NvidiaProfileInspector, nip_file: Path
    ) -> None:
        mock_proc = self._mock_popen(returncode=1, stderr=b"NVAPI access denied")
        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch.object(inspector, "check_nvapi_access", return_value=(True, None)),
        ):
            success, error = inspector.apply_profile(nip_file)
        assert success is False
        assert "nvapi" in (error or "").lower() or "Close" in (error or "")


# ---------------------------------------------------------------------------
# check_nvapi_access (non-win32 only — win32 path requires live binaries)
# ---------------------------------------------------------------------------


class TestCheckNvApiAccess:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-win32 path only")
    def test_returns_false_on_non_windows(self, inspector: NvidiaProfileInspector) -> None:
        ok, err = inspector.check_nvapi_access()
        assert ok is False
        assert err is not None
        assert "Windows" in err

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 path only")
    def test_returns_false_when_nvsmi_not_found(self, inspector: NvidiaProfileInspector) -> None:
        """On win32: nvidia-smi FileNotFoundError → False."""
        with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi not found")):
            ok, err = inspector.check_nvapi_access()
        assert ok is False
        assert "nvidia-smi" in (err or "")

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 path only")
    def test_blocking_process_nvcplui_causes_false(self, inspector: NvidiaProfileInspector) -> None:
        """On win32: nvcplui.exe in tasklist output → False with blocking process message."""

        def fake_run(cmd: list[str], **_: object) -> MagicMock:
            r = MagicMock()
            r.returncode = 0
            if "nvidia-smi" in cmd:
                r.stdout = "GPU 0: NVIDIA GeForce RTX 4080"
                return r
            if any("nvcplui.exe" in arg for arg in cmd):
                r.stdout = "nvcplui.exe  1234  Console  1  50,000 K"
                return r
            r.stdout = "No tasks are running"
            return r

        with patch("subprocess.run", side_effect=fake_run):
            ok, err = inspector.check_nvapi_access()
        assert ok is False
        assert "NVIDIA Control Panel" in (err or "")


# ---------------------------------------------------------------------------
# install — non-win32 early return
# ---------------------------------------------------------------------------


class TestInstall:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-win32 path only")
    def test_install_returns_false_on_non_windows(self, inspector: NvidiaProfileInspector) -> None:
        result = inspector.install()
        assert result is False

    def test_install_returns_false_when_release_url_unavailable(
        self, inspector: NvidiaProfileInspector
    ) -> None:
        with (
            patch.object(inspector, "get_latest_release_url", return_value=None),
            patch("sys.platform", "win32"),
        ):
            result = inspector.install()
        assert result is False


# ---------------------------------------------------------------------------
# _verify_download (pure hash logic)
# ---------------------------------------------------------------------------


class TestVerifyDownload:
    @pytest.fixture()
    def inspector(self, tmp_path: Path) -> NvidiaProfileInspector:
        return NvidiaProfileInspector(data_dir=tmp_path)

    def test_refuses_version_not_in_checksums(self, tmp_path: Path) -> None:
        """SEC-23 regression: an unpinned version used to be accepted with only
        a warning, then extracted and executed elevated — while the shipped
        checksums file was empty, so EVERY real download went unverified. The
        gate must fail closed."""

        fake_file = tmp_path / "content.zip"
        fake_file.write_bytes(b"fake zip content")
        inspector = NvidiaProfileInspector(data_dir=tmp_path)
        # Patch json.loads to return a checksums dict with no entry for v9.9.9
        with patch(
            "fpstune.core.nv_profile.json.loads", return_value={"nvidiaProfileInspector": {}}
        ):
            result = inspector._verify_download(fake_file, "v9.9.9")
        assert result is False

    def test_refuses_when_checksums_file_unreadable(
        self, inspector: NvidiaProfileInspector, tmp_path: Path
    ) -> None:
        """SEC-23: an unreadable pin store means nothing can be verified, so
        nothing may be trusted — deleting checksums.json must not reopen the gate."""
        fake_file = tmp_path / "content.zip"
        fake_file.write_bytes(b"some bytes")

        # Patch json.loads to raise so checksums_path.read_text triggers Exception branch
        with patch("fpstune.core.nv_profile.json.loads", side_effect=FileNotFoundError):
            result = inspector._verify_download(fake_file, "v2.3.4")
        assert result is False

    def test_shipped_checksums_pin_at_least_one_version(self) -> None:
        """Fail-closed with an empty pin store would break every install: the
        shipped resources/checksums.json must actually pin a release."""
        import json as _json
        from pathlib import Path as _Path

        import fpstune.core.nv_profile as nv_mod

        checksums_path = _Path(nv_mod.__file__).parent.parent / "resources" / "checksums.json"
        known = _json.loads(checksums_path.read_text(encoding="utf-8"))
        pinned = known["nvidiaProfileInspector"]
        assert pinned, "No pinned nvidiaProfileInspector version; install() can never verify"
        for version, sha in pinned.items():
            assert version.startswith("v")
            assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)

    def test_returns_false_on_hash_mismatch(
        self, inspector: NvidiaProfileInspector, tmp_path: Path
    ) -> None:

        fake_file = tmp_path / "content.zip"
        fake_file.write_bytes(b"real content")
        wrong_hash = "a" * 64

        fake_checksums = {"nvidiaProfileInspector": {"v2.0.0": wrong_hash}}
        with patch("fpstune.core.nv_profile.json.loads", return_value=fake_checksums):
            result = inspector._verify_download(fake_file, "v2.0.0")
        assert result is False

    def test_returns_true_on_correct_hash(
        self, inspector: NvidiaProfileInspector, tmp_path: Path
    ) -> None:
        import hashlib

        fake_file = tmp_path / "content.zip"
        data = b"real content"
        fake_file.write_bytes(data)
        correct_hash = hashlib.sha256(data).hexdigest()

        fake_checksums = {"nvidiaProfileInspector": {"v2.0.0": correct_hash}}
        with patch("fpstune.core.nv_profile.json.loads", return_value=fake_checksums):
            result = inspector._verify_download(fake_file, "v2.0.0")
        assert result is True
