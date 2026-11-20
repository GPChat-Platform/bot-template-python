"""Préférences des utilisateurs. Fichier JSON écrit de façon atomique (fichier temporaire puis renommage),
différé de 300 ms pour regrouper les écritures. Sans dossier : mémoire seulement.
Pour beaucoup d'utilisateurs, remplacez par SQLite/Postgres en gardant la même interface."""
from __future__ import annotations

import json
import os
import threading


class Store:
    def __init__(self, data_dir: str):
        self.file = os.path.join(data_dir, "bot.json") if data_dir else None
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self.data: dict = {"users": {}}
        if self.file and os.path.exists(self.file):
            try:
                with open(self.file, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                pass  # fichier illisible : état vide
        self.data.setdefault("users", {})

    def get(self, user_id: str) -> dict:
        with self.lock:
            return dict(self.data["users"].get(user_id, {}))

    def set(self, user_id: str, **patch) -> dict:
        with self.lock:
            prefs = {**self.data["users"].get(user_id, {}), **patch}
            self.data["users"][user_id] = prefs
        self._save()
        return prefs

    def count(self) -> int:
        with self.lock:
            return len(self.data["users"])

    def _save(self) -> None:
        if not self.file:
            return
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(0.3, self.flush)
        self.timer.daemon = True
        self.timer.start()

    def flush(self) -> None:
        if not self.file:
            return
        with self.lock:
            os.makedirs(os.path.dirname(self.file) or ".", exist_ok=True)
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.file)
