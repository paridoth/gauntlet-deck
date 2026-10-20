# Gauntlet Deck

A portable installer for your own GameCube copy of **Gauntlet: Dark Legacy**, with HD textures, bug fixes, Steam integration, and controller mappings for the Steam Deck. No ROM is included or downloaded.

## Install on the Deck

1. Switch to **Desktop Mode**. Save any work in Steam; the installer briefly closes and reopens Steam to add the game.
2. Copy **Install Gauntlet Deck.desktop** to the Deck and open it. KDE may ask you to trust/execute the downloaded launcher. The `.desktop` file contains the installer; it does not need other files beside it.
3. Choose your legal GameCube ROM if it is not detected automatically. Leave the installer running while it downloads and verifies the HD pack.
4. Return to **Gaming Mode → Library → Non-Steam → Gauntlet Dark Legacy HD**.

Alternate launcher: make `Install-Gauntlet-Deck.run` executable in Properties → Permissions, then open it, or run `bash Install-Gauntlet-Deck.run` in Konsole.

Allow **8 GiB free**, an internet connection, and approximately **2 GiB of texture downloads**. The completed game/profile is about 4 GiB plus the 2 GiB download cache and Dolphin itself. Downloads resume when the host supports byte ranges. All downloaded assets have pinned SHA-256 checksums.

**Your prepared personal kit:** `SteamDeck-Transfer.zip` contains the installer, your original USA Rev 1 ROM, and the verified mod download cache. Extract it and copy the whole `SteamDeck-Transfer` folder to the Deck. Open its `Install Gauntlet Deck.desktop`; it detects the adjacent ROM and cache automatically. If Dolphin is already installed, mod setup needs no downloads. Keep 8 GiB free in addition to the transfer folder. After installation, you can remove the transfer folder to recover space.

## Included setup

| Component | Default |
|---|---|
| DannyKhan419 HD texture pack 2.0 | Enabled; 19,199 textures |
| CyberNomadic Unofficial Revision 1.3 | Applied to a separate copy of a clean USA Rev 0 / Rev 1 disc |
| Vizyne item timer / charges display, version 2 | Enabled with the USA patch; its author recommends this combination |
| Vizyne 60 FPS AR + Gecko pair | Available through Settings, disabled initially |
| Vizyne intro skip, inventory patch, character reset / stats | Available in dedicated Dolphin → game Properties; disabled initially |
| Graphics | Vulkan, 2× internal resolution, 4:3, asynchronous ubershaders, 4× anisotropic filtering |
| Controllers | Four GameCube ports; detect SDL gamepads again at each launch |
| Saves | Separate GCI memory-card folder; existing Dolphin saves are untouched |

The default keeps the game's original frame rate. **60 FPS is experimental**: the code author documents faster basic attack animations, occasional speed spikes, and some sped-up camera/effect animations. It uses a **300% emulated CPU clock**; this is an emulation setting, not a change to the Deck's physical CPU or power limits. Performance on a real Deck has not been measured here.

The USA patch fixes stat resets, inventory visibility, access to the 11th item, inventory text placement/names, and Scroll Burn FX. It also restores the high-resolution Warrior via the in-game name code `CYBMOS`.

**PAL discs:** the installer offers HD textures with original gameplay. The USA binary patch and gameplay codes are not enabled on PAL. The HD archive author recommends PAL, although individual texture coverage may differ across disc versions.

**Compressed ROMs:** RVZ/GCZ/WIA and other Dolphin-readable disc images are converted with `dolphin-tool` before patching. A native/AppImage build without that tool needs an ISO first: right-click your game in Dolphin → Convert File → ISO. NKit, scrubbed, and already-patched images may not match the binary patch. A patch checksum error stops installation and leaves the original ROM untouched.

## Controllers and couch co-op

Launch from Steam in Gaming Mode. The installer seeds this shortcut with Valve's installed Steam Deck Gamepad template when it is available. If the Deck controls act like a mouse, open the game's Steam controller settings and apply **Templates → Gamepad** (or **Gamepad with Joystick Trackpad**). Leave Proton compatibility **off**; this is a native Linux launcher.

Connect up to four Bluetooth/USB controllers **before** launching. Dolphin mappings use SDL's standardized button positions, so Xbox, PlayStation, and Deck pads share a layout:

| Physical control | GameCube input |
|---|---|
| Left stick | Main stick |
| Right stick | C-stick |
| Bottom / right / left / top face button | A / B / X / Y |
| Left trigger or left shoulder | L |
| Right trigger | R |
| Right shoulder | Z |
| D-pad | D-pad, including inventory controls |
| Menu / Start | Start |

The included probe enumerates controllers **inside Dolphin's Flatpak runtime** when using Flatpak, avoiding hardcoded controller names. It assigns ports using SDL device order and same-name device indices. Steam's controller reordering may help with virtual pads, but mixed native devices can require manual port assignment. Reconnect/reorder pads, then relaunch. Hot-plugging during play does not rebuild the mappings.

Use **Gauntlet Deck Settings → Open Dolphin controller configuration** to test or manually assign each port. Closing that window keeps your manual mappings. Choose **Restore automatic controller detection** to resume automatic setup. Exit a Gaming Mode session with **Steam → Exit game**.

## Other texture packs

TheZac provides Sky Dominion skies, Arcade Cloud 9 backgrounds, and character/enemy recolors. See [SOURCES.md](SOURCES.md) for direct creator pages. These are optional artistic changes, not bug fixes. Their ModDB download pages can require a browser; they are not silently substituted if a download fails.

Download the ZIP you want, then use **Gauntlet Deck Settings → Import a texture pack ZIP**. The installer merges it by Dolphin texture filename and removes the matching PNG/DDS alternative, so the selected overlay wins. Later overlays win over earlier ones. A backup of the previous texture folder is retained. ZIPs containing conflicting duplicate texture hashes are rejected rather than relying on Dolphin's file-loading order. Only `tex1_*.png` and `tex1_*.dds` files are imported; archive scripts and executables are ignored. Packs tagged for a different disc region are rejected.

No widescreen or legacy “force 60 FPS” hack is enabled. I could not verify a complete widescreen solution compatible with this setup; stretching/cropping the HUD would undermine the default configuration. The newer optional 60 FPS mode installs both codes its author requires.

## Existing Dolphin and saves

The installer prefers an installed Dolphin Flatpak, then `dolphin-emu`, then a single Dolphin AppImage in `~/Applications` or `~/.local/bin`. If none is found, it offers Flathub installation or selection of an existing executable. No sudo or SteamOS filesystem changes are required.

Everything managed by this installer lives in `~/.local/share/gauntlet-deck/`. Dolphin receives `--user` pointing to this dedicated profile. Your global Dolphin settings, EmuDeck configuration, source ROM, and existing saves are not edited. The installer adds three application-menu entries and a desktop game launcher.

Use **Settings → Import copies of existing Dolphin memory cards / GCI saves**, then choose the **GC** folder from your previous Dolphin user directory. A previous dedicated GC folder is backed up before merging. Raw memory-card users should open the dedicated Dolphin profile and select the imported raw card in GameCube Slot A. New installations use a GCI-folder memory card.

If Steam was unavailable or would not exit cleanly, the game installation still completes. Sign in to Steam, close it if necessary, then use **Add Gauntlet to Steam** in the application menu. Existing shortcut files are backed up, unrelated shortcuts are preserved, and repeat installation updates the same launcher entry.

Logs: `~/.local/share/gauntlet-deck/gauntlet.log`. Controller detection: `controllers.txt`. Asset checksums: `app/assets.json`. Backups: `backups/`, with Steam shortcut backups beside Steam's `shortcuts.vdf`.

To remove the installation, first copy any saves you want from `user/GC`. Remove the Gauntlet entry in Steam, the three Gauntlet application-menu entries, the desktop game launcher, and the `gauntlet-deck` folder. The original ROM and global Dolphin install remain available.

## Command line and development

```sh
python3 gdl.py install --rom '/path/to/Gauntlet Dark Legacy.rvz'
python3 gdl.py install --cli --rom '/path/to/game.iso' --dolphin /path/to/dolphin-emu
python3 gdl.py install --cli --rom '/path/to/game.iso' --overlay '/path/to/CLOUD9.zip'
python3 gdl.py install --cli --rom '/path/to/game.iso' --no-patch
python3 gdl.py play --mode 60fps
python3 gdl.py settings
python3 -m unittest discover -s tests -v
python3 build_installer.py
```

`--root` changes the install location. `--cache` selects an already-downloaded cache, `--offline` prevents downloads, and `--no-steam` avoids Steam changes. `--no-textures` installs gameplay fixes without the HD download. CLI installs need `--rom` unless exactly one ROM is detected. Reinstalling preserves dedicated saves and backs up managed configuration; the recommended graphics/mode defaults are restored.

The installer and download/extraction/shortcut paths are tested with synthetic disc data and isolated directories. **Your provided USA Rev 1 disc successfully patched to Revision 1.3 with xdelta target checksums enabled**, and all 19,199 real HD textures extracted. The item timer and 60 FPS static hook locations are unchanged by the binary patch. See `VALIDATION.md` for exact checks and hashes. **No Steam Deck was available, so actual game boot, frame rate, and physical controller response remain unverified.**
