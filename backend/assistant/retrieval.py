"""Lexical BM25 over the committed docs corpus (no embeddings, no deps)."""

import json
import math
import re
from collections import Counter
from pathlib import Path

CORPUS_PATH = Path(__file__).with_name("corpus.json")
_TOKEN = re.compile(r"[a-z0-9_]+")
STOPWORDS = frozenset(
    "a an and are as at be by for from how in is it of on or that the this to was what when "
    "where which who why with does did do".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class Bm25Index:
    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        # Heading tokens are repeated so a heading match outranks a passing mention.
        self.docs = [
            tokenize(c["text"]) + tokenize(c["heading_path"]) * 2 for c in chunks
        ]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = (sum(len(d) for d in self.docs) / len(self.docs)) if self.docs else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4) -> list[dict]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            score = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    score += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                    )
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{**self.chunks[i], "score": round(s, 4)} for s, i in scored[:k]]


def load_index(path: Path = CORPUS_PATH) -> Bm25Index:
    data = json.loads(path.read_text())
    return Bm25Index(data["chunks"])
