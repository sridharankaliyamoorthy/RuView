# Running RuView locally (and opening it from a phone)

Verified against `5780c23` on Linux, 2026-08-10. Every command below was run
during the audit except where marked otherwise.

The dashboard is a plain static web app served by the Rust sensing server. There
is no npm build step. `ui/mobile/` is a **separate React Native / Expo app** — you
cannot open it in Safari, so ignore it for this.

---

## Read this first

**Without ESP32 hardware, everything you see is synthetic.** With no CSI source
on UDP :5005 the server takes the `auto` → simulated path and generates poses,
presence and vitals. It labels this clearly (see below), but the skeletons moving
on screen are not people.

**Auth is OFF by default.** `/api/v1/*` answers any unauthenticated request with
HTTP 200 (SEC-004). The moment you bind to anything other than loopback, your
whole LAN can read the sensing stream. The commands below set a token; do not
drop it.

---

## 1. Clone and build

```bash
git clone -b claude/ruview-wifi-audit-afopqa \
  https://github.com/sridharankaliyamoorthy/RuView
cd RuView

# Required. Two workspace members (crates/ruview-swarm, crates/worldgraph) are
# submodules — without this, cargo cannot resolve the workspace at all.
git submodule update --init --recursive

cd v2
cargo build --release -p wifi-densepose-sensing-server
```

The toolchain is pinned to Rust **1.89** by `v2/rust-toolchain.toml`; rustup will
fetch it. First build is slow — the debug build took ~25 minutes and 17 GB of
`target/` during the audit. **Have ~40 GB free.**

> Do **not** use `cargo test --workspace` — it pulls GTK3 via
> `wifi-densepose-desktop` and fails on any headless machine. Add
> `--exclude wifi-densepose-desktop` if you want the tests (3,894 pass).

## 2. Run it — localhost only

```bash
./target/release/sensing-server --http-port 8080 --ui-path ../ui
```

Open <http://localhost:8080/ui/index.html>. `--bind-addr` defaults to
`127.0.0.1`, so nothing is exposed off-machine.

## 3. Open it from an iPhone on the same Wi-Fi

```bash
# Find your machine's LAN IP
ipconfig getifaddr en0     # macOS
hostname -I | awk '{print $1}'   # Linux

# Set a token — auth is off without it
export RUVIEW_API_TOKEN="$(openssl rand -hex 24)"

./target/release/sensing-server \
  --http-port 8080 \
  --ui-path ../ui \
  --bind-addr 0.0.0.0 \
  --allowed-host 192.168.1.42:8080     # <- your actual LAN IP
```

On the iPhone: **`http://192.168.1.42:8080/ui/index.html`**

Three things that will otherwise waste your time:

- **`--allowed-host <ip>:8080` is mandatory.** Host-header validation is on by
  default (a deliberate DNS-rebinding defence) and rejects a bare LAN IP.
  Without it the server looks broken when it is working correctly.
- **Use the full `/ui/index.html` path.** Bare `/` does not serve the dashboard.
- **The web UI is not responsive.** At a 390px iPhone viewport the header and
  status cards clip horizontally and the page does not reflow. It is usable in
  landscape or with pinch-zoom, but it was not designed for a phone.

## 4. What to look for

The audit's open question was whether a viewer can tell simulated data from real.
Two indicators, both verified at runtime:

- a persistent **`● Simulated`** pill in the header, on every tab;
- an amber **"Data Source / SIMULATED / Server running without hardware"** card
  in the System Status grid.

Both are truthful and always present. Neither is loud — the pill is small and the
amber card is low-contrast. Judging whether that is prominent enough for a client
demo on a phone screen is the useful thing to do here.

The startup log is also worth reading; it states the situation plainly:

```
WARN No real CSI source at boot — serving SIMULATED data (tagged as 'simulated',
     not production) while the UDP :5005 receiver stays bound.
INFO API auth: OFF — /api/v1/* is unauthenticated.
INFO Edge module registry: enabled — upstream=https://storage.googleapis.com/...
WARN WDP_RUFIELD_SIGNING_SEED unset/invalid — using the DETERMINISTIC DEV signing key.
```

Those four lines are, respectively: C7, SEC-004, SEC-009 and SEC-011.

## 5. Useful endpoints

```bash
curl -s localhost:8080/api/v1/status  | jq   # {"source":"simulated", ...}
curl -s localhost:8080/api/v1/info    | jq
curl -s localhost:8080/api/v1/pose/current | jq '.persons[0].confidence'
curl -s localhost:8080/api/v1/sensing/latest | jq '.classification'
```

Every data-bearing endpoint carries `"source": "simulated"`. Note that
`/api/v1/pose/current` returns a person at `confidence: 0.9` whose 17 keypoints
all have `confidence: 0.0` — the pose model is a stub (C5), and the person-level
number comes from the simulator.

## 6. Connecting real hardware

Out of scope for this document and untested by the audit — no ESP32 was
available. See `firmware/esp32-csi-node/README.md`, and read **SEC-002** first:
`provision.py` takes the WiFi password on the command line and writes it to NVS
in plaintext.
