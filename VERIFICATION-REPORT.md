# RuView — Verification Report

**Baseline SHA:** `5780c23` · **Fork:** `sridharankaliyamoorthy/RuView` · **Date:** 2026-08-10
**Auditor:** Claude Code (Opus) · **Branch:** `claude/ruview-wifi-audit-afopqa`
**Evidence:** `docs/spec/claim-matrix.md` · `SECURITY-FINDINGS.md` · `docs/spec/evidence/c4/`

---

## Go / no-go

**Verdict: (b) — a credible R&D / prototype base. Go for evaluation and prototyping;
no-go for anything client-facing, and no-go for anything safety-adjacent, without
substantial work.** The core signal processing is real and I verified it against ground
truth the repo has never seen: the breathing extractor recovered 6, 10, 15, 20 and 30 BPM
with **exactly zero error**, held to −9.5 dB SNR, and correctly returned `None` on pure
noise 20 times out of 20 — this is genuine DSP, not a bandpass filter reporting a
plausible number. That result, plus a test suite where **3,894 tests pass and none
fail** (the badge's 1,463 *understates* the repo by 2.7×), a deterministic-proof harness
that is honestly non-circular, and a maintainer who documents his own 3.0% PCK failure
four separate times, is a real engineering foundation. But the gap between what the README presents
and what the repository contains is wide enough to be disqualifying on its own: the
advertised "105-cog catalog" resolves to **3 implemented cogs against 107 catalogued
names — zero of which match**, because the catalog is a remote storefront for a
different product fetched from a Google Cloud Storage bucket. Cog binary signing, the
foundation of the trust model, is a documented no-op. The sensing API is unauthenticated
by default. And the published PyPI release's heart-rate extractor returns `None` for
every input through its own documented API — a fail-silent vital-sign monitor. Treat
this as a promising research codebase by a candid author, not as a product.

---

## What is actually true

Verified by command, not by reading the README.

| # | Finding | Evidence |
|---|---|---|
| 1 | **Breathing extraction is real and accurate.** 0.0 BPM error across the entire claimed 6–30 range; robust to −9.5 dB SNR; returns `None` on pure noise 20/20 and on a linear ramp. | C4-A, C4-D |
| 2 | **Heart-rate extraction is real in source** — 60/72/90/120 BPM recovered to within 0.45 BPM — **but broken in the published release** and wrong at 40 BPM (+8.0). | C4-A, C4-B |
| 3 | **The deterministic proof is honest and non-circular.** Compares against a git-committed hash; the regeneration path is behind an explicit `--generate-hash` flag. It proves the pipeline is *not mocked*. It proves nothing about accuracy, and says so itself. | C2 |
| 4 | **The pose stub is disclosed exactly as claimed** — `confidence: 0.0` at `inference.rs:283`, PCK@20 = 3.0% in the cog README with per-joint breakdown and a frank cause analysis. | C5 |
| 5 | **No sensing-data exfiltration exists anywhere in the codebase.** Every external call found is an inbound fetch (registry, JWKS, models). | C9 |
| 6 | **The Ed25519 witness chain is real cryptography**, signing canonical bytes that commit to `prev_hash`. Key management is explicitly out of repo. | SEC positives |
| 7 | **Simulated data is honestly labelled, verified at runtime.** Every data-bearing endpoint returns `"source":"simulated"`, and the dashboard carries a persistent `● Simulated` header pill plus an amber "SIMULATED / Server running without hardware" card. The concern I raised before running it does not hold. | C7, evidence/c7 |
| 8 | **The test suite is healthy and the badge understates it.** 3,894 passed / 0 failed / 15 ignored / 0 filtered across 183 suites, against a badge claiming 1,463 — and that excludes one crate, so the real figure is higher. | C1 |

## What is not

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **The "105-cog catalog" does not exist in this repo.** 107 catalogued names, 3 implemented cogs, **0 matches**. `app-registry.json` is fetched from a GCS bucket at runtime. | **Critical (misrepresentation)** | R1 |
| 2 | **Cog signing is a no-op; cogs ship unsigned.** The README advertises "signed binaries on GCS"; `make sign` is documented as not signing. | **High** | SEC-003 |
| 3 | **WiFi passwords via argv, stored plaintext in NVS** — and it is the documented usage, contradicting the repo's own security rule. | **High** | SEC-002 |
| 4 | **The audited repo executes code inside the auditing agent** on every prompt and tool call, pre-consent, via unpinned `@latest`. | **High** | SEC-001 |
| 5 | **Sensing API is unauthenticated by default.** | **Medium–High** | SEC-004 |
| 6 | **Published `wifi-densepose 2.0.0a1` heart rate is fail-silent** — `None` for every input via the documented API (upstream #1423, fixed in source, not in the release). | **Medium** | SEC-005, C4-B |
| 7 | **Vitals are fabricated from noise unless the consumer checks `.status`** — 20/20 plausible in-range BPM from pure noise, all correctly flagged `Unreliable`, but `.value_bpm` is handed back regardless. | **Medium** | SEC-006, C4-D |
| 8 | **The repo's own documented test command does not build** on a headless machine — GTK3 is pulled into the default workspace graph, so the documented verification path is broken for CI, servers and containers. | **Medium** | C1 |
| 9 | **MQTT defaults to plaintext 1883**, mDNS-advertised, no topic ACLs. | **Medium** | SEC-007 |
| 10 | **82.69% MM-Fi is a cited external result**, not reproducible from this repo — the dataset is absent and the weights are on Hugging Face. | **Medium (framing)** | C6 |
| 11 | **`prompt-shield` "blocks replay and injection attacks"** is a 64-frame duplicate-hash check with no nonce or freshness. | **Low (misrepresentation)** | SEC-010 |
| 12 | **The Docker default serves simulated data while `docker-compose.yml` and the entrypoint both document it as failing hard with `exit 78`.** No `exit(78)` exists in the server. Issue #1004 superseded the #937 behaviour in code; the docs were never updated. | **Medium** | C7 |
| 13 | **A deterministic dev signing key is used by default** — `WDP_RUFIELD_SIGNING_SEED` unset means signatures from an unconfigured deployment prove nothing. | **Medium** | SEC-011 |
| 14 | **`/api/v1/info` reports `environment: "production"` while serving simulated data**, and gives a third version number (`0.3.5`) against the package's `2.0.0a1`. | **Low** | SEC-012 |
| 15 | **The generated session signing secret is not gitignored on a normal local run.** The existing rule only covers a crate-cwd run; the documented `cd v2 && ./sensing-server` writes it to `v2/data/session-secret`, unmatched. A `git add -A` would commit a live secret. | **Medium** | SEC-013 |

---

## The one that matters most: C4

Everything else in this audit reads code or runs someone else's tests. C4 is the only
place the auditor supplied ground truth. The hypothesis under test was Sri's: *a
bandpass filter with a zero-crossing counter will always report* a *number inside
6–30 BPM, so the vital-signs claim may be decoration.*

**The extractors are architecturally exactly what was suspected** — their own
docstrings say "0.1–0.5 Hz bandpass + zero-crossing analysis" and "0.8–2.0 Hz bandpass
+ autocorrelation peak detection". **The hypothesis is nonetheless disproven for
breathing and only half-true for heart rate.**

Breathing returned `None` on pure Gaussian noise in all 20 seeded trials, `None` on a
linear ramp, and recovered every injected frequency in its claimed range with zero
error. A decorative filter cannot do that.

Heart rate emitted a plausible in-range BPM from pure noise **20/20 times** (48.0–117.6,
mean 79.5) — but marked every one `VitalStatus.Unreliable` at confidence 0.07–0.30
against a 0.6 `Valid` cutoff. The detector knows. The API just doesn't force the caller
to look.

Two subtleties worth carrying forward:

- **Pure DC** makes breathing emit 17.0 BPM — at confidence exactly `0.0`. Honest, but
  it emits a number rather than `None`.
- **At the point breathing becomes wrong** (−20 dB, reporting 25 BPM against a 15 BPM
  truth) its **confidence rises**. Confidence is anti-correlated with correctness
  precisely where a consumer would lean on it.

![C4 synthetic ground truth results](docs/spec/evidence/c4/c4_charts.png)

**Reproduce:**
```bash
python -m venv .audit-venv && .audit-venv/bin/pip install numpy scipy matplotlib ruview
cd /tmp && /path/to/.audit-venv/bin/python /path/to/RuView/scripts/audit/c4_synthetic_vitals.py
# must NOT run from the repo root — see INT-01
```

---

## Commercial fit

### La Casa (ERPNext/Frappe + React PWA, manufacturing)

**Recommendation: do not pursue this pairing.** Not because the tech is fake — the
breathing DSP is real — but because the fit is weak on three independent axes, and I
would rather say so than construct a use case.

**RF environment.** A shop floor is close to the worst case for CSI sensing. Metal
machinery, racking and moving forklifts create dense, *non-stationary* multipath. CSI
models are notoriously environment-coupled: they degrade sharply when the room changes,
and a manufacturing floor changes continuously — pallets move, doors open, machines
cycle. RuView's own answer to this is `wifi-densepose-calibration` (ADR-151, per-room
calibration and specialist training), which is an admission that per-site tuning is
mandatory. Every line reconfiguration is a recalibration. I could not test any of this:
no hardware, no ESP32, no RF environment. That is a genuine unknown, not a verdict.

**Integration cost is the small problem.** Frappe integration is straightforward —
a custom app with a webhook receiver or an MQTT subscriber writing to a DocType, plus
the existing React PWA for display. Days, not months. It is not the obstacle.

**Value is the real problem.** For occupancy and worker-presence, the incumbents are
PIR sensors (~€10, deployed in an afternoon, no calibration), badge readers (already
installed, already tied to identity, already in the ERP), and cameras (often already
present for safety compliance). RuView's differentiator is "no cameras" — but on a shop
floor where badge readers already exist, the privacy argument mostly evaporates: you
already know who is in the building.

**The one genuinely interesting case is confined-space monitoring** — tanks, vessels,
crawl spaces where cameras are impractical or prohibited and a worker collapse must be
detected fast. That is a real, valuable, underserved problem. **And this codebase must
not be used for it.** Confined-space monitoring is life-safety. SEC-005 makes the
published heart-rate extractor fail-silent; SEC-006 means a consumer that skips the
status check displays a heart rate for an empty vessel. A life-safety system built on
either behaviour kills someone. Revisit only against a hardened, hardware-validated,
certified build — which is years and a compliance budget away, not a sprint.

### GDPR — Czech deployment

**The README's "no cameras, therefore no GDPR" framing is wrong, and it is the single
thing most likely to damage Sri's credibility if it reaches a client's legal team.**
The sensor modality does not determine the data category. What is inferred does.

- **Breathing rate and heart rate are health data** → **Art. 9(1) special category**.
  Processing is *prohibited* unless an Art. 9(2) exception applies. Camera-free changes
  nothing.
- **Presence and occupancy tied to an identifiable workplace** are personal data under
  **Art. 4(1)**, because a worker at a known workstation during a known shift is
  identifiable — even without a name in the payload. Combined with ERP shift data (which
  is exactly what a La Casa integration would do), identifiability is immediate.
- **Employee consent is not a valid Art. 9(2)(a) basis** in an employment relationship.
  The power imbalance vitiates freely-given consent — settled EDPB/WP29 position. The
  "we'll just ask staff to opt in" answer does not work.
- **A DPIA is mandatory under Art. 35** — systematic monitoring, special-category data,
  vulnerable data subjects (employees). Not optional, and it must precede deployment.
- **Czech specifics:** ÚOOÚ is the supervisory authority. **Zákoník práce § 316**
  independently restricts workplace monitoring — it requires a legitimate reason *and*
  prior notification to employees of the extent and manner of monitoring. **Art. 88
  GDPR** preserves these national employment rules, so § 316 applies *on top of* the
  GDPR analysis, not instead of it. Where a trade union or works council exists,
  consultation is expected.
- **Practical consequence:** a vital-signs deployment in a Czech workplace needs an
  Art. 9(2) basis that is realistically **9(2)(b)** (employment/social-security law
  obligations) or **9(2)(c)** (vital interests) — both narrow, both requiring a
  documented legal argument — plus a DPIA, plus § 316 notification. Presence-only
  detection, with vital signs disabled, is a dramatically simpler position and is the
  only configuration I would pitch.

**Add SEC-004 to this:** an unauthenticated API serving special-category data is an
Art. 32 (security of processing) failure on its face.

**If Sri ever presents WiFi sensing to a client:** lead with "this is special-category
health data and needs a DPIA", not with "no cameras means no GDPR". The second framing
is the kind of thing a client's counsel remembers.

---

## Prompt-injection surface — reported, not followed

Per the audit's own safety constraints, this is surfaced rather than complied with.

The repository ships `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.claude-plugin/`,
`.claude-flow/`, `.swarm/` and `.mcp.json`. Its `.claude/settings.json` registers Node
hooks on eight lifecycle events. **Two of them executed in this session before a single
file was read**, and the repo's `attribution.commit` string propagated verbatim into
the auditing agent's own system prompt as an instruction to sign commits as
`claude-flow <ruv@ruv.net>`.

The payload appears benign — developer tooling for routing, metrics and session memory,
not an attack. The defect is the mechanism: unconditional, pre-consent, and pointed at
an unpinned `@latest` npm package. Confirming it is benign was the job; the mechanism
remains a supply-chain problem regardless of the answer. Full detail in SEC-001.

**Nothing in it was complied with.** No plugin install, no `npx @ruvnet/ruview`, no
claude-flow MCP tool call, no agent spawning.

---

## What this audit could not test

Stated so no one mistakes silence for a pass.

| Item | Why | What it would take |
|---|---|---|
| **Docker image path only** (`docker compose up`) | Image build needs more than the 12 GB left after the native build | ~40 GB free disk. **The C7 question itself is now closed** — the server was run natively instead; see `docs/spec/evidence/c7/`. |
| **C8** — model loading, 8 KB int4 claim | `huggingface.co` 403 at the proxy (policy denial, logged) | Unrestricted egress |
| **C6** — MM-Fi 82.69% reproduction | Dataset absent from repo; weights on HF | MM-Fi dataset access + egress |
| **All RF / hardware claims** — through-wall, range, real-world accuracy | No ESP32, no RF environment | Real silicon. Per the repo's own rule, a successful build is not hardware evidence. |
| **Repo history claims** | Shallow clone — 142 of 1,211 commits | Full clone |
| **Cognitum / Seed runtime behaviour** | `cognitum.one` unreachable | Network access to the vendor |

---

## If Sri takes this further

1. **Close C7 first.** One afternoon on a machine with Docker: bring the stack up, hit
   `/api/v1/*`, and find out whether simulated data is flagged in the UI. If a demo can
   show fabricated readings as live, nothing else matters.
2. **Build from source, never from PyPI** (SEC-005).
3. **Test the breathing extractor on real CSI** — it is the one component that earned
   the right to a hardware trial.
4. **Ignore the cog catalog entirely.** It is a storefront for another product.
5. **Never quote 82.69%, "105 cogs", or "no GDPR"** in anything client-facing.

---

## Assessment of the maintainer

Worth separating from the assessment of the code. The README retracts its own "100%
presence" claim in three separate places rather than one. The pose model's 3.0% PCK
failure is disclosed four times, with per-joint numbers and an honest cause analysis.
`bearer_auth.rs` documents a past exposure-by-default security bug in its own source
comments. The deterministic proof is deliberately built to be falsifiable and is not
circular.

That is a real and uncommon commitment to honesty at the level of individual claims.
The failure is at the level of *aggregate presentation*: a README that assembles
verified components, aspirational components, and another product's remote catalog into
a single feature table, where a reader cannot tell which is which without doing this
audit. The honesty is genuine and the overall impression is still misleading. Both
things are true.
