import json
import time
import anthropic
from dataclasses import asdict
from api.config import settings
from api.services.deep_lookup.models import DeepLookupResult

# Internal fields that mean nothing to Sonnet — strip before sending
_METADATA_FIELDS = {"stage_reached", "tokens_used", "elapsed_seconds"}

FOLLOWUP_SYSTEM = """You are a rare book specialist. You previously assessed a book and requested
an additional photograph to resolve an uncertainty. The dealer has now provided that photo.

Review the photo in context of your original assessment and update your findings.
Return the same JSON schema as the original assessment — all fields required."""


async def run_followup(
    original: DeepLookupResult,
    new_photo: str,             # base64 JPEG
    research: dict,
) -> DeepLookupResult:
    start = time.monotonic()

    # Strip internal tracking fields — Sonnet doesn't need them and they waste tokens
    original_dict = {
        k: v for k, v in asdict(original).items()
        if k not in _METADATA_FIELDS
    }

    context_text = (
        f"Your original assessment:\n{json.dumps(original_dict, indent=2)}\n\n"
        f"You requested: {original.photo_request}\n\n"
        "The dealer has provided the requested photo. "
        "Update your assessment with this new information."
    )

    # Order: context text → image → nothing else needed
    # Sonnet reads the prior assessment before interpreting the new photo
    user_content = [
        {"type": "text", "text": context_text},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": new_photo,
            },
        },
    ]

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_deep_lookup_model,   # Sonnet — same model as initial assessment
        max_tokens=1000,
        system=[
            {
                "type": "text",
                "text": FOLLOWUP_SYSTEM,
                "cache_control": {"type": "ephemeral"},
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
        return original  # Return original on parse failure — don't regress

    return DeepLookupResult(
        anomaly_found=data.get("anomaly_found",       original.anomaly_found),
        anomaly_type=data.get("anomaly_type",         original.anomaly_type),
        anomaly_detail=data.get("anomaly_detail",     original.anomaly_detail),
        edition_assessment=data.get("edition_assessment", original.edition_assessment),
        signature_found=data.get("signature_found",   original.signature_found),
        signature_detail=data.get("signature_detail", original.signature_detail),
        baseline_value=data.get("baseline_value",     original.baseline_value),
        anomaly_value_low=data.get("anomaly_value_low",   original.anomaly_value_low),
        anomaly_value_high=data.get("anomaly_value_high", original.anomaly_value_high),
        confidence=data.get("confidence",             original.confidence),
        dealer_action=data.get("dealer_action",       original.dealer_action),
        physical_checks=data.get("physical_checks",   original.physical_checks),
        sources_used=data.get("sources_used",         original.sources_used),
        needs_more_photos=data.get("needs_more_photos", False),
        photo_request=data.get("photo_request"),
        stage_reached=4,
        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        elapsed_seconds=round(time.monotonic() - start, 2),
    )
