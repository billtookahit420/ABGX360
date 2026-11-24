"""Unit tests for the archive-input layer (app/archive_input.py)
and the engine's run_path handling.

Stdlib unittest; the .7z cases need py7zr and skip without it.
Run from the repo root:  python3 -m unittest discover -s tests -v

Covers .zip/.7z input (added 2026-11-22 alongside network-share
browsing): archives yield their disc image into LOCAL scratch,
the source archive is never modified, and the engine checks the
extracted file while the queue keeps showing the archive.
"""
import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "src" / "Abgx360GUI"))

from app import archive_input as arch  # noqa: E402
from app import abgx_engine as engine  # noqa: E402

try:
    import py7zr  # noqa: F401
    HAVE_PY7ZR = True
except Exception:  # noqa: BLE001
    HAVE_PY7ZR = False

ISO_BYTES = b"\x00" * 4096 + b"DUMMY-ISO-PAYLOAD" + b"\x01" * 4096


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def make_zip(path, members):
    with zipfile.ZipFile(str(path), "w",
                         zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class IsArchiveTests(unittest.TestCase):
    def test_suffixes(self):
        self.assertTrue(arch.is_archive("game.ZIP"))
        self.assertTrue(arch.is_archive("game.7z"))
        self.assertFalse(arch.is_archive("game.iso"))
        self.assertFalse(arch.is_archive("game.rar"))


class ZipInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src_dir = self.base / "share"
        self.src_dir.mkdir()
        self.scratch = self.base / "scratch"
        self.arc = self.src_dir / "Dummy Game.zip"
        make_zip(self.arc, {
            "Dummy Game.iso": ISO_BYTES,
            "Dummy Game.dvd": b"layerbreak=1913760\n",
            "readme.txt": b"hello",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_members_lists_only_disc_images(self):
        members = arch.iso_members(self.arc)
        self.assertEqual(members, [("Dummy Game.iso",
                                    len(ISO_BYTES))])

    def test_extract_to_local_scratch(self):
        before = sha256(self.arc)
        out = arch.extract_iso(self.arc, root=self.scratch)
        self.assertEqual(out.read_bytes(), ISO_BYTES)
        # scratch is local: under the given root, NOT beside the
        # archive on the "share"
        self.assertTrue(str(out).startswith(str(self.scratch)))
        self.assertFalse(str(out).startswith(str(self.src_dir)))
        # the source archive is untouched
        self.assertEqual(sha256(self.arc), before)

    def test_extract_reuses(self):
        first = arch.extract_iso(self.arc, root=self.scratch)
        mtime = first.stat().st_mtime_ns
        second = arch.extract_iso(self.arc, root=self.scratch)
        self.assertEqual(first, second)
        self.assertEqual(second.stat().st_mtime_ns, mtime)

    def test_no_iso_member(self):
        p = self.src_dir / "empty.zip"
        make_zip(p, {"notes.txt": b"x"})
        with self.assertRaises(arch.ArchiveError) as cm:
            arch.extract_iso(p, root=self.scratch)
        self.assertIn("no disc image", str(cm.exception))

    def test_largest_member_wins(self):
        p = self.src_dir / "multi.zip"
        make_zip(p, {"small.iso": b"s" * 10,
                     "big.iso": b"b" * 5000})
        out = arch.extract_iso(p, root=self.scratch)
        self.assertEqual(out.name, "big.iso")
        self.assertEqual(out.stat().st_size, 5000)

    def test_free_space_guard(self):
        usage = mock.Mock(free=1)
        with mock.patch.object(arch.shutil, "disk_usage",
                               return_value=usage):
            with self.assertRaises(arch.ArchiveError) as cm:
                arch.extract_iso(self.arc, root=self.scratch)
        self.assertIn("Not enough free space",
                      str(cm.exception))

    def test_bad_zip(self):
        p = self.src_dir / "bad.zip"
        p.write_bytes(b"this is not a zip")
        with self.assertRaises(arch.ArchiveError):
            arch.iso_members(p)


@unittest.skipUnless(HAVE_PY7ZR, "py7zr not installed")
class SevenZipInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src_dir = self.base / "share"
        self.src_dir.mkdir()
        self.scratch = self.base / "scratch"
        self.arc = self.src_dir / "Dummy Game.7z"
        stage = self.base / "stage"
        stage.mkdir()
        (stage / "Dummy Game.iso").write_bytes(ISO_BYTES)
        (stage / "Dummy Game.dvd").write_text("layerbreak=1\n")
        import py7zr
        with py7zr.SevenZipFile(str(self.arc), "w") as zf:
            zf.writeall(str(stage / "Dummy Game.iso"),
                        "Dummy Game.iso")
            zf.writeall(str(stage / "Dummy Game.dvd"),
                        "Dummy Game.dvd")

    def tearDown(self):
        self.tmp.cleanup()

    def test_backend_is_py7zr(self):
        self.assertEqual(arch.seven_zip_backend(), "py7zr")

    def test_members(self):
        members = arch.iso_members(self.arc)
        self.assertEqual(members, [("Dummy Game.iso",
                                    len(ISO_BYTES))])

    def test_extract(self):
        before = sha256(self.arc)
        out = arch.extract_iso(self.arc, root=self.scratch)
        self.assertEqual(out.read_bytes(), ISO_BYTES)
        self.assertTrue(str(out).startswith(str(self.scratch)))
        self.assertEqual(sha256(self.arc), before)


class NoSevenZipTests(unittest.TestCase):
    def test_error_names_options(self):
        with mock.patch.object(arch, "_py7zr", return_value=None), \
                mock.patch.object(arch, "_seven_zip_cli",
                                  return_value=None):
            with self.assertRaises(arch.ArchiveError) as cm:
                arch.iso_members("whatever.7z")
        self.assertIn("py7zr", str(cm.exception))
        self.assertIn("p7zip", str(cm.exception))


class RunPathTests(unittest.TestCase):
    def test_engine_uses_run_path(self):
        item = {"kind": "file", "path": "/share/Game.zip",
                "run_path": "/local/extracted/Game.iso"}
        argv = engine.build_argv(engine.DEFAULT_SETTINGS, item)
        self.assertEqual(argv[-1], "/local/extracted/Game.iso")
        preview = engine.preview_command(engine.DEFAULT_SETTINGS,
                                         item)
        self.assertIn('"/local/extracted/Game.iso"', preview)

    def test_engine_without_run_path_unchanged(self):
        item = {"kind": "file", "path": "/games/Game.iso"}
        argv = engine.build_argv(engine.DEFAULT_SETTINGS, item)
        self.assertEqual(argv[-1], "/games/Game.iso")


if __name__ == "__main__":
    unittest.main()
