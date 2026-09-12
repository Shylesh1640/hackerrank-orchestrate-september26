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
    
    for event in events:
        if not event.recurrence_pattern:
            continue
        
        pattern = event.recurrence_pattern
        freq = pattern["frequency"]
        interval = pattern["interval_days"]
        
        last_date = event.event_date
        while last_date < start_date:
            last_date += timedelta(days=interval)
        
        current_date = last_date
        occurrence = 0
        while current_date <= end_date:
            if current_date >= start_date:
                new_event = NormalizedEvent(
                    event_id=f"{event.event_id}_recur_{occurrence}",
                    user_id=event.user_id,
                    event_type=event.event_type,
                    description=f"{event.description} (recurring)",
                    category=event.category,
                    direction=event.direction,
                    amount=event.amount,
                    currency=event.currency,
                    home_amount=event.home_amount,
                    event_date=current_date,
                    settlement_date=current_date,
                    status="scheduled",
                    linked_event_id=event.event_id,
                    recurring=True,
                    frequency=freq,
                    flexibility=event.flexibility,
                    minimum_allowed_amount=event.minimum_allowed_amount,
                    source_row_index=-1,
                    is_recurring_income=event.is_recurring_income,
                    is_recurring_essential=event.is_recurring_essential,
                    is_recurring_flexible=event.is_recurring_flexible,
                    recurrence_pattern=event.recurrence_pattern,
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