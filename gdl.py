#!/usr/bin/env python3
"""Gauntlet Deck installer and launcher. Python standard library only."""
import argparse
import collections
import configparser
import contextlib
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

from steam_shortcut import active_config, upsert, seed_gamepad_template

APP_ID = 'org.DolphinEmu.dolphin-emu'
SOURCE = Path(__file__).resolve().parent
DEFAULT_ROOT = Path.home()/'.local/share/gauntlet-deck'
ASSETS = json.loads((SOURCE/'assets.json').read_text())
LOG = logging.getLogger('gauntlet')


class Cancelled(Exception):
    pass


class UI:
    def __init__(self, cli=False):
        self.kind = None if cli or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')) else (
            'zenity' if shutil.which('zenity') else 'kdialog' if shutil.which('kdialog') else None)
        self.progress = None

    def message(self, text, error=False):
        LOG.error(text) if error else LOG.info(text)
        if self.kind == 'zenity':
            subprocess.run(['zenity', '--error' if error else '--info', '--no-markup',
                            '--title=Gauntlet Deck', '--width=560', '--text='+text], check=False)
        elif self.kind == 'kdialog':
            subprocess.run(['kdialog', '--title', 'Gauntlet Deck', '--error' if error else '--msgbox', text], check=False)

    def file(self, title, directory=False):
        if self.kind == 'zenity':
            cmd = ['zenity', '--file-selection', '--title='+title]
            if directory:
                cmd.append('--directory')
        elif self.kind == 'kdialog':
            cmd = ['kdialog', '--title', title, '--getexistingdirectory' if directory else '--getopenfilename', str(Path.home())]
        else:
            raise RuntimeError('No file picker available. Run with --rom /path/to/your/game.iso from a terminal.')
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode or not p.stdout.strip():
            raise Cancelled()
        return Path(p.stdout.strip()).expanduser().resolve()

    def choice(self, title, choices, default):
        if not self.kind:
            return default
        if self.kind == 'zenity':
            cmd = ['zenity', '--list', '--radiolist', '--title=Gauntlet Deck', '--text='+title,
                   '--width=680', '--height=340', '--column=Use', '--column=Mode', '--column=Description', '--hide-column=2', '--print-column=2']
            for key, label in choices:
                cmd.extend(['TRUE' if key == default else 'FALSE', key, label])
        else:
            cmd = ['kdialog', '--title', 'Gauntlet Deck', '--radiolist', title]
            for key, label in choices:
                cmd.extend([key, label, 'on' if key == default else 'off'])
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode:
            raise Cancelled()
        return p.stdout.strip() or default

    def status(self, text):
        LOG.info(text)
        if not self.progress and self.kind == 'zenity':
            self.progress = subprocess.Popen(['zenity', '--progress', '--pulsate', '--no-cancel',
                                              '--auto-close', '--title=Installing Gauntlet Deck', '--width=570'],
                                             stdin=subprocess.PIPE, text=True)
        if self.progress and self.progress.poll() is None:
            try:
                self.progress.stdin.write('#'+text.replace('\n', ' ')+'\n')
                self.progress.stdin.flush()
            except BrokenPipeError:
                pass

    def close_progress(self):
        if self.progress:
            try:
                self.progress.stdin.write('100\n')
                self.progress.stdin.close()
                self.progress.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.progress.terminate()
            self.progress = None


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    tmp.write_text(text)
    os.replace(tmp, path)


def ini_write(path, sections):
    c = configparser.ConfigParser(interpolation=None)
    c.optionxform = str
    for section, items in sections.items():
        c[section] = {k: str(v) for k, v in items.items()}
    import io
    out = io.StringIO()
    c.write(out)
    atomic_text(path, out.getvalue())


@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError('Gauntlet is already running or an installation is in progress.') from e
        yield


def sha256(path):
    with path.open('rb') as f:
        h = hashlib.sha256()
        while block := f.read(4*1024*1024):
            h.update(block)
        return h.hexdigest()


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and a.get('id') == 'download-form':
            self.action = a.get('action')
        if tag == 'input' and a.get('type') == 'hidden' and a.get('name'):
            self.fields[a['name']] = a.get('value', '')


def open_asset(url, offset=0):
    headers = {'User-Agent': 'GauntletDeckInstaller/1.0', 'Accept-Encoding': 'identity'}
    if offset:
        headers['Range'] = f'bytes={offset}-'
    response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
    if 'text/html' in response.headers.get('Content-Type', ''):
        page = response.read(1024*1024).decode('utf-8', errors='replace')
        response.close()
        form = DownloadForm()
        form.feed(page)
        # Google's ordinary large-file confirmation, restricted to its download endpoint.
        if form.action and urllib.parse.urlsplit(form.action).hostname == 'drive.usercontent.google.com':
            url = form.action+'?'+urllib.parse.urlencode(form.fields)
            return open_asset(url, offset)
        raise RuntimeError('The download host returned a web page instead of the file. '
                           'Check your connection or download the file manually into the cache. URL: '+url)
    return response


def download(key, cache, ui, offline=False):
    asset = ASSETS[key]
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache/asset['filename']
    if dest.exists():
        ui.status('Checking '+asset['filename'])
        if sha256(dest) == asset['sha256']:
            return dest
        raise RuntimeError(f'Cached file failed SHA-256 verification: {dest}. Remove it and retry.')
    if offline:
        raise RuntimeError('Offline cache is missing '+str(dest))
    partial = dest.with_name(dest.name+'.part')
    last_error = None
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        ui.status(('Resuming ' if offset else 'Downloading ')+asset['filename']+' (HD pack is 2.0 GiB)')
        try:
            with open_asset(asset['url'], offset) as response:
                resume = response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
                if not resume:
                    offset = 0
                total = int(response.headers.get('Content-Length', 0))+offset
                current = offset
                last_report = time.monotonic()
                with partial.open('ab' if resume else 'wb') as f:
                    while block := response.read(1024*1024):
                        f.write(block)
                        current += len(block)
                        if time.monotonic()-last_report > 3:
                            ui.status(f"Downloading {asset['filename']}: {current/1048576:.0f} / {total/1048576:.0f} MiB")
                            last_report = time.monotonic()
                if total and current != total:
                    raise OSError('Incomplete download')
            if sha256(partial) != asset['sha256']:
                partial.unlink(missing_ok=True)
                raise RuntimeError('Downloaded file failed SHA-256 verification: '+asset['filename'])
            os.replace(partial, dest)
            return dest
        except (OSError, urllib.error.URLError) as e:
            last_error = e
            LOG.warning('Download attempt %d failed: %s', attempt+1, e)
    raise RuntimeError(f'Download failed after 3 attempts: {asset["url"]}: {last_error}')


def disc_info(path):
    with path.open('rb') as f:
        header = f.read(0x440)
    if len(header) < 0x440 or header[0x1c:0x20] != bytes.fromhex('c2339f3d'):
        raise ValueError('Not an uncompressed GameCube ISO/GCM')
    game_id = header[:6].decode('ascii', errors='replace')
    if game_id not in ('GUNE5D', 'GUNP5D'):
        raise RuntimeError(f'This is {game_id}, not the supported GameCube Gauntlet: Dark Legacy disc.')
    if header[0x200:0x204] == b'NKIT':
        raise RuntimeError('NKit images cannot be patched safely. Restore your full ISO with NKit first.')
    return {'game_id': game_id, 'revision': header[7], 'title': header[0x20:0x400].split(b'\0')[0].decode(errors='replace')}


class Dolphin:
    def __init__(self, kind, command):
        self.kind = kind
        self.command = command

    def serialize(self):
        return {'kind': self.kind, 'command': self.command}

    def prefix(self, root, program=None):
        if self.kind == 'flatpak':
            cmd = ['flatpak', 'run', '--filesystem='+str(root), '--device=all',
                   '--env=SDL_JOYSTICK_HIDAPI_STEAM=0', '--env=SDL_JOYSTICK_HIDAPI_STEAMDECK=0']
            if program:
                cmd.append('--command='+str(program))
            return cmd+[APP_ID]
        if program:
            if str(program) == 'dolphin-tool':
                found = shutil.which('dolphin-tool')
                sibling = Path(self.command[0]).parent/'dolphin-tool'
                if sibling.exists():
                    return [str(sibling)]
                if found:
                    return [found]
                raise RuntimeError('This Dolphin build has no dolphin-tool. Convert your ROM to ISO in Dolphin first (right-click → Convert File).')
            return [str(program)]
        return self.command

    def run(self, root, args, program=None, capture=False):
        env = dict(os.environ, SDL_JOYSTICK_HIDAPI_STEAM='0', SDL_JOYSTICK_HIDAPI_STEAMDECK='0')
        # Flatpak host:ro supplies the original ROM; only our own profile is writable.
        return subprocess.run(self.prefix(root, program)+list(map(str, args)), env=env,
                              capture_output=capture, text=True, check=False)


def find_dolphin(ui, explicit=None):
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file() or not os.access(p, os.X_OK):
            raise RuntimeError('Dolphin executable is missing or not executable: '+str(p))
        return Dolphin('native', [str(p)])
    if shutil.which('flatpak'):
        p = subprocess.run(['flatpak', 'info', APP_ID], capture_output=True)
        if not p.returncode:
            return Dolphin('flatpak', [])
    if p := shutil.which('dolphin-emu'):
        return Dolphin('native', [p])
    images = [p for folder in (Path.home()/'Applications', Path.home()/'.local/bin') if folder.exists()
              for p in folder.glob('*.AppImage') if 'dolphin' in p.name.lower() and os.access(p, os.X_OK)]
    if len(images) == 1:
        return Dolphin('native', [str(images[0])])
    choice = ui.choice('Dolphin was not found. Choose how to continue.',
                       [('flatpak', 'Install Dolphin from Flathub'), ('existing', 'Select my existing Dolphin executable / AppImage')], 'flatpak')
    if choice == 'existing':
        return find_dolphin(ui, ui.file('Choose your Dolphin executable or AppImage'))
    if not shutil.which('flatpak'):
        raise RuntimeError('Flatpak is unavailable. Install Dolphin with Discover, or pass --dolphin /path/to/Dolphin.AppImage.')
    ui.status('Installing Dolphin from Flathub — this can take several minutes')
    subprocess.run(['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
                    'https://flathub.org/repo/flathub.flatpakrepo'], check=True)
    subprocess.run(['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub', APP_ID], check=True)
    return Dolphin('flatpak', [])


def ensure_iso(rom, stage, dolphin, root, ui):
    if '.nkit.' in rom.name.lower():
        raise RuntimeError('Restore this NKit image to a full ISO using NKit before applying the patch.')
    try:
        info = disc_info(rom)
        return rom, info
    except ValueError:
        pass
    ui.status('Converting your compressed ROM to ISO with Dolphin')
    iso = stage/'source.iso'
    result = dolphin.run(root, ['convert', '-i', rom, '-o', iso, '-f', 'iso'], program='dolphin-tool', capture=True)
    if result.returncode:
        raise RuntimeError('Dolphin could not convert this ROM: '+result.stderr[-2500:])
    return iso, disc_info(iso)


def install_xdelta(cache, ui, offline, tool_dir):
    archive = download('xdelta', cache, ui, offline)
    # A transfer cache can be on read-only/noexec USB media. Run tools from our install drive.
    tool_dir.mkdir(parents=True, exist_ok=True)
    target = tool_dir/'xdelta3'
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if Path(m.name).name == 'xdelta3' and m.isfile())
        with tar.extractfile(member) as src, target.open('wb') as dest:
            shutil.copyfileobj(src, dest)
    target.chmod(0o755)
    return target


def apply_patch(source, destination, revision, cache, ui, offline=False):
    patch = download('patch'+str(revision), cache, ui, offline)
    tool = install_xdelta(cache, ui, offline, destination.parent/'tools')
    ui.status('Applying Unofficial Revision 1.3 to a separate copy of your ROM')
    result = subprocess.run([str(tool), '-d', '-s', str(source), str(patch), str(destination)], capture_output=True, text=True)
    if result.returncode:
        destination.unlink(missing_ok=True)
        raise RuntimeError('The patch did not match your disc. Your original ROM is untouched. '
                           'Use a full, clean USA Rev 0 or Rev 1 ISO; scrubbed/NKit/already-patched copies may not match.\n'+result.stderr[-2500:])
    disc_info(destination)


TEXTURE = re.compile(r'^tex1_[A-Za-z0-9_-]+\.(png|dds)$', re.I)


def extract_textures(archive, destination, overlay=False, game_id='GUNE5D'):
    """Whitelist textures; never extract paths, symlinks, scripts, or ROM content."""
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    replaced = []
    with zipfile.ZipFile(archive) as z:
        selected = []
        for info in z.infolist():
            parts = info.filename.replace('\\', '/').split('/')
            name = parts[-1]
            if not TEXTURE.fullmatch(name):
                continue
            if '..' in parts or info.filename.startswith('/') or stat.S_ISLNK(info.external_attr >> 16):
                raise RuntimeError('Unsafe texture archive entry: '+info.filename)
            region = [p for p in parts if p in ('GUNE5D', 'GUNP5D')]
            if region and region[-1] != game_id and overlay:
                raise RuntimeError(f'Overlay {archive.name} is for {region[-1]}, but your disc is {game_id}.')
            if info.file_size > 256*1024*1024:
                raise RuntimeError('Unreasonably large texture entry: '+name)
            selected.append((info, name))
        if sum(i.file_size for i, _ in selected) > 8*1024**3:
            raise RuntimeError('Texture archive exceeds the 8 GiB extraction limit')
        if not selected:
            raise RuntimeError('No Dolphin tex1_*.png/dds textures found in '+str(archive))
        stems = set()
        for info, name in selected:
            stem = Path(name).stem.lower()
            if stem in stems:
                raise RuntimeError('Duplicate texture hash in archive: '+name)
            stems.add(stem)
        for info, name in selected:
            target = destination/name
            if overlay:
                for existing in destination.glob(Path(name).stem+'.*'):
                    replaced.append(existing.name)
                    existing.unlink()
            elif target.exists():
                raise RuntimeError('Duplicate texture filename: '+name)
            with z.open(info) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return {'archive': Path(archive).name, 'textures': count, 'replaced': replaced}


def codes_from_text(text):
    codes = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('$'):
            current = {'name': line[1:], 'lines': []}
            codes.append(current)
        elif current and re.fullmatch(r'[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}', line):
            current['lines'].append(line.upper())
    if not codes or any(not c['lines'] for c in codes):
        raise ValueError('No valid codes found in the downloaded code document')
    return codes


def write_game_settings(root, state, mode):
    enhanced = state['patched']
    if mode == '60fps' and not enhanced:
        raise RuntimeError('60 FPS mode requires the USA Unofficial Revision 1.3 installation.')
    c = state.get('codes', {})
    ar = c.get('ar', []) if enhanced else []
    gecko = c.get('gecko', []) if enhanced else []
    active_ar = []
    active_gecko = []
    if enhanced:
        active_gecko.append(c['timer_name'])
        if mode == '60fps':
            active_ar.append(c['fps_ar_name'])
            active_gecko.append(c['fps_gecko_name'])
    lines = ['# Generated for Gauntlet Deck. Optional codes remain disabled unless selected.',
             '[Core]', 'CPUThread = True', 'EnableCheats = '+str(enhanced),
             'OverclockEnable = '+str(mode == '60fps'), 'Overclock = '+('3.0' if mode == '60fps' else '1.0'),
             '', '[ActionReplay]']
    for code in ar:
        lines.extend(['$'+code['name'], *code['lines']])
    lines.extend(['', '[ActionReplay_Enabled]', *('$'+n for n in active_ar), '', '[Gecko]'])
    for code in gecko:
        lines.extend(['$'+code['name'], *code['lines']])
    lines.extend(['', '[Gecko_Enabled]', *('$'+n for n in active_gecko), ''])
    atomic_text(root/'user/GameSettings'/f'{state["game_id"]}.ini', '\n'.join(lines))


def configure(root, state, mode):
    # Only dedicated profile files are managed. GC saves and installed ROM stay in place.
    ini_write(root/'user/Config/Dolphin.ini', {
        'Core': {'CPUThread': 'True', 'GFXBackend': 'Vulkan', 'EnableCheats': str(state['patched']),
                 **{f'SIDevice{i}': 6 for i in range(4)}, 'EXIDevice0': 8, 'EXIDevice1': 255},
        'Display': {'Fullscreen': 'True', 'RenderToMain': 'True', 'KeepWindowOnTop': 'False'},
        'Interface': {'ConfirmStop': 'False', 'OnScreenDisplayMessages': 'True'},
        'Input': {'BackgroundInput': 'True'},
        'General': {'ISOPath0': str(root/'games'), 'ISOPaths': 1}})
    ini_write(root/'user/Config/GFX.ini', {
        'Settings': {'InternalResolution': 2, 'AspectRatio': 2, 'HiresTextures': str(state.get('textures', 0) > 0),
                     'CacheHiresTextures': 'False', 'ShaderCompilationMode': 2,
                     'WaitForShadersBeforeStarting': 'True', 'wideScreenHack': 'False', 'ShowFPS': 'False'},
        'Hardware': {'VSync': 'True'}, 'Enhancements': {'MaxAnisotropy': 2}})
    write_game_settings(root, state, mode)


def make_pad_config(names):
    counters = collections.Counter()
    result = {}
    for i in range(4):
        name = names[i] if i < len(names) else 'Steam Virtual Gamepad'
        index = counters[name]
        counters[name] += 1
        result[f'GCPad{i+1}'] = {
            'Device': f'SDL/{index}/{name}', 'Buttons/A': '`Button S`', 'Buttons/B': '`Button E`',
            'Buttons/X': '`Button W`', 'Buttons/Y': '`Button N`', 'Buttons/Z': '`Shoulder R`',
            'Buttons/Start': 'Start', 'Main Stick/Up': '`Left Y+`', 'Main Stick/Down': '`Left Y-`',
            'Main Stick/Left': '`Left X-`', 'Main Stick/Right': '`Left X+`', 'Main Stick/Dead Zone': 15,
            'Main Stick/Calibration': '100 100 100 100 100 100 100 100',
            'C-Stick/Up': '`Right Y+`', 'C-Stick/Down': '`Right Y-`',
            'C-Stick/Left': '`Right X-`', 'C-Stick/Right': '`Right X+`', 'C-Stick/Dead Zone': 15,
            'Triggers/L': '`Trigger L` > 0.5 | `Shoulder L`', 'Triggers/R': '`Trigger R` > 0.5',
            'Triggers/L-Analog': '`Trigger L`', 'Triggers/R-Analog': '`Trigger R`',
            'D-Pad/Up': '`Pad N`', 'D-Pad/Down': '`Pad S`', 'D-Pad/Left': '`Pad W`', 'D-Pad/Right': '`Pad E`',
            'Rumble/Motor': 'Motor', 'Rumble/Strength': 60}
    return result


def controllers(root, dolphin):
    if (root/'manual-controllers').exists():
        LOG.info('Keeping manually configured controller mappings')
        return
    probe = root/'app/bin/controller-probe'
    try:
        p = dolphin.run(root, [], program=probe, capture=True)
        names = [n for n in p.stdout.splitlines() if n and len(n) < 200] if p.returncode == 0 else []
    except OSError:
        names = []
    if names:
        ini_write(root/'user/Config/GCPadNew.ini', make_pad_config(names[:4]))
        atomic_text(root/'controllers.txt', '\n'.join(f'Player {i+1}: {n}' for i, n in enumerate(names[:4]))+'\n')
    elif not (root/'user/Config/GCPadNew.ini').exists():
        ini_write(root/'user/Config/GCPadNew.ini', make_pad_config([]))
    LOG.info('Controllers: %s', names or 'No SDL gamepad detected. Connect controllers and relaunch; use Steam Gamepad template.')


def desktop_quote(text):
    # Desktop Entry double-quoted arguments have a separate escape layer.
    return '"'+str(text).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')+'"'


def install_launchers(root):
    app = root/'app'
    app.mkdir(parents=True, exist_ok=True)
    for name in ['gdl.py', 'steam_shortcut.py', 'assets.json', 'gauntlet.svg', 'README.md', 'SOURCES.md', 'VALIDATION.md', 'controller_probe.c']:
        src = SOURCE/name
        dst = app/name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    (app/'bin').mkdir(exist_ok=True)
    if (SOURCE/'bin/controller-probe').resolve() != (app/'bin/controller-probe').resolve():
        shutil.copy2(SOURCE/'bin/controller-probe', app/'bin/controller-probe')
    (app/'bin/controller-probe').chmod(0o755)
    for name, action in [('play-gauntlet.sh', 'play'), ('configure-gauntlet.sh', 'settings'),
                         ('add-to-steam.sh', 'add-steam')]:
        script = '#!/bin/sh\nexec python3 '+shlex.quote(str(app/'gdl.py'))+' '+action+' --root '+shlex.quote(str(root))+' "$@"\n'
        atomic_text(app/name, script)
        (app/name).chmod(0o755)
    apps = Path.home()/'.local/share/applications'
    entries = [('gauntlet-deck.desktop', 'Gauntlet Dark Legacy HD', 'play-gauntlet.sh'),
               ('gauntlet-deck-settings.desktop', 'Gauntlet Deck Settings', 'configure-gauntlet.sh'),
               ('gauntlet-deck-steam.desktop', 'Add Gauntlet to Steam', 'add-to-steam.sh')]
    for filename, title, script in entries:
        entry = ('[Desktop Entry]\nType=Application\nVersion=1.0\nName='+title+'\nExec='+desktop_quote(app/script)+
                 '\nIcon='+str(app/'gauntlet.svg')+'\nTerminal=false\nCategories=Game;\n')
        atomic_text(apps/filename, entry)
        if filename == 'gauntlet-deck.desktop':
            desktop = Path.home()/'Desktop'
            if desktop.is_dir():
                atomic_text(desktop/'Gauntlet Dark Legacy HD.desktop', entry)
                (desktop/'Gauntlet Dark Legacy HD.desktop').chmod(0o755)


def steam_running():
    for path in Path('/proc').glob('[0-9]*/comm'):
        try:
            if path.read_text().strip() == 'steam':
                return True
        except (OSError, ProcessLookupError):
            pass
    return False


def add_to_steam(root, ui):
    if 'gamescope' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
        raise RuntimeError('Use Desktop Mode to add the shortcut. Open Add Gauntlet to Steam from the application menu there.')
    config = active_config(Path.home())
    was_running = steam_running()
    command = ['steam'] if shutil.which('steam') else ['flatpak', 'run', 'com.valvesoftware.Steam']
    try:
        if was_running:
            ui.status('Saving the Steam shortcut — Steam will close briefly and reopen')
            subprocess.run(command+['-shutdown'], check=True, timeout=20, capture_output=True)
            deadline = time.monotonic()+40
            while steam_running() and time.monotonic() < deadline:
                time.sleep(0.5)
            if steam_running():
                raise RuntimeError('Steam has not exited. Close Steam and run Add Gauntlet to Steam again. No shortcut files were changed.')
        appid = upsert(config, root/'app/play-gauntlet.sh')
        seed_gamepad_template(config, appid)
    finally:
        if was_running and not steam_running():
            subprocess.Popen(command+['-silent'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def build_codes(cache, ui, offline):
    texts = {k: download(k, cache, ui, offline).read_text() for k in ('timer', 'fps60', 'skip_intro', 'inventory', 'reset_stats')}
    timer = codes_from_text(texts['timer'])[1]  # Author's version 2: visible whenever inventory is open.
    fps_ar, fps_gecko = codes_from_text(texts['fps60'])
    skip = codes_from_text(texts['skip_intro'])[0]
    inventory = codes_from_text(texts['inventory'])[0]
    reset = codes_from_text(texts['reset_stats'])[0]
    return {'ar': [fps_ar, inventory, reset], 'gecko': [timer, fps_gecko, skip],
            'timer_name': timer['name'], 'fps_ar_name': fps_ar['name'], 'fps_gecko_name': fps_gecko['name']}


def discover_rom():
    if os.environ.get('GAUNTLET_BUNDLE_DIR'):
        bundle_roms = [p.resolve() for p in Path(os.environ['GAUNTLET_BUNDLE_DIR']).iterdir()
                       if p.is_file() and p.suffix.lower() in ('.iso', '.gcm', '.rvz', '.gcz', '.wia', '.ciso')
                       and re.search('gauntlet|dark.?legacy|GUN[EP]5D', p.name, re.I)]
        if len(bundle_roms) == 1:
            return bundle_roms[0]
    roots = [Path.home()/'Emulation/roms/gamecube', Path.home()/'Emulation/roms/gc',
             Path.home()/'Downloads', Path.home()/'Documents']
    media = Path('/run/media')
    if media.exists():
        roots += list(media.glob('*/Emulation/roms/gamecube'))+list(media.glob('*/*/Emulation/roms/gamecube'))
    candidates = set()
    for folder in roots:
        if not folder.exists():
            continue
        # Downloads/Documents are intentionally shallow; don't crawl a user's full home.
        iterator = folder.rglob('*') if '/roms/' in str(folder) else folder.glob('*')
        for p in iterator:
            if p.is_file() and p.suffix.lower() in ('.iso', '.gcm', '.rvz', '.gcz', '.wia', '.ciso') and re.search('gauntlet|dark.?legacy|GUN[EP]5D', p.name, re.I):
                candidates.add(p.resolve())
    return next(iter(candidates)) if len(candidates) == 1 else None


def install(args, root, ui):
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('This package targets the x86-64 Steam Deck and Linux PCs.')
    rom = Path(args.rom).expanduser().resolve() if args.rom else discover_rom()
    if rom is None:
        rom = ui.file('Choose your legal GameCube Gauntlet Dark Legacy ROM (ISO / GCM / RVZ / GCZ)')
    if not rom.is_file():
        raise RuntimeError('ROM not found: '+str(rom))
    if rom.is_relative_to(root/'games'):
        raise RuntimeError('Select your original ROM, not this installer’s patched copy.')
    dolphin = find_dolphin(ui, args.dolphin)
    bundle = Path(os.environ['GAUNTLET_BUNDLE_DIR']) if os.environ.get('GAUNTLET_BUNDLE_DIR') else None
    cache = Path(args.cache).expanduser().resolve() if args.cache else (
        bundle/'assets' if bundle and (bundle/'assets').is_dir() else root/'cache')
    free = shutil.disk_usage(root).free
    required = (8 if not args.no_textures else 4)*1024**3
    if free < required:
        raise RuntimeError(f'Please free at least {required/1024**3:.0f} GiB on the install drive (currently {free/1024**3:.1f} GiB).')
    ui.status('Preparing your ROM — original files are only read')
    with tempfile.TemporaryDirectory(prefix='work-', dir=root) as work:
        stage = Path(work)
        iso, info = ensure_iso(rom, stage, dolphin, root, ui)
        patched = not args.no_patch
        if patched and info['game_id'] != 'GUNE5D':
            ui.close_progress()
            choice = ui.choice('The bug-fix patch only supports USA discs. Your PAL copy can use the HD textures without gameplay patches.',
                               [('hd', 'Install PAL with HD textures only'), ('cancel', 'Cancel')], 'hd')
            if choice == 'cancel':
                raise Cancelled()
            patched = False
        if patched and info['revision'] not in (0, 1):
            raise RuntimeError('Expected an unmodified USA Rev 0 or Rev 1 disc. Select a clean original ROM.')
        game = stage/'Gauntlet Dark Legacy.iso'
        if patched:
            apply_patch(iso, game, info['revision'], cache, ui, args.offline)
        else:
            ui.status('Copying your ROM into the dedicated installation')
            shutil.copyfile(iso, game)
        code_data = build_codes(cache, ui, args.offline) if patched else {}
        packs = []
        texture_stage = stage/'textures'
        if not args.no_textures:
            archive = download('hd', cache, ui, args.offline)
            ui.status('Installing DannyKhan419 HD 2.0 textures (19,199 textures)')
            packs.append(extract_textures(archive, texture_stage, game_id=info['game_id']))
        for overlay in args.overlay:
            ui.status('Merging optional texture overlay: '+str(overlay))
            packs.append(extract_textures(Path(overlay), texture_stage, overlay=True, game_id=info['game_id']))
        state = {'version': 1, **info, 'source_rom': str(rom), 'patched': patched,
                 'rom': str(root/'games/Gauntlet Dark Legacy.iso'), 'dolphin': dolphin.serialize(),
                 'mode': 'stable', 'codes': code_data,
                 'textures': len(list(texture_stage.glob('*'))) if texture_stage.exists() else 0,
                 'packs': packs, 'installed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        ui.status('Saving the game, controller profile, and launchers')
        # Preserve the previous installation's managed files before replacing any of them.
        if (root/'state.json').exists():
            backup = root/'backups'/str(time.time_ns())
            for relative in ('state.json', 'user/Config', 'user/GameSettings'):
                p = root/relative
                if p.is_dir():
                    shutil.copytree(p, backup/relative)
                elif p.exists():
                    (backup/relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, backup/relative)
        (root/'games').mkdir(exist_ok=True)
        os.replace(game, Path(state['rom']))
        textures = root/'user/Load/Textures'/info['game_id']
        textures.parent.mkdir(parents=True, exist_ok=True)
        if textures.exists():
            shutil.rmtree(textures)
        if texture_stage.exists():
            os.replace(texture_stage, textures)
        configure(root, state, 'stable')
        install_launchers(root)
        controllers(root, dolphin)
        atomic_text(root/'state.json', json.dumps(state, indent=2)+'\n')
    steam_note = ''
    if not args.no_steam:
        try:
            add_to_steam(root, ui)
            steam_note = '\nThe game has been added to Steam. Return to Gaming Mode and open Non-Steam.'
        except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as e:
            LOG.warning('Steam shortcut deferred: %s', e)
            steam_note = '\nSteam shortcut needs attention: '+str(e)+'\nUse “Add Gauntlet to Steam” in the application menu to retry.'
    ui.close_progress()
    ui.message('Installed Gauntlet Dark Legacy'+(' — Unofficial Revision 1.3' if patched else ' — original gameplay')+
               f' with {state["textures"]:,} custom textures.\n'+steam_note+
               '\n\nControllers: connect pads before launching. Player order follows the SDL device list; '
               'use Steam’s Gamepad layout. Gauntlet Deck Settings offers controller setup and optional 60 FPS mode. '
               '\n\nYour existing Dolphin saves remain separate. Import a copy through Settings if needed.\n\nInstall folder: '+str(root))


def load_state(root):
    if not (root/'state.json').exists():
        raise RuntimeError('Gauntlet has not been installed yet. Run the installer first.')
    return json.loads((root/'state.json').read_text())


def play(args, root, ui):
    state = load_state(root)
    mode = args.mode or state.get('mode', 'stable')
    if not Path(state['rom']).exists():
        raise RuntimeError('The installed game is missing. Run the installer again using your original ROM.')
    write_game_settings(root, state, mode)
    dolphin = Dolphin(**state['dolphin'])
    controllers(root, dolphin)
    result = dolphin.run(root, ['--user', root/'user', '--batch', '--exec', state['rom']])
    if result.returncode:
        raise RuntimeError(f'Dolphin exited with status {result.returncode}. See {root/"gauntlet.log"}. '
                           'Use Settings to open Dolphin and check the graphics backend if Vulkan is unavailable.')


def settings(args, root, ui):
    state = load_state(root)
    choice = ui.choice('Gauntlet Deck settings', [
        ('stable', 'Recommended: original frame rate, 2× resolution, HD textures'),
        ('60fps', 'Experimental 60 FPS: 300% emulated CPU, remaining animation/timing issues'),
        ('controllers', 'Open Dolphin controller configuration / test connected pads'),
        ('auto_controllers', 'Restore automatic controller detection for each launch'),
        ('dolphin', 'Open the dedicated Dolphin profile (graphics, saves, optional codes)'),
        ('overlay', 'Import a texture pack ZIP (overrides matching HD textures)'),
        ('saves', 'Import copies of existing Dolphin memory cards / GCI saves'),
        ('steam', 'Add or repair Steam shortcut (Desktop Mode)')], 'stable')
    if choice in ('stable', '60fps'):
        configure(root, state, choice)
        state['mode'] = choice
        atomic_text(root/'state.json', json.dumps(state, indent=2)+'\n')
        ui.message('Saved '+choice+' mode. Launch Gauntlet from Steam to play.')
    elif choice in ('controllers', 'dolphin'):
        dolphin = Dolphin(**state['dolphin'])
        if choice == 'controllers':
            controllers(root, dolphin)
            ui.message('Dolphin will open. Choose Controllers → Configure to test or change each port. '
                       'Your mappings will be kept after closing Dolphin. Use Restore automatic controller detection '
                       'in Gauntlet Deck Settings to resume automatic setup.')
        dolphin.run(root, ['--user', root/'user'])
        if choice == 'controllers':
            (root/'manual-controllers').touch()
    elif choice == 'auto_controllers':
        (root/'manual-controllers').unlink(missing_ok=True)
        controllers(root, Dolphin(**state['dolphin']))
        ui.message('Automatic controller detection restored. Connect pads before launching.')
    elif choice == 'steam':
        add_to_steam(root, ui)
        ui.close_progress()
        ui.message('Steam shortcut is ready.')
    elif choice == 'overlay':
        archive = ui.file('Choose a Dolphin texture ZIP — selected textures override the HD pack')
        with tempfile.TemporaryDirectory(dir=root) as work:
            staged = Path(work)/'textures'
            destination = root/'user/Load/Textures'/state['game_id']
            if destination.exists():
                shutil.copytree(destination, staged)
            record = extract_textures(archive, staged, overlay=True, game_id=state['game_id'])
            backup = root/'backups'/('textures-'+str(time.time_ns()))
            backup.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                os.replace(destination, backup)
            os.replace(staged, destination)
        state['packs'].append(record)
        state['textures'] = len(list(destination.glob('*')))
        atomic_text(root/'state.json', json.dumps(state, indent=2)+'\n')
        configure(root, state, state['mode'])
        ui.message(f'Imported {record["textures"]} textures; replaced {len(record["replaced"])} existing textures. Backup: {backup}')
    elif choice == 'saves':
        gc = ui.file('Choose the GC folder from your existing Dolphin user directory', directory=True)
        if gc.name != 'GC' or gc.resolve() == (root/'user/GC').resolve():
            raise RuntimeError('Choose the GC folder in your other Dolphin profile. In Dolphin use File → Open User Folder.')
        target = root/'user/GC'
        if target.exists():
            backup = root/'backups'/('GC-'+str(time.time_ns()))
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup)
        shutil.copytree(gc, target, dirs_exist_ok=True)
        ui.message('Copied your GC saves. Originals are unchanged. In the dedicated Dolphin profile, '
                   'check GameCube Slot A matches your old memory card type and file path if you used a raw memory card.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['install', 'play', 'settings', 'add-steam'], nargs='?', default='install')
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--rom')
    p.add_argument('--dolphin', help='Existing native Dolphin executable or AppImage')
    p.add_argument('--cache', help='Use a prepared download cache')
    p.add_argument('--overlay', action='append', default=[], help='Texture ZIP; later packs override earlier packs')
    p.add_argument('--offline', action='store_true')
    p.add_argument('--no-patch', action='store_true', help='Use original gameplay, without USA-only patches/codes')
    p.add_argument('--no-textures', action='store_true')
    p.add_argument('--no-steam', action='store_true')
    p.add_argument('--cli', action='store_true', help='No GUI dialogs; provide --rom when installing')
    p.add_argument('--mode', choices=['stable', '60fps'])
    args = p.parse_args()
    root = args.root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(root/'gauntlet.log'), logging.StreamHandler()])
    ui = UI(args.cli)
    try:
        with locked(root/'.lock'):
            if args.action == 'install':
                install(args, root, ui)
            elif args.action == 'play':
                play(args, root, ui)
            elif args.action == 'settings':
                settings(args, root, ui)
            else:
                add_to_steam(root, ui)
                ui.close_progress()
                ui.message('Steam shortcut is ready.')
    except Cancelled:
        LOG.info('Cancelled')
        return 0
    except Exception as e:
        LOG.exception('Gauntlet operation failed')
        ui.close_progress()
        ui.message(str(e)+'\n\nDetails: '+str(root/'gauntlet.log'), error=True)
        return 1
    finally:
        ui.close_progress()
    return 0


if __name__ == '__main__':
    sys.exit(main())
