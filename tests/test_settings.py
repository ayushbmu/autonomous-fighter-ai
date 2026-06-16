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


def test_load_runtime_settings_hud_env_override(monkeypatch):
    monkeypatch.setenv("AF_HUD_DEBUG_OVERLAY", "false")
    monkeypatch.setenv("AF_HUD_HEALTH_LEFT_ROI", "0.10,0.02,0.40,0.08")
    monkeypatch.setenv("AF_HUD_SHADOW_H_MIN", "82")
    monkeypatch.setenv("AF_HUD_SHADOW_H_MAX", "140")
    settings = load_runtime_settings()

    assert settings.hud_debug_overlay is False
    assert settings.hud_health_left_roi == (0.10, 0.02, 0.40, 0.08)
    assert settings.hud_shadow_h_min == 82
    assert settings.hud_shadow_h_max == 140
