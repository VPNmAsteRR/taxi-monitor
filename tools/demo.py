#!/usr/bin/env python3
"""
Демо без Telegram: прогоняет примеры сообщений из чатов такси и показывает,
что именно бот положил бы в канал «🚕 Заказы такси».
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg_mod  # noqa: E402
import triggers  # noqa: E402

CHAT = "Такси Город | Заказы"

MESSAGES = [
    ("Заказ! Ул. Ленина 15 → ТЦ Галерея, через 10 минут, 350₽, 2 чел. Тел 89991234567", "Такси Город | Заказы"),
    ("Нужна машина срочно, подача к 14:30, ул. Мира 3, подъезд 2", "Аэропорт | Водители"),
    ("Кто свободен на 15:00? Заказ с аэропорта, фикс 800р, багаж", "Такси Город | Заказы"),
    ("Есть заказ: пр-т Победы 22, ждёт клиент, детское кресло", "Межгород такси"),
    ("Ищу работу водителем, стаж 5 лет, категория B", "Такси Город | Заказы"),
    ("Сдам авто в аренду, 2000 в сутки, без залога", "Такси Город | Заказы"),
    ("Всем привет! Погода сегодня огонь", "Такси Город | Заказы"),
    ("Продам запчасти на Солярис, недорого", "Такси Город | Заказы"),
]


def main() -> int:
    conf = cfg_mod.load()
    print(f"Триггеры: порог MIN_SCORE={conf.min_score}, мин. длина {conf.min_length}")
    print(f"Заголовок: {conf.notify_header!r}, источник: {conf.include_source}")
    print("=" * 70)

    caught = 0
    for text, chat in MESSAGES:
        v = triggers.classify(text, conf.min_score, conf.min_length)
        if not v.is_order:
            print(f"\n[пропуск] {text}")
            print(f"          причина: {v.explain()}")
            continue

        caught += 1
        parts = []
        if conf.notify_header:
            parts.append(conf.notify_header)
        if conf.include_source:
            parts.append(f"Источник: {chat}")
        parts.append(text)
        print("\n" + "─" * 70)
        print("\n".join(parts))
        print("─" * 70)
        print(f"[скор {v.score}] {v.explain()}")
        print(f"[ссылка на источник] скрыта от глаз — текст заказа ровно как в чате")

    print(f"\nИтого: {caught} из {len(MESSAGES)} сообщений ушли бы в канал.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
