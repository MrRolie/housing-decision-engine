"""Task 12 contract tests. The first two are the plan's numbered contract, verbatim.
Everything below them pins a fact MEASURED 2026-08-07 that the plan body got wrong or
did not cover — each one is named at its test."""
import pandas as pd
import pytest

from demoflow.geography import Geography, Scenario
from demoflow.loaders.compo import load_immigrant_flows
from demoflow.errors import LoaderError


# ---------------------------------------------------------------- plan contract (verbatim)

def test_load_immigrant_flows_tidy():
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert set(df.columns) == {"geography", "scenario", "year", "immigrants_permanents", "npr_net_flow"}
    assert Geography.MTL_RMR in set(df["geography"].unique())
    assert {Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH} <= set(df["scenario"].unique())
    assert (df["immigrants_permanents"] >= 0).all()


def test_header_token_drift_raises(tmp_path):
    import demoflow.loaders.compo as compo
    with pytest.raises(LoaderError, match="header token"):
        compo._verify_header_tokens({16: "Naissances", 18: "Décès"})


# ---------------------------------------------------------------- added: measured facts

def test_swapped_flow_columns_raise():
    """The plan's guard used `token_a not in text AND token_b not in text`, so the REAL
    col-18 header ('...non permanents') satisfied col 16's check via 'permanent' alone: a
    16<->18 swap would have loaded the NPR net flow as the immigrant arrival flow, silently.
    The guard must require BOTH of its tokens."""
    import demoflow.loaders.compo as compo
    swapped = {16: "Migration internationale Solde de  résidents  non permanents n",
               18: "Migration internationale Immigrants permanents n"}
    with pytest.raises(LoaderError, match="header token"):
        compo._verify_header_tokens(swapped)


def test_real_header_tokens_pass():
    """Positive leg: the byte-exact joins measured in BOTH committed compo workbooks."""
    import demoflow.loaders.compo as compo
    compo._verify_header_tokens({16: "Migration internationale Immigrants permanents n",
                                 18: "Solde de  résidents  non permanents n"})


def test_header_row_is_LOCATED_per_workbook_not_hardcoded():
    """What this test measurably catches: a `_locate_id_row` that stops finding the RIGHT row
    in either workbook. It pins the two MEASURED id-header positions (rmr 6, ra 5) — the fact
    that the offsets genuinely DIFFER, which is why the plan's hardcoded `_DATA_FIRST_ROW =
    10` (= id row 6) cannot be right for both.

    What it does NOT catch, MEASURED 2026-08-07 by mutation rather than assumed: it does not
    discriminate located-vs-hardcoded. Restoring the plan's hardcode where the plan actually
    put it — at the CALL SITE in `load_immigrant_flows` (`id_row = 6`), leaving
    `_locate_id_row` itself intact — leaves this test GREEN, because it calls
    `_locate_id_row` DIRECTLY and never loads a workbook through the mutated path. The leg
    that reddens under that mutation is `test_ra_workbook_loads_with_its_own_header_offset`;
    see its docstring for the mechanism.

    (An earlier version of this docstring claimed this assertion was "the only leg that pins
    located-vs-hardcoded" — the attribution was inverted, and it was corrected only after the
    mutation was actually run.)"""
    import demoflow.loaders.compo as compo
    from demoflow.loaders import pins
    located = {}
    for name in ("compo-rmr-base.xlsx", "compo-ra-base.xlsx"):
        raw = pd.read_excel(pins.DATA_DIR / name, sheet_name=compo.SHEET, header=None,
                            engine="openpyxl")
        located[name] = compo._locate_id_row(raw, name)
    assert located == {"compo-rmr-base.xlsx": 6, "compo-ra-base.xlsx": 5}


def test_ra_workbook_loads_with_its_own_header_offset():
    """THE leg that kills the plan's hardcode, MEASURED 2026-08-07 by mutation: with
    `id_row = 6` hardcoded at the call site (the plan's `_DATA_FIRST_ROW = 10`), this test
    FAILS — `compo-ra-base.xlsx: missing id header columns ['Scénario', 'Code', 'Région1',
    'Année'] (schema drift)`.

    The mechanism is the id-POSITION lookup, not the row counts: `_id_positions` reads the
    LOCATED row for the four id labels, and the ra workbook's row 6 is a label row, so the
    lookup raises instead of silently shifting the body. The row-count identities below pin
    lattice COMPLETENESS (geos x scenarios x flow years, nothing dropped or duplicated) and
    are genuinely invariant to a one-row-off body — the row a hardcode drops from compo-ra is
    `Le Québec` 2025, which classifies IGNORED and never reaches the output (MEASURED:
    `iloc[9:]` and `iloc[10:]` both yield 405 in-scope rows spanning (2025, 2051)). So the
    counts are not what carries the claim; the load raising is."""
    df = load_immigrant_flows("compo-ra-base.xlsx")
    expected = {Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13, Geography.LANAUDIERE_RA14_PROXY,
                Geography.LAURENTIDES_RA15_PROXY, Geography.MONTEREGIE_RA16_PROXY}
    assert set(df["geography"].unique()) == expected
    assert len(df) == 5 * 3 * 26            # geos x scenarios x flow years
    assert len(load_immigrant_flows("compo-rmr-base.xlsx")) == 3 * 3 * 26


def test_flow_year_lattice_is_interval_start_2025_2050():
    """MEASURED: the sheet's `Année` spans 2025-2051 (ruling H) but every FLOW column on the
    2051 row is ISQ's '...' suppression marker — the flow labeled t is the t->t+1 bridge
    (verified: MTL 2050 stock 4460001 + accroissement -3920 = the 2051 stock 4456081), so
    the flow series spans 2025-2050 and covers the 2025-2051 stock lattice with no gap."""
    import demoflow.loaders.compo as compo
    assert compo.RAW_SHEET_SPAN == (2025, 2051)
    assert compo.FLOW_SPAN == (2025, 2050)
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert (int(df["year"].min()), int(df["year"].max())) == (2025, 2050)
    assert 2051 not in set(df["year"])


def test_suppressed_flow_at_a_nonterminal_year_raises():
    """The terminal-year drop is a NAMED, falsifiable rule, never a blanket filter: a '...'
    anywhere but the sheet's last year is drift and must raise."""
    import demoflow.loaders.compo as compo
    body = pd.DataFrame({"year": [2030, 2031], "immigrants_permanents": ["...", 100.0],
                         "npr_net_flow": ["...", -5.0], "stock": [1.0, 2.0]})
    with pytest.raises(LoaderError, match="suppress"):
        compo._drop_suppressed_terminal_year(body, terminal_year=2031, name="synthetic")


def test_partial_suppression_raises():
    """A row with ONE flow suppressed and the other numeric is not the out-of-horizon
    terminal row — it is drift, and dropping it silently would lose a real observation."""
    import demoflow.loaders.compo as compo
    body = pd.DataFrame({"year": [2050, 2051], "immigrants_permanents": [100.0, "..."],
                         "npr_net_flow": [-5.0, -7.0], "stock": [1.0, 2.0]})
    with pytest.raises(LoaderError, match="suppress"):
        compo._drop_suppressed_terminal_year(body, terminal_year=2051, name="synthetic")


@pytest.mark.parametrize("unpublished", [None, "..."], ids=["blank", "marker"])
def test_terminal_row_with_an_UNPUBLISHED_STOCK_raises(unpublished):
    """Separates 'terminal-year flow is out of horizon' (stock still published — MEASURED:
    4456081) from 'the trailing rows went blank', which must never be dropped quietly.

    BOTH unpublished forms bind, and the marker form is the one this sheet actually uses:
    MEASURED on the in-scope 2051 rows, cols 6/9/16/17/18/34/35 are all '...' while col 4
    alone is published — so a col-4 that went unpublished would go '...' too, not blank. An
    `isna()`-only gate is fail-OPEN against exactly the drift form this source produces."""
    import demoflow.loaders.compo as compo
    body = pd.DataFrame({"year": [2050, 2051], "immigrants_permanents": [100.0, "..."],
                         "npr_net_flow": [-5.0, "..."], "stock": [1.0, unpublished]})
    with pytest.raises(LoaderError, match="stock"):
        compo._drop_suppressed_terminal_year(body, terminal_year=2051, name="synthetic")


def test_npr_net_flow_is_signed_not_gated_nonneg():
    """Signed-flow carve-out (spec §4 r9-F2): the NPR balance is legitimately negative
    (MEASURED: MTL_RMR 2025 = -59399). A nonneg gate here would refuse a valid workbook."""
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert (df["npr_net_flow"] < 0).any()
    mtl_2025 = df[(df["geography"] == Geography.MTL_RMR) & (df["year"] == 2025)
                  & (df["scenario"] == Scenario.REFERENCE)]
    assert len(mtl_2025) == 1
    assert float(mtl_2025["npr_net_flow"].iloc[0]) == -59399.0


def test_enum_columns_stay_object_dtype_so_equality_filters_work():
    """pandas 3.x infers its `str` dtype for str-subclass enums and then compares against
    'Geography.MTL_RMR', matching NOTHING — every downstream filter would select an empty
    frame (measured by the sibling loader at Task 11)."""
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert df["geography"].dtype == object and df["scenario"].dtype == object
    assert len(df[df["geography"] == Geography.MTL_RMR]) == 3 * 26


def test_unregistered_workbook_refuses():
    """`WORKBOOK_GEOGRAPHIES.get(name, frozenset())` (the plan body) makes the completeness
    gate pass trivially — i.e. unfalsifiable — for any unregistered workbook."""
    import demoflow.loaders.compo as compo
    with pytest.raises(LoaderError, match="WORKBOOK_GEOGRAPHIES"):
        compo._expected_geographies("not-a-committed-workbook.xlsx")


def test_missing_workbook_raises():
    with pytest.raises(LoaderError, match="not found"):
        load_immigrant_flows("no-such-compo.xlsx")


def test_directory_masquerading_as_workbook_raises(tmp_path):
    """`exists()` passes for a DIRECTORY and then leaks IsADirectoryError out of the pin
    check, past the named guard; `is_file()` is the correct test."""
    (tmp_path / "compo-rmr-base.xlsx").mkdir()
    with pytest.raises(LoaderError, match="not found"):
        load_immigrant_flows("compo-rmr-base.xlsx", data_dir=tmp_path)


def test_sha256_drift_raises(tmp_path):
    (tmp_path / "compo-rmr-base.xlsx").write_bytes(b"not the pinned workbook")
    with pytest.raises(LoaderError, match="sha256 drift"):
        load_immigrant_flows("compo-rmr-base.xlsx", data_dir=tmp_path)


def test_primary_key_is_unique_per_geography_scenario_year():
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    assert not df.duplicated(subset=["geography", "scenario", "year"]).any()


def test_scenario_completeness_gate_fires_on_a_dropped_fan():
    """Spec §8: missing any of the three fans for a geography x year -> raise. The plan body
    mapped the labels but never checked completeness, so a workbook shipping one fan for a
    geography would have been ranked on a single scenario, silently."""
    import demoflow.loaders.compo as compo
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    short = df[~((df["geography"] == Geography.MTL_RMR) & (df["year"] == 2030)
                 & (df["scenario"] == Scenario.LOW))]
    with pytest.raises(LoaderError, match="missing scenario"):
        compo._check_scenario_completeness(short, "synthetic")


def test_negative_arrival_flow_raises():
    import demoflow.loaders.compo as compo
    with pytest.raises(LoaderError, match="negative"):
        compo._as_flow_column(pd.Series([10.0, -1.0]), "Immigrants permanents", "synthetic",
                              nonneg=True)


def test_nonfinite_and_nonnumeric_flow_cells_raise():
    import demoflow.loaders.compo as compo
    with pytest.raises(LoaderError, match="non-finite"):
        compo._as_flow_column(pd.Series([10.0, float("inf")]), "npr", "synthetic", nonneg=False)
    with pytest.raises(LoaderError, match="non-numeric"):
        compo._as_flow_column(pd.Series([10.0, "s.o."]), "npr", "synthetic", nonneg=False)
    with pytest.raises(LoaderError, match="non-numeric"):   # NaN, never coerced to 0
        compo._as_flow_column(pd.Series([10.0, None]), "npr", "synthetic", nonneg=False)


def test_units_row_dropped_from_a_REAL_workbook_raises(tmp_path, monkeypatch):
    """Hits the drifted-edition boundary LIVE rather than on a synthetic frame: a real
    xlsx with the units row deleted keeps every header token intact while shifting the body
    up by one, which would silently swallow the first data row. The sha256 pin refuses any
    mutated copy by design, so the pin entry is repointed at the mutated bytes for this
    test only — the drift being tested is SCHEMA drift, one layer past the pin."""
    import hashlib
    import openpyxl
    from demoflow.loaders import pins

    src = pins.DATA_DIR / "compo-rmr-base.xlsx"
    wb = openpyxl.load_workbook(src)
    wb["Scénarios de 2026"].delete_rows(10)      # 1-indexed: the units row ('n')
    mutated = tmp_path / "compo-rmr-base.xlsx"
    wb.save(mutated)
    monkeypatch.setitem(pins.WORKBOOK_SHA256, "compo-rmr-base.xlsx",
                        hashlib.sha256(mutated.read_bytes()).hexdigest())
    with pytest.raises(LoaderError, match="units row"):
        load_immigrant_flows("compo-rmr-base.xlsx", data_dir=tmp_path)


def test_closed_cohort_evidence_states_what_it_cannot_bound():
    """The compo section is EVIDENCE, not a bound: compo has no age axis, so the spec's
    originally-requested 75+ net-migration SHARE is not computable from it. A section that
    cannot verify its claim must say so (and must not sum three scenarios into one artifact
    number).

    It returns LINES and writes nothing — `probes/run_p7.py` is the note's single writer
    (ruling K). Asserting on the returned lines is what keeps this test measuring the
    MEASUREMENT rather than a file that some other generator may have last touched."""
    from demoflow.loaders.compo import compo_evidence_lines
    df = load_immigrant_flows("compo-rmr-base.xlsx")
    text = "\n".join(compo_evidence_lines(df))
    assert "not computable" in text.lower()
    assert "no age" in text.lower()
    for scenario in (Scenario.REFERENCE, Scenario.LOW, Scenario.HIGH):
        assert scenario.value in text          # per-scenario breakdown, never one blended total
    assert Geography.MTL_RMR.value in text     # per-geography breakdown
    assert "2025-2050" in text                 # the flow-interval domain the totals cover


def test_compo_evidence_lines_refuses_an_empty_frame():
    """The refusal is the point: an empty frame would otherwise publish a table with no rows
    under prose asserting the magnitudes it summarises — a section whose own evidence is
    absent. `probes/run_p7.py` routes this to UNKNOWN-PROBE-FAILED at the compo boundary."""
    from demoflow.loaders.compo import compo_evidence_lines
    with pytest.raises(LoaderError, match="empty flow frame"):
        compo_evidence_lines(pd.DataFrame(
            columns=["geography", "scenario", "year", "immigrants_permanents", "npr_net_flow"]))
