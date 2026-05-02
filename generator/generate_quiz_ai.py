"""
generate_quiz_ai.py  —  Generate a quiz using Gemini 2.5 Flash and insert it into the DB.

Usage:
    python generate_quiz_ai.py                           # random topic
    python generate_quiz_ai.py --topic "Space & Astronomy"

Prerequisites:
    Get a free API key at https://aistudio.google.com/app/apikey
    Then set GEMINI_API_KEY in generator/.env
"""

import argparse
import json
import os
import random
import sys

# Windows console defaults to cp1252 which can't encode emoji in AI-generated text
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

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
            "Then add it to generator/.env:  GEMINI_API_KEY=AIza..."
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Prompt & generation
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """Generate a fun and educational multiple-choice quiz about "{topic}" for a YouTube channel called AZ Quiz Hub.

Return ONLY valid JSON matching this exact schema — no markdown, no extra text:
{{
  "title": "Short catchy quiz title (max 60 chars, no emoji)",
  "intro_text": "Spoken video welcome (2-3 sentences, TTS-friendly).",
  "outro_text": "Spoken video closing (2-3 sentences, TTS-friendly).",
  "youtube_title": "SEO-optimised YouTube video title (60-80 chars, 1-2 emojis).",
  "youtube_description": "Full YouTube video description (400-600 words).",
  "youtube_tags": ["tag1", "tag2"],
  "questions": [
    {{
      "question_text": "Question sentence?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_index": 0,
      "fun_fact": "Interesting 1-2 sentence fact about the answer."
    }}
  ]
}}

Content rules:
- Exactly {count} questions, varying in difficulty (easy / medium / hard mix).
- correct_index is 0-based (0 = A, 1 = B, 2 = C, 3 = D). No repeated or similar questions.
- question_text: under 120 characters. Each option: under 60 characters.
- fun_fact: genuinely interesting and educational.

Writing rules for each field:
- title: plain text, max 60 chars, no emoji.
- intro_text: natural spoken English for TTS. Open with a direct question or surprising fact about "{topic}". Welcome the viewer to AZ Quiz Hub. Tell them there are {count} questions with 10 seconds each. Build excitement with an energetic, friendly tone.
- outro_text: natural spoken English for TTS. Congratulate the viewer warmly. Ask them to drop their score in the comments. Tell them to like the video and subscribe for a brand new quiz every single day.
- youtube_title: 60-80 chars, 1-2 relevant emojis placed naturally (not at the start), strong SEO keywords for "{topic}", end with a hook phrase such as "Can You Score 10/10?" or "How Many Can YOU Get Right?" or "Only Geniuses Score 100%!".
- youtube_description: 400-600 words. Structure: (1) First line — compelling hook visible before "show more" (must contain "{topic}" and a challenge hook). (2) Paragraph about what the quiz covers and why "{topic}" is fascinating. (3) What viewers will learn or discover. (4) Engagement section: ask viewers to pause and answer each question, then comment their score. (5) Subscribe CTA. (6) A blank line then 12-15 relevant hashtags. Use emoji bullets (🎯 🧠 💡 📚 🌍 etc.) for visual structure. No markdown asterisks.
- youtube_tags: 12-15 tags — mix of broad (quiz, trivia, education, general knowledge) and specific to "{topic}"."""


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
    required_top = ("title", "intro_text", "outro_text", "youtube_title",
                    "youtube_description", "youtube_tags", "questions")
    for key in required_top:
        if key not in data:
            raise ValueError(f"Gemini response missing key: '{key}'")
    if len(data["questions"]) < 5:
        raise ValueError(f"Too few questions returned: {len(data['questions'])}")
    for i, q in enumerate(data["questions"]):
        for k in ("question_text", "options", "correct_index", "fun_fact"):
            if k not in q:
                raise ValueError(f"Question {i} missing key: '{k}'")
        if len(q["options"]) != 4:
            raise ValueError(f"Question {i} must have exactly 4 options")
        if not (0 <= int(q["correct_index"]) <= 3):
            raise ValueError(f"Question {i} correct_index out of range: {q['correct_index']}")
    if not isinstance(data["youtube_tags"], list) or len(data["youtube_tags"]) < 3:
        raise ValueError("youtube_tags must be a list with at least 3 items")


# ---------------------------------------------------------------------------
# Media asset assignment
# ---------------------------------------------------------------------------

def _pick_media_assets() -> dict:
    media = config.MEDIA_DIR

    def resolve(filename):
        """Return filename if the file exists in MEDIA_DIR, otherwise None."""
        return filename if os.path.exists(os.path.join(media, filename)) else None

    return {
        "bg_music":         resolve(config.DEFAULT_BG_MUSIC)      or config.DEFAULT_BG_MUSIC,
        "correct_sound":    resolve(config.DEFAULT_CORRECT_SOUND) or config.DEFAULT_CORRECT_SOUND,
        "background_image": resolve(config.DEFAULT_BACKGROUND)    or config.DEFAULT_BACKGROUND,
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
        tags_json = json.dumps(data.get("youtube_tags", []))

        cur.execute("""
            INSERT INTO quizzes
              (title, topic, intro_text, outro_text,
               youtube_title, youtube_description, youtube_tags,
               bg_music, correct_sound, background_image)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data["title"],
            data.get("_topic", ""),
            data["intro_text"],
            data["outro_text"],
            data["youtube_title"],
            data["youtube_description"],
            tags_json,
            assets["bg_music"],
            assets["correct_sound"],
            assets["background_image"],
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
        print(f"YouTube title: {data['youtube_title']}")
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

def _pick_topic(forced: str | None) -> str:
    """Pick a topic not yet used, cycling through all topics before repeating."""
    if forced:
        return forced
    db  = mysql.connector.connect(
        host=config.DB_HOST, database=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    cur = db.cursor()
    try:
        cur.execute("SELECT topic FROM quizzes WHERE topic IS NOT NULL AND topic != ''")
        used = {row[0] for row in cur.fetchall()}
    finally:
        cur.close()
        db.close()

    available = [t for t in config.QUIZ_TOPICS if t not in used]
    if not available:
        # All topics exhausted — start fresh cycle
        print("All topics have been used. Restarting the topic cycle.")
        available = config.QUIZ_TOPICS
    return random.choice(available)


def generate_and_insert_quiz(topic: str | None = None) -> int:
    topic  = _pick_topic(topic)
    data   = generate_quiz_content(topic)
    data["_topic"] = topic   # pass to insert_quiz via data dict
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
