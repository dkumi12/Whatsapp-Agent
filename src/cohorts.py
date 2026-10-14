"""
Centralized Cohort Registry for WhatsApp Cohort Copilot.
Maps group JIDs to their official names/tags.
"""
from typing import Dict, Optional

COHORT_REGISTRY: Dict[str, str] = {
    # Original Cohorts
    "120363428812662381@g.us": "Cohort 1",
    "120363406407748018@g.us": "Cohort 2",
    
    # Newly Added Cohorts
    "120363427542055326@g.us": "AWS PRACTITIONER Cohort 2",
    "120363430746173915@g.us": "Python with AI Cohort 2",
    "120363411584074404@g.us": "A.I with Python for Everybody",
    "120363415570593617@g.us": "Data Science And Analytics Free-Training",
    "120363433400665333@g.us": "CloudWithShad Cohort 2",
    "120363408183500853@g.us": "Cloud Practitioner - Q n A",
    "120363426897508316@g.us": "CloudWithShad",
}

def resolve_cohort_tag(group_id: str) -> Optional[str]:
    """Returns the readable cohort name if the group is whitelisted, else None."""
    return COHORT_REGISTRY.get(group_id)

def is_whitelisted_group(group_id: str) -> bool:
    """Checks if a group JID is permitted to interact with the bot."""
    return group_id in COHORT_REGISTRY

def get_all_cohort_jids() -> list[str]:
    """Returns list of all allowed group JIDs."""
    return list(COHORT_REGISTRY.keys())
