from datetime import date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

from config import CONFIG

logger = logging.getLogger(__name__)


@dataclass
class PaymentPlan:
    method: str
    payments: List[Tuple[date, float]]
    total_cost: float
    spending_changes: List[Dict]
    completion_date: date
    payment_option_id: Optional[str] = None
    request_id: str = ""
    
    def __lt__(self, other):
        return rank_key(self) < rank_key(other)


def rank_key(plan: PaymentPlan) -> Tuple:
    completes_on_time = 1 if plan.completion_date <= plan.deadline else 0
    has_spending_changes = 1 if plan.spending_changes else 0
    total_cost = plan.total_cost
    start_date = min(p[0] for p in plan.payments) if plan.payments else date.max
    num_payments = len(plan.payments)
    option_id = plan.payment_option_id or "zzz"
    
    return (
        -completes_on_time,
        has_spending_changes,
        total_cost,
        start_date,
        num_payments,
        option_id,
    )


def rank_plans(plans: List[PaymentPlan], deadline: date) -> List[PaymentPlan]:
    for plan in plans:
        plan.deadline = deadline
    return sorted(plans)