"""
Tests for Error #3 — .env path resolution
Ensures config.py always finds the .env from any working directory.
"""
from pathlib import Path


def test_env_path_is_absolute():
    """config.py must use an absolute path, not a relative one."""
    source = Path("src/config.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve()" in source, (
        "config.py must use Path(__file__).resolve() for .env path, "
        "not a relative path that breaks on the VM."
    )


def test_env_path_points_to_project_root():
    """The resolved .env path must point to the project root."""
    from src.config import ENV_PATH
    assert ENV_PATH.name == ".env", f"Expected .env, got: {ENV_PATH.name}"
    # parent of src/ is the project root
    assert ENV_PATH.parent == Path("src/config.py").resolve().parent.parent, (
        f".env path {ENV_PATH} is not at the project root."
    )


def test_settings_object_loads_without_crash():
    """Settings class must instantiate without raising even if .env is absent (CI has no .env)."""
    try:
        from src.config import Settings
        s = Settings()
        assert isinstance(s.OPENROUTER_MODEL, str)
    except Exception as e:
        assert False, f"Settings() raised unexpectedly: {e}"
