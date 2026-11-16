"""Every public entry point of every module of the combinator, fed the standard hostile inputs (clearance c3's sweep).

The standard hostile inputs are runs of about 20,000 characters (blanks, tabs, line breaks, stops, closing marks, mark labels
such as "(A1)", parentheses, brackets, fence openers, number words joined by "and", "=" links, list markers and the openers
of this package's own readings), each followed by a character that defeats the match. One test per module feeds each of
its public entry points every one of them, as text where it takes text and inside a document of the published contract
where it takes one, and asserts a time bound with a wide margin (each call takes milliseconds; the bound is two seconds).
A reading here that rescanned the text from every opener, or a pattern with adjacent unbounded runs, would stall the
service on such an input and fail the bound.

The sweep found no stall in this package (the slowest call measured about 40 ms). It found two exits outside the exporter's
contract ("ExportError", or exit status 2 with one line on standard error, never a traceback), fixed with it:

* ``export`` looked a hostile ``--out`` path up before its error handling, so a name the system refuses as too long
  (OSError) or a path holding a NUL (ValueError) raised a traceback, and a refusal echoed the whole path, line breaks and
  control characters included; a path is now shown with its non-printable characters escaped, cut at 200 characters with
  its length (``test_the_exporter_refuses_a_hostile_path_in_one_line``: 29 of the 56 export cases failed before);
* ``read_export`` parsed the manifest with ``json.loads``, so a manifest of 20,000 nested brackets raised RecursionError; it
  is read with the protocol's strict reader (``jsonio.loads_strict``: at most 64 levels, no repeated key, no float) and
  refused by name (``test_export_is_linear_on_hostile_input``).
"""
from __future__ import annotations

import contextlib
import io
import json
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from combinator_helpers import IDS, claim, input_doc, text
from epinoic_combinator import jsonio, port, prompt, schema
from epinoic_combinator import runner as R
from epinoic_combinator.contract import load_contract
from epinoic_combinator.export import ExportError, export, main as export_main, read_export
from epinoic_combinator.jsonio import sha256_text
from epinoic_combinator.pack import load_pack, pack_sha256
from epinoic_combinator.providers import CompletionRequest, FaithfulFakeProvider, ScriptedProvider, withheld_work

CONTRACT = load_contract()
PACK = load_pack()

#: The standard hostile inputs: runs of about 20,000 characters, each followed by a character that defeats the match.
HOSTILE: dict[str, str] = {
    "blanks": " " * 20000 + "x", "tabs": "\t" * 20000 + "x", "line breaks": "\n" * 20000 + "x", "stops": "." * 20000 + "x",
    "closing marks": ")" * 20000 + "x", "mark labels": "(A1) " * 4000 + "x", "parentheses": "(" * 20000 + "x", "brackets": "[" * 20000 + "x",
    "braces": "{" * 20000 + "x", "quotation marks": '"' * 20000 + "x", "fence openers": "```" * 6667 + "x",
    "number words joined by and": "one and two and " * 1250 + "x", "= links": "x = " * 5000 + "y", "list markers": "- " * 10000 + "x",
    "sentence ends": ". " * 10000 + "x", "colons": ": " * 10000 + "x", "question marks": "? " * 10000 + "x",
    "decline openers": "I cannot " * 2223 + "x", "choice openers": "I can't choose a " * 1177 + "x", "reply openers": "reply " * 3334 + "x",
    "reply and I will write": "Reply and I will write the full " * 625, "once you confirm": "once you confirm " * 1177 + "x",
    "shall I write": "shall I write " * 1429 + "x", "would you like me to write": "would you like me to write " * 741 + "x",
    "no-break spaces then a control": "\u00a0" * 20000 + "\x01", "visible run then a control": "a" * 20000 + "\x01",
    "control characters": "\x07" * 20000 + "x", "bidirectional controls": "\u202e" * 20000 + "x",
}
#: The bound on one call, wide: every call measured here takes milliseconds.
BOUND_S = 2.0


def _bounded(what: str, call: Callable[[], Any]) -> Any:
    """Run ``call`` (whatever it raises is its answer, never a stall) and assert it returns within :data:`BOUND_S`."""
    start = time.perf_counter()
    try:
        value = call()
    except Exception as exc:  # noqa: BLE001 - the time is what is measured here; each test checks the outcomes it needs
        value = exc
    elapsed = time.perf_counter() - start
    assert elapsed < BOUND_S, f"{what}: {elapsed:.2f} s"
    return value


def _source(hostile: str, *, role: str = "point") -> dict:
    """A source report whose claims hold the hostile text, cut to a source text's limit in contract (4,000 characters)."""
    return {"report_id": "rep-h", "agent_id": "history", "subject": "History", "branch": "history",
            "claims": [claim("h1", hostile[:4000], role=role), claim("h2", hostile[-4000:], role="other", materiality="supporting"),
                       claim("h3", "The Treaty of Versailles was signed in June 1919.")]}


def _input(hostile: str) -> dict:
    """A combinator input in contract whose sources hold the hostile text."""
    second = {"report_id": "rep-e", "agent_id": "economics", "subject": "Economics", "branch": "economics",
              "claims": [claim("e1", hostile[:4000], certainty="probable")]}
    return input_doc(sources=[_source(hostile), second])


def _agent_output(hostile: str) -> dict:
    """What an agent might write with the hostile text in every text field (over a field's limit: out of contract)."""
    return {"claims": [{"text": hostile, "source_claim_ids": ["h1"], "certainty": "established", "transformation": "carried"}],
            "dropped": [{"source_claim_ids": ["h2"], "reason": hostile}],
            "conflicts": [{"claim_ids": ["h3", "e1"], "description": hostile}]}


def _message(hostile: str) -> dict:
    """The port message of :func:`_agent_output` for :func:`_input`."""
    return {"schema": "epinoic.integration.combinator-output.v1", "protocol": "epinoic.integration.v1", "port_version": CONTRACT.port_version,
            "ids": dict(IDS), "instruction_pack_sha256": PACK.sha256,
            "claims": [{**c, "evidence_refs": None} for c in _agent_output(hostile)["claims"]],
            "dropped": _agent_output(hostile)["dropped"], "conflicts": _agent_output(hostile)["conflicts"]}


# ----------------------------------------------------------------------------------------------- one test per module


@pytest.mark.parametrize("name", list(HOSTILE))
def test_jsonio_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    assert isinstance(_bounded("loads_strict(text)", lambda: jsonio.loads_strict(hostile)), jsonio.JsonError)
    assert isinstance(_bounded("loads_strict(bytes)", lambda: jsonio.loads_strict(hostile.encode("utf-8"))), jsonio.JsonError)
    assert _bounded("loads_strict(a JSON string)", lambda: jsonio.loads_strict(json.dumps(hostile))) == hostile
    nested = {"claims": [hostile, {"text": hostile}]}
    assert _bounded("loads_strict(a document)", lambda: jsonio.loads_strict(json.dumps(nested))) == nested
    assert _bounded("check_value", lambda: jsonio.check_value(nested)) is None
    assert _bounded("canonical_json", lambda: jsonio.canonical_json(nested)) == json.dumps(nested, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert len(_bounded("sha256_text", lambda: sha256_text(hostile))) == 64
    assert _bounded("sha256_json", lambda: jsonio.sha256_json(nested)) == jsonio.sha256_bytes(jsonio.canonical_json(nested).encode("utf-8"))
    assert _bounded("has_lone_surrogate", lambda: jsonio.has_lone_surrogate(hostile)) is False


@pytest.mark.parametrize("name", list(HOSTILE))
def test_schema_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    assert "characters" in _bounded("shown", lambda: schema.shown(hostile))
    for doc_name, doc in (("combinator-output.v1.schema.json", _message(hostile)), ("combinator-input.v1.schema.json", json.loads(text(_input(hostile))))):
        validator = schema.Validator(CONTRACT.documents[doc_name])
        _bounded(f"Validator.errors on {doc_name}", lambda: validator.errors(doc, limit=8))
        _bounded(f"Validator.is_valid on {doc_name}", lambda: validator.is_valid(doc))
        _bounded(f"Validator.errors on the text alone ({doc_name})", lambda: validator.errors(hostile))
    # the text rule reads the whole text: a run of visible characters that ends in a control character is refused
    text_rule = schema.Validator(CONTRACT.documents["combinator-output.v1.schema.json"])
    assert _bounded("the text rule on a run ending in a control", lambda: text_rule.errors(_message(hostile[:3999] + "\x01"), limit=8))


@pytest.mark.parametrize("name", list(HOSTILE))
def test_contract_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    inp = _bounded("check_input(a valid input)", lambda: CONTRACT.check_input(text(_input(hostile))))
    good, problem = inp if isinstance(inp, tuple) else (None, inp)
    for what, raw in (("check_input(text)", hostile), ("check_input(an input over a claim's limit)", text(input_doc(sources=[
            {**_source(hostile), "claims": [claim("h1", hostile)]}, _input(hostile)["sources"][1]])))):
        got = _bounded(what, lambda: CONTRACT.check_input(raw))
        assert isinstance(got, tuple) and got[0] is None and got[1].code == "KIT-CB-001", (what, got)
    reference = good if good is not None else input_doc()
    for what, raw in (("check_output(text)", hostile), ("check_output(a message)", _message(hostile)), ("check_output(its text)", text(_message(hostile)))):
        got = _bounded(what, lambda: CONTRACT.check_output(raw, reference))
        assert got is not None and got.code.startswith("KIT-CB-"), (what, got)
    assert _bounded("transformation_problem", lambda: CONTRACT.transformation_problem({"claims": [{"transformation": hostile}]})).code == "KIT-CB-003"
    for what, raw in (("check_hello(text)", hostile), ("check_hello(a hello)", {**json.loads(port.hello()), "combinator": {"name": hostile, "version": "1"}}),
                      ("check_refusal(text)", hostile), ("check_refusal(a refusal)", {"schema": "epinoic.integration.combinator-refusal.v1",
                       "protocol": "epinoic.integration.v1", "port_version": "1.0", "ids": None, "instruction_pack_sha256": PACK.sha256,
                       "code": "KIT-CB-001", "reason": "input_not_json", "detail": hostile})):
        check = CONTRACT.check_hello if what.startswith("check_hello") else CONTRACT.check_refusal
        got = _bounded(what, lambda: check(raw))
        assert got is not None and got.code == "KIT-CB-002", (what, got)


@pytest.mark.parametrize("name", list(HOSTILE))
def test_runner_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    refused = _bounded("run(hostile input text)", lambda: R.run(hostile, FaithfulFakeProvider()))
    assert not refused.ok and refused.refusal["code"] == "KIT-CB-001" and refused.provider_calls == 0
    inp = _input(hostile)
    for what, provider in (("run(hostile agent text)", ScriptedProvider(hostile)), ("run(hostile texts in the agent's format)", ScriptedProvider(text(_agent_output(hostile)))),
                           ("run(a hostile agent text over the runner's limit)", ScriptedProvider(hostile * 14))):
        result = _bounded(what, lambda: R.run(inp, provider))
        assert not result.ok and result.refusal["code"] in ("KIT-CB-002", "KIT-CB-006"), (what, result.refusal)
        assert len(result.refusal["detail"]) <= 300 and hostile[:50] not in result.refusal["detail"], "a refusal never echoes the agent's prose"
    faithful = _bounded("run(hostile claims, the faithful fake)", lambda: R.run(inp, FaithfulFakeProvider()))
    assert faithful.ok or faithful.refusal["code"] == "KIT-CB-002", faithful.refusal


@pytest.mark.parametrize("name", list(HOSTILE))
def test_prompt_is_linear_on_hostile_input(name):
    checked, problem = CONTRACT.check_input(_input(HOSTILE[name]))
    assert problem is None, problem
    view = _bounded("agent_view", lambda: prompt.agent_view(checked))
    assert [c["text"] for s in view["sources"] for c in s["claims"]] == [c["text"] for s in checked["sources"] for c in s["claims"]]
    assert json.loads(_bounded("render", lambda: prompt.render(checked))) == view


@pytest.mark.parametrize("name", list(HOSTILE))
def test_port_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    assert json.loads(_bounded("combine(hostile text)", lambda: port.combine(hostile, FaithfulFakeProvider())))["code"] == "KIT-CB-001"
    combined = json.loads(_bounded("combine(hostile claims)", lambda: port.combine(text(_input(hostile)), FaithfulFakeProvider())))
    assert combined["schema"].endswith(("combinator-output.v1", "combinator-refusal.v1"))
    assert json.loads(_bounded("combine(hostile claims, no provider)", lambda: port.combine(text(_input(hostile)))))["reason"] == "provider_unavailable"


@pytest.mark.parametrize("name", list(HOSTILE))
def test_providers_are_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    for cut in (hostile, hostile[:4000], hostile[-4000:]):
        start = time.perf_counter()
        for _ in range(5):
            withheld_work(cut)
        assert time.perf_counter() - start < BOUND_S, name
    checked, problem = CONTRACT.check_input(input_doc(sources=[_source(hostile, role="other"), _input(hostile)["sources"][1]]))
    assert problem is None, problem
    request = CompletionRequest(tier="cheapest", system=PACK.instructions, user=prompt.render(checked), instruction_pack_sha256=PACK.sha256,
                                request_id=IDS["request_id"], max_output_bytes=R.MAX_AGENT_OUTPUT_BYTES)
    written = json.loads(_bounded("FaithfulFakeProvider.complete", lambda: FaithfulFakeProvider().complete(request)))
    assert {cid for c in written["claims"] for cid in c["source_claim_ids"]} | {cid for d in written.get("dropped", []) for cid in d["source_claim_ids"]} \
        == {"h1", "h2", "h3", "e1"}
    assert _bounded("ScriptedProvider.complete", lambda: ScriptedProvider(hostile).complete(request)) == hostile


@pytest.mark.parametrize("name", list(HOSTILE))
def test_pack_is_linear_on_hostile_input(name):
    hostile = HOSTILE[name]
    assert len(_bounded("pack_sha256", lambda: pack_sha256(hostile, hostile, {hostile: hostile.encode("utf-8")}))) == 64
    assert _bounded("load_pack", load_pack).identity() == PACK.identity()


@pytest.mark.parametrize("name", list(HOSTILE))
def test_export_is_linear_on_hostile_input(name, tmp_path):
    hostile = HOSTILE[name]
    for k, manifest in enumerate((hostile, json.dumps({"files": {hostile: hostile}, "instruction_pack": {"name": hostile, "version": hostile, "sha256": hostile}}))):
        directory = tmp_path / f"pack-{k}"
        export(directory)
        (directory / "MANIFEST.json").write_text(manifest, encoding="utf-8")
        assert isinstance(_bounded("read_export(a hostile manifest)", lambda: read_export(directory)), ExportError)


@pytest.mark.parametrize("name", list(HOSTILE))
def test_the_exporter_refuses_a_hostile_path_in_one_line(name, tmp_path, monkeypatch):
    """A hostile ``--out`` (a name too long for the system, a NUL, line breaks, controls) is refused with exit status 2 and one
    line on standard error that shows at most 200 characters of the path, its control characters escaped; nothing is written
    outside the path (clearance c3's sweep: an OSError or a ValueError of the lookup raised a traceback)."""
    monkeypatch.chdir(tmp_path)
    for path in (HOSTILE[name], "\x00" + HOSTILE[name][:100], "a\nb\x1b[2J" + HOSTILE[name][:20000]):
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = _bounded("export main(--out hostile)", lambda: export_main(["--out", path]))
        if code == 0:  # a path the system can hold (a short run of printable characters): exported, and only there
            assert Path(path).is_dir() and json.loads(out.getvalue())["instruction_pack"] == PACK.identity()
            continue
        message = err.getvalue()
        assert code == 2 and out.getvalue() == "" and message.count("\n") == 1 and message.startswith("epinoic_combinator.export: "), message[:300]
        assert len(message) < 400 and "Traceback" not in message and all(ch.isprintable() for ch in message.rstrip("\n")), message[:300]
        with pytest.raises(ExportError):
            export(Path(path))
