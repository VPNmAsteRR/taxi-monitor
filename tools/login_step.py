#!/usr/bin/env python3
"""
Двухшаговый вход в аккаунт (для запуска через SSH без интерактивной консоли).

Шаг 1 — запросить код:
    .venv/bin/python tools/login_step.py request +79991234567

Шаг 2 — ввести код (и пароль 2FA, если включён):
    .venv/bin/python tools/login_step.py code 12345
    .venv/bin/python tools/login_step.py code 12345 --password мойпароль

После успеха печатает SESSION_STRING для .env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config as cfg_mod  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402

PENDING = BASE / "data" / "login_pending.json"
SESSION_FILE = BASE / "data" / "login_session"


def _client(conf) -> TelegramClient:
    # временная файловая сессия, чтобы между шагами сохранился auth key
    return TelegramClient(str(SESSION_FILE), conf.api_id, conf.api_hash, device_model="taxi-monitor")


async def request(conf, phone: str) -> int:
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    client = _client(conf)
    await client.connect()
    try:
        sent = await client.send_code_request(phone, force_sms=True)
    finally:
        await client.disconnect()
    PENDING.write_text(
        json.dumps({"phone": phone, "phone_code_hash": sent.phone_code_hash}), encoding="utf-8"
    )
    print(f"[+] Код отправлен на {phone}. Введите его из Telegram:")
    print("    .venv/bin/python tools/login_step.py code <КОД>")
    return 0


async def submit(conf, code: str, password: str | None) -> int:
    if not PENDING.exists():
        print("[!] Сначала: tools/login_step.py request +7999...")
        return 2
    data = json.loads(PENDING.read_text(encoding="utf-8"))

    client = _client(conf)
    await client.connect()
    try:
        try:
            await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "SessionPasswordNeededError":
                if not password:
                    print("[!] Включена 2FA. Повторите с --password <пароль>:")
                    print(f"    .venv/bin/python tools/login_step.py code {code} --password ***")
                    return 3
                await client.sign_in(password=password)
            else:
                print(f"[!] Ошибка входа: {exc}")
                return 4

        me = await client.get_me()
        session_string = StringSession.save(client.session)
        print(f"[+] Вошли как {me.first_name or ''} @{me.username or '—'} (id={me.id})")
    finally:
        await client.disconnect()

    PENDING.unlink(missing_ok=True)
    print("\n=== Добавьте в /opt/taxi-monitor/.env ===")
    print(f"SESSION_STRING={session_string}\n")
    print("Затем: systemctl restart taxi-monitor")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["request", "code"])
    ap.add_argument("value")
    ap.add_argument("--password", default=None)
    args = ap.parse_args()

    conf = cfg_mod.load()
    problem = conf.validate()
    if problem:
        print(f"[!] {problem}")
        return 2

    if args.action == "request":
        return asyncio.run(request(conf, args.value))
    return asyncio.run(submit(conf, args.value, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
