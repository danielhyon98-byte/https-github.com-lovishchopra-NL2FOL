"""Growth of a reader's cost between two input sizes (security round 1).

A wall-clock bound breaks when the machine is loaded; the ratio of the costs of one reader at two sizes of the same input
does not, because both sizes run under the same conditions. A linear reader costs about four times as much on an input
four times as long; a quadratic one about sixteen times. ``growth`` measures the process CPU time (other processes' load
is not charged to it) of interleaved runs of the reader on the two inputs, after a warm-up, with an inner loop long enough
for the timer, and returns the ratio of the smallest times. A reader that memoises its answer is given ``clear``, the
call that empties its memo (run before every call, untimed), so no run is served from an earlier one.
"""
from __future__ import annotations

import gc
import time
from typing import Any, Callable, Optional

__all__ = ["growth"]


def _cpu(fn: Callable[[Any], Any], arg: Any, loops: int, clear: Optional[Callable[[], Any]]) -> float:
    total = 0.0
    for _ in range(loops):
        if clear is not None:
            clear()
        t = time.process_time()
        fn(arg)
        total += time.process_time() - t
    return total


def growth(fn: Callable[[Any], Any], small: Any, large: Any, *, repeat: int = 3, floor_s: float = 0.02,
           clear: Optional[Callable[[], Any]] = None) -> tuple[float, float, float]:
    """``(ratio, t_small, t_large)``: the smallest CPU time of ``repeat`` interleaved runs of ``fn(small)`` and
    ``fn(large)`` (each run ``loops`` calls, ``loops`` chosen so that a run of the small input takes at least ``floor_s``,
    at most 256), per call, and their ratio."""
    if clear is not None:
        clear()
    fn(small)
    loops = 1
    while loops < 256 and _cpu(fn, small, loops, clear) < floor_s:
        loops *= 2
    gc.collect()
    ts, tl = [], []
    for _ in range(repeat):
        ts.append(_cpu(fn, small, loops, clear))
        tl.append(_cpu(fn, large, loops, clear))
    a, b = min(ts), min(tl)
    return b / max(a, 1e-9), a / loops, b / loops
