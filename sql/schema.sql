-- AZ Quiz Hub Database Schema
-- Run this against a fresh MySQL database named `quizflix`

CREATE DATABASE IF NOT EXISTS quizflix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE quizflix;

CREATE TABLE IF NOT EXISTS quizzes (
  id                  INT PRIMARY KEY AUTO_INCREMENT,
  title               VARCHAR(255) NOT NULL,
  topic               VARCHAR(100) NULL,
  intro_text          TEXT,
  outro_text          TEXT,
  youtube_title       VARCHAR(100) NULL,
  youtube_description TEXT         NULL,
  youtube_tags        TEXT         NULL,
  bg_music            VARCHAR(255),
  correct_sound       VARCHAR(255),
  background_image    VARCHAR(255),
  last_uploaded_at    TIMESTAMP NULL DEFAULT NULL,
  created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  quiz_id       INT NOT NULL,
  question_text TEXT NOT NULL,
  correct_index INT NOT NULL DEFAULT 0,
  fun_fact      TEXT,
  FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS options (
  id           INT PRIMARY KEY AUTO_INCREMENT,
  question_id  INT NOT NULL,
  option_index INT NOT NULL,
  option_text  TEXT NOT NULL,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_jobs (
  id               INT PRIMARY KEY AUTO_INCREMENT,
  quiz_id          INT NOT NULL,
  status           ENUM('pending','generating','uploading','done','failed') DEFAULT 'pending',
  video_path       VARCHAR(500),
  youtube_url      VARCHAR(500),
  youtube_video_id VARCHAR(50),
  error_message    TEXT,
  created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at     TIMESTAMP NULL DEFAULT NULL,
  FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);
