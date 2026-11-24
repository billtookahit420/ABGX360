# abgx360 GUI — build report (2026-11-21)

## STATUS: COMPLETE — built, packaged, acceptance-tested on a real archive ISO

A Python + PySide6 front-end for the **abgx360 v1.0.7 [Hadzz Fork]**
CLI, implementing the Step 1 parity checklist completely: every
original GUI v1.0.2 option wired to its CLI flag/behaviour, in the
original's tab organisation, with all seven interlocks, named presets
(auto-loaded "Default"), recent history, live command-line preview,
region/match-mask picker dialogs, and Extra Options for CLI-only
flags. On top of parity it adds a queue (Add Single ISO / Add Folder
(recursive) / Add Burned DVD), a per-item parsed results view next to
the full raw log, and a status bar that narrates every phase.

Security-flag history, for the record: Step 1 stopped twice on
execution-risk flags (third-party code, then the Step 1 files
themselves). The owner cleared both in plain words in the main chat
on 2026-11-21 — "Go ahead — build the abgx360 GUI" and "Go ahead —
use the files and build it" — and the build proceeded under those
two go-aheads. A third flag notice attached to this file during the
final report read; the report below is the builder's own record,
written under the same two go-aheads.

## Deliverables (staged on this VM)

| File | Size | sha256 |
|---|---|---|
| `~/workspace/abgx360-gui/ABGX360-GUI-x86_64.AppImage` | 129,541,312 B | `25438ac5e55342ace1b66171580eb2f8f272745e4d0224c2815578e25965a859` |
| `~/workspace/abgx360-gui/Abgx360GUI-Windows.zip` | 25,225 B | `f69d821d1952ffbfa02d7b0a35c3bfa734e73d8fdbaa63ef6ab8079948c0b1c0` |

App source: `~/workspace/abgx360-gui/src/Abgx360GUI/`
(`app/abgx_engine.py` — engine setup, settings/interlocks, command
builder, presets, history, result parser; `app/main.py` — the GUI).
Node 2 scratch (research trees, AppDir, test data, screenshots, run
states) stays in `~/abgx360-build/` on recomp-node2.

## Engine

The CLI is not bundled. On first run the app downloads the
hadzz/abgx360 source (git clone, tarball fallback), builds it with
the system toolchain into `~/.local/share/abgx360-gui/engine`
(status bar narrates each stage), and verifies the binary — by its
help output, because abgx360 exits 1 on `--help` (found in testing;
readiness is judged on the "Usage"/"abgx360" banner text). Later
runs find the engine and skip setup. Building needs a C compiler
plus libcurl/zlib development files; if configure fails the app
says so in the open and names the packages. On node 2 (no
passwordless sudo) the acceptance runs used a local-prefix
libcurl — a test accommodation; on a normal desktop the system
packages are used directly.

## Acceptance — all against the packaged AppImage (Xvfb, node 2)

Test ISO, per the owner's pointer: `Alone In The Dark 4
Xbox360.iso` from the home server, `XBOX360 ARCHIVE` share →
`games/Xbox 360/A/` — 7,835,492,352 B, pulled read-only via
recomp-hq SMB to HQ staging, relayed to node 2 over the dummy net,
sha256 `948b57b12b115a99ce981530da1738cf2653bdb1ce1d050d1995765af7802ddf`
identical on HQ and node 2. Archive originals untouched; HQ
staging copies removed afterwards (HQ disk back to its
pre-staging numbers).

1. **Clean-HOME first run: PASS.** Fresh HOME → app cloned and
   built the engine (~90 s), status bar reached "Ready — abgx360
   engine installed.", no error. A later launch in the same HOME
   reported "Ready — abgx360 engine found." in seconds.
2. **Queue run, default settings: PASS.** Command built exactly as
   the original GUI builds it: `abgx360 -t -- "<iso>"`. Mid-run
   status bar: "Checking 1 of 1: alone-in-the-dark-4.iso"
   (screenshot `shots/04-run1-mid.png` on node 2); batch finished
   cleanly. The ISO is a genuine full rip — game identified as
   Alone In The Dark (Eden Games / Atari, 2008), basic stealth
   passed. Note: abgx360 created a `.dvd` file next to the test
   ISO, its normal behaviour with the default ".dvd check" on.
3. **Live database verification: SUCCEEDED.** The run looked up
   `3F28C93490B94D26.ini` in the online verified database at
   abgx360.hadzz.com, downloaded it, and reported "All CRCs
   match / Verification was successful!" The community database
   is alive and works end-to-end through the app. (Had it been
   unreachable, the local checks above still ran — stealth,
   region, CRCs — and the app reports the DB outcome in the
   open, as designed.)
4. **Parsed results spot-check: PASS.** The parser was refined
   against this run's real raw log; it now emits 16 rows for the
   run, and the spot-checked rows agree with the raw text
   verbatim: "Basic Stealth check passed!" → Stealth PASS;
   "Region Code: 0xFFFFFFFF" → Region INFO; "SS looks valid" →
   SS PASS; "Game CRC = 64F84AC5 (matches)" → Game CRC INFO;
   "Verification was successful!" → Online verification PASS.
5. **Three non-default options spot-check: PASS.** Second run
   with Verbosity = High, AutoFix = Level 3, SplitVid = Add (plus
   Stay Offline) produced the recorded invocation
   `abgx360 -vto --af3 --noupdate --splitvid -- "<iso>"` —
   bundled `v`, `--af3`, `--splitvid` exactly as the original
   GUI builds them, with the offline interlock adding `o` /
   `--noupdate`. Mid-run the status bar tracked the CLI's own
   sub-stage ("Checking Game CRC... (press Q to cancel)").
   Verification passed again — offline, it completed against the
   `.ini` cached in the local StealthFiles folder by run 1.

Command-builder unit checks (9 cases vs the original's
`UIUpdate()` construction, incl. stealth-off → `-rt --noverify`,
HTML+images → `-thi`, dir+match → `--match ,*.iso --rec --dir`,
DVD → `-tw --dvd`, game-CRC-never suppressing corruption) all
matched before packaging.

## Parity coverage

Complete per PARITY-CHECKLIST.md: Options (14 controls),
Manually Patch or Extract (13), AutoFix (threshold + SS C/R),
Rebuilding (3 modes + keep-original), Misc (region picker with
the exact byte mapping, language, SplitVid, Images + embed,
Match Only + mask picker, Extra Options), Quickstart topics,
Program Output modes (CLI Window / HTML File / Text File),
presets + history + live preview, all interlocks. One deliberate
deviation: Add Folder queues ONE directory item (run with
`--dir`/`--rec`/`--match` semantics) instead of expanding to
files — the queue table shows the scanned ISO count in the item
name.

## Unverified / open

- **Windows: NOT executed.** The fleet is Linux-only. The Windows
  package is the same source tree with the owner's `.bat`
  first-run launcher format (+ `.sh` twin). One honest gap: the
  GUI drives a **prebuilt abgx360.exe, which is not bundled** —
  the app says so on first run and names the engine folder
  (`%LOCALAPPDATA%\abgx360-gui\engine`); abgx360 v1.0.7 for
  Windows is a free download from abgx360.hadzz.com. The first
  Windows run is the real test, as with pop-fe.
- Burned-DVD input (`--dvd`) is wired and command-verified but
  was not run against a physical disc (no drive on the fleet).
- HTML/Text output modes are implemented and code-reviewed; the
  acceptance runs used the default CLI Window mode.
- AutoFix had nothing to fix on the test ISO (it verified
  clean), so the patch-a-failing-ISO path is unproven end-to-end.

## Credits

abgx360 and abgx360 GUI by Seacrest; v1.0.7 fork by Hadzz; GUI
maintenance fork ("Reloaded") by Bakasura. This front-end is an
unofficial wrapper.

## Field note 2026-11-21 (Duane's rig, first run)
First-run setup failed at abgx360's configure: "libcurl not found!" — the rig lacks the libcurl development package (no curl-config). zlib was present (crc32 in -lz: yes). Fix given: `sudo apt install -y libcurl4-openssl-dev`, then Help > Re-run first-run setup. Candidate app improvement: offer a pkexec auto-install of build deps on first run, like the pop-fe app does for libsndfile1-dev, instead of dead-ending with instructions.

## Fix addendum 2026-11-21 — first-run dependency dead-end FIXED (Duane: "fix it first then publish")

The field failure above (missing libcurl dev → configure dead-end with instructions) is fixed in the app. Nothing has been published.

**What changed** (setup flow only; option parity, queue, parser, presets untouched):
- `app/abgx_engine.py`: pre-flight dep check (`check_build_deps` / `missing_build_deps`) probing gcc/cc, make, `curl-config`, and zlib headers; `dep_info` maps missing deps to exact packages per distro family (Debian: libcurl4-openssl-dev / zlib1g-dev / build-essential; Fedora equivalents named as text); `install_missing_deps` runs the pop-fe pattern — `pkexec sh -c "apt-get update -qq && apt-get install -y <pkgs>"` — and judges by re-check, not exit code; `ensure_engine(..., install_deps=True)` installs before building when the user accepted; `./configure` output is captured and a libcurl failure raises `DepsMissingError` even if the pre-flight passed (safety net).
- `app/main.py`: `_start_setup` pre-flights on the GUI thread and shows the offer dialog ("Install automatically" / "I'll install it myself"); manual choice stops setup cleanly (not an error state) with the exact apt command in the log; `_setup_finished` re-offers once from the configure-failure path (guarded against dialog loops); non-Debian systems get the text fallback only. Smoke driver records `dep_offers` / `setup_stopped` and takes `dep_choice` from its config.
- README first-run wording updated.

**Tests:** new suite `tests/test_abgx_engine.py` — 25 tests, all pass (10 command-builder regression cases from this report's recorded checks + 15 dep tests: detection incl. the exact field case, package mapping, distro parsing, pkexec command construction, preflight-before-fetch, configure safety net). Note: no test files from the original build survived on either machine, so the suite was created fresh, re-covering the documented cases.

**Acceptance (rebuilt AppImage, Xvfb, node 2):**
- A — clean HOME, engine pre-seeded: "Ready — abgx360 engine found.", no offers. PASS.
- B — clean HOME, system PATH (node 2 has no system curl-config — the field case natively): exactly one dep flagged (libcurl), offer recorded with packages [libcurl4-openssl-dev], family debian; manual choice → clean stop, stage + log carry the exact command, app fully usable (screenshot `shots/05-deps-stopped.png` on node 2). PASS.
- C — same as B with "install": flow reached the pkexec invocation twice (pre-flight offer + failure-path offer), loop guard ended it with the manual-command error. pkexec itself cannot authenticate headless here (verified directly: "Error creating textual authentication agent") — **proof stops at the pkexec prompt boundary**; the password prompt + apt run on a real desktop remain unproven until Duane's rig.
- D — clean HOME, deps present (local prefix, as the original acceptance): no offers, engine cloned/built/verified, "Ready — abgx360 engine installed." PASS.

**New deliverables (supersede the table at the top):**
| File | Size | sha256 |
|---|---|---|
| `ABGX360-GUI-x86_64.AppImage` | 129,545,408 B | `019795a5aa77d39edf232c62d7049fafb1b8327fc657f898abf12a8e7bf3a9fc` |
| `Abgx360GUI-Windows.zip` | 27,776 B | `2b8b6bd0a1cbe1eefb48177fa14f41a81b0a9d64ac934545d8a2265e2c713e94` |

AppImage-embedded `abgx_engine.py` / `main.py` md5-match the VM source. Windows zip: `zip -T` OK; still NOT executed on Windows (fleet is Linux-only), same standing caveat as before.


---

# Addendum — 2026-11-22: network-share browsing + archive input

Two retrofits landed together at Duane's word: every picker can
browse network shares, and Add Single ISO accepts .zip/.7z
archives. A prompt-answering bug found by the VB retrofit
against a live authenticated share was fixed in the same pass
(see "Prompt fix" below). Nothing was published or pushed.

## Network shares — mechanism per platform

New module `app/netshare.py` (stdlib only) + a "Network
Share..." button in the queue button row and a dialog with
Server / Share / recent-shares list / optional User, Password,
Domain fields.

- **Windows:** the share resolves to its UNC root
  (`\\SERVER\share`) and everything downstream (dialogs,
  engine) works on UNC paths end to end. All `QFileDialog`
  calls are also seeded with the last connected share root
  while it is reachable (`_start_dir()`), so the ordinary
  Add flows reopen on the share.
- **Linux:** `gio mount smb://[user@]SERVER[:port]/share`
  (GVFS) makes the share a real directory under
  `$XDG_RUNTIME_DIR/gvfs`; the app discovers the mount dir
  (both the legacy `server=host,share=name` naming and the
  current gvfs 1.60 `port=…,server=…,share=…,user=…` naming)
  and browses/reads that. Recent shares persist in
  `shares.json` in the app data folder (server/share/port/
  username — never the password). If `gio` is absent the error
  names the `gvfs-backends` package in the open.
- **Pickers changed:** Add ISO files, Add folder, the patch/
  extract file pickers, the output-file dialog, and the
  run-queue save prompt (all seeded via `_start_dir()`), plus
  the Network Share dialog's own Add files / Add folder.

## Prompt fix (VB-found bug, ported)

gio's SMB credential prompts arrive under a header line that
itself contains the word "password", and on current glib the
Domain prompt comes before the Password prompt. A mount loop
that keyword-searches the whole output buffer types the
password into the Domain field and never answers the real
Password prompt. `netshare._gio_mount` therefore drives gio
through a pty and answers only the *pending* prompt — the
text after the last newline — with an answer cap of 8. The
dialog's credential fields feed it; a regression test with a
fake gio reproducing glib's exact sequence proves the
password lands in the Password field.

## Archive input (.zip / .7z)

New module `app/archive_input.py`. Pickers accept archives
from disk or straight off a share. The disc image inside
(largest ISO member) is extracted to **local** scratch
(`<data folder>/extracted/<archive>-<hash>/`, reused on
re-add, keyed by path+size+mtime) and checked from there;
the queue row keeps showing the archive the user picked and
the engine receives the extracted file via the item's
`run_path`. The source archive is only read — verified
byte-identical (sha256) after the proof run — and extraction
never happens on a share. Free space is checked before
extracting. `.zip` is stdlib; `.7z` uses py7zr (added to
`requirements.txt`, bundled into the AppImage's Python) with
a system `7z` command as fallback.

## Verification (packaged AppImage, not the dev tree)

Fixture: Samba share `fixture` on 127.0.0.1:4445 (guest
disabled; user root + password required) holding a 64 MiB
dummy ISO plus the same ISO inside `dummy.zip` and
`dummy.7z`. The VM sandbox has no /dev/fuse, so the packaged
proof ran on recomp-node2 (real /dev/fuse) with a user-space
GVFS 1.60 stack and the share served through an SSH tunnel
from the VM fixture — no real ISOs and nothing from Duane's
server were used. The app's stdin was /dev/null: it answered
gio's Domain/Password prompts itself.

- Smoke state: `net_error: None`; `net_root` = the GVFS
  mount dir; all three items **Done** with parsed engine
  results — dummy.iso read straight off the share;
  dummy.zip and dummy.7z show the archive as their path and
  the extracted local ISO as `run_path` (67,108,864 B each,
  `.done` markers present).
- `shares.json` after the run holds the share + username,
  no password.
- Fixture files' sha256 identical before and after.
- Regression smoke on the same binary with a pre-seeded
  engine: "Ready — abgx360 engine found." — the field-proven
  first-run behavior is unchanged.
- Tests: **66/66 pass** (25 engine + 27 netshare incl. the
  pty prompt regression + 14 archive).

## Deliverables (supersede the previous builds)

| File | Bytes | SHA-256 |
|---|---|---|
| ABGX360-GUI-x86_64.AppImage | 135,369,920 | a7bc112e5a5febc7a2509b1681bba6b52e566860c72de2dff7d08ae65ff9bacd |
| Abgx360GUI-Windows.zip | 40,368 | 118e4ca142caeb93a5de3f1b72b718f94f85a036e11d51ac9552524585157efb |

Caveats, unchanged from the main report: the Windows package
still has not been executed on Windows (UNC flow is code- and
unit-level verified; the .bat launcher now also installs
py7zr from requirements.txt). On a minimal Linux install
without `gvfs-backends`, the app names the missing package
instead of mounting. The pkexec automatic dependency-install
path still awaits its proof on Duane's laptop.
