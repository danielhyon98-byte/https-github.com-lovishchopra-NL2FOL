#!/usr/bin/env python3
"""Record with each translation fixture of a round the digest of the claim text it was produced for.

Usage: python bind_translations.py <round> --listings <dir> [--force]
       python bind_translations.py <round> --current-parse [--force]

A translation fixture (``<round>/translations/<task>.json``, ``claims``: {claim id: the translation agent's output}) is
produced for one claim text: the text the listing the translation agent was briefed with (``list_claims.py <specialist
file> --json``) printed under that claim id, with its digest (``claim_text_sha256``). run_arena.py binds a fixture to
that text only when the translations file records the digest (``claim_text_sha256``: {claim id: sha256 of the claim
text}): the fixture provider then refuses it for any other text (STALE_FIXTURE_REFUSED), and the channel refuses an
outcome bound to another text (INT-STALE-011). Without the digest a replay can bind the fixture only to whatever text its
claim id carries in that run (``served_by_claim_id_only``), and the run is qualified FIXTURES_UNBOUND. Round 8's
translation-fidelity lens: all 469 of the round's translations were recorded without digests, so every one was matched by
claim id only. This tool writes the map, as the recording step of a round:

- ``--listings <dir>``: from the listings the translation agent was given, ``<dir>/<task file stem>.json``, each the
  ``--json`` output of list_claims.py for that specialists file. They are the record of the texts the translations were
  produced for: use them whenever they were kept.
- ``--current-parse``: from the listing list_claims.py prints now for each specialists file (the claim ids and texts the
  hub delivers, in run_arena.py's delivery order). This is right only when run as the recording step, before any change
  to the code: a later parse may carry another text under the same claim id, and the fixture would then be bound to a
  text it was never produced for. Choosing it is therefore explicit.

A fixture keyed by the other form of a claim id the hub may qualify ('s1.2' for 's1.2@physics-specialist', and the
reverse: ``run_arena.other_id_form``) takes the digest of the claim listed under that form, which is the claim
run_arena.py serves it to. A fixture whose claim id the listing does not hold in either form is left unbound and named
(a replay counts it as matching no delivered claim). A digest already recorded is kept; one that differs from the
listing's is a conflict: nothing is written and the exit status is 2, unless ``--force`` replaces the recorded digests
with the listing's. A listing of another report than the translations file's (its ``report_id``) is the wrong listing:
nothing is written and the exit status is 2, ``--force`` or not. Only the ``claim_text_sha256`` map
of a translations file changes; the fixtures themselves are left as recorded, so the digest of each fixture
(``run_arena.fixture_sha256``, by which an adjudication names what it judged) does not move.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import load_items, other_id_form, qualification_tag  # noqa: E402

#: The listing script whose ``--json`` output briefs the translation agent (beside this one).
LIST_CLAIMS = Path(__file__).resolve().parent / "list_claims.py"


class BindingError(Exception):
    """A listing that cannot be read or produced: nothing is written."""


def listing_digests(listing: dict) -> dict[str, str]:
    """claim id -> ``claim_text_sha256`` of every claim of a ``list_claims.py --json`` listing."""
    out: dict[str, str] = {}
    claims = listing.get("claims") if isinstance(listing, dict) else None
    for c in claims if isinstance(claims, list) else []:
        if isinstance(c, dict) and isinstance(c.get("claim_id"), str) and isinstance(c.get("claim_text_sha256"), str) and len(c["claim_text_sha256"]) == 64:
            out[c["claim_id"]] = c["claim_text_sha256"]
    return out


def current_listing(spec: Path) -> dict:
    """The ``list_claims.py --json`` listing of the specialists file ``spec``, printed now by the script itself (in its own
    process, as the translation agent's briefing runs it)."""
    proc = subprocess.run([sys.executable, str(LIST_CLAIMS), str(spec), "--json"], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise BindingError(f"list_claims.py refused {spec.name}: " + ((proc.stderr or "").strip().splitlines() or ["no message"])[-1][:300])
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise BindingError(f"list_claims.py printed no JSON listing for {spec.name} ({exc})") from None


def read_listings(round_dir: Path, listings_dir: Path | None) -> tuple[dict[str, dict], str]:
    """Every translations file's listing by file stem, and where the listings came from. With ``listings_dir`` the
    saved listing ``<dir>/<stem>.json`` (a file without one has no listing); without it, the listing list_claims.py prints
    now for ``<round>/specialists/<stem>.json``."""
    stems = [p.stem for p in sorted((round_dir / "translations").glob("*.json"))]
    out: dict[str, dict] = {}
    if listings_dir is not None:
        for stem in stems:
            path = listings_dir / f"{stem}.json"
            if path.exists():
                try:
                    listing = json.loads(path.read_text(encoding="utf-8"))
                except ValueError as exc:
                    raise BindingError(f"{path.name} is not a JSON listing ({exc})") from None
                if not isinstance(listing, dict) or not isinstance(listing.get("claims"), list):
                    raise BindingError(f"{path.name} is not a list_claims.py --json listing (an object with a claims list)")
                out[stem] = listing
        return out, f"the saved listings in {listings_dir.name}/"
    for stem in stems:
        spec = round_dir / "specialists" / f"{stem}.json"
        if spec.exists():
            out[stem] = current_listing(spec.resolve())
    return out, "the listings list_claims.py prints now (current parse)"


def bind(round_dir: Path, listings: dict[str, dict], *, force: bool = False) -> dict:
    """What binding ``round_dir``'s translations to ``listings`` (file stem -> a ``list_claims.py --json`` listing) does,
    per translations file: the new ``claim_text_sha256`` map (``maps``), the fixtures newly bound (``bound``), those
    already bound to the listing's digest (``kept``), those the listing does not hold (``unbound``) and every conflict: a
    recorded digest that differs from the listing's (``conflicts``; with ``force`` it is replaced by the listing's), or a
    listing of another report than the translations file's (``refused``: never bound, ``force`` or not). Nothing is
    written."""
    items = {it["_path"].stem: it for it in load_items(round_dir / "specialists")} if (round_dir / "specialists").is_dir() else {}
    out: dict = {"files": {}, "maps": {}, "conflicts": [], "refused": []}
    for p in sorted((round_dir / "translations").glob("*.json")):
        stem = p.stem
        tr = json.loads(p.read_text(encoding="utf-8"))
        fixtures = tr.get("claims") or {}
        recorded = dict(tr.get("claim_text_sha256") or {})
        entry = {"recorded": len(fixtures), "bound": [], "kept": [], "unbound": [], "conflicts": []}
        listing = listings.get(stem)
        if listing is None:
            entry["unbound"] = sorted(fixtures)
            entry["why_unbound"] = "no listing for this file"
            out["files"][p.name] = entry
            continue
        if tr.get("report_id") and listing.get("report_id") and tr["report_id"] != listing["report_id"]:
            entry["unbound"] = sorted(fixtures)
            entry["why_unbound"] = f"the listing is of report {listing['report_id']}, the translations of {tr['report_id']}"
            out["refused"].append(f"{p.name}: {entry['why_unbound']}")
            out["files"][p.name] = entry
            continue
        digests = listing_digests(listing)
        tag = qualification_tag(items[stem]) if stem in items else None
        new = dict(recorded)
        for cid in fixtures:
            digest = digests.get(cid)
            if digest is None:
                other = other_id_form(cid, tag)
                digest = digests.get(other) if other is not None else None
            if digest is None:
                entry["unbound"].append(cid)
                continue
            if cid not in recorded:
                new[cid] = digest
                entry["bound"].append(cid)
            elif recorded[cid] == digest:
                entry["kept"].append(cid)
            else:
                entry["conflicts"].append(f"{cid}: recorded {recorded[cid][:12]}..., listed {digest[:12]}...")
                out["conflicts"].append(f"{p.name} {entry['conflicts'][-1]}")
                if force:
                    new[cid] = digest
        out["files"][p.name] = entry
        if new != recorded:
            out["maps"][p.name] = new
    return out


def write(round_dir: Path, maps: dict[str, dict]) -> None:
    """Write each translations file's new ``claim_text_sha256`` map; every other field is kept as recorded."""
    for name, digests in maps.items():
        path = round_dir / "translations" / name
        tr = json.loads(path.read_text(encoding="utf-8"))
        tr["claim_text_sha256"] = {cid: digests[cid] for cid in sorted(digests)}
        path.write_text(json.dumps(tr, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record with each translation fixture of a round the digest of the claim text it was produced for.")
    ap.add_argument("round_dir", type=Path)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--listings", type=Path, help="the directory of the list_claims.py --json listings the translation agent was given (<stem>.json)")
    source.add_argument("--current-parse", action="store_true",
                        help="the listings list_claims.py prints now: right only as the recording step, before any change to the code")
    ap.add_argument("--force", action="store_true", help="replace a recorded digest that differs from the listing's")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    if not (rd / "translations").is_dir():
        print(f"{rd} has no translations/ directory: nothing to bind")
        return 2
    if args.listings is not None and not args.listings.is_dir():
        print(f"{args.listings} is not a directory of listings")
        return 2
    try:
        listings, where = read_listings(rd, args.listings.resolve() if args.listings is not None else None)
    except BindingError as exc:
        print(f"nothing written: {exc}")
        return 2
    result = bind(rd, listings, force=args.force)
    for name, e in result["files"].items():
        print(f"{name}: {len(e['bound'])} bound, {len(e['kept'])} already bound, {len(e['unbound'])} not in the listing"
              + (f" ({e['why_unbound']})" if e.get("why_unbound") else "") + (f": {e['unbound']}" if e["unbound"] and not e.get("why_unbound") else "")
              + (f"; conflicts: {e['conflicts']}" if e["conflicts"] else ""))
    if result["refused"]:
        print(f"nothing written: {len(result['refused'])} listing(s) of another report than their translations file's: {result['refused']}")
        return 2
    if result["conflicts"] and not args.force:
        print(f"nothing written: {len(result['conflicts'])} recorded digest(s) differ from the listing's (pass --force to replace them)")
        return 2
    write(rd, result["maps"])
    bound = sum(len(e["bound"]) for e in result["files"].values())
    print(f"claim-text digests from {where}: {bound} fixture(s) newly bound in {len(result['maps'])} translations file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
