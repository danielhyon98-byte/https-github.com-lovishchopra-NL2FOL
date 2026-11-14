"""``python -m epinoic_flash_router_cli {hello,plan,pool-hello,pool-plan,identity} [--data DIR]``

The flash router as a separate sub-agent over the router port: a routing request in on standard input (``plan``:
``routing-request.v1``; ``pool-plan``: ``pool-routing-request.v1``), the routing plan out on standard output, as the
router's canonical JSON text with no trailing newline. ``hello`` and ``pool-hello`` write the router's two hellos;
``identity`` writes its identity (name, version, the digests of its rules and of its cost data). Deterministic: the same
input and the same data give the same output, byte for byte.

``--data DIR`` runs the router over another data directory with the same layout (its ``MANIFEST.json`` and the files it
names): how a re-tuned copy of the rules or the cost data is tried before it is released. The identity then carries
that data's digests.

Exit status, each with its reason on standard error (never on standard output) and never a traceback:

* 0 with the answer;
* 2 when the data cannot be loaded: a file that cannot be read (``OSError``), that is not JSON or not the shape the
  planners read (``ValueError``, with the loader's reason) or that is nested too deep to decode (``RecursionError``);
* 3 when the input is not a request this router reads: standard input that cannot be read as text, or a request the
  router refuses (``RequestError``, with its reason: the member and the rule, from
  :mod:`epinoic_flash_router.contract`; a request nested too deep to decode, a number out of range, a zero quota, a
  transfer key named twice, say);
* 4 when the router itself fails: any other exception raised while importing its code and loading its data, writing a
  hello or its identity, or planning a request it reads. That is a fault in the router's own code (or a broken
  install), never in the input or in the data (a request that passes the router's checks cannot make the planners
  fail), so it is never reported as an input this router cannot read; it is named on standard error by its exception
  type only, as an engine's internal error is.

(A command line that ``argparse`` cannot read exits 2 with the usage, as every ``argparse`` program does.)
``SystemExit`` and ``KeyboardInterrupt`` are not caught.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

OPERATIONS = ("hello", "plan", "pool-hello", "pool-plan", "identity")
#: The data cannot be loaded.
EXIT_DATA = 2
#: The input is not a request this router reads.
EXIT_REQUEST = 3
#: The router failed: a fault in its own code, not in the input or the data.
EXIT_ROUTER = 4


def _router_failed(doing: str, exc: BaseException) -> int:
    print(f"epinoic-flash-router: the router failed {doing} ({type(exc).__name__}): a fault in the router's own code, not in the "
          "input or the data", file=sys.stderr)
    return EXIT_ROUTER


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="epinoic-flash-router", description="The Epinoic AI flash router as a separate sub-agent over the "
                                 "router port: a routing request on standard input, the routing plan on standard output.")
    ap.add_argument("operation", choices=OPERATIONS)
    ap.add_argument("--data", metavar="DIR", help="a data directory with its MANIFEST.json (default: the router's own data)")
    args = ap.parse_args(argv)
    try:
        # imported here, so that the package's own data, loaded when the router is imported, is reported as data too
        from epinoic_flash_router.contract import RequestError
        from epinoic_flash_router.port import FlashRouter
        from epinoic_flash_router.rules import canonical
        router = FlashRouter(args.data)
    except (OSError, ValueError) as exc:
        print(f"epinoic-flash-router: the data cannot be loaded ({type(exc).__name__}: {exc})", file=sys.stderr)
        return EXIT_DATA
    except RecursionError as exc:  # a data file nested too deep to decode: named, never a traceback
        print(f"epinoic-flash-router: the data cannot be loaded ({type(exc).__name__})", file=sys.stderr)
        return EXIT_DATA
    except Exception as exc:  # noqa: BLE001 - the loader's own fault (it refuses bad data with ValueError), or a broken install: 4, never 2
        return _router_failed("loading its code or its data", exc)
    if args.operation in ("plan", "pool-plan"):
        try:
            text = sys.stdin.read()
        except Exception as exc:  # noqa: BLE001 - input that is not text, say: the input's, exit 3
            print(f"epinoic-flash-router: the input is not a request this router reads ({type(exc).__name__}: standard input cannot be read "
                  "as text)", file=sys.stderr)
            return EXIT_REQUEST
        try:
            answer = router.plan(text) if args.operation == "plan" else router.pool_plan(text)
        except RequestError as exc:
            print(f"epinoic-flash-router: the input is not a request this router reads (RequestError: {exc})", file=sys.stderr)
            return EXIT_REQUEST
        except Exception as exc:  # noqa: BLE001 - raised planning a request the router reads: its own fault, exit 4, never 3
            return _router_failed("planning a request it reads", exc)
    else:
        try:
            if args.operation == "hello":
                answer = router.hello()
            elif args.operation == "pool-hello":
                answer = router.pool_hello()
            else:
                answer = canonical(router.identity)
        except Exception as exc:  # noqa: BLE001 - nothing of the input is read here: the router's own fault
            return _router_failed(f"writing its {args.operation}", exc)
    sys.stdout.write(answer)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
