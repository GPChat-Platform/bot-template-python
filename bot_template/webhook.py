"""Mode webhook : GPChat appelle votre serveur HTTPS (derrière un reverse proxy) à chaque événement.

- signature vérifiée sur le corps BRUT (X-GPChat-Signature), sinon 401 ;
- réponse 200 immédiate, traitement ensuite dans un fil (GPChat attend au plus quelques secondes) ;
- un même événement peut être relivré : dédoublonnage par identifiant.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .gpchat import verify_webhook_signature
from .ops import Logger

MAX_BODY = 1024 * 1024


class Dedupe:
    """Mémoire bornée des identifiants déjà traités (les plus anciens sont oubliés)."""

    def __init__(self, maximum: int = 5000):
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.maximum = maximum
        self.lock = threading.Lock()

    def first_time(self, event_id: str) -> bool:
        with self.lock:
            if event_id in self.seen:
                return False
            self.seen[event_id] = None
            if len(self.seen) > self.maximum:
                self.seen.popitem(last=False)
            return True


def start_webhook_server(port: int, secrets: list[str], on_event: Callable[[dict], None], log: Logger, workers: int = 16) -> ThreadingHTTPServer:
    dedupe = Dedupe()
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="webhook")

    def process(event: dict) -> None:
        try:
            on_event(event)
        except Exception as e:  # noqa: BLE001 — déjà journalisé par instrument()
            log.error("webhook : échec de traitement", error=str(e))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            return

        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._reply(413, {"error": "too large"})
            raw = self.rfile.read(length)
            if not verify_webhook_signature(raw, self.headers.get("X-GPChat-Signature"), secrets):
                log.warn("signature de webhook invalide")
                return self._reply(401, {"error": "invalid signature"})
            try:
                event = json.loads(raw)
            except ValueError:
                return self._reply(400, {"error": "invalid json"})
            self._reply(200, {"ok": True})
            if event.get("id") and not dedupe.first_time(event["id"]):
                return
            pool.submit(process, event)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="webhook", daemon=True).start()
    log.info("webhook en écoute", port=port)
    return server
