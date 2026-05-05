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
Everything below runs from inside the `gibson` folder unless noted.

### 2. Python environment
```bash
# Run from: /gibson
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment files
```bash
# Run from: /gibson
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
# Run from: /gibson
cd mobile
npm install
cd ..
```

### 5. Run it
Make sure you're in the root `gibson` folder, then:
```bash
./start.sh
```
This opens two Terminal windows automatically — one for the backend, one for Expo.
Scan the QR code with Expo Go on your phone.

Or manually if preferred — open two separate Terminal windows, both starting from the `gibson` root folder:

**Terminal 1 — backend (run from `/gibson`):**
```bash
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — mobile (run from `/gibson`):**
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

## Status

> **This is a test system running locally on Mac.** Nothing is hosted — both people run the backend on their own machine. The database (Supabase) is shared but everything else is local. Expect rough edges.

**Works:**
- Scan a barcode → identifies book, shows price
- Take a cover photo → identifies book, shows price
- Confirm → adds to inventory with SKU
- Browse and search inventory
- Multiple copies of the same book handled correctly
- New store setup + invite-based onboarding

**In progress (not working yet):**
- Import Amazon / Ka-Zam inventory files
- Pricing via BookFinder + Vialibri
- Defrag / inventory management tools
- POS / sale flow
- Research tab
- Ghost Book (overnight research for unidentified books)

**Not started yet:**
- Shelf scanner (scan a whole shelf at once)
- Whatnot show mode
- Voice assistant
- Listing to Biblio / Amazon

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
