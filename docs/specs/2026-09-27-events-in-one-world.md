# Events in one world — design (2026-09-27)

**Status:** ruled; the fix is being built.
**Anchored by:** board item 10, the central case charging a hazard-timed event whose hazard is 0.

## 1. What was measured

The engine prices one-time events (`condo.events`, `house.events`, `rent.events`) twice. The
central case (`deterministic.py`) prices them on one path. The futures (`monte_carlo.py`) price
them on every simulated path. An audit mapped every rule by which each engine places or charges
an event, built a config for each place the two could disagree, and measured it at 4,000 or more
paths on two seeds. It found fifteen disagreements. A second, independent check tried to refute
each one, and none was refuted. Grouped by what the user meets:

| # | Disagreement | Measured |
|---|---|---|
| C8 | `min_year` beyond the horizon: the futures sampler has no final bound when `timing_std_years` is 0 | the rent futures index past the horizon and **crash** with a traceback. The owned futures silently charge $0 while the central case charges the event in the final year |
| C1 | `timing_model: hazard` with zero hazard | the central case charges the event (a $15,000 event is $11,841 at 3%, year 8), and no future ever fires it. The single-path gate classes the event as deterministic, so the futures are never consulted |
| C2 | `hazard_start_year` after the horizon | the same $11,841 is charged centrally and never in the futures. On the measured config the central-case winner flips |
| C3, C4 | a hazard that fires on fewer than all futures, or whose typical year is far from `expected_year` | a gap of $4.5k to $5.9k on the measured configs. It moves the winner on a near-tie household |
| C5 | the hazard sampler ignores `min_year` and `max_year` | the futures fire the event outside the window the config states |
| C9 | `min_year > max_year` | the central case resolves the window to `max_year` and the futures to `min_year` |
| C13 | two events with the same name in one option | the owned options and the rent futures keep only the last one, while the rent central case keeps both. On the measured config the gap is $3,311 |
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
- the year by which half of the futures have fired it, or that fewer than half ever do.

When `rent.reset_hazard > 0` the read-back also says that the central case prices a tenancy that
never resets, and when a `price_shock` is stated, that it prices no crash. These are facts about
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

**E4. The single-path gate asks whether the futures' timing can differ, not which field is
non-zero.** An event is stochastic exactly when its fire-year distribution across futures is not
a single point, or its cost is drawn. The refusals of E2 remove the two cases that were misclassed.

**E5. The futures' affordability arrays place each event on each path**, as they already place
the reset (C12).

**E6. Left on the board, stated as conventions, not fixed here:** C6, C7, C10 and C11. Each is
the difference between one path and a mean, and each is small against its margin on every
measured household. The normal cost distribution's truncation bias is the one a user can pull
far with a large vol, so the board records it with its measured sizes.

## 3. What must stay true

- The seven shipped examples still load. `examples/advanced_config.yaml` states two hazard-timed
  events with windows, so its futures and its read-back change, as E1 and E3 intend. Every other
  example is byte-identical on `--json`.
- Every refusal names the key and the fact, and a test pins it, both for the refusal and for the
  legal config one step away from it.
- The read-back lines of E1 are pinned against the hazard schedule, computed independently in the
  test.
- A config that no longer loads because of E2 is never a shipped example, a test fixture, or a
  household in PROMPTS.md.
