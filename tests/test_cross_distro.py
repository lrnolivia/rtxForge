"""Host differences across Linux gaming distros: Steam layouts, GPU detection and launcher guidance."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import desktop_frontend
import discovery
import hardware


def steam_library(root, appid='1', name='Game'):
    apps = root / 'steamapps'
    (apps / 'common' / name).mkdir(parents=True)
    (apps / f'appmanifest_{appid}.acf').write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"installdir"\t\t"{name}"\n}}\n')
    return apps


class SteamLayoutTest(unittest.TestCase):
    def libraries(self, home, mounts=()):
        with mock.patch.dict(os.environ, {'HOME': str(home), 'USER': 'deck'}), \
             mock.patch.object(discovery, 'MOUNT_FALLBACKS', list(mounts)):
            return discovery.candidate_libraries()

    def test_steamos_internal_and_sd_card_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve();home = tmp / 'home/deck';media = tmp / 'run/media'
            apps = steam_library(home / '.local/share/Steam', '10', 'Internal')
            sd = media / 'mmcblk0p1';steam_library(sd, '20', 'OnCard')
            (apps / 'libraryfolders.vdf').write_text(
                f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{home}/.local/share/Steam"\n\t}}\n'
                f'\t"1"\n\t{{\n\t\t"path"\t\t"{sd}"\n\t}}\n}}\n')
            self.assertEqual(set(self.libraries(home)), {home / '.local/share/Steam', sd})

    def test_sd_card_found_from_mounts_without_libraryfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve();home = tmp / 'home/deck';media = tmp / 'run/media'
            home.mkdir(parents=True);card = media / 'deck/SteamCard';steam_library(card)
            self.assertEqual(self.libraries(home, [media]), [card])

    def test_cachyos_dot_steam_symlink_is_one_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / 'home/user';real = home / '.local/share/Steam'
            steam_library(real);(home / '.steam').mkdir()
            (home / '.steam/steam').symlink_to(real);(home / '.steam/root').symlink_to(real)
            self.assertEqual(self.libraries(home), [real])

    def test_same_library_through_two_paths_is_listed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve();home = tmp / 'home/user';other = tmp / 'mnt/library'
            apps = steam_library(home / '.local/share/Steam');other.parent.mkdir(parents=True)
            other.symlink_to(home / '.local/share/Steam', target_is_directory=True)
            (apps / 'libraryfolders.vdf').write_text(f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{other}"\n\t}}\n}}\n')
            with mock.patch.object(discovery.Path, 'resolve', lambda self, strict=False: Path(os.path.abspath(self))):
                self.assertEqual(self.libraries(home), [home / '.local/share/Steam'])

    def test_flatpak_steam_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / 'home/user'
            flatpak = home / '.var/app/com.valvesoftware.Steam/.local/share/Steam';steam_library(flatpak)
            self.assertEqual(self.libraries(home), [flatpak])
            self.assertEqual(len(discovery.discover_games(flatpak, [], include_unavailable=True)), 1)


class ProcGpuTest(unittest.TestCase):
    def test_reads_model_and_driver_without_nvidia_smi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);gpu = root / 'gpus/0000:01:00.0';gpu.mkdir(parents=True)
            (root / 'version').write_text('NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  615.78.08  Release Build\n')
            (gpu / 'information').write_text('Model: \t\t NVIDIA GeForce RTX 4070\nIRQ: 117\n')
            self.assertEqual(hardware.proc_gpus(root), [['NVIDIA GeForce RTX 4070', '615.78.08', 'Unknown']])

    def test_detect_falls_back_when_nvidia_smi_is_missing(self):
        with mock.patch.object(hardware.platform, 'system', return_value='Linux'), \
             mock.patch.object(hardware.platform, 'machine', return_value='x86_64'), \
             mock.patch.object(hardware.subprocess, 'run', side_effect=FileNotFoundError('nvidia-smi')), \
             mock.patch.object(hardware, 'proc_gpus', return_value=[['NVIDIA GeForce RTX 4070', '615.78.08', 'Unknown']]):
            info = hardware.detect()
        self.assertTrue(info['ready']);self.assertEqual(info['family'], 'ada');self.assertEqual(info['vram'], 'Unknown')

    def test_no_driver_still_refuses(self):
        with mock.patch.object(hardware.platform, 'system', return_value='Linux'), \
             mock.patch.object(hardware.platform, 'machine', return_value='x86_64'), \
             mock.patch.object(hardware.subprocess, 'run', side_effect=FileNotFoundError('nvidia-smi')), \
             mock.patch.object(hardware, 'proc_gpus', return_value=[]):
            self.assertFalse(hardware.detect()['ready'])


class LauncherGuidanceTest(unittest.TestCase):
    def guidance(self, release, missing='PyGObject (python3-gi) is not installed.', distrobox=True):
        with mock.patch.object(desktop_frontend.shutil, 'which', return_value='/usr/bin/distrobox' if distrobox else None):
            return desktop_frontend.guidance(release, missing)

    def test_cachyos_gets_pacman(self):
        text = self.guidance({'ID': 'cachyos', 'ID_LIKE': 'arch'})
        self.assertIn('pacman -S --needed python-gobject gtk4 libadwaita', text);self.assertIn('--container', text)

    def test_steamos_gets_container_not_packages(self):
        text = self.guidance({'ID': 'steamos', 'ID_LIKE': 'arch'})
        self.assertNotIn('pacman', text);self.assertIn('--container', text);self.assertIn('--cli', text)

    def test_old_libadwaita_is_not_fixed_by_apt(self):
        text = self.guidance({'ID': 'ubuntu', 'ID_LIKE': 'debian'}, 'libadwaita 1.5 is too old; rtxForge needs 1.7 or newer.')
        self.assertNotIn('apt install', text);self.assertIn('--container', text)

    def test_without_distrobox_names_what_to_install(self):
        text = self.guidance({'ID': 'steamos'}, distrobox=False)
        self.assertIn('Install distrobox', text)

    def test_container_runs_the_mounted_payload_with_a_gl_renderer(self):
        with mock.patch.dict(os.environ, {'APPIMAGE': '/apps/RTXForge.AppImage'}):
            os.environ.pop('GSK_RENDERER', None)
            argv = desktop_frontend.container_argv(['--smoke-test'])
        self.assertEqual(argv[:4], ['distrobox', 'enter', 'rtxforge', '--'])
        self.assertIn('RTXFORGE_IN_CONTAINER=1', argv);self.assertIn('GSK_RENDERER=ngl', argv)
        self.assertIn('HOME=' + str(Path.home().resolve()), argv)
        self.assertEqual(argv[-2:], [str(Path(desktop_frontend.__file__).resolve()), '--smoke-test'])


if __name__ == '__main__':
    unittest.main()
