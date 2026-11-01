import io

import numpy as np

from cacheshift import cache_demo


class FakeEmbedder:
    """Unit vectors chosen so each question's similarity to its intended match is known."""

    def __init__(self, similar):
        self.similar, self.vectors = similar, {}

    def __call__(self, text):
        if text not in self.vectors:
            if text in self.similar:
                target, cos = self.similar[text]
                base = self(target)
                other = np.zeros_like(base)
                other[len(self.vectors) + 1] = 1.0
                self.vectors[text] = (cos * base + np.sqrt(1 - cos**2) * other).astype(np.float32)
            else:
                v = np.zeros(64, dtype=np.float32)
                v[len(self.vectors) + 1] = 1.0
                self.vectors[text] = v
        return self.vectors[text]


def test_verdicts_follow_the_key_and_threshold():
    assert cache_demo.verdict("a", 0.92, 0.90, "a") == "reuse"
    assert cache_demo.verdict("a", 0.92, 0.90, None) == "wrong"
    assert cache_demo.verdict("a", 0.92, 0.95, None) == "router"
    assert cache_demo.verdict("a", 0.92, 0.90, cache_demo.ASKED) == "hit"


def test_demo_counts_right_and_wrong_reuse():
    similar = {"When do you open on Saturday?": ("What time do you open on Saturdays?", 0.91),
               "What time do you close on Sunday?": ("What time do you close on Saturday?", 0.94),
               "Are your muffins dairy-free?": ("Are your muffins nut-free?", 0.83)}
    embed = FakeEmbedder(similar)
    incoming = ((q, k) for q, k in cache_demo.INCOMING if q in similar)
    tally = cache_demo.run(embed, tuple(incoming), use_color=False, out=io.StringIO())
    assert tally[0.80] == {"reuse": 1, "wrong": 2, "router": 0}
    assert tally[0.90] == {"reuse": 1, "wrong": 1, "router": 1}
    assert tally[0.95] == {"reuse": 0, "wrong": 0, "router": 3}
