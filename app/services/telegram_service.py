"""Telegram notification service — async-safe wrapper."""
from __future__ import annotations
import asyncio
import threading
from typing import Optional


class TelegramService:
    def __init__(self):
        self._token: str = ""
        self._chat_id: str = ""
        self._enabled: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_loop()

    def _start_loop(self):
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def configure(self, token: str, chat_id: str, enabled: bool):
        self._token = token
        self._chat_id = chat_id
        self._enabled = enabled

    def is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, message: str):
        if not self._enabled or not self.is_configured():
            return
        asyncio.run_coroutine_threadsafe(self._async_send(message), self._loop)

    async def _async_send(self, message: str):
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception:
            try:
                import urllib.request, urllib.parse, json as _json
                data = urllib.parse.urlencode({
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }).encode()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    data=data
                )
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

    def notify_job_started(self, job_name: str, product: str, qty: int, machine: str):
        self.send(
            f"🔵 <b>Job Started</b>\n"
            f"Job: {job_name}\n"
            f"Product: {product} × {qty}\n"
            f"Machine: {machine}"
        )

    def notify_job_completed(self, job_name: str, product: str, qty: int, machine: str):
        self.send(
            f"✅ <b>Job Completed</b>\n"
            f"Job: {job_name}\n"
            f"Product: {product} × {qty}\n"
            f"Machine: {machine}"
        )

    def notify_job_failed(self, job_name: str, product: str, reason: str):
        self.send(
            f"❌ <b>Job Failed</b>\n"
            f"Job: {job_name}\n"
            f"Product: {product}\n"
            f"Reason: {reason}"
        )

    def notify_job_sheet_done(self, sheet_name: str):
        self.send(
            f"🎉 <b>Job Sheet Completed!</b>\n"
            f"All items in <b>{sheet_name}</b> are done."
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            import urllib.request, urllib.parse
            url = f"https://api.telegram.org/bot{self._token}/getMe"
            req = urllib.request.Request(url)
            urllib.request.urlopen(req, timeout=10)
            await self._async_send("✅ MYMINI3D Laser Studio connected successfully!")
            return True, "Connected"
        except Exception as e:
            return False, str(e)


telegram_service = TelegramService()
