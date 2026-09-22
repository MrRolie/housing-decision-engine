"""The refresh path: how a figure gets replaced by someone who did not fetch it
(board item 6, 2026-09-22; design `docs/specs/2026-09-22-anchor-refresh-path.md`).

`tests/test_anchor_validity.py` covers the alarm — `valid_until`, the warning a
run carries, and the day the suite turns red. This file covers the REPAIR: that
every dated figure names the release that publishes its replacement, that the
work order `hde --refresh-plan` prints carries what a stranger needs, and that
the three ways a hand refresh goes wrong each turn something red.

Each test here is named for the mistake it catches, and each was run against
that mistake before being trusted. The three that matter:

  * a value retyped, its `quoted` citation left stale
  * `as_of` moved to the new year, `valid_until` left at the old one
  * one sibling refreshed, the rest of the release left behind
"""

import dataclasses
import datetime
import json
import sys

import pytest

from hde.anchors import (
    ANCHORS,
    REFRESH_PROCEDURE,
    REFRESH_SOURCES,
    Anchor,
    AnchorError,
    RefreshSource,
    _RELEASE_EDITION,
    dated_anchors,
    refresh_group_members,
)
from hde.config import load_config_dict, validity_warnings
from hde.serialization import anchor_to_dict, refresh_plan

TODAY = datetime.date(2026, 9, 21)
LAPSED = datetime.date(2027, 1, 1)


def _anchor(**over):
    """A dated anchor that satisfies every rule, so a test can break exactly
    one of them."""
    base = dict(name="x.y", value=0.1, as_of="2026", source="s", url="u",
                rationale="r", band=(0.0, 1.0), short_cite="c",
                quoted="0.1 as printed", unit="fraction of something",
                valid_until="2026-12-31", refresh_group="some.release")
    base.update(over)
    return Anchor(**base)


def _source(**over):
    base = dict(key="some.release", publisher="p", edition="e",
                checked_on="2026-09-21", found="f")
    base.update(over)
    return RefreshSource(**base)


# ---------------------------------------------------------------------------
# A dated figure must say who will publish its replacement, and how it was printed
# ---------------------------------------------------------------------------

class TestWhatADatedAnchorOwes:
    def test_a_dated_anchor_must_name_the_release_that_publishes_it(self):
        """A `valid_until` promises the figure will be replaced. An anchor that
        makes that promise and cannot say who publishes the replacement leaves
        the repair in one person's head, which is the whole item."""
        with pytest.raises(AnchorError, match="refresh_group"):
            _anchor(refresh_group="")
        with pytest.raises(AnchorError, match="refresh_group"):
            _anchor(refresh_group="   ")

    @pytest.mark.parametrize("field", ["quoted", "unit"])
    def test_a_dated_anchor_must_carry_the_figure_as_quoted(self, field):
        """To replace a figure correctly you must see how the source printed it
        and what it was a rate or an amount OF. Reference entries have owed both
        since 2026-09-01 for a different reason; a dated entry owes them for the
        refresh."""
        with pytest.raises(AnchorError, match=field):
            _anchor(**{field: ""})

    def test_an_undated_anchor_owes_none_of_the_three(self):
        """The rule is scoped to figures that say they will change — not a
        blanket tightening that would make half the registry illegal."""
        assert _anchor(valid_until="", refresh_group="", quoted="", unit="").name == "x.y"

    def test_the_registry_itself_passes_all_three(self):
        for name in dated_anchors():
            anchor = ANCHORS[name]
            assert anchor.refresh_group.strip(), name
            assert anchor.quoted.strip(), name
            assert anchor.unit.strip(), name


# ---------------------------------------------------------------------------
# The release records
# ---------------------------------------------------------------------------

class TestRefreshSources:
    def test_every_dated_anchor_names_a_registered_refresh_source(self):
        """A typo'd or deleted group name leaves a dated figure with a publisher
        nobody can look up. `__post_init__` cannot catch this one: it sees the
        anchor, not the registry."""
        missing = {n: ANCHORS[n].refresh_group for n in dated_anchors()
                   if ANCHORS[n].refresh_group not in REFRESH_SOURCES}
        assert not missing, f"dated anchors naming an unregistered release: {missing}"

    def test_every_refresh_source_covers_a_dated_anchor(self):
        """A record left behind after its anchors went is a source nobody reads
        and a check nobody needs — and it would print an empty group in the work
        order."""
        orphans = {key for key in REFRESH_SOURCES
                   if not any(ANCHORS[n].valid_until for n in refresh_group_members(key))}
        assert not orphans, f"refresh records covering no dated anchor: {sorted(orphans)}"

    def test_every_release_declares_exactly_one_edition(self):
        """One row per release, and a release is the unit a refresh moves.

        Until 2026-09-22 this was not true of the registry: five releases read a
        shared `_TAX_RETRIEVED` and four a shared `_TAX_YEAR_END`, so the
        refresh the repo tells a stranger to perform could not be performed. The
        CRA publishes its indexation in November and Revenu Québec its
        parameters in December; a refresher updating the federal figures had to
        move a constant that also stamped Québec's and Ontario's, silently
        restating four releases as read on a day nobody read them — and every
        release stayed internally coherent while three of them lied.
        """
        assert set(_RELEASE_EDITION) == set(REFRESH_SOURCES), {
            "editions with no record": sorted(set(_RELEASE_EDITION) - set(REFRESH_SOURCES)),
            "records with no edition": sorted(set(REFRESH_SOURCES) - set(_RELEASE_EDITION)),
        }

    def test_every_member_carries_its_releases_edition(self):
        """THE SIBLING GUARD. The four federal bracket ceilings and the federal
        basic personal amount are one CRA release, not five facts. Every member
        takes its vintage and its retrieval date from that release's single
        declared edition — so refreshing one member and leaving the rest behind
        is not merely caught, it is unwriteable without editing an anchor to
        disagree with its own release.

        Honest about its reach: `test_tax_anchors.py` already pins
        `as_of == "2026"` and `retrieved_on == "2026-09-05"` as literals across
        the whole tax family, so a partial edit there fails twice today. This
        check earns its place on the small groups, and it is the one that keeps
        working after those literals are updated to the 2027 pass — a relation
        to the declared edition survives the edit that a literal does not.
        """
        for key, (as_of, retrieved_on, valid_until) in _RELEASE_EDITION.items():
            members = refresh_group_members(key)
            assert members, f"{key}: an edition nothing reads"
            for name in members:
                anchor = ANCHORS[name]
                assert anchor.as_of == as_of, (
                    f"{name}: vintage {anchor.as_of} against its release's {as_of} "
                    f"— one release publishes one edition, so part of {key} was "
                    f"refreshed and part was not")
                assert anchor.retrieved_on == retrieved_on, (
                    f"{name}: read {anchor.retrieved_on} against its release's "
                    f"{retrieved_on} — a release is read in one pass")
                assert anchor.valid_until in ("", valid_until), (
                    f"{name}: lapses {anchor.valid_until} against its release's "
                    f"{valid_until} — a dated member takes the release's date, "
                    f"an undated sibling takes none")
            assert any(ANCHORS[n].valid_until for n in members), (
                f"{key}: no member carries a validity date, so nothing here is "
                f"on the refresh path at all")

    def test_a_check_record_says_when_someone_looked_and_what_was_there(self):
        """The 'nobody has published it yet' state. Without a date and a finding
        it is indistinguishable from nobody having looked, which is exactly the
        reading this item exists to prevent."""
        for field in ("publisher", "edition", "checked_on", "found"):
            with pytest.raises(AnchorError, match=field):
                _source(**{field: ""})
        with pytest.raises(AnchorError, match="checked_on"):
            _source(checked_on="September 2026")
        with pytest.raises(AnchorError, match="checked_on"):
            _source(checked_on="2026-13-01")


# ---------------------------------------------------------------------------
# The two half-finished edits
# ---------------------------------------------------------------------------

# Dated dollar figures the source does NOT print, with the reason. A new one
# must quote its figure or be declared here — the pattern `CONSUMED_ELSEWHERE`
# in test_anchors.py already uses.
DERIVED_NOT_PRINTED = {
    "tfsa.cumulative_room_since_2009":
        "the SUM of the quoted annual-limit table; no CRA page prints the total, "
        "and test_tax_anchors.test_tfsa_cumulative_room_is_the_sum_of_the_quoted_table "
        "pins it against that arithmetic",
}


class TestTheHalfFinishedRefresh:
    def test_a_dated_dollar_figure_is_quoted_as_its_source_prints_it(self):
        """THE CITATION GUARD. Retype a ceiling and leave `quoted` alone and the
        registry states one figure while citing another — the exact shape of a
        registry rotting quietly. Scoped to dated anchors whose `unit` is stated
        in dollars, because that is where the source prints a separated amount.
        """
        for name in dated_anchors():
            anchor = ANCHORS[name]
            if not anchor.unit.strip().lower().startswith("dollars"):
                continue
            if name in DERIVED_NOT_PRINTED:
                continue
            printed = f"{anchor.value:,.0f}"
            assert printed in anchor.quoted, (
                f"{name}: registers {printed} but its quote of the source reads "
                f"{anchor.quoted!r} — the value was changed and the citation was "
                f"not, or the wrong figure was read off the page")

    def test_the_declared_exemptions_are_still_exemptions(self):
        """A declaration that has stopped being true is a hole in the guard: if
        the CRA starts printing the total, the entry must leave this list."""
        for name in DERIVED_NOT_PRINTED:
            assert name in dated_anchors(), f"{name}: declared derived but not dated"
            printed = f"{ANCHORS[name].value:,.0f}"
            assert printed not in ANCHORS[name].quoted, (
                f"{name}: its source now prints {printed}; drop it from "
                f"DERIVED_NOT_PRINTED so the citation guard covers it")

    def test_a_refreshed_figure_cannot_outlive_its_own_vintage(self):
        """THE DATE GUARD. Move `as_of` to the new year and leave `valid_until`
        at the old one and the registry ships a 2027 figure that claims to lapse
        in 2026 — it warns on every run from day one and nobody can tell a real
        lapse from a forgotten field."""
        for name in dated_anchors():
            anchor = ANCHORS[name]
            vintage = int(anchor.as_of[:4])
            lapses = int(anchor.valid_until[:4])
            assert lapses >= vintage, (
                f"{name}: as_of {anchor.as_of} but valid_until {anchor.valid_until} "
                f"— a figure published for {vintage} cannot have stopped being the "
                f"figure in {lapses}; one of the two was not moved")


# ---------------------------------------------------------------------------
# The work order
# ---------------------------------------------------------------------------

class TestThePlan:
    def test_the_plan_carries_every_dated_anchor(self):
        """A group silently dropped is a figure nobody is told to refresh."""
        plan = refresh_plan(TODAY)
        listed = [a["name"] for g in plan["groups"] for a in g["dated"]]
        assert sorted(listed) == sorted(dated_anchors())
        assert len(listed) == len(set(listed)), "an anchor listed under two releases"
        assert plan["dated_anchors"] == len(listed)

    def test_the_plan_ranks_by_how_soon_a_figure_lapses(self):
        groups = refresh_plan(TODAY)["groups"]
        assert [g["valid_until"] for g in groups] == sorted(g["valid_until"] for g in groups)
        assert groups[-1]["group"] == "cra.home_buyers_plan"   # 2028, the one that is not this year

    def test_the_plan_splits_dated_members_from_their_undated_siblings(self):
        """The split is what a refresher must not get wrong: a rate carries no
        validity date because its source names no change to it, but it comes off
        the same page and is re-read in the same pass."""
        plan = refresh_plan(TODAY)
        federal = next(g for g in plan["groups"] if g["group"] == "cra.federal_indexation")
        assert {a["name"] for a in federal["dated"]} == {
            "tax.federal.bracket_1_ceiling", "tax.federal.bracket_2_ceiling",
            "tax.federal.bracket_3_ceiling", "tax.federal.bracket_4_ceiling",
            "tax.federal.basic_personal_amount"}
        assert {a["name"] for a in federal["undated_siblings"]} == {
            f"tax.federal.bracket_{k}_rate" for k in range(1, 6)}
        for g in plan["groups"]:
            for a in g["dated"]:
                assert a["valid_until"], a["name"]
            for a in g["undated_siblings"]:
                assert not a["valid_until"], a["name"]

    def test_the_plan_hands_over_the_whole_anchor_record(self):
        """A refresher needs the figure as quoted, its unit, its source and its
        URL — and it must be the SAME record `--print-anchors` prints, not a
        second shape that can drift from it."""
        plan = refresh_plan(TODAY)
        for g in plan["groups"]:
            for doc in g["dated"] + g["undated_siblings"]:
                assert doc == anchor_to_dict(ANCHORS[doc["name"]])
                assert doc["source"].strip() and doc["url"].strip()
            for doc in g["dated"]:
                assert doc["quoted"].strip() and doc["unit"].strip()

    def test_the_plan_resolves_an_empty_url_to_the_anchors_own_sources(self):
        """An empty `url` on a record MEANS 'the page the anchors already cite',
        which is true wherever a page is republished in place. The work order
        must resolve it rather than hand a refresher a blank."""
        plan = refresh_plan(TODAY)
        for g in plan["groups"]:
            assert g["where_to_look"], g["group"]
            if not g["url"]:
                assert set(g["where_to_look"]) <= {a["url"] for a in g["dated"]}, g["group"]
            else:
                assert g["where_to_look"] == [g["url"]], g["group"]

    def test_the_plan_carries_the_procedure(self):
        """The steps of a correct refresh live in the repo's own bytes, not in
        docs/specs/ — the person doing this in 2027 has the CLI and may not have
        the build record (artifact boundary, clauses 1 and 4)."""
        plan = refresh_plan(TODAY)
        assert plan["procedure"] == list(REFRESH_PROCEDURE)
        joined = " ".join(plan["procedure"])
        assert "replaces" in joined and "restatements" in joined
        assert "change NO value" in joined

    def test_the_plan_reports_the_successor_that_is_already_published(self):
        """Québec's IPT is the one figure whose replacement is enacted law today.
        The work order must distinguish 'go and fetch' from 'apply the figure
        this anchor's own source already states, on its date' — otherwise a
        refresher goes looking for a publication that will never come."""
        plan = refresh_plan(TODAY)
        by_key = {g["group"]: g for g in plan["groups"]}
        assert by_key["revenu_quebec.insurance_premium_tax"]["successor_published"] is True
        assert all(not g["successor_published"] for k, g in by_key.items()
                   if k != "revenu_quebec.insurance_premium_tax")

    def test_the_plan_counts_what_has_lapsed_against_its_own_date(self):
        assert refresh_plan(TODAY)["lapsed_anchors"] == 0
        assert all(not g["lapsed"] for g in refresh_plan(TODAY)["groups"])
        # the nineteen that lapse 2026-12-31; the HBP grace runs to 2028
        assert refresh_plan(LAPSED)["lapsed_anchors"] == 19
        assert refresh_plan(datetime.date(2026, 12, 31))["lapsed_anchors"] == 0
        assert refresh_plan(datetime.date(2029, 1, 1))["lapsed_anchors"] == 20

    def test_days_remaining_counts_down_to_the_date_itself(self):
        plan = refresh_plan(datetime.date(2026, 12, 30))
        first = plan["groups"][0]
        assert first["valid_until"] == "2026-12-31" and first["days_remaining"] == 1
        assert refresh_plan(LAPSED)["groups"][0]["days_remaining"] == -1


class TestThePlanAgreesWithTheRun:
    def test_every_anchor_a_run_warns_about_is_on_the_plan_as_lapsed(self):
        """Two surfaces read `valid_until` — the run's warning and the work
        order. If they ever disagree, a user is told a figure went stale and the
        refresher is not told to fix it."""
        cfg = {
            "years": 10, "discount_rate": 0.03, "rates": "real", "province": "QC",
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0,
                      "down_payment": 75_000, "mortgage_rate": 0.04,
                      "mortgage_term_years": 25, "mortgage_insurance": "auto"},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 75_000, "investment_return_rate": 0.03},
            "income": {"annual_income": 80_000},
            # the shares total the renter's invested capital, as the loader requires
            "tax": {"renter_capital": {"tfsa": 40_000, "rrsp": 20_000, "taxable": 15_000}},
        }
        spec = load_config_dict(cfg)
        warned = {line.split(" ")[1] for line in validity_warnings(spec, LAPSED)}
        assert warned, "the fixture must actually use dated anchors"
        on_plan = {a["name"] for g in refresh_plan(LAPSED)["groups"] if g["lapsed"]
                   for a in g["dated"]}
        assert warned <= on_plan, sorted(warned - on_plan)


# ---------------------------------------------------------------------------
# The CLI surface
# ---------------------------------------------------------------------------

class TestTheCli:
    def _run(self, monkeypatch, capsys, *argv):
        from hde.cli import main
        monkeypatch.setattr(sys, "argv", ["hde", *argv])
        code = main()
        return code, capsys.readouterr()

    def test_the_flag_prints_the_plan_and_exits_zero_while_every_figure_holds(
            self, monkeypatch, capsys):
        code, out = self._run(monkeypatch, capsys, "--refresh-plan",
                              "--refresh-plan-as-of", "2026-09-21")
        assert code == 0
        doc = json.loads(out.out)
        assert doc == refresh_plan(TODAY)
        assert out.err == ""

    def test_the_cli_refuses_once_a_figure_has_lapsed(self, monkeypatch, capsys):
        """A registry stating figures their own sources say have changed is a
        surface that cannot verify, so it refuses rather than reporting success
        (AGENTS.md, artifact boundary clause 3). A figure still in force is
        information: a gate that went red for the three months before an edition
        is published, with nothing to fetch, would be a red that means nothing.
        """
        code, out = self._run(monkeypatch, capsys, "--refresh-plan",
                              "--refresh-plan-as-of", "2027-01-01")
        assert code == 3
        assert "REFUSING" in out.err and "19" in out.err
        assert json.loads(out.out)["lapsed_anchors"] == 19

        held, out = self._run(monkeypatch, capsys, "--refresh-plan",
                              "--refresh-plan-as-of", "2026-12-31")
        assert held == 0 and "REFUSING" not in out.err

    def test_a_date_that_is_not_a_date_is_refused_rather_than_guessed(
            self, monkeypatch, capsys):
        code, out = self._run(monkeypatch, capsys, "--refresh-plan",
                              "--refresh-plan-as-of", "Jan 2027")
        assert code == 1
        assert "ISO date" in out.err and out.out == ""

    def test_the_flag_defaults_to_the_wall_clock(self, monkeypatch, capsys):
        code, out = self._run(monkeypatch, capsys, "--refresh-plan")
        assert code == 0
        assert json.loads(out.out)["as_of"] == datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# What the registry says today (2026-09-21)
# ---------------------------------------------------------------------------

class TestTodaysRegistry:
    """TODAY-PINS, in the `test_no_dated_anchor_is_past_today` pattern: each
    records a decision this pass made about what NOT to put in the registry, and
    each goes red on the legitimate refresh that supersedes it. That is the
    point of them — the refresher is meant to have to look at the decision and
    replace it, not to inherit it silently. None of them can tell an invented
    figure from a published one; the guards above do that work.
    """

    def test_the_one_published_successor_is_not_applied(self):
        """Bill 99 is enacted and the 2027 Québec IPT rate is 9.975%. The engine
        still applies 9%, because 9% is the correct rate for a premium paid on or
        before 2026-12-31 and the engine holds one figure per key. The successor
        is recorded on the release, and its figure stays where every figure in
        this registry lives — the anchor's own source, band and rationale.

        Red on 2027-01-01, when the value becomes 0.09975 and `replaces` records
        the step."""
        anchor = ANCHORS["mortgage_insurance.premium_tax_rate.qc"]
        assert anchor.value == 0.09
        assert anchor.band == (0.09, 0.09975)
        assert "9.975" in anchor.quoted and "January 1st, 2027" in anchor.quoted
        record = REFRESH_SOURCES["revenu_quebec.insurance_premium_tax"]
        assert record.successor_published is True
        assert "not changed today" in record.found.lower()

    def test_nothing_carries_a_third_partys_projection(self):
        """The 2027 TFSA limit is projected at $7,500 by press reporting. It is
        not the publisher's figure, so it is not in the registry — and the
        release record says why in as many words, which is the sentence the next
        refresher has to delete deliberately rather than drift past.

        Red when the CRA announces and the anchor takes the published limit."""
        assert ANCHORS["tfsa.annual_limit"].value == 7_000.0
        found = REFRESH_SOURCES["cra.tfsa_limit"].found
        assert "projection is not the publisher's figure" in found


# ---------------------------------------------------------------------------
# The registry's own dump
# ---------------------------------------------------------------------------

def test_print_anchors_carries_the_release_each_figure_comes_from():
    """A refresher who starts from `--print-anchors` must be able to get to the
    release without a second lookup."""
    from hde.serialization import anchors_to_dict
    printed = anchors_to_dict()
    for name in dated_anchors():
        assert printed[name]["refresh_group"] == ANCHORS[name].refresh_group
        assert printed[name]["refresh_group"] in REFRESH_SOURCES
    assert printed["rent.investment_return_rate"]["refresh_group"] == ""


def test_a_dated_anchor_added_without_a_release_cannot_be_registered():
    """The end-to-end shape of the guard: `dataclasses.replace` on a live anchor
    is how a refresh edit is modelled in tests, and it goes through the same
    __post_init__ a source edit does."""
    anchor = ANCHORS["tfsa.annual_limit"]
    with pytest.raises(AnchorError, match="refresh_group"):
        dataclasses.replace(anchor, refresh_group="")
    with pytest.raises(AnchorError, match="quoted"):
        dataclasses.replace(anchor, quoted="")
