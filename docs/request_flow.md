# A request from name to response

```text
Client on Mac 1 or Mac 4
  | DNS question: A record for APP_DOMAIN
  v
Mac 1 dnsmasq, destination UDP 53
  | DNS response: EDGE_IP = Mac 2 private IPv4
  v
Client opens TCP to Mac 2:HTTPS_PORT
  | SYN -> SYN-ACK -> ACK
  v
TLS handshake with nginx
  | ClientHello -> ServerHello -> certificate/authentication
  | -> key agreement -> Finished (details depend on TLS version)
  v
Encrypted HTTP request: GET /api/status
  v
Mac 2 nginx decrypts and selects the next upstream
  | Separate HTTP/TCP connection to Mac 3:3001 or Mac 4:3002
  v
Backend returns JSON and X-Backend: A or B
  v
nginx encrypts the response on the client's TLS connection
  v
Client validates/reads the HTTPS response
```

DNS success proves only that the client found an address. It does not prove that a destination port is listening, that a certificate is trusted, or that the application works. The client knows the edge domain and HTTPS port; only nginx needs both backend addresses. The browser URL never changes to a backend address.

There are **two distinct TCP connections**: client↔edge and edge↔backend. Each has its own source IP/port, destination IP/port, sequence numbers, and acknowledgements. nginx forwards the original client information through `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto` because the backend's TCP peer is the edge.

TLS terminates at Mac 2. The backend hop is ordinary HTTP for this Phase 1 topology. To see unencrypted backend headers, capture the edge↔backend connection on Mac 2, Mac 3, or Mac 4. A normal Mac 1 capture sees only its own traffic, not all other LAN conversations.

For `/cache-demo`, a fresh cached representation may be reused for 60 seconds. If the client sends `If-None-Match: "cn-project-v1"`, either backend can return 304 without the representation body. This is HTTP cache validation, independent of DNS lookup.

Ordinary website DNS queries are forwarded by Mac 1 to the configured `UPSTREAM_DNS`. The entire `.test` namespace remains local, including nonexistent private names. This keeps internet name resolution available during the lab without changing the application request flow.
