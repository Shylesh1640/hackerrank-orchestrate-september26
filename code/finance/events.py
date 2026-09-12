import pandas as pd
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from config import (
    CONFIG, DIRECTION_SIGN, STATUS_SETTLED, STATUS_PENDING, STATUS_SCHEDULED,
    STATUS_CANCELLED, STATUS_FAILED, STATUS_UNREALIZED,
    FLEXIBILITY_STOPPABLE, FLEXIBILITY_REDUCIBLE, FLEXIBILITY_FIXED
)
from finance.currency import CurrencyConverter

logger = logging.getLogger(__name__)


class EventDirection(Enum):
    INCOME = 1
    EXPENSE = -1


class EventStatus(Enum):
    SETTLED = "settled"
    PENDING = "pending"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNREALIZED = "unrealized"


class EventFlexibility(Enum):
    FIXED = "fixed"
    STOPPABLE = "stoppable"
    REDUCIBLE = "reducible"


@dataclass
class NormalizedEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: int
    amount: float
    currency: str
    home_amount: float
    event_date: date
    settlement_date: date
    status: str
    linked_event_id: str
    recurring: bool
    frequency: Optional[str]
    flexibility: str
    minimum_allowed_amount: Optional[float]
    source_row_index: int
    
    is_recurring_income: bool = False
    is_recurring_essential: bool = False
    is_recurring_flexible: bool = False
    recurrence_pattern: Optional[Dict] = None


def parse_amount(val: Any) -> Optional[float]:
    if pd.isna(val) or val == "" or val == "nan":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_date_safe(val: Any) -> Optional[date]:
    if pd.isna(val) or val == "" or val == "nan":
        return None
    try:
        if isinstance(val, str):
            return datetime.strptime(val, "%Y-%m-%d").date()
        elif isinstance(val, datetime):
            return val.date()
        elif isinstance(val, date):
            return val
    except (ValueError, TypeError):
        pass
    return None


def determine_direction(event_type: str, direction: str) -> int:
    dir_str = str(direction).lower().strip()
    type_str = str(event_type).lower().strip()
    
    if dir_str in DIRECTION_SIGN:
        return DIRECTION_SIGN[dir_str]
    
    income_keywords = ["income", "salary", "credit", "refund", "bonus", "commission", "dividend", "interest"]
    expense_keywords = ["expense", "payment", "debit", "purchase", "subscription", "debt", "investment", "transfer", "rent", "utility"]
    
    for kw in income_keywords:
        if kw in type_str or kw in dir_str:
            return 1
    for kw in expense_keywords:
        if kw in type_str or kw in dir_str:
            return -1
    
    return -1


def normalize_event(row: pd.Series, converter: CurrencyConverter, profile: pd.Series) -> NormalizedEvent:
    event_id = str(row["event_id"])
    user_id = str(row["user_id"])
    event_type = str(row["event_type"])
    description = str(row["description"]) if not pd.isna(row["description"]) else ""
    category = str(row["category"]) if not pd.isna(row["category"]) else ""
    direction = determine_direction(event_type, row["direction"])
    
    amount = parse_amount(row["amount"])
    currency = str(row["currency"]) if not pd.isna(row["currency"]) else profile["home_currency"]
    
    event_date = parse_date_safe(row["event_date"])
    settlement_date = parse_date_safe(row["settlement_date"])
    if settlement_date is None:
        settlement_date = event_date
    
    status = str(row["status"]).lower().strip() if not pd.isna(row["status"]) else "unknown"
    linked_event_id = str(row["linked_event_id"]) if not pd.isna(row["linked_event_id"]) else ""
    
    flexibility = str(row["flexibility"]).lower().strip() if not pd.isna(row["flexibility"]) else "fixed"
    min_allowed = parse_amount(row["minimum_allowed_amount"])
    
    recurring = False
    frequency = None
    
    home_currency = profile["home_currency"]
    home_amount = 0.0
    if amount is not None:
        try:
            home_amount = converter.convert(amount, currency, home_currency, settlement_date or event_date)
        except Exception as e:
            logger.warning(f"Currency conversion failed for {event_id}: {e}")
            home_amount = amount
    
    return NormalizedEvent(
        event_id=event_id,
        user_id=user_id,
        event_type=event_type,
        description=description,
        category=category,
        direction=direction,
        amount=amount if amount is not None else 0.0,
        currency=currency,
        home_amount=home_amount,
        event_date=event_date,
        settlement_date=settlement_date,
        status=status,
        linked_event_id=linked_event_id,
        recurring=recurring,
        frequency=frequency,
        flexibility=flexibility,
        minimum_allowed_amount=min_allowed,
        source_row_index=row.name if hasattr(row, 'name') else 0,
    )


def normalize_all_events(events_df: pd.DataFrame, converter: CurrencyConverter, profile: pd.Series) -> List[NormalizedEvent]:
    normalized = []
    for _, row in events_df.iterrows():
        try:
            event = normalize_event(row, converter, profile)
            normalized.append(event)
        except Exception as e:
            logger.error(f"Failed to normalize event {row.get('event_id', 'unknown')}: {e}")
    return normalized