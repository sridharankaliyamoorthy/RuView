#!/usr/bin/env python3
"""C4 evidence charts — reads c4_results.csv, writes c4_charts.png.

Three panels, in the order the audit argues them:
  1. Recovered vs ground truth   — is the DSP real?
  2. Confidence vs SNR           — does it know when it is struggling?
  3. Null tests (20 noise seeds) — does it invent a BPM from nothing?

Palette: dataviz reference categorical slots 1 (blue) + 2 (orange), validated
via scripts/validate_palette.js — all six checks PASS in light mode.
"""

from __future__ import annotations

import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BREATH = "#2a78d6"   # categorical slot 1
HEART = "#eb6834"    # categorical slot 2
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8985"
SURFACE = "#fcfcfb"
GRID = "#e2e1dd"


def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else "/home/user/RuView"
    d = os.path.join(repo, "docs/spec/evidence/c4")
    rows = load(os.path.join(d, "c4_results.csv"))

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4))
    fig.patch.set_facecolor(SURFACE)

    # ---------------- Panel 1: recovered vs truth ----------------
    ax = axes[0]
    style(ax)
    sweep = [r for r in rows if r["test"] == "sweep" and r.get("weights_mode") == "ones"]
    for kind, color, label in (("breathing", BREATH, "Breathing"),
                               ("heart", HEART, "Heart rate")):
        pts = [(num(r["truth_bpm"]), num(r["recovered_bpm"]))
               for r in sweep if r["extractor"] == kind and num(r["recovered_bpm"]) is not None]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, s=88, color=color, zorder=3,
                       edgecolors=SURFACE, linewidths=2, label=label)
    lim = (0, 130)
    ax.plot(lim, lim, color=MUTED, linewidth=1.4, linestyle="--",
            zorder=1, label="perfect recovery (y = x)")
    # Call out the single miss.
    miss = [r for r in sweep if r["extractor"] == "heart" and num(r["truth_bpm"]) == 40.0]
    if miss and num(miss[0]["recovered_bpm"]) is not None:
        ax.annotate("40 BPM → 48.0\n(only miss: +8.0)",
                    xy=(40, num(miss[0]["recovered_bpm"])), xytext=(52, 26),
                    fontsize=8.5, color=INK2,
                    arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Ground truth (BPM)", fontsize=9.5, color=INK2)
    ax.set_ylabel("Recovered (BPM)", fontsize=9.5, color=INK2)
    ax.set_title("1 · Recovers the frequency we injected",
                 fontsize=11.5, color=INK, loc="left", pad=12, fontweight="bold")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", labelcolor=INK2)

    # ---------------- Panel 2: confidence vs SNR ----------------
    ax = axes[1]
    style(ax)
    snr = [r for r in rows if r["test"] == "snr_sweep"]
    for kind, color, label in (("breathing", BREATH, "Breathing"),
                               ("heart", HEART, "Heart rate")):
        pts = sorted(
            (num(r["snr_db"]), num(r["confidence"]), num(r["abs_error_bpm"]))
            for r in snr if r["extractor"] == kind and num(r["confidence"]) is not None
        )
        if not pts:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=3, label=label)
        # Mark points where the estimate was actually wrong (>1 BPM off).
        bad = [(p[0], p[1]) for p in pts if p[2] is not None and p[2] > 1.0]
        if bad:
            bx, by = zip(*bad)
            ax.scatter(bx, by, s=190, facecolors="none", edgecolors=color,
                       linewidths=2.2, zorder=4)
            ax.annotate("wrong answer (25 BPM),\nyet confidence RISES",
                        xy=(bad[0][0], bad[0][1]), xytext=(-4, 0.17),
                        fontsize=8.5, color=INK2,
                        arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
    ax.axhline(0.6, color=MUTED, linewidth=1.2, linestyle=":", zorder=1)
    ax.text(-31, 0.63, "0.6 = 'Valid' cutoff", fontsize=8, color=MUTED, ha="right")
    ax.set_xlabel("SNR (dB) — noise rising to the left", fontsize=9.5, color=INK2)
    ax.set_ylabel("Reported confidence", fontsize=9.5, color=INK2)
    ax.set_ylim(0, 1.05)
    ax.invert_xaxis()
    ax.set_title("2 · Confidence vs noise (circled = wrong)",
                 fontsize=11.5, color=INK, loc="left", pad=12, fontweight="bold")
    ax.legend(frameon=False, fontsize=8.5, loc="lower left", labelcolor=INK2)

    # ---------------- Panel 3: null tests ----------------
    ax = axes[2]
    style(ax)
    nulls = [r for r in rows if r["test"] == "null_noise_seedsweep"]
    heart_vals = [num(r["recovered_bpm"]) for r in nulls
                  if r["extractor"] == "heart" and num(r["recovered_bpm"]) is not None]
    breath_none = sum(1 for r in nulls
                      if r["extractor"] == "breathing" and r["returned_none"] == "True")
    ax.axhspan(40, 120, color=HEART, alpha=0.07, zorder=0)
    ax.text(20.6, 123, "claimed heart-rate range 40–120 BPM",
            fontsize=8, color=MUTED, ha="right")
    if heart_vals:
        ax.scatter(range(1, len(heart_vals) + 1), heart_vals, s=80, color=HEART,
                   edgecolors=SURFACE, linewidths=1.8, zorder=3,
                   label=f"Heart: emitted a BPM {len(heart_vals)}/20")
    ax.scatter([], [], s=80, color=BREATH,
               label=f"Breathing: returned None {breath_none}/20")
    ax.axhline(0, color=BREATH, linewidth=2.4, zorder=2)
    ax.text(0.4, -4.4, "Breathing: nothing to plot — it returns None every time",
            fontsize=8.5, color=BREATH, ha="left", va="top")
    ax.set_xlim(0, 21); ax.set_ylim(-16, 140)
    ax.set_xlabel("Random seed (input = pure Gaussian noise)", fontsize=9.5, color=INK2)
    ax.set_ylabel("Reported BPM", fontsize=9.5, color=INK2)
    ax.set_title("3 · Fed pure noise — the decisive test",
                 fontsize=11.5, color=INK, loc="left", pad=12, fontweight="bold")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left",
              bbox_to_anchor=(0.0, 0.90), labelcolor=INK2)

    fig.suptitle(
        "C4 — Synthetic ground truth vs RuView vital-sign extractors  "
        "(wifi_densepose 2.0.0a1 / rust 2.0.0-alpha.1, 56 subcarriers @ 100 Hz)",
        fontsize=12.5, color=INK, x=0.006, ha="left", y=0.985, fontweight="bold",
    )
    fig.text(
        0.006, 0.017,
        "Heart-rate figures require weights=[1.0]*56. With weights=[] — the idiom the "
        "class docstring itself shows — the published wheel returns None for every "
        "input (upstream #1423, fixed in repo source, not in the release).",
        fontsize=8.5, color=INK2, ha="left",
    )
    fig.tight_layout(rect=[0, 0.045, 1, 0.945])
    out = os.path.join(d, "c4_charts.png")
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
