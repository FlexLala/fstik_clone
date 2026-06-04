"""Поток создания пака: тип -> вид -> личный/совместный -> название -> медиа -> готово."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import TMP_DIR, config
from bot.keyboards.menus import (after_add, choose_kind, choose_shared,
                                 choose_target, confirm_sticker, main_menu)
from bot.services import db, stickers
from bot.services.media import MediaError, MediaKind, StickerTarget, process
from bot.services.queue import media_queue
from bot.states.flows import NewPack

router = Router()


# ---------- старт ----------
@router.callback_query(F.data == "new_pack")
async def new_pack(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(NewPack.choosing_target)
    await call.message.answer("📦 <b>Новый пак</b>\nЧто создаём?",
                              reply_markup=choose_target())
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Отменено.", reply_markup=main_menu())
    await call.answer()


# ---------- 1. цель: стикеры / эмодзи ----------
@router.callback_query(NewPack.choosing_target, F.data.startswith("target:"))
async def pick_target(call: CallbackQuery, state: FSMContext):
    target = call.data.split(":", 1)[1]
    await state.update_data(target=target)
    await state.set_state(NewPack.choosing_kind)
    await call.message.answer(
        "Выбери <b>вид</b> пака:\n\n"
        "🖼 <b>Статичный</b> — обычные картинки.\n"
        "🎞 <b>Видео</b> — анимация/видео/GIF.\n"
        "🌟 <b>Единый</b> — и картинки, и видео вместе "
        "(картинки станут зацикленными видео).",
        reply_markup=choose_kind(),
    )
    await call.answer()


# ---------- 2. вид: static / video / unified ----------
@router.callback_query(NewPack.choosing_kind, F.data.startswith("kind:"))
async def pick_kind(call: CallbackQuery, state: FSMContext):
    kind = call.data.split(":", 1)[1]  # static | video | unified
    await state.update_data(pack_kind=kind)
    await state.set_state(NewPack.choosing_shared)
    await call.message.answer(
        "Пак будет <b>личный</b> или <b>совместный</b>?\n\n"
        "👤 Личный — наполняешь только ты.\n"
        "👥 Совместный — приглашаешь людей по ссылке.",
        reply_markup=choose_shared(),
    )
    await call.answer()


# ---------- 3. личный / совместный ----------
@router.callback_query(NewPack.choosing_shared, F.data.startswith("shared:"))
async def pick_shared(call: CallbackQuery, state: FSMContext):
    is_shared = call.data.split(":", 1)[1] == "1"
    await state.update_data(is_shared=is_shared)
    await state.set_state(NewPack.entering_title)
    await call.message.answer("✏️ Введи <b>название</b> пака:")
    await call.answer()


# ---------- 4. название ----------
@router.message(NewPack.entering_title, F.text)
async def set_title(message: Message, state: FSMContext):
    title = message.text.strip()[:64]
    if not title:
        await message.answer("Название не может быть пустым. Попробуй ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(NewPack.waiting_media)
    await message.answer(
        "📤 Отправь мне <b>фото, видео, GIF или стикер</b>.\n"
        "Я сам подгоню размер и формат."
    )


# ---------- скачивание медиа ----------
async def _download(message: Message, bot: Bot) -> Path | None:
    file_id = None
    suffix = ".bin"
    if message.photo:
        file_id, suffix = message.photo[-1].file_id, ".jpg"
    elif message.video:
        file_id, suffix = message.video.file_id, ".mp4"
    elif message.animation:
        file_id, suffix = message.animation.file_id, ".mp4"
    elif message.document:
        file_id = message.document.file_id
        suffix = Path(message.document.file_name or "f.bin").suffix or ".bin"
    elif message.sticker:
        st = message.sticker
        file_id = st.file_id
        suffix = ".webm" if st.is_video else (".tgs" if st.is_animated else ".webp")
    elif message.video_note:
        file_id, suffix = message.video_note.file_id, ".mp4"
    if not file_id:
        return None
    src = TMP_DIR / f"{uuid.uuid4().hex}{suffix}"
    await bot.download(file_id, destination=src)
    return src


# ---------- 5. приём и обработка медиа (через очередь) ----------
@router.message(NewPack.waiting_media, F.content_type.in_(
    {"photo", "video", "animation", "document", "sticker", "video_note"}))
async def receive_media(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = StickerTarget(data.get("target", "sticker"))
    pack_kind = data.get("pack_kind", "static")
    force_video = pack_kind in ("video", "unified")

    src = await _download(message, bot)
    if not src:
        await message.answer("Не смог получить файл. Пришли фото/видео/GIF.")
        return

    # сообщаем про очередь, если все слоты заняты
    if not media_queue.has_free_slot:
        pos = media_queue.waiting + 1
        status = await message.answer(f"⏳ В очереди (позиция ~{pos})...")
    else:
        status = await message.answer("⏳ Обрабатываю...")

    async def _do():
        return await process(src, target, force_video=force_video)

    try:
        result = await media_queue.run(_do)
    except MediaError as e:
        src.unlink(missing_ok=True)
        await status.edit_text(f"❌ {e}")
        return
    except Exception as e:  # noqa: BLE001
        src.unlink(missing_ok=True)
        await status.edit_text(f"❌ Ошибка обработки: {e}")
        return
    finally:
        src.unlink(missing_ok=True)  # входной файл больше не нужен

    await state.update_data(
        out_path=str(result.path),
        media_kind=result.kind.value,
        emoji=[],
    )
    await status.delete()

    caption = (
        f"✅ Готово!\n"
        f"Тип: <b>{'видео' if result.kind.value == 'video' else 'статичный'}</b> · "
        f"{result.width}x{result.height} · {result.size_bytes // 1024}KB\n"
        f"<i>{result.note}</i>\n\n"
        f"Добавить в пак?"
    )
    file = FSInputFile(result.path)
    if result.kind.value == "video":
        await message.answer_video(file, caption=caption,
                                   reply_markup=confirm_sticker())
    else:
        await message.answer_document(file, caption=caption,
                                      reply_markup=confirm_sticker())
    await state.set_state(NewPack.confirming)


# ---------- эмодзи ----------
@router.callback_query(NewPack.confirming, F.data == "set_emoji")
async def ask_emoji(call: CallbackQuery, state: FSMContext):
    await state.set_state(NewPack.waiting_emoji)
    await call.message.answer("😀 Пришли 1-3 эмодзи для этого стикера:")
    await call.answer()


@router.message(NewPack.waiting_emoji, F.text)
async def save_emoji(message: Message, state: FSMContext):
    emojis = re.findall(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", message.text)[:3]
    await state.update_data(emoji=emojis or ["⭐"])
    await state.set_state(NewPack.confirming)
    await message.answer(
        f"Эмодзи сохранены: {''.join(emojis) or '⭐'}\n"
        "Теперь жми «✅ Добавить в пак».",
        reply_markup=confirm_sticker(),
    )


@router.callback_query(NewPack.confirming, F.data == "redo")
async def redo(call: CallbackQuery, state: FSMContext):
    await state.set_state(NewPack.waiting_media)
    await call.message.answer("📤 Ок, пришли другое медиа.")
    await call.answer()


# ---------- 6. добавление в пак ----------
@router.callback_query(NewPack.confirming, F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = StickerTarget(data["target"])
    title = data["title"]
    out_path = Path(data["out_path"])
    kind = MediaKind(data["media_kind"])
    pack_kind = data.get("pack_kind", "static")  # static|video|unified
    is_shared = bool(data.get("is_shared"))
    emoji = data.get("emoji") or ["⭐"]
    user = call.from_user
    user_id = user.id

    # имя пака. Если уже создан в этой сессии — берём его (добавляем туда же).
    name = data.get("pack_name") or stickers.build_pack_name(
        title, user_id, config.bot_username)

    # определяем владельца (для shared контент кладётся от имени владельца)
    existing = await db.get_pack(name)
    owner_id = existing["owner_id"] if existing else user_id

    await call.answer("Добавляю...")

    if not existing:
        # первый стикер — создаём набор
        try:
            await stickers.create_pack(
                bot, owner_id, name, title, out_path, kind, target, emoji)
        except TelegramBadRequest as e:
            await call.message.answer(f"❌ Telegram отклонил: {e}")
            return
        # media_kind в БД: для unified храним 'unified'
        db_kind = "unified" if pack_kind == "unified" else kind.value
        await db.add_pack(owner_id, name, title, target.value, db_kind,
                          is_shared=is_shared)
        existing = await db.get_pack(name)
    else:
        # проверка членства: кикнутый участник не может добавлять
        if existing["is_shared"] and not await db.is_member(name, user_id):
            await call.message.answer(
                "🚫 Тебя нет среди участников этого пака "
                "(возможно, тебя исключили). Добавление недоступно."
            )
            return
        # добавляем в существующий
        db_kind = existing["media_kind"]
        # защита от смешивания в НЕ-единый пак
        if db_kind != "unified" and db_kind != kind.value:
            await call.message.answer(
                "⚠️ В этом паке другой тип. Этот пак: "
                f"<b>{db_kind}</b>. Создай отдельный пак или выбери «Единый»."
            )
            return
        try:
            await stickers.add_to_pack(bot, owner_id, name, out_path, kind, emoji)
        except TelegramBadRequest as e:
            await call.message.answer(f"❌ Не удалось добавить: {e}")
            return

    Path(data["out_path"]).unlink(missing_ok=True)  # выходной webm/webp больше не нужен
    await state.update_data(pack_name=name, out_path=None)
    is_owner = (owner_id == user_id)
    await call.message.answer(
        f"🎉 Стикер добавлен в <b>{title}</b>!",
        reply_markup=after_add(name, is_owner, bool(existing["is_shared"])),
    )


# ---------- добавить ещё в тот же пак ----------
@router.callback_query(F.data == "add_more")
async def add_more(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("pack_name"):
        await call.message.answer("Сначала создай пак.", reply_markup=main_menu())
        await call.answer()
        return
    await state.set_state(NewPack.waiting_media)
    await call.message.answer("📤 Пришли следующее медиа для этого пака.")
    await call.answer()
