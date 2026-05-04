"""
Gibson Shelfie / shelf scan service.
YOLOv8n spine detection → EasyOCR per spine → database match.

Color overlay:
  GREEN  = matched, location confirmed
  YELLOW = matched, location conflicts
  RED    = not in database (potential underpriced book)
  GREY   = OCR failed
"""

from typing import Optional
from api.database import fetch, fetchrow


async def process_shelf_scan(
    image_base64: str,
    store_id: str,
    container_id: Optional[str] = None,
    shelf_id: Optional[str] = None,
) -> dict:
    """
    Process a shelf photo for spine scanning.
    Returns per-spine results with color coding and overlay positions.
    """
    # Step 1: Spine detection with YOLOv8n
    spines = await _detect_spines(image_base64)

    # Step 2: OCR each spine region
    results = []
    for spine in spines:
        ocr_text = await _ocr_spine(spine["image_region"])

        # Step 3: Match against database
        match = await _match_spine_text(ocr_text, store_id)

        color = "GREY"  # Default: OCR failed
        if ocr_text:
            if match:
                if match.get("location_matches"):
                    color = "GREEN"   # Matched, location confirmed
                else:
                    color = "YELLOW"  # Matched, location conflicts
            else:
                color = "RED"        # Not in database

        results.append({
            "position": spine["position"],
            "bbox": spine["bbox"],
            "spine_text": ocr_text,
            "color": color,
            "match": match,
        })

    # Check for RED items with pricing data
    promotions = []
    for r in results:
        if r["color"] == "RED" and r.get("match"):
            # This book isn't in our database but we found pricing
            promotions.append({
                "spine_text": r["spine_text"],
                "message": f"This book has pricing data. Pull for cataloguing?",
            })

    return {
        "spine_count": len(results),
        "results": results,
        "promotions": promotions,
        "colors_summary": {
            "GREEN": sum(1 for r in results if r["color"] == "GREEN"),
            "YELLOW": sum(1 for r in results if r["color"] == "YELLOW"),
            "RED": sum(1 for r in results if r["color"] == "RED"),
            "GREY": sum(1 for r in results if r["color"] == "GREY"),
        },
    }


async def _detect_spines(image_base64: str) -> list[dict]:
    """Detect book spine regions using YOLOv8n."""
    # Placeholder — YOLOv8n model needs to be loaded
    return []


async def _ocr_spine(image_region: bytes) -> Optional[str]:
    """OCR a single spine region."""
    from api.services.ocr import run_ocr_pipeline
    result = await run_ocr_pipeline(image_region)
    return result.get("text") if result.get("confidence", 0) > 0.3 else None


async def _match_spine_text(text: Optional[str], store_id: str) -> Optional[dict]:
    """Match spine text against the Gibson database."""
    if not text:
        return None

    row = await fetchrow(
        """
        SELECT w.work_id, w.title, e.edition_id, e.isbn_13,
               a.name_display as author,
               si.stock_item_id, si.asking_price, si.status,
               l.section
        FROM gibson_work w
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_edition e ON e.work_id = w.work_id
        LEFT JOIN gibson_stock_item si ON si.edition_id = e.edition_id AND si.store_id = $2
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE w.title % $1 OR a.name_display % $1
        ORDER BY similarity(w.title, $1) DESC
        LIMIT 1
        """,
        text, store_id,
    )
    if row:
        return dict(row)
    return None
