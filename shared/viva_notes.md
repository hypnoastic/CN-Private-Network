# Phase 1 viva notes

| Concept | Simple explanation for this setup |
|---|---|
| DNS | A directory translating a name into an address. Mac 1 answers both project names with Mac 2's address. |
| Resolution vs connection | Resolution finds the IP. A later TCP connection contacts a port on that IP. Either can fail independently. |
| Private IP | An address used within a private network, from 10/8, 172.16/12, or 192.168/16. It is not a globally routed public service address. |
| TCP | An ordered, reliable byte stream between two sockets. Both HTTPS and the backend HTTP hops use it. |
| SYN / SYN-ACK / ACK | The three-way setup exchange: client requests connection, server acknowledges and sends its initial sequence, client acknowledges the server. |
| Source port | Port on the sending endpoint; on an outgoing client connection it is usually temporarily allocated by the OS. |
| Destination port | Port at the receiving endpoint identifying the intended service. The return packet reverses the pair. |
| Ephemeral port | A temporary client-side port, visible in the SYN. Record the actual value in your capture rather than assuming one. |
| Socket pair | Source IP:port and destination IP:port identify one TCP conversation, together with the transport protocol. |
| HTTP | An application protocol with methods, paths, headers, bodies, and status codes. GET requests read our tiny REST resources. |
| HTTPS | HTTP protected by TLS. The URL names the edge; the browser verifies the certificate and encrypts traffic. |
| TLS | Authenticates the server and protects confidentiality/integrity of data in transit. It runs over TCP here. |
| TLS handshake | ClientHello proposes options; ServerHello chooses them; authentication and key agreement establish keys; Finished messages confirm the handshake. Exact ordering differs by TLS version. |
| Certificate | Binds a public key to identity names. The certificate SANs must include APP_DOMAIN and API_DOMAIN. |
| Certificate trust | Clients explicitly trust our self-signed server certificate in their system keychain. The private key never leaves Mac 2. |
| Reverse proxy | Accepts client requests and makes separate requests to upstream servers. It hides backend details from clients. |
| nginx | The actual reverse proxy software on Mac 2; it terminates TLS and selects an upstream backend. |
| Load balancer | Distributes requests among multiple application instances. |
| Round robin | Healthy servers take turns receiving requests; nginx's default strategy. Other clients and retries can affect the sequence one client sees. |
| Backend A / B | Simple Python HTTP servers on Macs 3 and 4, identifiable through X-Backend and status JSON. |
| Why no backend IP in the client | DNS points to the edge; nginx's configuration contains backend addresses. The client uses one stable service name. |
| Cache-Control | `public, max-age=60` allows a cache to treat a representation as fresh for 60 seconds. |
| ETag | A validator for a particular representation: `"cn-project-v1"`. The cache-demo body is identical on both backends. |
| 304 Not Modified | The client's validator matches. The server sends cache metadata with no representation body; the client can reuse its stored content. |
| Encrypted Wireshark payload | Captured TLS application records contain ciphertext. curl/browser sees plaintext after TLS processing; a packet capture lacks the session keys. |

**Ports:** DNS normally uses UDP destination 53 (TCP 53 also exists). HTTPS uses TCP 443 or this project's 8443. Backend A/B use TCP 3001/3002. nginx uses its own ephemeral source port for each upstream connection. The client's port is not automatically forwarded as the backend TCP source port.

**Fresh hit vs conditional vs full request:** a fresh cache entry can be reused without a network request. A conditional request asks whether a cached representation is still current and may receive 304. A full 200 response carries the whole body. curl itself does not save a browser-style cache between invocations; our script explicitly sends the validator.

**TCP reliability:** sequence numbers count bytes, ACKs identify the next byte expected, and retransmissions recover loss. The receive window controls how much data may be in flight. SYN and FIN each consume sequence space. Point at these fields in your saved Wireshark stream.

**Layer diagnosis for the five Phase 1 failures:**

1. DNS: use `dig` and check both the answer and which server answered. Wrong/no answer means the directory lookup is wrong before HTTPS begins.
2. IP/TCP: use ping for IP reachability and inspect the SYN/response or curl connection error. A ping response does not prove an application port is listening.
3. TLS: a connected TCP socket can still produce a certificate name/trust/validity error. Check the requested domain, SANs, trust installation, dates, and the Mac's clock.
4. Application: successful DNS/TCP/TLS followed by nginx 502 indicates the edge could not obtain a backend response. Check direct backend status from Mac 2.

**HTTP/1.1 vs HTTP/2:** HTTP/1.1 exchanges HTTP messages over TCP; HTTP/2 can multiplex multiple streams on one connection. TLS ALPN selects the version at the edge. The backend connections still use HTTP/1.1. HTTP/3 uses QUIC over UDP and is explanation-only.

**TLS 1.2 vs 1.3 capture:** TLS 1.2's Certificate and ChangeCipherSpec can be visible in a fresh capture. TLS 1.3 encrypts the server certificate after ServerHello and may send compatibility ChangeCipherSpec records. Successful validated curl output proves that the encrypted Finished exchange completed; an unreadable certificate packet alone does not mean a failed handshake.

**Topology/cloud parallels:** the LAN access point/switch connects the devices; private DNS resembles Route 53; nginx resembles an application load balancer; the two Python servers resemble application instances. A CDN caches content near users, whereas our proxy forwards to local backends. SMTP sends mail, IMAP synchronizes mailboxes, POP3 retrieves mail; those course topics require explanation only.
