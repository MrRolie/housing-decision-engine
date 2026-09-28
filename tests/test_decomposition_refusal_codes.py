"""Every refusal code the `--decompose` block can carry, each pinned by a
witness that asserts that exact code (spec §0.1 items 44 and 50).

A code is a word the contract defines, and a reader keys on it. A literal
swapped for another code of the same set still builds, since both are in the
set, and the reason beside it still reads as it did, so the only test that can
fail on the swap is one that asserts the code on a run where that code fires.
The four sets are enumerated here, not sampled: a code with no witness in
`WITNESSES` fails `test_every_code_of_every_set_has_a_witness`, and each
witness names a run — real where the engine reaches the code, constructed where
it cannot — and the exact code that run carries at one place. Where the run is
printed, its line carries the code too, in the refusal's one shape.
"""
from __future__ import annotations

import copy
import dataclasses

import pytest
import yaml

import hde.break_even as be
import hde.decomposition as dc
import hde.decomposition_run as dr
import hde.decomposition_text as dt
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo

from tests import decomposition_households as hh
from tests.decomposition_runs import (
    ALL_OTHER, CONDO_ONLY, FIXTURE, INCOME, MONTREAL, MORTGAGE, RARE2,
    STATED_BESIDE_CROSSING, STATED_UNDER_A_CROSSING, _block_text, _cli, _load, _strict,
    force_income_move, run, untag)
from tests.test_decomposition_sentences import TWINS


def _inputs(raw):
    spec = load_config_dict(raw)
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return spec, det, mc, verdict


def _write(tmp_path, name, raw):
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _render(source, *extra):
    """`(the --json decomposition, the printed block)` of one CLI run."""
    code, out, _ = _cli(source, "--decompose", *extra, "--json")
    assert code == 0, out
    block = _strict(out)["decomposition"]
    code, out, _ = _cli(source, "--decompose", *extra, "-q")
    assert code == 0
    return block, _block_text(out)


# ---------------------------------------------------------------------------
# The witnesses: each returns the code its run carries at one place
# ---------------------------------------------------------------------------

def _whole(source, *extra):
    def witness(tmp_path, monkeypatch):
        path = _write(tmp_path, "cfg", source) if isinstance(source, dict) else source
        block, text = _render(path, *extra)
        refusal = block["refusal"]
        assert text.splitlines()[0] == (f"which risk decides it — not split "
                                        f"({refusal['code']}): {refusal['reason']}")
        return refusal["code"]
    return witness


def _forced_whole(force, source=FIXTURE):
    """A whole-block refusal no correct engine reaches, forced through the CLI
    on 40 futures by the helper that moves one run or one input."""
    def witness(tmp_path, monkeypatch):
        from tests.test_decomposition_run import TestTheFreezeIdentity, TestTheIdentityIsGated
        if force == "leak":
            TestTheFreezeIdentity._leaky_mask(monkeypatch,
                                              escaped=dc.channel_by_key("shelter").id)
        elif force == "offset":
            TestTheIdentityIsGated._offset_all_frozen(monkeypatch, 0.01)
        elif force == "income":
            force_income_move(monkeypatch, 1000.0)
        else:
            untag(monkeypatch)
        return _whole(source, "40")(tmp_path, monkeypatch)
    return witness


def _no_sign_variation(tmp_path, monkeypatch):
    block, text = _render(_write(tmp_path, "all_other", ALL_OTHER), "400")
    refusal = block["spread"]["refusal"]
    assert f"  not split ({refusal['code']}): {refusal['reason']}" in text.splitlines()
    return refusal["code"]


# The head a refused boundary prints behind, code by code, written here rather
# than read off `decomposition.EDGE_REFUSAL_CODES`: a code that refuses one
# boundary of a field, while another of that field's may print, never says no
# boundary was printed; any other code says so.
HEADS = {
    "unchanged": "no boundary printed",
    "not_on_axis": "no boundary printed",
    "not_identified": "a boundary not printed",
    "unconfirmed": "a boundary not printed",
    "not_exact": "no boundary printed",
    "no_futures": "no boundary printed",
    "scan_mismatch": "no boundary printed",
    "not_printable": "a boundary not printed",
    "not_orderable": "a boundary not printed",
}


def _boundary_lines(text, code, reason):
    lines = [line for line in text.splitlines() if line.endswith(f"({code}): {reason}")]
    assert lines, (code, reason)
    return lines


def _printed_refusal(block, text, key, field, starts):
    """The code of `field`'s refusal on `key`'s row whose reason opens with
    `starts`, checked against its printed line: the code in the refusal's one
    shape, behind its code's head."""
    (row,) = [r for r in block["reversal"]["exact"] if r["key"] == key]
    found = [r for r in row["refused_boundaries"]
             if r["verdict_field"] == field and r["reason"].startswith(starts)]
    assert found, (key, field, row["refused_boundaries"])
    code = found[0]["code"]
    for line in _boundary_lines(text, code, found[0]["reason"]):
        assert line.startswith(f"      {HEADS[code]} for "), line
    return code


def _unchanged(tmp_path, monkeypatch):
    got = run("fixture")
    return _printed_refusal(got.block, got.text, "house.mortgage_renewal_rates", "decisive",
                            "decisive says 'not decisive' at every one of")


def _not_on_axis(tmp_path, monkeypatch):
    block, text = _render(_write(tmp_path, "stated", STATED_BESIDE_CROSSING))
    return _printed_refusal(block, text, "house.mortgage_rate", "decisive",
                            "decisive says 'not decisive' in this run and at none of")


def _not_identified(tmp_path, monkeypatch):
    """The fixture at 100 of its own paths and the block's 400: the reversal
    register reads the config's own sample, on which the majority's boundary
    moves inside two standard errors."""
    raw = _load(FIXTURE)
    raw["simulation"]["num_sims"] = 100
    block, text = _render(_write(tmp_path, "fixture_100", raw), "400")
    return _printed_refusal(block, text, "house.mortgage_renewal_rates", "mc_best",
                            "across the bracket P(rent cheapest) moves by ")


def _two_option_register(raw=None, **kwargs):
    raw = _load(MORTGAGE) if raw is None else raw
    spec, det, mc, _ = _inputs(raw)
    return be.reversal_register(raw, det, kwargs.pop("mc", mc), **kwargs)


def _unconfirmed(tmp_path, monkeypatch):
    """A re-simulation that disagrees with the curve, through the register's
    own seam: the boundary is withheld with the re-simulation's figures."""
    def disagreeing(spec):
        result = run_monte_carlo(spec)
        result.prob_house_cheapest = (result.prob_house_cheapest or 0.0) + 0.05
        return result
    (row,) = _two_option_register(simulate=disagreeing).exact
    found = [r for r in row.refused_boundaries
             if r.verdict_field == "best" and r.reason.startswith("the re-simulation at ")]
    assert found, row.refused_boundaries
    return found[0].code


def _not_exact(tmp_path, monkeypatch):
    """A gate that does not license the key: every field of its row is
    refused, the row estimated. Unreachable for a financing key on a correct
    engine, so the gate is moved."""
    def unlicensed(raw, key, far, *, paths, simulate):
        return {"licensed": False, "why": "the gate was moved", "paths": paths,
                "worst_deviation_over_sd": 1.0}
    monkeypatch.setattr(be, "reversal_gate", unlicensed)
    (row,) = _two_option_register().estimated
    codes = {r.code for r in row.refused_boundaries if r.verdict_field == "best"}
    assert len(codes) == 1
    return codes.pop()


def _boundary_no_futures(tmp_path, monkeypatch):
    """The library's own path with no futures: the CLI refuses the whole block
    first, so the register is called directly."""
    (row,) = _two_option_register(mc=None).exact
    return next(r.code for r in row.refused_boundaries if r.verdict_field == "mc_best")


def _scan_mismatch(tmp_path, monkeypatch):
    """The nine scan points disagreeing with the solved crossings, which no
    correct engine does: the verdict read at the bracket's low end is moved,
    and the row refuses that field alone, printed."""
    real = be._ranking_at

    def lying(doc, key, value):
        got = real(doc, key, value)
        return {**got, "best": "house"} if value == 0.01 else got

    monkeypatch.setattr(be, "_ranking_at", lying)
    raw = _load(FIXTURE)
    block, text = _render(_write(tmp_path, "fixture", raw), "40")
    return _printed_refusal(block, text, "house.mortgage_rate", "best",
                            "best says 'rent' in this run and on every stretch")


def _not_printable(tmp_path, monkeypatch):
    block, text = _render(_write(tmp_path, "under", STATED_UNDER_A_CROSSING))
    return _printed_refusal(block, text, "house.mortgage_rate", "best",
                            "the crossing of best from 'house'")


def _not_orderable(tmp_path, monkeypatch):
    got = run("stated_at_a_sampled_crossing")
    return _printed_refusal(got.block, got.text, "house.mortgage_rate", "mc_best",
                            "0.06278717945831885, a figure on this axis")


def _no_distance(name):
    def witness(tmp_path, monkeypatch):
        got = run(name)
        reversal = got.block["reversal"]
        assert (f"  WHAT WOULD HAVE TO CHANGE — not solved ({reversal['no_distance_code']}): "
                f"{reversal['no_distance_reason']}") in got.text.splitlines()
        return reversal["no_distance_code"]
    return witness


def _no_mapping(tmp_path, monkeypatch):
    raw = _load(MORTGAGE)
    spec, det, mc, verdict = _inputs(raw)
    got = dr.decompose(spec, det=det, mc=mc, verdict=verdict, raw=None, paths=40)
    return got.reversal.no_distance_code


def _no_distance_single_option(tmp_path, monkeypatch):
    spec, det, mc, _ = _inputs(copy.deepcopy(CONDO_ONLY))
    return be.reversal_register(copy.deepcopy(CONDO_ONLY), det, mc).no_distance_code


WITNESSES = {
    "REFUSAL_CODES": {
        "no_futures": _whole(MONTREAL),
        "too_few_futures": _whole(MORTGAGE, "39"),
        "single_option": _whole(CONDO_ONLY),
        "one_channel": _whole(INCOME),
        "no_spread": _whole(TWINS),
        "budget": _whole(FIXTURE, "250001"),
        "income_moved": _forced_whole("income"),
        "untagged_width": _forced_whole("untag"),
        "degenerate_resample": _whole(RARE2, "400"),
        "freeze_leak": _forced_whole("leak"),
        "identity_failed": _forced_whole("offset"),
    },
    "SPREAD_REFUSAL_CODES": {
        "no_sign_variation": _no_sign_variation,
    },
    "BOUNDARY_REFUSAL_CODES": {
        "unchanged": _unchanged,
        "not_on_axis": _not_on_axis,
        "not_identified": _not_identified,
        "unconfirmed": _unconfirmed,
        "not_exact": _not_exact,
        "no_futures": _boundary_no_futures,
        "scan_mismatch": _scan_mismatch,
        "not_printable": _not_printable,
        "not_orderable": _not_orderable,
    },
    "NO_DISTANCE_CODES": {
        "no_candidate": _no_distance("three"),
        "not_admitted": _no_distance("inert"),
        "no_mapping": _no_mapping,
        "single_option": _no_distance_single_option,
    },
}


def test_every_code_of_every_set_has_a_witness():
    """The sets are enumerated: a code added to one without a witness here, or
    a witness for a code no set holds, fails."""
    for name, witnesses in WITNESSES.items():
        assert tuple(witnesses) == getattr(dc, name), name


@pytest.mark.parametrize("codes, code", [(name, code) for name, witnesses in WITNESSES.items()
                                         for code in witnesses])
def test_the_witness_carries_its_code(codes, code, tmp_path, monkeypatch):
    """*Kills it:* any code literal swapped for another of its set at the
    place its witness reads it (§0.1 item 44's rule: a guard pinned only where
    the corpus happens to reach it is not pinned)."""
    assert WITNESSES[codes][code](tmp_path, monkeypatch) == code


@pytest.mark.parametrize("code", dc.BOUNDARY_REFUSAL_CODES)
def test_each_boundary_code_prints_behind_its_head(code):
    """Every boundary code, one at a time, on a household's printed row: the
    head is the one `HEADS` writes for it, and `HEADS` holds every code.
    *Kills it:* a code added to `EDGE_REFUSAL_CODES` or dropped from it, or
    a head keyed on anything but the code."""
    assert tuple(HEADS) == dc.BOUNDARY_REFUSAL_CODES
    outcome = hh.uncertainty_surface()
    renewal, contract_rate = outcome.reversal.exact
    refused = dc.RefusedBoundary(verdict_field="decisive", code=code, reason="a fact")
    row = dataclasses.replace(renewal, refused_boundaries=(refused,))
    outcome = dataclasses.replace(outcome, reversal=dataclasses.replace(
        outcome.reversal, exact=(row, contract_rate)))
    lines = [line for line in dt.format_decomposition(outcome).splitlines()
             if line.endswith(f"({code}): a fact")]
    assert lines == [f"      {HEADS[code]} for the decisiveness verdict ({code}): a fact"]
