import pandas as pd
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
import logging

from config import CONFIG, AFFORDABILITY_STATUSES, PAYMENT_METHODS

logger = logging.getLogger(__name__)


def validate_output_row(row: pd.Series, request: pd.Series) -> List[str]:
    errors = []
    
    requested_amount = float(request["requested_amount"])
    request_date = pd.to_datetime(request["request_date"]).date()
    desired_completion = pd.to_datetime(request["desired_completion_date"]).date()
    allows_partial = request["allows_partial_payment"]
    
    amount_safe = float(row["amount_safe_to_pay"])
    if amount_safe < 0 or amount_safe > requested_amount:
        errors.append(f"amount_safe_to_pay {amount_safe} not in [0, {requested_amount}]")
    
    status = str(row["affordability_status"])
    if status not in AFFORDABILITY_STATUSES:
        errors.append(f"Invalid affordability_status: {status}")
    
    method = str(row["recommended_payment_method"])
    if method not in PAYMENT_METHODS:
        errors.append(f"Invalid recommended_payment_method: {method}")
    
    if status == AFFORDABILITY_STATUSES[0]:
        earliest = str(row["earliest_date_for_full_payment"])
        if earliest and earliest != "none" and earliest != "":
            try:
                earliest_date = datetime.strptime(earliest, "%Y-%m-%d").date()
                if earliest_date != request_date:
                    errors.append(f"affordable_now but earliest_date {earliest} != request_date {request_date}")
            except:
                errors.append(f"Invalid earliest_date format: {earliest}")
    
    plan_str = str(row["payment_plan"])
    if plan_str and plan_str != "none":
        payments = plan_str.split("|")
        dates = []
        amounts = []
        for p in payments:
            try:
                d_str, a_str = p.split(":")
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
                a = float(a_str)
                dates.append(d)
                amounts.append(a)
            except Exception as e:
                errors.append(f"Invalid payment_plan format: {p}")
        
        if dates != sorted(dates):
            errors.append("Payment plan dates not chronological")
        
        if method == "partial_payment":
            if len(payments) != 2:
                errors.append("Partial payment must have exactly 2 payments")
            else:
                if dates[0] != request_date:
                    errors.append("First partial payment not on request_date")
                if abs(sum(amounts) - requested_amount) > 0.01:
                    errors.append(f"Partial payments sum {sum(amounts)} != requested {requested_amount}")
                if dates[1] > desired_completion:
                    errors.append(f"Second partial payment after desired completion")
        
        if method == "installments":
            pass
    
    if status == "affordable_with_plan" and method not in ["partial_payment", "installments"]:
        errors.append(f"affordable_with_plan but method is {method}")
    
    if status == "affordable_later" and method != "wait":
        errors.append(f"affordable_later but method is {method}")
    
    if status == "not_affordable" and method != "not_recommended":
        errors.append(f"not_affordable but method is {method}")
    
    spending_str = str(row["spending_changes_needed"])
    if spending_str and spending_str != "none":
        changes = spending_str.split("|")
        if len(changes) > CONFIG.max_spending_changes:
            errors.append(f"Too many spending changes: {len(changes)} > {CONFIG.max_spending_changes}")
        
        event_ids = []
        for c in changes:
            if c.startswith("stop:"):
                eid = c[5:]
                event_ids.append(eid)
            elif c.startswith("reduce_to:"):
                parts = c.split(":")
                if len(parts) == 3:
                    event_ids.append(parts[1])
        
        if len(event_ids) != len(set(event_ids)):
            errors.append("Duplicate event_ids in spending changes")
    
    explanation = str(row["decision_explanation"])
    if not explanation or explanation == "none" or len(explanation) < 10:
        errors.append("decision_explanation missing or too short")
    
    return errors


def validate_all_outputs(output_df: pd.DataFrame, requests_df: pd.DataFrame) -> Dict[str, List[str]]:
    all_errors = {}
    for _, row in output_df.iterrows():
        req = requests_df[requests_df["request_id"] == row["request_id"]]
        if len(req) == 0:
            all_errors[row["request_id"]] = ["Request not found"]
            continue
        errors = validate_output_row(row, req.iloc[0])
        if errors:
            all_errors[row["request_id"]] = errors
    return all_errors