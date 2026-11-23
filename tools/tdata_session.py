#!/usr/bin/env python3
"""
Извлечь сессию из already-залогиненного Telegram Desktop (tdata) → StringSession.

Запуск на машине, где стоит Telegram Desktop:
    python3 tools/tdata_session.py [путь к tdata] [--string]

По умолчанию путь: ~/.local/share/TelegramDesktop/tdata
Печатает SESSION_STRING (или сохраняет в файл).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from opentele.td import TDesktop
from opentele.api import API, UseCurrentSession


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tdata", nargs="?", default=str(Path.home() / ".local/share/TelegramDesktop/tdata"))
    ap.add_argument("--password", default=None, help="локальный пароль Telegram Desktop, если задан")
    ap.add_argument("--out", default=None, help="куда сохранить session string")
    args = ap.parse_args()

    base = Path(args.tdata)
    if not base.exists():
        print(f"[!] Не найдено: {base}")
        return 2

    print(f"[*] Читаю tdata: {base}")
    tdesk = TDesktop(str(base), passcode=args.password)
    if not tdesk.isLoaded():
        print("[!] tdata не загрузилась (возможно, нужен локальный пароль: --password)")
        return 3

    print(f"[*] Аккаунтов в tdata: {tdesk.accountsCount}")
    for i, acc in enumerate(tdesk.accounts):
        print(f"    #{i}: id={getattr(acc, 'UserId', '?')}")

    client = await tdesk.ToTelethon(session="string", flag=UseCurrentSession)
    await client.connect()
    if not await client.is_user_authorized():
        print("[!] Сессия в tdata неавторизована")
        return 4

    me = await client.get_me()
    print(f"[+] Аккаунт: {me.first_name or ''} @{me.username or '—'} (id={me.id}, phone={me.phone})")

    session_string = client.session.save()
    await client.disconnect()

    if args.out:
        out = Path(args.out)
        out.write_text(session_string, encoding="utf-8")
        out.chmod(0o600)
        print(f"[+] Сохранено в {out}")
    else:
        print("\n=== SESSION_STRING ===")
        print(session_string)
        print("======================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
