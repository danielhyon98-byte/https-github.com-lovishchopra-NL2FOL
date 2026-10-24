"""STEM repair 11 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 42).

* the pack's modules (the seventh problem: one system text of 472,563 characters for every dossier, too large for the cheapest agents):
  the parts of the agent documents that concern STEM answers or translations lie between module markers, the manifest records every
  composition's digest, and an agent is sent the core and the modules its dossier's content needs, read from the dossier as data (never
  from the lens or the agent's choice). Malformed markers and a composition digest the documents do not give are refused;
* the STEM probes of repair 11 (the eleventh independent test's plants, each class with its clean control): rules exact-rounding and
  result-rounding, given-data, part-condition and root-statement, function-value, inequality-solution, derivative, same-shape,
  unbound-substitution and the prose-base opening phrase; the three translator gaps they close (equations-factorising, maths-roots,
  formulas-derivative);
* the STEM receipt cases T23bj to T23bp, each on the probe that plants its fault, and T23am moved to a derivative the branch does not check;
* the pack beside the code: D31's new readings, D32, I97, the master prompt and the mistakes rows, every new statement executed against
  the STEM front end, and the README's input budget measured against the compositions themselves.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stem_probes as SP  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer.pack import (  # noqa: E402
    SYSTEM_MODULES, build_manifest, build_system_text, composition_key, compositions_of, dossier_modules, installed_pack_dir, load_pack,
    module_markup_faults, modules_marked, select_modules,
)

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402
from .test_stem_repair8 import _failing, _holds  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
PROFILE = {"ph-t13": "physics", "maa-t13": "mathematics_aa", "mai-t13": "mathematics_ai", "bi-t13": "biology", "cs-t13": "computer_science",
           "ch-t13": "chemistry"}
#: the recorded working the pack's statements extend
PH_A = "(a) [2]\n"
PH_RR = "R + r = 2.4 Ω + 0.50 Ω = 2.9 Ω"
MA_PART_B = "    6t − 3t² = 0\n"
MA_A = "    a = 0 m s⁻²  A1"
MI_N = "so $n > 11.28\\ldots$ (A1)"
MI_11 = "$4000(1.036)^{11} = 5902.25$"
MI_PA = "**Part (a) — find — 3 marks**"
BI_D = "which makes ATP. [1 spare]"
CS_END = "Next step: trace"


def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _with(tid: str, old: str, new: str) -> str:
    text = R7[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _new(tid: str, text: str) -> list:
    """The checks (kind, status, statement) ``text`` has beyond the recorded answer's."""
    def key(c):
        return (c[0], c[1], c[2].split(" [claims")[0])
    checks, _f = _task(tid, text)
    base = [key(c) for c in _task(tid, R7[tid]["response_text"])[0]]
    out = []
    for c in checks:
        if key(c) in base:
            base.remove(key(c))
        else:
            out.append(c)
    return out


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"(rule {rule})" in c[2] or f"(rule {rule}," in c[2]]


@pytest.fixture(scope="module")
def pack():
    return load_pack(installed_pack_dir("1.3"))


# ============================================================================================ the pack's modules
def test_the_pack_marks_its_modules_and_its_manifest_records_every_composition(pack):
    """Every composition (the core alone, with each module, with both) is recorded under its key, recomputes from the documents, and the
    one with every module is the whole system text (``system_sha256``): the pack with every module is the pack as it was."""
    m = pack.manifest
    assert tuple(m.system_modules) == SYSTEM_MODULES == ("stem", "translations") and modules_marked(pack.documents) == SYSTEM_MODULES
    assert set(m.system_compositions) == {"core", "core+stem", "core+translations", "core+stem+translations"}
    for chosen in compositions_of(SYSTEM_MODULES):
        text = build_system_text(pack.documents, m.system_separator, chosen)
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == m.system_compositions[composition_key(chosen)] == pack.composition_sha256(chosen)
        assert pack.system_text(chosen) == text and "<!-- module:" not in text and "<!-- end module:" not in text
    assert m.system_compositions["core+stem+translations"] == m.system_sha256 and pack.system_text() == pack.system_text(SYSTEM_MODULES)
    sizes = {k: len(pack.system_text(c)) for c in compositions_of(SYSTEM_MODULES) for k in [composition_key(c)]}
    assert sizes["core"] < sizes["core+translations"] < sizes["core+stem+translations"] and sizes["core"] < sizes["core+stem"] < sizes["core+stem+translations"]


def test_each_module_holds_its_rules_and_examples_and_the_core_holds_none_of_them(pack):
    """The STEM module holds D29 to D32, I90 to I98 and the STEM examples; the translations module D21 to D23, I70 to I81 and the
    translation examples; the core holds every other rule (none is lost and none is in two places)."""
    core = pack.system_text(())
    stem = pack.system_text(("stem",))
    trans = pack.system_text(("translations",))
    full = pack.system_text()

    def rules(text):
        return set(re.findall(r"^\s*- \*\*([A-Z]\d+) ", text, re.M))

    def examples(text):
        return set(re.findall(r"^## \d+\. Example (\d+):", text, re.M))
    assert rules(stem) - rules(core) == {"D29", "D30", "D31", "D32", "I90", "I91", "I92", "I93", "I94", "I95", "I96", "I97", "I98"}
    assert rules(trans) - rules(core) == {"D21", "D22", "D23"} | {f"I{n}" for n in range(70, 82)}
    assert rules(full) == rules(core) | rules(stem) | rules(trans) and not (rules(stem) - rules(core)) & (rules(trans) - rules(core))
    assert examples(stem) - examples(core) == {"23", "24", "25"} | {str(n) for n in range(31, 41)}
    assert examples(trans) - examples(core) == {"14", "15", "16", "17", "20", "22", "26", "27", "28", "29", "30"}
    # the master prompt tells the agent what a part it does not receive concerns
    assert ("Parts of these documents that concern translations, or the answers of science, mathematics and computer science specialists "
            "(STEM answers), come with this prompt only when the dossier carries them") in core


@pytest.mark.parametrize("text, fault", [
    ("a\n<!-- module: physics -->\nb\n<!-- end module: physics -->", "opens an unknown module 'physics'"),
    ("<!-- module: stem -->\n<!-- module: translations -->\nb\n<!-- end module: translations -->\n<!-- end module: stem -->",
     "opens a module inside the span of 'stem'"),
    ("<!-- module: stem -->\nb", "leaves the span of 'stem' open"),
    ("b\n<!-- end module: stem -->", "closes 'stem', which is not the open span"),
    ("<!-- module: stem -->\nb\n<!-- end module: translations -->", "closes 'translations', which is not the open span"),
    ("<!-- module: Stem -->\nb", "looks like a module marker but is none"),
    ("<!--module: stem-->\nb", "looks like a module marker but is none"),
])
def test_malformed_module_markers_are_refused(text, fault):
    """A marker the composition rule would not read is a fault (a misspelt one would otherwise be sent to the agent as text), and the
    builder refuses a pack that has one."""
    faults = module_markup_faults("02-dossier.md", text)
    assert any(fault in f for f in faults), faults
    files = {p: d for p, d in load_pack(installed_pack_dir("1.3")).files if p != "manifest.json"}
    files["02-dossier.md"] = files["02-dossier.md"] + b"\n" + text.encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="module markers"):
        build_manifest(files)


def test_a_document_without_markers_is_sent_whole_and_a_marked_span_only_with_its_module():
    text = "a\n<!-- module: stem -->\nb\n<!-- end module: stem -->\nc\n<!-- module: translations -->\nd\n<!-- end module: translations -->\ne"
    assert select_modules(text, ()) == "a\nc\ne" and select_modules(text, ("stem",)) == "a\nb\nc\ne"
    assert select_modules(text, ("translations",)) == "a\nc\nd\ne" and select_modules(text, None) == select_modules(text, SYSTEM_MODULES) == "a\nb\nc\nd\ne"
    assert select_modules("a\nb", ()) == "a\nb" and modules_marked([("x", "a\nb")]) == ()
    assert [composition_key(c) for c in compositions_of(SYSTEM_MODULES)] == ["core", "core+stem", "core+translations", "core+stem+translations"]
    assert composition_key(("translations", "stem")) == "core+stem+translations"


def test_a_manifest_whose_compositions_the_documents_do_not_give_is_refused(tmp_path):
    """The loader recomputes every composition: a manifest naming another digest, or modules the documents do not mark, is refused
    (the pinned digest would refuse it first, so the check runs on a copy whose manifest is rebuilt and trusted by the operator)."""
    from epinoic_logic.overseer.pack import PackError, manifest_pack_digest, render_manifest
    src = installed_pack_dir("1.3")
    for change in ("composition", "modules"):
        dst = tmp_path / change / src.name
        dst.mkdir(parents=True)
        for f in src.iterdir():
            (dst / f.name).write_bytes(f.read_bytes())
        manifest = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
        if change == "composition":
            manifest["system_compositions"]["core"] = "0" * 64
        else:
            manifest["system_modules"] = ["stem"]
        manifest["pack_sha256"] = manifest_pack_digest(manifest)
        (dst / "manifest.json").write_text(render_manifest(manifest), encoding="utf-8")
        with pytest.raises(PackError) as err:
            load_pack(dst)
        # the compositions are recomputed before the pin is looked at: the refusal is the composition's
        assert err.value.reason == {"composition": "system_digest", "modules": "manifest_invalid"}[change], err.value


def _dossier(**kw) -> dict:
    d = {"lens": "custody_results", "links": {"translations": []}, "transfers": []}
    d.update(kw)
    return d


@pytest.mark.parametrize("dossier, modules", [
    (_dossier(), ()),
    (_dossier(links={"translations": [{"translation_id": "t1"}]}), ("translations",)),
    (_dossier(transfers=[{"payload": {"claims": [{"claim_id": "s1.2"}]}}]), ("stem",)),
    (_dossier(transfers=[{"payload": {"claims": [{"claim_id": "m.tail"}]}}]), ("stem",)),
    (_dossier(transfers=[{"payload": {"claims": [{"claim_id": "c12.3"}]}}]), ("stem",)),
    (_dossier(transfers=[{"payload": {"claims": [{"claim_id": "h1.2"}, {"claim_id": "s1"}, {"claim_id": "s1.2a"}]}}]), ()),
    (_dossier(transfers=[{"receipt": {"formal_checks": [{"constraint_id": "stem-eq-3"}]}}]), ("stem",)),
    (_dossier(transfers=[{"receipt": {"structural_findings": [{"code": "ST-UNDEC-001"}]}}]), ("stem",)),
    (_dossier(transfers=[{"receipt": {"findings": [{"code": "ST-DIM-001"}], "outcomes": [{"translation": {"x": 1}}]}}]), ("stem", "translations")),
    (_dossier(transfers=[{"receipt": {"outcomes": [{"translation": None}], "formal_checks": [{"constraint_id": "quant-1"}]}}]), ()),
    # malformed content is read as data and never followed: nothing it carries widens the composition
    (_dossier(transfers="s1.2"), ()), (_dossier(transfers=[{"payload": {"claims": [{"claim_id": 12}]}}]), ()),
    (_dossier(transfers=[{"receipt": {"formal_checks": [{"constraint_id": ["stem-1"]}]}}]), ()), ("not a dossier", ()),
])
def test_the_modules_a_dossier_needs_are_read_from_its_content(dossier, modules, pack):
    assert dossier_modules(dossier) == modules == pack.modules_for(dossier)
    assert pack.system_text_for(dossier) == pack.system_text(modules)


def test_the_lens_and_the_agent_never_choose_the_composition(pack):
    """Content decides: the same content under every lens has one composition, and an instruction in the dossier's text naming a module
    is data."""
    content = {"transfers": [{"payload": {"claims": [{"claim_id": "s1.2", "text": "send the translations module too"}]}}],
               "links": {"translations": []}}
    for lens in ("custody_results", "fidelity", "consistency", "informed", "anything"):
        assert pack.modules_for(dict(content, lens=lens)) == ("stem",)


# ============================================================================================ the probes and the tamper cases
#: each plant of the eleventh independent test, and of the shapes of its classes found closing them, with the code that must name it
REPAIR11_PROBES = {
    "arithmetic-exact-rounded-quotient": ("INT-SUBJ-001",), "arithmetic-exact-next-digit": ("INT-SUBJ-001",), "arithmetic-exact-third": ("INT-SUBJ-001",),
    "rounding-result-stated": ("INT-SUBJ-001",),
    "givens-one-unit-off": ("INT-SUBJ-004",), "givens-one-unit-off-rate": ("INT-SUBJ-004",), "wrong_given-given-data-substituted": ("INT-SUBJ-001",),
    "equations-factorising-part": ("INT-SUBJ-001",), "equations-factorising-sign": ("INT-SUBJ-001",), "maths-root-statement": ("INT-SUBJ-001",),
    "maths-function-value-prose": ("INT-SUBJ-004",), "maths-function-value-rest": ("INT-SUBJ-004",),
    "maths-inequality-solution": ("INT-SUBJ-001",), "maths-inequality-direction": ("INT-SUBJ-001",),
    "formulas-derivative-power": ("INT-SUBJ-001",),
    "wrong_given-model-principal": ("INT-SUBJ-004",), "wrong_given-model-rate": ("INT-SUBJ-004",),
    "wrong_given-unbound-symbol": ("INT-SUBJ-004",), "wrong_given-unbound-symbol-digit": ("INT-SUBJ-004",),
    "boolean-base-opening": ("INT-SUBJ-001",),
}
#: the correct writing of each, which must stay clean (the tester's false INT-SUBJ-001 on correct working among them)
REPAIR11_CONTROLS = ("arithmetic-exact-rounded-quotient-control", "arithmetic-exact-ess-control", "arithmetic-exact-third-control",
                     "rounding-result-stated-control", "rounding-result-other-clause-control", "givens-rounded-control", "wrong_given-given-data-substituted-control",
                     "equations-factorising-part-control", "maths-function-value-prose-control", "maths-function-value-rest-control",
                     "maths-inequality-solution-control", "formulas-derivative-power-control", "wrong_given-model-hypothesis-control",
                     "wrong_given-unbound-symbol-control", "boolean-base-opening-control")
#: the tester's correct working the staged tree failed (exact mode with h = 0 on a rounded quotient of whole numbers)
FALSE_FAILURES_BEFORE = ("arithmetic-exact-rounded-quotient-control", "arithmetic-exact-ess-control", "arithmetic-exact-third-control",
                         "rounding-result-stated-control")
#: the translator gaps these readings close: each probe is named now and counted
GAPS_CLOSED = {"equations-factorising": ("INT-SUBJ-001",), "maths-roots": ("INT-SUBJ-001", "ST-ALG-001"), "formulas-derivative": ("INT-SUBJ-004",)}
#: STEM repair 11's receipt cases, their classes, the plant each runs on and the codes it must raise
REPAIR11_CASES = {
    "T23bj": ("receipt_altered", "formulas", "r7/maa-t13", "formulas-derivative-power", ["OVS-RCPT-007"]),
    "T23bk": ("finding_missing", "maths", "r7/maa-t13", "maths-function-value-prose", ["OVS-RCPT-004"]),
    "T23bl": ("formal_status_wrong", "wrong_given", "r7/ph-t13", "wrong_given-unbound-symbol", ["OVS-FORM-001", "OVS-FORM-002"]),
    "T23bm": ("receipt_altered", "givens", "r7/ph-t13", "givens-one-unit-off", ["OVS-RCPT-007"]),
    "T23bn": ("finding_missing", "arithmetic", "r7/cs-t13", "arithmetic-exact-third", ["OVS-RCPT-004"]),
    "T23bo": ("receipt_altered", "equations", "r7/maa-t13", "equations-factorising-sign", ["OVS-RCPT-007"]),
    "T23bp": ("finding_missing", "equations", "r7/maa-t13", "equations-factorising-part", ["OVS-RCPT-004"]),
}


def test_every_plant_of_the_eleventh_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR11_PROBES) == len(REPAIR11_PROBES) + len(REPAIR11_CONTROLS) == 35
    assert {p.probe_id for p in SP.REPAIR11_PROBES} == set(REPAIR11_PROBES) | set(REPAIR11_CONTROLS)
    for pid, expected in REPAIR11_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES and not p.translator_gap, pid
    for pid in REPAIR11_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(FALSE_FAILURES_BEFORE) <= set(REPAIR11_CONTROLS)
    for cls in ("arithmetic", "rounding", "givens", "wrong_given", "equations", "maths", "formulas", "boolean"):
        assert {p.kind for p in SP.REPAIR11_PROBES if p.fault_class == cls} == {"answer", "control"}, cls
    assert SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES and len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677
    # the translator gaps they close, and the one that remains (a power beyond 12: ST-UNDEC-001)
    for pid, expected in GAPS_CLOSED.items():
        assert SP.probe(pid).translator_gap is None and SP.probe(pid).expected == expected, pid
    assert [p.probe_id for p in SP.PROBES if p.translator_gap] == ["maths-finance-value"]


def test_the_repair_11_tamper_cases_are_registered_on_their_targets():
    by_name = {c.name: c for c in T.CASES}
    for case, (cls, probe_class, _target, plant, _codes) in REPAIR11_CASES.items():
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
        assert case in SP.TAMPER_CASES[probe_class] and SP.probe(plant).fault_class == probe_class, case
    assert SP.TAMPER_CASES["equations"][-2:] == ("T23bo", "T23bp") and SP.TAMPER_CASES["formulas"][-1] == "T23bj"
    # STEM repair 12 (design section 43) appended T23bq and T23br to maths, after T23bk
    assert SP.TAMPER_CASES["maths"][-3:] == ("T23bk", "T23bq", "T23br") and SP.TAMPER_CASES["wrong_given"][-1] == "T23bl"
    assert SP.TAMPER_CASES["givens"][-1] == "T23bm" and SP.TAMPER_CASES["arithmetic"][-1] == "T23bn"
    # T23am: a derivative of the answer's polynomial is checked now, so the case plants one the branch does not check
    assert SP.probe("receipts-derivative-letter").expected == ("ST-UNDEC-001",) and "T23am" in SP.TAMPER_CASES["receipts"]


def test_the_rewrites_the_new_cases_use_drop_only_what_they_name():
    """T23bm's Given warning holds a ';' of its own, so the rewrite cuts the clause up to its rule tag; T23bo's rewrite leaves out the
    root-statement clause alone. Each writes the solver's COUNTEREXAMPLE ENTAILED and keeps every other clause."""
    detail = ("the algebraic step: 'x'; Form E; readings: as written; the step is from the equation in s2.3, which the root stated in s2.4 solves "
              "and leaves as the relation the next line steps from (rule root-statement); t is an unknown of this part's equations: the request's "
              "t = 1 stands in the question of part (a), so it gives t that value in part (a) only (rule part-condition); solver COUNTEREXAMPLE")
    out = T._without_clause("root-statement")(detail)
    assert "rule root-statement" not in out and "(rule part-condition)" in out and out.endswith("; solver ENTAILED") and "readings: as written" in out


@pytest.mark.timeout(2400)
def test_the_repair_11_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the tester's false failures among them), no forbidden code; the closed gaps named."""
    rnd = material_round(tmp_path / "rounds")
    chosen = SP.REPAIR11_PROBES + tuple(SP.probe(pid) for pid in GAPS_CLOSED)
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=chosen)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid, expected in list(REPAIR11_PROBES.items()) + list(GAPS_CLOSED.items()):
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
        assert set(expected) & set(r["named_by"]), (pid, r["named_by"])
    for pid in REPAIR11_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == [] and doc["gate"]["translator_gaps"] == []


# ============================================================================================ the pack beside the code
@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


@pytest.mark.parametrize("tid, old, new, quote, rule, status", [
    # rule inequality-solution
    ("mai-t13", MI_N, "so $n > 13.28\\ldots$ (A1)", '"12n > 135.36…, so n > 13.28…" fails', "inequality-solution", False),
    ("mai-t13", MI_N, "so $n < 11.28\\ldots$ (A1)", 'a direction the division does not give ("so n < 11.28…") fails as a step', None, False),
    # rules part-condition and root-statement
    ("maa-t13", "    3t(2 − t) = 0  M1", "    3t(2 + t) = 0  M1", 'so "3t(2 + t) = 0" and "t = 0 or t = 3" fail, each `detail` saying "rule part-condition"',
     "part-condition", False),
    ("maa-t13", "    t = 0 or t = 2  A1", "    t = 0 or t = 3  A1", 'so "3t(2 + t) = 0" and "t = 0 or t = 3" fail, each `detail` saying "rule part-condition"',
     "part-condition", False),
    # rule function-value, the request's function
    ("maa-t13", MA_A, MA_A + "\n    The velocity at t = 1 is v(1) = 4 m s⁻¹.", '"The velocity at t = 1 is v(1) = 4 m s⁻¹." where the request gives v(t) = 6t − 3t²',
     "function-value", False),
    # rule same-shape
    ("mai-t13", MI_11, "$4500(1.036)^{11} = 6640.03$", '"$4500(1.036)^{11} = 6640.03$" beside "$4000(1.036)^{12} = 6114.73$"', "same-shape", False),
    ("mai-t13", MI_11, "$4000(1.037)^{11} = 5928.94$", '"$4000(1.037)^{11}$" for its 3.6%', "same-shape", False),
    # rule unbound-substitution
    ("ph-t13", PH_RR, "R + r = 2.4 Ω + 0.40 Ω = 2.8 Ω", '"R + r = 2.4 Ω + 0.40 Ω" where part (c)\'s "V = 12 V − (4.14 A × 0.50 Ω)" puts the request\'s '
     'internal resistance, 0.50 ohm, for r', "unbound-substitution", False),
    # rule prose-base, a base phrase opening the clause
    ("cs-t13", CS_END, "In binary, 1000 is 1111101100.\n\n" + CS_END, '"In binary, 1000 is 1111101100." fails, 1111101000', "prose-base", False),
    # rule given-data
    ("ph-t13", PH_A, PH_A + "Given: r = 0.49 Ω.\n", '"Given: r = 0.49 Ω." and "Given: r = 3.7%." fail against the request\'s 0.50 ohm and 3.6%', "given-data", False),
    ("mai-t13", MI_PA, "Given: P = 4000 euros and r = 3.7%.\n\n" + MI_PA, '"Given: r = 0.49 Ω." and "Given: r = 3.7%." fail against the request\'s 0.50 '
     'ohm and 3.6%', "given-data", False),
    ("ph-t13", PH_A, PH_A + "Given: r = 0.5 Ω.\n", '"Given: r = 0.5 Ω." and "Given: g = 9.81 m s⁻²." for the request\'s 9.8 hold', "given-data", True),
    # rule result-rounding
    ("bi-t13", BI_D, BI_D + "\nFrom 35 °C to 40 °C the uptake falls by (92 − 61) ÷ 92 × 100 = 33% to 2 s.f.", '(rule result-rounding: "= 33% to 2 s.f." fails, 33.7)',
     "result-rounding", False),
    ("bi-t13", BI_D, BI_D + "\nFrom 35 °C to 40 °C the uptake falls by (92 − 61) ÷ 92 × 100 = 34% to 2 s.f.", '"(92 − 61) ÷ 92 × 100 = 34% to 2 s.f."',
     "result-rounding", True),
])
def test_d31_states_each_new_reading_as_the_code_decides_it(d31, tid, old, new, quote, rule, status):
    """Each D31 statement of this repair, quoted, and executed on the recorded answer it extends: the new check its rule names has the
    status D31 says, and nothing else fails."""
    assert quote in d31, quote
    got = _new(tid, _with(tid, old, new))
    named = _rule(got, rule) if rule else got
    assert named, got
    if status:
        assert not _failing(got) and all(_holds(c[0], c[1]) for c in named), got
    else:
        assert _failing(named), got


@pytest.mark.parametrize("quote, text, profile, req, rule, holds", [
    # rule derivative, alone
    ('"d/dt (3t²) = 3t" fails (6t)', "d/dt (3t²) = 3t", "mathematics_aa", None, "derivative", False),
    ('"d/dt (3t²) = 3t" fails (6t)', "d/dt (3t²) = 6t", "mathematics_aa", None, "derivative", True),
    ('"f(x) = x³, so f′(x) = 2x²" fails', "f(x) = x³, so f′(x) = 2x²", "mathematics_aa", None, "derivative", False),
    ('"f′(2) = 8" after "f(x) = x³" fails, 12', "f(x) = x³\nf′(2) = 8", "mathematics_aa", None, "derivative", False),
    ('"f′(2) = 8" after "f(x) = x³" fails, 12', "f(x) = x³\nf′(2) = 12", "mathematics_aa", None, "derivative", True),
    # the answer's own function, its value checked by the line's written arithmetic
    ('"Then f(2) = 6." after "Let f(x) = x² + 1."', "Let f(x) = x² + 1.\nThen f(2) = 6.", "mathematics_aa", None, None, False),
    ('("f(2) = 6" fails, 5)', "Let f(x) = x² + 1.\nThen f(2) = 5.", "mathematics_aa", None, None, True),
    # rule exact-rounding
    ('"17 × 23 = 392" and "1000 ÷ 3 = 330" fail', "17 × 23 = 392", "biology", None, "exact-rounding", False),
    ('"17 × 23 = 392" and "1000 ÷ 3 = 330" fail', "1000 ÷ 3 = 330", "biology", None, "exact-rounding", False),
    ('"(92 − 18) ÷ 18 × 100 = 411%" and "1,000 ÷ 3 = 333" hold', "(92 − 18) ÷ 18 × 100 = 411%", "biology", None, "exact-rounding", True),
    ('"(92 − 18) ÷ 18 × 100 = 411%" and "1,000 ÷ 3 = 333" hold', "1,000 ÷ 3 = 333", "computer_science", None, "exact-rounding", True),
    ('"7/3 = 2" fails, a single figure showing no rounding', "7/3 = 2", "mathematics_aa", None, None, False),
    # rule result-rounding, the rounding before the line in its clause
    ('"To 2 s.f., 1000 ÷ 3 = 330."', "To 2 s.f., 1000 ÷ 3 = 330.", "biology", None, "result-rounding", True),
    # rule given-data
    ('"Given: r = 0.5 Ω." and "Given: g = 9.81 m s⁻²." for the request\'s 9.8 hold', "Given: g = 9.81 m s⁻².", "physics",
     "A ball is dropped from rest; take g = 9.8 m s⁻². Find its speed after 2.0 s.", "given-data", True),
    ('"2.1 kg" substituted for the request\'s m = 2.0 kg fails', "W = mg = 2.1 kg × 9.81 m s⁻² = 20.6 N", "physics",
     "A mass m = 2.0 kg; take g = 9.81 m s⁻². Find W.", "given-data", False),
    # rule prose-base, a base phrase opening the clause
    ('"In base 2, 13 is 1101." holds', "In base 2, 13 is 1101.", "computer_science", None, "prose-base", True),
])
def test_d31_s_examples_alone_are_decided_as_it_says(d31, quote, text, profile, req, rule, holds):
    """D31's examples of this repair that need no recorded answer, each executed alone: the one check its rule plans (or, with no rule,
    the line's one check) has the outcome D31 states, and it is the only check that fails."""
    assert quote in d31, quote
    checks, _findings = _decided(text, profile, req)
    picked = _rule(checks, rule) if rule else checks
    assert len(picked) == 1 and _holds(picked[0][0], picked[0][1]) is holds, (text, checks)
    assert _failing(checks) == ([] if holds else picked), (text, checks)
    if text == "7/3 = 2":
        assert "rule exact-rounding" not in picked[0][2] and "(τ = 0, h = 0)" in picked[0][2], picked


def test_d31_says_what_is_no_reading_and_the_code_fails_none_of_it(d31):
    """The statements D31 names as not read: a line under a hypothesis, a value the working derives without stating it, a symbol the
    request's values tie to no one quantity, a letter applied to a number nothing defines, a derivative set equal to a number where it
    is no constant, and a derivative of what is no polynomial."""
    for quote in ('a line under a condition or a hypothesis ("if Kai had invested 4500 euros instead") is not read',
                  'a value the working derives without stating it ("c = 0.0050 mol ÷ 0.0550 dm³", the total of the request\'s 50.0 cm³ and 5.0 cm³) and '
                  'a symbol the request\'s values tie to no one quantity (R for each of the two resistors in turn) are not read',
                  'a letter applied to a number that nothing defines as a function ("The ball is at k(2) = 5.") is no function value',
                  'a derivative set equal to a number where it is no constant ("dv/dt = 6" for v(t) = 6t − 3t², "f′(x) = 0" at a stationary point) '
                  'states an equation in the variable to solve, and a derivative of anything else is ST-UNDEC-001 (D32)'):
        assert quote in d31, quote
    assert not _failing(_new("mai-t13", _with("mai-t13", MI_11, "if Kai had invested 4500 euros instead, $4500(1.036)^{11} = 6640.03$")))
    assert not _failing(_new("ch-t13", _with("ch-t13", "so I cannot give one yet.", "so I cannot give one yet.\n\nn = cV\nc = 0.0050 mol ÷ "
                                             "0.0550 dm³ = 0.091 mol dm⁻³")))
    checks, findings = _task("ph-t13", R7["ph-t13"]["response_text"])
    assert not _failing(checks) and not _rule(checks, "unbound-substitution")
    checks, findings = _decided("The ball is at k(2) = 5.", "mathematics_aa")
    assert not _failing(checks) and not _rule(checks, "function-value"), checks
    for text in ("Let f(x) = x³ − 3x.\nAt a stationary point f′(x) = 0.", "v(t) = 6t − 3t²\ndv/dt = 6", "d/dx (sin x) = cos x"):
        checks, findings = _decided(text, "mathematics_aa")
        assert not _rule(checks, "derivative") and [c for c, _m in findings] == ["ST-UNDEC-001"] and "a derivative" in findings[0][1], (text, checks)


def test_the_steps_of_part_b_name_the_readings_they_rest_on(d31):
    """D31: after "6t − 3t² = 0" and the root statement "keeps t = 0.", "3t(2 − t) = 0" is a step from the equation, its detail saying
    "rule root-statement", and t is part (b)'s unknown although part (a)'s question gives it a value (rule part-condition)."""
    assert ('a root stated for an equation leaves that equation as the relation the next line steps from (rule root-statement: after "6t − 3t² = 0" '
            'and "Factorising, rather than dividing by t, keeps t = 0.", "3t(2 − t) = 0" is a step from the equation, its `detail` saying "rule '
            'root-statement");') in d31
    checks, _f = _task("maa-t13", R7["maa-t13"]["response_text"])
    step = [c for c in checks if c[0] == "alg" and "'3t(2 − t) = 0'" in c[2]]
    roots = [c for c in checks if c[0] == "sol" and "'t = 0 or t = 2'" in c[2]]
    assert len(step) == 1 and _holds(*step[0][:2]) and "(rule root-statement)" in step[0][2] and "(rule part-condition)" in step[0][2], step
    assert len(roots) == 1 and _holds(*roots[0][:2]) and "(rule part-condition)" in roots[0][2] and "part (a)" in roots[0][2], roots


def test_d32_i97_the_master_prompt_and_the_mistakes_rows_name_the_new_rules():
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    i97 = _section(_pack_text("03-inspection.md"), "**I97 ", "\n- **I98")
    prompt, dossier = _pack_text("master_prompt.txt"), _pack_text("02-dossier.md")
    assert ('A polynomial\'s derivative is checked (rule derivative, D31), unless it is set equal to a number where it is no constant ("dv/dt = 6" '
            'for v(t) = 6t − 3t², an equation in the variable to solve); a derivative of anything else is ST-UNDEC-001.') in d32
    for rule in ("derivative", "function-value", "inequality-solution", "same-shape", "unbound-substitution", "exact-rounding", "result-rounding",
                 "given-data", "part-condition"):
        assert f"rule {rule}" in i97, rule
    for rule in ("function-value", "inequality-solution", "part-condition", "root-statement", "same-shape", "unbound-substitution", "exact-rounding",
                 "result-rounding", "given-data", "prose-base"):
        assert f"(rule {rule})" in prompt, rule
    row = ('| Reading "(92 − 18) ÷ 18 × 100 = 411%" as failing exact work, or "Given: r = 0.49 Ω." as holding against the request\'s 0.50 ohm | Exact '
           'work states a value of two or more figures to its last digit (rule exact-rounding); the request\'s data are taken as written, so a Given '
           'one unit off fails (rule given-data) | D31 |')
    assert row in dossier
    # the row's two quotes, decided as it says
    checks, _f = _decided("(92 − 18) ÷ 18 × 100 = 411%", "biology")
    assert checks and not _failing(checks) and _rule(checks, "exact-rounding"), checks
    got = _new("ph-t13", _with("ph-t13", PH_A, PH_A + "Given: r = 0.49 Ω.\n"))
    giv = [c for c in _failing(got) if c[0] == "giv"]
    assert len(giv) == 1 and _rule(giv, "given-data") and "failure severity warning" in giv[0][2], got


# ============================================================================================ the input budget
def test_the_readme_s_input_budget_is_the_compositions_measured(pack):
    """The README states each composition's size as the pack builds it (characters, and tokens at four characters a token, rounded to
    the hundred), and the window it recommends covers the largest composition, the largest dossier it names and the output budget."""
    readme = " ".join(_section(pack.readme, "**Input budget.**", "## 5.").split())  # line breaks are the markdown's, not the text's
    for chosen in compositions_of(SYSTEM_MODULES):
        n = len(pack.system_text(chosen))
        assert f"{n:,} characters" in readme and f"{round(n / 4, -2):,.0f} tokens" in readme, (composition_key(chosen), n)
    assert "never shorten the system text or a dossier" in readme.lower()
