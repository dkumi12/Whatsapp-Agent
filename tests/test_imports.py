"""
Tests for Error #4 — critical package imports
Runs on the CI Linux runner to catch missing dependencies before deploy.
"""
import importlib
import pytest


REQUIRED_PACKAGES = [
    ("fastapi", "FastAPI"),
    ("uvicorn", None),
    ("pydantic", "BaseModel"),
    ("langgraph", None),
    ("langchain", None),
    ("langchain_openai", "ChatOpenAI"),
    ("psycopg", None),
    ("pgvector", None),
    ("chromadb", None),
    ("youtube_transcript_api", None),
    ("dotenv", None),
]


@pytest.mark.parametrize("package,attr", REQUIRED_PACKAGES)
def test_package_importable(package, attr):
    """Each critical package must be importable — catches missing pip installs."""
    mod = importlib.import_module(package)
    if attr:
        assert hasattr(mod, attr), (
            f"Package '{package}' imported but missing attribute '{attr}'"
        )


def test_src_modules_importable():
    """All src/ modules must be importable without connecting to external services."""
    import src.schemas   # noqa: F401
    import src.cohorts   # noqa: F401
    import src.config    # noqa: F401
