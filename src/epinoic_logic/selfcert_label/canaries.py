"""Keyed canaries: wholesale suppression of the label becomes a withhold (meaning-check design 2.3; overseer-side design 6.2).

For every rendered request, code inserts one or two POSITIVE canaries, self-certifications generated from the classes of
``canaries.json`` (language x family x form x evaluator x scope), each as its own paragraph with an ordinary sequential id, at a
keyed position among the answer's paragraphs. A reply that does not mark every positive canary ``gated`` with a located span
fails the ``control`` check, so "report nothing" withholds the answer instead of releasing it. In a keyed 10% of requests a
NEGATIVE canary (a boundary (b) sentence) is inserted as well; its verdict is recorded for drift only and never blocks.

Every choice is drawn from ``HMAC-SHA256(key, issue id | attempt | ...)``: in production the key is a deployment secret, offline a
separate recording key, in tests a fixed test key. A writer who has read this file can therefore predict neither the sentence nor
its position. A retry passes a new attempt number, so its canaries are fresh. Canary text is removed before any span is kept: it
never reaches a stored span, a finding or a receipt.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import pathlib
from dataclasses import dataclass
from typing import Iterator, Optional

__all__ = ["Canary", "draw_canaries", "canary_classes", "all_positive_canaries", "all_negative_canaries", "key_fingerprint",
           "NEGATIVE_PERCENT"]

_HERE = pathlib.Path(__file__).resolve().parent
CANARY_DATA = "canaries.json"
#: The share of requests (per cent, keyed) that also carry a negative canary.
NEGATIVE_PERCENT = 10


@dataclass(frozen=True)
class Canary:
    text: str
    slot: int          # inserted before the answer paragraph of this index in the chunk (== count: after the last)
    positive: bool
    language: str
    family: str
    form: str


@functools.lru_cache(maxsize=1)
def canary_classes() -> dict:
    return json.loads((_HERE / CANARY_DATA).read_text(encoding="utf-8"))


def key_fingerprint(key: bytes) -> str:
    """A public fingerprint of a canary key (the key itself is never stored or rendered)."""
    return hashlib.sha256(b"selfcert-label canary key\0" + bytes(key)).hexdigest()[:32]


def _stream(key: bytes, message: str) -> Iterator[int]:
    """An endless stream of 32-bit draws from HMAC-SHA256(key, message | counter)."""
    n = 0
    while True:
        block = hmac.new(bytes(key), f"{message}|{n}".encode("utf-8"), hashlib.sha256).digest()
        for k in range(0, 32, 4):
            yield int.from_bytes(block[k:k + 4], "big")
        n += 1


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _fill_en(t: dict, scope: dict, ev: Optional[dict]) -> str:
    plural = scope.get("n") == "p"
    values = {
        "Scope": _cap(scope["np"]), "scope": scope["np"],
        "be": "are" if plural else "is", "be_past": "were" if plural else "was", "have": "have" if plural else "has",
        "Evaluator": _cap(ev["np"]) if ev else "", "evaluator": ev["np"] if ev else "", "ebe": (ev or {}).get("be", "is"),
    }
    return t["text"].format(**values)


def _fill_es(t: dict, scope: dict, ev: Optional[dict]) -> str:
    values = {
        "Scope": _cap(scope["np"]), "scope": scope["np"], "ser": scope["ser"], "fue": scope["fue"], "adj": scope["adj"],
        "ptcp": scope["ptcp"], "Evaluator": _cap(ev["np"]) if ev else "", "evaluator": ev["np"] if ev else "",
        "v": (ev or {}).get("v", ""),
    }
    return t["text"].format(**values)


def _positive(lang: str, t: dict, scope: dict, ev: Optional[dict]) -> str:
    return _fill_es(t, scope, ev) if lang == "es" else _fill_en(t, scope, ev)


def all_positive_canaries() -> list[tuple[str, str, str, str]]:
    """Every positive canary the classes can generate, as (text, language, family, form) (for the tests that pin them)."""
    out = []
    data = canary_classes()["positive"]
    for lang in sorted(data):
        d = data[lang]
        for t in d["templates"]:
            evs = d["evaluators"].get(t["evaluator"]) or [None]
            for scope in d["scopes"]:
                for ev in evs:
                    out.append((_positive(lang, t, scope, ev), lang, t["family"], t["form"]))
    return out


def _negative(template: str, a: int, b: int) -> str:
    return template.format(a=a, b=b, c=a * b)


def all_negative_canaries(samples: int = 3) -> list[tuple[str, str]]:
    """Negative canaries for each template, with ``samples`` keyed number choices (for the tests that pin them)."""
    out = []
    data = canary_classes()["negative"]
    for lang in sorted(data):
        for t in data[lang]:
            for k in range(samples):
                out.append((_negative(t, 2 + 7 * k, 3 + 5 * k), lang))
    return out


def draw_canaries(key: bytes, issue_id: str, attempt: int, paragraphs: int) -> tuple[Canary, ...]:
    """The canaries of one rendered request: 1 or 2 positive, and in a keyed 10% of requests one negative, each with its keyed
    slot among ``paragraphs`` answer paragraphs. Deterministic for (key, issue id, attempt)."""
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise ValueError("a canary key is required")
    draws = _stream(key, f"selfcert-label-canary/1|{issue_id}|{attempt}")
    data = canary_classes()
    pos = data["positive"]
    langs = sorted(pos)
    out: list[Canary] = []
    count = 1 + next(draws) % 2
    for _ in range(count):
        lang = langs[next(draws) % len(langs)]
        d = pos[lang]
        t = d["templates"][next(draws) % len(d["templates"])]
        scope = d["scopes"][next(draws) % len(d["scopes"])]
        evs = d["evaluators"].get(t["evaluator"])
        ev = evs[next(draws) % len(evs)] if evs else None
        slot = next(draws) % (paragraphs + 1)
        out.append(Canary(_positive(lang, t, scope, ev), slot, True, lang, t["family"], t["form"]))
    if next(draws) % 100 < NEGATIVE_PERCENT:
        neg = data["negative"]
        nlangs = sorted(neg)
        lang = nlangs[next(draws) % len(nlangs)]
        template = neg[lang][next(draws) % len(neg[lang])]
        a, b = 2 + next(draws) % 37, 2 + next(draws) % 23
        slot = next(draws) % (paragraphs + 1)
        out.append(Canary(_negative(template, a, b), slot, False, lang, "", "negative"))
    return tuple(out)
