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
# Story 3 (#5): the real expensive-model share should be within this many points of plan.
DRIFT_BAND = 0.03
# The accuracy pill turns amber when the low end of the paired range is below this change.
ACCURACY_AMBER = -0.005
# #37/#5: the accuracy margin agreed for re-tuning (low end of the paired range).
RETUNE_MARGIN = -0.01
RETUNE_RATES = ("strong_share_of_routed", "accuracy", "usd_per_1000")


def read_log(path):
    events = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        for key in ("question_id", "cache_hit", "route", "answer", "cost_usd"):
            if key not in event:
                raise ValueError(f"{path}:{number} is missing '{key}'; is this a gateway request log?")
        if event["cache_hit"] and not event.get("matched_question_id"):
            raise ValueError(f"{path}:{number} is a cache hit without 'matched_question_id', so a saved answer "
                             "served to a different question could not be detected")
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
    if event["cache_hit"] and not event.get("matched_question_id"):
        raise ValueError(f"Cache hit for {event['question_id']} has no matched_question_id")
    wrong_question = bool(event["cache_hit"]) and event["matched_question_id"] != event["question_id"]
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


def retune_comparison(events, retuned_events, records, retune, planned_share, seed=SEED, samples=SAMPLES):
    """#49: the old and new cutoffs on the held-out question groups only, paired by group."""
    if len(retuned_events) != len(events):
        raise ValueError("The re-tuned log must replay the same number of requests as the cached run")
    if [e["question_id"] for e in retuned_events] != [e["question_id"] for e in events]:
        raise ValueError("The re-tuned log must replay the same question stream as the cached run")
    fitted = set(retune["fit_group_ids"])

    def held_out(stream):
        return [event for event in stream if records[event["question_id"]]["group_id"] not in fitted]

    before, after = group_totals(held_out(events), records), group_totals(held_out(retuned_events), records)
    if not before or set(before) != set(after):
        raise ValueError("The re-tune file's fit half leaves no held-out question groups in this run")
    keys = sorted(before)
    boot = bootstrap({"before": before, "after": after}, keys, seed, samples)
    (bp, bd), (ap, ad) = boot["before"], boot["after"]
    out = {"threshold_before": retune.get("previous_threshold"), "threshold_after": retune["threshold"],
           "held_out_groups": len(keys),
           "held_out_requests": int(np.array([before[key] for key in keys]).sum(axis=0)[FIELDS.index("requests")]),
           "before": {name: interval(bp[name], bd[name]) for name in RETUNE_RATES},
           "after": {name: interval(ap[name], ad[name]) for name in RETUNE_RATES},
           "change": {name: interval(ap[name] - bp[name], ad[name] - bd[name]) for name in RETUNE_RATES},
           "accuracy_margin": RETUNE_MARGIN}
    low = out["change"]["accuracy"]["ci95"][0]
    out["accuracy_range_above_margin"] = low is not None and low >= RETUNE_MARGIN - 1e-12
    if planned_share is not None:
        out["after_drift_from_plan"] = interval(ap["strong_share_of_routed"] - planned_share,
                                                ad["strong_share_of_routed"] - planned_share)
        out["before_drift_from_plan"] = interval(bp["strong_share_of_routed"] - planned_share,
                                                 bd["strong_share_of_routed"] - planned_share)
        estimate = out["after_drift_from_plan"]["estimate"]
        out["after_within_band"] = estimate is not None and abs(estimate) <= DRIFT_BAND + 1e-12
        out["after_band_verdict"] = band_verdict(out["after_drift_from_plan"])
    return out


def band_verdict(drift, band=DRIFT_BAND):
    """Where a drift from plan sits against the ±band, and whether its 95% range is narrow enough to say.

    within / outside: the estimate and its whole range are on that side of the band edge.
    within-unsure / outside-unsure: the estimate is on that side but the range crosses the band
    edge, so there are too few questions to tell."""
    estimate, (low, high) = drift["estimate"], drift["ci95"]
    if estimate is None or low is None:
        return None
    eps = 1e-12
    inside = abs(estimate) <= band + eps
    if inside:
        return "within" if -band - eps <= low and high <= band + eps else "within-unsure"
    return "outside" if high < -band - eps or low > band + eps else "outside-unsure"


VERDICT_WORDS = {
    "within": ("good", "Within {b} points of your plan"),
    "within-unsure": ("muted", "Within {b} points of your plan, but too few questions to be sure"),
    "outside": ("warn", "More than {b} points from your plan"),
    "outside-unsure": ("muted", "More than {b} points from your plan, but too few questions to be sure"),
}


def build(events, records, planned_share, fresh_events=None, seed=SEED, samples=SAMPLES,
          retuned_events=None, retune=None):
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
        drift = interval(point["strong_share_of_routed"] - planned_share,
                         draws["strong_share_of_routed"] - planned_share)
        report["rates"]["drift_from_plan"] = drift
        report["drift_band"] = DRIFT_BAND
        report["within_band"] = drift["estimate"] is not None and abs(drift["estimate"]) <= DRIFT_BAND + 1e-12
        report["band_verdict"] = band_verdict(drift)
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
    if (retuned_events is None) != (retune is None):
        raise ValueError("Re-tuning needs both the re-tuned log and the re-tune file")
    if retuned_events is not None:
        if retune.get("target_strong_share") is not None and planned_share is not None \
                and abs(retune["target_strong_share"] - planned_share) > 1e-12:
            raise ValueError("The re-tune file was fitted to a different planned share")
        report["retune"] = retune_comparison(events, retuned_events, records, retune, planned_share, seed, samples)
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
             f"Wrong answers caused by the cache (another question's saved answer): "
             f"{report['totals']['wrong_question_wrong']:,} ({pct(r['wrong_question_wrong_rate']['estimate'], 2)} of requests, "
             f"{rng(r['wrong_question_wrong_rate'], lambda v: pct(v, 2))})",
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
        band = f"±{100 * report['drift_band']:g}"
        verdict = f"within the {band}-point band" if report["within_band"] else f"outside the {band}-point band"
        if report.get("band_verdict", "").endswith("unsure"):
            verdict += ", but too few questions to be sure"
        lines.append(f"  plan {pct(report['planned_strong_share'])}; drift {pts(r['drift_from_plan']['estimate'])} points "
                     f"({rng(r['drift_from_plan'], pts)}), {verdict}")
    if "paired" in report:
        p = report["paired"]
        lines.append(f"Versus fresh answers (same stream, no cache): accuracy {pts(p['accuracy_change']['estimate'])} points "
                     f"({rng(p['accuracy_change'], pts)}); expensive-model share {pts(p['strong_share_change']['estimate'])} "
                     f"points ({rng(p['strong_share_change'], pts)})")
    if "retune" in report:
        x = report["retune"]
        lines.append(f"Re-tuning (new cutoff {x['threshold_after']:.4f}; {x['held_out_groups']:,} held-out question groups, "
                     f"{x['held_out_requests']:,} requests):")
        lines.append(f"  expensive-model share {pct(x['before']['strong_share_of_routed']['estimate'])} -> "
                     f"{pct(x['after']['strong_share_of_routed']['estimate'])} "
                     f"({rng(x['after']['strong_share_of_routed'], pct)})"
                     + ("" if "after_within_band" not in x else
                        f", {'within' if x['after_within_band'] else 'outside'} the ±{100 * DRIFT_BAND:g}-point band"
                        + (", but too few questions to be sure" if x.get("after_band_verdict", "").endswith("unsure") else "")))
        lines.append(f"  accuracy {pts(x['change']['accuracy']['estimate'])} points ({rng(x['change']['accuracy'], pts)}); "
                     f"cost per 1,000 {money(x['before']['usd_per_1000']['estimate'])} -> "
                     f"{money(x['after']['usd_per_1000']['estimate'])}")
        lines.append(f"  accuracy range {'stays above' if x['accuracy_range_above_margin'] else 'reaches below'} "
                     f"the {pts(RETUNE_MARGIN)}-point margin; your call whether to apply the new cutoff")
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
.bad{background:var(--bad-bg);color:var(--bad)}.muted{background:var(--line);color:var(--ink)}
.lead .big.alarm{color:var(--bad)}.lead .rows{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}.ex{border-left:3px solid var(--bad);padding:6px 0 6px 12px;margin:10px 0}
.ex .a{color:var(--muted);font-size:14px}footer{margin-top:18px;font-size:12.5px;color:var(--muted)}
table.settings{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
table.settings th{text-align:left;color:var(--muted);font-weight:600;font-size:12.5px;padding:6px 8px 6px 0;border-bottom:1px solid var(--line)}
table.settings td{padding:7px 8px 7px 0;border-bottom:1px solid var(--line);white-space:nowrap}
table.settings tr.pick td{background:var(--good-bg);font-weight:600}table.settings td.fail{color:var(--bad)}
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
        cls = "good" if change["ci95"][0] is not None and change["ci95"][0] >= ACCURACY_AMBER else "warn"
        quality_pill = (f'<span class="pill {cls}">{pts(change["estimate"])} points vs fresh answers</span> '
                        f'<span class="range">({rng(change, pts)})</span>')
    plan = ""
    if report["planned_strong_share"] is not None:
        drift = r["drift_from_plan"]
        band = f"{100 * report['drift_band']:g}"
        cls, words = VERDICT_WORDS[report["band_verdict"]]
        verdict = words.format(b=band)
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
    wrong = t["wrong_question_wrong"]
    rate = r["wrong_question_wrong_rate"]
    lead_pill = ('<span class="pill good">None in this run</span>' if wrong == 0 else
                 f'<span class="pill bad">About {1000 * rate["estimate"]:.1f} in every 1,000 answers</span> '
                 f'<span class="range">({rng(rate, lambda v: f"{1000 * v:.1f}")} per 1,000)</span>')
    lead = (f'<section class="card full lead"><h2>Wrong answers caused by the cache</h2>'
            f'<div class="big{" alarm" if wrong else ""}">{wrong:,}</div>{lead_pill}'
            f'<p class="range">A question that got another question\'s saved answer, and that answer was wrong for it.</p>'
            f'<div class="rows">'
            + row("Saved answer given to a <i>different</i> question",
                  f'{t["wrong_question"]:,} ({pct(r["wrong_question_rate"]["estimate"], 2)})')
            + row('Wrong answers repeated from the cache <span class="range">(the model was already wrong the '
                  'first time, so not caused by the cache)</span>',
                  f'{t["repeated_wrong"]:,} ({pct(r["repeated_wrong_rate"]["estimate"], 2)})')
            + f'</div><h2 style="margin-top:14px">Answers to check: saved answer served to a different question</h2>'
              f'{examples}</section>')
    fresh = ""
    if "fresh" in report:
        fresh = row("Fresh answers, no cache", pct(report["fresh"]["accuracy"]["estimate"]))
    retune = ""
    if "retune" in report:
        x = report["retune"]
        signed_money = lambda v: "n/a" if v is None else ("−" if v < 0 else "+") + money(abs(v))
        share_label = ""
        if x.get("after_band_verdict"):
            cls, words = VERDICT_WORDS[x["after_band_verdict"]]
            text = words.format(b=f"{100 * DRIFT_BAND:g}")
            share_label = f'<span class="pill {cls}">After re-tuning: {text[0].lower() + text[1:]}</span> '
        acc_cls = "good" if x["accuracy_range_above_margin"] else "warn"
        before_cut = "" if x["threshold_before"] is None else f'{x["threshold_before"]:.4f} → '
        retune = (f'<section class="card full"><h2>Re-tune the router? (your call)</h2>{share_label}'
                  f'<span class="pill {acc_cls}">{pts(x["change"]["accuracy"]["estimate"])} accuracy points</span> '
                  f'<span class="range">({rng(x["change"]["accuracy"], pts)})</span>'
                  + row("Expensive-model share", f'{pct(x["before"]["strong_share_of_routed"]["estimate"])} → '
                        f'{pct(x["after"]["strong_share_of_routed"]["estimate"])} '
                        f'<span class="range">({rng(x["after"]["strong_share_of_routed"], pct)})</span>')
                  + row("Correct answers", f'{pct(x["before"]["accuracy"]["estimate"])} → '
                        f'{pct(x["after"]["accuracy"]["estimate"])}')
                  + row("Cost per 1,000 requests", f'{money(x["before"]["usd_per_1000"]["estimate"])} → '
                        f'{money(x["after"]["usd_per_1000"]["estimate"])} <span class="range">(change '
                        f'{signed_money(x["change"]["usd_per_1000"]["estimate"])}, '
                        f'{rng(x["change"]["usd_per_1000"], signed_money)})</span>')
                  + row("Router cutoff", f'{before_cut}{x["threshold_after"]:.4f}')
                  + f'<p class="range">Fitted on the requests from half of the question groups that reached the router; '
                    f'compared here on the other {x["held_out_groups"]:,} groups ({x["held_out_requests"]:,} requests), '
                    f'old cutoff vs new, same cache. Apply the new cutoff if the accuracy change is acceptable to you.</p>'
                    f'</section>')
    settings = ""
    if "settings" in report:
        sw = report["settings"]
        limit = sw["limit"]
        body = ""
        for item in sw["rows"]:
            high = item["wrong_caused_rate"]["ci95"][1]
            over = high is not None and high > limit + 1e-12
            body += (f'<tr class="{"pick" if item["label"] == sw["recommended"] else ""}"><td>{e(item["label"])}</td>'
                     f'<td>{pct(item["hit_rate"]["estimate"])}</td>'
                     f'<td class="{"fail" if over else ""}">{item["wrong_caused"]:,} '
                     f'<span class="range">({rng(item["wrong_caused_rate"], lambda v: pct(v, 2))})</span></td>'
                     f'<td>{money(item["usd_per_1000"]["estimate"])}</td>'
                     f'<td>{pts(item["accuracy_change_vs_fresh"]["estimate"])}</td></tr>')
        pick = (f'<span class="pill good">Recommended: {e(sw["recommended"])}</span>' if sw["recommended"] else
                '<span class="pill bad">No setting kept wrong answers under the limit: keep the cache off</span>')
        settings = (f'<section class="card full"><h2>Which cache setting is safe for your questions?</h2>{pick} '
                    f'<span class="range">Your {sw["requests"]:,} requests replayed at each setting; no cache costs '
                    f'{money(sw["no_cache"]["usd_per_1000"]["estimate"])} per 1,000.</span>'
                    f'<table class="settings"><thead><tr><th>Setting</th><th>From the cache</th>'
                    f'<th>Wrong answers caused by the cache</th><th>Cost per 1,000</th><th>Accuracy vs no cache</th>'
                    f'</tr></thead><tbody>{body}</tbody></table></section>')
    rules = []
    if "settings" in report:
        rules.append(f"The recommended setting answers the most from the cache while the top of its range of wrong "
                     f"answers caused by the cache is at most {pct(report['settings']['limit'], 1)} of requests.")
    if "retune" in report:
        rules.append(f"The re-tuning accuracy label is amber when the low end of its range is below "
                     f"{pts(RETUNE_MARGIN)} point (the margin agreed in #37).")
    if "paired" in report:
        rules.append(f"The \"vs fresh answers\" label is amber when the low end of its range is below "
                     f"{pts(ACCURACY_AMBER)} points.")
    if report["planned_strong_share"] is not None:
        rules.append(f"The plan label is green when the expensive-model share is within "
                     f"±{100 * report['drift_band']:g} points of plan (Story 3).")
    rules = (" " + " ".join(rules)) if rules else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CacheShift Report</title><style>{CSS}</style></head><body><main>
<h1>{e(title)}</h1>
<p class="note">{t["requests"]:,} requests · {report["question_groups"]:,} question groups · source: {e(source)}</p>
<div class="grid">
{lead}
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
</section>
{settings}
{plan}
{retune}
</div>
<footer>Ranges are 95% bootstrap intervals over question groups ({report.get("bootstrap_samples", SAMPLES):,} resamples). Cost and quality are shown
separately and never combined into one score. "Correct" means the answer matches the question's official answer key.
Costs are historical estimates recorded by the replay gateway.{rules} Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.</footer>
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
    parser.add_argument("--retuned-log", type=Path,
                        help="Optional (#49): the same stream through the cache with the re-tuned cutoff")
    parser.add_argument("--retune", type=Path, help="The re-tune file from cacheshift.retune_log (with --retuned-log)")
    parser.add_argument("--settings", type=Path, help="Optional: the setting finder's output (cacheshift.setting_finder)")
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
        if (args.retuned_log is None) != (args.retune is None):
            raise ValueError("--retuned-log and --retune go together")
        retuned, retune = None, None
        if args.retune:
            from cacheshift import retune_log
            retuned, retune = read_log(args.retuned_log), retune_log.load(args.retune)
        report = build(events, records, planned, fresh, retuned_events=retuned, retune=retune)
        if args.settings:
            report["settings"] = json.loads(args.settings.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Could not build the report: {exc}\n")
    report["inputs"] = {"log": args.log.name, "log_sha256": hashlib.sha256(args.log.read_bytes()).hexdigest(),
                        "fresh_log": args.fresh_log.name if args.fresh_log else None,
                        "retuned_log": args.retuned_log.name if args.retuned_log else None,
                        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                        "seed": SEED}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(report, args.title, args.log.name), encoding="utf-8", newline="\n")
    args.out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(text_summary(report, args.title))
    print(f"Wrote {args.out} and {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    sys.exit(main())
