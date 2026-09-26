"""The decomposition contract — the one file every piece of the block shares.

Nothing here tests what a frozen dataclass gives for free. It guards: the
channel ids are FIXED INTEGERS in fixed slots, checked ACROSS PROCESSES at two
hash seeds, since a set-derived table moves only between processes and an id
feeds the stream key (§3.1, §3.2); a resolved figure and an unresolved one
share no attribute name, so a formatter cannot print the second as though it
resolved (§4, §7 rule 6); and the spread register cannot be built without its
level register, a refused spread is NAMED rather than empty, and the two
reversal kinds are not interchangeable (§5 mechanism 5, §0.1 item 7, §6).
"""
import dataclasses
import os
import subprocess
import sys

import pytest

from hde import decomposition as dc


# The table as the design fixes it: id, machine key, and the label §7 prints.
EXPECTED = (
    (0, "economy", "the economy"),
    (1, "market", "the housing market"),
    (2, "population", "the population"),
    (3, "condo", "the condo's costs"),
    (4, "house", "the house's costs"),
    (5, "shelter", "your tenancy"),
    (6, "portfolio", "the renter's portfolio"),
)

_DUMP = ("from hde.decomposition import CHANNELS; "
         "print([(c.id, c.key, c.label) for c in CHANNELS])")


def _fields(cls):
    return {f.name for f in dataclasses.fields(cls)}


class TestTheChannelTable:
    def test_ids_are_exactly_zero_to_six_in_fixed_slots(self):
        assert tuple((c.id, c.key, c.label) for c in dc.CHANNELS) == EXPECTED
        for slot, entry in enumerate(dc.CHANNELS):   # the id IS the position
            assert entry.id == slot
            assert dc.channel(slot) is entry
            assert dc.channel_by_key(entry.key) is entry

    @pytest.mark.parametrize("bad", [-1, len(dc.CHANNELS), dc.INCOME_STREAM_ID])
    def test_lookups_refuse_rather_than_wrap(self, bad):
        with pytest.raises(KeyError):   # -1 would return the last channel, and
            dc.channel(bad)             # income is a stream id, not a channel

    def test_the_table_is_immutable(self):
        assert isinstance(dc.CHANNELS, tuple)
        for entry in dc.CHANNELS:
            assert isinstance(entry.sizing_keys, tuple)
            with pytest.raises(dataclasses.FrozenInstanceError):
                entry.id = 99

    def test_ids_are_stable_across_processes_at_different_hash_seeds(self):
        seen = [subprocess.run([sys.executable, "-c", _DUMP], check=True,
                               env=dict(os.environ, PYTHONHASHSEED=seed),
                               capture_output=True, text=True).stdout.strip()
                for seed in ("1", "1993")]
        assert seen[0] == seen[1] == str([tuple(row) for row in EXPECTED])

    def test_every_channel_names_the_keys_that_size_it(self):
        # §5 mechanism 1 builds the provenance column from these alone.
        for entry in dc.CHANNELS:
            assert entry.sizing_keys
            assert all("." in key for key in entry.sizing_keys)


class TestResolvedAndUnresolvedAreDistinctStates:
    @pytest.mark.parametrize("resolved_cls, unresolved_cls, point, provisional", [
        (dc.ResolvedShares, dc.UnresolvedShares, "alone", "provisional_alone"),
        (dc.ResolvedLevel, dc.IndistinguishableLevel, "delta", "provisional_delta"),
    ])
    def test_the_point_estimate_has_a_different_name_in_each_state(
            self, resolved_cls, unresolved_cls, point, provisional):
        resolved, unresolved = _fields(resolved_cls), _fields(unresolved_cls)
        assert point in resolved and point not in unresolved
        assert provisional in unresolved and provisional not in resolved
        assert resolved_cls.__mro__[1:] == unresolved_cls.__mro__[1:] == (object,)

    def test_only_the_resolved_interaction_carries_a_residual(self):
        assert "residual" in _fields(dc.ResolvedInteraction)
        assert "residual" not in _fields(dc.RefusedInteraction)

    def test_the_unstated_share_sum_lives_on_the_resolved_branch_only(self):
        # §5 mechanism 4: on the refused branch that sum is noise, and a block
        # that refuses to print a figure as a residual then prints it as a
        # provenance finding says two things about one number.
        assert "unstated_first_order_sum" in _fields(dc.ResolvedInteraction)
        assert "unstated_first_order_sum" not in _fields(dc.RefusedInteraction)


class TestTheBinding:
    def test_no_spread_only_result_can_be_constructed(self):
        required = {
            f.name for f in dataclasses.fields(dc.Decomposition)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        }
        assert {"spread", "level", "reversal"} <= required

    def test_a_refused_spread_is_named_and_carries_no_rows(self):
        # §0.1 item 7: a refused spread beside a printed level is the honest
        # shape, and `rows=()` is exactly what that ruling rejects.
        assert _fields(dc.RefusedSpread) == {"code", "reason"}
        assert "no_sign_variation" in dc.SPREAD_REFUSAL_CODES

    def test_the_two_reversal_kinds_are_not_interchangeable(self):
        assert dc.ExactReversal.__mro__[1:] == dc.EstimatedReversal.__mro__[1:] == (object,)
        exact, estimated = _fields(dc.ExactReversal), _fields(dc.EstimatedReversal)
        assert exact != estimated
        assert "probe_paths" in exact and "probe_paths" not in estimated

    def test_a_solved_crossing_and_a_sampled_one_are_not_one_type(self):
        # §0.1 item 24: one type for both was the cardinal error, because
        # nothing downstream could tell a config property from a sample one.
        assert dc.SolvedBoundary.__mro__[1:] == dc.SampledBoundary.__mro__[1:] == (object,)
        solved, sampled = _fields(dc.SolvedBoundary), _fields(dc.SampledBoundary)
        assert solved != sampled
        assert {"curve_paths", "seed"} <= sampled
        assert not {"curve_paths", "seed"} & solved
        assert not [name for name in solved if "path" in name or "seed" in name]
        assert "curve_probabilities" not in solved
        assert dc.SolvedBoundary is not dc.EstimatedBoundary

    def test_a_sampled_boundary_cannot_be_built_without_its_sample(self):
        """Asserted in BOTH directions: the full call builds, and dropping
        either the path count or the seed refuses."""
        full = dict(verdict_field="mc_best", value=0.0271, was="condo", becomes="house",
                    curve_probabilities=(("condo", 0.44),),
                    confirming_probabilities=(("condo", 0.44),),
                    curve_paths=2000, seed=42)
        assert (dc.SampledBoundary(**full).curve_paths,
                dc.SampledBoundary(**full).seed) == (2000, 42)
        for missing in ("curve_paths", "seed"):
            with pytest.raises(TypeError):
                dc.SampledBoundary(**{k: v for k, v in full.items() if k != missing})

    def test_a_solved_boundary_states_its_corroboration_or_does_not_build(self):
        """An empty corroboration is a claim — "nothing re-simulated this" —
        so its producer must state it. Asserted in BOTH directions: an explicit
        empty tuple builds, and leaving the field out refuses rather than
        defaulting the claim into existence."""
        full = dict(verdict_field="best", value=0.016052, was="rent", becomes="house",
                    confirming_probabilities=())
        assert dc.SolvedBoundary(**full).confirming_probabilities == ()
        with pytest.raises(TypeError):
            dc.SolvedBoundary(**{k: v for k, v in full.items()
                                 if k != "confirming_probabilities"})


class TestABoundaryStatesBothSidesInWords:
    """`was` and `becomes` are the words a reader is shown for the verdict on
    each side of a boundary — an option's name, or "decisive for house" — on
    EVERY boundary kind. A boolean decisiveness once reached the output through
    a `str()` as "changes from True to False", on a crossing that ran from not
    decisive into decisive for the OTHER option; the type now refuses anything
    that is not text, so no coercion upstream can launder a raw value through.
    """

    _BUILDS = {
        dc.SolvedBoundary: dict(verdict_field="best", value=0.016052,
                                confirming_probabilities=()),
        dc.SampledBoundary: dict(verdict_field="decisive", value=0.0674,
                                 curve_probabilities=(("house", 0.65),),
                                 confirming_probabilities=(("house", 0.65),),
                                 curve_paths=5000, seed=42),
        dc.EstimatedBoundary: dict(verdict_field="best", value=0.014,
                                   value_ci=dc.Interval(0.012, 0.016),
                                   resimulation_paths=500),
    }

    @pytest.mark.parametrize("cls", list(_BUILDS), ids=lambda c: c.__name__)
    def test_words_build(self, cls):
        """The legal call, so the refusals below cannot pass by refusing
        everything."""
        built = cls(**self._BUILDS[cls], was="decisive for house", becomes="not decisive")
        assert (built.was, built.becomes) == ("decisive for house", "not decisive")

    @pytest.mark.parametrize("cls", list(_BUILDS), ids=lambda c: c.__name__)
    @pytest.mark.parametrize("side", ["was", "becomes"])
    @pytest.mark.parametrize("value", [True, False, None, 0.0, "", "   "])
    def test_anything_but_words_refuses(self, cls, side, value):
        sides = {"was": "house", "becomes": "rent", side: value}
        with pytest.raises(TypeError, match="not words"):
            cls(**self._BUILDS[cls], **sides)


class TestAStatedValueSaysWhoseFigureItIs:
    """`stated_source` has no default on either reversal kind: a row whose
    producer did not say whose figure the stated value is must not build, or
    the words keyed on it would fall back to whichever reading the default
    happened to favour."""

    _EXACT = dict(key="house.mortgage_renewal_rates", option="house",
                  stated_formatted="4.60%, 5.00%", bracket_low=0.01,
                  bracket_high=0.10, bracket_source="assistant", probe_paths=200,
                  max_path_deviation_over_sd=9.5e-16, boundaries=(),
                  refused_boundaries=(), references=())

    def test_both_kinds_build_with_it_and_refuse_without_it(self):
        exact = dc.ExactReversal(**self._EXACT, stated_source="assistant")
        assert exact.stated_source == "assistant"
        estimated_kwargs = {k: v for k, v in self._EXACT.items() if k != "probe_paths"}
        estimated = dc.EstimatedReversal(**estimated_kwargs, stated_source="user")
        assert estimated.stated_source == "user"
        with pytest.raises(TypeError, match="stated_source"):
            dc.ExactReversal(**self._EXACT)
        with pytest.raises(TypeError, match="stated_source"):
            dc.EstimatedReversal(**estimated_kwargs)

    def test_it_has_no_default_anywhere(self):
        for cls in (dc.ExactReversal, dc.EstimatedReversal):
            field = next(f for f in dataclasses.fields(cls) if f.name == "stated_source")
            assert field.default is dataclasses.MISSING
            assert field.default_factory is dataclasses.MISSING
