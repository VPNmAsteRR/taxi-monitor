#!/usr/bin/env python3
"""Перезапрос кода с попыткой переключить канал на SMS."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config as cfg_mod  # noqa: E402
from telethon import TelegramClient, functions  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402


async def main() -> int:
    conf = cfg_mod.load()
    pending = json.loads((BASE / "data" / "login_pending.json").read_text(encoding="utf-8"))

    client = TelegramClient(StringSession(), conf.api_id, conf.api_hash)
    await client.connect()
    try:
        try:
            sent = await client(functions.auth.ResendCodeRequest(
                phone_number=pending["phone"],
                phone_code_hash=pending["phone_code_hash"],
            ))
            print(f"Канал после resend: {type(sent.type).__name__} -> {sent.type}")
        except Exception as exc:  # noqa: BLE001
            print(f"[!] resend не сработал: {exc}")
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
