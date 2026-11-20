# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) · versionnage : [SemVer](https://semver.org/lang/fr/)

## [Non publié]

## [1.0.0] — 2026-11-20

### Ajouté
- Modèle de bot Python (bibliothèque standard uniquement) : polling parallèle ordonné par conversation ou webhook signé (rotation de secret, dédoublonnage), client API avec nouveaux essais, commandes, boutons, Markdown, FR/EN, préférences persistantes.
- Exploitation : journaux JSON, `/healthz` `/readyz` `/metrics`, configuration validée au démarrage.
- Dockerfile durci, CI (Python 3.10 à 3.13), 8 tests sans réseau.
