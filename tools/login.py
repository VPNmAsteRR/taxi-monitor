#!/usr/bin/env python3
"""
Одноразовый вход в аккаунт Telegram → получить SESSION_STRING для .env.

Запуск НА СЕРВЕРЕ (интерактивно, нужен код из Telegram):
    cd /opt/taxi-monitor
    .venv/bin/python tools/login.py

Спросит:
  1. телефон в формате +79991234567
  2. код из Telegram (придёт в приложение/чат «Telegram»)
  3. пароль 2FA, если включён

На выходе напечатает строку SESSION_STRING — вставьте её в .env.
Строка = полный доступ к аккаунту. Никому не передавайте.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg_mod  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402


async def main() -> int:
    conf = cfg_mod.load()
    problem = conf.validate()
    if problem:
        print(f"[!] {problem}")
        print("    Сначала получите API_ID/API_HASH на https://my.telegram.org")
        print("    и заполните .env")
        return 2

    print("Вход в аккаунт Telegram для taxi-monitor")
    print("─" * 45)
    async with TelegramClient(
        StringSession(), conf.api_id, conf.api_hash, device_model="taxi-monitor-login"
    ) as client:
        await client.start(
            phone=lambda: input("Телефон (+79991234567): ").strip(),
            password=lambda: input("Пароль 2FA (если есть, иначе Enter): ").strip(),
            code_callback=lambda: input("Код из Telegram: ").strip(),
        )
        me = await client.get_me()
        print(f"\n[+] Вошли как {me.first_name or ''} @{me.username or '—'} (id={me.id})")
        session_string = StringSession.save(client.session)

    print("\nДобавьте в .env на сервере:\n")
    print(f"SESSION_STRING={session_string}\n")
    print("После этого перезапустите: systemctl restart taxi-monitor")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
