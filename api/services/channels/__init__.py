from api.services.channels.base import PlatformAdapter
from api.services.channels.amazon import AmazonAdapter
from api.services.channels.ebay import EbayAdapter


def get_adapter(platform: str) -> PlatformAdapter:
    if platform == "amazon":
        return AmazonAdapter()
    if platform == "ebay":
        return EbayAdapter()
    raise ValueError(f"No adapter for platform: {platform}")
