#!/usr/bin/env python3
"""
C4 — Synthetic ground-truth verification of RuView's vital-sign extractors.

This is the only test in the audit where WE supply the ground truth. Everything
else reads the repo's code or runs the repo's own test suite; here we generate a
CSI-shaped signal containing a frequency we chose, and ask whether the shipped
DSP recovers it.

Under test (from `pip install ruview` -> wifi_densepose 2.0.0a1, Rust core
2.0.0-alpha.1):
  BreathingExtractor  — documented as 0.1-0.5 Hz bandpass + zero-crossing
  HeartRateExtractor  — documented as 0.8-2.0 Hz bandpass + autocorrelation

Four questions, in increasing order of how much they matter:
  1. Does it recover a known frequency?          (accuracy)
  2. Does it hold across the claimed range?      (sweep)
  3. Where does it break as SNR falls?           (noise floor)
  4. Does it invent a plausible BPM from signal  (NULL TESTS — decisive)
     that contains none at all?

A bandpass filter plus a zero-crossing counter will always emit *a* number
inside the claimed range. Q4 is what separates real estimation from decoration.

Usage:  python scripts/audit/c4_synthetic_vitals.py [--outdir DIR]

IMPORTANT: must not be run with CWD=repo root — the repo ships a
`wifi_densepose/` v1.2.0 stub at the root that shadows the installed package.
The script enforces this below.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np

# --- Guard against the repo-root package shadow (audit finding INT-01) -------
_REPO_ROOT_SHADOW = os.path.join(os.getcwd(), "wifi_densepose", "__init__.py")
if os.path.exists(_REPO_ROOT_SHADOW):
    sys.stderr.write(
        "REFUSING TO RUN: cwd contains a `wifi_densepose/` package that shadows\n"
        "the installed wheel. Run this from outside the repo root.\n"
    )
    sys.exit(3)

import wifi_densepose as wdp  # noqa: E402

FS = 100.0          # ESP32 default sample rate (Hz)
N_SUBCARRIERS = 56  # ESP32 default subcarrier count
SEED = 20260810

# Documented operating ranges, from the extractor docstrings.
BREATH_RANGE_BPM = (6.0, 30.0)
HEART_RANGE_BPM = (40.0, 120.0)


def make_extractor(kind: str):
    return (
        wdp.BreathingExtractor.esp32_default()
        if kind == "breathing"
        else wdp.HeartRateExtractor.esp32_default()
    )


def drive(extractor, frames: np.ndarray, weights_mode: str = "empty"):
    """Feed frames one at a time; return the final non-None estimate.

    `frames` is (n_samples, n_subcarriers) of per-subcarrier amplitude
    residuals — the shape the extractor's own docstring specifies.

    weights_mode selects the second argument:
      "empty" — `weights=[]`, the idiom the class docstring itself shows
                ("# equal weights"). This is what a reader of the published
                docs will write.
      "ones"  — `weights=[1.0]*56`, an explicit uniform weight vector.

    These are NOT equivalent in the published 2.0.0a1 wheel, and the
    difference is audit finding C4-B (upstream issue #1423): for
    HeartRateExtractor, `weights=[]` truncates the working subcarrier count
    to zero and every frame returns None. The repo source at HEAD carries the
    fix; the published wheel does not.
    """
    n_sc = frames.shape[1]
    wt = [] if weights_mode == "empty" else [1.0] * n_sc
    last = None
    for row in frames:
        est = extractor.extract(residuals=row.tolist(), weights=wt)
        if est is not None:
            last = est
    return last


def synth(
    bpm: float | None,
    duration_s: float,
    amplitude: float = 0.01,
    noise_sigma: float = 0.001,
    mode: str = "sine",
    second_bpm: float | None = None,
    second_amplitude: float = 0.0,
    seed: int = SEED,
) -> np.ndarray:
    """Build an (n, 56) CSI-shaped residual block.

    mode:
      sine  — sinusoid at `bpm` (plus optional second component)
      noise — pure Gaussian noise, NO periodic component at all
      dc    — constant offset, no variation
      ramp  — linear drift, no periodicity
    """
    n = int(FS * duration_s)
    t = np.arange(n) / FS
    rng = np.random.default_rng(seed)

    if mode == "sine":
        base = amplitude * np.sin(2.0 * np.pi * (bpm / 60.0) * t)
        if second_bpm is not None and second_amplitude > 0.0:
            base = base + second_amplitude * np.sin(
                2.0 * np.pi * (second_bpm / 60.0) * t
            )
    elif mode == "noise":
        base = np.zeros(n)
    elif mode == "dc":
        base = np.full(n, amplitude)
        noise_sigma = 0.0
    elif mode == "ramp":
        base = np.linspace(0.0, amplitude, n)
        noise_sigma = 0.0
    else:
        raise ValueError(mode)

    frames = base[:, None] + noise_sigma * rng.standard_normal((n, N_SUBCARRIERS))
    return frames


def snr_db(amplitude: float, noise_sigma: float) -> float:
    """Amplitude-vs-noise SNR in dB. Infinite when noise is zero."""
    if noise_sigma <= 0:
        return float("inf")
    return 20.0 * np.log10(amplitude / noise_sigma)


def record(rows, test, kind, truth, est, extra=None):
    in_range = (
        (BREATH_RANGE_BPM if kind == "breathing" else HEART_RANGE_BPM)
        if est is not None
        else None
    )
    row = {
        "test": test,
        "extractor": kind,
        "truth_bpm": truth,
        "recovered_bpm": None if est is None else round(est.value_bpm, 4),
        "confidence": None if est is None else round(est.confidence, 6),
        "status": None if est is None else str(est.status),
        "returned_none": est is None,
        "abs_error_bpm": (
            None if (est is None or truth is None) else round(abs(est.value_bpm - truth), 4)
        ),
        "in_claimed_range": (
            None
            if est is None
            else bool(in_range[0] <= est.value_bpm <= in_range[1])
        ),
    }
    row.update(extra or {})
    rows.append(row)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="docs/spec/evidence/c4")
    ap.add_argument("--repo", default="/home/user/RuView")
    args = ap.parse_args()

    outdir = os.path.join(args.repo, args.outdir)
    os.makedirs(outdir, exist_ok=True)
    rows: list[dict] = []

    print("=" * 74)
    print("C4 — SYNTHETIC GROUND TRUTH")
    print(f"package wifi_densepose {wdp.__version__} / rust {wdp.__rust_version__}")
    print(f"fs={FS} Hz  subcarriers={N_SUBCARRIERS}  seed={SEED}")
    print("=" * 74)

    # ---------------------------------------------------------------
    # TEST 1 — Baseline: both components present simultaneously.
    # 0.25 Hz = 15 BPM respiration, 1.2 Hz = 72 BPM cardiac.
    # ---------------------------------------------------------------
    print("\n[1] BASELINE — 15 BPM breathing + 72 BPM heart, both present")
    frames = synth(
        bpm=15.0, duration_s=40.0, amplitude=0.01,
        noise_sigma=0.001, second_bpm=72.0, second_amplitude=0.003,
    )
    for kind, truth in (("breathing", 15.0), ("heart", 72.0)):
        for wm in ("empty", "ones"):
            est = drive(make_extractor(kind), frames, wm)
            r = record(rows, "baseline_combined", kind, truth, est,
                       {"snr_db": round(snr_db(0.01, 0.001), 2), "weights_mode": wm})
            print(f"    {kind:10s} weights={wm:5s} truth={truth:6.1f}  "
                  f"got={r['recovered_bpm']}  conf={r['confidence']}  "
                  f"err={r['abs_error_bpm']}")

    # ---------------------------------------------------------------
    # TEST 2 — Sweep across the claimed operating ranges.
    # ---------------------------------------------------------------
    print("\n[2] SWEEP — across each extractor's documented range")
    for kind, sweep, dur in (
        ("breathing", [6.0, 10.0, 15.0, 20.0, 30.0], 60.0),
        ("heart", [40.0, 60.0, 90.0, 120.0], 30.0),
    ):
        print(f"  -- {kind} --")
        for truth in sweep:
            frames = synth(bpm=truth, duration_s=dur, amplitude=0.01,
                           noise_sigma=0.001)
            for wm in ("empty", "ones"):
                est = drive(make_extractor(kind), frames, wm)
                r = record(rows, "sweep", kind, truth, est,
                           {"snr_db": round(snr_db(0.01, 0.001), 2),
                            "weights_mode": wm})
                print(f"    weights={wm:5s} truth={truth:6.1f}  "
                      f"got={r['recovered_bpm']}  conf={r['confidence']}  "
                      f"err={r['abs_error_bpm']}")

    # ---------------------------------------------------------------
    # TEST 3 — SNR sweep downward until it breaks.
    # ---------------------------------------------------------------
    print("\n[3] SNR SWEEP — hold BPM fixed, raise the noise floor")
    for kind, truth, dur in (("breathing", 15.0, 60.0), ("heart", 72.0, 30.0)):
        print(f"  -- {kind} (truth {truth} BPM) --")
        wm = "ones"   # the mode in which both extractors actually function
        for sigma in [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1]:
            frames = synth(bpm=truth, duration_s=dur, amplitude=0.01,
                           noise_sigma=sigma)
            est = drive(make_extractor(kind), frames, wm)
            r = record(rows, "snr_sweep", kind, truth, est,
                       {"noise_sigma": sigma, "snr_db": round(snr_db(0.01, sigma), 2),
                        "weights_mode": wm})
            print(f"    SNR={r['snr_db']:7.2f} dB  got={r['recovered_bpm']}  "
                  f"conf={r['confidence']}  err={r['abs_error_bpm']}")

    # ---------------------------------------------------------------
    # TEST 4 — NULL TESTS. The decisive ones.
    # There is NO periodic component in any of these inputs. Correct
    # behaviour is to return None, or a number with ~zero confidence.
    # Returning a confident in-range BPM here means the extractor is
    # reporting structure that does not exist.
    # ---------------------------------------------------------------
    print("\n[4] NULL TESTS — input contains NO periodic component")
    print("    correct answer: None, or near-zero confidence")
    null_cases = [
        ("pure_noise_low", dict(mode="noise", amplitude=0.0, noise_sigma=0.001)),
        ("pure_noise_high", dict(mode="noise", amplitude=0.0, noise_sigma=0.05)),
        ("pure_dc", dict(mode="dc", amplitude=0.01, noise_sigma=0.0)),
        ("linear_ramp", dict(mode="ramp", amplitude=0.05, noise_sigma=0.0)),
    ]
    for case, kw in null_cases:
        for kind, dur in (("breathing", 60.0), ("heart", 30.0)):
            frames = synth(bpm=None, duration_s=dur, **kw)
            est = drive(make_extractor(kind), frames, "ones")
            r = record(rows, f"null_{case}", kind, None, est,
                       {"null_case": case, "weights_mode": "ones"})
            verdict = (
                "OK (None)" if est is None
                else f"EMITTED {r['recovered_bpm']} BPM conf={r['confidence']} "
                     f"in_range={r['in_claimed_range']}"
            )
            print(f"    {case:16s} {kind:10s} -> {verdict}")

    # Repeat the noise null across many seeds — a single seed could be luck.
    print("\n    [4b] pure noise across 20 seeds (is the output stable or random?)")
    for kind, dur in (("breathing", 60.0), ("heart", 30.0)):
        vals, nones, confs = [], 0, []
        for s in range(20):
            frames = synth(bpm=None, duration_s=dur, mode="noise",
                           amplitude=0.0, noise_sigma=0.001, seed=SEED + s)
            est = drive(make_extractor(kind), frames, "ones")
            record(rows, "null_noise_seedsweep", kind, None, est,
                   {"null_case": "pure_noise", "seed": SEED + s,
                    "weights_mode": "ones"})
            if est is None:
                nones += 1
            else:
                vals.append(est.value_bpm)
                confs.append(est.confidence)
        if vals:
            print(f"    {kind:10s} None={nones}/20  emitted={len(vals)}  "
                  f"bpm mean={np.mean(vals):.2f} sd={np.std(vals):.2f} "
                  f"min={np.min(vals):.2f} max={np.max(vals):.2f}  "
                  f"conf mean={np.mean(confs):.4f} max={np.max(confs):.4f}")
        else:
            print(f"    {kind:10s} None={nones}/20 — returned None every time")

    # ---------------------------------------------------------------
    # Persist evidence
    # ---------------------------------------------------------------
    csv_path = os.path.join(outdir, "c4_results.csv")
    keys = sorted({k for r in rows for k in r})
    with open(csv_path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=keys)
        wtr.writeheader()
        wtr.writerows(rows)

    meta = {
        "package_version": wdp.__version__,
        "rust_version": wdp.__rust_version__,
        "build_features": list(wdp.__build_features__),
        "fs_hz": FS,
        "n_subcarriers": N_SUBCARRIERS,
        "seed": SEED,
        "n_rows": len(rows),
    }
    with open(os.path.join(outdir, "c4_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nWrote {len(rows)} rows -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
