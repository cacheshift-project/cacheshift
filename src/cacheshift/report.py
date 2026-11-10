"""Issue #48: turn a gateway run log into the one-page CacheShift report.

    python -m cacheshift.report --log run/cacheshift.jsonl [--fresh-log run/no_cache.jsonl] \
        [--planned-share 0.5 | --config run/report.json] --out run/report.html

Reads the gateway's request log (one JSON object per request) and the replay dataset
(for official answer keys, question groups and the strong model's price). It writes:

- a one-page HTML report in the layout of the Sprint 2 mock-up (cost and quality kept
  separate, every rate with a 95% range),
- a JSON file with every number, and
- a short plain-text summary on the terminal.

Ranges are 95% percentile bootstrap intervals over question groups (2,000 resamples), so
repeats of the same question move together. With --fresh-log (the same question stream
run without the cache), accuracy and expensive-model share are also compared pairwise
against fresh answers. Costs are historical estimates, as recorded by the replay gateway.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sys

import numpy as np

from cacheshift.gateway import DATASET
from cacheshift.replay_gateway import STRONG, load_dataset
from cacheshift.retune import is_correct

SAMPLES = 2000
SEED = 601
# Per-group totals, in this order.
FIELDS = ("requests", "hits", "routed", "strong", "correct", "cost", "all_strong_cost",
          "wrong_question", "wrong_question_wrong", "repeated_wrong")
EXAMPLES = 5


def read_log(path):
    events = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        for key in ("question_id", "cache_hit", "route", "answer", "cost_usd"):
            if key not in event:
                raise ValueError(f"{path}:{number} is missing '{key}'; is this a gateway request log?")
        events.append(event)
    if not events:
        raise ValueError(f"{path} has no requests")
    configs = {event.get("config_id") for event in events}
    if len(configs) > 1:
        raise ValueError(f"{path} mixes {len(configs)} gateway configurations; report one run at a time")
    return events


def classify(event, records):
    """(correct, wrong_question, repeated_wrong) for one request."""
    row = records[event["question_id"]]
    correct = is_correct(row, event["answer"])
    matched = event.get("matched_question_id") or event["question_id"]
    wrong_question = bool(event["cache_hit"]) and matched != event["question_id"]
    repeated_wrong = bool(event["cache_hit"]) and not wrong_question and not correct
    return correct, wrong_question, repeated_wrong


def group_totals(events, records):
    groups = defaultdict(lambda: np.zeros(len(FIELDS)))
    for event in events:
        row = records.get(event["question_id"])
        if row is None:
            raise ValueError(f"Question {event['question_id']} is not in the dataset; use the run's --dataset")
        correct, wrong_question, repeated_wrong = classify(event, records)
        groups[row["group_id"]] += [1, event["cache_hit"], not event["cache_hit"], event["route"] == "strong",
                                    correct, event["cost_usd"], row["answers"][STRONG]["cost_usd"],
                                    wrong_question, wrong_question and not correct, repeated_wrong]
    return groups


def rates(t):
    """Report quantities from totals; t has FIELDS on its last axis (works on bootstrap draws too)."""
    f = dict(zip(FIELDS, np.moveaxis(t, -1, 0)))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "hit_rate": f["hits"] / f["requests"],
            "accuracy": f["correct"] / f["requests"],
            "wrong_question_rate": f["wrong_question"] / f["requests"],
            "wrong_question_wrong_rate": f["wrong_question_wrong"] / f["requests"],
            "repeated_wrong_rate": f["repeated_wrong"] / f["requests"],
            "strong_share_of_routed": f["strong"] / f["routed"],
            "usd_per_1000": 1000 * f["cost"] / f["requests"],
            "all_strong_usd_per_1000": 1000 * f["all_strong_cost"] / f["requests"],
            "saving_vs_all_strong": 1 - f["cost"] / f["all_strong_cost"],
        }


def interval(estimate, draws):
    draws = draws[np.isfinite(draws)]
    low, high = (np.quantile(draws, [0.025, 0.975]).tolist() if draws.size else (None, None))
    return {"estimate": None if not np.isfinite(estimate) else float(estimate), "ci95": [low, high]}


def bootstrap(groups, keys, seed=SEED, samples=SAMPLES):
    """Resample question groups; groups maps name -> {group_id: totals}, all over the same keys."""
    generator = np.random.default_rng(seed)
    index = generator.integers(0, len(keys), size=(samples, len(keys)))
    out = {}
    for name, values in groups.items():
        array = np.array([values.get(key, np.zeros(len(FIELDS))) for key in keys])
        out[name] = (rates(array.sum(axis=0)), rates(array[index].sum(axis=1)))
    return out


def build(events, records, planned_share, fresh_events=None, seed=SEED, samples=SAMPLES):
    cached = group_totals(events, records)
    groups = {"cached": cached}
    if fresh_events is not None:
        fresh = group_totals(fresh_events, records)
        if set(fresh) != set(cached):
            raise ValueError("The fresh log must cover the same question groups as the cached run")
        if len(fresh_events) != len(events):
            raise ValueError("The fresh log must replay the same number of requests as the cached run")
        groups["fresh"] = fresh
    keys = sorted(cached)
    boot = bootstrap(groups, keys, seed, samples)
    point, draws = boot["cached"]
    totals = dict(zip(FIELDS, np.array([cached[key] for key in keys]).sum(axis=0).tolist()))
    report = {"rates": {name: interval(point[name], draws[name]) for name in point},
              "totals": {key: (int(value) if key not in ("cost", "all_strong_cost") else value)
                         for key, value in totals.items()},
              "planned_strong_share": planned_share, "question_groups": len(keys),
              "bootstrap_samples": samples}
    if planned_share is not None:
        report["rates"]["drift_from_plan"] = interval(point["strong_share_of_routed"] - planned_share,
                                                      draws["strong_share_of_routed"] - planned_share)
    if fresh_events is not None:
        fresh_point, fresh_draws = boot["fresh"]
        report["fresh"] = {name: interval(fresh_point[name], fresh_draws[name])
                           for name in ("accuracy", "strong_share_of_routed", "usd_per_1000")}
        report["paired"] = {
            "accuracy_change": interval(point["accuracy"] - fresh_point["accuracy"],
                                        draws["accuracy"] - fresh_draws["accuracy"]),
            "strong_share_change": interval(point["strong_share_of_routed"] - fresh_point["strong_share_of_routed"],
                                            draws["strong_share_of_routed"] - fresh_draws["strong_share_of_routed"]),
        }
    report["examples"] = wrong_question_examples(events, records)
    return report


def wrong_question_examples(events, records, limit=EXAMPLES):
    seen, examples = set(), []
    for event in events:
        correct, wrong_question, _ = classify(event, records)
        if not wrong_question or correct:
            continue
        pair = (event["question_id"], event.get("matched_question_id"))
        if pair in seen:
            continue
        seen.add(pair)
        matched = records.get(event.get("matched_question_id"), {})
        examples.append({"question_id": event["question_id"], "question": first_line(records[event["question_id"]]["text"]),
                         "matched_question_id": event.get("matched_question_id"),
                         "matched_question": first_line(matched.get("text", "")),
                         "similarity": event.get("similarity"), "served_answer": event["answer"],
                         "correct_answer": records[event["question_id"]]["gold_answer"]})
        if len(examples) == limit:
            break
    return examples


def first_line(text, width=140):
    line = text.strip().split("\n")[0]
    return line if len(line) <= width else line[:width - 1] + "…"


# ---------- presentation ----------

def pct(value, digits=1):
    return "n/a" if value is None else f"{100 * value:.{digits}f}%"


def pts(value, digits=1):
    return "n/a" if value is None else f"{100 * value:+.{digits}f}"


def money(value):
    return "n/a" if value is None else f"${value:,.2f}"


def rng(entry, fmt):
    low, high = entry["ci95"]
    return "" if low is None else f"likely {fmt(low)} to {fmt(high)}"


def text_summary(report, title):
    r = report["rates"]
    lines = [title,
             f"Requests: {report['totals']['requests']:,} ({report['question_groups']:,} question groups)",
             f"Cost per 1,000 requests: {money(r['usd_per_1000']['estimate'])} ({rng(r['usd_per_1000'], money)}); "
             f"all-strong would be {money(r['all_strong_usd_per_1000']['estimate'])}, "
             f"saving {pct(r['saving_vs_all_strong']['estimate'])}",
             f"Answered from the cache: {pct(r['hit_rate']['estimate'])} ({rng(r['hit_rate'], pct)})",
             f"Correct answers: {pct(r['accuracy']['estimate'])} ({rng(r['accuracy'], pct)})",
             f"Saved answer given to a different question: {pct(r['wrong_question_rate']['estimate'], 2)} "
             f"({rng(r['wrong_question_rate'], lambda v: pct(v, 2))}); wrong as a result: "
             f"{pct(r['wrong_question_wrong_rate']['estimate'], 2)}",
             f"Wrong answers repeated from the cache: {pct(r['repeated_wrong_rate']['estimate'], 2)}",
             f"Expensive-model share of routed requests: {pct(r['strong_share_of_routed']['estimate'])} "
             f"({rng(r['strong_share_of_routed'], pct)})"]
    if report["planned_strong_share"] is not None:
        lines.append(f"  plan {pct(report['planned_strong_share'])}; drift {pts(r['drift_from_plan']['estimate'])} points "
                     f"({rng(r['drift_from_plan'], pts)})")
    if "paired" in report:
        p = report["paired"]
        lines.append(f"Versus fresh answers (same stream, no cache): accuracy {pts(p['accuracy_change']['estimate'])} points "
                     f"({rng(p['accuracy_change'], pts)}); expensive-model share {pts(p['strong_share_change']['estimate'])} "
                     f"points ({rng(p['strong_share_change'], pts)})")
    return "\n".join(lines)


CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d1f24;--muted:#5d6270;--line:#e3e1da;--good:#1f7a4d;--good-bg:#e7f4ec;
--warn:#9a5b00;--warn-bg:#fdf1dc;--bad:#a3272b;--bad-bg:#fbe7e7;--accent:#2a4d8f}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171c;--card:#1e2128;--ink:#eceef2;
--muted:#a2a8b6;--line:#30343e;--good:#6fd19c;--good-bg:#1c3428;--warn:#f0b860;--warn-bg:#3a2e18;--bad:#f28b8f;
--bad-bg:#3d2224;--accent:#8fb0ee}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 40px}.note{color:var(--muted);font-size:13px}
h1{font-size:24px;margin:0 0 2px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.full{grid-column:1/-1}
.card h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.big{font-size:34px;font-weight:700;line-height:1.1}.range{color:var(--muted);font-size:13px}
.row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}.row b{white-space:nowrap}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600;margin:10px 0 4px}
.good{background:var(--good-bg);color:var(--good)}.warn{background:var(--warn-bg);color:var(--warn)}
.bad{background:var(--bad-bg);color:var(--bad)}.ex{border-left:3px solid var(--bad);padding:6px 0 6px 12px;margin:10px 0}
.ex .a{color:var(--muted);font-size:14px}footer{margin-top:18px;font-size:12.5px;color:var(--muted)}
@media (max-width:640px){.grid{grid-template-columns:1fr}.big{font-size:28px}}
@media print{body{background:#fff}.card{break-inside:avoid}}
"""


def render_html(report, title, source):
    e = html.escape
    r, t = report["rates"], report["totals"]

    def row(label, value):
        return f'<div class="row"><span>{label}</span><b>{value}</b></div>'

    saving = r["saving_vs_all_strong"]["estimate"]
    quality_pill = ""
    if "paired" in report:
        change = report["paired"]["accuracy_change"]
        cls = "good" if change["ci95"][0] is not None and change["ci95"][0] >= -0.005 else "warn"
        quality_pill = (f'<span class="pill {cls}">{pts(change["estimate"])} points vs fresh answers</span> '
                        f'<span class="range">({rng(change, pts)})</span>')
    plan = ""
    if report["planned_strong_share"] is not None:
        drift = r["drift_from_plan"]
        low, high = drift["ci95"]
        off = low is not None and (low > 0 or high < 0)
        cls = "warn" if off else "good"
        verdict = "Drifted from your plan" if off else "No clear drift from your plan"
        plan = (f'<section class="card full"><h2>Is the expensive-model share where you set it?</h2>'
                f'<span class="pill {cls}">{verdict}: {pct(r["strong_share_of_routed"]["estimate"])} '
                f'vs planned {pct(report["planned_strong_share"])}</span>'
                + row("Change from plan, percentage points",
                      f'{pts(drift["estimate"])} <span class="range">({rng(drift, pts)})</span>'))
        if "paired" in report:
            plan += row("Change caused by the cache (vs the same stream with no cache)",
                        f'{pts(report["paired"]["strong_share_change"]["estimate"])} '
                        f'<span class="range">({rng(report["paired"]["strong_share_change"], pts)})</span>')
        plan += "</section>"
    examples = "".join(
        f'<div class="ex"><div><b>{e(x["question"])}</b></div><div class="a">got the saved answer for '
        f'“{e(x["matched_question"])}” (similarity {x["similarity"]:.2f}): answered {e(str(x["served_answer"]))}, '
        f'correct answer {e(x["correct_answer"])}</div></div>' if isinstance(x.get("similarity"), (int, float)) else ""
        for x in report["examples"])
    if not examples:
        examples = '<p class="range">None in this run.</p>'
    fresh = ""
    if "fresh" in report:
        fresh = row("Fresh answers, no cache", pct(report["fresh"]["accuracy"]["estimate"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CacheShift Report</title><style>{CSS}</style></head><body><main>
<h1>{e(title)}</h1>
<p class="note">{t["requests"]:,} requests · {report["question_groups"]:,} question groups · source: {e(source)}</p>
<div class="grid">
<section class="card"><h2>Cost</h2>
<div class="big">{money(r["usd_per_1000"]["estimate"])}</div><div class="range">per 1,000 requests · {rng(r["usd_per_1000"], money)}</div>
<span class="pill good">{pct(saving)} less than sending everything to the expensive model</span>
{row("Everything to the expensive model", money(r["all_strong_usd_per_1000"]["estimate"]) + " per 1,000")}
{row("Answered from the cache (free)", f'{t["hits"]:,} ({pct(r["hit_rate"]["estimate"])})')}
{row("Sent to the expensive model", f'{t["strong"]:,}')}
{row("Sent to the cheap model", f'{t["routed"] - t["strong"]:,}')}
</section>
<section class="card"><h2>Answer quality</h2>
<div class="big">{pct(r["accuracy"]["estimate"])}</div><div class="range">of answers correct · {rng(r["accuracy"], pct)}</div>
{quality_pill}
{fresh}
{row("Saved answer given to a <i>different</i> question", f'{t["wrong_question"]:,} ({pct(r["wrong_question_rate"]["estimate"], 2)})')}
{row("… and wrong as a result", f'{t["wrong_question_wrong"]:,} ({pct(r["wrong_question_wrong_rate"]["estimate"], 2)})')}
{row('Wrong answers repeated from the cache <span class="range">(already wrong when first given)</span>',
     f'{t["repeated_wrong"]:,} ({pct(r["repeated_wrong_rate"]["estimate"], 2)})')}
</section>
{plan}
<section class="card full"><h2>Answers to check: saved answer served to a different question</h2>{examples}</section>
</div>
<footer>Ranges are 95% bootstrap intervals over question groups ({report.get("bootstrap_samples", SAMPLES):,} resamples). Cost and quality are shown
separately and never combined into one score. "Correct" means the answer matches the question's official answer key.
Costs are historical estimates recorded by the replay gateway. Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.</footer>
</main></body></html>
"""


def planned_share_from(config_path):
    report = json.loads(Path(config_path).read_text(encoding="utf-8"))
    runs = report.get("runs")
    candidates = [report.get("config")] + ([run.get("config") for run in runs.values()] if isinstance(runs, dict) else [])
    for candidate in candidates:
        if isinstance(candidate, dict) and "target_strong_share" in candidate:
            return candidate["target_strong_share"]
    raise ValueError(f"No target_strong_share found in {config_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log", type=Path, required=True, help="Gateway request log (JSONL) with the cache on")
    parser.add_argument("--fresh-log", type=Path, help="Optional: the same question stream with no cache, for paired comparisons")
    parser.add_argument("--dataset", type=Path, default=DATASET, help="Replay dataset the run used")
    plan = parser.add_mutually_exclusive_group()
    plan.add_argument("--planned-share", type=float, help="Planned expensive-model share, e.g. 0.5")
    plan.add_argument("--config", type=Path, help="Run report.json holding the gateway config (target_strong_share)")
    parser.add_argument("--out", type=Path, required=True, help="HTML report to write; a .json file is written next to it")
    parser.add_argument("--title", default="Your AI assistant: CacheShift report")
    args = parser.parse_args(argv)
    try:
        records = load_dataset(args.dataset)
        planned = args.planned_share if args.planned_share is not None else (
            planned_share_from(args.config) if args.config else None)
        if planned is not None and not 0 <= planned <= 1:
            raise ValueError("--planned-share must be between 0 and 1")
        events = read_log(args.log)
        fresh = read_log(args.fresh_log) if args.fresh_log else None
        report = build(events, records, planned, fresh)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Could not build the report: {exc}\n")
    report["inputs"] = {"log": args.log.name, "log_sha256": hashlib.sha256(args.log.read_bytes()).hexdigest(),
                        "fresh_log": args.fresh_log.name if args.fresh_log else None,
                        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                        "seed": SEED}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(report, args.title, args.log.name), encoding="utf-8", newline="\n")
    args.out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(text_summary(report, args.title))
    print(f"Wrote {args.out} and {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    sys.exit(main())
