# Gibson — Bibliographic Intelligence System

**Alexandria Book Co-op** — Driftless Books & Music / Metaphysical Graffiti, Viroqua, Wisconsin

Gibson identifies books from photographs and barcodes, prices them against real market data,
catalogues them into a cooperative database, and lists them for sale across multiple marketplaces.

---

## Setup on a New Machine

### Prerequisites
- Python 3.11+: https://python.org
- Node.js: https://nodejs.org
- Git: https://git-scm.com (Macs usually have it already)
- Expo Go on your phone: App Store → "Expo Go"

### 1. Clone the repo
Open **Terminal** (Applications → Utilities → Terminal), then run:
```bash
git clone https://github.com/AstroCatimus/gibson.git
cd gibson
```
All commands from here on are run inside the `gibson` folder in Terminal, unless noted.

### 2. Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment files
```bash
cp .env.example .env
cp mobile/.env.example mobile/.env
```
Fill both files with the credentials from Nova.

In `mobile/.env`, set your Mac's local IP — find it under
System Settings → Wi-Fi → Details → IP Address:
```
EXPO_PUBLIC_API_BASE_URL=http://[YOUR_IP]:8000
```
You'll need to update this whenever your IP changes (usually after rejoining Wi-Fi).

### 4. Mobile dependencies
```bash
cd mobile && npm install && cd ..
```

### 5. Database migrations
Run each migration file in order in the **Supabase SQL editor**
(supabase.com → your project → SQL Editor):
```
db/migrations/001_schema_core.sql  through  016_marketplace.sql
```
Only run migrations you haven't run before. They are numbered and immutable — never edit an existing migration file.

### 6. Run it
Still in the `gibson` folder in Terminal:
```bash
./start.sh
```
This opens two Terminal windows automatically — one for the backend, one for Expo.
Scan the QR code that appears with the **Expo Go** app on your phone.

> **If `./start.sh` says "permission denied"**, run this once to fix it:
> ```bash
> chmod +x start.sh
> ```

To run manually instead:
```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2 — mobile (new Terminal window)
cd gibson/mobile && npx expo start
```

### Staying in sync
```bash
# Before you start work each day:
git pull

# When done:
git add -A && git commit -m "what you changed" && git push
```

---

## Status

> **Local dev only.** Database (Supabase) is shared; everything else runs on your machine.

**Working:**
- Scan barcode → identify → price → confirm → SKU created
- Take cover photo → identify → price → confirm → SKU created
- Publisher extracted and saved during scan and import
- Condition notes extracted from Amazon/Ka-Zam imports, editable per copy
- Browse inventory with filters (condition, status, section, unpriced), sort, and store switcher
- Tap any book to edit price, condition, section, status, notes, signed/inscribed, photos
- Add condition photos from camera or library — stored in Supabase Storage
- Amazon / Ka-Zam bulk import (re-uploading backfills publisher + condition notes without duplicates)
- Defrag (shelf verification with fuzzy title match)
- Row-level security in Supabase (bib commons vs. per-store data)
- Rotating log → `logs/gibson.log` (5 MB × 5 files)
- Marketplace infrastructure: eBay and Amazon adapters, OAuth connect flows, order sync worker

**In progress / ready but needs credentials:**
- eBay listing (adapter built, needs eBay developer account + OAuth credentials)
- Amazon listing (adapter built, needs SP-API developer app + LWA credentials)
- "List Online" mobile UI (backend done, mobile flow not yet built)

**Not started:**
- POS / sale flow
- Biblio sync
- Price refresh worker
- Shelf scanner (scan a whole shelf at once)
- Whatnot show mode
- Store membership gate (`get_store_id` currently trusts any header — blocker before external stores)
- Own website / storefront

---

## How Identification Works

```
INCOMING BOOK
├── Has barcode    → Fast Path    local DB → research agent (ISBN) → confirm
├── Cover photo    → Standard Path   Vision (Sonnet) → research agent → confirm
└── Neither        → Slow Path    placeholder created, overnight queue
```

**Fast Path (barcode):**
1. Check local DB — instant return if found
2. Miss → research agent: Open Library + LOC + BooksRun in parallel
3. Falls back to cover photo prompt if confidence < 0.50

**Standard Path (cover photo):**
1. Claude Vision reads the cover → title / author / ISBN / year with per-field confidence
2. Research agent enriches: verifies biblio, fetches pricing
3. Results merged — research wins on any field where it has higher confidence
4. Confidence ≥ 0.85 → one-tap confirm; 0.50–0.85 → follow-up; < 0.50 → Slow Path

---

## How Marketplace Listing Works

Each store connects its own Amazon and eBay seller accounts via OAuth in Settings.
Credentials are stored per-store — stores are fully isolated from each other.

**Listing flow (manual):**
1. Dealer opens a book in inventory → "List Online"
2. Selects platforms (eBay, Amazon, or both)
3. Reviews auto-generated draft (title, condition, description, price)
4. Publishes — Gibson pushes to selected platforms simultaneously

**When a book sells:**
- Platform sends a webhook or the order sync worker (runs every 2 min) catches it
- Gibson marks the stock item SOLD
- Delistings fire automatically on all other platforms

**Amazon notes:**
- Uses `JSON_LISTINGS_FEED` (not Listings Items API directly) — required because of
  a known Amazon bug where `condition_note` is silently dropped via the direct API
- After feed completes, Gibson verifies `condition_note` persisted via `getListingsItem`
- If it didn't save, listing is flagged `NEEDS_REVIEW` with instructions to fix in Seller Central

**eBay notes:**
- At least one photo is required per listing — books without photos cannot be listed on eBay
- Business policies (shipping, payment, return) must be configured once per seller account
  during the eBay connect flow in Settings

**Required env vars for marketplace (add to `.env` when you have credentials):**
```
AMAZON_LWA_CLIENT_ID=
AMAZON_LWA_CLIENT_SECRET=
EBAY_RU_NAME=
```

---

## Schema: Work → Edition → Stock Item (FRBR)

- **Work** — abstract title/author (shared across all stores)
- **Edition** — specific ISBN/publisher/year (shared across all stores)
- **Stock Item** — physical copy: condition, price, location, SKU (private per store)

Bibliographic data is cooperative — every store sees it.
Inventory, pricing, and sales are store-private, enforced at the database level via Row Level Security.

**Key invariants:**
- Every Stock Item query includes `store_id` filter. No exceptions.
- Cost basis never leaves the owning store.
- AI never writes directly to catalogue — human review is required.
- Migrations are immutable history — never edit an existing migration file.

---

## Logs

```bash
tail -f logs/gibson.log
```

---

## License

Private — Alexandria Book Co-op
