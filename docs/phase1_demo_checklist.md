# Phase 1 review checklist

Based on PDF §§6.1–6.3, §9, and Review 1 in §10 (50 marks).

- [ ] **Task A:** all four Macs on the same private LAN; all-pairs ping succeeds.
- [ ] Inventory includes each IPv4, netmask/prefix, gateway, interface, and MAC address.
- [ ] Show architecture, service inventory, and request-flow diagrams.
- [ ] **Task B:** both configured `.test` names resolve to Mac 2 through Mac 1.
- [ ] Mac 1 is the main client; Mac 2 and Mac 4 also select Mac 1 DNS, satisfying “two other Macs.”
- [ ] **Task C:** LAN-bound A:3001 and B:3002; `/` and `/api/status`; clear JSON and X-Backend.
- [ ] **Task D:** same edge domain returns both A and B in repeated requests.
- [ ] Explain why clients only know the edge, and identify the separate backend TCP connection.
- [ ] **Task E:** both DNS SANs, certificate trusted on clients, successful HTTPS without bypass.
- [ ] **Task F:** Cache-Control, ETag, conditional 304; explain fresh vs validated vs full responses.
- [ ] **Task G:** save DNS query/answer, SYN/SYN-ACK/ACK, ports, TLS handshake, encrypted data.
- [ ] Show visible TLS 1.2 Certificate and ChangeCipherSpec evidence; explain TLS 1.3 visibility.
- [ ] Identify TCP sequence numbers, ACK numbers, and window size; explain reliability.
- [ ] Show HTTP/1.1, and HTTP/2 if nginx supports it; explain HTTP/3 only.
- [ ] Show HTTP headers with curl/browser; save direct A/B and round-robin output.
- [ ] Complete all five §6.3 failures, with evidence and restoration after each.
- [ ] Keep source, generated configuration exports, TLS setup notes, and evidence easy to find.
- [ ] Every team member can explain every role, relevant protocol layers, and cloud parallels.
- [ ] Restore original DNS, stop services, retain the review evidence.

Suggested brief review order: topology/inventory → LAN/ping → DNS → trusted HTTPS → A/B balancing → packet evidence → HTTP caching → the five Phase 1 failures → individual viva. Use the Phase 1 portions of the PDF's final demonstration sequence; the full course's later-phase demonstrations are outside this repository.

Core commands on Mac 1 or Mac 4:

```bash
python3 shared/env_loader.py
bash shared/test_dns.sh
bash shared/test_https.sh
bash shared/test_load_balancing.sh
bash shared/test_caching.sh
```
