"""
Gibson — Stores Router
Handles store creation, discovery (by invite code), join requests,
and approval/denial of pending members.

Auth context comes from X-Employee-Id header (Supabase user UUID).
Store ownership is tracked in gibson_store_member with role = 'owner'.
"""

import secrets
import string
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.database import fetch, fetchrow, execute

router = APIRouter()


# ─── Helpers ────────────────────────────────────────────────────

def _require_user(employee_id: str):
    if not employee_id:
        raise HTTPException(status_code=401, detail="Authentication required.")


def _gen_invite_code() -> str:
    """Generate a random 6-character uppercase alphanumeric invite code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(6))


async def _require_admin(store_id: str, user_id: str):
    """Raise 403 if user is not owner or admin of the store."""
    row = await fetchrow(
        """
        SELECT role FROM gibson_store_member
         WHERE store_id = $1 AND user_id = $2 AND status = 'active'
        """,
        store_id, user_id,
    )
    if not row or row['role'] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Owner or admin access required.")
    return row['role']


# ─── Pydantic Models ─────────────────────────────────────────────

class CreateStoreBody(BaseModel):
    name: str
    address: Optional[str] = None
    prefix: str                    # 2-letter SKU prefix, e.g. "DL"

class JoinRequestBody(BaseModel):
    invite_code: str
    message: Optional[str] = None

class ReviewRequestBody(BaseModel):
    action: str                    # 'approve' | 'deny'


# ─── Routes ──────────────────────────────────────────────────────

@router.get("/mine")
async def get_my_stores(
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Return all stores where the current user is an active member,
    plus their role and the store's invite code.
    Also includes a count of pending join requests for admin/owner stores.
    """
    _require_user(x_employee_id)

    rows = await fetch(
        """
        SELECT
            s.store_id,
            s.name,
            s.prefix,
            s.address,
            s.invite_code,
            m.role,
            m.joined_at,
            (
                SELECT COUNT(*)
                FROM gibson_store_join_request r
                WHERE r.store_id = s.store_id AND r.status = 'pending'
            ) AS pending_requests
        FROM gibson_store_member m
        JOIN gibson_store s ON s.store_id = m.store_id
        WHERE m.user_id = $1 AND m.status = 'active'
        ORDER BY m.joined_at ASC
        """,
        x_employee_id,
    )

    return {"stores": [dict(r) for r in rows]}


@router.get("/lookup")
async def lookup_store_by_code(
    code: str,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Find a store by its invite code.
    Returns basic store info (no sensitive data).
    """
    _require_user(x_employee_id)

    row = await fetchrow(
        """
        SELECT store_id, name, prefix, address
        FROM gibson_store
        WHERE upper(invite_code) = upper($1)
        """,
        code.strip(),
    )

    if not row:
        raise HTTPException(status_code=404, detail="No store found with that invite code.")

    # Check if user already has a membership or pending request
    member = await fetchrow(
        "SELECT role, status FROM gibson_store_member WHERE store_id = $1 AND user_id = $2",
        str(row['store_id']), x_employee_id,
    )
    pending = await fetchrow(
        "SELECT status FROM gibson_store_join_request WHERE store_id = $1 AND user_id = $2",
        str(row['store_id']), x_employee_id,
    )

    return {
        "store_id":  str(row['store_id']),
        "name":      row['name'],
        "prefix":    row['prefix'],
        "address":   row['address'],
        "membership": dict(member) if member else None,
        "join_request": dict(pending) if pending else None,
    }


@router.post("")
async def create_store(
    body: CreateStoreBody,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Create a new store. The creator automatically becomes the owner.
    Returns the new store with its invite code.
    """
    _require_user(x_employee_id)

    prefix = body.prefix.upper().strip()
    if len(prefix) < 1 or len(prefix) > 4:
        raise HTTPException(status_code=422, detail="SKU prefix must be 1–4 letters.")

    # Generate a unique invite code
    for _ in range(10):
        code = _gen_invite_code()
        existing = await fetchrow(
            "SELECT 1 FROM gibson_store WHERE invite_code = $1", code
        )
        if not existing:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique invite code.")

    row = await fetchrow(
        """
        INSERT INTO gibson_store (name, prefix, address, invite_code, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING store_id, name, prefix, address, invite_code
        """,
        body.name.strip(), prefix, body.address, code, x_employee_id,
    )

    # Add creator as owner
    await execute(
        """
        INSERT INTO gibson_store_member (store_id, user_id, role, status)
        VALUES ($1, $2, 'owner', 'active')
        ON CONFLICT (store_id, user_id) DO NOTHING
        """,
        str(row['store_id']), x_employee_id,
    )

    return {
        "store_id":    str(row['store_id']),
        "name":        row['name'],
        "prefix":      row['prefix'],
        "address":     row['address'],
        "invite_code": row['invite_code'],
        "role":        "owner",
    }


@router.post("/{store_id}/join")
async def request_to_join(
    store_id: str,
    body: JoinRequestBody,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
    x_employee_email: str = Header(default="", alias="X-Employee-Email"),
    x_employee_name:  str = Header(default="", alias="X-Employee-Name"),
):
    """
    Submit a join request for a store.
    The store owner/admin must approve before the user becomes a member.
    """
    _require_user(x_employee_id)

    # Verify store + invite code match
    store = await fetchrow(
        "SELECT store_id, name FROM gibson_store WHERE store_id = $1 AND upper(invite_code) = upper($2)",
        store_id, body.invite_code.strip(),
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found or invite code is incorrect.")

    # Check for existing membership
    existing_member = await fetchrow(
        "SELECT role, status FROM gibson_store_member WHERE store_id = $1 AND user_id = $2",
        store_id, x_employee_id,
    )
    if existing_member and existing_member['status'] == 'active':
        raise HTTPException(status_code=409, detail="You are already a member of this store.")

    # Upsert the join request
    row = await fetchrow(
        """
        INSERT INTO gibson_store_join_request
            (store_id, user_id, user_email, user_name, message, status)
        VALUES ($1, $2, $3, $4, $5, 'pending')
        ON CONFLICT (store_id, user_id)
        DO UPDATE SET
            message    = EXCLUDED.message,
            status     = 'pending',
            created_at = now(),
            reviewed_at = NULL,
            reviewed_by = NULL
        RETURNING request_id, status, created_at
        """,
        store_id, x_employee_id,
        x_employee_email or "unknown",
        x_employee_name or None,
        body.message,
    )

    return {
        "request_id": str(row['request_id']),
        "store_id":   store_id,
        "store_name": store['name'],
        "status":     row['status'],
        "message":    "Your request has been sent. The store owner will review it shortly.",
    }


class DirectJoinBody(BaseModel):
    invite_code: str


@router.post("/{store_id}/join-direct")
async def join_store_direct(
    store_id: str,
    body: DirectJoinBody,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
    x_employee_email: str = Header(default="", alias="X-Employee-Email"),
    x_employee_name:  str = Header(default="", alias="X-Employee-Name"),
):
    """
    Join a store immediately using its invite code.
    No approval queue — the invite code IS the authorization.
    """
    _require_user(x_employee_id)

    store = await fetchrow(
        "SELECT store_id, name, prefix FROM gibson_store WHERE store_id = $1 AND upper(invite_code) = upper($2)",
        store_id, body.invite_code.strip(),
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found or invite code is incorrect.")

    # Check if already an active member
    existing = await fetchrow(
        "SELECT role, status FROM gibson_store_member WHERE store_id = $1 AND user_id = $2",
        store_id, x_employee_id,
    )
    if existing and existing['status'] == 'active':
        return {
            "store_id": store_id,
            "name":     store['name'],
            "prefix":   store['prefix'],
            "role":     existing['role'],
            "joined":   False,
            "message":  "Already a member.",
        }

    await execute(
        """
        INSERT INTO gibson_store_member (store_id, user_id, role, status)
        VALUES ($1, $2, 'employee', 'active')
        ON CONFLICT (store_id, user_id) DO UPDATE SET status = 'active'
        """,
        store_id, x_employee_id,
    )

    return {
        "store_id": store_id,
        "name":     store['name'],
        "prefix":   store['prefix'],
        "role":     "employee",
        "joined":   True,
    }


@router.get("/{store_id}/requests")
async def list_join_requests(
    store_id: str,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    List pending join requests for a store.
    Only available to owners and admins.
    """
    _require_user(x_employee_id)
    await _require_admin(store_id, x_employee_id)

    rows = await fetch(
        """
        SELECT
            request_id, user_id, user_email, user_name,
            message, status, created_at
        FROM gibson_store_join_request
        WHERE store_id = $1 AND status = 'pending'
        ORDER BY created_at ASC
        """,
        store_id,
    )

    return {"requests": [dict(r) for r in rows]}


@router.patch("/{store_id}/requests/{request_id}")
async def review_join_request(
    store_id: str,
    request_id: str,
    body: ReviewRequestBody,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Approve or deny a join request.
    Approving creates the member record. Denying marks the request denied.
    Only owners and admins can call this.
    """
    _require_user(x_employee_id)
    reviewer_role = await _require_admin(store_id, x_employee_id)

    if body.action not in ('approve', 'deny'):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'deny'.")

    # Fetch the request
    req = await fetchrow(
        """
        SELECT request_id, user_id, user_email, status
        FROM gibson_store_join_request
        WHERE request_id = $1 AND store_id = $2
        """,
        request_id, store_id,
    )
    if not req:
        raise HTTPException(status_code=404, detail="Join request not found.")
    if req['status'] != 'pending':
        raise HTTPException(status_code=409, detail=f"Request is already {req['status']}.")

    new_status = 'approved' if body.action == 'approve' else 'denied'

    await execute(
        """
        UPDATE gibson_store_join_request
           SET status = $1, reviewed_by = $2, reviewed_at = now()
         WHERE request_id = $3
        """,
        new_status, x_employee_id, request_id,
    )

    if body.action == 'approve':
        await execute(
            """
            INSERT INTO gibson_store_member (store_id, user_id, role, status)
            VALUES ($1, $2, 'employee', 'active')
            ON CONFLICT (store_id, user_id)
            DO UPDATE SET status = 'active', role = 'employee'
            """,
            store_id, req['user_id'],
        )

    return {
        "request_id": request_id,
        "status":     new_status,
        "user_email": req['user_email'],
    }


@router.get("/sections")
async def list_sections(
    x_store_id: str = Header(default="", alias="X-Store-Id"),
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """List all sections for the current store, ordered by name."""
    _require_user(x_employee_id)
    if not x_store_id:
        raise HTTPException(status_code=400, detail="X-Store-Id header required.")

    rows = await fetch(
        """
        SELECT gl.location_id, gl.section, gl.section_code, gl.floor,
               COUNT(si.stock_item_id) AS item_count
        FROM gibson_location gl
        LEFT JOIN gibson_stock_item si
               ON si.location_id = gl.location_id
        WHERE gl.store_id = $1
        GROUP BY gl.location_id, gl.section, gl.section_code, gl.floor
        ORDER BY gl.section ASC
        """,
        x_store_id,
    )
    return {"sections": [dict(r) for r in rows]}


@router.delete("/sections/{location_id}")
async def delete_section(
    location_id: str,
    x_store_id: str = Header(default="", alias="X-Store-Id"),
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Delete a section. Fails if any stock items are currently assigned to it.
    """
    _require_user(x_employee_id)

    row = await fetchrow(
        "SELECT location_id, store_id FROM gibson_location WHERE location_id = $1",
        location_id,
    )
    if not row or str(row["store_id"]) != x_store_id:
        raise HTTPException(status_code=404, detail="Section not found.")

    count = await fetchrow(
        "SELECT COUNT(*) as n FROM gibson_stock_item WHERE location_id = $1",
        location_id,
    )
    if count and count["n"] > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete — {count['n']} book(s) are in this section.",
        )

    await execute("DELETE FROM gibson_location WHERE location_id = $1", location_id)
    return {"deleted": location_id}


@router.delete("/{store_id}/members/{user_id}")
async def remove_member(
    store_id: str,
    user_id: str,
    x_employee_id: str = Header(default="", alias="X-Employee-Id"),
):
    """
    Suspend a member from a store. Only owners/admins can do this.
    An owner cannot suspend themselves.
    """
    _require_user(x_employee_id)
    await _require_admin(store_id, x_employee_id)

    if user_id == x_employee_id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")

    await execute(
        """
        UPDATE gibson_store_member
           SET status = 'suspended'
         WHERE store_id = $1 AND user_id = $2
        """,
        store_id, user_id,
    )

    return {"detail": "Member suspended."}
