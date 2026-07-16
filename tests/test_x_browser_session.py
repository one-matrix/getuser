from contextlib import nullcontext
from types import SimpleNamespace

from config import x_config
from media_platform.x import browser_session
from tools import browser_launcher


def test_profile_cdp_port_only_returns_a_live_profile_port(tmp_path, monkeypatch):
    profile_dir = tmp_path / "x-profile"
    profile_dir.mkdir()
    port = 9333
    (profile_dir / "DevToolsActivePort").write_text(
        f"{port}\n/devtools/browser/test\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        browser_session.socket,
        "create_connection",
        lambda *args, **kwargs: nullcontext(),
    )

    assert browser_session._profile_cdp_port(profile_dir) == port

    monkeypatch.setattr(
        browser_session.socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("closed")),
    )
    assert browser_session._profile_cdp_port(profile_dir) is None


def test_open_x_login_window_starts_the_dedicated_profile_with_cdp(
    tmp_path,
    monkeypatch,
):
    profile_dir = tmp_path / "x-profile"
    browser_path = tmp_path / "Google Chrome"
    browser_path.write_text("", encoding="utf-8")
    browser_path.chmod(0o755)
    launched = {}

    def fake_popen(args, **kwargs):
        launched["args"] = args
        launched["kwargs"] = kwargs
        return SimpleNamespace(pid=4321)

    monkeypatch.setattr(x_config, "X_BROWSER_USER_DATA_DIR", str(profile_dir))
    monkeypatch.setattr(browser_session.config, "CUSTOM_BROWSER_PATH", str(browser_path))
    monkeypatch.setattr(
        browser_session.subprocess,
        "Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        browser_launcher.BrowserLauncher,
        "find_available_port",
        lambda self, start_port: 9333,
    )

    result = browser_session.open_x_login_window()

    assert f"--user-data-dir={profile_dir}" in launched["args"]
    assert "--remote-debugging-port=9333" in launched["args"]
    assert "--remote-debugging-address=127.0.0.1" in launched["args"]
    assert result["debug_port"] == 9333
    assert result["already_running"] is False


def test_macos_browser_launcher_preserves_keychain_environment(
    tmp_path,
    monkeypatch,
):
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return SimpleNamespace(pid=1234)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SECURITYSESSIONID", "test-session")
    monkeypatch.setenv("VSCODE_TEST_INJECTED", "remove-me")
    monkeypatch.setattr(browser_launcher.subprocess, "Popen", fake_popen)

    launcher = browser_launcher.BrowserLauncher()
    launcher.system = "Darwin"
    launcher.launch_browser(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        9222,
        user_data_dir=str(tmp_path / "profile"),
    )

    assert captured["env"]["HOME"] == str(tmp_path)
    assert captured["env"]["SECURITYSESSIONID"] == "test-session"
    assert "VSCODE_TEST_INJECTED" not in captured["env"]
