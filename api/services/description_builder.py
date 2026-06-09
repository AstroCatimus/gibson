"""
Gibson listing description builder.

Two-zone output per listing:

  Zone 1 — verified_facts (template, deterministic)
    Condition grade, dust jacket state, signed/inscribed, edition points from
    deep lookup. These are dealer-verifiable facts. No AI touches this zone.
    Facsimile disclosure is non-suppressible and always prepends.

  Zone 2 — narrative (Haiku-generated, platform-tuned)
    Prose paragraph drawing on bibliographic data + deep lookup findings.
    Dealer MUST review and edit before posting. Never auto-submitted.

Platform character limits enforced:
  ebay      — conditionDescription ≤ 1000 chars (listingDescription has no hard cap)
  amazon    — condition_note ≤ 2000 chars (plain text, no HTML)
  biblio    — no strict limit; ~400 chars is conventional
"""

import anthropic
import logging

from api.config import settings

logger = logging.getLogger("gibson.description_builder")

# Platform-specific narrative instructions
_PLATFORM_INSTRUCTIONS = {
    "ebay": (
        "Write 2–3 sentences for an eBay listing. "
        "Collector-friendly tone. Lead with what makes this copy notable. "
        "Mention edition, signing, or provenance if known. "
        "Plain text only — no markdown, no HTML tags."
    ),
    "amazon": (
        "Write 1–2 sentences for an Amazon condition note. "
        "Plain text only. No HTML. Max 180 characters. "
        "Focus on condition highlights and any notable features. "
        "Terse and factual."
    ),
    "biblio": (
        "Write 3–4 sentences for a Biblio listing. "
        "Collector audience — detail edition points, provenance, and significance. "
        "Plain text only. Mention sources if relevant."
    ),
}

_PLATFORM_CHAR_LIMITS = {
    "ebay":    1000,
    "amazon":  2000,
    "biblio":  2000,
}


# ── Zone 1: Verified Facts (template) ────────────────────────────────────────

def build_verified_facts(item: dict, deep_lookup: dict | None = None) -> str:
    """
    Build the deterministic facts block from stock item fields.
    No AI. No inference. Only what's recorded.
    """
    parts = []

    # Facsimile — non-suppressible, always first
    if item.get("is_facsimile"):
        parts.append("FACSIMILE EDITION.")

    # Condition + dust jacket
    # jacket_present / jacket_grade come from the dust jacket schema migration (pending).
    # Handled gracefully if columns don't exist yet.
    grade = item.get("condition_grade") or ""
    jacket_present = item.get("jacket_present")       # 'present' | 'absent_expected' | 'absent_unknown'
    jacket_grade   = item.get("jacket_grade") or ""

    if grade:
        if jacket_present == "present" and jacket_grade:
            parts.append(f"{grade} in {jacket_grade} dust jacket.")
        elif jacket_present == "present":
            parts.append(f"{grade} in dust jacket.")
        elif jacket_present == "absent_expected":
            parts.append(f"{grade}. No dust jacket.")
        elif jacket_present == "absent_unknown":
            parts.append(f"{grade}. Dust jacket not present.")
        else:
            parts.append(f"{grade}.")

    # Signed / inscribed
    signed    = item.get("is_signed", False)
    inscribed = item.get("is_inscribed", False)
    if signed and inscribed:
        parts.append("Signed and inscribed by the author.")
    elif signed:
        parts.append("Signed by the author.")
    elif inscribed:
        parts.append("Inscribed.")

    inscription_note = (item.get("inscription_note") or "").strip()
    if inscription_note:
        parts.append(inscription_note)

    # Edition points from deep lookup
    if deep_lookup:
        anomaly_type   = deep_lookup.get("anomaly_type")
        edition_assess = (deep_lookup.get("edition_assessment") or "").strip()
        anomaly_detail = (deep_lookup.get("anomaly_detail") or "").strip()

        if anomaly_type == "FIRST_EDITION" and edition_assess:
            parts.append(edition_assess)
        elif anomaly_type == "VARIANT" and anomaly_detail:
            parts.append(anomaly_detail)
        elif edition_assess and anomaly_type not in ("SIGNED", "ASSOCIATION"):
            # Only surface edition assessment if it's not just restating the signature
            parts.append(edition_assess)

    # Condition notes (dealer-written)
    condition_notes = (item.get("condition_notes") or "").strip()
    if condition_notes:
        parts.append(condition_notes)

    return " ".join(parts)


# ── Zone 2: Narrative (Haiku) ─────────────────────────────────────────────────

def _deep_lookup_has_content(deep_lookup: dict) -> bool:
    """
    Only fire Haiku if the deep lookup actually found something worth writing about.
    A triage-stopped result (stage_reached == 2) or empty assessment has nothing to say.
    """
    if not deep_lookup:
        return False
    if deep_lookup.get("stage_reached", 0) < 3:
        return False
    has_edition  = bool((deep_lookup.get("edition_assessment") or "").strip())
    has_anomaly  = bool((deep_lookup.get("anomaly_detail") or "").strip())
    has_sig      = bool((deep_lookup.get("signature_detail") or "").strip())
    return has_edition or has_anomaly or has_sig


async def build_narrative(
    item: dict,
    platform: str,
    deep_lookup: dict,           # caller must pre-check _deep_lookup_has_content
) -> str:
    """
    Generate a short prose paragraph via Haiku.
    Only called when deep lookup has substantive findings.
    Platform-tuned. Dealer must review before use.
    """
    platform = platform.lower()
    instructions = _PLATFORM_INSTRUCTIONS.get(platform, _PLATFORM_INSTRUCTIONS["ebay"])

    ctx_lines = [
        f"Title: {item.get('title', '')}",
        f"Author: {item.get('author', '')}",
    ]
    if item.get("publisher"):
        ctx_lines.append(f"Publisher: {item['publisher']}")
    if item.get("publication_year"):
        ctx_lines.append(f"Year: {item['publication_year']}")
    if item.get("format"):
        ctx_lines.append(f"Format: {item['format']}")

    edition_assess = (deep_lookup.get("edition_assessment") or "").strip()
    anomaly_detail = (deep_lookup.get("anomaly_detail") or "").strip()
    sig_detail     = (deep_lookup.get("signature_detail") or "").strip()
    sources        = deep_lookup.get("sources_used") or []

    if edition_assess:
        ctx_lines.append(f"Edition findings: {edition_assess}")
    if anomaly_detail:
        ctx_lines.append(f"Notable: {anomaly_detail}")
    if sig_detail:
        ctx_lines.append(f"Signature: {sig_detail}")
    if sources:
        ctx_lines.append(f"Sources: {', '.join(sources[:3])}")

    prompt = (
        f"Book details:\n{'\n'.join(ctx_lines)}\n\n"
        f"Task: {instructions}\n\n"
        "Do not mention price. Do not repeat the condition grade — "
        "that appears separately. Do not invent facts not listed above."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_synthesis_model,   # Haiku
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = response.content[0].text.strip()

    # Enforce Amazon's plain-text limit
    if platform == "amazon" and len(narrative) > 180:
        sentences = narrative.split(". ")
        trimmed = ""
        for s in sentences:
            candidate = (trimmed + ". " + s).strip() if trimmed else s
            if len(candidate) <= 180:
                trimmed = candidate
            else:
                break
        narrative = trimmed or narrative[:180]

    return narrative


# ── Assembler ─────────────────────────────────────────────────────────────────

async def build_description(
    item: dict,
    platform: str,
    deep_lookup: dict | None = None,
) -> dict:
    """
    Build a listing description for a stock item.

    For most books (no deep lookup) this returns only the verified_facts block —
    a clean template-built condition string ready to paste. No AI call is made.

    When deep lookup found substantive findings (edition, signature, variant),
    a Haiku-generated narrative is added as a second zone for the dealer to review.

    Returns:
      verified_facts  — template zone (always present, dealer-verifiable)
      narrative       — AI-suggested zone (empty string if no deep lookup)
      has_narrative   — bool: whether a narrative zone was generated
      full_description — both zones joined (or just facts if no narrative)
      platform        — echoed back
      character_count — length of full_description
      within_limit    — whether it fits the platform's hard cap
    """
    facts     = build_verified_facts(item, deep_lookup)
    narrative = ""

    if _deep_lookup_has_content(deep_lookup):
        narrative = await build_narrative(item, platform, deep_lookup)

    separator = "\n\n" if narrative else ""
    full      = f"{facts}{separator}{narrative}".strip()

    limit   = _PLATFORM_CHAR_LIMITS.get(platform.lower(), 2000)
    in_lim  = len(full) <= limit

    if not in_lim:
        logger.warning(
            "Description for %s exceeds %s %d-char limit (%d chars). Dealer should trim.",
            item.get("gibson_sku"), platform, limit, len(full),
        )

    return {
        "verified_facts":   facts,
        "narrative":        narrative,
        "has_narrative":    bool(narrative),
        "full_description": full,
        "platform":         platform,
        "character_count":  len(full),
        "within_limit":     in_lim,
    }
