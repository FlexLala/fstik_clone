from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.menus import (main_menu, my_packs_kb, pack_menu_kb,
                                 size_settings_kb, reply_menu, choose_target)
from bot.services.db import get_pack, get_user_max_side, list_packs, set_user_max_side
from bot.states.flows import NewPack

router = Router()

WELCOME = (
    "👋 <b>Привет, {name}!</b>\n\n"
    "Я делаю стикеры и эмодзи из <b>фото, видео и GIF</b> — "
    "сам подгоняю размер и формат под Telegram.\n\n"
    "Просто жми «➕ Новый пак»."
)

HELP = (
    "<b>Как это работает</b>\n\n"
    "1. Создаёшь пак и выбираешь тип: <b>стикеры</b> или <b>эмодзи</b>.\n"
    "2. Кидаешь фото / видео / GIF — я сам:\n"
    "   - определю, статичный это или анимированный контент;\n"
    "   - подгоню пропорции (до 512px или своего размера), не обрезая;\n"
    "   - сожму видео под лимиты Telegram (VP9, &lt;3с, &lt;256KB, без звука).\n"
    "3. Покажу предпросмотр и предложу что-то поменять.\n\n"
    "⚠️ В одном паке Telegram держит <b>один тип</b>: либо статичные, "
    "либо видео-стикеры. Если контент не подходит — предложу отдельный пак.\n\n"
    "📐 Размер стикера можно изменить в /settings."
)


@router.message(CommandStart(deep_link=False))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # Сначала показываем reply-клавиатуру (нижняя панель)
    await message.answer(
        WELCOME.format(name=message.from_user.first_name),
        reply_markup=reply_menu(),
    )


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP, reply_markup=main_menu())


@router.callback_query(F.data == "help")
async def help_cb(call: CallbackQuery):
    await call.message.answer(HELP, reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == "menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    # ПУНКТ 2: редактируем текущее сообщение вместо отправки нового
    try:
        await call.message.edit_text("🏠 Главное меню", reply_markup=main_menu())
    except Exception:
        await call.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == "my_packs")
async def my_packs(call: CallbackQuery):
    packs = await list_packs(call.from_user.id)
    if not packs:
        try:
            await call.message.edit_text(
                "У тебя пока нет паков. Создай первый!",
                reply_markup=main_menu(),
            )
        except Exception:
            await call.message.answer(
                "У тебя пока нет паков. Создай первый!",
                reply_markup=main_menu(),
            )
    else:
        try:
            await call.message.edit_text(
                f"📁 Твои паки ({len(packs)}):",
                reply_markup=my_packs_kb(packs, call.from_user.id),
            )
        except Exception:
            await call.message.answer(
                f"📁 Твои паки ({len(packs)}):",
                reply_markup=my_packs_kb(packs, call.from_user.id),
            )
    await call.answer()


# ПУНКТ 1: переход в меню пака из списка паков
@router.callback_query(F.data.startswith("pack_menu:"))
async def pack_menu(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    pack = await get_pack(name)
    if not pack:
        await call.answer("Пак не найден.", show_alert=True)
        return
    is_owner = pack["owner_id"] == call.from_user.id
    icon = {"unified": "🌟", "video": "🎞"}.get(pack["media_kind"], "🖼")
    shared_str = "👥 Совместный" if pack["is_shared"] else "👤 Личный"
    text = (
        f"{icon} <b>{pack['title']}</b>\n"
        f"{shared_str} · {pack['media_kind']}"
    )
    try:
        await call.message.edit_text(text, reply_markup=pack_menu_kb(pack, is_owner))
    except Exception:
        await call.message.answer(text, reply_markup=pack_menu_kb(pack, is_owner))
    await call.answer()


# ПУНКТ 3: настройки размера
# ─── Обработчики кнопок нижней reply-панели ───────────────
@router.message(F.text == "➕ Новый пак")
async def reply_new_pack(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewPack.choosing_target)
    await message.answer("📦 <b>Новый пак</b>\nЧто создаём?",
                         reply_markup=choose_target())


@router.message(F.text == "📁 Мои паки")
async def reply_my_packs(message: Message):
    packs = await list_packs(message.from_user.id)
    if not packs:
        await message.answer("У тебя пока нет паков. Создай первый!",
                             reply_markup=main_menu())
    else:
        await message.answer(f"📁 Твои паки ({len(packs)}):",
                             reply_markup=my_packs_kb(packs, message.from_user.id))


@router.message(F.text == "❓ Помощь")
async def reply_help(message: Message):
    await message.answer(HELP, reply_markup=main_menu())


@router.message(F.text == "⚙️ Настройки")
async def reply_settings(message: Message):
    current = await get_user_max_side(message.from_user.id)
    await message.answer(
        f"📐 <b>Размер стикера</b>\n\n"
        f"Текущий максимум длинной стороны: <b>{current}px</b>\n\n"
        "Выбери новый размер или введи свой (от 50 до 512):",
        reply_markup=size_settings_kb(current),
    )


@router.message(Command("settings"))
async def settings_cmd(message: Message):
    current = await get_user_max_side(message.from_user.id)
    await message.answer(
        f"📐 <b>Размер стикера</b>\n\n"
        f"Текущий максимум длинной стороны: <b>{current}px</b>\n\n"
        "Выбери новый размер или введи свой (от 50 до 512):",
        reply_markup=size_settings_kb(current),
    )


@router.callback_query(F.data.startswith("size:"))
async def change_size(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]

    if val == "reset":
        await set_user_max_side(call.from_user.id, 512)
        await call.message.edit_text(
            "✅ Размер сброшен до <b>512px</b>.",
            reply_markup=size_settings_kb(512),
        )
        await call.answer("Сброшено!")
        return

    if val == "custom":
        await state.set_state(NewPack.setting_max_side)
        await call.message.answer(
            "✏️ Введи размер (целое число от 50 до 512):"
        )
        await call.answer()
        return

    try:
        side = int(val)
        side = max(50, min(512, side))
        await set_user_max_side(call.from_user.id, side)
        await call.message.edit_text(
            f"✅ Размер установлен: <b>{side}px</b>.",
            reply_markup=size_settings_kb(side),
        )
        await call.answer(f"Установлено {side}px!")
    except ValueError:
        await call.answer("Ошибка значения.", show_alert=True)


@router.message(NewPack.setting_max_side, F.text)
async def custom_size_input(message: Message, state: FSMContext):
    try:
        side = int(message.text.strip())
        if not (50 <= side <= 512):
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи целое число от 50 до 512.")
        return

    await set_user_max_side(message.from_user.id, side)
    await state.clear()
    await message.answer(
        f"✅ Размер установлен: <b>{side}px</b>.\n"
        "Этот размер будет использован при следующей конвертации.\n"
        "Сбросить: /settings",
        reply_markup=main_menu(),
    )
