"""
Управление паками:
  - Переименование (идея 3)
  - Лимит участников (идея 4)
  - Копирование пака (идея 8)
  - Уведомления участников при добавлении стикера (идея 9)
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.menus import (main_menu, manage_pack_kb,
                                 members_kb, notify_kb)
from bot.services import db
from bot.states.flows import ManagePack

router = Router()


# ─── меню управления паком ───────────────────────────────
@router.callback_query(F.data.startswith("manage:"))
async def manage_pack(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return
    if pack["owner_id"] != call.from_user.id:
        await call.answer("Только владелец может управлять паком.", show_alert=True)
        return

    members = await db.list_members(name)
    limit = pack.get("max_members", 0)
    limit_str = f"{limit}" if limit else "∞"

    await call.message.edit_text(
        f"⚙️ Управление паком <b>{pack['title']}</b>\n\n"
        f"👥 Участников: {len(members)} / {limit_str}\n"
        f"📦 Тип: {pack['media_kind']}",
        reply_markup=manage_pack_kb(name, pack["is_shared"]),
    )
    await call.answer()


# ─── ИДЕЯ 3: Переименование ───────────────────────────────
@router.callback_query(F.data.startswith("rename:"))
async def start_rename(call: CallbackQuery, state: FSMContext):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack or pack["owner_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(ManagePack.entering_new_title)
    await state.update_data(pack_name=name)
    await call.message.edit_text(
        f"✏️ Текущее название: <b>{pack['title']}</b>\n\n"
        "Введи новое название пака (до 64 символов):"
    )
    await call.answer()


@router.message(ManagePack.entering_new_title, F.text)
async def finish_rename(message: Message, state: FSMContext, bot: Bot):
    new_title = message.text.strip()[:64]
    if not new_title:
        await message.answer("Название не может быть пустым.")
        return

    data = await state.get_data()
    name = data["pack_name"]
    pack = await db.get_pack(name)

    # Переименовываем в Telegram
    try:
        await bot.set_sticker_set_title(name=name, title=new_title)
    except Exception as e:
        await message.answer(f"❌ Telegram не принял: {e}")
        await state.clear()
        return

    # Переименовываем в БД
    await db.rename_pack(name, new_title)
    await state.clear()

    await message.answer(
        f"✅ Пак переименован в <b>{new_title}</b>!",
        reply_markup=manage_pack_kb(name, pack["is_shared"]),
    )


# ─── ИДЕЯ 4: Лимит участников ────────────────────────────
@router.callback_query(F.data.startswith("setlimit:"))
async def start_set_limit(call: CallbackQuery, state: FSMContext):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack or pack["owner_id"] != call.from_user.id:
        await call.answer("Нет доступа.", show_alert=True)
        return
    cur = pack.get("max_members", 0)
    cur_str = str(cur) if cur else "не задан (∞)"
    await state.set_state(ManagePack.entering_limit)
    await state.update_data(pack_name=name)
    await call.message.edit_text(
        f"👥 Текущий лимит участников: <b>{cur_str}</b>\n\n"
        "Введи новый лимит (число от 2 до 100).\n"
        "Или отправь <b>0</b> чтобы убрать лимит:"
    )
    await call.answer()


@router.message(ManagePack.entering_limit, F.text)
async def finish_set_limit(message: Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        if limit != 0 and not (2 <= limit <= 100):
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи число от 2 до 100, или 0 чтобы убрать лимит.")
        return

    data = await state.get_data()
    name = data["pack_name"]
    pack = await db.get_pack(name)
    await db.set_pack_max_members(name, limit)
    await state.clear()

    limit_str = str(limit) if limit else "∞ (без лимита)"
    await message.answer(
        f"✅ Лимит участников установлен: <b>{limit_str}</b>",
        reply_markup=manage_pack_kb(name, pack["is_shared"]),
    )


# ─── ИДЕЯ 8: Копирование пака ────────────────────────────
@router.callback_query(F.data.startswith("copypack:"))
async def copy_pack(call: CallbackQuery, state: FSMContext):
    """
    Копирование = создаём новый пак с тем же типом/видом,
    но пустой — стикеры Telegram API не позволяет скопировать напрямую.
    Поэтому входим в режим добавления как в новый пак с теми же настройками.
    """
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return

    from bot.states.flows import NewPack
    await state.clear()
    await state.set_state(NewPack.entering_title)
    await state.update_data(
        target=pack["pack_type"],
        pack_kind=pack["media_kind"],
        is_shared=False,
        copy_hint=pack["title"],
        src_path=None,
    )
    await call.message.edit_text(
        f"📋 Копируем настройки пака <b>{pack['title']}</b>\n\n"
        f"Тип: {pack['pack_type']} · {pack['media_kind']}\n\n"
        "Введи <b>название</b> для нового пака\n"
        "(стикеры добавишь сам — Telegram не даёт копировать их напрямую):"
    )
    await call.answer()


# ─── ИДЕЯ 9: Уведомления ─────────────────────────────────
@router.callback_query(F.data.startswith("notifyset:"))
async def toggle_notify(call: CallbackQuery):
    """Переключение уведомлений для конкретного участника в конкретном паке."""
    _, pack_name, val = call.data.split(":", 2)
    notify = (val == "1")
    await db.set_member_notify(pack_name, call.from_user.id, notify)
    status = "включены ✅" if notify else "выключены ❌"
    pack = await db.get_pack(pack_name)
    title = pack["title"] if pack else pack_name
    await call.answer(f"Уведомления {status}", show_alert=False)
    try:
        await call.message.edit_reply_markup(
            reply_markup=notify_kb(pack_name, notify)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("mynotify:"))
async def my_notify_settings(call: CallbackQuery):
    """Показывает меню уведомлений для пака (вызывается участником)."""
    pack_name = call.data.split(":", 1)[1]
    pack = await db.get_pack(pack_name)
    if not pack or not pack["is_shared"]:
        await call.answer("Пак не найден.", show_alert=True)
        return
    members = await db.list_members(pack_name)
    me = next((m for m in members if m["user_id"] == call.from_user.id), None)
    notify = me["notify"] if me else 1
    await call.message.answer(
        f"🔔 Уведомления в паке <b>{pack['title']}</b>\n\n"
        "Когда участник добавляет стикер — тебе приходит сообщение.\n"
        f"Сейчас: <b>{'включены ✅' if notify else 'выключены ❌'}</b>",
        reply_markup=notify_kb(pack_name, bool(notify)),
    )
    await call.answer()
