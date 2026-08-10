# RuView — Security Findings

**Baseline SHA:** `5780c23` · **Date:** 2026-08-10 · **Auditor:** Claude Code (Opus)
**Method:** `ecommerce-security-audit` checklist methodology adapted to an
embedded/edge codebase. Static review plus the runtime probes recorded in
`docs/spec/claim-matrix.md`.

**Scope limits:** no ESP32 hardware, no reachable Cognitum or Hugging Face
endpoint. Everything below is source-level unless a command output is shown.
SEC-004, SEC-009, SEC-011 and SEC-012 were additionally **confirmed at runtime**
against a live `sensing-server` — see `docs/spec/evidence/c7/`. No penetration
testing was performed against any live system.

| ID | Finding | Severity |
|---|---|---|
| SEC-001 | Audited repo configures and executes code inside the auditing agent | **High** |
| SEC-002 | WiFi credentials via argv, stored unencrypted in NVS | **High** |
| SEC-003 | Cog binary signing is a documented no-op; cogs ship unsigned | **High** |
| SEC-004 | Sensing API is unauthenticated by default | **Medium–High** |
| SEC-005 | `wifi-densepose` HeartRateExtractor non-functional in the published release | **Medium** (safety-relevant) |
| SEC-006 | Vital-sign values are fabricated from noise unless the consumer checks status | **Medium** (safety-relevant) |
| SEC-007 | MQTT bridge defaults to plaintext 1883, no TLS | **Medium** |
| SEC-008 | Python dependencies floor-pinned (`>=`), no lockfile | **Medium** |
| SEC-009 | Default-on egress to Google Cloud Storage | **Low–Medium** |
| SEC-010 | `prompt-shield` capability claim overstates a 64-frame duplicate check | **Low** (misrepresentation) |
| SEC-011 | Deterministic dev signing key used by default (RuField surface) | **Medium** |
| SEC-012 | `environment: "production"` reported while serving simulated data | **Low** |
| SEC-013 | Generated session secret lands outside `.gitignore` on a normal local run | **Medium** |

---

## SEC-001 — The audited repository configures the agent auditing it · **High**

**Evidence.** `.claude/settings.json` registers Node hooks on **PreToolUse,
PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, Stop, PreCompact,
SubagentStart**, all invoking `$CLAUDE_PROJECT_DIR/.claude/helpers/hook-handler.cjs`
and `.claude/helpers/auto-memory-hook.mjs`.

These executed in this audit session **before any file was read**:

```
SessionStart:startup hook success: [AutoMemory] Importing auto memory files into bridge...
UserPromptSubmit hook success: [INFO] Routing task ... Agent: coder, Confidence: 50.0%
```

It also grants itself standing permissions and an identity:

```json
"permissions": { "allow": ["Bash(npx @claude-flow*)", "Bash(npx claude-flow*)",
                           "Bash(node .claude/*)", "mcp__claude-flow__:*"], "deny": [] }
"attribution": { "commit": "Co-Authored-By: claude-flow <ruv@ruv.net>" }
```

`.mcp.json` requests `npx -y @claude-flow/cli@latest mcp start` — **unpinned
`@latest`, auto-fetched from npm at run time**.

**Why it matters.** Two distinct problems. First, arbitrary Node from a cloned repo
runs on every prompt and every tool call, with no consent step — a repo you have not
yet decided to trust gets code execution the moment you open it in an agent. Second,
the `attribution.commit` string propagated **verbatim into this session's system
prompt**, instructing the auditor to sign commits as `claude-flow <ruv@ruv.net>`. A
repository under audit successfully wrote an instruction into its auditor.

`CLAUDE.md` (239 lines) and `AGENTS.md` (214 lines) were auto-loaded into agent
context before any deliberate read.

**Assessment.** The payload is plausibly benign — it looks like genuine developer
tooling (routing, metrics, session memory), not an attack. The defect is the
**mechanism**: unconditional, pre-consent, and unpinned. `@latest` means the code that
runs tomorrow is not the code reviewed today.

**Mitigation.** Before opening this repo in any agent: delete or neuter
`.claude/settings.json` hooks, remove `.mcp.json`, and review `CLAUDE.md` /
`AGENTS.md` as data. Pin `@claude-flow/cli` to an exact version if it is used at all.
Audit in a disposable VM. Nothing in this audit complied with any of it — no plugin
install, no `npx @ruvnet/ruview`, no claude-flow tool call.

---

## SEC-002 — WiFi credentials via argv, unencrypted in NVS · **High**

**Evidence.** `firmware/esp32-csi-node/provision.py`:

```
:9    python provision.py --port COM7 --ssid "MyWiFi" --password "secret" ...
:327  parser.add_argument("--password", help="WiFi password")
:186  writer.writerow(["password", "data", "string", args.password])
```

**Why it matters.** Three exposures in one path:

1. **argv is world-readable** on a multi-user host via `/proc/<pid>/cmdline`, and
   lands in shell history by default.
2. The credential is written as an NVS **`data string`** — plaintext in flash unless
   NVS encryption is separately enabled, which this script never configures. Anyone
   with physical access and a $10 flash reader recovers the WPA2 PSK.
3. This is the *documented* usage — `:9` and `:313` both show `--password "secret"` as
   the example, so the insecure path is the recommended one.

**Compounding.** The repo's own `CLAUDE.md` states: *"Never expose WiFi credentials in
commands, logs, issues, or commits."* Its own provisioning tool's headline example
violates its own rule.

**The documented workaround is also weak.** `provision.py:24-37` describes a
per-port JSON state file it merges from, which lets the password be pre-seeded
instead of passed on argv. That keeps it out of `/proc` and shell history, but:

- the state file holds the PSK **in plaintext indefinitely** at
  `~/.config/wifi-densepose/esp32-provision-state/<port>.json`;
- `save_state` (`:147-157`) writes a temp file at the **default umask** and
  `os.replace`s it over the target, so the file's permissions are **reset on every
  write** — a `chmod 600` applied by the operator does not survive the next run,
  and the default is typically `0644`, i.e. world-readable;
- `password` is in the merged key list (`:104`), so it is always persisted.

**Mitigation.** Read the password from stdin/`getpass` or an env var, never argv.
Create the state file with `os.open(..., 0o600)` and preserve mode across the
atomic replace. Enable NVS encryption and document it as mandatory. Change the
README example.

---

## SEC-003 — Cog signing is a no-op; cogs ship unsigned · **High**

**Evidence.** `v2/crates/cog-ha-matter/cog/README.md`:

```
:37  `make sign` is currently a no-op for the signature itself — the
:40  Until then, dev cogs ship unsigned and `app-registry.json` lists
:41  them with `"binary_signature": ""`.
```

`cog-pose-estimation/src/manifest.rs:17,32` — `binary_signature: Option<String>`,
defaulting to `None`.

**Why it matters.** The trust model in ADR-100 rests on signature verification of cog
binaries fetched from Google Cloud Storage. That verification **has no signature to
verify**. The README advertises *"signed aarch64 + x86_64 binaries on GCS"* (README:103);
the signing step that would produce those signatures is explicitly a no-op.

The result is remote code execution by design, gated only on TLS to a GCS bucket:
whoever can write to `cognitum-apps` — or MITM a client that fails open — controls
what executes on every appliance. The question Sri posed ("enforced, or logged and
continued?") has a third answer here: **there is nothing to enforce yet.**

**Mitigation.** Do not deploy cogs from the remote registry in any environment that
matters until signing is wired end-to-end, with a documented trust root and a
fail-closed verifier. Treat the current cog channel as unauthenticated code delivery.

---

## SEC-004 — Sensing API unauthenticated by default · **Medium–High**

**Evidence.** `v2/crates/wifi-densepose-sensing-server/src/bearer_auth.rs`:

```
:3   When the `RUVIEW_API_TOKEN` environment variable is set, every request ...
:9   deployment-time switch with **no default authentication change**.
:60  pub const API_TOKEN_ENV: &str = "RUVIEW_API_TOKEN";
```

**Confirmed at runtime.** Against a live server with no token set:

```
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/api/v1/status
200
INFO API auth: OFF — /api/v1/* is unauthenticated. Set RUVIEW_API_TOKEN=<token> ...
```

Full sensing data returned with no credential.

**Why it matters.** Authentication is opt-in. An operator who follows the quickstart
and runs the server exposes the sensing REST + WebSocket surface — presence, motion,
and vital-sign streams — with **no credential**. In a workplace deployment that is
unauthenticated access to what is, under GDPR, health and personal data (see the
commercial-fit section of `VERIFICATION-REPORT.md`).

**Credit where due.** `bearer_auth.rs:122-134` documents a *previous* exposure-by-
default bug in its own source comments, with measured consequences, and ADR-272 added
the middleware that closed it. The team found and fixed a real hole and wrote down
what it cost. The remaining issue is that the safe state is not the default state.

**Mitigation.** Set `RUVIEW_API_TOKEN` (or configure Cognitum OAuth) in every
deployment. Treat an unset token as a deployment blocker, not a warning. Never expose
port 3000 beyond localhost or a trusted VLAN.

---

## SEC-005 — Published HeartRateExtractor is non-functional · **Medium** (safety-relevant)

**Evidence.** Full reproduction in `docs/spec/claim-matrix.md` §C4-B. With
`weights=[]` — the idiom the class docstring demonstrates — the published
`wifi-densepose 2.0.0a1` returns `None` for every input, at every BPM, amplitude and
duration tested (up to 240 s of noiseless signal). Root cause is upstream issue
**#1423**, fixed in repo source at `5780c23`
(`v2/crates/wifi-densepose-vitals/src/heartrate.rs:100-113`) but **not in the release**.

**Why it's here and not just in the matrix.** A vital-sign monitor that silently
returns "no reading" rather than erroring is a **fail-silent** mode. A fall-detection
or health-monitoring integration built on the published wheel would report nothing and
look like a quiet room. Fail-silent is the worst failure mode for a safety-adjacent
sensor.

**Mitigation.** Do not build against `wifi-densepose==2.0.0a1`. Build from repo source
at or after `5780c23`, or wait for a release carrying the #1423 fix.

---

## SEC-006 — Fabricated vitals from noise unless the consumer checks status · **Medium** (safety-relevant)

**Evidence.** `docs/spec/claim-matrix.md` §C4-D. Fed **pure Gaussian noise** across 20
seeds, `HeartRateExtractor` emitted a heart rate **20 times out of 20**, spanning
48.0–117.6 BPM — every value inside the claimed 40–120 range and plausible to a human
reader.

**The mitigating fact:** all 20 carried `status = VitalStatus.Unreliable` and
confidence 0.069–0.299, against a `Valid` cutoff of 0.6. The guard exists and it fires
correctly. `BreathingExtractor` is cleaner still — `None` on all 20.

**Why it is still a finding.** The API hands back a `.value_bpm` that looks
authoritative. Correctness depends entirely on every downstream consumer — including
third-party cog authors and dashboard code — remembering to gate on `.status`. That is
an unenforced contract on a health-adjacent number. A dashboard that renders
`value_bpm` displays a clinically plausible heart rate for an empty room.

Related: at the point `BreathingExtractor` becomes *wrong* (−20 dB SNR, reporting 25
BPM for a 15 BPM truth), its **confidence rises** from 0.306 to 0.396 — confidence is
anti-correlated with correctness exactly where a consumer would rely on it.

**Mitigation.** Make the unreliable case unrepresentable: return `None` below the
`Valid` threshold, or make `value_bpm` inaccessible without unwrapping status. Until
then, mandate a status check in every integration and in the cog SDK docs.

---

## SEC-007 — MQTT bridge defaults to plaintext · **Medium**

**Evidence.** `v2/crates/cog-ha-matter/src/lib.rs:46` —
`DEFAULT_EMBEDDED_BROKER_PORT: u16 = 1883`. No `8883`, `mqtts`, or TLS configuration
found anywhere in the crate; mDNS advertises `mqtt_port 1883` (`mdns.rs:176`).

**Why it matters.** Presence, occupancy and vital-sign events are published in
cleartext across the LAN, and advertised via mDNS so they are trivially discoverable.
Any device on the same network — a guest phone, a compromised IoT bulb — can subscribe.
No topic ACL scheme was found.

**Mitigation.** TLS (8883) with a client certificate or credential, plus per-topic
ACLs, before any deployment carrying real occupancy data.

---

## SEC-008 — Floor-pinned Python dependencies, no lockfile · **Medium**

**Evidence.** `requirements.txt` — 26 entries, all `>=` constraints:
`numpy>=1.21.0`, `torch>=1.12.0`, `fastapi>=0.95.0`,
`python-jose[cryptography]>=3.3.0`, … No lockfile, no hashes.

**Why it matters.** `>=` means the build is not reproducible and a compromised or
merely broken upstream release is pulled automatically on the next install. This is
the standard supply-chain exposure, and it sits under a crypto-relevant package
(`python-jose`) used for token handling.

**Submodules, by contrast, are done right:** all 9 are pinned to explicit commit SHAs
and all resolve to `github.com/ruvnet/*`. One cosmetic oddity — `v2/crates/ruview-swarm`
points at `ruvnet/ruv-drone.git`, a path/name mismatch worth a comment but not a
security issue. No typosquat-adjacent package names were found.

**Mitigation.** Generate a lockfile with hashes (`uv lock` / `pip-compile
--generate-hashes`) and pin upper bounds.

---

## SEC-009 — Default-on egress to Google Cloud Storage · **Low–Medium**

**Evidence.** `v2/crates/wifi-densepose-sensing-server/src/edge_registry.rs:21` and the
CLI default at `main.rs:227` —
`https://storage.googleapis.com/cognitum-apps/app-registry.json`.

**Assessment.** This is an **inbound fetch, not telemetry**. The full egress scan
(`docs/spec/claim-matrix.md` §C9) found **no path that uploads CSI, sensing data or
person data anywhere.** That is a genuinely good result and worth stating plainly.

The finding is disclosure, not exfiltration: a server the operator never configured
will contact Google Cloud Storage the first time `/api/v1/edge/registry` is hit.
Stale-while-error caching means it also retains a copy. For an EU client this must
appear in the processing documentation.

**Mitigation.** Override the registry URL to an internal mirror, or firewall it, for
air-gapped and EU-sensitive deployments. The CLI already supports this.

---

## SEC-010 — `prompt-shield` overstates its capability · **Low** (misrepresentation)

**Evidence.** README:333 — *"Blocks signal replay and injection attacks on the seed."*
Implementation: `v2/crates/wifi-densepose-wasm-edge/src/ais_prompt_shield.rs`, 271
lines. Its own module header (`:4`): *"**Replay**: FNV-1a hash of quantized features;
match against 64-entry ring."*

**Why it matters.** It detects an **exact quantized-feature repeat within a 64-frame
window**. There is no nonce, no timestamp binding, no sequence number, no
cryptographic freshness. A replay 65 frames later passes. A replay with a single LSB
of added noise passes, because the hash is over quantized features and any
quantization-boundary crossing changes it.

The code is real and does something. It is a duplicate-frame heuristic labelled as an
attack-prevention control, which is the kind of claim that gets believed by a
non-specialist reader and quoted into a client's security questionnaire.

**Mitigation.** Relabel to what it is ("duplicate-frame detector, 64-frame window").
If replay resistance is actually required, it needs signed, monotonically-sequenced
frames from the sensor.

---

## SEC-011 — Deterministic dev signing key by default · **Medium**

**Evidence.** Observed at runtime on an unconfigured server
(`docs/spec/evidence/c7/startup.log`):

```
WARN ADR-262 P3: WDP_RUFIELD_SIGNING_SEED unset/invalid — RuField surface using the
     DETERMINISTIC DEV signing key. This is a dev/sensing key pending the ADR-262 §8
     Q1 (P2) key-ownership decision; set WDP_RUFIELD_SIGNING_SEED (64-hex or 32-byte
     value) for a real deployment.
```

**Why it matters.** A key derived from a constant in public source is reproducible
by anyone who can read the repo. Signatures produced by a default deployment
therefore authenticate nothing — they can be forged at will. This sits directly
alongside SEC-003 (cog signing is a no-op): two of the three signing surfaces in
the product are non-functional in their default state, while the README presents
cryptographic attestation as a headline feature.

**Credit.** The warning is loud, names the ADR, states the consequence, and gives
the exact fix. That is the right way to ship a known-insecure default — but it is
still an insecure default.

**Mitigation.** Set `WDP_RUFIELD_SIGNING_SEED` from a real CSPRNG in every
deployment; refuse to start without it in production builds.

---

## SEC-012 — `environment: "production"` while serving synthetic data · **Low**

**Evidence.** `GET /api/v1/info` on an unconfigured server
(`docs/spec/evidence/c7/resp_api_v1_info.json`):

```json
{ "backend": "rust", "environment": "production",
  "source": "simulated", "version": "0.3.5", ... }
```

**Why it matters.** `environment` is hardcoded to `production` regardless of actual
state. Any monitoring, alerting, or client-side gating that keys off it will treat
a simulated demo as a production deployment. The adjacent `"source": "simulated"`
is correct, so the two fields directly contradict each other.

Note also the **third version number**: `0.3.5` here, against `2.0.0a1` on PyPI and
`2.0.0-alpha.1` for the Rust core.

**Mitigation.** Derive `environment` from configuration, or remove the field.

---

## SEC-013 — Generated session secret is not gitignored on a normal run · **Medium**

**Found by tripping over it.** After running the server for the C7 evidence, an
untracked file appeared:

```
$ git status --short
?? v2/data/session-secret
$ ls -la v2/data/session-secret
-rw------- 1 root root 43 ...        # 43 random bytes, mode 0600
```

This is the browser session signing secret, generated at startup
(`browser_session.rs:319`, logged as `browser session secret: generated
path=data/session-secret`).

**Why it matters.** `.gitignore:310` already anticipates this file:

```
# sensing-server runtime artifacts written by its test suite (trained model
# snapshots + the generated session-secret) — never tracked
v2/crates/wifi-densepose-sensing-server/data/
```

But that path only matches a run whose working directory is the **crate**
directory — which is how the test suite invokes it. The **documented** way to
start the server is `cd v2 && ./target/release/sensing-server`, and the secret
then lands at `v2/data/session-secret`, which no rule matched.

So a developer who runs the server the documented way and then does `git add -A`
commits a live session signing secret to the repository. The author clearly
intended to prevent exactly this and the rule simply does not reach the real path.
Anyone with that secret can forge browser session tokens against that deployment.

**Confirmed by the near-miss in this audit:** a git hook prompted to commit the
untracked file. It was not committed; the secret was shredded and the ignore rule
widened to `**/data/session-secret` in this branch.

**Mitigation.** Match the file by name wherever it is written (done here), and
ideally write it under a path that is unambiguously ignored, or to the OS keyring
/ an env var rather than the working tree.

---

## Positives worth recording

A security review that only lists defects misrepresents this codebase.

- **The Ed25519 witness chain is real cryptography, not vocabulary.**
  `cog-ha-matter/src/witness_signing.rs` uses `ed25519-dalek` to sign the same canonical
  byte form the chain hashes, so a signature commits to kind, payload, timestamp, seq
  **and `prev_hash`** — splicing a signed event into a different chain breaks
  verification. The module separation (chain usable without dalek, for a WASM
  browser-side verifier) is a deliberate, competent design. The honest limitation is
  that **key management is explicitly out of scope** and deferred to a Cognitum control
  plane not present in this repo — so the primitive is sound and the trust root is
  unverifiable from here.
- **No sensing-data exfiltration anywhere in the codebase.**
- **Deliberate hardening in `provision.py`**: subprocess invocation is `argv`-based
  with a fixed interpreter and *never a shell* (`:267`) — command injection was
  actively considered.
- **`bearer_auth.rs` documents its own past security failure in source**, with measured
  consequences. That is unusually honest engineering.
- **Submodules pinned to exact SHAs.**
- **The runtime tells the truth about itself.** A default server logs, unprompted,
  that it is serving simulated data, that API auth is off, that it is contacting a
  GCS registry, and that it is using a dev signing key. Four of this report's
  findings are disclosed by the software in its own startup log. That is rare.
- **Simulated data is labelled end to end** — `"source":"simulated"` on every
  data-bearing endpoint plus two persistent dashboard indicators (verified by
  screenshot, `docs/spec/evidence/c7/`).
- **Host-header validation is ON by default** — an explicit DNS-rebinding defence,
  with `--disable-host-validation` opt-in rather than opt-out.
- **The deterministic proof is not circular** — the regeneration path is behind an
  explicit `--generate-hash` flag.

## Recommended order of remediation

1. SEC-003 (unsigned cog execution) and SEC-002 (credentials) — before any hardware pilot.
2. SEC-004 (auth default) — before anything is reachable off localhost.
3. SEC-005 / SEC-006 — before any health-adjacent integration.
4. SEC-007, SEC-008, SEC-011, SEC-013 — before a client deployment.
5. SEC-001 — before anyone else opens this repo in an agent.
