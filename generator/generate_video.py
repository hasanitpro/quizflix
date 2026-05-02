"""
generate_video.py  —  AZ Quiz Hub video generator

Renders frames that replicate the browser quiz interface:
  dark #07091a background + purple/blue/cyan radial gradient blobs
  glassmorphism question card  (blurred bg + semi-transparent panel)
  logo top-left  |  progress bar above card  |  timer centred below options
"""

import argparse
import asyncio
import math
import os
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageSequenceClip,
    VideoFileClip,
    concatenate_videoclips,
)
import numpy as np
import edge_tts

import config

# ---------------------------------------------------------------------------
# Layout  (all px, 1920 × 1080 target)
# ---------------------------------------------------------------------------

W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT

PANEL_W    = 1280          # content panel — ~1.5× the browser's 860px container
PANEL_X    = (W - PANEL_W) // 2   # = 320
PANEL_PAD  = 52            # horizontal padding inside panel

# Progress bar sits above the panel
PROG_Y     = 68            # top of "QUESTION X / Y" label
BAR_Y      = 97            # top of the progress bar track
BAR_H      = 6
PANEL_Y    = 122           # panel top

# Option grid
OPT_COLS   = 2
OPT_GAP    = 18
OPT_H      = 100
BADGE_R    = 26            # radius of letter-badge circle (diameter 52px)

# Timer  (below options, centred)
TIMER_R    = 62            # arc radius  (total diameter 124px ≈ 82px×1.5)

# Font sizes
FS_META    = 22
FS_Q       = 46
FS_OPT     = 28
FS_BADGE   = 24
FS_FF      = 28
FS_TIMER   = 52
FS_TITLE   = 82
FS_SUB     = 42

OUTPUT_FPS = 24
TIMER_FPS  = 5

# Option gradient colours  (matches browser CSS exactly)
OPT_GRADS = [
    ((231, 76,  60),  (192, 57,  43)),   # A red
    ((52,  152, 219), (41,  128, 185)),  # B blue
    ((46,  204, 113), (39,  174, 96)),   # C green
    ((241, 196, 15),  (243, 156, 18)),   # D yellow
]
CORRECT_GRAD = ((0, 200, 100), (0, 150, 70))


# ---------------------------------------------------------------------------
# Font loader  (tries Fredoka from MEDIA_DIR first, falls back to arial)
# ---------------------------------------------------------------------------

def _find_fredoka() -> str | None:
    for candidate in [
        os.path.join(config.MEDIA_DIR, "Fredoka-SemiBold.ttf"),
        os.path.join(config.MEDIA_DIR, "Fredoka.ttf"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None

_FREDOKA = _find_fredoka()


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Try Fredoka for title/heading fonts, fall back to the configured name."""
    if _FREDOKA and name in (config.FONT_TITLE, config.FONT_QUESTION):
        try:
            return ImageFont.truetype(_FREDOKA, size)
        except OSError:
            pass
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        bb   = font.getbbox(test)
        if bb[2] - bb[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

def _add_gradient_blobs(frame: np.ndarray) -> np.ndarray:
    """
    Add the three radial gradient blobs from the browser's body::before CSS:
      purple  @ 15% 40%   rgba(100,20,180,0.55)
      blue    @ 85% 15%   rgba(10,80,180,0.50)
      cyan    @ 55% 85%   rgba(5,140,200,0.35)
    """
    result = frame.astype(np.float32)
    y_idx, x_idx = np.mgrid[0:H, 0:W]

    def blob(cx_frac, cy_frac, rx_frac, ry_frac, strength, rgb):
        cx  = W * cx_frac;  cy  = H * cy_frac
        rx  = W * rx_frac;  ry  = H * ry_frac
        d   = np.sqrt(((x_idx - cx) / rx) ** 2 + ((y_idx - cy) / ry) ** 2)
        a   = np.clip(1.0 - d / 0.65, 0, 1) * strength
        a3  = a[:, :, np.newaxis]
        result[:, :, 0] += a3[:, :, 0] * rgb[0]
        result[:, :, 1] += a3[:, :, 0] * rgb[1]
        result[:, :, 2] += a3[:, :, 0] * rgb[2]

    blob(0.15, 0.40, 0.40, 0.30, 0.55, (100, 20, 180))   # purple
    blob(0.85, 0.15, 0.35, 0.25, 0.50, (10,  80, 180))   # blue
    blob(0.55, 0.85, 0.30, 0.35, 0.35, (5,  140, 200))   # cyan

    return np.clip(result, 0, 255).astype(np.uint8)


def _prepare_bg_frame(raw: np.ndarray) -> np.ndarray:
    """Darken the raw video frame and add the CSS gradient blobs."""
    dark = (raw * 0.28).astype(np.uint8)    # heavy darken → near #07091a
    return _add_gradient_blobs(dark)


def get_background_frame(bg_path: str | None) -> np.ndarray:
    if bg_path and os.path.exists(bg_path):
        ext = Path(bg_path).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            img = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
            return _prepare_bg_frame(np.array(img))
    base = np.full((H, W, 3), [7, 9, 26], dtype=np.uint8)
    return _add_gradient_blobs(base)


# ---------------------------------------------------------------------------
# Glass panel helper
# ---------------------------------------------------------------------------

def _apply_glass_panel(img_pil: Image.Image, x: int, y: int, w: int, h: int,
                        blur_r: int = 18, radius: int = 22) -> Image.Image:
    """
    Simulate backdrop-filter: blur() + rgba(255,255,255,0.055) panel.
    1. Blur the bg region.
    2. Paste a semi-transparent light overlay.
    """
    # 1. Blur the region behind the panel
    region  = img_pil.crop((x, y, x + w, y + h))
    blurred = region.filter(ImageFilter.GaussianBlur(blur_r))
    result  = img_pil.copy()
    result.paste(blurred, (x, y))

    # 2. Semi-transparent glass overlay  (rgba(255,255,255,0.055) = alpha 14)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d       = ImageDraw.Draw(overlay)
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                         fill=(255, 255, 255, 14),
                         outline=(255, 255, 255, 28), width=1)
    return Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")


# ---------------------------------------------------------------------------
# Gradient rect helper
# ---------------------------------------------------------------------------

def _paste_gradient_rect(img_rgba: Image.Image,
                          x1: int, y1: int, x2: int, y2: int,
                          col1: tuple, col2: tuple,
                          radius: int = 14, alpha: int = 178):
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return
    t    = np.linspace(0, 1, bw, dtype=np.float32)
    rows = np.stack([(col1[c]*(1-t) + col2[c]*t).astype(np.uint8) for c in range(3)], axis=1)
    grad_rgb = np.tile(rows[np.newaxis], (bh, 1, 1))

    mask_img = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask_img).rounded_rectangle([0, 0, bw-1, bh-1], radius=radius, fill=255)
    mask = (np.array(mask_img) * alpha // 255).astype(np.uint8)

    patch = Image.fromarray(np.dstack([grad_rgb, mask]), "RGBA")
    img_rgba.alpha_composite(patch, dest=(x1, y1))


# ---------------------------------------------------------------------------
# Logo helper
# ---------------------------------------------------------------------------

def _paste_logo(img_rgba: Image.Image):
    if not os.path.exists(config.LOGO_PATH):
        return
    try:
        logo   = Image.open(config.LOGO_PATH).convert("RGBA")
        logo_w = 150
        logo_h = int(logo.height * logo_w / logo.width)
        logo   = logo.resize((logo_w, logo_h), Image.LANCZOS)
        img_rgba.alpha_composite(logo, dest=(24, 18))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Frame builders  (return RGBA PIL, transparent background)
# ---------------------------------------------------------------------------

def _draw_progress(draw: ImageDraw.Draw, q_idx: int, total_q: int):
    """Thin progress bar + label above the panel (matches browser #quiz-progress)."""
    cx   = PANEL_X + PANEL_PAD
    cw   = PANEL_W - PANEL_PAD * 2
    font = load_font(config.FONT_OPTIONS, FS_META)

    lbl  = f"QUESTION  {q_idx} / {total_q}"
    bb   = font.getbbox(lbl)
    lw   = bb[2] - bb[0]
    draw.text(((W - lw) // 2, PROG_Y), lbl, font=font, fill=(0, 212, 255, 190))

    # Track
    draw.rounded_rectangle([cx, BAR_Y, cx + cw, BAR_Y + BAR_H],
                             radius=3, fill=(255, 255, 255, 25))
    # Fill (cyan → purple gradient approximated as solid cyan)
    fill_w = max(4, int(cw * q_idx / total_q))
    draw.rounded_rectangle([cx, BAR_Y, cx + fill_w, BAR_Y + BAR_H],
                             radius=3, fill=(0, 212, 255, 220))


def build_question_overlay(
    question: str,
    options: list[str],
    q_idx:   int | None  = None,
    total_q: int | None  = None,
    reveal_index: int | None = None,
    fun_fact:     str | None = None,
    show_timer_placeholder: bool = False,
) -> tuple[Image.Image, int, int, int]:
    """
    Returns (overlay_rgba, panel_x, panel_y, panel_h).
    panel_y is computed dynamically so callers know where to draw the timer.
    """
    f_meta  = load_font(config.FONT_OPTIONS,   FS_META)
    f_q     = load_font(config.FONT_QUESTION,  FS_Q)
    f_opt   = load_font(config.FONT_OPTIONS,   FS_OPT)
    f_badge = load_font(config.FONT_TITLE,     FS_BADGE)
    f_ff    = load_font(config.FONT_OPTIONS,   FS_FF)

    cx  = PANEL_X + PANEL_PAD           # content left
    cw  = PANEL_W - PANEL_PAD * 2       # content width

    # --- Measure content height ---
    q_lines   = wrap_text(question, f_q, cw)
    q_h       = len(q_lines) * (FS_Q + 10) - 10
    opts_rows = math.ceil(len(options) / OPT_COLS)
    opts_h    = opts_rows * OPT_H + (opts_rows - 1) * OPT_GAP
    timer_h   = (TIMER_R * 2 + 24) if not fun_fact else 0  # timer OR fact

    ff_h = 0
    if fun_fact:
        ff_lines = wrap_text(f"Fun Fact:  {fun_fact}", f_ff, cw - 20)
        ff_h = len(ff_lines) * (FS_FF + 8) + 28

    # Total inside panel
    inner_h = (FS_META + 20        # meta label
               + q_h    + 28       # question
               + opts_h + 26       # options
               + timer_h + (8 if not fun_fact else 0)
               + ff_h)
    panel_h = inner_h + PANEL_PAD * 2

    # Center panel vertically, shift down to leave room for progress bar
    p_y = max(PANEL_Y, (H - panel_h) // 2 + 20)

    # --- Build RGBA image ---
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Progress bar
    if q_idx is not None and total_q:
        _draw_progress(draw, q_idx, total_q)

    # Panel outline (glass drawn on bg later; here just content overlay)
    draw.rounded_rectangle([PANEL_X, p_y, PANEL_X + PANEL_W, p_y + panel_h],
                             radius=22, outline=(255, 255, 255, 28), width=1)

    y = p_y + PANEL_PAD

    # Question meta  ("Question X of Y")
    if q_idx is not None and total_q:
        meta = f"Question {q_idx} of {total_q}"
        bb   = f_meta.getbbox(meta)
        draw.text(((W - (bb[2]-bb[0])) // 2, y), meta,
                  font=f_meta, fill=(0, 212, 255, 200))
    y += FS_META + 20

    # Question text
    for line in q_lines:
        bb = f_q.getbbox(line)
        lw = bb[2] - bb[0]
        tx = (W - lw) // 2
        # Deep shadow + subtle blue-purple glow
        draw.text((tx+4, y+4), line, font=f_q, fill=(0, 0, 0, 180))
        draw.text((tx+2, y+2), line, font=f_q, fill=(30, 20, 80, 100))
        draw.text((tx,   y),   line, font=f_q, fill=(255, 255, 255, 255))
        y += FS_Q + 10
    y += 18

    # Options 2 × 2 grid
    opt_w = (cw - OPT_GAP) // OPT_COLS
    for i, (opt, lbl) in enumerate(zip(options, "ABCD")):
        col = i % OPT_COLS
        row = i // OPT_COLS
        ox  = cx + col * (opt_w + OPT_GAP)
        oy  = y  + row * (OPT_H + OPT_GAP)
        ox2 = ox + opt_w
        oy2 = oy + OPT_H

        grad = CORRECT_GRAD if (reveal_index is not None and i == reveal_index) \
               else OPT_GRADS[i]
        _paste_gradient_rect(img, ox, oy, ox2, oy2, grad[0], grad[1], radius=14, alpha=178)
        draw = ImageDraw.Draw(img)

        # Glow on correct
        if reveal_index is not None and i == reveal_index:
            for off in range(1, 5):
                draw.rounded_rectangle(
                    [ox-off, oy-off, ox2+off, oy2+off],
                    radius=14+off, outline=(0, 255, 136, max(0, 110-off*28)), width=1)

        # Card border
        draw.rounded_rectangle([ox, oy, ox2, oy2], radius=14,
                                outline=(255, 255, 255, 30), width=1)

        # Letter badge circle
        bcx = ox + 22 + BADGE_R
        bcy = oy + OPT_H // 2
        draw.ellipse([bcx-BADGE_R, bcy-BADGE_R, bcx+BADGE_R, bcy+BADGE_R],
                     fill=(255,255,255,55), outline=(255,255,255,180), width=2)
        bb = f_badge.getbbox(lbl)
        bx = bcx-(bb[2]-bb[0])//2
        by = bcy-(bb[3]-bb[1])//2
        draw.text((bx+1, by+1), lbl, font=f_badge, fill=(0,0,0,120))
        draw.text((bx, by),     lbl, font=f_badge, fill=(255,255,255,255))

        # Option text
        tx  = bcx + BADGE_R + 14
        tw  = ox2 - tx - 14
        olines = wrap_text(opt, f_opt, tw)
        oty = oy + (OPT_H - len(olines)*(FS_OPT+6)) // 2
        for ol in olines:
            draw.text((tx, oty), ol, font=f_opt, fill=(255,255,255,255))
            oty += FS_OPT + 6

    y += opts_rows * OPT_H + (opts_rows-1)*OPT_GAP + 26

    # Fun-fact strip (Phase C only)
    if fun_fact:
        ff_lines = wrap_text(f"Fun Fact:  {fun_fact}", f_ff, cw - 20)
        strip_h  = len(ff_lines) * (FS_FF + 8) + 20
        sx1 = PANEL_X + 18;  sx2 = PANEL_X + PANEL_W - 18
        sy1 = y - 8;         sy2 = y + strip_h

        panel2 = Image.new("RGBA", (W, H), (0,0,0,0))
        ImageDraw.Draw(panel2).rounded_rectangle(
            [sx1, sy1, sx2, sy2], radius=14,
            fill=(255,229,102,28), outline=(255,229,102,60), width=1)
        img.alpha_composite(panel2)
        draw = ImageDraw.Draw(img)

        fy = y
        for fl in ff_lines:
            bb  = f_ff.getbbox(fl)
            fx  = (W - (bb[2]-bb[0])) // 2
            draw.text((fx, fy), fl, font=f_ff, fill=(255,229,102,240))
            fy += FS_FF + 8

    # Store timer anchor for Phase B caller
    timer_centre_y = y + TIMER_R + 12   # where _draw_timer_on should centre

    # Logo
    _paste_logo(img)

    return img, PANEL_X, p_y, panel_h, timer_centre_y


def build_title_overlay(title: str, subtitle: str) -> Image.Image:
    """Intro / outro glass card — matches browser .intro-screen / .outro-screen."""
    f_title = load_font(config.FONT_TITLE,   FS_TITLE)
    f_sub   = load_font(config.FONT_OPTIONS, FS_SUB)
    f_brand = load_font(config.FONT_OPTIONS, FS_META + 4)

    pw  = min(PANEL_W + 60, W - 160)
    px  = (W - pw) // 2
    pad = 64

    # Measure height  (+brand label + divider)
    t_lines = wrap_text(title,    f_title, pw - pad*2)
    s_lines = wrap_text(subtitle, f_sub,   pw - pad*2) if subtitle else []
    t_h  = len(t_lines) * (FS_TITLE + 12)
    s_h  = len(s_lines) * (FS_SUB   + 10) + 30 if s_lines else 0
    ph   = pad*2 + t_h + s_h + 52  # +52 for divider + brand line
    py   = (H - ph) // 2

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Panel outline — brighter than question card
    draw.rounded_rectangle([px, py, px+pw, py+ph], radius=24,
                             outline=(255, 255, 255, 40), width=1)

    y = py + pad

    # Title
    for line in t_lines:
        bb = f_title.getbbox(line)
        lw = bb[2] - bb[0]
        tx = (W - lw) // 2
        draw.text((tx+4, y+4), line, font=f_title, fill=(0,  0,  0,   190))
        draw.text((tx+2, y+2), line, font=f_title, fill=(30, 20, 80,  100))
        draw.text((tx,   y),   line, font=f_title, fill=(255,255,255, 255))
        y += FS_TITLE + 12

    # Cyan divider line
    div_pad = pw // 4
    draw.line([(px + div_pad, y + 16), (px + pw - div_pad, y + 16)],
               fill=(0, 212, 255, 90), width=2)
    y += 36

    if s_lines:
        for line in s_lines:
            bb = f_sub.getbbox(line)
            lw = bb[2] - bb[0]
            draw.text(((W-lw)//2, y), line, font=f_sub, fill=(200, 220, 255, 215))
            y += FS_SUB + 10
        y += 10

    # "AZ QUIZ HUB" brand
    brand = "AZ QUIZ HUB"
    bb    = f_brand.getbbox(brand)
    draw.text(((W - (bb[2]-bb[0])) // 2, y + 4),
               brand, font=f_brand, fill=(0, 212, 255, 160))

    _paste_logo(img)
    return img, px, py, ph


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------

def composite_bg_overlay(bg_arr: np.ndarray,
                          overlay_rgba: Image.Image,
                          panel_x: int, panel_y: int,
                          panel_w: int, panel_h: int) -> np.ndarray:
    """
    1. Apply glass blur behind the panel on the bg.
    2. Alpha-composite the RGBA overlay.
    """
    bg  = _apply_glass_panel(Image.fromarray(bg_arr), panel_x, panel_y, panel_w, panel_h)
    bg  = bg.convert("RGBA")
    bg.alpha_composite(overlay_rgba)
    return np.array(bg.convert("RGB"))


def make_static_clip(bg_frames: list, overlay: Image.Image,
                     panel_x: int, panel_y: int, panel_w: int, panel_h: int,
                     loop_fps: float, duration: float) -> ImageSequenceClip:
    n_unique = len(bg_frames)
    unique   = [composite_bg_overlay(bg_frames[i], overlay, panel_x, panel_y, panel_w, panel_h)
                for i in range(n_unique)]
    n      = max(1, math.ceil(duration * loop_fps))
    frames = [unique[i % n_unique] for i in range(n)]
    return ImageSequenceClip(frames, fps=loop_fps)


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

def _draw_timer_on(img_arr: np.ndarray, seconds_left: float, total: float,
                   centre_y: int) -> np.ndarray:
    """Draw the circular timer centred horizontally, at centre_y."""
    img  = Image.fromarray(img_arr.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    cx = W // 2
    cy = centre_y
    r  = TIMER_R
    inner = r - 10

    # Urgency colour
    if seconds_left > 5:
        arc_col = (0, 212, 255, 240)
    elif seconds_left > 2:
        arc_col = (255, 183, 0, 240)
    else:
        arc_col = (255, 68, 68, 240)

    # Outer glow ring (low-opacity, matches browser box-shadow)
    for g in (4, 3, 2):
        draw.ellipse([cx-r-g*3, cy-r-g*3, cx+r+g*3, cy+r+g*3],
                     outline=(*arc_col[:3], 18), width=2)

    # BG circle
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(0, 0, 0, 185))
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(255, 255, 255, 28), width=2)

    # Track ring (matches browser .circle.bg  opacity 0.25)
    draw.ellipse([cx-inner, cy-inner, cx+inner, cy+inner],
                 outline=(255, 255, 255, 50), width=10)

    # Active arc
    if seconds_left > 0.001:
        draw.arc([cx-inner, cy-inner, cx+inner, cy+inner],
                  start=-90, end=-90 + 360*(seconds_left/total),
                  fill=arc_col, width=10)

    # Number
    f  = load_font(config.FONT_TITLE, FS_TIMER)
    n  = str(math.ceil(seconds_left))
    bb = f.getbbox(n)
    nx = cx - (bb[2]-bb[0]) // 2
    ny = cy - (bb[3]-bb[1]) // 2
    # subtle shadow
    draw.text((nx+2, ny+2), n, font=f, fill=(0, 0, 0, 160))
    draw.text((nx, ny),     n, font=f, fill=(255, 255, 255, 255))

    return np.array(img.convert("RGB"))


def make_timer_clip(base_arr: np.ndarray, timer_cy: int,
                    duration: float = 10.0) -> ImageSequenceClip:
    """Pre-render timer frames at TIMER_FPS (arc-only per frame = fast)."""
    n      = max(1, int(duration * TIMER_FPS)) + 1
    frames = []
    for i in range(n):
        t         = i / TIMER_FPS
        remaining = max(0.0, duration - t)
        frames.append(_draw_timer_on(base_arr, remaining, duration, timer_cy))
    return ImageSequenceClip(frames, fps=TIMER_FPS)


# ---------------------------------------------------------------------------
# Progress logger  (silent, no tqdm / stdout)
# ---------------------------------------------------------------------------

class _ProgressLogger:
    def __init__(self, cb, start_pct, end_pct, total_frames):
        self._cb     = cb
        self._start  = start_pct
        self._end    = end_pct
        self._total  = max(1, total_frames)
        self._frame  = 0
        self._stride = max(1, self._total // 60)

    def __call__(self, **changes):
        if 't' not in changes or not self._cb:
            return
        self._frame += 1
        if self._frame % self._stride == 0 or self._frame >= self._total:
            frac = min(1.0, self._frame / self._total)
            pct  = int(self._start + frac * (self._end - self._start))
            self._cb(pct, f"Encoding video… {self._frame} / {self._total} frames")

    def iter_bar(self, **kw):
        bar = next(iter(kw))
        for item in kw[bar]:
            yield item
            self(**{bar: item})

    def warning(self, *a, **kw): pass
    def info(self, *a, **kw):    pass
    def debug(self, *a, **kw):   pass
    def error(self, *a, **kw):   pass


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def mix_audio(bg_path, tts_path, sfx_path, dur, sfx_start=0.0):
    tracks = []
    if bg_path and os.path.exists(bg_path):
        music = AudioFileClip(bg_path).volumex(config.MUSIC_VOLUME)
        if music.duration < dur:
            from moviepy.audio.AudioClip import concatenate_audioclips
            music = concatenate_audioclips([music] * math.ceil(dur / music.duration))
        tracks.append(music.subclip(0, dur))
    if tts_path and os.path.exists(tts_path):
        tracks.append(AudioFileClip(tts_path))
    if sfx_path and os.path.exists(sfx_path):
        tracks.append(AudioFileClip(sfx_path).set_start(sfx_start).volumex(config.SFX_VOLUME))
    return CompositeAudioClip(tracks) if tracks else None


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

async def _tts_async(text, path):
    await edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE).save(path)

def generate_tts(text, path):
    asyncio.run(_tts_async((text or ".").strip(), path))

def tts_duration(path):
    if not os.path.exists(path):
        return 1.0
    c = AudioFileClip(path)
    d = c.duration
    c.close()
    return d


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_video(quiz_id: int, output_path: str | None = None,
                   progress_cb=None) -> str:

    def _rep(pct, lbl):
        if progress_cb:
            try: progress_cb(pct, lbl)
            except Exception: pass

    date_str = datetime.now().strftime("%Y%m%d")
    if output_path is None:
        output_path = os.path.join(config.OUTPUT_DIR, f"quiz_{quiz_id}_{date_str}.mp4")

    # 1. Fetch quiz data
    _rep(2, "Fetching quiz data…")
    resp = requests.get(f"{config.QUIZ_API_BASE}/api/get-quiz.php",
                        params={"id": quiz_id}, timeout=10)
    resp.raise_for_status()
    quiz = resp.json()

    title       = quiz.get("title",           "Quiz")
    intro_text  = quiz.get("introText",        "")
    outro_text  = quiz.get("outroText",        "")
    bg_file     = quiz.get("backgroundImage", "")
    questions   = quiz.get("questions",        [])
    total_q     = len(questions)

    def media(n): return os.path.join(config.MEDIA_DIR, n) if n else None
    bg_path      = media(bg_file)
    bg_music_path = media(quiz.get("bgMusic",      ""))
    correct_path  = media(quiz.get("correctSound", ""))

    # 2. Load background
    _rep(3, "Loading background…")
    bg_ext      = Path(bg_file).suffix.lower() if bg_file else ""
    use_video_bg = bg_ext == ".mp4" and bg_path and os.path.exists(bg_path)

    if use_video_bg:
        _raw      = VideoFileClip(bg_path)
        src_fps   = _raw.fps or 25.0
        loop_fps  = min(src_fps, 15.0)
        loop_dur  = min(_raw.duration, 2.0)
        bg_frames = []
        t = 0.0
        while t < loop_dur:
            raw_f   = _raw.get_frame(t)
            resized = Image.fromarray(raw_f).resize((W, H), Image.LANCZOS)
            bg_frames.append(_prepare_bg_frame(np.array(resized)))
            t += 1.0 / loop_fps
        _raw.close()
        print(f"Video bg: {len(bg_frames)} frames @ {loop_fps:.0f} fps")
    else:
        bg_frames = [get_background_frame(bg_path)]
        loop_fps  = 1.0

    # 3. TTS   (5 → 22 %)
    print("Generating TTS…")
    pfx         = os.path.join(config.AUDIO_TMP_DIR, f"q{quiz_id}_{date_str}")
    intro_tts   = f"{pfx}_intro.mp3"
    outro_tts   = f"{pfx}_outro.mp3"
    q_tts       = []
    f_tts       = []
    total_tts   = 2 + total_q * 2
    tts_done    = 0

    def _trep():
        nonlocal tts_done
        tts_done += 1
        _rep(5 + int(tts_done/total_tts*17), f"Generating speech… ({tts_done}/{total_tts})")

    generate_tts(intro_text or title, intro_tts);              _trep()
    generate_tts(outro_text or "Thanks for playing!", outro_tts); _trep()
    for i, q in enumerate(questions):
        qp = f"{pfx}_q{i}.mp3";  generate_tts(q["q"],          qp); _trep(); q_tts.append(qp)
        fp = f"{pfx}_f{i}.mp3";  generate_tts(q.get("f",""),   fp); _trep(); f_tts.append(fp)

    # 4. Build segments  (23 → 62 %)
    print("Building segments…")
    total_segs = 1 + total_q*3 + 1
    seg_done   = 0

    def _srep(lbl):
        nonlocal seg_done
        seg_done += 1
        _rep(23 + int(seg_done/total_segs*39), lbl)

    segments = []

    def _clip(overlay_tuple, dur, tts_p=None, sfx_p=None):
        """Build a pre-composited ImageSequenceClip with optional audio."""
        ov, px, py, ph, _ = overlay_tuple
        c = make_static_clip(bg_frames, ov, px, py, PANEL_W, ph, loop_fps, dur)
        a = mix_audio(bg_music_path, tts_p, sfx_p, dur)
        return c.set_audio(a) if a else c

    # --- Intro ---
    i_dur  = max(tts_duration(intro_tts) + 0.5, 5.0)
    i_ov   = build_title_overlay(title, intro_text)
    i_clip = make_static_clip(bg_frames, i_ov[0], i_ov[1], i_ov[2],
                               PANEL_W, i_ov[3], loop_fps, i_dur)
    i_aud  = mix_audio(bg_music_path, intro_tts, None, i_dur)
    segments.append(i_clip.set_audio(i_aud) if i_aud else i_clip)
    _srep("Building intro…")

    # --- Questions ---
    for i, q in enumerate(questions):
        print(f"  Q{i+1}/{total_q}")
        q_text   = q["q"]; options = q["o"]; correct = int(q["c"])
        fun_fact = q.get("f", ""); qn = i + 1

        # Phase A  (question + options, no timer)
        a_ov  = build_question_overlay(q_text, options, qn, total_q)
        a_dur = tts_duration(q_tts[i]) + 0.5
        a_clip = _clip(a_ov, a_dur, tts_p=q_tts[i])
        segments.append(a_clip)
        _srep(f"Q{qn} narration…")

        # Phase B  (timer countdown)
        b_dur     = float(config.TIMER_DURATION)
        b_base    = composite_bg_overlay(bg_frames[0], a_ov[0],
                                          PANEL_X, a_ov[2], PANEL_W, a_ov[3])
        timer_cy  = a_ov[4]   # vertical centre of timer circle
        b_clip    = make_timer_clip(b_base, timer_cy, b_dur)
        b_aud     = mix_audio(bg_music_path, None, None, b_dur)
        segments.append(b_clip.set_audio(b_aud) if b_aud else b_clip)
        _srep(f"Q{qn} timer…")

        # Phase C  (reveal + fun fact)
        c_ov  = build_question_overlay(q_text, options, qn, total_q,
                                        reveal_index=correct, fun_fact=fun_fact)
        c_dur = tts_duration(f_tts[i]) + 1.5
        c_clip = _clip(c_ov, c_dur, tts_p=f_tts[i], sfx_p=correct_path)
        segments.append(c_clip)
        _srep(f"Q{qn} reveal…")

    # --- Outro ---
    o_dur  = max(tts_duration(outro_tts) + 0.5, 5.0)
    o_ov   = build_title_overlay(title, outro_text)
    o_clip = make_static_clip(bg_frames, o_ov[0], o_ov[1], o_ov[2],
                               PANEL_W, o_ov[3], loop_fps, o_dur)
    o_aud  = mix_audio(bg_music_path, outro_tts, None, o_dur)
    segments.append(o_clip.set_audio(o_aud) if o_aud else o_clip)
    _srep("Building outro…")

    # 5. Concatenate & encode
    _rep(63, "Concatenating…")
    final        = concatenate_videoclips(segments, method="compose")
    total_frames = max(1, int(final.duration * OUTPUT_FPS))
    _rep(65, f"Encoding… 0/{total_frames} frames")

    enc_log    = _ProgressLogger(progress_cb, 65, 95, total_frames) if progress_cb else None
    temp_audio = os.path.join(config.OUTPUT_DIR, f"quiz_{quiz_id}_{date_str}_snd.m4a")
    final.write_videofile(
        output_path,
        fps=OUTPUT_FPS, codec="libx264", audio_codec="aac",
        bitrate="4000k", audio_bitrate="192k",
        temp_audiofile=temp_audio, remove_temp=True, logger=enc_log,
    )

    # 6. Thumbnail
    _rep(96, "Generating thumbnail…")
    _make_thumbnail(title, bg_frames[0],
                    os.path.join(config.THUMB_DIR, f"quiz_{quiz_id}_{date_str}.jpg"))
    _rep(98, "Video ready — starting upload…")

    print(f"Video: {output_path}")
    final.close()
    return output_path


def _make_thumbnail(title: str, bg_frame: np.ndarray, out_path: str):
    img  = Image.fromarray(bg_frame).convert("RGBA")

    # Dark gradient vignette over lower 65% of frame
    vig  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd   = ImageDraw.Draw(vig)
    grad_top = int(H * 0.35)
    for i in range(grad_top, H):
        frac = (i - grad_top) / (H - grad_top)
        a    = int(220 * (frac ** 0.6))
        vd.line([(0, i), (W, i)], fill=(4, 5, 20, a))
    img.alpha_composite(vig)

    draw      = ImageDraw.Draw(img)
    font_big  = load_font(config.FONT_TITLE,   92)
    font_sm   = load_font(config.FONT_OPTIONS, 40)
    font_tag  = load_font(config.FONT_OPTIONS, 34)

    # ── Title ──
    title_lines = wrap_text(title, font_big, W - 220)
    line_h      = 108
    block_h     = len(title_lines) * line_h + 56  # +56 for brand label
    y           = H - block_h - 72

    for line in title_lines:
        bb = font_big.getbbox(line)
        lw = bb[2] - bb[0]
        tx = (W - lw) // 2
        # Stroke shadow
        for dx, dy in [(-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)]:
            draw.text((tx+dx, y+dy), line, font=font_big, fill=(0, 0, 0, 255))
        draw.text((tx, y), line, font=font_big, fill=(255, 255, 255, 255))
        y += line_h

    # ── AZ Quiz Hub brand line ──
    brand = "AZ QUIZ HUB"
    bb    = font_sm.getbbox(brand)
    bw    = bb[2] - bb[0]
    draw.text(((W - bw) // 2, y + 10), brand, font=font_sm, fill=(0, 212, 255, 255))

    # ── "TRIVIA QUIZ" pill badge top-right ──
    badge_text = "TRIVIA QUIZ"
    bb2  = font_tag.getbbox(badge_text)
    bw2  = bb2[2] - bb2[0]
    pad  = 14
    rx1  = W - bw2 - pad*2 - 24
    rx2  = W - 24
    ry1  = 28
    ry2  = ry1 + 54
    draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=10, fill=(0, 212, 255, 230))
    draw.text((rx1 + pad, ry1 + (54-(bb2[3]-bb2[1]))//2),
              badge_text, font=font_tag, fill=(0, 0, 0, 255))

    # ── Logo top-left ──
    _paste_logo(img)

    img.convert("RGB").save(out_path, "JPEG", quality=93)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AZ Quiz Hub video generator")
    ap.add_argument("--quiz-id", type=int, required=True)
    ap.add_argument("--output",  type=str, default=None)
    args = ap.parse_args()
    generate_video(args.quiz_id, args.output)
