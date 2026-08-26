"""Local Windows launcher and admin panel for Yeonsam Bot.

This file intentionally uses only the Python standard library so a user can
start the project from a double-clicked .bat file. The Discord bot itself
continues to run from bot/main.py; this process supervises it and exposes a
loopback-only control panel.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BOT_ROOT = ROOT / "bot"
ENV_FILE = ROOT / ".env"
PANEL_FILE = Path(__file__).with_name("admin_panel.html")
DEFAULT_ADMIN_PORT = 8787
DEFAULT_HEALTH_PORT = 8788
DEFAULT_LOG_TAIL = 12000
TOKEN_KEYS = ("DISCORD_BOT_TOKEN", "TOKEN")
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_port(value: str | None, default: int) -> int:
    """Return a safe TCP port, falling back to *default* for bad input."""

    try:
        port = int(value or default)
    except (TypeError, ValueError):
        return default
    return port if 1024 <= port <= 65535 else default


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
        return value.replace(r"\n", "\n").replace(r"\"", '"').replace(r"\'", "'")

    # Keep the simple .env format useful for comments without changing token
    # characters that occur before the first whitespace-delimited comment.
    return value.split(" #", 1)[0].rstrip()


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Load simple KEY=VALUE entries from a UTF-8 .env file.

    The launcher deliberately does not print values. It supports both the
    repository's legacy TOKEN key and the user-facing DISCORD_BOT_TOKEN key.
    """

    if not path.exists():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise RuntimeError(f"환경 파일을 읽을 수 없습니다: {path} ({exc})") from exc

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, raw_value = stripped.partition("=")
        key = key.strip()
        if not separator or not ENV_KEY_PATTERN.fullmatch(key):
            raise RuntimeError(f".env {line_number}번째 줄의 형식이 올바르지 않습니다.")
        values[key] = _parse_env_value(raw_value)
    return values


def resolve_python() -> Path:
    """Prefer the repository virtual environment, then the current Python."""

    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def build_runtime_environment(
    env_file_values: dict[str, str], health_port: int
) -> tuple[dict[str, str], bool]:
    """Build the child environment and map DISCORD_BOT_TOKEN to TOKEN."""

    environment = dict(env_file_values)
    environment.update(os.environ)

    token = ""
    for key in TOKEN_KEYS:
        candidate = environment.get(key, "").strip()
        if candidate:
            token = candidate
            break

    child_environment = dict(environment)
    child_environment["TOKEN"] = token
    data_dir = Path(environment.get("BOT_DATA_DIR", str(ROOT / "data"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    child_environment["BOT_DATA_DIR"] = str(data_dir.resolve())
    child_environment["PORT"] = str(health_port)
    child_environment["PYTHONUNBUFFERED"] = "1"

    python_paths = [
        str(BOT_ROOT),
        str(ROOT / ".bot_runtime_deps"),
        str(ROOT / ".bot_deps"),
    ]
    existing_python_path = child_environment.get("PYTHONPATH", "")
    if existing_python_path:
        python_paths.extend(existing_python_path.split(os.pathsep))
    child_environment["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys(path for path in python_paths if Path(path).exists())
    )
    return child_environment, bool(token)


def dependency_check(python_executable: Path, environment: dict[str, str]) -> tuple[bool, str]:
    """Check the two packages required before loading the bot cogs."""

    try:
        result = subprocess.run(
            [str(python_executable), "-c", "import discord, steam_discord_patch_alerts"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Python 의존성 확인에 실패했습니다: {exc}"
    if result.returncode == 0:
        return True, "의존성 준비 완료"
    detail = (result.stderr or result.stdout).strip().splitlines()
    return False, detail[-1] if detail else "필수 Python 패키지를 불러오지 못했습니다."


def ensure_dependencies(python_executable: Path, environment: dict[str, str]) -> tuple[bool, str]:
    """Install requirements once when a clean machine has no bot packages."""

    ready, detail = dependency_check(python_executable, environment)
    if ready:
        return True, detail

    requirements = ROOT / "requirements.txt"
    if not requirements.exists():
        return False, f"requirements.txt를 찾을 수 없습니다: {requirements}"

    print("[런처] 필요한 Python 패키지가 없어 자동 설치를 시작합니다.", flush=True)
    try:
        result = subprocess.run(
            [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
        )
    except OSError as exc:
        return False, f"Python 패키지 설치를 실행하지 못했습니다: {exc}"
    if result.returncode != 0:
        return False, "패키지 자동 설치에 실패했습니다. 인터넷 연결과 Python 설치를 확인하세요."
    return dependency_check(python_executable, environment)


def read_tail(path: Path, limit: int = DEFAULT_LOG_TAIL) -> str:
    if not path.exists():
        return "아직 로그가 없습니다."
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"로그를 읽을 수 없습니다: {exc}"
    return content[-limit:]


def read_bot_health(port: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "reachable": True,
                "ready": bool(payload.get("ready")),
                "status": payload.get("status", "unknown"),
            }
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            payload = {}
        return {
            "reachable": True,
            "ready": bool(payload.get("ready")),
            "status": payload.get("status", "starting"),
        }
    except (OSError, ValueError):
        return {"reachable": False, "ready": False, "status": "offline"}


class BotSupervisor:
    """Own the bot child process and expose safe, UI-friendly state."""

    def __init__(self, health_port: int) -> None:
        self.health_port = health_port
        self.python_executable = resolve_python()
        self.process: subprocess.Popen[str] | None = None
        self.log_handle: Any = None
        self.started_at: float | None = None
        self.last_exit_code: int | None = None
        self.last_error = ""
        self.runtime_message = ""
        self.token_configured = False
        self.environment: dict[str, str] = {}
        self.lock = threading.RLock()
        self.refresh_configuration()

    @property
    def log_file(self) -> Path:
        return ROOT / "data" / "admin" / "bot.log"

    @property
    def data_dir(self) -> Path:
        return Path(self.environment.get("BOT_DATA_DIR", ROOT / "data"))

    def refresh_configuration(self) -> None:
        with self.lock:
            values = load_env_file()
            self.environment, self.token_configured = build_runtime_environment(
                values, self.health_port
            )
            if not self.token_configured:
                self.runtime_message = (
                    ".env에 DISCORD_BOT_TOKEN 값이 없습니다. "
                    "토큰을 입력한 뒤 다시 시작하세요."
                )
            else:
                self.runtime_message = ""

    def _refresh_process_locked(self) -> None:
        if self.process is None:
            return
        exit_code = self.process.poll()
        if exit_code is None:
            return
        self.last_exit_code = exit_code
        self.process = None
        self.started_at = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        if exit_code != 0:
            self.last_error = f"봇 프로세스가 종료되었습니다 (exit code {exit_code}). 로그를 확인하세요."

    def start(self) -> tuple[bool, str]:
        with self.lock:
            self._refresh_process_locked()
            if self.process is not None:
                return True, "봇이 이미 실행 중입니다."

            self.refresh_configuration()
            if not self.token_configured:
                return False, self.runtime_message

            ready, detail = ensure_dependencies(self.python_executable, self.environment)
            if not ready:
                self.runtime_message = detail
                return False, detail

            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.log_handle = self.log_file.open("a", encoding="utf-8", buffering=1)
                self.log_handle.write(
                    f"\n--- launcher start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
                )
                creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                self.process = subprocess.Popen(
                    [str(self.python_executable), "-u", str(BOT_ROOT / "main.py")],
                    cwd=BOT_ROOT,
                    env=self.environment,
                    stdout=self.log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                    text=True,
                )
            except (OSError, ValueError) as exc:
                if self.log_handle is not None:
                    self.log_handle.close()
                    self.log_handle = None
                self.process = None
                message = f"봇을 시작하지 못했습니다: {exc}"
                self.last_error = message
                return False, message

            self.started_at = time.time()
            self.last_exit_code = None
            self.last_error = ""
            self.runtime_message = ""
            return True, "봇 실행을 시작했습니다. Discord 연결을 기다리는 중입니다."

    def stop(self) -> tuple[bool, str]:
        with self.lock:
            self._refresh_process_locked()
            process = self.process
            if process is None:
                return True, "봇이 실행 중이 아닙니다."
            process.terminate()

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

        with self.lock:
            self._refresh_process_locked()
            self.last_error = ""
        return True, "봇을 중지했습니다."

    def restart(self) -> tuple[bool, str]:
        stopped, stop_message = self.stop()
        if not stopped:
            return False, stop_message
        return self.start()

    def open_data_folder(self) -> tuple[bool, str]:
        path = self.data_dir.resolve()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            return False, f"폴더를 열지 못했습니다: {exc}"
        return True, "데이터 폴더를 열었습니다."

    def status(self) -> dict[str, Any]:
        with self.lock:
            self._refresh_process_locked()
            process = self.process
            if process is None:
                state = "설정 필요" if not self.token_configured else "중지됨"
                if self.last_exit_code not in (None, 0):
                    state = "오류 종료"
            else:
                state = "실행 중"
            started_at = self.started_at
            pid = process.pid if process is not None else None
            last_error = self.last_error or self.runtime_message

        health = read_bot_health(self.health_port) if process is not None else {
            "reachable": False,
            "ready": False,
            "status": "offline",
        }
        uptime = int(max(0, time.time() - started_at)) if started_at else 0
        return {
            "state": state,
            "pid": pid,
            "ready": health["ready"],
            "health": health,
            "uptime_seconds": uptime,
            "token_configured": self.token_configured,
            "data_dir": str(self.data_dir.resolve()),
            "log_file": str(self.log_file.resolve()),
            "python": str(self.python_executable),
            "message": last_error,
            "last_exit_code": self.last_exit_code,
        }

    def shutdown(self) -> None:
        self.stop()


class AdminHandler(BaseHTTPRequestHandler):
    server: "AdminServer"

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        try:
            body = PANEL_FILE.read_bytes()
        except OSError as exc:
            self._send_json({"ok": False, "message": f"관리자 패널 파일을 읽지 못했습니다: {exc}"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path in ("/", "/index.html"):
            self._send_html()
            return
        if self.path == "/api/status":
            self._send_json({"ok": True, "status": self.server.supervisor.status()})
            return
        if self.path.startswith("/api/logs"):
            self._send_json({"ok": True, "logs": read_tail(self.server.supervisor.log_file)})
            return
        if self.path == "/api/open-data":
            ok, message = self.server.supervisor.open_data_folder()
            self._send_json({"ok": ok, "message": message}, 200 if ok else 500)
            return
        self._send_json({"ok": False, "message": "경로를 찾을 수 없습니다."}, 404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        actions = {
            "/api/bot/start": self.server.supervisor.start,
            "/api/bot/stop": self.server.supervisor.stop,
            "/api/bot/restart": self.server.supervisor.restart,
        }
        action = actions.get(self.path)
        if action is None:
            self._send_json({"ok": False, "message": "지원하지 않는 작업입니다."}, 404)
            return
        try:
            ok, message = action()
            self._send_json({"ok": ok, "message": message}, 200 if ok else 400)
        except Exception as exc:  # Keep the panel usable after an unexpected startup error.
            self._send_json({"ok": False, "message": f"작업 중 오류가 발생했습니다: {exc}"}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        return


class AdminServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], supervisor: BotSupervisor) -> None:
        self.supervisor = supervisor
        super().__init__(address, AdminHandler)


def open_panel_later(url: str) -> None:
    def open_browser() -> None:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            print(f"[런처] 브라우저를 자동으로 열지 못했습니다: {url}", flush=True)

    timer = threading.Timer(1.0, open_browser)
    timer.daemon = True
    timer.start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Yeonsam local bot launcher")
    parser.add_argument("--admin-port", type=int, default=DEFAULT_ADMIN_PORT)
    parser.add_argument("--health-port", type=int, default=DEFAULT_HEALTH_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    args = parser.parse_args()

    admin_port = parse_port(str(args.admin_port), DEFAULT_ADMIN_PORT)
    health_port = parse_port(str(args.health_port), DEFAULT_HEALTH_PORT)
    supervisor = BotSupervisor(health_port)
    server = AdminServer(("127.0.0.1", admin_port), supervisor)
    panel_url = f"http://127.0.0.1:{admin_port}/"

    print(f"[런처] 관리자 패널: {panel_url}", flush=True)
    print("[런처] 이 창을 닫으면 관리자 런처와 봇이 함께 종료됩니다.", flush=True)
    if not args.no_start:
        started, message = supervisor.start()
        print(f"[런처] {'OK' if started else 'ERROR'} {message}", flush=True)
    else:
        print("[런처] --no-start: 봇은 시작하지 않았습니다.", flush=True)

    if not args.no_browser:
        open_panel_later(panel_url)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n[런처] 종료 중입니다.", flush=True)
    finally:
        server.server_close()
        supervisor.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
