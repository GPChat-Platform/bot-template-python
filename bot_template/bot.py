"""Routeur : transforme un événement GPChat (polling ou webhook) en appel de commande ou de bouton.

- conversation privée : commandes, et texte libre → /help (à remplacer par votre logique) ;
- groupe : uniquement les commandes ou les messages qui MENTIONNENT le bot (jamais toute la conversation) ;
- bouton : `callback.received` avec la donnée du bouton (ici le compteur `counter:<n>`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .commands import COMMANDS, counter_buttons
from .i18n import t
from .ops import Logger
from .store import Store

_COMMAND = re.compile(r"^/([a-zA-Z0-9_]+)(?:@\w+)?(?:\s+([\s\S]*))?$")
_TARGET = re.compile(r"^/[a-zA-Z0-9_]+@(\w+)")
_COUNTER = re.compile(r"^counter:(-?\d+)$")


def command_target(text: Optional[str]) -> Optional[str]:
    """« /aide@mon_bot » → "mon_bot" : en groupe, une commande adressée ne concerne QUE ce bot (convention Telegram)."""
    m = _TARGET.match((text or "").strip())
    return m.group(1).lower() if m else None


def parse_command(text: Optional[str]) -> Optional[tuple[str, str]]:
    """« /echo@mon_bot bonjour » → ("echo", "bonjour") ; sinon None."""
    m = _COMMAND.match((text or "").strip())
    return (m.group(1).lower(), (m.group(2) or "").strip()) if m else None


@dataclass
class Context:
    args: str
    lang: str
    user_id: str
    is_group: bool
    is_admin: bool
    target: dict
    _bot: "Bot"

    def reply(self, text: str, markdown: bool = True, buttons: Optional[list] = None) -> Any:
        return self._bot.client.send(self.target, text, markdown=markdown, buttons=buttons)

    def typing(self) -> None:
        if "to" in self.target:
            try:
                self._bot.client.send_chat_action(self.target["to"], "typing", 3)
            except Exception:  # noqa: BLE001 — cosmétique
                pass

    def t(self, key: str, **params) -> str:
        return t(self.lang, key, **params)

    def t_in(self, lang: str, key: str, **params) -> str:
        return t(lang, key, **params)

    @property
    def prefs(self) -> dict:
        return self._bot.store.get(self.user_id)

    def set_prefs(self, **patch) -> dict:
        return self._bot.store.set(self.user_id, **patch)

    def users_count(self) -> int:
        return self._bot.store.count()


class Bot:
    def __init__(self, client: Any, store: Store, admin_ids: list[str], default_lang: str, log: Logger, bot_username: Optional[str] = None):
        self.client = client
        self.store = store
        self.admin_ids = set(admin_ids)
        self.default_lang = default_lang
        self.log = log
        self.bot_username = (bot_username or "").lstrip("@").lower() or None

    def lang_of(self, user_id: str) -> str:
        return self.store.get(user_id).get("lang") or self.default_lang

    def _context(self, target: dict, user_id: str, args: str, is_group: bool) -> Context:
        return Context(args, self.lang_of(user_id), user_id, is_group, user_id in self.admin_ids, target, self)

    def _run(self, ctx: Context, name: str) -> None:
        cmd = COMMANDS.get(name)
        if not cmd:
            ctx.reply(ctx.t("unknown"))
        elif cmd.admin_only and not ctx.is_admin:
            ctx.reply(ctx.t("admin_only"))
        else:
            cmd.run(ctx)

    def handle(self, update: dict) -> None:
        """Point d'entrée unique. Une exception = événement non acquitté (relivré plus tard)."""
        d = update.get("data") or {}
        user_id = d.get("from")
        if not user_id:
            return
        kind = update.get("type")
        if kind == "message.received":
            if d.get("type") not in (None, "text"):
                return
            cmd = parse_command(d.get("textMsg"))
            target = {"to": d.get("chatId") or user_id}
            self._run(self._context(target, user_id, cmd[1] if cmd else "", False), cmd[0] if cmd else "help")
        elif kind == "group_message.received":
            if d.get("type") not in (None, "text") or not d.get("groupId"):
                return
            cmd = parse_command(d.get("textMsg"))
            if not cmd and not d.get("isMentioned"):
                return  # le bot n'écoute pas les conversations de groupe
            target = command_target(d.get("textMsg"))
            if cmd and target and self.bot_username and target != self.bot_username:
                return  # commande adressée à un autre bot du groupe
            self._run(self._context({"groupId": d["groupId"]}, user_id, cmd[1] if cmd else "", True), cmd[0] if cmd else "help")
        elif kind == "callback.received":
            target = {"groupId": d["groupId"]} if d.get("groupId") else {"to": d.get("chatId") or user_id}
            m = _COUNTER.match(str(d.get("data") or ""))
            if not m:
                return
            n = max(-999, min(999, int(m.group(1))))
            text = t(self.lang_of(user_id), "counter", n=n)
            if d.get("msgId"):
                self.client.edit_message(target, d["msgId"], content=text, buttons=counter_buttons(n))
            else:
                self.client.send(target, text, markdown=True, buttons=counter_buttons(n))
        else:
            self.log.debug("événement ignoré", type=kind)


def instrument(handle: Callable[[dict], None], metrics, log: Logger) -> Callable[[dict], None]:
    """Compte, mesure et journalise chaque événement ; laisse remonter l'erreur (non-acquittement)."""
    import time

    def wrapped(update: dict) -> None:
        kind = update.get("type", "inconnu")
        t0 = time.monotonic()
        try:
            handle(update)
            metrics.inc("events_total", {"type": kind, "result": "ok"}, "Événements traités")
        except Exception as e:
            metrics.inc("events_total", {"type": kind, "result": "error"}, "Événements traités")
            log.error("échec de traitement", type=kind, error=str(e))
            raise
        finally:
            metrics.observe("event_duration_seconds", time.monotonic() - t0, {"type": kind}, "Durée de traitement")

    return wrapped
