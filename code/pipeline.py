from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd
import logging

from config import CONFIG, AFFORDABLE_NOW, AFFORDABLE_WITH_PLAN, AFFORDABLE_LATER, NOT_AFFORDABLE
from config import METHOD_FULL, METHOD_PARTIAL, METHOD_INSTALLMENTS, METHOD_WAIT, METHOD_NOT_RECOMMENDED

from data.loader import load_all_data, get_request, get_payment_options, get_user_messages, get_linked_images, parse_date
from finance.currency import get_converter
from finance.state import build_user_state
from finance.forecast import run_forecast, is_safe_immediate_payment
from planning.full_payment import calculate_amount_safe_to_pay, calculate_earliest_full_payment
from planning.partial_payment import check_partial_payment_eligible, build_partial_payment_plan
from planning.installments import parse_payment_options, filter_eligible_installments, build_installment_schedule, check_installment_safety
from planning.spending_changes import find_best_spending_changes
from planning.ranking import PaymentPlan, rank_plans
from verification.safety import verify_plan
from explanation.generator import generate_explanation, format_payment_plan, format_spending_changes, format_earliest_date
from evidence.messages import extract_facts_from_message, apply_message_facts
from evidence.images import extract_image_facts, apply_image_facts

logger = logging.getLogger(__name__)


def process_request(request_id: str, data_bundle, converter) -> Dict:
    request = get_request(data_bundle, request_id)
    user_id = str(request["user_id"])
    request_date = parse_date(request["request_date"])
    desired_completion = parse_date(request["desired_completion_date"])
    requested_amount = float(request["requested_amount"])
    allows_partial = str(request["allows_partial_payment"]).lower() in ["true", "1", "yes"]
    
    logger.info(f"Processing {request_id} for {user_id} on {request_date}")
    
    state = build_user_state(data_bundle, request_id, request_date, converter)
    
    messages = get_user_messages(data_bundle, user_id, request_id)
    for _, msg in messages.iterrows():
        facts = extract_facts_from_message(msg)
        state.__dict__["events"] = apply_message_facts(facts, state.__dict__.get("events", []), converter, state.home_currency)
    
    images = get_linked_images(data_bundle, request_id)
    for _, img in images.iterrows():
        extraction = extract_image_facts(str(img["image_id"]), CONFIG.images_dir)
        if extraction:
            state.__dict__["events"] = apply_image_facts(extraction, state.__dict__.get("events", []), converter, state.home_currency, request_date)
    
    amount_safe = calculate_amount_safe_to_pay(state, requested_amount, request_date)
    earliest_full = calculate_earliest_full_payment(state, requested_amount, request_date, desired_completion)
    
    plans = []
    
    if is_safe_immediate_payment(state, requested_amount, request_date) and METHOD_FULL in state.payment_methods:
        plans.append(PaymentPlan(
            method=METHOD_FULL,
            payments=[(request_date, requested_amount)],
            total_cost=requested_amount,
            spending_changes=[],
            completion_date=request_date,
            request_id=request_id,
        ))
    
    if check_partial_payment_eligible(state, request, amount_safe, earliest_full):
        partial_plan = build_partial_payment_plan(state, request, amount_safe, earliest_full)
        if partial_plan:
            plans.append(PaymentPlan(
                method=METHOD_PARTIAL,
                payments=partial_plan,
                total_cost=requested_amount,
                spending_changes=[],
                completion_date=earliest_full,
                request_id=request_id,
            ))
    
    payment_options_df = get_payment_options(data_bundle, request_id)
    installment_options = parse_payment_options(payment_options_df)
    eligible_installments = filter_eligible_installments(installment_options, state, request_date, desired_completion)
    
    for opt in eligible_installments:
        schedule = build_installment_schedule(opt)
        if check_installment_safety(state, schedule):
            plans.append(PaymentPlan(
                method=METHOD_INSTALLMENTS,
                payments=schedule,
                total_cost=opt["total_payable_amount"],
                spending_changes=[],
                completion_date=schedule[-1][0],
                payment_option_id=opt["payment_option_id"],
                request_id=request_id,
            ))
    
    if earliest_full and earliest_full > request_date and METHOD_FULL in state.payment_methods:
        if earliest_full <= desired_completion:
            plans.append(PaymentPlan(
                method=METHOD_WAIT,
                payments=[(earliest_full, requested_amount)],
                total_cost=requested_amount,
                spending_changes=[],
                completion_date=earliest_full,
                request_id=request_id,
            ))
    
    verified_plans = []
    for plan in plans:
        verified, errors = verify_plan(plan, state, request)
        if verified:
            verified_plans.append(plan)
        else:
            logger.debug(f"Plan {plan.method} failed verification: {errors}")
            
            if plan.method in [METHOD_FULL, METHOD_PARTIAL, METHOD_INSTALLMENTS]:
                spending_changes = find_best_spending_changes(state, plan.payments)
                if spending_changes:
                    sc_dict = {c["event_id"]: c["new_amount"] for c in spending_changes if c["type"] == "reduce"}
                    stopped = [c["event_id"] for c in spending_changes if c["type"] == "stop"]
                    verified2, errors2 = verify_plan(plan, state, request, sc_dict, stopped)
                    if verified2:
                        plan.spending_changes = spending_changes
                        verified_plans.append(plan)
    
    if not verified_plans:
        status = NOT_AFFORDABLE
        method = METHOD_NOT_RECOMMENDED
        best_plan = PaymentPlan(
            method=METHOD_NOT_RECOMMENDED,
            payments=[],
            total_cost=0,
            spending_changes=[],
            completion_date=desired_completion,
            request_id=request_id,
        )
    else:
        ranked = rank_plans(verified_plans, desired_completion)
        best_plan = ranked[0]
        method = best_plan.method
        
        if method == METHOD_FULL:
            status = AFFORDABLE_NOW
        elif method in [METHOD_PARTIAL, METHOD_INSTALLMENTS]:
            status = AFFORDABLE_WITH_PLAN
        elif method == METHOD_WAIT:
            status = AFFORDABLE_LATER
        else:
            status = NOT_AFFORDABLE
    
    explanation = generate_explanation(state, request, best_plan, amount_safe, earliest_full, status)
    
    return {
        "request_id": request_id,
        "amount_safe_to_pay": round(amount_safe, 2),
        "affordability_status": status,
        "recommended_payment_method": method,
        "payment_plan": format_payment_plan(best_plan),
        "earliest_date_for_full_payment": format_earliest_date(earliest_full),
        "spending_changes_needed": format_spending_changes(best_plan.spending_changes),
        "decision_explanation": explanation,
    }


def run_pipeline(request_ids: Optional[List[str]] = None) -> pd.DataFrame:
    data_bundle = load_all_data()
    converter = get_converter(data_bundle)
    
    if request_ids is None:
        request_ids = data_bundle.requests["request_id"].tolist()
    
    results = []
    for req_id in request_ids:
        try:
            result = process_request(req_id, data_bundle, converter)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to process {req_id}: {e}")
            results.append({
                "request_id": req_id,
                "amount_safe_to_pay": 0.0,
                "affordability_status": NOT_AFFORDABLE,
                "recommended_payment_method": METHOD_NOT_RECOMMENDED,
                "payment_plan": "none",
                "earliest_date_for_full_payment": "",
                "spending_changes_needed": "none",
                "decision_explanation": f"Processing error: {str(e)[:100]}",
            })
    
    return pd.DataFrame(results)


def main():
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logger.info("Starting Buy or Wait? pipeline")
    
    output_df = run_pipeline()
    
    output_df.to_csv(CONFIG.output_file, index=False)
    logger.info(f"Output written to {CONFIG.output_file}")
    
    print(f"Processed {len(output_df)} requests")
    print(f"Output saved to {CONFIG.output_file}")


if __name__ == "__main__":
    main()