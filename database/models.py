"""Veritabanı tablo tanımları"""

TABLES = {
    "signals": """
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument  TEXT    NOT NULL,
            timeframe   TEXT    DEFAULT '1h',
            signal      TEXT    NOT NULL,
            net_score   INTEGER DEFAULT 0,
            conf_bull   INTEGER DEFAULT 0,
            conf_bear   INTEGER DEFAULT 0,
            price       REAL    NOT NULL,
            sl          REAL,
            tp1         REAL,
            tp2         REAL,
            rr1         REAL,
            rr2         REAL,
            reasons     TEXT,
            daily_bias  TEXT,
            kill_zone   TEXT,
            news_sentiment TEXT,
            news_impact TEXT,
            commentary  TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """,

    "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id     INTEGER REFERENCES signals(id),
            instrument    TEXT    NOT NULL,
            direction     TEXT    NOT NULL,
            entry_price   REAL    NOT NULL,
            current_price REAL,
            sl            REAL    NOT NULL,
            tp1           REAL,
            tp2           REAL,
            initial_sl    REAL,
            lot_size      REAL    DEFAULT 0,
            risk_usd      REAL    DEFAULT 0,
            be_triggered  INTEGER DEFAULT 0,
            trailing_active INTEGER DEFAULT 0,
            trailing_sl   REAL,
            status        TEXT    DEFAULT 'OPEN',
            close_price   REAL,
            close_reason  TEXT,
            pnl_pips      REAL    DEFAULT 0,
            pnl_usd       REAL    DEFAULT 0,
            pnl_pct       REAL    DEFAULT 0,
            kill_zone     TEXT,
            concepts_used TEXT,
            opened_at     TEXT DEFAULT (datetime('now','localtime')),
            closed_at     TEXT,
            notes         TEXT
        )
    """,

    "capital_history": """
        CREATE TABLE IF NOT EXISTS capital_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            balance   REAL    NOT NULL,
            equity    REAL    NOT NULL,
            trade_id  INTEGER,
            event     TEXT,
            timestamp TEXT DEFAULT (datetime('now','localtime'))
        )
    """,

    "daily_performance": """
        CREATE TABLE IF NOT EXISTS daily_performance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT UNIQUE NOT NULL,
            total_trades   INTEGER DEFAULT 0,
            wins           INTEGER DEFAULT 0,
            losses         INTEGER DEFAULT 0,
            total_pnl_usd  REAL    DEFAULT 0,
            win_rate       REAL    DEFAULT 0,
            best_trade_usd REAL    DEFAULT 0,
            worst_trade_usd REAL   DEFAULT 0
        )
    """,

    "learning_log": """
        CREATE TABLE IF NOT EXISTS learning_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id        INTEGER REFERENCES trades(id),
            instrument      TEXT,
            direction       TEXT,
            kill_zone       TEXT,
            concepts        TEXT,
            tf_alignment    INTEGER DEFAULT 0,
            news_impact     TEXT,
            result          TEXT,
            pnl_usd         REAL    DEFAULT 0,
            duration_min    REAL    DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        )
    """,

    "pattern_scores": """
        CREATE TABLE IF NOT EXISTS pattern_scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_key TEXT UNIQUE NOT NULL,
            total       INTEGER DEFAULT 0,
            wins        INTEGER DEFAULT 0,
            win_rate    REAL    DEFAULT 0,
            bonus       INTEGER DEFAULT 0,
            disabled    INTEGER DEFAULT 0,
            disabled_until TEXT,
            updated_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """,

    "news": """
        CREATE TABLE IF NOT EXISTS news (
            id              TEXT PRIMARY KEY,
            title           TEXT,
            summary         TEXT,
            source          TEXT,
            url             TEXT,
            published       TEXT,
            currency        TEXT,
            impact          TEXT DEFAULT 'LOW',
            sentiment       TEXT DEFAULT 'NEUTRAL',
            sentiment_score REAL DEFAULT 0,
            fetched_at      TEXT
        )
    """,

    "watchlist": """
        CREATE TABLE IF NOT EXISTS watchlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument  TEXT NOT NULL,
            direction   TEXT,
            note        TEXT,
            target_price REAL,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """,
}
