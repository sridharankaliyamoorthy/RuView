# C7 runtime evidence — sensing server + dashboard

Captured 2026-08-10 against `sensing-server` built from `5780c23`
(`v2/target/debug/sensing-server`, the binary produced by the C1 test run).

```bash
cd v2 && ./target/debug/sensing-server --http-port 8080 --ui-path ../ui --bind-addr 127.0.0.1
```

No ESP32 present, so the server takes the `auto` → simulated path
(`main.rs:3102`). Every file here is raw captured output.

| File | What it shows |
|---|---|
| `status.json`, `resp*.json` | Raw `/api/v1/*` responses |
| `dashboard_desktop.png` | Dashboard at 1440px |
| `dashboard_iphone.png` | Dashboard at 390×844 (iPhone viewport) |
| `tab_sensing.png`, `tab_live-demo.png` | Sensing / Live Demo tabs |
|  `startup-log.txt` | Full server startup log |

---

## 1. The `exit 78` documentation is wrong — confirmed at runtime

```
WARN No real CSI source at boot — serving SIMULATED data (tagged as 'simulated',
     not production) while the UDP :5005 receiver stays bound. The server promotes
     to live the instant a real frame arrives (issue #1004).
INFO Data source: simulated (udp_receiver=true, simulator=true, wifi=false)
```

The server **starts and serves synthetic data**. It does not exit 78, as
`docker-compose.yml` and `docker-entrypoint.sh` both claim. Confirms the C7
finding from source reading.

**Credit:** the log message itself is exemplary — it says "SIMULATED", says
"not production", explains the promotion behaviour, and names the issue. The
code is honest; only the docs are stale.

## 2. Simulated data IS labelled — on every data-bearing endpoint

| Endpoint | `source` field |
|---|---|
| `/api/v1/status` | `"simulated"` |
| `/api/v1/info` | `"simulated"` |
| `/api/v1/pose/current` | `"simulated"` |
| `/api/v1/sensing/latest` | `"simulated"` |
| `/api/v1/pose/stats` | `"simulated"` |
| `/api/v1/metrics` | *(none — system CPU/mem only, not sensing data)* |

This is a **good result**. My report flagged the risk that a consumer could not
tell fabricated data from real; at the API layer they always can.

## 3. The dashboard labels it too — two independent indicators

From `dashboard_desktop.png`:

- A **persistent `● Simulated` pill in the header**, visible on every tab.
- An **amber "Data Source / SIMULATED / Server running without hardware"** card
  in the System Status grid.

The Sensing tab also carries an "About this data" panel stating
*"…With 0 ESP32 node(s) you get presence detection, breathing estimation, and
gross…"* — an honest disclosure of node count.

**This resolves the open question in the audit report.** A client shown this
demo is told, in two places, that the data is synthetic. It is not screaming —
the pill is small and the amber card is low-contrast — but it is present,
persistent, and truthful.

## 4. SEC-004 confirmed live

```
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/api/v1/status
200
```

No credential, full sensing data returned. The server logs the warning itself:

```
INFO API auth: OFF — /api/v1/* is unauthenticated.
     Set RUVIEW_API_TOKEN=<token> or RUVIEW_OAUTH_ISSUER=<issuer> to enforce auth.
```

Host-header validation is ON by default (3 entries + loopback), which is a real
DNS-rebinding defence and worth crediting.

## 5. C5 pose stub confirmed live

`/api/v1/pose/current` returns a person at **`confidence: 0.9`** whose **17
keypoints all carry `confidence: 0.0`** — exactly the
`inference.rs:283` stub, visible through the API. A UI that renders the skeleton
and reads person-level confidence would display a 90%-confident person made
entirely of zero-confidence joints.

## 6. New findings from this run

- **SEC-011 (Medium) — deterministic dev signing key by default.**
  ```
  WARN ADR-262 P3: WDP_RUFIELD_SIGNING_SEED unset/invalid — RuField surface using
       the DETERMINISTIC DEV signing key.
  ```
  A default deployment signs with a key derived from a constant. Anyone with the
  source can reproduce it, so signatures from an unconfigured deployment prove
  nothing. The warning is loud and honest, and the fix is a documented env var —
  but the insecure state is the default.

- **SEC-012 (Low) — `environment: "production"` while serving synthetic data.**
  `/api/v1/info` returns `"environment": "production"` alongside
  `"source": "simulated"`. Anything keying off `environment` will believe this is
  a production deployment.

- **Version inconsistency.** `/api/v1/info` reports `"version": "0.3.5"`; the
  PyPI package is `2.0.0a1` and the Rust core `2.0.0-alpha.1`. Three different
  version numbers for one product.

- **Adaptive classifier ships at 41.5% accuracy.**
  `INFO Loaded adaptive classifier: 3316 frames, 41.5% accuracy` — loaded and
  active by default, with no UI indication that its accuracy is near chance for a
  multi-class problem.

- **The web UI is not responsive.** At a 390px iPhone viewport
  (`dashboard_iphone.png`) the header and status cards are clipped horizontally;
  the page does not reflow. The mobile client (`ui/mobile/`) is a separate React
  Native / Expo app, not reachable from Safari.

- **The hero copy describes someone else's research.** *"AI can track your
  full-body movement through walls using just WiFi signals. Researchers at
  Carnegie Mellon have trained a neural network…"* is the CMU DensePose paper,
  presented as the product's headline description. Adds to the C10 pattern.
