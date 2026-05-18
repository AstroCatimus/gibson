-- Gibson Migration 015: Remove local LLM training pipeline
-- ─────────────────────────────────────────────────────────────────
-- The Ollama / local fine-tuning plan has been dropped.
-- Gibson uses the Claude API exclusively (Year 1 and beyond).
--
-- gibson_correction stays — it's a useful audit trail regardless of training.
-- gibson_conversation stays — it's a standing architectural decision.
--
-- Run this in the Supabase SQL editor.
-- ─────────────────────────────────────────────────────────────────

-- Drop training examples table (was collecting fine-tuning data for Ollama)
DROP TABLE IF EXISTS gibson_training_example;

-- Remove the training-specific column from corrections
ALTER TABLE gibson_correction DROP COLUMN IF EXISTS is_training_pair;
ALTER TABLE gibson_correction DROP COLUMN IF EXISTS reviewed_by;
