# CLAUDE.md — Gibson Build Instructions
# Alexandria Book Co-op
# Last updated: April 2026

This file is the authoritative instruction set for building Gibson.
Read it completely before writing a single line of code.

---

## What Gibson Is

Gibson is the bibliographic intelligence system of the Alexandria Book Co-op.
Its job, in order of priority: identify a book from a photograph, price it
against real market data, catalogue it into a cooperative database, and list
it for sale.

Gibson is a field tool first. Everything else is built on top of a working
field tool. Build the field tool first.

Gibson always has an opinion. It reads what it can see, makes the most informed
recommendation it can, shows its reasoning, and asks the dealer to confirm or
override with one tap.

---

## Tech Stack

- **Backend:** Python / FastAPI
- **Frontend:** Progressive Web App (vanilla JS, no framework)
- **Database:** PostgreSQL via Supabase (raw SQL migrations only — no ORM)
- **Vision / AI:** Anthropic API (Sonnet for identification, Haiku for synthesis)
- **Local LLM (post-migration):** Ollama + Llama 3 8B
- **Deployment:** Cloud-first (Supabase + Railway + Cloudflare R2)

This is not a prototype. Write production code from Day 1.

---

## The Two Stores

**Driftless Books & Music** — 518 Walnut Street, Viroqua, WI 54665
- ~100,000 uncatalogued + ~250,000 upstairs. SKU prefix: DL-

**Metaphysical Graffiti** — 1919-era storefront, Viroqua
- Fully uncatalogued, pencil-priced. SKU prefix: MG-

Both stores share one database, one API. Store context via JWT claim.

---

## Standing Decisions — Do Not Relitigate

- Local-first is the destination. Cloud is the starting point.
- Work → Edition → Stock Item is the schema (FRBR-aligned).
- Publisher and Agent are entity tables with authority record support.
- Confidence scores are always visible.
- The research agent never writes directly to the catalog.
- Vialibri is the pricing gate.
- Gibson always prompts the logical choice. One tap.
- Ghost Book is a first-class pipeline path.
- Raw SQL migrations only. No ORM.
- Pricing is Day 1. Not Month 7.

---

## Development Commands

```bash
# Backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Database migrations (via psql against Supabase)
psql $DATABASE_URL -f db/migrations/001_schema_core.sql

# Docker local dev
docker-compose up -d

# Run tests
pytest api/tests/
```

---

## Repository Layout

```
gibson/
├── CLAUDE.md
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── routers/            # Route handlers
│   ├── services/           # Business logic
│   └── models/             # Pydantic schemas
├── pwa/                    # Progressive Web App
│   ├── index.html
│   ├── manifest.json
│   ├── service-worker.js
│   └── src/views/          # View modules
├── db/
│   ├── migrations/         # Raw SQL, sequential
│   └── seeds/              # Store + section data
├── agent/                  # Overnight research agent
│   ├── source_cascade.yaml
│   └── sources/            # Per-source scrapers
├── scripts/                # Ingest + maintenance
└── training/               # QLoRA datasets + eval
```

---

## Key Rules

- Every Stock Item query includes store_id filter. No exceptions.
- Cost basis never exposed outside owning store.
- AI output never writes directly to catalog without human review.
- Confidence scores in every API response.
- Every environment variable documented in .env.example before use.
