"""
USBN — Universal Standard Book Number.

Open pre-ISBN identifier for books that predate or fall outside the ISBN system.
Computed deterministically from title + author + year as printed on the book.

Spec: openusbn.org
Format: USBN-XXXXXXXXXX (10-char hex hash)

The USBN is stable: same inputs always produce the same identifier.
It does not prove identity — two different editions of the same work
by the same author in the same year will share a USBN. That is by design.
The USBN groups related items; edition-level disambiguation happens
at the bibliographic record level.
"""

import hashlib
import re
import unicodedata


def normalize_for_usbn(text: str) -> str:
    """
    Normalize text for USBN computation.

    1. Unicode NFC normalization
    2. Lowercase
    3. Strip diacritics (ü→u, é→e, etc.)
    4. Collapse whitespace
    5. Remove punctuation except hyphens
    6. Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # NFC normalize
    text = unicodedata.normalize("NFC", text)
    text = text.lower()

    # Strip diacritics: decompose, remove combining marks, recompose
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text)

    # Remove punctuation except hyphens
    text = re.sub(r"[^\w\s-]", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def compute_usbn(title: str, author: str, year: int | str | None = None) -> str:
    """
    Compute a USBN from title, author, and optional year.

    Args:
        title: Book title as printed
        author: Author name as printed (last, first or first last)
        year: Publication year as printed (optional)

    Returns:
        USBN string in format "USBN-XXXXXXXXXX"
    """
    norm_title = normalize_for_usbn(title or "")
    norm_author = normalize_for_usbn(author or "")
    norm_year = str(year).strip() if year else ""

    # Canonical input string: title | author | year
    canonical = f"{norm_title}|{norm_author}|{norm_year}"

    # SHA-256, take first 10 hex characters
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10]

    return f"USBN-{digest.upper()}"


def validate_usbn(usbn: str) -> bool:
    """Check if a string is a valid USBN format."""
    return bool(re.match(r"^USBN-[0-9A-F]{10}$", usbn))
