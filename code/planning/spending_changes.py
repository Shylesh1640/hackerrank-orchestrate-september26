from datetime import date
from typing import List, Dict, Tuple, Optional, Set
from itertools import combinations
import logging

from config import CONFIG
from finance.state import UserFinancialState
from finance.forecast import run_forecast
from finance.events import NormalizedEvent

logger = logging.getLogger(__name__)


def get_flexible_events(state: UserFinancialState) -> List[NormalizedEvent]:
    flexible = []
    for event in state.flexible_expenses:
        cat_match = False
        for cat in state.reducible_categories:
            if cat.lower() in event.category.lower():
                cat_match = True
                break
        for cat in state.stoppable_categories:
            if cat.lower() in event.category.lower():
                cat_match = True
                break
        if cat_match:
            flexible.append(event)
    return flexible


def generate_spending_change_candidates(
    state: UserFinancialState
) -> List[Dict]:
    flexible_events = get_flexible_events(state)
    candidates = []
    
    for event in flexible_events:
        is_stoppable = any(cat.lower() in event.category.lower() for cat in state.stoppable_categories)
        is_reducible = any(cat.lower() in event.category.lower() for cat in state.reducible_categories)
        
        if is_stoppable:
            candidates.append({
                "type": "stop",
                "event_id": event.event_id,
                "original_amount": event.home_amount,
                "new_amount": 0.0,
                "category": event.category,
            })
        
        if is_reducible and event.minimum_allowed_amount is not None:
            if event.minimum_allowed_amount < event.home_amount:
                candidates.append({
                    "type": "reduce",
                    "event_id": event.event_id,
                    "original_amount": event.home_amount,
                    "new_amount": event.minimum_allowed_amount,
                    "category": event.category,
                })
    
    return candidates


def apply_spending_changes(
    state: UserFinancialState,
    changes: List[Dict]
) -> Tuple[Dict[str, float], List[str]]:
    spending_changes = {}
    stopped_events = []
    
    for change in changes:
        if change["type"] == "stop":
            stopped_events.append(change["event_id"])
        elif change["type"] == "reduce":
            spending_changes[change["event_id"]] = change["new_amount"]
    
    return spending_changes, stopped_events


def find_best_spending_changes(
    state: UserFinancialState,
    request_payments: List[Tuple[date, float]],
    max_changes: int = 3
) -> Optional[List[Dict]]:
    candidates = generate_spending_change_candidates(state)
    
    if not candidates:
        return None
    
    base_forecast = run_forecast(state, request_payments=request_payments)
    if base_forecast.is_safe:
        return []
    
    best_changes = None
    best_min_balance = base_forecast.min_balance
    
    for r in range(1, min(max_changes, len(candidates)) + 1):
        for combo in combinations(candidates, r):
            event_ids = [c["event_id"] for c in combo]
            if len(set(event_ids)) != len(event_ids):
                continue
            
            spending_changes, stopped_events = apply_spending_changes(state, list(combo))
            forecast = run_forecast(
                state, 
                request_payments=request_payments,
                spending_changes=spending_changes,
                stopped_events=stopped_events
            )
            
            if forecast.is_safe:
                return list(combo)
            
            if forecast.min_balance > best_min_balance:
                best_min_balance = forecast.min_balance
                best_changes = list(combo)
    
    return best_changes