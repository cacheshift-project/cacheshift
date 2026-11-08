"""Slide 6 figures: does the cache shift the router's strong-model share?

Reads committed experiment reports (no model, no network) and draws:

  A  drift_random_repeats.png   ARC, exact cache, uniform repeats, five seeds (PR #23)
  B  drift_random_vs_skewed.png MMLU, exact cache: uniform repeats vs. repeats skewed
                                2:1 toward easy or hard questions, five seeds each (PR #28)

Each row is one seed: the dot is the cache-on minus cache-off strong-model share
(percentage points of requests reaching the router), the bar its 95% paired
question-group bootstrap interval, taken directly from the report files.

Run from the repo root (needs matplotlib):
  python tools/plot_drift_figures.py
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARC_REPORT = ROOT / "experiments/results/retune-20261004/report.json"
SKEW_REPORT = ROOT / "experiments/results/controlled-drift-20261012/report.json"
OUT = ROOT / "docs/sprints/Sprint_1/figures"

INK, MUTED, GRID = "#16202E", "#6A7684", "#C9D1DA"
NEUTRAL = "#4B5563"   # random repeats in figure B: grey, unlike the two coloured skew groups
BAR, DOT = "#9DB4CC", "#B2491A"
EASY, HARD = "#C2410C", "#1D4ED8"   # orange / blue: differ in hue and lightness


def cache_effect(run):
    effect = run["metrics"]["paired_differences"]["cache_effect"]["strong_share_of_routed"]
    lo, hi = effect["ci95"]
    return 100 * effect["estimate"], 100 * lo, 100 * hi


def zero_label(ax, y):
    ax.text(0, y, "0 = no drift", ha="center", va="bottom", fontsize=11, color=MUTED,
            bbox=dict(facecolor="white", edgecolor="none", pad=2), zorder=4)


def style(ax, xlim, step):
    ax.set_xlim(*xlim)
    ax.set_xticks(range(xlim[0], xlim[1] + 1, step))
    ax.axvline(0, color=MUTED, lw=1.4, zorder=1)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="y", length=0, labelsize=13, colors=INK)
    ax.tick_params(axis="x", labelsize=12, colors=MUTED)


def row(ax, y, est, lo, hi, color):
    ax.plot([lo, hi], [y, y], color=BAR if color == DOT else color, lw=7, alpha=1 if color == DOT else 0.45,
            solid_capstyle="round", zorder=2)
    ax.plot(est, y, "o", ms=11, color=color, zorder=3)


def fmt(v):
    return f"{v:+.1f}".replace("-", "−") if abs(v) >= 0.05 else "0.0"


def figure_a(report, out):
    runs = sorted(report["runs"], key=lambda r: r["seed"])
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200)
    for i, run in enumerate(runs):
        est, lo, hi = cache_effect(run)
        y = len(runs) - 1 - i
        row(ax, y, est, lo, hi, DOT)
        ax.text(6.4, y, f"{fmt(est)}  [{fmt(lo)}, {fmt(hi)}]", va="center", fontsize=12.5,
                family="monospace", color=INK)
    style(ax, (-6, 6), 2)
    ax.set_yticks(range(len(runs)), [f"Seed {r['seed']}" for r in reversed(runs)])
    ax.set_xlabel("Change in expensive-model share with the cache on (percentage points)", fontsize=13, color=INK)
    zero_label(ax, len(runs) - 0.55)
    ax.set_ylim(-0.6, len(runs) - 0.2)
    fig.text(0.01, 0.01, "Dot = change · bar = 95% bootstrap range · ARC, 300 questions + 300 random repeats, exact cache · "
             "source: experiments/results/retune-20261004", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.11, right=0.74, top=0.95, bottom=0.2)
    fig.savefig(out)
    plt.close(fig)


GROUPS = (
    ("uniform", "Random repeats", NEUTRAL),
    ("low", "Easy questions\nrepeat 2× as often", EASY),
    ("high", "Hard questions\nrepeat 2× as often", HARD),
)


def figure_b(report, out):
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=200)
    ticks, labels, y = [], [], 0
    for policy, label, color in reversed(GROUPS):
        runs = sorted((r for r in report["runs"] if r["policy"] == policy), key=lambda r: r["seed"])
        ys = []
        for run in runs:
            est, lo, hi = cache_effect(run)
            row(ax, y, est, lo, hi, color)
            ys.append(y)
            y += 0.42
        effects = [cache_effect(r)[0] for r in runs]
        ax.text(10.6, sum(ys) / len(ys), f"{fmt(min(effects))} to {fmt(max(effects))} pts", va="center",
                fontsize=12.5, color=color if policy != "uniform" else INK, fontweight="bold")
        ticks.append(sum(ys) / len(ys))
        labels.append(label)
        y += 0.6
    style(ax, (-10, 10), 5)
    ax.set_yticks(ticks, labels)
    ax.set_xlabel("Change in expensive-model share with the cache on (percentage points)", fontsize=13, color=INK)
    zero_label(ax, y - 0.55)
    ax.set_ylim(-0.4, y - 0.1)
    fig.text(0.01, 0.01, "Each dot = one seed (5 per group) · bar = 95% bootstrap range · MMLU, exact cache · the skew is "
             "deliberate (a controlled test, not real traffic)\nsource: experiments/results/controlled-drift-20261012",
             fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.2, right=0.8, top=0.95, bottom=0.2)
    fig.savefig(out)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    figure_a(json.loads(ARC_REPORT.read_text()), args.out / "drift_random_repeats.png")
    figure_b(json.loads(SKEW_REPORT.read_text()), args.out / "drift_random_vs_skewed.png")
    print(f"Wrote {args.out / 'drift_random_repeats.png'} and {args.out / 'drift_random_vs_skewed.png'}")


if __name__ == "__main__":
    main()
