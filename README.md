# Modèle de bot GPChat — Python

Point de départ **prêt pour la production** pour un bot [GPChat](https://gpchat.app) en Python (≥ 3.10, **bibliothèque standard uniquement**).
Cliquez sur **« Use this template »**, renseignez votre clé API, lancez : votre bot répond.

> Autres langages : [JavaScript](https://github.com/GPChat-Platform/bot-template) · [TypeScript](https://github.com/GPChat-Platform/bot-template-ts) · **Python** · [Go](https://github.com/GPChat-Platform/bot-template-go) · [Java (Quarkus)](https://github.com/GPChat-Platform/bot-template-quarkus) — même architecture, mêmes commandes, même comportement.

## Ce que vous obtenez
- **Polling** (aucun serveur public) ou **webhook** signé (HMAC-SHA256, rotation de secret, dédoublonnage).
- **Polling parallèle** : jusqu'à `CONCURRENCY` conversations à la fois, toujours dans l'ordre au sein d'une conversation ; un événement n'est acquitté que s'il a été traité.
- Client API avec **nouveaux essais** (429/5xx, `Retry-After`) et délais maximaux.
- Registre de **commandes** (`/start`, `/help`, `/ping`, `/echo`, `/counter` avec boutons, `/lang`, `/whoami`, `/stats` admin), **Markdown**, **boutons**, **français / anglais**, préférences persistantes.
- **Groupes** : le bot ne répond qu'aux commandes et aux mentions.
- **Exploitation** : journaux JSON, `/healthz`, `/readyz`, `/metrics` (Prometheus), version exposée.
- Configuration **validée au démarrage**, Dockerfile durci (`HEALTHCHECK`, utilisateur non root), CI GitHub Actions, tests sans réseau.

## Démarrer en 3 minutes
1. Créez le bot : console développeur (https://gpchat.app/developers/console) ou `@gpchat_forge` → `/newbot`, puis copiez la clé API.
2. Dans l'onglet *Webhooks* de la console, choisissez le mode **polling** (ou `/setmode polling` dans `@gpchat_forge`).
3. Lancez :
```bash
cp .env.example .env              # renseignez GPCHAT_API_KEY
set -a && . ./.env && set +a       # charge .env dans le shell
python -m bot_template
```
Écrivez `/start` à votre bot dans GPChat.

## Écrire votre bot
Tout se passe dans **`bot_template/commands.py`** : ajoutez une fonction décorée `@command("nom", "description fr", "description en")` qui reçoit `ctx`.
`ctx` fournit `args`, `lang`, `user_id`, `is_group`, `is_admin`, `reply(texte, markdown=…, buttons=…)`, `typing()`, `t(clé)`, `prefs` / `set_prefs()` ; boutons : `callback_button()` / `link_button()`.
Les textes sont dans `bot_template/i18n.py`. Les boutons d'action arrivent dans `bot_template/bot.py` (`callback.received`).
`python -m bot_template commands` affiche la liste des commandes à déclarer dans la console (menu `/` de l'app).

| Fichier | Rôle |
|---|---|
| `bot_template/commands.py` | **vos commandes** |
| `bot_template/bot.py` | routeur : messages privés, groupes (commandes et mentions), boutons |
| `bot_template/gpchat.py` | client API, polling parallèle ordonné, vérification de signature |
| `bot_template/webhook.py` | serveur webhook (signature, 200 immédiat, dédoublonnage) |
| `bot_template/config.py` | variables d'environnement validées |
| `bot_template/ops.py` | journaux JSON, métriques, `/healthz` `/readyz` `/metrics` |
| `bot_template/store.py` | préférences (fichier JSON atomique) |

## Configuration
| Variable | Défaut | Rôle |
|---|---|---|
| `GPCHAT_API_KEY` | — | clé API du bot (**obligatoire**) |
| `GPCHAT_MODE` | `polling` | `polling` ou `webhook` |
| `GPCHAT_WEBHOOK_SECRET` | — | secret(s) de signature, séparés par des virgules pendant une rotation |
| `PORT` | `8080` | port du webhook |
| `CONCURRENCY` | `16` | conversations traitées en parallèle (polling) |
| `DATA_DIR` | `./data` | préférences ; vide = mémoire seulement |
| `ADMIN_IDS` | — | userId des administrateurs (`/whoami` affiche le vôtre) |
| `DEFAULT_LANG` | `fr` | `fr` ou `en` |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warn`, `error` |
| `OPS_PORT` / `OPS_HOST` | `9100` / `127.0.0.1` | serveur d'exploitation (jamais exposé sur Internet) |

## Production
```bash
docker build -t mon-bot .
docker run -d --restart unless-stopped --env-file .env -v mon-bot-data:/data -p 127.0.0.1:9100:9100 mon-bot
```
- Webhook : mettez le bot derrière un reverse proxy HTTPS, déclarez l'URL dans la console et testez-la (bouton *Tester*).
- Alertes : renseignez un e-mail ou un webhook d'alerte dans la console — GPChat vous prévient si votre bot ne vient plus chercher ses messages ou si votre webhook tombe.
- État de la plateforme : https://gpchat.app/status (JSON : `GET https://api.gpchat.app/v1/status`).

## Tests
```bash
python -m unittest discover -s tests -v   # signature, configuration, commandes, groupes, boutons, polling ordonné
```

---

## English
Production-ready **Python** starter (standard library only) for a GPChat bot: polling or signed webhook, ordered parallel polling, retries, commands, buttons, FR/EN, JSON logs, `/healthz` `/readyz` `/metrics`, Docker, CI, tests.
Click **“Use this template”**, copy `.env.example` to `.env`, set `GPCHAT_API_KEY`, then `python -m bot_template`. Write your bot in `bot_template/commands.py`.
Docs: https://gpchat.app/en/developers/docs.html

Licence MIT.
