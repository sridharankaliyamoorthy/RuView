# Hardware trial — does breathing detection work on real CSI?

> **Status: UNTESTED against hardware.** No ESP32 existed in the environment where
> this audit ran. Every command below traces to a file in this repository (cited
> inline), but none was executed against a board. The pass/fail criteria are
> **predictions** — you are the one who falsifies them.
>
> This is deliberate. The audit does not mark hardware claims CONFIRMED without
> real silicon, and neither does its own guide. Per the repo's own rule: a
> successful build is not hardware evidence.

**Baseline:** `5780c23` · Companion to [`../RECOMMENDATION.md`](../RECOMMENDATION.md)

---

## The one question

**Does `BreathingExtractor` track a real chest at a known rate, on real CSI?**

That is the whole trial. It is the only claim in the repository that survived
synthetic ground truth it had never seen — zero BPM error across 6–30, `None` on
pure noise 20/20 (see `docs/spec/claim-matrix.md` §C4).

**Explicitly not under test:** pose estimation (C5 — an honest 3.0% PCK stub
returning `confidence: 0.0`), heart rate (SEC-005 — fail-silent in the published
release), the cog catalog (R1 — not in this repository), or the 82.69% MM-Fi
figure (C6 — a cited external result). Testing several things at once means a
failure tells you nothing about which one failed.

---

## 1. Board choice — read this before ordering

**Recommended: ESP32-C6.** It is the only variant with a hardware-verified CSI
yield figure anywhere in this repository. From
`firmware/esp32-csi-node/release_bins/version.txt`:

```
0.6.7
note: RuView#893 — display-less boards capture DATA frames (CSI yield 0pps fix);
      hardware-verified on ESP32-C6 (0->27 pps)
```

A matching prebuilt ships at `release_bins/c6-adr110/`.

**The ESP32-S3-DevKitC-1 trap.** The obvious choice is the wrong one, and it fails
silently:

- `release_bins/esp32-csi-node.bin` is **byte-identical** to
  `release_bins/s3-adr110/esp32-csi-node.bin` (both sha256 `e21ef94aba779d53…`) —
  the default S3 prebuilt is the **display-enabled** build.
- Per `firmware/esp32-csi-node/sdkconfig.defaults.devkitc`, on a panel-less S3 the
  ADR-045 runtime probe **false-positives**: the SH8601 init sequence reports
  success with floating QSPI pins, `display_is_active()` returns true, `main.c`
  skips the RuView#893 MGMT+DATA promiscuous upgrade, and **CSI yield collapses to
  0 pps**.

So a DevKitC-1 flashed with the stock prebuilt **captures nothing**, and looks
like a wiring or WiFi problem rather than a build problem. Fixing it needs a
Docker + ESP-IDF build with the `devkitc` overlay — i.e. the toolchain you were
trying to avoid.

**Thermal warning — buy a full-size board.** From
`firmware/esp32-csi-node/README.md` §116: the firmware runs the radio with modem
sleep disabled (`WIFI_PS_NONE`, required for continuous CSI) plus edge DSP on
Core 1, with no duty-cycling. On coin-sized clones (ESP32-S3-Zero, SuperMini) the
repo reports boards running hot to the touch, and *"in at least one field report,
boards that ran hot during a session failed to power on afterward (regulator
damage suspected)"*. Give it airflow, do not enclose it, and check it by hand in
the first few minutes.

| | Choose |
|---|---|
| **Primary** | ESP32-C6 dev board, full size, ≥4 MB flash |
| **If you already own an S3** | Expect to build with the `devkitc` overlay via Docker; the stock prebuilt will give you 0 pps |
| **Avoid** | Coin-sized clones of any chip |

## 2. Verify the binaries before flashing

The repo ships `SHA256SUMS.txt` beside each prebuilt set and **no document tells
you to check them**. Check them — you are about to run a third-party binary on
hardware attached to your network.

```bash
cd firmware/esp32-csi-node/release_bins/c6-adr110
sha256sum -c SHA256SUMS.txt        # paths inside are repo-root-relative
```

Run it from the repository root if the relative paths do not resolve. Any
mismatch: stop and do not flash.

## 3. Flash

Offsets are from `firmware/esp32-csi-node/README.md` §0/§2 and must match the
partition table. For the **C6** prebuilt:

```bash
python -m esptool --chip esp32c6 --port /dev/ttyACM0 --baud 460800 \
  write_flash --flash_mode dio \
  0x0     firmware/esp32-csi-node/release_bins/c6-adr110/bootloader.bin \
  0x8000  firmware/esp32-csi-node/release_bins/c6-adr110/partition-table.bin \
  0xf000  firmware/esp32-csi-node/release_bins/c6-adr110/ota_data_initial.bin \
  0x20000 firmware/esp32-csi-node/release_bins/c6-adr110/esp32-csi-node.bin
```

Port is `/dev/ttyACM0` or `/dev/ttyUSB0` on Linux, `/dev/cu.usbmodem*` on macOS,
`COMn` on Windows. Confirm the port before writing — flashing the wrong device is
not recoverable from this document.

## 4. Provision WiFi — not the way the README shows

`firmware/esp32-csi-node/provision.py` documents this as its headline example:

```bash
python provision.py --port COM7 --ssid "MyWiFi" --password "secret" ...   # DON'T
```

**This is SEC-002.** `argv` is world-readable via `/proc/<pid>/cmdline` on a
multi-user host and lands in your shell history. The credential is then written to
NVS as a `data string` (`provision.py:186`) — plaintext in flash unless NVS
encryption is separately enabled, which this script never configures.

The script supports a per-port JSON **state file** it merges from
(`provision.py:24-37`), so you can pre-seed the password instead of passing it on
the command line:

```bash
STATE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/wifi-densepose/esp32-provision-state"
mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"

# port name sanitised: / : \ become _   (provision.py:_state_path_for)
umask 077
cat > "$STATE_DIR/_dev_ttyACM0.json" <<'EOF'
{ "ssid": "YourSSID", "password": "YourPSK",
  "target_ip": "192.168.1.42", "target_port": 5005 }
EOF

python firmware/esp32-csi-node/provision.py --port /dev/ttyACM0   # no --password
```

**Be clear-eyed about what this buys you.** It keeps the PSK out of `/proc` and
out of shell history. It does **not** make it safe:

- the state file holds the PSK **in plaintext, indefinitely**, on the
  provisioning machine;
- `save_state` writes a temp file at default umask and `os.replace`s it over the
  target, so **a `chmod 600` you apply is reset to `0644` on the next run** —
  re-apply it, or keep `umask 077` set in the shell that runs the script;
- the PSK is still plaintext in device NVS either way.

Use a throwaway SSID/PSK, or a guest VLAN, for the trial. Delete the state file
afterwards: `shred -u "$STATE_DIR/_dev_ttyACM0.json"`.

## 5. Run the server

See [`RUN-LOCALLY.md`](RUN-LOCALLY.md) for the build. For the trial, force the
real source rather than letting `auto` fall back to the simulator — otherwise a
board that never connects looks like a working demo:

```bash
cd v2
export RUVIEW_API_TOKEN="$(openssl rand -hex 24)"   # SEC-004: auth is off without it
./target/release/sensing-server \
  --http-port 8080 --ui-path ../ui --source esp32 --udp-port 5005
```

Confirm frames are actually arriving **before** you start breathing at anything:

```bash
curl -s -H "Authorization: Bearer $RUVIEW_API_TOKEN" \
  localhost:8080/api/v1/status | jq .source          # must be "esp32", NOT "simulated"
curl -s -H "Authorization: Bearer $RUVIEW_API_TOKEN" \
  localhost:8080/api/v1/nodes  | jq                  # node should appear
```

**If `source` reads `simulated`, stop.** You are measuring the simulator, and
every number after that point is meaningless. That is the single easiest way to
fool yourself in this trial.

## 6. The measurements

Node ~2 m away, line of sight, you seated and still. Pace your breathing with a
metronome — 10 BPM is one full breath every 6 s, 20 BPM every 3 s. Sixty seconds
per run, and record what the API reports rather than what the dashboard animates.

```bash
watch -n2 'curl -s -H "Authorization: Bearer '"$RUVIEW_API_TOKEN"'" \
  localhost:8080/api/v1/sensing/latest | jq "{source, classification, features}"'
```

| # | Condition | Expected if the DSP is real |
|---|---|---|
| A | Paced **10 BPM**, 60 s | recovered rate **10 ± 2** |
| B | Paced **20 BPM**, 60 s | recovered rate **20 ± 2** |
| C | **Empty room**, 60 s, nobody present | `None`, or confidence **< 0.3** |
| D | Seated, holding breath 30 s | rate decays or confidence drops |

### Pass / fail — decide this before you run it

- **PASS** = A and B both land within ±2 BPM, **and** C returns nothing
  confident.
- **FAIL** = neither A nor B tracks, **or** C reports a confident rate for an
  empty room.

**C is the load-bearing half.** A detector that follows your breathing but also
reports 14 BPM for an empty room has told you nothing — it is responding to
ambient multipath, not to you. This is the C4 null test repeated against physical
reality, and it is the reason this trial is worth doing at all rather than just
trusting the synthetic result.

Run C **first**, before you have seen a good number from A or B. It is much harder
to talk yourself out of a bad null result you have not yet motivated.

## 7. What a pass would license

A pass justifies **further R&D on presence and breathing** — a second node,
different rooms, different distances, a real multipath environment.

It does **not** license:

- a client pitch or a demo presented as product capability (R1, SEC-003, SEC-004);
- anything safety-adjacent — fall detection, confined-space, vitals monitoring
  (SEC-005 fail-silent, SEC-006 fabricated-from-noise);
- any vital-signs deployment in an EU workplace without an Art. 9 legal basis and
  a DPIA (see `../RECOMMENDATION.md`).

A fail is equally informative and much cheaper than finding out later: it would
mean the synthetic C4 result does not transfer to real CSI, and that the whole
platform rests on nothing you can use.

## 8. Record the result

Whatever happens, write the four numbers and the board/firmware version into
`docs/spec/evidence/hardware/` and update the claim matrix. If it passes, that is
the first `MEASURED` hardware evidence in this audit. If it fails, that is a
finding worth more than any of the source reading.
