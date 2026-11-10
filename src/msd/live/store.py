"""SQLite persistence and signal deduplication."""
from __future__ import annotations

from pathlib import Path
import sqlite3

SIGNAL_FIELDS = ("signal_key", "symbol", "setup", "side", "decision_ts", "entry_ts", "entry_price",
                 "initial_stop", "stop", "take_profit", "planned_risk", "notional", "confidence", "expected_r", "stop_loss_pct",
                 "status", "exit_ts", "planned_exit_ts", "exit_price", "realized_r", "created_at")


class SignalStore:
    def __init__(self, path: str | Path = "data/live/state.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS signals (
            signal_key TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            setup TEXT NOT NULL,
            side INTEGER NOT NULL,
            decision_ts TEXT NOT NULL,
            entry_ts TEXT,
            entry_price REAL,
            initial_stop REAL,
            stop REAL,
            take_profit REAL,
            planned_risk REAL,
            notional REAL,
            confidence REAL,
            expected_r REAL,
            stop_loss_pct REAL,
            status TEXT NOT NULL,
            exit_ts TEXT,
            planned_exit_ts TEXT,
            exit_price REAL,
            realized_r REAL,
            created_at TEXT NOT NULL
        )""")
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(signals)")}
        if "planned_exit_ts" not in columns:
            self.connection.execute("ALTER TABLE signals ADD COLUMN planned_exit_ts TEXT")
        self.connection.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.connection.commit()

    def insert(self, values: dict) -> bool:
        row = {key: values.get(key) for key in SIGNAL_FIELDS}
        placeholders = ",".join("?" for _ in SIGNAL_FIELDS)
        cursor = self.connection.execute(
            f"INSERT OR IGNORE INTO signals ({','.join(SIGNAL_FIELDS)}) VALUES ({placeholders})",
            [row[key] for key in SIGNAL_FIELDS],
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def update(self, signal_key: str, **fields) -> None:
        allowed = set(SIGNAL_FIELDS) - {"signal_key", "created_at"}
        fields = {key: value for key, value in fields.items() if key in allowed}
        if not fields:
            return
        assignments = ",".join(f"{key}=?" for key in fields)
        self.connection.execute(f"UPDATE signals SET {assignments} WHERE signal_key=?",
                                [*fields.values(), signal_key])
        self.connection.commit()

    def get(self, signal_key: str) -> dict | None:
        self.connection.row_factory = sqlite3.Row
        row = self.connection.execute("SELECT * FROM signals WHERE signal_key=?", (signal_key,)).fetchone()
        return dict(row) if row else None

    def for_date(self, day: str) -> list[dict]:
        self.connection.row_factory = sqlite3.Row
        rows = self.connection.execute("SELECT * FROM signals WHERE substr(decision_ts,1,10)=? ORDER BY decision_ts", (day,)).fetchall()
        return [dict(row) for row in rows]

    def recent(self, since: str) -> list[dict]:
        self.connection.row_factory = sqlite3.Row
        rows = self.connection.execute("SELECT * FROM signals WHERE decision_ts>=? ORDER BY decision_ts", (since,)).fetchall()
        return [dict(row) for row in rows]

    def get_state(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_state(self, key: str, value: str) -> None:
        self.connection.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                (key, value))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
