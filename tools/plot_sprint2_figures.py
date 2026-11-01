"""Sprint 2 slide figures, drawn from committed experiment reports (no model, no network).

  1  real_traffic_drift.png      controlled drift (#28) vs real LMSYS traffic (#36), with the 5-point line
  2  cache_quality_threshold.png wrong-question answers and accuracy cost by semantic-cache setting (Story 2)
  3  retune_accuracy.png         accuracy cost of re-tuning in the six no-shift settings, with the -1 point bound (#37, #5)
  4  energy_full_vs_4bit.png     Llama-3.1-8B energy per token and speed, full precision vs 4-bit, SCC L40S (#35)

Run from the repo root (needs matplotlib):
  python tools/plot_sprint2_figures.py
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments/results"
CONTROLLED = RESULTS / "controlled-drift-20261012/report.json"
REAL = RESULTS / "real-traffic-20261028/report.json"
QUALITY = RESULTS / "cache-quality-20261012/report.json"
RETUNE = RESULTS / "lru-retune-20261026/report.json"
ENERGY = RESULTS / "scc-energy-8291245/report.json"
OUT = ROOT / "docs/sprints/Sprint_2/figures"

# Colours from the Sprint 2 slide template (Slidesgo, teal); red only marks wrong answers and failures
BG, INK, MUTED, GRID = "#F3F3F3", "#212121", "#66706E", "#D3D9D7"
EASY, HARD, REAL_C = "#2FAE92", "#305C54", "#212121"
PASS, FAIL, BAND, FAIL_BAND = "#4C9484", "#B91C1C", "#DDE9E6", "#F2DCDC"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG})


def pts(x):
    return 100 * x


def fmt(v, digits=1):
    return f"{v:+.{digits}f}".replace("-", "−") if round(abs(v), digits) else "0.0"


def clean(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(labelsize=12, colors=INK)


def source(fig, text):
    fig.text(0.01, 0.015, text, fontsize=8.5, color=MUTED)


def interval(ax, y, est, lo, hi, color, alpha=0.4, ms=10):
    ax.plot([lo, hi], [y, y], color=color, lw=7, alpha=alpha, solid_capstyle="round", zorder=2)
    ax.plot(est, y, "o", ms=ms, color=color, zorder=3)


def figure_drift(controlled, real, out):
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=200)
    ax.axvspan(-5, 5, color=BAND, zorder=0)
    ax.text(0, 4.55, "inside ±5 points = too small to matter\n(line set before the run)", ha="center",
            va="center", fontsize=10.5, color=MUTED, bbox=dict(facecolor=BAND, edgecolor="none", pad=2), zorder=4)
    rows = []
    for y, policy, label, color in ((3.6, "high", "Test: hard questions\nrepeat 2× as often", HARD),
                                    (2.6, "low", "Test: easy questions\nrepeat 2× as often", EASY)):
        effects = []
        for i, run in enumerate(sorted((r for r in controlled["runs"] if r["policy"] == policy),
                                       key=lambda r: r["seed"])):
            e = run["metrics"]["paired_differences"]["cache_effect"]["strong_share_of_routed"]
            lo, hi = map(pts, e["ci95"])
            interval(ax, y - 0.24 + 0.12 * i, pts(e["estimate"]), lo, hi, color, alpha=0.3, ms=7)
            effects.append(pts(e["estimate"]))
        ax.text(11.2, y, f"{fmt(min(effects))} to {fmt(max(effects))}", va="center", fontsize=12.5,
                color=color, fontweight="bold")
        rows.append((y, label))
    main = real["main"]
    est = pts(main["estimates"]["unbounded_drift"])
    lo, hi = map(pts, main["intervals_95"]["unbounded_drift"])
    interval(ax, 1.4, est, lo, hi, REAL_C, ms=11)
    ax.text(11.2, 1.4, f"{fmt(est)} [{fmt(lo)}, {fmt(hi)}]", va="center", fontsize=12.5, color=INK,
            fontweight="bold")
    rows.append((1.4, "Real chat traffic\ncache never forgets"))
    for y, fraction in ((0.75, 0.25), (0.25, 0.10)):
        drifts = [pts(r["drift"]) for r in main["lru"] if r["capacity_fraction"] == fraction]
        ax.plot(drifts, [y] * len(drifts), "o", ms=8, color=REAL_C, alpha=0.6, zorder=3)
        low, high = fmt(min(drifts)), fmt(max(drifts))
        ax.text(11.2, y, low if low == high else f"{low} to {high}", va="center", fontsize=12, color=INK)
        rows.append((y, f"Real traffic, cache holds {fraction:.0%}"))
    ax.set_xlim(-10, 10)
    ax.set_xticks(range(-10, 11, 5))
    ax.set_ylim(-0.1, 4.95)
    ax.set_yticks([y for y, _ in rows], [label for _, label in rows])
    ax.axvline(0, color=MUTED, lw=1.2, zorder=1)
    clean(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Change in expensive-model share with the cache on (percentage points)", fontsize=12.5,
                  color=INK)
    source(fig, "Dots = estimates · bars = 95% bootstrap ranges · top: MMLU, 5 seeds, skew set on purpose (#28)\n"
                f"bottom: {real['traffic']['requests']:,} English LMSYS-Chat-1M requests, exact cache, LRU in 5 "
                "random orders (#36)")
    fig.subplots_adjust(left=0.25, right=0.74, top=0.97, bottom=0.2)
    fig.savefig(out)
    plt.close(fig)


def figure_quality(quality, out, model="gpt-4-1106-preview", seed=601):
    runs = {r["setting"]: r for r in quality["runs"] if r["model"] == model and r["seed"] == seed}
    settings = quality["settings"]
    labels = ["exact" if s == "exact" else s.replace("cos>=", "≥ ") for s in settings]
    x = range(len(settings))
    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4.6), dpi=200)
    for ax, metric, title, color in ((left, "false_hit_rate", "Answers served for a different question (%)", FAIL),
                                     (right, "accuracy_change", "Accuracy change vs fresh answers (points)", HARD)):
        est = [pts(runs[s][metric]["estimate"]) for s in settings]
        lo = [pts(runs[s][metric]["ci95"][0]) for s in settings]
        hi = [pts(runs[s][metric]["ci95"][1]) for s in settings]
        ax.vlines(x, lo, hi, color=color, lw=6, alpha=0.3)
        ax.plot(x, est, "o-", color=color, ms=8, lw=2)
        ax.set_xticks(list(x), labels)
        ax.set_title(title, fontsize=12.5, color=INK, loc="left")
        ax.axhline(0, color=MUTED, lw=1)
        clean(ax, "y")
        i = settings.index("cos>=0.90")
        ax.annotate(f"{est[i]:.1f}".replace("-", "−"), (i, est[i]), textcoords="offset points",
                    xytext=(0, 12 if metric == "false_hit_rate" else -20), ha="center", fontsize=11.5,
                    color=INK, fontweight="bold")
    left.set_ylim(-0.3, 5)
    right.set_ylim(-4.5, 0.6)
    fig.supxlabel("Semantic cache match setting (stricter ← → looser)", fontsize=12, color=INK, y=0.09)
    source(fig, f"{model}, seed {seed} · 970 ARC questions + 970 repeats · answers graded against the official key · "
                "bars = 95% bootstrap ranges\nblind hand check of 50 rows: 96% agreement · "
                "source: experiments/results/cache-quality-20261012")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.9, bottom=0.26, wspace=0.25)
    fig.savefig(out)
    plt.close(fig)


POLICY = {"uniform": "Random repeats", "high": "Hard questions popular", "low": "Easy questions popular"}


def figure_retune(retune, out):
    decisions = [d for d in retune["decisions"] if d["arm"] == "no_shift"]
    sizes = sorted({d["capacity"] for d in decisions})
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200)
    ax.axvspan(-2, -1, color=FAIL_BAND, zorder=0)
    ax.axvline(-1, color=FAIL, lw=1.4, ls="--", zorder=1)
    ax.text(-1.05, 5.75, "fails below −1.0\n(agreed before the run)", ha="right", va="center", fontsize=10.5,
            color=FAIL)
    ticks, labels = [], []
    for y, d in enumerate(sorted(decisions, key=lambda d: (-sizes.index(d["capacity"]), d["test_policy"]))):
        effect = d["pooled_retune_accuracy_effect"]
        est, (lo, hi) = pts(effect["estimate"]), map(pts, effect["ci95"])
        color = PASS if d["passes"] else FAIL
        interval(ax, y, est, lo, hi, color)
        ax.text(1.25, y, f"{fmt(est, 2)} [{fmt(lo, 2)}, {fmt(hi, 2)}]  " + ("pass" if d["passes"] else "FAIL"),
                va="center", fontsize=11.5, color=color, fontweight="bold" if not d["passes"] else "normal")
        fraction = retune["capacity_fractions"][sizes.index(d["capacity"])]
        ticks.append(y)
        labels.append(f"{POLICY[d['test_policy']]}, cache {fraction:.0%}")
    ax.set_xlim(-2, 1.2)
    ax.set_ylim(-0.6, 6.3)
    ax.set_yticks(ticks, labels)
    ax.axvline(0, color=MUTED, lw=1.2, zorder=1)
    clean(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Accuracy change from re-tuning (points), pooled over 5 seeds", fontsize=12.5, color=INK)
    source(fig, "Dots = estimates · bars = paired 95% bootstrap ranges · every re-tuned share landed in 47–53%\n"
                "MMLU, LRU exact cache · source: experiments/results/lru-retune-20261026")
    fig.subplots_adjust(left=0.33, right=0.7, top=0.97, bottom=0.2)
    fig.savefig(out)
    plt.close(fig)


def figure_energy(energy, out):
    runs = {m["precision"]: m["sustained_load"] for m in energy["models"]}
    names, colors = ["Full precision", "4-bit"], [MUTED, HARD]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), dpi=200)
    for ax, key, title, unit in ((axes[0], "joules_per_output_token", "Energy per output token", "J"),
                                 (axes[1], "output_tokens_per_second", "Speed", "tokens/s")):
        values = [runs["full"][key], runs["4bit"][key]]
        bars = ax.bar(names, values, color=colors, width=0.55)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2f} {unit}" if unit == "J"
                    else f"{value:.1f} {unit}", ha="center", va="bottom", fontsize=13, color=INK, fontweight="bold")
        ax.set_title(title, fontsize=13, color=INK, loc="left")
        ax.set_ylim(0, max(values) * 1.2)
        ax.set_yticks([])
        clean(ax, "y")
        ax.spines["left"].set_visible(False)
    idle = energy["idle"]["mean_watts"]
    source(fig, f"{energy['model']} on one {energy['gpu']['name']} (BU SCC), batch size 1, 128 output tokens per "
                f"request, 5 minutes of load each, one run · idle {idle:.1f} W · "
                "\nsource: experiments/results/scc-energy-8291245")
    fig.subplots_adjust(left=0.04, right=0.98, top=0.9, bottom=0.2, wspace=0.2)
    fig.savefig(out)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    load = lambda path: json.loads(path.read_text())  # noqa: E731
    figure_drift(load(CONTROLLED), load(REAL), args.out / "real_traffic_drift.png")
    figure_quality(load(QUALITY), args.out / "cache_quality_threshold.png")
    figure_retune(load(RETUNE), args.out / "retune_accuracy.png")
    figure_energy(load(ENERGY), args.out / "energy_full_vs_4bit.png")
    print(f"Wrote 4 figures to {args.out}")


if __name__ == "__main__":
    main()
