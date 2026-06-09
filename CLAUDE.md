# CLAUDE.md — Gibson
**Alexandria Book Co-op · Gibson v2 · May 2026**

---

## Standing Decisions — Do Not Re-Litigate

| Decision | Rule |
|---|---|
| Schema | Work → Edition → Stock Item (FRBR). Originated by Mitch. |
| Source records | Immutable JSONB blobs. Never deleted, never compacted. |
| AI writes | Never directly to catalog. Human review is absolute. |
| Pricing gate | No online listing without a gate comp lookup (currently BookFinder; Vialibri sanctioned API when partnership lands). |
| Pricing paths | Field-tool and research share zero code paths. |
| Cost basis | Never leaves the owning store. Enforced at query level. |
| Dust jacket | Bibliographic object. Three-state field. Never folded into book grade. |
| Facsimile | Disclosure non-suppressible. Always prepends to listing. |
| Slash format | Never. "VG+ in VG dust jacket." Not "VG+/VG". |
| Ghost Book | First-class pipeline path. Not an edge case. |
| Conversation logger | Ships with v1, Day 1. Not a retrofit. |
| eBay Finding API | Forbidden. Decommissioned without notice. |
| AbeBooks dependency | Forbidden. Amazon-owned. |
| Every cataloguing action | Is simultaneously a listing action. |
| Every external endpoint | Configurable env var. No hardcoded URLs. |

---

## Tech Stack

**Backend:** Python 3.11+, FastAPI, asyncpg. No ORM.

**Frontend:** Expo / React Native (mobile, primary). Vanilla JS PWA (secondary). Decision on canonical frontend pending.

**Database:** PostgreSQL via Supabase (Year 1). Extensions: pg_trgm, uuid-ossp, pgvector (post-migration).

**AI (Claude API):**
- Vision + identification (fast path): `claude-haiku-4-5-20251001` (`settings.anthropic_vision_model`)
- Vision escalation (low-confidence covers): `claude-sonnet-4-6` (`settings.anthropic_vision_escalation_model`)
- Research agent: `claude-haiku-4-5-20251001` (`settings.anthropic_research_model`)
- Deep lookup triage + full assessment: Sonnet via `settings.anthropic_research_model` — set to Sonnet in env for deep lookup quality
- Opus is not wired. Add it as an explicit escalation path with its own env var when warranted.
- Prompt caching active on all calls. Batch API for async workloads.

**Code rules:**
- Every DB query touching Stock Item includes `store_id` filter.
- Every API call: retry logic, timeout, graceful degradation.
- Every correction logged as an audit trail.
- Every conversation logged in full (multi-turn schema).

---

## Data Model

**Core hierarchy:**
```
Work → Edition → Stock Item → Sale
                            → Location
                            → Photographs
                            → Condition Q&A Log
                → Source Records (immutable, per-edition)
```

**Key invariants:**
- `source_record`: every external API response, Claude Vision output, MARC record preserved as JSONB. `correction_of`, `correction_reason` fields required.
- `pricing_record`: NO `store_id` column by design. Cooperative privacy enforced at schema level.
- `stock_item.cost_basis_at_acquisition`: only queryable from owning store dashboard.
- SKU format: `{employee_initials}-{seq}` e.g. `KK-3412`. Global sequence, never reissued. Bulk imports use `IMP-{seq}`.

**Employees / initials:** JS (Jill), KK (Kim), CM (Cameron), NV (Nova), EN (Eddy).

**Two stores:** Driftless Books (DL), Metaphysical Graffiti (MG). Same DB, same API, `store_id` on every request.

---

## Identification Pipeline

```
INCOMING BOOK
├── Has barcode         → FAST PATH    sub-second, BooksRun + DB, no Claude
├── Hand-priced < $15   → TRIAGE PATH  ~1.5s, Haiku, "shelf it / research it"
├── Cover legible       → STANDARD PATH  5–6s, Sonnet, cover-first protocol
└── None of above       → SLOW PATH    overnight, placeholder created, dealer not blocked
```

**Fast Path:** DB lookup + BooksRun fire simultaneously. Never touches Claude.

**Standard Path — cover-first:**
1. One cover photo → Sonnet returns structured JSON with per-field confidence
2. If overall confidence ≥ 0.85 and gap to second candidate ≥ 0.15 → auto-accept
3. If 0.60–0.85 → Gibson asks one targeted follow-up ("Can I see the copyright page?")
4. If < 0.60 after follow-up → dealer picks candidate or routes to Slow Path

**Slow Path:** Placeholder `PENDING_RESEARCH` created immediately. Overnight research agent runs. Results → human review queue. Agent never writes directly to catalog.

---

## Pricing

**Display order:** Realized (Gibson POS, eBay sold, auction) → Asking (Vialibri, eBay active, BookScouter) → Trend → Gibson Suggests → Your Price (editable).

**Vialibri gate:**
- Comps found → proceed to listing
- No comps → three options: price $3 in-store only / queue overnight / list anyway (logged as `priced_without_comps = true`)

**Dealer price is always final.** Gibson warns if > 40% below market. Never blocks.

**Cost basis warnings:** surface if listing < cost basis, or if > 5× cost basis.

---

## Condition System

**Tap Mode** (< $15, first floor, triage-routed): Single row picker. `Fine / VG+ / VG / Good / Reading Copy`. Under 2 seconds.

**Q&A Mode** (≥ $15, online listing): 7 questions one at a time.

| Q | Subject |
|---|---|
| Q1 | Writing / stamps / marks |
| Q2 | Binding feel |
| Q3 | Cover and boards wear |
| Q4 | Pages: foxing, tanning, water |
| Q5 | Dust jacket — **three-state** |
| Q6 | Missing pages / plates |
| Q7 | Overall grade (Gibson-suggested, dealer overrides) |

**Q5 three states (non-negotiable):**
- `Yes, complete` → fires Q5a (jacket grade), Q5b (price on jacket if pre-1970), Q5c (sleeve + facsimile check)
- `No — issued without` → `jacket_present = 'absent_expected'`
- `No — unknown if issued` → `jacket_present = 'absent_unknown'`

**Listing format:** `"Very Good+ in Very Good dust jacket."` Never slash.

---

## Cooperative Data Governance

**Every member sees:** Full bibliographic commons (Work, Edition, Agent). Realized prices in aggregate, no attribution. Collective copy counts (numbers only).

**No member sees:** Another member's cost basis, asking prices pre-listing, inventory details, sales data, correction history.

**Enforcement:** At DB query level, not application logic.
- Every Stock Item query: `store_id` filter required.
- `pricing_record`: no `store_id` column. Attribution structurally impossible.
- Audit log records cross-member data access (aggregate only, no member detail).

---

## Environment Variables

```bash
DATABASE_URL=
DATABASE_POOL_SIZE=10

ANTHROPIC_API_KEY=
ANTHROPIC_API_BASE=https://api.anthropic.com
ANTHROPIC_VISION_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_VISION_ESCALATION_MODEL=claude-sonnet-4-6
ANTHROPIC_SYNTHESIS_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_RESEARCH_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_ENABLE_BATCH=true
ANTHROPIC_PROMPT_CACHE=true

BOOKSRUN_API_KEY=
BOOKSCOUTER_API_KEY=
VIALIBRI_API_KEY=
EBAY_APP_ID=
EBAY_CERT_ID=
EBAY_DEV_ID=
BIBLIO_API_KEY=
WHATNOT_API_KEY=

LOCAL_IMAGE_PATH=/data/images    # dev fallback — production uses Supabase Storage (bucket: gibson-images)

STORE_DL_ID=
STORE_MG_ID=

FAST_PATH_AUTO_ACCEPT=0.90
STANDARD_PATH_AUTO_ACCEPT=0.85
STANDARD_PATH_FOLLOWUP_THRESHOLD=0.60
SLOW_PATH_FALLBACK_THRESHOLD=0.50

VIALIBRI_GATE_ENFORCE=true
PRICING_BELOW_COST_WARN=true
CONVERSATION_LOGGER=true
```

---

## Current Status (May 2026)

**Working:** Supabase + all migrations, `./start.sh`, Expo mobile app, API routing, logging (`logs/gibson.log`).

**Built / in dev (not tested on real data):** Amazon + Ka-Zam import, defrag shelf verification, identification endpoints, ghostbook router, deep lookup pipeline (Serper + Sonnet).

**Not started / stub:** Biblio sync, price refresh worker, dust jacket schema migration, store membership gate (`get_store_id` trusts any header — blocker before external members).

**Research agent (`agent/research.py`) is live and central** to both fast path (barcode miss) and standard path (cover photo). It runs parallel tool calls with hard timeouts, prompt caching, structured output with per-field confidence, and routes to GHOST_BOOK when no institutional record is found. It never writes to the catalogue — returns a result for human confirmation only.

**Local-first ML deferred:** The local LLM training pipeline (qlora) is empty stubs as of migration 015. Inference is Claude API + cloud for the bridge period. Deferred to the August–September hardware window. Member data portability is preserved by construction in the meantime — no training data is held outside the co-op's own DB.

**Known gaps:**
- Import is sequential — 60k books ≈ 3–4 hours. Needs batching.
- Store isolation enforced by header trust only — `get_store_id` accepts any `X-Store-Id` header and falls back to Driftless. RLS in migration 013 is inert because the API connects as the service role, which bypasses RLS by design. Must be fixed before any store other than Driftless uses this system.
- Ghost Book `/confirm` and Catalogue `/confirm` are stubs — they return 200 without writing anything. Do not wire UI to them.
- No canonical frontend decision yet (Expo vs PWA).

---

*The real test: Eddy picks up a book in the warehouse. Does Gibson make his day easier?*
