from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.config import Settings


def default_chrome_user_data_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"


def find_chrome_executable() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Google Chrome not found. Install Chrome or set CHROME_EXECUTABLE in .env."
    )


_PROFILE_EXCLUDE_DIRS = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "GrShaderCache",
    "ShaderCache",
    "Service Worker",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "BrowserMetrics",
    "Crashpad",
    "OptimizationGuidePredictionModels",
    "Safe Browsing",
    "component_crx_cache",
    "extensions_crx_cache",
    "BrowserMetrics-spare.pma",
)


def sync_chrome_user_data_for_automation(
    source_user_data_dir: Path,
    dest_user_data_dir: Path,
    profile: str,
) -> None:
    """Mirror Chrome User Data to a non-default folder for CDP automation."""
    profile_ready = (dest_user_data_dir / profile / "Preferences").exists()
    if profile_ready:
        print("Using existing automation Chrome profile.", flush=True)
        return

    if not source_user_data_dir.exists():
        raise FileNotFoundError(f"Chrome user data not found: {source_user_data_dir}")

    print("First run: copying Chrome profile (this can take a minute)...", flush=True)
    dest_user_data_dir.mkdir(parents=True, exist_ok=True)
    exclude_args = " ".join(f'/XD "{name}"' for name in _PROFILE_EXCLUDE_DIRS)
    cmd = (
        f'robocopy "{source_user_data_dir}" "{dest_user_data_dir}" /MIR '
        f"{exclude_args} /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if result.returncode >= 8:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Failed to sync Chrome profile (robocopy exit {result.returncode}). {detail}"
        )


def automation_user_data_dir(settings: Settings) -> Path:
    return settings.chrome_automation_dir


def get_effective_profile_directory(settings: Settings) -> str:
    if settings.chrome_profile_directory != "Default":
        return settings.chrome_profile_directory
    return detect_last_used_profile(settings.chrome_user_data_dir)


def detect_last_used_profile(user_data_dir: Path) -> str:
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        return "Default"

    try:
        data = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "Default"

    last_used = data.get("profile", {}).get("last_used")
    if isinstance(last_used, str) and last_used.strip():
        return last_used.strip()
    return "Default"


def is_cdp_port_ready(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_for_cdp_port(port: int, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_cdp_port_ready(port):
            return
        time.sleep(0.5)
    raise TimeoutError(f"Chrome debug port {port} did not become ready in {timeout:.0f}s")


def find_listening_pid(port: int) -> int | None:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if not parts[1].endswith(suffix):
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


def terminate_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/F", "/T"],
        capture_output=True,
        text=True,
        check=False,
    )


def release_debug_port(port: int) -> None:
    """Stop a stale automation Chrome instance blocking the debug port."""
    pid = find_listening_pid(port)
    if pid is not None:
        terminate_process_tree(pid)
        time.sleep(1)


def clear_chrome_lock_files(user_data_dir: Path) -> None:
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = user_data_dir / name
        if lock_path.exists() or lock_path.is_symlink():
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass


def close_automation_chrome(
    chrome_process: subprocess.Popen | None,
    *,
    user_data_dir: Path | None = None,
) -> None:
    """Stop only the automation Chrome process launched by this project."""
    if chrome_process is not None and chrome_process.poll() is None:
        terminate_process_tree(chrome_process.pid)
        deadline = time.time() + 20
        while time.time() < deadline:
            if chrome_process.poll() is not None:
                break
            time.sleep(0.5)
    if user_data_dir is not None:
        clear_chrome_lock_files(user_data_dir)
