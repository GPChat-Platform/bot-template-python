"""Textes du bot (français / anglais). {x} = paramètre. Ajoutez vos textes ici."""

TEXTS = {
    "fr": {
        "welcome": "👋 **Bonjour !** Je suis un bot modèle GPChat écrit en Python.\n\nTapez /help pour voir ce que je sais faire.",
        "help": "📖 **Commandes**",
        "pong": "🏓 Pong ! Le bot répond.",
        "echo": "🔁",
        "echo_usage": "Exemple : /echo bonjour",
        "counter": "🔢 Compteur : **{n}**",
        "lang_set": "🇫🇷 Langue : français.",
        "lang_bad": "Langue : /lang fr ou /lang en",
        "whoami": "🆔 Votre identifiant GPChat : `{id}`",
        "unknown": "Commande inconnue. Tapez /help.",
        "admin_only": "🔒 Commande réservée aux administrateurs du bot.",
        "docs": "📚 Documentation",
    },
    "en": {
        "welcome": "👋 **Hi!** I am a GPChat template bot written in Python.\n\nType /help to see what I can do.",
        "help": "📖 **Commands**",
        "pong": "🏓 Pong! The bot is answering.",
        "echo": "🔁",
        "echo_usage": "Example: /echo hello",
        "counter": "🔢 Counter: **{n}**",
        "lang_set": "🇬🇧 Language: English.",
        "lang_bad": "Language: /lang fr or /lang en",
        "whoami": "🆔 Your GPChat id: `{id}`",
        "unknown": "Unknown command. Type /help.",
        "admin_only": "🔒 This command is reserved for the bot administrators.",
        "docs": "📚 Documentation",
    },
}


def t(lang: str, key: str, **params) -> str:
    text = TEXTS.get(lang, TEXTS["fr"]).get(key) or TEXTS["fr"][key]
    for k, v in params.items():
        text = text.replace("{" + k + "}", str(v))
    return text
