"""
Tests for bridge/index.js configuration sanity.
Catches Error #7 (Axios timeout too short) and Error #2 (PREFECT_JID hardcoded).
These are static analysis tests — no Node.js runtime needed.
"""
import re
from pathlib import Path


BRIDGE_JS = Path("bridge/index.js").read_text(encoding="utf-8")


def test_axios_timeout_is_sufficient():
    """
    axios.post timeouts (message processing) must be >= 30,000ms.
    The axios.get health-check probe (3000ms) is intentionally short and excluded.
    """
    # Extract only axios.post call timeouts — health probe GET is allowed to be short
    post_timeouts = [
        int(m)
        for m in re.findall(
            r"axios\.post\([^)]*timeout:\s*(\d+)", BRIDGE_JS, re.DOTALL
        )
    ]
    assert post_timeouts, (
        "No axios.post timeout found in bridge/index.js — "
        "add { timeout: 60000 } to all axios.post() calls."
    )
    low = [t for t in post_timeouts if t < 30000]
    assert not low, (
        f"axios.post timeout(s) too short: {low}ms — minimum is 30,000ms (30s). "
        "Gemini RAG can take up to 40s on complex queries. "
        "Note: the 3000ms axios.get health probe is intentional and not checked here."
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
