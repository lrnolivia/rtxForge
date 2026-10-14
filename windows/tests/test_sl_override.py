"""sl_override against fake logs, PE version resources and NGX override folders.

Run: python -m unittest discover -s windows/tests
"""
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine-host"))
import sl_override  # noqa: E402

HEADER = "[20:04:14.803060] [W] OptiScaler v0.9.33-final (8bfff272) loaded\n"
SL = "[I] StreamlineHooks::streamlineLogCallback [streamline][info]"
OVERRIDE_RUN = HEADER + f"""\
{SL}pluginManager.cpp:430[setHostSDKVersion] Streamline v2.14.1.98614dad6 - host SDK v2.14.1
{SL}ota.cpp:699[readOTAOverrideDRS] Read SL_DLSS_OVERRIDE DRS key (global profile): 1
{SL}ota.cpp:406[parseServerManifest] OTA feature dlss_g_override_0 version 2.14.16
{SL}pluginManager.cpp:1004[loadPlugins] OTA override DRS key is set, searching for override OTA'd plugins...
{SL}ota.cpp:950[getOTAPluginForFeature] OTA override is enabled, using override feature name: dlss_g_override_0
{SL}ota.cpp:950[getOTAPluginForFeature] OTA override is enabled, using override feature name: common_override_0
{SL}pluginManager.cpp:907[mapPlugins] Loaded plugin 'sl.dlss_g' - version 2.14.16.0 PRODUCTION - id 1000
{SL}pluginManager.cpp:620[findPlugins] Ignoring plugin 'G:\\Game\\sl.dlss_g.dll' since it is a duplicate of already-loaded v2.14.16
"""
# Lauren's live log after the 2.14.16 folders were moved away (2026-10-13).
ABORTED_RUN = HEADER + f"""\
{SL}ota.cpp:699[readOTAOverrideDRS] Read SL_DLSS_OVERRIDE DRS key (global profile): 1
{SL}ota.cpp:950[getOTAPluginForFeature] OTA override is enabled, using override feature name: dlss_override_0
{SL}ota.cpp:1065[getOTAPluginForFeature] Found non-zero plugin "dlss_override_0" in NGX Cache but missing file
{SL}pluginManager.cpp:1020[loadPlugins] Not all override plugins available, OTA'd plugins will not be loaded
{SL}pluginManager.cpp:907[mapPlugins] Loaded plugin 'sl.dlss_g' - version 2.14.1.98614dad6 PRODUCTION - id 1000
"""
PLAIN_RUN = HEADER + f"""\
{SL}ota.cpp:699[readOTAOverrideDRS] Read SL_DLSS_OVERRIDE DRS key (global profile): 0
{SL}pluginManager.cpp:907[mapPlugins] Loaded plugin 'sl.dlss_g' - version 2.14.1.98614dad6 PRODUCTION - id 1000
"""


def fake_dll(version: str) -> bytes:
    a, b, c, d = (int(x) for x in version.split("."))
    fixed = struct.pack("<IIII", 0xFEEF04BD, 0x10000, (a << 16) | b, (c << 16) | d)
    return b"MZ" + b"\0" * 300 + b"VS_VERSION_INFO\0" + fixed + b"\0" * 64


class SlOverrideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.game = base / "The Witcher 3"
        self.exe_dir = self.game / "bin" / "x64_dx12"
        (self.exe_dir / "OptiScaler" / "streamline").mkdir(parents=True)
        for name in ("sl.dlss_g.dll", "sl.interposer.dll"):
            (self.exe_dir / "OptiScaler" / "streamline" / name).write_bytes(fake_dll("2.14.1.0"))
        self.models = base / "models"
        for feature in ("sl_dlss_g_override_0", "sl_common_override_0"):
            for build, version in (("134656", "2.14.0.0"), ("134672", "2.14.16.0")):
                folder = self.models / feature / "versions" / build / "files"
                folder.mkdir(parents=True)
                (folder / "190_E658700.dll").write_bytes(fake_dll(version))
        (self.models / "sl_dlss_g_0" / "versions" / "1" / "files").mkdir(parents=True)
        (self.models / "sl_dlss_g_0" / "versions" / "1" / "files" / "x.dll").write_bytes(fake_dll("9.0.0.0"))

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, log=None, **kw):
        if log is not None:
            (self.exe_dir / "OptiScaler.log").write_text(log, encoding="utf-8")
        return sl_override.check(self.exe_dir, self.game, provider="DLSS-Unlocked NR-v0.9.33", models=self.models, **kw)

    def snapshot(self):
        return {p: p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file()}

    def test_pe_version(self):
        self.assertEqual(sl_override.pe_version(fake_dll("2.14.16.0")), "2.14.16.0")
        self.assertIsNone(sl_override.pe_version(b"not a pe"))

    def test_override_folders_list_newest_per_feature_only(self):
        found = {p["feature"]: p["version"] for p in sl_override.override_plugins(self.models)}
        self.assertEqual(found, {"sl_common_override_0": "2.14.16", "sl_dlss_g_override_0": "2.14.16"})

    def test_override_loading_newer_streamline_warns(self):
        result = self.check(OVERRIDE_RUN)
        self.assertEqual(result["provider_streamline"], "2.14.1")
        self.assertEqual(result["loading"], "2.14.16")
        self.assertEqual(result["log"]["features"], ["common_override_0", "dlss_g_override_0"])
        self.assertEqual(result["log"]["ignored"][0]["version"], "2.14.16")
        self.assertEqual(result["warning"],
                         "NVIDIA App's DLSS Override is loading Streamline 2.14.16 for this game; DLSS-Unlocked NR-v0.9.33 "
                         "was verified with 2.14.1. Turn off DLSS Override – Frame Generation for this game in "
                         "NVIDIA App → Graphics → Program Settings.")

    def test_override_matching_version_is_quiet(self):
        result = self.check(OVERRIDE_RUN.replace("2.14.16", "2.14.1"))
        self.assertIsNone(result["warning"])

    def test_incomplete_override_is_a_note_not_a_warning(self):
        result = self.check(ABORTED_RUN)
        self.assertIsNone(result["warning"])
        self.assertTrue(result["log"]["aborted"])
        self.assertIn("incomplete on the last run", result["notes"][0])

    def test_override_off_for_game_is_quiet_even_with_downloads(self):
        self.assertIsNone(self.check(PLAIN_RUN)["warning"])

    def test_no_log_heads_up_from_downloaded_plugins(self):
        result = self.check()
        self.assertIsNone(result["log"])
        self.assertIn("has downloaded Streamline 2.14.16 override plugins", result["warning"])

    def test_no_log_older_downloads_are_quiet(self):
        for dll in self.models.rglob("134672/files/*.dll"):
            dll.write_bytes(fake_dll("2.14.0.0"))
        self.assertIsNone(self.check()["warning"])

    def test_install_review_uses_reviewed_payload(self):
        payload = {"OptiScaler/streamline/sl.dlss_g.dll": fake_dll("2.14.16.0")}
        self.assertIsNone(self.check(OVERRIDE_RUN, payload=payload)["warning"])

    def test_newest_log_below_game_folder(self):
        other = self.game / "launcher"
        other.mkdir()
        (other / "OptiScaler.log").write_text(OVERRIDE_RUN, encoding="utf-8")
        self.assertEqual(self.check()["log"]["path"], str(other / "OptiScaler.log"))

    def test_last_run_only(self):
        self.assertIsNone(self.check(OVERRIDE_RUN + PLAIN_RUN)["warning"])

    def test_read_only(self):
        (self.exe_dir / "OptiScaler.log").write_text(OVERRIDE_RUN, encoding="utf-8")
        before = self.snapshot()
        self.check()
        self.assertEqual(self.snapshot(), before)

    def test_env_models_root(self):
        os.environ["RTXFORGE_NGX_MODELS"] = str(self.models)
        try:
            self.assertEqual(sl_override.models_root(), self.models)
        finally:
            del os.environ["RTXFORGE_NGX_MODELS"]


if __name__ == "__main__":
    unittest.main()
