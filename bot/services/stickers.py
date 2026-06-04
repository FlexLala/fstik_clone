"""
Обёртка над Telegram Bot API для стикерпаков (aiogram 3).

Против боли №1 (анимация и статика не уживаются в одном паке):
у каждого набора фиксированный media_kind. При создании запоминаем тип
и не даём подмешать несовместимый стикер — бот предложит отдельный пак.
"""
from __future__ import annotations

import re
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker

from bot.services.media import MediaKind, StickerTarget

_SAFE = re.compile(r"[^a-z0-9_]")


def build_pack_name(base: str, user_id: int, bot_username: str) -> str:
    base = _SAFE.sub("_", base.lower()).strip("_") or "pack"
    prefix = f"{base}_{user_id}"[:40]
    return f"{prefix}_by_{bot_username}"


def pack_link(name: str) -> str:
    return f"https://t.me/addstickers/{name}"


def _sticker_format(kind: MediaKind) -> str:
    return "video" if kind == MediaKind.VIDEO else "static"


def _input_sticker(file_bytes: bytes, filename: str,
                   kind: MediaKind, emoji: list[str]) -> InputSticker:
    return InputSticker(
        sticker=BufferedInputFile(file_bytes, filename=filename),
        format=_sticker_format(kind),
        emoji_list=emoji or ["⭐"],
    )


async def create_pack(bot: Bot, user_id: int, name: str, title: str,
                      file_path: Path, kind: MediaKind, target: StickerTarget,
                      emoji: list[str]) -> None:
    data = file_path.read_bytes()
    sticker = _input_sticker(data, file_path.name, kind, emoji)
    await bot.create_new_sticker_set(
        user_id=user_id,
        name=name,
        title=title,
        stickers=[sticker],
        sticker_type="custom_emoji" if target == StickerTarget.EMOJI else "regular",
    )


async def add_to_pack(bot: Bot, user_id: int, name: str,
                      file_path: Path, kind: MediaKind, emoji: list[str]) -> None:
    data = file_path.read_bytes()
    sticker = _input_sticker(data, file_path.name, kind, emoji)
    await bot.add_sticker_to_set(user_id=user_id, name=name, sticker=sticker)
