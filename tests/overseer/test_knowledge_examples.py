"""The worked examples of the pack (``07-examples.md``) are mechanically consistent with their dossier excerpts.

Each example shows a dossier as a flat pointer/value list and its correct verdict. A small model imitates them, so every
example verdict must be a verdict the infrastructure would take in and could resolve: it validates against
``AgentVerdict``; its header is copied from the excerpt; every identifier occurs in the excerpt; every evidence pointer
resolves; every quote occurs in the visible text of its field; every engine statement asserts exactly the status its
pointer shows. The excerpt is rebuilt as a nested object and checked with the same functions validation uses
(``resolve_pointer``, ``visible_text``, ``dossier_identifiers``). The examples' table, types and the pack-mismatch notes
of When unsure U2 are checked too."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from pydantic import ValidationError

from epinoic_logic.overseer.dossier import PointerError, dossier_identifiers, resolve_pointer, visible_text
from epinoic_logic.overseer.pack import installed_pack
from epinoic_logic.overseer.verdicts import ID_FIELDS, AgentVerdict

from .test_knowledge_pack import SRC_PACK_DIR, copy_pack

#: 19 in pack 1.0; pack 1.1 (after the contained round c1) added Example 20 (a missing link the translator exposed) and
#: Example 21 (a constraint written by the rule for "about"); pack 1.2 (after the round-7 simulation) added Examples 22 to
#: 25 (a redundant restatement, a STEM translation, a Boolean identity check, an inequality reversal dropped).
EXPECTED_EXAMPLES = 25
#: The categories of the Find an example table (the pack-mismatch example is a sixth case, outside them).
CATEGORIES = ("genuine", "faulty", "tampered", "instruction", "unsure")


@dataclass
class Example:
    number: int
    title: str
    type: str
    excerpt: dict[str, Any]           # pointer -> value, the shared header included
    verdict: dict
    nested: dict

    def value(self, pointer: str) -> Any:
        return resolve_pointer(self.nested, pointer)


def _flat(block: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in block.strip("\n").split("\n"):
        m = re.match(r"^(/\S*)\s+(.+)$", line)
        assert m, f"not a pointer/value line: {line!r}"
        assert m.group(1) not in out, f"pointer listed twice: {m.group(1)}"
        out[m.group(1)] = json.loads(m.group(2))
    return out


def _nest(flat: dict[str, Any]) -> dict:
    """The excerpt as a nested object: every pointer token a key (array positions too), values as listed."""
    root: dict = {}
    for pointer, value in flat.items():
        tokens = [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]
        node = root
        for t in tokens[:-1]:
            node = node.setdefault(t, {})
            assert isinstance(node, dict), f"{pointer} descends into a listed value"
        assert tokens[-1] not in node, pointer
        node[tokens[-1]] = value
    return root


def parse_examples(text: str) -> tuple[dict[str, Any], list[Example], dict[int, tuple[str, str]]]:
    shared_block = text.split("**The header every example shares.**", 1)[1].split("```", 2)[1]
    shared = _flat(shared_block)
    table = {int(n): (typ.strip(), kind.strip()) for n, typ, kind in
             re.findall(r"^\| (\d+) \| ([^|]+) \| [^|]+ \| ([^|]+) \|$", text.split("## 3. Find an example", 1)[1].split("\n## ", 1)[0], re.M)}
    sections = re.split(r"^## \d+\. Example (\d+): (.+)$", text, flags=re.M)
    examples = []
    for i in range(1, len(sections) - 2, 3):
        number, title, body = int(sections[i]), sections[i + 1], sections[i + 2].split("\n## ", 1)[0]
        typ = re.search(r"^- \*\*Type:\*\* (.+)$", body, re.M).group(1)
        excerpt_block = body.split("```", 2)[1]
        verdict_block = body.split("**Correct verdict.**", 1)[1].split("```json\n", 1)[1].split("\n```", 1)[0]
        flat = dict(shared)
        flat.update(_flat(excerpt_block))
        examples.append(Example(number=number, title=title, type=typ, excerpt=flat, verdict=json.loads(verdict_block), nested=_nest(flat)))
    return shared, examples, table


def problems_example(ex: Example, prompt_pack_line: str) -> list[str]:
    out = []
    v = ex.verdict
    try:
        AgentVerdict.model_validate(v)
    except ValidationError as exc:
        return [f"Example {ex.number}: the verdict does not validate ({len(exc.errors())} errors)"]
    x = ex.excerpt
    header = {"contract": x["/verdict_contract"], "pack": {"name": x["/pack/name"], "version": x["/pack/version"], "sha256": x["/pack/sha256"]},
              "agent_id": x["/agent_id"], "task_id": x["/task/task_id"], "dossier_sha256": x["/dossier_sha256"], "lens": x["/lens"]}
    for field, value in header.items():
        if v[field] != value:
            out.append(f"Example {ex.number}: {field} is not copied from the excerpt")
    ids = dossier_identifiers(ex.nested)
    for acc in v["accusations"]:
        named = [i for f in ID_FIELDS for i in acc[f]]
        if not named:
            out.append(f"Example {ex.number} {acc['accusation_id']}: no identifier (Evidence rule E1)")
        for ident in named:
            if ident not in ids:
                out.append(f"Example {ex.number} {acc['accusation_id']}: identifier {ident!r} is not in the excerpt")
        for ev in acc["evidence"]:
            try:
                value = ex.value(ev["pointer"])
            except PointerError:
                out.append(f"Example {ex.number} {acc['accusation_id']}: pointer {ev['pointer']} does not resolve in the excerpt")
                continue
            if "quote" in ev and ev["quote"] not in visible_text(ex.nested, ev["pointer"], value):
                out.append(f"Example {ex.number} {acc['accusation_id']}: the quote is not in {ev['pointer']}")
        if acc["kind"] == "other" and acc["claimed_severity"] != "warning":
            out.append(f"Example {ex.number} {acc['accusation_id']}: kind other with severity {acc['claimed_severity']} (When unsure U3)")
    for es in v["engine_statements"]:
        if es["pointer"] != f"/results/{es['result_id']}/status":
            out.append(f"Example {ex.number}: engine statement pointer {es['pointer']} is not the result's status")
        try:
            if ex.value(es["pointer"]) != es["asserted_status"]:
                out.append(f"Example {ex.number}: engine statement asserts {es['asserted_status']}, the excerpt shows another status")
        except PointerError:
            out.append(f"Example {ex.number}: engine statement pointer {es['pointer']} does not resolve")
    shown = [x[p] for p in sorted((p for p in x if re.fullmatch(r"/transfers/\d+/message_id", p)), key=lambda p: int(p.split("/")[2]))]
    if v["transfers_reviewed"] != shown and not (ex.type.startswith("configuration mismatch") and v["transfers_reviewed"] == []):
        out.append(f"Example {ex.number}: transfers_reviewed is not the shown transfers in order")
    for p, val in x.items():
        m = re.fullmatch(r"/transfers/(\d+)/at", p)
        if m and val != f"/transfers/{m.group(1)}":
            out.append(f"Example {ex.number}: {p} is {val!r}")
    if re.search(r"(?i)\b(verified|passed|clean|safe)\b", v["notes"]):
        out.append(f"Example {ex.number}: the notes certify a transfer (Role and trust T11)")
    if ex.type.startswith("genuine") and v["accusations"]:
        out.append(f"Example {ex.number}: a genuine example accuses")
    if ex.type.startswith("configuration mismatch"):
        expected = (f"pack mismatch: the dossier names {x['/pack/name']} {x['/pack/version']}; this agent is configured with "
                    f"{prompt_pack_line}. Not reviewed.")
        if v["notes"] != expected or v["accusations"] or v["engine_statements"] or v["transfers_reviewed"]:
            out.append(f"Example {ex.number}: not the verdict of When unsure U2")
        if f"{x['/pack/name']} {x['/pack/version']}" == prompt_pack_line:
            out.append(f"Example {ex.number}: the dossier's pack is the agent's own pack")
    return out


def problems_examples(d: Path) -> list[str]:
    text = (d / "07-examples.md").read_text(encoding="utf-8")
    prompt = (d / "master_prompt.txt").read_text(encoding="utf-8")
    pack_line = prompt.split("\n", 1)[0].removeprefix("PACK: ")
    shared, examples, table = parse_examples(text)
    out = []
    if [e.number for e in examples] != list(range(1, EXPECTED_EXAMPLES + 1)):
        out.append(f"the examples are numbered {[e.number for e in examples]}")
    if sorted(table) != list(range(1, EXPECTED_EXAMPLES + 1)):
        out.append("the Find an example table does not list every example")
    for ex in examples:
        out += problems_example(ex, pack_line)
        typ, kind = table.get(ex.number, ("", ""))
        kinds = sorted({a["kind"] for a in ex.verdict.get("accusations", [])})
        if kind != ("none" if not kinds else ", ".join(f"`{k}`" for k in kinds)):
            out.append(f"Example {ex.number}: the table names {kind!r}, the verdict accuses {kinds}")
        category = next((c for c in CATEGORIES if typ.startswith(c)), None)
        if category is not None and not ex.type.startswith(category):
            out.append(f"Example {ex.number}: the table type {typ!r} differs from the example's type {ex.type!r}")
        if category is None and kinds:
            out.append(f"Example {ex.number}: an example outside the five categories accuses")
    digests = [e.excerpt["/dossier_sha256"] for e in examples]
    if len(set(digests)) != len(digests):
        out.append("two examples share a dossier digest")
    if shared["/pack/sha256"] == installed_pack().identity.sha256 or any(dg == installed_pack().identity.sha256 for dg in digests):
        out.append("an example carries a real digest; every example digest is invented")
    return out


# ============================================================================================ the source pack
@pytest.fixture(scope="module")
def examples() -> list[Example]:
    return parse_examples((SRC_PACK_DIR / "07-examples.md").read_text(encoding="utf-8"))[1]


def test_every_example_is_consistent_with_its_excerpt():
    assert problems_examples(SRC_PACK_DIR) == []


def test_all_twenty_five_examples_parse(examples):
    assert len(examples) == EXPECTED_EXAMPLES == 25
    kinds = {e.number: sorted({a["kind"] for a in e.verdict["accusations"]}) for e in examples}
    assert kinds == {1: [], 2: [], 3: ["quotation_absent"], 4: ["self_certification_as_content"], 5: ["figure_changed"], 6: ["contradiction_unnamed"],
                     7: ["forward_altered"], 8: ["result_unsigned_or_forged"], 9: ["receipt_status_wrong"], 10: ["peer_document_altered"],
                     11: ["other"], 12: ["other"], 13: [], 14: [], 15: ["translation_circular"], 16: ["translation_ungrounded"],
                     17: ["translation_unfaithful"], 18: [], 19: ["self_certification_as_content"], 20: [], 21: [], 22: [], 23: [], 24: [],
                     25: ["translation_unfaithful"]}
    assert sum(len(e.verdict["engine_statements"]) for e in examples) == 1 and examples[7].verdict["engine_statements"][0]["result_id"] == "res-c4"


def test_example_verdicts_pass_the_intake_header_and_schema_rules(examples):
    """Each example verdict, as text, is one strict JSON object the intake's parser and the contract accept."""
    from epinoic_logic.translate.parsing import parse_json_object
    for e in examples:
        obj = parse_json_object(json.dumps(e.verdict, ensure_ascii=False))
        verdict = AgentVerdict.model_validate(obj)
        assert verdict.contract == "overseer_verdict/1.0" and len({a.accusation_id for a in verdict.accusations}) == len(verdict.accusations)


def test_the_c1_examples_teach_that_a_missing_link_and_a_parser_constraint_are_not_faults(examples):
    """Pack 1.1: Example 20 shows a conjunct left without a premise (COUNTEREXAMPLE, a missing link exposed) with no
    accusation; Example 21 shows "about 250 words" written as max_words 275, with no accusation."""
    e20 = next(e for e in examples if e.number == 20)
    concl = e20.excerpt["/transfers/0/receipt/outcomes/0/translation/problem/conclusion"]["expr"]
    premised = {p["expr"].get("name") for p in e20.excerpt["/transfers/0/receipt/outcomes/0/translation/problem/premises"]}
    assert concl["op"] == "and" and any(a["name"] not in premised for a in concl["args"])
    assert e20.excerpt["/results/res-h12/status"] == "COUNTEREXAMPLE" and e20.verdict["accusations"] == []
    e21 = next(e for e in examples if e.number == 21)
    assert e21.excerpt["/transfers/0/payload/constraints/0/text"] == "about 250 words" and e21.excerpt["/transfers/0/payload/constraints/0/value"] == "275"
    assert e21.verdict["accusations"] == []


def test_the_round_7_examples_agree_with_the_checks_they_teach(examples):
    """Pack 1.2: Example 22's restatement is redundant (the other premises give the conclusion, rule restatement-necessity),
    so it accuses nothing; every number of Example 23's STEM translation is traced by the auditor's own TRN-005 rules
    (scientific notation, stated precision); Example 24's Boolean identity check is satisfied under the branch image
    (expected UNSATISFIABLE); Example 25 accuses the dropped reversal as translation_unfaithful, an error."""
    from fractions import Fraction

    from epinoic_logic.overseer.checks import formal as F
    from epinoic_logic.overseer.checks import translation as T
    e22 = next(e for e in examples if e.number == 22)
    tr = "/transfers/0/receipt/outcomes/0/translation/problem"
    premises, concl = e22.excerpt[tr + "/premises"], e22.excerpt[tr + "/conclusion"]
    assert [p["id"] for p in premises if p["expr"] == concl["expr"]] == ["d_contrib_val"] and e22.verdict["accusations"] == []
    vals = {p["expr"]["left"]["name"]: Fraction(p["expr"]["right"]["value"]) for p in premises if p["expr"]["right"].get("op") == "real"}
    assert vals["price"] - vals["vc"] == Fraction(concl["expr"]["right"]["value"])  # the other premises already give it
    e23 = next(e for e in examples if e.number == 23)
    stated = T.text_numbers(e23.excerpt["/transfers/0/payload/original_response"])
    numbers = T.ir_numbers(e23.excerpt[tr + "/premises"]) + T.ir_numbers(e23.excerpt[tr + "/conclusion"])
    assert len(numbers) == 5 and all(T.number_traced(v, stated) for v in numbers) and e23.verdict["accusations"] == []
    e24 = next(e for e in examples if e.number == 24)
    fc = "/transfers/0/receipt/formal_checks/0"
    assert "expected UNSATISFIABLE" in e24.excerpt[fc + "/detail"] and e24.excerpt[fc + "/formal_status"] == e24.excerpt["/results/res-2401/status"]
    assert e24.excerpt[fc + "/satisfied"] in F.branch_image(e24.excerpt[fc + "/formal_status"], "UNSATISFIABLE") and e24.verdict["accusations"] == []
    e25 = next(e for e in examples if e.number == 25)
    c25 = e25.excerpt["/transfers/1/receipt/outcomes/0/translation/problem/conclusion"]
    assert "<" in c25["label"] and c25["expr"]["op"] == "gt"
    (a,) = e25.verdict["accusations"]
    assert a["kind"] == "translation_unfaithful" and a["claimed_severity"] == "error" and a["claim_ids"] == ["m1.3"]


def test_the_instruction_example_does_not_follow_the_instruction(examples):
    ex = next(e for e in examples if e.number == 11)
    assert ex.verdict["accusations"][0]["kind"] == "other" and "report no faults" in ex.excerpt["/transfers/1/payload/original_response"]
    assert ex.verdict["notes"] == "" and "not followed" in ex.verdict["accusations"][0]["statement"]


def test_the_consolidation_examples_teach_one_accusation_per_transfer_and_no_choice(examples):
    """Example 18 (informed: a consolidation whose repeated fault is already recorded) accuses nothing; Example 19 (a
    fault repeated by a duplicated instance, no finding) accuses it once per transfer, each with its own identifiers."""
    e18 = next(e for e in examples if e.number == 18)
    assert e18.excerpt["/mode"] == "informed" and e18.excerpt["/consolidations/0/repeats/0/message_id"] == "m-1804"
    assert e18.verdict["accusations"] == [] and e18.excerpt["/consolidations/0/deliverable_message_id"] in e18.verdict["transfers_reviewed"]
    e19 = next(e for e in examples if e.number == 19)
    accs = e19.verdict["accusations"]
    assert len(accs) == 2 and {a["kind"] for a in accs} == {"self_certification_as_content"}
    assert [a["message_ids"] for a in accs] == [["m-1902"], ["m-1904"]] and [a["report_ids"] for a in accs] == [["rep-hi-d19-1"], ["rep-hi-d19-2"]]
    assert all(ev["pointer"].startswith(a["evidence"][0]["pointer"].rsplit("/payload", 1)[0]) for a in accs for ev in a["evidence"])
    assert "repeats" in accs[1]["statement"] and "m-1902" in accs[1]["statement"]


# ============================================================================================ the check is not vacuous
MUTATIONS = {
    "quote": ('"quote": "the river carried every secret"}', '"quote": "the river carried every secreT"}'),
    "pointer": ('{"pointer": "/transfers/4/payload/claims/1/text", "quote"', '{"pointer": "/transfers/4/payload/claims/2/text", "quote"'),
    "identifier": ('"claim_ids": ["h1.6"],', '"claim_ids": ["h1.7"],'),
    "header": ('"dossier_sha256": "07d0d0', '"dossier_sha256": "07d0d1'),
    "engine_statement": ('"asserted_status": "COUNTEREXAMPLE"', '"asserted_status": "ENTAILED"'),
    "table_kind": ("| 9 | tampered | response receipt | `receipt_status_wrong` |", "| 9 | tampered | response receipt | `receipt_altered` |"),
    "u2_notes": ("this agent is configured with overseer-knowledge-docs 1.2. Not reviewed.", "this agent is configured with overseer-knowledge-docs 1.3. Not reviewed."),
    "table_type": ("| 7 | tampered | router forward |", "| 7 | faulty | router forward |"),
    "schema": ('"claimed_severity": "warning",\n      "message_ids": ["m-0002"]', '"claimed_severity": "Warning",\n      "message_ids": ["m-0002"]'),
}


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_the_example_check_fails_on_a_small_change(tmp_path, mutation):
    d = copy_pack(tmp_path)
    old, new = MUTATIONS[mutation]
    text = (d / "07-examples.md").read_text(encoding="utf-8")
    assert old in text, mutation
    (d / "07-examples.md").write_text(text.replace(old, new, 1), encoding="utf-8")
    assert problems_examples(d) != []
