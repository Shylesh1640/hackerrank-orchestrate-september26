from datetime import date, timedelta
from typing import List, Tuple, Optional
import pandas as pd
import logging

from config import CONFIG
from finance.state import UserFinancialState
from finance.forecast import run_forecast

logger = logging.getLogger(__name__)


def parse_payment_options(payment_options_df: pd.DataFrame) -> List[dict]:
    options = []
    for _, row in payment_options_df.iterrows():
        method = str(row["payment_method"]).lower()
        if method == "installments":
            try:
                option = {
                    "payment_option_id": str(row["payment_option_id"]),
                    "method": method,
                    "payment_amount": float(row["payment_amount"]),
                    "number_of_payments": int(row["number_of_payments"]),
                    "first_payment_date": pd.to_datetime(row["first_payment_date"]).date(),
                    "payment_frequency_days": int(row["payment_frequency_days"]) if pd.notna(row["payment_frequency_days"]) else 30,
                    "financing_fee": float(row["financing_fee"]) if pd.notna(row["financing_fee"]) else 0.0,
                    "total_payable_amount": float(row["total_payable_amount"]),
                }
                options.append(option)
            except Exception as e:
                logger.warning(f"Failed to parse payment option {row.get('payment_option_id')}: {e}")
    return options


def filter_eligible_installments(
    options: List[dict],
    state: UserFinancialState,
    request_date: date,
    desired_completion_date: date
) -> List[dict]:
    eligible = []
    
    for opt in options:
        if "installments" not in state.payment_methods:
            continue
        
        if state.max_installment_months is not None:
            max_payments = state.max_installment_months
            if opt["payment_frequency_days"] <= 31:
                if opt["number_of_payments"] > max_payments:
                    continue
        
        last_payment = opt["first_payment_date"] + timedelta(
            days=opt["payment_frequency_days"] * (opt["number_of_payments"] - 1)
        )
        if last_payment > desired_completion_date:
            continue
        
        eligible.append(opt)
    
    return eligible


def build_installment_schedule(option: dict) -> List[Tuple[date, float]]:
    schedule = []
    current = option["first_payment_date"]
    for i in range(option["number_of_payments"]):
        schedule.append((current, option["payment_amount"]))
        current += timedelta(days=option["payment_frequency_days"])
    return schedule


def check_installment_safety(
    state: UserFinancialState,
    schedule: List[Tuple[date, float]]
) -> bool:
    forecast = run_forecast(state, request_payments=schedule)
    return forecast.is_safe