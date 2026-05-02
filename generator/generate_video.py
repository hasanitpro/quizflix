"""
generate_video.py  —  QuizFlix video generator

Usage:
    python generate_video.py --quiz-id 1
    python generate_video.py --quiz-id 1 --output my_video.mp4
"""

import argparse
import asyncio
import math
import os
import textwrap
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# moviepy 1.0.3 still references the removed PIL.Image.ANTIALIAS (dropped in Pillow 10)
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.audio.AudioClip import AudioArrayClip
import numpy as np
import edge_tts

import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        # Fallback: Pillow default bitmap font (no sizing)
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text_with_shadow(
    draw: ImageDraw.Draw,
    xy: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str = config.TEXT_COLOR,
    shadow: str = config.SHADOW_COLOR,
    shadow_offset: int = 3,
):
    x, y = xy
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def get_background_frame(bg_path: str | None) -> np.ndarray:
    """Return a single 1920×1080 RGB numpy array for the background."""
    W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    if bg_path and os.path.exists(bg_path):
        ext = Path(bg_path).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            img = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
            return np.array(img)
    # Default dark gradient background
    img = Image.new("RGB", (W, H), "#0d1b2a")
    return np.array(img)


def dark_overlay(frame: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Darken a frame to improve text legibility."""
    overlay = np.zeros_like(frame)
    return (frame * (1 - alpha) + overlay * alpha).astype(np.uint8)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

async def _tts_async(text: str, output_path: str):
    communicate = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)
    await communicate.save(output_path)


def generate_tts(text: str, output_path: str):
    if not text or not text.strip():
        text = "."
    asyncio.run(_tts_async(text.strip(), output_path))


def tts_duration(path: str) -> float:
    if not os.path.exists(path):
        return 1.0
    clip = AudioFileClip(path)
    d = clip.duration
    clip.close()
    return d


# ---------------------------------------------------------------------------
# Frame builders (return Pillow Image)
# ---------------------------------------------------------------------------

def build_title_frame(title: str, subtitle: str, bg_frame: np.ndarray) -> Image.Image:
    W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img = Image.fromarray(dark_overlay(bg_frame, 0.5))
    draw = ImageDraw.Draw(img)

    f_title = load_font(config.FONT_TITLE, 90)
    f_sub   = load_font(config.FONT_OPTIONS, 48)

    # Title
    lines = wrap_text(title, f_title, W - 200)
    y = H // 2 - len(lines) * 100 // 2
    for line in lines:
        bbox = f_title.getbbox(line)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw_text_with_shadow(draw, (x, y), line, f_title)
        y += 110

    # Subtitle
    if subtitle:
        sub_lines = wrap_text(subtitle, f_sub, W - 300)
        y += 30
        for line in sub_lines:
            bbox = f_sub.getbbox(line)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw_text_with_shadow(draw, (x, y), line, f_sub, fill="#d0e8ff")
            y += 58

    return img


def build_question_frame(
    question: str,
    options: list[str],
    bg_frame: np.ndarray,
    reveal_index: int | None = None,
    fun_fact: str | None = None,
) -> Image.Image:
    W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img = Image.fromarray(dark_overlay(bg_frame, 0.5))
    draw = ImageDraw.Draw(img)

    f_q   = load_font(config.FONT_QUESTION, 56)
    f_opt = load_font(config.FONT_OPTIONS, 44)
    f_ff  = load_font(config.FONT_OPTIONS, 38)

    # Question text
    lines = wrap_text(question, f_q, W - 160)
    y = 80
    for line in lines:
        bbox = f_q.getbbox(line)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw_text_with_shadow(draw, (x, y), line, f_q)
        y += 70
    q_bottom = y + 20

    # Option boxes — 2×2 grid
    labels = ["A", "B", "C", "D"]
    pad    = 30
    cols   = 2
    box_w  = (W - pad * (cols + 1)) // cols
    box_h  = 130
    grid_top = q_bottom + 40
    row_gap  = 20

    for i, (opt, label) in enumerate(zip(options, labels)):
        col = i % 2
        row = i // 2
        x1  = pad + col * (box_w + pad)
        y1  = grid_top + row * (box_h + row_gap)
        x2  = x1 + box_w
        y2  = y1 + box_h

        color = config.OPTION_COLORS[i]
        if reveal_index is not None and i == reveal_index:
            color = config.CORRECT_HIGHLIGHT
            # Glow: draw wider border
            for offset in range(1, 6):
                draw.rounded_rectangle(
                    [x1 - offset, y1 - offset, x2 + offset, y2 + offset],
                    radius=16, outline="#00ff88", width=2,
                )

        draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=color)

        # Label letter
        lbbox = f_opt.getbbox(label)
        draw.text(
            (x1 + 20, y1 + (box_h - (lbbox[3] - lbbox[1])) // 2),
            label, font=f_opt, fill="white",
        )
        # Option text
        opt_lines = wrap_text(opt, f_opt, box_w - 90)
        oy = y1 + (box_h - len(opt_lines) * 50) // 2
        for ol in opt_lines:
            draw.text((x1 + 80, oy), ol, font=f_opt, fill="white")
            oy += 50

    # Fun fact strip
    if fun_fact:
        ff_lines = wrap_text(f"Fun Fact: {fun_fact}", f_ff, W - 160)
        strip_h  = len(ff_lines) * 50 + 30
        strip_y  = H - strip_h - 40
        draw.rectangle([0, strip_y - 10, W, strip_y + strip_h], fill=(0, 0, 0, 180))
        fy = strip_y
        for fl in ff_lines:
            bbox = f_ff.getbbox(fl)
            fx = (W - (bbox[2] - bbox[0])) // 2
            draw_text_with_shadow(draw, (fx, fy), fl, f_ff, fill="#ffe066")
            fy += 50

    return img


def build_timer_frame(
    question: str,
    options: list[str],
    bg_frame: np.ndarray,
    seconds_left: float,
    total: float = 10.0,
) -> Image.Image:
    img = build_question_frame(question, options, bg_frame)
    draw = ImageDraw.Draw(img)

    W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    cx, cy, r = W - 120, 120, 90
    # Background circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 160))
    # Arc
    fraction = seconds_left / total
    end_angle = -90 + 360 * fraction
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=end_angle,
             fill="#ffffff", width=10)
    # Number
    f_timer = load_font(config.FONT_TITLE, 64)
    num_str = str(math.ceil(seconds_left))
    bbox = f_timer.getbbox(num_str)
    draw.text(
        (cx - (bbox[2] - bbox[0]) // 2, cy - (bbox[3] - bbox[1]) // 2),
        num_str, font=f_timer, fill="white",
    )
    return img


# ---------------------------------------------------------------------------
# Segment builders (return moviepy VideoClip)
# ---------------------------------------------------------------------------

def make_static_clip(frame: np.ndarray | Image.Image, duration: float):
    if isinstance(frame, Image.Image):
        frame = np.array(frame)
    return ImageClip(frame).set_duration(duration)


def make_timer_clip(
    question: str,
    options: list[str],
    bg_frame: np.ndarray,
    duration: float = 10.0,
) -> "VideoClip":
    from moviepy.video.VideoClip import VideoClip

    def make_frame(t):
        remaining = max(0.0, duration - t)
        img = build_timer_frame(question, options, bg_frame, remaining, duration)
        return np.array(img)

    return VideoClip(make_frame, duration=duration).set_fps(config.VIDEO_FPS)


def mix_audio(
    bg_music_path: str | None,
    tts_path: str | None,
    sfx_path: str | None,
    total_duration: float,
    sfx_start: float = 0.0,
) -> CompositeAudioClip | None:
    tracks = []

    if bg_music_path and os.path.exists(bg_music_path):
        music = AudioFileClip(bg_music_path).volumex(config.MUSIC_VOLUME)
        # Loop music if shorter than needed
        if music.duration < total_duration:
            loops = math.ceil(total_duration / music.duration)
            from moviepy.audio.AudioClip import concatenate_audioclips
            music = concatenate_audioclips([music] * loops)
        music = music.subclip(0, total_duration)
        tracks.append(music)

    if tts_path and os.path.exists(tts_path):
        tracks.append(AudioFileClip(tts_path))

    if sfx_path and os.path.exists(sfx_path):
        tracks.append(AudioFileClip(sfx_path).set_start(sfx_start).volumex(config.SFX_VOLUME))

    if not tracks:
        return None
    return CompositeAudioClip(tracks)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_video(quiz_id: int, output_path: str | None = None) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    if output_path is None:
        output_path = os.path.join(config.OUTPUT_DIR, f"quiz_{quiz_id}_{date_str}.mp4")

    # 1. Fetch quiz data
    resp = requests.get(f"{config.QUIZ_API_BASE}/api/get-quiz.php", params={"id": quiz_id}, timeout=10)
    resp.raise_for_status()
    quiz = resp.json()

    title       = quiz.get("title", "Quiz")
    intro_text  = quiz.get("introText", "")
    outro_text  = quiz.get("outroText", "")
    bg_file     = quiz.get("backgroundImage", "")
    bg_music    = quiz.get("bgMusic", "")
    correct_snd = quiz.get("correctSound", "")
    questions   = quiz.get("questions", [])

    # Resolve media paths
    def media(name):
        return os.path.join(config.MEDIA_DIR, name) if name else None

    bg_path       = media(bg_file)
    bg_music_path = media(bg_music)
    correct_path  = media(correct_snd)

    # 2. Get background image frame (static image; videos handled separately)
    bg_ext = Path(bg_file).suffix.lower() if bg_file else ""
    use_video_bg = bg_ext in (".mp4",) and bg_path and os.path.exists(bg_path)

    if use_video_bg:
        bg_clip_src = VideoFileClip(bg_path).resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
        bg_frame    = bg_clip_src.get_frame(0)
        _vid_dur    = bg_clip_src.duration
        _vid_fps    = bg_clip_src.fps or config.VIDEO_FPS
    else:
        bg_frame = get_background_frame(bg_path)

    def get_bg_clip(duration):
        if use_video_bg:
            # Use a custom VideoClip that loops via modulo — avoids passing the
            # same VideoFileClip object multiple times to concatenate_videoclips,
            # which causes [Errno 22] Invalid argument on Windows.
            from moviepy.video.VideoClip import VideoClip
            return (
                VideoClip(lambda t: bg_clip_src.get_frame(t % _vid_dur), duration=duration)
                .set_fps(_vid_fps)
            )
        return ImageClip(bg_frame).set_duration(duration)

    # 3. Generate TTS files
    print("Generating TTS audio...")
    tts_prefix = os.path.join(config.AUDIO_TMP_DIR, f"q{quiz_id}_{date_str}")

    intro_tts  = f"{tts_prefix}_intro.mp3"
    outro_tts  = f"{tts_prefix}_outro.mp3"
    q_tts_paths = []
    f_tts_paths = []

    generate_tts(intro_text or title, intro_tts)
    generate_tts(outro_text or "Thanks for playing!", outro_tts)

    for i, q in enumerate(questions):
        qp = f"{tts_prefix}_q{i}.mp3"
        fp = f"{tts_prefix}_f{i}.mp3"
        generate_tts(q["q"], qp)
        generate_tts(q.get("f", ""), fp)
        q_tts_paths.append(qp)
        f_tts_paths.append(fp)

    # 4. Build video segments
    print("Building video segments...")
    segments = []

    # --- Intro ---
    intro_dur = max(tts_duration(intro_tts) + 0.5, 5.0)
    intro_frame = build_title_frame(title, intro_text, bg_frame)
    intro_bg    = get_bg_clip(intro_dur)
    intro_text_clip = make_static_clip(intro_frame, intro_dur)
    intro_audio = mix_audio(bg_music_path, intro_tts, None, intro_dur)
    intro_comp  = CompositeVideoClip([intro_bg, intro_text_clip.set_opacity(0.95)])
    if intro_audio:
        intro_comp = intro_comp.set_audio(intro_audio)
    segments.append(intro_comp)

    # --- Questions ---
    for i, q in enumerate(questions):
        print(f"  Building question {i + 1}/{len(questions)}...")
        q_text   = q["q"]
        options  = q["o"]
        correct  = int(q["c"])
        fun_fact = q.get("f", "")

        # Phase A: show question (TTS narration)
        a_dur = tts_duration(q_tts_paths[i]) + 0.5
        a_frame = build_question_frame(q_text, options, bg_frame)
        a_bg    = get_bg_clip(a_dur)
        a_fg    = make_static_clip(a_frame, a_dur)
        a_audio = mix_audio(bg_music_path, q_tts_paths[i], None, a_dur)
        a_comp  = CompositeVideoClip([a_bg, a_fg.set_opacity(0.95)])
        if a_audio:
            a_comp = a_comp.set_audio(a_audio)
        segments.append(a_comp)

        # Phase B: timer countdown (10s)
        b_dur  = float(config.TIMER_DURATION)
        b_bg   = get_bg_clip(b_dur)
        b_timer = make_timer_clip(q_text, options, bg_frame, b_dur)
        b_audio = mix_audio(bg_music_path, None, None, b_dur)
        b_comp  = CompositeVideoClip([b_bg, b_timer.set_opacity(0.95)])
        if b_audio:
            b_comp = b_comp.set_audio(b_audio)
        segments.append(b_comp)

        # Phase C: answer reveal + fun fact
        c_dur  = tts_duration(f_tts_paths[i]) + 1.5
        c_frame = build_question_frame(q_text, options, bg_frame, reveal_index=correct, fun_fact=fun_fact)
        c_bg    = get_bg_clip(c_dur)
        c_fg    = make_static_clip(c_frame, c_dur)
        c_audio = mix_audio(bg_music_path, f_tts_paths[i], correct_path, c_dur, sfx_start=0.0)
        c_comp  = CompositeVideoClip([c_bg, c_fg.set_opacity(0.95)])
        if c_audio:
            c_comp = c_comp.set_audio(c_audio)
        segments.append(c_comp)

    # --- Outro ---
    outro_dur  = max(tts_duration(outro_tts) + 0.5, 5.0)
    outro_frame = build_title_frame(title, outro_text, bg_frame)
    outro_bg    = get_bg_clip(outro_dur)
    outro_fg    = make_static_clip(outro_frame, outro_dur)
    outro_audio = mix_audio(bg_music_path, outro_tts, None, outro_dur)
    outro_comp  = CompositeVideoClip([outro_bg, outro_fg.set_opacity(0.95)])
    if outro_audio:
        outro_comp = outro_comp.set_audio(outro_audio)
    segments.append(outro_comp)

    # 5. Concatenate & export
    print("Concatenating and exporting video (this may take a while)...")
    final = concatenate_videoclips(segments, method="compose")
    final.write_videofile(
        output_path,
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="5000k",
        audio_bitrate="192k",
        threads=4,
        logger="bar",
    )

    # 6. Generate thumbnail
    thumb_path = os.path.join(config.THUMB_DIR, f"quiz_{quiz_id}_{date_str}.jpg")
    _make_thumbnail(title, bg_frame, thumb_path)

    print(f"Video saved: {output_path}")
    print(f"Thumbnail:   {thumb_path}")

    if use_video_bg:
        bg_clip_src.close()
    final.close()

    return output_path


def _make_thumbnail(title: str, bg_frame: np.ndarray, out_path: str):
    W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img  = Image.fromarray(dark_overlay(bg_frame, 0.4))
    draw = ImageDraw.Draw(img)
    font = load_font(config.FONT_TITLE, 110)

    lines = wrap_text(title, font, W - 200)
    y = (H - len(lines) * 130) // 2
    for line in lines:
        bbox = font.getbbox(line)
        x = (W - (bbox[2] - bbox[0])) // 2
        # Thick shadow
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                draw.text((x + dx, y + dy), line, font=font, fill="#000000")
        draw.text((x, y), line, font=font, fill="#ffffff")
        y += 130

    img.save(out_path, "JPEG", quality=92)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a quiz video from QuizFlix")
    parser.add_argument("--quiz-id", type=int, required=True, help="Quiz ID from the database")
    parser.add_argument("--output", type=str, default=None, help="Output MP4 file path")
    args = parser.parse_args()
    generate_video(args.quiz_id, args.output)
