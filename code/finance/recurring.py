from datetime import date, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import logging

from finance.events import NormalizedEvent

logger = logging.getLogger(__name__)


def generate_recurring_events(
    events: List[NormalizedEvent],
    start_date: date,
    end_date: date
) -> List[NormalizedEvent]:
    recurring_events = []
    
    by_category = defaultdict(list)
    for event in events:
        if event.recurrence_pattern:
            by_category[(event.user_id, event.category, event.direction)].append(event)
    
    for (user_id, category, direction), group in by_category.items():
        group.sort(key=lambda e: e.event_date)
        representative = group[-1]
        
        pattern = representative.recurrence_pattern
        freq = pattern["frequency"]
        interval = pattern["interval_days"]
        
        last_date = representative.event_date
        while last_date < start_date:
            last_date += timedelta(days=interval)
        
        current_date = last_date
        occurrence = 0
        while current_date <= end_date:
            if current_date >= start_date:
                new_event = NormalizedEvent(
                    event_id=f"{representative.event_id}_recur_{occurrence}",
                    user_id=user_id,
                    event_type=representative.event_type,
                    description=f"{representative.description} (recurring)",
                    category=category,
                    direction=direction,
                    amount=representative.amount,
                    currency=representative.currency,
                    home_amount=representative.home_amount,
                    event_date=current_date,
                    settlement_date=current_date,
                    status="scheduled",
                    linked_event_id=representative.event_id,
                    recurring=True,
                    frequency=freq,
                    flexibility=representative.flexibility,
                    minimum_allowed_amount=representative.minimum_allowed_amount,
                    source_row_index=-1,
                    is_recurring_income=representative.is_recurring_income,
                    is_recurring_essential=representative.is_recurring_essential,
                    is_recurring_flexible=representative.is_recurring_flexible,
                    recurrence_pattern=representative.recurrence_pattern,
                )
                recurring_events.append(new_event)
            
            current_date += timedelta(days=interval)
            occurrence += 1
            if occurrence > 100:
                break
    
    return recurring_events


def get_recurring_summary(events: List[NormalizedEvent]) -> Dict:
    summary = {
        "income": [],
        "essential_expenses": [],
        "flexible_expenses": [],
    }
    
    for event in events:
        if event.is_recurring_income:
            summary["income"].append(event)
        elif event.is_recurring_essential:
            summary["essential_expenses"].append(event)
        elif event.is_recurring_flexible:
            summary["flexible_expenses"].append(event)
    
    return summary