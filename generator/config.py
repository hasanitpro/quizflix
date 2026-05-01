import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- Database ---
DB_HOST     = "localhost"
DB_NAME     = "quizflix"
DB_USER     = "root"
DB_PASSWORD = ""

# --- Quiz API ---
QUIZ_API_BASE = "http://localhost/quizflix"

# --- Paths ---
OUTPUT_DIR    = os.path.join(BASE_DIR, "output")
THUMB_DIR     = os.path.join(BASE_DIR, "thumbnails")
AUDIO_TMP_DIR = os.path.join(BASE_DIR, "audio_tmp")
MEDIA_DIR     = r"D:\xampp\htdocs\quizflix\public\media"
LOGO_PATH     = r"D:\xampp\htdocs\quizflix\public\assets\logo.png"

# --- Video ---
VIDEO_WIDTH    = 1920
VIDEO_HEIGHT   = 1080
VIDEO_FPS      = 30
TIMER_DURATION = 10  # seconds per question timer

# --- TTS ---
TTS_VOICE = "en-US-AriaNeural"
TTS_RATE  = "+0%"

# --- Audio ---
MUSIC_VOLUME = 0.3
SFX_VOLUME   = 0.8

# --- YouTube ---
YOUTUBE_SECRETS  = os.path.join(BASE_DIR, "client_secrets.json")
YOUTUBE_TOKEN    = os.path.join(BASE_DIR, "token.json")
YOUTUBE_CATEGORY = "22"  # Education
YOUTUBE_SCOPES   = ["https://www.googleapis.com/auth/youtube.upload"]

# --- Gemini AI Quiz Generator ---
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL       = "gemini-2.5-flash"
QUESTIONS_PER_QUIZ = 10

QUIZ_TOPICS = [
    "World Geography", "Ancient History", "Space & Astronomy",
    "Human Biology", "Famous Scientists", "World Capitals",
    "Classic Literature", "Pop Culture", "World Religions",
    "Mathematics & Logic", "Animals & Wildlife", "Technology & Computers",
    "Famous Inventions", "Movies & Cinema", "Music History",
    "Sports Trivia", "Food & Cuisine", "Famous Artworks",
    "World Languages", "Climate & Environment", "Economics & Finance",
    "Philosophy", "Mythology", "Architecture",
    "Medical Science", "Oceans & Marine Life", "Famous Leaders",
    "Astronomy & Black Holes", "Cryptography", "Aviation History",
    "The Human Brain", "Extreme Weather", "Dinosaurs & Prehistoric Life",
    "Ancient Civilisations", "Famous Quotes", "Video Games",
    "World Records", "Flags of the World", "Currency & Economics",
    "Famous Battles", "Chemistry Basics",
]

# --- Behaviour ---
DELETE_VIDEO_AFTER_UPLOAD = True

# --- Visual theme ---
OPTION_COLORS = {
    0: "#e74c3c",  # A — red
    1: "#3498db",  # B — blue
    2: "#2ecc71",  # C — green
    3: "#f1c40f",  # D — yellow
}
CORRECT_HIGHLIGHT = "#27ae60"
TEXT_COLOR        = "#ffffff"
SHADOW_COLOR      = "#000000"
OVERLAY_ALPHA     = 160        # 0-255, darkness of text background strip

# Fonts — uses default Pillow TrueType if these paths don't exist on the system
FONT_QUESTION = "arialbd.ttf"
FONT_OPTIONS  = "arial.ttf"
FONT_TITLE    = "arialbd.ttf"

for d in (OUTPUT_DIR, THUMB_DIR, AUDIO_TMP_DIR):
    os.makedirs(d, exist_ok=True)
