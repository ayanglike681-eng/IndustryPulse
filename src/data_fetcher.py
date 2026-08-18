# -*- coding: utf-8 -*-
"""数据采集层: akshare → SQLite.

数据需求:
    个股行情  收盘价/成交量/总市值     日度
    财务数据  营收/净利润/毛利率/ROE/资本开支  季度
    信用环境  中债 AA-AAA 信用利差 (Phi 输入)  日度
    市场情绪  A股波动率指数 (VIX 代理)        日度
"""
import pandas as pd

from .db import Database


class DataFetcher:
    """数据采集封装. 复用固定股票池保证 CSAD 跨期可比."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pool = cfg["industry"]["stock_pool"]
        self.dates = cfg["data"]
        self.db = Database(self.dates["db_path"])
        self.db.init_schema()

    def run(self):
        """串联采集全流程."""
        prices = self.fetch_stock_prices()
        self.db.upsert_df(prices, "daily_prices")

        financials = self.fetch_financials()
        self.db.upsert_df(financials, "financials")

        macro = self.fetch_macro()
        self.db.upsert_df(macro, "macro_daily")
        self.db.close()

    # ---- 个股行情 ----
    def fetch_stock_prices(self) -> pd.DataFrame:
        """抓取股票池日度行情.

        TODO: akshare.stock_zh_a_hist(symbol, period='daily', start, end)
        返回: date / code / close / volume / market_cap
        """
        rows = []
        for code in self.pool:
            # TODO: akshare 调用
            # df = ak.stock_zh_a_hist(symbol=code, period="daily",
            #                         start_date=start, end_date=end, adjust="qfq")
            # 处理列名 → close/volume, market_cap 另取 stock_zh_a_spot
            pass
        return pd.DataFrame(rows, columns=["date", "code", "close", "volume", "market_cap"])

    # ---- 财务数据 ----
    def fetch_financials(self) -> pd.DataFrame:
        """抓取季度财务指标.

        TODO: akshare.stock_financial_analysis_indicator / stock_financial_report_sina
        返回: report_date / code / revenue / net_profit / gross_margin / roe / capex
        """
        rows = []
        for code in self.pool:
            # TODO: akshare 调用, 取营收/净利润/毛利率/ROE/资本开支
            pass
        return pd.DataFrame(
            rows,
            columns=["report_date", "code", "revenue", "net_profit",
                     "gross_margin", "roe", "capex"],
        )

    # ---- 宏观: 信用利差 + 波动率 ----
    def fetch_macro(self) -> pd.DataFrame:
        """抓取信用利差 (Phi) 与 VIX 代理.

        TODO:
          信用利差: ak.bond_china_yield (AA-AAA) 或 macro_china_bond
          波动率:   ak.option_finance_board / 自算 A股 30 日已实现波动率
        返回: date / credit_spread / vix
        """
        # TODO: 实现
        return pd.DataFrame(columns=["date", "credit_spread", "vix"])
