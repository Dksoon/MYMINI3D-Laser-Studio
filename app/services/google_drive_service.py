"""Google Drive sync service — syncs the local library folder to a Drive folder."""
from __future__ import annotations
import os
import json
import threading
from pathlib import Path
from typing import Callable, Optional

from app.core.config import get_app_data_dir, get_library_dir

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = get_app_data_dir() / "gdrive_token.json"


def _get_creds(credentials_path: str):
    """Load or refresh OAuth2 credentials. Returns None if unavailable."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_path or not Path(credentials_path).exists():
                    return None, "credentials.json not found"
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

        return creds, None
    except ImportError:
        return None, "google-api-python-client not installed"
    except Exception as e:
        return None, str(e)


def _build_service(creds):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds)


class GoogleDriveService:
    def __init__(self):
        self._enabled          = False
        self._credentials_path = ""
        self._folder_id        = ""
        self._last_error       = ""

    def configure(self, enabled: bool, credentials_path: str, folder_id: str):
        self._enabled          = enabled
        self._credentials_path = credentials_path
        self._folder_id        = folder_id

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def last_error(self) -> str:
        return self._last_error

    # ------------------------------------------------------------------ auth

    def authenticate(self) -> tuple[bool, str]:
        """Run OAuth2 flow. Opens browser for user consent."""
        creds, err = _get_creds(self._credentials_path)
        if err:
            self._last_error = err
            return False, err
        return True, "Authenticated"

    def is_authenticated(self) -> bool:
        return TOKEN_FILE.exists()

    def revoke(self):
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink(missing_ok=True)

    # ------------------------------------------------------------------ sync

    def sync_library(
        self,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ):
        """Upload all files in the library folder to the configured Drive folder."""
        t = threading.Thread(
            target=self._sync_worker,
            args=(on_progress, on_done),
            daemon=True
        )
        t.start()

    def _sync_worker(self, on_progress, on_done):
        try:
            creds, err = _get_creds(self._credentials_path)
            if err:
                if on_done:
                    on_done(False, err)
                return

            service = _build_service(creds)
            lib_dir = get_library_dir()
            files   = list(lib_dir.iterdir())
            total   = len(files)

            # Get existing files in the Drive folder to avoid duplicates
            existing = self._list_drive_files(service)

            for i, fpath in enumerate(files):
                if not fpath.is_file():
                    continue
                if on_progress:
                    on_progress(fpath.name, i + 1, total)

                if fpath.name in existing:
                    self._update_file(service, existing[fpath.name], fpath)
                else:
                    self._upload_file(service, fpath)

            if on_done:
                on_done(True, f"Synced {total} file(s)")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def _list_drive_files(self, service) -> dict[str, str]:
        """Returns {filename: file_id} for files in the target folder."""
        if not self._folder_id:
            return {}
        results = service.files().list(
            q=f"'{self._folder_id}' in parents and trashed=false",
            fields="files(id,name)"
        ).execute()
        return {f["name"]: f["id"] for f in results.get("files", [])}

    def _upload_file(self, service, fpath: Path):
        from googleapiclient.http import MediaFileUpload
        meta = {"name": fpath.name}
        if self._folder_id:
            meta["parents"] = [self._folder_id]
        media = MediaFileUpload(str(fpath))
        service.files().create(body=meta, media_body=media, fields="id").execute()

    def _update_file(self, service, file_id: str, fpath: Path):
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(fpath))
        service.files().update(
            fileId=file_id, media_body=media
        ).execute()

    # ------------------------------------------------------------------ download

    def download_library(
        self,
        on_done: Optional[Callable[[bool, str], None]] = None
    ):
        """Download all SVG/DXF files from the Drive folder into the library."""
        t = threading.Thread(
            target=self._download_worker,
            args=(on_done,),
            daemon=True
        )
        t.start()

    def _download_worker(self, on_done):
        try:
            creds, err = _get_creds(self._credentials_path)
            if err:
                if on_done: on_done(False, err)
                return
            service  = _build_service(creds)
            lib_dir  = get_library_dir()
            existing = self._list_drive_files(service)
            count    = 0
            for name, fid in existing.items():
                if not name.lower().endswith((".svg", ".dxf")):
                    continue
                dest = lib_dir / name
                from googleapiclient.http import MediaIoBaseDownload
                import io
                req  = service.files().get_media(fileId=fid)
                buf  = io.BytesIO()
                dl   = MediaIoBaseDownload(buf, req)
                done = False
                while not done:
                    _, done = dl.next_chunk()
                dest.write_bytes(buf.getvalue())
                count += 1
            if on_done:
                on_done(True, f"Downloaded {count} file(s)")
        except Exception as e:
            if on_done:
                on_done(False, str(e))


gdrive_service = GoogleDriveService()
