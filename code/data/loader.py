import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, date
import logging

from config import CONFIG

logger = logging.getLogger(__name__)


@dataclass
class DataBundle:
    requests: pd.DataFrame
    sample_requests: pd.DataFrame
    profiles: pd.DataFrame
    events: pd.DataFrame
    exchange_rates: pd.DataFrame
    payment_options: pd.DataFrame
    messages: pd.DataFrame
    images: pd.DataFrame


def load_csv(path: Path, **kwargs) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, **kwargs)
        logger.info(f"Loaded {len(df)} rows from {path.name}")
        return df
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        raise


def load_all_data() -> DataBundle:
    requests = load_csv(CONFIG.requests_file)
    sample_requests = load_csv(CONFIG.sample_requests_file)
    profiles = load_csv(CONFIG.financial_profiles_file)
    events = load_csv(CONFIG.financial_events_file)
    exchange_rates = load_csv(CONFIG.exchange_rates_file)
    payment_options = load_csv(CONFIG.request_payment_options_file)
    messages = load_csv(CONFIG.messages_file)
    images = load_csv(CONFIG.images_file)

    for df, name in [(events, "events"), (payment_options, "payment_options"), 
                     (messages, "messages"), (images, "images")]:
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).replace({"nan": "", "None": ""})

    return DataBundle(
        requests=requests,
        sample_requests=sample_requests,
        profiles=profiles,
        events=events,
        exchange_rates=exchange_rates,
        payment_options=payment_options,
        messages=messages,
        images=images,
    )


def get_user_profile(data: DataBundle, user_id: str) -> pd.Series:
    profile = data.profiles[data.profiles["user_id"] == user_id]
    if len(profile) == 0:
        raise ValueError(f"No profile found for user {user_id}")
    return profile.iloc[0]


def get_user_events(data: DataBundle, user_id: str) -> pd.DataFrame:
    return data.events[data.events["user_id"] == user_id].copy()


def get_request(data: DataBundle, request_id: str) -> pd.Series:
    req = data.requests[data.requests["request_id"] == request_id]
    if len(req) == 0:
        req = data.sample_requests[data.sample_requests["request_id"] == request_id]
    if len(req) == 0:
        raise ValueError(f"No request found for {request_id}")
    return req.iloc[0]


def get_sample_request(data: DataBundle, request_id: str) -> Optional[pd.Series]:
    req = data.sample_requests[data.sample_requests["request_id"] == request_id]
    if len(req) == 0:
        return None
    return req.iloc[0]


def get_payment_options(data: DataBundle, request_id: str) -> pd.DataFrame:
    return data.payment_options[data.payment_options["request_id"] == request_id].copy()


def get_user_messages(data: DataBundle, user_id: str, request_id: Optional[str] = None) -> pd.DataFrame:
    msgs = data.messages[data.messages["user_id"] == user_id].copy()
    if request_id:
        msgs = msgs[msgs["request_id"] == request_id]
    return msgs


def get_linked_images(data: DataBundle, request_id: str) -> pd.DataFrame:
    return data.images[(data.images["request_id"] == request_id) | (data.images["user_id"].isin(
        data.requests[data.requests["request_id"] == request_id]["user_id"]
    ))].copy()


def get_event_by_id(data: DataBundle, event_id: str) -> Optional[pd.Series]:
    event = data.events[data.events["event_id"] == event_id]
    if len(event) == 0:
        return None
    return event.iloc[0]


def parse_date(date_str: str) -> Optional[date]:
    if pd.isna(date_str) or date_str == "":
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(dt_str: str) -> Optional[datetime]:
    if pd.isna(dt_str) or dt_str == "":
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None