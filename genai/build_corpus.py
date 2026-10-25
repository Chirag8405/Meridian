"""Build backend/assistant/corpus.json from the project docs.

Splits each doc by markdown heading (## / ###, ignoring '#' lines inside code
fences), splits chunks over MAX_CHARS on paragraph boundaries, and stores a
hash of the sources so a stale corpus is detectable:

    python genai/build_corpus.py          # (re)write backend/assistant/corpus.json
    python genai/build_corpus.py --check  # exit 1 if the committed corpus is stale

Render deploys only backend/, so the output MUST be committed there.
SETUP.md is excluded on purpose (operational paths/secrets handling).
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "assistant" / "corpus.json"
SOURCES = ["FINDINGS.md", "ARCHITECTURE.md", "SCOPE.md", "DATA_SOURCES.md"]
MAX_CHARS = 1500
_HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


def split_sections(text: str) -> list[tuple[str, str]]:
    """[(heading_path, body)] with fences respected."""
    sections: list[tuple[str, str]] = []
    path: list[str] = []
    body: list[str] = []
    in_fence = False

    def flush():
        joined = "\n".join(body).strip()
        if joined:
            sections.append((" > ".join(path), joined))
        body.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2)]
        else:
            body.append(line)
    flush()
    return sections


def _atoms(body: str) -> list[str]:
    """Paragraphs; any paragraph over MAX_CHARS is cut on line, then word, boundaries."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", body):
        if len(para) <= MAX_CHARS:
            out.append(para)
            continue
        cur = ""
        for line in para.split("\n"):
            while len(line) > MAX_CHARS:  # a single huge line: cut on a space
                cut = line.rfind(" ", 0, MAX_CHARS) or MAX_CHARS
                if cut <= 0:
                    cut = MAX_CHARS
                out.append(line[:cut])
                line = line[cut:].lstrip()
            if cur and len(cur) + len(line) + 1 > MAX_CHARS:
                out.append(cur)
                cur = ""
            cur += line + "\n"
        if cur.strip():
            out.append(cur.rstrip())
    return out


def split_long(body: str) -> list[str]:
    if len(body) <= MAX_CHARS:
        return [body]
    parts, cur = [], ""
    for atom in _atoms(body):
        if cur and len(cur) + len(atom) + 2 > MAX_CHARS:
            parts.append(cur.strip())
            cur = ""
        cur += atom + "\n\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts


def build() -> dict:
    h = hashlib.sha256()
    chunks = []
    for name in SOURCES:
        text = (ROOT / "docs" / name).read_text()
        h.update(name.encode() + b"\0" + text.encode())
        n = 0
        for heading, body in split_sections(text):
            for piece in split_long(body):
                n += 1
                chunks.append({"id": f"{name}#{n}", "file": name, "heading_path": heading or name, "text": piece})
    return {"source_hash": h.hexdigest(), "chunks": chunks}


def main() -> int:
    corpus = build()
    if "--check" in sys.argv:
        if not OUT.exists() or json.loads(OUT.read_text()).get("source_hash") != corpus["source_hash"]:
            print("corpus.json is stale: run `python genai/build_corpus.py` and commit the result", file=sys.stderr)
            return 1
        print("corpus.json is up to date")
        return 0
    OUT.write_text(json.dumps(corpus, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(corpus['chunks'])} chunks from {len(SOURCES)} docs to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
