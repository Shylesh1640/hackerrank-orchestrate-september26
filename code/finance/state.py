from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd
import logging

from config import CONFIG
from finance.events import NormalizedEvent
from finance.resolver import EventResolver
from finance.recurring import generate_recurring_events, get_recurring_summary
from finance.currency import CurrencyConverter
from data.loader import get_user_profile, get_user_events, parse_date, get_request

logger = logging.getLogger(__name__)


@dataclass
class UserFinancialState:
    user_id: str
    home_currency: str
    current_balance: float
    minimum_balance: float
    request_date: date
    
    confirmed_income: List[NormalizedEvent] = field(default_factory=list)
    recurring_income: List[NormalizedEvent] = field(default_factory=list)
    essential_expenses: List[NormalizedEvent] = field(default_factory=list)
    flexible_expenses: List[NormalizedEvent] = field(default_factory=list)
    confirmed_payments: List[NormalizedEvent] = field(default_factory=list)
    pending_debits: List[NormalizedEvent] = field(default_factory=list)
    
    protected_categories: List[str] = field(default_factory=list)
    reducible_categories: List[str] = field(default_factory=list)
    stoppable_categories: List[str] = field(default_factory=list)
    payment_methods: List[str] = field(default_factory=list)
    max_installment_months: Optional[int] = None
    financial_priorities: List[str] = field(default_factory=list)


def parse_categories(cat_str: str) -> List[str]:
    if pd.isna(cat_str) or cat_str == "":
        return []
    return [c.strip() for c in str(cat_str).split("|") if c.strip()]


def build_user_state(
    data_bundle,
    request_id: str,
    request_date: date,
    converter: CurrencyConverter
) -> UserFinancialState:
    request = get_request(data_bundle, request_id)
    user_id = str(request["user_id"])
    profile = get_user_profile(data_bundle, user_id)
    
    home_currency = str(profile["home_currency"])
    current_balance = float(profile["current_available_balance"])
    minimum_balance = float(profile["minimum_balance_to_keep"])
    
    protected = parse_categories(profile["expense_categories_to_protect"])
    reducible = parse_categories(profile["expense_categories_user_is_willing_to_reduce"])
    stoppable = parse_categories(profile["expense_categories_user_is_willing_to_stop"])
    payment_methods = parse_categories(profile["payment_methods_user_will_consider"])
    
    max_installments = profile["max_installment_months"]
    max_installment_months = int(max_installments) if pd.notna(max_installments) and max_installments != "" else None
    
    priorities = parse_categories(profile["financial_priorities"])
    
    raw_events = get_user_events(data_bundle, user_id)
    normalized = []
    for _, row in raw_events.iterrows():
        event = NormalizedEvent(
            event_id=str(row["event_id"]),
            user_id=user_id,
            event_type=str(row["event_type"]),
            description=str(row["description"]) if not pd.isna(row["description"]) else "",
            category=str(row["category"]) if not pd.isna(row["category"]) else "",
            direction=1 if str(row["direction"]).lower() in ["credit", "income", "refund"] else -1,
            amount=float(row["amount"]) if pd.notna(row["amount"]) and row["amount"] != "" else 0.0,
            currency=str(row["currency"]) if pd.notna(row["currency"]) else home_currency,
            home_amount=0.0,
            event_date=parse_date(row["event_date"]),
            settlement_date=parse_date(row["settlement_date"]),
            status=str(row["status"]).lower() if pd.notna(row["status"]) else "unknown",
            linked_event_id=str(row["linked_event_id"]) if pd.notna(row["linked_event_id"]) else "",
            recurring=False,
            frequency=None,
            flexibility=str(row["flexibility"]).lower() if pd.notna(row["flexibility"]) else "fixed",
            minimum_allowed_amount=float(row["minimum_allowed_amount"]) if pd.notna(row["minimum_allowed_amount"]) and row["minimum_allowed_amount"] != "" else None,
            source_row_index=row.name,
        )
        if event.amount > 0:
            try:
                event.home_amount = converter.convert(event.amount, event.currency, home_currency, event.settlement_date or event.event_date)
            except:
                event.home_amount = event.amount
        normalized.append(event)
    
    resolver = EventResolver(normalized, request_date)
    resolved = resolver.resolve()
    
    forecast_end = request_date + timedelta(days=CONFIG.forecast_horizon_days)
    future_recurring = generate_recurring_events(resolved, request_date, forecast_end)
    all_events = resolved + future_recurring
    
    state = UserFinancialState(
        user_id=user_id,
        home_currency=home_currency,
        current_balance=current_balance,
        minimum_balance=minimum_balance,
        request_date=request_date,
        protected_categories=protected,
        reducible_categories=reducible,
        stoppable_categories=stoppable,
        payment_methods=payment_methods,
        max_installment_months=max_installment_months,
        financial_priorities=priorities,
    )
    
    for event in all_events:
        if event.settlement_date and event.settlement_date < request_date:
            if event.status == "settled":
                state.current_balance += event.home_amount
        elif event.settlement_date and event.settlement_date >= request_date:
            if event.direction > 0:
                if event.status == "settled" or event.is_recurring_income:
                    state.confirmed_income.append(event)
                elif event.status in ["pending", "scheduled"]:
                    pass
            else:
                if event.is_recurring_essential:
                    state.essential_expenses.append(event)
                elif event.is_recurring_flexible:
                    state.flexible_expenses.append(event)
                elif event.status in ["pending", "scheduled", "settled"]:
                    state.confirmed_payments.append(event)
                if event.status == "pending":
                    state.pending_debits.append(event)
    
    return state