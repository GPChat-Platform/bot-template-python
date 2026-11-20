"""LES COMMANDES DU BOT — c'est ici que vous écrivez votre bot.

Chaque commande est une fonction décorée par @command(nom, fr=…, en=…, admin_only=False) qui reçoit `ctx`
(voir bot.py) : ctx.args, ctx.lang, ctx.user_id, ctx.is_group, ctx.is_admin, ctx.reply(texte, markdown=…, buttons=…),
ctx.typing(), ctx.t(clé, **params), ctx.prefs, ctx.set_prefs(**patch).
Les descriptions alimentent /help et la liste à déclarer dans la console : python -m bot_template commands
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .gpchat import callback_button, link_button


@dataclass
class Command:
    name: str
    fr: str
    en: str
    run: Callable
    admin_only: bool = False


COMMANDS: dict[str, Command] = {}


def command(name: str, fr: str, en: str, admin_only: bool = False):
    def register(fn: Callable) -> Callable:
        COMMANDS[name] = Command(name, fr, en, fn, admin_only)
        return fn
    return register


def counter_buttons(n: int) -> list:
    return [[callback_button("➖", f"counter:{n - 1}"), callback_button("➕", f"counter:{n + 1}")]]


@command("start", "Démarrer le bot", "Start the bot")
def start(ctx):
    ctx.reply(ctx.t("welcome"), buttons=[[callback_button("🔢 Compteur / Counter", "counter:0"), link_button(ctx.t("docs"), "https://gpchat.app/developers/docs.html")]])


@command("help", "Liste des commandes", "List the commands")
def help_(ctx):
    lines = [f"• `/{c.name}` — {c.fr if ctx.lang == 'fr' else c.en}" for c in COMMANDS.values() if not c.admin_only or ctx.is_admin]
    ctx.reply(ctx.t("help") + "\n" + "\n".join(lines))


@command("ping", "Vérifier que le bot répond", "Check that the bot answers")
def ping(ctx):
    ctx.reply(ctx.t("pong"))


@command("echo", "Répète votre texte : /echo bonjour", "Repeats your text: /echo hello")
def echo(ctx):
    # Texte venant d'un utilisateur : renvoyé SANS Markdown (il ne doit pas pouvoir mettre en forme ma réponse).
    if not ctx.args:
        return ctx.reply(ctx.t("echo_usage"))
    ctx.reply(f"{ctx.t('echo')} {ctx.args}", markdown=False)


@command("counter", "Démo de boutons : un compteur modifiable", "Buttons demo: an editable counter")
def counter(ctx):
    ctx.reply(ctx.t("counter", n=0), buttons=counter_buttons(0))


@command("lang", "Changer de langue : /lang fr ou en", "Change language: /lang fr or en")
def lang(ctx):
    v = ctx.args.lower()
    if v not in ("fr", "en"):
        return ctx.reply(ctx.t("lang_bad"))
    ctx.set_prefs(lang=v)
    ctx.reply(ctx.t_in(v, "lang_set"))


@command("whoami", "Afficher votre identifiant GPChat", "Show your GPChat id")
def whoami(ctx):
    ctx.reply(ctx.t("whoami", id=ctx.user_id))


@command("stats", "Statistiques du bot (admin)", "Bot statistics (admin)", admin_only=True)
def stats(ctx):
    ctx.reply(f"📊 {ctx.users_count()} utilisateurs")
