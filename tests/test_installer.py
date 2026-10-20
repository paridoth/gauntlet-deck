import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gdl
import steam_shortcut as steam


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def disc(self, name='disc.iso', region='GUNE5D', rev=1):
        path = self.root/name
        data = bytearray(2048)
        data[:6] = region.encode()
        data[7] = rev
        data[0x1c:0x20] = bytes.fromhex('c2339f3d')
        data[0x20:0x20+7] = b'Gauntlet'
        path.write_bytes(data)
        return path

    def archive(self, entries):
        path = self.root/('pack'+str(len(list(self.root.glob('*.zip'))))+'.zip')
        with zipfile.ZipFile(path, 'w') as z:
            for key, val in entries:
                z.writestr(key, val)
        return path

    def test_disc_detection_rejects_wrong_game_and_nkit(self):
        for region in ('GUNE5D', 'GUNP5D'):
            self.assertEqual(gdl.disc_info(self.disc(region=region))['game_id'], region)
        with self.assertRaises(RuntimeError):
            gdl.disc_info(self.disc(region='GM8E01'))
        p = self.disc()
        with p.open('r+b') as f:
            f.seek(0x200)
            f.write(b'NKIT')
        with self.assertRaisesRegex(RuntimeError, 'NKit'):
            gdl.disc_info(p)

    def test_overlay_replaces_other_format_for_same_texture(self):
        output = self.root/'textures'
        gdl.extract_textures(self.archive([('GUNE5D/tex1_8x8_aaa_1.dds', b'old')]), output)
        result = gdl.extract_textures(self.archive([('folder/tex1_8x8_aaa_1.png', b'new'),
                                                  ('install.sh', b'ignored')]), output, overlay=True)
        self.assertEqual(result['replaced'], ['tex1_8x8_aaa_1.dds'])
        self.assertEqual([p.name for p in output.iterdir()], ['tex1_8x8_aaa_1.png'])
        self.assertEqual(next(output.iterdir()).read_bytes(), b'new')

    def test_archive_traversal_symlink_duplicates_and_region(self):
        output = self.root/'textures'
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            gdl.extract_textures(self.archive([('../tex1_evil.png', b'evil')]), output)
        symlink = zipfile.ZipInfo('tex1_evil.png')
        symlink.external_attr = (0o120777 << 16)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            gdl.extract_textures(self.archive([(symlink, b'/etc/passwd')]), output)
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            gdl.extract_textures(self.archive([('tex1_same.png', b'a'), ('tex1_same.dds', b'b')]), output)
        with self.assertRaisesRegex(RuntimeError, 'GUNP5D'):
            gdl.extract_textures(self.archive([('GUNP5D/tex1_pal.png', b'a')]), output, overlay=True)
        self.assertFalse((self.root/'tex1_evil.png').exists())

    def test_game_settings_enable_both_60fps_parts_and_only_one_timer(self):
        c = lambda name: {'name': name, 'lines': ['04000000 60000000']}
        data = {'ar': [c('fps AR'), c('reset')], 'gecko': [c('timer'), c('fps Gecko')],
                'timer_name': 'timer', 'fps_ar_name': 'fps AR', 'fps_gecko_name': 'fps Gecko'}
        state = {'patched': True, 'game_id': 'GUNE5D', 'codes': data}
        file = self.root/'user/GameSettings/GUNE5D.ini'
        gdl.write_game_settings(self.root, state, 'stable')
        s = file.read_text()
        self.assertIn('[ActionReplay_Enabled]\n\n[Gecko]', s)
        self.assertTrue(s.endswith('[Gecko_Enabled]\n$timer\n'))
        gdl.write_game_settings(self.root, state, '60fps')
        s = file.read_text()
        self.assertIn('[ActionReplay_Enabled]\n$fps AR', s)
        self.assertTrue(s.endswith('[Gecko_Enabled]\n$timer\n$fps Gecko\n'))
        self.assertIn('Overclock = 3.0', s)
        state['patched'] = False
        with self.assertRaises(RuntimeError):
            gdl.write_game_settings(self.root, state, '60fps')

    def test_mixed_controller_names_keep_distinct_per_name_ids(self):
        pads = gdl.make_pad_config(['Xbox 360 Controller', 'DualSense Wireless Controller', 'Xbox 360 Controller'])
        self.assertEqual(pads['GCPad1']['Device'], 'SDL/0/Xbox 360 Controller')
        self.assertEqual(pads['GCPad2']['Device'], 'SDL/0/DualSense Wireless Controller')
        self.assertEqual(pads['GCPad3']['Device'], 'SDL/1/Xbox 360 Controller')
        self.assertEqual(pads['GCPad1']['Main Stick/Up'], '`Left Y+`')

    def test_personal_bundle_rom_takes_priority_over_other_library_copies(self):
        bundle = self.root/'bundle'
        bundle.mkdir()
        rom = self.disc('Gauntlet Dark Legacy.iso')
        shutil.copy2(rom, bundle/rom.name)
        home = self.root/'home'
        library = home/'Emulation/roms/gamecube'
        library.mkdir(parents=True)
        shutil.copy2(rom, library/rom.name)
        with patch.dict(os.environ, {'GAUNTLET_BUNDLE_DIR': str(bundle), 'HOME': str(home)}):
            self.assertEqual(gdl.discover_rom(), (bundle/rom.name).resolve())

    def test_patch_tool_extracts_to_install_drive_not_transfer_cache(self):
        cache = self.root/'external-cache'
        cache.mkdir()
        archive = cache/'tool.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo('package/xdelta3')
            member.size = 4
            tar.addfile(member, io.BytesIO(b'tool'))
        with patch.dict(gdl.ASSETS, {'xdelta': {'filename': archive.name, 'sha256': gdl.sha256(archive)}}):
            target = gdl.install_xdelta(cache, gdl.UI(True), True, self.root/'install/tools')
        self.assertEqual(target, self.root/'install/tools/xdelta3')
        self.assertTrue(os.access(target, os.X_OK))
        self.assertEqual(list(cache.iterdir()), [archive])

    def test_flatpak_probe_uses_the_same_runtime_and_writable_profile(self):
        d = gdl.Dolphin('flatpak', [])
        cmd = d.prefix(self.root, self.root/'app/bin/controller-probe')
        self.assertEqual(cmd[-1], gdl.APP_ID)
        self.assertIn('--filesystem='+str(self.root), cmd)
        self.assertIn('--command='+str(self.root/'app/bin/controller-probe'), cmd)

    def test_manual_controller_profile_is_preserved(self):
        (self.root/'manual-controllers').touch()
        class Fail:
            def run(*a, **kw):
                raise AssertionError('Probe should not run')
        gdl.controllers(self.root, Fail())

    def test_downloader_checks_cached_hash_and_offline_never_uses_network(self):
        cache = self.root/'cache'
        cache.mkdir()
        asset = {'filename': 'test.bin', 'sha256': hashlib.sha256(b'correct').hexdigest(), 'url': 'https://invalid.example/'}
        with patch.dict(gdl.ASSETS, {'test': asset}):
            with patch.object(gdl.urllib.request, 'urlopen', side_effect=AssertionError('No network expected')):
                with self.assertRaisesRegex(RuntimeError, 'missing'):
                    gdl.download('test', cache, gdl.UI(True), offline=True)
                (cache/'test.bin').write_bytes(b'correct')
                self.assertEqual(gdl.download('test', cache, gdl.UI(True), offline=True).read_bytes(), b'correct')
                (cache/'test.bin').write_bytes(b'wrong')
                with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                    gdl.download('test', cache, gdl.UI(True), offline=True)

    def test_download_resume_restarts_if_server_ignores_range(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': '8'}
        asset = {'filename': 'test.bin', 'sha256': hashlib.sha256(b'complete').hexdigest(), 'url': 'https://invalid.example/'}
        (self.root/'test.bin.part').write_bytes(b'partial')
        with patch.dict(gdl.ASSETS, {'test': asset}), patch.object(gdl, 'open_asset', return_value=Response(b'complete')):
            self.assertEqual(gdl.download('test', self.root, gdl.UI(True)).read_bytes(), b'complete')

    def test_shortcut_roundtrip_preserves_other_entries_and_rerun_is_idempotent(self):
        entry = [(2, 'appid', struct.pack('<I', 0xffffffff)), (1, 'AppName', 'Other game'),
                 (1, 'Exe', '"/path with spaces/other"'), (7, 'uint64', b'12345678'),
                 (0, 'tags', [(1, '0', 'Favorites')])]
        original = steam.encode([(0, 'shortcuts', [(0, '0', entry)])])
        self.assertEqual(steam.encode(steam.decode(original)), original)
        config = self.root/'config'
        config.mkdir()
        path = config/'shortcuts.vdf'
        path.write_bytes(original)
        launcher = self.root/'app/play-gauntlet.sh'
        steam.upsert(config, launcher)
        first = path.read_bytes()
        steam.upsert(config, launcher)
        shortcuts = steam.value(steam.decode(path.read_bytes()), 'shortcuts')
        self.assertEqual(len(shortcuts), 2)
        self.assertEqual(shortcuts[0], (0, '0', entry))
        self.assertEqual(path.read_bytes(), first)
        self.assertTrue(list(config.glob('shortcuts.vdf.gauntlet-backup-*')))

    def test_malformed_shortcuts_fail_without_changing_file(self):
        config = self.root/'config'
        config.mkdir()
        path = config/'shortcuts.vdf'
        original = b'\x00shortcuts\0\x12unknown\0'
        path.write_bytes(original)
        with self.assertRaises(ValueError):
            steam.upsert(config, self.root/'play.sh')
        self.assertEqual(path.read_bytes(), original)

    def test_active_steam_account_and_only_shortcut_specific_template(self):
        root = self.root/'.local/share/Steam'
        (root/'config').mkdir(parents=True)
        (root/'config/loginusers.vdf').write_text('"users" { "76561197960265729" { "MostRecent" "0" } "76561197960265730" { "MostRecent" "1" }}')
        for uid in ('1','2'):
            (root/'userdata'/uid/'config').mkdir(parents=True)
        config = steam.active_config(self.root)
        self.assertEqual(config, root/'userdata/2/config')
        template = root/'controller_base/templates/controller_neptune_gamepad_joystick.vdf'
        template.parent.mkdir(parents=True)
        template.write_text('Valve gamepad template')
        self.assertTrue(steam.seed_gamepad_template(config, 123))
        target = root/'controller_config/app_123.vdf'
        target.write_text('user customized it')
        self.assertFalse(steam.seed_gamepad_template(config, 123))
        self.assertEqual(target.read_text(), 'user customized it')

    def test_install_and_launch_in_isolated_home_with_synthetic_disc(self):
        home = self.root/'home'
        home.mkdir()
        (home/'Desktop').mkdir()
        executable = self.root/'fake-dolphin'
        result = self.root/'launch-args.json'
        executable.write_text('#!/usr/bin/env python3\nimport json,sys,pathlib\npathlib.Path('+repr(str(result))+').write_text(json.dumps(sys.argv[1:]))\n')
        executable.chmod(0o755)
        rom = self.disc('source with spaces.iso')
        original = rom.read_bytes()
        install = self.root/'installation with spaces'
        env = dict(os.environ, HOME=str(home))
        common = [sys.executable, str(gdl.SOURCE/'gdl.py')]
        p = subprocess.run(common+['install', '--cli', '--root', str(install), '--rom', str(rom),
                                  '--dolphin', str(executable), '--offline', '--no-patch', '--no-textures', '--no-steam'],
                           env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertEqual(rom.read_bytes(), original)
        state = json.loads((install/'state.json').read_text())
        self.assertFalse(state['patched'])
        self.assertEqual(Path(state['rom']).read_bytes(), original)
        self.assertTrue((home/'.local/share/applications/gauntlet-deck.desktop').exists())
        p = subprocess.run([str(install/'app/play-gauntlet.sh'), '--cli'], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertEqual(json.loads(result.read_text()), ['--user', str(install/'user'), '--batch', '--exec', state['rom']])


if __name__ == '__main__':
    unittest.main()
