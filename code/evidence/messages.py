import pandas as pd
import json
import re
from datetime import date, datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from functools import lru_cache
import logging

from config import CONFIG
from data.loader import parse_date, parse_datetime

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    fact_type: str
    event_id: Optional[str]
    amount: Optional[float]
    currency: Optional[str]
    effective_date: Optional[date]
    status: str
    source_message_id: str
    confidence: float


_message_cache: Dict[str, List[ExtractedFact]] = {}


def parse_salary_message(message_text: str, sent_at: date) -> List[ExtractedFact]:
    facts = []
    text = message_text.lower()
    
    amount_patterns = [
        r"(?:salary|pay|gaji|penggajian).*?(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur|rs\.?|r\$?)",
        r"(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur|rs\.?|r\$?).*?(?:salary|pay|gaji|monthly)",
        r"monthly.*?(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur)",
    ]
    
    date_patterns = [
        r"(?:effective|starting|from|berlaku|mulai)\s*(\d{4}-\d{2}-\d{2})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    
    amount = None
    currency = None
    effective_date = None
    
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amt_str = match.group(1).replace(",", "")
            try:
                amount = float(amt_str)
            except:
                pass
            break
    
    for curr in ["inr", "zar", "idr", "usd", "eur", "rs", "r$"]:
        if curr in text:
            currency = curr.upper().replace("RS", "INR").replace("R$", "ZAR")
            break
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                effective_date = parse_date(match.group(1))
                if effective_date and effective_date >= sent_at:
                    break
            except:
                pass
    
    if amount is not None:
        facts.append(ExtractedFact(
            fact_type="salary_change",
            event_id=None,
            amount=amount,
            currency=currency,
            effective_date=effective_date or sent_at,
            status="confirmed" if "confirmed" in text or "dikonfirmasi" in text else "pending",
            source_message_id="",
            confidence=0.8,
        ))
    
    return facts


def parse_bonus_message(message_text: str, sent_at: date) -> List[ExtractedFact]:
    facts = []
    text = message_text.lower()
    
    if any(w in text for w in ["bonus", "commission", "komisi", "performance"]):
        if any(w in text for w in ["pending", "menunggu", "not approved", "belum disetujui", "unconfirmed"]):
            return facts
        
        amount_match = re.search(r"(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur)", text, re.IGNORECASE)
        if amount_match:
            amt = float(amount_match.group(1).replace(",", ""))
            curr_match = re.search(r"(inr|zar|idr|usd|eur)", text, re.IGNORECASE)
            curr = curr_match.group(1).upper() if curr_match else None
            
            facts.append(ExtractedFact(
                fact_type="bonus_confirmed",
                event_id=None,
                amount=amt,
                currency=curr,
                effective_date=sent_at,
                status="confirmed",
                source_message_id="",
                confidence=0.7,
            ))
    
    return facts


def parse_transaction_message(message_text: str, sent_at: date, related_event_id: str) -> List[ExtractedFact]:
    facts = []
    text = message_text.lower()
    
    if any(w in text for w in ["cancelled", "canceled", "dibatalkan", "cancel"]):
        facts.append(ExtractedFact(
            fact_type="event_cancelled",
            event_id=related_event_id,
            amount=None,
            currency=None,
            effective_date=sent_at,
            status="cancelled",
            source_message_id="",
            confidence=0.9,
        ))
    
    elif any(w in text for w in ["settled", "completed", "processed", "disetujui", "confirmed"]):
        facts.append(ExtractedFact(
            fact_type="event_settled",
            event_id=related_event_id,
            amount=None,
            currency=None,
            effective_date=sent_at,
            status="settled",
            source_message_id="",
            confidence=0.9,
        ))
    
    elif any(w in text for w in ["delayed", "postponed", "ditunda", "delay"]):
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        new_date = parse_date(date_match.group(1)) if date_match else None
        facts.append(ExtractedFact(
            fact_type="event_delayed",
            event_id=related_event_id,
            amount=None,
            currency=None,
            effective_date=new_date or sent_at,
            status="delayed",
            source_message_id="",
            confidence=0.8,
        ))
    
    elif any(w in text for w in ["amount", "jumlah", "changed", "diubah", "modified"]):
        amt_match = re.search(r"(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur)", text, re.IGNORECASE)
        if amt_match:
            amt = float(amt_match.group(1).replace(",", ""))
            curr_match = re.search(r"(inr|zar|idr|usd|eur)", text, re.IGNORECASE)
            curr = curr_match.group(1).upper() if curr_match else None
            facts.append(ExtractedFact(
                fact_type="amount_changed",
                event_id=related_event_id,
                amount=amt,
                currency=curr,
                effective_date=sent_at,
                status="amended",
                source_message_id="",
                confidence=0.7,
            ))
    
    return facts


def extract_facts_from_message(message_row: pd.Series) -> List[ExtractedFact]:
    msg_id = str(message_row["message_id"])
    if msg_id in _message_cache:
        return _message_cache[msg_id]
    
    text = str(message_row["message_text"])
    user_id = str(message_row["user_id"])
    request_id = str(message_row["request_id"]) if pd.notna(message_row["request_id"]) else ""
    related_event_id = str(message_row["related_event_id"]) if pd.notna(message_row["related_event_id"]) else ""
    sent_at = parse_datetime(message_row["sent_at"])
    sent_date = sent_at.date() if sent_at else date.today()
    source_type = str(message_row["source_type"]).lower()
    
    facts = []
    
    if source_type == "employer":
        facts.extend(parse_salary_message(text, sent_date))
        facts.extend(parse_bonus_message(text, sent_date))
    elif source_type == "service_provider":
        facts.extend(parse_transaction_message(text, sent_date, related_event_id))
    
    if related_event_id:
        facts.extend(parse_transaction_message(text, sent_date, related_event_id))
    
    for fact in facts:
        fact.source_message_id = msg_id
    
    _message_cache[msg_id] = facts
    return facts


def apply_message_facts(
    facts: List[ExtractedFact],
    events: List,
    converter,
    home_currency: str
) -> List:
    event_map = {e.event_id: e for e in events}
    
    for fact in facts:
        if fact.event_id and fact.event_id in event_map:
            event = event_map[fact.event_id]
            if fact.fact_type == "event_cancelled":
                event.status = "cancelled"
            elif fact.fact_type == "event_settled":
                event.status = "settled"
                event.settlement_date = fact.effective_date
            elif fact.fact_type == "event_delayed":
                event.settlement_date = fact.effective_date
                event.status = "scheduled"
            elif fact.fact_type == "amount_changed" and fact.amount:
                event.amount = fact.amount
                event.currency = fact.currency or event.currency
                try:
                    event.home_amount = converter.convert(fact.amount, fact.currency, home_currency, fact.effective_date)
                except:
                    event.home_amount = fact.amount
        
        elif fact.fact_type in ["salary_change", "bonus_confirmed"] and fact.amount:
            new_event = NormalizedEvent(
                event_id=f"msg_{fact.source_message_id}",
                user_id="",
                event_type="income",
                description=f"Message: {fact.fact_type}",
                category="salary" if fact.fact_type == "salary_change" else "bonus",
                direction=1,
                amount=fact.amount,
                currency=fact.currency or home_currency,
                home_amount=0.0,
                event_date=fact.effective_date,
                settlement_date=fact.effective_date,
                status=fact.status,
                linked_event_id="",
                recurring=False,
                frequency=None,
                flexibility="fixed",
                minimum_allowed_amount=None,
                source_row_index=-1,
            )
            try:
                new_event.home_amount = converter.convert(fact.amount, fact.currency, home_currency, fact.effective_date)
            except:
                new_event.home_amount = fact.amount
            events.append(new_event)
    
    return events


from finance.events import NormalizedEvent