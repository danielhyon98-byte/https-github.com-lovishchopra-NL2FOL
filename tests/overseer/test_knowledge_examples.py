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
#: 25 (a redundant restatement, a STEM translation, a Boolean identity check, an inequality reversal dropped); pack 1.3 (the
#: repair of the translator merge, design decision 49) added Example 26 (a restatement grounded by a label the code did
#: not verify, which the merged translator delivers: translation_circular); its second in-place correction (the second
#: repair, decision 51) added Example 27 (a conclusion restated in part under a task_setting label no number of the
#: request can verify, beside a transcription the request verifies: translation_circular); its third in-place correction
#: (the third repair, decision 55) rewrote Example 27 as the question's data restated by task settings the request states
#: (a transcription the code could not verify: no accusation, the reviewer's finding on record version 4) and added Example
#: 28 (the answer's result restated as given where the request states it only as a "show that" target:
#: translation_circular); its fourth in-place correction (the fourth repair, decision 56: a Bool premise is never undecided,
#: only its label presents it as data) made Example 27 faulty on the same excerpt (translation_circular naming the Bool task
#: setting) and added Example 29 (the question's data restated by task settings the request states: no accusation).
#: The fifth repair (decision 57) added Example 30 (a number the request only requires, restated as given:
#: translation_circular). The STEM completion (design section 31) added Example 31 (a STEM check that fails, named by its
#: receipt: no accusation) and Example 32 (a STEM check whose detail was rewritten to read as holding: receipt_altered).
#: STEM repair 1 (design section 32) added Example 33 (another stated given substituted in a STEM translation, decided by
#: no check: translation_unfaithful). STEM repair 2 (design section 33) added Example 34 (a Given value the receipt leaves with
#: neither its check nor its ST code: finding_missing). STEM repair 3 (design section 34) added Example 35 (a Given stated under a
#: condition, checked against the supplied table's row: no accusation, the condition is no Given of its own). STEM repair 4 (design section
#: 35) added Example 36 (a Boolean expression evaluated under the values its statement gives, checked by the branch: no accusation).
#: STEM repair 5 (design section 36) added Example 37 (a symbol reused for another quantity, its substitution checked against the
#: part's own result by rule part-value: no accusation). STEM repair 6 (design section 37) added Example 38 (a Given written in a
#: Data list, its contradiction named by its check: no accusation). STEM repair 8 (design section 39) added Example 39 (a law its
#: evaluation does not follow, named by its check: no accusation). STEM repair 9 (design section 40) added Example 40 (a Given of a
#: function's value, set against the request's function and named by its check: no accusation).
EXPECTED_EXAMPLES = 40
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


def test_all_forty_examples_parse(examples):
    # renamed from test_all_thirty_nine_examples_parse (STEM repair 9 added Example 40, a Given of a function's value set against the
    # request's function, named by its check: no accusation), itself from test_all_thirty_eight_examples_parse (STEM repair 8 added
    # Example 39, a law its evaluation does not follow, named
    # by its check: no accusation), itself from test_all_thirty_seven_examples_parse (STEM repair 6 added Example 38, a Given written
    # in a Data list, its contradiction named by its check: no accusation), itself from test_all_thirty_six_examples_parse (STEM repair 5 added
    # Example 37, a symbol reused for another quantity, its
    # substitution checked against the part's own result: no accusation), itself from test_all_thirty_five_examples_parse (STEM
    # repair 4 added Example 36, a Boolean evaluation under the values its
    # statement gives, checked by the branch: no accusation), itself from test_all_thirty_four_examples_parse (STEM repair 3 added Example 35, a Given stated under a condition, checked
    # against the supplied table's row: no accusation), itself from test_all_thirty_three_examples_parse (STEM repair 2 added
    # Example 34, a Given value the receipt leaves with
    # neither its check nor its ST code: finding_missing), itself from test_all_thirty_two_examples_parse (STEM repair 1 added
    # Example 33, another stated given substituted in a
    # STEM translation: translation_unfaithful), itself from test_all_thirty_examples_parse (the STEM completion added
    # Example 31, a STEM check named by its receipt,
    # and Example 32, a STEM check's detail rewritten: receipt_altered, with the second engine statement of the pack), itself
    # from test_all_twenty_nine_examples_parse (the fifth repair of the translator merge added Example 30, a number
    # the request only requires restated as given: translation_circular), itself from test_all_twenty_eight_examples_parse
    # (the fourth repair of the translator merge added Example 29 and made
    # Example 27 translation_circular: its Bool task setting is what only a label presents as data), itself from
    # test_all_twenty_seven_examples_parse (the third repair added Example 28 and made Example 27 a transcription the code
    # could not verify, no accusation), test_all_twenty_six_examples_parse (the second repair added Example 27) and
    # test_all_twenty_five_examples_parse (the first repair added Example 26): the same exact count and exact kinds per
    # example, one more example pinned
    assert len(examples) == EXPECTED_EXAMPLES == 40
    kinds = {e.number: sorted({a["kind"] for a in e.verdict["accusations"]}) for e in examples}
    assert kinds == {1: [], 2: [], 3: ["quotation_absent"], 4: ["self_certification_as_content"], 5: ["figure_changed"], 6: ["contradiction_unnamed"],
                     7: ["forward_altered"], 8: ["result_unsigned_or_forged"], 9: ["receipt_status_wrong"], 10: ["peer_document_altered"],
                     11: ["other"], 12: ["other"], 13: [], 14: [], 15: ["translation_circular"], 16: ["translation_ungrounded"],
                     17: ["translation_unfaithful"], 18: [], 19: ["self_certification_as_content"], 20: [], 21: [], 22: [], 23: [], 24: [],
                     25: ["translation_unfaithful"], 26: ["translation_circular"], 27: ["translation_circular"], 28: ["translation_circular"], 29: [],
                     30: ["translation_circular"], 31: [], 32: ["receipt_altered"], 33: ["translation_unfaithful"], 34: ["finding_missing"],
                     35: [], 36: [], 37: [], 38: [], 39: [], 40: []}
    assert sum(len(e.verdict["engine_statements"]) for e in examples) == 2 and examples[7].verdict["engine_statements"][0]["result_id"] == "res-c4"
    assert examples[31].verdict["engine_statements"] == [{"result_id": "res-3201", "asserted_status": "COUNTEREXAMPLE", "pointer": "/results/res-3201/status"}]


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
    # pack 1.3 (the translator merge): "about 250 words" is written as both bounds, min_words 225 and max_words 275, each
    # keeping the student's words, exactly as the merged request parser writes them
    from epinoic_logic.channel.request_parser import extract_constraints
    shown = [(e21.excerpt[f"/transfers/0/payload/constraints/{i}/kind"], e21.excerpt[f"/transfers/0/payload/constraints/{i}/value"],
              e21.excerpt[f"/transfers/0/payload/constraints/{i}/text"]) for i in (0, 1)]
    assert shown == [("min_words", "225", "about 250 words"), ("max_words", "275", "about 250 words")]
    parsed = [(c.kind, c.value, c.text) for c in extract_constraints(e21.excerpt["/transfers/0/payload/user_input"]) if c.kind.endswith("words")]
    assert parsed == shown
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


def test_the_repair_example_agrees_with_the_check_it_teaches(examples):
    """Pack 1.3 (the repair of the translator merge, decision 49): Example 26's only premise restates the conclusion
    under a ``supplied_text`` label the code did not verify. The merged translator's own rule delivers it (no E112), and
    the overseer's rule ``grounded-transcription`` reads it as the writer's own (OVS-TRN-006 when, as here, nothing else
    gives the conclusion): the example accuses exactly that, translation_circular at error. Since the third repair the
    example shows its symbols, and the check is pinned under rule data-standing too (shown not to be data)."""
    from epinoic_logic.engine import SolverConfig, verify
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks import translation as T
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
    e = next(x for x in examples if x.number == 26)
    tr = "/transfers/0/receipt/outcomes/0/translation"
    premise, concl = e.excerpt[tr + "/problem/premises/0"], e.excerpt[tr + "/problem/conclusion"]
    assert premise["expr"] == concl["expr"] and premise["grounding"]["kind"] == "supplied_text" and premise["grounding"]["verified"] is None
    assert e.excerpt[tr + "/grounding_checks/0"]["method"] == "not_checkable" and e.excerpt["/results/res-2601/status"] == "ENTAILED"
    claim = e.excerpt["/transfers/0/payload/claims/0/claim_text"]
    cid = e.excerpt["/transfers/0/payload/claims/0/claim_id"]
    doc = SuppliedText(document_id="doc-q26", title="Case", author="Anonymous", text="A tax of $0.40 per litre was introduced.")
    rep = SpecialistReport(report_id="rep-ec-q26-0", request_id="req", task_id="ec-q26", agent_id="economics-specialist", subject="Economics",
                           task_type="short_answer", original_response=claim, response_sha256=sha256_text(claim), supplied_texts=[doc],
                           created_at="2026-10-16T00:00:00Z",
                           claims=[ClaimRecord(request_id="req", task_id="ec-q26", report_id="rep-ec-q26-0", agent_id="economics-specialist",
                                               subject="Economics", task_type="short_answer", claim_id=cid, claim_text=claim, claim_role="point")])
    symbols = e.excerpt[tr + "/problem/symbols"]
    assert symbols == [{"name": "inelastic", "sort": "Bool", "meaning": "demand for the drink is price inelastic"}]  # no grounding as data
    prob = Problem.model_validate({"problem_id": "p26", "request_id": "req", "claim_id": cid, "query": "entailment",
                                   "symbols": symbols, "premises": [premise], "conclusion": concl})
    assert not assumed_grounding(prob.premises[0].grounding)  # the translator's rule reads the label as a transcription: delivered
    rs = T.restatement(prob, rep, [])
    assert rs.holds and rs.own == ("P1",) and not rs.translator_holds and "not verified" in rs.why_own[0][1]
    # the third repair (rule data-standing): a check SHOWS P1 is not data whether or not the request supplied doc-q26 (it
    # names no source a check could read; or the translation gives its Bool symbol no grounding as data), so the result
    # rests on a premise shown not to be data: OVS-TRN-006 by rule engine-shown, as the example accuses
    for docs, standing in (((), "uncheckable"), ((doc,), "refuted")):
        rs2 = T.restatement(prob, rep, [], request_documents=docs)
        assert rs2.holds and rs2.standings == (("P1", standing),) and rs2.shown == ("P1",), (docs, rs2.why_own)
        problem_json = json.loads(prob.model_dump_json(exclude_none=True))
        follows = lambda pids: verify(json.dumps(T.without_premises(problem_json, pids)), SolverConfig()).status.value == "ENTAILED"  # noqa: E731
        assert T.engine_shown_codes(rs2, False, follows) == ["OVS-TRN-006"]
    (a,) = e.verdict["accusations"]
    assert a["kind"] == "translation_circular" and a["claimed_severity"] == "error" and a["claim_ids"] == [cid]


def _example_report(cid: str, claim: str, task: str, *, docs=()):
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
    return SpecialistReport(report_id=f"rep-{task}-0", request_id="req", task_id=task, agent_id="mathematics-specialist", subject="Mathematics",
                            task_type="structured_question", original_response=claim, response_sha256=sha256_text(claim), supplied_texts=list(docs),
                            created_at="2026-10-16T00:00:00Z",
                            claims=[ClaimRecord(request_id="req", task_id=task, report_id=f"rep-{task}-0", agent_id="mathematics-specialist",
                                                subject="Mathematics", task_type="structured_question", claim_id=cid, claim_text=claim, claim_role="point")])


def _plain_follows(obj: dict):
    from epinoic_logic.engine import SolverConfig, verify
    from epinoic_logic.overseer.checks import translation as T
    return lambda pids: verify(json.dumps(T.without_premises(obj, pids)), SolverConfig()).status.value == "ENTAILED"


def test_the_second_repair_example_agrees_with_the_check_it_teaches(examples):
    """Pack 1.3, the second in-place correction (decision 51) made Example 27 accuse ``translation_circular``; the third
    (decision 55) rewrote it as a transcription the code could not verify; the fourth (decision 56, the review of the third
    repair: no grounding label is evidence on its own) keeps its excerpt and makes it accuse again, and this test asserts
    what the example now teaches, with every structural assertion on the same excerpt kept. The conclusion is restated as a
    whole, one conjunct by a ``task_setting`` premise stating a figure the request states for the quantity it names
    (t_years: undecided), one by a ``task_setting`` premise on a Bool symbol the translation grounds as task data
    throughout (t_wants). The merged translator delivers it (it reads both labels as transcriptions). No check reads a Bool
    statement against the request, so only its label presents t_wants as data: uncheckable, shown not to be data (it
    asserted "undecided"). The run without t_wants, keeping t_years, is COUNTEREXAMPLE: OVS-TRN-006 naming t_wants (it
    asserted OVS-TRN-011 for both), and the example accuses exactly that. Controls, kept: a request that does not state 5
    refutes t_years (OVS-TRN-006); the conclusion without the Bool conjunct rests on t_years alone, undecided
    (OVS-TRN-011)."""
    from epinoic_logic.engine import SolverConfig, verify
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks import translation as T
    e = next(x for x in examples if x.number == 27)
    tr = "/transfers/1/receipt/outcomes/0/translation/problem"
    premises = [e.excerpt[f"{tr}/premises/{i}"] for i in (0, 1)]
    concl = e.excerpt[tr + "/conclusion"]
    assert [p["grounding"]["kind"] for p in premises] == ["task_setting", "task_setting"] and all(p["grounding"]["verified"] is None for p in premises)
    assert concl["expr"] == {"op": "and", "args": [premises[0]["expr"], premises[1]["expr"]]}
    assert e.excerpt["/transfers/1/in_reply_to"] == e.excerpt["/transfers/0/message_id"] and e.excerpt["/results/res-2701/status"] == "ENTAILED"
    assert e.excerpt["/transfers/1/receipt/outcomes/0/verification/ungrounded_dependencies"] == [] == e.excerpt["/transfers/1/receipt/outcomes/0/verification/unverified_dependencies"]
    request = e.excerpt["/transfers/0/payload/user_input"]
    claim = e.excerpt["/transfers/1/payload/claims/0/claim_text"]
    cid = e.excerpt["/transfers/1/payload/claims/0/claim_id"]
    rep = _example_report(cid, claim, "ma-q27")
    obj = {"problem_id": "p27", "request_id": "req", "claim_id": cid, "query": "entailment", "symbols": e.excerpt[tr + "/symbols"], "premises": premises,
           "conclusion": concl}
    prob = Problem.model_validate(obj)
    assert not any(assumed_grounding(p.grounding) for p in prob.premises)  # the translator's rule reads both labels as transcriptions: delivered
    rs = T.restatement(prob, rep, [request])
    assert rs.holds and rs.own == ("t_years", "t_wants") and rs.grounded == () and not rs.translator_holds
    assert rs.standings == (("t_years", "undecided"), ("t_wants", "uncheckable")) and rs.shown == ("t_wants",) and rs.undecided == ("t_years",)
    assert "a number match is no evidence" in dict(rs.why_own)["t_years"] and "declares as data throughout" in dict(rs.why_own)["t_wants"]
    assert "no deterministic check reads Boolean content" in dict(rs.why_own)["t_wants"]
    assert verify(json.dumps(T.without_premises(obj, ["t_wants"])), SolverConfig()).status.value == "COUNTEREXAMPLE"  # the result rests on t_wants
    assert T.engine_shown_grade(rs, False, _plain_follows(obj)) == [("OVS-TRN-006", ["t_wants"], ["t_wants"])]
    (a,) = e.verdict["accusations"]
    assert a["kind"] == "translation_circular" and a["claimed_severity"] == "error" and a["claim_ids"] == [cid] and e.verdict["engine_statements"] == []
    assert any(ev["pointer"] == tr + "/premises/1/expr" for ev in a["evidence"]) and "t_wants" in a["statement"]
    # controls: a request that does not state 5 refutes t_years (stated nowhere), which then carries the result with t_wants:
    # OVS-TRN-006; without the Bool conjunct, the conclusion rests on t_years alone, undecided: OVS-TRN-011
    other = T.restatement(prob, rep, ["Find the value of the investment, to the nearest euro."])
    assert other.own == ("t_years", "t_wants") and other.standings == (("t_years", "refuted"), ("t_wants", "uncheckable"))
    assert T.engine_shown_codes(other, False, _plain_follows(obj)) == ["OVS-TRN-006"]
    alone_obj = {**obj, "premises": premises[:1], "conclusion": {**concl, "expr": premises[0]["expr"]}}
    alone = T.restatement(Problem.model_validate(alone_obj), rep, [request])
    assert alone.holds and alone.own == ("t_years",) and alone.standings == (("t_years", "undecided"),)
    assert T.engine_shown_codes(alone, False, _plain_follows(alone_obj)) == ["OVS-TRN-011"]


def test_the_fourth_repair_example_agrees_with_the_check_it_teaches(examples):
    """Pack 1.3, fourth in-place correction (decision 56): Example 29 keeps the genuine case Example 27 taught before. Every
    conjunct is restated by a ``task_setting`` premise with no excerpt stating one value of a quantity, and the request
    states each figure for the quantity the premise names, as a value (5 years; 3.6%): both undecided, no check verifies or
    refutes either, and the run without them is COUNTEREXAMPLE, which shows only that a data conjunct needs its data
    premise: OVS-TRN-011. The example accuses nothing. Controls: a request that states 3.6 only bare refutes nothing but
    reads nothing either (t_rate uncheckable: OVS-TRN-006); a premise stating a Bool symbol beside them is uncheckable
    (Example 27)."""
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks import translation as T
    e = next(x for x in examples if x.number == 29)
    tr = "/transfers/1/receipt/outcomes/0/translation/problem"
    premises = [e.excerpt[f"{tr}/premises/{i}"] for i in (0, 1)]
    concl = e.excerpt[tr + "/conclusion"]
    assert [p["grounding"] for p in premises] == [{"kind": "task_setting", "source_refs": [], "verified": None}] * 2
    assert concl["expr"] == {"op": "and", "args": [premises[0]["expr"], premises[1]["expr"]]}
    assert e.excerpt["/transfers/1/in_reply_to"] == e.excerpt["/transfers/0/message_id"] and e.excerpt["/results/res-2901/status"] == "ENTAILED"
    request = e.excerpt["/transfers/0/payload/user_input"]
    cid = e.excerpt["/transfers/1/payload/claims/0/claim_id"]
    rep = _example_report(cid, e.excerpt["/transfers/1/payload/claims/0/claim_text"], "ma-q29")
    obj = {"problem_id": "p29", "request_id": "req", "claim_id": cid, "query": "entailment", "symbols": e.excerpt[tr + "/symbols"], "premises": premises,
           "conclusion": concl}
    prob = Problem.model_validate(obj)
    assert not any(assumed_grounding(p.grounding) for p in prob.premises)
    rs = T.restatement(prob, rep, [request])
    assert rs.holds and rs.own == ("t_years", "t_rate") and rs.standings == (("t_years", "undecided"), ("t_rate", "undecided")) and rs.shown == ()
    assert T.engine_shown_grade(rs, False, _plain_follows(obj)) == [("OVS-TRN-011", ["t_years", "t_rate"], ["t_years", "t_rate"])]
    assert e.verdict["accusations"] == [] and e.verdict["engine_statements"] == []
    bare = T.restatement(prob, rep, ["A sum of 2000 euros is invested for 5 years. Rate: 3.6 (nominal, annual), compounded monthly."])
    assert bare.standings == (("t_years", "undecided"), ("t_rate", "uncheckable")) and T.engine_shown_codes(bare, False, _plain_follows(obj)) == ["OVS-TRN-006"]


def test_the_third_repair_example_agrees_with_the_check_it_teaches(examples):
    """Pack 1.3, third in-place correction (decision 55): Example 28's only premise restates the answer's result under a
    ``task_setting`` label with no excerpt, and the request states that figure only as the target the answer must show.
    The merged translator delivers it (no E112); rule same-quantity refutes the premise as the request's statement (a
    "show that" target is never data), so a check shows it is not data and the result rests on it: OVS-TRN-006 by rule
    engine-shown. The example accuses exactly that, translation_circular at error. Under the withdrawn rule
    figure-transcription the 8 in the request verified it. Control: the request stating 8 m as data gives no refutation
    (undecided: OVS-TRN-011)."""
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks import translation as T
    e = next(x for x in examples if x.number == 28)
    tr = "/transfers/1/receipt/outcomes/0/translation/problem"
    premise, concl = e.excerpt[tr + "/premises/0"], e.excerpt[tr + "/conclusion"]
    assert premise["expr"] == concl["expr"] and premise["grounding"] == {"kind": "task_setting", "source_refs": [], "verified": None}
    assert e.excerpt["/results/res-2801/status"] == "ENTAILED" and e.excerpt["/transfers/1/in_reply_to"] == "m-2800"
    request = e.excerpt["/transfers/0/payload/user_input"]
    cid = e.excerpt["/transfers/1/payload/claims/0/claim_id"]
    rep = _example_report(cid, e.excerpt["/transfers/1/payload/claims/0/claim_text"], "ma-q28")
    obj = {"problem_id": "p28", "request_id": "req", "claim_id": cid, "query": "entailment", "symbols": e.excerpt[tr + "/symbols"], "premises": [premise],
           "conclusion": concl}
    prob = Problem.model_validate(obj)
    assert not assumed_grounding(prob.premises[0].grounding)  # delivered by the translator's rule
    rs = T.restatement(prob, rep, [request])
    assert rs.holds and rs.own == ("t_target",) and rs.standings == (("t_target", "refuted"),)
    assert "only as the target the answer must derive" in dict(rs.why_own)["t_target"]
    assert T.engine_shown_codes(rs, False, _plain_follows(obj)) == ["OVS-TRN-006"]
    (a,) = e.verdict["accusations"]
    assert a["kind"] == "translation_circular" and a["claimed_severity"] == "error" and a["claim_ids"] == [cid]
    data = T.restatement(prob, rep, ["A particle travels 8 m along a line in 2 s. Find its mean speed."])
    assert data.standings == (("t_target", "undecided"),) and T.engine_shown_codes(data, False, _plain_follows(obj)) == ["OVS-TRN-011"]


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
    "u2_notes": ("this agent is configured with overseer-knowledge-docs 1.4. Not reviewed.", "this agent is configured with overseer-knowledge-docs 1.5. Not reviewed."),
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


def test_the_fifth_repair_example_agrees_with_the_check_it_teaches(examples):
    """Pack 1.3, fifth in-place correction (decision 57, rule statement-context): Example 30 restates the paragraph's own
    length under a ``task_setting`` label with no excerpt, while the request states 80 words only as a requirement on the
    answer ("Your answer should be 80 words long"). The merged translator delivers it (its rule reads the label as a
    transcription); no check reads the requirement as the request's statement of the paragraph's length, so t_len is
    uncheckable, shown not to be data, the result rests on it, and the grade is OVS-TRN-006: the example accuses exactly
    that. Controls: the request stating the length ("The paragraph is 80 words long.") leaves t_len undecided
    (OVS-TRN-011); a premise naming the requirement reads it (undecided); the question and the negation the example names
    are shown not to be data too."""
    from epinoic_logic.engine.runner import assumed_grounding
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks import translation as T
    e = next(x for x in examples if x.number == 30)
    tr = "/transfers/1/receipt/outcomes/0/translation/problem"
    premise = e.excerpt[f"{tr}/premises/0"]
    concl = e.excerpt[tr + "/conclusion"]
    assert premise["grounding"] == {"kind": "task_setting", "source_refs": [], "verified": None} and concl["expr"] == premise["expr"]
    assert e.excerpt["/transfers/1/in_reply_to"] == e.excerpt["/transfers/0/message_id"] and e.excerpt["/results/res-3001/status"] == "ENTAILED"
    request = e.excerpt["/transfers/0/payload/user_input"]
    cid = e.excerpt["/transfers/1/payload/claims/0/claim_id"]
    rep = _example_report(cid, e.excerpt["/transfers/1/payload/claims/0/claim_text"], "en-q30")
    obj = {"problem_id": "p30", "request_id": "req", "claim_id": cid, "query": "entailment", "symbols": e.excerpt[tr + "/symbols"], "premises": [premise],
           "conclusion": concl}
    prob = Problem.model_validate(obj)
    assert not any(assumed_grounding(p.grounding) for p in prob.premises)  # the translator's rule reads the label as a transcription: delivered
    rs = T.restatement(prob, rep, [request])
    assert rs.holds and rs.own == ("t_len",) and rs.standings == (("t_len", "uncheckable"),) and rs.shown == ("t_len",)
    reason = dict(rs.why_own)["t_len"]
    assert "as a requirement on the answer" in reason and T.CONTEXT_RULE in reason, reason
    assert T.engine_shown_grade(rs, False, _plain_follows(obj)) == [("OVS-TRN-006", ["t_len"], ["t_len"])]
    (a,) = e.verdict["accusations"]
    assert a["kind"] == "translation_circular" and a["claimed_severity"] == "error" and a["claim_ids"] == [cid] and e.verdict["engine_statements"] == []
    assert {"pointer": "/transfers/0/payload/user_input", "quote": "Your answer should be 80 words long"} in a["evidence"]
    # controls
    stated = T.restatement(prob, rep, ["Analyse how the writer presents work in the extract. The paragraph is 80 words long."])
    assert stated.standings == (("t_len", "undecided"),) and T.engine_shown_codes(stated, False, _plain_follows(obj)) == ["OVS-TRN-011"]
    named = {**premise, "label": "the required length is 80 words"}
    named_obj = {**obj, "premises": [named], "conclusion": {**concl, "label": "the required length is 80 words"},
                 "symbols": [{**e.excerpt[tr + "/symbols"][0], "meaning": "the number of words the answer should have"}]}
    assert T.restatement(Problem.model_validate(named_obj), rep, [request]).standings == (("t_len", "undecided"),)
    for other in ("Analyse the extract. Is the paragraph 80 words long?", "Analyse the extract. Explain why the paragraph is not 80 words long."):
        assert T.restatement(prob, rep, [other]).standings == (("t_len", "uncheckable"),), other

