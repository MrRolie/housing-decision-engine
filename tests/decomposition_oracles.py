"""Instruments that answer "did this stream draw?" and "does re-drawing it move a
present value?" WITHOUT the assembler's own measurement (§0.1 item 39).

The engine measures both on the block's futures: a recorder on the addressed
binding of `A`, and one `A_B^(c)` per drawing stream compared with `A`
(`decomposition_run.measure_channels`). A test that re-ran that code and
compared it with itself could not fail, so these instruments reach the same
questions another way:

  - `oracle_drawn`: one plain generator per stream, held for the whole run and
    drawn sequentially across paths — not the addressed per-path binding — and
    a stream drew when its generator's state moved;
  - `oracle_moves`: that stream alone re-seeded (101 against 202) on the held
    generators, and the largest present-value difference between the two runs;
  - `freeze_moves`: `A` against `A` with the channel FROZEN at the central
    case's value (`run_monte_carlo(freeze=...)`), the level register's
    mechanism rather than the re-draw's.

The threshold they are compared with is `decomposition_run.identity_budget`,
the one home of the figure; the tests import it, and never the comparison.
"""
from __future__ import annotations

from typing import Dict, Set

import numpy as np

from hde import decomposition_run as dr
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo

OPTIONS = ("condo", "house", "rent")
STREAMS = dr.STREAM_IDS


def held_streams(overrides=None):
    seeds = {c: 1000 + c for c in STREAMS}
    seeds.update(overrides or {})
    return {c: np.random.default_rng(s) for c, s in seeds.items()}


def _pvs(result) -> Dict[str, np.ndarray]:
    return {o: np.asarray(getattr(result, o).pvs, dtype=np.float64)
            for o in OPTIONS if getattr(result, o) is not None}


def _largest_difference(left, right) -> float:
    a, b = _pvs(left), _pvs(right)
    return max(float(np.max(np.abs(a[o] - b[o]))) for o in a)


def oracle_drawn(spec, paths: int = 40) -> Set[int]:
    streams = held_streams()
    before = {c: g.bit_generator.state for c, g in streams.items()}
    run_monte_carlo(dr._spec_at(spec, paths), streams)
    return {c for c, g in streams.items() if g.bit_generator.state != before[c]}


def oracle_moves(spec, paths: int) -> Dict[int, float]:
    small = dr._spec_at(spec, paths)
    return {c: _largest_difference(run_monte_carlo(small, held_streams({c: 101})),
                                   run_monte_carlo(small, held_streams({c: 202})))
            for c in STREAMS}


def freeze_moves(spec, paths: int) -> Dict[int, float]:
    small = dr._spec_at(spec, paths)
    base = dr._run(small, dr.MATRIX_A)
    return {c: _largest_difference(base, dr._run(small, dr.MATRIX_A, freeze=(c,)))
            for c in dr.ALL_CHANNEL_IDS}


def threshold(spec) -> float:
    det = compute_deterministic(spec)
    verdict = compute_verdict(det, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return dr.identity_budget(det, verdict)
