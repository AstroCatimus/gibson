"""
Gibson POS & Counter Flow router.

COUNTER FLOW:
1. Tap "Sale"
2. Camera opens — auto-capture on cover
3. Catalogued book: type SKU → full record, price auto-fills
   Uncatalogued: type section code + price ("K 5" = Fiction, $5.00)
4. Section code carries forward across multi-book sale
5. Next book — repeat
6. Close sale: tax, total, payment method
7. Confirm → receipt

Every book sold:
  → Realized price → pricing_record immediately (no store attribution)
  → Stock Item → SOLD
  → All listing channels synced within 15 minutes
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional
from pydantic import BaseModel

from api.dependencies import get_store_id, get_employee_id
from api.database import fetch, fetchrow, execute, get_transaction

router = APIRouter()


class SaleItemInput(BaseModel):
    stock_item_id: Optional[UUID] = None
    gibson_sku: Optional[str] = None
    section_code: Optional[str] = None
    price: float
    discount_reason: Optional[str] = None


class CreateSaleRequest(BaseModel):
    items: list[SaleItemInput]
    payment_method: str = "cash"
    customer_id: Optional[UUID] = None
    notes: Optional[str] = None


@router.post("/sale")
async def create_sale(
    request: CreateSaleRequest,
    store_id: str = Depends(get_store_id),
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """
    Close a sale. Creates sale record, updates stock items to SOLD,
    records realized prices (no store attribution on pricing_record).
    """
    async with get_transaction() as conn:
        # Calculate totals
        subtotal = sum(item.price for item in request.items)
        tax = round(subtotal * 0.055, 2)  # Wisconsin 5.5%
        total = subtotal + tax

        # Create sale record
        sale = await conn.fetchrow(
            """
            INSERT INTO gibson_sale_record (store_id, employee_id, total_amount,
                                             tax_amount, payment_method, customer_id, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING sale_id
            """,
            store_id, employee_id, total, tax,
            request.payment_method,
            str(request.customer_id) if request.customer_id else None,
            request.notes,
        )

        sale_items = []
        for item in request.items:
            # Resolve SKU to stock_item_id
            sid = str(item.stock_item_id) if item.stock_item_id else None
            if item.gibson_sku and not sid:
                row = await conn.fetchrow(
                    "SELECT stock_item_id FROM gibson_stock_item WHERE gibson_sku = $1 AND store_id = $2",
                    item.gibson_sku, store_id,
                )
                if row:
                    sid = str(row["stock_item_id"])

            if sid:
                # Create sale item
                await conn.execute(
                    """
                    INSERT INTO gibson_sale_item (sale_id, stock_item_id, asking_price,
                                                   realized_price, discount_reason)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    sale["sale_id"], sid, item.price, item.price, item.discount_reason,
                )

                # Mark stock item SOLD
                await conn.execute(
                    """
                    UPDATE gibson_stock_item SET status = 'SOLD', updated_at = now()
                    WHERE stock_item_id = $1 AND store_id = $2
                    """,
                    sid, store_id,
                )

                # Record realized price — NO store attribution
                edition_row = await conn.fetchrow(
                    "SELECT edition_id FROM gibson_stock_item WHERE stock_item_id = $1",
                    sid,
                )
                if edition_row:
                    await conn.execute(
                        """
                        INSERT INTO gibson_pricing_record (edition_id, source, price_type,
                                                            amount, condition_grade)
                        VALUES ($1, 'gibson_pos', 'realized', $2, $3)
                        """,
                        edition_row["edition_id"], item.price, None,
                    )

            sale_items.append({"stock_item_id": sid, "price": item.price})

        return {
            "sale_id": sale["sale_id"],
            "total": total,
            "tax": tax,
            "items": sale_items,
        }


@router.get("/recent")
async def recent_sales(
    store_id: str = Depends(get_store_id),
    limit: int = 20,
):
    """Recent sales for the store."""
    rows = await fetch(
        """
        SELECT sr.sale_id, sr.sale_timestamp, sr.total_amount, sr.payment_method,
               e.name as employee_name,
               (SELECT COUNT(*) FROM gibson_sale_item si WHERE si.sale_id = sr.sale_id) as item_count
        FROM gibson_sale_record sr
        LEFT JOIN gibson_employee e ON e.employee_id = sr.employee_id
        WHERE sr.store_id = $1
        ORDER BY sr.sale_timestamp DESC
        LIMIT $2
        """,
        store_id, limit,
    )
    return [dict(r) for r in rows]
