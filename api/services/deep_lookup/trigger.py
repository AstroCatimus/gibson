def should_suggest_deep_lookup(research: dict) -> tuple[bool, list[str]]:
    """
    Returns (should_suggest: bool, reasons: list[str])
    reasons is shown in the UI suggestion card.
    """
    title      = research["title"]["value"]
    author     = research["author"]["value"]
    publisher  = research["publisher"]["value"]
    year       = research["year"]["value"]
    isbn       = research["isbn_13"]["value"]
    price      = research["pricing"]["suggested_price"]
    price_low  = research["pricing"]["range_low"]
    comp_count = research["pricing"]["comp_count"]
    routing    = research["routing"]

    reasons = []

    # No ISBN — pre-1972 era or self-published
    if not isbn:
        reasons.append("No ISBN — may predate standard publishing")

    # Pre-1970 publication
    if year and year < 1970:
        reasons.append(f"Published {year} — potential collectible era")

    # Pre-1980 with no pricing comps at all
    if year and year < 1980 and comp_count == 0:
        reasons.append("Pre-1980 with no market comps found")

    # Significant price gap between suggested and low comp
    if price and price_low and price_low >= price * 2.0:
        reasons.append("Market comps suggest higher value than standard price")

    # Ghost book — no institutional record found
    if routing == "GHOST_BOOK":
        reasons.append("No institutional record found — may be rare")

    # LOC record but no BooksRun pricing — strong pre-ISBN signal
    if research["publisher"]["source"] == "loc" and comp_count == 0:
        reasons.append("Library of Congress record only — no market pricing found")

    if not reasons:
        return False, []

    return True, reasons
