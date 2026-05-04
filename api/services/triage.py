"""
Gibson triage router.
Determines which identification path a book takes based on what's available.

Fast Path:  barcode detected → ISBN lookup → done
Standard:   cover photo → OCR + Vision → identification
Slow:       confidence too low → overnight research queue
Ghost Book: pre-ISBN, no institutional record → specialized pipeline
"""

from typing import Optional
from api.models.identification import IdentificationResult


def determine_path(
    has_barcode: bool,
    isbn: Optional[str],
    confidence: float,
    has_isbn: bool,
    language_signal: Optional[str] = None,
    pre_isbn_signals: bool = False,
) -> str:
    """
    Determine which identification path to use.
    Returns: fast_path | standard_path | slow_path | ghost_book
    """
    if has_barcode and isbn:
        return "fast_path"

    if pre_isbn_signals and not has_isbn:
        return "ghost_book"

    if confidence >= 0.85:
        return "standard_path"  # resolved

    if confidence >= 0.50:
        return "standard_path"  # needs follow-up

    return "slow_path"


def determine_condition_mode(
    floor: Optional[str],
    asking_price: Optional[float],
    listing_channels: list[str] = [],
) -> str:
    """
    Determine condition assessment mode.
    Tap: first floor / commodity / under $15
    QA: upstairs / online listing / $15 and above
    """
    if floor and "first" in floor.lower():
        if not asking_price or asking_price < 15:
            return "tap"

    if listing_channels:
        return "qa"

    if asking_price and asking_price >= 15:
        return "qa"

    return "tap"


def assign_concern_level(
    field_name: str,
    asking_price: Optional[float],
    gibson_confidence: float,
    conflicts_source: bool,
    correction_count: int,
    is_ghost_book: bool,
    is_online_listed: bool,
    price_deviation_pct: Optional[float],
) -> str:
    """
    Auto-assign concern level for corrections.

    HIGH: bib field on book >$25, conflicts source record,
          confidence >85% and corrected, same field corrected by multiple people
    MEDIUM: condition override on online-listed, price >40% from comps,
            any Ghost Book correction
    LOW: first-floor commodity condition, section change, confidence <50%
    """
    # HIGH conditions
    if asking_price and asking_price > 25 and field_name in (
        "title", "author", "publisher", "publication_year", "isbn_13"
    ):
        return "HIGH"

    if conflicts_source:
        return "HIGH"

    if gibson_confidence > 0.85:
        return "HIGH"

    if correction_count > 1:
        return "HIGH"

    # MEDIUM conditions
    if is_ghost_book:
        return "MEDIUM"

    if is_online_listed and field_name == "condition_grade":
        return "MEDIUM"

    if price_deviation_pct and price_deviation_pct > 0.40:
        return "MEDIUM"

    # LOW
    return "LOW"
