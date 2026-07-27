# 🎨 Telegram-stickerBOT-lite 
(аналог fStik)

> Telegram-бот для создания стикерпаков из фото, видео и GIF — быстро, без лишних кнопок.

Просто кидаешь медиа → бот сам подгоняет размер и формат → стикер готов в паке.

---

## ✨ Возможности

- 🖼 **Фото → стикер** — конвертирует в WebP, подгоняет до 512px
- 🎞 **Видео / GIF → стикер** — VP9/WebM, обрезает до 3 сек, убирает звук, сжимает до 256KB
- 🌟 **Единый пак** — статика и видео вместе (картинки становятся зацикленными видео)
- ✂️ **Режим кадрирования** — выбери: вписать с полями или обрезать до квадрата
- 🔍 **Шарпенинг** — автоматическое улучшение резкости стикеров
- 👥 **Совместные паки** — пригласи друзей по ссылке, все добавляют стикеры в общий пак
- 👑 **Лимит участников** — ограничь количество людей в совместном паке
- 🔔 **Уведомления** — участники получают сообщение о новых стикерах
- ✏️ **Редактирование** — возвращайся в любой пак и докидывай стикеры
- 📐 **Свой размер** — выбери сторону от 50 до 512px через `/settings`
- ⚡ **Ускорение видео** — если видео длиннее 3 сек, бот предложит ускорить или обрезать
- ⏳ **Очередь** — если несколько человек одновременно, никто не потеряется

---

## 🚀 Быстрый старт

### Что нужно
- Python 3.10+
- FFmpeg с поддержкой VP9 (`libvpx-vp9`)
- Токен бота от [@BotFather](https://t.me/BotFather)

### 1. Клонируй репозиторий
```bash
git clone https://github.com/FlexLala/fstik_clone.git
cd fstik_clone
```

### 2. Запусти установщик
```bash
python setup.py
```
Он спросит токен бота, имя бота (без @) и создаст `.env` автоматически.

### 3. Запусти бота
```bash
python main.py
```

Напиши боту `/start` — всё готово! 🎉

---

## 🖥 Деплой на сервер (Ubuntu 22.04)

### Системные зависимости
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip ffmpeg
```

Проверь поддержку VP9:
```bash
ffmpeg -hide_banner -encoders | grep vp9
# Должно показать: libvpx-vp9
```

### Клонируй и настрой
```bash
cd /opt
git clone https://github.com/FlexLala/fstik_clone.git
cd fstik_clone
python setup.py
```

### Автозапуск через systemd
```bash
sudo nano /etc/systemd/system/fstik.service
```

Вставь:
```ini
[Unit]
Description=fStik Clone Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/fstik_clone
ExecStart=/opt/fstik_clone/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запусти:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fstik
sudo systemctl status fstik
```

### Обновление в будущем
```bash
cd /opt/fstik_clone
git pull
sudo systemctl restart fstik
```

### Перенос данных между серверами
Если переносишь бота на новый сервер, **не забудь скопировать**:
```
storage/db/bot.sqlite3
```
Это база данных с информацией о паках, участниках и настройках. Без неё бот не будет видеть старые паки.

---

## ⚙️ Конфигурация (.env)

| Переменная | Описание | По умолчанию |
|------------|---------|--------------|
| `BOT_TOKEN` | Токен бота от @BotFather | ❌ Обязательно |
| `BOT_USERNAME` | Юзернейм бота (без @) | ❌ Обязательно |
| `FFMPEG_BIN` | Путь к ffmpeg | `ffmpeg` |
| `FFPROBE_BIN` | Путь к ffprobe | `ffprobe` |

---

## 🔧 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/help` | Справка по боту |
| `/settings` | Настройки размера стикера |

---

## 📁 Структура проекта

```
bot/
├── config.py          # Конфигурация и загрузка .env
├── handlers/
│   ├── start.py       # Команды /start, /help, /settings
│   ├── newpack.py     # Создание и редактирование паков
│   ├── manage.py      # Управление паками
│   └── shared.py      # Совместные паки и приглашения
├── keyboards/
│   └── menus.py       # Все клавиатуры бота
├── services/
│   ├── db.py          # SQLite хранилище
│   ├── media.py       # Обработка медиа (ffmpeg, PIL)
│   ├── stickers.py    # Telegram Bot API обёртка
│   └── queue.py       # Очередь обработки
└── states/
    └── flows.py       # FSM состояния
```

---

## 📝 Лицензия

MIT
