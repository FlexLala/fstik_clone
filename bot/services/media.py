"""
Сервис обработки медиа под требования Telegram.

Решает обе боли пользователя:
1) Сам определяет, что прислали (фото / видео / гиф / анимированный webp/webm),
   и автоматически делает либо СТАТИЧНЫЙ (.webp/.png), либо ВИДЕО (.webm/vp9) стикер.
2) Сам подгоняет пропорции: длинная сторона = 512px (для стикера) или 100x100 (эмодзи),
   ничего обрезать не нужно — добавляет прозрачные поля при необходимости.

Требования Telegram (на 2024+):
  Статичный стикер: .webp/.png, одна сторона ровно 512px, вторая <= 512px.
  Видео-стикер: .webm (VP9), одна сторона ровно 512px, длительность <= 3с,
                до 30 FPS, <= 256 KB, без аудио, желательно зацикленный.
  Эмодзи: ровно 100x100 (и для статики, и для видео).
"""
from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image

from bot.config import config, TMP_DIR

STICKER_SIDE = 512
EMOJI_SIDE = 100
VIDEO_MAX_DURATION = 2.9
VIDEO_MAX_FPS = 30
VIDEO_MAX_BYTES = 256 * 1024
STATIC_MAX_BYTES = 512 * 1024


class MediaKind(str, Enum):
    STATIC = "static"
    VIDEO = "video"


class StickerTarget(str, Enum):
    STICKER = "sticker"
    EMOJI = "emoji"


@dataclass
class ProbeResult:
    kind: MediaKind
    width: int
    height: int
    duration: float
    has_audio: bool
    fps: float


@dataclass
class ConvertResult:
    path: Path
    kind: MediaKind
    width: int
    height: int
    size_bytes: int
    note: str = ""


class MediaError(Exception):
    pass


async def _run(*args: str):
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out, err


async def probe(src: Path) -> ProbeResult:
    ffprobe = config.ffprobe_bin if config else "ffprobe"
    code, out, err = await _run(
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(src),
    )
    if code != 0:
        raise MediaError(f"ffprobe error: {err.decode(errors='ignore')[:300]}")

    data = json.loads(out or b"{}")
    streams = data.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if vstream is None:
        raise MediaError("В файле нет видеодорожки/изображения.")

    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    width = int(vstream.get("width") or 0)
    height = int(vstream.get("height") or 0)
    duration = float(data.get("format", {}).get("duration") or vstream.get("duration") or 0)
    nb_frames = int(vstream.get("nb_frames") or 0)

    fps = 0.0
    afr = vstream.get("avg_frame_rate") or "0/0"
    try:
        num, den = afr.split("/")
        if float(den) != 0:
            fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    animated = nb_frames > 1 or duration > 0.1
    codec = (vstream.get("codec_name") or "").lower()
    if codec in {"mjpeg", "png", "webp"} and nb_frames <= 1:
        animated = False

    kind = MediaKind.VIDEO if animated else MediaKind.STATIC
    return ProbeResult(kind, width, height, duration, has_audio, fps)


def _target_box(target: StickerTarget) -> int:
    return EMOJI_SIDE if target == StickerTarget.EMOJI else STICKER_SIDE


def _convert_static(src: Path, dst: Path, target: StickerTarget) -> ConvertResult:
    box = _target_box(target)
    img = Image.open(src).convert("RGBA")
    w, h = img.size

    if target == StickerTarget.EMOJI:
        img.thumbnail((box, box), Image.LANCZOS)
        canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        canvas.paste(img, ((box - img.width) // 2, (box - img.height) // 2), img)
        out = canvas
        note = "Приведено к 100x100 (эмодзи)."
    else:
        scale = box / max(w, h)
        new = (max(1, round(w * scale)), max(1, round(h * scale)))
        out = img.resize(new, Image.LANCZOS)
        note = f"Масштаб до {out.width}x{out.height} (длинная сторона 512)."

    out.save(dst, format="WEBP", quality=95, method=6)
    size = dst.stat().st_size
    if size > STATIC_MAX_BYTES:
        for q in (85, 75, 65, 55):
            out.save(dst, format="WEBP", quality=q, method=6)
            if dst.stat().st_size <= STATIC_MAX_BYTES:
                break
        size = dst.stat().st_size
    return ConvertResult(dst, MediaKind.STATIC, out.width, out.height, size, note)


async def _convert_video(src: Path, dst: Path, target: StickerTarget, info: ProbeResult) -> ConvertResult:
    box = _target_box(target)
    ffmpeg = config.ffmpeg_bin if config else "ffmpeg"

    if target == StickerTarget.EMOJI:
        vf = (
            f"scale={box}:{box}:force_original_aspect_ratio=decrease,"
            f"pad={box}:{box}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"fps={VIDEO_MAX_FPS}"
        )
    else:
        vf = (
            f"scale='if(gt(iw,ih),{box},-2)':'if(gt(iw,ih),-2,{box})',"
            f"fps={VIDEO_MAX_FPS}"
        )

    notes = []
    if info.duration > VIDEO_MAX_DURATION:
        notes.append(f"обрезано до {VIDEO_MAX_DURATION}с (было {info.duration:.1f}с)")
    if info.has_audio:
        notes.append("удалён звук")

    for crf, bitrate in ((32, "400k"), (40, "260k"), (50, "180k"), (56, "120k")):
        code, _, err = await _run(
            ffmpeg, "-y",
            "-t", f"{VIDEO_MAX_DURATION}",
            "-i", str(src),
            "-vf", vf,
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-an",
            "-b:v", bitrate, "-crf", str(crf),
            "-loop", "0",
            "-deadline", "realtime", "-cpu-used", "5",
            "-threads", "1", "-row-mt", "1",
            str(dst),
        )
        if code != 0:
            raise MediaError(f"ffmpeg error: {err.decode(errors='ignore')[:300]}")
        if dst.stat().st_size <= VIDEO_MAX_BYTES:
            break

    size = dst.stat().st_size
    if size > VIDEO_MAX_BYTES:
        notes.append(f"WARN: файл {size//1024}KB > 256KB, попробуй короче/проще видео")

    final = await probe(dst)
    note = "Видео-стикер VP9/WEBM. " + (", ".join(notes) if notes else "")
    return ConvertResult(dst, MediaKind.VIDEO, final.width, final.height, size, note.strip())


async def _static_to_webm(src: Path, dst: Path, target: StickerTarget) -> ConvertResult:
    """Превращаем статичную картинку в зацикленный VP9/WEBM (~1с).

    Нужно для ЕДИНОГО пака: чтобы статика и видео лежали вместе, всё приводим
    к video-стикерам. Картинку нормализуем через Pillow (размер/альфа),
    затем ffmpeg делает из одного кадра короткое зацикленное видео.
    """
    box = _target_box(target)
    ffmpeg = config.ffmpeg_bin if config else "ffmpeg"

    norm = TMP_DIR / f"{src.stem}_norm.png"
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    if target == StickerTarget.EMOJI:
        img.thumbnail((box, box), Image.LANCZOS)
        canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        canvas.paste(img, ((box - img.width) // 2, (box - img.height) // 2), img)
        out_img = canvas
        dims_note = "100x100 (эмодзи)"
    else:
        scale = box / max(w, h)
        new = (max(1, round(w * scale)), max(1, round(h * scale)))
        new = (new[0] - (new[0] % 2) or 2, new[1] - (new[1] % 2) or 2)
        out_img = img.resize(new, Image.LANCZOS)
        dims_note = f"{out_img.width}x{out_img.height}"
    out_img.save(norm, format="PNG")

    duration = 1.0
    for crf, bitrate in ((30, "300k"), (40, "180k"), (50, "120k")):
        code, _, err = await _run(
            ffmpeg, "-y",
            "-loop", "1", "-t", str(duration),
            "-i", str(norm),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-an",
            "-b:v", bitrate, "-crf", str(crf),
            "-r", "10",
            "-loop", "0",
            "-deadline", "realtime", "-cpu-used", "5",
            "-threads", "1", "-row-mt", "1",
            str(dst),
        )
        if code != 0:
            raise MediaError(f"ffmpeg error: {err.decode(errors='ignore')[:300]}")
        if dst.stat().st_size <= VIDEO_MAX_BYTES:
            break

    norm.unlink(missing_ok=True)
    final = await probe(dst)
    note = f"Статика -> зацикленный VP9/WEBM, {dims_note} (для единого пака)."
    return ConvertResult(dst, MediaKind.VIDEO, final.width, final.height,
                         dst.stat().st_size, note)


async def process(src: Path, target: StickerTarget,
                  force_video: bool = False) -> ConvertResult:
    """force_video=True -> даже статику приводим к video-стикеру (.webm)."""
    if shutil.which((config.ffmpeg_bin if config else "ffmpeg")) is None:
        raise MediaError("FFmpeg не найден. Установи: sudo apt install ffmpeg")

    info = await probe(src)
    stem = src.stem
    if info.kind == MediaKind.STATIC and not force_video:
        dst = TMP_DIR / f"{stem}_out.webp"
        return await asyncio.to_thread(_convert_static, src, dst, target)
    elif info.kind == MediaKind.STATIC and force_video:
        dst = TMP_DIR / f"{stem}_out.webm"
        return await _static_to_webm(src, dst, target)
    else:
        dst = TMP_DIR / f"{stem}_out.webm"
        return await _convert_video(src, dst, target, info)
