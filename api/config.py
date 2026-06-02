"""
Gibson configuration — all settings from environment variables.
Every variable documented in .env.example before use here.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://gibson:gibson_dev@localhost:5432/gibson"
    database_pool_size: int = 10
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    # Haiku handles the fast path (barcode + easy covers). Sonnet is the
    # escalation fallback for low-confidence vision results only (<0.60).
    anthropic_vision_model: str = "claude-haiku-4-5-20251001"
    anthropic_vision_escalation_model: str = "claude-sonnet-4-6"
    anthropic_synthesis_model: str = "claude-haiku-4-5-20251001"
    anthropic_research_model: str = "claude-haiku-4-5-20251001"  # escalate to sonnet for hard cases
    # Confidence threshold below which vision escalates from Haiku → Sonnet
    vision_escalation_threshold: float = 0.60

    # Pricing
    booksrun_api_key: str = ""
    booksrun_affiliate_id: str = ""
    bookscouter_api_key: str = ""
    vialibri_base_url: str = "https://www.vialibri.net"
    ebay_app_id: str = ""
    ebay_cert_id: str = ""
    ebay_dev_id: str = ""

    # Channels
    biblio_api_key: str = ""
    whatnot_api_key: str = ""

    # eBay Sell APIs (ebay_app_id = client_id, ebay_cert_id = client_secret)
    ebay_ru_name: str = ""            # RuName registered in eBay developer console
    ebay_environment: str = "production"  # 'production' or 'sandbox'

    # Amazon SP-API — Login with Amazon (LWA) OAuth credentials
    # Separate from the eBay creds; registered in SP-API developer console
    amazon_lwa_client_id: str = ""
    amazon_lwa_client_secret: str = ""
    amazon_marketplace_id: str = "ATVPDKIKX0DER"  # US marketplace

    # Image storage (Supabase Storage — bucket: gibson-images)
    local_image_path: str = "/data/images"

    # Notifications
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # Store IDs (set after seeding)
    store_dl_id: str = "a1b2c3d4-0001-4000-8000-000000000001"
    store_mg_id: str = "a1b2c3d4-0002-4000-8000-000000000002"
    dl_store_id: str = "a1b2c3d4-0001-4000-8000-000000000001"
    mg_store_id: str = "a1b2c3d4-0002-4000-8000-000000000002"
    default_store_id: str = "a1b2c3d4-0001-4000-8000-000000000001"

    # Feature flags
    shelfie_enabled: bool = False
    agent_enabled: bool = False
    whatnot_live_camera: bool = False
    bookfinder_enabled: bool = True

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    allowed_origins: str = "http://localhost:8000,http://localhost:3000"
    jwt_secret: str = ""
    debug: bool = False
    api_secret_key: str = "change-this-in-production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()


def get_settings() -> Settings:
    """Return the global settings singleton. Exists for agent/script compatibility."""
    return settings
