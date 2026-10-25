"""Hand check for Story 2: does a person agree with the automatic cache-hit labels?

  sample: draw cache hits into a blind CSV sheet (no automatic labels shown) and a
          separate key file holding those labels.
  score:  after a person fills in the sheet, report agreement with the key.

The person answers two questions per row, Y or N:
  same_question   Is the matched question the same question as the query?
  served_correct  Is the served answer correct for the query, by the answer key?

Run (from the repo root):
  python tools/hand_check.py sample --hits <run>/hits-601.jsonl --sheet <dir>/hand_check_sheet.csv --key <dir>/hand_check_key.json
  python tools/hand_check.py score --sheet <dir>/hand_check_sheet.csv --key <dir>/hand_check_key.json
"""

import argparse
import csv
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cacheshift.cache_quality import DATASET, load_records  # noqa: E402

SHEET_FIELDS = ("item", "query_question", "matched_question", "served_answer", "answer_key",
                "same_question", "served_correct", "notes")
TARGET = 0.90


def choose(hits, n, seed):
    """Half false hits; the other half split between inherited errors and correct same-question hits.

    One row per (query, match, served answer), so the grader is checked on wrong answers too.
    """
    unique = {}
    for hit in hits:
        unique.setdefault((hit["question_id"], hit["matched_question_id"], hit["served_answer"]), hit)
    rows = sorted(unique.values(), key=lambda h: (h["question_id"], h["matched_question_id"], h["served_answer"]))
    false_hits = [h for h in rows if h["label"].startswith("false_hit")]
    inherited = [h for h in rows if h["label"] == "inherited_error"]
    correct = [h for h in rows if h["label"] == "hit_ok"]
    rng = random.Random(seed)
    picked = rng.sample(false_hits, min(len(false_hits), n // 2))
    picked += rng.sample(inherited, min(len(inherited), (n - len(picked)) // 2))
    picked += rng.sample(correct, min(len(correct), n - len(picked)))
    rng.shuffle(picked)
    return picked


def sample(hits_path, dataset, sheet, key, n=50, seed=0):
    records = load_records(dataset)
    hits = [json.loads(line) for line in Path(hits_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    picked = choose(hits, n, seed)
    if len(picked) < n:
        print(f"Only {len(picked)} distinct hits available; sheet has {len(picked)} rows.")
    sheet, key = Path(sheet), Path(key)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    with sheet.open("x", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=SHEET_FIELDS)
        writer.writeheader()
        for i, hit in enumerate(picked, 1):
            query = records[hit["question_id"]]
            writer.writerow({"item": i, "query_question": query["text"],
                             "matched_question": records[hit["matched_question_id"]]["text"],
                             "served_answer": hit["served_answer"], "answer_key": query["gold_answer"],
                             "same_question": "", "served_correct": "", "notes": ""})
    labels = {str(i): {"same_question": not hit["label"].startswith("false_hit"), "served_correct": hit["correct"],
                       "label": hit["label"], "setting": hit["setting"], "model": hit["model"],
                       "question_id": hit["question_id"], "matched_question_id": hit["matched_question_id"]}
              for i, hit in enumerate(picked, 1)}
    with key.open("x", encoding="utf-8") as out:
        json.dump({"hits_file": str(hits_path), "seed": seed, "items": labels}, out, indent=2)
    print(f"Wrote {len(picked)} rows to {sheet} and the hidden labels to {key}.")


def wilson(successes, total, z=1.96):
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [centre - half, centre + half]


def parse_yes_no(value, item, field):
    value = value.strip().upper()
    if value in ("Y", "YES"):
        return True
    if value in ("N", "NO"):
        return False
    raise ValueError(f"Item {item}: {field} must be Y or N, got {value!r}")


def score(sheet, key):
    labels = json.loads(Path(key).read_text(encoding="utf-8"))["items"]
    rows = list(csv.DictReader(Path(sheet).open(encoding="utf-8", newline="")))
    if {row["item"] for row in rows} != set(labels):
        raise ValueError("Sheet items do not match the key")
    result, disagreements = {}, []
    for field in ("same_question", "served_correct"):
        agree = 0
        for row in rows:
            human = parse_yes_no(row[field], row["item"], field)
            if human == labels[row["item"]][field]:
                agree += 1
            else:
                disagreements.append({"item": row["item"], "field": field, "human": human,
                                      "automatic": labels[row["item"]][field], "notes": row.get("notes", "")})
        result[field] = {"agree": agree, "total": len(rows), "rate": agree / len(rows), "ci95": wilson(agree, len(rows))}
    both = sum(1 for row in rows if all(parse_yes_no(row[f], row["item"], f) == labels[row["item"]][f]
                                        for f in ("same_question", "served_correct")))
    result["both_labels"] = {"agree": both, "total": len(rows), "rate": both / len(rows), "ci95": wilson(both, len(rows))}
    result["passes_90_percent"] = result["both_labels"]["rate"] >= TARGET
    result["disagreements"] = disagreements
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--hits", type=Path, required=True)
    s.add_argument("--dataset", type=Path, default=DATASET)
    s.add_argument("--sheet", type=Path, required=True)
    s.add_argument("--key", type=Path, required=True)
    s.add_argument("--n", type=int, default=50)
    s.add_argument("--seed", type=int, default=0)
    c = sub.add_parser("score")
    c.add_argument("--sheet", type=Path, required=True)
    c.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "sample":
        sample(args.hits, args.dataset, args.sheet, args.key, args.n, args.seed)
    else:
        score(args.sheet, args.key)


if __name__ == "__main__":
    main()
