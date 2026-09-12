from datetime import date
from typing import List, Tuple, Optional
import logging

from config import CONFIG
from finance.state import UserFinancialState
from finance.forecast import run_forecast, is_safe_immediate_payment
from planning.full_payment import calculate_amount_safe_to_pay, calculate_earliest_full_payment

logger = logging.getLogger(__name__)


def check_partial_payment_eligible(
    state: UserFinancialState,
    request,
    amount_safe_to_pay: float,
    earliest_full_date: Optional[date]
) -> bool:
    if not request.get("allows_partial_payment", False):
        return False
    
    if "partial_payment" not in state.payment_methods:
        return False
    
    if amount_safe_to_pay <= 0:
        return False
    
    if amount_safe_to_pay >= float(request["requested_amount"]):
        return False
    
    if earliest_full_date is None:
        return False
    
    desired_completion = request.get("desired_completion_date")
    if isinstance(desired_completion, str):
        from datetime import datetime
        desired_completion = datetime.strptime(desired_completion, "%Y-%m-%d").date()
    
    if earliest_full_date > desired_completion:
        return False
    
    return True


def build_partial_payment_plan(
    state: UserFinancialState,
    request,
    amount_safe_to_pay: float,
    earliest_full_date: date
) -> Optional[List[Tuple[date, float]]]:
    requested_amount = float(request["requested_amount"])
    remaining = requested_amount - amount_safe_to_pay
    
    if remaining <= 0:
        return None
    
    request_date = state.request_date
    
    forecast = run_forecast(state, request_payments=[
        (request_date, amount_safe_to_pay),
        (earliest_full_date, remaining)
    ])
    
    if forecast.is_safe:
        return [(request_date, amount_safe_to_pay), (earliest_full_date, remaining)]
    
    return None