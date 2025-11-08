# RUDY / Slow POST Defense & Detection Guide

> **Purpose:** This guide explains how to detect, investigate, and mitigate application-layer “Slow POST” attacks that exhaust web-server threads by trickling request bodies. It is intended for use in **authorized environments** only (internal incident response, SOC monitoring, red/blue exercises, etc.).

---

## 1. Understanding the Attack

**Attack mechanics:**
- The attacker opens many HTTP `POST` connections.
- Each request declares an enormous `Content-Length`.
- The attacker **sends body data extremely slowly** (e.g., 1 byte every 10 seconds).
- Each connection monopolizes a server worker/thread until the request completes.
- The cumulative effect is thread exhaustion → new clients hang or timeout.

**Why it works:**
- Many web servers dedicate a full thread or process per connection.
- Default body-read timeouts are generous (30–300 seconds).
- Application servers trust the declared `Content-Length`.

---

## 2. Early-Warning Indicators

| Category | Observable Symptoms |
|-----------|--------------------|
| **Network** | Many open TCP sessions with minimal throughput. SYN + ACK complete but body bytes trickle slowly. |
| **Web server metrics** | Spike in “reading request body” or “request in progress.” Worker utilization near 100%. |
| **Logs** | Long-lived `POST` requests that never finish, huge `Content-Length`, very small `request_length`. |
| **Client behavior** | Same IP(s) repeatedly open dozens/hundreds of POSTs. User-Agent often random or stale. |
| **Application** | Front-end responsiveness drops although CPU / network utilization remains moderate. |

---

## 3. Log-Based Detection

### Apache

Enable detailed timing in access logs:
```apache
LogFormat "%h %l %u %t \"%r\" %>s %b %D %I \"%{User-agent}i\"" rudy
CustomLog logs/rudy.log rudy
````

Focus on:

* Large `Content-Length` but low `%I` (bytes received).
* Request durations (`%D`) >> expected.

### NGINX

Custom log format:

```nginx
log_format slowpost '$remote_addr "$request" $status '
                    '$request_time req_s '
                    '$request_length bytes_in '
                    '$body_bytes_sent bytes_out '
                    '$upstream_response_time up_resp';
```

Query examples (using `grep`/`awk`/`GoAccess`/SIEM):

```bash
awk '$6 == "POST" && $7 > 30 && $8 < 2000' access.log
```

### SIEM Correlation Rules

* **Rule 1:** ≥ N (10–20) concurrent POSTs from same IP with `request_time > 60 s`.
* **Rule 2:** POSTs with `Content-Length > 1 MB` but `bytes_in < 10 KB`.
* **Rule 3:** ≥ 5 HTTP 408/499 per minute from same IP.

---

## 4. Real-Time Telemetry

### a. Metrics to collect

* Active connections by state (`reading_request_body`, `keepalive`, etc.)
* Request time histograms per method.
* Bytes received per request vs. declared `Content-Length`.
* Worker utilization (% busy).

### b. Prometheus / Grafana example

```yaml
expr: (sum(rate(nginx_http_request_duration_seconds_sum{method="POST"}[1m]))
      / sum(rate(nginx_http_request_duration_seconds_count{method="POST"}[1m]))) > 30
for: 2m
labels:
  severity: warning
```

---

## 5. Mitigation Techniques

### A. Timeouts & Rate Limits

| Server     | Directive                                                    | Purpose                      |
| ---------- | ------------------------------------------------------------ | ---------------------------- |
| **Apache** | `RequestReadTimeout header=20 body=30`                       | Drops slow bodies after 30 s |
|            | `LimitRequestBody 1048576`                                   | 1 MB limit per request       |
| **NGINX**  | `client_header_timeout 10s`                                  | Limit header read            |
|            | `client_body_timeout 15s`                                    | Drop slow body uploads       |
|            | `limit_req_zone $binary_remote_addr zone=one:10m rate=1r/s;` | Rate-limit POSTs             |
| **IIS**    | `<requestFiltering>` `maxAllowedContentLength`               | Cap body size                |
|            | `<serverRuntime uploadReadAheadSize="4096" />`               | Require min read speed       |

---

### B. Application-Layer Defenses

* Validate `Content-Length` in middleware; reject absurdly large values.
* Use async frameworks (Node.js, FastAPI + Uvicorn, NGINX) for I/O.
* Implement **request-body streaming timeouts**.

---

### C. Infrastructure

* Terminate clients at a **reverse proxy / CDN edge** enforcing stricter timeouts.
* Employ **Anycast / load-balancer** with health-based routing.
* Enable **connection per IP** caps at the firewall (`connlimit`, `hashlimit`, WAF rules).

---

## 6. Example Apache Mitigation Snippet

```apache
<IfModule reqtimeout_module>
  RequestReadTimeout header=20-40,minrate=500
  RequestReadTimeout body=20,minrate=500
</IfModule>

<IfModule mod_security2.c>
  SecRuleEngine On
  SecRule REQUEST_HEADERS:Content-Length "@gt 1000000" "id:1001,deny,msg:'Excessive Content-Length'"
  SecAction phase:5,pass,nolog,initcol:ip=%{REMOTE_ADDR},setvar:ip.rudy_score=+1,expirevar:ip.rudy_score=60
  SecRule IP:RUDY_SCORE "@ge 5" "id:1002,drop,msg:'Slow POST DoS suspected'"
</IfModule>
```

---

## 7. Example NGINX Defensive Config

```nginx
client_max_body_size 1m;
client_header_timeout 10s;
client_body_timeout 15s;

limit_conn_zone $binary_remote_addr zone=addr:10m;
limit_conn addr 10;

limit_req_zone $binary_remote_addr zone=req:10m rate=2r/s;
limit_req zone=req burst=5 nodelay;
```

---

## 8. Incident Response Workflow

| Step                       | Action                                                            |
| -------------------------- | ----------------------------------------------------------------- |
| **1. Detect**              | SOC alert triggers on long POSTs or worker starvation.            |
| **2. Confirm**             | Check logs & metrics; validate pattern of incomplete bodies.      |
| **3. Contain**             | Tighten timeouts; block offending IPs / ASNs; throttle POST rate. |
| **4. Preserve Evidence**   | Save logs, pcap, and metrics for root-cause analysis.             |
| **5. Eradicate / Recover** | Apply permanent limits and patch configurations.                  |
| **6. Lessons Learned**     | Add dashboards, run tabletop simulation, update runbooks.         |

---

## 9. Testing Defenses Safely

* Build an **isolated lab** (local VM, container, or cloud sandbox).
* Use **loopback or private subnet** (no shared traffic).
* Simulate multiple slow connections at low concurrency (≤10) just to observe behavior.
* Validate that the server drops slow bodies and remains responsive.

---

## 10. Summary Checklist

- Enable header/body read timeouts
- Cap `Content-Length`
- Monitor request-duration and body ingress rates
- Use event-driven front ends
- Rate-limit POSTs per IP
- Employ WAF/IDS slow-read rules
- Test mitigations quarterly

---

**References**

* [Trustwave – Mitigating Slow HTTP DoS Attacks](https://www.trustwave.com/Resources/SpiderLabs-Blog/%28Updated%29-ModSecurity-Advanced-Topic-of-the-Week--Mitigating-Slow-HTTP-DoS-Attacks/)
* [Radware DDoSPedia – RUDY](https://security.radware.com/knowledge-center/DDoSPedia/rudy-r-u-dead-yet/)
* [Qualys – Protect Against Slow HTTP Attacks](https://community.qualys.com/blogs/securitylabs/2011/11/02/how-to-protect-against-slow-http-attacks)
