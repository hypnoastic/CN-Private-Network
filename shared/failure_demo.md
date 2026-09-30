# Phase 1 failure demonstrations — PDF §6.3

Start from passing DNS, HTTPS, balancing, and caching checks. Perform **one scenario at a time**. Save the command, output/screenshot, explanation, and restored result under `evidence/collected/`. Use a second Terminal tab for stop commands. In every new tab, run:

```bash
cd "$HOME/Downloads/CN-Private-Network"
source shared/common.sh
cn_load_env
```

## 1. Wrong DNS server configured on a client

**RUN ON MAC 4.** Its original DNS must already have been saved by Step 16. Mac 3 runs only Backend A, with no DNS service.

```bash
python3 shared/client_dns.py wrong-server
dig +time=2 +tries=1 "$APP_DOMAIN"
ping -c 3 "$EDGE_IP"
/usr/bin/curl --disable --noproxy '*' --connect-timeout 3 --max-time 8 -i "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
```

Expected: dig cannot contact a working resolver and name-based curl fails; ping may still succeed. **Layer:** DNS/application lookup versus IP/network reachability. The wrong resolver prevents finding the name even though the LAN still works. The script changes the selected macOS service to `MAC3_IP`, preserves the original DNS backup, and flushes the OS DNS cache. Check the dig SERVER line. Applications with their own cached answer may temporarily succeed; use a fresh curl process and the dig result as evidence.

**Restore on Mac 4:**

```bash
python3 shared/client_dns.py repair-project
bash shared/test_dns.sh
bash shared/test_https.sh
```

This restores the working project resolver. At the end of the evaluation, `bash mac4_backend_b_client/restore_client_dns.sh` restores the pre-project DNS settings.

## 2. DNS record points to the wrong IP

**RUN ON MAC 1:** stop DNS, inject only the APP_DOMAIN record error in the generated local config, then start that exact config:

```bash
bash mac1_dns_client/stop_dns.sh
python3 shared/failure_injection.py wrong-record
python3 shared/service_control.py dns start
```

Keep the last command running. Use `service_control.py` here because normal `start_dns.sh` intentionally regenerates correct records from `network.env`. The wrong destination is Mac 3, which has no HTTPS edge on `HTTPS_PORT`.

**RUN ON MAC 4:**

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
dig @"$DNS_IP" "$APP_DOMAIN"
dig "$APP_DOMAIN"
/usr/bin/curl --disable --noproxy '*' --connect-timeout 3 --max-time 8 -i "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
```

Expected: DNS succeeds but returns Mac 3; TCP to its HTTPS port normally fails. If another service uses that port, the wrong response or certificate mismatch still demonstrates the wrong destination. **Layer:** DNS data causes a wrong IP destination; TCP/TLS then exposes the error. DNS is a directory, not proof that a service exists.

**Restore on Mac 1, second tab:**

```bash
bash mac1_dns_client/stop_dns.sh
python3 shared/failure_injection.py restore-record
bash mac1_dns_client/start_dns.sh
```

**Restore/check on Mac 4:**

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
bash shared/test_dns.sh
bash shared/test_https.sh
```

## 3. Stop one backend

**RUN ON MAC 3, second tab:**

```bash
bash mac3_backend_a/stop_backend.sh
```

**RUN ON MAC 4:**

```bash
for n in 1 2 3 4 5 6; do
  /usr/bin/curl --disable --noproxy '*' --http1.1 --connect-timeout 4 --max-time 15 -i "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
done
```

Expected: successful responses from B as nginx encounters A's refused connection and retries using its standard error/timeout behavior. A failed attempt may appear in nginx's error log. **Layer:** backend application/TCP availability; DNS and the edge's TLS connection still work. nginx's default passive behavior may temporarily skip a failed peer and try it again later; this is not an active health-check system. In this clean Ctrl+C/stop case the refusal is immediate; other network failures may involve timeouts. Do not use `test_load_balancing.sh` while A is intentionally stopped: it correctly fails unless both A and B appear.

**Restore on Mac 3:**

```bash
python3 mac3_backend_a/backend_a.py
```

**RUN ON MAC 4:** allow the default passive failure timeout to expire, then check:

```bash
sleep 11
bash shared/test_load_balancing.sh
```

## 4. Stop both backends

**RUN ON MAC 3:**

```bash
bash mac3_backend_a/stop_backend.sh
```

**RUN ON MAC 4:**

```bash
bash mac4_backend_b_client/stop_backend.sh
dig "$APP_DOMAIN"
/usr/bin/curl --disable --noproxy '*' --http1.1 --connect-timeout 4 --max-time 15 -v "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
```

Expected: correct DNS and successful TLS authentication of Mac 2, followed by **502 Bad Gateway** with both stopped backends refusing connections. A dropped connection instead of refusal may yield an upstream timeout/504. **Layer:** edge-to-backend TCP/application failure. A working edge cannot create an application response without an upstream.

**Restore on Mac 3:**

```bash
python3 mac3_backend_a/backend_a.py
```

**Restore on Mac 4, backend Terminal:**

```bash
python3 mac4_backend_b_client/backend_b.py
```

**Verify on Mac 4, client Terminal:**

```bash
sleep 11
bash shared/test_https.sh
bash shared/test_load_balancing.sh
```

## 5. Wrong destination port

**RUN ON MAC 4.** Choose a port that is closed **on Mac 2**, without changing any service:

```bash
WRONG_PORT=65534
while [ "$WRONG_PORT" = "$HTTPS_PORT" ] || nc -z -G 2 "$EDGE_IP" "$WRONG_PORT"; do
  WRONG_PORT=$((WRONG_PORT - 1))
done
printf 'Closed destination port selected: %s\n' "$WRONG_PORT"
ping -c 3 "$EDGE_IP"
dig "$APP_DOMAIN"
/usr/bin/curl --disable --noproxy '*' --connect-timeout 3 --max-time 8 -i "https://$APP_DOMAIN:$WRONG_PORT/api/status"
```

Expected: ping and DNS succeed, but TCP on the wrong port is refused or times out before TLS begins. **Layer:** transport destination port. An IP identifies a host/interface; a port identifies a service on it.

**Restore on Mac 4:** simply use the correct configured port again:

```bash
unset WRONG_PORT
/usr/bin/curl --disable --noproxy '*' --http1.1 -i "https://$APP_DOMAIN:$HTTPS_PORT/api/status"
bash shared/test_https.sh
```

No persistent configuration was changed in scenario 5. Finish with all five restore outcomes saved, then follow README Steps 24–25.
