"""
Tests for Error #5 — state_input key completeness
Parses api.py with AST to ensure all required LangGraph state keys are present.
Add a key to REQUIRED_STATE_KEYS whenever you add one to the LangGraph state schema.
"""
import ast
from pathlib import Path


# ✅ Update this list whenever you add a new field to the LangGraph state schema
REQUIRED_STATE_KEYS = [
    "sender",
    "group_id",
    "raw_message",
    "file_name",
    "mime_type",
    "file_data",
    "classification",
    "retrieved_context",
    "draft_response",
    "should_reply",
    "should_alert_prefect",
    "prefect_alert_text",
]


def _extract_state_input_keys() -> list[str]:
    """Parse src/api.py and extract the keys in the state_input dict literal."""
    source = Path("src/api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "state_input":
                    if isinstance(node.value, ast.Dict):
                        return [
                            k.value for k in node.value.keys
                            if isinstance(k, ast.Constant)
                        ]
    return []


def test_state_input_dict_exists():
    """state_input dict must exist in api.py."""
    keys = _extract_state_input_keys()
    assert keys, (
        "Could not find 'state_input = { ... }' in src/api.py. "
        "Make sure the webhook handler builds this dict."
    )


def test_state_input_has_all_required_keys():
    """Every key in REQUIRED_STATE_KEYS must be present in state_input."""
    actual_keys = _extract_state_input_keys()
    missing = [k for k in REQUIRED_STATE_KEYS if k not in actual_keys]
    assert not missing, (
        f"state_input in api.py is missing required LangGraph keys: {missing}\n"
        f"Found keys: {actual_keys}"
    )
