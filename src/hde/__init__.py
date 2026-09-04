"""
Housing Decision Engine

Present value comparison engine for rent / condo / house decisions on a
net-wealth basis, with an affordability layer, Monte Carlo uncertainty, a
demographic scenario prior, and a provenance registry for every default.

Library use: build a ComparisonSpec (load_config / load_config_dict), run
compute_deterministic and/or run_monte_carlo, and read compute_verdict for
the decision. The CLI (`hde`) wraps exactly these.
"""

from hde.anchors import ANCHORS, Anchor
from hde.config import (
    ComparisonSpec,
    ConfigValidationError,
    all_warnings,
    coherence_warnings,
    load_config,
    load_config_dict,
    single_path_run,
)
from hde.deterministic import compute_deterministic
from hde.market_scenario import LoadedScenarioPrior, ScenarioPriorError, load_scenario_prior
from hde.models import (
    AffordabilityReport,
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    CondoParams,
    EconomicParams,
    EventConfig,
    HouseParams,
    IncomeParams,
    MonteCarloSummary,
    OptionResult,
    PayDropEvent,
    PriceShockParams,
    RecurringOtherCost,
    RentParams,
    SimulationParams,
    Verdict,
    compute_verdict,
)
from hde.monte_carlo import run_monte_carlo
from hde.pv import pv_to_monthly_savings
from hde.serialization import (
    anchors_to_dict,
    assumptions_to_dict,
    det_to_dict,
    engine_version,
    format_assumptions,
    mc_to_dict,
    read_back_lines,
    verdict_to_dict,
)

__version__ = engine_version()

__all__ = [
    # Provenance
    "ANCHORS", "Anchor", "anchors_to_dict",
    # Spec + config
    "ComparisonSpec", "ConfigValidationError", "load_config", "load_config_dict",
    "all_warnings", "coherence_warnings", "single_path_run",
    # Parameter classes
    "CondoParams", "HouseParams", "RentParams", "IncomeParams", "SimulationParams",
    "EconomicParams", "EventConfig", "RecurringOtherCost", "PayDropEvent", "PriceShockParams",
    # Engines + results
    "compute_deterministic", "run_monte_carlo",
    "ComparisonDeterministicResult", "ComparisonMonteCarloResult", "OptionResult",
    "AffordabilityReport", "MonteCarloSummary",
    # Verdict
    "Verdict", "compute_verdict",
    # Demographic prior
    "LoadedScenarioPrior", "ScenarioPriorError", "load_scenario_prior",
    # Serialization
    "assumptions_to_dict", "det_to_dict", "mc_to_dict", "verdict_to_dict",
    "format_assumptions", "read_back_lines", "engine_version", "pv_to_monthly_savings",
]
