"""Regression checks for the observed hotspot resolver issue; no OS mutations."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
import client_dns
import env_loader


class ResolverRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'client-dns.json'
        self.state = {'machine': 'this-mac', 'service': 'Wi-Fi', 'servers': [], 'raw': 'automatic'}
        self.path.write_text(json.dumps(self.state))
        self.env = env_loader.load_env(ROOT / 'network.env.example')
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(client_dns, 'STATE', self.path))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def test_healthy_resolver_never_changes_ipv6(self):
        with patch.object(client_dns, 'wait_for_resolver', return_value=True), patch.object(client_dns, 'set_ipv6') as change:
            client_dns.verify_active_dns(self.state, self.env)
        change.assert_not_called()
        self.assertNotIn('ipv6_restore', json.loads(self.path.read_text()))

    def test_unreachable_dns_never_changes_ipv6(self):
        with patch.object(client_dns, 'wait_for_resolver', return_value=False), patch.object(client_dns, 'lookup_ok', return_value=False), patch.object(client_dns, 'set_ipv6') as change:
            with self.assertRaisesRegex(ValueError, 'not answering'):
                client_dns.verify_active_dns(self.state, self.env)
        change.assert_not_called()

    def test_unrelated_resolver_and_manual_ipv6_are_not_modified(self):
        for override, mode in ((False, 'Automatic'), (True, 'Manual'), (True, 'Link-local only')):
            with self.subTest(override=override, mode=mode), patch.object(client_dns, 'wait_for_resolver', return_value=False), patch.object(client_dns, 'lookup_ok', return_value=True), patch.object(client_dns, 'ipv6_override_on_service', return_value=override), patch.object(client_dns, 'ipv6_mode', return_value=mode), patch.object(client_dns, 'set_ipv6') as change:
                with self.assertRaisesRegex(ValueError, 'No automatic IPv6'):
                    client_dns.verify_active_dns(self.state, self.env)
                change.assert_not_called()

    def repair_context(self, succeeds):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(client_dns, 'wait_for_resolver', side_effect=[False, succeeds]))
        stack.enter_context(patch.object(client_dns, 'lookup_ok', return_value=True))
        stack.enter_context(patch.object(client_dns, 'ipv6_override_on_service', return_value=True))
        stack.enter_context(patch.object(client_dns, 'ipv6_mode', return_value='Automatic'))
        stack.enter_context(patch.object(client_dns, 'change'))
        stack.enter_context(patch.object(client_dns, 'flush'))
        return stack

    def test_successful_repair_records_rollback_before_change_and_restores(self):
        def assert_saved(*args):
            self.assertEqual(json.loads(self.path.read_text())['ipv6_restore'], 'Automatic')
        with self.repair_context(True), patch.object(client_dns, 'set_ipv6', side_effect=assert_saved) as change:
            client_dns.verify_active_dns(self.state, self.env)
        change.assert_called_once_with('Wi-Fi', '-setv6LinkLocal', 'Link-local only')
        self.assertEqual(json.loads(self.path.read_text())['servers'], [])
        with patch.object(client_dns.platform, 'system', return_value='Darwin'), patch.object(client_dns.os, 'geteuid', return_value=501), patch.object(client_dns, 'machine_id', return_value='this-mac'), patch.object(client_dns, 'read_dns', return_value=([self.env['DNS_IP']], 'project')), patch.object(client_dns, 'change') as dns, patch.object(client_dns, 'set_ipv6') as ipv6, patch.object(client_dns, 'flush'), patch.object(sys, 'argv', ['client_dns.py', 'restore']):
            client_dns.main()
        dns.assert_called_once_with('Wi-Fi', [])
        ipv6.assert_called_once_with('Wi-Fi', '-setv6automatic', 'Automatic')
        self.assertFalse(self.path.exists())

    def test_unsuccessful_repair_rolls_back_ipv6(self):
        with self.repair_context(False), patch.object(client_dns, 'set_ipv6') as change:
            with self.assertRaisesRegex(ValueError, 'still differs'):
                client_dns.verify_active_dns(self.state, self.env)
        self.assertEqual(change.call_args_list[-1].args, ('Wi-Fi', '-setv6automatic', 'Automatic'))
        self.assertNotIn('ipv6_restore', json.loads(self.path.read_text()))
        self.assertEqual(json.loads(self.path.read_text())['servers'], [])

    def test_failed_rollback_retains_recovery_metadata(self):
        failure = subprocess.CalledProcessError(1, 'networksetup')
        with self.repair_context(False), patch.object(client_dns, 'set_ipv6', side_effect=[None, failure]):
            with self.assertRaises(subprocess.CalledProcessError):
                client_dns.verify_active_dns(self.state, self.env)
        self.assertEqual(json.loads(self.path.read_text())['ipv6_restore'], 'Automatic')

    def test_ipv6_override_must_belong_to_selected_interface(self):
        records = [{'name': 'Wi-Fi', 'device': 'en0'}]
        for interface, server, expected in [('en0', 'fe80::1%en0', True), ('en6', 'fe80::1%en6', False), ('en0', self.env['DNS_IP'], False)]:
            with self.subTest(interface=interface, server=server), patch.object(client_dns, 'services', return_value=records), patch.object(client_dns, 'run', return_value=f'DNS configuration\n\nresolver #1\n  nameserver[0] : {server}\n  if_index : 11 ({interface})\n\nresolver #2\n  domain : local\n'):
                self.assertEqual(client_dns.ipv6_override_on_service('Wi-Fi'), expected)

    def test_lookup_requires_correct_record_and_actual_server(self):
        def response(command, **kwargs):
            name = command[-2]
            return subprocess.CompletedProcess(command, 0, f";; status: NOERROR\n{name}. 0 IN A {self.env['EDGE_IP']}\n;; SERVER: {self.env['DNS_IP']}#53\n", '')
        with patch.object(client_dns.subprocess, 'run', side_effect=response) as run:
            self.assertTrue(client_dns.lookup_ok(self.env, direct=True))
            self.assertIn('@' + self.env['DNS_IP'], run.call_args.args[0])
        bad = subprocess.CompletedProcess([], 0, ';; status: NXDOMAIN\n;; SERVER: fe80::1#53\n', '')
        with patch.object(client_dns.subprocess, 'run', return_value=bad):
            self.assertFalse(client_dns.lookup_ok(self.env))


if __name__ == '__main__':
    unittest.main()
