"""Benchmark conditions for the suite's wall-clock bounds.

The review of 12 October 2026 asked for the timing tests to stay visible and for their benchmark conditions to be
stabilised rather than their bounds relaxed: one full-suite run measured a bracket-heavy hub crossing at about 2.49 s
against a 2 s bound that the same test met on its own. A bound such as 'this answer crosses the hub in under 2 s' is a
property of the code, so these tests measure it under fixed conditions instead of taking one sample of whatever the
process happens to be doing:

- Warm-up. The measured call runs once, unmeasured, so imports, compiled patterns, the solver's first context and
  other first-use initialisation of the process are not charged to the answer. A test whose own preceding calls already
  run the same path on the same text may pass ``warmup=False`` and say so beside the call; the report records it.
- Every sample is a first crossing. Before each measured run the package's memoisation caches are emptied (every
  functools cache of an ``epinoic_logic`` module, every module-level ``BoundedLRU``, and the report caches of the packs
  the branch registry shares), so no sample is served from what the warm-up or an earlier sample computed. A single
  sample in the full suite could find the same text already cached by an earlier test; this condition is stricter.
- Isolation from collection overhead. Before each measured run the objects the process already holds are frozen
  (``gc.freeze``): the cyclic collector still runs and still charges the measured call for collecting what it
  allocates, but no longer walks the heap the earlier tests left behind, whose size depends on what ran before it.
  They are unfrozen afterwards, whatever happened.
- Repeated measurement with a robust statistic. The verdict is on the median wall-clock time of ``repeat`` runs (five by
  default): the bound holds when a majority of the runs are under it and fails when a majority are at or over it.
  Sampling stops once the majority is decided, so the verdict is the one all ``repeat`` runs would give.

The bound itself is never changed, and each test asserts on every run's result what it asserted on its single run.
Each sample also records process CPU time beside the wall-clock time; the report gives both, so a contended machine
(wall time far above CPU time) can be told apart from a slow code path. Every measurement is printed, so pytest shows it
with ``-rP`` or ``-s``.
"""
from __future__ import annotations

import gc
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["Timing", "measure", "decided", "empty_caches", "cache_entries"]

PACKAGE = "epinoic_logic"


def _package_modules():
    return [(name, module) for name, module in list(sys.modules.items())
            if module is not None and (name == PACKAGE or name.startswith(PACKAGE + "."))]


def _shared_pack_caches():
    """(pack, attribute name, cache) for every cache attribute of the packs the branch registry shares between hubs."""
    registry = sys.modules.get(f"{PACKAGE}.branches.registry")
    out = []
    for branch in getattr(registry, "BRANCHES", ()):
        for pack in getattr(branch, "packs", ()):
            try:
                attrs = vars(pack)
            except TypeError:
                continue
            out += [(pack, name, value) for name, value in attrs.items() if "cache" in name.lower() and callable(getattr(value, "clear", None))]
    return out


def _module_caches():
    """(module name, cache) for every functools cache and module-level BoundedLRU defined in a loaded package module."""
    out = []
    for name, module in _package_modules():
        for value in list(vars(module).values()):
            if callable(getattr(value, "cache_clear", None)) and getattr(value, "__module__", None) == name:
                out.append((name, value))
            elif type(value).__name__ == "BoundedLRU" and callable(getattr(value, "clear", None)):
                out.append((name, value))
    return out


def empty_caches() -> int:
    """Empty every memoisation cache of the loaded package (see the module docstring); return how many were emptied.
    Every cache emptied is a pure memo of its arguments, so emptying one changes how long a call takes, never what it
    returns."""
    emptied = 0
    for _name, cache in _module_caches():
        (cache.cache_clear if hasattr(cache, "cache_clear") else cache.clear)()
        emptied += 1
    for pack, _attr, cache in _shared_pack_caches():
        lock = getattr(pack, "_lock", None)
        if lock is not None:
            with lock:
                cache.clear()
        else:
            cache.clear()
        emptied += 1
    return emptied


def cache_entries() -> int:
    """How many entries the caches ``empty_caches`` empties hold now (0 right after it)."""
    total = 0
    for _name, cache in _module_caches():
        total += cache.cache_info().currsize if hasattr(cache, "cache_info") else len(cache)
    for _pack, _attr, cache in _shared_pack_caches():
        total += len(cache)
    return total


@dataclass(frozen=True)
class Timing:
    """The measured runs of one call against its bound (seconds)."""
    label: str
    bound: float
    repeat: int
    wall: tuple[float, ...]
    cpu: tuple[float, ...]
    warmup: bool
    results: tuple[Any, ...] = field(repr=False, compare=False)

    @property
    def under(self) -> int:
        """How many of the runs taken were under the bound."""
        return sum(1 for w in self.wall if w < self.bound)

    @property
    def holds(self) -> bool:
        """The median wall-clock time of ``repeat`` runs is under the bound: a majority of them were under it."""
        return self.under > self.repeat // 2

    @property
    def median(self) -> float:
        """The median of the runs taken (the verdict is ``holds``, decided over all ``repeat`` runs)."""
        return statistics.median(self.wall)

    def __str__(self) -> str:
        fmt = lambda xs: "[" + ", ".join(f"{x:.3f}" for x in xs) + "]"  # noqa: E731
        runs = lambda n: f"{n} run{'' if n == 1 else 's'}"  # noqa: E731
        return (f"{self.label or 'measured call'}: the median wall-clock time of {runs(self.repeat)} is "
                f"{'under' if self.holds else 'NOT under'} the {self.bound:g} s bound ({self.under} of the {runs(len(self.wall))} taken under it, "
                f"which decides the median of {self.repeat}); wall {fmt(self.wall)} s, CPU {fmt(self.cpu)} s; "
                f"{'one unmeasured warm-up run first, ' if self.warmup else 'no warm-up run (the test warms the path itself), '}"
                "the package's caches emptied and the earlier heap frozen before each run")


def decided(under: int, taken: int, repeat: int) -> bool | None:
    """Whether the median of ``repeat`` runs is under the bound, once ``taken`` runs of which ``under`` were under it are
    known: True or False when the remaining runs cannot change it, None while they can."""
    majority = repeat // 2 + 1
    if under >= majority:
        return True
    if taken - under >= majority:
        return False
    return None


def measure(run: Callable[[], Any], bound: float, *, repeat: int = 5, label: str = "", warmup: bool = True) -> Timing:
    """Time ``run()`` against ``bound`` seconds under the conditions of the module docstring and return the runs.

    ``repeat`` must be odd, so the median is one of the runs; ``repeat=1`` is a single sample (still warmed up, with
    caches emptied and the heap frozen). ``warmup=False`` skips the unmeasured first run, for a test whose own preceding
    calls warm the same path. The caller asserts ``timing.holds`` (and whatever it asserted on its result, on every entry
    of ``timing.results``)."""
    if repeat < 1 or repeat % 2 == 0:
        raise ValueError("repeat must be a positive odd number, so that the median is one of the runs")
    if warmup:
        run()
    wall: list[float] = []
    cpu: list[float] = []
    results: list[Any] = []
    while len(wall) < repeat:
        empty_caches()
        gc.freeze()
        try:
            c0, t0 = time.process_time(), time.perf_counter()
            out = run()
            t1, c1 = time.perf_counter(), time.process_time()
        finally:
            gc.unfreeze()
        wall.append(t1 - t0)
        cpu.append(c1 - c0)
        results.append(out)
        if decided(sum(1 for w in wall if w < bound), len(wall), repeat) is not None:
            break
    timing = Timing(label, bound, repeat, tuple(wall), tuple(cpu), warmup, tuple(results))
    print(timing)
    return timing
