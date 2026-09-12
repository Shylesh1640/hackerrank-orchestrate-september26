from datetime import date
from typing import List, Optional, Tuple
import logging

from finance.state import UserFinancialState
from finance.forecast import is_safe_immediate_payment, find_earliest_full_payment_date

logger = logging.getLogger(__name__)


def calculate_amount_safe_to_pay(
    state: UserFinancialState,
    requested_amount: float,
    request_date: date
) -> float:
    if requested_amount <= 0:
        return 0.0
    
    if is_safe_immediate_payment(state, requested_amount, request_date):
        return requested_amount
    
    low = 0.0
    high = requested_amount
    best = 0.0
    
    for _ in range(20):
        mid = (low + high) / 2
        if mid <= 0:
            break
        if is_safe_immediate_payment(state, mid, request_date):
            best = mid
            low = mid
        else:
            high = mid
        
        if high - low < 1.0:
            break
    
    return round(best, 2)


def calculate_earliest_full_payment(
    state: UserFinancialState,
    requested_amount: float,
    request_date: date,
    desired_completion_date: date
) -> Optional[date]:
    return find_earliest_full_payment_date(state, requested_amount, request_date, desired_completion_date)