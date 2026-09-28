# Events in one world — design (2026-09-27)

**Status:** ruled, amended 2026-09-27 after the first review of the fix (E7-E9).
**Anchored by:** board item 10, the central case charging a hazard-timed event whose hazard is 0.

## 1. What was measured

The engine prices one-time events (`condo.events`, `house.events`, `rent.events`) twice. The
central case (`deterministic.py`) prices them on one path. The futures (`monte_carlo.py`) price
them on every simulated path. A measurement mapped every rule by which each engine places or charges
an event, built a config for each place the two could disagree, and measured it at 4,000 or more
paths on two seeds. It found fifteen disagreements. A second, independent check tried to refute
each one, and none was refuted. Grouped by what the user meets:

| # | Disagreement | What was found (dollar gaps are best guess minus futures unless marked) |
|---|---|---|
| C8 | `min_year` beyond the horizon: the futures sampler has no final bound when `timing_std_years` is 0 | the rent futures index past the horizon and **crash** with a traceback. The owned futures silently charge $0 while the central case charges the event in the final year |
| C1 | `timing_model: hazard` with zero hazard | the central case charges the event (a $15,000 event is $11,841 at 3%, year 8), and no future ever fires it. The single-path gate classes the event as deterministic, so the futures are never consulted |
| C2 | `hazard_start_year` after the horizon | the same $11,841 is charged centrally and never in the futures. On the measured config the central-case winner flips |
| C3, C4 | a hazard that fires on fewer than all futures, or whose typical year is far from `expected_year` | a gap of $4.5k to $5.9k on the measured configs. It moves the winner on a near-tie household |
| C5 | the hazard sampler ignores `min_year` and `max_year` | the futures fire the event outside the window the config states |
| C9 | `min_year > max_year` | the central case resolves the window to `max_year` and the futures to `min_year` |
| C13 | two events with the same name in one option | the owned options and the rent futures charge both, each in the last one's year, while the rent central case charges each in its own year. On the measured config the gap is $3,311 |
| C12 | the futures' affordability arrays | every path uses the central case's event years, while the reset already gets per-path arrays |
| C15 | a pay drop whose year lies outside the horizon | the central case and the futures disagree about the affordability flag |
| C14 | the lease reset | the central case prices a tenancy that never resets. It is always an extreme of the futures, never their centre: the best tail when the rent is below what a comparable unit asks, and the worst tail when it is above (measured on both sides) |
| C6, C7, C10, C11 | a one-sided jitter clamp ($310), discount convexity ($44), the normal cost distribution's truncation (mean +8.3% at vol 1.0), and condo reserve netting (about $1.4k) | differences between a single path and a mean, each small against its margin |

Two conventions coexist and nothing says so. The central case never fires the reset or the price
shock. It fires every event with certainty at `expected_year`.

## 2. Rulings

**E1. The central case keeps its meaning, and the read-back names where the futures time an
event differently.** An event is charged once, in the year the config places it. That is the
user's own statement of when it happens. The futures time it by its model. That difference is a
modelled uncertainty, which the three-state verdict already names; it is not a defect. What was
missing is the sentence that says so. For every hazard-timed event the read-back prints the
facts, computed exactly from the hazard schedule:
- the year the central case charges it;
- the probability that it fires within the horizon;
- the year by which half of the futures have fired it, or that fewer than half ever do
  (superseded by E7: the line states the model's schedule, not a count of futures).

When `rent.reset_hazard > 0` the read-back also says that the central case prices a tenancy that
never resets, and when `price_shock.annual_hazard > 0`, that it prices no crash. These are facts about
the run, with no dollar gap and no advice.

**E2. A config whose event cannot happen, or whose window contradicts itself, is refused at
load.** A surface that cannot tell the user something true refuses. The loader refuses, naming
the key and the fact, each of:
- a hazard-timed event whose hazard is zero in every year of its window;
- a `hazard_start_year` after the horizon or after `max_year`;
- a `min_year` beyond the horizon;
- a `min_year` above `max_year`;
- an `expected_year` outside the event's own window, which the central case used to clamp
  silently;
- two events with the same name in one option;
- a negative `timing_std_years` or `cost_vol` (the six simulation vols already refuse one);
- a pay-drop year outside the horizon.

The C8 crash becomes unreachable through the loader. The rent futures loop also bounds its year,
as the owned loops do, so no legal path indexes past the horizon.

**E3. The futures respect the event's window for hazard timing too.** A hazard fires only in
years that lie in both the hazard's range and the stated window: from
`max(min_year, hazard_start_year)` to `min(max_year, years)`. Jitter timing already respects the
window.

**E4 (superseded by E8 and E11). The single-path gate asks whether the futures' timing can differ, not which field is
non-zero.** An event is stochastic exactly when its fire-year distribution across futures is not
a single point, or its cost is drawn. The refusals of E2 remove the two cases that were misclassed.

**E5. The futures' affordability arrays place each event on each path**, as they already place
the reset (C12).

**E6. Left on the board, stated as conventions, not fixed here:** C6, C7, C10 and C11. Each is
the difference between one path and a mean, and each is small against its margin on every
measured household. The normal cost distribution's truncation bias is the one a user can pull
far with a large vol, so the board records it with its measured sizes.

**E7. E1's lines state the model's schedule, not a count of futures, and every rate is the one
the model applies.** The first build printed "X% of futures fire it" and "the futures reset it" on
runs with no futures at all (`--no-monte-carlo`, or a single-path run), where the contract itself
says the run has none. The facts are properties of the model's schedule and hold whether or not
the run draws paths, so the lines say so: the chance the event fires within the horizon, and
the year by which that chance reaches one half. The crash line printed `annual_hazard` while the
futures draw at `min(annual_hazard × drawdown_weight_tilt, 1)` under a demographic prior. A
rate the line prints is the rate the model applies after every multiplier, and it prints as a
range when that rate varies by year. Every rate and probability follows item 51 of the
`--decompose` spec: it prints 0.0% or 100.0% only when it is exactly 0 or 1. A probability
whose complement underflows float therefore prints as below 100%, never as 100.0%.

**E8. E4 corrected: the futures are consulted whenever they can differ from the central case,
not only when they differ among themselves.** Consider an event whose hazard is certain in its
first window year. Every future fires it in that year, so its fire-year distribution is a single
point. If that year is not the one the central case charges, every future disagrees with the
central case. E4 as first written called that event deterministic. The gate then skipped the
futures and printed a decisive verdict that every future contradicts, where main had printed "the
two disagree, not decisive". An event is stochastic exactly when some future can place or cost it
differently from the central case. `sources.uncertainty_inputs` reads the same predicate, so the
engine keeps one definition of "widens the distribution".

**E9. E2 extended: a hazard-timed event's `expected_year` lies in the years its hazard can fire.**
With `expected_year` 3 and `hazard_start_year` 10, the central case charges the event in a year
no future can fire it. That is the same contradiction E2 refuses for the stated window. For a
hazard-timed event, the window checked is `[max(min_year, hazard_start_year),
min(max_year, years)]`.

**E10. E9 made exact: the year the central case charges an event is a year in which some future
can fire it** *(2026-09-28, on the second review of the fix)*. E9's window is a proxy, and it let
two contradictions through:
- a hazard that is zero in its first window year (a zero base that grows), with `expected_year`
  in that year;
- a hazard that is certain in an earlier year, which every future fires before the central year.

The exact statement is one predicate, read from the one home of where the futures can fire an
event: `_event_year_deterministic(event, years) ∈ event.fire_years(years)`. It holds for jitter
timing by E2, and the loader refuses a hazard-timed event for which it fails, naming the year
the central case would charge and the years the futures can fire it. E8's witnesses of a hazard
that is certain in another year now fail at load, which is E9's own contradiction. A spec built
in code, bypassing the loader, can still break the predicate, so the library functions that
assume it say so.

**E11. With E10, "some future can differ" and "the futures disperse" are one predicate.** The
first fix gated the futures on "some future can differ from the central case", and used the
same test to name a side "stochastic" in the one-sided-uncertainty warning. On a hazard certain
in another year, every future is one point, so the warning's "stochastic" and "OVERconfident"
were false. Under E10 the central year is always one of the fire years. The fire-year set
therefore differs from `{central year}` exactly when it holds more than one outcome, which is
when the futures disperse. The gate, `dispersion_sources` and `sources.uncertainty_inputs` read
that one predicate, and a test pins the three against each other by enumeration over event
shapes.

**E12. Superseded wording is marked where it stands.** E1's third bullet ("the year by which
half of the futures have fired it") is superseded by E7, and E4 by E8 and E11. Each carries a
one-line pointer to the ruling that replaced it, so no reader takes the older text as current.

## 3. What must stay true

- The seven shipped examples still load. `examples/advanced_config.yaml` states two hazard-timed
  events with windows, so its futures and its read-back change, as E1 and E3 intend.
  `examples/showcase_demographic_prior.yaml` states a price shock on both owned options, so its
  read-back gains E1's crash lines. Every other example is byte-identical on `--json`.
- Every refusal names the key and the fact, and a test pins it, both for the refusal and for the
  legal config one step away from it.
- The read-back lines of E1 are pinned against the hazard schedule, computed independently in the
  test.
- A config that no longer loads because of E2 is never a shipped example, a test fixture, or a
  household in PROMPTS.md.
