# Phase 1 protocol layers

| Protocol/concept | OSI teaching model | TCP/IP model | Evidence in this project |
|---|---|---|---|
| DNS | Application (7) | Application | A question/answer, normally UDP 53; TCP 53 also supported |
| HTTP/REST | Application (7) | Application | GET paths, status codes, JSON, request/response headers |
| TLS | Presentation/session (6/5), between HTTP and transport in practice | Usually discussed with application security over transport | Certificate, handshake, encrypted application data |
| TCP | Transport (4) | Transport | Reliable ordered byte stream, handshake, ports, sequence/ACK numbers |
| UDP | Transport (4) | Transport | Datagram DNS query/response; no TCP-style three-way handshake |
| IPv4 | Network (3) | Internet | Private source/destination IPs and same-LAN reachability |
| Ethernet / Wi-Fi | Data link (2) and physical (1) | Link / network access | Interface, MAC address, frames crossing the LAN |

The PDF labels TLS “Session/Transport”; layer boundaries here are a teaching approximation. TLS is not a replacement for TCP in this HTTPS setup. Wi-Fi captures on a normal macOS interface often present Ethernet-style frame headers without radio details.

**TCP reliability and flow control:** the SYN exchanges initial sequence numbers. Each sequence number identifies a position in the byte stream; an ACK states the next byte expected. TCP can retransmit lost bytes. The receive window advertises buffer space to limit how much unacknowledged data the sender sends. SYN and FIN each consume one sequence number. A clean LAN may show no retransmissions; explain their purpose without manufacturing loss. In Wireshark select a TCP stream and expand Sequence Number, Acknowledgment Number, TCP Length, and Window Size.

**HTTP versions:** HTTP/1.1 is demonstrated explicitly by the test scripts. If nginx is built with HTTP/2 support, the renderer enables it and `test_https.sh --http2` verifies ALPN negotiation and HTTP/2 responses. HTTP/2 multiplexes streams over one TCP connection and compresses headers. HTTP/3 uses QUIC over UDP and incorporates TLS 1.3; explain it only, as the PDF specifies.

**TLS evidence:** normal clients may negotiate TLS 1.3. Its Certificate and later handshake messages are encrypted after ServerHello, so they may not be readable without session keys. A fresh, explicitly TLS 1.2 connection exposes the Certificate and ChangeCipherSpec messages for the required evidence; certificate verification stays enabled. Finished is encrypted; successful curl output proves handshake completion.

**Caching/CDN:** Cache-Control sets freshness. ETag is a representation validator. A fresh browser cache hit can avoid a request; a stale entry can be revalidated by a conditional request; a 200 carries the full representation. A CDN would distribute/copy content nearer users, but this project has one local reverse proxy with no proxy cache.

**Email (explanation only):** SMTP sends/relays mail, IMAP synchronizes mailbox state, and POP3 retrieves mail. None is installed or needed for the application. Conventional service ports include SMTP 25 (relay), submission 587, IMAP 143/993, POP3 110/995.

Implementation references: [nginx round-robin defaults](https://nginx.org/en/docs/http/load_balancing.html), [nginx HTTP/2 module](https://nginx.org/en/docs/http/ngx_http_v2_module.html), [dnsmasq configuration manual](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html), and [curl certificate verification and native trust stores](https://curl.se/docs/sslcerts.html). The assignment determines project scope.
