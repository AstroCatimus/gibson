# Gibson — Bibliographic Intelligence System

**Alexandria Book Co-op** — Driftless Books & Music / Metaphysical Graffiti, Viroqua, Wisconsin

Gibson identifies books from photographs, prices them against real market data,
catalogues them into a cooperative database, and lists them for sale.

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env
# Fill in DATABASE_URL, ANTHROPIC_API_KEY, etc.

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run database migrations
psql $DATABASE_URL -f db/migrations/001_schema_core.sql
psql $DATABASE_URL -f db/migrations/002_schema_store.sql
psql $DATABASE_URL -f db/migrations/003_schema_training.sql
psql $DATABASE_URL -f db/migrations/004_schema_ghostbook.sql
psql $DATABASE_URL -f db/migrations/005_indexes.sql
psql $DATABASE_URL -f db/migrations/006_schema_store_mapping.sql
psql $DATABASE_URL -f db/migrations/007_schema_conversation.sql
psql $DATABASE_URL -f db/seeds/stores.sql

# 4. Start the API
uvicorn api.main:app --reload --port 8000

# 5. Open the PWA
open http://localhost:8000
```

## Architecture

```
Photo → OCR + Vision → Identification → Pricing → Catalogue → List for Sale
         ↓                    ↓              ↓
    EasyOCR+Paddle      Source Cascade    Vialibri Gate
    + Claude Sonnet     (100+ sources)    + eBay Sold
         ↓                    ↓              ↓
    Confidence Score    Work → Edition    SOLD/ASKING/TREND
    + Follow-up Ask     → Stock Item      → Dealer Decides
```

## Schema: Work → Edition → Stock Item (FRBR)

- **Work**: Abstract intellectual creation (title, author, subject)
- **Edition**: Specific published form (ISBN, publisher, year, format)
- **Stock Item**: Physical copy in a store (condition, price, location, SKU)

## License

Private — Alexandria Book Co-op
