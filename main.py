"""
Polymarket Arbitrage Bot — Main Entry Point

Starts Telegram control bot (main thread) + arbitrage scanner (background thread).

Usage:
    python main.py

Setup:
    Copy '.env copy.example' to '.env' and fill in:
    - TELEGRAM_BOT_TOKEN   (from @BotFather)
    - TELEGRAM_CHAT_ID     (your numeric ID from @userinfobot)
    - PRIVATE_KEY          (optional, for actual trading)
"""
import logging
import sys


def main():
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    if not TELEGRAM_BOT_TOKEN:
        print("[✗] TELEGRAM_BOT_TOKEN not set in .env")
        print("    Get one from @BotFather on Telegram.")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        print("[✗] TELEGRAM_CHAT_ID not set in .env")
        print("    Get your numeric ID from @userinfobot on Telegram.")
        sys.exit(1)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.WARNING,
    )

    from bot import PolyArbitrageBot
    from telegram_handler import TelegramHandler

    print("=" * 60)
    print("Polymarket Arbitrage Bot — Telegram Edition")
    print("=" * 60)
    print(f"Authorized chat ID : {TELEGRAM_CHAT_ID}")
    print("Send /help in Telegram to see available commands.")
    print("-" * 60)

    arb_bot = PolyArbitrageBot()
    handler = TelegramHandler(arb_bot)
    handler.run()


if __name__ == "__main__":
    main()
