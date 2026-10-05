# Phase 1 evidence guide

The PDF requires evidence for LAN inventory/reachability, private DNS, both backends, TLS trust, load balancing, caching, and all five failures (§§6.1–6.3 and §9). Capture real results on your four Macs; generated examples are not evidence.

## Prepare on Mac 4 (recommended capture client)

Use a separate Terminal from Backend B:

```bash
cd "$HOME/Downloads/CN-Private-Network"
source shared/common.sh
cn_load_env
mkdir -p evidence/collected
LAN_IFACE="$(route -n get "$DNS_IP" | awk '/interface:/ {print $2; exit}')"
printf 'Capture interface: %s\nDNS: %s\nEdge: %s\nHTTPS port: %s\n' "$LAN_IFACE" "$DNS_IP" "$EDGE_IP" "$HTTPS_PORT"
```

In Wireshark, select that interface and start capturing. On Mac 1, a query to its own DNS address may stay on `lo0`, so capture `lo0` for self-queries or use Mac 4 to show DNS on the LAN. A client capture normally cannot see another machine's separate backend connection.

If Wireshark capture permissions are unavailable, **on Mac 4**, record with tcpdump and inspect the resulting file in Wireshark:

```bash
sudo tcpdump -i "$LAN_IFACE" -n -s 0 -U -w evidence/collected/phase1.pcap "port 53 or tcp port $HTTPS_PORT"
```

Leave this running. Run the following capture actions in another configured Terminal tab. End tcpdump with Ctrl+C, then open the file:

```bash
open -a Wireshark evidence/collected/phase1.pcap
```

## 1. DNS query and response

While capturing, run:

```bash
dig @"$DNS_IP" "$APP_DOMAIN"
dig "$APP_DOMAIN"
dig "$API_DOMAIN"
```

Wireshark display filters: `dns` or `udp.port == 53`. Expand **Domain Name System** and identify the question for APP_DOMAIN, transaction ID, query/response flag, and A answer containing Mac 2's actual IP. Match the response transaction ID to the request. The client uses an ephemeral UDP source port; the server listens on destination UDP 53. Show the reverse port direction in the response.

## 2. TCP three-way handshake and HTTP headers

Create a new curl connection:

```bash
/usr/bin/curl --disable --noproxy '*' --http1.1 --verbose "https://$APP_DOMAIN:$HTTPS_PORT/api/status" 2>&1 | tee evidence/collected/http-headers.txt
```

Filter `tcp`, or paste the actual port filter printed by:

```bash
printf 'tcp.port == %s\n' "$HTTPS_PORT"
```

Select the edge connection and use **Follow → TCP Stream** or a `tcp.stream == N` display filter with the stream number Wireshark shows. Find:

1. **SYN:** client → edge, SYN=1, ACK=0; filter `tcp.flags.syn == 1 && tcp.flags.ack == 0`.
2. **SYN-ACK:** edge → client, SYN=1, ACK=1; filter `tcp.flags.syn == 1 && tcp.flags.ack == 1`.
3. **ACK:** client → edge, SYN=0, ACK=1. It follows the SYN-ACK and may share a segment with later data.

Record both IPs and ports. The client source port is ephemeral; the edge destination is HTTPS_PORT. Expand **Transmission Control Protocol** to show relative sequence number, acknowledgement number, TCP length, and window size. Explain that ACKs acknowledge received byte positions and the window controls flow. In relative numbering, the SYN usually starts at 0 and its acknowledgement is 1. A clean capture need not contain a retransmission.

curl verbose output shows request `Host`, path/method, response status, `Content-Type`, `Content-Length`, and `X-Backend`. Browser alternative: open Developer Tools → Network → select `/api/status` → Headers; save a screenshot. Keep certificate validation enabled.

## 3. TLS handshake, certificate, and encrypted application data

Display filter `tls`. If Wireshark has not decoded the custom port, select a packet → **Analyze → Decode As… → TLS** for the TCP port. Identify ClientHello (type 1), ServerHello (type 2), and negotiated version/cipher. `tls.handshake.type == 1 || tls.handshake.type == 2` isolates the hello messages.

Modern clients usually use TLS 1.3. Its Certificate and later handshake messages are encrypted after ServerHello. For the PDF's visible **Certificate and ChangeCipherSpec** evidence, make a fresh TLS 1.2 connection while the capture is running:

```bash
/usr/bin/curl --disable --noproxy '*' --http1.1 --tlsv1.2 --tls-max 1.2 --verbose "https://$APP_DOMAIN:$HTTPS_PORT/api/status" 2>&1 | tee evidence/collected/tls12-validated.txt
```

This changes only the protocol version of this request; trust validation remains enabled. Select the Certificate handshake (`tls.handshake.type == 11`) and inspect its SANs/issuer. Use `tls.record.content_type == 20` for ChangeCipherSpec where decoded. Explain ClientHello → ServerHello → Certificate → key exchange → Finished. Finished is encrypted, so Wireshark may label it encrypted handshake data. Successful authenticated curl output and subsequent Application Data records show completion.

Take a screenshot showing **Application Data** after the handshake. HTTPS HTTP headers/body are encrypted on the client↔edge link, so you generally cannot read X-Backend or JSON in that capture. Show those through curl/browser after decryption. TLS 1.3 compatibility ChangeCipherSpec messages are not a separate certificate or proof of application plaintext.

## 4. Backend and port identification

On **Mac 2**:

```bash
mkdir -p evidence/collected
bash shared/test_backends.sh | tee evidence/collected/backends.txt
```

Save separate screenshots of A's JSON/header and B's JSON/header. To inspect the plain HTTP upstream hop, capture on Mac 2's LAN interface and filter the actual backend ports:

```bash
source shared/common.sh
cn_load_env
printf 'tcp.port == %s || tcp.port == %s\n' "$BACKEND_A_PORT" "$BACKEND_B_PORT"
```

Show nginx's ephemeral source port and destination 3001 or 3002. These are separate TCP connections from the client↔edge connection. Use Decode As → HTTP if needed on a backend port. For HTTPS, 443 is the standard destination port and 8443 is the assignment-permitted substitute. DNS supports UDP/TCP 53; ordinary captured A queries here use UDP.

## 5. Load balancing and HTTP versions

On **Mac 1 or Mac 4**:

```bash
bash shared/test_load_balancing.sh | tee evidence/collected/load-balancing.txt
bash shared/test_https.sh | tee evidence/collected/https.txt
bash shared/test_https.sh --http2 | tee evidence/collected/http2.txt
```

Save A and B header evidence and the PASS summary. Run the HTTP/2 command when Step 9 reports support; otherwise save nginx build information showing it is unavailable. HTTP/1.1 is always demonstrated. The nginx access log on Mac 2 also records the upstream IP, backend header, protocol, and TLS version.

## 6. HTTP caching

```bash
bash shared/test_caching.sh | tee evidence/collected/caching.txt
/usr/bin/curl --disable --noproxy '*' -I "https://$APP_DOMAIN:$HTTPS_PORT/cache-demo"
```

Capture `Cache-Control: public, max-age=60`, `ETag: "cn-project-v1"`, the conditional request header, and `304 Not Modified` with no body. Browser alternative: visit `/cache-demo` with Developer Tools open and **Disable cache unchecked**. A fresh reused response may be marked memory/disk cache; forced reload may revalidate. The scripted conditional request is the deterministic evidence. Explain fresh hit vs conditional validation vs full 200 response.

## 7. Save the full evidence bundle

Use easily identifiable filenames under `evidence/collected/`:

| Evidence | Save |
|---|---|
| Four interfaces/IPs/netmasks/gateways/MACs | `mac1-inventory.txt` through `mac4-inventory.txt` |
| Every pair reachable | ping output/screenshot from each of the four Macs |
| Both names and resolver identity | `dns.txt`, DNS query/answer screenshot |
| Direct Backend A and B | `backends.txt`, both header/JSON screenshots |
| Trusted domain-based HTTPS | `https.txt`, browser certificate/no-warning screenshot |
| Both X-Backend values | `load-balancing.txt` and screenshot |
| HTTP versions | HTTP/1.1 and HTTP/2 (if supported) output |
| DNS/TCP/TLS captures | `phase1.pcap` or `.pcapng`, annotated screenshots |
| TCP source/destination ports and reliability | socket pairs, sequence/ACK/window screenshot |
| TLS 1.2 Certificate/ChangeCipherSpec | `tls12-validated.txt` and screenshots |
| Cache-Control/ETag/304 | `caching.txt` and screenshots |
| Each required broken and restored result | `failure-1` through `failure-5` screenshots/output |
| Generated configuration bundle | copies of dnsmasq.conf and nginx.conf from their owning Macs |

On Mac 1: `cp mac1_dns_client/runtime/dnsmasq.conf evidence/collected/dnsmasq.conf`. On Mac 2: `cp mac2_edge/runtime/nginx.conf evidence/collected/nginx.conf`. Include public certificate information/setup notes, never private keys. Transfer the collected evidence into one review folder only after retaining each Mac's original local DNS backup. Follow [the five failure demonstrations](../shared/failure_demo.md) and [the review checklist](../docs/phase1_demo_checklist.md).
