import pandas as pd
from datetime import datetime, date
from typing import Dict, Optional, Tuple
from functools import lru_cache
import logging

from config import CONFIG

logger = logging.getLogger(__name__)


class CurrencyConverter:
    def __init__(self, exchange_rates: pd.DataFrame):
        self.rates = self._build_rate_index(exchange_rates)
    
    def _build_rate_index(self, df: pd.DataFrame) -> Dict[str, Dict[Tuple[str, str], float]]:
        index = {}
        for _, row in df.iterrows():
            rate_date = row["rate_date"]
            from_curr = row["from_currency"]
            to_curr = row["to_currency"]
            rate = float(row["rate"])
            if rate_date not in index:
                index[rate_date] = {}
            index[rate_date][(from_curr, to_curr)] = rate
            index[rate_date][(to_curr, from_curr)] = 1.0 / rate
        return index
    
    def _find_closest_rate_date(self, target_date: date) -> Optional[str]:
        if not self.rates:
            return None
        rate_dates = sorted(self.rates.keys())
        target_str = target_date.strftime("%Y-%m-%d")
        
        closest = None
        for d in rate_dates:
            if d <= target_str:
                closest = d
            else:
                break
        return closest
    
    def convert(self, amount: float, from_currency: str, to_currency: str, 
                conversion_date: date) -> float:
        if from_currency == to_currency:
            return amount
        
        rate_date = self._find_closest_rate_date(conversion_date)
        if rate_date is None:
            raise ValueError(f"No exchange rate available on or before {conversion_date}")
        
        rate_key = (from_currency, to_currency)
        if rate_key not in self.rates[rate_date]:
            raise ValueError(f"No exchange rate for {from_currency} -> {to_currency} on {rate_date}")
        
        rate = self.rates[rate_date][rate_key]
        return amount * rate


def get_converter(data_bundle) -> CurrencyConverter:
    return CurrencyConverter(data_bundle.exchange_rates)