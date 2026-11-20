"""Démarrage : python -m bot_template   (ou : python -m bot_template commands)

configuration → client → routeur → polling OU webhook → serveur d'exploitation ; arrêt propre sur SIGINT/SIGTERM.
"""
from __future__ import annotations

import json
import signal
import sys
import threading
import time

from . import __version__
from .bot import Bot, instrument
from .commands import COMMANDS
from .config import ConfigError, load_config
from .gpchat import GPChatClient, poll
from .ops import Logger, Metrics, start_ops_server
from .store import Store
from .webhook import start_webhook_server


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "commands":
        print(json.dumps([{"command": c.name, "description": c.fr} for c in COMMANDS.values() if not c.admin_only], ensure_ascii=False, indent=2))
        return 0
    try:
        config = load_config()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 1

    log = Logger("bot", config.log_level)
    metrics = Metrics()
    metrics.set("info", 1, {"version": __version__, "python": sys.version.split()[0]}, "Version du bot")
    client = GPChatClient(config.api_key, base_url=config.base_url)

    def on_request(route: str, status: str, seconds: float) -> None:
        metrics.inc("api_requests_total", {"route": route, "status": status}, "Appels à l’API GPChat")
        metrics.observe("api_request_duration_seconds", seconds, {"route": route}, "Durée des appels à l’API GPChat")

    client.on_request = on_request
    store = Store(config.data_dir)
    bot = Bot(client, store, config.admin_ids, config.default_lang, log, bot_username=config.bot_username)
    handle = instrument(bot.handle, metrics, log)

    last_poll = {"at": time.time()}
    checks = {}
    if config.mode == "polling":
        stop = poll(client, handle, concurrency=config.concurrency,
                    on_poll=lambda: last_poll.__setitem__("at", time.time()),
                    on_error=lambda e: log.warn("polling en erreur", error=str(e)))
        checks["polling"] = lambda: (time.time() - last_poll["at"] < 90, "aucun polling réussi depuis 90 s")
    else:
        server = start_webhook_server(config.port, config.webhook_secrets, handle, log, workers=config.concurrency)
        stop = server.shutdown

    start_ops_server(config.ops_host, config.ops_port, metrics, checks, log)
    log.info("bot démarré", version=__version__, mode=config.mode, concurrency=config.concurrency)

    done = threading.Event()

    def shutdown(signum, _frame) -> None:
        log.info("arrêt", signal=signal.Signals(signum).name)
        stop()
        store.flush()
        done.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    done.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
