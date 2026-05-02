"""
upload_youtube.py  —  Upload a video to YouTube via Data API v3

Usage:
    python upload_youtube.py --video output/quiz_1_20260501.mp4 --quiz-id 1 --title "My Quiz"

First run opens a browser for one-time OAuth consent; subsequent runs use
the saved token.json automatically.

Prerequisites:
  1. Create a project at console.cloud.google.com
  2. Enable "YouTube Data API v3"
  3. Create OAuth 2.0 credentials (Desktop app) → download as client_secrets.json
  4. Place client_secrets.json next to this file
"""

import argparse
import os
import pickle
from datetime import datetime

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config


def get_authenticated_service():
    creds = None

    if os.path.exists(config.YOUTUBE_TOKEN):
        with open(config.YOUTUBE_TOKEN, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.YOUTUBE_SECRETS):
                raise FileNotFoundError(
                    f"client_secrets.json not found at {config.YOUTUBE_SECRETS}\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_SECRETS,
                scopes=config.YOUTUBE_SCOPES,
            )
            creds = flow.run_local_server(port=0)

        with open(config.YOUTUBE_TOKEN, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    thumbnail_path: str | None = None,
    privacy: str = "public",
) -> dict:
    """Upload video and return {'video_id': ..., 'url': ...}"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": config.YOUTUBE_CATEGORY,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10,  # 10MB chunks
    )

    print(f"Uploading: {os.path.basename(video_path)}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%", end="\r")

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\nUploaded: {video_url}")

    # Set thumbnail (requires a verified YouTube channel — skipped gracefully if not)
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            print("Thumbnail set.")
        except Exception as e:
            print(f"Warning: could not set thumbnail (channel may need verification): {e}")

    return {"video_id": video_id, "url": video_url}


def upload_quiz_video(quiz_id: int, video_path: str, quiz_data: dict) -> dict:
    date_code  = datetime.now().strftime("%Y%m%d")
    thumb_path = os.path.join(config.THUMB_DIR, f"quiz_{quiz_id}_{date_code}.jpg")

    # Use AI-generated YouTube metadata; fall back to a basic title if missing
    title = (
        quiz_data.get("youtubeTitle") or
        f"{quiz_data.get('title', 'Quiz')} | Can You Score 10/10? 🧠"
    )
    description = (
        quiz_data.get("youtubeDescription") or
        f"{quiz_data.get('introText', '').strip()}\n\n"
        f"{quiz_data.get('outroText', '').strip()}\n\n"
        "👍 Like and subscribe for daily quiz videos!\n\n"
        "#quiz #trivia #dailyquiz #challenge #education"
    )
    tags = (
        quiz_data.get("youtubeTags") or
        ["quiz", "trivia", "daily quiz", "challenge", "education",
         "general knowledge", quiz_data.get("title", "quiz")]
    )

    return upload_video(video_path, title, description, tags, thumb_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import requests as req

    parser = argparse.ArgumentParser(description="Upload a quiz video to YouTube")
    parser.add_argument("--video",   required=True, help="Path to the MP4 file")
    parser.add_argument("--quiz-id", type=int, required=True, help="Quiz ID")
    args = parser.parse_args()

    resp = req.get(f"{config.QUIZ_API_BASE}/api/get-quiz.php", params={"id": args.quiz_id})
    quiz = resp.json()

    result = upload_quiz_video(args.quiz_id, args.video, quiz)
    print(f"YouTube URL: {result['url']}")
