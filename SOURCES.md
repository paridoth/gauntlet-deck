# Sources and compatibility notes

Researched October 17, 2026. Assets are downloaded from their creators' sources at installation time. ROMs are never downloaded. This installer does not redistribute the texture pack, game assets, or third-party patch/code files.

| Project | Creator / source | Integration |
|---|---|---|
| Gauntlet Dark Legacy HD 2.0 | [DannyKhan419 announcement](https://www.reddit.com/r/gauntlet/comments/k9dhh0/gauntlet_dark_legacy_hd/) · [creator's download folder](https://drive.google.com/drive/folders/1dXaSzAdqoOiT7GjuD3S309p5QsjT5MJD) | GC ZIP only, file ID `1zhLTYNhxg3XrXG_fDkZHvMYrzT4uBwzm`; 2,147,869,113 bytes; 19,199 texture files |
| Unofficial Revision Patch | [CyberNomadic repository](https://github.com/CyberNomadic/GDL_Patch) · [Revision 1.3 release](https://github.com/CyberNomadic/GDL_Patch/releases/tag/patch13) | Separate Rev 0 and Rev 1 xdelta patches; USA only. Source repository declares GPL-3.0. |
| Gameplay codes | [Vizyne repository](https://github.com/Vizyne/Gauntlet-Dark-Legacy---Game-Codes-by-Vizyne) | Pinned commit `085fdcc725b98fce51bc0d0426354659fd3ef7f4`; author targets USA Rev 1 and explicitly recommends CyberNomadic's patch for the item timer. No blanket license was found; files download directly from author sources. |
| xdelta3 | [jmacd/xdelta](https://github.com/jmacd/xdelta) · [v3.2.2 release](https://github.com/jmacd/xdelta/releases/tag/v3.2.2) | Official Linux x86-64 archive, SHA-256 pinned. Executed with target checksum validation; no `-n` bypass. Version identifies Apache-2.0. |
| Dolphin | [Official source](https://github.com/dolphin-emu/dolphin) · [Flathub packaging](https://github.com/flathub/org.DolphinEmu.dolphin-emu) | Reuses installed emulator or installs the Flathub build. Checked source for CLI conversion, user profiles, graphics enum values, memory-card type, SDL names, and per-name device numbering. |
| Steam Deck gamepad template | Valve template already installed with Steam | Copied only to this new shortcut's local override if no override exists. No templates from other games are changed. |

## Optional TheZac texture overlays

These are alternatives/additions, **not all enabled at once by default**. Obtain your desired ZIPs from their creator pages and import through Settings. ModDB's site rejected automated fetching during research, so automatic download is not claimed. These files are marked proprietary by their creator; none are bundled here.

- [Zac's Improved Sky Dominion 1.3](https://www.moddb.com/mods/texture-packs-for-gauntlet/addons/zacs-improved-sky-dominion-13): skies representing different times of day; 3,822,950 bytes; published MD5 `953450ed2159eeb1e534f03a391da3b9`.
- [Cloud 9 v0.137](https://www.moddb.com/mods/texture-packs-for-gauntlet/addons/cloud-9-v0137-arcade-cloud-9-textures): restores Arcade Cloud 9 backgrounds; 956,579 bytes; published MD5 `51f6c88cefc3f0f86d66b33fd324a78b`.
- [Creator's complete addon collection](https://www.moddb.com/mods/texture-packs-for-gauntlet/addons): also lists Mountain Orcs (Red), Playable Province General (Black), Forsaken Province Zombies (Black), White Death, and Hammy the Hamster. Their texture hashes can replace the HD equivalents, so choose the appearance you prefer.
- [Creator's individual texture files](https://www.moddb.com/mods/texture-packs-for-gauntlet/downloads).

## Deliberately optional or excluded

- Vizyne 60 FPS: both AR and Gecko components are required; 300% emulated CPU recommended. Known issues are documented in the author's `$60 FPS - No Game Speedup [Vizyne].txt` and repeated in the README. No Deck benchmark was available.
- Vizyne inventory-name/delay code: installed but disabled because it overlaps inventory behavior already changed by the binary patch. Do not assume every combination has been gameplay-tested.
- Vizyne character reset/stats: installed but disabled because reset changes saved character progression. The author documents a confirmation in the game's character selector.
- Intro skip: installed but disabled so the default retains the game's opening presentation.
- Other old 60 FPS/overclock and generic widescreen codes: not stacked; no reliable complete compatibility evidence was established.
- Native PC rewrite/decompilation experiments: outside this Dolphin installation and not substituted for the emulator the user requested.

Downloading exact known files and verifying their checksums establishes integrity, not a full playthrough. The user's supplied USA Rev 1 disc was successfully patched with xdelta target checksums enabled. The default item timer and optional 60 FPS static hook/write locations were compared against the original DOL and are unchanged by the binary patch. All 19,199 HD textures were extracted successfully. Visible coverage of modified game assets, region-specific texture coverage, and actual Deck gameplay still need testing in the emulator.
