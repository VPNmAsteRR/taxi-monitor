#!/usr/bin/env python3
"""
Вход по QR-коду (не нужен код из Telegram).

Запуск на сервере:
    .venv/bin/python tools/qr_login.py

Скрипт создаёт QR (data/qr.png) и ждёт сканирования.
Телефон: Telegram → Настройки → Устройства → Подключить устройство → сканировать QR.

После успеха печатает SESSION_STRING.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config as cfg_mod  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402

QR_PATH = BASE / "data" / "qr.png"
RESULT_PATH = BASE / "data" / "session_string.txt"
STATUS_PATH = BASE / "data" / "qr_status.txt"


def render(url: str) -> None:
    import qrcode

    img = qrcode.make(url)
    QR_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(QR_PATH)


async def main() -> int:
    conf = cfg_mod.load()
    problem = conf.validate()
    if problem:
        print(f"[!] {problem}")
        return 2

    client = TelegramClient(StringSession(), conf.api_id, conf.api_hash, device_model="taxi-monitor")
    await client.connect()

    deadline = time.time() + 1800
    while time.time() < deadline:
        try:
            qr = await client.qr_login()
            render(qr.url)
            STATUS_PATH.write_text(f"waiting {int(time.time())}\n", encoding="utf-8")
            print(f"[+] QR готов: {QR_PATH}  (обновляется каждые ~30 c)")
            try:
                await qr.wait(timeout=20)
                break
            except asyncio.TimeoutError:
                continue
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "SessionPasswordNeededError":
                STATUS_PATH.write_text("2fa\n", encoding="utf-8")
                print("[!] Включена 2FA — нужен пароль облачной защиты Telegram")
                password = sys.argv[1] if len(sys.argv) > 1 else None
                if not password:
                    print("    Запустите: .venv/bin/python tools/qr_login.py '<пароль 2FA>'")
                    await client.disconnect()
                    return 3
                await client.sign_in(password=password)
                break
            print(f"[!] {exc}")
            await asyncio.sleep(2)

    if not await client.is_user_authorized():
        print("[!] Время вышло, вход не выполнен")
        STATUS_PATH.write_text("timeout\n", encoding="utf-8")
        await client.disconnect()
        return 4

    me = await client.get_me()
    session_string = StringSession.save(client.session)
    RESULT_PATH.write_text(session_string, encoding="utf-8")
    RESULT_PATH.chmod(0o600)
    STATUS_PATH.write_text("ok\n", encoding="utf-8")
    print(f"[+] Вошли как {me.first_name or ''} @{me.username or '—'} (id={me.id})")
    print(f"[+] Session string сохранена в {RESULT_PATH}")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
