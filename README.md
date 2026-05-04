# Gibson — Bibliographic Intelligence System

**Alexandria Book Co-op** — Driftless Books & Music / Metaphysical Graffiti, Viroqua, Wisconsin

Gibson identifies books from photographs, prices them against real market data,
catalogues them into a cooperative database, and lists them for sale.

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
Fill both files in with the credentials from Nova.

In `mobile/.env`, update this line to your Mac's local IP
(find it: System Settings → Wi-Fi → Details → IP Address):
```
EXPO_PUBLIC_API_BASE_URL=http://[YOUR_IP]:8000
```

### 4. Mobile dependencies
```bash
cd mobile
npm install
cd ..
```

### 5. Run it
```bash
./start.sh
```
This opens two Terminal windows automatically — one for the backend, one for Expo.
Scan the QR code with Expo Go on your phone.

Or manually if preferred:

**Terminal 1 — backend:**
```bash
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — mobile:**
```bash
cd mobile
npx expo start
```

### Staying in sync
Pull changes from the other person before you start working:
```bash
git pull
```
Push your changes when done:
```bash
git add -A
git commit -m "describe what you changed"
git push
```
The backend auto-reloads when you pull new code (`--reload` flag handles it).

## What Works Right Now

**✅ Fully working:**
- Barcode scanning → instant identification via local DB + Open Library
- Cover photo identification (Claude Vision + OCR)
- Pricing (BooksRun, BookFinder, Vialibri)
- Confirm book → creates Work/Edition/Stock Item with SKU
- Inventory tab — browse, search, filter by section
- Defrag tab — export inventory, import Amazon TSV + Ka-Zam TSV (background job with progress bar)
- Multi-copy picker — if you scan a book with 2+ copies in stock, shows a picker
- Onboarding — create a new store or join an existing one with an invite code
- Login / signup

**🚧 Built but not wired up yet:**
- POS / sale flow (router exists, mobile tab exists, not connected end to end)
- Research tab (skeleton only)
- Ghost Book pipeline (overnight research agent — logic written, not triggered from mobile)

**📋 Planned, not started:**
- Shelfie / shelf scan (YOLO spine detection)
- Whatnot show mode
- Conversation / ambient voice mode
- Local LLM (Ollama) — cloud Anthropic API only for now
- Cloudflare R2 image storage — photos currently stored as base64
- eBay, BooksCouter pricing — need API keys
- Biblio, Amazon SP listing channels

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
