"""The decomposition contract — the one file five parallel tracks share.

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
        assert {"curve_paths", "seed"} <= sampled
        assert not {"curve_paths", "seed"} & solved
