"""The cross-repository golden vectors (PROTOCOL.md section 14.4): fresh (the generator writes exactly the committed files), true for
the translator's own functions, and passed by the Worker's adapter in JavaScript on the same files (node:test, when a
Node.js of at least 22.13 is installed)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings as hsettings, strategies as st

from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.canonical import CanonicalError, canonical_json, loads_strict, sha256_json, sha256_text
from epinoic_logic.integration.errors import CODES, WORKER_RAW_CODES
from epinoic_logic.integration.handshake import evaluate
from epinoic_logic.integration.protocol import dump

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "integration" / "vectors"


def _load(folder: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((VECTORS / folder).glob("*.json"))]


def test_the_vectors_are_what_the_generator_writes():
    proc = subprocess.run([sys.executable, str(ROOT / "integration" / "tools" / "vectors.py"), "--check"], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_canonical_vectors_hold_for_the_translator():
    for v in _load("canonical"):
        if v["name"] == "texts":
            assert all(sha256_text(t["text"]) == t["sha256"] for t in v["texts"])
        elif v["name"] == "refused":
            for doc in v["documents"]:
                with pytest.raises(CanonicalError):
                    loads_strict(doc)
        else:
            assert canonical_json(v["value"]) == v["canonical"] and sha256_json(v["value"]) == v["sha256"], v["name"]


def test_handshake_vectors_hold_for_the_translator():
    for v in _load("handshake"):
        out = evaluate(v["capabilities"], worker_env=v["worker_env"], base=v["base"])
        assert {"ok": out.ok, "code": out.code, "raw_code": out.raw_code} == v["expect"], v["name"]
    names = {v["name"] for v in _load("handshake")}
    # one refusal per handshake code the Worker can see (001, 002, 004-007, 009-013, 016), and the router's
    # attachment changes nothing
    codes = {v["expect"]["code"] for v in _load("handshake") if v["expect"]["code"]}
    assert codes == {"KIT-HS-001", "KIT-HS-002", "KIT-HS-004", "KIT-HS-005", "KIT-HS-006", "KIT-HS-007", "KIT-HS-009", "KIT-HS-010",
                     "KIT-HS-011", "KIT-HS-012", "KIT-HS-013", "KIT-HS-016"}
    assert "router-attached-changes-nothing" in names


def test_code_vectors_are_the_closed_tables():
    [raw] = [v for v in _load("codes") if "raw_codes" in v]
    [kit] = [v for v in _load("codes") if "codes" in v]
    assert raw["raw_codes"] == list(WORKER_RAW_CODES) and len(set(WORKER_RAW_CODES)) == len(WORKER_RAW_CODES)
    assert kit["codes"] == dict(CODES)
    assert all(re.fullmatch(r"[a-z0-9_]{1,64}", c) for c in WORKER_RAW_CODES)
    for code in CODES:
        if code.startswith("KIT-DL-"):
            assert f"kit_dl_{code[-3:]}" in WORKER_RAW_CODES, code


def test_the_answer_badge_says_passed_only_when_every_material_eligible_claim_has_a_permitted_positive_result():
    """The page's badge (chat-contract labels.json ``badges``, decision D27's conservative default): only
    ``formally_checked`` says "Automatic checks passed" or carries the success tone. The shared delivered cases give their
    summary and badge here as in the Worker's tests, among them one positive result of the encoding among eight material
    claims, an ambiguous material claim with a positive one, and a permitted positive with an invalid formalization."""
    from epinoic_logic.integration.delivery import ClaimFields, count_claims, summarize
    [labels] = _load("chat-contract")
    badges = labels["badges"]
    passed = lambda b: "passed" in b[0].lower() or b[1] == "is-ok"  # noqa: E731
    assert [s for s, b in badges.items() if passed(b)] == ["formally_checked"]
    assert not passed(labels["unknown_summary_badge"])
    cases = {c["name"]: c for c in labels["badge_cases"]}
    assert {"one-positive-of-eight-encoding-only", "an-ambiguous-material-claim-and-a-positive-one",
            "a-permitted-positive-and-an-invalid-formalization"} <= set(cases)
    for c in cases.values():
        summary = summarize(count_claims(ClaimFields(x["materiality"], x["formal"], x["attempt"], x["release_permitted"]) for x in c["claims"]))
        assert (summary, badges[summary]) == (c["summary"], c["badge"]), c["name"]
    assert not passed(cases["one-positive-of-eight-encoding-only"]["badge"])


_BADGE_CLAIM = st.tuples(st.sampled_from(["material", "supporting"]),
                         st.sampled_from(["ENTAILED", "CONSISTENT", "SATISFIABLE", "UNSUPPORTED", "INVALID_FORMALIZATION",
                                          "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "UNKNOWN", "TIMEOUT", "NOT_ATTEMPTED"]),
                         st.booleans())


@hsettings(max_examples=500, deadline=None)
@given(st.lists(_BADGE_CLAIM, max_size=10))
def test_a_passed_badge_implies_every_material_eligible_claim_positive_and_permitted(raw):
    from epinoic_logic.integration.delivery import ClaimFields, count_claims, summarize
    from epinoic_logic.integration.protocol import POSITIVE
    badges = _load("chat-contract")[0]["badges"]
    claims = [ClaimFields(m, f, "not_eligible" if f == "NOT_ELIGIBLE" else "skipped_budget" if f == "NOT_ATTEMPTED" else "attempted",
                          permitted and f in POSITIVE) for m, f, permitted in raw]
    text, tone = badges[summarize(count_claims(claims))]
    if "passed" in text.lower() or tone == "is-ok":
        eligible = [c for c in claims if c.materiality == "material" and c.attempt != "not_eligible"]
        assert eligible and all(c.formal in POSITIVE and c.release_permitted for c in eligible)


def test_router_port_vectors_re_derive():
    hello = R.check_hello(next(v for v in _load("router-port") if v["hello"])["hello"])
    origins = set()
    for v in _load("router-port"):
        req = R.check_request(v["request"])
        adm = R.admit_plan(req, v["plan"], hello=hello if v["hello"] else None)
        assert {"origin": adm.origin, "refusal": adm.refusal, "floor": dump(adm.floor), "effective_plan_id": adm.effective.plan_id} == v["expect"], v["name"]
        origins.add((adm.origin, adm.refusal))
    assert ("floor", None) in origins and ("router", None) in origins and ("floor", "KIT-RT-020") in origins


def _node() -> str | None:
    node = shutil.which("node")
    if node is None:
        return None
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in out.split(".")[:2])
    return node if (major, minor) >= (22, 13) else None


def test_the_worker_adapter_passes_the_same_vectors_in_javascript():
    node = _node()
    if node is None:
        pytest.skip("Node.js 22.13 or later is not installed: the JavaScript half of the vectors is NOT RUN here (readiness reports it)")
    tests = sorted(str(p) for p in (ROOT / "integration" / "website" / "tests").glob("*.test.js"))
    proc = subprocess.run([node, "--test", *tests], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert re.search(r"^# fail 0$", proc.stdout, re.M), proc.stdout[-2000:]
