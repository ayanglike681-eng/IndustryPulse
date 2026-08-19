# -*- coding: utf-8 -*-
"""SQLite 存储管理.

表结构:
    daily_prices   (date, code, close, volume, market_cap)
    financials     (report_date, code, revenue, revenue_growth, net_profit, gross_margin, roe, capex)
    macro_daily    (date, credit_spread, vix)        -- 信用利差 / 波动率
    industry_state (date, csad, phi, health_score, state)  -- 计算产物
"""
import sqlite3
from pathlib import Path

import pandas as pd


class Database:
    """SQLite 连接与读写封装."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")

    def init_schema(self):
        """建表 (若不存在) + 兼容已建表补列."""
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                date TEXT, code TEXT, close REAL,
                volume REAL, market_cap REAL,
                PRIMARY KEY (date, code)
            );
            CREATE TABLE IF NOT EXISTS financials (
                report_date TEXT, code TEXT,
                revenue REAL, revenue_growth REAL, net_profit REAL,
                gross_margin REAL, roe REAL, capex REAL,
                PRIMARY KEY (report_date, code)
            );
            CREATE TABLE IF NOT EXISTS macro_daily (
                date TEXT PRIMARY KEY,
                credit_spread REAL, vix REAL
            );
            CREATE TABLE IF NOT EXISTS industry_state (
                date TEXT PRIMARY KEY,
                csad REAL, phi REAL,
                health_score INTEGER, state TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_prices_date ON daily_prices(date);
            CREATE INDEX IF NOT EXISTS idx_prices_code ON daily_prices(code);
            """
        )
        # 兼容已建表: 旧 schema 无 revenue_growth 列, 补上
        cols = {r[1] for r in cur.execute(
            "PRAGMA table_info(financials)").fetchall()}
        if "revenue_growth" not in cols:
            cur.execute("ALTER TABLE financials ADD COLUMN revenue_growth REAL")
        self.conn.commit()

    # ---- 写入 (INSERT OR REPLACE, 处理重复键) ----
    def upsert_df(self, df: pd.DataFrame, table: str):
        if df.empty:
            return
        cols = list(df.columns)
        placeholders = ",".join(["?"] * len(cols))
        sql = (f"INSERT OR REPLACE INTO {table} "
               f"({','.join(cols)}) VALUES ({placeholders})")
        self.conn.executemany(
            sql, df.where(pd.notnull(df), None).values.tolist())
        self.conn.commit()

    # ---- 读取 ----
    def load_prices(self, start=None, end=None) -> pd.DataFrame:
        sql = "SELECT * FROM daily_prices"
        params = []
        where = []
        if start:
            where.append("date >= ?")
            params.append(start)
        if end:
            where.append("date <= ?")
            params.append(end)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date, code"
        return pd.read_sql(sql, self.conn, params=params)

    def load_financials(self) -> pd.DataFrame:
        return pd.read_sql(
            "SELECT * FROM financials ORDER BY report_date, code", self.conn)

    def load_macro(self) -> pd.DataFrame:
        return pd.read_sql(
            "SELECT * FROM macro_daily ORDER BY date", self.conn
        )

    def load_state(self) -> pd.DataFrame:
        return pd.read_sql("SELECT * FROM industry_state ORDER BY date", self.conn)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
