"""Состояние userbot'а: список чатов и кэш дублей. Всё в JSON — переживает рестарт."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.chats: List[str] = []
        self.seen: Dict[str, float] = {}
        self.pending: List[str] = []  # чаты, которые не удалось разрезолвить
        self.notify_channel_id: Optional[int] = None
        self.stats: Dict[str, int] = {"messages": 0, "orders": 0, "sent": 0, "errors": 0}
        self._load()

    # ── файл ────────────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Не смог прочитать %s: %s — начинаю с пустого состояния", self.path, exc)
            return
        self.chats = list(data.get("chats") or [])
        self.seen = {str(k): float(v) for k, v in (data.get("seen") or {}).items()}
        self.pending = list(data.get("pending") or [])
        if data.get("notify_channel_id"):
            self.notify_channel_id = int(data["notify_channel_id"])
        self.stats.update({k: int(v) for k, v in (data.get("stats") or {}).items() if k in self.stats})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        payload: Dict[str, Any] = {
            "chats": self.chats,
            "seen": self.seen,
            "pending": self.pending,
            "notify_channel_id": self.notify_channel_id,
            "stats": self.stats,
            "saved_at": int(time.time()),
        }
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.error("Не смог сохранить состояние: %s", exc)

    # ── чаты ────────────────────────────────────────────────────────────────
    def add_chat(self, ref: str) -> bool:
        ref = ref.strip()
        if not ref or ref in self.chats:
            return False
        self.chats.append(ref)
        self.save()
        return True

    def remove_chat(self, ref: str) -> bool:
        ref = ref.strip()
        if ref in self.chats:
            self.chats.remove(ref)
            self.save()
            return True
        return False

    # ── дубли ───────────────────────────────────────────────────────────────
    def is_duplicate(self, key: str, ttl: int) -> bool:
        now = time.time()
        self._gc(now, ttl)
        ts = self.seen.get(key)
        return bool(ts and now - ts < ttl)

    def mark_seen(self, key: str) -> None:
        self.seen[key] = time.time()

    def _gc(self, now: float, ttl: int) -> None:
        expired = [k for k, ts in self.seen.items() if now - ts > max(ttl, 60) * 2]
        for k in expired:
            self.seen.pop(k, None)

    # ── прочее ──────────────────────────────────────────────────────────────
    def bump(self, name: str, by: int = 1) -> None:
        if name in self.stats:
            self.stats[name] += by

    def summary(self) -> str:
        s = self.stats
        return (
            f"чатов: {len(self.chats)} | сообщений: {s['messages']} | "
            f"заказов: {s['orders']} | отправлено: {s['sent']} | ошибок: {s['errors']}"
        )


def resolve_state_path(session_name: str) -> Path:
    """state.json кладём рядом с файлом сессии."""
    p = Path(session_name)
    if p.parent == Path("."):
        return Path("data") / "state.json"
    return p.parent / "state.json"
