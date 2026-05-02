-- Migration v3: remove chalk_sound, add topic column for deduplication
-- Run once against an existing quizflix database:
--   mysql -u root quizflix < sql/migrate_v3_remove_chalk_add_topic.sql

ALTER TABLE quizzes
  ADD COLUMN IF NOT EXISTS topic VARCHAR(100) NULL AFTER title,
  DROP COLUMN IF EXISTS chalk_sound;
