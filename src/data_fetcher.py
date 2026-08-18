# -*- coding: utf-8 -*-
"""数据采集层: akshare 新浪源 → SQLite.

数据源: ak.stock_zh_a_daily (新浪)
  原因: 东财源 (stock_zh_a_hist / stock_board_industry_cons_em) 在沙箱环境被
        反爬/地域拦截 (http=000), 新浪源已验证可用且含收盘价/成交量/流通股本.
  symbol 格式: sz300750 / sh600519 (固定股票池, 保证 CSAD 跨期可比)

数据需求:
    个股行情  收盘价/成交量/流通股本   日度  ← 新浪源
    信用环境  BAA-AAA 信用利差 (Phi)   日度  ← 手动 CSV (FRED/中债)
    财务数据  营收/净利润/ROE/资本开支  季度  ← 稍后换源探测
"""
import time
import pandas as pd
import akshare as ak

from .db import Database


class DataFetcher:
    """新浪源数据采集. 固定股票池保证 CSAD 跨期可比."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pool = cfg["industry"]["stock_pool"]
        self.db_path = cfg["data"]["db_path"]
        self.start = cfg["data"]["start_date"]
        self.end = cfg["data"]["end_date"]
        self.db = Database(self.db_path)
        self.db.init_schema()

    # ---- 个股行情 (新浪源) ----
    def fetch_price_data(self, symbol: str, start_date: str = None,
                         end_date: str = None) -> pd.DataFrame:
        """新浪源单股日度行情.

        symbol: sz300750 / sh600519
        返回: [symbol, trade_date, close_price, volume, outstanding_share]
        """
        start_date = start_date or self.start
        end_date = end_date or self.end
        try:
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            df["date"] = pd.to_datetime(df["date"])
            mask = (df["date"] >= start_date) & (df["date"] <= end_date)
            df = df.loc[mask].copy()
            df = df.rename(columns={
                "date": "trade_date",
                "close": "close_price",
                "outstanding_share": "outstanding_share",
            })
            df["symbol"] = symbol
            return df[["symbol", "trade_date", "close_price",
                       "volume", "outstanding_share"]]
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")
            return pd.DataFrame()

    def fetch_industry_batch(self, stock_list: list = None,
                             start_date: str = None,
                             end_date: str = None) -> pd.DataFrame:
        """批量抓取, 带进度 + 容错 + 礼貌间隔(0.5s)."""
        stock_list = stock_list or self.pool
        all_data = []
        for i, symbol in enumerate(stock_list):
            print(f"Fetching {symbol} ({i + 1}/{len(stock_list)})...")
            df = self.fetch_price_data(symbol, start_date, end_date)
            if not df.empty:
                all_data.append(df)
            time.sleep(0.5)  # 礼貌间隔, 避免被封
        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

    def run(self):
        """CLI 调用: 抓固定股票池 + 入库 SQLite."""
        prices = self.fetch_industry_batch()
        if not prices.empty:
            # 映射至 daily_prices 表结构 (date/code/close/volume/market_cap)
            out = prices.rename(columns={
                "trade_date": "date", "symbol": "code",
                "close_price": "close", "outstanding_share": "market_cap",
            })
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            self.db.upsert_df(out[["date", "code", "close", "volume", "market_cap"]],
                              "daily_prices")
        # Phi (CSV 导入)
        self.fetch_macro()
        self.db.close()
        return prices

    # ---- Phi 信用利差 (手动 CSV 导入) ----
    def load_phi_data(self, csv_path: str = "data/credit_spread.csv") -> pd.DataFrame:
        """手动导入信用利差 CSV (FRED BAA-AAA 或中债 AA-国债).

        CSV 列: trade_date, baa_yield, aaa_yield  (phi 自动算 = baa - aaa)
        数据来源: 美联储 FRED 或中债估值中心, 手动下载 2020 至今日度/月度.
        找不到 BAA-AAA 时, 用 中债 AA 企业债 - 国债收益率 替代.
        """
        try:
            df = pd.read_csv(csv_path, parse_dates=["trade_date"])
            if "phi" not in df.columns:
                df["phi"] = df["baa_yield"] - df["aaa_yield"]
            return df[["trade_date", "phi"]]
        except Exception as e:
            print(f"[WARN] load_phi_data 失败 ({csv_path}): {e}")
            return pd.DataFrame(columns=["trade_date", "phi"])

    # ---- 宏观: Phi 入库 ----
    def fetch_macro(self) -> pd.DataFrame:
        """Phi 信用利差从 CSV 导入并入库 macro_daily."""
        phi = self.load_phi_data()
        if not phi.empty:
            out = phi.rename(columns={"trade_date": "date"})
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            out["vix"] = None  # TODO: A股波动率代理
            self.db.upsert_df(out[["date", "phi", "vix"]].rename(
                columns={"phi": "credit_spread"}), "macro_daily")
        return pd.DataFrame(columns=["date", "credit_spread", "vix"])

    # ---- 财务数据 (稍后换源) ----
    def fetch_financials(self) -> pd.DataFrame:
        """季度财务. TODO: 新浪/同花顺源探测 (东财源不可用)."""
        return pd.DataFrame(columns=["report_date", "code", "revenue",
                                     "net_profit", "gross_margin", "roe", "capex"])
