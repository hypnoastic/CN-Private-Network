# Phase 1 architecture

```text
             Shared private Wi-Fi / Ethernet LAN
                        MAC 1
                   DNS + main client
              dnsmasq, UDP/TCP port 53
                        |
        DNS: app.<team>.test and api.<team>.test -> MAC 2
                        |
                        v
                        MAC 2
                nginx + TLS termination
               HTTPS + round-robin balancer
                 TCP 8443 (configurable)
                     /       \
         HTTP over TCP       HTTP over TCP
                   /           \
                MAC 3         MAC 4
              Backend A       Backend B + client
              0.0.0.0:3001     0.0.0.0:3002
```

Mac 4's client also queries Mac 1 and connects to Mac 2 over HTTPS. Even when Mac 4's own backend serves a request, the client goes through the edge. DNS provides an address; DNS does not relay the HTTPS request. Return data follows backend → nginx → client on established connections.

`network.env` is the only normal configuration input. `DNS_IP = MAC1_IP`, `EDGE_IP = MAC2_IP`, `BACKEND_A_IP = MAC3_IP`, and `BACKEND_B_IP = MAC4_IP` are validated. No dedicated switch or router configuration is required; the existing Wi-Fi access point/router or LAN switch carries frames. The default gateway connects the LAN to other networks, but same-subnet traffic does not need to be routed through it.

Mac 2 also selects Mac 1 as its resolver so there are **two other Macs** (Mac 2 and Mac 4) as required by PDF Task B. This does not change any service placement.

Conceptual equivalents: Mac 1 is like a managed DNS service such as Route 53; Mac 2 is like an application load balancer such as AWS ALB or GCP Load Balancer; Macs 3/4 are application instances. These are explanatory parallels; the entire running setup stays local. The edge is not configured as a CDN cache. HTTP caching is demonstrated by backend cache headers and client conditional requests.
