-- Migration v2: add AI-generated YouTube metadata columns to quizzes table
-- Run once against an existing quizflix database:
--   mysql -u root quizflix < sql/migrate_v2_youtube_fields.sql

ALTER TABLE quizzes
  ADD COLUMN IF NOT EXISTS youtube_title       VARCHAR(100) NULL AFTER outro_text,
  ADD COLUMN IF NOT EXISTS youtube_description TEXT         NULL AFTER youtube_title,
  ADD COLUMN IF NOT EXISTS youtube_tags        TEXT         NULL AFTER youtube_description;
