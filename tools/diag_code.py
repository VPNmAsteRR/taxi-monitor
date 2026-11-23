#!/usr/bin/env python3
"""Диагностика: каким способом Telegram отправляет код входа."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config as cfg_mod  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402


async def main() -> int:
    conf = cfg_mod.load()
    phone = sys.argv[1] if len(sys.argv) > 1 else "+79150065975"

    client = TelegramClient(StringSession(), conf.api_id, conf.api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        print(f"Аккаунт в этой сессии: {'да' if await client.is_user_authorized() else 'нет'}")
        print(f"Тип отправки кода: {type(sent.type).__name__}")
        print(f"Детали: {sent.type}")
        print(f"Timeout: {sent.timeout}s | NextType: {sent.next_type}")
        # сохраним pending, чтобы можно было сразу ввести код
        import json
        p = BASE / "data" / "login_pending.json"
        p.write_text(json.dumps({"phone": phone, "phone_code_hash": sent.phone_code_hash}), encoding="utf-8")
        print("pending сохранён — можно вводить код: tools/login_step.py code <КОД>")
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
