"""Live demo: a semantic cache serving a saved answer to the wrong question.

A made-up bakery chatbot has six saved answers. Six new customer questions go through the
same semantic cache (all-MiniLM-L6-v2, the Story 2 cache) at three match settings. For each
question the demo shows the closest saved question, the similarity, and what each setting
does: reuse the right answer, serve a wrong one, or send the question on to the router.
Which saved question is really the same question is written by hand below, so the verdicts
do not depend on the model. Runs on a laptop CPU; no API calls.

  python -m cacheshift.cache_demo                    # whole demo at once
  python -m cacheshift.cache_demo --step             # pause after each question (press Enter)
  python -m cacheshift.cache_demo --ask "Is the cafe open on Labor Day?"   # add a question from the room
"""

import argparse
import os
import sys

from cacheshift.semantic_cache import SemanticCache, SentenceEmbedder

SAVED = {  # made-up business; answers as the chatbot first gave them
    "What time do you open on Saturdays?": "We open at 7 am on Saturdays.",
    "What time do you close on Saturday?": "We close at 6 pm on Saturdays.",
    "Do you have gluten-free cookies?": "Yes! Gluten-free cookies are baked fresh every Friday.",
    "Are your muffins nut-free?": "Yes, all our muffins are made without nuts.",
    "Do you deliver to Cambridge?": "Yes, we deliver to Cambridge for $5.",
    "How much is a dozen bagels?": "A dozen bagels is $14.",
}

# Each new question, and the saved question that really asks the same thing (None = nothing saved).
INCOMING = (
    ("When do you open on Saturday?", "What time do you open on Saturdays?"),
    ("Do you sell gluten free cookies?", "Do you have gluten-free cookies?"),
    ("What time do you close on Sunday?", None),
    ("Are your muffins dairy-free?", None),
    ("Can I order a birthday cake for Friday?", None),
    ("Do you have gluten-free bread?", None),
)

THRESHOLDS = (0.80, 0.90, 0.95)
ASKED = "?"  # an audience question: no key, so the presenter judges the match

GREEN, RED, GREY, BOLD, RESET = "\033[32m", "\033[1;31m", "\033[90m", "\033[1m", "\033[0m"


def paint(text, color, use_color):
    return f"{color}{text}{RESET}" if use_color else text


def verdict(best, similarity, threshold, same_as):
    """'reuse' (right saved answer), 'wrong' (saved answer to a different question), 'router' (miss),
    or 'hit' for an audience question, where nobody has said which saved question is the same."""
    if similarity is None or similarity < threshold:
        return "router"
    if same_as == ASKED:
        return "hit"
    if same_as is None:
        return "wrong"
    return "reuse" if best == same_as else "wrong"


def run(embed, incoming=INCOMING, thresholds=THRESHOLDS, step=False, use_color=True, out=sys.stdout):
    caches = {t: SemanticCache(embed, t) for t in thresholds}
    for question, answer in SAVED.items():
        for cache in caches.values():
            cache.insert(question, question)  # store the question so the match can be shown
    labels = {"reuse": ("✓ right answer", GREEN), "wrong": ("✗ WRONG answer", RED), "router": ("→ to the model", GREY),
              "hit": ("↺ saved answer", BOLD)}
    tally = {t: {"reuse": 0, "wrong": 0, "router": 0} for t in thresholds}

    print(paint("CacheShift demo · a semantic cache in front of a bakery chatbot (made-up business)", BOLD, use_color),
          file=out)
    print(f"{len(SAVED)} saved answers · cache: {embed.model_name if hasattr(embed, 'model_name') else 'test'} · "
          f"match settings: {', '.join(f'≥ {t:.2f}' for t in thresholds)}\n", file=out)
    for n, (question, same_as) in enumerate(incoming, 1):
        loosest = caches[min(thresholds)]
        best, similarity = loosest.lookup(question)
        if best is None:  # below the loosest setting: still show the nearest saved question
            best, similarity = loosest.entries[int((loosest.matrix @ embed(question)).argmax())], similarity
        print(paint(f"{n}. \"{question}\"", BOLD, use_color), file=out)
        print(f"   closest saved question: \"{best}\"   similarity {similarity:.2f}", file=out)
        cells = []
        for t in thresholds:
            v = verdict(best, similarity, t, same_as)
            if same_as != ASKED:
                tally[t][v] += 1
            text, color = labels[v]
            cells.append(f"≥ {t:.2f} " + paint(text, color, use_color))
        print("   " + "   ".join(cells), file=out)
        served = {verdict(best, similarity, t, same_as) for t in thresholds}
        if "wrong" in served:
            print("   " + paint(f"wrong answer served: \"{SAVED[best]}\"", RED, use_color), file=out)
        elif "hit" in served:
            print(f"   answer it would serve: \"{SAVED[best]}\"   right or wrong?", file=out)
        print(file=out)
        if step and n < len(incoming):
            input(paint("   [Enter]", GREY, use_color))
    print(paint(f"Out of the {len(INCOMING)} prepared questions:", BOLD, use_color), file=out)
    for t in thresholds:
        c = tally[t]
        print(f"   ≥ {t:.2f}   {c['reuse']} right answers reused · " +
              paint(f"{c['wrong']} wrong answer{'' if c['wrong'] == 1 else 's'} served", RED if c["wrong"] else GREY, use_color) +
              f" · {c['router']} sent to the model", file=out)
    print("\nNo setting reuses every right answer without serving a wrong one, "
          "so CacheShift measures it on your own traffic.", file=out)
    return tally


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", action="store_true", help="pause after each question")
    parser.add_argument("--ask", action="append", default=[], metavar="QUESTION",
                        help="add a question from the audience (shown without a right/wrong key)")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    embed = SentenceEmbedder()
    embed.warm(list(SAVED) + [q for q, _ in INCOMING] + args.ask)
    incoming = INCOMING + tuple((q, ASKED) for q in args.ask)
    run(embed, incoming, step=args.step, use_color=not args.no_color and sys.stdout.isatty())


if __name__ == "__main__":
    main()
