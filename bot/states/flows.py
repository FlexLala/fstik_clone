from aiogram.fsm.state import State, StatesGroup


class NewPack(StatesGroup):
    choosing_target = State()    # стикеры или эмодзи
    choosing_kind = State()      # статичный / видео / единый
    choosing_shared = State()    # личный / совместный
    entering_title = State()     # название набора
    waiting_media = State()      # ждём медиа
    confirming = State()         # предпросмотр
    waiting_emoji = State()      # эмодзи для стикера
    setting_max_side = State()   # ввод кастомного размера (пункт 3)
    speed_confirm = State()      # подтверждение ускорения видео (пункт 4)
