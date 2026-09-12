from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Config:
    data_dir: Path = Path(__file__).parent.parent / "dataset"
    requests_file: Path = None
    sample_requests_file: Path = None
    financial_profiles_file: Path = None
    financial_events_file: Path = None
    exchange_rates_file: Path = None
    request_payment_options_file: Path = None
    messages_file: Path = None
    images_file: Path = None
    images_dir: Path = None
    output_file: Path = None
    
    forecast_horizon_days: int = 90
    max_spending_changes: int = 3
    
    def __post_init__(self):
        if self.requests_file is None:
            self.requests_file = self.data_dir / "requests.csv"
        if self.sample_requests_file is None:
            self.sample_requests_file = self.data_dir / "sample_requests.csv"
        if self.financial_profiles_file is None:
            self.financial_profiles_file = self.data_dir / "financial_profiles.csv"
        if self.financial_events_file is None:
            self.financial_events_file = self.data_dir / "financial_events.csv"
        if self.exchange_rates_file is None:
            self.exchange_rates_file = self.data_dir / "exchange_rates.csv"
        if self.request_payment_options_file is None:
            self.request_payment_options_file = self.data_dir / "request_payment_options.csv"
        if self.messages_file is None:
            self.messages_file = self.data_dir / "messages.csv"
        if self.images_file is None:
            self.images_file = self.data_dir / "images.csv"
        if self.images_dir is None:
            self.images_dir = self.data_dir / "media" / "images"
        if self.output_file is None:
            self.output_file = self.data_dir / "output.csv"

CONFIG = Config()

CURRENCIES = ["INR", "ZAR", "IDR", "USD", "EUR"]

DIRECTION_SIGN = {
    "credit": 1,
    "debit": -1,
    "income": 1,
    "expense": -1,
    "payment": -1,
    "refund": 1,
    "debt_payment": -1,
    "investment": -1,
    "transfer": -1,
    "subscription": -1,
}

STATUS_SETTLED = "settled"
STATUS_PENDING = "pending"
STATUS_SCHEDULED = "scheduled"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"
STATUS_UNREALIZED = "unrealized"

FLEXIBILITY_STOPPABLE = "stoppable"
FLEXIBILITY_REDUCIBLE = "reducible"
FLEXIBILITY_FIXED = "fixed"

AFFORDABLE_NOW = "affordable_now"
AFFORDABLE_WITH_PLAN = "affordable_with_plan"
AFFORDABLE_LATER = "affordable_later"
NOT_AFFORDABLE = "not_affordable"

METHOD_FULL = "full_payment"
METHOD_PARTIAL = "partial_payment"
METHOD_INSTALLMENTS = "installments"
METHOD_WAIT = "wait"
METHOD_NOT_RECOMMENDED = "not_recommended"

AFFORDABILITY_STATUSES = [AFFORDABLE_NOW, AFFORDABLE_WITH_PLAN, AFFORDABLE_LATER, NOT_AFFORDABLE]
PAYMENT_METHODS = [METHOD_FULL, METHOD_PARTIAL, METHOD_INSTALLMENTS, METHOD_WAIT, METHOD_NOT_RECOMMENDED]