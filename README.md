# CN Private Network — Phase 1: Build & Observe

Four physical Macs, one private LAN, one DNS server, one HTTPS nginx edge, and two small Python backends. The source of truth is `CN_Project_Doc.pdf`, read in full, especially §§6.1–6.3 and the Phase 1 deliverables in §9. This repository implements Phase 1 only.

## Quick start

Clone the full repository on all four Macs, connect to the same private LAN, and run the guided setup:

```bash
cd "$HOME/Downloads"
git clone https://github.com/hypnoastic/CN-Private-Network.git
cd CN-Private-Network
bash setup.sh
```

For an existing checkout, follow the [restart guide](docs/restart.md).

Select your name (Yash, Ritesh, Parul, or Dhruv), then **1 — Full setup / start**. The launcher prompts for missing network settings, installs missing dependencies, starts this Mac's services in the background, generates/fetches the certificate, saves and sets DNS, installs trust, and runs the checks. Run it on all four Macs while they wait for each other. Mac 2 displays a certificate fingerprint to paste on Mac 1 and Mac 4; manual certificate-file transfer is unnecessary. Use option **2** to retry client setup once the other Macs are ready, **3** for status/logs, and **4** to stop and restore DNS. See [guided setup](docs/launcher.md).

### Your team assignment

| Select | Person | Runs | Original folder/role |
|---|---|---|---|
| 1 | Yash | DNS + main client | Mac 1 / `mac1_dns_client/` |
| 2 | Ritesh | nginx + HTTPS + load balancer | Mac 2 / `mac2_edge/` |
| 3 | Parul | Backend A, port 3001 | Mac 3 / `mac3_backend_a/` |
| 4 | Dhruv | Backend B, port 3002 + client | Mac 4 / `mac4_backend_b_client/` |

The menu accepts names or numbers. On a fresh clone, the launcher helps create `network.env`; use the same real network settings on all four Macs. This file stays excluded from Git. All services read their addresses exclusively from it.

Start Parul first, then Dhruv, Yash, and Ritesh. While a launcher waits, start the next laptop. Ritesh displays the certificate fingerprint for Yash and Dhruv to paste. Use option 2 on any waiting clients once all services are running. Wi-Fi addresses can change; use option 5 to update `network.env` consistently on all four laptops if needed.

## Repository layout

```text
CN-Private-Network/
├── README.md                   # Setup, verification, and safe shutdown
├── network.env.example         # Copy to network.env; enter actual LAN values
├── setup.sh                    # Interactive per-Mac launcher
├── mac1_dns_client/            # Yash: dnsmasq and client DNS
├── mac2_edge/                  # Ritesh: nginx, TLS, and round robin
├── mac3_backend_a/             # Parul: Python backend on port 3001
├── mac4_backend_b_client/      # Dhruv: backend on port 3002 and client DNS
├── shared/                     # Configuration, tests, restore, failure demos, viva
├── docs/                       # Architecture, request flow, and evaluation guides
├── evidence/                   # Selected screenshots, test output, packet capture
└── tests/                      # Repository audit, regressions, local integration
```

Generated configurations and process logs stay in each role's `runtime/` directory. Mac 2 creates certificates in `mac2_edge/certs/`. Private keys, runtime state, and the local `network.env` are excluded from Git.

## Phase 1 deliverables

| Assignment deliverable | Where to find it |
|---|---|
| Architecture and machine roles | [Topology](docs/architecture.md), [IP/service inventory](docs/ip_service_inventory.md) |
| Request flow and protocol layers | [Request flow](docs/request_flow.md), [protocol guide](docs/protocol_layers.md) |
| DNS and nginx configuration | `mac1_dns_client/dnsmasq.conf.template`, `mac2_edge/nginx.conf.template`; render using each role's `configure.py` |
| TLS setup and backend launch | Steps 8–18 below; [guided setup](docs/launcher.md) |
| Backend source | `mac3_backend_a/backend_a.py`, `mac4_backend_b_client/backend_b.py`, `shared/backend_server.py` |
| Recorded evidence | [Evidence index](evidence/README.md), [capture instructions](docs/full_evidence_guide.md) |
| Required failure demonstrations | [Five reversible Phase 1 scenarios](shared/failure_demo.md) |
| Checkpoint and viva | [Review checklist](docs/phase1_demo_checklist.md), [viva notes](shared/viva_notes.md) |
| Validation | [Checks and limitations](docs/validation.md) |

The evidence index distinguishes collected results from records still needed for evaluation. The numbered steps below are the manual setup and evaluation guide.

Read the steps in order. Commands run in Terminal. A server command stays running: keep its Terminal window open and use a **new Terminal tab** for later commands on that Mac. In each new tab, run `cd "$HOME/Downloads/CN-Private-Network"` after placing the repository there in Step 5. Scripts themselves also work when invoked by absolute path from another directory.

Only edit **network.env** for normal setup. Four IP addresses are entered once; role aliases and domain names are derived automatically. Do not manually edit generated configurations.

## STEP 1 — RUN ON ALL FOUR MACS: connect to the same LAN

Use the Wi-Fi menu to join the same private Wi-Fi/hotspot, or connect all Macs to the same wired LAN. Keep the laptops awake and plugged in throughout the demonstration.

```bash
networksetup -listallhardwareports
scutil --nwi
```

Expected: an active network interface on each Mac. Some guest Wi-Fi/hotspots prevent devices from contacting each other; use a LAN that permits peer connections if Step 4 fails.

## STEP 2 — RUN ON ALL FOUR MACS: find the real private IP

```bash
ipconfig getifaddr en0
networksetup -listallhardwareports
route -n get default
```

Expected: a private IPv4 address from the first command. If the Wi-Fi hardware entry says a device other than `en0`, this command detects it automatically:

```bash
LAN_IFACE="$(networksetup -listallhardwareports | awk '/Hardware Port: (Wi-Fi|AirPort)/ {getline; print $2; exit}')"
ipconfig getifaddr "$LAN_IFACE"
ifconfig "$LAN_IFACE"
```

For Ethernet, use the `interface:` value printed by `route -n get default` with `ipconfig getifaddr` and `ifconfig`. Record IPv4, netmask, default gateway, interface name, and the `ether` MAC address. The inventory script in Step 7 saves all five.

## STEP 3 — RUN ON ALL FOUR MACS: write down the four IPs

Have the four students share the addresses shown in Step 2. Run this in each Mac's Terminal and type the real IP when prompted:

```bash
printf 'MAC 1 IP: '; read MAC1_IP
printf 'MAC 2 IP: '; read MAC2_IP
printf 'MAC 3 IP: '; read MAC3_IP
printf 'MAC 4 IP: '; read MAC4_IP
printf 'MAC 1=%s\nMAC 2=%s\nMAC 3=%s\nMAC 4=%s\n' "$MAC1_IP" "$MAC2_IP" "$MAC3_IP" "$MAC4_IP"
```

Keep this output or take a screenshot. These variables last for this Terminal tab.

## STEP 4 — RUN ON ALL FOUR MACS: verify every pair with ping

In the same Terminal tab as Step 3:

```bash
ping -c 3 "$MAC1_IP"
ping -c 3 "$MAC2_IP"
ping -c 3 "$MAC3_IP"
ping -c 3 "$MAC4_IP"
```

Expected: replies and 0% packet loss. Running this on all four Macs checks every direction between each pair (and each Mac's own address). Save screenshots. Resolve LAN connectivity before continuing.

## STEP 5 — RUN ON ALL FOUR MACS: copy the FULL repository

Copy the entire `CN-Private-Network` folder into each Mac's Downloads folder using AirDrop or a USB drive. If using the supplied zip, save it in Downloads and extract it:

```bash
cd "$HOME/Downloads"
unzip -n CN-Private-Network.zip
cd CN-Private-Network
ls README.md network.env.example shared/env_loader.py
```

If you copied the folder directly, use:

```bash
cd "$HOME/Downloads/CN-Private-Network"
ls README.md network.env.example shared/env_loader.py
```

Expected: all three filenames exist. Copy before starting services so no machine-specific runtime or DNS backup is transferred. If you later use Git, clone the entire repository on each Mac. `network.env`, private keys, and runtime state are deliberately ignored by Git.

## STEP 6 — RUN ON ALL FOUR MACS: create identical network.env files

```bash
[ -f network.env ] || cp network.env.example network.env
nano network.env
```

Change `TEAM_NAME` and the **four `MAC1_IP`–`MAC4_IP` values** to your real values. Keep `DNS_IP=${MAC1_IP}`, `EDGE_IP=${MAC2_IP}`, and the backend aliases as written. Domains derive from `TEAM_NAME`. Keep ports 3001/3002 for the assignment; `HTTPS_PORT` defaults to 8443 and can be changed to 443 if desired. Backend port changes require faculty agreement. `UPSTREAM_DNS` forwards ordinary website lookups through an existing reachable IPv4 DNS resolver; the example uses Google DNS. On a restricted LAN, use its supplied resolver instead. Leaving this value empty makes DNS lab-only. Save in nano with Ctrl+O, Enter, Ctrl+X. Use the same file contents on all Macs. Do not run the copy command again after editing.

## STEP 7 — RUN ON ALL FOUR MACS: install dependencies

Check Python 3 (version 3.9 or newer):

```bash
python3 --version
```

If missing, install Python from [python.org](https://www.python.org/downloads/macos/) or run `brew install python` after installing Homebrew. There are no pip dependencies.

On Macs 1 and 2, check Homebrew:

```bash
brew --version
```

If missing, install from the [official Homebrew instructions](https://brew.sh/):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Run the installer's printed “Next steps” to add Homebrew to PATH, then reopen Terminal. All project scripts use `brew --prefix`, supporting Intel and Apple Silicon.

**RUN ON MAC 1:**

```bash
brew install dnsmasq
```

**RUN ON MAC 2:**

```bash
brew install nginx openssl@3
"$(brew --prefix openssl@3)/bin/openssl" version
```

**RUN ON MAC 3 AND MAC 4:** Python 3 is sufficient for the backends. Built-in `/usr/bin/curl`, `dig`, `networksetup`, and `security` supply the client tools.

**RUN ON MAC 4** (recommended capture client), optionally also Mac 1:

```bash
brew install --cask wireshark
```

Wireshark is also available from [wireshark.org](https://www.wireshark.org/download.html). Install its capture permissions helper if prompted, or use the sudo tcpdump command in the evidence guide. Project `.test` names stay local. Ordinary website lookups are forwarded to `UPSTREAM_DNS` while the project DNS server runs. Restore client DNS before stopping Mac 1 so clients retain internet name resolution.

Now validate the shared configuration and save the LAN inventory:

```bash
python3 shared/env_loader.py
bash shared/ping_all.sh
```

Run the appropriate inventory command on each Mac:

```bash
# MAC 1
bash shared/record_inventory.sh 1
# MAC 2
bash shared/record_inventory.sh 2
# MAC 3
bash shared/record_inventory.sh 3
# MAC 4
bash shared/record_inventory.sh 4
```

Run only your Mac's line. If automatic interface selection does not match your LAN, pass the interface from Step 2 as the second argument, for example `bash shared/record_inventory.sh 1 en0`. Output goes to `evidence/collected/`. Address changes after reconnecting require updating the same `network.env` on all Macs and restarting the role services.

## STEP 8 — RUN ON MAC 1: generate DNS configuration

```bash
python3 mac1_dns_client/configure.py
cat mac1_dns_client/runtime/dnsmasq.conf
```

Expected: both `host-record` entries point to Mac 2. The file is project-local; Homebrew's normal dnsmasq configuration is not overwritten.

## STEP 9 — RUN ON MAC 2: generate nginx configuration

```bash
python3 mac2_edge/configure.py
cat mac2_edge/runtime/nginx.conf
```

Expected: upstream servers are Mac 3 on 3001 and Mac 4 on 3002; TLS listens on `HTTPS_PORT`. HTTP/2 is automatically enabled when supported by the installed nginx. Certificate paths are generated now; native nginx validation happens after the certificate exists.

## STEP 10 — RUN ON MAC 3: start Backend A

```bash
python3 mac3_backend_a/backend_a.py
```

Expected: `Backend A listening on 0.0.0.0:3001`. Keep this Terminal open. Ctrl+C stops the backend cleanly.

## STEP 11 — RUN ON MAC 4: start Backend B

```bash
python3 mac4_backend_b_client/backend_b.py
```

Expected: `Backend B listening on 0.0.0.0:3002`. Keep this Terminal open; use a second tab for Mac 4's client commands.

## STEP 12 — RUN ON MAC 2: test both backends directly

```bash
bash shared/test_backends.sh
```

Expected: valid status JSON, `X-Backend: A`, `X-Backend: B`, and two PASS messages. Direct-IP requests are for this backend diagnostic; the final application demonstration uses domain names.

## STEP 13 — RUN ON MAC 2: generate the TLS certificate

```bash
bash mac2_edge/generate_certificate.sh
"$(brew --prefix openssl@3)/bin/openssl" x509 -in mac2_edge/certs/server.crt -noout -ext subjectAltName -fingerprint -sha256
```

Expected: both configured domain names appear as DNS SANs. This uses the PDF's self-signed certificate option, valid for 365 days, explicitly trusted by each client. Keep `server.key` only on Mac 2. Re-running preserves an existing valid matching key/certificate. To replace an expired or renamed certificate, use `bash mac2_edge/generate_certificate.sh --renew`, then repeat Step 14 and reload nginx.

## STEP 14 — RUN ON MAC 1 AND MAC 4: copy and trust the certificate

On **Mac 2**, open the directory:

```bash
open mac2_edge/certs
```

Use Finder/AirDrop to send **only `server.crt`** to Mac 1 and Mac 4; save it in Downloads. On **Mac 1 and Mac 4**:

```bash
cp "$HOME/Downloads/server.crt" shared/trusted/server.crt
openssl x509 -in shared/trusted/server.crt -noout -fingerprint -sha256
bash shared/trust_certificate.sh
```

Compare the SHA-256 fingerprint with Mac 2 before trusting. The script states the change and uses sudo to add this certificate as a trusted SSL certificate in the macOS System keychain. This is an explicit system trust change.

**On Mac 2**, also trust it for the additional client verification required below:

```bash
cp mac2_edge/certs/server.crt shared/trusted/server.crt
bash shared/trust_certificate.sh
```

Use `/usr/bin/curl` (Apple's curl) for the demo so verification uses the macOS trust store. A Homebrew curl may use a different CA store. Do not bypass verification. Safari uses system trust; configure a browser to use the operating system resolver rather than a custom secure DNS resolver.

## STEP 15 — RUN ON MAC 1: start private DNS

```bash
bash mac1_dns_client/start_dns.sh
```

Expected: dnsmasq configuration syntax OK, followed by foreground DNS logs. sudo is required for port 53. Keep this window open. Do not start a second Homebrew dnsmasq service. If port 53 is occupied, identify the existing service with `sudo lsof -nP -i :53` and stop your conflicting service intentionally before retrying.

## STEP 16 — RUN ON MAC 1 AND MAC 4: select Mac 1 as client DNS

**Mac 1, in a new tab:**

```bash
bash mac1_dns_client/set_client_dns.sh
```

**Mac 4, in a new tab:**

```bash
bash mac4_backend_b_client/set_client_dns.sh
```

**Also run on Mac 2:**

```bash
bash shared/set_client_dns.sh
```

The PDF's Task B says “at least two other Macs.” Mac 2 and Mac 4 satisfy that wording; Mac 1 remains the main test client, exactly as in the requested architecture. Mac 2 gains only client DNS settings.

Each script detects the active Wi-Fi service, prints the current settings, saves its original state in `shared/runtime/client-dns.json`, shows the new resolver, applies it with sudo, and verifies the change. It preserves the first backup on repeated runs. Automatic/DHCP DNS and explicit server lists are restored correctly. If selection is ambiguous, choose the service number or pass `--service 'Wi-Fi'` using your actual service name. Run these scripts as your normal user. Do not copy runtime directories between Macs or delete the DNS backup before restoring.

## STEP 17 — RUN ON MAC 1, MAC 4, AND MAC 2: verify DNS by name

```bash
source shared/common.sh
cn_load_env
dig @"$DNS_IP" "$APP_DOMAIN"
dig "$APP_DOMAIN"
nslookup "$API_DOMAIN" "$DNS_IP"
bash shared/test_dns.sh
```

Expected: the answer is `$EDGE_IP` (Mac 2), and the `SERVER` line identifies Mac 1 on port 53. The script verifies both names using direct queries and the normally configured resolver. `dig` and macOS application resolution use different resolver paths; the HTTPS check also tests application resolution.

## STEP 18 — RUN ON MAC 2: start nginx

```bash
bash mac2_edge/start_nginx.sh
```

Expected: nginx's `syntax is ok` and `test is successful` before the server starts. A failed test prevents startup. Keep this terminal open. Port 8443 runs without sudo; a configured port below 1024 uses sudo. nginx logs are in `mac2_edge/runtime/access.log` and `error.log`.

For a deliberate config change later, regenerate, validate, and reload with:

```bash
bash mac2_edge/reload_nginx.sh
```

## STEP 19 — RUN ON MAC 1 AND MAC 4: verify trusted HTTPS

```bash
bash shared/test_https.sh
source shared/common.sh
cn_load_env
/usr/bin/curl --disable --noproxy '*' --http1.1 -i "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
open "https://$APP_DOMAIN:$HTTPS_PORT/"
```

Expected: successful certificate validation, HTTP 200, backend JSON, and `X-Backend`. No certificate warning in the browser. The test checks both SAN names. For HTTP/2 when enabled by Step 9:

```bash
/usr/bin/curl --version
bash shared/test_https.sh --http2
```

Expected: HTTP/1.1 plus HTTP/2 PASS. If nginx was built without HTTP/2, record its `nginx -V` output and demonstrate HTTP/1.1 as required by §6.1. HTTP/3 is explanation-only.

## STEP 20 — RUN ON MAC 1 AND MAC 4: demonstrate round robin

```bash
bash shared/test_load_balancing.sh
```

Expected: ten lines showing `X-Backend: A` and `X-Backend: B`, followed by PASS. With idle healthy backends and sequential requests, they alternate. Other simultaneous requests can change the apparent sequence. Seeing only one backend fails the check.

## STEP 21 — RUN ON MAC 1 AND MAC 4: demonstrate caching

```bash
bash shared/test_caching.sh
source shared/common.sh
cn_load_env
/usr/bin/curl --disable --noproxy '*' --http1.1 -I "https://$APP_DOMAIN:$HTTPS_PORT/cache-demo"
/usr/bin/curl --disable --noproxy '*' --http1.1 -i -H 'If-None-Match: "cn-project-v1"' "https://$APP_DOMAIN:$HTTPS_PORT/cache-demo"
```

Expected: `Cache-Control: public, max-age=60`, `ETag: "cn-project-v1"`, and a bodyless `304 Not Modified` for the conditional request. Both backends serve identical cache-demo content, so the validator remains correct when the next request reaches the other backend. curl does not maintain a browser-style cache; this explicitly demonstrates validation.

The complete final functional check, on Mac 1 or Mac 4, is:

```bash
bash shared/verify_phase1.sh
```

## STEP 22 — RUN ON MAC 4: capture Phase 1 evidence

```bash
cat evidence/README.md
mkdir -p evidence/collected
bash shared/test_dns.sh | tee evidence/collected/dns.txt
bash shared/test_https.sh | tee evidence/collected/https.txt
bash shared/test_load_balancing.sh | tee evidence/collected/load-balancing.txt
bash shared/test_caching.sh | tee evidence/collected/caching.txt
```

Use the evidence guide's capture commands for DNS, TCP, TLS (including visible TLS 1.2 Certificate and ChangeCipherSpec packets), source/destination ports, sequence/acknowledgement numbers, and HTTP headers. Save screenshots and `.pcap`/`.pcapng` files. Also retain inventories, all-pairs ping, direct Backend A/B tests, and failure evidence. Mac 4 is preferred for DNS capture because its DNS query actually crosses the LAN to Mac 1.

## STEP 23 — RUN ON THE MACS NAMED IN THE GUIDE: five reversible failures

```bash
cat shared/failure_demo.md
```

Follow each numbered scenario, capture the observed result, and run its restore commands before starting the next one. These are exactly the five failures in PDF §6.3. The one-backend demonstration uses nginx's standard passive failure/retry behavior.

## STEP 24 — RUN ON MAC 1, MAC 4, AND MAC 2: restore original client DNS

**Mac 1:**

```bash
bash mac1_dns_client/restore_client_dns.sh
```

**Mac 4:**

```bash
bash mac4_backend_b_client/restore_client_dns.sh
```

**Mac 2:**

```bash
bash shared/restore_client_dns.sh
```

Expected: the original automatic/DHCP or explicit DNS settings are restored and verified. An audit copy remains as `client-dns.last-restored.json`. Restore before stopping DNS. To repeat the project later, run the set scripts again to create a new original-state backup.

## STEP 25 — STOP SERVICES ON THEIR RESPECTIVE MACS

**Mac 2, a second Terminal tab:**

```bash
bash mac2_edge/stop_nginx.sh
```

**Mac 1, a second Terminal tab:**

```bash
bash mac1_dns_client/stop_dns.sh
```

**Mac 3 and Mac 4:** press **Ctrl+C** in each backend's running Terminal. Alternatively, use the recorded project PID from a new tab:

```bash
# MAC 3 only
bash mac3_backend_a/stop_backend.sh
# MAC 4 only
bash mac4_backend_b_client/stop_backend.sh
```

The scripts check process identity before sending the interrupt. Check listeners after stopping:

```bash
# MAC 3
lsof -nP -iTCP:3001 -sTCP:LISTEN
# MAC 4
lsof -nP -iTCP:3002 -sTCP:LISTEN
```

No output means those ports have no listener. For faculty-agreed custom ports, load `network.env` with `source shared/common.sh; cn_load_env` and use `"$BACKEND_A_PORT"` / `"$BACKEND_B_PORT"`.

The trusted certificate can remain for future course sessions. To remove only this project's certificate after evaluation, **run on each Mac where it was trusted**:

```bash
CERT_SHA1="$(openssl x509 -in shared/trusted/server.crt -noout -fingerprint -sha1 | cut -d= -f2 | tr -d ':')"
sudo security remove-trusted-cert -d shared/trusted/server.crt
sudo security delete-certificate -Z "$CERT_SHA1" /Library/Keychains/System.keychain
```

## Exact per-Mac file responsibility

Clone/copy the **entire repository** on all four Macs; shared code is used by the role entry points.

| Mac | Main files | Main jobs / command |
|---|---|---|
| **MAC 1 — DNS + Client** | `network.env`, `mac1_dns_client/`, `shared/`, `evidence/`, `docs/` | Start DNS; configure client DNS; dig; curl; capture evidence. First role command: `python3 mac1_dns_client/configure.py`. |
| **MAC 2 — NGINX EDGE** | `network.env`, `mac2_edge/`, `shared/` | Generate config and certificate; run nginx; balance requests. First role command: `python3 mac2_edge/configure.py`. Also acts as the PDF's second external DNS client. |
| **MAC 3 — BACKEND A** | `network.env`, `mac3_backend_a/`, `shared/` | `python3 mac3_backend_a/backend_a.py` |
| **MAC 4 — BACKEND B + CLIENT** | `network.env`, `mac4_backend_b_client/`, `shared/` | `python3 mac4_backend_b_client/backend_b.py`; configure its DNS to Mac 1; run client/evidence checks. |

Architecture, inventory, request flow, layer mapping, and the checkpoint checklist are in [docs/](docs/). Study [viva notes](shared/viva_notes.md). See [validation](docs/validation.md) for what was checked locally and what still requires the physical LAN. Run development checks with `python3 -m unittest discover -s tests -v`.
