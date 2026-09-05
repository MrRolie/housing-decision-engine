"""The input contract, emitted as data (agents query the living
schema; docs rot, this cannot). REQUIRED flags and NOTES are hand-curated beside
the machine key-sets; a test pins completeness against `_SECTION_KEYS` so a key
added to the parser without a schema entry fails the suite.
"""
from __future__ import annotations

from typing import Any, Dict

from .anchors import ANCHORS
from .config import _SECTION_KEYS

_NOMINAL_PLANNING = ANCHORS["economic.inflation_rate.nominal_planning"]

# Jurisdictions the registry has no source for, read OFF the registry so the
# note cannot claim "source: none" for a city that has since been sourced.
_UNSOURCED_JURISDICTIONS = ", ".join(
    name.split(".", 1)[1].replace("_", " ").title()
    for name, anchor in sorted(ANCHORS.items())
    if name.startswith("property_tax.") and anchor.kind == "unsourced"
)

# key -> (required?, note[, required_if]) per section; top-level scalars AND the
# section blocks themselves live under "top". `required` means "required when the
# block is present"; `required_if` states a conditional requirement in the
# validator's own words so the schema and the refusal can never disagree.
_NOTES: Dict[str, Dict[str, Any]] = {
    "top": {
        "years": (True, "analysis horizon in years (>=1)"),
        "discount_rate": (False, "annual discount rate — the household's opportunity cost, "
                                  "DECIMAL (0.05 = 5%), AS QUOTED like every typed rate: the "
                                  "engine deflates it by inflation_rate in real mode and uses it "
                                  "as typed in nominal mode, and the read-back shows both forms; "
                                  "DEFAULT 0.03 real = the anchored investment return (FP Canada "
                                  "2026 PAG 60/40), composed with inflation_rate in nominal mode"),
        "rates": (False, "'as_quoted' (DEFAULT) or 'real' — the convention of every rate you "
                         "TYPE (growth, escalation, return and discount rates; never "
                         "mortgage_rate, a contract rate): as_quoted means the figure as you see "
                         "it quoted, converted ONCE at load — deflated by inflation_rate in real "
                         "mode, (1 + r)/(1 + π) − 1, used as typed in nominal mode — and the "
                         "read-back's `rates:` line shows both forms; 'real' means your figures "
                         "are already real and are read as before (composed with inflation_rate "
                         "in nominal mode). Anchored defaults are real either way"),
        # Section blocks: all optional, but at least one option must be present;
        # a key marked required inside a block is required only when the block is.
        "condo": (False, "optional block — at least ONE of condo / house / rent must be "
                         "present; keys marked required apply only when the block is present"),
        "house": (False, "optional block — at least ONE of condo / house / rent must be present"),
        "rent": (False, "optional block — at least ONE of condo / house / rent must be present"),
        "income": (False, "optional block; enables affordability ratios"),
        "simulation": (False, "optional block; Monte Carlo + uncertainty knobs"),
        "economic": (False, "optional block; real (default) vs nominal mode"),
        "market_scenario": (False, "optional block; demographic prior (path + geography)"),
        "tax": (False, "optional block — the tax treatment of the two sides' money "
                       "(docs/specs/2026-09-05-tax-treatment.md): the renter's TAXABLE share earns "
                       "the after-tax return (sheltered TFSA / RRSP / FHSA shares untouched), the "
                       "owner's principal-residence exemption is named, and for a first_time_buyer "
                       "the FHSA refunds and a Home Buyers' Plan withdrawal join the day-one cash. "
                       "Absent = neither side taxed (the engine warns when the renter holds "
                       "capital). Keys: marginal_rate, renter_capital, taxable_return_treatment, "
                       "retirement_marginal_rate, fhsa, hbp_withdrawal"),
        "province": (False, "QC | ON | other — the jurisdiction whose tax on insurance "
                            "premiums applies to a mortgage-insurance premium (CMHC: the "
                            "tax 'can't be added to the loan amount', so it is cash at "
                            "closing). REQUIRED with mortgage_insurance: auto; an option "
                            "may override it (an Ottawa-vs-Gatineau config prices two "
                            "provinces at once). Rates: QC 9%, ON 8%, other 0%. Québec's "
                            "rate rises to 9.975% for premiums paid after 2026-12-31 "
                            "(Bill 99) — the engine applies 9% and names it. SK taxes the "
                            "premium but its rate is not anchored: state an explicit "
                            "schedule instead of being charged 0%. QUOTE THE CODE — "
                            "province: \"ON\" — an unquoted ON (or NO / YES / OFF) is a YAML "
                            "boolean and is refused with that hint"),
        "sources": (False, "optional block; WHO stated each value — a mapping from a dotted "
                           "config key the config actually sets (e.g. rent.monthly_rent, "
                           "simulation.investment_return_vol, house.events for a whole list) to "
                           "'user' (the user's own figure), 'assistant' (a value typed on their "
                           "behalf) or 'anchor:<name>' (a name from --print-anchors). Affects NO "
                           "computation: it splits the assumption echo into user-stated / "
                           "assistant-typed / anchor-sourced / unattributed lines, and lets the "
                           "engine warn when Monte Carlo decisiveness rests on uncertainty inputs "
                           "the user never stated. Declare a key that the config does not set, a "
                           "value outside those three forms, or an anchor name outside the "
                           "registry, and the load refuses. An other_recurring_costs LINE is "
                           "declared by NAME — <option>.other_recurring_costs.<line name>."
                           "annual_amount (or .escalation_rate) — so a $813 insurance line "
                           "may declare anchor:home_insurance.qc and a dollar tax line "
                           "anchor:property_tax.<municipality> (compared as amount ÷ "
                           "initial_value, the read-back's own probe); the bare list key stays "
                           "user | assistant only, and an unknown line name is refused naming "
                           "the lines that exist"),
    },
    "condo": {
        "initial_value": (True, "purchase price in DOLLARS (480000, not 480)"),
        "value_growth_rate": (False, "annual price growth, decimal, AS QUOTED — the engine "
                                       "deflates it by inflation_rate in real mode and uses it as "
                                       "typed in nominal mode; the read-back shows both forms; "
                                       "default 0.0 real — neutral, no universal long-run real "
                                       "default; set your view or a market_scenario prior. With a "
                                       "prior, its drift is ADDED to this base in the Monte Carlo; "
                                       "the deterministic line uses this base alone"),
        "monthly_fee": (True, "condo fee, $/month — REQUIRED whenever a condo: block is "
                             "present; use 0 for a fee-free unit"),
        "fee_escalation_rate": (False, "annual fee growth, decimal, AS QUOTED (converted once at "
                                       "load like value_growth_rate); default 0.0 real — fees "
                                       "track inflation"),
        "down_payment": (False, "$ paid at purchase; with mortgage_rate + mortgage_term_years "
                               "it is the capital structure", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "cash_available": (False, "$ of cash you bring to the closing table — an ALTERNATIVE to "
                                   "down_payment, never both: the engine nets purchase_costs out of "
                                   "it and the remainder IS the down payment (financed_purchase_costs "
                                   "ride the loan and are NOT netted). Use it when you know the pile "
                                   "rather than the split; the assumptions line shows the netting, and "
                                   "the loan-to-value and the 20% mortgage-insurance test read the "
                                   "computed figure. Like-for-like rent.invested_down_payment = this "
                                   "number", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_rate": (False, "EFFECTIVE ANNUAL rate, decimal, with ANNUAL level payments; "
                                "a Canadian posted rate is semi-annually compounded — convert: "
                                "r_eff = (1 + r_posted/2)^2 − 1. No quote in hand? "
                                "`hde --print-anchors` → `mortgage_rate.posted_5y`, the Bank of "
                                "Canada's weekly POSTED 5-year conventional rate: a list price and "
                                "so a CEILING — contracted rates run lower, and the anchor's "
                                "rationale carries what borrowers actually paid", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_term_years": (False, "amortization term in years", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "all_cash": (False, "true = the whole price is paid at purchase, no financing", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026); "
                                       "dominates short horizons"),
        "purchase_costs": (False, "$ paid at purchase (year 0, undiscounted, outside the "
                                   "affordability ratio): land-transfer/welcome tax, notary, "
                                   "inspection, a mortgage-insurance premium paid in cash; "
                                   "default 0 — warns when an owned option models no purchase "
                                   "or carrying costs. Use purchase_costs_rate instead when the "
                                   "price is the thing being swept or solved"),
        "purchase_costs_rate": (False, "closing costs as a FRACTION of the price (0.03 = 3%) — an "
                                        "ALTERNATIVE to purchase_costs, never both: the loader "
                                        "derives the dollars from initial_value on EVERY load, so "
                                        "--sweep / --break-even on the price re-derive them (a "
                                        "dollar figure stays sized for the seed price and moves the "
                                        "threshold it reports); cash_available nets the DERIVED "
                                        "figure"),
        "property_tax_rate": (False, "annual property tax as a FRACTION of value (0.0085 = 0.85%/yr) "
                                      "— an ALTERNATIVE to an other_recurring_costs tax line, never "
                                      "both: the loader derives the bill from initial_value on EVERY "
                                      "load, so a price sweep or break-even re-derives it, and it "
                                      "escalates at this option's value_growth_rate so it stays that "
                                      "fraction of the home's value. No default: absent means no "
                                      "property tax is modelled, and the missing-costs warning "
                                      "fires only if other_recurring_costs is empty too"),
        "financed_purchase_costs": (False, "$ rolled INTO THE LOAN at purchase — a financed "
                                            "mortgage-insurance premium (CMHC/Sagen, due under 20% "
                                            "down): raises the payment and the balance, never year-0 "
                                            "cash; requires the mortgage block; default 0. The MANUAL "
                                            "path: prefer mortgage_insurance: auto, which derives the "
                                            "premium from the anchored schedule and re-derives it at "
                                            "every --sweep / --break-even grid point. Refused together "
                                            "with mortgage_insurance (double counting)"),
        "mortgage_insurance": (False, "'none' (DEFAULT — nothing priced, today's behaviour), 'auto' "
                                       "(the anchored CMHC schedule — --print-anchors lists every "
                                       "band), or an explicit {bands: [{ltv_max, rate}], "
                                       "premium_tax_rate} schedule for your lender's own sheet. With "
                                       "auto above 80% loan-to-value the engine picks the tier on the "
                                       "loan BEFORE the premium, ADDS the premium to the loan, and "
                                       "pays the provincial tax on it in CASH — netted out of "
                                       "cash_available when stated, else added to purchase_costs "
                                       "(CMHC: the tax 'can't be added to the loan amount'). Adds "
                                       "0.20% when mortgage_term_years exceeds 25. Needs province; "
                                       "refuses all_cash, financed_purchase_costs, and a loan-to-value "
                                       "above the schedule maximum (95%), quoting both figures"),
        "province": (False, "QC | ON | other for THIS option, overriding the top-level province: the "
                             "tax on the mortgage-insurance premium and the land-transfer-tax "
                             "schedule both follow the property's own jurisdiction, so an "
                             "Ottawa-vs-Gatineau comparison prices each side correctly. See the "
                             "top-level province note for the rates. Quote it (province: \"ON\"): "
                             "an unquoted ON is a YAML boolean and is refused"),
        "land_transfer_tax": (False, "'none' (DEFAULT — nothing priced), 'auto' (the anchored "
                                      "schedule for this option's province and municipality — "
                                      "--print-anchors lists every bracket), or an explicit "
                                      "{brackets: [{up_to, rate}], first_time_buyer_rebate} schedule "
                                      "(omit up_to on the last bracket for the uncapped top band). "
                                      "The duty is CASH at closing: it is ADDED to purchase_costs / "
                                      "purchase_costs_rate — which go on covering notary, inspection "
                                      "and the rest — and so netted out of cash_available when you "
                                      "state one. Derived on every load, so --sweep and --break-even "
                                      "re-derive it at each price. Anchored schedules: QC and ON "
                                      "provincial, montreal (which REPLACES the Québec table) and "
                                      "toronto (which ADDS to Ontario's). Needs province; refuses a "
                                      "municipality outside its province, and a province with no "
                                      "anchored schedule rather than charge $0 of a tax really owed. "
                                      "The base is the PRICE — in Québec the duty is levied on the "
                                      "GREATER of price and municipal assessment × the year's "
                                      "comparative factor, so a purchase well under assessment is "
                                      "under-taxed here"),
        "municipality": (False, "montreal | toronto — the city whose own transfer-tax schedule "
                                 "applies; read only with land_transfer_tax: auto. Omit for the "
                                 "provincial schedule alone. Montréal publishes one complete table "
                                 "that REPLACES the provincial one; Toronto's municipal tax is "
                                 "charged IN ADDITION to Ontario's. Stated alone, it also places "
                                 "the option in its province for the coherence notes (montreal → "
                                 "QC school tax; toronto → the Ontario assessment base)"),
        "first_time_buyer": (False, "true | false (DEFAULT false) — applies the anchored "
                                     "first-time-buyer rebate where the schedule has one (Ontario "
                                     "refund max $4,000, Toronto rebate max $4,475; neither Québec "
                                     "schedule has an anchored rebate, and the read-back says so "
                                     "rather than implying a zero was computed). Each rebate is "
                                     "capped at its own leg's tax, so it never becomes a payment to "
                                     "the buyer. This is YOUR assertion that you qualify: the engine "
                                     "cannot check age, occupancy, or prior ownership anywhere in "
                                     "the world"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs during "
                          "the horizon (roof, appliances, special assessment); purchase-time "
                          "costs belong in purchase_costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "property tax, home/unit insurance, utilities the "
                                         "owner pays; escalation_rate is AS QUOTED like every "
                                         "typed rate (deflated by inflation_rate in real mode, "
                                         "used as typed in nominal mode; omitted = 0.0 real, the "
                                         "line tracks inflation). PROPERTY TAX AND HOME "
                                         "INSURANCE ARE YOUR OWN FIGURES — the engine applies "
                                         "no default for either. Published figures to check "
                                         "them against: `hde --print-anchors`, keys "
                                         "property_tax.<municipality> and "
                                         "home_insurance.<province>; a line named 'property "
                                         "tax' or 'insurance' is cited by name in the "
                                         "assumptions read-back when your figure equals a "
                                         "published one. Municipal rates are levied on "
                                         "ASSESSED value, which is not market value (Ontario's "
                                         "2026 assessments are January 2016 values), so a rate "
                                         "× purchase price is an approximation. Québec's "
                                         "school tax is a separate provincial levy on top "
                                         "of the municipal rate (school_tax.qc). No source "
                                         f"registered for: {_UNSOURCED_JURISDICTIONS}. A Québec "
                                         "option (province QC or municipality montreal) with a "
                                         "property-tax line and no line named for the school tax "
                                         "gets a coherence warning naming the rate; an Ontario "
                                         "tax line no anchor matches carries the 2016 assessment "
                                         "base in its read-back line. Declare a line's source by "
                                         "name: sources: <option>.other_recurring_costs.<line "
                                         "name>.annual_amount"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
        "reserve_contribution_rate": (False, "fraction of each year's fees set aside into the "
                                             "reserve fund; default 0 = reserve not modelled"),
        "reserve_initial_balance": (False, "$ in the reserve fund at year 0; default 0"),
        "reserve_growth_rate": (False, "annual growth on the reserve balance, decimal, AS QUOTED "
                                       "(converted once at load like every typed rate); default 0 "
                                       "real"),
    },
    "house": {
        "initial_value": (True, "purchase price in DOLLARS"),
        "value_growth_rate": (False, "annual price growth, decimal, AS QUOTED — the engine "
                                       "deflates it by inflation_rate in real mode and uses it as "
                                       "typed in nominal mode; the read-back shows both forms; "
                                       "default 0.0 real — neutral, no universal long-run real "
                                       "default; set your view or a market_scenario prior. With a "
                                       "prior, its drift is ADDED to this base in the Monte Carlo; "
                                       "the deterministic line uses this base alone"),
        "annual_maintenance_rate": (False, "fraction of value per year; DEFAULT 0.0 = no "
                                            "maintenance modelled (neutral, warns when omitted); "
                                            "NAHB 2019 AHS routine ≈ 0.6% of value/yr"),
        "maintenance_curve": (False, "list of {year, rate} overrides"),
        "down_payment": (False, "$ paid at purchase; with mortgage_rate + mortgage_term_years "
                               "it is the capital structure", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "cash_available": (False, "$ of cash you bring to the closing table — an ALTERNATIVE to "
                                   "down_payment, never both: the engine nets purchase_costs out of "
                                   "it and the remainder IS the down payment (financed_purchase_costs "
                                   "ride the loan and are NOT netted). Use it when you know the pile "
                                   "rather than the split; the assumptions line shows the netting, and "
                                   "the loan-to-value and the 20% mortgage-insurance test read the "
                                   "computed figure. Like-for-like rent.invested_down_payment = this "
                                   "number", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_rate": (False, "EFFECTIVE ANNUAL rate, decimal, with ANNUAL level payments; "
                                "a Canadian posted rate is semi-annually compounded — convert: "
                                "r_eff = (1 + r_posted/2)^2 − 1. No quote in hand? "
                                "`hde --print-anchors` → `mortgage_rate.posted_5y`, the Bank of "
                                "Canada's weekly POSTED 5-year conventional rate: a list price and "
                                "so a CEILING — contracted rates run lower, and the anchor's "
                                "rationale carries what borrowers actually paid", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_term_years": (False, "amortization term in years", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "all_cash": (False, "true = the whole price is paid at purchase, no financing", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026)"),
        "purchase_costs": (False, "$ paid at purchase (year 0, undiscounted, outside the "
                                   "affordability ratio): land-transfer/welcome tax, notary, "
                                   "inspection, a mortgage-insurance premium paid in cash; "
                                   "default 0 — warns when an owned option models no purchase "
                                   "or carrying costs. Use purchase_costs_rate instead when the "
                                   "price is the thing being swept or solved"),
        "purchase_costs_rate": (False, "closing costs as a FRACTION of the price (0.03 = 3%) — an "
                                        "ALTERNATIVE to purchase_costs, never both: the loader "
                                        "derives the dollars from initial_value on EVERY load, so "
                                        "--sweep / --break-even on the price re-derive them (a "
                                        "dollar figure stays sized for the seed price and moves the "
                                        "threshold it reports); cash_available nets the DERIVED "
                                        "figure"),
        "property_tax_rate": (False, "annual property tax as a FRACTION of value (0.0085 = 0.85%/yr) "
                                      "— an ALTERNATIVE to an other_recurring_costs tax line, never "
                                      "both: the loader derives the bill from initial_value on EVERY "
                                      "load, so a price sweep or break-even re-derives it, and it "
                                      "escalates at this option's value_growth_rate so it stays that "
                                      "fraction of the home's value. No default: absent means no "
                                      "property tax is modelled, and the missing-costs warning "
                                      "fires only if other_recurring_costs is empty too"),
        "financed_purchase_costs": (False, "$ rolled INTO THE LOAN at purchase — a financed "
                                            "mortgage-insurance premium (CMHC/Sagen, due under 20% "
                                            "down): raises the payment and the balance, never year-0 "
                                            "cash; requires the mortgage block; default 0. The MANUAL "
                                            "path: prefer mortgage_insurance: auto, which derives the "
                                            "premium from the anchored schedule and re-derives it at "
                                            "every --sweep / --break-even grid point. Refused together "
                                            "with mortgage_insurance (double counting)"),
        "mortgage_insurance": (False, "'none' (DEFAULT — nothing priced, today's behaviour), 'auto' "
                                       "(the anchored CMHC schedule — --print-anchors lists every "
                                       "band), or an explicit {bands: [{ltv_max, rate}], "
                                       "premium_tax_rate} schedule for your lender's own sheet. With "
                                       "auto above 80% loan-to-value the engine picks the tier on the "
                                       "loan BEFORE the premium, ADDS the premium to the loan, and "
                                       "pays the provincial tax on it in CASH — netted out of "
                                       "cash_available when stated, else added to purchase_costs "
                                       "(CMHC: the tax 'can't be added to the loan amount'). Adds "
                                       "0.20% when mortgage_term_years exceeds 25. Needs province; "
                                       "refuses all_cash, financed_purchase_costs, and a loan-to-value "
                                       "above the schedule maximum (95%), quoting both figures"),
        "province": (False, "QC | ON | other for THIS option, overriding the top-level province: the "
                             "tax on the mortgage-insurance premium and the land-transfer-tax "
                             "schedule both follow the property's own jurisdiction, so an "
                             "Ottawa-vs-Gatineau comparison prices each side correctly. See the "
                             "top-level province note for the rates. Quote it (province: \"ON\"): "
                             "an unquoted ON is a YAML boolean and is refused"),
        "land_transfer_tax": (False, "'none' (DEFAULT — nothing priced), 'auto' (the anchored "
                                      "schedule for this option's province and municipality — "
                                      "--print-anchors lists every bracket), or an explicit "
                                      "{brackets: [{up_to, rate}], first_time_buyer_rebate} schedule "
                                      "(omit up_to on the last bracket for the uncapped top band). "
                                      "The duty is CASH at closing: it is ADDED to purchase_costs / "
                                      "purchase_costs_rate — which go on covering notary, inspection "
                                      "and the rest — and so netted out of cash_available when you "
                                      "state one. Derived on every load, so --sweep and --break-even "
                                      "re-derive it at each price. Anchored schedules: QC and ON "
                                      "provincial, montreal (which REPLACES the Québec table) and "
                                      "toronto (which ADDS to Ontario's). Needs province; refuses a "
                                      "municipality outside its province, and a province with no "
                                      "anchored schedule rather than charge $0 of a tax really owed. "
                                      "The base is the PRICE — in Québec the duty is levied on the "
                                      "GREATER of price and municipal assessment × the year's "
                                      "comparative factor, so a purchase well under assessment is "
                                      "under-taxed here"),
        "municipality": (False, "montreal | toronto — the city whose own transfer-tax schedule "
                                 "applies; read only with land_transfer_tax: auto. Omit for the "
                                 "provincial schedule alone. Montréal publishes one complete table "
                                 "that REPLACES the provincial one; Toronto's municipal tax is "
                                 "charged IN ADDITION to Ontario's. Stated alone, it also places "
                                 "the option in its province for the coherence notes (montreal → "
                                 "QC school tax; toronto → the Ontario assessment base)"),
        "first_time_buyer": (False, "true | false (DEFAULT false) — applies the anchored "
                                     "first-time-buyer rebate where the schedule has one (Ontario "
                                     "refund max $4,000, Toronto rebate max $4,475; neither Québec "
                                     "schedule has an anchored rebate, and the read-back says so "
                                     "rather than implying a zero was computed). Each rebate is "
                                     "capped at its own leg's tax, so it never becomes a payment to "
                                     "the buyer. This is YOUR assertion that you qualify: the engine "
                                     "cannot check age, occupancy, or prior ownership anywhere in "
                                     "the world"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs during "
                          "the horizon (roof, appliances, special assessment); purchase-time "
                          "costs belong in purchase_costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "property tax, home/unit insurance, utilities the "
                                         "owner pays; escalation_rate is AS QUOTED like every "
                                         "typed rate (deflated by inflation_rate in real mode, "
                                         "used as typed in nominal mode; omitted = 0.0 real, the "
                                         "line tracks inflation). PROPERTY TAX AND HOME "
                                         "INSURANCE ARE YOUR OWN FIGURES — the engine applies "
                                         "no default for either. Published figures to check "
                                         "them against: `hde --print-anchors`, keys "
                                         "property_tax.<municipality> and "
                                         "home_insurance.<province>; a line named 'property "
                                         "tax' or 'insurance' is cited by name in the "
                                         "assumptions read-back when your figure equals a "
                                         "published one. Municipal rates are levied on "
                                         "ASSESSED value, which is not market value (Ontario's "
                                         "2026 assessments are January 2016 values), so a rate "
                                         "× purchase price is an approximation. Québec's "
                                         "school tax is a separate provincial levy on top "
                                         "of the municipal rate (school_tax.qc). No source "
                                         f"registered for: {_UNSOURCED_JURISDICTIONS}. A Québec "
                                         "option (province QC or municipality montreal) with a "
                                         "property-tax line and no line named for the school tax "
                                         "gets a coherence warning naming the rate; an Ontario "
                                         "tax line no anchor matches carries the 2016 assessment "
                                         "base in its read-back line. Declare a line's source by "
                                         "name: sources: <option>.other_recurring_costs.<line "
                                         "name>.annual_amount"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
    },
    "rent": {
        "monthly_rent": (True, "$/month"),
        "rent_escalation_rate": (False, "annual, AS QUOTED — the figure as your lease or market "
                                          "quotes it, converted once at load (deflated by "
                                          "inflation_rate in real mode, used as typed in nominal "
                                          "mode; the read-back shows both forms); DEFAULT 0.01 real "
                                          "(FP Canada 2026 PAG shelter-cost growth, 3.1% quoted)"),
        "invested_down_payment": (False, "capital the renter keeps invested instead of buying: charged at year 0 like "
                                        "the buyer's down payment and credited at its terminal value; like-for-like "
                                        "= the buyer's TOTAL year-0 cash, down_payment + purchase_costs (all cash: "
                                        "price + purchase_costs); DEFAULT 0 = assume it earns exactly the discount rate"),
        "investment_return_rate": (False, "annual, AS QUOTED — the return as your fund quotes "
                                            "it, converted once at load like value growth; "
                                            "DEFAULT 0.03 real (FP Canada 2026 PAG 60/40, ≈ 5.1% "
                                            "quoted)"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs such as "
                          "moving costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "tenant insurance, parking, utilities the tenant pays. "
                                         "The home_insurance.* anchors are HOMEOWNER premiums "
                                         "and are deliberately never matched against a tenant "
                                         "policy: different product, different price"),
    },
    "economic": {
        "mode": (False, '"real" (DEFAULT) or "nominal". In both, a typed growth, escalation, '
                        'return or discount rate is AS QUOTED (top-level rates: as_quoted, the '
                        'default): deflated by inflation_rate in real mode, used as typed in '
                        'nominal mode; anchored defaults are real and the engine composes '
                        'inflation_rate on top of them in nominal mode; mortgage_rate — a quoted '
                        'contract rate — is used as entered in both. Nominal mode keeps the payment '
                        'a lender actually collects, which is why a mortgage runs there'),
        "inflation_rate": (False, "the deflator of every rate typed as quoted in real mode, and "
                                    "the rate composed onto the real defaults in nominal mode; "
                                    f"DEFAULT in real mode {_NOMINAL_PLANNING.value} "
                                    f"({_NOMINAL_PLANNING.short_cite}, echoed under defaults "
                                    "applied), 0.0 in nominal mode (the engine warns and suggests "
                                    "the same figure) and under rates: real (inert there)"),
        "inflation_vol": (False, "drives correlated cost shocks; default 0.0"),
    },
    "income": {
        "annual_income": (True, "$/year — REQUIRED whenever an income: block is present; "
                                "the block itself is optional (omit it to skip affordability)"),
        "income_growth_rate": (False, "annual, AS QUOTED (converted once at load like every "
                                        "typed rate, so income and costs share one convention in "
                                        "the affordability ratio); DEFAULT 0.01 real (FP Canada "
                                        "2026 PAG salary growth, 3.1% quoted)"),
        "affordability_threshold": (False, "cost/income ratio; DEFAULT 0.32 (legacy GDS "
                                             "32%, below CMHC's 39% cap)"),
        "pay_drop_events": (False, "list of {year, magnitude, year_jitter_std, magnitude_vol}; "
                                    "magnitude = retained-income fraction in (0, 1] (0.8 = 20% "
                                    "cut); shocked draws are clamped to [0.01, 1.0]"),
    },
    "simulation": {
        "num_sims": (False, "Monte Carlo paths; default 10,000"),
        "random_seed": (False, "default 42 — same seed, same answer"),
        "house_maintenance_vol": (False, "annual vol of house maintenance (lognormal "
                                         "multiplicative shock); uncertainty knobs all "
                                         "default 0 = single-path run, NOT a forecast"),
        "condo_fee_vol": (False, "annual vol of condo fees; default 0 (see house_maintenance_vol)"),
        "other_cost_vol": (False, "annual vol of other recurring costs; default 0"),
        "rent_escalation_vol": (False, "vol of the rent escalation rate per path; default 0"),
        "investment_return_vol": (False, "ANNUAL volatility of the renter's gross return "
                                           "(one mean-preserving shock per year on 1 + r, so "
                                           "capital can end below principal): 0.10 ≈ a 60/40 "
                                           "portfolio, 0.16 ≈ all equities; default 0 = risk-free "
                                           "at investment_return_rate (asymmetric against an "
                                           "owned option with price_shock — the engine warns)"),
        "corr_inflation_house": (False, "correlation of house-maintenance shocks with the "
                                        "inflation shock, [-1, 1]; default 0; inert unless "
                                        "economic.inflation_vol > 0"),
        "corr_inflation_condo": (False, "correlation of condo-fee shocks with inflation, [-1, 1]; default 0"),
        "corr_inflation_other": (False, "correlation of other-cost shocks with inflation, [-1, 1]; default 0"),
        "corr_inflation_event_cost": (False, "correlation of event-cost shocks with inflation, [-1, 1]; default 0"),
        "shock_model": (False, '"lognormal" (default) or "normal"'),
    },
    "tax": {
        "marginal_rate": (False, "the household's combined marginal income-tax rate as a FRACTION "
                                 "in [0, 1) (0.3612 = 36.12%) — never a percentage, never "
                                 "converted by the rates convention. Omit it to have the engine "
                                 "resolve it from income.annual_income and the top-level province "
                                 "(QC or ON) through the registry's 2026 brackets "
                                 "(tax_rates.marginal_rate: the Québec abatement or the Ontario "
                                 "surtax applied); the read-back names the derivation. Held flat "
                                 "for the run",
                          "tax: type marginal_rate, or state income.annual_income with a top-level province of QC or ON — refused when neither is available"),
        "renter_capital": (False, "{tfsa, rrsp, fhsa, taxable} in DOLLARS — where the renter's "
                                  "invested capital sits at year 0; REQUIRED when "
                                  "rent.invested_down_payment > 0 and refused without a rent: "
                                  "block; the shares must sum to rent.invested_down_payment (an "
                                  "omitted share is 0). The taxable share earns the after-tax "
                                  "return; the sheltered shares are untouched (the RRSP's pre-tax "
                                  "nature is not modelled — symmetric across the two sides). With "
                                  "a tax.fhsa block the fhsa share is DERIVED (balance + "
                                  "contributions) and must not be stated. A TFSA share above the "
                                  "cumulative room since 2009 draws a warning"),
        "taxable_return_treatment": (False, "'capital_gains' (DEFAULT: the drag on the taxable "
                                            "share is marginal_rate × the one-half inclusion rate "
                                            "[tax.capital_gains_inclusion_rate]) or 'interest' "
                                            "(marginal_rate × 1). Gains are taxed in nominal terms: "
                                            "the engine composes the return to nominal, taxes it and "
                                            "deflates back in real mode. Annual realisation is "
                                            "assumed (deferral not modelled — toward buying)"),
        "retirement_marginal_rate": (False, "fraction in [0, 1): the rate the renter pays when the "
                                            "FHSA share, rolled into an RRSP, is eventually "
                                            "withdrawn — the haircut on that share at the horizon "
                                            "end. DEFAULT = the current marginal rate, printed "
                                            "'(= current, default)'"),
        "fhsa": (False, "{balance, annual_contribution, years_until_purchase} for a first-time "
                        "buyer (an owned option with first_time_buyer: true, financed — never "
                        "all_cash; needs a rent: block): today's FHSA balance; the contribution "
                        "in each saving year before year 0 (one figure, or a list per year); "
                        "the number of saving years (DEFAULT 0 = the decision is now, no "
                        "refunds to add). Each year's deductible contribution is capped by the "
                        "room — $8,000 + carry-forward (≤ $8,000, none assumed on entry), "
                        "within the $40,000 lifetime limit (today's balance stands in for "
                        "contributions to date). Refunds = Σ contributions × marginal_rate and "
                        "accrue to BOTH sides (the deduction does not depend on buying): they "
                        "join the buyer's down payment and the renter's taxable share. The "
                        "renter's FHSA share (balance + contributions) rolls to an RRSP and is "
                        "haircut at retirement_marginal_rate at the horizon; the buyer's leaves "
                        "tax-free. No growth inside the saving years"),
        "hbp_withdrawal": (False, "$ withdrawn from an RRSP under the Home Buyers' Plan for a "
                                  "first-time buyer (first_time_buyer: true, financed; needs a "
                                  "rent: block): ≤ $60,000 [hbp.withdrawal_limit] and ≤ "
                                  "tax.renter_capital.rrsp. It JOINS the down payment (state "
                                  "cash_available WITHOUT it; like-for-like is cash_available + "
                                  "hbp_withdrawal = rent.invested_down_payment — the engine warns "
                                  "otherwise). Its cost is the repayment schedule alone: fixed "
                                  "nominal outlays of 1/15 a year from year 5 (2026–2028 "
                                  "withdrawals) [hbp.repayment_years, hbp.repayment_grace_years] "
                                  "against the RRSP they rebuild, credited at the horizon at the "
                                  "renter's return — hbp_repayment_pv, zero when that return "
                                  "equals the discount rate. Outside the affordability ratio and "
                                  "the year-1 cash line (a transfer into the household's own RRSP)"),
    },
    "market_scenario": {
        "path": (True, "ScenarioPrior JSON (see examples/showcase_demographic_prior.yaml)"),
        "geography": (True, "exact string; the shipped prior (tests/fixtures/scenario_prior_golden.json) carries "
                            "HORS_RMR, LAVAL_RA13, MTL_ISLAND_RA06, MTL_RMR, QC_RMR — use the finest one that "
                            "contains the user's area; a refusal lists what the file has"),
    },
}


def input_schema() -> dict:
    """The full input contract as a dict (one section per YAML block)."""
    sections: Dict[str, Any] = {}
    for section, keys in _SECTION_KEYS.items():
        notes = _NOTES.get(section, {})
        block: Dict[str, Any] = {}
        for key in sorted(keys):
            required, note, *rest = notes.get(key, (False, ""))
            entry: Dict[str, Any] = {
                "required": bool(required),
                "note": note or "see examples/README.md",
            }
            if rest and rest[0]:
                # conditional requirement, quoting the validator's own sentence
                entry["required_if"] = rest[0]
            block[key] = entry
        sections[section] = block
    sections["top_level"] = {
        key: {"required": req, "note": note}
        for key, (req, note) in sorted(_NOTES["top"].items())
    }
    return sections
