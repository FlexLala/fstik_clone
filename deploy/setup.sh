#!/usr/bin/env bash
# Запускать на сервере из каталога /opt/fstik_clone
set -e

echo "==> Системные зависимости"
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg

echo "==> Проверка VP9"
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libvpx-vp9; then
  echo "   OK: libvpx-vp9 найден"
else
  echo "   ВНИМАНИЕ: libvpx-vp9 не найден!"; exit 1
fi

echo "==> Виртуальное окружение"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "==> Конфиг"
[ -f .env ] || cp .env.example .env
echo "   Отредактируй .env (BOT_TOKEN, BOT_USERNAME): nano .env"

echo "==> Готово. Дальше — установка systemd-сервиса (см. README)."
