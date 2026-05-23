"""
Telegram Bot Handler for Polymarket Arbitrage Bot
Controls the arbitrage scanner via Telegram commands and inline buttons.
"""
import asyncio
import logging
import threading
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from config import (
    BOT_AUTO_START,
    MAX_MARKETS_TO_MONITOR,
    STATS_INTERVAL_HOURS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

logger = logging.getLogger(__name__)


class TelegramHandler:
    """Handles all Telegram bot interactions for the arbitrage bot."""

    def __init__(self, arb_bot):
        self.arb_bot = arb_bot
        self.application = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .build()
        )
        self._arb_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._register_handlers()

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def _register_handlers(self):
        app = self.application
        app.add_handler(CommandHandler("help",        self.cmd_help))
        app.add_handler(CommandHandler("start",       self.cmd_start))
        app.add_handler(CommandHandler("stop",        self.cmd_stop))
        app.add_handler(CommandHandler("status",      self.cmd_status))
        app.add_handler(CommandHandler("stats",       self.cmd_stats))
        app.add_handler(CommandHandler("settings",    self.cmd_settings))
        app.add_handler(CommandHandler("setprofit",   self.cmd_setprofit))
        app.add_handler(CommandHandler("setinterval", self.cmd_setinterval))
        app.add_handler(CommandHandler("setmarkets",  self.cmd_setmarkets))
        app.add_handler(CommandHandler("strategy5",   self.cmd_strategy5))
        app.add_handler(CommandHandler("paper",       self.cmd_paper))
        app.add_handler(CommandHandler("reserpaper",  self.cmd_reserpaper))
        app.add_handler(CallbackQueryHandler(self.cmd_button_callback))

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    def _auth(self, update: Update) -> bool:
        return update.effective_chat.id == TELEGRAM_CHAT_ID

    # ------------------------------------------------------------------
    # Keyboard builders
    # ------------------------------------------------------------------

    def _build_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Start",     callback_data="start"),
                InlineKeyboardButton("⏹ Stop",       callback_data="stop"),
            ],
            [
                InlineKeyboardButton("📊 Status",    callback_data="status"),
                InlineKeyboardButton("📈 Stats",     callback_data="stats"),
            ],
            [
                InlineKeyboardButton("⚙️ Settings",  callback_data="settings"),
                InlineKeyboardButton("❓ Help",      callback_data="help"),
            ],
            [
                InlineKeyboardButton("💰 Profit %",  callback_data="menu_profit"),
                InlineKeyboardButton("⏱ Interval",  callback_data="menu_interval"),
            ],
            [
                InlineKeyboardButton("🏪 Markets",   callback_data="menu_markets"),
                InlineKeyboardButton("🎯 S5 ON",     callback_data="s5_on"),
                InlineKeyboardButton("🎯 S5 OFF",    callback_data="s5_off"),
            ],
            [
                InlineKeyboardButton("📝 Paper Stats", callback_data="paper"),
            ],
        ])

    def _build_profit_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1%",  callback_data="profit_1"),
                InlineKeyboardButton("2%",  callback_data="profit_2"),
                InlineKeyboardButton("5%",  callback_data="profit_5"),
                InlineKeyboardButton("10%", callback_data="profit_10"),
            ],
            [InlineKeyboardButton("← Back", callback_data="back")],
        ])

    def _build_interval_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("0.5s", callback_data="interval_05"),
                InlineKeyboardButton("1s",   callback_data="interval_1"),
                InlineKeyboardButton("2s",   callback_data="interval_2"),
                InlineKeyboardButton("5s",   callback_data="interval_5"),
            ],
            [InlineKeyboardButton("← Back", callback_data="back")],
        ])

    def _build_markets_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("10",  callback_data="markets_10"),
                InlineKeyboardButton("50",  callback_data="markets_50"),
                InlineKeyboardButton("100", callback_data="markets_100"),
                InlineKeyboardButton("200", callback_data="markets_200"),
            ],
            [InlineKeyboardButton("← Back", callback_data="back")],
        ])

    # ------------------------------------------------------------------
    # Core business logic helpers (return strings, used by both
    # /commands and button callbacks)
    # ------------------------------------------------------------------

    async def _do_start(self) -> str:
        if self.arb_bot.running or (self._arb_thread and self._arb_thread.is_alive()):
            return "Bot is already scanning. Use 📊 Status to check."
        self.arb_bot.running = True
        self.arb_bot.market_ids = []  # reset so run_threaded re-discovers
        self._arb_thread = threading.Thread(
            target=self.arb_bot.run_threaded,
            daemon=True,
            name="ArbitrageScanner",
        )
        self._arb_thread.start()
        return (
            "✅ Arbitrage scanning STARTED\n"
            f"Markets: up to {MAX_MARKETS_TO_MONITOR}\n"
            f"Interval: {self.arb_bot.scan_interval}s\n"
            f"Min profit: {self.arb_bot.min_profit_margin * 100:.1f}%"
        )

    async def _do_stop(self) -> str:
        if not self.arb_bot.running:
            return "Bot is not scanning."
        self.arb_bot.running = False
        return "⏹ Stop signal sent. Scanning halts after the current cycle."

    async def _do_status(self) -> str:
        state = "🟢 RUNNING" if self.arb_bot.running else "🔴 STOPPED"
        uptime = ""
        if self.arb_bot._start_time and self.arb_bot.running:
            delta = datetime.now() - self.arb_bot._start_time
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m = rem // 60
            uptime = f"\nUptime: {h}h {m}m"

        markets_line = f"\nMarkets monitored: {len(self.arb_bot.market_ids)}" if self.arb_bot.market_ids else ""

        stats_line = ""
        if self.arb_bot.logger:
            stats = self.arb_bot.logger.get_arbitrage_statistics(hours=24)
            stats_line = f"\nOpportunities (24h): {stats['total_opportunities']}"

        return f"Status: {state}{uptime}{markets_line}{stats_line}"

    async def _do_stats(self) -> str:
        if not self.arb_bot.logger:
            return "Data logging is disabled."
        stats = self.arb_bot.logger.get_arbitrage_statistics(hours=24)
        msg = (
            "📈 24h Statistics\n"
            f"Opportunities: {stats['total_opportunities']}\n"
            f"Avg profit: {stats['avg_profit'] * 100:.2f}%\n"
            f"Max profit: {stats['max_profit'] * 100:.2f}%\n"
            f"Unique markets: {stats['unique_markets']}"
        )
        s5 = self.arb_bot.get_strategy_5_statistics()
        if s5.get("total_positions", 0) > 0:
            msg += (
                f"\n\n🎯 Strategy 5 Positions: {s5['total_positions']}/{s5['max_positions']}\n"
                f"Total invested: ${s5['total_invested']:.4f}\n"
                f"Avg upside: {s5['avg_upside_multiplier']:.1f}x"
            )
        return msg

    async def _do_settings(self) -> str:
        bot = self.arb_bot
        return (
            "⚙️ Current Settings\n"
            f"Min profit margin: {bot.min_profit_margin * 100:.2f}%\n"
            f"Scan interval: {bot.scan_interval}s\n"
            f"Max markets: {MAX_MARKETS_TO_MONITOR}\n"
            f"Strategy 5: {'ON' if bot.strategy_5_enabled else 'OFF'}\n"
            f"Data logging: {'ON' if bot.logger else 'OFF'}\n\n"
            "Use 💰/⏱/🏪 buttons to change settings."
        )

    async def _do_help(self) -> str:
        return (
            "🤖 Polymarket Arbibot\n\n"
            "Tap the buttons below to control the bot.\n\n"
            "Text commands:\n"
            "/setprofit 0.02 — set profit margin\n"
            "/setinterval 1.0 — set scan interval\n"
            "/setmarkets 100 — set max markets\n"
            "/strategy5 on|off — toggle strategy 5\n\n"
            "All other controls are available as buttons ↓"
        )

    async def _do_paper(self) -> str:
        pt = self.arb_bot.paper_trader
        if not pt:
            return "Paper trading is disabled. Set PAPER_TRADING=true in .env"
        s = pt.get_stats()
        recent = pt.get_recent_trades(5)

        sign = "+" if s["total_profit"] >= 0 else ""
        msg = (
            "📝 Paper Trading Stats\n"
            f"Balance: ${s['balance']:.2f} (started ${s['starting_balance']:.2f})\n"
            f"Total P&L: {sign}${s['total_profit']:.4f} ({sign}{s['total_return_pct']:.2f}%)\n"
            f"Trades: {s['total_trades']} | Volume: ${s['total_volume']:.2f}\n"
            f"Avg profit/trade: {s['avg_profit_pct']:.2f}% | Best: {s['max_profit_pct']:.2f}%"
        )
        if recent:
            msg += "\n\nRecent trades:"
            for t in recent:
                ts = t["timestamp"][:16].replace("T", " ")
                q = (t["market_question"] or "")[:30]
                msg += f"\n• {ts} | +${t['gross_profit']:.4f} ({t['profit_pct']:.2f}%) | {q}"
        return msg

    async def _do_strategy5(self, arg: str) -> str:
        if arg == "on":
            self.arb_bot.strategy_5_enabled = True
            return "🎯 Strategy 5 (Long-Shot Floor Buying) ENABLED."
        else:
            self.arb_bot.strategy_5_enabled = False
            return "🎯 Strategy 5 DISABLED."

    # ------------------------------------------------------------------
    # Command handlers (thin wrappers that call _do_* helpers)
    # ------------------------------------------------------------------

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_help()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_start()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_stop()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_status()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_stats()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_settings()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_paper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        text = await self._do_paper()
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_reserpaper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        pt = self.arb_bot.paper_trader
        if not pt:
            await update.message.reply_text("Paper trading is disabled.")
            return
        from config import PAPER_BALANCE
        pt.reset(PAPER_BALANCE)
        await update.message.reply_text(
            f"📝 Paper trading reset.\nNew balance: ${PAPER_BALANCE:.2f}",
            reply_markup=self._build_keyboard()
        )

    async def cmd_strategy5(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        try:
            arg = context.args[0].lower()
            if arg not in ("on", "off"):
                raise ValueError
            text = await self._do_strategy5(arg)
        except (IndexError, ValueError):
            state = "ON" if self.arb_bot.strategy_5_enabled else "OFF"
            text = f"Strategy 5 is currently {state}.\nUsage: /strategy5 on|off"
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_setprofit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        try:
            value = float(context.args[0])
            if not (0.0 < value < 1.0):
                raise ValueError
            self.arb_bot.min_profit_margin = value
            text = f"💰 Min profit margin set to {value * 100:.2f}%"
        except (IndexError, ValueError):
            text = "Usage: /setprofit 0.02  (value between 0.0 and 1.0)"
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_setinterval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        try:
            value = float(context.args[0])
            if value < 0.1:
                raise ValueError
            self.arb_bot.scan_interval = value
            text = f"⏱ Scan interval set to {value}s"
        except (IndexError, ValueError):
            text = "Usage: /setinterval 1.0  (minimum 0.1 seconds)"
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    async def cmd_setmarkets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return
        try:
            value = int(context.args[0])
            if value < 1:
                raise ValueError
            self.arb_bot.max_markets = value
            if len(self.arb_bot.market_ids) > value:
                self.arb_bot.market_ids = self.arb_bot.market_ids[:value]
            text = (
                f"🏪 Max markets set to {value}.\n"
                f"Currently monitoring {len(self.arb_bot.market_ids)} markets.\n"
                "Use /stop then /start to rediscover with new limit."
            )
        except (IndexError, ValueError):
            text = "Usage: /setmarkets 100"
        await update.message.reply_text(text, reply_markup=self._build_keyboard())

    # ------------------------------------------------------------------
    # Inline button callback — routes all button presses
    # ------------------------------------------------------------------

    async def cmd_button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self._auth(update):
            return

        data = query.data
        text = ""
        keyboard = self._build_keyboard()

        # Sub-menus
        if data == "menu_profit":
            text = "💰 Select min profit margin:"
            keyboard = self._build_profit_keyboard()
        elif data == "menu_interval":
            text = "⏱ Select scan interval:"
            keyboard = self._build_interval_keyboard()
        elif data == "menu_markets":
            text = "🏪 Select max markets to monitor:"
            keyboard = self._build_markets_keyboard()
        elif data == "back":
            text = "Main menu:"

        # Profit presets
        elif data.startswith("profit_"):
            val = {"profit_1": 0.01, "profit_2": 0.02, "profit_5": 0.05, "profit_10": 0.10}[data]
            self.arb_bot.min_profit_margin = val
            text = f"💰 Min profit margin set to {val * 100:.0f}%"

        # Interval presets
        elif data.startswith("interval_"):
            val = {"interval_05": 0.5, "interval_1": 1.0, "interval_2": 2.0, "interval_5": 5.0}[data]
            self.arb_bot.scan_interval = val
            text = f"⏱ Scan interval set to {val}s"

        # Markets presets
        elif data.startswith("markets_"):
            val = int(data.split("_")[1])
            self.arb_bot.max_markets = val
            if len(self.arb_bot.market_ids) > val:
                self.arb_bot.market_ids = self.arb_bot.market_ids[:val]
            text = (
                f"🏪 Max markets set to {val}\n"
                "Use ⏹ Stop then ▶️ Start to rediscover with new limit."
            )

        # Strategy 5 toggles
        elif data == "s5_on":
            text = await self._do_strategy5("on")
        elif data == "s5_off":
            text = await self._do_strategy5("off")

        # Main commands
        else:
            dispatch = {
                "start":    self._do_start,
                "stop":     self._do_stop,
                "status":   self._do_status,
                "stats":    self._do_stats,
                "settings": self._do_settings,
                "help":     self._do_help,
                "paper":    self._do_paper,
            }
            fn = dispatch.get(data)
            if fn:
                text = await fn()

        if text:
            await query.edit_message_text(text=text, reply_markup=keyboard)

    # ------------------------------------------------------------------
    # Notification (called cross-thread from arb bot)
    # ------------------------------------------------------------------

    async def send_notification(self, message: str):
        """Send a message to the authorized chat. Called via run_coroutine_threadsafe."""
        await self.application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )

    # ------------------------------------------------------------------
    # Periodic stats job
    # ------------------------------------------------------------------

    async def _periodic_stats(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.arb_bot.logger:
            return
        stats = self.arb_bot.logger.get_arbitrage_statistics(hours=STATS_INTERVAL_HOURS)
        state = "🟢 RUNNING" if self.arb_bot.running else "🔴 STOPPED"
        msg = (
            f"📊 Periodic Summary (last {STATS_INTERVAL_HOURS}h)\n"
            f"Bot: {state}\n"
            f"Opportunities: {stats['total_opportunities']}\n"
            f"Avg profit: {stats['avg_profit'] * 100:.2f}%\n"
            f"Unique markets: {stats['unique_markets']}"
        )
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Start the Telegram Application (blocking, runs on main thread)."""

        async def _post_init(app):
            self._loop = asyncio.get_running_loop()
            self.arb_bot.set_callback(self.send_notification, self._loop)

            interval_secs = int(STATS_INTERVAL_HOURS * 3600)
            app.job_queue.run_repeating(
                self._periodic_stats,
                interval=interval_secs,
                first=interval_secs,
                name="periodic_stats",
            )

            if BOT_AUTO_START:
                self.arb_bot.running = True
                self._arb_thread = threading.Thread(
                    target=self.arb_bot.run_threaded,
                    daemon=True,
                    name="ArbitrageScanner",
                )
                self._arb_thread.start()
                await app.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text="🤖 Bot started automatically (BOT_AUTO_START=true). Send /status to check.",
                )
            else:
                await app.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text="🤖 Polymarket Arbibot is online!\nSend /help or tap a button to get started.",
                    reply_markup=self._build_keyboard(),
                )

        self.application.post_init = _post_init
        self.application.run_polling(drop_pending_updates=True)
