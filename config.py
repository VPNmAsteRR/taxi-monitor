from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    """Минимальный парсер .env (без внешних зависимостей)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str) -> List[str]:
    raw = os.getenv(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class Config:
    api_id: int
    api_hash: str
    session_string: str
    session_name: str
    notify_to: str
    notify_header: str = "🚕 Новый заказ"
    include_source: bool = True
    monitor_chats: List[str] = field(default_factory=list)
    min_score: int = 2
    allow_bots: bool = False
    min_length: int = 15
    dedupe_ttl: int = 900
    send_delay: float = 1.5
    dry_run: bool = False
    log_level: str = "INFO"

    @property
    def notify_target(self):
        """'auto' | 'me' | @username | числовой ID."""
        v = (self.notify_to or "auto").strip()
        if v.lower() in {"me", "self", "saved", "избранное"}:
            return "me"
        if v.lstrip("-").isdigit():
            return int(v)
        return v

    def validate(self) -> Optional[str]:
        if not self.api_id or self.api_id == 0:
            return "API_ID не задан (см. .env.example)"
        if not self.api_hash or len(self.api_hash) < 10:
            return "API_HASH не задан (см. .env.example)"
        return None


def load() -> Config:
    _load_dotenv()
    return Config(
        api_id=_int("API_ID", 0),
        api_hash=os.getenv("API_HASH", "").strip(),
        session_string=os.getenv("SESSION_STRING", "").strip(),
        session_name=os.getenv("SESSION_NAME", str(BASE_DIR / "data" / "taxi_monitor")),
        notify_to=os.getenv("NOTIFY_TO", "auto").strip(),
        notify_header=os.getenv("NOTIFY_HEADER", "🚕 Новый заказ").strip(),
        include_source=_bool("INCLUDE_SOURCE", True),
        monitor_chats=_list("MONITOR_CHATS"),
        min_score=_int("MIN_SCORE", 2),
        allow_bots=_bool("ALLOW_BOTS", False),
        min_length=_int("MIN_LENGTH", 15),
        dedupe_ttl=_int("DEDUPE_TTL", 900),
        send_delay=_float("SEND_DELAY", 1.5),
        dry_run=_bool("DRY_RUN", False),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
