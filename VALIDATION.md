# Validation

October 17, 2026. Development host: x86-64 Linux. Steam Deck hardware was not attached.

## Real files

- Supplied source: `Gauntlet - Dark Legacy (Revision 1).iso`.
- Parsed GameCube ID: `GUNE5D`, disc revision `1`.
- Source size: `1,459,978,240` bytes.
- Source SHA-256: `00c8d64167fddf6a20a1e189de4cc72619d6cc03cf78d5e587015a14113cf81d`.
- Applied the creator's `Rev1-to-Rev13.xdelta` using official xdelta3 3.2.2 with target checksum verification enabled. Exit status 0.
- Patched output SHA-256: `e4729234c8c6463daa8828b597897c29976c21b767452e60abac0bd6516c265c`.
- Downloaded HD GC archive: `2,147,869,113` bytes; SHA-256 `2667195680ef70e09c3e6761d1458a9302fd069defb19cb770c1e650be8c7572`.
- Extracted **19,199** texture files, with no duplicate hash filenames or unsafe archive entries.
- All pinned patch, tool, and code download SHA-256 values verified against `assets.json`.
- Compared original/patched DOL sections at all direct static writes/hooks in the default item timer and optional 60 FPS AR+Gecko code pair. No differences at those locations. This is a static compatibility check, not a behavioral test.
- Optional character reset code uses a code cave whose filler bytes differ between original/patched DOL; this code remains disabled by default. Inventory code and intro-skip hooks are unchanged; those also remain disabled by default.

## Automated checks

`python3 -m unittest discover -s tests -v`: 15 tests pass.

Covered wrong game/NKit rejection; texture traversal, symlink, region and duplicate rejection; deterministic PNG/DDS overlay replacement; verified cache/offline behavior; download restart when byte ranges are ignored; correct 60 FPS AR+Gecko activation; mixed-controller per-name device indices; Flatpak runtime selection; preservation of manual mappings; byte-preserving Steam shortcut parsing, backup and idempotent updates; malformed shortcut refusal; active Steam account selection and per-game template seeding; isolated installation and launcher arguments with a synthetic disc and test emulator executable.

Both self-contained launchers are built from the same embedded source payload, including the SDL probe. The probe is compiled with warnings enabled. The standalone installer contains no ROM or texture archive. The separate personal transfer kit carries the supplied ROM and verified download cache.

The self-extracting `.run` installer was also executed in full offline mode with the real supplied ROM and verified cached assets, an isolated HOME, and an emulator detection stub. It exited 0, installed Revision 1.3 and all 19,199 textures, and created the dedicated profile and launchers. Steam writes were disabled in this end-to-end test. This validates installation, not actual emulation. The `.desktop` Exec command's extracted payload also passed a command-line smoke test, and `desktop-file-validate` accepted the standalone desktop entry.

Additional tests cover priority of a ROM beside the personal-kit launcher over other library copies, and execution-tool extraction to the install drive rather than potentially read-only/noexec transfer media.

## Remaining checks on the Deck

- Boot into actual gameplay, verify HD textures visually, and play through patched inventory behavior.
- Test built-in controls and the intended external controllers in Gaming Mode, including each co-op port.
- Measure frame pacing and temperature/power behavior; optional 60 FPS is not a performance guarantee.
- Verify the Steam-provided local controller template is selected by the installed Steam client. A Gamepad template can be selected in Steam if required.
