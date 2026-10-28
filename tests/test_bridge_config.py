"""
Tests for bridge/index.js configuration sanity.
Catches Error #7 (Axios timeout too short) and Error #2 (PREFECT_JID hardcoded).
These are static analysis tests — no Node.js runtime needed.
"""
import re
from pathlib import Path


BRIDGE_JS = Path("bridge/index.js").read_text(encoding="utf-8")


def test_axios_timeout_is_sufficient():
    """All Axios timeouts must be >= 30,000ms (30s) to handle slow RAG responses."""
    timeouts = [int(m) for m in re.findall(r"timeout:\s*(\d+)", BRIDGE_JS)]
    assert timeouts, "No Axios timeout found in bridge/index.js — add { timeout: 60000 }"
    low = [t for t in timeouts if t < 30000]
    assert not low, (
        f"Axios timeout(s) too short: {low}ms — minimum is 30,000ms (30s). "
        "Gemini RAG can take up to 40s on complex queries."
    )


def test_prefect_jid_uses_env_var():
    """VIP alerts must use PREFECT_JID from env, not hardcoded sock.user resolution."""
    assert "process.env.PREFECT_JID" in BRIDGE_JS, (
        "bridge/index.js must use process.env.PREFECT_JID for VIP alerts. "
        "Relying solely on jidNormalizedUser(sock.user.id) causes 'Waiting for this message'."
    )


def test_jid_normalization_imported():
    """jidNormalizedUser must be imported for @lid → @s.whatsapp.net conversion."""
    assert "jidNormalizedUser" in BRIDGE_JS, (
        "jidNormalizedUser is not imported/used in bridge/index.js"
    )


def test_queue_file_defined():
    """queue.jsonl path must be defined for zero-drop message buffering."""
    assert "queue.jsonl" in BRIDGE_JS or "QUEUE_FILE" in BRIDGE_JS, (
        "queue.jsonl buffer not found in bridge/index.js"
    )


def test_allowed_groups_whitelist_has_nine_entries():
    """The bridge whitelist must contain all 9 cohort group JIDs."""
    jid_pattern = re.compile(r"'\d+@g\.us'")
    matches = jid_pattern.findall(BRIDGE_JS)
    unique = set(matches)
    assert len(unique) >= 9, (
        f"Expected at least 9 group JIDs in bridge whitelist, found {len(unique)}: {unique}"
    )
