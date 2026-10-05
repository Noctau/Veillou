import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_cli(*args: str, password: str = "cli-password-1"):
    import os

    env = {**os.environ, "VEILLOU_PASSWORD": password}
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_create_user_and_duplicate():
    ok = run_cli("create-user", "cli@example.com")
    assert ok.returncode == 0, ok.stderr
    assert "cli@example.com" in ok.stdout

    dup = run_cli("create-user", "CLI@example.com")
    assert dup.returncode != 0
    assert "уже есть" in dup.stderr


def test_cli_set_password_unknown_user():
    res = run_cli("set-password", "ghost@example.com")
    assert res.returncode != 0
    assert "не найден" in res.stderr
