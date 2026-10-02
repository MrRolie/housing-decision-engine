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
import re
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

    def test_no_provenance_summary_survives_the_cut(self):
        # §0.1 item 35: the block prints each width's own source tag and no
        # summary of them, so the fields that fed the cut summary sentences
        # are gone from the types, and a structural zero carries its kind, not
        # a sentence.
        assert _fields(dc.ResolvedInteraction) == {
            "first_order_sum", "first_order_sum_ci", "residual", "residual_ci"}
        assert not {"superlative_licensed", "check_first",
                    "unattributed_channel_ids"} & _fields(dc.SpreadRegister)
        assert _fields(dc.StructuralZero) == {"kind", "label", "keys", "channel_id",
                                              "reversal_key", "measured_paths",
                                              "move_threshold"}


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
        assert _fields(dc.RefusedSpread) == {"code", "reason", "structural_zeros"}
        assert "no_sign_variation" in dc.SPREAD_REFUSAL_CODES

    def test_the_two_reversal_kinds_are_not_interchangeable(self):
        assert dc.ExactReversal.__mro__[1:] == dc.EstimatedReversal.__mro__[1:] == (object,)
        exact, estimated = _fields(dc.ExactReversal), _fields(dc.EstimatedReversal)
        assert exact != estimated
        assert "probe_paths" in exact and "probe_paths" not in estimated

    def test_a_row_holds_only_its_own_kind_of_boundary(self):
        """Both ways: an exact row builds with solved and sampled boundaries
        and refuses an estimated one; an estimated row builds with an
        estimated boundary and refuses a solved one.
        *Kills it:* deleting the check, or narrowing it to refuse a legal kind."""
        from tests.decomposition_households import (seven_channel_other_household,
                                                    uncertainty_surface)
        exact = uncertainty_surface().reversal.exact[0]
        estimated = seven_channel_other_household().reversal.estimated[0]
        assert {type(b) for b in exact.boundaries} == {dc.SolvedBoundary, dc.SampledBoundary}
        assert {type(b) for b in estimated.boundaries} == {dc.EstimatedBoundary}
        with pytest.raises(TypeError, match="EstimatedBoundary"):
            dataclasses.replace(exact, boundaries=exact.boundaries + estimated.boundaries)
        with pytest.raises(TypeError, match="SolvedBoundary"):
            dataclasses.replace(estimated, boundaries=exact.boundaries[:1])

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
        full = dict(verdict_field="mc_best", value=0.0271, upper_end=0.0271 + 5e-13,
                    formatted="2.71%", was="house",
                    becomes="condo", further_changes=None,
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
        full = dict(verdict_field="best", value=0.016052, upper_end=0.016052,
                    formatted="1.6052%", was="house", becomes="rent", further_changes=None,
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
        dc.SolvedBoundary: dict(verdict_field="best", value=0.016052, upper_end=0.016052,
                                formatted="1.6052%", further_changes=None,
                                confirming_probabilities=()),
        dc.SampledBoundary: dict(verdict_field="decisive", value=0.0674,
                                 upper_end=0.0674 + 5e-13, formatted="6.74%",
                                 further_changes="above",
                                 curve_probabilities=(("house", 0.65),),
                                 confirming_probabilities=(("house", 0.65),),
                                 curve_paths=5000, seed=42),
        dc.EstimatedBoundary: dict(verdict_field="best", value=0.014,
                                   value_ci=dc.Interval(0.012, 0.016),
                                   further_changes=None, resimulation_paths=500),
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


class TestABoundarySaysWhetherTheRangeChangesAgain:
    """`further_changes` — on every boundary kind — is None, "above" or
    "below": whether the searched range changes AGAIN past the crossing, on
    the side away from the run's own region, where no row reports it. A row
    reports only the nearest edge (§6), so without it a reader takes `becomes`
    to hold to the end of the bracket. It has no default: "nothing further" is
    a claim its producer states."""

    _BUILDS = TestABoundaryStatesBothSidesInWords._BUILDS

    @pytest.mark.parametrize("cls", list(_BUILDS), ids=lambda c: c.__name__)
    @pytest.mark.parametrize("side", [None, "above", "below"])
    def test_none_or_a_side_builds(self, cls, side):
        """The legal calls, so the refusals below cannot pass by refusing
        everything — and a guard widened to refuse a side fails here."""
        fields = {**self._BUILDS[cls], "further_changes": side}
        built = cls(**fields, was="house", becomes="rent")
        assert built.further_changes == side

    @pytest.mark.parametrize("cls", list(_BUILDS), ids=lambda c: c.__name__)
    @pytest.mark.parametrize("side", ["sideways", "Above", True, 1, ""])
    def test_anything_else_refuses(self, cls, side):
        """*Kills it:* deleting `_require_side`, which lets a value print as a
        side no reader can place."""
        fields = {**self._BUILDS[cls], "further_changes": side}
        with pytest.raises(ValueError, match="further_changes"):
            cls(**fields, was="house", becomes="rent")

    @pytest.mark.parametrize("cls", list(_BUILDS), ids=lambda c: c.__name__)
    def test_it_has_no_default(self, cls):
        fields = {k: v for k, v in self._BUILDS[cls].items() if k != "further_changes"}
        with pytest.raises(TypeError):
            cls(**fields, was="house", becomes="rent")


class TestARegisterHasOneTopRow:
    """The top row of a register, by point estimate, either LEADS (it resolved)
    or is the UNRESOLVED TOP (it did not). Both at once would let the text name
    one channel as leading while the JSON names another as the largest — the
    disagreement the pair exists to end."""

    @staticmethod
    def _spread(**over):
        fields = dict(rows=(), interaction=dc.RefusedInteraction(
                          first_order_sum=1.1, first_order_sum_ci=dc.Interval(1.0, 1.2)),
                      leading_channel_id=6, unresolved_top_channel_id=None,
                      interaction_channel_ids=(), structural_zeros=())
        fields.update(over)
        return dc.SpreadRegister(**fields)

    @staticmethod
    def _level(**over):
        fields = dict(rows=(), paths=2000, prob_best_base=0.34, futures_margin=-1.0,
                      all_frozen_margin=1.0, all_frozen_path_spread=0.0,
                      all_frozen_deviation=0.0, accounted_for=2.0,
                      leading_channel_id=5, unresolved_top_channel_id=None)
        fields.update(over)
        return dc.LevelRegister(**fields)

    def test_the_legal_shapes_build(self):
        """A leader; an unresolved top. A guard widened to refuse either
        fails here."""
        assert self._spread().leading_channel_id == 6
        assert self._spread(leading_channel_id=None,
                            unresolved_top_channel_id=3).unresolved_top_channel_id == 3
        assert self._level().leading_channel_id == 5
        assert self._level(leading_channel_id=None,
                           unresolved_top_channel_id=3).unresolved_top_channel_id == 3

    @pytest.mark.parametrize("build", ["_spread", "_level"])
    def test_a_leader_and_an_unresolved_top_together_refuse(self, build):
        """*Kills it:* deleting `_require_one_top`."""
        with pytest.raises(ValueError, match="at most one of the two"):
            getattr(self, build)(leading_channel_id=4, unresolved_top_channel_id=3)

    @pytest.mark.parametrize("register", [dc.SpreadRegister, dc.LevelRegister])
    def test_the_unresolved_top_has_no_default(self, register):
        field = next(f for f in dataclasses.fields(register)
                     if f.name == "unresolved_top_channel_id")
        assert field.default is dataclasses.MISSING


class TestAnEmptyRegisterSaysWhatItSearched:
    """`no_distance_reason` is set exactly when no row carries a distance: an
    empty register with no reason leaves the reader to take the absence for a
    finding, and a reason beside rows explains an emptiness that is not there.
    *Kills it:* deleting the guard, or widening it to refuse a legal register."""

    _ROW = dict(key="house.mortgage_renewal_rates", option="house", bracket_low=0.01,
                bracket_high=0.10, bracket_source="assistant", probe_paths=200,
                max_path_deviation_over_sd=9.5e-16, boundaries=(),
                refused_boundaries=())

    def test_the_legal_shapes_build(self):
        dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(),
                            no_distance_code="no_candidate",
                            no_distance_reason="nothing was searched")
        dc.ReversalRegister(exact=(dc.ExactReversal(**self._ROW),),
                            estimated=(), structural_zeros=(), no_distance_code=None,
                            no_distance_reason=None)

    def test_an_empty_register_without_a_reason_refuses(self):
        with pytest.raises(ValueError, match="no_distance_reason"):
            dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(),
                                no_distance_code=None, no_distance_reason=None)

    def test_a_reason_beside_rows_refuses(self):
        with pytest.raises(ValueError, match="no_distance_reason"):
            dc.ReversalRegister(
                exact=(dc.ExactReversal(**self._ROW),),
                estimated=(), structural_zeros=(), no_distance_code="no_candidate",
                no_distance_reason="none searched")

    def test_a_refused_row_is_a_row(self):
        """§0.1 item 64: a register whose one row is a refused key carries no
        no-distance reason, and one beside it refuses."""
        refused = (dc.RefusedReversal(key="condo.mortgage_rate", option="condo",
                                      code="not_admitted", reason="r"),)
        dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(), no_distance_code=None,
                            no_distance_reason=None, refused=refused)
        with pytest.raises(ValueError, match="no_distance_reason"):
            dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(),
                                no_distance_code="no_candidate", no_distance_reason="r",
                                refused=refused)
        with pytest.raises(TypeError, match="ReversalRegister.refused"):
            dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(),
                                no_distance_code=None, no_distance_reason=None,
                                refused=(dc.RefusedBoundary(verdict_field="best",
                                                            code="unchanged", reason="r"),))


class TestARefusalCarriesACodeFromItsSet:
    """§0.1 item 50: the refused-boundary and no-distance lines print a code
    before their reason, so each type takes a code from its own set and no
    other: a code outside it prints a word the contract does not define.
    *Kills it:* deleting either check (an undefined code builds), or pointing
    it at the other set (a defined code refuses)."""

    @pytest.mark.parametrize("code", dc.BOUNDARY_REFUSAL_CODES)
    def test_a_refused_boundary_takes_each_boundary_code(self, code):
        assert dc.RefusedBoundary(verdict_field="best", code=code, reason="r").code == code

    @pytest.mark.parametrize("code", [None, "throughout", "no_candidate"])
    def test_a_refused_boundary_refuses_any_other(self, code):
        with pytest.raises(ValueError, match="RefusedBoundary.code"):
            dc.RefusedBoundary(verdict_field="best", code=code, reason="r")

    @pytest.mark.parametrize("code", dc.NO_DISTANCE_CODES)
    def test_an_empty_register_takes_each_no_distance_code(self, code):
        assert dc.ReversalRegister(
            exact=(), estimated=(), structural_zeros=(), no_distance_code=code,
            no_distance_reason="r").no_distance_code == code

    @pytest.mark.parametrize("code", ["unchanged", "nothing", "not_admitted"])
    def test_an_empty_register_refuses_any_other(self, code):
        with pytest.raises(ValueError, match="ReversalRegister.no_distance.code"):
            dc.ReversalRegister(exact=(), estimated=(), structural_zeros=(),
                                no_distance_code=code, no_distance_reason="r")

    @pytest.mark.parametrize("code", dc.REVERSAL_REFUSAL_CODES)
    def test_a_refused_key_takes_each_of_its_codes(self, code):
        assert dc.RefusedReversal(key="k", option="condo", code=code, reason="r").code == code

    @pytest.mark.parametrize("code", ["no_candidate", "unchanged", None])
    def test_a_refused_key_refuses_any_other(self, code):
        with pytest.raises(ValueError, match="RefusedReversal.code"):
            dc.RefusedReversal(key="k", option="condo", code=code, reason="r")


class TestEachRegisterHoldsTheRowsOfItsOwnSample:
    """§0.1 item 48: a `dead_draw` row is measured on the block's own futures,
    so it lives in the spread register, refused or not; a `stated_path` row is
    measured on none, and it lives in the reversal register, which reads no
    figure that moves with `N`.
    *Kills it:* deleting either register's kind check (a row of the other
    kind builds), or widening it (a row of its own kind refuses)."""

    _DEAD = dict(kind="dead_draw", label="your tenancy", keys=("rent.events",),
                 channel_id=5, measured_paths=400, move_threshold=1e-9)
    _STATED = dict(kind="stated_path", label="the contract rate",
                   keys=("house.mortgage_rate",), reversal_key="house.mortgage_rate")

    @staticmethod
    def _spread(zeros):
        return TestARegisterHasOneTopRow._spread(structural_zeros=zeros)

    @staticmethod
    def _refused(zeros):
        return dc.RefusedSpread(code="no_sign_variation", reason="r", structural_zeros=zeros)

    @staticmethod
    def _reversal(zeros):
        return dc.ReversalRegister(exact=(), estimated=(), structural_zeros=zeros,
                                   no_distance_code="no_candidate",
                                   no_distance_reason="nothing was searched")

    @pytest.mark.parametrize("build", ["_spread", "_refused"])
    def test_the_spread_holds_the_dead_draw_rows_and_no_other(self, build):
        dead, stated = dc.StructuralZero(**self._DEAD), dc.StructuralZero(**self._STATED)
        assert getattr(self, build)((dead, dead)).structural_zeros == (dead, dead)
        with pytest.raises(ValueError, match="stated_path"):
            getattr(self, build)((dead, stated))

    def test_the_reversal_holds_the_stated_path_rows_and_no_other(self):
        dead, stated = dc.StructuralZero(**self._DEAD), dc.StructuralZero(**self._STATED)
        assert self._reversal((stated,)).structural_zeros == (stated,)
        with pytest.raises(ValueError, match="dead_draw"):
            self._reversal((stated, dead))

    @pytest.mark.parametrize("register", [dc.SpreadRegister, dc.RefusedSpread,
                                          dc.ReversalRegister])
    def test_no_register_defaults_its_rows(self, register):
        field = next(f for f in dataclasses.fields(register) if f.name == "structural_zeros")
        assert field.default is dataclasses.MISSING


class TestABlockPricesNoMoreThanTheBudgetAdmits:
    """`paths` lies in (0, max_paths]: the budget gate refuses any count above
    `max_paths`, so a block past it is a producer defect, and the route clause
    that reads `max_paths` as "the most this register prices on this run"
    would be false over it.
    *Kills it:* deleting the guard, or widening it to refuse the cap itself."""

    @staticmethod
    def _build(paths, max_paths):
        from tests.decomposition_households import two_channel_option_state
        return dataclasses.replace(two_channel_option_state(), paths=paths,
                                   max_paths=max_paths)

    def test_the_cap_itself_builds(self):
        assert self._build(4000, 4000).paths == 4000

    @pytest.mark.parametrize("paths, max_paths", [(4001, 4000), (0, 4000)])
    def test_outside_the_range_refuses(self, paths, max_paths):
        with pytest.raises(ValueError, match="largest affordable"):
            self._build(paths, max_paths)


# What a pointer in the types module may say, whole: the contract section, or
# the design record with an optional section and ruling. Nothing else.
_POINTER_LINE = re.compile(
    r"Fields: docs/reference/API_CONTRACT\.md § The `decomposition` block\."
    r"|Design: docs/specs/2026-09-22-which-risk-decides-it\.md"
    r"(?: §\d+(?:\.\d+)?(?: items? \d+(?: and \d+)?)?)?\.")
_RULE_LINE = re.compile(r"-{20,}")


def _prose_of_the_types_module(source):
    """`(where, text)` for every string statement in `source` and every
    comment, each comment by line. A string statement is any expression
    statement that is a string or an f-string, wherever it stands: the
    docstring of the module, a class or a function, one under a field, and a
    bare one inside a body."""
    import ast
    import inspect
    import io
    import tokenize
    tree = ast.parse(source)
    owners = {}
    for node in [tree] + [n for n in ast.walk(tree) if isinstance(
            n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]:
        if node.body and isinstance(node.body[0], ast.Expr):
            owners[id(node.body[0])] = getattr(node, "name", "<module>")
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text = inspect.cleandoc(value.value)
        elif isinstance(value, ast.JoinedStr):
            text = ast.unparse(value)
        else:
            continue
        where = (f"docstring of {owners[id(node)]}" if id(node) in owners
                 else f"string at line {node.lineno}")
        out.append((where, text))
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            out.append((f"comment at line {token.start[0]}", token.string.lstrip("#").strip()))
    return out


def _not_a_pointer(source):
    wrong = []
    for where, text in _prose_of_the_types_module(source):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines or not all(_POINTER_LINE.fullmatch(line) or _RULE_LINE.fullmatch(line)
                                for line in lines):
            wrong.append((where, text))
    return wrong


_SIDE_HEAD = ("def _require_side(kind: str, verdict_field: str, further_changes: object) "
              "-> None:\n    \"\"\"Design: docs/specs/2026-09-22-which-risk-decides-it.md §6.")


def test_every_docstring_and_every_comment_is_a_pointer():
    """§0.1 item 52: the types module carries no prose but pointers, in
    docstrings and comments alike. What a field means, when a refusal fires and
    why a shape is what it is are written in the contract and the design
    record; a sentence here would be a second home with nothing to keep it
    true. Every string statement of the module — its docstrings, one under a
    field, a bare one in a body — and every comment is a pointer line (or a
    rule of dashes), whole.
    *Kills it:* a sentence appended to any docstring or any comment, or
    written as a string statement anywhere — the ones below fail it — or one
    put in place of a pointer."""
    import pathlib
    source = pathlib.Path(dc.__file__).read_text(encoding="utf-8")
    found = _prose_of_the_types_module(source)
    assert sum(where.startswith("docstring") for where, _ in found) >= 25
    assert sum(where.startswith("comment") for where, _ in found) >= 10
    assert _not_a_pointer(source) == []
    # the test fails on a restatement, in a function docstring and in a comment
    restated = "`mean_margin` is the mean of `f` over the block's own futures."
    appended = source.replace(_SIDE_HEAD, _SIDE_HEAD + "\n    " + restated)
    assert appended != source
    assert _not_a_pointer(appended) == [
        ("docstring of _require_side",
         "Design: docs/specs/2026-09-22-which-risk-decides-it.md §6.\n" + restated)]
    pointer = "# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 items 39 and 40.\n"
    comment = "A dead_draw row is a stream that drew and moved no present value."
    commented = source.replace(pointer, pointer + "# " + comment + "\n")
    assert commented != source
    assert [text for _, text in _not_a_pointer(commented)] == [comment]
    positions = "# Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.2.\n"
    same_line = source.replace(positions, positions[:-1] + " Ids are positions.\n")
    assert same_line != source and len(_not_a_pointer(same_line)) == 1
    # and a string statement that is no docstring of a class or a function: one
    # under a field, and a bare one in a function body, an f-string included
    for anchor, restatement, after in (
            ("    move_threshold: Optional[float] = None\n",
             '    """`move_threshold` is the largest move any re-draw made."""\n', True),
            ("    tag: Optional[str] = None\n",
             '    """`tag` is the read-back\'s tag for this width\'s key."""\n', True),
            ("    found = [entry for entry in CHANNELS if entry.id == channel_id]\n",
             '    "A channel id is the address of the stream that draws it."\n', False),
            ("    found = [entry for entry in CHANNELS if entry.id == channel_id]\n",
             '    f"A channel id is {channel_id}."\n', False)):
        assert source.count(anchor) == 1, anchor
        mutated = source.replace(anchor, anchor + restatement if after
                                 else restatement + anchor)
        assert [where.split(" at ")[0] for where, _ in _not_a_pointer(mutated)] == [
            "string"], restatement



def test_every_class_docstring_is_the_pointer_and_nothing_more():
    """What each field means is written once, in the contract. A class
    docstring that restated it would be a second home with nothing to keep it
    true, so every class the module defines carries exactly `POINTER`, and the
    pointer names a section the contract has.
    *Kills it:* any sentence added to, or put in place of, a class docstring."""
    import ast
    import pathlib
    source = pathlib.Path(dc.__file__)
    tree = ast.parse(source.read_text(encoding="utf-8"))
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert len(classes) >= 20
    wrong = [(node.name, ast.get_docstring(node, clean=False)) for node in classes
             if ast.get_docstring(node, clean=False) != dc.POINTER]
    assert not wrong, wrong
    for node in classes:
        assert getattr(dc, node.name).__doc__ == dc.POINTER, node.name
    contract = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "reference"
                / "API_CONTRACT.md").read_text(encoding="utf-8")
    assert dc.POINTER.startswith("Fields: docs/reference/API_CONTRACT.md § ")
    heading = dc.POINTER.split(" § ", 1)[1].rstrip(".")
    assert any(line.startswith(f"## {heading}") for line in contract.splitlines())
