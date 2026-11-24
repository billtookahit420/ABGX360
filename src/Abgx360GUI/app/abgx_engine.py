"""abgx360 GUI -- engine layer.

Owns everything that is not widgets:

* finding / fetching / building the abgx360 CLI (first-run setup,
  Recomp Tools style: the engine lives in a per-user folder, is
  downloaded and built on first run, and is reused after that);
* the settings model -- every option of the original abgx360 GUI
  v1.0.2, with the original's shipped defaults;
* command construction that reproduces the original GUI's
  UIUpdate() exactly (bundled short-option order, long-option
  order, interlocks applied first);
* running one queue item and streaming its output;
* parsing a run's output into per-check results.

abgx360 v1.0.7 [Hadzz Fork] -- https://github.com/hadzz/abgx360
Original tool and GUI by Seacrest.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
# AppRun / the .bat launcher point these at a per-user folder;
# unpackaged (dev) runs fall back to folders beside the app.
ENGINE_DIR = Path(os.environ.get(
    "ABGX360_GUI_ENGINE_DIR", str(APP_DIR / "engine")))
DATA_DIR = Path(os.environ.get(
    "ABGX360_GUI_DATA_DIR", str(APP_DIR)))
PRESETS_DIR = DATA_DIR / "presets"
HISTORY_PATH = DATA_DIR / "history.json"
WINDOW_PATH = DATA_DIR / "window.json"

REPO_URL = "https://github.com/hadzz/abgx360.git"
TARBALL_URL = ("https://github.com/hadzz/abgx360/archive/"
               "refs/heads/master.tar.gz")
SITE_URL = "http://abgx360.hadzz.com"


def _noop(_msg):
    pass


# ------------------------------------------------------------------
# Engine acquisition
# ------------------------------------------------------------------

def binary_path():
    name = "abgx360.exe" if sys.platform.startswith("win") else "abgx360"
    return ENGINE_DIR / name


def engine_ready():
    b = binary_path()
    if not b.is_file():
        return False
    try:
        # NOTE: abgx360 prints its help but exits 1 for --help, so
        # readiness is judged by the output, not the exit code.
        r = subprocess.run([str(b), "--help"], capture_output=True,
                           timeout=30)
        return b"Usage" in r.stdout and b"abgx360" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def _run_stream(cmd, cwd, log, env=None, timeout=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    log("+ " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen(
        [str(c) for c in cmd], cwd=str(cwd), env=full_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", bufsize=1)
    try:
        for line in proc.stdout:
            log(line.rstrip("\n"))
        proc.wait(timeout=timeout)
    except Exception:
        proc.kill()
        raise
    return proc.returncode


class EngineError(Exception):
    pass


def _fetch_source(log):
    """Download the hadzz/abgx360 source tree into ENGINE_DIR/src-tree."""
    tree = ENGINE_DIR / "src-tree"
    if (tree / "linux" / "abgx360" / "src" / "abgx360.c").is_file():
        return tree
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.which("git"):
        tmp = ENGINE_DIR / "clone-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        rc = _run_stream(["git", "clone", "--depth", "1", REPO_URL, tmp],
                         ENGINE_DIR, log)
        if rc == 0 and (tmp / "linux").is_dir():
            if tree.exists():
                shutil.rmtree(tree)
            tmp.rename(tree)
            return tree
        log("git clone did not produce a usable tree; "
            "falling back to the source tarball.")
    tarball = ENGINE_DIR / "abgx360-src.tar.gz"
    log("Downloading " + TARBALL_URL)
    req = urllib.request.Request(
        TARBALL_URL, headers={"User-Agent": "abgx360-gui-setup"})
    with urllib.request.urlopen(req, timeout=120) as r, \
            open(tarball, "wb") as f:
        shutil.copyfileobj(r, f)
    extract = ENGINE_DIR / "extract-tmp"
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True)
    with tarfile.open(tarball) as tf:
        tf.extractall(extract, filter="data")
    roots = [p for p in extract.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise EngineError("Unexpected source tarball layout.")
    if tree.exists():
        shutil.rmtree(tree)
    roots[0].rename(tree)
    shutil.rmtree(extract, ignore_errors=True)
    return tree


# ------------------------------------------------------------------
# Build dependencies -- checked before the engine build so a
# missing compiler/libcurl/zlib is an offer to install, never a
# dead-end configure failure. Field case, 2026-11-21: a rig with
# no curl-config died at ./configure and the app could only print
# instructions to install libcurl4-openssl-dev by hand.
# ------------------------------------------------------------------

class DepsMissingError(EngineError):
    """Build dependencies are missing. .info carries everything
    the GUI needs to offer a one-click install: the missing dep
    names, the apt package list (Debian family), the Fedora-family
    equivalents, the distro family, and the exact manual command."""

    def __init__(self, info):
        self.info = info
        super().__init__(info["manual_text"])


def _os_release():
    data = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"')
    except Exception:  # noqa: BLE001
        pass
    return data


def distro_family(os_release=None):
    """'debian' | 'fedora' | 'other', from /etc/os-release."""
    if os_release is None:
        os_release = _os_release()
    ids = (os_release.get("ID", "") + " "
           + os_release.get("ID_LIKE", "")).lower()
    if "debian" in ids or "ubuntu" in ids:
        return "debian"
    if "fedora" in ids or "rhel" in ids or "centos" in ids:
        return "fedora"
    return "other"


def _zlib_dev_present():
    for p in ("/usr/include/zlib.h", "/usr/local/include/zlib.h"):
        if Path(p).is_file():
            return True
    if shutil.which("pkg-config"):
        try:
            return subprocess.run(
                ["pkg-config", "--exists", "zlib"],
                capture_output=True, timeout=10).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    return False


def check_build_deps():
    """[(key, name, ok, apt package, fedora package)] for what
    abgx360's configure + build need on Linux. Empty on Windows
    (no engine build happens there)."""
    if sys.platform.startswith("win"):
        return []
    return [
        ("cc", "a C compiler (gcc)",
         shutil.which("gcc") is not None
         or shutil.which("cc") is not None,
         "build-essential", "gcc"),
        ("make", "make",
         shutil.which("make") is not None,
         "build-essential", "make"),
        ("curl", "the libcurl development files (curl-config)",
         shutil.which("curl-config") is not None,
         "libcurl4-openssl-dev", "libcurl-devel"),
        ("zlib", "the zlib development files (zlib.h)",
         _zlib_dev_present(),
         "zlib1g-dev", "zlib-devel"),
    ]


def missing_build_deps():
    return [c for c in check_build_deps() if not c[2]]


def dep_info(missing=None):
    """Structured description of the missing build deps and how
    to install them -- the GUI's offer dialog and error text."""
    if missing is None:
        missing = missing_build_deps()
    family = distro_family()
    names = [c[1] for c in missing]
    apt = sorted({c[3] for c in missing})
    fedora = sorted({c[4] for c in missing})
    if family == "debian":
        manual_command = "sudo apt-get install -y " + " ".join(apt)
    elif family == "fedora":
        manual_command = "sudo dnf install -y " + " ".join(fedora)
    else:
        manual_command = ("(your distro's equivalents of: "
                          + ", ".join(fedora) + ")")
    manual_text = (
        "Building abgx360 needs " + ", ".join(names)
        + ", which are not installed. Install them with: "
        + manual_command
        + " -- then use Help > Re-run first-run setup.")
    return {"missing": names, "packages": apt,
            "alt_packages": fedora, "family": family,
            "manual_command": manual_command,
            "manual_text": manual_text}


def install_missing_deps(log=_noop):
    """Install the missing build deps via pkexec apt (Debian
    family only; one GUI password prompt -- the pop-fe GUI's
    pattern). Returns True when nothing is missing afterwards;
    the re-check is the judge, not the installer's exit code."""
    missing = missing_build_deps()
    if not missing:
        return True
    info = dep_info(missing)
    if info["family"] != "debian":
        log("Automatic install is only wired for Debian/Ubuntu; "
            "on this system install manually: "
            + info["manual_command"])
        return False
    if not shutil.which("pkexec"):
        log("pkexec is not available, so I cannot install them "
            "for you. Install manually: " + info["manual_command"])
        return False
    pkgs = info["packages"]
    log("Asking for your password once (pkexec) to install: "
        + " ".join(pkgs))
    _run_stream(["pkexec", "sh", "-c",
                 "apt-get update -qq && apt-get install -y "
                 + " ".join(pkgs)], Path("/"), log)
    still = missing_build_deps()
    if still:
        log("Still missing after the install attempt: "
            + ", ".join(c[1] for c in still))
        return False
    log("Build dependencies installed.")
    return True


def _build_linux(log):
    tree = _fetch_source(log)
    src = tree / "linux" / "abgx360"
    build = ENGINE_DIR / "build"
    if build.exists():
        shutil.rmtree(build)
    shutil.copytree(src, build)
    # Keep the pre-generated autotools files newer than their sources
    # so make does not try to regenerate them (autoconf/automake are
    # not required to build this tree).
    for name in ("aclocal.m4", "configure", "config.h.in",
                 "Makefile.in", "src/Makefile.in"):
        p = build / name
        if p.exists():
            p.touch()
    lines = []

    def clog(msg):
        lines.append(msg)
        log(msg)

    rc = _run_stream(["./configure"], build, clog)
    if rc != 0:
        out = "\n".join(lines).lower()
        if "libcurl" in out or "curl-config" in out:
            # The pre-flight passed but configure disagrees (e.g.
            # a curl-config that does not actually work): treat it
            # as the dependency problem it is, so the GUI can
            # offer the install from the failure path too.
            missing = missing_build_deps()
            if not missing:
                missing = [c for c in check_build_deps()
                           if c[0] == "curl"]
            raise DepsMissingError(dep_info(missing))
        raise EngineError(
            "abgx360's configure step failed -- see the log above "
            "for the exact error, then use Help > Re-run "
            "first-run setup.")
    rc = _run_stream(["make", "-j4"], build, log)
    if rc != 0:
        raise EngineError("Building abgx360 failed -- see the log.")
    built = build / "abgx360"
    if not built.is_file():
        raise EngineError("Build finished but no abgx360 binary "
                          "was produced.")
    dest = binary_path()
    shutil.copy2(built, dest)
    dest.chmod(0o755)


def ensure_engine(log=_noop, stage=_noop, install_deps=False):
    """First-run setup. Returns True when the engine is usable.

    Build deps are pre-flighted: if any are missing and
    install_deps is set (the user accepted the GUI's one-click
    offer), they are installed via pkexec first; otherwise
    DepsMissingError is raised before any download/build, so the
    GUI can make the offer. Other failures raise EngineError with
    a plain-language explanation; the app stays open either way
    and says what is missing in the open (same honesty rule as
    the pop-fe GUI's missing chdman).
    """
    if engine_ready():
        return True
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        stage("First-run setup: looking for abgx360.exe...")
        raise EngineError(
            "On Windows this app drives a prebuilt abgx360.exe, "
            "which is not bundled. Download abgx360 v1.0.7 from "
            + SITE_URL + " and place abgx360.exe in the engine "
            "folder: " + str(ENGINE_DIR))
    missing = missing_build_deps()
    if missing:
        if install_deps:
            stage("First-run setup: installing build "
                  "dependencies...")
            install_missing_deps(log)
            missing = missing_build_deps()
        if missing:
            raise DepsMissingError(dep_info(missing))
    stage("First-run setup: downloading the abgx360 source...")
    _build_linux(log)
    stage("First-run setup: verifying the engine...")
    if not engine_ready():
        raise EngineError("The engine was built but does not run "
                          "(--help failed). See the log.")
    return True


def stealthfiles_dir():
    return Path.home() / ".abgx360" / "StealthFiles"


def images_dir():
    return Path.home() / ".abgx360" / "Images"


# ------------------------------------------------------------------
# Settings model -- every original GUI option, original defaults.
# Keys are the original GUI's own config key names where it had them.
# ------------------------------------------------------------------

DEFAULT_SETTINGS = {
    # run panel / program output
    "WriteDisable": False,
    "ProgramOutput": 0,          # 0 CLI Window, 1 HTML File, 2 Text File
    "OutputFile": "",
    "Maximize": True,
    "OpenFileWhenDone": False,
    "TerminalFont": True,
    # options tab
    "CheckDVDFile": True,
    "CheckStealth": True,
    "Verify": True,
    "CheckVideoPadding": False,
    "ShowAvatarAwards": False,
    "UseColors": True,
    "Verbosity": 1,              # 0 Low, 1 Medium, 2 High
    "CheckCorruption": False,
    "DisplayFilesystem": False,
    "OnlineUpdate": True,
    "CSVUpdate": False,
    "StayOffline": False,
    "CheckGameCRCWhenNeeded": True,
    "RecurseSubdirs": False,
    "ShowAchievements": False,
    "HideSecretAchievements": False,
    # manually patch or extract tab
    "PatchIfStealthPasses": False,
    "PatchIfInvalid": False,
    "PatchVideo": False, "PatchVideoFile": "",
    "PatchPFI": False, "PatchPFIFile": "",
    "PatchDMI": False, "PatchDMIFile": "",
    "PatchSS": False, "PatchSSFile": "",
    "Clobber": False,
    "ExtractVideo": False, "ExtractVideoFile": "",
    "ExtractEntireVideoPartition": False,
    "ExtractPFI": False, "ExtractPFIFile": "",
    "ExtractDMI": False, "ExtractDMIFile": "",
    "ExtractSS": False, "ExtractSSFile": "",
    # autofix tab
    "AutoFix": 1,                # 0 L3, 1 L2, 2 L1, 3 L0
    "TrustSSv2": True,
    "FixAngle359": False,
    "FixDRT": True,
    "FixBadAngles": True,
    "FixBadAnglesValue": 3,      # degrees 0..13; 3 = CLI default
    # rebuilding tab
    "RebuildMethod": 0,          # 0 Default, 1 Low Disk Space, 2 Don't
    "KeepOriginalISO": False,
    # misc tab
    "MyRegion": "",
    "PreferredLang": 0,          # index into LANGUAGES; 0 = English
    "SplitVid": 2,               # 0 Add, 1 Remove, 2 Leave
    "XexImages": 0,              # 0 when HTML, 1 always, 2 never
    "EmbedImages": False,
    "ExtraOptions": "",
    # match only (folder items)
    "MatchOnly": False,
    "MatchMask": "",
}

LANGUAGES = ["English", "Japanese", "German", "French", "Spanish",
             "Italian", "Korean", "Traditional Chinese", "Portuguese",
             "Simplified Chinese", "Polish", "Russian"]

MATCH_MASKS = ["*.iso", "*.000", "*.360", "*.img", "*.bin", "*.xex",
               "*pfi*.bin", "*dmi*.bin", "*ss*.bin", "*video*.iso"]

ISO_EXTENSIONS = {".iso", ".000", ".360", ".img", ".bin", ".xex",
                  ".dvd"}


def effective(settings, item_kind=None):
    """Settings with the original GUI's interlocks applied -- the
    settled state its UIUpdate() converges to."""
    s = dict(settings)
    if s["StayOffline"]:
        s["OnlineUpdate"] = False
    if not s["OnlineUpdate"]:
        s["CSVUpdate"] = False
    if not s["CheckStealth"]:
        s["Verify"] = False
    if not s["CheckGameCRCWhenNeeded"]:
        s["CheckCorruption"] = False
    if s["RebuildMethod"] != 0:
        s["KeepOriginalISO"] = False
    if s["XexImages"] == 2:
        s["EmbedImages"] = False
    if item_kind == "dvd":
        s["WriteDisable"] = True
    if not s["ExtractVideo"]:
        s["ExtractEntireVideoPartition"] = False
    return s


def build_argv(settings, item):
    """Reproduce the original GUI's command construction exactly.

    item = {"kind": "file"|"dir"|"dvd", "path": str}
    An item may also carry "run_path": the file the engine
    actually checks when "path" is what the user picked (an
    archive whose ISO was extracted to local scratch). Returns
    the argv list (binary first).
    """
    s = effective(settings, item["kind"])
    letters = ""
    if s["Verbosity"] == 0:
        letters += "n"
    elif s["Verbosity"] == 2:
        letters += "v"
    if not s["CheckStealth"]:
        letters += "r"
    if s["CheckVideoPadding"]:
        letters += "p"
    if s["CheckCorruption"]:
        letters += "c"
    if not s["UseColors"] or s["ProgramOutput"] == 2:
        letters += "s"
    if not s["CheckGameCRCWhenNeeded"]:
        letters += "g"
    if s["RebuildMethod"] == 1:
        letters += "l"
    elif s["RebuildMethod"] == 2:
        letters += "b"
    if s["TerminalFont"]:
        letters += "t"
    if s["StayOffline"]:
        letters += "o"
    if s["ProgramOutput"] == 1:
        letters += "h"
        if s["XexImages"] != 2:
            letters += "i"
    elif s["XexImages"] == 1:
        letters += "i"
    if not s["CheckDVDFile"]:
        letters += "d"
    if s["FixAngle359"]:
        letters += "x"
    if s["KeepOriginalISO"]:
        letters += "k"
    if s["WriteDisable"]:
        letters += "w"

    argv = [str(binary_path())]
    if letters:
        argv.append("-" + letters)
    if s["DisplayFilesystem"]:
        argv.append("--showfiles")
    if s["ShowAvatarAwards"]:
        argv.append("--aa")
    if s["ShowAchievements"]:
        argv.append("--achs" if s["HideSecretAchievements"] else "--ach")
    if s["AutoFix"] == 0:
        argv.append("--af3")
    elif s["AutoFix"] == 2:
        argv.append("--af1")
    elif s["AutoFix"] == 3:
        argv.append("--af0")
    if not s["FixDRT"]:
        argv.append("--nofixdrt")
    if not s["FixBadAngles"]:
        argv.append("--nofixdev")
    elif s["FixBadAnglesValue"] != 3:
        argv += ["--dev", str(s["FixBadAnglesValue"])]
    if not s["TrustSSv2"]:
        argv.append("--notrust")
    if not s["Verify"]:
        argv.append("--noverify")
    if not s["OnlineUpdate"]:
        argv.append("--noupdate")
    if s["CSVUpdate"]:
        argv.append("--csv")
    if item["kind"] == "dir" and s["MatchOnly"] and s["MatchMask"]:
        mask = s["MatchMask"]
        if "," not in mask:
            mask = "," + mask
        argv += ["--match", mask]
    if s["MyRegion"]:
        argv += ["--rgn", s["MyRegion"]]
    if s["PreferredLang"] != 0:
        argv += ["--lang", str(s["PreferredLang"] + 1)]
    if s["SplitVid"] == 0:
        argv.append("--splitvid")
    elif s["SplitVid"] == 1:
        argv.append("--removesplitvid")
    if s["EmbedImages"]:
        argv.append("--embed")
    if s["PatchIfStealthPasses"]:
        argv.append("--patchitanyway")
    if s["PatchIfInvalid"]:
        argv.append("--patchgarbage")
    for key, flag in (("PatchVideo", "--p-video"),
                      ("PatchPFI", "--p-pfi"),
                      ("PatchDMI", "--p-dmi"),
                      ("PatchSS", "--p-ss")):
        if s[key]:
            argv += [flag, s[key + "File"]]
    if s["Clobber"]:
        argv.append("--clobber")
    if s["ExtractVideo"]:
        flag = ("--e-videopartition" if s["ExtractEntireVideoPartition"]
                else "--e-video")
        argv += [flag, s["ExtractVideoFile"]]
    for key, flag in (("ExtractPFI", "--e-pfi"),
                      ("ExtractDMI", "--e-dmi"),
                      ("ExtractSS", "--e-ss")):
        if s[key]:
            argv += [flag, s[key + "File"]]
    if s["ExtraOptions"]:
        argv += shlex.split(s["ExtraOptions"])
    # input spec
    path = item.get("run_path") or item["path"]
    if item["kind"] == "file":
        argv += ["--", path]
    elif item["kind"] == "dir":
        if s["RecurseSubdirs"]:
            argv.append("--rec")
        argv += ["--dir", path]
    elif item["kind"] == "dvd":
        argv += ["--dvd", path]
    return argv


_VALUE_FLAGS = {"--p-video", "--p-pfi", "--p-dmi", "--p-ss",
                "--e-video", "--e-videopartition", "--e-pfi",
                "--e-dmi", "--e-ss", "--dir", "--dvd", "--match"}


def preview_command(settings, item):
    """The command as the original GUI's status field would show it
    (binary shown as 'abgx360', file arguments quoted)."""
    argv = build_argv(settings, item)
    target = item.get("run_path") or item["path"]
    parts = []
    quote_next = False
    for i, a in enumerate(argv):
        if i == 0:
            parts.append("abgx360")
        elif quote_next or a == target:
            parts.append('"%s"' % a)
            quote_next = False
        else:
            parts.append(a)
        if a in _VALUE_FLAGS:
            quote_next = True
    return " ".join(parts)


# ------------------------------------------------------------------
# Presets + history
# ------------------------------------------------------------------

def list_presets():
    if not PRESETS_DIR.is_dir():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def save_preset(name, settings):
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    (PRESETS_DIR / (name + ".json")).write_text(
        json.dumps(settings, indent=1, sort_keys=True))


def load_preset(name):
    p = PRESETS_DIR / (name + ".json")
    if not p.is_file():
        return None
    data = json.loads(p.read_text())
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in data.items()
                   if k in DEFAULT_SETTINGS})
    return merged


def delete_preset(name):
    p = PRESETS_DIR / (name + ".json")
    if p.is_file():
        p.unlink()


def load_history():
    try:
        return json.loads(HISTORY_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {"files": [], "dirs": []}


def save_history(hist):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(hist, indent=1))


def remember(hist, key, path, limit=10):
    entries = [e for e in hist.get(key, []) if e != path]
    entries.insert(0, path)
    hist[key] = entries[:limit]
    save_history(hist)


def scan_folder(folder, recurse=True):
    """Folder scan for Add Folder: ISO-ish files, recursive by
    design (the Recurse Subdirectories option governs the CLI's own
    --dir recursion; our queue always lists what it found)."""
    folder = Path(folder)
    it = folder.rglob("*") if recurse else folder.glob("*")
    found = []
    for p in sorted(it):
        if p.is_file() and p.suffix.lower() in ISO_EXTENSIONS:
            found.append(str(p))
    return found


# ------------------------------------------------------------------
# Running + parsing
# ------------------------------------------------------------------

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text):
    return ANSI_RE.sub("", text)


class RunHandle:
    """One running abgx360 process; the GUI polls/drains it."""

    def __init__(self, argv, cwd):
        self.argv = argv
        self.proc = subprocess.Popen(
            [str(a) for a in argv], cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1)

    def terminate(self):
        try:
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass


def start_run(argv):
    return RunHandle(argv, Path.home())


# Verdict words abgx360 uses, in priority order.
_FAIL_HINTS = ("failed", "failure", "doesn't match", "does not match",
               "not verified", "invalid", "corrupt", "error")
_PASS_HINTS = ("passed", "matches known ini", "matches!", "match!",
               "successful", "is verified", "verified!")


def parse_results(text):
    """Parse one run's (ANSI-stripped) output into per-check rows:
    {"check": str, "result": "PASS"|"FAIL"|"WARN"|"INFO",
     "detail": str}. Refined against real v1.0.7 output."""
    rows = []
    seen = set()

    def add(check, result, detail=""):
        key = (check, result)
        if key in seen:
            return
        seen.add(key)
        rows.append({"check": check, "result": result,
                     "detail": detail.strip()})

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "stealth check passed" in low or "stealth passed" in low:
            add("Stealth check", "PASS", line)
        elif "stealth check failed" in low or "stealth failed" in low:
            add("Stealth check", "FAIL", line)
        elif low.startswith("region code:"):
            add("Region", "INFO", line)
        elif "ss looks valid" in low:
            add("SS", "PASS", line)
        elif "dmi looks valid" in low:
            add("DMI", "PASS", line)
        elif "pfi matches known data" in low:
            add("PFI", "PASS", line)
        elif "video partition matches known data" in low:
            add("Video partition", "PASS", line)
        elif "anydvd style corruption was not detected" in low:
            add("Corruption", "PASS", line)
        elif "game appears to have random padding" in low:
            add("Padding", "INFO", line)
        elif "all crcs match" in low:
            add("All CRCs", "PASS", line)
        elif "verification was successful" in low or \
                "verification successful" in low or \
                "this game is verified" in low:
            add("Online verification", "PASS", line)
        elif "failed to find a verified ini" in low or \
                "verification failed" in low:
            add("Online verification", "FAIL", line)
        elif "autofix was successful" in low:
            add("AutoFix", "PASS", line)
        elif "autofix failed" in low:
            add("AutoFix", "FAIL", line)
        elif "crc = " in low or " crc =" in low:
            subject = line.split("=", 1)[0].strip().rstrip("CRC").strip()
            subject = (subject or "CRC") + " CRC"
            if "matches known ini" in low:
                add(subject, "PASS", line)
            elif "doesn't match" in low or "does not match" in low:
                add(subject, "FAIL", line)
            else:
                add(subject, "INFO", line)
        elif "topology data" in low and ("verified" in low or
                                         "valid" in low):
            add("Topology data", "PASS", line)
        elif low.startswith("error:") or " error:" in low:
            add("Error", "FAIL", line)
        elif "warning" in low or "caution" in low:
            add("Warning", "WARN", line)
    return rows
