# Phase 1 evidence: start here

Study these **six screenshots, one packet capture and one combined test log**. The five-slide presentation and timed speaker script are in [presentation/](../presentation/).

| Folder | Open first | What it proves |
|---|---|---|
| [Yash](collected/01_Yash/) | `dns-and-https.png`, `balancing-and-caching.png` | Project DNS, trusted HTTPS, both backends, Cache-Control, ETag and 304 |
| [Ritesh](collected/02_Ritesh/) | `direct-backends-and-pings.png` | nginx host reaches both backend services over the LAN |
| [Parul](collected/03_Parul/) | `backend-a-and-pings.png` | Parul's local Backend A responds with HTTP 200 and X-Backend A |
| [Dhruv](collected/04_Dhruv/) | `https-balancing-caching.jpeg` | Successful second-client HTTPS, A/B requests and 304 |
| [Packets](collected/05_Packets/) | `wireshark-dns-tcp.png`, `phase1.pcapng` | Real DNS/TCP/TLS traffic captured on Yash |

## Screenshot attribution

Yash: original screenshots at 4:47:58 PM and 4:48:03 PM. The latter visibly identifies Yash's Terminal, and the outputs form one run. Wireshark at 4:21:13 PM matches his saved capture.

Ritesh: original `Screenshot 2026-10-05 at 16.45.31.png` exactly matches the Ritesh output supplied in the conversation. No username appears inside this screenshot.

Parul: original `Screenshot 2026-10-05 at 16.49.47.png` visibly ends with `parul@Paruls-MacBook-Pro`.

Dhruv: original `WhatsApp Image 2026-10-05 at 16.57.42.jpeg` follows his certificate-trust fix in the conversation. Assigned from that context; the image itself does not display a username. Confirm with Dhruv before labeling it in a formal submission.

## Read the results accurately

The Ritesh and Parul screenshots include a failed ping to Ritesh, while backend HTTP tests succeeded. Do not claim all-pairs ping passed. The originals are unmodified. Slide excerpts focus on the named HTTP results and do not serve as ping-success evidence.

`01_Yash/verified-results.txt` combines the original successful DNS, HTTPS, balancing, caching, HTTP/2 and TLS 1.2 logs. The packet capture contains 532 real packets. No certificate bypass was used in the application checks.

## Wireshark: only three views needed

Open `collected/05_Packets/phase1.pcapng` and use:

- `dns`: frames 2–3 show app.team1.test query/answer with Ritesh's IP.
- `tcp.stream == 2`: frames 34, 40 and 41 show SYN, SYN-ACK and ACK to port 8443.
- `tcp.stream == 20`: frames 513/516 show ClientHello and ServerHello/Certificate. Frames 520/522 show encrypted handshake completion and 524/526 carry encrypted request/response data.

Yash's DNS self-queries appear on loopback. His connections to the other laptops appear on Wi-Fi. The visible screenshot includes direct backend traffic; it does not show nginx's own upstream TCP connections. The capture contains TLS evidence beyond the screenshot's visible rows.

## Archived material

All earlier loose evidence, diagnostic failures, duplicate screenshot and original filenames are preserved in the local `Evidence-Archive-20261005.zip` archive outside this repository. This archive is outside the study folder. Nothing is permanently lost.

The full collection instructions moved to [docs/full_evidence_guide.md](../docs/full_evidence_guide.md). The five required failure demonstrations and the complete four-machine inventory still need their own records for a full assignment submission. This concise set supports the short video and does not claim those missing records exist.
