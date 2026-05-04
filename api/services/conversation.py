"""
Gibson conversational intelligence service.
Not a chatbot. A colleague who knows the store completely.

System prompt rebuilt fresh every conversation from database state:
  - Store identity, staff, date
  - Inventory summary, recent sales, dead stock
  - Store map state, pull recommendations, overnight findings
  - Pricing intelligence, market signals
  - Customer context: want lists, upcoming visits
  - Institutional memory: recent decisions
"""

from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime

from api.config import settings
from api.database import fetch, fetchrow, execute


async def process_message(
    user_id: str,
    store_id: str,
    conversation_id: Optional[UUID],
    mode: str,
    message: str,
    context_photo: Optional[str] = None,
) -> dict:
    """
    Process a conversation message.
    Ambient: 2-4 sentences max. Fast. Answer and wait.
    Deep: no limit. Gibson brings everything.
    """
    # Get or create conversation
    if not conversation_id:
        conv_row = await fetchrow(
            """
            INSERT INTO gibson_conversation (user_id, mode, full_transcript)
            VALUES ($1, $2, '[]'::jsonb)
            RETURNING conversation_id
            """,
            user_id, mode,
        )
        conversation_id = conv_row["conversation_id"]

    # Build system prompt from database state
    system_prompt = await _build_system_prompt(store_id, mode)

    # Get conversation history
    conv = await fetchrow(
        "SELECT full_transcript FROM gibson_conversation WHERE conversation_id = $1",
        str(conversation_id),
    )
    transcript = conv["full_transcript"] if conv else []

    # Add user message to transcript
    transcript.append({"role": "user", "content": message, "timestamp": datetime.now().isoformat()})

    # Call Claude
    response_text = await _call_claude(system_prompt, transcript, mode, context_photo)

    # Add response to transcript
    transcript.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})

    # Save updated transcript
    import json
    await execute(
        """
        UPDATE gibson_conversation
        SET full_transcript = $1::jsonb, updated_at = now()
        WHERE conversation_id = $2
        """,
        json.dumps(transcript), str(conversation_id),
    )

    # Detect preparation triggers
    prep_tasks = await _detect_preparation_triggers(message, conversation_id)

    # Extract decisions from deep mode
    decisions = []
    if mode == "deep":
        decisions = await _extract_decisions(message, response_text, conversation_id)

    return {
        "conversation_id": conversation_id,
        "response": response_text,
        "preparation_tasks_queued": prep_tasks,
        "decisions_logged": decisions,
        "follow_up_suggested": None,
    }


async def _build_system_prompt(store_id: str, mode: str) -> str:
    """Build system prompt from current database state."""
    parts = [
        "You are Gibson, the bibliographic intelligence system of the Alexandria Book Co-op.",
        "You are a knowledgeable colleague, not a chatbot.",
    ]

    if mode == "ambient":
        parts.append("AMBIENT MODE: Answer in 2-4 sentences maximum. Be fast, accurate, and short.")
        parts.append("Never volunteer unsolicited information. Answer the question and wait.")
    else:
        parts.append("DEEP MODE: Full conversational session. No length limit.")
        parts.append("Bring everything you know. Ask clarifying questions. Surface relevant data.")

    # Add inventory summary
    inv = await fetchrow(
        """
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE status = 'AVAILABLE') as available,
               COUNT(*) FILTER (WHERE status = 'SOLD') as sold_total
        FROM gibson_stock_item WHERE store_id = $1
        """,
        store_id,
    )
    if inv:
        parts.append(f"Inventory: {inv['total']} total items, {inv['available']} available.")

    # Add recent decisions
    decisions = await fetch(
        """
        SELECT decision_text, topic FROM gibson_conversation_decision
        WHERE status = 'ACTIVE'
        ORDER BY created_at DESC LIMIT 5
        """,
    )
    if decisions:
        parts.append("Active decisions:")
        for d in decisions:
            parts.append(f"  - [{d['topic']}] {d['decision_text']}")

    return "\n".join(parts)


async def _call_claude(
    system_prompt: str,
    transcript: list,
    mode: str,
    context_photo: Optional[str] = None,
) -> str:
    """Call Claude with the assembled context."""
    if not settings.anthropic_api_key:
        return "[Conversation API not configured — set ANTHROPIC_API_KEY]"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        messages = []
        for msg in transcript:
            messages.append({"role": msg["role"], "content": msg["content"]})

        model = settings.anthropic_vision_model if mode == "deep" else settings.anthropic_synthesis_model
        max_tokens = 4096 if mode == "deep" else 512

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )

        return response.content[0].text

    except Exception as e:
        return f"[Error communicating with Claude: {str(e)}]"


async def _detect_preparation_triggers(message: str, conversation_id: UUID) -> list:
    """
    Intent-based detection of preparation cycle triggers.
    "I'm working on X tomorrow" → queue overnight preparation.
    """
    triggers = [
        "tomorrow", "tonight", "overnight", "morning",
        "cataloguing", "cataloging", "working on",
        "learn everything about", "focus on", "ready to catalogue",
    ]

    message_lower = message.lower()
    if any(trigger in message_lower for trigger in triggers):
        # Extract subject — simplified; Claude should do this in production
        subject = message  # Placeholder
        row = await fetchrow(
            """
            INSERT INTO gibson_preparation_task (conversation_id, subject, subject_type)
            VALUES ($1, $2, 'topic')
            RETURNING task_id, subject
            """,
            str(conversation_id), subject,
        )
        if row:
            return [{"task_id": str(row["task_id"]), "subject": row["subject"]}]

    return []


async def _extract_decisions(message: str, response: str, conversation_id: UUID) -> list:
    """Extract and log decisions from deep mode conversations."""
    # Simplified — in production, Claude identifies decisions
    return []
