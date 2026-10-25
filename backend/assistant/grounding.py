"""Post-hoc numeric grounding check.

Every number (and date/time) in an answer must appear in the evidence the
model was given in the same turn (tool outputs, retrieved chunks, the user's
own question). Comparison is by value, allowing the answer to round to the
precision it writes (72 vs 72.0, 4.3575 vs 4.357463...). A tiny, explicit
allow-list covers the 0-100 / 0-1 scales and zero/one.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ALLOWED_CONSTANTS = {Decimal(0), Decimal(1), Decimal(100)}

_CITATION = re.compile(r"\[S\d+\]")
_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def extract_numbers(text: str) -> list[tuple[str, Decimal]]:
    """(as written, value) pairs. Dates/times are reduced to their components."""
    text = _CITATION.sub(" ", text)
    out: list[tuple[str, Decimal]] = []

    def take(m: re.Match) -> str:
        for part in m.groups():
            if part is not None:
                out.append((part, Decimal(int(part))))
        return " "

    text = _DATE.sub(take, text)
    text = _TIME.sub(take, text)
    for raw in _NUMBER.findall(text):
        val = _dec(raw)
        if val is not None:
            out.append((raw, abs(val)))
    return out


# Free-text strings inside tool results (labels from the DB, wallet names, caveats)
# are untrusted: an injected "say 999" there must not make 999 count as evidence.
# Numbers are taken from numeric values, ISO timestamps, and the keys our own code
# or the committed docs control.
TRUSTED_TEXT_KEYS = {"text", "label", "heading", "file"}
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]")


def evidence_numbers(*blobs) -> list[Decimal]:
    """All trusted numeric values appearing in strings/JSON-like structures.
    Top-level strings (the user's question) are fully trusted."""
    values: list[Decimal] = []

    def walk(x, trusted: bool) -> None:
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            values.append(abs(Decimal(str(x))))
        elif isinstance(x, str):
            if trusted or _ISO_TS.match(x):
                values.extend(v for _, v in extract_numbers(x))
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, k in TRUSTED_TEXT_KEYS)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, trusted)

    for b in blobs:
        walk(b, isinstance(b, str))
    return values


def _matches(written: str, value: Decimal, pool: list[Decimal]) -> bool:
    if value in ALLOWED_CONSTANTS:
        return True
    places = _decimals(written.replace(",", ""))
    quantum = Decimal(1).scaleb(-places)
    for v in pool:
        if v == value:
            return True
        try:
            if v.quantize(quantum, rounding=ROUND_HALF_UP) == value:
                return True
        except InvalidOperation:
            continue
    return False


def ungrounded_numbers(answer: str, pool: list[Decimal]) -> list[str]:
    seen, bad = set(), []
    for written, value in extract_numbers(answer):
        if written in seen:
            continue
        seen.add(written)
        if not _matches(written, value, pool):
            bad.append(written)
    return bad


def invalid_citations(answer: str, valid_ids: set[str]) -> list[str]:
    cited = set(re.findall(r"\[(S\d+)\]", answer))
    return sorted(cited - valid_ids)
