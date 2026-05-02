# AZ Quiz Hub — CLAUDE.md

## What this project is

AZ Quiz Hub is an automated YouTube quiz video channel. Every day it:
1. Calls **Gemini 2.5 Flash** to generate a fresh 10-question multiple-choice quiz on a random topic
2. Renders a **1080p MP4 video** of the quiz (backgrounds, animated timer, TTS narration, sound effects)
3. **Uploads the video to YouTube** via the Data API v3

There is also a browser-based quiz player at `http://localhost/quizflix/` and an admin dashboard at `http://localhost/quizflix/admin/`.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Web server | Apache (XAMPP) |
| Backend / Admin | PHP 8+ (procedural, no framework) |
| Database | MySQL via PDO |
| Quiz player | Vanilla JS + CSS3 (no frameworks) |
| Video generator | Python 3.11 + moviepy + Pillow + FFmpeg |
| TTS narration | Microsoft Edge TTS (`edge-tts`) |
| AI quiz content | Google Gemini 2.5 Flash (`google-genai`) |
| YouTube upload | YouTube Data API v3 (`google-api-python-client`) |
| Scheduler | Windows Task Scheduler (`QuizFlixDailyUpload`, runs at 09:00) |

---

## File map

```
/quizflix
  index.php                   ← Public quiz player (selector + quiz UI)
  /public
    /css/style.css            ← Full quiz UI styles (glassmorphism design)
    /js/script.js             ← Quiz logic: timer, TTS, score, progress bar
    /assets/logo.png
    /media/                   ← Uploaded audio (MP3), images, videos used in quizzes
  /api
    get-quizzes.php           ← JSON: list all quizzes [{id, title}]
    get-quiz.php              ← JSON: full quiz data with questions & options
  /admin
    index.php                 ← Dashboard: quiz list + video upload history
    create-quiz.php           ← Manual quiz creation form
    edit.php                  ← Tabbed quiz editor (metadata + questions)
    upload-csv.php            ← Bulk import from CSV
    upload-assets.php         ← File uploader popup (MP3/MP4/images)
    delete-quiz.php           ← Cascade-delete a quiz
    trigger-video.php         ← "Generate & Upload Now" handler (on-demand)
  /includes
    db.php                    ← PDO connection (localhost, root, no password)
  /generator
    config.py                 ← All settings: DB, paths, Gemini key, YouTube, topics
    generate_quiz_ai.py       ← Gemini 2.5 Flash → quiz JSON → DB insert
    generate_video.py         ← Quiz data → TTS audio → Pillow frames → MP4
    upload_youtube.py         ← OAuth2 YouTube upload + thumbnail
    run_daily.py              ← Orchestrator: AI quiz → video → YouTube → DB log
    requirements.txt          ← Python dependencies
    setup_scheduler.bat       ← Register Windows Task Scheduler (run as Admin)
    quizflix_daily.log        ← Auto-created run log
    /output/                  ← Generated MP4s (deleted after upload)
    /thumbnails/              ← Generated JPG thumbnails
    /audio_tmp/               ← Temp TTS MP3 files (cleaned up after run)
    client_secrets.json       ← YouTube OAuth credentials (gitignored)
    token.json                ← YouTube OAuth token, auto-refreshed (gitignored)
  /sql
    schema.sql                ← Full DDL for all 4 tables
  upload.csv                  ← Sample CSV format for bulk import
```

---

## Database schema (4 tables)

```sql
quizzes        id, title, intro_text, outro_text, bg_music, chalk_sound,
               correct_sound, background_image, last_uploaded_at, created_at

questions      id, quiz_id→quizzes, question_text, correct_index (0-3), fun_fact

options        id, question_id→questions, option_index (0-3), option_text

video_jobs     id, quiz_id→quizzes, status (pending|generating|uploading|done|failed),
               video_path, youtube_url, youtube_video_id, error_message,
               created_at, completed_at
```

`quizzes.last_uploaded_at` drives the daily rotation — the quiz with the oldest (or NULL) value is picked next.

---

## API response shape

`GET /api/get-quiz.php?id={id}` returns:
```json
{
  "title": "...",
  "introText": "...",
  "outroText": "...",
  "bgMusic": "filename.mp3",
  "chalkSound": "filename.mp3",
  "correctSound": "filename.mp3",
  "backgroundImage": "filename.jpg",
  "questions": [
    { "q": "Question text?", "o": ["A","B","C","D"], "c": 0, "f": "Fun fact." }
  ]
}
```

---

## Running things

### Daily pipeline (automated)
```
# Windows Task Scheduler runs this at 09:00 every day:
python generator/run_daily.py

# Force a specific quiz (skip AI generation):
python generator/run_daily.py --quiz-id 13

# Manual test of just the AI generator:
python generator/generate_quiz_ai.py --topic "Space & Astronomy"

# Manual test of just video generation:
python generator/generate_video.py --quiz-id 13

# Manual test of just YouTube upload:
python generator/upload_youtube.py --video output/quiz_13_20260501.mp4 --quiz-id 13
```

### Database
```bash
# Apply schema (fresh setup):
mysql -u root quizflix < sql/schema.sql

# Check recent video jobs:
mysql -u root quizflix -e "SELECT id,status,youtube_url,created_at FROM video_jobs ORDER BY id DESC LIMIT 5;"
```

### Scheduler management
```bat
# Register daily task (run as Administrator):
generator\setup_scheduler.bat

# Change run time:
schtasks /change /tn "QuizFlixDailyUpload" /st 10:00

# Run immediately:
schtasks /run /tn "QuizFlixDailyUpload"

# Remove:
schtasks /delete /tn "QuizFlixDailyUpload" /f
```

---

## Key configuration (`generator/config.py`)

```python
GEMINI_API_KEY  = "AIza..."          # From https://aistudio.google.com/app/apikey
GEMINI_MODEL    = "gemini-2.5-flash" # Free tier, no billing needed
QUIZ_TOPICS     = [...]              # 40+ topics, one picked randomly each day

DB_HOST/NAME/USER/PASSWORD           # XAMPP defaults (root, no password)
MEDIA_DIR       = r"D:\xampp\htdocs\quizflix\public\media"
VIDEO_WIDTH/HEIGHT = 1920, 1080
TIMER_DURATION  = 10                 # seconds per question
TTS_VOICE       = "en-US-AriaNeural"
DELETE_VIDEO_AFTER_UPLOAD = True     # saves disk space
```

---

## First-time setup checklist

- [ ] XAMPP running (Apache + MySQL)
- [ ] MySQL: `CREATE DATABASE quizflix;` then run `sql/schema.sql`
- [ ] Python 3.11+ and FFmpeg in PATH
- [ ] `pip install -r generator/requirements.txt`
- [ ] Set `GEMINI_API_KEY` in `generator/config.py` (free key from aistudio.google.com)
- [ ] Run `python generator/run_daily.py` once to complete YouTube OAuth (browser opens)
- [ ] Run `generator\setup_scheduler.bat` as Administrator for daily automation

---

## CSV import format

`upload.csv` — one row per question, multiple rows share a quiz by title:

```
quiz_title, intro_text, outro_text, bg_music, chalk_sound, correct_sound,
background_image, question, option_1, option_2, option_3, option_4,
correct_index (0-based), fun_fact
```

---

## Security notes (known gaps for local/dev use)

- Admin panel has no login — add `auth.php` session guard before production use
- No CSRF tokens on admin forms
- DB credentials hardcoded in `includes/db.php` — move to `.env` for production
- File upload validates MIME type from `$_FILES` only — use `finfo_file()` for production

---

## Important behaviours

- **Video generation** takes ~5–10 minutes per quiz depending on question count and TTS length
- **Thumbnail upload** requires a phone-verified YouTube channel; silently skipped if not verified
- **TTS** uses Microsoft Edge neural voices via `edge-tts`; requires internet
- **Background assets** are randomly assigned from `/public/media/` at quiz creation time
- **Quiz rotation** uses `ORDER BY last_uploaded_at ASC NULLS FIRST` — AI-generated quizzes always upload the freshest one
- `generator/quizflix_daily.log` is the first place to check if a run fails
