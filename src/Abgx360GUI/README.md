# abgx360 GUI

A batch front-end for **abgx360** (by Seacrest), driving the
**v1.0.7 [Hadzz Fork]** CLI. For people who hate the command line:
add ISOs (or a whole folder, or a burned DVD), choose from the
same options the original abgx360 GUI v1.0.2 offered — all of
them, organised the same way — and run the queue.

What it adds over the original GUI:

- a **queue** (Add Single ISO / Add Folder / Add Burned DVD),
  processed in order, one abgx360 run per item;
- a **parsed results view** per item (per-check PASS/FAIL) next to
  the **full raw log**;
- a **status bar** that narrates every phase (first-run setup,
  scanning, checking, batch summary) — no silent phases;
- the **live command-line preview** the original showed, here per
  queue item.

Everything else is parity: Options / Manually Patch or Extract /
AutoFix / Rebuilding / Misc / Quickstart tabs, settings presets
(File menu, Ctrl+S/L/D — a preset named "Default" auto-loads at
launch), recent input history, the region and match-mask picker
dialogs, and every interlock (offline ⇒ no updates ⇒ no CSV,
stealth off ⇒ verify off, and so on). CLI-only flags the original
GUI never exposed (`--pL0`, `--gamecrc`, `--localonly`,
`--retries`, ...) go in Misc > Extra command line options.

## First run

The GUI runtime is bundled (AppImage) or installed by the
launcher (.bat/.sh). The **abgx360 engine is not bundled**: on
first run the app downloads the hadzz/abgx360 source and builds
the CLI into a per-user folder (`~/.local/share/abgx360-gui/
engine` on Linux), showing progress in the status bar. Later
runs find it and skip straight to Ready. Building needs a C
compiler plus the libcurl and zlib development files; if they
are missing, the app offers to install them for you (one
password prompt on Debian/Ubuntu-family systems) or names the
exact packages and command so you can install them yourself.

Online verification and AutoFix downloads use the community
database at abgx360.hadzz.com (the original abgx360.net database
died in 2020; v1.0.7 points at the replacement natively). If the
database is unreachable, turn on "Disable all online functions"
— every local check (stealth, region, CRCs against local
StealthFiles) still runs.

## Network shares

ISOs kept on a home server can be checked in place — no copying
to a local disk first. The **Network Share...** button above
the queue takes a server (e.g. `192.168.0.102`) and a share
name, then lets you pick ISO files or a whole folder from the
share. Recent shares are remembered for next time, and once a
share is connected the other file dialogs (patch/extract files,
HTML/Text output) open on it too.

- **Windows:** the share is used through its UNC path
  (`\\SERVER\share`). You can also type a UNC path directly
  into any file dialog.
- **Linux:** the share is mounted through **GVFS**
  (`gio mount smb://SERVER/share`), which makes it a real
  folder abgx360 can read. GVFS ships in the `gvfs-backends`
  package; if it is missing the app says so and names the
  package. If the server asks for credentials, fill in the
  dialog's User / Password / Domain fields — the app answers
  gio's prompts itself (the username is remembered with the
  share; the password never is). Mounting the share in your
  file manager first also works.

## Archive input (.zip / .7z)

Add Single ISO also accepts `.zip` and `.7z` archives — from a
local disk or straight off a network share. The disc image
inside is extracted to **local** scratch (the `extracted`
folder in the app's data folder) and checked from there; the
queue row keeps showing the archive you picked. The archive
itself is only read, never modified, and extraction never
happens on a share. If an archive holds several disc images,
the largest is extracted. Re-adding the same archive reuses
the extraction; delete the `extracted` folder's contents to
reclaim disk space. `.zip` support is built in; `.7z` uses
py7zr (in `requirements.txt`, bundled in the AppImage) or a
system `7z` command if present.

## Windows

The Windows package is this same source tree with
`abgx360-gui.bat` as the first-run launcher. The GUI runs on
Windows, but it drives a **prebuilt abgx360.exe, which is not
bundled**: download abgx360 v1.0.7 from
http://abgx360.hadzz.com and place `abgx360.exe` in the engine
folder the app names on first run
(`%LOCALAPPDATA%\abgx360-gui\engine`). The Windows path has not
been executed by the build fleet (Linux-only) — the first
Windows run is the real test.

## AppImage note

On a system without libfuse2, run the AppImage with
`--appimage-extract-and-run`. On a desktop with libfuse2 it runs
directly.

## Credits

abgx360 and abgx360 GUI by Seacrest. v1.0.7 fork by Hadzz;
GUI maintenance fork ("Reloaded") by Bakasura. This front-end
is an unofficial wrapper.
