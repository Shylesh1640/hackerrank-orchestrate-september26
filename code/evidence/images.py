from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass
from functools import lru_cache
import logging
import json

from config import CONFIG

logger = logging.getLogger(__name__)


@dataclass
class ImageExtraction:
    image_id: str
    amount: Optional[float]
    currency: Optional[str]
    date: Optional[str]
    document_type: Optional[str]
    status: Optional[str]
    description: Optional[str]
    confidence: float
    raw_text: str


_image_cache: Dict[str, ImageExtraction] = {}


def extract_with_vlm(image_path: Path) -> Optional[ImageExtraction]:
    try:
        return extract_with_ocr_fallback(image_path)
    except Exception as e:
        logger.warning(f"VLM extraction failed for {image_path.name}: {e}")
        return None


def extract_with_ocr_fallback(image_path: Path) -> Optional[ImageExtraction]:
    import pytesseract
    from PIL import Image
    
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        
        return parse_image_text(image_path.stem, text)
    except Exception as e:
        logger.warning(f"OCR failed for {image_path.name}: {e}")
        return None


def parse_image_text(image_id: str, text: str) -> ImageExtraction:
    import re
    
    amount = None
    currency = None
    doc_date = None
    doc_type = None
    status = None
    description = ""
    
    amount_patterns = [
        r"(?:amount|total|balance|jumlah|total)\s*[:\-]?\s*(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur|rs\.?|r\$?)",
        r"(\d[\d,\.]*)\s*(?:inr|zar|idr|usd|eur|rs\.?|r\$?)",
    ]
    
    for pattern in amount_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                amount = float(matches[0].replace(",", ""))
                break
            except:
                pass
    
    for curr in ["inr", "zar", "idr", "usd", "eur", "rs", "r$"]:
        if curr in text.lower():
            currency = curr.upper().replace("RS", "INR").replace("R$", "ZAR")
            break
    
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if date_match:
        doc_date = date_match.group(1)
    
    if any(w in text.lower() for w in ["invoice", "bill", "tagihan"]):
        doc_type = "invoice"
    elif any(w in text.lower() for w in ["receipt", "kwitansi"]):
        doc_type = "receipt"
    elif any(w in text.lower() for w in ["statement", "statement"]):
        doc_type = "statement"
    elif any(w in text.lower() for w in ["payslip", "salary slip", "slip gaji"]):
        doc_type = "payslip"
    else:
        doc_type = "document"
    
    if any(w in text.lower() for w in ["paid", "lunas", "settled"]):
        status = "paid"
    elif any(w in text.lower() for w in ["pending", "menunggu", "unpaid"]):
        status = "pending"
    elif any(w in text.lower() for w in ["cancelled", "dibatalkan"]):
        status = "cancelled"
    
    description = text[:500]
    
    return ImageExtraction(
        image_id=image_id,
        amount=amount,
        currency=currency,
        date=doc_date,
        document_type=doc_type,
        status=status,
        description=description,
        confidence=0.6,
        raw_text=text[:1000],
    )


def extract_image_facts(image_id: str, image_dir: Path) -> Optional[ImageExtraction]:
    if image_id in _image_cache:
        return _image_cache[image_id]
    
    image_path = image_dir / f"{image_id}.png"
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None
    
    result = extract_with_vlm(image_path)
    if result:
        _image_cache[image_id] = result
    return result


def apply_image_facts(
    extraction: ImageExtraction,
    events: list,
    converter,
    home_currency: str,
    request_date
) -> list:
    if not extraction or extraction.amount is None:
        return events
    
    new_event = NormalizedEvent(
        event_id=f"img_{extraction.image_id}",
        user_id="",
        event_type="expense",
        description=f"Image: {extraction.document_type}",
        category=extraction.document_type or "other",
        direction=-1,
        amount=extraction.amount,
        currency=extraction.currency or home_currency,
        home_amount=0.0,
        event_date=None,
        settlement_date=None,
        status=extraction.status or "pending",
        linked_event_id="",
        recurring=False,
        frequency=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
        source_row_index=-1,
    )
    
    if extraction.date:
        try:
            from datetime import datetime
            new_event.event_date = datetime.strptime(extraction.date, "%Y-%m-%d").date()
            new_event.settlement_date = new_event.event_date
        except:
            pass
    
    if new_event.settlement_date is None:
        new_event.settlement_date = request_date
    
    try:
        new_event.home_amount = converter.convert(
            extraction.amount, 
            extraction.currency or home_currency, 
            home_currency, 
            new_event.settlement_date
        )
    except:
        new_event.home_amount = extraction.amount
    
    events.append(new_event)
    return events


from finance.events import NormalizedEvent