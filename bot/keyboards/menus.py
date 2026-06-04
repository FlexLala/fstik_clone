"""Inline-меню в стиле fStikBot."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
    """Тип содержимого пака."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Статичный", callback_data="kind:static")
    kb.button(text="🎞 Видео", callback_data="kind:video")
    kb.button(text="🌟 Единый (всё в видео)", callback_data="kind:unified")
    kb.button(text="← Отмена", callback_data="cancel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def choose_shared() -> InlineKeyboardMarkup:
    """Личный или совместный пак."""
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
    if is_shared and is_owner:
        kb.button(text="👥 Участники", callback_data=f"members:{pack_name}")
        kb.button(text="🔗 Ссылка-приглашение", callback_data=f"invite:{pack_name}")
    elif is_shared:
        kb.button(text="🔗 Пригласить", callback_data=f"invite:{pack_name}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1, 1, 2, 1)
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
                  url=f"https://t.me/addstickers/{p['name']}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def members_kb(pack_name: str, members: list[dict], owner_id: int) -> InlineKeyboardMarkup:
    """Список участников с кнопкой кикнуть (для владельца)."""
    kb = InlineKeyboardBuilder()
    for m in members[:25]:
        if m["user_id"] == owner_id:
            continue  # владельца не кикаем
        name = m["username"] and f"@{m['username']}" or f"id{m['user_id']}"
        kb.button(text=f"❌ {name}", callback_data=f"kick:{pack_name}:{m['user_id']}")
    kb.button(text="🔗 Ссылка-приглашение", callback_data=f"invite:{pack_name}")
    kb.button(text="🏠 В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()
