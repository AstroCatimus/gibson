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

### 5. Run it — open two terminals

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
Scan the QR code with Expo Go on your phone.

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
