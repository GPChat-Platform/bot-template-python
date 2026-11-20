"""Client minimal de l'API GPChat pour les bots (Python ≥ 3.10, bibliothèque standard uniquement).

    client = GPChatClient(api_key)
    client.send_message(user_id, "Bonjour **monde**", markdown=True)
    stop = poll(client, handler, concurrency=16)

Contrat de l'API : https://gpchat.app/developers/docs.html
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

DEFAULT_BASE_URL = "https://api.gpchat.app/v1"
_SIGNATURE = re.compile(r"^t=(\d+)((?:,v1=[0-9a-f]{64})+)$")


class GPChatError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.code = code


def callback_button(text: str, data: str) -> dict:
    """Bouton d'action : `data` est renvoyée au bot (événement callback.received)."""
    return {"text": text, "callbackData": data}


def link_button(text: str, url: str) -> dict:
    return {"text": text, "url": url}


class GPChatClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: float = 15.0, max_retries: int = 2):
        if not api_key:
            raise ValueError("api_key requise")
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.on_request: Optional[Callable[[str, str, float], None]] = None  # métriques

    def request(self, path: str, body: Any, timeout: Optional[float] = None, retries: Optional[int] = None) -> Any:
        """POST JSON avec nouveaux essais (429 et 5xx, en respectant Retry-After)."""
        retries = self.max_retries if retries is None else retries
        data = json.dumps(body or {}).encode("utf-8")
        attempt = 0
        while True:
            t0 = time.monotonic()
            req = urllib.request.Request(
                self.base_url + path,
                data=data,
                method="POST",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as res:
                    payload = json.loads(res.read() or b"{}")
                    self._report(path, f"{str(res.status)[0]}xx", t0)
                    return payload.get("data", payload) if isinstance(payload, dict) else payload
            except urllib.error.HTTPError as e:
                self._report(path, f"{str(e.code)[0]}xx", t0)
                try:
                    payload = json.loads(e.read() or b"{}")
                except ValueError:
                    payload = {}
                if (e.code == 429 or e.code >= 500) and attempt < retries:
                    after = e.headers.get("Retry-After") if e.headers else None
                    time.sleep(float(after) if after and after.isdigit() else 0.5 * 2**attempt)
                    attempt += 1
                    continue
                raise GPChatError(payload.get("message") or f"HTTP {e.code}", e.code, payload.get("code")) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                self._report(path, "réseau", t0)
                if attempt < retries:
                    time.sleep(0.5 * 2**attempt)
                    attempt += 1
                    continue
                raise GPChatError(str(e), code="network") from None

    def _report(self, path: str, status: str, t0: float) -> None:
        if self.on_request:
            self.on_request(path, status, time.monotonic() - t0)

    @staticmethod
    def _text(base: dict, content: str, markdown: bool, buttons: Optional[list]) -> dict:
        body = {**base, "type": "text", "content": content}
        if markdown:
            body["parseMode"] = "markdown"
        if buttons:
            body["buttons"] = buttons
        return body

    def send_message(self, to: str, content: str, markdown: bool = False, buttons: Optional[list] = None) -> Any:
        return self.request("/messages", self._text({"to": to}, content, markdown, buttons))

    def send_group_message(self, group_id: str, content: str, markdown: bool = False, buttons: Optional[list] = None) -> Any:
        return self.request("/messages/group", self._text({"groupId": group_id}, content, markdown, buttons))

    def send(self, target: dict, content: str, markdown: bool = False, buttons: Optional[list] = None) -> Any:
        """Répond dans la conversation d'origine : target = {"to": userId} ou {"groupId": …}."""
        if "groupId" in target:
            return self.send_group_message(target["groupId"], content, markdown, buttons)
        return self.send_message(target["to"], content, markdown, buttons)

    def edit_message(self, target: dict, msg_id: str, content: Optional[str] = None, buttons: Optional[list] = None) -> Any:
        body = {**target, "msgId": msg_id}
        if content is not None:
            body["content"] = content
        if buttons is not None:
            body["buttons"] = buttons
        return self.request("/messages/edit", body)

    def send_chat_action(self, to: str, action: str = "typing", seconds: int = 5) -> Any:
        """« écrit… » (cosmétique) : aucun nouvel essai, pour ne pas consommer le quota sous forte charge."""
        return self.request("/chat/action", {"to": to, "action": action, "seconds": seconds}, timeout=seconds + 30, retries=0)

    def get_updates(self, ack: Optional[list] = None, limit: int = 50, timeout: int = 0) -> dict:
        return self.request("/updates", {"ack": ack or [], "limit": limit, "timeout": timeout}, timeout=timeout + 30)


def verify_webhook_signature(raw_body: bytes, header: Optional[str], secrets: list[str], now: Optional[float] = None, tolerance: int = 300) -> bool:
    """Vérifie X-GPChat-Signature (`t=<s>,v1=<hex>[,v1=…]`) : HMAC-SHA256(secret, f"{t}.{corps}") sur le corps BRUT."""
    m = _SIGNATURE.match(header or "")
    if not m:
        return False
    ts = int(m.group(1))
    if abs(int(now if now is not None else time.time()) - ts) > tolerance:
        return False
    provided = [p[3:] for p in m.group(2).split(",") if p]
    message = f"{ts}.".encode("utf-8") + raw_body
    for secret in secrets:
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(expected, p) for p in provided):
            return True
    return False


def conversation_key(update: dict) -> str:
    """L'ordre des messages est garanti à l'intérieur d'une même conversation."""
    d = update.get("data") or {}
    if d.get("groupId"):
        return f"g:{d['groupId']}"
    if d.get("chatId"):
        return f"c:{d['chatId']}"
    if d.get("from"):
        return f"u:{d['from']}"
    return f"e:{update.get('id')}"


def poll(
    client: Any,
    handler: Callable[[dict], None],
    concurrency: int = 16,
    timeout: int = 20,
    limit: int = 50,
    busy_poll: float = 1.1,
    idle_delay: float = 1.0,
    retry_after: float = 30.0,
    on_error: Callable[[Exception], None] = lambda e: print(f"[gpchat] polling : {e}"),
    on_poll: Callable[[], None] = lambda: None,
) -> Callable[[], None]:
    """Boucle de polling dans un fil dédié. `handler` est appelé pour chaque événement, jusqu'à `concurrency`
    conversations en parallèle mais toujours dans l'ordre dans une conversation ; un événement n'est acquitté
    que si `handler` réussit (sinon relivré, au plus tôt après `retry_after` s). Retourne une fonction d'arrêt."""
    stopped = threading.Event()
    lock = threading.Lock()
    to_ack: list[str] = []
    in_flight: set[str] = set()
    done: dict[str, float] = {}
    failed: dict[str, float] = {}
    queues: dict[str, deque] = {}
    pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="gpchat")

    def drain(key: str) -> None:
        # Traite la file d'UNE conversation, un événement après l'autre.
        while True:
            with lock:
                q = queues.get(key)
                if not q:
                    queues.pop(key, None)
                    return
                update = q.popleft()
            try:
                handler(update)
                with lock:
                    to_ack.append(update["id"])
                    done[update["id"]] = time.time()
            except Exception as e:  # noqa: BLE001 — l'événement sera relivré
                with lock:
                    failed[update["id"]] = time.time()
                on_error(e)
            finally:
                with lock:
                    in_flight.discard(update["id"])

    def loop() -> None:
        while not stopped.is_set():
            try:
                with lock:
                    busy = bool(in_flight)
                    ack = to_ack[:]
                    to_ack.clear()
                res = client.get_updates(ack=ack, limit=limit, timeout=0 if busy else timeout)
                on_poll()
                updates = (res or {}).get("updates") or []
                fresh = 0
                now = time.time()
                with lock:
                    for u in updates:
                        uid = u.get("id")
                        if uid in in_flight:
                            continue
                        if uid in done:
                            to_ack.append(uid)
                            continue
                        if now - failed.get(uid, 0) < retry_after:
                            continue
                        in_flight.add(uid)
                        key = conversation_key(u)
                        start = key not in queues
                        queues.setdefault(key, deque()).append(u)
                        if start:
                            pool.submit(drain, key)
                        fresh += 1
                    cutoff = now - 300
                    for d in (done, failed):
                        for k in [k for k, at in d.items() if at < cutoff]:
                            d.pop(k, None)
                    busy = bool(in_flight)
                if fresh == 0 and (busy or updates):
                    stopped.wait(busy_poll)
                elif not updates and timeout == 0:
                    stopped.wait(idle_delay)
            except Exception as e:  # noqa: BLE001
                on_error(e)
                stopped.wait(3)

    threading.Thread(target=loop, name="gpchat-poll", daemon=True).start()

    def stop() -> None:
        stopped.set()
        pool.shutdown(wait=False, cancel_futures=False)

    return stop
