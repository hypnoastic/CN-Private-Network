"""Meaningful regression tests for configuration, HTTP semantics and DNS rollback."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import backend_server
import client_dns
import env_loader
import service_control
import checks


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cn env ")
        self.path = Path(self.directory.name) / "network.env"
        self.original = (ROOT / "network.env.example").read_text()
        self.path.write_text(self.original)

    def tearDown(self):
        self.directory.cleanup()

    def test_aliases_and_port_defaults(self):
        env = env_loader.load_env(self.path)
        self.assertEqual(env["DNS_IP"], env["MAC1_IP"])
        self.assertEqual(env["EDGE_IP"], env["MAC2_IP"])
        self.assertEqual(env["BACKEND_A_IP"], env["MAC3_IP"])
        self.assertEqual(env["BACKEND_B_IP"], env["MAC4_IP"])
        self.assertEqual(env["APP_DOMAIN"], f"app.{env['TEAM_NAME']}.test")
        self.path.write_text("\n".join(line for line in self.original.splitlines() if not line.startswith(tuple(env_loader.DEFAULTS))))
        env = env_loader.load_env(self.path)
        self.assertEqual(env["BACKEND_A_PORT"], "3001")
        self.assertEqual(env["BACKEND_B_PORT"], "3002")
        self.assertEqual(env["HTTPS_PORT"], "8443")

    def test_rejects_invalid_configuration(self):
        original_env = env_loader.load_env(self.path)
        changes = [
            ("HTTPS_PORT=8443", "HTTPS_PORT=65536"),
            ("HTTPS_PORT=8443", "HTTPS_PORT=oops"),
            ("DNS_IP=${MAC1_IP}", "DNS_IP=${MAC2_IP}"),
            ("APP_DOMAIN=app.${TEAM_NAME}.test", "APP_DOMAIN=app.${TEAM_NAME}.local"),
            ("TEAM_NAME=team1", "TEAM_NAME=$(touch /tmp/should-not-run)"),
            ("TEAM_NAME=team1", "TEAM_NAME=${TEAM_NAME}"),
            ("DNS_IP=${MAC1_IP}", "DNS_IP=${UNKNOWN}"),
            ("DNS_IP=${MAC1_IP}", ""),
            (original_env["MAC4_IP"], original_env["MAC3_IP"]),
            (original_env["MAC1_IP"], "999.0.0.1"),
            (original_env["MAC1_IP"], "127.0.0.1"),
        ]
        for before, after in changes:
            with self.subTest(after=after):
                self.path.write_text(self.original.replace(before, after))
                with self.assertRaises(ValueError):
                    env_loader.load_env(self.path)
        for suffix in ("\nTEAM_NAME=duplicate", "\nUNKNOWN=yes", "\nnot-an-assignment"):
            self.path.write_text(self.original + suffix)
            with self.assertRaises(ValueError):
                env_loader.load_env(self.path)

    def test_missing_file_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "cp network.env.example network.env"):
            env_loader.load_env(self.path.with_name("missing.env"))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.servers = []
        for backend in ("A", "B"):
            server = backend_server.ThreadingHTTPServer(("127.0.0.1", 0), backend_server.handler_for(backend))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.servers.append((backend, server, thread))

    def tearDown(self):
        for _, server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()

    def request(self, server, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_endpoints_headers_head_and_404(self):
        for name, server, _ in self.servers:
            for path in ("/", "/api/status"):
                code, headers, body = self.request(server, path)
                self.assertEqual(code, 200)
                self.assertEqual(headers["X-Backend"], name)
                self.assertEqual(int(headers["Content-Length"]), len(body))
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
                if path == "/api/status":
                    self.assertEqual(json.loads(body), {"backend": name, "status": "ok"})
            code, headers, body = self.request(server, "/cache-demo", "HEAD")
            self.assertEqual(code, 200)
            self.assertEqual(body, b"")
            self.assertEqual(int(headers["Content-Length"]), len(backend_server.CACHE_BODY))
            self.assertEqual(self.request(server, "/missing")[0], 404)

    def test_shared_validator_and_bodyless_304(self):
        bodies = []
        for _, server, _ in self.servers:
            code, headers, body = self.request(server, "/cache-demo")
            bodies.append(body)
            self.assertEqual(headers["Cache-Control"], "public, max-age=60")
            self.assertEqual(headers["ETag"], '"cn-project-v1"')
            for etag in ('"cn-project-v1"', 'W/"cn-project-v1"', '"old", "cn-project-v1"', '*'):
                code, headers, body = self.request(server, "/cache-demo", headers={"If-None-Match": etag})
                self.assertEqual(code, 304)
                self.assertEqual(body, b"")
                self.assertEqual(headers["ETag"], '"cn-project-v1"')
            self.assertEqual(self.request(server, "/cache-demo", headers={"If-None-Match": '"old"'})[0], 200)
        self.assertEqual(bodies[0], bodies[1])


class CurlOutputTests(unittest.TestCase):
    def test_missing_output_file_is_allowed_only_for_304(self):
        for status in (304, 200):
            with self.subTest(status=status):
                def curl_without_body(command, **kwargs):
                    Path(command[command.index("--dump-header") + 1]).write_text(
                        f'HTTP/1.1 {status}\r\nETag: "cn-project-v1"\r\n\r\n')
                    return subprocess.CompletedProcess(command, 0, f"{status} 1.1", "")
                with patch.object(checks.subprocess, "run", side_effect=curl_without_body):
                    if status == 304:
                        code, _, headers, body = checks.request("https://app.unit.test/cache-demo", show=False)
                        self.assertEqual(code, 304)
                        self.assertEqual(headers["etag"], '"cn-project-v1"')
                        self.assertEqual(body, b"")
                    else:
                        with self.assertRaises(FileNotFoundError):
                            checks.request("https://app.unit.test/cache-demo", show=False)


class DnsRollbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name) / "runtime/client-dns.json"
        self.current = []
        self.env = env_loader.load_env(ROOT / "network.env.example")
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(client_dns, "STATE", self.state))
        self.stack.enter_context(patch.object(client_dns.platform, "system", return_value="Darwin"))
        self.stack.enter_context(patch.object(client_dns.os, "geteuid", return_value=501))
        self.stack.enter_context(patch.object(client_dns, "machine_id", return_value="this-mac"))
        self.stack.enter_context(patch.object(client_dns, "choose_service", return_value="Wi-Fi"))
        self.stack.enter_context(patch.object(client_dns, "load_env", return_value=self.env))
        self.stack.enter_context(patch.object(client_dns, "read_dns", side_effect=lambda _: (list(self.current), str(self.current))))
        self.stack.enter_context(patch.object(client_dns, "change", side_effect=self.change))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def tearDown(self):
        self.stack.close()
        self.directory.cleanup()

    def change(self, service, entries):
        self.assertEqual(service, "Wi-Fi")
        self.current = list(entries)

    def invoke(self, action):
        with patch.object(sys, "argv", ["client_dns.py", action]):
            client_dns.main()

    def test_automatic_and_explicit_dns_survive_repeat_and_failure_demo(self):
        for original in ([], ["1.1.1.1", "2606:4700:4700::1111"]):
            self.current = original.copy()
            self.invoke("set")
            saved = self.state.read_bytes()
            self.invoke("set")
            self.assertEqual(self.state.read_bytes(), saved)
            self.invoke("wrong-server")
            self.assertEqual(self.current, [self.env["MAC3_IP"]])
            self.invoke("repair-project")
            self.assertEqual(self.current, [self.env["DNS_IP"]])
            self.invoke("restore")
            self.assertEqual(self.current, original)
            self.assertFalse(self.state.exists())
            self.invoke("restore")

    def test_failed_change_preserves_original_backup(self):
        with patch.object(client_dns, "change", side_effect=subprocess.CalledProcessError(1, "networksetup")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.invoke("set")
        self.assertEqual(json.loads(self.state.read_text())["servers"], [])

    def test_foreign_backup_is_rejected_without_change(self):
        self.invoke("set")
        with patch.object(client_dns, "machine_id", return_value="different-mac"):
            with self.assertRaisesRegex(ValueError, "different Mac"):
                self.invoke("restore")
        self.assertTrue(self.state.exists())

class MacCommandTests(unittest.TestCase):
    def test_automatic_restore_uses_empty_and_checks_readback(self):
        with patch.object(client_dns.subprocess, "run") as run, patch.object(client_dns, "read_dns", return_value=([], "automatic")), patch.object(client_dns, "flush"):
            client_dns.change("Wi-Fi", [])
        run.assert_called_once_with(["sudo", "/usr/sbin/networksetup", "-setdnsservers", "Wi-Fi", "Empty"], check=True)

    def test_pid_identity_prevents_unrelated_process_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nginx.pid"
            path.write_text("1234")
            result = subprocess.CompletedProcess([], 0, "unrelated-process", "")
            with patch.object(service_control.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(ValueError, "another process"):
                    service_control.process_at(path, Path(tmp) / "nginx.conf", "nginx")

    def test_exited_child_is_treated_as_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nginx.pid"
            path.write_text("1234")
            result = subprocess.CompletedProcess([], 0, "Z <defunct>", "")
            with patch.object(service_control.subprocess, "run", return_value=result):
                self.assertIsNone(service_control.process_at(path, Path(tmp) / "nginx.conf", "nginx"))

    def test_native_validation_failure_prevents_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "mac2_edge/runtime"
            runtime.mkdir(parents=True)
            (runtime / "nginx.conf").write_text("broken configuration")
            with patch.object(service_control, "ROOT", root), patch.object(service_control, "brew_binary", return_value="nginx"), patch.object(service_control, "load_env", return_value={"HTTPS_PORT": "8443"}), patch.object(service_control.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "nginx -t")), patch.object(service_control.os, "execvp") as execute, patch.object(sys, "argv", ["service_control.py", "nginx", "start"]):
                with self.assertRaises(subprocess.CalledProcessError):
                    service_control.main()
                execute.assert_not_called()


class OfficialCheckTests(unittest.TestCase):
    def setUp(self):
        self.env = env_loader.load_env(ROOT / "network.env.example")

    def test_load_balancing_rejects_only_one_backend(self):
        with patch.object(checks, "load_env", return_value=self.env), patch.object(checks, "status_response", return_value="A"), patch.object(sys, "argv", ["checks.py", "balancing"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Both backends required"):
                checks.main()

    def test_load_balancing_accepts_both_backends(self):
        with patch.object(checks, "load_env", return_value=self.env), patch.object(checks, "status_response", side_effect=["A", "B"] * 5), patch.object(sys, "argv", ["checks.py", "balancing"]), contextlib.redirect_stdout(io.StringIO()) as output:
            checks.main()
        self.assertIn("PASS", output.getvalue())

    def test_caching_rejects_a_body_in_304(self):
        headers = {"cache-control": "public, max-age=60", "etag": '"cn-project-v1"'}
        responses = [(200, "1.1", headers, b"content"), (304, "1.1", headers, b"invalid body")]
        with patch.object(checks, "request", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "must not contain"):
                checks.test_caching("https://unit.test")


if __name__ == "__main__":
    unittest.main()
