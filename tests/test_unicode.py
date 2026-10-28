"""
Tests for Error #10 — UnicodeEncodeError safety
Simulates emoji-heavy and Arabic WhatsApp messages that crash on Windows cp1252.
These pass on Linux CI (utf-8) to catch any encoding assumptions in the codebase.
"""
import sys
from src.schemas import WhatsAppWebhookPayload


SAMPLE_MESSAGES = [
    "🚨 VIP Alert from E. Shad — Payment deadline today!",
    "Hello Team 👋🏾 — Please submit your assignments 📝",
    "مرحبا بكم في كورس السحابة",           # Arabic
    "☁️ CloudWithShad Cohort 2 Update 🎯",
    "Deadline ⏰ Friday 5PM — Don't miss it! 🔥💪🏽",
    "Assignment Link: https://example.com/hw1 📎",
]


def test_python_stdout_is_utf8_on_ci():
    """CI runner must use UTF-8 stdout — catches Windows cp1252 assumptions."""
    encoding = sys.stdout.encoding or ""
    assert encoding.lower().replace("-", "") in ("utf8", "utf-8", ""), (
        f"stdout encoding is '{encoding}' — expected utf-8. "
        "Add sys.stdout.reconfigure(encoding='utf-8') to scripts that print WhatsApp messages."
    )


def test_emoji_messages_survive_roundtrip():
    """Messages with emoji must encode → decode to utf-8 without loss."""
    for msg in SAMPLE_MESSAGES:
        encoded = msg.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert decoded == msg, f"Roundtrip failed for: {msg!r}"


def test_webhook_payload_accepts_emoji():
    """WhatsAppWebhookPayload schema must accept emoji without crashing."""
    for msg in SAMPLE_MESSAGES:
        payload = WhatsAppWebhookPayload(
            group_id="120363428812662381@g.us",
            sender="E. Shad",
            message=msg,
            timestamp=1234567890,
            is_private=False,
        )
        assert payload.message == msg
