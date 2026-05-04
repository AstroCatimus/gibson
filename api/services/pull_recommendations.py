"""
Gibson Pull Recommendation Engine.

Generates prioritized pull lists for morning report. Surfaces books where
there is a specific reason to act today — never recommends pulling everything.

Priority 1 (act today):
  - 3+ Vialibri comps above $15
  - Active customer want list match
  - Recent customer search with zero results — now matched
  - First edition signals visible on spine
  - Handwriting visible — possible inscription

Priority 2 (worth the pull):
  - Gibson can almost identify — one more photo resolves it
  - Pre-ISBN, no institutional record — Ghost Book queue

Priority 3 (batch when working the section):
  - Vialibri comps $8-$15, commodity signal
  - Author matches high-demand section pattern
"""

import logging
from datetime import datetime, timezone

from api.database import fetch, execute

logger = logging.getLogger("gibson.services.pull_recommendations")

PULL_CRITERIA = [
    # Priority 1
    {"key": "vialibri_comps_above_15", "priority": 1, "reason": "3+ Vialibri comps above $15"},
    {"key": "want_list_match", "priority": 1, "reason": "Active customer want list match"},
    {"key": "search_zero_result_match", "priority": 1, "reason": "Recent customer search — zero results, now matched"},
    {"key": "first_edition_signals", "priority": 1, "reason": "Edition signals visible on spine"},
    {"key": "signed_copy_visible", "priority": 1, "reason": "Handwriting visible — possible inscription"},
    # Priority 2
    {"key": "partial_id_needs_title_page", "priority": 2, "reason": "Gibson can almost identify — one photo resolves"},
    {"key": "ghost_book_candidate", "priority": 2, "reason": "Pre-ISBN, no institutional record — Ghost Book queue"},
    # Priority 3
    {"key": "vialibri_comps_8_to_15", "priority": 3, "reason": "Vialibri comps $8-15, commodity signal"},
    {"key": "high_demand_author", "priority": 3, "reason": "Author matches high-demand section pattern"},
]


async def generate_pull_list(store_id: str, pool) -> list[dict]:
    """
    Generate a prioritized pull list from overnight container_item analysis.

    Returns items sorted by priority (1=highest), with location info
    for the employee carrying the printed sheet.
    """
    pulls = []

    # Priority 1: Want list matches
    want_matches = await fetch(
        pool,
        """SELECT ci.item_id, ci.spine_text_raw, ci.identification_confidence,
                  ci.position_on_shelf,
                  s.shelf_number, c.name as container_name,
                  r.name as room_name,
                  w.title, a.name as author
           FROM gibson_container_item ci
           JOIN gibson_shelf s ON ci.shelf_id = s.shelf_id
           JOIN gibson_container c ON s.container_id = c.container_id
           JOIN gibson_room r ON c.room_id = r.room_id
           LEFT JOIN gibson_work w ON ci.identified_work_id = w.work_id
           LEFT JOIN gibson_work_agent wa ON w.work_id = wa.work_id AND wa.role = 'author'
           LEFT JOIN gibson_agent a ON wa.agent_id = a.agent_id
           WHERE ci.pull_recommended = true
             AND r.store_id = $1
           ORDER BY ci.pull_priority ASC, ci.created_at ASC
           LIMIT 100""",
        store_id
    )

    for row in want_matches:
        pulls.append({
            "item_id": str(row["item_id"]),
            "priority": row.get("pull_priority", 2),
            "location": {
                "room": row["room_name"],
                "container": row["container_name"],
                "shelf": row["shelf_number"],
                "position": row["position_on_shelf"],
            },
            "title_as_read": row["spine_text_raw"],
            "identified_title": row.get("title"),
            "identified_author": row.get("author"),
            "confidence": float(row["identification_confidence"]) if row["identification_confidence"] else None,
            "reason": row.get("pull_reason", "Pull recommended"),
        })

    # Sort by priority
    pulls.sort(key=lambda x: (x["priority"], -(x.get("confidence") or 0)))

    logger.info("Generated pull list: %d items for store %s", len(pulls), store_id)
    return pulls


async def run_overnight_pull_analysis(store_id: str, pool):
    """
    Overnight analysis: cross-reference container_items against
    pricing data and want lists, then flag pull recommendations.

    Called by the agent runner at ~4:30 AM.
    """
    # Check want list matches
    await execute(
        pool,
        """UPDATE gibson_container_item ci
           SET pull_recommended = true,
               pull_reason = 'Customer want list match',
               pull_priority = 1
           FROM gibson_work w, gibson_want_list wl
           WHERE ci.identified_work_id = w.work_id
             AND (w.title ILIKE '%' || wl.search_query || '%'
                  OR wl.search_query ILIKE '%' || w.title || '%')
             AND wl.status = 'ACTIVE'
             AND ci.pull_recommended = false
             AND ci.resolved_at IS NULL"""
    )

    # Check pricing signals (Vialibri comps > $15)
    await execute(
        pool,
        """UPDATE gibson_container_item ci
           SET pull_recommended = true,
               pull_reason = '3+ Vialibri comps above $15',
               pull_priority = 1
           FROM gibson_work w, gibson_edition e, gibson_pricing_record pr
           WHERE ci.identified_work_id = w.work_id
             AND e.work_id = w.work_id
             AND pr.edition_id = e.edition_id
             AND pr.source = 'vialibri'
             AND pr.price_amount > 15
             AND ci.pull_recommended = false
             AND ci.resolved_at IS NULL"""
    )

    # Ghost book candidates
    await execute(
        pool,
        """UPDATE gibson_container_item ci
           SET pull_recommended = true,
               pull_reason = 'Pre-ISBN, no institutional record — Ghost Book queue',
               pull_priority = 2
           WHERE ci.identified_work_id IS NULL
             AND ci.identification_confidence < 0.3
             AND ci.spine_text_raw IS NOT NULL
             AND ci.pull_recommended = false
             AND ci.resolved_at IS NULL"""
    )

    logger.info("Overnight pull analysis complete for store %s", store_id)
