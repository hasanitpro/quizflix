"""
run_daily.py  —  AZ Quiz Hub daily orchestrator

Selects the next quiz (oldest last_uploaded_at), generates the video,
uploads to YouTube, and logs the result to the video_jobs table.

Run manually:   python run_daily.py
Scheduled via:  setup_scheduler.bat  (Windows Task Scheduler)
"""

import logging
import os
import shutil
import sys
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass
from datetime import datetime

import mysql.connector
import requests

import config
from generate_quiz_ai import generate_and_insert_quiz
from generate_video import generate_video
from upload_youtube import upload_quiz_video

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_PATH = os.path.join(os.path.dirname(__file__), "quizflix_daily.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    return mysql.connector.connect(
        host=config.DB_HOST,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def select_next_quiz(cursor) -> int | None:
    cursor.execute("""
        SELECT id FROM quizzes
        ORDER BY last_uploaded_at ASC, id ASC
        LIMIT 1
    """)
    row = cursor.fetchone()
    return row[0] if row else None


def create_job(cursor, quiz_id: int) -> int:
    cursor.execute(
        "INSERT INTO video_jobs (quiz_id, status) VALUES (%s, 'pending')",
        (quiz_id,),
    )
    return cursor.lastrowid


def update_job(cursor, job_id: int, **fields):
    cols   = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [job_id]
    cursor.execute(f"UPDATE video_jobs SET {cols} WHERE id = %s", values)


def _make_progress_cb(cursor, db, job_id: int):
    """Returns a callback that persists progress % + label to the DB."""
    def cb(pct: int, label: str):
        try:
            cursor.execute(
                "UPDATE video_jobs SET progress = %s, progress_label = %s WHERE id = %s",
                (pct, label, job_id),
            )
            db.commit()
        except Exception:
            pass
    return cb


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(forced_quiz_id: int | None = None, existing_job_id: int | None = None):
    log.info("=== AZ Quiz Hub daily run started ===")
    db  = get_db()
    cur = db.cursor()

    try:
        if forced_quiz_id:
            quiz_id = forced_quiz_id
            log.info(f"Using forced quiz ID: {quiz_id}")
            # Guard: abort if this quiz already has a completed video upload
            cur.execute(
                "SELECT id FROM video_jobs WHERE quiz_id = %s AND status = 'done' LIMIT 1",
                (quiz_id,),
            )
            if cur.fetchone():
                log.warning(
                    f"Quiz {quiz_id} already has a completed video upload. "
                    "Use a different quiz ID or generate a new quiz. Aborting."
                )
                return
        else:
            # Generate a fresh AI quiz for today (topic deduplication handled inside)
            log.info("Generating new AI quiz with Gemini...")
            quiz_id = generate_and_insert_quiz()
            log.info(f"AI quiz created: ID={quiz_id}")

        log.info(f"Selected quiz ID: {quiz_id}")
        job_id = existing_job_id if existing_job_id else create_job(cur, quiz_id)
        db.commit()

        # Fetch quiz metadata (for YouTube title/description later)
        resp = requests.get(
            f"{config.QUIZ_API_BASE}/api/get-quiz.php",
            params={"id": quiz_id},
            timeout=10,
        )
        resp.raise_for_status()
        quiz_data = resp.json()
        log.info(f"Quiz: {quiz_data.get('title')}")

        # Step 1: Generate video
        update_job(cur, job_id, status="generating", progress=1, progress_label="Starting…")
        db.commit()

        log.info("Generating video...")
        progress_cb = _make_progress_cb(cur, db, job_id)
        video_path  = generate_video(quiz_id, progress_cb=progress_cb)
        log.info(f"Video generated: {video_path}")

        update_job(cur, job_id, video_path=video_path, status="uploading",
                   progress=99, progress_label="Uploading to YouTube…")
        db.commit()

        # Step 2: Upload to YouTube
        log.info("Uploading to YouTube...")
        result = upload_quiz_video(quiz_id, video_path, quiz_data)
        yt_id  = result["video_id"]
        yt_url = result["url"]
        log.info(f"Uploaded: {yt_url}")

        # Step 3: Mark success
        update_job(cur, job_id,
                   status="done",
                   youtube_video_id=yt_id,
                   youtube_url=yt_url,
                   completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur.execute(
            "UPDATE quizzes SET last_uploaded_at = NOW() WHERE id = %s",
            (quiz_id,),
        )
        db.commit()
        log.info("Job complete.")

        # Step 4: Cleanup
        _cleanup(quiz_id, video_path)

    except Exception as exc:
        tb = traceback.format_exc()
        log.error(f"Job failed: {exc}\n{tb}")
        try:
            detail = f"{exc}\n\n{tb}"
            update_job(cur, job_id, status="failed", error_message=detail[:4000])
            db.commit()
        except Exception:
            pass
    finally:
        cur.close()
        db.close()
        log.info("=== AZ Quiz Hub daily run finished ===\n")


def _cleanup(quiz_id: int, video_path: str):
    # Remove temp TTS files
    date_str = datetime.now().strftime("%Y%m%d")
    prefix   = os.path.join(config.AUDIO_TMP_DIR, f"q{quiz_id}_{date_str}")
    for f in os.listdir(config.AUDIO_TMP_DIR):
        if f.startswith(f"q{quiz_id}_{date_str}"):
            try:
                os.remove(os.path.join(config.AUDIO_TMP_DIR, f))
            except OSError:
                pass

    # Optionally delete the video file after upload
    if config.DELETE_VIDEO_AFTER_UPLOAD and os.path.exists(video_path):
        os.remove(video_path)
        log.info(f"Deleted local video: {video_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiz-id", type=int, default=None,
                        help="Force a specific quiz ID (skips rotation logic)")
    parser.add_argument("--job-id", type=int, default=None,
                        help="Reuse an existing video_jobs row instead of creating a new one")
    args = parser.parse_args()
    run(forced_quiz_id=args.quiz_id, existing_job_id=args.job_id)
