"""Inline-меню в стиле fStikBot."""
from aiogram.types import (InlineKeyboardMarkup, ReplyKeyboardMarkup,
                            KeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def reply_menu() -> ReplyKeyboardMarkup:
    """Нижняя панель быстрых команд (кнопки под полем ввода)."""
    kb = ReplyKeyboardBuilder()
    kb.button(text="➕ Новый пак")
    kb.button(text="📁 Мои паки")
    kb.button(text="⚙️ Настройки")
    kb.button(text="❓ Помощь")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True, input_field_placeholder="Выбери действие...")


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новый пак", callback_data="new_pack")
    kb.button(text="📁 Мои паки", callback_data="my_packs")
    kb.button(text="❓ Помощь", callback_data="help")
    kb.adjust(1, 2)
    return kb.as_markup()


def choose_target() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Стикеры", callback_data="target:sticker")
    kb.button(text="✨ Эмодзи", callback_data="target:emoji")
    kb.button(text="← Отмена", callback_data="cancel")
    kb.adjust(2, 1)
    return kb.as_markup()


def choose_kind() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Статичный", callback_data="kind:static")
    kb.button(text="🎞 Видео", callback_data="kind:video")
    kb.button(text="🌟 Единый (всё в видео)", callback_data="kind:unified")
    kb.button(text="← Отмена", callback_data="cancel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def choose_shared() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Личный", callback_data="shared:0")
    kb.button(text="👥 Совместный", callback_data="shared:1")
    kb.button(text="← Отмена", callback_data="cancel")
    kb.adjust(2, 1)
    return kb.as_markup()


def confirm_sticker() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Добавить в пак", callback_data="confirm_add")
    kb.button(text="😀 Задать эмодзи", callback_data="set_emoji")
    kb.button(text="🔁 Прислать другое", callback_data="redo")
    kb.button(text="← Отмена", callback_data="cancel")
    kb.adjust(1, 1, 2)
    return kb.as_markup()


def after_add(pack_name: str, is_owner: bool, is_shared: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Открыть пак", url=f"https://t.me/addstickers/{pack_name}")
    kb.button(text="➕ Добавить ещё", callback_data="add_more")
    # ПУНКТ 1: кнопка «Редактировать пак» — перезапускает поток для этого пака
    kb.button(text="✏️ Редактировать пак", callback_data=f"edit_pack:{pack_name}")
    if is_shared and is_owner:
        kb.button(text="👥 Участники", callback_data=f"members:{pack_name}")
        kb.button(text="🔗 Ссылка-приглашение", callback_data=f"invite:{pack_name}")
    elif is_shared:
        kb.button(text="🔗 Пригласить", callback_data=f"invite:{pack_name}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1, 1, 1, 2, 1)
    return kb.as_markup()


def my_packs_kb(packs: list[dict], user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in packs[:20]:
        if p["media_kind"] == "unified":
            icon = "🌟"
        elif p["media_kind"] == "video":
            icon = "🎞"
        else:
            icon = "🖼"
        shared = "👥" if p["is_shared"] else ""
        kb.button(text=f"{icon}{shared} {p['title']}",
                  callback_data=f"pack_menu:{p['name']}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def pack_menu_kb(pack: dict, is_owner: bool) -> InlineKeyboardMarkup:
    """Меню управления конкретным паком из списка паков."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Открыть в Telegram", url=f"https://t.me/addstickers/{pack['name']}")
    kb.button(text="✏️ Редактировать (добавить стикеры)", callback_data=f"edit_pack:{pack['name']}")
    if pack["is_shared"] and is_owner:
        kb.button(text="👥 Участники", callback_data=f"members:{pack['name']}")
        kb.button(text="🔗 Ссылка-приглашение", callback_data=f"invite:{pack['name']}")
    elif pack["is_shared"]:
        kb.button(text="🔗 Пригласить", callback_data=f"invite:{pack['name']}")
    kb.button(text="◀️ Мои паки", callback_data="my_packs")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def members_kb(pack_name: str, members: list[dict], owner_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for m in members[:25]:
        if m["user_id"] == owner_id:
            continue
        name = m["username"] and f"@{m['username']}" or f"id{m['user_id']}"
        kb.button(text=f"❌ {name}", callback_data=f"kick:{pack_name}:{m['user_id']}")
    kb.button(text="🔗 Ссылка-приглашение", callback_data=f"invite:{pack_name}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


# ПУНКТ 3: меню настройки размера
def size_settings_kb(current: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for side in (512, 256, 128):
        mark = "✅ " if side == current else ""
        kb.button(text=f"{mark}{side}px", callback_data=f"size:{side}")
    kb.button(text="✏️ Свой размер", callback_data="size:custom")
    kb.button(text="🔄 Сбросить (512px)", callback_data="size:reset")
    kb.button(text="← Назад", callback_data="cancel")
    kb.adjust(3, 1, 1, 1)
    return kb.as_markup()


# ПУНКТ 4: предложение ускорить видео
def speed_up_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡ Ускорить до 3 сек", callback_data="speed:up")
    kb.button(text="✂️ Просто обрезать", callback_data="speed:cut")
    kb.adjust(2)
    return kb.as_markup()
