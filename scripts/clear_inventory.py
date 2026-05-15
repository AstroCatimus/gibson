"""
Clear all inventory for a store.

Usage (from the gibson/ folder, venv active):
    python scripts/clear_inventory.py --store dl
    python scripts/clear_inventory.py --store mg
    python scripts/clear_inventory.py --store dl --hard   # permanent DELETE, no recovery

Default (no --hard): marks every item WITHDRAWN — preserves the audit trail.
With --hard: deletes stock items + source records permanently.
"""

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

STORE_IDS = {
    "dl": "a1b2c3d4-0001-4000-8000-000000000001",   # Driftless Books
    "mg": "a1b2c3d4-0002-4000-8000-000000000002",   # Metaphysical Graffiti
}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, choices=["dl", "mg"])
    parser.add_argument("--hard", action="store_true",
                        help="Permanently DELETE items (irreversible). Default is WITHDRAWN.")
    args = parser.parse_args()

    store_id = STORE_IDS[args.store]
    store_name = {"dl": "Driftless Books", "mg": "Metaphysical Graffiti"}[args.store]

    from api.database import fetchrow, execute, fetch, init_pool
    import api.database as db_module
    await init_pool()

    # Count first
    row = await fetchrow(
        "SELECT COUNT(*) AS cnt FROM gibson_stock_item WHERE store_id = $1 AND status != 'WITHDRAWN'",
        store_id,
    )
    count = row["cnt"]

    if count == 0:
        print(f"No active items found for {store_name}.")
        await db_module._pool.close()
        return

    action = "DELETE" if args.hard else "WITHDRAW"
    print(f"\n{'='*50}")
    print(f"Store:  {store_name}")
    print(f"Items:  {count}")
    print(f"Action: {action}")
    print(f"{'='*50}")
    confirm = input(f"\nType '{args.store.upper()}' to confirm: ").strip()
    if confirm != args.store.upper():
        print("Cancelled.")
        await db_module._pool.close()
        return

    if args.hard:
        # Delete source records first (FK constraint)
        await execute(
            """
            DELETE FROM gibson_source_record
            WHERE stock_item_id IN (
                SELECT stock_item_id FROM gibson_stock_item WHERE store_id = $1
            )
            """,
            store_id,
        )
        await execute(
            "DELETE FROM gibson_stock_item WHERE store_id = $1",
            store_id,
        )
        print(f"\n✓ Permanently deleted {count} items from {store_name}.")
    else:
        await execute(
            """
            UPDATE gibson_stock_item
            SET status = 'WITHDRAWN', updated_at = now()
            WHERE store_id = $1 AND status != 'WITHDRAWN'
            """,
            store_id,
        )
        print(f"\n✓ Withdrew {count} items from {store_name}.")
        print("  (Items are hidden from all views but preserved in the database.)")
        print("  To permanently delete, re-run with --hard.")

    await db_module._pool.close()

if __name__ == "__main__":
    asyncio.run(main())
