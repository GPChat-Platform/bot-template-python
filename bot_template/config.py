"""Configuration lue depuis l'environnement, validée au démarrage (toutes les erreurs d'un coup).

    GPCHAT_API_KEY         (obligatoire) clé API du bot — console développeur → Identifiants
    GPCHAT_MODE            polling (défaut) | webhook
    GPCHAT_WEBHOOK_SECRET  (webhook) secret(s) de signature, séparés par des virgules pendant une rotation
    PORT                   port du webhook (8080)
    CONCURRENCY            conversations traitées en parallèle en polling (16)
    DATA_DIR               dossier des préférences (./data) ; vide = mémoire seulement
    ADMIN_IDS              userId des administrateurs, séparés par des virgules
    DEFAULT_LANG           fr (défaut) | en
    LOG_LEVEL              debug | info (défaut) | warn | error
    OPS_PORT / OPS_HOST    serveur d'exploitation /healthz /readyz /metrics (9100 / 127.0.0.1)
    GPCHAT_BASE_URL        autre environnement (rare)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional


class ConfigError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("Configuration invalide :\n  - " + "\n  - ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Config:
    api_key: str
    mode: str = "polling"
    webhook_secrets: list[str] = field(default_factory=list)
    port: int = 8080
    concurrency: int = 16
    data_dir: str = "./data"
    admin_ids: list[str] = field(default_factory=list)
    default_lang: str = "fr"
    log_level: str = "info"
    ops_port: int = 9100
    ops_host: str = "127.0.0.1"
    base_url: Optional[str] = None


def _list(v: Optional[str]) -> list[str]:
    return [s.strip() for s in (v or "").split(",") if s.strip()]


def _int(name: str, raw: Optional[str], default: int, lo: int, hi: int, errors: list[str]) -> int:
    if raw is None or raw == "":
        return default
    try:
        n = int(raw)
    except ValueError:
        n = lo - 1
    if not lo <= n <= hi:
        errors.append(f"{name} doit être un entier entre {lo} et {hi} (reçu : « {raw} »)")
    return n


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    errors: list[str] = []
    mode = (env.get("GPCHAT_MODE") or "polling").lower()
    if mode not in ("polling", "webhook"):
        errors.append(f"GPCHAT_MODE doit valoir polling ou webhook (reçu : « {env.get('GPCHAT_MODE')} »)")
    if not env.get("GPCHAT_API_KEY"):
        errors.append("GPCHAT_API_KEY est obligatoire (console développeur → Identifiants)")
    secrets = _list(env.get("GPCHAT_WEBHOOK_SECRET"))
    if mode == "webhook" and not secrets:
        errors.append("GPCHAT_WEBHOOK_SECRET est obligatoire en mode webhook")
    lang = (env.get("DEFAULT_LANG") or "fr").lower()
    if lang not in ("fr", "en"):
        errors.append("DEFAULT_LANG doit valoir fr ou en")
    level = (env.get("LOG_LEVEL") or "info").lower()
    if level not in ("debug", "info", "warn", "error"):
        errors.append("LOG_LEVEL doit valoir debug, info, warn ou error")
    cfg = Config(
        api_key=env.get("GPCHAT_API_KEY", ""),
        mode=mode,
        webhook_secrets=secrets,
        port=_int("PORT", env.get("PORT"), 8080, 1, 65535, errors),
        concurrency=_int("CONCURRENCY", env.get("CONCURRENCY"), 16, 1, 256, errors),
        data_dir=env["DATA_DIR"] if "DATA_DIR" in env else "./data",
        admin_ids=_list(env.get("ADMIN_IDS")),
        default_lang=lang,
        log_level=level,
        ops_port=_int("OPS_PORT", env.get("OPS_PORT"), 9100, 1, 65535, errors),
        ops_host=env.get("OPS_HOST") or "127.0.0.1",
        base_url=env.get("GPCHAT_BASE_URL") or None,
    )
    if errors:
        raise ConfigError(errors)
    return cfg
