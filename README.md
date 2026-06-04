# fStik-clone — быстрый конструктор стикерпаков для Telegram

Бот на **aiogram 3** + **FFmpeg**, который из фото/видео/GIF сам собирает
стикеры и эмодзи, автоматически подгоняя формат и пропорции под Telegram.

## Что умеет
- Сам определяет тип контента (статичный / анимированный) и выбирает выход:
  `.webp` (статика) или `.webm`/VP9 (видео).
- Сам приводит размеры: длинная сторона = **512px** (стикеры) или **100×100** (эмодзи),
  без обрезки — добавляет прозрачные поля.
- Сам ужимает видео под лимиты: ≤3с, ≤30 FPS, ≤256KB, без звука, зацикленное.
- Inline-меню в стиле fStikBot: Новый пак → тип → название → медиа → предпросмотр → готово.
- Хранит твои паки в SQLite, защищает от смешивания статики и видео в одном паке.

## Архитектура
```
main.py                  — запуск, polling
bot/config.py            — чтение .env
bot/services/media.py    — ★ конвертация (ffprobe/ffmpeg/Pillow)
bot/services/stickers.py — обёртка над Bot API стикерпаков
bot/services/db.py       — SQLite (aiosqlite)
bot/handlers/start.py    — /start, меню, помощь, мои паки
bot/handlers/newpack.py  — ★ весь поток создания пака
bot/keyboards/menus.py   — inline-клавиатуры
bot/states/flows.py      — FSM-состояния
```

## Установка на Ubuntu 22 (рядом с другими ботами)

```bash
# 1. системные зависимости
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg

# проверь, что есть VP9 (нужен libvpx-vp9):
ffmpeg -hide_banner -encoders | grep vp9   # должно показать libvpx-vp9

# 2. проект
cd /opt                      # или твой каталог с ботами
git clone <твой-репо> fstik_clone   # либо просто скопируй папку
cd fstik_clone

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. конфиг
cp .env.example .env
nano .env        # впиши BOT_TOKEN и BOT_USERNAME (без @)

# 4. запуск вручную для проверки
python main.py
```

## Автозапуск через systemd (чтобы жил рядом с другими ботами)

Создай `/etc/systemd/system/fstik-clone.service`:

```ini
[Unit]
Description=fStik clone Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/opt/fstik_clone
ExecStart=/opt/fstik_clone/.venv/bin/python /opt/fstik_clone/main.py
Restart=always
RestartSec=5
# опционально ограничить ресурсы, чтобы ffmpeg не съел сервер:
CPUQuota=80%
MemoryMax=1G

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fstik-clone
sudo systemctl status fstik-clone
journalctl -u fstik-clone -f      # логи
```

## Важные нюансы Telegram
- У одного бота на одного пользователя своё имя набора. Имя = `[a-z0-9_]`,
  обязано заканчиваться на `_by_<bot_username>` — это уже зашито.
- Создать стикер пользователю можно только если он раньше писал боту (он автор).
- Анимированные (.tgs) пакеты тут не делаются — только static (.webp) и video (.webm).
  Это сознательно: video-стикеры покрывают 99% «живых» мемов из видео/GIF.

## Идеи для развития
- Несколько стикеров одним сообщением (media group) — добавить хендлер на album.
- Очередь обработки (например, asyncio.Semaphore), чтобы ffmpeg не грузил все ядра.
- Удаление/переупорядочивание стикеров (deleteStickerFromSet / setStickerPositionInSet).
- Telegram Mini App для совсем красивого UI (следующий этап).

## Обновление: единый пак, очередь, совместные паки

### Единый пак (статика + видео вместе)
При создании пак спрашивает вид: **Статичный / Видео / Единый**.
В режиме «Единый» (🌟) статичные картинки автоматически конвертируются в
зацикленный VP9/WEBM (1с), поэтому лежат в одном паке с настоящими видео.
Реализация: `media.process(src, target, force_video=True)` → `_static_to_webm`.

### Очередь обработки (`bot/services/queue.py`)
Глобальный Semaphore ограничивает число одновременных ffmpeg-задач
(`MAX_CONCURRENT`, по умолчанию 2). Остальные ждут; пользователю показывается
позиция в очереди. Подбери `MAX_CONCURRENT` под ядра сервера (обычно ядра-1,
но оставь запас другим ботам).

### Совместные паки
- При создании можно выбрать **Совместный** (👥).
- Владелец получает **ссылку-приглашение** `t.me/<bot>?start=join_<token>`.
- Любой перешедший становится участником и может добавлять стикеры в общий пак.
- Контент кладётся в набор от имени **владельца** (требование Telegram API),
  поэтому участники могут наполнять пак даже если они не его создатели.
- Только **владелец** видит список участников и может **исключать** (кик).
  Исключённый сразу теряет возможность добавлять (проверка `db.is_member`).

Таблицы БД: `packs` (+ `owner_id`, `is_shared`, `join_token`, `media_kind=unified`),
`members` (pack_name, user_id, username).

### ⚠️ Важно про FSM-хранилище
Сейчас используется `MemoryStorage` — состояние теряется при рестарте бота.
Для продакшена с совместными паками лучше переключить на Redis:
`pip install redis`, затем `RedisStorage.from_url("redis://localhost:6379/0")`
в `main.py`. Данные о паках/участниках уже в SQLite и переживают рестарт —
теряется только незавершённый шаг создания.

## Деплой на сервер (Ryzen 1 ядро / 2 ГБ)

### Способ A — через git (рекомендую)
На своём компе:
```bash
cd fstik_clone
git init && git add . && git commit -m "init"
# залей на GitHub/GitLab (приватный репо) или свой gitea
git remote add origin git@github.com:USER/fstik_clone.git
git push -u origin master
```
На сервере:
```bash
sudo mkdir -p /opt/fstik_clone && sudo chown $USER /opt/fstik_clone
git clone git@github.com:USER/fstik_clone.git /opt/fstik_clone
cd /opt/fstik_clone
bash deploy/setup.sh        # ставит ffmpeg, venv, зависимости
nano .env                   # BOT_TOKEN, BOT_USERNAME
```

### Способ B — без git, напрямую (scp/rsync)
На своём компе из папки с проектом:
```bash
# rsync аккуратно исключает мусор
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.env' \
      --exclude 'storage/tmp/*' --exclude 'storage/db/*.sqlite3' \
      ./ USER@SERVER_IP:/opt/fstik_clone/
# затем на сервере:
ssh USER@SERVER_IP
cd /opt/fstik_clone && bash deploy/setup.sh && nano .env
```

### Установка автозапуска (оба способа)
```bash
# подставь своего пользователя в unit
sed "s/__USER__/$USER/" deploy/fstik-clone.service | sudo tee /etc/systemd/system/fstik-clone.service
sudo systemctl daemon-reload
sudo systemctl enable --now fstik-clone
sudo systemctl status fstik-clone
journalctl -u fstik-clone -f   # живые логи
```

## Рекомендации под слабый сервер (1 ядро / 2 ГБ)
- `MAX_CONCURRENT = 1` в `bot/services/queue.py` — НЕ запускать 2 ffmpeg на 1 ядре.
- ffmpeg уже настроен бережно: `-threads 1 -row-mt 1 -deadline realtime -cpu-used 5`.
- systemd-unit ограничивает бота: `MemoryMax=1300M`, `CPUQuota=85%`, `Nice=5`.
- **Сделай swap 2 ГБ** — дешёвая страховка от OOM при пиках:
  ```bash
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```
- Диск: входные/выходные файлы автоматически удаляются из `storage/tmp` после
  обработки, так что 25 ГБ свободного места — с огромным запасом.

### Вывод по железу
1 ядро / 2 ГБ / 25 ГБ свободно — **подходит** для старта и десятков активных
пользователей. Конвертация короткого видео занимает ~доли–единицы секунд;
очередь (1 слот) сглаживает пики, а лимиты systemd защищают соседние боты.
Если бот «выстрелит» (сотни одновременных) — добавишь ядро/память и поднимешь
`MAX_CONCURRENT`.
