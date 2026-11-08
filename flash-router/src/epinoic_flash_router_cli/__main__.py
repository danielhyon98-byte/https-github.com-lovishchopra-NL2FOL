"""``python -m epinoic_flash_router_cli {hello,plan,pool-hello,pool-plan,identity} [--data DIR]``

The flash router as a separate sub-agent over the router port: a routing request in on standard input (``plan``:
``routing-request.v1``; ``pool-plan``: ``pool-routing-request.v1``), the routing plan out on standard output, as the
router's canonical JSON text with no trailing newline. ``hello`` and ``pool-hello`` write the router's two hellos;
``identity`` writes its identity (name, version, the digests of its rules and of its cost data). Deterministic: the same
input and the same data give the same output, byte for byte.

``--data DIR`` runs the router over another data directory with the same layout (its ``MANIFEST.json`` and the files it
names): how a re-tuned copy of the rules or the cost data is tried before it is released. The identity then carries
that data's digests.

Exit status: 0 with the answer; 2 when the data cannot be loaded; 3 when the input is not a request this router reads
(the reason on standard error, never on standard output).
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from epinoic_flash_router.port import FlashRouter
from epinoic_flash_router.rules import canonical

OPERATIONS = ("hello", "plan", "pool-hello", "pool-plan", "identity")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="epinoic-flash-router", description="The Epinoic AI flash router as a separate sub-agent over the "
                                 "router port: a routing request on standard input, the routing plan on standard output.")
    ap.add_argument("operation", choices=OPERATIONS)
    ap.add_argument("--data", metavar="DIR", help="a data directory with its MANIFEST.json (default: the router's own data)")
    args = ap.parse_args(argv)
    try:
        router = FlashRouter(args.data)
    except (OSError, ValueError) as exc:
        print(f"epinoic-flash-router: the data cannot be loaded ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    if args.operation in ("plan", "pool-plan"):
        text = sys.stdin.read()
        try:
            answer = router.plan(text) if args.operation == "plan" else router.pool_plan(text)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            print(f"epinoic-flash-router: the input is not a request this router reads ({type(exc).__name__})", file=sys.stderr)
            return 3
    elif args.operation == "hello":
        answer = router.hello()
    elif args.operation == "pool-hello":
        answer = router.pool_hello()
    else:
        answer = canonical(router.identity)
    sys.stdout.write(answer)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
