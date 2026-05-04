"""
Gibson Training Data Export.

╔══════════════════════════════════════════════════════════════════╗
║  TRAINING PIPELINE IS DISABLED                                   ║
║                                                                  ║
║  This script requires a local Ollama + Llama 3 8B server for    ║
║  QLoRA fine-tuning. That infrastructure is not set up yet.       ║
║                                                                  ║
║  To enable when ready:                                           ║
║    1. Stand up a local machine with Ollama + sufficient VRAM     ║
║    2. Set TRAINING_ENABLED=true in .env on that machine ONLY     ║
║    3. Do NOT set this on the cloud/Railway server                 ║
╚══════════════════════════════════════════════════════════════════╝

Exports confirmed identifications, corrections, and pricing decisions
as training datasets for QLoRA fine-tuning.

Three dataset types:
- Bibliographic: image + OCR text → identification (for vision model)
- Condition: image → condition grade (for condition model)
- Pricing: edition + comps → price suggestion (for pricing model)

Only rows with is_training_pair = true are included.

Usage:
    TRAINING_ENABLED=true python scripts/maintenance/training_export.py --type all
    TRAINING_ENABLED=true python scripts/maintenance/training_export.py --type bibliographic --output training/datasets/
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.config import settings
from api.database import init_pool, close_pool, fetch

logger = logging.getLogger("gibson.maintenance.training_export")

# ── Hard gate ────────────────────────────────────────────────────
if not settings.training_enabled:
    print(
        "\n"
        "  TRAINING PIPELINE IS DISABLED\n"
        "  ─────────────────────────────────────────────────────────\n"
        "  Set TRAINING_ENABLED=true in your .env to run this script.\n"
        "  This should only be done on a local machine with Ollama set up,\n"
        "  NOT on the cloud server.\n"
    )
    sys.exit(1)


async def export_training_data(data_type: str = "all", output_dir: str = "training/datasets"):
    """Export training data from confirmed Gibson operations."""
    pool = await init_pool()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        if data_type in ("all", "bibliographic"):
            await _export_bibliographic(pool, output_path)
        if data_type in ("all", "condition"):
            await _export_condition(pool, output_path)
        if data_type in ("all", "pricing"):
            await _export_pricing(pool, output_path)
    finally:
        await close_pool()


async def _export_bibliographic(pool, output_path: Path):
    """
    Export bibliographic training examples.

    Each example: {image_url, ocr_text, identified_title, identified_author,
    isbn, confidence, was_corrected, correction_details}
    """
    rows = await fetch(
        pool,
        """SELECT te.example_id, te.input_data, te.output_data,
                  te.model_prediction, te.human_correction, te.example_type
           FROM gibson_training_example te
           WHERE te.example_type = 'identification'
             AND te.human_correction IS NOT NULL
           ORDER BY te.created_at DESC
           LIMIT 10000"""
    )

    examples = []
    for row in rows:
        examples.append({
            "id": str(row["example_id"]),
            "input": row["input_data"],
            "output": row["output_data"],
            "model_prediction": row["model_prediction"],
            "human_correction": row["human_correction"],
        })

    filepath = output_path / "bibliographic" / "training_data.jsonl"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    logger.info("Exported %d bibliographic training examples to %s", len(examples), filepath)


async def _export_condition(pool, output_path: Path):
    """Export condition assessment training examples."""
    rows = await fetch(
        pool,
        """SELECT te.example_id, te.input_data, te.output_data,
                  te.model_prediction, te.human_correction
           FROM gibson_training_example te
           WHERE te.example_type = 'condition'
           ORDER BY te.created_at DESC
           LIMIT 10000"""
    )

    examples = []
    for row in rows:
        examples.append({
            "id": str(row["example_id"]),
            "input": row["input_data"],
            "output": row["output_data"],
            "correction": row["human_correction"],
        })

    filepath = output_path / "condition" / "training_data.jsonl"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    logger.info("Exported %d condition training examples to %s", len(examples), filepath)


async def _export_pricing(pool, output_path: Path):
    """Export pricing decision training examples."""
    rows = await fetch(
        pool,
        """SELECT si.stock_item_id, si.asking_price, si.cost_basis,
                  e.isbn_13, w.title,
                  c.original_value as gibson_suggested_price,
                  c.corrected_value as dealer_set_price,
                  c.field_name
           FROM gibson_correction c
           JOIN gibson_stock_item si ON c.stock_item_id = si.stock_item_id
           LEFT JOIN gibson_edition e ON si.edition_id = e.edition_id
           LEFT JOIN gibson_work w ON e.work_id = w.work_id
           WHERE c.field_name = 'asking_price'
             AND c.status = 'APPROVED'
           ORDER BY c.created_at DESC
           LIMIT 10000"""
    )

    examples = []
    for row in rows:
        examples.append({
            "isbn": row["isbn_13"],
            "title": row["title"],
            "gibson_price": float(row["gibson_suggested_price"]) if row["gibson_suggested_price"] else None,
            "dealer_price": float(row["dealer_set_price"]) if row["dealer_set_price"] else None,
        })

    filepath = output_path / "pricing" / "training_data.jsonl"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    logger.info("Exported %d pricing training examples to %s", len(examples), filepath)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gibson training data export")
    parser.add_argument("--type", choices=["all", "bibliographic", "condition", "pricing"], default="all")
    parser.add_argument("--output", default="training/datasets")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(export_training_data(args.type, args.output))
