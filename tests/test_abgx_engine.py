"""Unit tests for the abgx360 GUI engine layer.

Stdlib unittest only (the engine imports no Qt). Run from the
repo root:  python3 -m unittest discover -s tests -v

Covers the command builder (the cases recorded in BUILD-REPORT.md
against the original GUI's UIUpdate()) and the build-dependency
pre-flight added 2026-11-21 (detection, package mapping, the
pkexec install command, the configure-failure safety net).
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "src" / "Abgx360GUI"))

from app import abgx_engine as engine  # noqa: E402


def settings(**over):
    s = dict(engine.DEFAULT_SETTINGS)
    s.update(over)
    return s


FILE = {"kind": "file", "path": "/games/Some Game.iso"}


class CommandBuilderTests(unittest.TestCase):
    def argv(self, s, item=FILE):
        return engine.build_argv(s, item)

    def test_defaults(self):
        self.assertEqual(self.argv(settings())[1:],
                         ["-t", "--", FILE["path"]])
        self.assertEqual(
            engine.preview_command(settings(), FILE),
            'abgx360 -t -- "/games/Some Game.iso"')

    def test_stealth_off_forces_noverify(self):
        a = self.argv(settings(CheckStealth=False))
        self.assertIn("-rt", a)
        self.assertIn("--noverify", a)

    def test_html_with_images(self):
        a = self.argv(settings(ProgramOutput=1))
        self.assertIn("-thi", a)

    def test_dir_match_recurse(self):
        a = self.argv(settings(MatchOnly=True, MatchMask="*.iso",
                               RecurseSubdirs=True),
                      {"kind": "dir", "path": "/games"})
        i = a.index("--match")
        self.assertEqual(a[i + 1], ",*.iso")
        self.assertIn("--rec", a)
        self.assertEqual(a[-2:], ["--dir", "/games"])

    def test_dvd_forces_writes_off(self):
        a = self.argv(settings(), {"kind": "dvd", "path": "/dev/sr0"})
        self.assertIn("-tw", a)
        self.assertEqual(a[-2:], ["--dvd", "/dev/sr0"])

    def test_spot_check_combo(self):
        # The build report's recorded spot-check invocation.
        a = self.argv(settings(Verbosity=2, AutoFix=0, SplitVid=0,
                               StayOffline=True))
        self.assertEqual(a[1], "-vto")
        self.assertIn("--af3", a)
        self.assertIn("--noupdate", a)
        self.assertIn("--splitvid", a)

    def test_game_crc_never_suppresses_corruption(self):
        a = self.argv(settings(CheckGameCRCWhenNeeded=False,
                               CheckCorruption=True))
        self.assertIn("g", a[1])
        self.assertNotIn("c", a[1])
        self.assertNotIn("--csv", a)

    def test_rebuild_method_suppresses_keep_original(self):
        a = self.argv(settings(RebuildMethod=1, KeepOriginalISO=True))
        self.assertIn("l", a[1])
        self.assertNotIn("-k", a)

    def test_images_never_suppresses_embed(self):
        a = self.argv(settings(XexImages=2, EmbedImages=True))
        self.assertNotIn("--embed", a)

    def test_autofix_levels_and_dev(self):
        self.assertIn("--af1", self.argv(settings(AutoFix=2)))
        self.assertIn("--af0", self.argv(settings(AutoFix=3)))
        self.assertIn("--nofixdev",
                      self.argv(settings(FixBadAngles=False)))
        a = self.argv(settings(FixBadAnglesValue=5))
        self.assertEqual(a[a.index("--dev") + 1], "5")


CURL = ("curl", "the libcurl development files (curl-config)",
        False, "libcurl4-openssl-dev", "libcurl-devel")


def fake_which(present):
    def _which(name, *a, **k):
        return "/usr/bin/" + name if name in present else None
    return _which


class DepDetectionTests(unittest.TestCase):
    ALL = {"gcc", "make", "curl-config", "pkexec"}

    def run_checks(self, present, zlib=True):
        with mock.patch("shutil.which", fake_which(present)), \
                mock.patch.object(engine, "_zlib_dev_present",
                                  lambda: zlib):
            return engine.check_build_deps()

    def test_all_present_no_missing(self):
        checks = self.run_checks(self.ALL)
        self.assertTrue(all(c[2] for c in checks))
        with mock.patch("shutil.which", fake_which(self.ALL)), \
                mock.patch.object(engine, "_zlib_dev_present",
                                  lambda: True):
            self.assertEqual(engine.missing_build_deps(), [])

    def test_missing_curl_config_is_the_field_case(self):
        checks = self.run_checks(self.ALL - {"curl-config"})
        missing = [c for c in checks if not c[2]]
        self.assertEqual([c[0] for c in missing], ["curl"])
        self.assertEqual(missing[0][3], "libcurl4-openssl-dev")
        self.assertEqual(missing[0][4], "libcurl-devel")

    def test_missing_compiler_and_make_share_build_essential(self):
        checks = self.run_checks({"curl-config"})
        missing = [c for c in checks if not c[2]]
        self.assertEqual({c[0] for c in missing}, {"cc", "make"})
        # zlib patched present above; both cc and make map to the
        # one apt package.
        info = engine.dep_info(missing)
        self.assertEqual(info["packages"], ["build-essential"])


class DepInfoTests(unittest.TestCase):
    def info(self, family, missing):
        with mock.patch.object(engine, "distro_family",
                               lambda os_release=None: family):
            return engine.dep_info(missing)

    def test_debian_packages_and_command(self):
        info = self.info("debian", [CURL])
        self.assertEqual(info["packages"], ["libcurl4-openssl-dev"])
        self.assertEqual(info["manual_command"],
                         "sudo apt-get install -y "
                         "libcurl4-openssl-dev")
        self.assertIn("libcurl4-openssl-dev", info["manual_text"])

    def test_fedora_fallback_names(self):
        info = self.info("fedora", [CURL])
        self.assertEqual(info["manual_command"],
                         "sudo dnf install -y libcurl-devel")
        self.assertEqual(info["alt_packages"], ["libcurl-devel"])

    def test_other_distro_is_text_only(self):
        info = self.info("other", [CURL])
        self.assertIn("libcurl-devel", info["manual_command"])
        self.assertNotIn("apt-get", info["manual_command"])
        self.assertNotIn("dnf install", info["manual_command"])

    def test_distro_family_parsing(self):
        self.assertEqual(engine.distro_family(
            {"ID": "ubuntu", "ID_LIKE": "debian"}), "debian")
        self.assertEqual(engine.distro_family(
            {"ID": "linuxmint", "ID_LIKE": "ubuntu debian"}),
            "debian")
        self.assertEqual(engine.distro_family(
            {"ID": "fedora", "ID_LIKE": ""}), "fedora")
        self.assertEqual(engine.distro_family(
            {"ID": "arch", "ID_LIKE": ""}), "other")


class InstallCommandTests(unittest.TestCase):
    def test_pkexec_command_construction(self):
        captured = {}

        def fake_run(cmd, cwd, log, env=None, timeout=None):
            captured["cmd"] = [str(c) for c in cmd]
            return 0

        states = [[CURL], []]
        with mock.patch.object(engine, "missing_build_deps",
                               side_effect=lambda: states.pop(0)), \
                mock.patch.object(engine, "distro_family",
                                  lambda os_release=None: "debian"), \
                mock.patch("shutil.which",
                           fake_which({"pkexec"})), \
                mock.patch.object(engine, "_run_stream", fake_run):
            self.assertTrue(engine.install_missing_deps())
        self.assertEqual(
            captured["cmd"],
            ["pkexec", "sh", "-c",
             "apt-get update -qq && apt-get install -y "
             "libcurl4-openssl-dev"])

    def test_still_missing_after_attempt_returns_false(self):
        with mock.patch.object(engine, "missing_build_deps",
                               lambda: [CURL]), \
                mock.patch.object(engine, "distro_family",
                                  lambda os_release=None: "debian"), \
                mock.patch("shutil.which",
                           fake_which({"pkexec"})), \
                mock.patch.object(engine, "_run_stream",
                                  lambda *a, **k: 0):
            self.assertFalse(engine.install_missing_deps())

    def test_no_pkexec_no_attempt(self):
        with mock.patch.object(engine, "missing_build_deps",
                               lambda: [CURL]), \
                mock.patch.object(engine, "distro_family",
                                  lambda os_release=None: "debian"), \
                mock.patch("shutil.which", fake_which(set())), \
                mock.patch.object(
                    engine, "_run_stream",
                    side_effect=AssertionError("must not run")):
            self.assertFalse(engine.install_missing_deps())

    def test_non_debian_never_installs(self):
        with mock.patch.object(engine, "missing_build_deps",
                               lambda: [CURL]), \
                mock.patch.object(engine, "distro_family",
                                  lambda os_release=None: "fedora"), \
                mock.patch.object(
                    engine, "_run_stream",
                    side_effect=AssertionError("must not run")):
            self.assertFalse(engine.install_missing_deps())


class EnsureEnginePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(engine, "ENGINE_DIR",
                              Path(self.tmp.name) / "engine")
        p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch.object(engine, "engine_ready", lambda: False)
        p2.start()
        self.addCleanup(p2.stop)

    def test_missing_deps_raise_before_any_fetch(self):
        with mock.patch.object(engine, "missing_build_deps",
                               lambda: [CURL]), \
                mock.patch.object(
                    engine, "_build_linux",
                    side_effect=AssertionError("must not build")):
            with self.assertRaises(engine.DepsMissingError) as cm:
                engine.ensure_engine()
        self.assertEqual(cm.exception.info["packages"],
                         ["libcurl4-openssl-dev"])

    def test_install_deps_true_installs_then_builds(self):
        calls = []
        states = [[CURL], []]
        with mock.patch.object(
                engine, "missing_build_deps",
                side_effect=lambda: states.pop(0) if states else []), \
                mock.patch.object(
                    engine, "install_missing_deps",
                    lambda log: calls.append("install") or True), \
                mock.patch.object(
                    engine, "_build_linux",
                    lambda log: calls.append("build")), \
                mock.patch.object(engine, "engine_ready",
                                  lambda: bool(calls)):
            # engine_ready is checked again after the build; the
            # lambda above flips once install/build ran.
            self.assertTrue(engine.ensure_engine(install_deps=True))
        self.assertEqual(calls, ["install", "build"])


class ConfigureSafetyNetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.tree = root / "tree"
        src = self.tree / "linux" / "abgx360"
        src.mkdir(parents=True)
        (src / "configure").write_text("# fake\n")
        for p in (mock.patch.object(engine, "ENGINE_DIR",
                                    root / "engine"),
                  mock.patch.object(engine, "_fetch_source",
                                    lambda log: self.tree),
                  mock.patch.object(engine, "distro_family",
                                    lambda os_release=None: "debian")):
            p.start()
            self.addCleanup(p.stop)

    def run_build(self, log_lines, rc=1):
        def fake_run(cmd, cwd, log, env=None, timeout=None):
            for line in log_lines:
                log(line)
            return rc
        with mock.patch.object(engine, "_run_stream", fake_run):
            engine._build_linux(lambda _m: None)

    def test_libcurl_configure_failure_becomes_deps_error(self):
        with mock.patch.object(engine, "missing_build_deps",
                               lambda: []):
            with self.assertRaises(engine.DepsMissingError) as cm:
                self.run_build(
                    ["checking for curl-config... no",
                     'configure: error: "libcurl not found!"'])
        self.assertIn("libcurl4-openssl-dev",
                      cm.exception.info["packages"])

    def test_other_configure_failure_stays_generic(self):
        with self.assertRaises(engine.EngineError) as cm:
            self.run_build(["configure: error: something else"])
        self.assertNotIsInstance(cm.exception,
                                 engine.DepsMissingError)


if __name__ == "__main__":
    unittest.main()
