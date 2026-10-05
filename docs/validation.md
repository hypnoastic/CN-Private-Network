# Validation and Phase 1 requirement audit

All 12 assignment pages were read, including the boundary between the two phases. The build is limited to §6 and Phase 1 deliverables. The five failure demonstrations follow §6.3. The additional Mac 2 DNS-client setting satisfies Task B's explicit “two other Macs” wording while preserving all four requested service roles.

## Checks completed locally

Final results: **37 regression tests passed**, syntax checks passed for **19 Python files and 32 shell files**, and the full real-service integration run passed, including restoration of stopped backends. The repository audit also validated documentation commands, file links, configuration isolation, and the 25-step README.

- Python syntax and shell syntax, including Bash/zsh syntax of all documentation command blocks.
- All README script targets and local Markdown links; Steps 1–25 in the requested order.
- Example LAN IPs occur only in `network.env.example`; aliases and domain names are derived and validated.
- Configuration errors: missing file/settings, invalid IPv4/port, mismatched machine roles, duplicate keys/addresses, unsafe values, unknown/circular references, and wrong domain namespace.
- Both backends: `/`, `/api/status`, correct JSON/X-Backend/Content-Type/Content-Length, HEAD, 404, shared cache representation, weak/list/star validators, and bodyless 304.
- Active-DNS repair with simulated OS commands: successful repair saves IPv6 rollback before mutation; healthy resolvers, unreachable DNS, different interfaces, and custom IPv6 modes are preserved; failed repair rolls back; failed rollback retains recovery metadata; stop restores DNS and IPv6. Physical macOS resolver behavior still requires the connected laptops.
- Client DNS logic with simulated macOS commands: original automatic and explicit DNS, repeated setup, wrong-server/repair, failure preservation, foreign-Mac backup rejection, and restore using the macOS `Empty` keyword.
- Safe process checks reject unrelated PIDs; exited children are recognized as stopped. A failed native nginx test prevents startup.
- Official load-balancing logic passes with A and B and rejects an always-A result; cache checks reject a 304 body. The curl wrapper accepts an absent output file for 304 while still rejecting missing output for a normal 200 response.
- Guided launcher: configuration wizard preserves valid files on invalid input, reuses existing settings and custom backend ports, rejects the wrong physical role, starts Mac 4's backend before waiting on client dependencies, rejects mismatched certificate fingerprints without importing trust, verifies trust after a matched import, and preserves DNS service if restoration fails.
- Real detached backend startup, response, restart, and shutdown; native background nginx/dnsmasq startup and stop; persistent DNS log output; real automatic public-certificate retrieval and its SHA-256 fingerprint match. System-trust installation in the launcher is simulated in tests, not applied to the development machine.

**Real integration test:** actual Homebrew nginx, dnsmasq, OpenSSL, both Python entry points, and Apple's curl were run in a disposable repository copy on this Mac. The copy used loopback and temporary high ports, retaining the production architecture mappings in separate rendering checks. No user DNS settings or system certificate trust were changed.

The integration test verified native DNS syntax, UDP and TCP DNS answers for both names, correct upstream rendering, wildcard backend listening, certificate SANs and key permissions, certificate reuse, trusted-file TLS verification, rejection of untrusted and wrong-name certificates, HTTP/1.1, HTTP/2, a validated TLS 1.2 connection, round robin, cache metadata/304, nginx start/reload/stop, both backend stop scripts, one-backend default retry, both-backend 502, DNS stop, and wrong-record injection/restoration. Paths containing spaces and loading `network.env` from a different working directory were tested in Bash and zsh.

The test's explicit certificate trust file and loopback destination override are confined to the developer harness. Official `shared/test_https.sh` resolves the real domain and uses the macOS system trust store without a verification bypass. The launcher's first-contact TLS connection retrieves only the public certificate; its fingerprint must match the value displayed on Mac 2 before installation. All application checks still use system certificate verification.

Reproduce on a development Mac with Python 3, Homebrew nginx/dnsmasq/openssl@3 installed:

```bash
python3 tests/audit_repository.py
python3 -m unittest discover -s tests -v
python3 tests/integration.py
```

## Requires the four connected physical Macs

Real DHCP/private addresses and inventory; all-pairs ping; LAN reachability of ports 53, HTTPS_PORT, 3001, and 3002; privileged port-53 startup/restart; the actual macOS DNS change/restore on each chosen network service; certificate installation and browser/system-keychain trust; normal domain-based HTTPS from both primary clients; live balancing across separate machines; live failure demonstrations and all Wireshark screenshots/captures. Port 443's privileged startup also needs a real machine if you choose it instead of 8443. Intel Homebrew paths are discovered automatically, but physical Intel hardware was not available for this validation.

Do not present the loopback integration run as four-machine evaluation evidence. Collect the genuine LAN evidence using `evidence/README.md`.

## PDF coverage

| PDF requirement | Implementation / review material |
|---|---|
| §6.2 A: LAN, inventory, ping, topology | README 1–7; record_inventory.sh; ping_all.sh; architecture and inventory docs |
| §6.2 B: two `.test` records and client resolvers | dnsmasq template/configure; client DNS backup/set/restore; test_dns.sh; README 15–17 |
| §6.2 C: two simple LAN REST backends | backend_a.py; backend_b.py; shared/backend_server.py; test_backends.sh |
| §6.2 D: reverse proxy and round robin | nginx template; generated upstream; test_load_balancing.sh |
| §6.2 E: TLS termination and trusted certificate | certificate.py; generate_certificate.sh; trust_certificate.sh; test_https.sh |
| §6.2 F: HTTP cache headers and validation | `/cache-demo`; test_caching.sh; evidence guide |
| §6.2 G: DNS/TCP/TLS/headers/ports evidence | evidence guide; tcpdump/Wireshark instructions; TLS 1.2 capture command |
| §6.1: layers, TCP reliability, HTTP versions, email/CDN/cloud explanation | protocol_layers.md; request_flow.md; viva_notes.md |
| §6.3: five required failures | failure_demo.md; reversible DNS injection helper; ordinary nginx failure behavior |
| §9: Phase 1 source/config/evidence/checkpoint bundle | entire repository; generated config exports; evidence folder; phase1_demo_checklist.md |

No later-phase infrastructure is included.
