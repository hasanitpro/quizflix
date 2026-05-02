-- Migration v5: add real-time progress columns to video_jobs
ALTER TABLE video_jobs
  ADD COLUMN IF NOT EXISTS progress       TINYINT UNSIGNED NOT NULL DEFAULT 0  AFTER status,
  ADD COLUMN IF NOT EXISTS progress_label VARCHAR(200)     NULL                 AFTER progress;
