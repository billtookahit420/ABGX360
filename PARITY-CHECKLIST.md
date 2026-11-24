# abgx360 GUI — Option Parity Checklist (Step 1 deliverable)

Researched 2026-11-20 from primary sources, read as plain text only:

- **Original GUI source**: `abgx360gui/src/abgx360gui.cpp` (2,535 lines) from the
  hadzz/abgx360 tree (Bakasura "Reloaded" maintenance fork of Seacrest's
  abgx360 GUI v1.0.2 — same option set as the shipped GUI, plus the
  Quickstart tab). Every control, default, interlock and the exact
  command-line construction (`UIUpdate()`) were read directly.
- **CLI source**: `linux/abgx360/src/abgx360.c` v1.0.7 — the full built-in
  help text (usage block) was read directly and cross-checked against
  every flag the GUI emits.
- **Secondary**: ConsoleMods wiki + GBAtemp recommended-settings pages
  (agree with the source).

## Facts about abgx360 itself

- **Latest version: v1.0.7 [Hadzz Fork], released 2022-03-13.** Changes:
  internal URLs updated to `http://abgx360.hadzz.com` (no abgx360.ini
  needed for online functions); Video CRC recalculated with the new PFI
  during AutoFix. Last official release by the original author
  (Seacrest): CLI v1.0.6 (2012-01-03), GUI v1.0.2.
- **Where obtained**: https://abgx360.hadzz.com (download page,
  Windows/Linux/BSD), GitHub `hadzz/abgx360` (fork of
  `BakasuraRCE/abgx360`), GBAtemp download mirror. The Linux CLI is
  source-only (autotools) and must be compiled (gcc/autotools, libcurl).
  FreeBSD's port is at 1.0.7.
- **Verification database state**: the original abgx360.net/.cc database
  went down in late 2020, taking the stealth-file/verified-ini store
  with it. The community rebuilt it and Hadzz hosts the replacement at
  abgx360.hadzz.com. v1.0.7 talks to it natively; v1.0.6 needs a patched
  abgx360.ini pointing at it. The host was reachable from recomp-node2
  on 2026-11-20 (the GUI source tarball downloaded from
  abgx360.hadzz.com successfully). Whether live verification queries
  succeed end-to-end can only be proven by running the tool — **not yet
  done** (see BUILD-REPORT.md). App requirement stands: if the database
  is unreachable, say so in the open and still run every local check
  (stealth check, region, local CRC/ini checks all work offline;
  online verify + AutoFix downloads are the dependent parts).

## How the original GUI drives the CLI

It builds one command line: `abgx360 -<bundled short letters> <long
options> <input spec>`, shows it live in a read-only status field at the
bottom of the window, and launches it in a terminal (xterm on Linux) or
redirects stdout to the chosen HTML/Text output file. Our app reproduces
the same construction per queue item and shows the command in the item's
log/details.

## Parity table — every original GUI option

Defaults are the original GUI's shipped defaults (from the creation
code). "Bundled" = a letter in the `-xyz` bundle the GUI builds.

### Input section (top of window)

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Input type: File(s) / Directory / Burned DVD | File(s) | File(s): `-- "<file>"`; Directory: `--dir "<dir>"`; Burned DVD (Win): `--dvd <letter>` | Queue items are files or folder scans; a Burned DVD mode is offered — on Linux it takes a device path (e.g. /dev/cdrom) exactly as the original instructs ("Devices are files"), with writes auto-disabled |
| Disable Writes | off | bundled `w` (--nowrite); also forced on for Burned DVD input | Per-run checkbox in the run panel (same forcing rule) |
| Match Only: + mask + Select... | off, empty | `--match "<mask>"` (Directory input only; GUI prepends "," if the mask has no comma) | Filter field on Add Folder (same comma behaviour) |

### Program Output section

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Output: CLI Window / HTML File / Text File | CLI Window | HTML: bundled `h`; Text File: bundled `s` (strip colours); file modes redirect stdout to the output file | Per-item results view + raw log in-app (= CLI Window); HTML File and Text File output modes write the run to the chosen file |
| Output file path | empty | redirect target for HTML/Text modes | File picker next to the output mode |
| Maximize it | on | Win: `--max`; Linux: xterm geometry | App-side only: remembered window state (no CLI effect) |
| Open file when done | off | App-side: opens the HTML/Text output after a run | Same checkbox behaviour for file outputs |
| Use Terminal font characters | on | bundled `t` (--terminal) | Checkbox, same flag |

### Options tab

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Check/Create .dvd file | on | off → bundled `d` (--nodvdcheck) | Same checkbox (inverted flag) |
| Check Stealth | on | off → bundled `r` (--regioncheck: region only, NO stealth check) | Same checkbox; label keeps the original meaning clear |
| Verify if Stealth passes | on | off → `--noverify`; disabled unless Check Stealth is on | Same checkbox + interlock |
| Check/Fix Video padding | off | bundled `p` (--padding) | Same checkbox |
| Show Avatar Awards | off | `--aa` | Same checkbox |
| Use colors | on | off (or Text File output) → bundled `s` (--stripcolors) | Same checkbox; our log view renders colours either way, raw log keeps them |
| Verbosity Level: Low / Medium / High | Medium | Low → bundled `n` (--noverbose); High → bundled `v` (--verbose); Medium → neither | Same 3-way choice |
| Check for AnyDVD style game data corruption | off | bundled `c` (--corrupt); force-disabled when Game CRC = never | Same checkbox + interlock |
| Display ISO Filesystem | off | `--showfiles` | Same checkbox |
| Check for updates | on | off → `--noupdate`; forced off by Disable-all-online | Same checkbox + interlock |
| Include the CSV | off | `--csv`; only enabled when Check for updates is on | Same checkbox + interlock |
| Disable all online functions | off | bundled `o` (--stayoffline) | Same checkbox + interlock |
| Check Game Partition CRC when needed | on | off → bundled `g` (--nogamecrc = never) | Same checkbox |
| Recurse subdirectories when using Directory Input | off | `--rec` with `--dir` | Our Add Folder scan is recursive by design; the checkbox is kept and maps to scan depth + `--rec` on folder items |
| Show Achievements | off | `--ach` | Same checkbox |
| Hide secret ones | off | with Show Achievements → `--achs` instead of `--ach` | Same sub-checkbox |

### Manually Patch or Extract Files tab

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Patch even if stealth passes | off | `--patchitanyway` | Same checkbox |
| Patch even if these files are invalid | off | `--patchgarbage` | Same checkbox |
| Patch Video + file | off | `--p-video "<file>"` | Same checkbox + file picker |
| Patch PFI + file | off | `--p-pfi "<file>"` | Same |
| Patch DMI + file | off | `--p-dmi "<file>"` | Same |
| Patch SS + file | off | `--p-ss "<file>"` | Same |
| Overwrite these files without prompting | off | `--clobber` | Same checkbox |
| Extract Video + dest file | off | `--e-video "<file>"` | Same checkbox + save picker |
| Extract entire video partition (253 MB) | off | with Extract Video → `--e-videopartition "<file>"` instead | Same sub-checkbox |
| Extract PFI + dest | off | `--e-pfi "<file>"` | Same |
| Extract DMI + dest | off | `--e-dmi "<file>"` | Same |
| Extract SS + dest | off | `--e-ss "<file>"` | Same |
| (note in original: extraction happens before patching when both are chosen) | — | CLI behaviour | Same note shown |

### AutoFix tab

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| AutoFix Threshold: Level 3 / 2 / 1 / 0 | Level 2 | L3 → `--af3`; L2 → (default, no flag); L1 → `--af1`; L0 → `--af0` | Same 4-way choice with the original's full level descriptions |
| Trust SS v2 angles | on | off → `--notrust` | Same checkbox |
| Adjust SS v1 angle 359 for iXtreme < v1.4 | off | bundled `x` (--fixangle359) | Same checkbox |
| Fix C/R Table if data is invalid | on | off → `--nofixdrt` | Same checkbox |
| Adjust angles that deviate more than [0–13] degrees from their CCRT targets | on, 3 | off → `--nofixdev`; on with value ≠ 3 → `--dev <value>`; value 3 = CLI default, no flag | Same checkbox + value choice |

### Rebuilding tab

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Default Method | selected | (no flag; needs 7–7.5 GB free) | Same radio |
| Low Disk Space Method | — | bundled `l` (--rebuildlowspace; 253 MB, corrupts ISO if it fails midway) | Same radio |
| Don't rebuild | — | bundled `b` (--norebuild) | Same radio |
| Don't delete the original ISO after rebuilding | off | bundled `k` (--keeporiginaliso); disabled unless Default Method | Same checkbox + interlock |

### Misc tab

| Original option | Default | CLI / behaviour | In our GUI |
|---|---|---|---|
| Your console's region code + Select... dialog | empty | `--rgn <code>` when non-empty (hex, up to 8 chars; multiple regions allowed; e.g. 000000FF NTSC/U, 00FE0000 PAL) | Same field + a region-picker dialog reproducing the original's Select... |
| Preferred Language (12 languages) | English | non-English → `--lang <n>` (1=English … 12=Russian) | Same choice |
| SplitVid: Add it if it doesn't exist or isn't valid / Remove it if it exists / Leave it the way it is | Leave it | Add → `--splitvid`; Remove → `--removesplitvid`; Leave → none | Same 3-way choice |
| Images: Extract when using HTML output / Extract always / Don't extract | when HTML | when-HTML + HTML output, or always → bundled `i` (--images) | Same 3-way choice |
| Embed them in HTML | off | `--embed`; disabled when Images = Don't extract | Same checkbox + interlock |
| Extra command line options (free text) | empty | appended verbatim before the input spec | Same field |

### App-side features of the original with no CLI flag (reproduced in our app layer)

- **Settings presets** (File menu): Save Settings… (Ctrl+S), Load
  Settings… (Ctrl+L), Delete Settings… (Ctrl+D). A preset named
  "Default" auto-loads at launch. Every option above persists (the
  original's full saved-key list was captured from source).
- **Recent input history**: Reopen File(s) / Reopen Directory submenus
  with Clear History.
- **Quickstart tab**: 9 help topics — Welcome; How to change the
  default settings or create preset settings; How to check/fix an ISO
  or create a .dvd file; Angle Deviation and You; To SplitVid or not
  to SplitVid; What is AnyDVD style corruption?; Is there such a thing
  as a "bad kreon rip"?; What is SS v2?; Where are my StealthFiles and
  Images stored?
- **Help menu**: official site link; "Where is my StealthFiles
  folder…" (Ctrl+F); "Where is my Images folder…" (Ctrl+I); About.
- **Live command-line preview** in the bottom status field (hidden if
  the command contains --user/--pass). Ours: the exact command is shown
  per queue item before/while it runs.
- **Interlocks** (all reproduced): offline ⇒ updates off; updates off
  ⇒ CSV off; stealth off ⇒ verify off; Game-CRC-never ⇒ corruption
  check off; Low-space/Don't-rebuild ⇒ keep-original off; Images=never
  ⇒ embed off; DVD input ⇒ writes disabled.
- **`--pause`** (appended by the Windows GUI for CLI-Window output) is
  a console "press any key" behaviour, not a checking option — our
  integrated log/results view makes it moot; noted here for
  completeness.

### CLI flags the original GUI does NOT expose (reachable via Extra Options; listed so nothing is silently lost)

`--pL0` (with `-p`, enables fixing XGD2 L0 zero padding — the guides'
recommended extra option), `--gamecrc` (always check Game CRC),
`--localonly` (verified files from the local StealthFiles folder only —
the GUI's code for it is commented out upstream), `--skiplb`,
`--truncate <size>`, `--retries <n>` (default 20), `--nettimeout <secs>`
(default 20), `--dvdtimeout <secs>` (default 20), `--devkey`, `--help`.
