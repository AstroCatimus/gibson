"""
Gibson conversational intelligence router.
Not a chatbot. Not a query form. A colleague who knows the store completely.

Two modes:
  Ambient — tap microphone, get short answer (2-4 sentences), keep working
  Deep — full session, no length limit, Gibson brings everything
"""

from fastapi import APIRouter, Depends
from uuid import UUID
from typing import Optional
from pydantic import BaseModel

from api.dependencies import verify_token
from api.database import fetch, fetchrow, execute

router = APIRouter()


class ConversationMessage(BaseModel):
    conversation_id: Optional[UUID] = None
    mode: str = "ambient"  # ambient | deep
    message: str
    context_photo: Optional[str] = None  # base64 if holding a book


class ConversationResponse(BaseModel):
    conversation_id: UUID
    response: str
    preparation_tasks_queued: list = []
    decisions_logged: list = []
    follow_up_suggested: Optional[str] = None


@router.post("/message", response_model=ConversationResponse)
async def send_message(
    msg: ConversationMessage,
    claims: dict = Depends(verify_token),
):
    """
    POST /api/conversation/message
    Main conversation endpoint. Routes to ambient or deep mode.
    System prompt rebuilt fresh every conversation from database state.
    """
    from api.services.conversation import process_message

    result = await process_message(
        user_id=claims.get("user_id"),
        store_id=claims.get("store_id"),
        conversation_id=msg.conversation_id,
        mode=msg.mode,
        message=msg.message,
        context_photo=msg.context_photo,
    )
    return result


@router.get("/history")
async def conversation_history(
    claims: dict = Depends(verify_token),
    limit: int = 20,
):
    """Recent conversations for the user."""
    rows = await fetch(
        """
        SELECT conversation_id, mode, started_at, ended_at,
               title, summary, topics
        FROM gibson_conversation
        WHERE user_id = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        claims.get("user_id"), limit,
    )
    return [dict(r) for r in rows]


@router.get("/decisions")
async def active_decisions(
    topic: Optional[str] = None,
    claims: dict = Depends(verify_token),
):
    """
    All active decisions from deep mode conversations.
    Searchable institutional memory.
    "What did we decide about the pull recommendation threshold?"
    """
    if topic:
        rows = await fetch(
            """
            SELECT d.decision_id, d.decision_text, d.topic, d.status,
                   d.created_at, c.title as conversation_title
            FROM gibson_conversation_decision d
            JOIN gibson_conversation c ON c.conversation_id = d.conversation_id
            WHERE d.status = 'ACTIVE' AND d.topic ILIKE '%' || $1 || '%'
            ORDER BY d.created_at DESC
            """,
            topic,
        )
    else:
        rows = await fetch(
            """
            SELECT d.decision_id, d.decision_text, d.topic, d.status,
                   d.created_at, c.title as conversation_title
            FROM gibson_conversation_decision d
            JOIN gibson_conversation c ON c.conversation_id = d.conversation_id
            WHERE d.status = 'ACTIVE'
            ORDER BY d.created_at DESC
            """,
        )
    return [dict(r) for r in rows]


@router.get("/preparation-tasks")
async def preparation_tasks(
    status: str = "QUEUED",
):
    """Overnight preparation tasks queued from conversations."""
    rows = await fetch(
        """
        SELECT task_id, subject, subject_type, scope, status,
               queued_at, completed_at, result_summary
        FROM gibson_preparation_task
        WHERE status = $1
        ORDER BY queued_at
        """,
        status,
    )
    return [dict(r) for r in rows]
