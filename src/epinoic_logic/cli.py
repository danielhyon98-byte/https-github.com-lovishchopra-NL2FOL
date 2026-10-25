"""Command-line interface (``epinoic-logic``).

Commands
--------
``verify <problem.json> [--timeout-ms N] [--rlimit N] [--policy NAME] [--signing-key-file PATH | --signing-key-env [VAR] | --signing-key-hex HEX] [--key-id ID]``
    Verify one IR problem file and print the ``VerificationResult`` as JSON. The file
    is passed to the engine as untrusted bytes, so a malformed file yields a bound
    ``INVALID_FORMALIZATION`` result rather than a crash. ``--policy`` names the engine
    policy (``linear`` by default, ``nonlinear`` or ``joint``; ``engine.policies.named_policy``),
    exactly as ``POST /v1/verify`` takes it: never raw limits. Exit code 0 whenever a
    result was produced (the verdict is in ``status``), 2 on usage or I/O errors (an
    unknown policy name included).

Signing keys (``verify`` and ``check-report``) are hex text of at least
:data:`MIN_SIGNING_KEY_BYTES` bytes, the service's own floor: a shorter key is a usage error,
never a signature. Give the key in a file (``--signing-key-file``, the hex text on its first
line) or in an environment variable (``--signing-key-env``, by default ``EPINOIC_SIGNING_KEY``,
the service's variable). ``--signing-key-hex`` puts the key on the command line, where other
users of the machine can read it in the process list; it is kept for compatibility only.
At most one key source may be given, and the key itself is never echoed.

``check-report <report.json> --fixtures <fixtures.json> [--adapter ID] [--claim-id ID ...] [--task-type TYPE]``
    Run every claim of a specialist report (or the selected ones) through
    translation (fixture provider), verification and outcome composition, and
    print the list of ``ClaimVerificationOutcome`` objects as JSON. ``report.json``
    is either a ``SpecialistReport`` document or an envelope
    ``{"response": "<raw specialist text>", "request_id", "task_id", "report_id",
    "subject", "task_type", "supplied_texts": [...], "course_level"?, "agent_version"?}``
    parsed by the chosen adapter. ``fixtures.json`` maps ``claim_id`` to the fixture
    provider's response (JSON text, object, or list of those for successive attempts).
    Quotation roles (a correction or a suggestion frame is read only in a marking or
    feedback task) are read in the task type the operator states: ``--task-type``, else
    an envelope's ``task_type`` (the request's metadata beside the raw response). A
    ``SpecialistReport`` document's own ``task_type`` is the report's statement about
    itself and never widens them: without ``--task-type`` such a report is read in no
    task, where every quoted span is checked as a quotation.
    Exit code 3 when the translation pipeline is not available in this build.

``version``
    Print the component versions as JSON.

``serve [--host H] [--port P]``
    Run the HTTP service with uvicorn using settings from the environment.
    Untested live in this repository.

Output is JSON on stdout; errors are one-line JSON objects on stderr, never stack traces.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from .engine.policies import LINEAR, NAMED_POLICIES, UnknownPolicyError, named_policy
from .engine.provenance import z3_version
from .engine.results import SolverConfig
from .engine.runner import verify
from .version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION

__all__ = ["build_parser", "main", "ADAPTER_IDS", "MIN_SIGNING_KEY_BYTES", "SIGNING_KEY_ENV"]

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3

#: The shortest signing key accepted: the service's floor (``service.settings.MIN_SIGNING_KEY_BYTES``, kept equal by a
#: test; the service package is not imported here because it needs the optional HTTP dependencies).
MIN_SIGNING_KEY_BYTES = 16
#: The environment variable ``--signing-key-env`` reads by default: the one the service reads its key from.
SIGNING_KEY_ENV = "EPINOIC_SIGNING_KEY"
#: A key file holds hex text; anything longer than this is not a key file.
_KEY_FILE_MAX_BYTES = 4096

#: Adapter ids accepted by ``check-report``; they are looked up in the adapter registry.
ADAPTER_IDS = ("generic-structured", "english-specialist", "history-specialist")


class CliError(Exception):
    """A usage or input error reported as one JSON line on stderr."""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _emit(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _emit_error(message: str) -> None:
    sys.stderr.write(json.dumps({"error": message}) + "\n")


def _read_bytes(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as exc:
        raise CliError(f"cannot read {path}: {type(exc).__name__}") from None


def _read_json(path: str) -> Any:
    try:
        return json.loads(_read_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CliError(f"{path} is not valid JSON") from None


def _key_text(args: argparse.Namespace) -> tuple[Optional[str], str]:
    """``(hex text of the signing key or None, the option it came from)``; at most one source may be given."""
    given = [name for name, value in (("--signing-key-hex", args.signing_key_hex), ("--signing-key-file", args.signing_key_file),
                                      ("--signing-key-env", args.signing_key_env)) if value is not None]
    if len(given) > 1:
        raise CliError(f"give one signing key source, not {' and '.join(given)}")
    if args.signing_key_file is not None:
        try:
            with open(args.signing_key_file, "rb") as handle:
                raw = handle.read(_KEY_FILE_MAX_BYTES + 1)
        except OSError as exc:
            raise CliError(f"cannot read --signing-key-file: {type(exc).__name__}") from None
        if len(raw) > _KEY_FILE_MAX_BYTES:
            raise CliError("--signing-key-file is too long to be a key file (hex text on its first line)")
        try:
            lines = raw.decode("ascii").splitlines()
        except UnicodeDecodeError:
            raise CliError("--signing-key-file must hold the key as hex text") from None
        return (lines[0] if lines else ""), "--signing-key-file"
    if args.signing_key_env is not None:
        value = os.environ.get(args.signing_key_env)
        if value is None:
            raise CliError(f"--signing-key-env: the environment variable {args.signing_key_env} is not set")
        return value, f"--signing-key-env ({args.signing_key_env})"
    return args.signing_key_hex, "--signing-key-hex"


def _signing(args: argparse.Namespace) -> tuple[Optional[bytes], Optional[str]]:
    """The signing key and key id the command signs with, or ``(None, None)`` when no key source is given. A key that is
    not hex text or is shorter than :data:`MIN_SIGNING_KEY_BYTES` is a usage error; the key is never echoed."""
    text, source = _key_text(args)
    if text is None:
        return None, None
    try:
        key = bytes.fromhex(text.strip())
    except ValueError:
        raise CliError(f"{source} must be hex text") from None
    if not key:
        raise CliError(f"{source} must not be empty")
    if len(key) < MIN_SIGNING_KEY_BYTES:
        raise CliError(f"{source}: a signing key must be at least {MIN_SIGNING_KEY_BYTES} bytes ({2 * MIN_SIGNING_KEY_BYTES} hex digits), "
                       f"as the service requires; this one has {len(key)}")
    return key, args.key_id or "default"


def _solver_config(args: argparse.Namespace) -> SolverConfig:
    values: dict[str, Any] = {}
    if args.timeout_ms is not None:
        values["timeout_ms"] = args.timeout_ms
    if args.rlimit is not None:
        values["rlimit"] = args.rlimit
    try:
        return SolverConfig.model_validate(values)
    except Exception:  # pydantic ValidationError; message kept generic
        raise CliError("invalid solver configuration (--timeout-ms must be 1..120000, --rlimit >= 1)") from None


# --- commands ------------------------------------------------------------------------

def cmd_version(_: argparse.Namespace) -> int:
    _emit({
        "ir_version": IR_VERSION,
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "translator_version": TRANSLATOR_VERSION,
        "z3_version": z3_version(),
    })
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    raw = _read_bytes(args.problem)
    try:
        limits, config = named_policy(args.policy, _solver_config(args))
    except UnknownPolicyError:
        raise CliError(f"--policy must be one of: {', '.join(sorted(NAMED_POLICIES))}") from None
    key, key_id = _signing(args)
    result = verify(raw, config, limits, key, key_id)
    _emit(result.model_dump(mode="json"))
    return EXIT_OK


def _load_pipeline() -> tuple[Any, Any, Any]:
    try:
        pipeline = importlib.import_module("epinoic_logic.translate.pipeline")
        outcome = importlib.import_module("epinoic_logic.translate.outcome")
        fixture = importlib.import_module("epinoic_logic.translate.providers.fixture")
    except ImportError:
        raise CliError("the translation pipeline is not available in this build", EXIT_UNAVAILABLE) from None
    return pipeline, outcome, fixture


def _load_adapter(adapter_id: str) -> Optional[Any]:
    """Return the registered adapter, or None when the adapters package is not available."""
    try:
        importlib.import_module("epinoic_logic.adapters")
        base = importlib.import_module("epinoic_logic.adapters.base")
    except ImportError:
        return None
    try:
        return base.get_adapter(adapter_id)
    except (KeyError, LookupError, ValueError):
        pass
    # The registry may be populated only when the adapter's own module is imported.
    with contextlib.suppress(ImportError):
        importlib.import_module(f"epinoic_logic.adapters.{adapter_id.replace('-', '_')}")
    try:
        return base.get_adapter(adapter_id)
    except (KeyError, LookupError, ValueError):
        raise CliError(f"unknown adapter {adapter_id!r}; expected one of {', '.join(ADAPTER_IDS)}") from None


def _is_report_document(document: Any) -> bool:
    """A ``SpecialistReport`` document (not an envelope with a raw response)."""
    return isinstance(document, dict) and "original_response" in document and "claims" in document


def _load_report(path: str, adapter: Optional[Any]) -> Any:
    from .translate.contracts import SpecialistReport, SuppliedText

    document = _read_json(path)
    if not isinstance(document, dict):
        raise CliError(f"{path} must contain a JSON object")
    if _is_report_document(document):
        try:
            return SpecialistReport.model_validate(document)
        except Exception:
            raise CliError(f"{path} does not match the SpecialistReport contract") from None
    if "response" not in document:
        raise CliError(f"{path} must be a SpecialistReport or an envelope with a 'response' field")
    if adapter is None:
        raise CliError("parsing a raw specialist response requires the adapters package, which is not available", EXIT_UNAVAILABLE)
    required = ("request_id", "task_id", "report_id", "subject", "task_type")
    missing = [k for k in required if not isinstance(document.get(k), str) or not document.get(k)]
    if missing:
        raise CliError(f"{path} envelope is missing: {', '.join(missing)}")
    try:
        texts = [SuppliedText.model_validate(t) for t in document.get("supplied_texts", [])]
    except Exception:
        raise CliError(f"{path} has invalid supplied_texts") from None
    if not isinstance(document["response"], str):
        raise CliError(f"{path} 'response' must be a string")
    try:
        return adapter.parse_response(
            document["response"],
            request_id=document["request_id"], task_id=document["task_id"], report_id=document["report_id"],
            subject=document["subject"], task_type=document["task_type"], supplied_texts=texts,
            course_level=document.get("course_level", "unknown"), agent_version=document.get("agent_version"),
        )
    except Exception as exc:
        raise CliError(f"adapter could not parse the response: {type(exc).__name__}") from None


def cmd_check_report(args: argparse.Namespace) -> int:
    from .adapters.markdown import quotation_task
    pipeline, outcome_mod, fixture_mod = _load_pipeline()
    adapter = _load_adapter(args.adapter)
    stated = getattr(args, "task_type", None)
    with quotation_task(stated, authoritative=True) if stated else contextlib.nullcontext():
        report = _load_report(args.report, adapter)
    if not stated and not _is_report_document(_read_json(args.report)):
        stated = getattr(report, "task_type", None)  # an envelope's task_type: the request's metadata beside the raw response
    fixtures = _read_json(args.fixtures)
    if not isinstance(fixtures, dict):
        raise CliError(f"{args.fixtures} must map claim_id to fixture responses")
    key, key_id = _signing(args)
    config = _solver_config(args)
    selected = set(args.claim_id or [])
    claims = [c for c in report.claims if not selected or c.claim_id in selected]
    unknown = sorted(selected - {c.claim_id for c in report.claims})
    if unknown:
        raise CliError(f"claim id(s) not in report: {', '.join(unknown)}")
    # quotation roles in the task type the operator states (module docstring); a report document's own task type is
    # advisory and never widens them (repair round 5, INV-QROLE-1)
    with (quotation_task(stated, authoritative=True) if stated else quotation_task(getattr(report, "task_type", None), advisory=True)):
        structural: list[Any] = []
        if adapter is not None:
            structural = list(adapter.structural_checks(report))
        else:
            sys.stderr.write(json.dumps({"note": "adapters package not available; structural checks skipped"}) + "\n")
        translator = pipeline.Translator(fixture_mod.FixtureTranslationProvider(fixtures))
        outcomes = [
            outcome_mod.verify_claim(
                claim, report, translator, structural=structural, config=config, signing_key=key, key_id=key_id,
            ).model_dump(mode="json")
            for claim in claims
        ]
    _emit(outcomes)
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the HTTP service. Untested live in this repository."""
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ImportError:
        raise CliError("uvicorn is not installed; install the 'service' extra", EXIT_UNAVAILABLE) from None
    from .service import ServiceSettings, SettingsError, create_app

    try:
        settings = ServiceSettings.from_env()
    except SettingsError as exc:
        raise CliError(str(exc)) from None
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")
    return EXIT_OK


# --- parser --------------------------------------------------------------------------

def _add_solver_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout-ms", type=int, default=None, help="solver timeout in milliseconds (default 2000)")
    parser.add_argument("--rlimit", type=int, default=None, help="Z3 resource limit for deterministic cutoffs")
    parser.add_argument("--signing-key-file", default=None, metavar="PATH",
                        help=f"file holding the HMAC-SHA256 signing key as hex text on its first line (at least {MIN_SIGNING_KEY_BYTES} bytes)")
    parser.add_argument("--signing-key-env", default=None, nargs="?", const=SIGNING_KEY_ENV, metavar="VAR",
                        help=f"read the signing key (hex) from the environment variable VAR (default {SIGNING_KEY_ENV})")
    parser.add_argument("--signing-key-hex", default=None,
                        help="the signing key as hex on the command line; other users of the machine can read it in the process "
                             "list, so prefer --signing-key-file or --signing-key-env")
    parser.add_argument("--key-id", default=None, help="key identifier bound into signed results (covered by the signature)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epinoic-logic", description="Epinoic AI logic verification engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify an IR problem file and print the result JSON")
    p_verify.add_argument("problem", help="path to a problem JSON file")
    _add_solver_options(p_verify)
    p_verify.add_argument("--policy", default=LINEAR, help=f"named engine policy ({'|'.join(sorted(NAMED_POLICIES))}; default {LINEAR})")
    p_verify.set_defaults(func=cmd_verify)

    p_check = sub.add_parser("check-report", help="translate and verify the claims of a specialist report")
    p_check.add_argument("report", help="SpecialistReport JSON, or an envelope with a raw 'response'")
    p_check.add_argument("--fixtures", required=True, help="JSON mapping claim_id to fixture provider responses")
    p_check.add_argument("--adapter", default="generic-structured", help=f"adapter id ({'|'.join(ADAPTER_IDS)})")
    p_check.add_argument("--claim-id", action="append", default=None, help="restrict to these claim ids (repeatable)")
    p_check.add_argument("--task-type", default=None, metavar="TYPE",
                         help="the task type the operator states for the report (quotation roles); a report document's own task_type never widens them")
    _add_solver_options(p_check)
    p_check.set_defaults(func=cmd_check_report)

    p_version = sub.add_parser("version", help="print component versions")
    p_version.set_defaults(func=cmd_version)

    p_serve = sub.add_parser("serve", help="run the HTTP service (settings from the environment)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns the process exit code instead of calling ``sys.exit``."""
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse already printed usage/help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
    try:
        return int(args.func(args))
    except CliError as exc:
        _emit_error(str(exc))
        return exc.exit_code
    except KeyboardInterrupt:
        _emit_error("interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
