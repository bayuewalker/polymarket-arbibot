"""
Paper Trading System for Polymarket Arbitrage Bot
Simulates trades with virtual balance — no real funds involved.
"""
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


class PaperTrader:
    """Tracks simulated arbitrage trades with a virtual USDC balance."""

    def __init__(self, db_path: str, starting_balance: float, trade_size: float):
        self.db_path = db_path
        self.trade_size = trade_size
        self._init_db(starting_balance)

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

    def _init_db(self, starting_balance: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT NOT NULL,
                    market_id       TEXT NOT NULL,
                    market_question TEXT,
                    yes_price       REAL NOT NULL,
                    no_price        REAL NOT NULL,
                    total_cost      REAL NOT NULL,
                    trade_size_usd  REAL NOT NULL,
                    gross_profit    REAL NOT NULL,
                    profit_pct      REAL NOT NULL,
                    balance_after   REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_balance (
                    id      INTEGER PRIMARY KEY CHECK (id = 1),
                    balance REAL NOT NULL
                )
            """)
            # Insert starting balance only if table is empty
            conn.execute("""
                INSERT OR IGNORE INTO paper_balance (id, balance) VALUES (1, ?)
            """, (starting_balance,))
            conn.commit()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT balance FROM paper_balance WHERE id = 1").fetchone()
            return row[0] if row else 0.0

    def open_trade(
        self,
        market_id: str,
        market_question: str,
        yes_price: float,
        no_price: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Simulate buying YES + NO at current prices.
        Profit is locked in immediately (guaranteed at settlement).
        Returns trade record or None if insufficient balance.
        """
        balance = self.get_balance()
        total_cost_per_unit = yes_price + no_price
        # How many units can we buy with trade_size?
        units = self.trade_size / total_cost_per_unit
        cost = units * total_cost_per_unit          # = trade_size
        payout = units * 1.0                        # guaranteed $1 per unit at settlement
        gross_profit = payout - cost
        profit_pct = gross_profit / cost * 100

        if balance < cost:
            return None

        new_balance = balance + gross_profit
        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO paper_trades
                    (timestamp, market_id, market_question,
                     yes_price, no_price, total_cost,
                     trade_size_usd, gross_profit, profit_pct, balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, market_id, market_question,
                yes_price, no_price, total_cost_per_unit,
                cost, gross_profit, profit_pct, new_balance,
            ))
            conn.execute("UPDATE paper_balance SET balance = ? WHERE id = 1", (new_balance,))
            conn.commit()

        return {
            "timestamp": timestamp,
            "market_id": market_id,
            "market_question": market_question,
            "yes_price": yes_price,
            "no_price": no_price,
            "units": units,
            "cost": cost,
            "gross_profit": gross_profit,
            "profit_pct": profit_pct,
            "balance_after": new_balance,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return overall paper trading statistics."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)            AS total_trades,
                    SUM(gross_profit)   AS total_profit,
                    AVG(profit_pct)     AS avg_profit_pct,
                    MAX(profit_pct)     AS max_profit_pct,
                    MIN(profit_pct)     AS min_profit_pct,
                    SUM(trade_size_usd) AS total_volume
                FROM paper_trades
            """).fetchone()

            balance = self.get_balance()

            # Get starting balance from first trade record
            first = conn.execute(
                "SELECT balance_after - gross_profit FROM paper_trades ORDER BY id LIMIT 1"
            ).fetchone()
            starting = first[0] if first else balance

        total_trades = row[0] or 0
        total_profit = row[1] or 0.0
        return {
            "balance": balance,
            "starting_balance": starting,
            "total_profit": total_profit,
            "total_return_pct": (total_profit / starting * 100) if starting else 0.0,
            "total_trades": total_trades,
            "total_volume": row[5] or 0.0,
            "avg_profit_pct": row[2] or 0.0,
            "max_profit_pct": row[3] or 0.0,
            "min_profit_pct": row[4] or 0.0,
        }

    def get_recent_trades(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the most recent paper trades."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT timestamp, market_question, yes_price, no_price,
                       gross_profit, profit_pct, balance_after
                FROM paper_trades
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [
            {
                "timestamp": r[0],
                "market_question": r[1],
                "yes_price": r[2],
                "no_price": r[3],
                "gross_profit": r[4],
                "profit_pct": r[5],
                "balance_after": r[6],
            }
            for r in rows
        ]

    def reset(self, starting_balance: float):
        """Reset paper trading balance and wipe trade history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM paper_trades")
            conn.execute("UPDATE paper_balance SET balance = ? WHERE id = 1", (starting_balance,))
            conn.commit()
