import json
import time
import anthropic
from api.config import settings
from api.services.deep_lookup.models import DeepLookupResult

# Max photos passed to Sonnet. Cover + title page + copyright page + colophon
# is enough for any real assessment. Beyond that you're paying for noise.
MAX_PHOTOS = 4

# Static system prompt — Sonnet sees this on every assessment call.
# Marked for prompt caching: the instructions never change, only the
# search context and photos do. Cache TTL is 5 minutes.
ASSESSMENT_SYSTEM = """You are a rare book specialist assessing a physical copy for anomalous value.

The dealer has photographed this copy. Search results and market data are in the user message above the photos.

Assess IN ORDER. Stop and flag immediately if you find something significant:

1. SIGNATURE CHECK
   - Is there handwriting visible in any photo?
   - If yes: whose? Where (title page, half-title, limitation page, colophon)?
   - Is it a full signature, inscription ("To John, with warmth"), or association copy?
   - Does it appear authentic or like a facsimile/bookplate?

2. EDITION IDENTIFICATION
   - What edition is this? First, later, book club, reprint, advance copy?
   - What physical points confirm this? (Look at copyright page, colophon, binding)
   - Are there known issue points for this title? Do the photos confirm or deny them?

3. CONDITION FACTORS
   - Is a dust jacket present? Condition if visible?
   - Any visible damage, restoration, or notable preservation?

4. MARKET ASSESSMENT
   - Based on the search results AND your training knowledge:
     What is the realistic value range for this specific copy?
   - What is the baseline value for a standard copy?
   - What premium does this copy warrant and why?

5. PHYSICAL VERIFICATION
   - What should the dealer physically check that photos don't show clearly?
   - Be specific: "Check copyright page for the words First Edition"
     not "verify the edition"

Return ONLY this JSON with no other text:
{
  "anomaly_found": true | false,
  "anomaly_type": "SIGNED" | "FIRST_EDITION" | "VARIANT" | "ASSOCIATION" | "MULTIPLE" | null,
  "anomaly_detail": str | null,
  "edition_assessment": str,
  "signature_found": true | false,
  "signature_detail": str | null,
  "baseline_value": float | null,
  "anomaly_value_low": float | null,
  "anomaly_value_high": float | null,
  "confidence": 0.0-1.0,
  "dealer_action": str,
  "physical_checks": [str],
  "sources_used": [str],
  "needs_more_photos": true | false,
  "photo_request": str | null
}

dealer_action: one clear sentence telling the dealer what to do right now.
physical_checks: specific things to verify on the physical copy.
photo_request: only populate if needs_more_photos is true — exactly which page/area to photograph."""


async def run_assessment(
    research: dict,
    search_context: str,
    photos: list[str],          # list of base64-encoded JPEG strings
) -> DeepLookupResult:
    start = time.monotonic()

    # Cap photos — cover + title page + copyright page + colophon is sufficient
    if len(photos) > MAX_PHOTOS:
        photos = photos[:MAX_PHOTOS]

    # User message: search context first, then photos
    # Context before images so Sonnet reads the data before interpreting the photos
    user_content = [
        {
            "type": "text",
            "text": search_context,
        }
    ]

    for photo_b64 in photos:
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": photo_b64,
            },
        })

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_deep_lookup_model,   # Sonnet — Haiku lacks rare book knowledge
        max_tokens=1000,
        system=[
            {
                "type": "text",
                "text": ASSESSMENT_SYSTEM,
                "cache_control": {"type": "ephemeral"},  # static prompt — cache it
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    text = response.content[0].text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        return DeepLookupResult(
            anomaly_found=False,
            anomaly_type=None,
            anomaly_detail="Assessment parse failed — manual review recommended",
            edition_assessment="Unable to assess",
            signature_found=False,
            signature_detail=None,
            baseline_value=None,
            anomaly_value_low=None,
            anomaly_value_high=None,
            confidence=0.0,
            dealer_action="Assessment failed. Please retry or consult a specialist.",
            physical_checks=[],
            sources_used=[],
            needs_more_photos=False,
            photo_request=None,
            stage_reached=3,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            elapsed_seconds=round(time.monotonic() - start, 2),
        )

    return DeepLookupResult(
        anomaly_found=data.get("anomaly_found", False),
        anomaly_type=data.get("anomaly_type"),
        anomaly_detail=data.get("anomaly_detail"),
        edition_assessment=data.get("edition_assessment", ""),
        signature_found=data.get("signature_found", False),
        signature_detail=data.get("signature_detail"),
        baseline_value=data.get("baseline_value"),
        anomaly_value_low=data.get("anomaly_value_low"),
        anomaly_value_high=data.get("anomaly_value_high"),
        confidence=data.get("confidence", 0.0),
        dealer_action=data.get("dealer_action", ""),
        physical_checks=data.get("physical_checks", []),
        sources_used=data.get("sources_used", []),
        needs_more_photos=data.get("needs_more_photos", False),
        photo_request=data.get("photo_request"),
        stage_reached=3,
        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        elapsed_seconds=round(time.monotonic() - start, 2),
    )
