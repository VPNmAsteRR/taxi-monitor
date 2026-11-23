"""
Определение «заказ такси» в тексте сообщения.

Логика: набор сильных триггеров (сам факт заказа) + структурные признаки
(адрес, время, телефон, цена, маршрут). Скор = 2*сильные + 1*структурные.
Порог задаётся в .env (MIN_SCORE).

Дополнительно есть жёсткие «стоп-слова»: реклама, работа, аренда авто и т.п.
Если сработало стоп-слово, сообщение отбрасывается даже при высоком скоре.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# ── Сильные триггеры: прямой заказ / поиск машины ────────────────────────────
STRONG = [
    r"\bзаказ\b",
    r"\bзаказик\b",
    r"\bзаявка\b",
    r"\bнужн[аоы]?\s+(?:машина|такси|авто|водител)",
    r"\bнужен\s+(?:водител|экипаж)",
    r"\bкто\s+(?:свободен|на\s+линии|может\s+подать|подаст|забер[её]т|возьм[её]т)",
    r"\bесть\s+(?:заказ|заявка|работа)\b",
    r"\bприму\s+заказ\b",
    r"\bвозьму\s+заказ\b",
    r"\bотдам\s+заказ\b",
    r"\bпередам\s+заказ\b",
    r"\bсвободн\w*\s+(?:экипаж|машина|водител)",
    r"\bподач[аи]\s+(?:к|на)\b",
    r"\bклиент\s+жд[её]т\b",
    r"\bпассажир\s+жд[её]т\b",
    r"\bвстреч[аи]\s+(?:у|на)\b.*\b(?:аэропорт|вокзал)",
    r"\bтрансфер\b",
    r"\bмежгород\b",
    r"\bпо\s+городу\b",
    r"\bсрочно\s+(?:такси|машина|подача)",
]

# ── Структурные признаки ────────────────────────────────────────────────────
STRUCT = [
    # телефон
    r"(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}",
    # адрес
    r"\b(?:ул\.?|улица|пр-?т\.?|проспект|пер\.?|переулок|бульвар|шоссе|мкр\.?|микрорайон|д\.\s?\d|дом\s?\d|кв\.?\s?\d|подъезд)\b",
    # время
    r"\b(?:через\s+\d+\s*(?:мин|минут|ч|час)|сейчас|прямо\s+сейчас|как\s+можно\s+быстрее|к\s+\d{1,2}[:.]\d{2})\b",
    r"\b[01]?\d|2[0-3][:.][0-5]\d\b",
    # цена/оплата
    r"\b\d+\s*(?:₽|р\.?|руб\.?|рублей)\b",
    r"\b(?:наличн\w*|безнал\w*|перевод\w*|на\s+карту|оплата\s+по\s+счётчику|фикс)\b",
    # маршрут
    r"(?:->|→|=>|—\s*>|\bот\b.{3,40}\bдо\b)",
    # количество пассажиров / детали
    r"\b\d+\s*(?:чел|человек|пассажир|детей|мест)\b",
    r"\b(?:детск\w*\s+кресл|багаж|животн|курить\s+нельзя)\b",
]

# ── Стоп-слова: это не заказ ────────────────────────────────────────────────
NEGATIVE = [
    r"\bищу\s+работу\b",
    r"\bтребуются\s+водител",
    r"\bваканси",
    r"\bсдам\s+(?:авто|машину|такси)",
    r"\bаренда\s+(?:авто|машины|такси)",
    r"\bпрода(?:м|ю|жа)\b",
    r"\bкуплю\b",
    r"\bзапчаст",
    r"\bремонт\s+(?:авто|машин)",
    r"\bшиномонтаж",
    r"\bреклам\w*\s+(?:услуг|канал|групп)",
    r"\bподпис\w+\s+на\s+канал",
    r"\bобучени[ея]\b.*\bводител",
    r"\bштраф",
    r"\bдтп\b",
    r"\bрозыск",
]

_RE_STRONG = [re.compile(p, re.IGNORECASE) for p in STRONG]
_RE_STRUCT = [re.compile(p, re.IGNORECASE) for p in STRUCT]
_RE_NEG = [re.compile(p, re.IGNORECASE) for p in NEGATIVE]


@dataclass
class Verdict:
    is_order: bool
    score: int
    strong: List[str] = field(default_factory=list)
    struct: List[str] = field(default_factory=list)
    negative: List[str] = field(default_factory=list)
    reason: str = ""

    def explain(self) -> str:
        parts = [f"score={self.score}"]
        if self.strong:
            parts.append("сильные: " + ", ".join(self.strong))
        if self.struct:
            parts.append("структура: " + ", ".join(self.struct))
        if self.negative:
            parts.append("стоп: " + ", ".join(self.negative))
        if self.reason:
            parts.append(self.reason)
        return "; ".join(parts)


def classify(text: str, min_score: int = 2, min_length: int = 15) -> Verdict:
    """Оценить текст и решить, заказ это или нет."""
    text = (text or "").strip()

    if len(text) < min_length:
        return Verdict(False, 0, reason=f"короче {min_length} символов")

    # Реклама/работа: режем сразу
    neg = _uniq(m.group(0) for r in _RE_NEG if (m := r.search(text)))
    if neg:
        return Verdict(False, 0, negative=neg, reason="стоп-слово")

    strong = _uniq(m.group(0) for r in _RE_STRONG if (m := r.search(text)))
    struct = _uniq(m.group(0) for r in _RE_STRUCT if (m := r.search(text)))

    score = len(strong) * 2 + len(struct)

    # Заказ без явного «заказ/нужна машина», но с полным набором структуры
    # (адрес + время/телефон + цена) — тоже считаем заказом.
    has_contact = any("+" in s or "8" == s.strip()[:1] for s in struct)
    if not strong and score < 3:
        return Verdict(False, score, strong=strong, struct=struct, reason="мало признаков")

    return Verdict(score >= min_score, score, strong=strong, struct=struct)


def _uniq(items) -> List[str]:
    out: List[str] = []
    for i in items:
        i = " ".join(i.split())
        if i and i not in out:
            out.append(i)
    return out


# Нормализация для поиска дублей: разные водители шлют один и тот же заказ.
_DUP_NOISE = re.compile(r"[\W_]+", re.UNICODE)
_DUP_NUM = re.compile(r"\d+")


def dedupe_key(text: str) -> str:
    """Ключ похожести: текст без пунктуации, цифр и регистра.

    Цифры убираем специально: «заказ 15» и «заказ 16» — разные, но
    «Подача к 14:30» и «Подача к 15:30» часто дубли одного заказа.
    """
    t = (text or "").lower()
    t = _DUP_NUM.sub(" ", t)
    t = _DUP_NOISE.sub(" ", t)
    return " ".join(t.split())
