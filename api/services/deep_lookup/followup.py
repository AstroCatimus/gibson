import json
import time
import anthropic
from dataclasses import asdict
from api.config import settings
from api.services.deep_lookup.models import DeepLookupResult


async def run_followup(
    original: DeepLookupResult,
    new_photo: str,             # base64 JPEG
    research: dict,
) -> DeepLookupResult:
    start = time.monotonic()

    prompt = f"""You previously assessed this book and requested an additional photo.

Original assessment:
{json.dumps(asdict(original), indent=2)}

You requested: {original.photo_request}

The dealer has provided the requested photo above.
Update your assessment with this new information.
Return the same JSON schema as before."""

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": new_photo,
            },
        },
        {"type": "text", "text": prompt},
    ]

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_research_model,
        max_tokens=1000,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        return original  # Return original if parse fails

    return DeepLookupResult(
        anomaly_found=data.get("anomaly_found", original.anomaly_found),
        anomaly_type=data.get("anomaly_type", original.anomaly_type),
        anomaly_detail=data.get("anomaly_detail", original.anomaly_detail),
        edition_assessment=data.get("edition_assessment", original.edition_assessment),
        signature_found=data.get("signature_found", original.signature_found),
        signature_detail=data.get("signature_detail", original.signature_detail),
        baseline_value=data.get("baseline_value", original.baseline_value),
        anomaly_value_low=data.get("anomaly_value_low", original.anomaly_value_low),
        anomaly_value_high=data.get("anomaly_value_high", original.anomaly_value_high),
        confidence=data.get("confidence", original.confidence),
        dealer_action=data.get("dealer_action", original.dealer_action),
        physical_checks=data.get("physical_checks", original.physical_checks),
        sources_used=data.get("sources_used", original.sources_used),
        needs_more_photos=data.get("needs_more_photos", False),
        photo_request=data.get("photo_request"),
        stage_reached=4,
        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        elapsed_seconds=round(time.monotonic() - start, 2),
    )
