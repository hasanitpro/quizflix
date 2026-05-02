"""
generate_video.py  —  AZ Quiz Hub video generator

Usage:
    python generate_video.py --quiz-id 1
    python generate_video.py --quiz-id 1 --output my_video.mp4
"""

import argparse
import asyncio
import math
import os
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# moviepy 1.0.3 still references the removed PIL.Image.ANTIALIAS (dropped in Pillow 10)
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    ImageSequenceClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.VideoClip import VideoClip
import numpy as np
import edge_tts

import config

# ---------------------------------------------------------------------------
# Layout constants  (all in pixels at 1920×1080)
# ---------------------------------------------------------------------------

W, H       = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
PANEL_W    = 920           # content panel width  (≈ browser 860px container)
PANEL_X    = (W - PANEL_W) // 2
PANEL_PAD  = 60            # horizontal padding inside panel
OUTPUT_FPS = 24            # encode at 24 fps (saves ~20 % vs 30)
TIMER_FPS  = 5             # timer animation rate — arc only needs ~5 fps

# Option gradient colours (matching browser CSS)
# Each entry: (colour_left, colour_right) as RGB tuples
OPT_GRADIENTS = [
    ((231, 76,  60),  (192, 57,  43)),   # A — red
    ((52,  152, 219), (41,  128, 185)),  # B — blue
    ((46,  204, 113), (39,  174, 96)),   # C — green
    ((241, 196, 15),  (243, 156, 18)),   # D — yellow
]
CORRECT_GRADIENT = ((0, 200, 100), (0, 150, 70))


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(name, size)
    except OSError:
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


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

def dark_overlay(frame: np.ndarray, alpha: float = 0.70) -> np.ndarray:
    """Darken a frame to approximate browser's #07091a background."""
    return (frame * (1 - alpha)).astype(np.uint8)


def get_background_frame(bg_path: str | None) -> np.ndarray:
    if bg_path and os.path.exists(bg_path):
        ext = Path(bg_path).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            img = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
            return np.array(img)
    return np.array(Image.new("RGB", (W, H), "#07091a"))


# ---------------------------------------------------------------------------
# RGBA drawing helpers
# ---------------------------------------------------------------------------

def _paste_gradient_rect(img_rgba: Image.Image, x1: int, y1: int, x2: int, y2: int,
                          col1: tuple, col2: tuple, radius: int = 14, alpha: int = 178):
    """Paste a horizontal-gradient rounded rectangle into an RGBA image."""
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return

    # Gradient array  (shape: bh × bw × 3)
    t   = np.linspace(0, 1, bw, dtype=np.float32)
    rgb = np.stack([
        (col1[c] * (1 - t) + col2[c] * t).astype(np.uint8)
        for c in range(3)
    ], axis=1)                            # bw × 3
    grad_rgb = np.tile(rgb[np.newaxis], (bh, 1, 1))  # bh × bw × 3

    # Rounded-rectangle alpha mask
    mask_img = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask_img).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=radius, fill=255)
    mask = (np.array(mask_img) * alpha // 255).astype(np.uint8)

    grad_rgba = np.dstack([grad_rgb, mask])           # bh × bw × 4
    patch = Image.fromarray(grad_rgba, "RGBA")
    img_rgba.alpha_composite(patch, dest=(x1, y1))


def _draw_glass_panel(img_rgba: Image.Image, x: int, y: int, w: int, h: int,
                      radius: int = 22):
    """Draw a semi-transparent dark 'glass' panel with a subtle border."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                        fill=(10, 10, 35, 210), outline=(255, 255, 255, 28), width=1)
    img_rgba.alpha_composite(overlay)


# ---------------------------------------------------------------------------
# Frame builders — return RGBA PIL Images (transparent background)
# ---------------------------------------------------------------------------

def build_question_overlay(
    question: str,
    options: list[str],
    q_idx: int | None    = None,
    total_q: int | None  = None,
    reveal_index: int | None = None,
    fun_fact: str | None = None,
) -> Image.Image:
    """
    Renders the quiz question UI as an RGBA overlay (transparent background).
    Matches the browser glassmorphism card layout.
    """
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_label = load_font(config.FONT_OPTIONS,   30)
    f_q     = load_font(config.FONT_QUESTION,  56)
    f_opt   = load_font(config.FONT_OPTIONS,   40)
    f_badge = load_font(config.FONT_TITLE,     34)
    f_ff    = load_font(config.FONT_OPTIONS,   34)

    cx      = PANEL_X + PANEL_PAD          # content left edge
    cw      = PANEL_W - PANEL_PAD * 2      # content width
    panel_y = 60
    panel_h = H - 80

    # Glass panel
    _draw_glass_panel(img, PANEL_X, panel_y, PANEL_W, panel_h)
    draw = ImageDraw.Draw(img)

    y = panel_y + 36

    # Progress bar + "QUESTION X / Y"
    if q_idx is not None and total_q:
        bar_h = 4
        draw.rounded_rectangle([cx, y, cx + cw, y + bar_h],
                                radius=2, fill=(255, 255, 255, 25))
        fill_w = int(cw * q_idx / total_q)
        if fill_w > 0:
            draw.rounded_rectangle([cx, y, cx + fill_w, y + bar_h],
                                    radius=2, fill=(0, 212, 255, 220))
        y += bar_h + 16

        label = f"QUESTION  {q_idx} / {total_q}"
        lb    = f_label.getbbox(label)
        lw    = lb[2] - lb[0]
        draw.text(((W - lw) // 2, y), label, font=f_label, fill=(0, 212, 255, 180))
        y += (lb[3] - lb[1]) + 22

    # Question text
    lines = wrap_text(question, f_q, cw)
    for line in lines:
        bb  = f_q.getbbox(line)
        lw  = bb[2] - bb[0]
        # Shadow
        draw.text(((W - lw) // 2 + 3, y + 3), line, font=f_q, fill=(0, 0, 0, 180))
        draw.text(((W - lw) // 2,     y),     line, font=f_q, fill=(255, 255, 255, 255))
        y += (bb[3] - bb[1]) + 14
    y += 26

    # Option cards — 2 × 2 grid
    gap   = 18
    box_w = (cw - gap) // 2
    box_h = 108

    for i, (opt, lbl) in enumerate(zip(options, "ABCD")):
        col = i % 2
        row = i // 2
        ox  = cx  + col * (box_w + gap)
        oy  = y   + row * (box_h + gap)
        ox2 = ox  + box_w
        oy2 = oy  + box_h

        grad = CORRECT_GRADIENT if (reveal_index is not None and i == reveal_index) \
               else OPT_GRADIENTS[i]
        _paste_gradient_rect(img, ox, oy, ox2, oy2, grad[0], grad[1], radius=14, alpha=178)
        draw = ImageDraw.Draw(img)

        # Glow border on correct answer
        if reveal_index is not None and i == reveal_index:
            for off in range(1, 5):
                draw.rounded_rectangle(
                    [ox - off, oy - off, ox2 + off, oy2 + off],
                    radius=14 + off, outline=(0, 255, 136, max(0, 110 - off * 28)), width=1,
                )

        # Card border
        draw.rounded_rectangle([ox, oy, ox2, oy2], radius=14,
                                outline=(255, 255, 255, 30), width=1)

        # Letter badge circle
        badge_r = 19
        bcx = ox + 22 + badge_r
        bcy = oy + box_h // 2
        draw.ellipse([bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r],
                     fill=(255, 255, 255, 50))
        bb = f_badge.getbbox(lbl)
        draw.text((bcx - (bb[2] - bb[0]) // 2, bcy - (bb[3] - bb[1]) // 2),
                  lbl, font=f_badge, fill=(255, 255, 255, 255))

        # Option text
        text_x = bcx + badge_r + 14
        text_w = ox2 - text_x - 12
        opt_lines = wrap_text(opt, f_opt, text_w)
        oty = oy + (box_h - len(opt_lines) * 50) // 2
        for ol in opt_lines:
            draw.text((text_x, oty), ol, font=f_opt, fill=(255, 255, 255, 255))
            oty += 50

    # Fun-fact strip
    if fun_fact:
        ff_lines = wrap_text(f"Fun Fact:  {fun_fact}", f_ff, cw - 20)
        strip_h  = len(ff_lines) * 46 + 20
        strip_y  = panel_y + panel_h - strip_h - 16
        overlay2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(overlay2).rounded_rectangle(
            [PANEL_X + 16, strip_y - 10, PANEL_X + PANEL_W - 16, strip_y + strip_h],
            radius=12, fill=(255, 229, 102, 28), outline=(255, 229, 102, 60), width=1,
        )
        img.alpha_composite(overlay2)
        draw = ImageDraw.Draw(img)
        fy = strip_y
        for fl in ff_lines:
            bb  = f_ff.getbbox(fl)
            fx  = (W - (bb[2] - bb[0])) // 2
            draw.text((fx, fy), fl, font=f_ff, fill=(255, 229, 102, 240))
            fy += 46

    return img


def build_title_overlay(title: str, subtitle: str) -> Image.Image:
    """RGBA overlay for intro / outro title screen."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_title = load_font(config.FONT_TITLE,   86)
    f_sub   = load_font(config.FONT_OPTIONS, 44)

    pw = min(PANEL_W + 80, W - 160)
    px = (W - pw) // 2
    py = H // 4

    _draw_glass_panel(img, px, py, pw, H // 2, radius=24)
    draw = ImageDraw.Draw(img)

    y = py + 60
    for line in wrap_text(title, f_title, pw - 100):
        bb = f_title.getbbox(line)
        lw = bb[2] - bb[0]
        draw.text(((W - lw) // 2 + 3, y + 3), line, font=f_title, fill=(0, 0, 0, 180))
        draw.text(((W - lw) // 2,     y),     line, font=f_title, fill=(255, 255, 255, 255))
        y += (bb[3] - bb[1]) + 18

    if subtitle:
        y += 22
        for line in wrap_text(subtitle, f_sub, pw - 120):
            bb = f_sub.getbbox(line)
            lw = bb[2] - bb[0]
            draw.text(((W - lw) // 2, y), line, font=f_sub, fill=(200, 220, 255, 210))
            y += (bb[3] - bb[1]) + 12

    return img


# ---------------------------------------------------------------------------
# Compositing helper
# ---------------------------------------------------------------------------

def composite_bg_overlay(bg_arr: np.ndarray, overlay_rgba: Image.Image) -> np.ndarray:
    """Darken bg and alpha-composite the RGBA overlay on top."""
    bg = Image.fromarray(dark_overlay(bg_arr, 0.70)).convert("RGBA")
    bg.alpha_composite(overlay_rgba)
    return np.array(bg.convert("RGB"))


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
# Segment builders
# ---------------------------------------------------------------------------

def make_static_clip(bg_frames: list, overlay: Image.Image, loop_fps: float,
                     duration: float) -> ImageSequenceClip:
    """
    Pre-composites a static RGBA overlay with the looping bg frames and
    returns an ImageSequenceClip. Avoids Python-level compositing at write time.
    """
    n_unique = len(bg_frames)
    # Render only the unique loop frames once
    unique = [composite_bg_overlay(bg_frames[i], overlay) for i in range(n_unique)]
    n      = max(1, math.ceil(duration * loop_fps))
    frames = [unique[i % n_unique] for i in range(n)]
    return ImageSequenceClip(frames, fps=loop_fps)


def _draw_timer_on(img_arr: np.ndarray, seconds_left: float, total: float) -> np.ndarray:
    """Draw timer circle + number on a copy of img_arr; returns new array."""
    img  = Image.fromarray(img_arr.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Timer positioned at top-right of the panel
    cx = PANEL_X + PANEL_W - 80
    cy = 60 + 80   # panel_y + offset
    r  = 62

    # Colour by urgency (matches browser: cyan → yellow → red)
    if seconds_left > 5:
        arc_color = (0, 212, 255, 230)
    elif seconds_left > 2:
        arc_color = (255, 183, 0, 230)
    else:
        arc_color = (255, 68, 68, 230)

    # Background circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 170))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 22), width=2)

    # Arc
    fraction = seconds_left / total
    if fraction > 0.001:
        end_angle = -90 + 360 * fraction
        draw.arc([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8],
                 start=-90, end=end_angle, fill=arc_color, width=8)

    # Number
    f_timer = load_font(config.FONT_TITLE, 54)
    num     = str(math.ceil(seconds_left))
    bb      = f_timer.getbbox(num)
    draw.text((cx - (bb[2] - bb[0]) // 2, cy - (bb[3] - bb[1]) // 2),
              num, font=f_timer, fill=(255, 255, 255, 255))

    return np.array(img.convert("RGB"))


def make_timer_clip(
    base_arr: np.ndarray,       # pre-composited base (bg + question overlay)
    duration: float = 10.0,
) -> ImageSequenceClip:
    """
    Pre-renders timer frames at TIMER_FPS by drawing only the arc+number
    on top of the already-composited base frame.
    """
    n_frames = max(1, int(duration * TIMER_FPS)) + 1
    frames   = []
    for i in range(n_frames):
        t         = i / TIMER_FPS
        remaining = max(0.0, duration - t)
        frames.append(_draw_timer_on(base_arr, remaining, duration))
    return ImageSequenceClip(frames, fps=TIMER_FPS)


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
        if music.duration < total_duration:
            from moviepy.audio.AudioClip import concatenate_audioclips
            loops = math.ceil(total_duration / music.duration)
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
    resp = requests.get(f"{config.QUIZ_API_BASE}/api/get-quiz.php",
                        params={"id": quiz_id}, timeout=10)
    resp.raise_for_status()
    quiz = resp.json()

    title       = quiz.get("title", "Quiz")
    intro_text  = quiz.get("introText",  "")
    outro_text  = quiz.get("outroText",  "")
    bg_file     = quiz.get("backgroundImage", "")
    bg_music    = quiz.get("bgMusic",     "")
    correct_snd = quiz.get("correctSound","")
    questions   = quiz.get("questions",  [])
    total_q     = len(questions)

    def media(name):
        return os.path.join(config.MEDIA_DIR, name) if name else None

    bg_path       = media(bg_file)
    bg_music_path = media(bg_music)
    correct_path  = media(correct_snd)

    # 2. Load background — for video files pre-extract all loop frames into RAM
    #    then close the reader before write_videofile starts to avoid concurrent
    #    ffmpeg subprocess conflicts on Windows.
    bg_ext      = Path(bg_file).suffix.lower() if bg_file else ""
    use_video_bg = bg_ext == ".mp4" and bg_path and os.path.exists(bg_path)

    if use_video_bg:
        _raw      = VideoFileClip(bg_path)
        _src_fps  = _raw.fps or 25.0
        _loop_fps = min(_src_fps, 15.0)
        _loop_dur = min(_raw.duration, 2.0)
        _interval = 1.0 / _loop_fps

        bg_frames = []
        t = 0.0
        while t < _loop_dur:
            frame   = _raw.get_frame(t)
            resized = Image.fromarray(frame).resize((W, H), Image.LANCZOS)
            bg_frames.append(np.array(resized))
            t += _interval
        _raw.close()
        print(f"Video background: {len(bg_frames)} frames @ {_loop_fps:.0f} fps")
    else:
        single = get_background_frame(bg_path)
        bg_frames = [single]
        _loop_fps = 1.0

    # Static bg_frame (first frame) used for thumbnail
    bg_frame = bg_frames[0]

    # 3. Generate TTS files
    print("Generating TTS audio…")
    tts_prefix  = os.path.join(config.AUDIO_TMP_DIR, f"q{quiz_id}_{date_str}")
    intro_tts   = f"{tts_prefix}_intro.mp3"
    outro_tts   = f"{tts_prefix}_outro.mp3"
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
    print("Building video segments…")
    segments = []

    # --- Intro ---
    intro_dur     = max(tts_duration(intro_tts) + 0.5, 5.0)
    intro_overlay = build_title_overlay(title, intro_text)
    intro_clip    = make_static_clip(bg_frames, intro_overlay, _loop_fps, intro_dur)
    intro_audio   = mix_audio(bg_music_path, intro_tts, None, intro_dur)
    if intro_audio:
        intro_clip = intro_clip.set_audio(intro_audio)
    segments.append(intro_clip)

    # --- Questions ---
    for i, q in enumerate(questions):
        print(f"  Building question {i + 1}/{total_q}…")
        q_text   = q["q"]
        options  = q["o"]
        correct  = int(q["c"])
        fun_fact = q.get("f", "")
        q_num    = i + 1

        # Phase A: question read-aloud (TTS narration)
        a_overlay = build_question_overlay(q_text, options, q_num, total_q)
        a_dur     = tts_duration(q_tts_paths[i]) + 0.5
        a_clip    = make_static_clip(bg_frames, a_overlay, _loop_fps, a_dur)
        a_audio   = mix_audio(bg_music_path, q_tts_paths[i], None, a_dur)
        if a_audio:
            a_clip = a_clip.set_audio(a_audio)
        segments.append(a_clip)

        # Phase B: timer countdown
        # Build base frame (bg composited with question overlay) once, then
        # add only the animated arc per TIMER_FPS frame — ~20× fewer PIL draws.
        b_dur       = float(config.TIMER_DURATION)
        b_base_arr  = composite_bg_overlay(bg_frames[0], a_overlay)
        b_timer     = make_timer_clip(b_base_arr, b_dur)
        b_audio     = mix_audio(bg_music_path, None, None, b_dur)
        if b_audio:
            b_timer = b_timer.set_audio(b_audio)
        segments.append(b_timer)

        # Phase C: answer reveal + fun fact
        c_overlay = build_question_overlay(q_text, options, q_num, total_q,
                                           reveal_index=correct, fun_fact=fun_fact)
        c_dur     = tts_duration(f_tts_paths[i]) + 1.5
        c_clip    = make_static_clip(bg_frames, c_overlay, _loop_fps, c_dur)
        c_audio   = mix_audio(bg_music_path, f_tts_paths[i], correct_path, c_dur)
        if c_audio:
            c_clip = c_clip.set_audio(c_audio)
        segments.append(c_clip)

    # --- Outro ---
    outro_dur     = max(tts_duration(outro_tts) + 0.5, 5.0)
    outro_overlay = build_title_overlay(title, outro_text)
    outro_clip    = make_static_clip(bg_frames, outro_overlay, _loop_fps, outro_dur)
    outro_audio   = mix_audio(bg_music_path, outro_tts, None, outro_dur)
    if outro_audio:
        outro_clip = outro_clip.set_audio(outro_audio)
    segments.append(outro_clip)

    # 5. Concatenate & export
    print("Concatenating and exporting video…")
    final      = concatenate_videoclips(segments, method="compose")
    temp_audio = os.path.join(config.OUTPUT_DIR, f"quiz_{quiz_id}_{date_str}_snd.m4a")
    final.write_videofile(
        output_path,
        fps=OUTPUT_FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        audio_bitrate="192k",
        temp_audiofile=temp_audio,
        remove_temp=True,
        logger=None,
    )

    # 6. Generate thumbnail
    thumb_path = os.path.join(config.THUMB_DIR, f"quiz_{quiz_id}_{date_str}.jpg")
    _make_thumbnail(title, bg_frame, thumb_path)

    print(f"Video saved:  {output_path}")
    print(f"Thumbnail:    {thumb_path}")

    final.close()
    return output_path


def _make_thumbnail(title: str, bg_frame: np.ndarray, out_path: str):
    img  = Image.fromarray(dark_overlay(bg_frame, 0.55))
    draw = ImageDraw.Draw(img)
    font = load_font(config.FONT_TITLE, 110)

    lines = wrap_text(title, font, W - 200)
    y = (H - len(lines) * 130) // 2
    for line in lines:
        bb = font.getbbox(line)
        x  = (W - (bb[2] - bb[0])) // 2
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
    parser = argparse.ArgumentParser(description="Generate a quiz video from AZ Quiz Hub")
    parser.add_argument("--quiz-id", type=int, required=True)
    parser.add_argument("--output",  type=str, default=None)
    args = parser.parse_args()
    generate_video(args.quiz_id, args.output)
