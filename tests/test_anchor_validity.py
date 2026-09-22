"""`Anchor.valid_until` — the date after which a source says its figure changes
(2026-09-08).

`retrieved_on` says when a figure was confirmed; `valid_until` says when the
source itself says it stops being the figure: the Québec tax on insurance
premiums steps from 9% to 9.975% for premiums paid after 2026-12-31, an
indexed 2026 bracket ceiling is a 2026 ceiling. It is set ONLY where the
source states the change — never as a "review by" guess.

A run that USES a dated anchor past its date — an applied default, a
`sources:` declaration, a schedule the loader priced — gets one warning per
anchor. Reference anchors the run never touched stay silent. The comparison
date is the run date, so every dated anchor is silent today, and
`test_no_dated_anchor_is_past_today` turns red on the first day one passes:
that is the point of it.
"""

import dataclasses
import datetime
import json
import sys
from pathlib import Path

import pytest

from hde.anchors import ANCHORS, Anchor, AnchorError
from hde.config import all_warnings, anchors_in_use, load_config, load_config_dict, validity_warnings
from hde.serialization import anchors_to_dict

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
PAST = "past its validity date"

# Every anchor whose source states when its figure changes, and the date.
DATED = {
    # Revenu Québec: 9% → 9.975% for premiums paid after 2026-12-31
    "mortgage_insurance.premium_tax_rate.qc": "2026-12-31",
    # CRA "Indexation increase 2.0 %" / Revenu Québec "indexed" / T4032 "Effective January 1, 2026"
    "tax.federal.bracket_1_ceiling": "2026-12-31",
    "tax.federal.bracket_2_ceiling": "2026-12-31",
    "tax.federal.bracket_3_ceiling": "2026-12-31",
    "tax.federal.bracket_4_ceiling": "2026-12-31",
    "tax.qc.bracket_1_ceiling": "2026-12-31",
    "tax.qc.bracket_2_ceiling": "2026-12-31",
    "tax.qc.bracket_3_ceiling": "2026-12-31",
    "tax.on.bracket_1_ceiling": "2026-12-31",
    "tax.on.bracket_2_ceiling": "2026-12-31",
    "tax.on.bracket_3_ceiling": "2026-12-31",
    "tax.on.bracket_4_ceiling": "2026-12-31",
    "tax.federal.basic_personal_amount": "2026-12-31",
    "tax.qc.basic_personal_amount": "2026-12-31",
    "tax.on.basic_personal_amount": "2026-12-31",
    "tax.on.surtax_1_threshold": "2026-12-31",
    "tax.on.surtax_2_threshold": "2026-12-31",
    # RC4466: "indexed to inflation and rounded to the nearest $500"; the 2026 limit
    "tfsa.annual_limit": "2026-12-31",
    # the sum of the annual limits THROUGH 2026 — it grows by the 2027 limit
    "tfsa.cumulative_room_since_2009": "2026-12-31",
    # CRA: the relief applies to a first withdrawal "between January 1, 2026, and
    # December 31, 2028"; the standard two years resume after that
    "hbp.repayment_grace_years": "2028-12-31",
}


def _anchor(**over):
    # `quoted`, `unit` and `refresh_group` are carried because a DATED anchor
    # owes all three since 2026-09-22 (board item 6): a figure that says it will
    # be replaced must show how its source printed it, what base it is stated
    # on, and who publishes the replacement. They are inert on the undated
    # cases below. The rule itself is pinned in tests/test_anchor_refresh.py.
    base = dict(name="x.y", value=0.1, as_of="2026", source="s", url="u",
                rationale="r", band=(0.0, 1.0), short_cite="c",
                quoted="0.1 as printed", unit="fraction of something",
                refresh_group="some.release")
    base.update(over)
    return Anchor(**base)


def _insured_qc(**over):
    """A Québec purchase under 20% down: the loader prices the CMHC premium and
    the 9% Québec tax on it — the one applied schedule anchor dated today."""
    cfg = {
        "years": 10, "discount_rate": 0.03, "rates": "real", "province": "QC",
        "house": {"initial_value": 500_000, "value_growth_rate": 0.0,
                  "down_payment": 75_000, "mortgage_rate": 0.04,
                  "mortgage_term_years": 25, "mortgage_insurance": "auto"},
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                 "invested_down_payment": 75_000, "investment_return_rate": 0.03},
    }
    cfg.update(over)
    return cfg


def _taxed_qc(**over):
    """A `tax:` block resolving its rate from the 2026 Québec brackets at $80,000,
    with a Home Buyers' Plan withdrawal (the 2026–2028 grace anchor)."""
    cfg = {
        "years": 10, "discount_rate": 0.03, "rates": "real", "province": "QC",
        "house": {"initial_value": 500_000, "value_growth_rate": 0.0,
                  "down_payment": 100_000, "mortgage_rate": 0.04,
                  "mortgage_term_years": 25, "first_time_buyer": True},
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                 "invested_down_payment": 100_000, "investment_return_rate": 0.03},
        "income": {"annual_income": 80_000},
        "tax": {"renter_capital": {"tfsa": 50_000, "rrsp": 20_000, "taxable": 30_000},
                "hbp_withdrawal": 15_000},
    }
    cfg.update(over)
    return cfg


def _plain():
    """No schedule priced, nothing declared: only the engine's own defaults."""
    return {
        "years": 10, "discount_rate": 0.03, "rates": "real",
        "condo": {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True},
        "rent": {"monthly_rent": 1_800, "rent_escalation_rate": 0.0},
    }


def _validity(warnings):
    return [w for w in warnings if PAST in w]


# ---------------------------------------------------------------------------
# The field
# ---------------------------------------------------------------------------

class TestField:
    def test_defaults_to_empty(self):
        assert _anchor().valid_until == ""

    def test_accepts_an_iso_date(self):
        assert _anchor(valid_until="2026-12-31").valid_until == "2026-12-31"

    @pytest.mark.parametrize("bad", ["2026-13-01", "31/12/2026", "2026", "December 31, 2026",
                                     "2026-12-31T00:00", " 2026-12-31"])
    def test_refuses_anything_but_an_iso_date(self, bad):
        with pytest.raises(AnchorError, match="valid_until"):
            _anchor(valid_until=bad)

    def test_print_anchors_carries_the_field(self):
        printed = anchors_to_dict()
        for name, doc in printed.items():
            assert "valid_until" in doc, name
        assert printed["mortgage_insurance.premium_tax_rate.qc"]["valid_until"] == "2026-12-31"
        assert printed["rent.investment_return_rate"]["valid_until"] == ""

    def test_the_cli_dump_carries_the_field(self, monkeypatch, capsys):
        from hde.cli import main
        monkeypatch.setattr(sys, "argv", ["hde", "--print-anchors"])
        assert main() == 0
        dump = json.loads(capsys.readouterr().out)
        assert dump["hbp.repayment_grace_years"]["valid_until"] == "2028-12-31"


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_exactly_the_scheduled_anchors_carry_a_date(self):
        dated = {n: a.valid_until for n, a in ANCHORS.items() if a.valid_until}
        assert dated == DATED

    def test_a_bracket_rate_is_never_dated(self):
        """Revenu Québec: the thresholds are indexed 'whereas the income tax
        rates remain unchanged' — a rate's source names no change, so the
        warning's sentence would be false of it."""
        for name, anchor in ANCHORS.items():
            if name.endswith("_rate") and name.startswith("tax."):
                assert anchor.valid_until == "", name

    def test_every_dated_anchor_says_so_in_its_rationale(self):
        for name, anchor in ANCHORS.items():
            if anchor.valid_until:
                assert anchor.valid_until in anchor.rationale, name

    def test_no_dated_anchor_is_past_today(self):
        """Turns red on the first day a dated figure lapses — re-read the
        source, update the anchor (`replaces` if the value moved), move or
        clear the date. Until then every example runs silent."""
        today = datetime.date.today()
        lapsed = {n: a.valid_until for n, a in ANCHORS.items()
                  if a.valid_until and datetime.date.fromisoformat(a.valid_until) < today}
        assert not lapsed, f"anchors past their validity date on {today}: {lapsed}"


# ---------------------------------------------------------------------------
# What a run uses
# ---------------------------------------------------------------------------

class TestAnchorsInUse:
    def test_a_plain_run_uses_its_applied_defaults_and_nothing_else(self):
        used = anchors_in_use(load_config_dict(_plain()))
        assert "rent.investment_return_rate" in used
        assert "condo.house.selling_cost_rate" in used          # the echo alias resolves
        assert not any(n.startswith(("tax.", "fhsa.", "hbp.", "tfsa.",
                                     "mortgage_insurance.", "land_transfer_tax.",
                                     "property_tax.", "mortgage_rate.")) for n in used)

    def test_a_declared_anchor_counts_once(self):
        cfg = _plain()
        cfg["rent"]["investment_return_rate"] = 0.03
        cfg["sources"] = {"rent.investment_return_rate": "anchor:rent.investment_return_rate"}
        used = anchors_in_use(load_config_dict(cfg))
        assert used.count("rent.investment_return_rate") == 1

    def test_an_insured_quebec_mortgage_uses_the_band_and_the_tax(self):
        used = anchors_in_use(load_config_dict(_insured_qc()))
        # $75,000 on $500,000 is 85.00% loan-to-value: the 80.01%–85% band, edge inclusive
        assert "mortgage_insurance.premium_rate.ltv_80_85" in used
        assert "mortgage_insurance.premium_tax_rate.qc" in used
        assert "mortgage_insurance.amortization_surcharge" not in used  # 25-year amortization
        assert "mortgage_insurance.premium_rate.ltv_85_90" not in used
        assert "mortgage_insurance.max_ltv" not in used

    def test_an_explicit_schedule_uses_no_anchor(self):
        cfg = _insured_qc()
        cfg["house"]["mortgage_insurance"] = {
            "bands": [{"ltv_max": 0.95, "rate": 0.04}], "premium_tax_rate": 0.0}
        assert not any(n.startswith("mortgage_insurance.") for n in anchors_in_use(load_config_dict(cfg)))

    def test_a_montreal_transfer_tax_uses_the_brackets_the_price_reached(self):
        cfg = _insured_qc()
        cfg["house"].update({"land_transfer_tax": "auto", "municipality": "montreal",
                             "first_time_buyer": True})
        used = anchors_in_use(load_config_dict(cfg))
        assert "land_transfer_tax.montreal.to_62900" in used
        assert "land_transfer_tax.montreal.to_552300" in used            # $500,000 sits here
        assert "land_transfer_tax.montreal.to_1104700" not in used
        # the flag was set and Montréal has no anchored figure: the unsourced entry
        # is what the read-back names, so it counts as consulted
        assert "land_transfer_tax.montreal.first_time_buyer_rebate" in used

    def test_a_resolved_tax_rate_uses_the_brackets_the_income_reached(self):
        used = anchors_in_use(load_config_dict(_taxed_qc()))
        assert {"tax.federal.bracket_1_ceiling", "tax.federal.bracket_2_ceiling",
                "tax.federal.bracket_2_rate", "tax.qc.bracket_1_ceiling",
                "tax.qc.bracket_2_ceiling", "tax.qc.bracket_2_rate",
                "tax.federal.quebec_abatement", "tax.capital_gains_inclusion_rate",
                "tax.principal_residence_exempt_fraction",
                "hbp.withdrawal_limit", "hbp.repayment_years", "hbp.repayment_grace_years",
                } <= set(used)
        assert "tax.federal.bracket_3_ceiling" not in used
        assert "tax.federal.bracket_1_rate" not in used
        assert not any(n.startswith(("tax.on.", "fhsa.")) for n in used)
        assert "tfsa.cumulative_room_since_2009" in used   # the TFSA share was checked against it

    def test_a_typed_tax_rate_uses_no_bracket(self):
        cfg = _taxed_qc()
        cfg["tax"]["marginal_rate"] = 0.40
        del cfg["income"]
        used = anchors_in_use(load_config_dict(cfg))
        assert not any(".bracket_" in n or "abatement" in n for n in used)

    def test_ontario_uses_the_surtax_and_the_basic_personal_amount(self):
        cfg = _taxed_qc(province="ON")
        cfg["income"]["annual_income"] = 150_000
        used = anchors_in_use(load_config_dict(cfg))
        assert {"tax.on.basic_personal_amount", "tax.on.surtax_1_threshold",
                "tax.on.surtax_2_threshold", "tax.on.surtax_1_rate", "tax.on.surtax_2_rate",
                "tax.on.bracket_1_rate", "tax.on.bracket_2_rate", "tax.on.bracket_3_rate",
                "tax.federal.bracket_3_rate"} <= set(used)
        # the surtax base sums every Ontario tranche; the federal side reads one rate
        assert "tax.federal.bracket_1_rate" not in used
        assert "tax.federal.quebec_abatement" not in used


# ---------------------------------------------------------------------------
# The warning
# ---------------------------------------------------------------------------

TEXT = ("anchor mortgage_insurance.premium_tax_rate.qc (0.09) is past its validity date "
        "2026-12-31: the source says the figure changes after that date — re-read "
        "Revenu Québec IPT before relying on the run")


class TestWarning:
    def test_a_priced_schedule_past_its_date_warns_with_the_exact_text(self):
        spec = load_config_dict(_insured_qc())
        assert validity_warnings(spec, datetime.date(2027, 1, 1)) == [TEXT]

    def test_the_date_itself_is_still_valid(self):
        spec = load_config_dict(_insured_qc())
        assert validity_warnings(spec, datetime.date(2026, 12, 31)) == []

    def test_an_applied_default_past_its_date_warns(self, monkeypatch):
        anchor = ANCHORS["rent.investment_return_rate"]
        # Dating an anchor that was not dated means owing what a dated anchor
        # owes (board item 6): the quote, the base, and the release that
        # publishes the replacement.
        monkeypatch.setitem(ANCHORS, anchor.name, dataclasses.replace(
            anchor, valid_until="2026-06-30", refresh_group="fp_canada.pag",
            quoted="60/40 balanced portfolio ≈ 3.0% real",
            unit="fraction of invested capital per year, real"))
        spec = load_config_dict(_plain())
        assert "rent.investment_return_rate" in spec.defaults_applied
        lines = validity_warnings(spec, datetime.date(2026, 9, 8))
        assert lines == [
            "anchor rent.investment_return_rate (0.03) is past its validity date 2026-06-30: "
            "the source says the figure changes after that date — re-read FP Canada 2026 PAG "
            "before relying on the run"]
        assert validity_warnings(spec, datetime.date(2026, 6, 30)) == []

    def test_a_declared_anchor_past_its_date_warns_once(self):
        """The TFSA share declared as the cumulative room — a reference anchor
        the run also checks the share against: one line, not two."""
        cfg = _taxed_qc()
        cfg["tax"]["renter_capital"] = {"tfsa": 109_000, "rrsp": 20_000, "taxable": 0}
        cfg["rent"]["invested_down_payment"] = 129_000
        cfg["sources"] = {"tax.renter_capital.tfsa": "anchor:tfsa.cumulative_room_since_2009"}
        spec = load_config_dict(cfg)
        lines = validity_warnings(spec, datetime.date(2027, 1, 1))
        room = [l for l in lines if l.startswith("anchor tfsa.cumulative_room_since_2009 ")]
        assert len(room) == 1
        assert room[0] == ("anchor tfsa.cumulative_room_since_2009 (109000) is past its validity "
                           "date 2026-12-31: the source says the figure changes after that date "
                           "— re-read CRA TFSA before relying on the run")
        assert validity_warnings(spec, datetime.date(2026, 12, 31)) == []

    def test_a_tax_block_past_the_year_names_only_the_brackets_it_reached(self):
        spec = load_config_dict(_taxed_qc())
        lines = validity_warnings(spec, datetime.date(2027, 1, 1))
        names = [l.split(" ")[1] for l in lines]
        assert "tax.federal.bracket_2_ceiling" in names
        assert "tax.federal.bracket_3_ceiling" not in names
        assert "tax.qc.bracket_2_rate" not in names          # rates carry no date
        assert "tfsa.cumulative_room_since_2009" in names
        assert "hbp.repayment_grace_years" not in names       # valid through 2028
        assert len(names) == len(set(names))

    def test_the_grace_anchor_lapses_after_2028(self):
        spec = load_config_dict(_taxed_qc())
        lines = validity_warnings(spec, datetime.date(2029, 1, 1))
        assert ("anchor hbp.repayment_grace_years (5) is past its validity date 2028-12-31: "
                "the source says the figure changes after that date — re-read CRA HBP before "
                "relying on the run") in lines
        assert not any("hbp.repayment_grace_years" in l
                       for l in validity_warnings(spec, datetime.date(2028, 12, 31)))

    def test_an_unused_reference_anchor_never_warns(self):
        spec = load_config_dict(_plain())
        assert validity_warnings(spec, datetime.date(2035, 1, 1)) == []

    def test_all_warnings_carries_it_and_defaults_to_today(self):
        spec = load_config_dict(_insured_qc())
        assert _validity(all_warnings(spec)) == []
        assert _validity(all_warnings(spec, run_date=datetime.date(2027, 1, 1))) == [TEXT]

    def test_the_cli_reads_the_wall_clock_at_the_edge(self, tmp_path, monkeypatch, capsys):
        """--json `warnings` and the read-back carry the line once the date passes."""
        import yaml
        from hde.cli import main

        class _Date(datetime.date):
            @classmethod
            def today(cls):
                return cls(2027, 1, 1)

        path = tmp_path / "cfg.yaml"
        path.write_text(yaml.safe_dump(_insured_qc(), sort_keys=False), encoding="utf-8")
        monkeypatch.setattr(datetime, "date", _Date)
        monkeypatch.setattr(sys, "argv", ["hde", str(path), "--json", "--no-monte-carlo"])
        assert main() == 0
        out = capsys.readouterr()
        doc = json.loads(out.out)
        assert doc["warnings"].count(TEXT) == 1
        assert f"[warning] {TEXT}" in doc["assumptions"]["read_back"]
        assert f"[warning] {TEXT}" in out.err


# ---------------------------------------------------------------------------
# The examples today
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.yaml")))
def test_every_example_runs_silent_today(name):
    """No dated anchor has lapsed, so the seven read-backs are the same bytes
    they were before the field existed. When `test_no_dated_anchor_is_past_today`
    goes red, so does whichever of these prices the lapsed figure."""
    spec = load_config(EXAMPLES / name)
    assert _validity(all_warnings(spec)) == []
