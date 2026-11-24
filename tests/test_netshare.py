"""Unit tests for the network-share layer (app/netshare.py).

Stdlib unittest only (netshare imports no Qt). Run from the repo
root:  python3 -m unittest discover -s tests -v

Covers share-target parsing, UNC/URL construction, the remembered
shares file, GVFS mount discovery, and the gio mount wrapper --
the mechanisms behind the GUI's Network Share dialog (added
2026-11-22 so the pickers can see the home server's SMB shares).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "src" / "Abgx360GUI"))

from app import netshare  # noqa: E402


class ParseTargetTests(unittest.TestCase):
    def test_unc(self):
        t = netshare.parse_target(r"\\192.168.0.102\XBOX360 ARCHIVE")
        self.assertEqual(t["server"], "192.168.0.102")
        self.assertEqual(t["share"], "XBOX360 ARCHIVE")
        self.assertIsNone(t["port"])
        self.assertEqual(t["subpath"], "")

    def test_unc_with_subpath(self):
        t = netshare.parse_target(r"\\SERVER\share\games\Xbox 360")
        self.assertEqual(t["server"], "SERVER")
        self.assertEqual(t["share"], "share")
        self.assertEqual(t["subpath"], "games/Xbox 360")

    def test_smb_url(self):
        t = netshare.parse_target("smb://server.local/games")
        self.assertEqual(t["server"], "server.local")
        self.assertEqual(t["share"], "games")

    def test_smb_url_with_port(self):
        t = netshare.parse_target("smb://127.0.0.1:4445/fixture")
        self.assertEqual(t["server"], "127.0.0.1")
        self.assertEqual(t["port"], 4445)
        self.assertEqual(t["share"], "fixture")

    def test_plain_server_share(self):
        t = netshare.parse_target("192.168.0.102/PS2 ARCHIVE")
        self.assertEqual(t["server"], "192.168.0.102")
        self.assertEqual(t["share"], "PS2 ARCHIVE")

    def test_bare_server_plus_share_field(self):
        t = netshare.parse_target("192.168.0.102", "XBOX360 ARCHIVE")
        self.assertEqual(t["server"], "192.168.0.102")
        self.assertEqual(t["share"], "XBOX360 ARCHIVE")

    def test_embedded_share_wins_over_field(self):
        t = netshare.parse_target("srv/embedded", "fieldshare")
        self.assertEqual(t["share"], "embedded")

    def test_garbage(self):
        self.assertIsNone(netshare.parse_target(""))
        self.assertIsNone(netshare.parse_target("   "))
        self.assertIsNone(netshare.parse_target("just-a-server"))
        self.assertIsNone(netshare.parse_target(None))


class PathConstructionTests(unittest.TestCase):
    def test_unc_root(self):
        self.assertEqual(netshare.unc_root("192.168.0.102", "games"),
                         r"\\192.168.0.102\games")

    def test_smb_url(self):
        self.assertEqual(netshare.smb_url("srv", "games"),
                         "smb://srv/games")
        self.assertEqual(netshare.smb_url("srv", "games", 4445),
                         "smb://srv:4445/games")

    def test_share_label(self):
        self.assertEqual(
            netshare.share_label({"server": "srv", "share": "g",
                                  "port": None}), "srv/g")
        self.assertEqual(
            netshare.share_label({"server": "srv", "share": "g",
                                  "port": 4445}), "srv:4445/g")


class RememberedSharesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "shares.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_and_dedupe(self):
        netshare.remember_share("srv", "a", path=self.path)
        netshare.remember_share("srv", "b", path=self.path)
        netshare.remember_share("SRV", "A", path=self.path)
        shares = netshare.load_shares(self.path)
        self.assertEqual(len(shares), 2)
        self.assertEqual(shares[0]["share"], "A")
        self.assertEqual(shares[1]["share"], "b")

    def test_port_distinguishes_entries(self):
        netshare.remember_share("srv", "a", path=self.path)
        netshare.remember_share("srv", "a", port=4445,
                                path=self.path)
        self.assertEqual(len(netshare.load_shares(self.path)), 2)

    def test_missing_file_is_empty(self):
        self.assertEqual(netshare.load_shares(self.path), [])

    def test_corrupt_file_is_empty(self):
        self.path.write_text("not json {")
        self.assertEqual(netshare.load_shares(self.path), [])


class GvfsDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _mk(self, name):
        d = self.root / name
        d.mkdir()
        return d

    def test_find_plain(self):
        want = self._mk("smb-share:server=192.168.0.102,"
                        "share=XBOX360 ARCHIVE")
        self._mk("smb-share:server=other,share=nope")
        got = netshare.find_gvfs_mount(
            "192.168.0.102", "xbox360 archive", root=self.root)
        self.assertEqual(got, want)

    def test_find_with_encoded_port(self):
        want = self._mk("smb-share:server=127.0.0.1%3A4445,"
                        "share=fixture")
        got = netshare.find_gvfs_mount("127.0.0.1", "fixture",
                                       root=self.root)
        self.assertEqual(got, want)

    def test_find_missing(self):
        self._mk("smb-share:server=a,share=b")
        self.assertIsNone(netshare.find_gvfs_mount(
            "zzz", "b", root=self.root))
        self.assertIsNone(netshare.find_gvfs_mount(
            "a", "b", root=self.root / "does-not-exist"))


class GioMountTests(unittest.TestCase):
    def test_missing_gio_gives_package_hint(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value=None):
            ok, msg = netshare.gio_mount("srv", "share")
        self.assertFalse(ok)
        self.assertIn("gvfs-backends", msg)

    def test_success(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value="/usr/bin/gio"), \
                mock.patch.object(netshare, "_gio_mount",
                                  return_value=(0, "")) as gm:
            ok, _ = netshare.gio_mount("srv", "share", 4445)
        self.assertTrue(ok)
        self.assertEqual(gm.call_args[0][1],
                         "smb://srv:4445/share")

    def test_credentials_reach_url_and_engine(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value="/usr/bin/gio"), \
                mock.patch.object(netshare, "_gio_mount",
                                  return_value=(0, "")) as gm:
            ok, _ = netshare.gio_mount(
                "srv", "share", username="al ice",
                password="pw", workgroup="WG")
        self.assertTrue(ok)
        args = gm.call_args[0]
        self.assertEqual(args[1], "smb://al%20ice@srv/share")
        self.assertEqual(args[2:], ("al ice", "pw", "WG", 90))

    def test_already_mounted_is_success(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value="/usr/bin/gio"), \
                mock.patch.object(
                    netshare, "_gio_mount",
                    return_value=(1, "gio: smb://srv/share: "
                                     "Already mounted")):
            ok, _ = netshare.gio_mount("srv", "share")
        self.assertTrue(ok)

    def test_failure_message_passes_through(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value="/usr/bin/gio"), \
                mock.patch.object(
                    netshare, "_gio_mount",
                    return_value=(1, "Failed to mount: host "
                                     "down")):
            ok, msg = netshare.gio_mount("srv", "share")
        self.assertFalse(ok)
        self.assertIn("host down", msg)

    def test_timeout_message(self):
        with mock.patch.object(netshare.shutil, "which",
                               return_value="/usr/bin/gio"), \
                mock.patch.object(netshare, "_gio_mount",
                                  return_value=(124, "")):
            ok, msg = netshare.gio_mount("srv", "share")
        self.assertFalse(ok)
        self.assertIn("Timed out", msg)


FAKE_GIO = """#!/usr/bin/env python3
import os, sys
out = os.environ["FAKE_GIO_ANSWERS"]
def ask(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    return line.rstrip("\\n")
sys.stdout.write("Authentication Required\\n")
sys.stdout.write("Enter user and password for share "
                 "\\u201cshare\\u201d on \\u201csrv\\u201d:\\n")
sys.stdout.flush()
d = ask("Domain [WORKGROUP]: ")
p = ask("Password: ")
with open(out, "w") as fh:
    fh.write("domain=%s\\npassword=%s\\n" % (d, p))
"""


@unittest.skipUnless(os.name == "posix", "pty test is POSIX-only")
class GioPromptTests(unittest.TestCase):
    """Regression test for the prompt-answering bug found in
    the recomp-tools family: gio's header line contains the
    word "password" and the Domain prompt comes first, so a
    loop that keyword-searches the whole output buffer types
    the password into the Domain field and never answers the
    real Password prompt. Only the pending prompt (after the
    last newline) may be answered."""

    def test_password_lands_in_password_field(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "gio"
            answers = Path(td) / "answers.txt"
            fake.write_text(FAKE_GIO)
            fake.chmod(0o755)
            env = dict(os.environ, FAKE_GIO_ANSWERS=str(answers))
            with mock.patch.object(netshare.shutil, "which",
                                   return_value=str(fake)), \
                    mock.patch.dict(os.environ, env):
                ok, _msg = netshare.gio_mount(
                    "srv", "share", username="alice",
                    password="s3cret", workgroup="MYWG")
            self.assertTrue(ok)
            got = answers.read_text()
            self.assertIn("domain=MYWG", got)
            self.assertIn("password=s3cret", got)


class EnsureLocalPathTests(unittest.TestCase):
    def test_already_mounted_short_circuits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "smb-share:server=srv,share=sh").mkdir()
            with mock.patch.object(netshare, "gvfs_root",
                                   return_value=root), \
                    mock.patch.object(netshare, "gio_mount") as gm:
                got = netshare.ensure_local_path("srv", "sh")
            self.assertTrue(got.endswith("share=sh"))
            gm.assert_not_called()

    def test_mount_failure_raises_user_message(self):
        with mock.patch.object(netshare, "find_gvfs_mount",
                               return_value=None), \
                mock.patch.object(netshare, "gio_mount",
                                  return_value=(False, "boom")):
            with self.assertRaises(netshare.NetShareError) as cm:
                netshare.ensure_local_path("srv", "sh")
        self.assertEqual(str(cm.exception), "boom")


if __name__ == "__main__":
    unittest.main()
