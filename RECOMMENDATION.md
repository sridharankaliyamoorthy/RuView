# RuView — recommendation

**Baseline:** `5780c23` · **Date:** 2026-08-10 · **For:** Sri (Mr.RooT.ai)
**Basis:** [`VERIFICATION-REPORT.md`](VERIFICATION-REPORT.md) ·
[`SECURITY-FINDINGS.md`](SECURITY-FINDINGS.md) ·
[`docs/spec/claim-matrix.md`](docs/spec/claim-matrix.md)

Three decisions, in the order they matter.

---

## 1. No client work. Drop the La Casa pairing.

This is settled by evidence, not preference. Any one of the following surfaces
badly in a client's due diligence, and you would be the one holding it:

| | Finding |
|---|---|
| **R1** | The advertised "105-cog catalog" is **107 catalogued names against 3 implemented cogs, zero matching**. The catalog is a remote storefront for a different product, fetched from a Google Cloud Storage bucket at runtime. |
| **SEC-003** | Cog binary signing is a **documented no-op**. The README advertises "signed binaries on GCS"; `make sign` does not sign. That is unauthenticated remote code execution by design. |
| **SEC-004** | The sensing API is **unauthenticated by default** — confirmed live, HTTP 200 with no credential. |
| **SEC-005** | The published PyPI heart-rate extractor is **fail-silent**: `None` for every input via its own documented API. |

The GDPR framing compounds it. "No cameras, therefore no GDPR" is wrong —
breathing and heart rate are **Art. 9 special-category health data** regardless of
sensor modality, employee consent is not a valid basis in an employment context,
a **DPIA under Art. 35** is mandatory, and Czech **§ 316 Zákoníku práce** applies
on top via Art. 88. If that framing reaches a client's counsel, it costs you
credibility you cannot buy back.

**For La Casa specifically:** the integration is the easy part (a Frappe app with
a webhook receiver — days). The problems are that a shop floor is close to the
worst case for CSI sensing — dense non-stationary multipath off metal, racking and
moving forklifts, with the repo's own `wifi-densepose-calibration` (ADR-151)
conceding that per-site tuning is mandatory — and that PIR sensors, badge readers
and existing safety cameras already solve occupancy more cheaply. The one
genuinely interesting case, **confined-space monitoring**, is life-safety, and
SEC-005/SEC-006 disqualify this codebase for it outright.

## 2. Run exactly one experiment: breathing on real CSI.

One component earned a hardware trial. The `BreathingExtractor` recovered
**6, 10, 15, 20 and 30 BPM with zero error**, held to −9.5 dB SNR, and returned
`None` on pure Gaussian noise **20 times out of 20**. That is real DSP, and it is
the only claim in the repository that survived contact with ground truth it had
never seen (C4).

Protocol: **[`docs/HARDWARE-TRIAL.md`](docs/HARDWARE-TRIAL.md)**. Roughly €15 and
an afternoon. It tests one question and defines pass/fail in advance, including
an empty-room control — because a detector that tracks your breathing but also
reports a rate for an empty room has told you nothing.

Nothing else in the repo earned this. Pose is an honest 3.0% PCK stub (C5), heart
rate is broken in the release (SEC-005), the cog catalog is not here (R1), and
the 82.69% MM-Fi figure is a cited external result that cannot be reproduced from
this repository (C6).

## 3. The audit method is worth more to you than RuView is.

You are an OSVČ selling cybersecurity and AI engineering. What you now have is a
repeatable engagement — *verify an agent-generated codebase before you trust it* —
with a worked example attached and one technique that generalises to any AI or ML
claim:

> **Supply your own ground truth, then null-test the detector.**
> Everything else reads code or runs someone else's tests. Only this tells you
> whether a system knows the difference between signal and nothing.

That single move is what separated "the breathing extractor is real" from "the
heart-rate extractor emits a plausible number from pure noise 20/20 times". No
amount of code reading would have produced either conclusion.

**SEC-001 is a talk on its own.** A repository that ships `.claude/settings.json`,
`.mcp.json` and lifecycle hooks configured its own auditor: arbitrary Node
executed on every prompt and tool call before a single file was read, and the
repo's `attribution.commit` string propagated **verbatim into the auditing agent's
system prompt**. The payload was benign. The mechanism was not consented to. As
more codebases become agent-generated and agent-audited, that is a supply-chain
category most people have not thought about yet.

---

## What is genuinely good here

Worth stating, because a recommendation that only lists defects misrepresents the
work and would be poor evidence if you ever discuss it publicly.

- The **breathing DSP is real** and behaves correctly at the noise floor.
- **3,894 tests pass, none fail.** The badge claiming 1,463 *understates* the repo
  by 2.7×.
- The **deterministic proof is not circular** — it compares against a committed
  hash, with regeneration behind an explicit flag, and its own docstring correctly
  scopes it as a mock-detector rather than a benchmark.
- The maintainer **discloses his own 3.0% PCK failure four separate times**,
  retracts a "100% presence" claim in three places, and documents a past
  exposure-by-default security bug in his own source comments.
- The **Ed25519 witness chain is real cryptography**, not vocabulary.
- **No sensing-data exfiltration exists anywhere in the codebase.**
- The **running server discloses four of this audit's findings in its own startup
  log**, unprompted.

The failure is not dishonesty. It is *aggregate presentation*: a README that
assembles verified components, aspirational components and another product's
remote catalog into one feature table, where a reader cannot tell which is which
without doing this audit.

## If you take nothing else from this

Do not quote **"105 cogs"**, **"82.69%"**, or **"no cameras, no GDPR"** in
anything client-facing. Those three are the ones that would not survive scrutiny.
