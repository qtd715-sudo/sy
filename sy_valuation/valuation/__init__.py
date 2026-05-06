"""Corporate valuation engine.

Combines multiple valuation methods to estimate fair stock price:
- DCF  (Discounted Cash Flow)
- RIM  (Residual Income Model)
- Multiples (PER, PBR, PSR, EV/EBITDA)
- Graham Number
- Lynch PEG
"""

from .engine import value_company, ValuationResult
from .dcf import dcf_per_share
from .rim import rim_per_share
from .multiples import per_per_share, pbr_per_share, psr_per_share, ev_ebitda_per_share
from .graham import graham_number
from .lynch import lynch_fair_price
from .sy_method import evaluate_sy, SyInputs, SyValuationResult
from .sy_builder import build_inputs_from_raw

__all__ = [
    "value_company",
    "ValuationResult",
    "dcf_per_share",
    "rim_per_share",
    "per_per_share",
    "pbr_per_share",
    "psr_per_share",
    "ev_ebitda_per_share",
    "graham_number",
    "lynch_fair_price",
    "evaluate_sy",
    "SyInputs",
    "SyValuationResult",
    "build_inputs_from_raw",
]
