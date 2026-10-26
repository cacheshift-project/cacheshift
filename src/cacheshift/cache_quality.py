"""Story 2: what does a cached answer cost in quality?

Replays a question stream through a cache at several similarity settings and grades
every served answer against the benchmark's official answer key. Each cache hit is
labelled automatically:

  hit_ok           matched the same question; the stored answer is right
  inherited_error  matched the same question; the stored answer was already wrong
  false_hit        matched a different question (split into lucky/right and error/wrong)

"Same question" means the same item, or a rewording of it (same group, not both
originals). Two original benchmark items that share a stem are different questions.

Run: python -m cacheshift.cache_quality --run-dir experiments/results/cache-quality-<date>
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

import numpy as np

from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import STRONG, WEAK
from cacheshift.retune import SEEDS, is_correct
from cacheshift.semantic_cache import EMBEDDING_MODEL, SemanticCache

DATASET = ROOT / "data/retune_holdout_20261007/questions.jsonl"
SETTINGS = (None, 0.98, 0.95, 0.90, 0.85, 0.80)  # None = exact-text cache
MODELS = (STRONG, WEAK)
COUNTS = ("requests", "hits", "false_hits", "false_hit_errors", "inherited_errors",
          "correct_with_cache", "correct_fresh")


def setting_name(threshold):
    return "exact" if threshold is None else f"cos>={threshold:.2f}"


def load_records(path):
    records = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["question_id"] in records:
                raise ValueError("Duplicate question_id")
            records[row["question_id"]] = row
    if not records:
        raise ValueError("Empty dataset")
    return records


def request_stream(records, seed, repeat_fraction=0.5):
    """Every question once, plus repeats drawn uniformly, shuffled. Same rule as retune."""
    if not 0 <= repeat_fraction < 1:
        raise ValueError("repeat_fraction must be in [0, 1)")
    ids = sorted(records)
    rng = random.Random(seed)
    stream = ids + rng.choices(ids, k=round(len(ids) * repeat_fraction / (1 - repeat_fraction)))
    rng.shuffle(stream)
    return stream


def same_question(query, match):
    if query["question_id"] == match["question_id"]:
        return True
    return query["group_id"] == match["group_id"] and not (query["is_original"] and match["is_original"])


def replay(records, stream, cache, model):
    """Serve the stream through one cache. Misses get the model's recorded answer and are stored."""
    events = []
    for qid in stream:
        row = records[qid]
        fresh = row["answers"][model]["answer"]
        entry, similarity = cache.lookup(row["text"])
        hit = entry is not None
        if hit:
            served, matched = entry["answer"], entry["question_id"]
        else:
            served, matched = fresh, qid
            cache.insert(row["text"], {"question_id": qid, "answer": fresh})
        same = same_question(row, records[matched])
        correct = is_correct(row, served)
        if not hit:
            label = "miss"
        elif same:
            label = "hit_ok" if correct else "inherited_error"
        else:
            label = "false_hit_lucky" if correct else "false_hit_error"
        events.append({"question_id": qid, "matched_question_id": matched, "similarity": similarity,
                       "cache_hit": hit, "served_answer": served, "correct": correct,
                       "fresh_correct": is_correct(row, fresh), "label": label})
    return events


def group_counts(events, records):
    totals = defaultdict(lambda: np.zeros(len(COUNTS)))
    for event in events:
        label = event["label"]
        totals[records[event["question_id"]]["group_id"]] += [
            1, event["cache_hit"], label.startswith("false_hit"), label == "false_hit_error",
            label == "inherited_error", event["correct"], event["fresh_correct"]]
    return totals


def rates(sums):
    requests, hits, false_hits, false_errors, inherited, correct, fresh = np.moveaxis(sums, -1, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {
            "hit_rate": hits / requests,
            "false_hit_rate": false_hits / requests,
            "false_hits_per_hit": np.where(hits > 0, false_hits / np.maximum(hits, 1), np.nan),
            "false_hit_error_rate": false_errors / requests,
            "inherited_error_rate": inherited / requests,
            "wrong_cached_answer_rate": (false_errors + inherited) / requests,
            "accuracy_with_cache": correct / requests,
            "accuracy_fresh": fresh / requests,
            "accuracy_change": (correct - fresh) / requests,
        }


def summarize(events, records, seed, samples=2000):
    """Point estimates and 95% percentile bootstrap intervals, resampling question groups."""
    totals = group_counts(events, records)
    groups = sorted(totals)
    array = np.array([totals[group] for group in groups])
    point = rates(array.sum(axis=0))
    picks = np.random.default_rng(seed).integers(0, len(groups), size=(samples, len(groups)))
    draws = rates(array[picks].sum(axis=1))
    report = {"counts": dict(zip(COUNTS, (int(x) for x in array.sum(axis=0))))}
    for name, value in point.items():
        lo, hi = np.nanquantile(draws[name], [0.025, 0.975])
        report[name] = {"estimate": None if np.isnan(value) else float(value),
                        "ci95": [float(lo), float(hi)] if np.isfinite([lo, hi]).all() else None}
    return report


def nearest_other_similarity(records, embed):
    """For each question, its highest cosine similarity to a *different* question."""
    ids = sorted(records)
    matrix = np.stack([embed(records[qid]["text"]) for qid in ids])
    sims = matrix @ matrix.T
    for i, qid in enumerate(ids):
        for j, other in enumerate(ids):
            if i == j or same_question(records[qid], records[other]):
                sims[i, j] = -1.0
    best = sims.max(axis=1)
    return {f"p{q}": float(np.percentile(best, q)) for q in (50, 90, 99)} | {"max": float(best.max())}


def run(records, embed, run_dir, digest, settings=SETTINGS, models=MODELS, seeds=SEEDS,
        repeat_fraction=0.5, samples=2000):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "purpose": "Story 2 (#4): quality of cached answers, graded against official answer keys",
        "dataset_sha256": digest, "embedding_model": getattr(embed, "model_name", "custom"),
        "models": list(models), "settings": [setting_name(t) for t in settings], "seeds": list(seeds),
        "repeat_fraction": repeat_fraction, "bootstrap_samples": samples,
        "ci_method": "95% percentile bootstrap over question groups, paired within each run",
        "labels": "Automatic. Validated by a human hand check of 50 hits (tools/hand_check.py).",
        "limitations": ("Replay mode: re-asking a question returns the identical recorded answer, so inherited "
                        "errors cost no accuracy versus a fresh call here; with live models they can. Uniform "
                        "repeats and no rewordings yet. Full prompts are embedded, including shared instructions."),
        "nearest_other_question_similarity": nearest_other_similarity(records, embed),
        "runs": [],
    }
    for seed in seeds:
        stream = request_stream(records, seed, repeat_fraction)
        for model in models:
            for threshold in settings:
                events = replay(records, stream, SemanticCache(embed, threshold), model)
                if seed == seeds[0]:
                    hits = [dict(e, model=model, setting=setting_name(threshold)) for e in events if e["cache_hit"]]
                    (run_dir / "raw").mkdir(exist_ok=True)
                    with (run_dir / "raw" / f"hits-{seed}.jsonl").open("a", encoding="utf-8", newline="\n") as out:
                        out.writelines(json.dumps(h) + "\n" for h in hits)
                report["runs"].append({"seed": seed, "model": model, "setting": setting_name(threshold),
                                       **summarize(events, records, seed, samples)})
        print(f"Completed seed {seed}", flush=True)
    hits_file = run_dir / "raw" / f"hits-{seeds[0]}.jsonl"
    report["hits_file"] = {"path": str(hits_file.relative_to(run_dir)),
                           "sha256": hashlib.sha256(hits_file.read_bytes()).hexdigest(),
                           "note": "Every cache hit for the first seed; kept local (gitignored), used for the hand check"}
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def pct(metric):
    if metric["estimate"] is None:
        return "–"
    ci = metric["ci95"]
    return f"{100 * metric['estimate']:.1f}% [{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]" if ci else f"{100 * metric['estimate']:.1f}%"


def markdown(report):
    seed = report["seeds"][0]
    lines = [f"# Cache quality (Story 2), seed {seed}", "",
             "Rates are per request; brackets are 95% bootstrap intervals over question groups.", "",
             "| Model | Cache | Hit rate | False hits | False-hit errors | Inherited errors | Accuracy change vs fresh |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for run in report["runs"]:
        if run["seed"] == seed:
            lines.append(f"| {run['model']} | {run['setting']} | {pct(run['hit_rate'])} | {pct(run['false_hit_rate'])} | "
                         f"{pct(run['false_hit_error_rate'])} | {pct(run['inherited_error_rate'])} | {pct(run['accuracy_change'])} |")
    near = report["nearest_other_question_similarity"]
    lines += ["", f"Nearest *different* question, cosine similarity: median {near['p50']:.3f}, "
              f"90th percentile {near['p90']:.3f}, 99th {near['p99']:.3f}, max {near['max']:.3f}.",
              "", report["limitations"], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repeat-fraction", type=float, default=0.5)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/embeddings")
    args = parser.parse_args()
    from cacheshift.semantic_cache import SentenceEmbedder

    records = load_records(args.dataset)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(args.cache_dir))
    embed.warm(row["text"] for row in records.values())
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    run(records, embed, args.run_dir, digest, repeat_fraction=args.repeat_fraction)
    print((args.run_dir / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
