"""The Overseer's checks over one channel's transfers.

Every check decides by one of four means (trust rule TR1): a digest comparison, an HMAC verification, a re-run
of this repository's deterministic rules on journaled inputs, or an engine run the auditor signs itself.
Agent text is data: it is compared, hashed and parsed against allowlisted contracts, never followed.

Each check runs inside :meth:`CheckContext.guard`; an exception becomes ``OVS-AUDIT-001`` naming the check and
the transfer, so a check that could not run can never let a transfer pass.

Modules (live tier L1-L6, re-derivation R2, batch tier B1-B5):

* ``custody``   L1 / B1: CUST-001..006
* ``receipts``  L2: RCPT-001/002/003/006/007
* ``results``   L3: RES-001..006, 009, 010 (RES-007/008 come from the replayer)
* ``formal``    L4: FORM-001/002; R2: FORM-002 (branch), FORM-003/004
* ``fidelity``  L5: FID-001..008 (FID-009 with ``selfcert``)
* ``selfcert``  the independent structural self-certification detector
* ``translation`` translator oversight: TRN-001..007 (each translation of a delivered claim re-validated as untrusted IR,
  its status and eligibility re-derived, its grounding re-checked, traced to the claim and the claims it cites, checked
  for circularity, and its summary regenerated from the signed result); run with L5
* ``peer``      L6: PEER-001/002/003
* ``synthesis`` L6: SYN-001; B2: SYN-002/003, RCPT-005 (ledger)
* ``joint``     L6: JOINT-004; B3: JOINT-001/002/003
* ``divergence`` B4: DIV-001/002
* ``shadow``    B5: RCPT-004/005/008 (RES-008 when an undecided run explains a difference)
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from ...integrity.contracts import IntegrityFinding
from ..codes import ovs_finding
from ..contracts import AuditCoverage
from ..keys import KeyRing
from ..store import ResultStore
from ..view import OverseerView, Transfer

__all__ = ["CheckContext", "json_diff_paths", "normalise", "plain_form", "drop_invisible", "is_default_ignorable", "strip_list_markers", "claim_ids_for_paths",
           "Replay", "Rederived"]


@dataclass
class Replay:
    """The outcome of one fresh-engine replay of a stored result (R1)."""
    result_id: str
    replay_result_id: Optional[str]
    original_status: str
    replay_status: Optional[str]
    problem_digest_ok: bool
    config_digest_ok: bool
    versions_changed: bool
    budget_exceeded: bool
    error: Optional[str] = None


@dataclass
class Rederived:
    """R2 for one transfer: the pack checks and constraint encodings re-derived from journaled content."""
    seq: int
    expected_if_sound: dict[str, str] = field(default_factory=dict)
    findings: list[IntegrityFinding] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class CheckContext:
    view: OverseerView
    keyring: KeyRing
    store: ResultStore
    live: Any = None
    registry: Any = None
    presented: dict[str, Any] = field(default_factory=dict)
    coverage: AuditCoverage = field(default_factory=AuditCoverage)
    replays: dict[str, Replay] = field(default_factory=dict)
    rederived: dict[int, Rederived] = field(default_factory=dict)
    findings: list[tuple[int, IntegrityFinding]] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    auditor_result_ids: list[str] = field(default_factory=list)
    cited_result_ids: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    translations: list = field(default_factory=list)
    _universe: Optional[dict] = None

    # ------------------------------------------------------------------ findings
    def add(self, seq: int, finding: IntegrityFinding) -> None:
        self.findings.append((seq, finding))

    def ovs(self, seq: int, code: str, message: str, **ids) -> IntegrityFinding:
        f = ovs_finding(code, message, **ids)
        self.add(seq, f)
        return f

    def ran(self, stage: str) -> None:
        if stage not in self.checks_run:
            self.checks_run.append(stage)

    def guard(self, stage: str, name: str, fn: Callable[[], Any], *, seq: int = 0, transfer: Optional[Transfer] = None) -> Any:
        """Run one check; an internal failure is OVS-AUDIT-001 naming the check (and the transfer), never a pass."""
        self.ran(stage)
        try:
            return fn()
        except Exception as exc:
            ids = transfer.ids() if transfer is not None else {}
            self.ovs(seq if transfer is None else transfer.seq, "OVS-AUDIT-001",
                     f"audit check {name!r} failed internally ({type(exc).__name__}: {str(exc)[:300]}); its findings are missing and the transfer cannot pass", **ids)
            return None

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def auditor_run(self, fn: Callable[[], Any], *, seq: int) -> tuple[Any, list[str]]:
        """Run engine work of the auditor's own (joint checks, re-runs) UNSIGNED inside a capture, then sign every
        captured run under the auditor's run key (``overseer-run``) and store it with origin ``auditor_run``. The
        auditor never signs with an engine key (TR5), so an engine result and an auditor run can never be confused."""
        from ...engine.provenance import sign_result
        from ...engine.results import VerificationResult
        from ...engine.sink import CapturedResult, capture_results
        from ...ir.canonical import canonical_json, sha256_hex
        from ..faithful import faithful
        from ..keys import RUN_KEY_ID
        with capture_results() as cap:
            out = fn()
        ids: list[str] = []
        key = self.keyring.subkey("runs")
        for c in cap.items:
            try:
                res = faithful(VerificationResult, json.loads(c.result_json))
                signed = sign_result(res.model_copy(update={"signature": None, "signature_key_id": None}), key, RUN_KEY_ID)
                js = canonical_json(signed.model_dump(mode="json", exclude_none=True))
                self.store.put(CapturedResult(result_id=signed.result_id, key_id=RUN_KEY_ID, result_json=js, result_sha256=sha256_hex(js), problem_json=c.problem_json,
                                              problem_digest=c.problem_digest), channel_uid=self.view.channel_uid, task_id=self.view.task_id,
                               request_id=self.view.request_id, event_seq=seq, origin="auditor_run")
                ids.append(signed.result_id)
            except Exception:
                continue
        for rid in ids:
            if rid not in self.auditor_result_ids:
                self.auditor_result_ids.append(rid)
        return out, ids

    # ------------------------------------------------------------------ helpers
    def message_ids_for_reports(self, report_ids: Iterable[str]) -> list[str]:
        out = []
        for rid in report_ids:
            t = self.view.first_delivery(rid)
            if t is not None and t.message_id:
                out.append(t.message_id)
        return out

    def message_ids_for_claims(self, claim_ids: Iterable[str], *, pairs: Iterable[tuple[Optional[str], str]] = (),
                               report_ids: Optional[Iterable[str]] = None) -> tuple[list[str], list[str], list[str]]:
        """(message ids, report ids, agent ids) of the deliveries carrying the claims.

        Claim ids are unique only within a report (the parsers restart at ``g1.1``, ``h1.1`` in every report), so a
        caller that knows which report a claim belongs to says so: ``pairs`` gives ``(report_id, claim_id)`` (a pool
        entry's report, a finding's report), and ``report_ids`` restricts the claims with no known report to the
        deliveries of those reports. A claim with neither is matched in every delivered report (the legacy rule)."""
        mids, rids, aids = [], [], []
        wanted = set(claim_ids)
        known: dict[str, set[str]] = {}
        for rid_, cid in pairs:
            if rid_ and cid in wanted:
                known.setdefault(cid, set()).add(rid_)
        allowed = set(report_ids) if report_ids is not None else None
        for t in self.view.transfers:
            r = t.report
            if r is None or not t.delivered or t.kind not in ("response", "response_text", "relay_report"):
                continue
            mine = wanted & {c.claim_id for c in r.claims}
            hit = any((r.report_id in known[c]) if c in known else (allowed is None or r.report_id in allowed) for c in mine)
            if hit:
                if t.message_id and t.message_id not in mids:
                    mids.append(t.message_id)
                if r.report_id not in rids:
                    rids.append(r.report_id)
                if r.agent_id not in aids:
                    aids.append(r.agent_id)
        return mids, rids, aids


# ---------------------------------------------------------------------------------------------- JSON diff
def json_diff_paths(a: Any, b: Any, path: str = "", limit: int = 24) -> list[str]:
    """The JSON paths at which ``a`` and ``b`` differ (``claims[2].claim_text``), at most ``limit``."""
    out: list[str] = []

    def walk(x: Any, y: Any, p: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y), key=str):
                q = f"{p}.{k}" if p else str(k)
                if k not in x or k not in y:
                    out.append(q)
                elif x[k] != y[k]:
                    walk(x[k], y[k], q)
            return
        if isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                n = min(len(x), len(y))
                for i in range(n):
                    if x[i] != y[i]:
                        walk(x[i], y[i], f"{p}[{i}]")
                out.append(f"{p}[length {len(x)} -> {len(y)}]")
                return
            for i, (u, v) in enumerate(zip(x, y)):
                if u != v:
                    walk(u, v, f"{p}[{i}]")
            return
        if x != y:
            out.append(p or "$")

    walk(a, b, path)
    return out


_CLAIM_PATH_RE = re.compile(r"^claims\[(\d+)\]")


def claim_ids_for_paths(payload: Optional[dict], paths: Iterable[str], other: Optional[dict] = None) -> list[str]:
    """Claim ids touched by diff paths (``claims[i]...``), read from the journaled payload; a claim present in only one
    of the two payloads is named too."""
    out: list[str] = []
    claims = (payload or {}).get("claims") or []
    for p in paths:
        m = _CLAIM_PATH_RE.match(p)
        if m and int(m.group(1)) < len(claims) and isinstance(claims[int(m.group(1))], dict):
            cid = claims[int(m.group(1))].get("claim_id")
            if isinstance(cid, str) and cid not in out:
                out.append(cid)
    if other is not None:
        mine = {c.get("claim_id") for c in claims if isinstance(c, dict)}
        theirs = {c.get("claim_id") for c in ((other or {}).get("claims") or []) if isinstance(c, dict)}
        for cid in sorted(x for x in mine ^ theirs if isinstance(x, str)):
            if cid not in out:
                out.append(cid)
    return out


# ---------------------------------------------------------------------------------------------- normalisation
#: Fidelity normalisation (fixed and documented; any extension is a named rule with its own test):
#: invisible characters removed (named rule ``invisible``: category Cf and every default-ignorable code point, such as a
#: zero-width no-break space U+FEFF inside a text); NFKC; typographic quotes, apostrophes and dashes folded; markdown
#: emphasis and code markers, heading hashes and list bullets removed; whitespace runs collapsed. No case folding and no similarity threshold. Named rule
#: ``joined-list-markers``: list markers are removed on both sides alike, at the start of a line AND where an adapter's
#: line join left them after sentence or colon punctuation (a bullet ``- `` after ``.``, ``:``, ``;``, ``!`` or ``?``; a
#: list number ``2.`` or ``2)`` after ``.``, ``!`` or ``?``, also at the very end of a text).
_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "´": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})
_HEADING_RE = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")
_BULLET_RE = re.compile(r"(?m)^[ \t]*(?:[-*+•]|\d{1,3}[.)])[ \t]+")
#: Emphasis and code markers: every ``*``, ``_`` and backtick (removed on both sides of a comparison alike).
_EMPHASIS_RE = re.compile(r"[*_`]+")
_WS_RE = re.compile(r"\s+")
#: joined-list-markers: a bullet after sentence or colon punctuation, a list number after sentence punctuation.
_JOINED_NUMBER_RE = re.compile(r"(?<=[.!?]) \d{1,3}[.)](?= |$)")
_JOINED_DASH_RE = re.compile(r"(?<=[.:;!?]) [-+•](?= )")


#: The Unicode Default_Ignorable_Code_Point ranges (DerivedCoreProperties), assigned or not. Invisible: removed on both
#: sides of every comparison (with category Cf), so a zero-width no-break space (U+FEFF) left where two chunks of an
#: answer were joined never makes a claim "absent" from its own response.
_IGNORABLE_RANGES = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F),
                     (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
                     (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))


def is_default_ignorable(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in _IGNORABLE_RANGES)


def drop_invisible(text: str) -> str:
    """``text`` without format characters (category Cf) and default-ignorable code points (named rule ``invisible``)."""
    if text.isascii():
        return text
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf" and not is_default_ignorable(ch))


def plain_form(text: str) -> str:
    """The context-free comparison form (named rule ``context-free``): invisible characters removed, NFKC, quotes and
    dashes folded, emphasis markers removed, whitespace collapsed; NO list-marker or heading stripping, so a claim that
    occurs verbatim in its response always occurs in this form, whatever markdown structure surrounds it."""
    t = unicodedata.normalize("NFKC", drop_invisible(text or ""))
    t = t.translate(_FOLD)
    t = _EMPHASIS_RE.sub("", t)
    return _WS_RE.sub(" ", t).strip()


def strip_list_markers(text: str) -> str:
    """Rule ``joined-list-markers`` on raw text (for figures): list numbers and bullets at the start of a line, or left
    by a line join after sentence punctuation (bullets also after a colon), removed; everything else unchanged."""
    t = _BULLET_RE.sub("", text or "")
    t = _JOINED_NUMBER_RE.sub("", _WS_RE.sub(" ", t))
    return _JOINED_DASH_RE.sub("", t)


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", drop_invisible(text or ""))
    t = _HEADING_RE.sub("", t)
    t = _BULLET_RE.sub("", t)
    t = t.translate(_FOLD)
    t = _EMPHASIS_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip()
    t = _JOINED_NUMBER_RE.sub("", t)
    t = _JOINED_DASH_RE.sub("", t)
    return _WS_RE.sub(" ", t).strip()


def load_json(text: Optional[str]) -> Any:
    return json.loads(text) if text else None
