#!/usr/bin/env python3
"""Build ``tests/stem/data/stem_corpus.json``: the labelled STEM corpus of stage ``corpus-eval``
(docs/STEM_DESIGN.md, section 16).

Run from the repository root:  python tests/stem/data/build_stem_corpus.py

The corpus holds three sources, each item with its gold labels:

* the 84 hand-written items of ``tests/fixtures/stem/corpus`` (46 correct, 38 with one fault),
  copied verbatim (``tests/stem/test_corpus.py`` checks the copies against the fixtures);
* the 22 probe answers of section 1 (``tests/channel/test_stem_channel.py``): the 13
  deliberately wrong answers that crossed the hub silently before STEM support, and 9 correct;
* items written here from templates (``corpus_items.py``), each in one notation, with its
  mutants (one injected fault each, drawn from the fault catalogue of section 16) and its
  rounding-only controls (a correct result written to fewer figures: they must pass).

Labels never come from the implementation under test. Every numeric label is exact
``Fraction`` arithmetic over decimal strings this builder writes (``corpus_lib.py`` states the
rule: a correct step holds at the written values with τ = 0; a fault fails over the widest
reading with τ = 1/20); chemical balances, Boolean identities, truth tables and based numerals
are tallied or enumerated from data the builder writes, never from the item text. No item text
is evaluated anywhere.
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction as F
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from corpus_dsl import Item, Mut, Step, fault_proof, mismatch_proof, numeric_proof, scaled  # noqa: E402
from corpus_lib import Iv, W, holds_point, leading_digit_slip, point, round_sig  # noqa: E402

ROOT = HERE.parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "stem" / "corpus"
OUT = HERE / "stem_corpus.json"

#: the fault catalogue (section 16): class -> codes that name it, the check kinds that decide it, severity
CATALOGUE = {
    "arithmetic_slip": (["INT-SUBJ-001"], ["eq"], "error"),
    "wrong_operator": (["INT-SUBJ-001"], ["eq", "sub"], "error"),
    "power_of_ten": (["INT-SUBJ-001"], ["eq", "cnv", "sub"], "error"),
    "wrong_substitution": (["INT-SUBJ-001"], ["sub"], "error"),
    "dropped_factor": (["INT-SUBJ-001"], ["sub", "eq"], "error"),
    "wrong_rearrangement": (["INT-SUBJ-001"], ["alg"], "error"),
    "lost_root": (["INT-SUBJ-001", "ST-ALG-001"], ["sol"], "error"),
    "unit_conversion": (["INT-SUBJ-001"], ["cnv", "eq"], "error"),
    "wrong_restatement": (["INT-SUBJ-001"], ["res"], "error"),
    "unbalanced_atoms": (["INT-SUBJ-001"], ["chem"], "error"),
    "unbalanced_charge": (["INT-SUBJ-001"], ["chem"], "error"),
    "wrong_boolean_identity": (["INT-SUBJ-001"], ["bool"], "error"),
    "wrong_truth_table_row": (["INT-SUBJ-001"], ["tt"], "error"),
    "wrong_base_conversion": (["INT-SUBJ-001"], ["base"], "error"),
    "sign_error": (["INT-SUBJ-001"], ["eq", "res"], "error"),
    "wrong_comparison": (["INT-SUBJ-001"], ["cmp"], "error"),
    "misstated_given": (["INT-SUBJ-004"], ["giv"], "warning"),
    "show_that_mismatch": (["INT-SUBJ-004"], ["tgt"], "warning"),
    "dimension_error": (["ST-DIM-001", "ST-DIM-002"], [], "warning"),
}
CLASS_OF_KIND = {"eq": "arithmetic_slip", "cnv": "unit_conversion", "res": "wrong_restatement"}


# ------------------------------------------------------------------------------------- automatic mutants
def _replace_last(text: str, old: str, new: str) -> str:
    k = text.rfind(old)
    if k < 0:
        raise ValueError(f"{old!r} not in {text!r}")
    return text[:k] + new + text[k + len(old):]


def _stated_mutant(it: Item, st: Step, new_spec: str, new_text: str, cls: str, note: str) -> Optional[Mut]:
    proof = fault_proof(st.expr, new_spec)
    if not proof["fails"]:
        return None  # an automatic mutant that does not provably fail is not a fault: it is left out
    codes, kinds, sev = CATALOGUE[cls]
    kinds = [st.kind] if st.kind in kinds else kinds
    return Mut(cls, st.key, [(st.stated(), new_text, st.text, "last")], tuple(codes), tuple(kinds), proof, note, severity=sev)


def auto_mutants(it: Item) -> list[Mut]:
    out: list[Mut] = []
    numeric = [s for s in it.steps if s.kind in ("eq", "cnv", "res") and s.S is not None and s.mutable]
    if not numeric:
        return out
    eqs = [s for s in numeric if s.kind in ("eq", "cnv")]
    if "slip" in it.auto and eqs:
        st = eqs[0]
        if st.sci is not None:
            mant, exp, r = st.sci
            nm = leading_digit_slip(mant)
            out.append(_stated_mutant(it, st, f"{nm}e{exp}", r.sci(nm, exp), CLASS_OF_KIND[st.kind],
                                      f"the stated mantissa {mant} became {nm}"))
        else:
            ns = leading_digit_slip(st.S)
            out.append(_stated_mutant(it, st, ns, it.r.num(ns), CLASS_OF_KIND[st.kind], f"the stated value {st.S} became {ns}"))
    if "pow10" in it.auto and eqs:
        st = eqs[-1] if len(eqs) > 1 else eqs[0]
        if st.sci is not None:
            mant, exp, r = st.sci
            out.append(_stated_mutant(it, st, f"{mant}e{exp + 1}", r.sci(mant, exp + 1), "power_of_ten", f"the exponent {exp} became {exp + 1}"))
        elif not st.S.lstrip("-").startswith("0") or "." in st.S:
            ns = scaled(st.S, 1)
            out.append(_stated_mutant(it, st, ns, it.r.num(ns), "power_of_ten", f"the stated value {st.S} became {ns} (a factor of ten)"))
    if "res" in it.auto:
        res = [s for s in numeric if s.kind == "res"]
        if res:
            st = res[-1]
            if st.sci is not None:
                mant, exp, r = st.sci
                nm = leading_digit_slip(mant)
                out.append(_stated_mutant(it, st, f"{nm}e{exp}", r.sci(nm, exp), "wrong_restatement", f"the restated mantissa {mant} became {nm}"))
            else:
                ns = leading_digit_slip(st.S)
                rr = it.r if st.S_text == it.r.num(st.S) else None
                text = rr.num(ns) if rr is not None else st.stated().replace(st.S.lstrip("-"), ns.lstrip("-"), 1)
                out.append(_stated_mutant(it, st, ns, text, "wrong_restatement", f"the restated value {st.S} became {ns}"))
    if "sign" in it.auto:
        cands = [s for s in numeric if s.sign_ok and not s.S.startswith("-") and not (isinstance(s.expr(point), F) and s.expr(point) == 0)]
        res = [s for s in cands if s.kind == "res"]
        st = (res or [s for s in cands if s.kind == "eq"] or [None])[0]
        if st is not None:
            ns = "-" + st.S
            text = it.r.neg(st.stated()) if st.sci is None else it.r.minus + st.stated()
            out.append(_stated_mutant(it, st, ns, text, "sign_error", f"the stated value {st.S} lost its sign: {ns}"))
    return out


def controls(it: Item) -> list[tuple[str, Step, str]]:
    """Rounding-only controls: the first decimal result written to one significant figure fewer (still correct)."""
    if "round" not in it.auto:
        return []
    for st in it.steps:
        if st.kind != "eq" or st.S is None or st.sci is not None or "." not in st.S or not st.mutable:
            continue
        C = st.expr(point)
        if isinstance(C, Iv):
            continue
        digits = st.S.lstrip("-").replace(".", "").lstrip("0")
        sf = len(digits)
        if sf < 2:
            continue
        ns = round_sig(C, sf - 1)
        if ns == st.S or not holds_point(C, W(ns)):
            continue
        return [(ns, st, it.r.num(ns))]
    return []


# ------------------------------------------------------------------------------------------- assembly
def _dependents(it: Item, key: str) -> set[str]:
    out = {key}
    changed = True
    while changed:
        changed = False
        for s in it.steps:
            if s.key not in out and any(d in out for d in s.deps):
                out.add(s.key)
                changed = True
    return out


def _once(text: str, sub: str, what: str) -> None:
    n = text.count(sub)
    if n != 1:
        raise ValueError(f"{what}: {sub!r} occurs {n} times")


def _edits(response: str, repl: list[tuple], ident: str) -> list[tuple[int, int, str]]:
    """Replacements as edits of the original response, never overlapping. A replacement is ``(old, new)`` with ``old``
    occurring exactly once, or ``(old, new, anchor)`` / ``(old, new, anchor, "last")``: ``anchor`` occurs exactly once and the
    edit is the first (or last) occurrence of ``old`` inside it, so an edit touches only the characters that change."""
    edits = []
    for rp in repl:
        old, new = rp[0], rp[1]
        if len(rp) == 2:
            _once(response, old, f"{ident}: replacement")
            a = response.index(old)
        else:
            anchor = rp[2]
            _once(response, anchor, f"{ident}: anchor")
            base = response.index(anchor)
            k = anchor.rfind(old) if len(rp) > 3 and rp[3] == "last" else anchor.find(old)
            if k < 0:
                raise ValueError(f"{ident}: {old!r} not inside its anchor {anchor!r}")
            a = base + k
        edits.append((a, a + len(old), new))
    edits.sort()
    for (a1, b1, _), (a2, _b2, _) in zip(edits, edits[1:]):
        if a2 < b1:
            raise ValueError(f"{ident}: overlapping replacements")
    return edits


def _apply(response: str, edits: list[tuple[int, int, str]]) -> str:
    out, cur = [], 0
    for a, b, new in edits:
        out.append(response[cur:a])
        out.append(new)
        cur = b
    out.append(response[cur:])
    return "".join(out)


def _map(x: int, side: str, edits: list[tuple[int, int, str]]) -> int:
    """An offset of the original response in the edited one; a step boundary inside an edit widens to the edit."""
    shift = 0
    for a, b, new in edits:
        if b <= x:
            shift += len(new) - (b - a)
        elif a < x < b:
            return a + shift + (0 if side == "start" else len(new))
    return x + shift


def _step_texts(it: Item, response: str, edits: list[tuple[int, int, str]]) -> dict[str, str]:
    mutated = _apply(response, edits)
    out = {}
    for s in it.steps:
        a = response.index(s.text)
        b = a + len(s.text)
        out[s.key] = mutated[_map(a, "start", edits):_map(b, "end", edits)]
    return out


def _record(it: Item, ident: str, role: str, response: str, faults: list[dict], correct: list[str], affected: list[str], parent=None) -> dict:
    return {"id": ident, "role": role, "parent": parent, "source": "built", "subject": it.subject, "topic": it.topic, "task_type": it.task_type,
            "question": it.question, "supplied_texts": it.supplied, "response_text": response, "notation": it.notation,
            "gold": {"faults": faults, "correct_steps": correct, "affected_steps": affected,
                     "undecided": [{"step": t, "expected_codes": list(c), "reason": why} for t, c, why in it.undecided if t in response]}}


def build_item(it: Item) -> list[dict]:
    resp = it.response
    for s in it.steps:
        _once(resp, s.text, f"{it.id} step {s.key}")
        if s.expr is not None and s.S is not None:
            s.proof = numeric_proof(s)
        if not s.proof or not (s.proof.get("holds") is True):
            raise ValueError(f"{it.id} step {s.key}: no proof that it holds: {s.proof}")
    for t, _c, _w in it.undecided:
        _once(resp, t, f"{it.id} undecided")
    recs = [_record(it, it.id, "correct", resp, [], [s.text for s in it.steps], [])]
    for ns, st, ntext in controls(it):
        edits = _edits(resp, [(st.stated(), ntext, st.text, "last")], it.id)
        cresp = _apply(resp, edits)
        texts = _step_texts(it, resp, edits)
        rec = _record(it, f"{it.id}--control-1", "control", cresp, [], [texts[s.key] for s in it.steps], [], parent=it.id)
        rec["gold"]["control"] = {"step": texts[st.key], "note": f"rounding only: {st.S} written as {ns}", "proof": {"C": numeric_proof(st)["C"], "S": ns,
                                  "holds": True, "rule": "|C - S| <= h(S) at the written values"}}
        recs.append(rec)
    muts = [m for m in auto_mutants(it) if m is not None] + list(it.muts)
    seen: dict[str, int] = {}
    for m in muts:
        if not (m.proof.get("fails") is True or m.proof.get("holds") is False):
            raise ValueError(f"{it.id} {m.cls}: the proof does not establish a fault: {m.proof}")
        seen[m.cls] = seen.get(m.cls, 0) + 1
        ident = f"{it.id}--{m.cls}-{seen[m.cls]}"
        edits = _edits(resp, m.repl, ident)
        mresp = _apply(resp, edits)
        texts = _step_texts(it, resp, edits)
        hit = _dependents(it, m.target) | set(m.affected)
        fault_text = texts[m.target]
        _once(mresp, fault_text, f"{ident} fault step")
        correct = [texts[s.key] for s in it.steps if s.key not in hit]
        affected = [texts[s.key] for s in it.steps if s.key in hit and s.key != m.target]
        for t in correct + affected:
            _once(mresp, t, f"{ident} step")
        codes, kinds, sev = list(m.codes), list(m.kinds), m.severity
        note = m.note
        if it.unknown_units and "INT-SUBJ-001" in codes:
            codes.append("INT-SUBJ-004")
            note += " (the unit yr is not in the design's unit table: the relation is checked as written only and a failure is INT-SUBJ-004, section 6.4)"
        faults = [{"class": m.cls, "step": fault_text, "expected_codes": codes, "check_kinds": kinds, "severity": sev, "note": note, "proof": m.proof}]
        recs.append(_record(it, ident, "mutant", mresp, faults, correct, affected, parent=it.id))
    return recs


#: mutants of the classes every formula answer yields are kept up to this many per class (round-robin over subjects, in id
#: order), so the corpus stays balanced across the catalogue and its run through the hub stays fast
COMMON_CAP = 22
COMMON = ("arithmetic_slip", "power_of_ten", "sign_error", "wrong_substitution", "wrong_restatement", "dimension_error", "wrong_operator",
          "misstated_given")


def select(records: list[dict]) -> list[dict]:
    by_class: dict[str, dict[str, list[dict]]] = {}
    for r in records:
        if r["source"] == "built" and r["role"] == "mutant" and r["gold"]["faults"][0]["class"] in COMMON:
            by_class.setdefault(r["gold"]["faults"][0]["class"], {}).setdefault(r["subject"], []).append(r)
    drop: set[str] = set()
    for cls, subjects in by_class.items():
        queues = [list(v) for _k, v in sorted(subjects.items())]
        chosen: list[dict] = []
        while len(chosen) < COMMON_CAP and any(queues):
            for q in queues:
                if q and len(chosen) < COMMON_CAP:
                    chosen.append(q.pop(0))
        keep = {r["id"] for r in chosen}
        drop |= {r["id"] for v in subjects.values() for r in v if r["id"] not in keep}
    return [r for r in records if r["id"] not in drop]


def fixture_records() -> list[dict]:
    out = []
    for p in sorted(FIXTURES.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        faults = []
        for f in d["gold"]["faults"]:
            cls = f["kind"]
            codes = f["expected_codes"]
            faults.append({"class": cls, "step": f["step"], "expected_codes": codes, "check_kinds": [], "severity": "warning" if codes[0] != "INT-SUBJ-001" else "error",
                           "note": f["note"]})
        out.append({"id": d["id"], "role": "mutant" if faults else "correct", "parent": None, "source": f"tests/fixtures/stem/corpus/{p.name}",
                    "subject": d["subject"], "topic": "", "task_type": d["task_type"], "question": d["question"], "supplied_texts": d.get("supplied_texts", []),
                    "response_text": d["response_text"], "notation": d["notation"],
                    "gold": {"faults": faults, "correct_steps": d["gold"]["correct_steps"], "affected_steps": [], "undecided": []}})
    return out


def main() -> None:
    from corpus_items import ITEMS, PROBES, FIXTURE_LABELS
    records = []
    for rec in fixture_records():
        extra = FIXTURE_LABELS.get(rec["id"])
        if extra:
            for k, v in extra.items():
                if k == "check_kinds":
                    rec["gold"]["faults"][0]["check_kinds"] = v
                else:
                    rec["gold"][k] = v
        records.append(rec)
    records.extend(PROBES)
    for it in ITEMS:
        records.extend(build_item(it))
    records = select(records)
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids")
    corpus = {
        "schema": "stem_corpus/1.0",
        "description": "Labelled STEM answers for stage corpus-eval (docs/STEM_DESIGN.md, section 16). Built by tests/stem/data/build_stem_corpus.py; "
                       "labels are exact Fraction arithmetic over values the builder writes (see corpus_lib.py), never output of the implementation.",
        "label_rule": {"correct": "a correct step holds at the written values: |C - S| <= h(S) with tau = 0 (h = 0 for exact work)",
                       "fault": "a fault fails over the widest reading: every decimal operand over [w - h(w), w + h(w)], constants hulled with their "
                                "booklet values, the band h_wide(S) + |C|/20",
                       "substitution_and_restatement": "|a - b| > h_wide(a) + h_wide(b)"},
        "catalogue": {k: {"expected_codes": v[0], "check_kinds": v[1], "severity": v[2]} for k, v in CATALOGUE.items()},
        "selection": f"built mutants of the classes {', '.join(COMMON)} are kept up to {COMMON_CAP} per class, round-robin over subjects in id order; "
                     "every other built mutant, every correct answer and every control is kept",
        "items": records,
    }
    OUT.write_text(json.dumps(corpus, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    roles = {}
    for r in records:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
    print(f"wrote {OUT} with {len(records)} items: {roles}")


if __name__ == "__main__":
    main()
