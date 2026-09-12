from datetime import date
from typing import List, Tuple, Dict, Optional
import logging

from config import CONFIG
from finance.state import UserFinancialState
from finance.forecast import run_forecast
from planning.ranking import PaymentPlan

logger = logging.getLogger(__name__)


def verify_plan(
    plan: PaymentPlan,
    state: UserFinancialState,
    request,
    spending_changes: Optional[Dict[str, float]] = None,
    stopped_events: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    errors = []
    
    if not plan.payments:
        errors.append("No payments in plan")
        return False, errors
    
    payments_sorted = sorted(plan.payments, key=lambda x: x[0])
    if payments_sorted != plan.payments:
        errors.append("Payments not in chronological order")
    
    total_paid = sum(p[1] for p in plan.payments)
    requested_amount = float(request["requested_amount"])
    
    if abs(total_paid - requested_amount) > 0.01:
        if plan.method != "partial_payment" or total_paid > requested_amount:
            errors.append(f"Payment total {total_paid} != requested {requested_amount}")
    
    if plan.method == "partial_payment":
        if len(plan.payments) != 2:
            errors.append("Partial payment must have exactly 2 payments")
        else:
            first_date, first_amt = plan.payments[0]
            second_date, second_amt = plan.payments[1]
            if first_date != state.request_date:
                errors.append("First partial payment must be on request_date")
            if abs(first_amt + second_amt - requested_amount) > 0.01:
                errors.append("Partial payments must sum to requested amount")
    
    if plan.method == "installments" and plan.payment_option_id:
        pass
    
    completion_date = max(p[0] for p in plan.payments)
    desired_completion = request.get("desired_completion_date")
    if isinstance(desired_completion, str):
        from datetime import datetime
        desired_completion = datetime.strptime(desired_completion, "%Y-%m-%d").date()
    
    if completion_date > desired_completion:
        errors.append(f"Completion date {completion_date} exceeds desired {desired_completion}")
    
    if plan.method in ["full_payment", "partial_payment", "installments"]:
        if plan.method not in state.payment_methods:
            errors.append(f"Payment method {plan.method} not in user preferences")
    
    if state.max_installment_months and plan.method == "installments":
        max_payments = state.max_installment_months
        if len(plan.payments) > max_payments:
            errors.append(f"Installments exceed max {max_payments} months")
    
    if spending_changes:
        for event_id, new_amount in spending_changes.items():
            event = next((e for e in state.flexible_expenses if e.event_id == event_id), None)
            if not event:
                errors.append(f"Spending change references unknown event {event_id}")
            elif event.minimum_allowed_amount and new_amount < event.minimum_allowed_amount:
                errors.append(f"Reduction below minimum for {event_id}")
    
    if stopped_events:
        for event_id in stopped_events:
            event = next((e for e in state.flexible_expenses if e.event_id == event_id), None)
            if not event:
                errors.append(f"Stop references unknown event {event_id}")
            elif not any(cat.lower() in event.category.lower() for cat in state.stoppable_categories):
                errors.append(f"Event {event_id} not in stoppable categories")
    
    changed_and_stopped = set(spending_changes or {}).intersection(set(stopped_events or []))
    if changed_and_stopped:
        errors.append(f"Events both reduced and stopped: {changed_and_stopped}")
    
    if len(spending_changes or []) + len(stopped_events or []) > CONFIG.max_spending_changes:
        errors.append("Too many spending changes")
    
    forecast = run_forecast(state, request_payments=plan.payments, 
                          spending_changes=spending_changes, stopped_events=stopped_events)
    
    if not forecast.is_safe:
        errors.append(f"Balance falls below minimum: {forecast.min_balance} < {state.minimum_balance}")
    
    return len(errors) == 0, errors