"""Lossless binary KeyValues editing for Steam shortcuts. No third-party modules."""
import os
from pathlib import Path
import re
import shutil
import struct
import time
import zlib


def decode(data):
    pos = 0

    def string():
        nonlocal pos
        end = data.index(b'\0', pos)
        s = data[pos:end].decode('utf-8', errors='surrogateescape')
        pos = end + 1
        return s

    def obj():
        nonlocal pos
        rows = []
        while pos < len(data):
            kind = data[pos]
            pos += 1
            if kind == 8:
                return rows
            key = string()
            if kind == 0:
                value = obj()
            elif kind == 1:
                value = string()
            elif kind in (2, 3, 4, 6):
                value = data[pos:pos+4]
                pos += 4
            elif kind == 7:
                value = data[pos:pos+8]
                pos += 8
            elif kind == 5:
                start = pos
                while data[pos:pos+2] != b'\0\0':
                    pos += 2
                pos += 2
                value = data[start:pos]
            else:
                raise ValueError(f'Unsupported Steam KeyValues type {kind}; file left unchanged')
            rows.append((kind, key, value))
        raise ValueError('Truncated shortcuts.vdf; file left unchanged')

    result = obj()
    if pos != len(data):
        raise ValueError('Unexpected trailing Steam shortcut data; file left unchanged')
    return result


def encode(rows):
    output = bytearray()
    for kind, key, value in rows:
        output.append(kind)
        output.extend(key.encode('utf-8', errors='surrogateescape') + b'\0')
        if kind == 0:
            output.extend(encode(value))
        elif kind == 1:
            output.extend(value.encode('utf-8', errors='surrogateescape') + b'\0')
        else:
            output.extend(value)
    output.append(8)
    return bytes(output)


def value(rows, key, default=None):
    return next((v for _, k, v in rows if k.lower() == key.lower()), default)


def steam_roots(home):
    return list(dict.fromkeys(p.resolve() for p in (
        home/'.local/share/Steam', home/'.steam/steam', home/'.steam/root',
        home/'.var/app/com.valvesoftware.Steam/.local/share/Steam') if p.exists()))


def active_config(home):
    """Choose MostRecent account, never alter every Steam user's shortcuts."""
    for root in steam_roots(home):
        login = root/'config/loginusers.vdf'
        text = login.read_text(errors='replace') if login.exists() else ''
        blocks = re.findall(r'"(\d{17})"\s*\{([^{}]*)\}', text, re.S)
        accounts = sorted(blocks, key=lambda b: bool(re.search(r'"MostRecent"\s*"1"', b[1])), reverse=True)
        for steam_id, _ in accounts:
            p = root/'userdata'/str(int(steam_id) & 0xffffffff)/'config'
            if p.exists():
                return p
        candidates = list((root/'userdata').glob('[0-9]*/config'))
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise RuntimeError('Several Steam accounts found. Sign in to the intended account, then retry Add to Steam.')
    raise RuntimeError('No signed-in Steam account found. Sign in to Steam first, then use Add Gauntlet to Steam.')


def upsert(config, launcher, title='Gauntlet Dark Legacy HD'):
    config = Path(config)
    path = config/'shortcuts.vdf'
    rows = decode(path.read_bytes()) if path.exists() else [(0, 'shortcuts', [])]
    shortcuts = value(rows, 'shortcuts')
    if not isinstance(shortcuts, list):
        raise ValueError('Unexpected shortcuts.vdf format; file left unchanged')
    exe = f'"{launcher}"'
    appid = (zlib.crc32((exe + title).encode()) | 0x80000000) & 0xffffffff
    entry = [(2, 'appid', struct.pack('<I', appid)), (1, 'AppName', title),
             (1, 'Exe', exe), (1, 'StartDir', f'"{launcher.parent}"'),
             (1, 'icon', str(launcher.parent/'gauntlet.svg')), (1, 'ShortcutPath', ''),
             (1, 'LaunchOptions', ''), (2, 'IsHidden', struct.pack('<I', 0)),
             (2, 'AllowDesktopConfig', struct.pack('<I', 0)),
             (2, 'AllowOverlay', struct.pack('<I', 1)),
             (2, 'OpenVR', struct.pack('<I', 0)), (2, 'Devkit', struct.pack('<I', 0)),
             (1, 'DevkitGameID', ''), (2, 'DevkitOverrideAppID', struct.pack('<I', 0)),
             (2, 'LastPlayTime', struct.pack('<I', 0)),
             (0, 'tags', [(1, '0', 'Gauntlet'), (1, '1', 'Installed Locally')])]
    existing = next((i for i, (kind, _, v) in enumerate(shortcuts)
                     if kind == 0 and value(v, 'Exe') == exe), None)
    if existing is None:
        used = {int(k) for _, k, _ in shortcuts if k.isdecimal()}
        index = 0
        while index in used:
            index += 1
        shortcuts.append((0, str(index), entry))
    else:
        # Preserve user artwork, playtime, categories, and other Steam-owned fields.
        old = shortcuts[existing][2]
        for kind, key, val in entry:
            if key in ('AppName', 'Exe', 'StartDir', 'LaunchOptions'):
                position = next((i for i, (_, n, _) in enumerate(old) if n.lower() == key.lower()), None)
                if position is None:
                    old.append((kind, key, val))
                else:
                    old[position] = (kind, key, val)
    if path.exists():
        backup = path.with_name(f'shortcuts.vdf.gauntlet-backup-{time.time_ns()}')
        shutil.copy2(path, backup)
    config.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.gauntlet-tmp')
    temporary.write_bytes(encode(rows))
    os.replace(temporary, path)
    return appid


def seed_gamepad_template(config, appid):
    """Seed only this shortcut with the user's installed Valve gamepad template."""
    root = config.parents[2]
    template = root/'controller_base/templates/controller_neptune_gamepad_joystick.vdf'
    target = root/'controller_config'/f'app_{appid}.vdf'
    if template.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, target)
        return True
    return False
