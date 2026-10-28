"""
Tests for cohort registry and alias resolution (src/cohorts.py).
Also catches Error #9 indirectly — JID whitelist must stay in sync.
"""
import pytest
from src.cohorts import (
    COHORT_REGISTRY,
    resolve_cohort_tag,
    is_whitelisted_group,
    find_matching_cohort,
    get_all_cohort_jids,
)

# All 9 known cohort JIDs
KNOWN_JIDS = [
    "120363428812662381@g.us",
    "120363406407748018@g.us",
    "120363427542055326@g.us",
    "120363430746173915@g.us",
    "120363411584074404@g.us",
    "120363415570593617@g.us",
    "120363433400665333@g.us",
    "120363408183500853@g.us",
    "120363426897508316@g.us",
]


def test_all_jids_end_with_g_us():
    """All group JIDs must be @g.us — not @s.whatsapp.net or @lid."""
    for jid in COHORT_REGISTRY:
        assert jid.endswith("@g.us"), (
            f"Non-group JID found in COHORT_REGISTRY: {jid}"
        )


def test_all_known_jids_are_whitelisted():
    """Every known cohort JID must be in the registry."""
    for jid in KNOWN_JIDS:
        assert is_whitelisted_group(jid), f"JID not whitelisted: {jid}"


def test_unknown_jid_is_not_whitelisted():
    """A random JID must NOT be whitelisted (privacy shield)."""
    assert not is_whitelisted_group("999999999999@g.us")
    assert not is_whitelisted_group("233205265381@s.whatsapp.net")


def test_resolve_cohort_tag_returns_name():
    assert resolve_cohort_tag("120363428812662381@g.us") == "Cohort 1"
    assert resolve_cohort_tag("120363406407748018@g.us") == "Cohort 2"


@pytest.mark.parametrize("alias,expected", [
    ("aws", "AWS PRACTITIONER Cohort 2"),
    ("python", "Python with AI Cohort 2"),
    ("data science", "Data Science And Analytics Free-Training"),
    ("qna", "Cloud Practitioner - Q n A"),
    ("shad", "CloudWithShad"),
    ("cohort 1", "Cohort 1"),
    ("c2", "Cohort 2"),
])
def test_alias_resolution(alias, expected):
    result = find_matching_cohort(alias)
    assert result == expected, f"Alias '{alias}' → expected '{expected}', got '{result}'"


def test_unknown_alias_returns_none():
    assert find_matching_cohort("random gibberish xyz") is None
    assert find_matching_cohort("") is None


def test_registry_has_nine_cohorts():
    """Sanity check — must have all 9 cohorts registered."""
    assert len(COHORT_REGISTRY) == 9, (
        f"Expected 9 cohorts, found {len(COHORT_REGISTRY)}. "
        "Update KNOWN_JIDS in this test if you added a new cohort."
    )
