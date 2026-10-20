#!/usr/bin/env python3
"""Prepare a local personal transfer folder; keep ROMs out of the reusable installer."""
import argparse
import json
import os
from pathlib import Path
import shutil
import zipfile

import gdl


def link_or_copy(source, target):
    if target.exists():
        if gdl.sha256(source) == gdl.sha256(target):
            return
        raise RuntimeError('Refusing to replace a different file: '+str(target))
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True, type=Path)
    p.add_argument('--cache', required=True, type=Path)
    p.add_argument('--output', type=Path, default=Path('SteamDeck-Transfer'))
    p.add_argument('--zip', action='store_true')
    args = p.parse_args()
    rom = args.rom.resolve()
    info = gdl.disc_info(rom)
    if info['game_id'] != 'GUNE5D' or info['revision'] not in (0, 1):
        raise RuntimeError('The prepared patched kit expects a clean USA Rev 0 / Rev 1 disc')
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    assets = folder/'assets'
    assets.mkdir(exist_ok=True)
    for key in ('hd', 'xdelta', 'patch'+str(info['revision']), 'timer', 'fps60', 'skip_intro', 'inventory', 'reset_stats'):
        spec = gdl.ASSETS[key]
        src = args.cache/spec['filename']
        if not src.is_file() or gdl.sha256(src) != spec['sha256']:
            raise RuntimeError('Missing or incorrect asset: '+str(src))
        link_or_copy(src, assets/src.name)
    link_or_copy(rom, folder/rom.name)
    for filename in ('Install Gauntlet Deck.desktop', 'Install-Gauntlet-Deck.run'):
        shutil.copy2(gdl.SOURCE/'dist'/filename, folder/filename)
    (folder/'START HERE.txt').write_text(
        'PERSONAL GAUNTLET STEAM DECK TRANSFER KIT\n\n'
        '1. Copy this WHOLE folder to your Steam Deck (for example, Downloads).\n'
        '2. In Desktop Mode, open Install Gauntlet Deck.desktop.\n'
        '   KDE may ask you to trust/execute the downloaded launcher.\n'
        '3. Wait for installation, then return to Gaming Mode.\n'
        '4. Library > Non-Steam > Gauntlet Dark Legacy HD.\n\n'
        'Your ROM and all required mod downloads are beside the installer.\n'
        'The installer finds them automatically. If Dolphin is already installed,\n'
        'no mod downloads are needed. A missing Dolphin install requires internet.\n'
        'Allow 8 GiB free for installation in addition to this folder.\n'
        'Steam briefly closes and reopens while its shortcut is added.\n\n'
        'Connect controllers before launching. Optional 60 FPS and manual\n'
        'controller setup are in Gauntlet Deck Settings in the application menu.\n'
        'Use the Steam Gamepad layout; leave Proton compatibility off.\n\n'
        'This personal kit contains your ROM. The standalone reusable installer\n'
        'in dist/ contains no ROM or texture assets.\n')
    print(folder)
    if args.zip:
        out = folder.with_suffix('.zip')
        with zipfile.ZipFile(out, 'w', allowZip64=True) as z:
            for f in sorted(folder.rglob('*')):
                if f.is_file():
                    # HD archive is already compressed; avoid recompressing 2 GiB.
                    compression = zipfile.ZIP_STORED if f.suffix.lower() in ('.zip', '.gz') else zipfile.ZIP_DEFLATED
                    z.write(f, folder.name+'/'+str(f.relative_to(folder)), compress_type=compression, compresslevel=1)
        print(out, f'({out.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
