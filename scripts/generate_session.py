#!/usr/bin/env python3
"""
Скрипт для генерации строки сессии Telethon для video-clipper.

Использование:
    python scripts/generate_session.py

Поддерживает два метода авторизации:
1. QR-код — сканируй в Telegram (Настройки → Устройства → Подключить)
2. Телефон + SMS/код — классический способ

Результат сохраняется в creds.json как "session_string".
"""
import asyncio
import json
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


def load_creds():
    """Загрузить api_id и api_hash из creds.json."""
    try:
        with open("creds.json", encoding="utf-8") as f:
            creds = json.load(f)
        api_id = creds.get("api_id")
        api_hash = creds.get("api_hash")
        if not api_id or not api_hash:
            print("Ошибка: В creds.json отсутствуют api_id или api_hash")
            sys.exit(1)
        return int(api_id), api_hash
    except FileNotFoundError:
        print("Ошибка: Файл creds.json не найден")
        print("Создайте его на основе creds.example.json")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка: Не удалось прочитать creds.json: {e}")
        sys.exit(1)


def save_session(session_string: str):
    """Сохранить session_string в creds.json."""
    try:
        with open("creds.json", encoding="utf-8") as f:
            creds = json.load(f)
        creds["session_string"] = session_string
        with open("creds.json", "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=4)
        print()
        print("=" * 60)
        print("Session string сохранена в creds.json!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print("Не удалось сохранить автоматически.")
        print("Добавьте вручную в creds.json:")
        print(f'"session_string": "{session_string}"')
        print(f"Ошибка: {e}")
        print("=" * 60)


async def qr_login(api_id: int, api_hash: str) -> str | None:
    """Авторизация через QR-код."""
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    try:
        qr = await client.qr_login()
    except Exception as e:
        print(f"Ошибка QR-авторизации: {e}")
        await client.disconnect()
        return None

    print()
    print("=" * 60)
    print("  Отсканируй QR-код в Telegram:")
    print("  Настройки -> Устройства -> Подключить устройство")
    print("=" * 60)
    print()

    try:
        import qrcode
        qr_img = qrcode.QRCode(version=1, box_size=1, border=1)
        qr_img.add_data(qr.url)
        qr_img.make(fit=True)
        qr_img.print_ascii(invert=True)
    except ImportError:
        print(f"QR URL: {qr.url}")
        print()
        print("Для отображения QR в терминале: pip install qrcode")

    print()
    print("Ожидание сканирования (120 сек)...")

    try:
        await qr.wait(timeout=120)
        session_string = client.session.save()
        me = await client.get_me()
        print(f"\nУспех! {me.first_name} (ID: {me.id})")
        await client.disconnect()
        return session_string
    except asyncio.TimeoutError:
        print("\nТаймаут — QR не отсканирован за 120 секунд")
        await client.disconnect()
        return None
    except Exception as e:
        print(f"\nОшибка: {e}")
        await client.disconnect()
        return None


async def phone_login(api_id: int, api_hash: str) -> str | None:
    """Авторизация по номеру телефона."""
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    phone = input("Номер телефона (с +, например +79991234567): ")
    await client.send_code_request(phone)

    code = input("Код подтверждения из Telegram: ")
    try:
        await client.sign_in(phone, code)
    except Exception as e:
        if "password" in str(e).lower():
            password = input("Пароль двухфакторной аутентификации: ")
            await client.sign_in(password=password)
        else:
            print(f"Ошибка: {e}")
            await client.disconnect()
            return None

    session_string = client.session.save()
    me = await client.get_me()
    print(f"\nУспех! {me.first_name} (ID: {me.id})")
    await client.disconnect()
    return session_string


async def main():
    print("=" * 60)
    print("  Генератор строки сессии Telethon — video-clipper")
    print("=" * 60)

    api_id, api_hash = load_creds()
    print(f"API ID: {api_id}")
    print()

    print("Выберите метод авторизации:")
    print("  1 — QR-код (рекомендуется)")
    print("  2 — Номер телефона + код")
    print()

    choice = input("Выбор (1/2): ").strip()

    if choice == "2":
        session_string = await phone_login(api_id, api_hash)
    else:
        session_string = await qr_login(api_id, api_hash)

    if session_string:
        save_session(session_string)
        print()
        print("ВАЖНО: НЕ публикуйте creds.json в репозитории!")
    else:
        print("\nСессия не создана.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nПрервано")
        sys.exit(1)
