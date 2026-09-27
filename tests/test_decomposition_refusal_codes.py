"""Every refusal code the `--decompose` block can carry, each pinned by a
witness that asserts that exact code (spec §0.1 items 44 and 50).

A code is a word the contract defines, and a reader keys on it. A literal
swapped for another code of the same set still builds, since both are in the
set, and the reason beside it still reads as it did, so the only test that can
fail on the swap is one that asserts the code on a run where that code fires.
The block's two sets are enumerated here, not sampled: a code with no witness
in `WITNESSES` fails `test_every_code_of_every_set_has_a_witness`, and each
witness names a run — real where the engine reaches the code, constructed where
it cannot — and the exact code that run carries at one place. Where the run is
printed, its line carries the code too, in the refusal's one shape. The
reversal library's own codes are no block's (§0.1 item 56), and its tests are
`test_reversal_register.py`'s.
"""
from __future__ import annotations

import pytest
import yaml

import hde.decomposition as dc

from tests.decomposition_runs import (
    ALL_OTHER, CONDO_ONLY, FIXTURE, INCOME, MONTREAL, MORTGAGE, RARE2, _block_text, _cli,
    _strict, force_income_move, untag)
from tests.test_decomposition_sentences import TWINS


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
