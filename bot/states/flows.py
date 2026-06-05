from aiogram.fsm.state import State, StatesGroup


class NewPack(StatesGroup):
    choosing_target = State()
    choosing_kind = State()
    choosing_shared = State()
    entering_title = State()
    waiting_media = State()
    confirming = State()
    waiting_emoji = State()
    setting_max_side = State()
    speed_confirm = State()


class ManagePack(StatesGroup):
    entering_new_title = State()   # переименование
    entering_limit = State()       # лимит участников
