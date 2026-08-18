"""IRCC PR-landings loader tests (spec §7c tripwire input).

The two plan-verbatim contracts (absent -> UNAVAILABLE, present-but-empty -> raise) open
the file; everything after them is the DRIFT surface the plan body did not cover.

FIXTURE PROVENANCE (derivation, never transcription — ruling B's spirit):
`fixtures/ircc_pr_by_cma_sample.csv` is a raw BYTE SLICE of the live feed
`https://www.ircc.canada.ca/opendata-donneesouvertes/data/ODP-PR-PT_CMA.csv`
(fetched 2026-08-08: HTTP 200, 1,714,674 bytes, 21,217 data rows, 11 columns) — the
verbatim header line plus six verbatim data rows, CRLF preserved. It is not hand-typed.
The six rows are chosen to carry every hazard the loader must survive: both modeled CMAs
(Montréal, Québec), one SUPPRESSED `--` cell (Alma), and one COMMA-BEARING member name
(`Territories (outside Census agglomeration, Nunavut)`) — that last row is the one that
kills a comma-delimited read, so the fixture is a regression test for the real defect,
not an illustration of it.
"""
import shutil
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.loaders.ircc import CSV_NAME, EXPECTED_COLUMNS, PRLandings, load_pr_landings

FIXTURE = Path(__file__).parent / "fixtures" / "ircc_pr_by_cma_sample.csv"


def _plant(tmp_path: Path, text: str | None = None) -> Path:
    """Put the fixture (optionally a mutated variant of it) where the loader looks."""
    target = tmp_path / CSV_NAME
    if text is None:
        shutil.copyfile(FIXTURE, target)
    else:
        target.write_text(text, encoding="utf-8", newline="")
    return target


def _fixture_lines() -> list[str]:
    """Read BYTES, not text: `Path.read_text` applies universal-newline translation (and has
    no `newline=` parameter before 3.13), which silently turns the fixture's CRLF into LF and
    collapses a `split("\\r\\n")` to one giant line — the mutation helpers below would then
    build variants that test nothing."""
    return FIXTURE.read_bytes().decode("utf-8").rstrip("\r\n").split("\r\n")


# --- the two plan-verbatim contracts -------------------------------------------------
# Both CONTRACTS are the plan's, unchanged. One TOKEN is strengthened (the plan body is
# reviewable, not gospel): see `test_present_but_empty_raises`.

def test_absent_file_is_unavailable_not_raise(tmp_path):
    result = load_pr_landings(data_dir=tmp_path)
    assert isinstance(result, PRLandings)
    assert result.available is False
    assert result.reason and "not found" in result.reason.lower()


def test_present_but_empty_raises(tmp_path):
    """`match` is `CSV is empty`, not the plan's bare `empty`, and the difference is the
    whole test. `tmp_path` is derived from this function's OWN name, so it contains the
    substring `empty` — and every LoaderError here prints the path. Under the bare token
    the assertion is satisfied by the directory string alone: with the size-0 gate deleted,
    `_read` raises `...unparseable...<tmp>/test_present_but_empty_raises0/...` and `empty`
    still matches. MEASURED both ways against a gate-removed copy of the loader: bare
    `empty` PASSES the mutant (blind); `CSV is empty` FAILS it and passes shipped."""
    (tmp_path / "ircc_pr_by_cma.csv").write_text("")
    with pytest.raises(LoaderError, match=r"CSV is empty"):
        load_pr_landings(data_dir=tmp_path)


# --- the real feed loads (tab-delimited despite `.csv`) ------------------------------

def test_real_slice_loads_and_keeps_suppressed_token(tmp_path):
    """A verbatim slice of the live feed must load, with `--` preserved as a TOKEN.

    `--` may never arrive as NaN: naive band comparisons classify NaN as inside every
    band (spec §7c value-integrity, codex r3-F5), so a suppressed cell silently becoming
    a float is exactly how a tripwire false-greens.
    """
    _plant(tmp_path)
    result = load_pr_landings(data_dir=tmp_path)
    assert result.available is True
    assert result.reason == ""
    assert result.frame is not None
    assert list(result.frame.columns) == list(EXPECTED_COLUMNS)
    # Test-OWNED literals for the two columns the loader actually addresses (the spec's
    # co-deletion pattern, codex r4-F4): the assertion above alone is circular — it would
    # survive a co-edit of EXPECTED_COLUMNS and the loader. These do not, and neither does
    # the header gate itself, which runs against the real bytes in the fixture.
    assert len(result.frame.columns) == 11
    assert result.frame.columns[6] == "EN_CENSUS_METROPOLITAN_AREA"
    assert result.frame.columns[10] == "TOTAL"
    assert len(result.frame) == 6
    totals = result.frame["TOTAL"]
    assert totals.isna().sum() == 0
    assert "--" in set(totals)
    members = set(result.frame["EN_CENSUS_METROPOLITAN_AREA"])
    assert {"Montréal", "Québec"} <= members


def test_comma_delimited_feed_is_refused(tmp_path):
    """The defect this loader was written against: the feed is TAB-delimited despite its
    `.csv` name. A comma read of the real bytes raises `pandas.errors.ParserError` — a
    class no `except LoaderError` catches. Whatever the delimiter turns out to be, a file
    this loader cannot address by column must fail as a LoaderError."""
    commas = "\r\n".join(line.replace("\t", ",") for line in _fixture_lines()) + "\r\n"
    _plant(tmp_path, commas)
    with pytest.raises(LoaderError, match="schema drift|unparseable"):
        load_pr_landings(data_dir=tmp_path)


# --- drift surface --------------------------------------------------------------------

def test_whitespace_only_file_is_loader_error(tmp_path):
    """Size > 0 slips the empty-file gate; pandas then raises EmptyDataError, which no
    `except LoaderError` catches. The read must be wrapped."""
    _plant(tmp_path, "\r\n\r\n")
    with pytest.raises(LoaderError, match="unparseable"):
        load_pr_landings(data_dir=tmp_path)


def test_ragged_row_is_loader_error(tmp_path):
    """Extra tab fields make the C parser raise ParserError — wrapped, never leaked."""
    lines = _fixture_lines()
    lines.append(lines[-1] + "\textra\tfields")
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="unparseable"):
        load_pr_landings(data_dir=tmp_path)


def test_renamed_column_is_schema_drift(tmp_path):
    lines = _fixture_lines()
    lines[0] = lines[0].replace("TOTAL", "TOTAUX")
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="schema drift"):
        load_pr_landings(data_dir=tmp_path)


def test_header_only_has_no_data_rows(tmp_path):
    _plant(tmp_path, _fixture_lines()[0] + "\r\n")
    with pytest.raises(LoaderError, match="no data rows"):
        load_pr_landings(data_dir=tmp_path)


def test_missing_modeled_cma_raises_not_silent_zero(tmp_path):
    """The fabricated-zero guard. A feed that parses but no longer carries a modeled CMA
    would let the tripwire sum an empty selection to 0 realized landings — a number that
    reads as a catastrophic immigration collapse and is CROSSED, not UNKNOWN. Presence is
    schema, so it is refused here (the 0-band interval semantics of `--` is NOT: that is
    value modeling and belongs to the tripwire task)."""
    lines = [ln for ln in _fixture_lines() if not ln.split("\t")[6] == "Québec"]
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="Québec"):
        load_pr_landings(data_dir=tmp_path)


def test_unknown_total_token_raises(tmp_path):
    """TOTAL's vocabulary is `--` or a nonnegative integer (MEASURED live 2026-08-08:
    16,539 numeric cells, min 5, 0 negative; 4,678 `--`; 0 other tokens). A new token
    would reach the tripwire's arithmetic as a bare ValueError."""
    lines = _fixture_lines()
    lines[1] = lines[1].rsplit("\t", 1)[0] + "\tN/A"
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="TOTAL"):
        load_pr_landings(data_dir=tmp_path)


# --- period axis: gated vocabulary + the as_of the consumers must not re-derive --------
# Added at Task 28. EN_MONTH was parsed by NOBODY and gated by nothing, so a month-token
# mutant was absorbed silently — and the tripwire's discriminating completeness check is
# "twelve DISTINCT months on the selected year", which a renamed token defeats while still
# counting twelve. The vocabulary is closed here, once, where the schema lives.

def test_month_vocabulary_is_closed(tmp_path):
    """`Febr` still counts as one distinct month. Only a closed vocabulary refuses it."""
    lines = _fixture_lines()
    lines[1] = lines[1].replace("\tFeb\t", "\tFebr\t", 1)
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="EN_MONTH"):
        load_pr_landings(data_dir=tmp_path)


def test_non_integer_year_token_raises(tmp_path):
    """EN_YEAR is the selection key for an annual tripwire; a token that is not a year
    would be silently unselectable rather than loudly wrong."""
    lines = _fixture_lines()
    lines[1] = lines[1].replace("2015\tQ1", "20I5\tQ1", 1)
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="EN_YEAR"):
        load_pr_landings(data_dir=tmp_path)


def test_latest_period_and_as_of_are_exposed_not_re_derived(tmp_path):
    """Every consumer re-deriving the feed's own coverage is a defect per consumer. The
    slice carries 2015 Jan-Feb, so the latest published period is 2015-02."""
    result = load_pr_landings(data_dir=_plant(tmp_path).parent)
    assert result.latest_period == (2015, 2)
    assert result.as_of == "2015-02"


def test_vintage_digest_is_recorded_on_load(tmp_path):
    """IRCC RESTATES history, so a downstream red must be attributable to data-vs-code.
    The digest is recorded (identity), NOT pinned (this feed refreshes monthly, and a pin
    would red on every upstream publication)."""
    import hashlib
    path = _plant(tmp_path)
    result = load_pr_landings(data_dir=tmp_path)
    assert result.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    from demoflow.loaders.pins import WORKBOOK_SHA256
    assert CSV_NAME not in WORKBOOK_SHA256          # recorded, never pinned


# --- review-response gates (adversarial review of Task 28) -----------------------------
# Three drift classes the shipped loader let through, each demonstrated on real bytes.
# All three are SCHEMA — the same argument `_check_modeled_cmas` and `_check_periods`
# already make: a PRESENT file asserting it is the feed must raise on every way it can lie.

def test_duplicate_cell_key_is_refused(tmp_path):
    """A republished / appended vintage that repeats a (province, member, year, month)
    cell DOUBLE-COUNTS, and doubling is not merely an inflated CROSSED — it reaches a
    FALSE GREEN: measured on the QC slice, a vintage whose true provincial total is
    29,918 (CROSSED below a 55k-65k band) becomes 59,836 (OK, exit 0) when every row is
    duplicated. Uniqueness is keyed on the PROVINCE too: a member token that legitimately
    appeared under two provinces would false-red a (member, year, month) key."""
    lines = _fixture_lines()
    _plant(tmp_path, "\r\n".join(lines + [lines[1]]) + "\r\n")
    with pytest.raises(LoaderError, match="duplicate"):
        load_pr_landings(data_dir=tmp_path)


def test_missing_province_token_raises_not_silent_unknown(tmp_path):
    """EN_PROVINCE_TERRITORY is the tripwire's PRIMARY selection key and was gated by
    nothing. A token drift ('Quebec' -> 'Québec') loads clean, selects nothing, and the
    indicator reports UNKNOWN forever while the run log points the reader at IRCC's
    publication calendar — verbatim the harm `_check_periods`' own docstring exists to
    prevent. Gated where the other selection keys are gated."""
    lines = _fixture_lines()
    mutated = [lines[0]]
    for line in lines[1:]:
        fields = line.split("\t")
        if fields[8] == "Quebec":
            fields[8] = "Québec"
        mutated.append("\t".join(fields))
    _plant(tmp_path, "\r\n".join(mutated) + "\r\n")
    with pytest.raises(LoaderError, match="EN_PROVINCE_TERRITORY"):
        load_pr_landings(data_dir=tmp_path)


@pytest.mark.parametrize("token", ["²", "١٢", "02026"])
def test_year_token_must_parse_and_be_canonical(tmp_path, token):
    """`str.isdigit()` is the wrong gate on all three counts, and each class fails
    differently. `'²'.isdigit()` is True but `int('²')` RAISES — a bare ValueError leaking
    out of `load_pr_landings`, routing around the one `except LoaderError` handler the
    module docstring says every failure lands in. `'١٢'` and `'02026'` both clear the gate
    AND parse, but neither string-matches the tripwire's `EN_YEAR == str(year)` selection:
    present-but-unselectable, the exact state the gate was written to close. One rule
    closes all three: `int(y)` parses AND round-trips to the same token."""
    lines = _fixture_lines()
    fields = lines[1].split("\t")
    fields[0] = token
    lines[1] = "\t".join(fields)
    _plant(tmp_path, "\r\n".join(lines) + "\r\n")
    with pytest.raises(LoaderError, match="EN_YEAR"):
        load_pr_landings(data_dir=tmp_path)
