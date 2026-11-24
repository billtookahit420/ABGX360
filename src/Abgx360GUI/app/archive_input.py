"""Archive input for the abgx360 GUI (.zip / .7z).

Add Single ISO also accepts a .zip or .7z archive: the disc
image inside is extracted to LOCAL scratch (the per-user data
folder's "extracted" directory) and the queue then checks the
extracted ISO exactly like a directly picked file. The queue
row keeps showing the archive the user picked; the engine is
handed the extracted file through the item's "run_path".

Rules, by design:
* the source archive is only ever read -- never modified, and
  extraction never happens next to it (in particular never back
  onto a network share, where a multi-GB extracted ISO would be
  slow and is not wanted);
* verification never happens "inside" an archive -- abgx360
  always gets a real extracted file;
* re-adding the same archive reuses the extraction (keyed by
  the archive's path + size + mtime).

.zip is stdlib (zipfile). .7z has no stdlib support: py7zr is
used when importable (it is in requirements.txt and bundled
into the AppImage); a system 7z/7zz/7zr command is the fallback;
with neither, the error names both options in the open.
"""
import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
# Same per-user data folder the engine layer uses -- local by
# construction (AppRun / the launchers point it at
# ~/.local/share/abgx360-gui).
DATA_DIR = Path(os.environ.get(
    "ABGX360_GUI_DATA_DIR", str(APP_DIR)))
SCRATCH_DIR = DATA_DIR / "extracted"

ARCHIVE_EXTS = {".zip", ".7z"}
ISO_EXTS = {".iso", ".000", ".360", ".img", ".bin", ".xex"}


def _noop(_msg):
    pass


class ArchiveError(Exception):
    """An archive could not yield an extracted ISO; the message
    is written for the user, not the log."""


def is_archive(path):
    return Path(str(path)).suffix.lower() in ARCHIVE_EXTS


def is_iso_member(name):
    return Path(name).suffix.lower() in ISO_EXTS


# ------------------------------------------------------------------
# Member listing
# ------------------------------------------------------------------

def _zip_members(path):
    try:
        with zipfile.ZipFile(str(path)) as zf:
            return [(i.filename, i.file_size) for i in zf.infolist()
                    if not i.is_dir() and is_iso_member(i.filename)]
    except zipfile.BadZipFile:
        raise ArchiveError("%s is not a readable zip file."
                           % Path(str(path)).name)


def _py7zr():
    try:
        import py7zr
        return py7zr
    except Exception:  # noqa: BLE001
        return None


def _seven_zip_cli():
    for name in ("7z", "7zz", "7zr"):
        p = shutil.which(name)
        if p:
            return p
    return None


def seven_zip_backend():
    """"py7zr", "cli", or None -- what .7z support rests on."""
    if _py7zr() is not None:
        return "py7zr"
    if _seven_zip_cli() is not None:
        return "cli"
    return None


def _7z_members_py7zr(path):
    py7zr = _py7zr()
    with py7zr.SevenZipFile(str(path), "r") as zf:
        out = []
        for info in zf.list():
            name = info.filename
            if not info.is_directory and is_iso_member(name):
                out.append((name, info.uncompressed or 0))
        return out


def _7z_members_cli(path):
    exe = _seven_zip_cli()
    r = subprocess.run([exe, "l", "-slt", str(path)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ArchiveError("7z could not list %s: %s"
                           % (Path(str(path)).name,
                              (r.stderr or r.stdout).strip()[:200]))
    out, name, size = [], None, 0
    for line in r.stdout.splitlines():
        if line.startswith("Path = "):
            if name and is_iso_member(name):
                out.append((name, size))
            name, size = line[7:].strip(), 0
        elif line.startswith("Size = "):
            try:
                size = int(line[7:].strip() or 0)
            except ValueError:
                size = 0
        elif line.startswith("Folder = +"):
            name = None
    if name and is_iso_member(name):
        out.append((name, size))
    return out


def iso_members(path):
    """[(member_name, uncompressed_size)] for the disc images
    inside an archive. Raises ArchiveError."""
    p = Path(str(path))
    if p.suffix.lower() == ".zip":
        return _zip_members(p)
    if p.suffix.lower() == ".7z":
        if _py7zr() is not None:
            return _7z_members_py7zr(p)
        if _seven_zip_cli() is not None:
            return _7z_members_cli(p)
        raise ArchiveError(_no_7z_text())
    raise ArchiveError("Not an archive: %s" % p.name)


def _no_7z_text():
    return ("Reading .7z archives needs py7zr (pip install "
            "py7zr -- it is in this app's requirements and "
            "bundled in the AppImage) or a 7z command (the "
            "p7zip package). Neither was found.")


def choose_member(members):
    """The disc image to extract: the largest ISO member (a game
    ISO dwarfs any .dvd/.bin sidecar in the same archive)."""
    return max(members, key=lambda m: m[1])


# ------------------------------------------------------------------
# Extraction
# ------------------------------------------------------------------

def scratch_dir_for(archive_path, root=None):
    """Per-archive scratch folder under the local data dir,
    keyed by path + size + mtime so a changed archive gets a
    fresh extraction and an unchanged one is reused."""
    p = Path(str(archive_path))
    try:
        st = p.stat()
        sig = "%s|%d|%d" % (p.resolve(), st.st_size,
                            int(st.st_mtime))
    except Exception:  # noqa: BLE001
        sig = str(p)
    key = hashlib.sha1(sig.encode()).hexdigest()[:12]
    return (root or SCRATCH_DIR) / ("%s-%s" % (p.stem, key))


def _extract_zip_member(path, member, dest):
    with zipfile.ZipFile(str(path)) as zf:
        with zf.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)


def _extract_7z_member(path, member, dest, tmp_root):
    backend = seven_zip_backend()
    if backend == "py7zr":
        py7zr = _py7zr()
        with py7zr.SevenZipFile(str(path), "r") as zf:
            zf.extract(path=str(tmp_root), targets=[member])
        got = tmp_root / member
        if not got.is_file():
            raise ArchiveError(
                "py7zr did not extract %s from %s."
                % (member, Path(str(path)).name))
        shutil.move(str(got), str(dest))
        return
    if backend == "cli":
        exe = _seven_zip_cli()
        r = subprocess.run(
            [exe, "x", "-y", "-o%s" % tmp_root, str(path), member],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise ArchiveError(
                "7z could not extract %s: %s"
                % (Path(str(path)).name,
                   (r.stderr or r.stdout).strip()[:200]))
        got = tmp_root / member
        if not got.is_file():
            raise ArchiveError(
                "7z did not extract %s from %s."
                % (member, Path(str(path)).name))
        shutil.move(str(got), str(dest))
        return
    raise ArchiveError(_no_7z_text())


def extract_iso(archive_path, root=None, log=_noop):
    """Extract the archive's disc image into local scratch and
    return the extracted file's Path. The archive is only read.
    Raises ArchiveError with a user-ready message."""
    p = Path(str(archive_path))
    if not p.is_file():
        raise ArchiveError("Archive not found: %s" % p)
    members = iso_members(p)
    if not members:
        raise ArchiveError(
            "%s contains no disc image (%s)."
            % (p.name, ", ".join(sorted(ISO_EXTS))))
    member, size = choose_member(members)
    if len(members) > 1:
        log("Archive holds %d disc images; extracting the "
            "largest: %s" % (len(members), member))
    out_dir = scratch_dir_for(p, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / Path(member).name
    marker = out_dir / ".done"
    if dest.is_file() and marker.is_file():
        try:
            if dest.stat().st_size == size and \
                    marker.read_text().strip() == member:
                log("Already extracted: %s" % dest)
                return dest
        except Exception:  # noqa: BLE001
            pass
    anchor = out_dir
    while not anchor.exists():
        anchor = anchor.parent
    free = shutil.disk_usage(str(anchor)).free
    if free < size:
        raise ArchiveError(
            "Not enough free space in %s to extract %s "
            "(%s needed, %s free). Extracted ISOs live in the "
            "app's data folder; delete old ones there to make "
            "room." % (out_dir, member, _gb(size), _gb(free)))
    log("Extracting %s from %s -> %s" % (member, p.name, dest))
    tmp = out_dir / (".partial-" + Path(member).name)
    if p.suffix.lower() == ".zip":
        _extract_zip_member(p, member, tmp)
    else:
        tmp_root = out_dir / ".tmp7z"
        shutil.rmtree(tmp_root, ignore_errors=True)
        tmp_root.mkdir(parents=True, exist_ok=True)
        try:
            _extract_7z_member(p, member, tmp, tmp_root)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
    if size and tmp.stat().st_size != size:
        got = tmp.stat().st_size
        tmp.unlink(missing_ok=True)
        raise ArchiveError(
            "Extraction of %s stopped at %s of %s -- the "
            "archive may be corrupt." % (member, _gb(got),
                                         _gb(size)))
    tmp.replace(dest)
    marker.write_text(member)
    log("Extracted: %s (%s)" % (dest, _gb(dest.stat().st_size)))
    return dest


def _gb(n):
    return "%.2f GB" % (n / float(1024 ** 3))
