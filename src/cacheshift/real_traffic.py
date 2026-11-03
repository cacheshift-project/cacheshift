"""Issue #36 (A2, part 2): do the prompts people repeat score differently on the router than the
ones they ask once, and how far would an exact cache move the strong-model share on real traffic?

Plan (docs/sprints/Sprint_2/Real_Traffic_Plan.md, fixed 28 Oct 2026 before any scoring):
- LMSYS-Chat-1M, first user message of each English conversation; one conversation = one request.
- Repeat key: whitespace trimmed and collapsed, case-sensitive. Repeated groups have size >= 2.
- Scored set (amended 28 Oct before scoring): every key of size >= 3, 15,000 size-2 keys and 20,000
  one-off keys, seed 601, weighted by stratum size / keys scored in the stratum. Single-prompt router
  scoring on the key.
- Cutoff: weighted midgap rule, 50% of all requests strong with no cache.
- Headline: never-evicting exact cache drift (cache-on minus cache-off strong share of routed requests).
  Secondary: LRU caches at 10% and 25% of unique keys over five random stream orders (601-605).
- 95% percentile bootstrap, 2,000 resamples of prompt groups within each sampling stratum, conditional
  on the cutoff. Decision on the headline CI against +/-5 points.
- Sensitivity (not used for the decision): without NAME_n keys; size-2 groups counted as one request
  (possible Arena pairs); without keys repeated more than 100 times (possible automated traffic).

No LMSYS text is written to the committed report. Per-prompt scores go to <run-dir>/raw/ (git-ignored),
keyed by the SHA-256 of the key so an interrupted run can resume.
"""

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import re
import time

import numpy as np

from cacheshift.gateway import ROOT
from cacheshift.lru_drift import lru_misses
from cacheshift.router import CHECKPOINT, REVISION

DEFAULT_DATA = ROOT / "data/raw/lmsys-chat-1m/data"
PLAN = ROOT / "docs/sprints/Sprint_2/Real_Traffic_Plan.md"
LANGUAGE = "English"
SEED = 601
LRU_SEEDS = (601, 602, 603, 604, 605)
CAPACITY_FRACTIONS = (0.10, 0.25)
ONE_OFF_SAMPLE = 20_000
PAIR_SAMPLE = 15_000
AUTOMATED_OVER = 100
TARGET = 0.5
DECISION_LINE = 0.05  # proportion: 5 percentage points
SAMPLES = 2000
NAME_TAG = re.compile(r"NAME_\d+")


def normalize(text):
    """The exact-cache key: trim the ends and collapse every whitespace run. Case is kept."""
    return re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""


def first_user_message(conversation):
    for turn in conversation or ():
        if turn.get("role") == "user":
            return turn.get("content")
    return None


def load_requests(data_dir, language=LANGUAGE):
    """English request keys in dataset order, plus counts of what was dropped and why."""
    import pyarrow.parquet as pq

    files = sorted(Path(data_dir).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files in {data_dir}; download LMSYS-Chat-1M first")
    keys, counts = [], Counter()
    for path in files:
        table = pq.read_table(path, columns=["conversation", "language"])
        for conversation, lang in zip(table.column("conversation").to_pylist(),
                                      table.column("language").to_pylist()):
            counts["conversations"] += 1
            if lang != language:
                counts["other_language"] += 1
                continue
            key = normalize(first_user_message(conversation))
            if not key:
                counts["empty_first_message"] += 1
                continue
            keys.append(key)
    counts["requests"] = len(keys)
    return keys, dict(counts), files


def stratum_of(count):
    return "one_off" if count == 1 else "pair" if count == 2 else "multi"


def sample_keys(groups, seed=SEED, one_off_sample=ONE_OFF_SAMPLE, pair_sample=PAIR_SAMPLE):
    """Every key of size >= 3, plus seeded samples of size-2 and one-off keys.

    Returns ({stratum: scored keys}, {stratum: design weight}); a weight is the stratum's key count over
    the keys scored from it, so weighted sums estimate the whole population (and any subset of it).
    """
    rng = random.Random(seed)
    pools = {name: [] for name in ("multi", "pair", "one_off")}
    for key in sorted(groups):
        pools[stratum_of(groups[key])].append(key)
    sizes = {"multi": len(pools["multi"]), "pair": pair_sample, "one_off": one_off_sample}
    sampled = {name: sorted(rng.sample(pool, min(sizes[name], len(pool)))) if name != "multi" else pool
               for name, pool in pools.items()}
    weights = {name: len(pools[name]) / len(keys) for name, keys in sampled.items() if keys}
    return sampled, weights


def key_hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def score_keys(keys, router, raw_path):
    """Score one prompt at a time, appending to raw_path so an interrupted run resumes."""
    raw_path = Path(raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if raw_path.is_file():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["key_sha256"]] = row
    pending = [key for key in keys if key_hash(key) not in done]
    print(f"{len(done)} keys already scored; {len(pending)} to score", flush=True)
    start = time.perf_counter()
    with raw_path.open("a", encoding="utf-8", newline="\n") as out:
        for index, key in enumerate(pending, 1):
            result = router.score_many([key], batch_size=1)[0]
            score = float(result["router_score"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Router score must be finite and between zero and one")
            row = {"key_sha256": key_hash(key), "router_score": score,
                   "input_tokens": int(result["input_tokens"]), "truncated": bool(result["truncated"])}
            out.write(json.dumps(row) + "\n")
            done[row["key_sha256"]] = row
            if index % 500 == 0 or index == len(pending):
                out.flush()
                rate = index / (time.perf_counter() - start)
                print(f"scored {index}/{len(pending)} ({rate:.1f}/s, ~{(len(pending) - index) / rate / 60:.0f} min left)",
                      flush=True)
    return {key: done[key_hash(key)] for key in keys}


def weighted_midgap(scores, weights, target=TARGET):
    """Weighted version of calibrate_midgap: same candidates, same tie-breaks, boundary between groups."""
    scores, weights = np.asarray(scores, dtype=float), np.asarray(weights, dtype=float)
    if not len(scores) or not np.all(np.isfinite(scores)) or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Expected nonempty finite scores between zero and one")
    total = weights.sum()
    candidates = np.unique(np.concatenate([[0.0, math.nextafter(1.0, math.inf)], scores]))
    order = np.argsort(scores)
    sorted_scores, sorted_weights = scores[order], weights[order]
    # Weight at or above each candidate: total minus weight strictly below it.
    below = np.concatenate([[0.0], np.cumsum(sorted_weights)])[np.searchsorted(sorted_scores, candidates, "left")]
    shares = (total - below) / total
    best = min(range(len(candidates)), key=lambda i: (abs(shares[i] - target), shares[i], -candidates[i]))
    cut = float(candidates[best])
    lower, upper = scores[scores < cut], scores[scores >= cut]
    if len(lower) and len(upper):
        low, high = float(lower.max()), float(upper.min())
        middle = low + (high - low) / 2
        cut = middle if low < middle <= high else high
    return {"threshold": cut, "threshold_rule": "weighted_midgap", "target_strong_share": target,
            "strong_share_of_requests": float(weights[scores >= cut].sum() / total)}


def share(strong, weights):
    return float(np.sum(weights * strong) / np.sum(weights))


def estimates(s, w, c, rep, cut, misses=None):
    """Point estimates for one set of scored keys (arrays are aligned)."""
    strong = (s >= cut).astype(float)
    off = share(strong, w * c)
    on = share(strong, w)  # never-evicting exact cache: every unique key reaches the router once
    # Key-level comparisons: each unique key once, weighted back to its stratum's population.
    out = {"cache_off_share": off, "unbounded_cache_on_share": on, "unbounded_drift": on - off,
           "mean_score_repeated": share(s[rep], w[rep]), "mean_score_one_off": share(s[~rep], w[~rep]),
           "share_above_cutoff_repeated": share(strong[rep], w[rep]),
           "share_above_cutoff_one_off": share(strong[~rep], w[~rep])}
    out["score_gap"] = out["mean_score_repeated"] - out["mean_score_one_off"]
    out["share_gap"] = out["share_above_cutoff_repeated"] - out["share_above_cutoff_one_off"]
    if misses is not None:
        out["lru_drift"] = share(strong, w * misses) - off
    return out


def bootstrap(s, w, c, rep, strata, cut, samples=SAMPLES, seed=SEED):
    """Resample prompt groups within each sampling stratum; cutoff held fixed (as in Sprint 1)."""
    rng = np.random.default_rng(seed)
    pools = [np.flatnonzero(strata == name) for name in np.unique(strata)]
    names = ("unbounded_drift", "score_gap", "share_gap")
    draws = {name: [] for name in names}
    for _ in range(samples):
        idx = np.concatenate([rng.choice(pool, len(pool)) for pool in pools])
        point = estimates(s[idx], w[idx], c[idx], rep[idx], cut)
        for name in names:
            draws[name].append(point[name])
    return {name: [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
            for name, values in draws.items()}


def decide(interval, line=DECISION_LINE):
    low, high = interval
    if low > line or high < -line:
        return "drift matters in real traffic (A2 holds)"
    if low > -line and high < line:
        return "drift too small to matter at this traffic's repeat rate (A2, real traffic, fails)"
    return "inconclusive"


def analyze(groups, scored, weights, keep=lambda key: True, count_of=None, misses_by_order=None,
            samples=SAMPLES):
    """Design weights (stratum size / keys scored) make any kept subset an unbiased estimate.

    count_of(key) gives the requests a key stands for (default: its group size); a sensitivity check can
    change it, e.g. counting size-2 groups as one request.
    """
    count_of = count_of or groups.__getitem__
    rows = [(key, row) for key, row in scored.items() if keep(key)]
    strata = np.array([stratum_of(groups[key]) for key, _ in rows])
    w = np.array([weights[name] for name in strata])
    s = np.array([row["router_score"] for _, row in rows])
    c = np.array([count_of(key) for key, _ in rows], dtype=float)
    rep = c >= 2
    if not rep.any() or rep.all():
        raise ValueError("Need scored keys that repeat and keys that do not")
    calibration = weighted_midgap(s, w * c)
    cut = calibration["threshold"]
    point = estimates(s, w, c, rep, cut)
    intervals = bootstrap(s, w, c, rep, strata, cut, samples)
    result = {"scored_keys": {name: int((strata == name).sum()) for name in ("multi", "pair", "one_off")},
              "estimated_keys": {"repeated": float(w[rep].sum()), "one_off": float(w[~rep].sum())},
              "calibration": calibration, "estimates": point, "intervals_95": intervals,
              "decision": decide(intervals["unbounded_drift"]),
              "truncated_scored": int(sum(row["truncated"] for _, row in rows)),
              "truncated_share_of_requests": share(np.array([row["truncated"] for _, row in rows], dtype=float),
                                                   w * c)}
    if misses_by_order:
        lru = []
        for (fraction, order_seed), misses in misses_by_order.items():
            m = np.array([misses.get(key, 0) for key, _ in rows], dtype=float)
            lru.append({"capacity_fraction": fraction, "order_seed": order_seed,
                        "drift": estimates(s, w, c, rep, cut, m)["lru_drift"]})
        result["lru"] = lru
    return result


def lru_miss_counts(keys, n_unique, fractions=CAPACITY_FRACTIONS, seeds=LRU_SEEDS):
    out = {}
    for fraction in fractions:
        capacity = max(1, round(n_unique * fraction))
        for seed in seeds:
            stream = list(keys)
            random.Random(seed).shuffle(stream)
            out[(fraction, seed)] = Counter(lru_misses(stream, capacity))
            print(f"LRU {fraction:.0%} order {seed}: {sum(out[(fraction, seed)].values())} misses", flush=True)
    return out


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


SENSITIVITY_LABELS = {
    "without_name_tags": "Without keys containing NAME_n tags",
    "pairs_as_one_request": "Size-2 groups counted as one request (possible Arena pairs)",
    "without_automated": f"Without keys repeated more than {AUTOMATED_OVER} times (possible automated traffic)",
}


def sensitivity(groups, scored, weights, samples=SAMPLES):
    return {
        "without_name_tags": analyze(groups, scored, weights, keep=lambda key: not NAME_TAG.search(key),
                                     samples=samples),
        "pairs_as_one_request": analyze(groups, scored, weights,
                                        count_of=lambda key: 1 if groups[key] == 2 else groups[key],
                                        samples=samples),
        "without_automated": analyze(groups, scored, weights, keep=lambda key: groups[key] <= AUTOMATED_OVER,
                                     samples=samples),
    }


def pct(value):
    return f"{value * 100:+.1f}"


def markdown(report):
    main, rate = report["main"], report["traffic"]
    est, ci = main["estimates"], main["intervals_95"]
    lines = [
        "# Real-traffic drift check (#36)", "",
        f"Plan: `{report['plan_file']}` (SHA-256 `{report['plan_sha256'][:12]}…`). "
        "Generated by `python -m cacheshift.real_traffic`; no LMSYS text is included.", "",
        "## Traffic", "",
        f"- Conversations: {rate['conversations']:,}; English first messages used: {rate['requests']:,} "
        f"(non-English share {rate['non_english_share']:.1%})",
        f"- Unique keys: {rate['unique_keys']:,}; repeated groups: {rate['repeated_groups']:,}",
        f"- Repeat rate (requests that repeat an earlier key): {rate['repeat_rate']:.2%}", "",
        "## Result", "",
        f"- **Drift, never-evicting exact cache: {pct(est['unbounded_drift'])} points "
        f"[{pct(ci['unbounded_drift'][0])}, {pct(ci['unbounded_drift'][1])}]**",
        f"- **Decision: {main['decision']}**",
        f"- Mean router score, repeated minus one-off: {est['score_gap']:+.4f} "
        f"[{ci['score_gap'][0]:+.4f}, {ci['score_gap'][1]:+.4f}]",
        f"- Share above the cutoff, repeated minus one-off: {pct(est['share_gap'])} points "
        f"[{pct(ci['share_gap'][0])}, {pct(ci['share_gap'][1])}]",
        f"- Cutoff {main['calibration']['threshold']:.6f}; cache-off strong share {est['cache_off_share']:.2%}", "",
        "## LRU caches (secondary)", "",
        "| Capacity | Drift by stream order (points) |", "|---|---|"]
    for fraction in report["capacity_fractions"]:
        drifts = [row["drift"] for row in main["lru"] if row["capacity_fraction"] == fraction]
        lines.append(f"| {fraction:.0%} of unique keys | " + ", ".join(pct(d) for d in drifts)
                     + f" (range {pct(min(drifts))} to {pct(max(drifts))}) |")
    lines += ["", "## Sensitivity (not used for the decision)", ""]
    for label, sens in report["sensitivity"].items():
        lines.append(f"- {SENSITIVITY_LABELS[label]}: drift {pct(sens['estimates']['unbounded_drift'])} points "
                     f"[{pct(sens['intervals_95']['unbounded_drift'][0])}, "
                     f"{pct(sens['intervals_95']['unbounded_drift'][1])}], "
                     f"score gap {sens['estimates']['score_gap']:+.4f}")
    lines += [f"- Scored prompts truncated at 512 tokens: {main['truncated_scored']:,} "
              f"(about {main['truncated_share_of_requests']:.1%} of requests)", ""]
    return "\n".join(lines)


def run(run_dir, router, data_dir=DEFAULT_DATA, plan=PLAN, samples=SAMPLES):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    plan = Path(plan)
    if not plan.is_file():
        raise FileNotFoundError("The committed plan must exist before scoring")
    keys, counts, files = load_requests(data_dir)
    groups = Counter(keys)
    sampled, weights = sample_keys(groups)
    print(f"{counts['requests']:,} English requests, {len(groups):,} unique keys; scoring "
          + ", ".join(f"{len(keys_):,} {name}" for name, keys_ in sampled.items()), flush=True)
    scored = score_keys([key for name in ("multi", "pair", "one_off") for key in sampled[name]],
                        router, run_dir / "raw" / "scores.jsonl")
    misses = lru_miss_counts(keys, len(groups))
    report = {
        "scope": "LMSYS-Chat-1M English first user messages; exact-match repeats; router scores only "
                 "(no answer quality)",
        "plan_file": plan.name, "plan_sha256": sha256_file(plan),
        "data_files": [{"name": path.name, "sha256": sha256_file(path)} for path in files],
        "router": {"checkpoint": CHECKPOINT, "revision": REVISION, "scoring_mode": "single", "device": "cpu",
                   "packages": {name: importlib.metadata.version(name)
                                for name in ("torch", "transformers", "tokenizers")},
                   "python": platform.python_version(), "platform": platform.platform()},
        "seed": SEED, "lru_seeds": list(LRU_SEEDS), "capacity_fractions": list(CAPACITY_FRACTIONS),
        "bootstrap_samples": samples, "decision_line": DECISION_LINE,
        "sampling": {"scored": {name: len(keys_) for name, keys_ in sampled.items()}, "weights": weights},
        "traffic": {**counts, "non_english_share": counts.get("other_language", 0) / counts["conversations"],
                    "unique_keys": len(groups),
                    "repeated_groups": sum(count >= 2 for count in groups.values()),
                    "size_2_groups": sum(count == 2 for count in groups.values()),
                    "largest_group": max(groups.values()),
                    "requests_in_repeated_groups": sum(count for count in groups.values() if count >= 2),
                    "repeat_rate": (len(keys) - len(groups)) / len(keys)},
        "main": analyze(groups, scored, weights, misses_by_order=misses, samples=samples),
        "sensitivity": sensitivity(groups, scored, weights, samples),
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    (run_dir / "report.md").write_text(markdown(report), encoding="utf-8", newline="\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/routellm")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    from cacheshift.router import LocalBERTRouter

    report = run(args.run_dir, LocalBERTRouter(args.cache_dir, threads=args.threads), args.data_dir)
    main_result = report["main"]
    print("Drift (never-evicting cache):", main_result["estimates"]["unbounded_drift"],
          main_result["intervals_95"]["unbounded_drift"])
    print("Decision:", main_result["decision"])


if __name__ == "__main__":
    main()
