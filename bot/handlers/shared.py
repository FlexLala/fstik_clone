"""Совместные паки: вступление по ссылке, участники, кик."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.keyboards.menus import main_menu, members_kb
from bot.services import db
from bot.states.flows import NewPack

router = Router()


def invite_link(token: str) -> str:
    return f"https://t.me/{config.bot_username}?start=join_{token}"


@router.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message, command: CommandObject,
                         state: FSMContext, bot: Bot):
    arg = (command.args or "").strip()
    if not arg.startswith("join_"):
        await state.clear()
        await message.answer("👋 Привет! Жми /start для меню.",
                             reply_markup=main_menu())
        return

    token = arg[len("join_"):]
    pack = await db.get_pack_by_token(token)
    if not pack or not pack["is_shared"]:
        await message.answer("❌ Приглашение недействительно или пак удалён.",
                             reply_markup=main_menu())
        return

    user = message.from_user
    if pack["owner_id"] == user.id:
        await message.answer("Ты владелец этого пака 🙂", reply_markup=main_menu())
        return

    await db.add_member(pack["name"], user.id, user.username)
    await state.clear()
    await state.set_state(NewPack.waiting_media)
    await state.update_data(
        target=pack["pack_type"],
        pack_kind=pack["media_kind"],
        is_shared=True,
        title=pack["title"],
        pack_name=pack["name"],
        emoji=[],
    )
    await message.answer(
        f"✅ Ты присоединился к совместному паку <b>{pack['title']}</b>!\n\n"
        "📤 Пришли фото/видео/GIF — я добавлю их в общий пак."
    )


@router.callback_query(F.data.startswith("invite:"))
async def show_invite(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack or not pack["is_shared"] or not pack["join_token"]:
        await call.answer("Это не совместный пак.", show_alert=True)
        return
    link = invite_link(pack["join_token"])
    # ПУНКТ 2: редактируем сообщение вместо отправки нового
    try:
        await call.message.edit_text(
            f"🔗 Ссылка-приглашение в <b>{pack['title']}</b>:\n\n"
            f"{link}\n\n"
            "Кто перейдёт — сможет добавлять стикеры в этот пак."
        )
    except Exception:
        await call.message.answer(
            f"🔗 Ссылка-приглашение в <b>{pack['title']}</b>:\n\n"
            f"{link}\n\n"
            "Кто перейдёт — сможет добавлять стикеры в этот пак."
        )
    await call.answer()


@router.callback_query(F.data.startswith("members:"))
async def show_members(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return
    if pack["owner_id"] != call.from_user.id:
        await call.answer("Только владелец может управлять участниками.",
                          show_alert=True)
        return
    members = await db.list_members(name)
    lines = []
    for m in members:
        tag = "👑 " if m["user_id"] == pack["owner_id"] else "• "
        who = m["username"] and f"@{m['username']}" or f"id{m['user_id']}"
        lines.append(tag + who)
    text = (f"👥 Участники <b>{pack['title']}</b> ({len(members)}):\n\n"
            + "\n".join(lines) +
            "\n\nНажми на участника ниже, чтобы исключить.")
    # ПУНКТ 2: редактируем вместо нового сообщения
    try:
        await call.message.edit_text(
            text, reply_markup=members_kb(name, members, pack["owner_id"]))
    except Exception:
        await call.message.answer(
            text, reply_markup=members_kb(name, members, pack["owner_id"]))
    await call.answer()


@router.callback_query(F.data.startswith("kick:"))
async def kick_member(call: CallbackQuery):
    _, name, uid = call.data.split(":", 2)
    uid = int(uid)
    pack = await db.get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return
    if pack["owner_id"] != call.from_user.id:
        await call.answer("Только владелец может исключать.", show_alert=True)
        return
    if uid == pack["owner_id"]:
        await call.answer("Нельзя исключить владельца.", show_alert=True)
        return

    await db.remove_member(name, uid)
    members = await db.list_members(name)
    await call.message.edit_text(
        f"✅ Участник исключён.\n👥 Осталось: {len(members)}",
        reply_markup=members_kb(name, members, pack["owner_id"]),
    )
    await call.answer("Исключён. Новые стикеры он добавлять не сможет.")
