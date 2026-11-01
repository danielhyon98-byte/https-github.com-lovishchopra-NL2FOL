#!/usr/bin/env python3
"""Print the claim records the infrastructure extracts from a specialist output file,
so a dummy combinator can cite them and a translation provider can formalize them.
Usage: list_claims.py <specialist.json> [--eligible] [--json] [--instructions <dir> [--allow-other-release]]
       list_claims.py --agent-view <specialist.json> <specialist.json> ... [--instructions <dir> [--allow-other-release]]
(each <specialist.json> a file of <round>/specialists/, read with the other files of its group there)

With ``--agent-view`` it prints, for the two to sixteen reports of one group, the one JSON document the combinator's
runner gives its agent (``{"request": ..., "sources": [...]}``, what the pack's INSTRUCTIONS.md calls "What you
receive"): the combinator input the service builds from the delivered reports, rendered by the combinator sub-project's
own code in its own isolated process. A single report is no combinator input (the runner combines two reports or more);
scripts/arena/README.md says how its ``--json`` listing maps onto that document.

Every listing prints the claim ids the hub delivers. The reports of one group (one hub task) are delivered in
run_arena.py's order (``run_arena.load_items``: name order, a peer-dependent task after the task it depends on), and the
hub parses a report whose claim ids a report of ANOTHER agent delivered before it already holds with its ids qualified by
its agent (``channel.bus.needs_qualified_ids``: the STEM parsers, ``s1.2@physics-specialist`` for the second Physics or
Chemistry report of a group, and since integration gate 3 the History and English parsers, ``p1-point@english-a-lang-lit-specialist``
for an English A: Language and Literature report after an English A: Literature one). So a file is parsed after every member of its group delivered before it, given on the
command line or not, each taken as delivered, with the subject, task type and request text the group's plan
(``run_arena.group_plan``) gives its agent, as the hub parses it. Integration gate, round 2: the single-file listing
parsed a file alone and printed 's1.2' for that report, so a translation fixture or a combinator citation written from it
named an id the hub never delivered (the fixture was never served; the citation named the other agent's claim). With
``--json`` the listing also says the file's ``group``, the files of the group delivered before it (``delivered_after``)
and whether its ids are qualified (``ids_qualified``); ``--agent-view`` renders the reports in the order given, each
with the ids the hub delivers it under.

A peer-dependent task (``peer_of``) is listed with the peer's report supplied as the document
``peer:<task>`` when <round>/relayed/<task_id>.json exists, as the hub supplies it. Every source
reference says whether its excerpt was LOCATED in the named document. An excerpt no text holds is
attributed to the text the sentence names (so the hub reports a wrong credit, INT-REQ-003) and
otherwise carries no source reference: the parser records an assumption and the core pack reports
it as unverifiable (CORE-SRC-003). Each claim's ``assumptions`` are printed under its row (the History
parser records inline from-memory labels and single-quoted spans with no text to check them
against there) and a claim that is an agent self-report shows its ``advisory_verification_status``
(recorded for audit, never trusted). With ``--json`` every claim also carries ``claim_text_sha256``,
the digest a translation fixture file may record so run_arena.py refuses the fixture once the
claim's text changes.

The combinator's instructions are the combinator sub-project's (``combinator/``, package
``epinoic_combinator``): both outputs end with the synthesis format the combinator writes (``synthesis_format``
in the JSON), read from its exported instruction pack, the one ``python -m epinoic_combinator.export --out
<dir>`` writes (``--instructions <dir>``; without it the sub-project of this repository exports it in its own
process, so this script never imports it). The pack is checked against its manifest, and its transformation
values, what each records and the certainty words against the synthesis contract itself
(``integrity.contracts.TRANSFORMATION_MEANINGS``), so they can never drift from what the hub accepts: a pack
that names other values is refused (exit status 2). While the combinator sub-project is in this repository, a given
export must also be the instruction pack of this repository's release (its name, version and digest, read from an
export the sub-project writes in its own isolated process): a rewritten ``INSTRUCTIONS.md`` with a recomputed
manifest is refused (exit status 2) unless ``--allow-other-release`` explicitly allows another release's
instructions (said on standard error). Without the sub-project here, only the manifest and the format file are
checked. A transformation is one of those words, never a description of the edit: the hub refuses any other value
(INT-REQ-009 with INT-SYNTH-014) and the synthesis is not delivered. Brief a combinator agent with the pack's
``INSTRUCTIONS.md`` and this script's ``--json`` output for each report (scripts/arena/README.md, "Synthesis
format")."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

from epinoic_logic.adapters.sources import check_excerpt
from epinoic_logic.branches import default_registry
from epinoic_logic.channel.bus import ids_held_by_other_agents, needs_qualified_ids
from epinoic_logic.integrity.contracts import CERTAINTY_RANK, SYNTHESIZED_CLAIM_TRANSFORMATIONS, TRANSFORMATION_MEANINGS
from epinoic_logic.translate.contracts import SuppliedText, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.subjects import resolve_profile

sys.path.insert(0, str(Path(__file__).resolve().parent))
# run_arena.py, beside this script: the order its genuine pass delivers a round's reports in, and each group's plan
from run_arena import group_of, group_plan, load_items  # noqa: E402

#: The combinator sub-project of this repository, whose exporter writes the combinator agent's instructions.
COMBINATOR_SRC = Path(__file__).resolve().parents[2] / "combinator" / "src"
PACK_FILES = ("INSTRUCTIONS.md", "output-format.json")
_EXPORT = "import sys; sys.path.insert(0, sys.argv[1]); from epinoic_combinator.export import main; sys.exit(main(['--out', sys.argv[2]]))"


def _refuse(message: str) -> None:
    print(f"list_claims.py: {message}", file=sys.stderr)
    sys.exit(2)


def _isolated_export(tmp: str) -> Path:
    """The instruction pack of this repository's combinator release, exported now by the sub-project's own exporter in
    its own isolated process (``python -I``: this script never imports the sub-project)."""
    proc = subprocess.run([sys.executable, "-I", "-c", _EXPORT, str(COMBINATOR_SRC), tmp], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        _refuse("the combinator's exporter failed: " + (proc.stderr.strip().splitlines() or ["no message"])[-1][:200])
    return Path(tmp)


def _read_export(directory: Path) -> tuple[dict, dict[str, bytes]]:
    try:
        manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
        files = {name: (directory / name).read_bytes() for name in PACK_FILES}
    except (OSError, ValueError) as exc:
        _refuse(f"{directory} holds no exported combinator pack ({type(exc).__name__})")
    if not isinstance(manifest, dict):
        _refuse(f"{directory} holds no exported combinator pack (its manifest is not an object)")
    return manifest, files


def _shown(pack: dict) -> str:
    return f"{pack.get('name')} {pack.get('version')} sha256={str(pack.get('sha256'))[:16]}..."


def combinator_pack(instructions: Path | None, *, allow_other_release: bool = False) -> tuple[dict, dict]:
    """The manifest and the output format of the combinator agent's exported instructions: the export in
    ``instructions``, else one the sub-project of this repository writes now in its own isolated process. Refused when
    the files are not the manifest's, the pack's digest is not theirs, or the format names other closed values than
    the hub's synthesis contract; and, while the combinator sub-project is in this repository, when a given export is
    not the instruction pack of this repository's release (its identity, from an isolated export of the sub-project),
    unless ``allow_other_release`` (``--allow-other-release``) explicitly allows another release's instructions. Without
    the sub-project here, a given export is checked against its manifest and its format file against the contract only."""
    from epinoic_logic.integration.canonical import sha256_json
    here = (COMBINATOR_SRC / "epinoic_combinator").is_dir()
    release: dict | None = None
    with tempfile.TemporaryDirectory(prefix="combinator-pack-") as tmp:
        if instructions is None:
            if not here:
                _refuse("no combinator sub-project in this repository: pass --instructions <dir>, an export of epinoic_combinator")
            manifest, files = _read_export(_isolated_export(tmp))
        else:
            manifest, files = _read_export(instructions)
            if here:
                release = _read_export(_isolated_export(tmp))[0].get("instruction_pack") or {}
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    pack = manifest.get("instruction_pack") or {}
    if manifest.get("files") != digests or pack.get("sha256") != sha256_json({"name": pack.get("name"), "version": pack.get("version"), "files": digests}):
        _refuse("the exported combinator pack does not match its manifest: export it again")
    fmt = json.loads(files["output-format.json"].decode("utf-8"))
    contract = {v: TRANSFORMATION_MEANINGS[v] for v in SYNTHESIZED_CLAIM_TRANSFORMATIONS}
    if list(fmt.get("transformation") or {}) != list(contract) or fmt["transformation"] != contract \
            or fmt.get("certainty") != sorted(CERTAINTY_RANK, key=CERTAINTY_RANK.get, reverse=True):
        _refuse("the combinator's exported instructions name other transformation or certainty values than the hub's synthesis contract")
    if release is not None and {k: pack.get(k) for k in ("name", "version", "sha256")} != {k: release.get(k) for k in ("name", "version", "sha256")}:
        if not allow_other_release:
            _refuse(f"the exported pack {_shown(pack)} is not the instruction pack of this repository's combinator release ({_shown(release)}): "
                    "export it again with python -m epinoic_combinator.export --out <dir>, or pass --allow-other-release to brief the agents with "
                    "another release's instructions")
        print(f"list_claims.py: the exported pack {_shown(pack)} is another release's than this repository's ({_shown(release)}); "
              "allowed by --allow-other-release", file=sys.stderr)
    elif instructions is not None and not here:
        print("list_claims.py: no combinator sub-project in this repository: the export is checked against its manifest and its output format "
              "against the synthesis contract only", file=sys.stderr)
    return manifest, fmt


def synthesis_format(manifest: dict, fmt: dict) -> dict:
    """What the combinator writes to <round>/syntheses/<task_id>.json for this report (scripts/arena/README.md, "Synthesis
    format"): the exported pack's output format, under its identity."""
    return {"file": "<round>/syntheses/<task_id>.json", "shape": fmt["output"], "claim": fmt["claim"], "transformation": fmt["transformation"],
            "certainty": fmt["certainty"], "rules": fmt["rules"], "instruction_pack": manifest["instruction_pack"], "combinator": manifest["combinator"],
            "instructions": "INSTRUCTIONS.md of the exported pack (python -m epinoic_combinator.export --out <dir>)"}


class Parsed(NamedTuple):
    """A specialist output file parsed as the hub parses it on its delivery (``specialist_report``)."""
    item: dict
    branch: object
    profile: object
    texts: list
    group: str
    report: object
    #: whether the hub's rule (``channel.bus.needs_qualified_ids``) gave the report agent-qualified claim ids
    qualified: bool = False
    #: the file names of the group's reports delivered before it on its hub task (``delivered_reports``)
    earlier: tuple = ()


def specialist_report(spec_path: Path, held: frozenset = frozenset(), plan=None) -> Parsed:
    """A specialist output file parsed as run_arena.py's genuine pass has the hub parse it: a peer-dependent task with the
    peer's relayed report supplied as ``peer:<task>``; the subject and task type ``plan`` (the group's WorkPlan,
    ``run_arena.group_plan``) gives the file's agent, else the file's own; the request text for a parser that reads it
    (``accepts_request_text``: a STEM parser reads the request's bindings and targets into the claims' assumptions).
    ``held`` are the claim ids the reports of OTHER agents delivered before it on the task hold: the hub's rule
    (``channel.bus.needs_qualified_ids``) then parses a report whose ids collide with them with agent-qualified ids, so
    the group's reports share no claim id. ``delivered_reports`` gives each file the ``held`` and ``plan`` of its
    delivery."""
    item = json.loads(spec_path.read_text())
    if item.get("peer_of"):
        relayed = spec_path.parent.parent / "relayed" / f"{item['task_id']}.json"
        if relayed.exists():
            rel = json.loads(relayed.read_text())
            if rel.get("delivered") and rel.get("payload"):
                item["supplied_texts"] = [*item.get("supplied_texts", []), {"document_id": rel.get("document_id", f"peer:{item['peer_of']}"), "title": "peer report relayed through the hub", "author": rel["payload"].get("agent_id"), "text": rel["payload"]["original_response"]}]
    agent = item["agent_id"]
    subject = plan.agent_subjects.get(agent, plan.subject) if plan is not None else item["subject"]
    task_type = plan.agent_task_types.get(agent, plan.task_type) if plan is not None else item.get("task_type", "analytical_paragraph")
    branch, profile = default_registry().for_subject(subject)
    texts = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]
    group = item.get("group") or spec_path.stem  # tasks of one group share one hub task and request, as in run_arena.py
    parser = branch.parser()
    args = dict(request_id=f"req-{group}", task_id=group, report_id=f"rep-{item['task_id']}-0", subject=subject,
                task_type=task_type, supplied_texts=texts, agent_id=agent)
    if getattr(parser, "accepts_request_text", False) is True and isinstance(item.get("question"), str):
        args["request_text"] = item["question"]  # the request the router dispatches is the task's question
    report = parser.parse_response(item["response_text"], **args)
    qualified = needs_qualified_ids(parser, report, set(held))
    if qualified:
        report = parser.parse_response(item["response_text"], **args, qualify_ids=True)
    return Parsed(item, branch, profile, texts, group, report, qualified)


def delivered_reports(spec_paths: list[Path]) -> list[Parsed]:
    """Each file of ``spec_paths`` (resolved paths), in the order given, parsed with the claim ids the hub delivers it
    under in run_arena.py's genuine pass: the reports of its group (one hub task) are delivered in run_arena's order
    (``run_arena.load_items`` over the file's directory: name order, a peer-dependent task after the task it depends
    on), each with the plan of its group, and a report whose ids a report of ANOTHER agent delivered before it holds is
    parsed with agent-qualified ids (``channel.bus.needs_qualified_ids``). Every member delivered before a given file
    counts, given or not, and is taken as delivered, as a genuine report is (the hub holds no id of a report it rejects;
    run_arena.py serves a recorded translation under either form of a STEM claim id, so a fixture still reaches its
    claim). A file that is no specialist file of its directory is refused (exit status 2)."""
    rounds: dict[Path, list[dict]] = {}
    parsed: dict[Path, Parsed] = {}
    for spec in spec_paths:
        if spec in parsed:
            continue
        directory = spec.parent
        if directory not in rounds:
            try:
                rounds[directory] = load_items(directory)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                _refuse(f"the specialist files in {directory} cannot be read as run_arena.py reads a round ({type(exc).__name__}: {str(exc)[:200]}); "
                        "a report is listed with the ids the hub delivers after the reports of its group")
        items = rounds[directory]
        me = next((it for it in items if it["_path"].resolve() == spec), None)
        if me is None:
            _refuse(f"{spec.name} is not a specialist file of {directory} (its *.json files), so its group's delivery order is unknown")
        group = group_of(me)
        try:
            plan = group_plan(items, group)
        except (ValueError, TypeError, KeyError) as exc:  # pydantic's ValidationError is a ValueError
            _refuse(f"the plan of group {group} cannot be built as run_arena.py builds it ({type(exc).__name__}: {str(exc).splitlines()[0][:200]}), "
                    "so run_arena.py cannot deliver its reports either")
        before: list[tuple[str, Parsed]] = []  # (file name, parse) of the members delivered so far, in delivery order
        for it in (x for x in items if group_of(x) == group):
            path = it["_path"].resolve()
            if path not in parsed:
                held = frozenset(ids_held_by_other_agents([p.report for _name, p in before], it["agent_id"]))
                parsed[path] = specialist_report(path, held, plan)._replace(earlier=tuple(name for name, _p in before))
            before.append((path.name, parsed[path]))
            if path == spec:
                break
    return [parsed[spec] for spec in spec_paths]


#: The combinator's own rendering of what its agent reads (``epinoic_combinator.prompt.render`` of a checked input), run in
#: the sub-project's own isolated process: this script never imports the sub-project.
_AGENT_VIEW = ("import sys; sys.path.insert(0, sys.argv[1]); from epinoic_combinator.contract import load_contract; "
               "from epinoic_combinator.prompt import render; inp, p = load_contract().check_input(sys.stdin.buffer.read()); "
               "sys.stdout.buffer.write(render(inp).encode('utf-8') + b'\\n') if p is None else "
               "(sys.stderr.write(p.code + ' ' + p.reason + ': ' + p.detail + '\\n'), sys.exit(2))")


def agent_view(spec_paths: list[Path], manifest: dict) -> str:
    """The document the combinator's runner gives its agent for the reports of one group (``--agent-view``): the
    combinator input the service builds from the delivered reports (``integration.combinator_port.source_report`` and
    ``build_input``, under the exported pack's identity), rendered by the combinator sub-project's own code. The runner
    combines two to sixteen reports of one request, so fewer, more, or files of different groups are refused (exit 2)."""
    from epinoic_logic.integration import combinator_port as CB
    from epinoic_logic.integration.canonical import canonical_json
    from epinoic_logic.integration.errors import IntegrationError
    from epinoic_logic.integration.protocol import dump
    if not (COMBINATOR_SRC / "epinoic_combinator").is_dir():
        _refuse("no combinator sub-project in this repository: the agent's view is rendered by the combinator's own code")
    # in the order given, each with the ids the hub delivers it under: its group's reports are delivered in run_arena.py's
    # order, and a report whose ids another agent's earlier report holds is qualified (delivered_reports)
    parsed = delivered_reports(spec_paths)
    groups = sorted({p.group for p in parsed})
    if len(groups) != 1:
        _refuse(f"--agent-view takes the reports of one group (one request); these belong to {groups}")
    if not 2 <= len(parsed) <= 16:
        _refuse(f"the combinator's runner combines two to sixteen reports of one request (the port's combined answer); {len(parsed)} given: brief the "
                "agent with this script's --json listing, mapped onto the runner's input as scripts/arena/README.md says")
    sources = [CB.source_report(p.report.model_dump(mode="json"), p.branch.key) for p in parsed]
    try:
        inp = CB.build_input({"task_id": groups[0], "request_id": f"req-{groups[0]}"}, sources, manifest["instruction_pack"])
    except IntegrationError as exc:
        _refuse(f"the reports make no combinator input ({exc.code}: {exc})")
    proc = subprocess.run([sys.executable, "-I", "-c", _AGENT_VIEW, str(COMBINATOR_SRC)], input=canonical_json(dump(inp)).encode("utf-8"), capture_output=True, timeout=120)
    if proc.returncode != 0:
        _refuse("the combinator refused the input: " + (proc.stderr.decode("utf-8", "replace").strip().splitlines() or ["no message"])[-1][:300])
    return proc.stdout.decode("utf-8")


_flags = {"--eligible", "--json", "--allow-other-release", "--agent-view"}
_instructions = sys.argv[sys.argv.index("--instructions") + 1] if "--instructions" in sys.argv[:-1] else None
_positional = [a for k, a in enumerate(sys.argv[1:], start=1) if a not in _flags and a != "--instructions" and sys.argv[k - 1] != "--instructions"]
_manifest, _fmt = combinator_pack(Path(_instructions).resolve() if _instructions else None, allow_other_release="--allow-other-release" in sys.argv)
if "--agent-view" in sys.argv:
    sys.stdout.write(agent_view([Path(p).resolve() for p in _positional], _manifest))
    sys.exit(0)
spec_path = Path(_positional[0] if _positional else sys.argv[1]).resolve()
only_eligible = "--eligible" in sys.argv
as_json = "--json" in sys.argv
SYNTHESIS_FORMAT = synthesis_format(_manifest, _fmt)
# the ids the hub delivers: the file is parsed after the members of its group run_arena.py delivers before it
item, branch, profile, texts, group, report, qualified, earlier = delivered_reports([spec_path])[0]
rows = []
for c in report.claims:
    e = decide_eligibility(c)
    eligible = e.eligible and profile.allows(e.eligibility_class)
    if only_eligible and not eligible:
        continue
    docs = {t.document_id: t for t in texts}
    refs = [{**r.model_dump(exclude_none=True), "located": bool(r.excerpt) and r.document_id in docs and check_excerpt(r.excerpt, r.document_id, docs).located} for r in c.source_refs]
    rows.append({"claim_id": c.claim_id, "role": c.claim_role, "materiality": c.materiality, "certainty": c.certainty, "eligible": eligible, "eligibility_class": e.eligibility_class.value,
                 "supporting_claim_ids": c.supporting_claim_ids, "source_refs": refs, "assumptions": list(c.assumptions), "advisory_verification_status": c.advisory_verification_status,
                 "claim_text_sha256": sha256_text(c.claim_text), "text": c.claim_text})
if as_json:
    print(json.dumps({"report_id": report.report_id, "request_id": report.request_id, "branch": branch.key, "group": group, "delivered_after": list(earlier),
                      "ids_qualified": qualified, "claims": rows, "synthesis_format": SYNTHESIS_FORMAT}, indent=2, ensure_ascii=False))
else:
    print(f"report_id={report.report_id} request_id={report.request_id} branch={branch.key} claims={len(report.claims)}")
    if earlier:
        print(f"group {group}: delivered after {', '.join(earlier)} (run_arena.py's delivery order); "
              + ("its claim ids are qualified with its agent, as the hub delivers them: a report of another agent delivered before it holds "
                 "the same ids (channel.bus.needs_qualified_ids)" if qualified else "no claim id of it is held by another agent's report delivered before it"))
    for r in rows:
        unlocated = [x["document_id"] for x in r["source_refs"] if not x["located"]]
        self_report = f" SELF-REPORT={r['advisory_verification_status']}" if r["advisory_verification_status"] else ""
        print(f"{r['claim_id']:8} {r['role']:16} {r['materiality']:11} {'ELIGIBLE' if r['eligible'] else '-':9} {r['eligibility_class']:28} supports={r['supporting_claim_ids']}{' UNLOCATED-EXCERPT' if unlocated else ''}{self_report} :: {r['text'][:140]}")
        for a in r["assumptions"]:
            print(f"{'':8} assumption: {a[:220]}")
    pack = SYNTHESIS_FORMAT["instruction_pack"]
    print(f"combinator instructions: pack {pack['name']} {pack['version']} sha256={pack['sha256']} "
          f"({SYNTHESIS_FORMAT['combinator']['name']} {SYNTHESIS_FORMAT['combinator']['version']}; python -m epinoic_combinator.export --out <dir>)")
    print(f"synthesis transformation (exactly one of): {', '.join(SYNTHESIS_FORMAT['transformation'])}; certainty: {', '.join(SYNTHESIS_FORMAT['certainty'])} "
          "(never stronger than the weakest source); any other transformation value is refused by the hub (INT-SYNTH-014)")
