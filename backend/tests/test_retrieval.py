import json
from pathlib import Path

from assistant.retrieval import Bm25Index, load_index

CHUNKS = [
    {"id": "a#1", "file": "a.md", "heading_path": "UST has no reliable baseline", "text": "UST was already destabilized before the dataset begins."},
    {"id": "a#2", "file": "a.md", "heading_path": "Wallets", "text": "Most top wallets are infrastructure contracts."},
    {"id": "a#3", "file": "a.md", "heading_path": "Clustering", "text": "K-Means separates stress patterns by severity."},
]


def test_ranks_relevant_chunk_first():
    idx = Bm25Index(CHUNKS)
    assert idx.search("why does UST have no baseline")[0]["id"] == "a#1"


def test_no_match_returns_empty():
    assert Bm25Index(CHUNKS).search("zebra") == []


def test_heading_match_counts():
    assert Bm25Index(CHUNKS).search("clustering")[0]["id"] == "a#3"


def test_committed_corpus_loads_and_answers():
    idx = load_index()
    hits = idx.search("lead time USDC early warning", k=3)
    assert hits and all(len(h["text"]) <= 1600 for h in hits)


def test_committed_corpus_is_fresh():
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(root / "genai" / "build_corpus.py"), "--check"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()
    assert json.loads((root / "backend/assistant/corpus.json").read_text())["chunks"]
