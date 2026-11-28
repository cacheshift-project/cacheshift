"""Semantic cache: reuse a stored answer when a new prompt is close enough to one already answered.

Prompts are embedded as unit vectors, so cosine similarity is a dot product. A
threshold of None makes an exact-text cache (a hit only on identical text).
"""

import numpy as np

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


CANDIDATES = 5


def difference(a, b):
    """The parts of two prompts that differ: trim the longest shared run of words at the start and end."""
    x, y = a.split(), b.split()
    start = 0
    while start < min(len(x), len(y)) and x[start] == y[start]:
        start += 1
    end = 0
    while end < min(len(x), len(y)) - start and x[len(x) - 1 - end] == y[len(y) - 1 - end]:
        end += 1
    return " ".join(x[start:len(x) - end]), " ".join(y[start:len(y) - end])


class SemanticCache:
    def __init__(self, embed, threshold, verify=None):
        """verify (the difference check): reuse a match only if the parts of the two prompts that
        differ, once their shared start and end are trimmed, are at least this alike."""
        if threshold is not None and not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1], or None for an exact-text cache")
        if verify is not None and (threshold is None or not 0 < verify <= 1):
            raise ValueError("verify must be in (0, 1] and needs a semantic threshold")
        self.embed = embed
        self.threshold = threshold
        self.verify = verify
        self.entries = []
        self.texts = []
        self.rejected = 0   # matches the difference check turned into misses
        self.exact = {}
        self.matrix = None

    def lookup(self, text):
        """Return (entry, similarity) for the best stored prompt; entry is None on a miss.

        On a miss the similarity is still the best one seen (None if the cache is empty),
        so near-misses can be inspected.
        """
        if self.threshold is None:
            entry = self.exact.get(text)
            return (entry, 1.0) if entry is not None else (None, None)
        if self.matrix is None:
            return None, None
        similarities = self.matrix @ self.embed(text)
        best = int(np.argmax(similarities))
        similarity = float(similarities[best])
        if similarity < self.threshold:
            return None, similarity
        if self.verify is None:
            return self.entries[best], similarity
        order = np.argsort(-similarities)[:CANDIDATES]
        for index in order:
            if similarities[index] < self.threshold:
                break
            if self.passes(text, self.texts[index]):
                return self.entries[int(index)], float(similarities[index])
        self.rejected += 1
        return None, similarity

    def passes(self, text, saved):
        mine, theirs = difference(text, saved)
        if not mine and not theirs:
            return True
        if not mine or not theirs:
            return False
        return float(np.dot(self.embed(mine), self.embed(theirs))) >= self.verify

    def insert(self, text, entry):
        if self.threshold is None:
            self.exact.setdefault(text, entry)
            return
        vector = np.asarray(self.embed(text), dtype=np.float32)[None, :]
        self.matrix = vector if self.matrix is None else np.vstack([self.matrix, vector])
        self.entries.append(entry)
        self.texts.append(text)


class SentenceEmbedder:
    """CPU sentence-transformers embedder with an in-memory memo (no API calls)."""

    def __init__(self, model=EMBEDDING_MODEL, cache_dir=None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model
        self.model = SentenceTransformer(model, device="cpu", cache_folder=cache_dir)
        self.memo = {}

    def warm(self, texts, batch_size=64):
        missing = sorted({text for text in texts if text not in self.memo})
        if missing:
            vectors = self.model.encode(missing, batch_size=batch_size, normalize_embeddings=True,
                                        convert_to_numpy=True, show_progress_bar=False)
            self.memo.update(zip(missing, vectors.astype(np.float32)))

    def __call__(self, text):
        if text not in self.memo:
            self.warm([text])
        return self.memo[text]
