from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging
from statistics import mean

from finance.events import NormalizedEvent
from finance.state import UserFinancialState

logger = logging.getLogger(__name__)


@dataclass
class DailyForecast:
    date: date
    balance: float
    income: float = 0.0
    essential_expenses: float = 0.0
    flexible_expenses: float = 0.0
    confirmed_payments: float = 0.0
    request_payments: float = 0.0
    net_flow: float = 0.0


@dataclass
class ForecastResult:
    daily_forecasts: List[DailyForecast]
    min_balance: float
    min_balance_date: date
    final_balance: float
    is_safe: bool


def compute_variable_essential_budget(resolved_events: List[NormalizedEvent], request_date: date) -> Dict[str, float]:
    variable_categories = {"groceries", "transport"}
    budgets = {}
    
    for cat in variable_categories:
        cat_events = [e for e in resolved_events if e.category.lower() == cat and e.direction < 0 and e.status == "settled" and e.settlement_date and e.settlement_date < request_date]
        if cat_events:
            cat_events.sort(key=lambda e: e.settlement_date)
            recent = cat_events[-12:]
            amounts = [e.home_amount for e in recent]
            if amounts:
                monthly_budget = mean(amounts) * (30 / 7)
                budgets[cat] = monthly_budget
    
    return budgets


def run_forecast(
    state: UserFinancialState,
    request_payments: Optional[List[Tuple[date, float]]] = None,
    spending_changes: Optional[Dict[str, float]] = None,
    stopped_events: Optional[List[str]] = None
) -> ForecastResult:
    request_date = state.request_date
    horizon_end = request_date + timedelta(days=90)
    
    variable_budgets = compute_variable_essential_budget(
        [e for e in (state.confirmed_income + state.recurring_income + state.essential_expenses + state.flexible_expenses + state.confirmed_payments + state.pending_debits) if not (hasattr(e, 'event_id') and 'recur_' in e.event_id)],
        request_date
    )
    
    all_events = []
    all_events.extend(state.confirmed_income)
    all_events.extend(state.recurring_income)
    all_events.extend([e for e in state.essential_expenses if e.category.lower() not in {"groceries", "transport"}])
    all_events.extend(state.flexible_expenses)
    all_events.extend(state.confirmed_payments)
    all_events.extend(state.pending_debits)
    
    if request_payments:
        for pay_date, amount in request_payments:
            all_events.append(NormalizedEvent(
                event_id=f"request_payment_{pay_date}",
                user_id=state.user_id,
                event_type="request_payment",
                description="Request payment",
                category="request",
                direction=-1,
                amount=amount,
                currency=state.home_currency,
                home_amount=amount,
                event_date=pay_date,
                settlement_date=pay_date,
                status="scheduled",
                linked_event_id="",
                recurring=False,
                frequency=None,
                flexibility="fixed",
                minimum_allowed_amount=None,
                source_row_index=-1,
            ))
    
    if spending_changes:
        for event in state.flexible_expenses:
            if event.event_id in spending_changes:
                event.home_amount = spending_changes[event.event_id]
    
    if stopped_events:
        state.flexible_expenses = [e for e in state.flexible_expenses if e.event_id not in stopped_events]
        all_events = [e for e in all_events if e.event_id not in stopped_events]
    
    daily_flows = defaultdict(lambda: {
        "income": 0.0, "essential": 0.0, "flexible": 0.0, 
        "confirmed": 0.0, "request": 0.0
    })
    
    for event in all_events:
        if event.settlement_date and request_date <= event.settlement_date <= horizon_end:
            d = event.settlement_date
            if event.category == "request":
                daily_flows[d]["request"] += event.home_amount
            elif event.direction > 0:
                daily_flows[d]["income"] += event.home_amount
            else:
                if event.is_recurring_essential or (not event.is_recurring_flexible and event.category in ["rent", "housing", "utilities", "education", "debt_repayment"]):
                    daily_flows[d]["essential"] += event.home_amount
                elif event.is_recurring_flexible:
                    daily_flows[d]["flexible"] += event.home_amount
                else:
                    daily_flows[d]["confirmed"] += event.home_amount
    
    for cat, monthly_budget in variable_budgets.items():
        current = request_date.replace(day=1)
        if current < request_date:
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        while current <= horizon_end:
            daily_flows[current]["essential"] += monthly_budget
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    
    daily_forecasts = []
    balance = state.current_balance
    min_balance = balance
    min_balance_date = request_date
    
    current_date = request_date
    while current_date <= horizon_end:
        flows = daily_flows[current_date]
        net = flows["income"] - flows["essential"] - flows["flexible"] - flows["confirmed"] - flows["request"]
        balance += net
        
        forecast = DailyForecast(
            date=current_date,
            balance=balance,
            income=flows["income"],
            essential_expenses=flows["essential"],
            flexible_expenses=flows["flexible"],
            confirmed_payments=flows["confirmed"],
            request_payments=flows["request"],
            net_flow=net,
        )
        daily_forecasts.append(forecast)
        
        if balance < min_balance:
            min_balance = balance
            min_balance_date = current_date
        
        current_date += timedelta(days=1)
    
    is_safe = min_balance >= state.minimum_balance
    
    return ForecastResult(
        daily_forecasts=daily_forecasts,
        min_balance=min_balance,
        min_balance_date=min_balance_date,
        final_balance=balance,
        is_safe=is_safe,
    )


def is_safe_immediate_payment(
    state: UserFinancialState,
    amount: float,
    request_date: date
) -> bool:
    forecast = run_forecast(state, request_payments=[(request_date, amount)])
    return forecast.is_safe


def find_earliest_full_payment_date(
    state: UserFinancialState,
    requested_amount: float,
    request_date: date,
    desired_completion_date: date
) -> Optional[date]:
    horizon_end = request_date + timedelta(days=90)
    search_end = min(desired_completion_date, horizon_end)
    
    current = request_date
    while current <= search_end:
        if is_safe_immediate_payment(state, requested_amount, current):
            return current
        current += timedelta(days=1)
    
    return None