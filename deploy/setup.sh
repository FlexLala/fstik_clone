#!/usr/bin/env python3
"""
Интерактивный установщик fStik-clone.
Запуск: python setup.py
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def ask(prompt: str, default: str = "") -> str:
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val or default
    while True:
        val = input(f"{prompt}: ").strip()
        if val:
            return val
        print("  ⚠️  Поле не может быть пустым.")


def main():
    print("\n" + "=" * 50)
    print("  🤖  fStik-clone — Установщик")
    print("=" * 50 + "\n")

    # --- Токен ---
    print("Открой @BotFather в Telegram, создай бота и скопируй токен.")
    token = ask("Ваш токен бота")

    # --- Имя пользователя бота ---
    print("\nИмя пользователя бота (без @), например: my_sticker_bot")
    username = ask("Имя пользователя бота (без @)").lstrip("@")

    # --- FFmpeg ---
    ffmpeg = ask("Путь к ffmpeg", default="ffmpeg")
    ffprobe = ask("Путь к ffprobe", default="ffprobe")

    # --- Записываем .env ---
    env_content = (
        f"BOT_TOKEN={token}\n"
        f"BOT_USERNAME={username}\n"
        f"FFMPEG_BIN={ffmpeg}\n"
        f"FFPROBE_BIN={ffprobe}\n"
    )
    ENV_FILE.write_text(env_content, encoding="utf-8")
    print(f"\n✅ Файл .env создан: {ENV_FILE}")

    # --- Установка зависимостей ---
    print("\n📦 Устанавливаю зависимости (pip install -r requirements.txt)...")
    req = BASE_DIR / "requirements.txt"
    if req.exists():
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            capture_output=False,
        )
        if result.returncode == 0:
            print("✅ Зависимости установлены.")
        else:
            print("⚠️  Установка зависимостей завершилась с ошибкой. Проверь вывод выше.")
    else:
        print("⚠️  requirements.txt не найден, пропускаю.")

    print("\n" + "=" * 50)
    print("  🚀  Всё готово! Запусти бота командой:")
    print("       python main.py")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
