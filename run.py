#!/usr/bin/env python3
"""
taxi-monitor — userbot на аккаунте Telegram.

Читает сообщения в чатах, куда добавлен аккаунт. Если сообщение похоже на
заказ такси — отправляет ТОЧНО этот текст в «Избранное» (или указанный чат).

Аккаунт должен быть участником чатов: у userbot нет «доступа к чатам» через
бота-админа, он видит только то, что видит сам аккаунт.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

import config as cfg_mod
import store
import triggers

log = logging.getLogger("taxi-monitor")

_HELP = """
Команды (пишите в «Избранное» самому себе):
  /status         — состояние и статистика
  /chats          — список отслеживаемых чатов
  /add <ссылка>   — добавить чат (@name, t.me/..., ID)
  /del <ссылка>   — убрать чат
  /test <текст>   — проверить, сработают ли триггеры
  /id             — показать ID текущего чата
  /help           — эта справка
"""


class Monitor:
    def __init__(self, conf: cfg_mod.Config) -> None:
        self.cfg = conf
        self.state = store.State(store.resolve_state_path(conf.session_name))
        self.client = self._build_client()
        self.entities: Dict[int, object] = {}
        self.chat_titles: Dict[int, str] = {}
        self.notify_entity = None
        self.notify_entity_id = None
        self._last_send = 0.0
        self._stop = asyncio.Event()
        self._current_chat_id = 0

    # ── клиент ──────────────────────────────────────────────────────────────
    def _build_client(self) -> TelegramClient:
        if self.cfg.session_string:
            session = StringSession(self.cfg.session_string)
            log.info("Сессия: StringSession из .env")
        else:
            session = self.cfg.session_name
            log.info("Сессия: файл %s.session", self.cfg.session_name)
        return TelegramClient(
            session,
            self.cfg.api_id,
            self.cfg.api_hash,
            device_model="taxi-monitor",
            system_version="Linux",
            app_version="1.0",
            flood_sleep_threshold=60,
        )

    # ── старт ───────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await self.client.start()
        me = await self.client.get_me()
        log.info("Вошёл как %s (id=%s)", _name(me), me.id)

        # когда сессия жила в файле — сохраняем строку для деплоя без файла
        try:
            if not self.cfg.session_string and isinstance(self.client.session, StringSession):
                pass
        except Exception:  # noqa: BLE001 — не критично
            pass

        self.notify_entity = await self._resolve_notify()
        if self.notify_entity_id is None:
            self.notify_entity_id = _entity_id(self.notify_entity)

        await self._resolve_chats()
        self._register_handlers()

        log.info("Мониторинг запущен. %s", self.state.summary())
        if not self.state.chats:
            log.warning(
                "Список чатов пуст — слушаю ВСЕ входящие сообщения. "
                "Добавьте чаты: /add @chat в «Избранном» или MONITOR_CHATS в .env"
            )

    async def _resolve_notify(self):
        target = self.cfg.notify_target

        if target == "auto":
            return await self._ensure_notify_channel()

        try:
            if target == "me":
                return await self.client.get_input_entity("me")
            ent = await self.client.get_input_entity(target)
            log.info("Уведомления → %s (id=%s)", _name(ent), _entity_id(ent))
            return ent
        except Exception as exc:  # noqa: BLE001
            log.error("Не смог найти получателя %s: %s — создаю свой канал", target, exc)
            return await self._ensure_notify_channel()

    async def _ensure_notify_channel(self):
        """Канал для заказов: берём сохранённый, иначе создаём приватный."""
        saved = self.state.notify_channel_id
        if saved:
            try:
                ent = await self.client.get_entity(saved)
                log.info("Уведомления → канал «%s» (id=%s)", _name(ent), saved)
                self._publish_notify_entity(ent, saved)
                return ent
            except Exception as exc:  # noqa: BLE001
                log.warning("Сохранённый канал %s недоступен: %s", saved, exc)

        from telethon.tl.functions.channels import CreateChannelRequest

        title = "🚕 Заказы такси"
        result = await self.client(CreateChannelRequest(
            title=title, about="Заказы такси, найденные taxi-monitor", megagroup=False
        ))
        channel = result.chats[0]
        # закрепляем в списке диалогов, чтобы было под рукой
        try:
            from telethon.tl.functions.folders import EditPeerFoldersRequest
            from telethon.tl.types import InputFolderPeer
            await self.client(EditPeerFoldersRequest(
                folder_peers=[InputFolderPeer(peer=channel, folder_id=1)]
            ))
        except Exception:  # noqa: BLE001 — папки не критичны
            pass

        self.state.notify_channel_id = channel.id
        self.state.save()
        log.info("Создан канал «%s» (id=%s)", title, channel.id)
        self._publish_notify_entity(channel, channel.id)
        return channel

    def _publish_notify_entity(self, ent, ent_id: int) -> None:
        self.notify_entity_id = ent_id
        try:
            username = getattr(ent, "username", None)
            log.info(
                "Заказы будут приходить в канал «%s»%s",
                _name(ent),
                f" — https://t.me/{username}" if username else "",
            )
        except Exception:  # noqa: BLE001
            pass

    async def _resolve_chats(self) -> None:
        refs = list(dict.fromkeys(self.cfg.monitor_chats + self.state.chats))
        if not refs:
            # режим «все чаты»: запоминаем всё, что видит аккаунт
            async for dialog in self.client.iter_dialogs(limit=None):
                ent = dialog.entity
                if isinstance(ent, (Channel, Chat)):
                    self.entities[ent.id] = ent
                    self.chat_titles[ent.id] = dialog.name
            log.info("Подписан на все чаты: %d", len(self.entities))
            return

        self.state.pending.clear()
        for ref in refs:
            try:
                ent = await self.client.get_entity(ref)
                ent_id = _entity_id(ent)
                self.entities[ent_id] = ent
                self.chat_titles[ent_id] = _name(ent)
                log.info("Чат OK: %-30s id=%s", _name(ent), ent_id)
            except Exception as exc:  # noqa: BLE001
                self.state.pending.append(ref)
                log.warning("Чат НЕ найден: %s (%s)", ref, exc)

        if self.state.pending:
            log.warning(
                "Не разрезолвлено: %s. Аккаунт должен быть в чате, а для приватных "
                "групп — сначала вступить по ссылке.",
                ", ".join(self.state.pending),
            )
        self.state.save()

    def _register_handlers(self) -> None:
        @self.client.on(events.NewMessage())
        async def on_message(event):  # type: ignore[no-untyped-def]
            try:
                await self._handle(event)
            except FloodWaitError as exc:
                log.warning("FloodWait %s сек, жду", exc.seconds)
                await asyncio.sleep(exc.seconds + 2)
            except Exception:  # noqa: BLE001
                self.state.bump("errors")
                log.exception("Ошибка обработки сообщения")

        @self.client.on(events.MessageEdited())
        async def on_edit(event):  # type: ignore[no-untyped-def]
            # водители часто правят заказ — обрабатываем как новое
            try:
                await self._handle(event)
            except Exception:  # noqa: BLE001
                log.exception("Ошибка обработки правки")

    # ── обработка ───────────────────────────────────────────────────────────
    async def _handle(self, event) -> None:
        msg = event.message
        chat_id = event.chat_id
        text = (msg.message or "").strip()
        self._current_chat_id = chat_id

        # команды в «Избранном» / у самого себя
        if event.out and await self._maybe_command(text):
            return

        if not text:
            return
        if getattr(msg, "via_bot_id", None) and not self.cfg.allow_bots:
            return
        sender = await self._sender(msg)
        if sender is not None and getattr(sender, "bot", False) and not self.cfg.allow_bots:
            return

        self.state.bump("messages")

        # не обрабатываем собственный канал уведомлений (защита от петли)
        if getattr(self, "notify_entity_id", None) and _abs_id(chat_id) in {
            _abs_id(self.notify_entity_id), int(str(_abs_id(self.notify_entity_id))[-10:])
        }:
            return

        # фильтр по чатам
        if self.entities and not _in_chats(chat_id, self.entities):
            return

        verdict = triggers.classify(text, self.cfg.min_score, self.cfg.min_length)
        if not verdict.is_order:
            log.debug("Пропуск (%s): %s", verdict.explain(), _short(text))
            return

        key = triggers.dedupe_key(text)
        if self.state.is_duplicate(key, self.cfg.dedupe_ttl):
            log.debug("Дубль (%s): %s", verdict.explain(), _short(text))
            return

        self.state.bump("orders")
        self.state.mark_seen(key)
        self.state.save()

        chat_title = self.chat_titles.get(_abs_id(chat_id), str(chat_id))
        log.info("ЗАКАЗ [%s] %s | %s", chat_title, verdict.explain(), _short(text, 160))

        await self._deliver(text, chat_title, msg)

    async def _deliver(self, text: str, chat_title: str, msg) -> None:
        parts = []
        if self.cfg.notify_header:
            parts.append(self.cfg.notify_header)
        if self.cfg.include_source and chat_title:
            parts.append(f"Источник: {chat_title}")
        parts.append(text)
        body = "\n".join(parts)

        if self.cfg.dry_run:
            log.info("DRY_RUN: %s", _short(body, 300))
            return

        # антифлуд
        wait = self.cfg.send_delay - (time.monotonic() - self._last_send)
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            await self.client.send_message(self.notify_entity, body, link_preview=False)
            self._last_send = time.monotonic()
            self.state.bump("sent")
            self.state.save()
        except FloodWaitError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.state.bump("errors")
            log.error("Не смог отправить заказ: %s", exc)

    async def _sender(self, msg):
        try:
            return await msg.get_sender()
        except Exception:  # noqa: BLE001
            return None

    # ── команды ─────────────────────────────────────────────────────────────
    async def _maybe_command(self, text: str) -> bool:
        if not text.startswith("/"):
            return False
        cmd, _, arg = text.partition(" ")
        cmd = cmd.strip().lower()
        arg = arg.strip()
        if cmd not in {"/status", "/chats", "/add", "/del", "/test", "/id", "/help", "/ping"}:
            return False

        if cmd in {"/help"}:
            reply = _HELP.strip()
        elif cmd in {"/status", "/ping"}:
            reply = (
                f"taxi-monitor жив\n"
                f"{self.state.summary()}\n"
                f"чатов в списке: {len(self.state.chats)}\n"
                f"DRY_RUN: {self.cfg.dry_run}"
            )
        elif cmd == "/chats":
            if not self.state.chats and not self.cfg.monitor_chats:
                reply = "Список пуст — слушаю все чаты аккаунта."
            else:
                lines = list(self.cfg.monitor_chats) + [
                    c for c in self.state.chats if c not in self.cfg.monitor_chats
                ]
                reply = "Чаты:\n" + "\n".join(f"• {c}" for c in lines)
        elif cmd == "/add":
            if not arg:
                reply = "Использование: /add @username | /add https://t.me/+invite"
            else:
                try:
                    ent = await self.client.get_entity(arg)
                    ent_id = _entity_id(ent)
                    self.entities[ent_id] = ent
                    self.chat_titles[ent_id] = _name(ent)
                    self.state.add_chat(arg)
                    reply = f"Добавлен: {_name(ent)} (id={ent_id})"
                except Exception as exc:  # noqa: BLE001
                    reply = f"Не смог добавить {arg}: {exc}"
        elif cmd == "/del":
            ok = self.state.remove_chat(arg)
            reply = "Удалён из списка" if ok else "Такого чата нет в списке"
        elif cmd == "/test":
            v = triggers.classify(arg or "", 0, 0)
            reply = (
                f"Заказ: {'ДА' if v.is_order else 'НЕТ'}\n{v.explain()}\n"
                f"(порог MIN_SCORE={self.cfg.min_score})"
            )
        elif cmd == "/id":
            reply = f"ID этого чата: {self._current_chat_id}"
        else:  # pragma: no cover
            reply = "?"

        await self.client.send_message(self.notify_entity, reply)
        return True

    # ── остановка ───────────────────────────────────────────────────────────
    def install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:  # pragma: no cover
                pass

    async def run_forever(self) -> None:
        await self.start()
        self.install_signal_handlers()
        stopper = asyncio.create_task(self._stop.wait())
        runner = asyncio.create_task(self.client.run_until_disconnected())
        done, pending = await asyncio.wait(
            {stopper, runner}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        log.info("Останавливаюсь. %s", self.state.summary())
        self.state.save()
        if self.client.is_connected():
            await self.client.disconnect()


# ── утилиты ─────────────────────────────────────────────────────────────────
def _name(ent) -> str:
    if isinstance(ent, User):
        return " ".join(x for x in [getattr(ent, "first_name", None), getattr(ent, "last_name", None)] if x) or (
            f"@{ent.username}" if getattr(ent, "username", None) else str(ent.id)
        )
    return getattr(ent, "title", None) or str(getattr(ent, "id", "?"))


def _entity_id(ent) -> int:
    return getattr(ent, "id", 0)


def _abs_id(chat_id: int) -> int:
    return abs(int(chat_id))


def _in_chats(chat_id: int, entities: Dict[int, object]) -> bool:
    cid = _abs_id(chat_id)
    if cid in entities:
        return True
    # супергруппы/каналы приходят как -100<id>
    bare = int(str(cid)[3:]) if str(cid).startswith("100") and len(str(cid)) > 10 else cid
    return bare in entities


def _short(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    conf = cfg_mod.load()
    logging.basicConfig(
        level=getattr(logging, conf.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    problem = conf.validate()
    if problem:
        log.error("%s", problem)
        return 2
    try:
        asyncio.run(Monitor(conf).run_forever())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
