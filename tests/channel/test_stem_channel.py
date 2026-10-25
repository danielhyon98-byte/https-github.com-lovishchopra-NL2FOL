"""STEM answers through the hub (docs/STEM_DESIGN.md, sections 1, 9 and 11): the observed case, the 22 probe answers
(13 deliberately wrong: each caught by an engine check on its claim or named undecided; 9 correct: no error), the
STEM hub hooks (echo exemption, coverage, imperatives, word count), relay, and quotations checked exactly as on the
other branches."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel.request_parser import count_answer_words, extract_items
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.stem.hub_hooks import STEM_HOOKS
from epinoic_logic.translate.contracts import SuppliedText

KEY = b"stem-channel-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)

#: (case, subject, agent, request, answer). The answers were written for the read-only probe of section 1.
CASES = [
    ('P1-observed', 'Physics', 'physics-specialist', 'A trolley accelerates uniformly from rest to 20 m s^-1 in 4.0 s. Calculate its acceleration.', 'The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻².'),
    ('P2-latex-inline-ok', 'Physics', 'physics-specialist', 'A stone is dropped from rest. Calculate its speed after 3.0 s.', 'Taking $g = 9.8\\ \\text{m s}^{-2}$ and $u = 0$, we use $v = u + at$. So $v = 0 + 9.8 \\times 3.0 = 29.4\\ \\text{m s}^{-1}$.'),
    ('P3-latex-display-err', 'Physics', 'physics-specialist', 'Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.', 'The kinetic energy is given by\n\\[ E_k = \\frac{1}{2} m v^2 = \\frac{1}{2}(2.0)(3.0)^2 = 18\\,\\text{J} \\]\nThe mass therefore carries 18 J of kinetic energy.'),
    ('P4-unicode-ok', 'Physics', 'physics-specialist', 'Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.', 'Eₖ = ½mv² = ½ × 2.0 × 3.0² = 9.0 J. This is the energy the mass carries.'),
    ('P5-sci-notation-err', 'Physics', 'physics-specialist', 'Light of frequency 5.0 × 10^14 Hz travels in a vacuum. Determine its wavelength.', 'The speed of light is c = 3.0 × 10^8 m/s (3.0e8 m s⁻¹). Using λ = c/f, λ = 3.0 × 10⁸ / 5.0 × 10¹⁴ = 6.0 × 10⁻⁶ m.'),
    ('P6-gravitation-ok', 'Physics', 'physics-specialist', "Calculate the gravitational force on a 70 kg person at the Earth's surface.", 'F = Gm₁m₂/r² with G = 6.67 × 10⁻¹¹ N m² kg⁻², M = 5.97e24 kg and r = 6.37e6 m. F = 6.67 × 10⁻¹¹ × 5.97e24 × 70 / (6.37e6)² ≈ 687 N.'),
    ('P7-momentum-err', 'Physics', 'physics-specialist', 'Calculate the momentum of a 1200 kg car moving at 25 m/s.', "Momentum p = mv = 1200 kg × 25 m/s = 3.5 × 10⁴ kg·m/s. The car's momentum is 3.5 × 10⁴ kg m s⁻¹."),
    ('P8-unit-conversion-err', 'Physics', 'physics-specialist', 'Convert 72 km/h into m/s and state the time to travel 100 m.', '72 km h⁻¹ = 72 × 1000 / 3600 = 25 m s⁻¹. At 25 m/s, 100 m takes t = 100/25 = 4.0 s.'),
    ('P9-sqrt-trig-ok', 'Physics', 'physics-specialist', 'A ball falls 5.0 m. Calculate its speed, and the horizontal component of a 10 N force at 60° to the horizontal.', 'v = √(2gh) = √(2 × 9.8 × 5.0) = 9.9 m/s. The horizontal component is F cos θ = 10 cos 60° = 5.0 N.'),
    ('P10-percent-efficiency-err', 'Physics', 'physics-specialist', 'A motor uses 500 J of electrical energy and does 400 J of useful work. Calculate its efficiency.', 'Efficiency = useful output / input × 100% = 400 J / 500 J × 100% = 75%. The efficiency rose from 60 per cent to 75 per cent after servicing, a rise of 15 per cent.'),
    ('P11-units-misread-ok', 'Physics', 'physics-specialist', 'Describe the change in length of the spring.', "The spring's length fell from 2 m to 50 cm, a fall of 75 per cent. The extension rose from 500 mm to 2 m, a fourfold increase."),
    ('P12-self-check-ok', 'Physics', 'physics-specialist', 'Calculate the speed if d = 120 m and t = 8 s.', 'v = d/t = 120 m / 8 s = 15 m/s. Check: 15 × 8 = 120, so the answer is verified and the units are correct.'),
    ('C1-moles-err', 'Chemistry', 'chemistry-specialist', 'Calculate the amount of water in 36 g of H₂O and the enthalpy change for burning 2 mol of hydrogen.', 'n(H₂O) = m/M = 36 g ÷ 18.0 g mol⁻¹ = 3.0 mol. For 2 H₂ + O₂ → 2 H₂O, ΔH = 2 × (−286 kJ mol⁻¹) = −572 kJ.'),
    ('C2-concentration-yield-err', 'Chemistry', 'chemistry-specialist', 'Calculate the concentration and the percentage yield.', 'c = n/V = 0.50 mol / 0.250 dm³ = 2.0 mol dm⁻³. The percentage yield is 4.5 g / 6.0 g × 100 = 80%.'),
    ('C3-gas-law-ok', 'Chemistry', 'chemistry-specialist', 'Calculate the volume of 0.50 mol of an ideal gas at 300 K and 100 kPa.', 'Using pV = nRT, V = nRT/p = (0.50 × 8.31 × 300) / (100 × 10³) = 0.0125 m³ = 12.5 dm³.'),
    ('M1-latex-quadratic-ok', 'Mathematics: Analysis and Approaches', 'maths-specialist', 'Solve x^2 - 5x + 6 = 0.', 'We solve $x^2 - 5x + 6 = 0$ with the quadratic formula: $x = \\frac{5 \\pm \\sqrt{25 - 24}}{2}$, so $x = 2$ or $x = 3$. Checking, $2^2 - 5(2) + 6 = 0$.'),
    ('M2-series-err', 'Mathematics AA HL', 'maths-specialist', 'Find the 10th term and the sum of the first 10 terms of the arithmetic sequence 3, 7, 11, ...', 'Here $u_1 = 3$ and $d = 4$. Then $u_{10} = u_1 + 9d = 3 + 9 \\times 4 = 39$ and $S_{10} = \\frac{10}{2}(2(3) + 9(4)) = 220$.'),
    ('M3-calculus-err', 'Mathematics: Analysis and Approaches', 'maths-specialist', 'Differentiate f(x) = 3x^2 + 2x.', "Using the power rule, $f'(x) = \\frac{d}{dx}(3x^2 + 2x) = 3x + 2$. At $x = 1$, $f'(1) = 5$."),
    ('M4-ai-percent-err', 'Mathematics: Applications and Interpretation', 'maths-specialist', 'A price rose from 250 to 300. Calculate the percentage increase.', 'The price rose from 250 to 300, a rise of 25 per cent. As a fraction, 50/250 = 0.2.'),
    ('B1-magnification-err', 'Biology', 'biology-specialist', 'Calculate the magnification of a cell whose image is 25 mm long and whose actual length is 50 µm.', 'Magnification = image size / actual size = 25 mm / 50 µm = 25 000 µm / 50 µm = 50×.'),
    ('E1-ess-efficiency-ok', 'Environmental Systems and Societies', 'ess-specialist', 'Calculate the efficiency of energy transfer between the trophic levels.', 'Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%. About 10% of the energy passes to the next level.'),
    ('CS1-binary-err', 'Computer Science', 'cs-specialist', 'Convert 1011 in binary to denary and FF in hexadecimal to denary.', '1011₂ = 1×2³ + 0×2² + 1×2¹ + 1×2⁰ = 11₁₀. FF₁₆ = 15 × 16 + 15 = 256.'),
]
BRANCH = {"Physics": "sciences", "Chemistry": "sciences", "Biology": "sciences", "Environmental Systems and Societies": "sciences",
          "Computer Science": "computer_science"}
#: wrong answers caught by an engine check: (case, a fragment of the claim the INT-SUBJ-001 finding must name)
CAUGHT = {
    "P1-observed": "(20 - 0)/4.0 = 6.0", "P3-latex-display-err": "\\frac{1}{2}(2.0)(3.0)^2 = 18", "P5-sci-notation-err": "= 6.0 × 10⁻⁶ m",
    "P7-momentum-err": "= 3.5 × 10⁴ kg·m/s", "P8-unit-conversion-err": "72 × 1000 / 3600 = 25", "P10-percent-efficiency-err": "a rise of 15 per cent",
    "C1-moles-err": "= 3.0 mol", "C2-concentration-yield-err": "× 100 = 80%", "M2-series-err": "= 220", "M4-ai-percent-err": "a rise of 25 per cent",
    "CS1-binary-err": "15 × 16 + 15 = 256", "B1-magnification-err": "25 000 µm / 50 µm = 50×",
}
#: wrong answers outside the encodings or the front end's reading: named on the receipt with the claim, never silent
NAMED = {"M3-calculus-err": "ST-UNDEC-001"}
CORRECT = {"P2-latex-inline-ok", "P4-unicode-ok", "P6-gravitation-ok", "P9-sqrt-trig-ok", "P11-units-misread-ok", "P12-self-check-ok", "C3-gas-law-ok",
           "M1-latex-quadratic-ok", "E1-ess-efficiency-ok"}


def send(subject: str, agent: str, request: str, answer: str, *, supplied=(), report_id="r1"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, rq = hub.dispatch("t", agent, request, list(supplied))
    assert rq.status is TransmissionStatus.ACCEPTED
    reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id=report_id)
    return hub, reply, rc


def claim_text(hub: RouterHub, cid: str) -> str:
    rep = next(iter(hub.channels["t"].transmitted_reports.values()))
    return next(c.claim_text for c in rep.claims if c.claim_id == cid)


def test_the_case_lists_cover_every_probe_answer():
    assert set(CAUGHT) | set(NAMED) | CORRECT == {c[0] for c in CASES} and len(CAUGHT) + len(NAMED) == 13 and len(CORRECT) == 9


def test_the_observed_case_end_to_end():
    case = CASES[0]
    hub, reply, rc = send(*case[1:])
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and rc.branch == "sciences"
    err = [f for f in rc.errors if f.code == "INT-SUBJ-001"]
    assert len(err) == 1 and err[0].claim_ids == ["s1.2"] and "(20 - 0)/4.0 = 6.0 m s⁻²" in err[0].message and "c = 5, r = 6" in err[0].message
    assert claim_text(hub, "s1.2") == "Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻²."
    eq = next(c for c in rc.formal_checks if c.constraint_id == "stem-eq-1")
    assert eq.satisfied is False and eq.formal_status == "COUNTEREXAMPLE" and eq.formal_result_id == err[0].formal_result_id
    rep = hub.channels["t"].transmitted_reports["r1"]
    assert rep.original_response == case[4]  # delivered verbatim
    assert rc.summary.endswith("Formal results concern only the encoded checks under their premises; coverage is heuristic.")
    assert "FAILED: stem-eq-1" in rc.summary


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_probe_answers(case):
    cid, subject, agent, request, answer = case
    hub, reply, rc = send(subject, agent, request, answer)
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert rc.branch == BRANCH.get(subject, "mathematics")
    assert not any(f.code in ("INT-SUBJ-003", "INT-REQ-011", "INT-REQ-012") for f in rc.findings)
    if cid in CORRECT:
        assert rc.errors == [], [f.message[:160] for f in rc.errors]
        assert not any(f.code == "INT-SUBJ-004" for f in rc.findings)
        assert all(c.satisfied is not False for c in rc.formal_checks)
    elif cid in CAUGHT:
        named = [f for f in rc.errors if f.code == "INT-SUBJ-001" and f.claim_ids]
        assert named, [f.code for f in rc.findings]
        assert any(CAUGHT[cid] in claim_text(hub, c) for f in named for c in f.claim_ids), [f.claim_ids for f in named]
    else:
        st = [s for s in rc.structural_findings if s.code == NAMED[cid]]
        assert st and all(s.claim_ids and s.severity == "warning" for s in st)
        assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


def test_a_correct_show_that_answer_is_not_an_echo_of_the_request():
    request = "Show that 36 g of water is 2.0 mol."
    answer = "n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol"
    hub, reply, rc = send("Chemistry", "chemistry-specialist", request, answer)
    assert not any(f.code == "INT-REQ-011" for f in rc.findings) and rc.errors == []
    assert STEM_HOOKS.echo_exempt(answer, request, "chemistry") is True
    # a restatement with no computation of its own is not exempt
    assert STEM_HOOKS.echo_exempt("36 g of water is 2.0 mol.", request, "chemistry") is False
    restated = send("Chemistry", "chemistry-specialist", "Show that 36 g of water is 2.0 mol in this sample.", "Show that 36 g of water is 2.0 mol.")[2]
    assert any(f.code == "INT-REQ-011" for f in restated.errors)


def test_an_equation_only_answer_covers_its_item():
    _, _, rc = send("Physics", "physics-specialist", "Calculate the acceleration.", "a = (20 - 0)/4.0 = 5.0 m s⁻²")
    assert all(c.addressed for c in rc.coverage) and not any(f.code == "INT-REQ-004" for f in rc.findings) and rc.errors == []


def test_stem_imperatives_split_a_multi_part_question():
    request = "A car accelerates from rest at 2.0 m s⁻² for 5.0 s.\n(a) Determine its final speed.\n(b) Find the distance travelled."
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"]))
    _, req, _ = hub.dispatch("t", "physics-specialist", request)
    assert [i.text for i in req.items] == ["(a) Determine its final speed.", "(b) Find the distance travelled."]
    # the default reading (every non-STEM branch) gives one item per part too (round 7): the same items
    assert [i.text for i in extract_items(request)] == ["(a) Determine its final speed.", "(b) Find the distance travelled."]


def test_latex_control_words_are_not_words_and_a_maths_span_is_one_word():
    answer = "The energy is $E_k = \\frac{1}{2} m v^2 = \\frac{1}{2}(2.0)(3.0)^2 = 9.0\\,\\text{J}$, so the mass carries 9.0 J."
    view = lambda t: STEM_HOOKS.word_count_view(t, "physics")  # noqa: E731
    assert count_answer_words(answer, view=view)[0] < count_answer_words(answer)[0]
    _, _, rc = send("Physics", "physics-specialist", "Calculate the kinetic energy in no more than 12 words.", answer)
    assert not any(f.code == "INT-REQ-005" for f in rc.findings), [f.message for f in rc.findings]
    assert any(c.satisfied for c in rc.constraint_results)


def test_a_code_only_answer_is_an_answer():
    _, _, rc = send("Computer Science", "cs-specialist", "Write a function that returns the area of a circle.",
                    "```python\ndef area(r):\n    return 3.14159 * r ** 2\n```")
    assert not any(f.code == "INT-REQ-012" for f in rc.findings) and rc.errors == []
    assert any(s.code == "ST-CODE-001" and s.severity == "info" for s in rc.structural_findings)


def test_relay_without_a_request_binds_only_the_answers_own_values():
    agent = "chemistry-specialist"
    plan = WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Chemistry", task_type="short_answer", selected_agent_ids=[agent, "combinator"])
    ch = TranslatorChannel(plan, signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", agent, "Show that 36 g of water is 2.0 mol.")
    reply, rc = ch.respond_text(m.message_id, "n = m/M = 36 g / 18 g mol⁻¹ = 3.0 mol", agent_id=agent, report_id="r-c")
    assert {c.constraint_id for c in rc.formal_checks} >= {"stem-eq-1", "stem-tgt-1"}
    report = ch.transmitted_reports["r-c"]
    _, relayed = ch.relay(agent, AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, report)
    ids = {c.constraint_id for c in relayed.formal_checks}
    assert "stem-eq-1" in ids and not any(i.startswith(("stem-tgt", "stem-giv")) for i in ids)
    assert any(f.code == "INT-SUBJ-001" and f.claim_ids == ["s1.1"] for f in relayed.errors)


def test_quotations_in_a_stem_answer_are_checked_as_on_every_branch():
    from epinoic_logic.branches.generic_parser import GenericTextParser
    booklet = SuppliedText(document_id="doc-b", title="Data booklet", text="The acceleration of free fall near the Earth's surface is 9.81 m s⁻².")
    good = 'The Data booklet states "The acceleration of free fall near the Earth\'s surface is 9.81 m s⁻²", so v = 9.81 × 2.0 = 19.62 m s⁻¹.'
    _, _, rc = send("Physics", "physics-specialist", "Calculate the speed after 2.0 s.", good, supplied=[booklet])
    assert not any(f.code in ("INT-REQ-003", "INT-REQ-010") for f in rc.findings) and rc.errors == []
    invented = 'The Data booklet states "free fall is exactly ten metres per second squared everywhere", so v = 10 × 2.0 = 20 m s⁻¹.'
    hub, _, rc2 = send("Physics", "physics-specialist", "Calculate the speed after 2.0 s.", invented, supplied=[booklet])
    assert any(f.code == "INT-REQ-003" and f.claim_ids == ["s1.1"] for f in rc2.errors)
    # the credit is the one every other branch gives the same sentence (the shared attribution rule)
    stem_claim = hub.channels["t"].transmitted_reports["r1"].claims[0]
    generic = GenericTextParser("physics-specialist").parse_response(invented, request_id="q", task_id="t", report_id="x", subject="Physics", task_type="short_answer",
                                                                     supplied_texts=[booklet]).claims[0]
    assert stem_claim.source_refs == generic.source_refs and stem_claim.source_refs[0].document_id == "doc-b"
    uncredited = 'A textbook says "free fall is exactly ten metres per second squared everywhere", so v = 10 × 2.0 = 20 m s⁻¹.'
    _, _, rc3 = send("Physics", "physics-specialist", "Calculate the speed after 2.0 s.", uncredited, supplied=[booklet])
    assert any(s.code == "CORE-SRC-003" and s.severity == "warning" for s in rc3.structural_findings)


def test_an_unverifiable_quotation_with_no_text_is_named_and_an_inch_mark_is_not():
    _, _, rc = send("Physics", "physics-specialist", "Describe the ruler.", 'The ruler is 12" long and the book says "energy is conserved in every collision".')
    codes = {s.code for s in rc.structural_findings}
    assert "CORE-SRC-003" in codes and "CORE-SRC-004" not in codes


def test_a_peer_report_quoted_in_a_stem_answer_is_checked():
    peer = SuppliedText(document_id="peer:t-maths", author="maths-specialist", text="The gradient of the line is 2.5 so the acceleration is 2.5 m s⁻².")
    answer = 'The maths specialist writes "the acceleration is 2.5 m s⁻²", so F = ma = 2.0 × 2.5 = 5.0 N.'
    _, _, rc = send("Physics", "physics-specialist", "Calculate the force.", answer, supplied=[peer])
    assert rc.errors == [] and not any(f.code == "INT-REQ-003" for f in rc.findings)
    wrong = 'The maths specialist writes "the acceleration is 4.5 m s⁻²", so F = ma = 2.0 × 4.5 = 9.0 N.'
    _, _, rc2 = send("Physics", "physics-specialist", "Calculate the force.", wrong, supplied=[peer])
    assert any(f.code in ("INT-REQ-003", "INT-REQ-010") for f in rc2.findings)


def test_a_self_certification_never_becomes_a_material_claim():
    answer = "v = d/t = 120 m / 8 s = 15 m/s.\n\nAll figures have been verified."
    hub, _, rc = send("Physics", "physics-specialist", "Calculate the speed.", answer)
    rep = hub.channels["t"].transmitted_reports["r1"]
    note = next(c for c in rep.claims if c.claim_text == "All figures have been verified.")
    assert note.claim_role == "other" and note.materiality == "supporting"
    assert any(s.code == "CORE-SELF-001" for s in rc.structural_findings)
    assert rc.errors == []


def test_the_stem_branches_keep_non_stem_branches_unchanged():
    # a History answer on the same hub still goes through the general reading (no STEM hooks, no STEM pack)
    hub, _, rc = send("History", "history-specialist", "Explain the rise in unemployment.",
                      "Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932. The Depression was therefore decisive.")
    assert rc.branch == "history" and not any(c.constraint_id.startswith("stem-") for c in rc.formal_checks)


def test_statements_beyond_the_claim_limit_are_named_int_req_013():
    answer = "\n\n".join(f"Step {i}: x = {i}." for i in range(600))
    hub, reply, rc = send("Mathematics: Analysis and Approaches", "maths-specialist", "Solve the system.", answer)
    assert reply is not None
    f = next(f for f in rc.findings if f.code == "INT-REQ-013")
    assert f.claim_ids == ["m.tail"] and "89" in f.message
    rep = hub.channels["t"].transmitted_reports["r1"]
    assert len(rep.claims) == 512 and rep.original_response == answer
