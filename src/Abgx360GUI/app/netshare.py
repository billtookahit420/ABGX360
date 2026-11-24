"""Network-share browsing for the abgx360 GUI.

Duane's ISO library lives on a home server (SMB), so the pickers
must be able to reach network shares, not just local disks. This
module owns everything that is not widgets:

* parsing whatever the user types for a share (a UNC path, an
  smb:// URL, or plain "SERVER/share") into server/share/port;
* remembering recently used shares (shares.json beside the
  history file, same per-user data folder as the engine layer);
* turning a share into a path the rest of the app can use:
  - Windows: the UNC path itself (\\\\SERVER\\share) -- Explorer,
    the native file dialogs and the abgx360 CLI all speak UNC;
  - Linux: a GVFS mount. `gio mount smb://SERVER/share` makes the
    share a real directory under $XDG_RUNTIME_DIR/gvfs, which the
    file dialogs can browse and the abgx360 CLI can read like any
    local folder. If GVFS is not installed the error says so in
    the open and names the package, in the same spirit as the
    build-dependency pre-flight.

Stdlib only, like abgx_engine, so the unit tests cover it without
Qt.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
# Same per-user data folder the engine layer uses (AppRun / the
# launchers point ABGX360_GUI_DATA_DIR at it; unpackaged runs fall
# back to a folder beside the app).
DATA_DIR = Path(os.environ.get(
    "ABGX360_GUI_DATA_DIR", str(APP_DIR)))
SHARES_PATH = DATA_DIR / "shares.json"

GVFS_PACKAGE_HINT = (
    "Network shares on Linux are mounted through GVFS, which is "
    "not available on this system. Install the package "
    "\"gvfs-backends\" (Debian/Ubuntu: sudo apt install "
    "gvfs-backends), then try again.")


class NetShareError(Exception):
    """A share could not be turned into a usable path; the
    message is written for the user, not the log."""


# ------------------------------------------------------------------
# Parsing + path construction (pure helpers)
# ------------------------------------------------------------------

def parse_target(text, share_text=""):
    """Parse a share target into {"server", "share", "port",
    "subpath"} or return None when it does not look like one.

    Accepts \\\\SERVER\\share\\sub\\path, //SERVER/share,
    smb://SERVER/share, smb://SERVER:port/share, SERVER/share
    and SERVER:port/share. When `text` is a bare server name, the
    share may come from `share_text` (the dialog has separate
    fields); a share embedded in `text` wins.
    """
    if text is None:
        return None
    t = text.strip().replace("\\", "/")
    if t.lower().startswith("smb://"):
        t = t[6:]
    t = t.strip("/")
    if not t:
        return None
    parts = [p for p in t.split("/") if p != ""]
    if not parts:
        return None
    server_field = parts[0]
    m = re.match(r"^(.+?):(\d+)$", server_field)
    if m:
        server, port = m.group(1), int(m.group(2))
    else:
        server, port = server_field, None
    share = parts[1] if len(parts) > 1 else (share_text or ""
                                             ).strip()
    if not server or not share:
        return None
    subpath = "/".join(parts[2:]) if len(parts) > 2 else ""
    return {"server": server, "share": share, "port": port,
            "subpath": subpath}


def unc_root(server, share):
    """\\\\SERVER\\share -- the browsable root on Windows."""
    return "\\\\" + server + "\\" + share.replace("/", "\\")


def smb_url(server, share, port=None, username=""):
    host = server if not port else "%s:%d" % (server, port)
    user = ""
    if username:
        user = "%s@" % urllib.parse.quote(username, safe="")
    return "smb://%s%s/%s" % (user, host, share)


def share_label(entry):
    """Display form for a remembered share: SERVER/share."""
    host = entry["server"]
    if entry.get("port"):
        host = "%s:%d" % (host, entry["port"])
    return "%s/%s" % (host, entry["share"])


# ------------------------------------------------------------------
# Remembered shares (shares.json in the data folder)
# ------------------------------------------------------------------

def load_shares(path=None):
    try:
        data = json.loads((path or SHARES_PATH).read_text())
    except Exception:  # noqa: BLE001
        return []
    out = []
    if isinstance(data, list):
        for e in data:
            if isinstance(e, dict) and e.get("server") \
                    and e.get("share"):
                out.append({"server": str(e["server"]),
                            "share": str(e["share"]),
                            "port": e.get("port"),
                            "user": str(e.get("user") or "")})
    return out


def save_shares(shares, path=None):
    p = path or SHARES_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(shares, indent=1))


def remember_share(server, share, port=None, user="", limit=10,
                   path=None):
    """Most-recent-first, de-duplicated; returns the new list.
    The username is remembered with the share; a password never
    is."""
    shares = [s for s in load_shares(path)
              if not (s["server"].lower() == server.lower()
                      and s["share"].lower() == share.lower()
                      and s.get("port") == port)]
    shares.insert(0, {"server": server, "share": share,
                      "port": port, "user": user})
    shares = shares[:limit]
    save_shares(shares, path)
    return shares


# ------------------------------------------------------------------
# Linux: GVFS mounting
# ------------------------------------------------------------------

def gvfs_root():
    base = os.environ.get("XDG_RUNTIME_DIR") or \
        "/run/user/%d" % os.getuid()
    return Path(base) / "gvfs"


def _mount_dir_matches(name, server, share):
    """GVFS names its mount dirs like
    "smb-share:server=192.168.0.102,share=XBOX360 ARCHIVE" (a
    non-default port is URL-encoded into the server field, e.g.
    "server=127.0.0.1%3A4445"). Match loosely: the server and
    share fields must both be present, case-insensitively."""
    low = name.lower()
    if not low.startswith("smb-share:"):
        return False
    srv = re.search(r"server=([^,]+)", low)
    shr = re.search(r"share=([^,]+)", low)
    if not srv or not shr:
        return False
    want_srv = server.lower()
    got_srv = srv.group(1).replace("%3a", ":")
    if got_srv != want_srv and \
            not got_srv.startswith(want_srv + ":"):
        return False
    return shr.group(1) == share.lower()


def find_gvfs_mount(server, share, root=None):
    """The local directory of an already-mounted share, or None."""
    root = root or gvfs_root()
    try:
        entries = sorted(root.iterdir())
    except Exception:  # noqa: BLE001
        return None
    for e in entries:
        if e.is_dir() and _mount_dir_matches(e.name, server, share):
            return e
    return None


def _gio_mount(gio, url, username, password, workgroup,
               timeout=90):
    """Run `gio mount url`, answering its credential prompts.

    gio asks for credentials when a mount needs them -- for SMB
    the prompts come under a header line that itself contains
    the word "password" ("Enter user and password for share
    ..."), and the Domain prompt may come before the Password
    one. So the whole output buffer must NOT be keyword
    searched: only the PENDING prompt -- the text after the
    last newline, since prompts are printed without one --
    says what is actually being asked. (Keyword-searching the
    buffer types the password into the Domain field and then
    never answers the real Password prompt; that bug was found
    and fixed in the recomp-tools family and is not repeated
    here.) gio is driven through a pty so the prompts behave
    exactly as they do in a terminal. Answers are capped so a
    re-prompting server cannot loop us forever.
    Returns (rc, output text); rc 124 means timed out."""
    import pty

    master, slave = pty.openpty()
    p = subprocess.Popen([gio, "mount", url], stdin=slave,
                         stdout=slave, stderr=slave,
                         close_fds=True)
    os.close(slave)
    buf = b""
    answered = 0
    deadline = time.time() + timeout
    os.set_blocking(master, False)
    while True:
        if p.poll() is not None:
            try:
                while True:
                    chunk = os.read(master, 4096)
                    if not chunk:
                        break
                    buf += chunk
            except OSError:
                pass
            break
        if time.time() > deadline:
            p.kill()
            try:
                os.close(master)
            except OSError:
                pass
            return 124, (buf.decode("utf-8", "replace")
                         + "\n(mount timed out)")
        try:
            chunk = os.read(master, 4096)
            if chunk:
                buf += chunk
        except BlockingIOError:
            time.sleep(0.05)
            continue
        except OSError:
            break
        text = buf.decode("utf-8", "replace")
        pending = text.replace("\r", "\n").rsplit("\n", 1)[-1]
        answer = None
        if "omain" in pending:
            answer = workgroup or "WORKGROUP"
        elif "assword" in pending:
            answer = password
        elif "sername" in pending or \
                pending.rstrip().endswith("ser:"):
            answer = username
        if answer is not None and answered < 8:
            os.write(master, (answer + "\n").encode())
            answered += 1
            buf = b""
    rc = p.wait()
    try:
        os.close(master)
    except OSError:
        pass
    return rc, buf.decode("utf-8", "replace")


def gio_mount(server, share, port=None, timeout=90, username="",
              password="", workgroup=""):
    """Ask GVFS to mount the share, answering credential
    prompts with the given username/password/workgroup (all
    optional; a guest share needs none). Returns
    (ok, message)."""
    gio = shutil.which("gio")
    if gio is None:
        return False, GVFS_PACKAGE_HINT
    url = smb_url(server, share, port, username)
    try:
        rc, out = _gio_mount(gio, url, username, password,
                             workgroup, timeout)
    except Exception as e:  # noqa: BLE001
        return False, "Could not run gio: %s" % e
    out = out.strip()
    if rc == 0:
        return True, out
    if rc == 124:
        return False, ("Timed out mounting %s. If the server "
                       "keeps asking for credentials, check "
                       "the username and password, or mount "
                       "the share once in your file manager, "
                       "then try again." % url)
    # "already mounted" is success for our purposes -- the
    # caller re-scans the gvfs folder either way.
    if "already mounted" in out.lower():
        return True, out
    return False, out or ("gio mount failed for %s" % url)


def ensure_local_path(server, share, port=None, username="",
                      password="", workgroup=""):
    """Linux: the share as a real local directory (GVFS mount),
    mounting it first if needed. Raises NetShareError."""
    found = find_gvfs_mount(server, share)
    if found is not None:
        return str(found)
    ok, msg = gio_mount(server, share, port, username=username,
                        password=password, workgroup=workgroup)
    if not ok:
        raise NetShareError(msg)
    # gio can take a moment to publish the mount point.
    for _ in range(25):
        found = find_gvfs_mount(server, share)
        if found is not None:
            return str(found)
        time.sleep(0.2)
    raise NetShareError(
        "The share %s was mounted but its folder was not "
        "found under %s. Mount it once in your file manager, "
        "then try again."
        % (smb_url(server, share, port), gvfs_root()))


# ------------------------------------------------------------------
# Platform dispatcher used by the GUI
# ------------------------------------------------------------------

def browse_root(server, share, port=None, username="",
                password="", workgroup=""):
    """Turn a share into the path the file dialogs should open.

    Windows: the UNC root (existence is the caller's check -- the
    native dialog also accepts a typed UNC path). Linux: the
    GVFS mount directory, mounting first if needed; raises
    NetShareError with a user-ready message on failure.
    """
    if sys.platform.startswith("win"):
        return unc_root(server, share)
    return ensure_local_path(server, share, port,
                             username=username, password=password,
                             workgroup=workgroup)
