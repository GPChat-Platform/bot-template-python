"""Exploitation : journaux JSON, métriques Prometheus, serveur /healthz · /readyz · /metrics."""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Union

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}


class Logger:
    def __init__(self, service: str, level: str = "info", out=None):
        self.service = service
        self.min = _LEVELS.get(level, 20)
        self.out = out or (lambda line: print(line, file=sys.stdout, flush=True))

    def _log(self, level: str, msg: str, **fields) -> None:
        if _LEVELS[level] < self.min:
            return
        record = {"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": level, "service": self.service, "msg": msg, **fields}
        self.out(json.dumps(record, ensure_ascii=False, default=str))

    def debug(self, msg: str, **f) -> None: self._log("debug", msg, **f)
    def info(self, msg: str, **f) -> None: self._log("info", msg, **f)
    def warn(self, msg: str, **f) -> None: self._log("warn", msg, **f)
    def error(self, msg: str, **f) -> None: self._log("error", msg, **f)


class Metrics:
    def __init__(self, prefix: str = "gpchat_bot"):
        self.prefix = prefix
        self.series: dict[str, dict] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _key(labels: dict | None) -> str:
        return ",".join(f'{k}="{str(v).replace(chr(34), "_")}"' for k, v in sorted((labels or {}).items()))

    def _get(self, name: str, kind: str, help_: str) -> dict:
        return self.series.setdefault(name, {"type": kind, "help": help_, "values": {}})

    def inc(self, name: str, labels: dict | None = None, help_: str = "") -> None:
        with self.lock:
            v = self._get(name, "counter", help_)["values"]
            k = self._key(labels)
            v[k] = v.get(k, 0) + 1

    def set(self, name: str, value: float, labels: dict | None = None, help_: str = "") -> None:
        with self.lock:
            self._get(name, "gauge", help_)["values"][self._key(labels)] = value

    def observe(self, name: str, seconds: float, labels: dict | None = None, help_: str = "") -> None:
        with self.lock:
            v = self._get(name, "summary", help_)["values"]
            k = self._key(labels)
            s, c = v.get(k, (0.0, 0))
            v[k] = (s + seconds, c + 1)

    def render(self) -> str:
        lines = []
        with self.lock:
            for name, s in self.series.items():
                full = f"{self.prefix}_{name}"
                if s["help"]:
                    lines.append(f"# HELP {full} {s['help']}")
                lines.append(f"# TYPE {full} {s['type']}")
                for k, v in s["values"].items():
                    sel = f"{{{k}}}" if k else ""
                    if s["type"] == "summary":
                        lines += [f"{full}_sum{sel} {v[0]}", f"{full}_count{sel} {v[1]}"]
                    else:
                        lines.append(f"{full}{sel} {v}")
        return "\n".join(lines) + "\n"


Check = Callable[[], Union[bool, tuple[bool, str]]]


def start_ops_server(host: str, port: int, metrics: Metrics, checks: dict[str, Check], log: Logger) -> ThreadingHTTPServer:
    started = time.time()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence : nos journaux sont en JSON
            return

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/healthz":
                return self._json(200, {"ok": True})
            if path == "/metrics":
                data = metrics.render().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/readyz":
                problems = []
                for name, check in checks.items():
                    try:
                        r = check()
                        ok, detail = (r, "") if isinstance(r, bool) else r
                        if not ok:
                            problems.append(f"{name} : {detail}" if detail else name)
                    except Exception as e:  # noqa: BLE001
                        problems.append(f"{name} : {e}")
                return self._json(503 if problems else 200, {"ok": not problems, "problems": problems, "uptimeSeconds": round(time.time() - started)})
            return self._json(404, {"error": "not found"})

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, name="ops", daemon=True).start()
    log.info("serveur d'exploitation en écoute", host=host, port=port, routes=["/healthz", "/readyz", "/metrics"])
    return server
