-- Align stg_dukes_chapter1_sup with chapter 4/5 staging (value_text for non-numeric cells).
ALTER TABLE stg_dukes_chapter1_sup ADD COLUMN IF NOT EXISTS value_text TEXT;
