from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List


@dataclass(frozen=True)
class MarketSnapshot:
    ts: int
    exchange: str
    symbol: str
    price: float
    volume_1h: float
    open_interest_usd: float
    funding_rate_pct: float
    depth_usd: float
    spread_pct: float


class MarketStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    ts INTEGER NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume_1h REAL NOT NULL,
                    open_interest_usd REAL NOT NULL,
                    funding_rate_pct REAL NOT NULL,
                    depth_usd REAL NOT NULL,
                    spread_pct REAL NOT NULL,
                    PRIMARY KEY (ts, exchange, symbol)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_market_symbol_ts ON market_snapshots(exchange, symbol, ts)")

    def record_snapshot(self, snapshot: MarketSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_snapshots
                (ts, exchange, symbol, price, volume_1h, open_interest_usd, funding_rate_pct, depth_usd, spread_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.ts,
                    snapshot.exchange,
                    snapshot.symbol.upper(),
                    snapshot.price,
                    snapshot.volume_1h,
                    snapshot.open_interest_usd,
                    snapshot.funding_rate_pct,
                    snapshot.depth_usd,
                    snapshot.spread_pct,
                ),
            )

    def latest(self, exchange: str, symbol: str) -> Optional[MarketSnapshot]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM market_snapshots
                WHERE exchange = ? AND symbol = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (exchange, symbol.upper()),
            ).fetchone()
        return self._row_to_snapshot(row)

    def nearest_before(self, exchange: str, symbol: str, target_ts: int) -> Optional[MarketSnapshot]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM market_snapshots
                WHERE exchange = ? AND symbol = ? AND ts <= ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (exchange, symbol.upper(), target_ts),
            ).fetchone()
        return self._row_to_snapshot(row)

    def snapshots_since(self, exchange: str, symbol: str, since_ts: int, *, before_ts: int | None = None, limit: int = 24) -> List[MarketSnapshot]:
        with self._connect() as conn:
            params: list[object] = [exchange, symbol.upper(), since_ts]
            before_clause = ''
            if before_ts is not None:
                before_clause = 'AND ts <= ?'
                params.append(before_ts)
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT * FROM market_snapshots
                WHERE exchange = ? AND symbol = ? AND ts >= ? {before_clause}
                ORDER BY ts ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [s for s in (self._row_to_snapshot(row) for row in rows) if s is not None]

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row | None) -> Optional[MarketSnapshot]:
        if row is None:
            return None
        return MarketSnapshot(
            ts=int(row['ts']),
            exchange=str(row['exchange']),
            symbol=str(row['symbol']),
            price=float(row['price']),
            volume_1h=float(row['volume_1h']),
            open_interest_usd=float(row['open_interest_usd']),
            funding_rate_pct=float(row['funding_rate_pct']),
            depth_usd=float(row['depth_usd']),
            spread_pct=float(row['spread_pct']),
        )
