from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.menus import main_menu, my_packs_kb
from bot.services.db import list_packs

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
    "   - подгоню пропорции (512px или 100x100), не обрезая;\n"
    "   - сожму видео под лимиты Telegram (VP9, &lt;3с, &lt;256KB, без звука).\n"
    "3. Покажу предпросмотр и предложу что-то поменять.\n\n"
    "⚠️ В одном паке Telegram держит <b>один тип</b>: либо статичные, "
    "либо видео-стикеры. Если контент не подходит — предложу отдельный пак."
)


@router.message(CommandStart(deep_link=False))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        WELCOME.format(name=message.from_user.first_name),
        reply_markup=main_menu(),
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
    await call.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == "my_packs")
async def my_packs(call: CallbackQuery):
    packs = await list_packs(call.from_user.id)
    if not packs:
        await call.message.answer("У тебя пока нет паков. Создай первый!",
                                  reply_markup=main_menu())
    else:
        await call.message.answer(f"📁 Твои паки ({len(packs)}):",
                                  reply_markup=my_packs_kb(packs, call.from_user.id))
    await call.answer()
