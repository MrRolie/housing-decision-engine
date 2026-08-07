import math

import pandas as pd
import pytest

from demoflow.loaders.validate import (
    assert_fraction, assert_finite, assert_nonneg_finite, assert_unique_primary_key,
    assert_year_lattice, assert_uniform_year_domain, assert_statut_sublattice,
)
from demoflow.errors import LoaderError


def test_fraction_accepts_unit_interval_rejects_out_of_range_and_nonfinite():
    assert assert_fraction("x", 0.0) == 0.0
    assert assert_fraction("x", 1.0) == 1.0
    for bad in (1.0000001, -1e-9, math.nan, math.inf, -math.inf):
        with pytest.raises(LoaderError):
            assert_fraction("x", bad)


def test_nonneg_finite_ratio_carveout_allows_gt_one():
    assert assert_nonneg_finite("ratio", 1.2) == 1.2   # ratio can exceed 1 (not a fraction)
    assert assert_nonneg_finite("ratio", 0.0) == 0.0
    for bad in (-0.01, math.nan, math.inf):
        with pytest.raises(LoaderError):
            assert_nonneg_finite("ratio", bad)


def test_finite_rejects_nan_inf_and_nonnumeric():
    assert assert_finite("x", 5.0) == 5.0
    for bad in (math.nan, math.inf, -math.inf, "n/a", None):
        with pytest.raises(LoaderError):
            assert_finite("x", bad)


def test_primary_key_uniqueness():
    ok = pd.DataFrame({"g": [1, 1], "y": [2030, 2031], "v": [1.0, 2.0]})
    assert_unique_primary_key(ok, ["g", "y"], "pop")  # no raise
    dup = pd.DataFrame({"g": [1, 1], "y": [2030, 2030], "v": [1.0, 2.0]})
    with pytest.raises(LoaderError, match="duplicate"):
        assert_unique_primary_key(dup, ["g", "y"], "pop")


def test_year_lattice_contiguity_and_expected_span():
    assert_year_lattice([2030, 2031, 2032], "pop")                      # contiguous, no span check
    with pytest.raises(LoaderError, match="contiguous|lattice"):
        assert_year_lattice([2030, 2031, 2033], "pop")                  # 2032 deleted
    with pytest.raises(LoaderError, match="empty"):
        assert_year_lattice([], "pop")
    assert_year_lattice(list(range(2021, 2052)), "pop", expected_span=(2021, 2051))  # ok
    with pytest.raises(LoaderError, match="span|endpoint"):
        assert_year_lattice(list(range(2021, 2051)), "pop", expected_span=(2021, 2051))  # 2051 missing


def test_uniform_year_domain_across_series():
    ok = pd.DataFrame({"geo": ["A", "A", "B", "B"], "sex": ["M"] * 4,
                       "year": [2030, 2031, 2030, 2031], "v": [1.0, 2.0, 3.0, 4.0]})
    assert_uniform_year_domain(ok, ["geo", "sex"], "year", "pop")       # every series {2030,2031}
    bad = pd.DataFrame({"geo": ["A", "A", "B"], "sex": ["M"] * 3,
                        "year": [2030, 2031, 2030], "v": [1.0, 2.0, 3.0]})  # B missing 2031
    with pytest.raises(LoaderError, match="domain|terminal"):
        assert_uniform_year_domain(bad, ["geo", "sex"], "year", "pop")


def test_statut_sublattice_single_transition_and_uniform_projected_domain():
    ok = pd.DataFrame({"geo": ["A"] * 4 + ["B"] * 4, "year": [2021, 2022, 2023, 2024] * 2,
                       "status": ["est", "est", "proj", "proj"] * 2})
    assert_statut_sublattice(ok, ["geo"], "year", "status", {"est", "proj"}, "pop")   # no raise
    # RED: relabel B's terminal 2024 proj->est (raw lattice intact; projected domain shortens)
    bad = ok.copy()
    bad.loc[(bad["geo"] == "B") & (bad["year"] == 2024), "status"] = "est"
    with pytest.raises(LoaderError, match="reversal|transitions|PROJECTED-year domain"):
        assert_statut_sublattice(bad, ["geo"], "year", "status", {"est", "proj"}, "pop")
    with pytest.raises(LoaderError, match="allowed set"):
        assert_statut_sublattice(ok.assign(status="???"), ["geo"], "year", "status", {"est", "proj"}, "pop")


# --- Four tests ADDED beyond the plan's 7 (each closes a gate the plan's bodies leave unexercised;
# --- reported to the seat as a divergence from the plan's "Expected: 7 PASS").

def test_statut_projected_domain_differs_without_reversal():
    """ADDED (spec §4, codex r10-F5). The plan's RED fixture (proj->est relabel of B's terminal
    year) trips the REVERSAL gate, and its regex alternation accepts that message — so the
    'IDENTICAL projected-year domain' gate the test NAMES never actually runs. A per-geography
    est->proj BOUNDARY shift is monotone AND single-transition, so only the projected-domain gate
    can catch it; the match is pinned to that message so this test cannot pass via another branch."""
    shifted = pd.DataFrame({"geo": ["A"] * 4 + ["B"] * 4, "year": [2021, 2022, 2023, 2024] * 2,
                            "status": ["est", "est", "proj", "proj",     # A: proj domain {2023,2024}
                                       "est", "proj", "proj", "proj"]})  # B: proj domain {2022,2023,2024}
    with pytest.raises(LoaderError, match="PROJECTED-year domain"):
        assert_statut_sublattice(shifted, ["geo"], "year", "status", {"est", "proj"}, "pop")


def test_non_integer_year_cells_raise_loader_error_not_bare_valueerror():
    """ADDED (spec §4: these causes are data/environment state -> EXPLICIT NAMED error). The three
    year-coercion sites bare-cast `int(y)`, so a blank `Annee` cell (NaN) or a text cell escapes as
    ValueError/TypeError — a different class from every other contract in this module, past any
    `except LoaderError` a caller writes. Covers all three sites."""
    for bad_years in ([2030, math.nan, 2032], [2030, "n/a"], [2030, 2031.5], [2030, math.inf]):
        with pytest.raises(LoaderError, match="year"):
            assert_year_lattice(bad_years, "pop")

    dom = pd.DataFrame({"geo": ["A", "A"], "sex": ["M", "M"],
                        "year": [2030, math.nan], "v": [1.0, 2.0]})
    with pytest.raises(LoaderError, match="year"):
        assert_uniform_year_domain(dom, ["geo", "sex"], "year", "pop")

    st = pd.DataFrame({"geo": ["A"] * 3, "year": [2021, 2022, math.nan],
                       "status": ["est", "proj", "proj"]})
    with pytest.raises(LoaderError, match="year"):
        assert_statut_sublattice(st, ["geo"], "year", "status", {"est", "proj"}, "pop")


def test_null_keyed_series_is_not_excised_from_uniform_year_domain():
    """ADDED (spec §4, codex r6-F3). pandas `groupby` defaults to `dropna=True`, so a row whose
    GROUP KEY is null is silently excised — the frame is non-empty, the gate runs, and it returns
    clean without ever examining that series. Reachable on the committed primary workbook:
    `pd.read_excel(pop-as-rmr-base.xlsx, sheet_name="Années d'âge", header=6)` yields 2513 rows of
    which 2 (header-continuation rows) carry NaN in EVERY label column — Scénario, Code, Région1,
    Année, Statut, Sexe — exactly the columns spec §8 makes the group keys. Deleting `dropna=False`
    turns this RED: the SAME deficiency raises under a labelled key and passes under a null one."""
    bad = pd.DataFrame({"geo": ["A", "A", math.nan], "sex": ["M"] * 3,
                        "year": [2030, 2031, 2030], "v": [1.0, 2.0, 3.0]})  # null-keyed B missing 2031
    with pytest.raises(LoaderError, match="non-uniform year domain"):
        assert_uniform_year_domain(bad, ["geo", "sex"], "year", "pop")


def test_null_keyed_series_is_not_excised_from_statut_sublattice():
    """ADDED (spec §4, codex r10-F5). Same `dropna=True` excision on the Statut loop — it fails open
    on ALL THREE per-series gates, so each is pinned by its own message here (an alternation would
    let one branch vouch for the other two, the failure mode
    `test_statut_projected_domain_differs_without_reversal` already exists to prevent)."""
    def frame(b_status):
        return pd.DataFrame({"geo": ["A"] * 4 + [math.nan] * 4, "year": [2021, 2022, 2023, 2024] * 2,
                             "status": ["est", "est", "proj", "proj"] + b_status})

    # proj→est relabel of the null-keyed series' terminal year -> reversal gate
    with pytest.raises(LoaderError, match="reversal"):
        assert_statut_sublattice(frame(["est", "est", "proj", "est"]), ["geo"], "year", "status",
                                 {"est", "proj"}, "pop")
    # all-est null-keyed series (0 transitions) -> exactly-one-transition gate
    with pytest.raises(LoaderError, match="transitions"):
        assert_statut_sublattice(frame(["est", "est", "est", "est"]), ["geo"], "year", "status",
                                 {"est", "proj"}, "pop")
    # est→proj BOUNDARY shift (monotone, single transition) -> projected-domain gate only
    with pytest.raises(LoaderError, match="PROJECTED-year domain"):
        assert_statut_sublattice(frame(["est", "proj", "proj", "proj"]), ["geo"], "year", "status",
                                 {"est", "proj"}, "pop")
