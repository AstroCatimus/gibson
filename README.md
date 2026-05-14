# Gibson — Bibliographic Intelligence System

**Alexandria Book Co-op** — Driftless Books & Music / Metaphysical Graffiti, Viroqua, Wisconsin

Gibson identifies books from photographs and barcodes, prices them against real market data,
catalogues them into a cooperative database, and lists them for sale.

---

## Setup on a New Machine

### Prerequisites
- Python 3.11+: https://python.org
- Node.js: https://nodejs.org
- Git: https://git-scm.com (Macs usually have it already)
- Expo Go on your phone: App Store → "Expo Go"

### 1. Clone the repo
```bash
git clone https://github.com/AstroCatimus/gibson.git
cd gibson
```
Everything below runs from inside the `gibson` folder unless noted.

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

In `mobile/.env`, set your Mac's local IP
(System Settings → Wi-Fi → Details → IP Address):
```
EXPO_PUBLIC_API_BASE_URL=http://[YOUR_IP]:8000
```

### 4. Mobile dependencies
```bash
cd mobile && npm install && cd ..
```

### 5. Run it
```bash
./start.sh
```
Opens two Terminal windows — backend and Expo. Scan the QR code with Expo Go.

Or manually:
```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2 — mobile
cd mobile && npx expo start
```

### Staying in sync
```bash
git pull          # before you start
git add -A && git commit -m "what you changed" && git push   # when done
```

---

## Status

> **Local dev only.** Database (Supabase) is shared; everything else runs on your machine.

**Working:**
- Scan barcode → identify → price → confirm → SKU created
- Take cover photo → identify → price → confirm → SKU created
- Browse and search inventory
- Multiple copies of the same edition handled correctly
- Amazon / Ka-Zam bulk import
- Defrag (shelf verification with fuzzy title match)
- Row-level security in Supabase (bib commons vs. per-store data)
- Rotating log → `logs/gibson.log` (5 MB × 5 files)

**In progress:**
- POS / sale flow
- Biblio sync
- Price refresh worker
- Import batching (60k books currently ~3–4 hrs; needs parallelism)

**Not started:**
- Shelf scanner (scan a whole shelf at once)
- Whatnot show mode
- Listing to Biblio / Amazon
- Store membership gate (get_store_id currently trusts any header)

---

## How Identification Works

```
INCOMING BOOK
├── Has barcode    → Fast Path   local DB → research agent (ISBN) → confirm
├── Cover photo    → Standard Path  Vision (Sonnet) → research agent → confirm
└── Neither        → Slow Path   placeholder created, overnight queue
```

**Fast Path (barcode):**
1. Check local DB — instant return if found
2. Miss → research agent fires: Open Library + Google Books + LOC + BooksRun + BookScouter in parallel
3. Falls back to cover photo prompt if confidence < 0.50

**Standard Path (cover photo):**
1. Claude Vision reads the cover → title / author / ISBN / year with per-field confidence
2. Research agent enriches: verifies biblio, fetches pricing
3. Results merged — research wins on any field where it has higher confidence
4. Confidence ≥ 0.85 → one-tap confirm; 0.50–0.85 → follow-up; < 0.50 → Slow Path

**Research agent tools** (max 6 calls, 5s timeout each, parallel where possible):
- Open Library (ISBN + text search)
- Google Books
- Library of Congress catalog
- BooksRun (pricing)
- BookScouter (pricing)

---

## Schema: Work → Edition → Stock Item (FRBR)

- **Work** — abstract title/author (shared across all stores)
- **Edition** — specific ISBN/publisher/year (shared across all stores)
- **Stock Item** — physical copy: condition, price, location, SKU (private per store)

Bibliographic data is cooperative — every store sees it. Inventory, pricing, and sales are store-private, enforced at the database level via Row Level Security.

---

## Logs

```bash
tail -f logs/gibson.log
```

---

## License

Private — Alexandria Book Co-op
