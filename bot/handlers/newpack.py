"""
Поток создания / редактирования пака.
ИЗМЕНЕНИЯ:
  - ПУНКТ 1: edit_pack — возврат к добавлению стикеров в существующий пак
  - ПУНКТ 2: удаляем промежуточные сообщения (статус обработки и др.)
  - ПУНКТ 3: читаем max_side из БД настроек пользователя
  - ПУНКТ 4: если видео > 3с — предлагаем ускорить или обрезать
"""
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
                                 choose_target, confirm_sticker, main_menu,
                                 speed_up_kb)
from bot.services import db, stickers
from bot.services.media import MediaError, MediaKind, StickerTarget, process
from bot.services.queue import media_queue
from bot.states.flows import NewPack

router = Router()


# ─── вспомогательная функция тихого удаления сообщения ───
async def _delete(msg) -> None:
    try:
        await msg.delete()
    except Exception:
        pass


# ─── новый пак ───────────────────────────────────────────
@router.callback_query(F.data == "new_pack")
async def new_pack(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(NewPack.choosing_target)
    # ПУНКТ 2: редактируем текущее сообщение
    try:
        await call.message.edit_text(
            "📦 <b>Новый пак</b>\nЧто создаём?",
            reply_markup=choose_target(),
        )
    except Exception:
        await call.message.answer(
            "📦 <b>Новый пак</b>\nЧто создаём?",
            reply_markup=choose_target(),
        )
    await call.answer()


# ПУНКТ 1: редактировать (добавить в) существующий пак
@router.callback_query(F.data.startswith("edit_pack:"))
async def edit_pack(call: CallbackQuery, state: FSMContext):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return

    # Проверяем, есть ли у пользователя доступ
    user_id = call.from_user.id
    if pack["is_shared"]:
        if not await db.is_member(name, user_id):
            await call.answer("Тебя нет в участниках этого пака.", show_alert=True)
            return
    elif pack["owner_id"] != user_id:
        await call.answer("Это не твой пак.", show_alert=True)
        return

    await state.clear()
    await state.set_state(NewPack.waiting_media)
    await state.update_data(
        target=pack["pack_type"],
        pack_kind=pack["media_kind"],
        is_shared=bool(pack["is_shared"]),
        title=pack["title"],
        pack_name=name,
        emoji=[],
    )
    try:
        await call.message.edit_text(
            f"✏️ Редактирование пака <b>{pack['title']}</b>\n\n"
            "📤 Пришли фото/видео/GIF — добавлю в этот пак."
        )
    except Exception:
        await call.message.answer(
            f"✏️ Редактирование пака <b>{pack['title']}</b>\n\n"
            "📤 Пришли фото/видео/GIF — добавлю в этот пак."
        )
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("Отменено.", reply_markup=main_menu())
    except Exception:
        await call.message.answer("Отменено.", reply_markup=main_menu())
    await call.answer()


@router.callback_query(NewPack.choosing_target, F.data.startswith("target:"))
async def pick_target(call: CallbackQuery, state: FSMContext):
    target = call.data.split(":", 1)[1]
    await state.update_data(target=target)
    await state.set_state(NewPack.choosing_kind)
    try:
        await call.message.edit_text(
            "Выбери <b>вид</b> пака:\n\n"
            "🖼 <b>Статичный</b> — обычные картинки.\n"
            "🎞 <b>Видео</b> — анимация/видео/GIF.\n"
            "🌟 <b>Единый</b> — и картинки, и видео вместе "
            "(картинки станут зацикленными видео).",
            reply_markup=choose_kind(),
        )
    except Exception:
        await call.message.answer(
            "Выбери <b>вид</b> пака:",
            reply_markup=choose_kind(),
        )
    await call.answer()


@router.callback_query(NewPack.choosing_kind, F.data.startswith("kind:"))
async def pick_kind(call: CallbackQuery, state: FSMContext):
    kind = call.data.split(":", 1)[1]
    await state.update_data(pack_kind=kind)
    await state.set_state(NewPack.choosing_shared)
    try:
        await call.message.edit_text(
            "Пак будет <b>личный</b> или <b>совместный</b>?\n\n"
            "👤 Личный — наполняешь только ты.\n"
            "👥 Совместный — приглашаешь людей по ссылке.",
            reply_markup=choose_shared(),
        )
    except Exception:
        await call.message.answer(
            "Пак будет личный или совместный?",
            reply_markup=choose_shared(),
        )
    await call.answer()


@router.callback_query(NewPack.choosing_shared, F.data.startswith("shared:"))
async def pick_shared(call: CallbackQuery, state: FSMContext):
    is_shared = call.data.split(":", 1)[1] == "1"
    await state.update_data(is_shared=is_shared)
    await state.set_state(NewPack.entering_title)
    try:
        await call.message.edit_text("✏️ Введи <b>название</b> пака:")
    except Exception:
        await call.message.answer("✏️ Введи <b>название</b> пака:")
    await call.answer()


@router.message(NewPack.entering_title, F.text)
async def set_title(message: Message, state: FSMContext):
    title = message.text.strip()[:64]
    if not title:
        await message.answer("Название не может быть пустым. Попробуй ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(NewPack.waiting_media)
    # ПУНКТ 2: удаляем сообщение пользователя и отвечаем одним
    await _delete(message)
    await message.answer(
        "📤 Отправь мне <b>фото, видео, GIF или стикер</b>.\n"
        "Я сам подгоню размер и формат."
    )


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


@router.message(NewPack.waiting_media, F.content_type.in_(
    {"photo", "video", "animation", "document", "sticker", "video_note"}))
async def receive_media(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = StickerTarget(data.get("target", "sticker"))
    pack_kind = data.get("pack_kind", "static")
    force_video = pack_kind in ("video", "unified")

    # ПУНКТ 3: читаем кастомный размер пользователя
    max_side = await db.get_user_max_side(message.from_user.id)

    # ПУНКТ 4: читаем флаг speed_up из FSM (установлен после выбора пользователя)
    speed_up = bool(data.get("speed_up", False))

    src = await _download(message, bot)
    if not src:
        await message.answer("Не смог получить файл. Пришли фото/видео/GIF.")
        return

    if not media_queue.has_free_slot:
        pos = media_queue.waiting + 1
        status = await message.answer(f"⏳ В очереди (позиция ~{pos})...")
    else:
        status = await message.answer("⏳ Обрабатываю...")

    async def _do():
        return await process(src, target, force_video=force_video,
                             max_side=max_side, speed_up=speed_up)

    try:
        result = await media_queue.run(_do)
    except MediaError as e:
        src.unlink(missing_ok=True)
        await _delete(status)
        await message.answer(f"❌ {e}")
        return
    except Exception as e:
        src.unlink(missing_ok=True)
        await _delete(status)
        await message.answer(f"❌ Ошибка обработки: {e}")
        return
    finally:
        src.unlink(missing_ok=True)

    await _delete(status)  # ПУНКТ 2: удаляем «⏳ Обрабатываю...»

    # ПУНКТ 4: если видео слишком длинное И флаг speed_up ещё не выбран — спрашиваем
    # Если speed_up уже установлен — сразу показываем превью (цикл исключён)
    if result.was_too_long and not speed_up:
        await state.update_data(
            out_path=str(result.path),
            media_kind=result.kind.value,
            original_duration=result.original_duration,
            emoji=[],
        )
        await message.answer(
            f"⏱ Видео длиннее 3 секунд ({result.original_duration:.1f}с).\n\n"
            "Как поступим?\n"
            "⚡ <b>Ускорить</b> — весь ролик уместится в 3 сек (ускорение в "
            f"{result.original_duration / 3:.1f}x).\n"
            "✂️ <b>Просто обрезать</b> — возьмём первые 3 сек.",
            reply_markup=speed_up_kb(),
        )
        await state.set_state(NewPack.speed_confirm)
        return

    # Сбрасываем флаг speed_up после успешной обработки
    await state.update_data(speed_up=False)
    await _show_preview(message, state, result)


# ПУНКТ 4: обработка выбора ускорения/обрезки
@router.callback_query(NewPack.speed_confirm, F.data.startswith("speed:"))
async def speed_choice(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":", 1)[1]
    data = await state.get_data()
    speed_up = (choice == "up")

    # Удаляем старый обрезанный результат — он нам не нужен
    old_path = Path(data["out_path"]) if data.get("out_path") else None
    if old_path:
        old_path.unlink(missing_ok=True)
    await state.update_data(out_path=None)

    # Сохраняем выбор и просим прислать видео ещё раз
    # (оригинал уже удалён, поэтому просим переслать — без нового вопроса)
    await state.update_data(speed_up=speed_up)
    await state.set_state(NewPack.waiting_media)

    action = "с ускорением ⚡" if speed_up else "с обрезкой до 3 сек ✂️"
    await call.message.edit_text(
        f"🔄 Понял! Пришли это видео ещё раз — обработаю {action}.\n\n"
        "На этот раз вопросов задавать не буду 😊"
    )
    await call.answer()


async def _show_preview(message: Message, state: FSMContext, result) -> None:
    await state.update_data(
        out_path=str(result.path),
        media_kind=result.kind.value,
        emoji=[],
        speed_up=False,
    )
    caption = (
        f"✅ Готово!\n"
        f"Тип: <b>{'видео' if result.kind.value == 'video' else 'статичный'}</b> · "
        f"{result.width}x{result.height} · {result.size_bytes // 1024}KB\n"
        f"<i>{result.note}</i>\n\n"
        f"Добавить в пак?"
    )
    file = FSInputFile(result.path)
    if result.kind.value == "video":
        await message.answer_video(file, caption=caption, reply_markup=confirm_sticker())
    else:
        await message.answer_document(file, caption=caption, reply_markup=confirm_sticker())
    await state.set_state(NewPack.confirming)


@router.callback_query(NewPack.confirming, F.data == "set_emoji")
async def ask_emoji(call: CallbackQuery, state: FSMContext):
    await state.set_state(NewPack.waiting_emoji)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer("😀 Пришли 1–3 эмодзи для этого стикера:")
    await call.answer()


@router.message(NewPack.waiting_emoji, F.text)
async def save_emoji(message: Message, state: FSMContext):
    emojis = re.findall(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", message.text)[:3]
    await state.update_data(emoji=emojis or ["⭐"])
    await state.set_state(NewPack.confirming)
    await _delete(message)  # ПУНКТ 2: убираем сообщение с эмодзи
    await message.answer(
        f"Эмодзи сохранены: {''.join(emojis) or '⭐'}\n"
        "Теперь жми «✅ Добавить в пак».",
        reply_markup=confirm_sticker(),
    )


@router.callback_query(NewPack.confirming, F.data == "redo")
async def redo(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("out_path"):
        Path(data["out_path"]).unlink(missing_ok=True)
    await state.set_state(NewPack.waiting_media)
    try:
        await call.message.edit_text("📤 Ок, пришли другое медиа.")
    except Exception:
        await call.message.answer("📤 Ок, пришли другое медиа.")
    await call.answer()


@router.callback_query(NewPack.confirming, F.data == "confirm_add")
async def confirm_add(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = StickerTarget(data["target"])
    title = data["title"]
    out_path = Path(data["out_path"])
    kind = MediaKind(data["media_kind"])
    pack_kind = data.get("pack_kind", "static")
    is_shared = bool(data.get("is_shared"))
    emoji = data.get("emoji") or ["⭐"]
    user = call.from_user
    user_id = user.id

    name = data.get("pack_name") or stickers.build_pack_name(
        title, user_id, config.bot_username)

    existing = await db.get_pack(name)
    owner_id = existing["owner_id"] if existing else user_id

    await call.answer("Добавляю...")

    if not existing:
        try:
            await stickers.create_pack(
                bot, owner_id, name, title, out_path, kind, target, emoji)
        except TelegramBadRequest as e:
            await call.message.answer(f"❌ Telegram отклонил: {e}")
            return
        db_kind = "unified" if pack_kind == "unified" else kind.value
        await db.add_pack(owner_id, name, title, target.value, db_kind,
                          is_shared=is_shared)
        existing = await db.get_pack(name)
    else:
        if existing["is_shared"] and not await db.is_member(name, user_id):
            await call.message.answer(
                "🚫 Тебя нет среди участников этого пака "
                "(возможно, тебя исключили). Добавление недоступно."
            )
            return
        db_kind = existing["media_kind"]
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

    Path(data["out_path"]).unlink(missing_ok=True)
    await state.update_data(pack_name=name, out_path=None)
    is_owner = (owner_id == user_id)

    # ПУНКТ 2: редактируем сообщение с предпросмотром вместо нового
    try:
        await call.message.edit_caption(
            caption=f"🎉 Стикер добавлен в <b>{title}</b>!",
            reply_markup=after_add(name, is_owner, bool(existing["is_shared"])),
        )
    except Exception:
        await call.message.answer(
            f"🎉 Стикер добавлен в <b>{title}</b>!",
            reply_markup=after_add(name, is_owner, bool(existing["is_shared"])),
        )


@router.callback_query(F.data == "add_more")
async def add_more(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("pack_name"):
        await call.message.answer("Сначала создай пак.", reply_markup=main_menu())
        await call.answer()
        return
    await state.set_state(NewPack.waiting_media)
    try:
        await call.message.edit_text("📤 Пришли следующее медиа для этого пака.")
    except Exception:
        await call.message.answer("📤 Пришли следующее медиа для этого пака.")
    await call.answer()
