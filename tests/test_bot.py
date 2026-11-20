import hashlib
import hmac
import threading
import time
import unittest

from bot_template.bot import Bot, parse_command
from bot_template.config import ConfigError, load_config
from bot_template.gpchat import conversation_key, poll, verify_webhook_signature
from bot_template.ops import Logger, Metrics
from bot_template.store import Store
from bot_template.webhook import Dedupe

SILENT = Logger("test", "error", out=lambda _l: None)


def sign(body: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class FakeClient:
    def __init__(self):
        self.sent = []
        self.edits = []

    def send(self, target, text, markdown=False, buttons=None):
        self.sent.append({"target": target, "text": text, "markdown": markdown, "buttons": buttons})

    def edit_message(self, target, msg_id, content=None, buttons=None):
        self.edits.append({"msgId": msg_id, "content": content})

    def send_chat_action(self, *a, **k):
        return None


class SignatureTest(unittest.TestCase):
    def test_signature(self):
        body = b'{"id":"e1"}'
        self.assertTrue(verify_webhook_signature(body, sign(body, "s1"), ["s1"]))
        self.assertFalse(verify_webhook_signature(body + b" ", sign(body, "s1"), ["s1"]))
        self.assertFalse(verify_webhook_signature(body, sign(body, "s1", int(time.time()) - 3600), ["s1"]))
        self.assertTrue(verify_webhook_signature(body, sign(body, "ancien"), ["nouveau", "ancien"]))
        self.assertFalse(verify_webhook_signature(body, "n'importe quoi", ["s1"]))
        self.assertFalse(verify_webhook_signature(body, None, ["s1"]))


class ConfigTest(unittest.TestCase):
    def test_errors_grouped(self):
        with self.assertRaises(ConfigError) as cm:
            load_config({"GPCHAT_MODE": "webhook", "CONCURRENCY": "0"})
        msg = str(cm.exception)
        for part in ("GPCHAT_API_KEY", "GPCHAT_WEBHOOK_SECRET", "CONCURRENCY"):
            self.assertIn(part, msg)

    def test_defaults(self):
        c = load_config({"GPCHAT_API_KEY": "k", "GPCHAT_WEBHOOK_SECRET": "a, b"})
        self.assertEqual(c.mode, "polling")
        self.assertEqual(c.concurrency, 16)
        self.assertEqual(c.webhook_secrets, ["a", "b"])


class BotTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.bot = Bot(self.client, Store(""), ["admin"], "fr", SILENT)

    def dm(self, text, sender="u1"):
        self.bot.handle({"id": text, "type": "message.received", "data": {"from": sender, "chatId": sender, "type": "text", "textMsg": text}})
        return self.client.sent[-1]

    def test_parse(self):
        self.assertEqual(parse_command("/echo@mon_bot bonjour  "), ("echo", "bonjour"))
        self.assertEqual(parse_command("/PING"), ("ping", ""))
        self.assertIsNone(parse_command("bonjour"))

    def test_commands(self):
        self.assertIn("Bonjour", self.dm("/start")["text"])
        self.assertFalse(self.dm("/echo **gras**")["markdown"])
        self.dm("/lang en")
        self.assertIn("Pong!", self.dm("/ping")["text"])
        self.assertIn("reserved", self.dm("/stats")["text"])
        self.assertIn("utilisateurs", self.dm("/stats", "admin")["text"])
        self.assertIn("Unknown", self.dm("/inconnue")["text"])

    def test_group_and_buttons(self):
        self.bot.handle({"id": "g1", "type": "group_message.received", "data": {"from": "u1", "groupId": "G", "type": "text", "textMsg": "salut"}})
        self.assertEqual(self.client.sent, [])
        self.bot.handle({"id": "g2", "type": "group_message.received", "data": {"from": "u1", "groupId": "G", "type": "text", "textMsg": "/ping"}})
        self.assertEqual(self.client.sent[-1]["target"], {"groupId": "G"})
        self.bot.handle({"id": "c1", "type": "callback.received", "data": {"from": "u1", "chatId": "u1", "data": "counter:3", "msgId": "m9"}})
        self.assertEqual(self.client.edits[-1], {"msgId": "m9", "content": "🔢 Compteur : **3**"})


class PollTest(unittest.TestCase):
    def test_order_parallel_ack(self):
        batches = [[
            {"id": "a1", "type": "message.received", "data": {"from": "A", "chatId": "A"}},
            {"id": "a2", "type": "message.received", "data": {"from": "A", "chatId": "A"}},
            {"id": "b1", "type": "message.received", "data": {"from": "B", "chatId": "B"}},
        ]]
        acks = []

        class Client:
            def get_updates(self, ack=None, limit=50, timeout=0):
                acks.extend(ack or [])
                return {"updates": batches.pop(0) if batches else []}

        order, running, peak = [], [0], [0]
        lock = threading.Lock()

        def handler(u):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.15 if u["id"] == "a1" else 0.02)
            with lock:
                order.append(u["id"])
                running[0] -= 1

        stop = poll(Client(), handler, concurrency=8, timeout=0, busy_poll=0.02, idle_delay=0.02)
        time.sleep(0.6)
        stop()
        self.assertLess(order.index("a1"), order.index("a2"))
        self.assertLess(order.index("b1"), order.index("a1"))
        self.assertEqual(peak[0], 2)
        self.assertEqual(sorted(acks), ["a1", "a2", "b1"])
        self.assertEqual(conversation_key({"id": "x", "data": {"groupId": "G", "from": "u"}}), "g:G")


class MiscTest(unittest.TestCase):
    def test_dedupe_and_metrics(self):
        d = Dedupe(2)
        self.assertTrue(d.first_time("a"))
        self.assertFalse(d.first_time("a"))
        d.first_time("b")
        d.first_time("c")
        self.assertTrue(d.first_time("a"))
        m = Metrics()
        m.inc("events_total", {"type": "x", "result": "ok"}, "Événements")
        m.observe("event_duration_seconds", 0.5, {"type": "x"})
        self.assertIn('gpchat_bot_events_total{result="ok",type="x"} 1', m.render())
        self.assertIn('gpchat_bot_event_duration_seconds_count{type="x"} 1', m.render())


if __name__ == "__main__":
    unittest.main()
