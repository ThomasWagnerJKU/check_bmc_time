"""Tests for check_bmc_time with a fake bmc-device (no BMC needed)."""
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), "check_bmc_time")

# fake bmc-device: prints the SEL time from $FAKE_SEL ("MM/DD/YYYY - HH:MM:SS"), records its
# arguments and the content of the --config-file in $FAKE_LOG, exits with $FAKE_RC
FAKE = r"""#!/usr/bin/env python3
import os, sys
with open(os.environ["FAKE_LOG"], "w") as log:
    log.write("ARGS " + repr(sys.argv[1:]) + "\n")
    for a in sys.argv[1:]:
        if a.startswith("--config-file="):
            path = a.split("=", 1)[1]
            log.write("CONFMODE %o\n" % (os.stat(path).st_mode & 0o777))
            log.write("CONF " + open(path).read().replace("\n", "|") + "\n")
rc = int(os.environ.get("FAKE_RC", "0"))
if rc:
    print("bmc-device: connection timeout (user " + os.environ.get("FAKE_ECHO", "") + ")")
else:
    print("SEL Time : " + os.environ["FAKE_SEL"])
sys.exit(rc)
"""


def sel(epoch):
    return time.strftime("%m/%d/%Y - %H:%M:%S", time.gmtime(epoch))


class CheckBmcTime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = os.path.join(self.tmp.name, "bmc-device")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        os.chmod(self.fake, stat.S_IRWXU)
        self.log = os.path.join(self.tmp.name, "log")

    def tearDown(self):
        self.tmp.cleanup()

    def run_plugin(self, sel_epoch=None, *extra, tz="UTC", rc=0, echo=""):
        env = dict(os.environ, FAKE_LOG=self.log, FAKE_SEL=sel(sel_epoch if sel_epoch is not None else time.time()),
                   FAKE_RC=str(rc), FAKE_ECHO=echo, TZ=tz, TMPDIR=self.tmp.name)
        r = subprocess.run([sys.executable, PLUGIN, "-H", "bmc.example", "-U", "monitor",
                            "--bmc-device", self.fake] + list(extra), capture_output=True, text=True, env=env)
        return r.returncode, r.stdout.strip()

    def log_text(self):
        with open(self.log) as f:
            return f.read()

    def test_in_sync(self):
        rc, out = self.run_plugin(None, "-P", "secret")
        self.assertEqual(rc, 0, out)
        self.assertIn("BMC TIME OK", out)
        self.assertRegex(out, r"\| offset=-?[01]s;-60:60;-300:300;;$")

    def test_warning_and_critical(self):
        rc, out = self.run_plugin(time.time() - 120, "-P", "secret")
        self.assertEqual(rc, 1, out)
        # the SEL time is cut to whole seconds and the plugin reads the clock a moment later,
        # so the offset may be one second off
        self.assertRegex(out, r"2m 0[01]s behind")
        rc, out = self.run_plugin(time.time() + 70 * 86400, "-P", "secret")
        self.assertEqual(rc, 2, out)
        self.assertRegex(out, r"(70d 0h 00m|69d 23h 59m) ahead")

    def test_local_time_bmc(self):
        # a BMC that keeps local time (here fixed UTC+1, "Etc/GMT-1" has no DST) is in sync
        rc, out = self.run_plugin(time.time() + 3600, "-P", "secret", tz="Etc/GMT-1")
        self.assertEqual(rc, 0, out)
        self.assertIn("(local time) in sync", out)
        # and a UTC BMC under the same time zone as well
        rc, out = self.run_plugin(time.time(), "-P", "secret", tz="Etc/GMT-1")
        self.assertEqual(rc, 0, out)
        self.assertIn("(UTC) in sync", out)

    def test_password_not_on_command_line(self):
        rc, out = self.run_plugin(None, "-P", "s3cr3t")
        log = self.log_text()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("s3cr3t", log.split("\n")[0])          # not in the arguments
        self.assertIn("CONF username monitor|password s3cr3t|", log)
        self.assertIn("CONFMODE 600", log)
        leftovers = [f for f in os.listdir(self.tmp.name) if f.startswith("check_bmc_time.")]
        self.assertEqual(leftovers, [], "temporary config file not removed")

    def test_password_file(self):
        pwfile = os.path.join(self.tmp.name, "pw")
        with open(pwfile, "w") as f:
            f.write("fromfile\n")
        rc, out = self.run_plugin(None, "-f", pwfile)
        self.assertEqual(rc, 0, out)
        self.assertIn("password fromfile|", self.log_text())

    def test_password_with_blank_falls_back_to_command_line(self):
        rc, out = self.run_plugin(None, "-P", "with blank")
        self.assertEqual(rc, 0, out)
        self.assertIn("'-p', 'with blank'", self.log_text())

    def test_extra_options_passed(self):
        self.run_plugin(None, "-P", "x", "--extra", "-W authcap")
        self.assertIn("'-W', 'authcap'", self.log_text())

    def test_unreadable_bmc_hides_secrets(self):
        rc, out = self.run_plugin(None, "-P", "topsecret", rc=1, echo="monitor topsecret")
        self.assertEqual(rc, 3, out)
        self.assertIn("BMC TIME UNKNOWN - cannot read the BMC clock (bmc-device exit 1)", out)
        self.assertNotIn("topsecret", out)
        self.assertNotIn("monitor", out)

    def test_missing_password_file(self):
        rc, out = self.run_plugin(None, "-f", "/nonexistent/pw")
        self.assertEqual(rc, 3, out)
        self.assertIn("cannot read the password file", out)

    def test_warning_larger_than_critical(self):
        rc, out = self.run_plugin(None, "-P", "x", "-w", "500", "-c", "100")
        self.assertEqual(rc, 3, out)


if __name__ == "__main__":
    unittest.main()
