"""Setup automation regression tests; system mutations are simulated."""
import contextlib
import io
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import env_loader
import launcher
import service_control


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="cn wizard ")
        self.root = Path(self.work.name)
        shutil.copyfile(ROOT / "network.env.example", self.root / "network.env.example")
        self.env = env_loader.load_env(ROOT / "network.env.example")
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(launcher, "ROOT", self.root))
        self.stack.enter_context(patch.object(launcher, "RUNTIME", self.root / "shared/runtime"))

    def tearDown(self):
        self.stack.close()
        self.work.cleanup()

    def test_wizard_derives_aliases_and_validates_before_replace(self):
        ips = [self.env[f"MAC{n}_IP"] for n in range(1, 5)]
        text = launcher.configuration_text("group7", ips, "9443")
        result = launcher.write_configuration(text)
        self.assertEqual(result["APP_DOMAIN"], "app.group7.test")
        self.assertEqual(result["EDGE_IP"], ips[1])
        self.assertEqual(result["HTTPS_PORT"], "9443")
        custom = launcher.write_configuration(launcher.configuration_text("group7", ips, "9443", {"BACKEND_A_PORT": "4001", "BACKEND_B_PORT": "4002"}))
        self.assertEqual(custom["BACKEND_A_PORT"], "4001")
        self.assertEqual(custom["BACKEND_B_PORT"], "4002")
        before = (self.root / "network.env").read_bytes()
        with self.assertRaises(ValueError):
            launcher.write_configuration(launcher.configuration_text("group7", [ips[0]] * 4))
        self.assertEqual((self.root / "network.env").read_bytes(), before)

    def test_existing_configuration_is_reused_without_prompt(self):
        shutil.copyfile(self.root / "network.env.example", self.root / "network.env")
        with patch.object(launcher, "load_env", return_value=self.env), patch.object(launcher, "prompt") as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.configure(1), self.env)
        prompt.assert_not_called()

    def test_wrong_local_role_is_rejected(self):
        with patch.object(launcher, "addresses", return_value=[self.env["MAC4_IP"]]):
            with self.assertRaisesRegex(ValueError, "selected Mac 1"):
                launcher.check_local_role(1, self.env)


class CertificateBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.env = env_loader.load_env(ROOT / "network.env.example")

    def test_fingerprint_accepts_openssl_labels_but_rejects_invalid_input(self):
        value = ":".join(["ab"] * 32)
        for prefix in ("", "Fingerprint=", "sha256 Fingerprint=", "SHA-256 Fingerprint= "):
            with self.subTest(prefix=prefix):
                self.assertEqual(launcher.normalize_fingerprint(prefix + value), "AB" * 32)
        for value in ("AB" * 31, "ZZ" * 32, "SHA1 Fingerprint=" + "AB" * 32):
            with self.assertRaises(ValueError):
                launcher.normalize_fingerprint(value)

    def test_mismatched_fingerprint_never_installs_trust(self):
        with patch.object(launcher, "fetch_certificate", return_value=Path("candidate.crt")), patch.object(launcher, "system_trusts", return_value=False), patch.object(launcher, "show_fingerprint", return_value="AB" * 32), patch.object(launcher, "prompt", return_value="CD" * 32), patch.object(launcher, "script") as script, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Fingerprint did not match"):
                launcher.trust_for_client(4, self.env)
        script.assert_not_called()

    def test_matching_fingerprint_installs_and_checks_system_trust(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared").mkdir()
            candidate = root / "candidate.crt"
            candidate.write_text("public certificate test fixture")
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "fetch_certificate", return_value=candidate), patch.object(launcher, "system_trusts", side_effect=[False, True]) as verify, patch.object(launcher, "show_fingerprint", return_value="AB" * 32), patch.object(launcher, "prompt", return_value=":".join(["ab"] * 32)), patch.object(launcher, "script") as script, contextlib.redirect_stdout(io.StringIO()):
                launcher.trust_for_client(4, self.env)
            script.assert_called_once_with("shared/trust_certificate.sh", str(candidate))
            self.assertEqual(verify.call_count, 2)
            self.assertEqual((root / "shared/trusted/server.crt").read_text(), candidate.read_text())

    def test_already_trusted_certificate_needs_no_import_or_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared").mkdir()
            candidate = root / "candidate.crt"
            candidate.write_text("public certificate test fixture")
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "fetch_certificate", return_value=candidate), patch.object(launcher, "system_trusts", return_value=True), patch.object(launcher, "prompt") as prompt, patch.object(launcher, "script") as script, contextlib.redirect_stdout(io.StringIO()):
                launcher.trust_for_client(1, self.env)
            prompt.assert_not_called()
            script.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def test_dns_background_logging_round_trip_preserves_records(self):
        with tempfile.TemporaryDirectory(prefix="dns log ") as tmp:
            path = Path(tmp) / "dnsmasq.conf"
            original = "log-facility=-\nhost-record=app.unit.test,127.0.0.1\n"
            path.write_text(original)
            service_control.configure_dns_logging(path, True)
            self.assertIn(f"log-facility={path.parent / 'dnsmasq.log'}", path.read_text())
            self.assertIn("host-record=app.unit.test,127.0.0.1", path.read_text())
            service_control.configure_dns_logging(path, False)
            self.assertEqual(path.read_text(), original)

    def test_restore_failure_does_not_stop_dns(self):
        with patch.object(launcher, "script", side_effect=ValueError("restore failed")), patch.object(launcher, "stop_service") as stop:
            with self.assertRaisesRegex(ValueError, "restore failed"):
                launcher.stop_and_restore(1)
        stop.assert_not_called()

    def test_backend_b_starts_before_waiting_for_other_macs(self):
        env = env_loader.load_env(ROOT / "network.env.example")
        order = []
        with patch.object(launcher, "configure", return_value=env), patch.object(launcher, "check_local_role"), patch.object(launcher, "dependencies"), patch.object(launcher, "start_backend", side_effect=lambda *_: order.append("backend")), patch.object(launcher, "run") as run, patch.object(launcher, "finish_client", side_effect=lambda *_: order.append("client")), contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            launcher.setup(4, 0)
        self.assertEqual(order, ["backend", "client"])

    def test_wait_failure_is_explicit_and_retryable(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "left running"):
                launcher.wait_for("Mac 2", lambda: False, 0)

    def test_background_nginx_validates_and_uses_native_daemon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "mac2_edge/runtime"
            runtime.mkdir(parents=True)
            (runtime / "nginx.conf").write_text("test config")
            with patch.object(service_control, "ROOT", root), patch.object(service_control, "process_at", side_effect=[None, 123]), patch.object(service_control, "brew_binary", return_value="nginx"), patch.object(service_control, "load_env", return_value={"HTTPS_PORT": "8443"}), patch.object(service_control.subprocess, "run") as run, patch.object(service_control.os, "execvp") as execute, patch.object(sys, "argv", ["service_control.py", "nginx", "start", "--background"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(service_control.main(), 0)
            self.assertIn("-t", run.call_args_list[0].args[0])
            self.assertNotIn("daemon off;", run.call_args_list[1].args[0])
            execute.assert_not_called()


class BackgroundBackendTest(unittest.TestCase):
    def test_detached_backend_start_response_restart_and_stop(self):
        with tempfile.TemporaryDirectory(prefix="cn background ") as tmp:
            root = Path(tmp).resolve() / "project"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "runtime", "__pycache__", "network.env", "certs", "trusted", "collected"))
            env = env_loader.load_env(ROOT / "network.env.example")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                env["BACKEND_A_PORT"] = str(sock.getsockname()[1])
            (root / "network.env").write_text("\n".join(f"{k}={v}" for k, v in env.items()))
            with patch.object(launcher, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                try:
                    launcher.start_backend(3, env)
                    first = launcher.running(3)
                    self.assertIsNotNone(first)
                    result = launcher.run(["/usr/bin/curl", "--disable", "--noproxy", "*", "-si", f"http://127.0.0.1:{env['BACKEND_A_PORT']}/api/status"], capture=True)
                    self.assertIn("X-Backend: A", result.stdout)
                    launcher.start_backend(3, env)
                    self.assertNotEqual(first, launcher.running(3))
                finally:
                    launcher.stop_service(3)
                self.assertIsNone(launcher.running(3))


if __name__ == "__main__":
    unittest.main()
