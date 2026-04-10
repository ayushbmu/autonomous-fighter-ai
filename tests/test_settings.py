import os

from common.settings import load_runtime_settings


def test_load_runtime_settings_defaults(monkeypatch):
    monkeypatch.delenv("AF_API_HOST", raising=False)
    monkeypatch.delenv("AF_API_PORT", raising=False)
    settings = load_runtime_settings()
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8001


def test_load_runtime_settings_env_override(monkeypatch):
    monkeypatch.setenv("AF_API_HOST", "0.0.0.0")
    monkeypatch.setenv("AF_API_PORT", "9001")
    monkeypatch.setenv("AF_TARGET_FPS", "45")
    settings = load_runtime_settings()
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9001
    assert settings.target_fps == 45.0
