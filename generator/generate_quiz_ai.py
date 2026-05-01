"""
generate_quiz_ai.py  —  Generate a quiz using Gemini 2.5 Flash and insert it into the DB.

Usage:
    python generate_quiz_ai.py                           # random topic
    python generate_quiz_ai.py --topic "Space & Astronomy"

Prerequisites:
    Get a free API key at https://aistudio.google.com/app/apikey
    Then set GEMINI_API_KEY in generator/config.py
"""

import argparse
import json
import os
import random

from google import genai
from google.genai import types
import mysql.connector

import config


# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

def _get_client() -> genai.Client:
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "YOUR_KEY_HERE":
        raise ValueError(
            "GEMINI_API_KEY is not set.\n"
            "Get a free key at https://aistudio.google.com/app/apikey\n"
            "Then set it in generator/config.py:  GEMINI_API_KEY = \"AIza...\""
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Prompt & generation
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """Generate a fun and educational multiple-choice quiz about "{topic}".

Return ONLY valid JSON matching this exact schema — no markdown, no extra text:
{{
  "title": "Short catchy quiz title (max 60 chars)",
  "intro_text": "2-3 sentences welcoming the viewer and describing what the quiz is about.",
  "outro_text": "2-3 sentences congratulating the viewer and encouraging them to subscribe.",
  "questions": [
    {{
      "question_text": "The full question sentence?",
      "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
      "correct_index": 0,
      "fun_fact": "1-2 interesting sentences explaining the answer or a related fact."
    }}
  ]
}}

Rules:
- Exactly {count} questions.
- correct_index is 0-based: 0=A, 1=B, 2=C, 3=D.
- Questions should vary in difficulty (mix of easy, medium, hard).
- Do NOT repeat similar questions.
- Keep question_text under 120 characters.
- Keep each option under 60 characters.
- fun_fact must be genuinely interesting and educational."""


def generate_quiz_content(topic: str) -> dict:
    client = _get_client()
    prompt = PROMPT_TEMPLATE.format(topic=topic, count=config.QUESTIONS_PER_QUIZ)
    print(f"Asking Gemini ({config.GEMINI_MODEL}) to generate a quiz about: {topic}")

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.85,
            response_mime_type="application/json",
        ),
    )
    data = json.loads(response.text)
    _validate(data)
    return data


def _validate(data: dict):
    for key in ("title", "intro_text", "outro_text", "questions"):
        if key not in data:
            raise ValueError(f"LLM response missing key: {key}")
    if len(data["questions"]) < 5:
        raise ValueError(f"Too few questions returned: {len(data['questions'])}")
    for i, q in enumerate(data["questions"]):
        for k in ("question_text", "options", "correct_index", "fun_fact"):
            if k not in q:
                raise ValueError(f"Question {i} missing key: {k}")
        if len(q["options"]) != 4:
            raise ValueError(f"Question {i} must have exactly 4 options")
        if not (0 <= int(q["correct_index"]) <= 3):
            raise ValueError(f"Question {i} correct_index out of range: {q['correct_index']}")


# ---------------------------------------------------------------------------
# Media asset assignment
# ---------------------------------------------------------------------------

def _pick_media_assets() -> dict:
    all_files   = os.listdir(config.MEDIA_DIR) if os.path.exists(config.MEDIA_DIR) else []
    audio_files = [f for f in all_files if f.lower().endswith(".mp3")]
    bg_files    = [f for f in all_files if f.lower().split(".")[-1] in ("jpg","jpeg","png","webp","gif","mp4")]

    def pick(pool, default):
        return random.choice(pool) if pool else default

    return {
        "bg_music":         pick(audio_files, "bg-music.mp3"),
        "chalk_sound":      pick(audio_files, "chalk.mp3"),
        "correct_sound":    pick(audio_files, "correct.mp3"),
        "background_image": pick(bg_files,    "chalkboard-bg.jpg"),
    }


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

def insert_quiz(data: dict, assets: dict) -> int:
    db  = mysql.connector.connect(
        host=config.DB_HOST, database=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO quizzes
              (title, intro_text, outro_text, bg_music, chalk_sound, correct_sound, background_image)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data["title"], data["intro_text"], data["outro_text"],
            assets["bg_music"], assets["chalk_sound"],
            assets["correct_sound"], assets["background_image"],
        ))
        quiz_id = cur.lastrowid

        for q in data["questions"]:
            cur.execute("""
                INSERT INTO questions (quiz_id, question_text, correct_index, fun_fact)
                VALUES (%s, %s, %s, %s)
            """, (quiz_id, q["question_text"], int(q["correct_index"]), q["fun_fact"]))
            qid = cur.lastrowid
            for idx, opt in enumerate(q["options"]):
                cur.execute(
                    "INSERT INTO options (question_id, option_index, option_text) VALUES (%s, %s, %s)",
                    (qid, idx, opt),
                )

        db.commit()
        print(f"Quiz inserted: ID={quiz_id}, title='{data['title']}'")
        return quiz_id
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()
        db.close()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_and_insert_quiz(topic: str | None = None) -> int:
    if topic is None:
        topic = random.choice(config.QUIZ_TOPICS)
    data   = generate_quiz_content(topic)
    assets = _pick_media_assets()
    return insert_quiz(data, assets)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an AI quiz and insert into DB")
    parser.add_argument("--topic", type=str, default=None, help="Quiz topic (random if omitted)")
    args = parser.parse_args()

    quiz_id = generate_and_insert_quiz(args.topic)
    print(f"Done. New quiz ID: {quiz_id}")
    print(f"Preview: http://localhost/quizflix/?id={quiz_id}")
