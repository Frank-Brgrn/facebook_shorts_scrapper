from __future__ import annotations

import subprocess
import time
from pathlib import Path
from src.chrome_utils import (
    automation_user_data_dir,
    clear_chrome_lock_files,
    close_automation_chrome,
    find_chrome_executable,
    get_effective_profile_directory,
    is_cdp_port_ready,
    release_debug_port,
    sync_chrome_user_data_for_automation,
    wait_for_cdp_port,
)
from src.config import Settings
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


class ChromeSession:
    def __init__(
        self,
        context: BrowserContext,
        page: Page,
        playwright: Playwright,
        browser: Browser | None = None,
        chrome_process: subprocess.Popen | None = None,
        *,
        user_data_dir: Path | None = None,
    ) -> None:
        self.context = context
        self.page = page
        self._playwright = playwright
        self._browser = browser
        self._chrome_process = chrome_process
        self._user_data_dir = user_data_dir

    @classmethod
    def open(cls, settings: Settings, *, start_url: str = "https://www.facebook.com/") -> "ChromeSession":
        profile = get_effective_profile_directory(settings)
        user_data_dir = automation_user_data_dir(settings)

        print("Syncing Chrome profile for automation...", flush=True)
        sync_chrome_user_data_for_automation(
            settings.chrome_user_data_dir,
            user_data_dir,
            profile,
        )
        clear_chrome_lock_files(user_data_dir)

        port = settings.chrome_debug_port
        chrome_process: subprocess.Popen | None = None
        playwright = sync_playwright().start()
        browser: Browser | None = None

        if is_cdp_port_ready(port):
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                print("Reusing existing automation Chrome session.", flush=True)
            except Exception:
                release_debug_port(port)

        if browser is None:
            chrome_exe = find_chrome_executable()
            mode = "headless" if settings.headless else "visible"
            print(f"Launching automation Chrome ({mode}) with profile: {profile}", flush=True)

            cmd = [
                str(chrome_exe),
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                f"--profile-directory={profile}",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            if settings.headless:
                cmd.append("--headless=new")
            else:
                cmd.extend(["--start-minimized", "--window-position=-2400,-2400"])
            cmd.append(start_url)

            chrome_process = subprocess.Popen(cmd)
            wait_for_cdp_port(port)
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        if start_url not in page.url:
            print(f"Opening: {start_url}", flush=True)
            page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        cls._wait_for_facebook_login(page)

        return cls(
            context,
            page,
            playwright,
            browser=browser,
            chrome_process=chrome_process,
            user_data_dir=user_data_dir,
        )

    @staticmethod
    def _wait_for_facebook_login(page: Page, timeout: int = 300) -> None:
        if "login" not in page.url.lower():
            return

        print(
            "\nFacebook login required in the automation Chrome window.\n"
            "Log in, then return here.\n"
            "Waiting up to 5 minutes...\n",
            flush=True,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = page.url.lower()
            if "login" not in current and "facebook.com" in current:
                print("Facebook login detected.", flush=True)
                return
            time.sleep(2)

        raise RuntimeError(
            "Timed out waiting for Facebook login. "
            "Log in inside the Chrome window opened by the script, then run again."
        )

    def disconnect(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            self._playwright.stop()
        except Exception:
            pass
        close_automation_chrome(
            self._chrome_process,
            user_data_dir=self._user_data_dir,
        )

    @property
    def url(self) -> str:
        return self.page.url

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

    def evaluate(self, script: str, arg=None):
        if arg is None:
            return self.page.evaluate(script)
        return self.page.evaluate(script, arg)
