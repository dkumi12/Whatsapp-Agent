"""
Centralized Cohort Registry for WhatsApp Cohort Copilot.
Maps group JIDs to their official names/tags.
"""
import re
from typing import Dict, Optional, List, Tuple

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

COHORT_ALIASES: List[Tuple[List[str], str]] = [
    (["aws practitioner cohort 2", "aws practitioner", "aws cohort 2", "aws"], "AWS PRACTITIONER Cohort 2"),
    (["python with ai cohort 2", "python with ai", "python ai", "py ai"], "Python with AI Cohort 2"),
    (["a.i with python for everybody", "ai with python", "python for everybody", "py4e"], "A.I with Python for Everybody"),
    (["data science and analytics", "data science", "analytics", "ds"], "Data Science And Analytics Free-Training"),
    (["cloudwithshad cohort 2", "cloud cohort 2", "shad cohort 2"], "CloudWithShad Cohort 2"),
    (["cloud practitioner - q n a", "cloud practitioner qna", "qna", "q n a", "q&a"], "Cloud Practitioner - Q n A"),
    (["cloudwithshad", "cloud with shad", "shad"], "CloudWithShad"),
    (["cohort 1", "c1"], "Cohort 1"),
    (["cohort 2", "c2"], "Cohort 2"),
]

def resolve_cohort_tag(group_id: str) -> Optional[str]:
    """Returns the readable cohort name if the group is whitelisted, else None."""
    return COHORT_REGISTRY.get(group_id)

def is_whitelisted_group(group_id: str) -> bool:
    """Checks if a group JID is permitted to interact with the bot."""
    return group_id in COHORT_REGISTRY

def get_all_cohort_jids() -> list[str]:
    """Returns list of all allowed group JIDs."""
    return list(COHORT_REGISTRY.keys())

def find_matching_cohort(text: str) -> Optional[str]:
    """Matches user input (e.g. 'aws', 'python', 'cohort 2') to official cohort name."""
    clean = text.lower().strip()
    if not clean:
        return None
    # 1. Exact match against official names
    for name in COHORT_REGISTRY.values():
        if name.lower() == clean:
            return name
    # 2. Match against aliases
    for aliases, official_name in COHORT_ALIASES:
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', clean):
                return official_name
    # 3. Partial contains fallback
    for name in COHORT_REGISTRY.values():
        if clean in name.lower():
            return name
    return None
