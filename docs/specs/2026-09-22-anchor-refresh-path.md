# Anchors that survive their author — the refresh path

**2026-09-22** · board item 6 · artifact boundary, clause 3

---

## The problem, stated as it actually is

Twenty registry entries carry a `valid_until`. Nineteen of them lapse on
2026-12-31: the federal, Québec and Ontario income-tax bracket ceilings, the
three basic personal amounts, Ontario's two surtax thresholds, the two TFSA
room figures, and Québec's tax on mortgage-insurance premiums. The twentieth,
`hbp.repayment_grace_years`, lapses 2028-12-31.

Every one of those figures was fetched by hand, in a session, by the person who
built the engine. When the date passes the engine does the right thing — it
warns on every run that used a lapsed figure, and the suite turns red — but
neither of those tells anyone **what to go and read**, **where it is published**,
**whether anybody has looked**, or **what they found when they did**. The repair
is a research task that currently exists only in one person's head, which is the
definition of a resident-builder assumption and the thing the artifact boundary
forbids.

So this is not a "update nineteen numbers" item. Two things are missing and only
one of them is numbers.

---

## §1. What was refreshable today, and what was not

Checked 2026-09-21, primary sources only. **Zero of the nineteen values change
today.** Canadian personal-tax parameters for a year are published once the
indexation factor is known, which is November for the CRA and Finances Québec
and December for the T4032 payroll tables. September is too early, and the
engine is not permitted to compute the factor itself: an indexation factor
applied by this repo would be an estimate wearing a citation's clothes, which
`CLAUDE.md`'s honesty contract forbids in exactly those words.

| Source | What the page showed on 2026-09-21 | Verdict |
|---|---|---|
| CRA, indexation adjustment | columns 2023, 2024, 2025, 2026; "Indexation increase per year" ends at 2.0% (2026); no 2027 column | not published |
| CRA, current-year rates and brackets | "For income earned in: 2026"; no 2027 selection | not published |
| CRA, T4032-ON payroll tables | "Effective January 1, 2026"; page dated 2025-12-17; no 2027 edition linked | not published |
| Finances Québec, personal-tax parameters | `AUTEN_IncomeTax2027.pdf` and `AUTFR_RegimeImpot2027.pdf` both HTTP 404 | not published |
| Revenu Québec, TP-1015.F-V | `TP-1015.F-V(2027-01).pdf` HTTP 410 | not published |
| CRA, TFSA contribution room | 2026 limit $7,000; the 2027 limit is announced in November | not published |
| Norton Rose Fulbright / Baker Tilly on Bill 99 | "October 28, 2025, marked the enactment of Bill 99 providing for the increase, effective January 1st, 2027, in the Québec insurance premium tax (IPT) rate … from 9% to 9.975%" | **successor published** |

The last row is the one exception and it is instructive. The 2027 Québec IPT
rate is not a forecast — it is enacted law, and the registry has known it since
2026-09-03: it is the upper edge of the anchor's own band and it is named in the
anchor's rationale. But it does not change the anchor's value today, because 9%
is still the correct rate for a premium paid on or before 2026-12-31. The
refresh is a **known edit on a known date**, not a fetch.

Press reporting projects the 2027 TFSA limit at $7,500 on CPI data published so
far. That is a projection by a third party, not the publisher's figure. It does
not go in. The anchor stays at $7,000 and lapses loudly.

### §1.1 The one shape a refresh takes: `replaces`, never `restatements`

The registry has two fields that look like they might carry a new year's figure
and neither of them does:

- `restatements` is **the same figure in another convention** — 6.09% posted
  semi-annually is 6.1827% effective annually, one figure, two notations. A 2027
  bracket ceiling is not the 2026 ceiling in other units. It never goes here.
- `replaces` is `(old_value, why)`, and every instance today is a **correction**
  — an uncited default swapped for a sourced one.

There is no third field and there must not be one. A registry entry holds **one
current figure**: the engine has one bracket schedule per jurisdiction, and a
run in 2027 has no use for the 2026 ceilings. So a scheduled new edition
**replaces** the old figure in place, and `why` says which kind of change it was:

> `replaces=(58_523.0, "scheduled 2027 indexation, not a correction: $58,523 was the correct 2026 ceiling")`

That distinction matters to a reader of `--print-anchors`, because "this default
was wrong" and "this default aged out" are different statements about the
engine's past answers. Nothing sits beside anything. The refresh moves `value`,
`as_of`, `quoted`, `retrieved_on` and `valid_until` together, and records
`replaces`. That rule is stated once, in `anchors.REFRESH_PROCEDURE`, which
`hde --refresh-plan` prints; this paragraph describes it and does not restate it.

---

## §2. The four questions the mechanism has to answer

**How does anyone LEARN an anchor needs refreshing?** Today: a run-time warning
to a user who cannot act, and `test_no_dated_anchor_is_past_today`, which turns
red on the first day *after* a figure lapses. Both are alarms with no work order
attached, and the run-time one reaches the wrong person.

**What does a refresher need in front of them?** The figure as its source prints
it (so a new edition can be diffed against it), the URL of the next edition, the
publisher, and the sibling figures that come off the same release — because the
five federal bracket ceilings and the federal basic personal amount are not six
independent facts, they are one CRA release.

**How is a refresh VERIFIED rather than trusted?** By making the incomplete edit
fail: a value moved without its quote, a vintage moved without its validity
date, one sibling moved without the rest.

**What if nobody has published it yet?** That state must be recordable, dated,
and distinguishable from nobody having looked.

---

## §3. What is built

### 3.1 `Anchor.refresh_group` — which release publishes this figure

One new field on the existing dataclass. It names the publishing release, not
the URL and not the date: `"cra.federal_indexation"`, `"revenu_quebec.insurance_premium_tax"`.

`__post_init__` **refuses a dated anchor that does not name one**, in the same
breath as it refuses a live URL with no `retrieved_on`. A `valid_until` is a
promise that this figure will be replaced; an anchor that makes that promise and
cannot say who will publish the replacement is the defect this item exists to
remove.

The same method now also **refuses a dated anchor with no `quoted` or no
`unit`**. Reference entries have carried both since 2026-09-01 for a different
reason (a municipal rate read off the wrong base is the registry's most
dangerous number). For a dated entry the reason is the refresh: to replace a
figure correctly you must be able to see how the source printed it, and to know
what it was a rate or an amount *of*. One anchor needed them added —
`mortgage_insurance.premium_tax_rate.qc`, whose quote now carries the enacted
9% → 9.975% step verbatim.

### 3.2 `_RELEASE_EDITION` — one edition per release, and why it was not optional

Writing §3.1 exposed a defect that made the rest of this design unusable. The
registry held `_TAX_RETRIEVED` and `_TAX_YEAR_END` as constants shared by **five**
and **four** releases respectively, and `as_of="2026"` as a literal inside the
bracket generator, which runs for all three jurisdictions. So the refresh this
repo is about to tell a stranger to perform could not be performed. The CRA
publishes its indexation in November and Revenu Québec its parameters in
December; a refresher updating the federal figures in November had to move a
constant that also stamped Québec's and Ontario's — leaving the registry
asserting that Québec's 2026 brackets were the 2027 brackets, read on a day
nobody read them.

Nothing would have caught it. The citation guard passes (Québec's value still
matches Québec's quote), the date guard passes (2027 ≥ 2027), and a
members-agree-with-each-other sibling check passes too, because each release
stays internally coherent while three of them lie.

The fix is one row per release:

```python
_RELEASE_EDITION: Dict[str, Tuple[str, str, str]] = {   # (as_of, retrieved_on, valid_until)
    "cra.federal_indexation":             ("2026", "2026-09-05", "2026-12-31"),
    ...
}

def _edition(group: str, *, dated: bool) -> Dict[str, str]: ...
```

spread into every grouped anchor's constructor (`**_edition(group, dated=True)`),
so no member of a release can carry a date of its own and a refresh edits exactly
the row it read. `_TAX_YEAR_END` is deleted — nothing reads it any more.
`_TAX_RETRIEVED` survives for the seven entries that belong to **no** release
(the Québec abatement, the capital-gains inclusion rate, the principal-residence
exemption, the four FHSA limits): none is annually indexed and none carries a
validity date, so none is on the refresh path.

The refactor moved no figure, date or citation: all 117 anchor records are
byte-identical before and after, which is how it was checked.

This is the repo's own "sweep the siblings of any single-instance fix" one level
up — the single-instance fix was `refresh_group`, and the sibling was the shared
constant that made grouping meaningless.

### 3.3 `RefreshSource` — the record of a source, and of looking at it

A second frozen dataclass and a registry keyed by the same group name:

```python
@dataclass(frozen=True)
class RefreshSource:
    key: str                          # matches Anchor.refresh_group
    publisher: str                    # who publishes the next edition
    edition: str                      # what the next edition is called, in the publisher's words
    url: str = ""                     # where it appears; "" = the same URL its anchors cite
    checked_on: str = ""              # ISO date someone last looked
    found: str = ""                   # what the source showed on that date
    successor_published: bool = False # the next figure is already stated by the source
```

Three properties earn their places:

- **It does not list its members.** They are derived from `Anchor.refresh_group`,
  so membership has one home and a new anchor joins a release by saying so.
- **`url` is optional and `""` means "the same page the anchors already cite"** —
  true of the CRA indexation adjustment, where the 2027 column appears on the
  page the 2026 figures were read from. Québec's parameters PDF changes filename
  every year, so that record carries its own URL.
- **`checked_on` + `found` are the "nobody has published it" state**, and they
  are what stops a lapsing figure reading as neglect. "The CRA indexation page
  prints 2023–2026 and no 2027 column, checked 2026-09-21" is a completed piece
  of work, not an omission.

`successor_published` is the only stored status bit, and it carries the one
distinction a refresher acts on: *go and fetch* versus *the figure is already in
this anchor's own source, apply it on the date*. Everything else a status field
might say — lapsed, in force, how long is left — is **derived** from
`valid_until` against the run date and is not stored anywhere.

Six records cover all twenty dated anchors:

| group | dated members | undated siblings |
|---|---|---|
| `cra.federal_indexation` | 4 bracket ceilings, basic personal amount | 5 bracket rates |
| `cra.ontario_parameters` | 4 bracket ceilings, basic personal amount, 2 surtax thresholds | 5 bracket rates, 2 surtax rates |
| `revenu_quebec.personal_parameters` | 3 bracket ceilings, basic personal amount | 4 bracket rates |
| `cra.tfsa_limit` | annual limit, cumulative room | — |
| `cra.home_buyers_plan` | repayment grace years | withdrawal limit, repayment years |
| `revenu_quebec.insurance_premium_tax` | premium tax rate (QC) | — |

The undated siblings are in the groups deliberately. A rate carries no
`valid_until` because its source names no change to it, and that stays true —
but a refresher opening the 2027 T4032-ON re-reads the whole table, and the work
order should hand them the whole table.

### 3.4 `hde --refresh-plan [--refresh-plan-as-of YYYY-MM-DD]` — the work order

A new CLI surface printing one JSON document: every refresh group that has a
dated member, ranked by how soon its earliest figure stops being the figure.
Per group: the publisher, the edition to look for, the URL, the last check and
what it found, whether a successor is already published, the days remaining,
and the **full `anchor_to_dict` record of every member** — dated and undated,
in two lists. `anchor_to_dict` is the existing shape, not a second one, so a
figure's record reads identically here and under `--print-anchors`.

The document opens with `procedure`: `anchors.REFRESH_PROCEDURE`, the steps of a
correct refresh, stated once in the repo's own bytes rather than in this spec,
because a person doing the refresh in 2027 will have the CLI and may not have
`docs/specs/`.

**Exit code 3 when any figure has lapsed**, 0 otherwise. A figure that has not
lapsed yet is information, not a failure — a gate that fired for three months
with no published figure to fetch would be a gate whose red means nothing.

`--as-of` exists so the surface is testable and so a refresher can ask what
January looks like. It is the only clock the command reads.

### 3.5 Where the surface is named

`README.md`, `PROMPTS.md`, `docs/reference/API_CONTRACT.md`,
`docs/reference/CONFIG_SCHEMAS.md`, `AGENTS.md`, and a new gate §9 in
`.claude/skills/hde/references/gates.md`. The skill surface is the one that
matters: under the artifact boundary the stranger's Claude, in the session that
sees the lapsed-anchor warning, **is** the maintainer at that moment, and it is
the only agent in the loop that can act on it.

It went into `references/gates.md` rather than `SKILL.md` because the hot path
was measured at 2,599 words against its own 2,600-word cap
(`test_hot_path_stays_under_the_documented_body_budget`) — one word of headroom,
so a dispatch row could not land without displacing existing guidance, which
this item has no mandate to do. `gates.md` is where "why a gate exists and the
phrasing that satisfies it" already lives, the validity `[warning]` IS such a
gate, and reference files carry no budget. That the hot path is at its ceiling is
a finding for whoever next wants to add to it, not something this item resolved.

---

## §4. What fails, and on which mistake

Each test is named for the mistake it catches, and each was run against a
mutation before being trusted.

| Mistake | What goes red |
|---|---|
| a new dated anchor names no release | `AnchorError` at import; `test_a_dated_anchor_must_name_the_release_that_publishes_it` |
| a dated anchor carries no quote or no unit | `AnchorError` at import; `test_a_dated_anchor_must_carry_the_figure_as_quoted` |
| a group name is typo'd or its record is deleted | `test_every_dated_anchor_names_a_registered_refresh_source` |
| a record is left behind after its anchors go | `test_every_refresh_source_covers_a_dated_anchor` |
| a release's edition row is deleted | `KeyError` at import — the registry cannot be built at all |
| an edition row names a release nothing reads | `test_every_release_declares_exactly_one_edition` |
| **one sibling refreshed, the rest left at the old edition** | `test_every_member_carries_its_releases_edition` |
| **a value retyped, its `quoted` citation left stale** | `test_a_dated_dollar_figure_is_quoted_as_its_source_prints_it` |
| **`as_of` moved to the new year, `valid_until` left behind** | `test_a_refreshed_figure_cannot_outlive_its_own_vintage` |
| the work order silently omits a dated anchor | `test_the_plan_carries_every_dated_anchor` |
| a lapsed registry reports success | `test_the_cli_refuses_once_a_figure_has_lapsed` |

Two of these are honest about their own limits.

`test_every_member_carries_its_releases_edition` is a self-consistency test, and
the standing question for those is whether they can fail on any registry. This
one can, because each member is pinned to its release's **single declared
edition**, not merely to its siblings — but it is also partly redundant today:
`test_tax_anchors.py` already pins `retrieved_on == "2026-09-05"` and
`as_of == "2026"` as literals across the whole tax family, so a partial edit
there fails twice. It earns its place on the small groups, and it is the check
that keeps working after the family literal is updated to the 2027 pass, which a
mutation demonstrates: with that literal updated exactly as the refresh
requires, it is the only test in the suite that fires.

What is NOT caught by any test, only by the structure: re-introducing a shared
date constant while every release's dates still happen to coincide. `_edition`
is the sanctioned path and `_RELEASE_EDITION` is the only place these dates are
written, but a future anchor hardcoding `retrieved_on=_TAX_RETRIEVED` on a day
when that equals its release's date would pass. The comment on `_TAX_RETRIEVED`
names which seven entries may read it and why.

`test_a_dated_dollar_figure_is_quoted_as_its_source_prints_it` scopes itself to
dated anchors whose `unit` begins with "dollars", and declares one exemption
with its reason: `tfsa.cumulative_room_since_2009` is a **sum** of the quoted
table rather than a figure the CRA prints, and `test_tfsa_cumulative_room_is_the_sum_of_the_quoted_table`
already pins it against that arithmetic. A new dated dollar anchor must quote
its figure or be added to that list with a reason, which is the declaration
pattern `CONSUMED_ELSEWHERE` already uses.

### §4.1 Tests written and then removed

Two drafts did not survive the standing question "would this fail if the
implementation were wrong in the way it claims to guard?".

`test_no_2027_figure_was_invented` asserted `as_of == "2026"` on every dated
anchor. Its docstring promised it would catch a fabricated 2027 figure; the
assertion cannot, because it reddens identically on a **legitimate** 2027
refresh. It was also redundant with `test_tax_anchors.py`'s literal. Removed.

`test_every_record_was_actually_checked` asserted a non-empty `found` — already
refused at construction — and `checked_on <= 2026-09-21`, which turns red on the
November check, i.e. on the correct action. Removed.

What replaced them is the class `TestTodaysRegistry`, documented as what it is:
**today-pins**, in the pattern `test_no_dated_anchor_is_past_today` already
establishes. Each records a decision this pass made about what NOT to put in the
registry — the successor is not applied, the projection is not a figure — and
each reddens on the refresh that supersedes it, which is the point: the refresher
must look at the decision and replace it rather than inherit it silently.

---

## §5. Rejected

**A second warning line in the run's output pointing at the command.** It reaches
the person who cannot act, costs a verbatim-pinned shipped string in five tests,
and puts a second voice in the warnings channel talking about lapse. The skill
gate reaches the same session's Claude — who *can* act — for no shipped byte.

**A `successor` value field on `Anchor` holding the 2027 figure.** For the Québec
IPT the 9.975% is already in the anchor's `band`, its `source` and its
`rationale`; a fourth, machine-readable copy with no alarm between it and the
other three is the truth-homes defect. `successor_published` records *that* the
source states it; the anchor itself states *what*.

**A separate anchor for the 2027 figure sitting beside the 2026 one.** The engine
holds one figure per key, and a second one would need a `valid_from`, a
resolution rule, and a closing date the engine does not model. It would change
computed answers to solve a bookkeeping problem. §1.1 is the rule instead.

**A filter on `--print-anchors`.** The work order is grouped by release, ranked by
date, and carries a check record and a procedure — none of which is a property of
an anchor. It shares `anchor_to_dict` and nothing else.

**A staleness gate on `checked_on`** (red once a check is older than N days). It
would fail on a clock with no published figure to fetch, and the repo would ship
a red suite to strangers. The check record is reported by `--refresh-plan`, not
enforced by the suite.

**A scheduled CI job.** It is the mechanism that would actually survive the
author — and the repo has no `.github/` at all. Standing one up is a delivery
decision that belongs with board item 9, not a side effect of this one. §6 says
so plainly instead of pretending otherwise.

---

## §6. What still depends on a person remembering

With no CI in this repo, **nothing runs `--refresh-plan` on a schedule.** The
alarms that fire without anyone deciding to look are unchanged in kind: the
suite goes red the day after a figure lapses, and a run that used one warns. What
this item changes is that both of those now have a work order behind them that a
stranger can execute — but somebody still has to run the suite, or read the
warning, or open the plan.

The honest one-line version: this item converts "only the author can repair it"
into "anyone can repair it", and leaves "somebody has to notice" for board item 9
to close with a delivery form that has a scheduler in it.
