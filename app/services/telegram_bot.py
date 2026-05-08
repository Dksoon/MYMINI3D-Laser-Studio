"""
Telegram Control Bot — control the laser from your phone.

Commands:
  /status   — machine status (online / busy / offline)
  /queue    — pending jobs across all job sheets
  /jobs     — active job sheets + progress
  /cut      — list cuttable items (then reply with item number to cut)
  /done     — mark an in-progress run as complete
  /stop     — emergency stop ALL connected machines
  /help     — list all commands

Security: only responds to the configured chat_id.
"""
from __future__ import annotations
import asyncio
import threading
import logging
from typing import Optional

log = logging.getLogger(__name__)


class TelegramControlBot:
    def __init__(self):
        self._token:   str  = ""
        self._chat_id: str  = ""
        self._enabled: bool = False
        self._loop:    Optional[asyncio.AbstractEventLoop] = None
        self._thread:  Optional[threading.Thread] = None
        self._app    = None
        self._running = False

    # ------------------------------------------------------------------ config

    def configure(self, token: str, chat_id: str, enabled: bool):
        was_running = self._running
        if was_running:
            self.stop()
        self._token   = token
        self._chat_id = chat_id
        self._enabled = enabled
        if enabled and token and chat_id:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------ start/stop

    def start(self):
        if self._running or not self._token:
            return
        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._app:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._app.stop(), self._loop
                )
            except Exception:
                pass
        self._app = None

    # ------------------------------------------------------------------ bot runner

    def _run_bot(self):
        try:
            from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            app = (
                ApplicationBuilder()
                .token(self._token)
                .build()
            )
            self._app = app

            # Register commands
            app.add_handler(CommandHandler("start",  self._cmd_start))
            app.add_handler(CommandHandler("help",   self._cmd_help))
            app.add_handler(CommandHandler("status", self._cmd_status))
            app.add_handler(CommandHandler("queue",  self._cmd_queue))
            app.add_handler(CommandHandler("jobs",   self._cmd_jobs))
            app.add_handler(CommandHandler("cut",    self._cmd_cut))
            app.add_handler(CommandHandler("done",   self._cmd_done))
            app.add_handler(CommandHandler("stop",   self._cmd_stop_machines))

            self._running = True
            self._loop.run_until_complete(
                app.run_polling(close_loop=False, stop_signals=None)
            )
        except Exception as e:
            log.error(f"Telegram bot error: {e}")
            self._running = False

    # ------------------------------------------------------------------ security

    def _auth(self, update) -> bool:
        """Only respond to the configured chat ID."""
        cid = str(update.effective_chat.id)
        return cid == str(self._chat_id)

    async def _deny(self, update):
        await update.message.reply_text("⛔ Unauthorized")

    # ------------------------------------------------------------------ commands

    async def _cmd_start(self, update, context):
        if not self._auth(update): await self._deny(update); return
        await update.message.reply_text(
            "👋 <b>MYMINI3D Laser Studio</b>\n\n"
            "Bot is connected and ready.\n"
            "Use /help to see available commands.",
            parse_mode="HTML"
        )

    async def _cmd_help(self, update, context):
        if not self._auth(update): await self._deny(update); return
        await update.message.reply_text(
            "📋 <b>Available Commands</b>\n\n"
            "/status       — Machine status\n"
            "/queue        — Pending job items\n"
            "/jobs         — Active job sheets\n"
            "/cut          — List pending items\n"
            "/cut N        — Mark item N done (1 unit)\n"
            "/cut N qty    — Mark item N done (qty units)\n"
            "/done         — List pending items (same as /cut)\n"
            "/done N       — Mark item N done\n"
            "/stop         — 🛑 Emergency stop ALL machines\n"
            "/help         — This message",
            parse_mode="HTML"
        )

    async def _cmd_status(self, update, context):
        if not self._auth(update): await self._deny(update); return
        from app.core.database import get_session, Machine, MachineStatus
        from app.core.laser_driver import machine_manager

        with get_session() as s:
            machines = s.query(Machine).order_by(Machine.id).all()

        if not machines:
            await update.message.reply_text("No machines configured.")
            return

        lines = ["🔧 <b>Machine Status</b>\n"]
        for m in machines:
            drv = machine_manager.status(m.id)
            if drv.connected and drv.busy:
                icon, stat = "🟡", f"BUSY ({drv.progress:.0f}%)"
            elif drv.connected:
                icon, stat = "🟢", "IDLE"
            else:
                icon, stat = "⚫", "OFFLINE"
            lines.append(f"{icon} <b>{m.name}</b> — {stat}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_queue(self, update, context):
        if not self._auth(update): await self._deny(update); return
        from app.core.database import get_session, JobSheet, JobSheetStatus

        with get_session() as s:
            sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status.in_([
                    JobSheetStatus.open, JobSheetStatus.in_progress
                ]))
                .all()
            )
            lines = ["📋 <b>Pending Jobs</b>\n"]
            total_pending = 0
            for sh in sheets:
                pending = [(i.product.name if i.product else "?",
                            i.quantity_pending)
                           for i in sh.items if i.quantity_pending > 0]
                if not pending:
                    continue
                lines.append(f"\n<b>{sh.name}</b>")
                for pname, qty in pending:
                    lines.append(f"  • {pname}  ×{qty}")
                    total_pending += qty

        if total_pending == 0:
            await update.message.reply_text("✅ No pending items — all jobs up to date.")
        else:
            lines.append(f"\n<i>Total pending: {total_pending} units</i>")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_jobs(self, update, context):
        if not self._auth(update): await self._deny(update); return
        from app.core.database import get_session, JobSheet, JobSheetStatus

        with get_session() as s:
            sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status.in_([
                    JobSheetStatus.open, JobSheetStatus.in_progress
                ]))
                .order_by(JobSheet.updated_at.desc())
                .all()
            )

        if not sheets:
            await update.message.reply_text("No active job sheets.")
            return

        lines = ["📂 <b>Active Job Sheets</b>\n"]
        for sh in sheets:
            pct = sh.progress_pct
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(
                f"<b>{sh.name}</b>\n"
                f"  {bar} {pct:.0f}%  "
                f"({sh.completed_items}/{sh.total_items} done)"
            )

        await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

    async def _cmd_cut(self, update, context):
        if not self._auth(update): await self._deny(update); return
        await self._pending_done_cmd(update, context)

    async def _cmd_done(self, update, context):
        if not self._auth(update): await self._deny(update); return
        await self._pending_done_cmd(update, context)

    async def _pending_done_cmd(self, update, context):
        """Shared handler for /cut and /done — list or mark pending items done."""
        from app.core.database import get_session, JobSheet, JobSheetStatus, JobItem

        args = context.args
        item_num = None
        qty = 1
        if args:
            try:
                item_num = int(args[0])
                if len(args) >= 2:
                    qty = max(1, int(args[1]))
            except (ValueError, IndexError):
                await update.message.reply_text(
                    "Usage:\n"
                    "/cut        — list pending items\n"
                    "/cut N      — mark item N done (1 unit)\n"
                    "/cut N qty  — mark item N done (qty units)"
                )
                return

        # Read all pending items in one session
        with get_session() as s:
            sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status.in_([
                    JobSheetStatus.open, JobSheetStatus.in_progress
                ]))
                .all()
            )
            items = []
            for sh in sheets:
                for item in sh.items:
                    if item.quantity_pending > 0 and item.product:
                        items.append({
                            "item_id":      item.id,
                            "product_name": item.product.name,
                            "qty_pending":  item.quantity_pending,
                            "sheet_name":   sh.name,
                        })

        # List mode
        if item_num is None:
            if not items:
                await update.message.reply_text("✅ No pending items.")
                return
            lines = ["✂️ <b>Pending Items</b>",
                     "<i>/cut N  or  /cut N qty  to mark done</i>\n"]
            for i, it in enumerate(items, 1):
                lines.append(
                    f"{i}. <b>{it['product_name']}</b>  ×{it['qty_pending']}"
                    f"  ({it['sheet_name']})"
                )
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
            return

        # Mark-done mode
        if item_num < 1 or item_num > len(items):
            await update.message.reply_text(
                f"❌ Item {item_num} not found. Use /cut to see the list."
            )
            return

        chosen     = items[item_num - 1]
        actual_qty = min(qty, chosen["qty_pending"])

        with get_session() as s:
            item = s.get(JobItem, chosen["item_id"])
            if not item:
                await update.message.reply_text("Item no longer exists.")
                return
            sheet = item.job_sheet
            item.quantity_completed += actual_qty
            sheet_done = sheet and all(i.is_done for i in sheet.items)
            if sheet_done and sheet:
                sheet.status = JobSheetStatus.completed
            elif sheet and sheet.status == JobSheetStatus.open:
                sheet.status = JobSheetStatus.in_progress
            sheet_name = sheet.name if sheet else "?"
            s.commit()

        from app.services.telegram_service import telegram_service
        telegram_service.notify_job_completed(
            sheet_name, chosen["product_name"], actual_qty, "Telegram"
        )
        if sheet_done:
            telegram_service.notify_job_sheet_done(sheet_name)

        remaining = chosen["qty_pending"] - actual_qty
        reply_lines = [
            f"✅ <b>{chosen['product_name']}</b>  ×{actual_qty} marked done."
        ]
        if remaining > 0:
            reply_lines.append(f"Remaining: ×{remaining}")
        await update.message.reply_text("\n".join(reply_lines), parse_mode="HTML")

    async def _cmd_stop_machines(self, update, context):
        if not self._auth(update): await self._deny(update); return
        from app.core.laser_driver import machine_manager

        stopped = 0
        for mid, drv in machine_manager._drivers.items():
            if drv.is_connected:
                drv.abort()
                stopped += 1

        if stopped:
            await update.message.reply_text(
                f"🛑 <b>Emergency Stop sent to {stopped} machine(s)</b>",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("No connected machines to stop.")


# Global singleton
telegram_bot = TelegramControlBot()
