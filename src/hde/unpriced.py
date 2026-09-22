"""Dimensions this RUN does not price, measured on this run's own numbers.

Design: docs/specs/2026-09-21-unpriced-dimensions.md. Slice 1 (§16) is the
affordability application of §14 alone — one cited load, one ratio, one named
gap — and this module is its home.

WHAT SEPARATES THIS CHANNEL FROM THE OTHERS (spec §8). A coherence warning says
a dimension is switched off and names the input that switches it on. A
`no anchor match` line says a figure inside the model has no citation. This
line says: the number the run DID print is priced against a rule the run does
not apply, and here is that number under the rule, solved from the user's own
config.

THE GUARD (spec §5), which is the whole reason the channel is honest: **the
line prints a number solved from this run, and the same feature must be able to
print nothing. A line that cannot come out silent is a disclaimer. A line that
can is a measurement.** Four ways this one comes out silent, all reachable:

1. no `income:` block, so there is no ratio to load (a present-value-only run);
2. no financed owned option — an all-cash purchase is never stress-tested;
3. no rate AS QUOTED to load (a spec built in code rather than from YAML, or no
   raw mapping to reload): the spread is defined on the quoted axis and adding
   it to an effective annual figure would understate the test, so the surface
   REFUSES rather than print a figure it cannot place on an axis;
4. the loader refuses the reloaded config at the qualifying rate.

THE RULE IS NOT THE ENGINE'S. `qualifying_rate.buffer` and
`qualifying_rate.floor` are OSFI's two legs of one published sentence
(`anchors.MQR_RULE`, which the line cites by name rather than quoting),
applied here and nowhere else: no default falls back to either, no present
value moves with them, no verdict reads them. Spec §2 — the
engine may choose the SHAPE of a counterfactual, never its MAGNITUDE; this
magnitude is a citation, not a convention the engine imported.

AND IT IS A TEST ON ONE TRANSACTION, WHICH THE LINE MUST NAME. The minimum
qualifying rate is an ORIGINATION test. Every owned option in this engine
starts at a purchase, so on a run that prices only that purchase the sentence
is exactly true; on a run that ALSO prices a renewal it read as a standing
verdict on the household, and since 2024-11-21 that is false — OSFI no longer
prescribes the rate for an uninsured straight switch at renewal. So the line
says which transaction its figures describe and names the exemption as a case
it does not price, never as one it claims for the user. The whole argument,
including why the insured branch reports an absent source instead of borrowing
the other branch's exemption, is in `straight_switch_clause` and in the scope
paragraph both anchors carry.

AND IT IS NOT A LENDER'S ANSWER. `income.affordability_threshold`'s own
rationale records that this engine's numerator is BROADER than the gross debt
service a lender measures — full condo fees, maintenance, stochastic events.
So the line prints the ratio on the engine's own measure, NAMES that gap, and
never says the household would fail to qualify. The engine is not a lender and
does not have the lender's numerator; a sentence claiming otherwise is the one
that would fail contact with a reader (spec §14).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .anchors import ANCHORS
from .rates import effective_mortgage_rate

# The direction vocabulary, one home (spec §13). An omission's direction is
# which way it moves the verdict if it were priced: `coherence_warnings` writes
# these same three phrases and formats them from here.
TOWARD_BUYING = "toward buying"
TOWARD_RENTING = "toward renting"
NEUTRAL = "neutral"

# Spec §4: at most a small fixed number of unpriced lines per run. Two is the
# number of owned options a config can carry, so the cap binds only if a later
# slice adds a second dimension — which is the point of having it before then.
UNPRICED_LINE_CAP = 2

# The owned options, in the order every other warning list uses.
_OWNED = ("condo", "house")


@dataclass(frozen=True)
class QualifyingLoad:
    """One owned option's affordability ratio under the minimum qualifying
    rate, beside the ratio the run itself prices.

    Every rate here is stated on ITS OWN AXIS and says which: `*_quoted` are on
    the as-quoted axis the config types `mortgage_rate` on, `*_effective` are
    the effective annual rates the level payment uses. `mortgage_rate_
    compounding` is the only conversion between them, applied by the loader —
    this module never converts a rate itself.
    """

    option: str
    contract_quoted: float
    contract_effective: float
    qualifying_quoted: float
    qualifying_effective: float
    # Year 1, on both sides: the minimum qualifying rate is an ORIGINATION
    # test, and a max over the horizon would attribute to the load a peak that
    # a renewal step or a cost event put there.
    own_ratio_year1: float
    qualifying_ratio_year1: float
    # Whether the loader derived mortgage insurance on this option. It changes
    # WHOSE test is being cited: OSFI's minimum qualifying rate governs
    # UNINSURED mortgages, and on an insured loan the same two figures are the
    # federal government's (both citations are on the anchors). The formula is
    # the same today by decision, not by identity — so the line has to say
    # which authority applies to THIS loan.
    insured: bool
    # The year of the first renewal THIS RUN PRICES, or None when it prices
    # none. It answers WHICH TRANSACTION the figures above describe, which the
    # line was silently getting wrong: the minimum qualifying rate is an
    # ORIGINATION test, so on a run that also prices a renewal the same
    # sentence read as a standing verdict on the household. Read from
    # `renewals_priced_inside`, the one answer to "did the ladder reach this
    # run", so this can never name a step the verdict never saw.
    first_renewal_year: Optional[int] = None

    @property
    def lift(self) -> float:
        """Points of income the load adds — the size of what is unpriced."""
        return self.qualifying_ratio_year1 - self.own_ratio_year1


def qualifying_rate_quoted(contract_quoted: float) -> float:
    """OSFI's minimum qualifying rate for one contract rate, ON THE AS-QUOTED
    AXIS: the greater of the contract rate plus the buffer, or the floor.

    The contract rate goes in as the config typed it and the result comes out
    on the same axis, so `mortgage_rate_compounding` converts the SUM exactly
    as it converts the contract rate. Adding the buffer to an effective annual
    figure instead would convert the contract rate alone and understate the
    test by the compounding on the buffer.
    """
    return max(contract_quoted + ANCHORS["qualifying_rate.buffer"].value,
               ANCHORS["qualifying_rate.floor"].value)


def _ratios_for(det: Any, option: str) -> Optional[List[float]]:
    report = getattr(det, "income_report", None)
    if report is None:
        return None
    ratios = getattr(report, f"{option}_ratios", None)
    return ratios or None


def qualifying_loads(
    spec: Any,
    det: Any,
    raw: Optional[Dict[str, Any]] = None,
) -> List[QualifyingLoad]:
    """Every financed owned option's affordability ratio under the qualifying
    rate — empty when nothing qualifies, which is the guard above.

    The counterfactual is run the way `break_even._affordability_at` runs its
    own: set the option's `mortgage_rate` in the RAW mapping to the qualifying
    figure and reload. That is spec §14's sentence executed literally ("move
    `mortgage_rate` by the rule, run deterministically, read only the income
    report and discard the present value"), and it routes the figure through
    `mortgage_rate_compounding` by construction rather than by a conversion
    written here that could drift from the loader's.
    """
    # Lazy: `sweep` and `deterministic` import `config`, which imports the
    # direction vocabulary above. Keeping these inside the call keeps this
    # module's import surface to `anchors` + `rates`.
    from .config import ConfigValidationError
    from .deterministic import (
        compute_deterministic, renewal_segments_for, renewals_priced_inside)
    from .sweep import load_at

    if raw is None:
        return []
    horizon = spec.simulation.years
    out: List[QualifyingLoad] = []
    for option in _OWNED:
        opt = getattr(spec, option, None)
        if opt is None or getattr(opt, "all_cash", False):
            continue
        if opt.mortgage_rate is None or opt.mortgage_rate_quoted is None:
            # No rate, or no rate ON THE QUOTED AXIS: refuse rather than load a
            # spread onto a figure whose axis the run cannot establish.
            continue
        own = _ratios_for(det, option)
        if own is None:
            continue
        quoted = qualifying_rate_quoted(opt.mortgage_rate_quoted)
        try:
            stressed = compute_deterministic(
                load_at(raw, f"{option}.mortgage_rate", quoted))
        except (ConfigValidationError, ValueError):
            continue
        loaded = _ratios_for(stressed, option)
        if loaded is None:
            continue
        # WHICH TRANSACTION the figures describe. Gated on the renewals this
        # run actually PRICES, not on the ladder being stated: a first renewal
        # past the horizon reaches no payment and no PV (its own coherence
        # warning says so), and naming that year here would report a step the
        # verdict never saw. Segment start years are non-decreasing, so a
        # positive count means `segments[1]` is the priced one.
        first_renewal_year: Optional[int] = None
        if renewals_priced_inside(opt, horizon) > 0:
            segments = renewal_segments_for(opt)
            first_renewal_year = segments[1].start_year
        out.append(QualifyingLoad(
            option=option,
            contract_quoted=opt.mortgage_rate_quoted,
            contract_effective=opt.mortgage_rate,
            qualifying_quoted=quoted,
            qualifying_effective=effective_mortgage_rate(
                quoted, opt.mortgage_rate_compounding),
            own_ratio_year1=own[0],
            qualifying_ratio_year1=loaded[0],
            insured=bool(getattr(getattr(opt, "mortgage_insurance", None),
                                 "required", False)),
            first_renewal_year=first_renewal_year,
        ))
    # Spec §4, promotion: the bigger measured load leads. These lines' size is
    # in points of income, not present value, so the verdict's margin — which
    # orders the PV-sized dimensions — cannot rank them; within one class the
    # size that exists does. Stable, so the owned-option order breaks ties.
    return sorted(out, key=lambda load: -load.lift)[:UNPRICED_LINE_CAP]


def _rate(value: float) -> str:
    return f"{value:.2%}"


def straight_switch_clause(load: QualifyingLoad) -> str:
    """WHICH TRANSACTION the qualifying-rate figures price — empty when this
    run prices no renewal, which is most runs (spec §5: the addition must be
    able to come out silent, or it is a disclaimer riding on a measurement).

    THE DEFECT THIS FIXES (2026-09-21). The minimum qualifying rate is an
    ORIGINATION test and the line stated it in the engine's own voice as "the
    minimum qualifying rate a lender would test you at", with a citation
    attached. On a run that also prices a renewal that reads as a standing
    verdict on the household — and since 2024-11-21 it is not one, because
    OSFI no longer prescribes the MQR for an uninsured STRAIGHT SWITCH at
    renewal. The reader most likely to meet the sentence is the household
    already frightened by a payment jump, which is the first user this tool
    was written for (README, `docs/BOARD.md` item 5).

    WHAT THIS MAY NEVER SAY, and it is the whole difficulty (spec §15, and the
    scope paragraph on both anchors). A straight switch is defined by facts
    about the household's ACTUAL transaction — the amount carried over and the
    amortization kept — which no config states and no run observes. Taking
    money out or restretching the amortization puts them back inside the test.
    So the clause names the exemption as a case the run DOES NOT PRICE and
    never claims it for the user: told they are exempt when they are not, they
    meet a refusal at the branch, which is worse than the sentence it replaced.

    Two further things it must carry, both from the sources rather than from
    judgment:

    - the relief is from OSFI's PRESCRIBED rate, not from being assessed —
      OSFI still expects the loan assessed "like any other new origination"
      under Guideline B-20, with the new lender setting its own qualifying
      rate. Dropping that turns a scope limit into a promise;
    - the insured side is a DIFFERENT measure. `insured` here means the loader
      derived mortgage insurance, which happens only above the 80% line, so
      this engine's insured loan is HIGH-RATIO — and the federal removal
      (2024-12-16) is written for the renewal of a prior LOW-RATIO loan. No
      primary source was found either way for a high-ratio insured switch, so
      the branch reports the absence instead of borrowing the other branch's
      exemption.

    THE LINE CITES, THE ANCHORS RECITE (operator ruling, standing, 2026-09-21;
    ruled once before the same day when a guillemet quotation of the MQR
    sentence was cut from the line and the legs cited instead). The first draft
    of this clause ran 78 words and took the line to 205 — longer than a
    version already rejected for length. It taught the rule: the effective
    date, the three conditions of a straight switch, the B-20 mechanism. All of
    that is stored VERBATIM on `qualifying_rate.buffer` and
    `qualifying_rate.floor` and is one `--print-anchors` away, and none of it
    is the clause's job. The clause's job is to stop a reader concluding
    something false, in about forty words: which transaction the figure tests,
    that an exemption is not exemption from a lender's test, and that this run
    cannot see which case the household is in. The line rides verbatim into the
    read-back, and the reader it exists for is a household already frightened
    by a payment jump — a clause they do not finish protects nobody.
    """
    if load.first_renewal_year is None:
        return ""
    # The run-specific quantity, and the reason this is a measurement: the year
    # comes from this config's own ladder, and the sentence differs with it.
    head = (
        f" The figure tests the year-0 purchase, not the renewal this run prices "
        f"at year {load.first_renewal_year}:"
    )
    if load.insured:
        # The absence, reported. Not "you are tested" and not "you are exempt":
        # the low-ratio measure does not reach a loan that starts above the
        # line, and nothing else registered here does either.
        return head + (
            " the insured straight-switch removal is written for low-ratio loans and this "
            "one starts above that line, so no source here says it reaches you "
            "[qualifying_rate.buffer, qualifying_rate.floor]."
        )
    # Both hedges in one clause, refusing rather than explaining: PRESCRIBED
    # rate versus a lender's test is the whole difference between a scope limit
    # and a promise, and "cannot see whether yours is one" is the sentence that
    # keeps the exemption from being claimed for a household whose transaction
    # the engine cannot observe.
    return head + (
        " a straight switch is outside OSFI's prescribed rate, not outside a lender's "
        "test, and this run cannot see whether yours is one "
        "[qualifying_rate.buffer, qualifying_rate.floor]."
    )


def qualifying_rate_line(load: QualifyingLoad) -> str:
    """The one line, subject first (spec §6: other warnings sit between this
    and the affordability figures it qualifies, so a bare magnitude clause
    landing after that distance is unreadable).

    The line names the RATE the rule produces and cites the two legs; the
    rule's own sentence stays in the registry (`anchors.MQR_RULE`, printed by
    `--print-anchors`) rather than being quoted here, which keeps it one home
    and the line short enough to be read. `test_the_stored_figures_are_the_ones
    _the_printed_rule_states` is what makes that safe: it pins the two values
    against the sentence, so they cannot drift apart unobserved.

    The lift is subtracted from the two figures AS SHOWN, so a reader who
    checks the arithmetic in the line gets the line's own answer.
    """
    own = round(100 * load.own_ratio_year1, 1)
    loaded = round(100 * load.qualifying_ratio_year1, 1)
    # WHOSE test this is, in one clause. OSFI's minimum qualifying rate governs
    # UNINSURED mortgages; on an insured loan the same two figures are the
    # federal government's, aligned to OSFI's by decision in 2021. Both
    # citations sit on the anchors; the line states only which one applies to
    # THIS loan, because that is the part a reader cannot look up about
    # themselves. Saying OSFI's rule governs an insured borrower would be
    # false, which is the whole reason the branch exists.
    whose = ("the federal government's, not OSFI's" if load.insured
             else "OSFI's, which governs uninsured mortgages like yours")
    return (
        f"{load.option}: unpriced — at the minimum qualifying rate a lender would test you "
        f"at ({_rate(load.qualifying_quoted)} as quoted, against your contract "
        f"{_rate(load.contract_quoted)}), year-1 housing cost runs {loaded:.1f}% of income "
        f"against this run's own {own:.1f}% — {loaded - own:.1f} points the run does not "
        f"show, {TOWARD_BUYING}. Your loan is {'insured' if load.insured else 'uninsured'}, "
        f"so that rate is {whose} [qualifying_rate.buffer, qualifying_rate.floor]."
        # WHICH TRANSACTION, when this run prices one — between whose rule it
        # is and what the ratio is not, so the reader meets the scope of the
        # test before the scope of the numerator. Empty on a run that prices
        # no renewal, which leaves the sentence exactly as it shipped.
        f"{straight_switch_clause(load)}"
        f" Both "
        f"ratios are the engine's own measure, broader than the gross debt service a lender "
        f"uses [income.affordability_threshold], so this run cannot say how a lender would "
        f"rule on you."
    )


def unpriced_warnings(
    spec: Any,
    det: Any,
    raw: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """The unpriced lines for one run, in order — empty when none qualifies.

    Empty is the normal outcome and carries its own meaning: no reassurance
    stands in for it (spec §4 — `references/quick-sense.md` lists reassurance
    phrases as the first thing to cut, so a line reporting survival is what
    this repo already refuses).
    """
    return [qualifying_rate_line(load) for load in qualifying_loads(spec, det, raw)]


__all__ = [
    "NEUTRAL",
    "QualifyingLoad",
    "TOWARD_BUYING",
    "TOWARD_RENTING",
    "UNPRICED_LINE_CAP",
    "qualifying_loads",
    "qualifying_rate_line",
    "qualifying_rate_quoted",
    "straight_switch_clause",
    "unpriced_warnings",
]
