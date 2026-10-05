# Restart the four-person Phase 1 lab

Use the updated team ZIP on all four laptops. It contains the current shared `network.env`. Keep your existing project folder: it contains that laptop's original DNS backup and, on Ritesh's laptop, the private certificate key. Do not copy runtime folders, trusted folders, or private keys between laptops.

## 1. Update each existing copy

Save the latest `CN-Private-Network.zip` in Downloads. For copies already in Downloads:

```bash
cd "$HOME/Downloads"
unzip -o CN-Private-Network.zip
cd CN-Private-Network
```

This replaces source files and the supplied team configuration. The ZIP excludes runtime backups, certificates, private keys, and collected evidence, so those existing files remain. Yash's maintained working copy is `/Users/yashkumar/CN/CN-Private-Network` and is already updated:

```bash
cd /Users/yashkumar/CN/CN-Private-Network
```

## 2. Cleanly finish the previous session

Run the menu in each person's existing project folder:

```bash
bash setup.sh
```

Choose your name, then **4**. Do this on Ritesh and Dhruv before Yash; stop Parul as well. The stop action works even when `network.env` has changed, because it identifies the existing project process and uses the original machine-bound DNS backup. If restore reports an error, preserve the backup and resolve the error before starting a new session.

The new code restores IPv6 when its own automatic DNS repair changed it. Last session's manually applied IPv6 workaround was not recorded by that old code. On any laptop where you applied it, inspect the saved snapshot:

```bash
cat shared/runtime/ipv6-before.txt
networksetup -getinfo "Wi-Fi"
```

Only if that snapshot says **IPv6: Automatic** and you applied the earlier manual Link-local workaround, return it to its original setting:

```bash
sudo networksetup -setv6automatic "Wi-Fi"
```

If the snapshot does not exist, do not guess a previous custom setting. The new launcher preserves pre-existing manual, off, and link-local modes.

## 3. Confirm the new network

Everyone connects to the same LAN and checks their actual IPv4:

```bash
ipconfig getifaddr en0
cat network.env
```

If Wi-Fi is on a different device, find it with `networksetup -listallhardwareports`. Yash is `MAC1_IP`, Ritesh is `MAC2_IP`, Parul is `MAC3_IP`, and Dhruv is `MAC4_IP`. All four copies must contain the same real addresses. Use menu **5** after stopping services to edit the configuration, or edit the single `network.env` file. Setup rejects a role whose address does not belong to the current laptop and prints a configuration ID that must match on every laptop.

Check peer connectivity on each laptop:

```bash
bash shared/ping_all.sh
```

Missing ping replies need investigation, but do not alone prove TCP services are unreachable. The launcher also tests the actual DNS and backend service connections. Complete any Wi-Fi sign-in before setup; dependency installation needs working internet access. The shared `UPSTREAM_DNS` value must be a reachable existing resolver so normal websites continue resolving during the lab.

## 4. Start all four laptops

```bash
bash setup.sh
```

Choose your own name, then **1**. Start **Parul, Dhruv, Yash, then Ritesh**. Move to the next laptop while an earlier one waits for dependencies. Parul starts Backend A, Dhruv starts Backend B, Yash starts DNS, and Ritesh starts nginx once both backends answer.

If a wait expires, local services remain running. Choose **2** after the other laptops are ready. The menu now defaults to **2** when the local service is running; explicit **1** still performs a full restart. If nginx has not yet started on Ritesh, choose **1** there.

Ritesh displays the certificate SHA-256 fingerprint. It is also available through menu **3**. Paste that full value into the prompts on Yash and Dhruv. Existing valid certificates and trust are reused.

## 5. Automatic DNS repair and verification

Setup verifies real default DNS queries for both project names after saving the service setting. If direct queries to Yash succeed but the default resolver belongs to an IPv6 server on the selected interface, and that service uses Automatic IPv6, setup tries **Link-local only**. This limits IPv6 to local traffic ([Apple TCP/IP settings](https://support.apple.com/en-gb/guide/mac-help/mh14129/mac)) and may affect IPv6 internet access for the session.

The previous IPv6 mode is saved before the change, alongside the original DNS backup. A failed repair rolls IPv6 back immediately; a successful repair is reversed by menu **4** or `shared/restore_client_dns.sh`. If the OS refuses restoration, the backup remains for retry. Healthy DNS, unreachable project DNS, unrelated interfaces, and custom IPv6 settings do not trigger this repair. Setup reports remaining failures rather than claiming success.

Run on Yash and Dhruv after setup:

```bash
bash shared/verify_phase1.sh
```

Expected: DNS, trusted HTTPS, both A/B responses, Cache-Control, ETag, and bodyless **304 Not Modified** pass. The curl wrapper now supports curl versions that do not create an output file for 304. No server or certificate restart is needed for that fix.

After these checks, collect [packet evidence](../evidence/README.md) and perform the five [Phase 1 failure demonstrations](../shared/failure_demo.md). Finish with menu **4** on Ritesh/Dhruv, then Yash, and stop Parul. Everything remains Phase 1 only.

## Internet access during the lab

The updated DNS configuration forwards ordinary website lookups to `UPSTREAM_DNS` in `network.env`, while `.test` names stay local. Use the same configuration on all four laptops. On Yash, after changing that value:

```bash
bash mac1_dns_client/restart_dns.sh --background
source <(python3 shared/env_loader.py --shell)
dig @"$DNS_IP" example.com
dig example.com
/usr/bin/curl --connect-timeout 5 --max-time 15 -I https://example.com
```

Expected: public DNS answers and a validated HTTPS response. If the direct public lookup fails, check that the configured upstream is reachable on this network. When finishing, restore client DNS before stopping Yash. To restore internet DNS immediately on any affected client:

```bash
bash shared/restore_client_dns.sh
```

This restores the saved original DNS and any IPv6 setting changed by setup; project names then require starting setup again.
