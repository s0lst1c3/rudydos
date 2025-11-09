# rudydos

**RUDY** (R-U-DEAD-YET) is a proof-of-concept tool that demonstrates how **Layer 7 Slow POST Denial of Service attacks** work.  
This implementation is written in Python 3 and is inspired by the original *r-u-dead-yet* PoC by Hybrid Security.

> **Disclaimer:**  
> This tool is for **educational and authorized testing purposes only**.  
> Do **not** use it on systems or networks that you do not own or have explicit permission to test.  
> Misuse of this software may violate computer crime laws.

---

## Overview

RUDY attacks exploit how web servers handle long-running HTTP POST requests.  
The attacker sends a valid header with an extremely large `Content-Length` value and then transmits the body **one byte at a time** with large delays between each byte. This causes the target server to hold a worker thread open indefinitely, eventually exhausting available connections.

This tool automates that process across multiple worker processes to simulate a realistic Layer 7 DoS.

> ***Included Defensive Guidance:** In addition to the PoC attack logic and usage instructions, this repository includes a compact **Defense & Detection Guide**. The guide covers practical detection checks, recommended server and proxy timeout hardening, WAF and `mod_reqtimeout` tuning, logging/metric signals to watch for, and safe test configurations you can use to validate protections in a controlled environment. See `BLUETEAM.md`.*

---

## Features

- Supports **SOCKS5 proxy chains** for anonymized connections (e.g., via Tor) — proxy handling/format unchanged.
- Performs **form discovery and parameter extraction** using BeautifulSoup.
- Configurable:
  - Number of connections
  - Sleep time between bytes
  - **User agent rotation** (load from a local file *or* fetch from a remote JSON URL)
- Fully written in **Python 3** (ported from legacy Python 2 version)
- Works on Linux, macOS, and Windows

---

## Requirements

| Dependency | Purpose |
|-------------|----------|
| `requests` | HTTP requests |
| `pysocks` (PySocks) | SOCKS proxy support (`socks` module) |
| `beautifulsoup4` | HTML parsing |

Install dependencies using:

```bash
pip install -r requirements.txt
````

Example `requirements.txt`:

```
requests
pysocks
beautifulsoup4
```

> Note: older versions referenced `requesocks` / `SocksiPy`.
> This version uses `requests` + `pysocks` for modern compatibility.

---

## Setup

### 1. Create and activate a virtual environment

**Linux/macOS:**

```bash
python3 -m venv env
. env/bin/activate
```

**Windows (PowerShell):**

```powershell
py -3 -m venv env
.\env\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Verify the environment

```bash
python --version
```

---

## Usage

### Basic Example

```bash
python3 rudy.py --connections 100 --target http://example.local/login.php
```

This command:

* Connects to `http://example.local/login.php`
* Prompts you to select a form and POST parameter
* Spawns 100 child processes that slowly transmit data

---

### User-Agent Loading (New Behavior)

The `--user-agents` flag now supports **two modes**:

1. **Local file** — load one user-agent string per line (original behavior)
2. **Remote JSON URL** — fetch a JSON file containing user-agent strings or nested objects, and automatically extract all recognizable user agents.

#### Examples

Local file (one UA per line):

```bash
python3 rudy.py --target http://example.local/login.php --user-agents ./user_agents.txt
```

Remote JSON (e.g., microlinkhq list):

```bash
python3 rudy.py --target http://example.local/login.php --user-agents https://cdn.jsdelivr.net/gh/microlinkhq/top-user-agents@master/src/index.json
```

> If the JSON doesn’t have a direct list of user agents, the tool will recursively collect string values and heuristically filter those that look like real user agents (e.g., containing `Mozilla`, `AppleWebKit`, etc.).

If `--user-agents` is not provided, the script defaults to a Googlebot-style user agent.

---

### Optional Flags

| Flag            | Description                                  | Default     |
| --------------- | -------------------------------------------- | ----------- |
| `--connections` | Number of simultaneous worker processes      | `50`        |
| `--sleep`       | Seconds to wait before sending each byte     | `10`        |
| `--user-agents` | Path to file or JSON URL for user-agent list | Built-in UA |
| `--proxies`     | File(s) containing SOCKS proxy list(s)       | None        |

Example with proxy chain (unchanged):

```bash
python3 rudy.py --connections 50 --target http://example.com/login.php --proxies proxies.txt
```

Example `proxies.txt`:

```
127.0.0.1 9050
198.51.100.10 1080
```

---

## Example Attack Flow

1. Script fetches target page and parses available forms.
2. User selects a form and an input field to attack.
3. Tool establishes concurrent TCP connections (direct or via SOCKS proxies).
4. Each connection sends headers and slowly transmits the POST body.
5. The target server holds resources open until exhaustion.

---

## Cross-Platform Notes

* The tool’s Python code is OS-agnostic.
* Network management commands in the blog (e.g., Apache restarts, virtualenv setup) are compatible with:

  * **Linux/macOS (bash/zsh):** `systemctl`, `service`, `. env/bin/activate`
  * **Windows (PowerShell/CMD):** `py -3`, `env\Scripts\Activate.ps1`, `net start/stop Apache2.4`

---

## Defensive Testing

The RUDY technique is valuable for **defensive testing**:

* Validate WAF rules (e.g., ModSecurity)
* Test Apache modules like `mod_reqtimeout`
* Assess timeout policies for reverse proxies or load balancers
* Benchmark asynchronous servers (e.g., Nginx, Node.js) under slow POST load

---

## Legal & Ethical Notice

Use this software responsibly.
Running denial-of-service tests without authorization may be illegal under laws such as the CFAA (US), the Computer Misuse Act (UK), and equivalent statutes in other jurisdictions.

If conducting authorized testing:

* Obtain **written consent** from stakeholders.
* Limit the scope to **your own infrastructure**.
* Use isolated environments or private test networks.

---

## References

* [Hybrid Security – r-u-dead-yet (original PoC)](https://code.google.com/p/r-u-dead-yet/)
* [Trustwave – Mitigating Slow HTTP DoS Attacks](https://www.trustwave.com/Resources/SpiderLabs-Blog/%28Updated%29-ModSecurity-Advanced-Topic-of-the-Week--Mitigating-Slow-HTTP-DoS-Attacks/)
* [Radware – RUDY Attack Overview](http://security.radware.com/knowledge-center/DDoSPedia/rudy-r-u-dead-yet/)
* [Akamai – Slow DoS on the Rise](https://blogs.akamai.com/2013/09/slow-dos-on-the-rise.html)
* [Qualys – Protecting Against Slow HTTP Attacks](https://community.qualys.com/blogs/securitylabs/2011/11/02/how-to-protect-against-slow-http-attacks)

