"""Auto-update service — checks GitHub releases and runs the new installer."""
from __future__ import annotations
import os
import sys
import subprocess
import threading
import tempfile
from typing import Callable, Optional

from app import __version__

GITHUB_API = "https://api.github.com/repos/MYMINI3D/laser-studio/releases/latest"


def _parse_version(v: str) -> tuple:
    try:
        from packaging.version import Version
        return Version(v.lstrip("v"))
    except Exception:
        return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


class UpdateService:
    def __init__(self):
        self._update_url     = GITHUB_API
        self._auto_check     = True
        self._latest_version = ""
        self._download_url   = ""

    def configure(self, update_url: str, auto_check: bool):
        self._update_url = update_url or GITHUB_API
        self._auto_check = auto_check

    # ------------------------------------------------------------------ check

    def check_for_update(
        self,
        on_result: Optional[Callable[[bool, str, str], None]] = None
    ):
        """Non-blocking check. Calls on_result(available, latest_version, download_url)."""
        t = threading.Thread(
            target=self._check_worker, args=(on_result,), daemon=True
        )
        t.start()

    def _check_worker(self, on_result):
        try:
            import urllib.request, json
            req = urllib.request.Request(
                self._update_url,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "MYMINI3D-Laser-Studio"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())

            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                if on_result: on_result(False, __version__, "")
                return

            self._latest_version = latest_tag

            # Find .exe asset
            assets = data.get("assets", [])
            exe_url = ""
            for a in assets:
                if a.get("name", "").endswith(".exe"):
                    exe_url = a.get("browser_download_url", "")
                    break
            self._download_url = exe_url

            available = _parse_version(latest_tag) > _parse_version(__version__)
            if on_result:
                on_result(available, latest_tag, exe_url)
        except Exception as e:
            if on_result:
                on_result(False, __version__, "")

    # ------------------------------------------------------------------ download + install

    def download_and_install(
        self,
        download_url: str,
        on_progress: Optional[Callable[[int], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None
    ):
        """Download the new .exe installer and run it silently."""
        t = threading.Thread(
            target=self._download_worker,
            args=(download_url, on_progress, on_done),
            daemon=True
        )
        t.start()

    def _download_worker(self, url, on_progress, on_done):
        try:
            import urllib.request

            tmp = tempfile.NamedTemporaryFile(
                suffix="_mymini3d_update.exe", delete=False
            )
            tmp_path = tmp.name
            tmp.close()

            def _reporthook(count, block, total):
                if total > 0 and on_progress:
                    pct = min(100, int(count * block / total * 100))
                    on_progress(pct)

            urllib.request.urlretrieve(url, tmp_path, _reporthook)

            # Launch installer — /SILENT keeps settings, /NORESTART skips reboot prompt
            subprocess.Popen(
                [tmp_path, "/SILENT", "/NORESTART"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            if on_done:
                on_done(True, "Installer launched — app will restart.")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    @property
    def latest_version(self) -> str:
        return self._latest_version

    @property
    def download_url(self) -> str:
        return self._download_url


update_service = UpdateService()
