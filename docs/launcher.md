# Guided setup: one command on each Mac

Copy the full project to each Mac and connect all four to the same private LAN. In the project folder, run:

```bash
bash setup.sh
```

1. Select your name: **Yash (1), Ritesh (2), Parul (3), or Dhruv (4)**. Names and numbers both work.
2. Choose **1 — Full setup / start**.
3. The team ZIP already includes your prefilled `network.env`; setup reuses it. If `network.env` does not exist, enter the team name and four real private IP addresses. The wizard fills the role aliases, domains, and ports. Use identical settings on all Macs; you can copy the resulting `network.env` to the others before running their launcher.
4. Respond to any administrator-password or macOS developer-tools installation prompts.
5. Run the launcher on the other Macs while the first ones wait. Parul starts A; Dhruv starts B before waiting for client services; Yash starts DNS; Ritesh starts nginx after both backends are available. The launchers can run concurrently on the four physical machines.
6. Ritesh's laptop prints its certificate's **SHA-256 fingerprint**. Yash and Dhruv automatically fetch the public certificate over the edge's TLS connection. Paste the full fingerprint displayed on Ritesh into their prompt. The launcher requires a match before installing trust. No certificate files need to be copied manually.
7. Clients automatically save their old DNS settings, select Yash as DNS, and run DNS, trusted HTTPS, load-balancing, and caching checks. Parul verifies its backend directly.

Successful setup prints PASS. Keep the laptops awake. Services run in the background, so exiting the launcher menu or closing its Terminal is fine; they are not configured to restart automatically after a reboot.

## What the menu does

| Choice | Action |
|---|---|
| 1 | Install missing role dependencies, create/reuse configuration, start/restart this Mac's service, finish client setup, and verify |
| 2 | Finish client setup or retry checks after the other Macs become ready; preserves a running backend on Dhruv |
| 3 | Show service status, recent logs, and Ritesh's certificate fingerprint |
| 4 | Restore this Mac's original DNS settings, then stop its project service |
| 5 | Create/edit `network.env` through prompts; stop this Mac's service first |
| 0 | Leave the menu with services still running |

If a dependency is not ready within 90 seconds, the launcher explains what is missing and returns to the menu. Started local services stay running. Complete setup on the other Macs, then use **2**. If Ritesh was waiting for backends and nginx never started, use **1** on Ritesh.

Use **4** on Ritesh and Dhruv before stopping Yash's DNS. Stop Parul when done. Each Mac must restore its own settings; no remote control or passwords are exchanged between machines. Existing certificate trust remains available for the next course session; README Step 25 includes optional certificate removal.

## What is automated

- Python/Homebrew installation when needed; role software installation.
- Network configuration prompts and validation, including checking that the selected Mac's configured address belongs to this machine.
- Project-local DNS/nginx configuration generation and native validation.
- Backend, DNS, and edge service startup in the background, with project-local logs and existing safe stop scripts.
- SAN certificate creation on Ritesh; automatic public-certificate retrieval and verified fingerprint comparison on the other clients.
- macOS certificate trust installation and safe client DNS backup/set/restore.
- LAN inventory collection and the existing functional verification scripts.

Connecting Wi-Fi, copying the repository, entering real IP addresses, entering administrator passwords, and comparing the certificate fingerprint still require you. Wireshark captures and the five deliberate failure demonstrations remain explicit evaluation steps in the README. Setup does not deliberately break a working network.

The bootstrap connection only reads an untrusted certificate so its fingerprint can be compared with Ritesh; it makes no HTTP application request. All application checks use normal certificate validation and the macOS trust store.

## Optional direct commands

After configuration, run these from the repository folder on the named Mac:

```bash
bash setup.sh --role 1 --action setup
```

Choose `--role 2`, `--role 3`, or `--role 4` on the other Macs. These options skip the menu, but configuration/password/fingerprint prompts still appear when necessary. Setup exits nonzero if dependencies or verification fail.

```bash
bash setup.sh --role 4 --action verify
bash setup.sh --role 4 --action status
bash setup.sh --role 4 --action stop
```

Change the role number for the Mac you are using. `--wait-seconds 180` increases the wait for each remote dependency. Network values continue to come only from `network.env`.

The original per-Mac scripts and 25-step README remain usable. To start DNS/nginx directly in the background, the start scripts now accept `--background`; their default behavior still runs in the foreground.
