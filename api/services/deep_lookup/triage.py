import anthropic
from api.config import settings


async def triage_collectibility(research: dict) -> tuple[bool, str]:
    """
    Returns (proceed: bool, reason: str)
    If proceed is False, reason is shown to dealer and pipeline stops.
    """
    title      = (research.get("title")           or {}).get("value") or "Unknown"
    author     = (research.get("author")          or {}).get("value") or "Unknown"
    publisher  = (research.get("publisher")       or {}).get("value") or "unknown"
    year       = (research.get("year")            or {}).get("value")
    isbn       = (research.get("isbn_13")         or {}).get("value") or ""
    edition    = (research.get("edition_statement") or {}).get("value") or ""
    subjects   = (research.get("subjects")        or {}).get("value") or []
    pricing    = research.get("pricing")          or {}
    comp_count = pricing.get("comp_count") or 0
    price      = pricing.get("suggested_price")

    prompt = f"""You are a rare book specialist. Based only on bibliographic metadata,
assess whether this book is likely to have collectible value beyond a standard reading copy.

Title: {title}
Author: {author}
Publisher: {publisher}
Year: {year or "unknown"}
ISBN: {isbn or "none — pre-ISBN era"}
Edition statement: {edition or "none recorded"}
Subjects: {', '.join(subjects[:3]) if subjects else "none"}
Current pricing comps: {comp_count} found, suggested ${price or 'none'}

Consider: author significance, publisher significance, era, known collectible titles,
first edition likelihood, whether this author's work is actively collected.

Respond with ONLY one of these two formats:
PROCEED: [one sentence reason]
SKIP: [one sentence reason]

Be conservative — if uncertain, say PROCEED. Missing a valuable book costs more
than an unnecessary lookup."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_research_model,   # Haiku — triage is cheap by design
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    if text.upper().startswith("PROCEED"):
        reason = text.split(":", 1)[1].strip() if ":" in text else text
        return True, reason
    elif text.upper().startswith("SKIP"):
        reason = text.split(":", 1)[1].strip() if ":" in text else text
        return False, reason
    else:
        # Default to proceed on ambiguous response
        return True, "Uncertain — proceeding to full lookup"
