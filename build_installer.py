#!/usr/bin/env python3
"""Build self-contained .desktop/.run installers without hosting a script."""
import base64
import io
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent


def build():
    (ROOT/'bin').mkdir(exist_ok=True)
    subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-o', str(ROOT/'bin/controller-probe'),
                    str(ROOT/'controller_probe.c'), '-ldl'], check=True)
    files = ['gdl.py', 'steam_shortcut.py', 'assets.json', 'controller_probe.c',
             'bin/controller-probe', 'gauntlet.svg', 'README.md', 'SOURCES.md', 'VALIDATION.md']
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for filename in files:
            z.write(ROOT/filename, filename)
    payload = base64.b64encode(stream.getvalue()).decode('ascii')
    bootstrap = ("import base64,io,os,pathlib,shutil,subprocess,sys,tempfile,urllib.parse,zipfile; "
                 "a=urllib.parse.urlparse(sys.argv[1]); "
                 "f=pathlib.Path(urllib.parse.unquote(a.path) if a.scheme=='file' else sys.argv[1]).resolve(); "
                 "os.environ['GAUNTLET_BUNDLE_DIR']=str(f.parent); "
                 "p=pathlib.Path(tempfile.mkdtemp(prefix='gauntlet-installer-')); "
                 f"zipfile.ZipFile(io.BytesIO(base64.b64decode('{payload}'))).extractall(p); "
                 "(p/'bin/controller-probe').chmod(493); "
                 "r=subprocess.call([sys.executable,str(p/'gdl.py')]+sys.argv[2:]); "
                 "shutil.rmtree(p); sys.exit(r)")
    # No shell interpolation in Desktop Entry: python receives one quoted -c argument.
    assert not any(c in bootstrap for c in ('"', '%', '\n', '\\'))
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    desktop = dist/'Install Gauntlet Deck.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nVersion=1.0\nName=Install Gauntlet Deck\n'
                       'Comment=Install HD textures, bug fixes, Steam shortcut, and controller mappings\n'
                       'Icon=applications-games\nTerminal=false\nExec=python3 -c "'+bootstrap+'" %k\nCategories=Game;\n')
    desktop.chmod(0o755)
    # bootstrap contains single quotes, so the POSIX shell version uses double quotes;
    # the base64/source-independent bootstrap contains no $, backticks, or backslashes.
    assert not any(c in bootstrap for c in ('$', '`'))
    run = dist/'Install-Gauntlet-Deck.run'
    run.write_text('#!/bin/sh\nexec python3 -c "'+bootstrap+'" "$0" "$@"\n')
    run.chmod(0o755)
    print(f'Built {desktop} ({desktop.stat().st_size:,} bytes)')
    print(f'Built {run} ({run.stat().st_size:,} bytes)')
    if desktop.stat().st_size >= 120000:
        raise RuntimeError('Installer argument is approaching Linux single-argument limit')


if __name__ == '__main__':
    build()
