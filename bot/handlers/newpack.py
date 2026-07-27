"""
Поток создания / редактирования пака.

Логика длинного видео:
  1. Пользователь присылает видео
  2. Делаем probe (быстро, без конвертации)
  3. Если > 3 сек — сразу спрашиваем: ускорить или обрезать (оригинал сохранён)
  4. После выбора — конвертируем оригинал с нужным флагом
  Итого: одна отправка видео, один вопрос, одна конвертация.
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
from bot.services.media import (MediaError, MediaKind, StickerTarget,
                                FitMode, process, probe)
from bot.services.queue import media_queue
from bot.states.flows import NewPack

router = Router()


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


# ─── редактировать существующий пак ──────────────────────
@router.callback_query(F.data.startswith("edit_pack:"))
async def edit_pack(call: CallbackQuery, state: FSMContext):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return

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
        src_path=None,
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
        await call.message.answer("Выбери вид пака:", reply_markup=choose_kind())
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
        await call.message.answer("Личный или совместный?", reply_markup=choose_shared())
    await call.answer()


@router.callback_query(NewPack.choosing_shared, F.data.startswith("shared:"))
async def pick_shared(call: CallbackQuery, state: FSMContext):
    is_shared = call.data.split(":", 1)[1] == "1"
    await state.update_data(is_shared=is_shared)
    await state.set_state(NewPack.entering_title)
    try:
        await call.message.edit_text("✏️ Введи <b>название</b> пака:")
    except Exception:
        await call.message.answer("✏️ Введи название пака:")
    await call.answer()


@router.message(NewPack.entering_title, F.text)
async def set_title(message: Message, state: FSMContext):
    title = message.text.strip()[:64]
    if not title:
        await message.answer("Название не может быть пустым. Попробуй ещё раз.")
        return
    await state.update_data(title=title, src_path=None)
    await state.set_state(NewPack.waiting_media)
    await _delete(message)
    await message.answer(
        "📤 Отправь мне <b>фото, видео, GIF или стикер</b>.\n"
        "Я сам подгоню размер и формат."
    )


# ─── скачивание файла ─────────────────────────────────────
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


# ─── приём медиа ─────────────────────────────────────────
@router.message(NewPack.waiting_media, F.content_type.in_(
    {"photo", "video", "animation", "document", "sticker", "video_note"}))
async def receive_media(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = StickerTarget(data.get("target", "sticker"))
    pack_kind = data.get("pack_kind", "static")
    force_video = pack_kind in ("video", "unified")
    max_side = await db.get_user_max_side(message.from_user.id)

    src = await _download(message, bot)
    if not src:
        await message.answer("Не смог получить файл. Пришли фото/видео/GIF.")
        return

    # Читаем настройки пользователя
    s = await db.get_user_settings(message.from_user.id)
    max_side = s.get("max_side", 512)
    fit_mode = FitMode(s.get("fit_mode", "fit"))
    sharpen = bool(s.get("sharpen", True))

    status = await message.answer("⏳ Обрабатываю...")

    # Быстро смотрим длительность через probe (без конвертации)
    try:
        info = await probe(src)
        is_too_long = (info.kind == MediaKind.VIDEO and info.duration > 3.0)
    except Exception:
        is_too_long = False
        info = None

    # Видео длиннее 3 сек — спрашиваем сразу, оригинал сохраняем
    if is_too_long:
        await _delete(status)
        await state.update_data(
            src_path=str(src),
            force_video=force_video,
            max_side=max_side,
            fit_mode=fit_mode.value,
            sharpen=int(sharpen),
            target=target.value,
            original_duration=info.duration,
            emoji=[],
        )
        await message.answer(
            f"⏱ Видео длиннее 3 секунд ({info.duration:.1f}с).\n\n"
            f"⚡ <b>Ускорить</b> — весь ролик в 3 сек (x{info.duration / 3:.1f})\n"
            "✂️ <b>Обрезать</b> — первые 3 сек",
            reply_markup=speed_up_kb(),
        )
        await state.set_state(NewPack.speed_confirm)
        return

    # Обычная конвертация
    async def _do():
        return await process(
            src, target,
            force_video=force_video,
            max_side=max_side,
            speed_up=False,
            fit_mode=fit_mode,
            sharpen=sharpen,
        )

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

    await _delete(status)
    await _show_preview(message, state, result)


# ─── пользователь выбрал: ускорить или обрезать ──────────
@router.callback_query(NewPack.speed_confirm, F.data.startswith("speed:"))
async def speed_choice(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":", 1)[1]
    data = await state.get_data()

    src_path = data.get("src_path")
    if not src_path or not Path(src_path).exists():
        await call.message.edit_text(
            "❌ Файл куда-то пропал. Пришли видео ещё раз."
        )
        await state.set_state(NewPack.waiting_media)
        await call.answer()
        return

    src = Path(src_path)
    target = StickerTarget(data.get("target", "sticker"))
    force_video = data.get("force_video", True)
    max_side = data.get("max_side", 512)
    fit_mode = FitMode(data.get("fit_mode", "fit"))
    sharpen = bool(data.get("sharpen", True))
    speed_up = (choice == "up")

    action_text = "⚡ Ускоряю..." if speed_up else "✂️ Обрезаю до 3 сек..."
    await call.message.edit_text(action_text)
    await call.answer()

    async def _do():
        return await process(
            src, target,
            force_video=force_video,
            max_side=max_side,
            speed_up=speed_up,
            fit_mode=fit_mode,
            sharpen=sharpen,
        )

    try:
        result = await media_queue.run(_do)
    except MediaError as e:
        src.unlink(missing_ok=True)
        await call.message.edit_text(f"❌ {e}")
        return
    except Exception as e:
        src.unlink(missing_ok=True)
        await call.message.edit_text(f"❌ Ошибка: {e}")
        return
    finally:
        src.unlink(missing_ok=True)

    await state.update_data(src_path=None)
    await _show_preview(call.message, state, result)


# ─── предпросмотр ─────────────────────────────────────────
async def _show_preview(message: Message, state: FSMContext, result) -> None:
    await state.update_data(
        out_path=str(result.path),
        media_kind=result.kind.value,
        emoji=[],
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
    await _delete(message)
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

    # Если эмодзи не заданы, используем ⭐ по умолчанию
    if not emoji:
        emoji = ["⭐"]

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
                "🚫 Тебя нет среди участников этого пака. Добавление недоступно."
            )
            return
        db_kind = existing["media_kind"]
        if db_kind != "unified" and db_kind != kind.value:
            await call.message.answer(
                f"⚠️ В этом паке тип <b>{db_kind}</b>. "
                "Создай отдельный пак или выбери «Единый»."
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

    # ИДЕЯ 9: уведомляем участников совместного пака
    if existing and existing["is_shared"]:
        who = call.from_user.username and f"@{call.from_user.username}" \
              or call.from_user.first_name
        notifiable = await db.get_notifiable_members(name, user_id)
        for m in notifiable:
            try:
                await bot.send_message(
                    m["user_id"],
                    f"🖼 <b>{who}</b> добавил стикер в пак «{title}»!\n"
                    f"📦 <a href='https://t.me/addstickers/{name}'>Открыть пак</a>",
                    disable_notification=True,
                )
            except Exception:
                pass  # пользователь заблокировал бота — не страшно

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
    await state.update_data(src_path=None)
    try:
        await call.message.edit_text("📤 Пришли следующее медиа для этого пака.")
    except Exception:
        await call.message.answer("📤 Пришли следующее медиа для этого пака.")
    await call.answer()
