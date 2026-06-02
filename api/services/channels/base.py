"""
Abstract base for all Gibson marketplace platform adapters.

Each adapter implements list_item, delist_item, update_price,
get_new_orders, and refresh_token. The listings router calls these
without knowing which platform is underneath.
"""

from abc import ABC, abstractmethod
import datetime


class PlatformAdapter(ABC):

    @abstractmethod
    async def list_item(self, stock_item: dict, integration: dict) -> dict:
        """
        Push a listing to the platform.
        stock_item: enriched dict with title, author, isbn_13, condition_grade,
                    condition_notes, asking_price, images, gibson_sku, amazon_asin, etc.
        integration: row from gibson_store_integration.
        Returns: {
            platform_listing_id: str,
            platform_feed_id: str | None,   # Amazon only
            platform_item_url: str | None,
            status: 'PENDING' | 'ACTIVE',
            payload: dict,                  # full submitted payload for storage
        }
        """

    @abstractmethod
    async def delist_item(self, listing: dict, integration: dict) -> bool:
        """
        Remove a live listing.
        listing: row from gibson_listing.
        Returns True on success, False if already gone (treat as success).
        """

    @abstractmethod
    async def update_price(self, listing: dict, new_price: float, integration: dict) -> bool:
        """Update asking price on a live listing."""

    @abstractmethod
    async def get_new_orders(
        self, since: datetime.datetime, integration: dict
    ) -> list[dict]:
        """
        Poll for orders completed since `since`.
        Returns list of:
          { platform_order_id, seller_sku, sold_at, platform_listing_id }
        seller_sku maps back to gibson_stock_item.gibson_sku.
        """

    @abstractmethod
    async def refresh_token(self, integration: dict) -> dict:
        """
        Refresh the stored access token.
        Returns updated fields: { access_token, token_expires_at, refresh_token? }
        """

    async def ensure_fresh_token(self, integration: dict) -> dict:
        """
        Refresh the token if it expires within 5 minutes.
        Returns integration dict (possibly updated).
        """
        import datetime as dt
        expires = integration.get("token_expires_at")
        if expires:
            if isinstance(expires, str):
                expires = dt.datetime.fromisoformat(expires.replace("Z", "+00:00"))
            threshold = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
            if expires < threshold:
                updated = await self.refresh_token(integration)
                return {**integration, **updated}
        return integration
