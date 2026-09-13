from datetime import date, timedelta
from typing import List, Dict, Optional, Set
from collections import defaultdict
import logging

from finance.events import NormalizedEvent, EventStatus

logger = logging.getLogger(__name__)


class EventResolver:
    def __init__(self, events: List[NormalizedEvent], request_date: date):
        self.events = events
        self.request_date = request_date
        self.event_map: Dict[str, NormalizedEvent] = {e.event_id: e for e in events}
        self.resolved_events: List[NormalizedEvent] = []
        self.excluded_ids: Set[str] = set()
    
    def resolve(self) -> List[NormalizedEvent]:
        self._handle_lifecycle_links()
        self._handle_cancellations_and_amendments()
        self._handle_duplicates()
        self._filter_invalid_events()
        self._determine_recurrence()
        return self.resolved_events
    
    def _handle_lifecycle_links(self):
        linked_groups = defaultdict(list)
        for event in self.events:
            if event.linked_event_id:
                linked_groups[event.linked_event_id].append(event)
        
        for parent_id, children in linked_groups.items():
            parent = self.event_map.get(parent_id)
            if not parent:
                continue
            
            for child in children:
                if child.status in [EventStatus.CANCELLED.value, EventStatus.FAILED.value]:
                    self.excluded_ids.add(child.event_id)
                elif child.status == EventStatus.SETTLED.value and parent.status != EventStatus.SETTLED.value:
                    parent.status = EventStatus.SETTLED.value
                    parent.settlement_date = child.settlement_date
                    parent.home_amount = child.home_amount
    
    def _handle_cancellations_and_amendments(self):
        by_key = defaultdict(list)
        for event in self.events:
            if event.event_id in self.excluded_ids:
                continue
            key = (event.user_id, event.category, event.description, event.event_type)
            by_key[key].append(event)
        
        for key, group in by_key.items():
            if len(group) <= 1:
                continue
            
            group.sort(key=lambda e: (e.event_date, e.source_row_index))
            
            latest = group[-1]
            for event in group[:-1]:
                if latest.status in [EventStatus.CANCELLED.value, EventStatus.FAILED.value]:
                    self.excluded_ids.add(event.event_id)
                elif latest.status == EventStatus.SETTLED.value:
                    if event.status != EventStatus.SETTLED.value:
                        self.excluded_ids.add(event.event_id)
    
    def _handle_duplicates(self):
        seen = {}
        for event in self.events:
            if event.event_id in self.excluded_ids:
                continue
            dup_key = (event.user_id, event.category, event.amount, event.currency, 
                       event.event_date, event.direction)
            if dup_key in seen:
                existing = seen[dup_key]
                if event.source_row_index > existing.source_row_index:
                    self.excluded_ids.add(existing.event_id)
                    seen[dup_key] = event
                else:
                    self.excluded_ids.add(event.event_id)
            else:
                seen[dup_key] = event
    
    def _filter_invalid_events(self):
        self.resolved_events = []
        for event in self.events:
            if event.event_id in self.excluded_ids:
                continue
            
            if event.status in [EventStatus.FAILED.value, EventStatus.CANCELLED.value]:
                continue
            
            if event.status == EventStatus.UNREALIZED.value and event.direction > 0:
                continue
            
            if event.settlement_date and event.settlement_date > self.request_date + timedelta(days=365):
                if event.status != EventStatus.SETTLED.value:
                    continue
            
            self.resolved_events.append(event)
    
    def _determine_recurrence(self):
        by_category = defaultdict(list)
        for event in self.resolved_events:
            by_category[(event.user_id, event.category, event.direction)].append(event)
        
        recurring_categories = {"rent", "housing", "utilities", "education", "debt_repayment", "salary", "subscription"}
        variable_essential_categories = {"groceries", "transport"}
        
        for key, group in by_category.items():
            user_id, category, direction = key
            min_occurrences = 2 if direction > 0 else 3
            if len(group) >= min_occurrences:
                group.sort(key=lambda e: e.event_date)
                
                is_recurring_category = any(rc in category.lower() for rc in recurring_categories)
                is_variable_essential = any(vc in category.lower() for vc in variable_essential_categories)
                
                if is_variable_essential:
                    continue
                
                intervals = []
                amounts = [e.amount for e in group]
                amount_cv = 0.0
                if amounts and max(amounts) > 0:
                    mean_amt = sum(amounts) / len(amounts)
                    if mean_amt > 0:
                        variance = sum((a - mean_amt) ** 2 for a in amounts) / len(amounts)
                        amount_cv = (variance ** 0.5) / mean_amt
                
                for i in range(1, len(group)):
                    days = (group[i].event_date - group[i-1].event_date).days
                    if 25 <= days <= 35:
                        intervals.append("monthly")
                    elif 6 <= days <= 10:
                        intervals.append("weekly")
                    elif 85 <= days <= 95:
                        intervals.append("quarterly")
                
                if intervals:
                    most_common = max(set(intervals), key=intervals.count)
                    if intervals.count(most_common) >= 2:
                        if amount_cv > 0.5 and not is_recurring_category:
                            continue
                        
                        for event in group:
                            event.recurrence_pattern = {
                                "frequency": most_common,
                                "interval_days": 30 if most_common == "monthly" else (7 if most_common == "weekly" else 90)
                            }
                            if event.direction > 0:
                                event.is_recurring_income = True
                            else:
                                protected_categories = ["rent", "housing", "utilities", "education", "debt_repayment"]
                                if any(pc in event.category.lower() for pc in protected_categories):
                                    event.is_recurring_essential = True
                                elif event.flexibility in ["stoppable", "reducible"]:
                                    event.is_recurring_flexible = True
                                else:
                                    event.is_recurring_essential = True