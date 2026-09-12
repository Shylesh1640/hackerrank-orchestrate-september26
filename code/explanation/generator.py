from datetime import date
from typing import List, Dict, Optional
from finance.state import UserFinancialState
from planning.ranking import PaymentPlan

AFFORDABLE_NOW = "affordable_now"
AFFORDABLE_WITH_PLAN = "affordable_with_plan"
AFFORDABLE_LATER = "affordable_later"
NOT_AFFORDABLE = "not_affordable"


def generate_explanation(
    state: UserFinancialState,
    request,
    plan: PaymentPlan,
    amount_safe_to_pay: float,
    earliest_full_date: Optional[date],
    status: str
) -> str:
    currency = state.home_currency
    requested_amount = float(request["requested_amount"])
    request_date = state.request_date
    min_balance = state.minimum_balance
    
    if status == AFFORDABLE_NOW:
        return (
            f"Pay {currency} {requested_amount:,.2f} today. "
            f"This leaves at least {currency} {min_balance:,.2f} available over the next 90 days."
        )
    
    elif status == AFFORDABLE_WITH_PLAN:
        if plan.method == "partial_payment":
            first_amt = plan.payments[0][1]
            second_amt = plan.payments[1][1]
            second_date = plan.payments[1][0].strftime("%Y-%m-%d")
            return (
                f"Pay {currency} {first_amt:,.2f} today and the remaining "
                f"{currency} {second_amt:,.2f} on {second_date}. "
                f"This completes the full request and keeps the {currency} {min_balance:,.2f} minimum protected."
            )
        
        elif plan.method == "installments":
            num_payments = len(plan.payments)
            amt = plan.payments[0][1]
            start_date = plan.payments[0][0].strftime("%Y-%m-%d")
            total = plan.total_cost
            return (
                f"Use {num_payments} installments of {currency} {amt:,.2f}, starting {start_date}. "
                f"Total cost {currency} {total:,.2f}. "
                f"This leaves at least {currency} {min_balance:,.2f} available."
            )
        
        elif plan.spending_changes:
            changes_desc = []
            for change in plan.spending_changes:
                if change["type"] == "stop":
                    changes_desc.append(f"stop the {change['category']}")
                elif change["type"] == "reduce":
                    changes_desc.append(f"reduce the {change['category']} to {currency} {change['new_amount']:,.2f}")
            
            changes_str = " and ".join(changes_desc)
            return (
                f"{changes_str.capitalize()}, then pay {currency} {requested_amount:,.2f} today. "
                f"This leaves at least {currency} {min_balance:,.2f} available."
            )
    
    elif status == AFFORDABLE_LATER:
        if earliest_full_date:
            date_str = earliest_full_date.strftime("%Y-%m-%d")
            return (
                f"Pay {currency} {requested_amount:,.2f} in full on {date_str}. "
                f"Paying earlier would take the balance below the {currency} {min_balance:,.2f} minimum."
            )
        else:
            return (
                f"Wait until a later date to pay {currency} {requested_amount:,.2f} in full. "
                f"Paying earlier would take the balance below the {currency} {min_balance:,.2f} minimum."
            )
    
    else:
        return (
            f"Do not make this payment by {request['desired_completion_date']}. "
            f"None of the available options keeps the {currency} {min_balance:,.2f} minimum protected."
        )


def format_payment_plan(plan: PaymentPlan) -> str:
    if not plan.payments:
        return "none"
    return "|".join(f"{d.strftime('%Y-%m-%d')}:{a:.2f}" for d, a in plan.payments)


def format_spending_changes(changes: List[Dict]) -> str:
    if not changes:
        return "none"
    parts = []
    for c in changes:
        if c["type"] == "stop":
            parts.append(f"stop:{c['event_id']}")
        elif c["type"] == "reduce":
            parts.append(f"reduce_to:{c['event_id']}:{c['new_amount']:.2f}")
    return "|".join(parts)


def format_earliest_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d")