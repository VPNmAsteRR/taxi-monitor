#!/usr/bin/env python3
"""Проверка триггеров без Telegram: python tools/test_triggers.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import triggers  # noqa: E402

CASES = [
    # (текст, ожидание: True = заказ)
    ("Заказ! Ул. Ленина 15 → ТЦ Галерея, через 10 минут, 350₽, 2 чел.", True),
    ("Нужна машина срочно, подача к 14:30, ул. Мира 3. Тел 89991234567", True),
    ("Кто свободен на 15:00? Заказ с аэропорта, фикс 800р", True),
    ("Есть заказ: пр-т Победы 22, подъезд 3, ждёт клиент", True),
    ("Передам заказ, 8-999-123-45-67, детское кресло нужно", True),
    ("Подача к 18:00, ул. Садовая 4 → вокзал, 2 пассажира, безнал", True),
    # не заказы
    ("Ищу работу водителем, есть опыт 5 лет, категория B", False),
    ("Сдам авто в аренду, тариф 2000 в сутки", False),
    ("Привет всем! Как дела?", False),
    ("Продам запчасти на Солярис, недорого", False),
    ("Требуются водители на постоянную работу, з/п 60к", False),
    ("Реклама услуг шиномонтажа, скидка 20%", False),
    ("Купил новые тапки, огонь 🔥", False),
]

def main() -> int:
    failed = 0
    for text, expected in CASES:
        v = triggers.classify(text)
        ok = v.is_order == expected
        failed += 0 if ok else 1
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] expected={expected!s:<5} got={v.is_order!s:<5} | {text[:60]}")
        if not ok:
            print(f"       {v.explain()}")
    print(f"\nИтого: {len(CASES) - failed}/{len(CASES)} ок")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
