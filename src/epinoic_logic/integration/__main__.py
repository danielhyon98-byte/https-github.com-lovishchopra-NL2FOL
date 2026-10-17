"""``python -m epinoic_logic.integration serve [--host H] [--port P]`` and ``... preflight [--host H]``.

Order: the standard-library bootstrap (Z3 present and in range, else ``KIT-HS-003 z3_unavailable`` and exit status 2,
before any engine import), then the preflight (every required part, ``KIT-HS`` codes), then the self-test
(``KIT-HS-004``), then the service. A refusal prints one line, the code and its name (and a secret-free reason), on
standard error, and exits with status 2. ``preflight`` stops before binding and prints the capabilities document.
The profile comes from ``EPINOIC_PROFILE`` (``integration`` when unset; ``integration-sim`` for the simulation).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m epinoic_logic.integration", description="the integration checks service")
    sub = ap.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="preflight, self-test, then serve the checks port")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    pre = sub.add_parser("preflight", help="preflight and self-test only; print the capabilities document")
    pre.add_argument("--host", default="127.0.0.1")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    from .bootstrap import require_z3
    require_z3()  # standard library only: exits 2 with KIT-HS-003 before any engine import
    from .errors import IntegrationError
    from .settings import IntegrationSettings
    settings = IntegrationSettings.from_env(host=args.host)
    try:
        from .runtime import build_runtime
        runtime = build_runtime(settings)
    except IntegrationError as exc:
        sys.stderr.write(exc.line() + (f": {exc.detail}" if exc.detail else "") + "\n")
        return 2
    if args.command == "preflight":
        sys.stdout.write(json.dumps(runtime.capabilities(), indent=2, sort_keys=True) + "\n")
        return 0
    try:
        import uvicorn
    except ImportError:
        sys.stderr.write("uvicorn is not installed; install the 'service' extra\n")
        return 3
    from ..service.app import create_app
    from ..service.settings import ServiceSettings
    keys = runtime.facts.keys
    service = ServiceSettings(service_token=keys.service_token, signing_key=keys.engine_key, signing_key_id=keys.engine_key_id,
                              max_body_bytes=runtime.facts.limits.max_body_bytes, max_concurrency=runtime.facts.limits.turn_slots,
                              rate_per_minute=runtime.facts.rate_per_minute)
    uvicorn.run(create_app(service, integration=runtime), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
