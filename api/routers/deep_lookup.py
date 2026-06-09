from dataclasses import asdict
from fastapi import APIRouter
from pydantic import BaseModel
from api.services.deep_lookup.trigger import should_suggest_deep_lookup
from api.services.deep_lookup.triage import triage_collectibility
from api.services.deep_lookup.search import run_search
from api.services.deep_lookup.assess import run_assessment
from api.services.deep_lookup.followup import run_followup

router = APIRouter(prefix="/deep-lookup", tags=["deep-lookup"])


class TriggerRequest(BaseModel):
    research_result: dict

class RunRequest(BaseModel):
    research_result: dict
    photos: list[str]        # base64 JPEG strings

class FollowupRequest(BaseModel):
    original_result: dict
    new_photo: str           # base64 JPEG string
    research_result: dict


@router.post("/trigger")
async def trigger(req: TriggerRequest):
    suggest, reasons = should_suggest_deep_lookup(req.research_result)
    return {"suggest": suggest, "reasons": reasons}


@router.post("/run")
async def run(req: RunRequest):
    research = req.research_result

    # Stage 2 — triage
    proceed, reason = await triage_collectibility(research)
    if not proceed:
        return {
            "stage_reached": 2,
            "anomaly_found": False,
            "dealer_action": reason,
            "tokens_used": 0,
        }

    # Stage 3a — search
    title     = research["title"]["value"]
    author    = research["author"]["value"]
    year      = research["year"]["value"]
    publisher = research["publisher"]["value"]
    search_context = await run_search(title, author, year, publisher)

    # Stage 3b — assess
    result = await run_assessment(research, search_context, req.photos)
    return asdict(result)


@router.post("/followup")
async def followup(req: FollowupRequest):
    from api.services.deep_lookup.models import DeepLookupResult
    original = DeepLookupResult(**req.original_result)
    result = await run_followup(original, req.new_photo, req.research_result)
    return asdict(result)
