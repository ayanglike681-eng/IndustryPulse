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
import numpy as np
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
        """批量抓取, 带进度 + 容错(>=60交易日过滤) + 礼貌间隔(0.3s)."""
        stock_list = stock_list or self.pool
        all_data = []
        failed = []
        for i, symbol in enumerate(stock_list):
            print(f"[{i + 1}/{len(stock_list)}] Fetching {symbol}...")
            df = self.fetch_price_data(symbol, start_date, end_date)
            if not df.empty and len(df) > 60:  # 至少 60 个交易日
                all_data.append(df)
            else:
                failed.append(symbol)
            time.sleep(0.3)  # 新浪源较友好
        if failed:
            print(f"[WARN] 数据不足/失败: {failed}")
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            print(f"[OK] 成功 {result['symbol'].nunique()} 家, {len(result)} 行")
            return result
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
        # 财务 (同花顺源)
        self.fetch_financials_batch()
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

    # ---- 财务数据 (同花顺源 stock_financial_abstract_ths) ----
    @staticmethod
    def _cn_amount_to_yuan(s):
        """'8.67亿'→8.67e8, '5442.58万'→54425800, 失败→NaN."""
        if not isinstance(s, str):
            return pd.NA
        s = s.strip()
        try:
            if s.endswith("亿"):
                return float(s[:-1]) * 1e8
            if s.endswith("万"):
                return float(s[:-1]) * 1e4
            return float(s)
        except ValueError:
            return pd.NA

    def fetch_financial_ths(self, symbol: str) -> pd.DataFrame:
        """同花顺财务摘要. symbol=sz300750. 清洗: False→NaN, %→float, 亿/万→元.

        返回 [report_date, code, revenue, revenue_growth, net_profit, gross_margin, roe]
        """
        code = symbol[2:]  # sz300750 → 300750
        try:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        except Exception as e:
            print(f"[ERROR] fin {symbol}: {e}")
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "报告期": "report_date", "营业总收入": "revenue",
            "营业总收入同比增长率": "revenue_growth", "净利润": "net_profit",
            "净资产收益率": "roe", "销售毛利率": "gross_margin",
        })
        # 百分比字段: 去 % 转 float, False→NaN
        for c in ["revenue_growth", "roe", "gross_margin"]:
            if c in df.columns:
                s = df[c].astype(str).str.replace("%", "", regex=False)
                s = s.replace({"False": np.nan, "nan": np.nan})
                df[c] = pd.to_numeric(s, errors="coerce")
        # 金额字段: 亿/万 → 元
        for c in ["revenue", "net_profit"]:
            if c in df.columns:
                df[c] = df[c].map(self._cn_amount_to_yuan)
        df["code"] = symbol
        df["report_date"] = pd.to_datetime(df["report_date"])
        keep = ["report_date", "code", "revenue", "revenue_growth",
                "net_profit", "gross_margin", "roe"]
        return df[[c for c in keep if c in df.columns]]

    def fetch_financials_batch(self, stock_list: list = None) -> pd.DataFrame:
        """批量抓取财务, 带进度 + 容错 + 入库."""
        stock_list = stock_list or self.pool
        all_data = []
        failed = []
        for i, sym in enumerate(stock_list):
            print(f"[{i + 1}/{len(stock_list)}] Fin {sym}...")
            df = self.fetch_financial_ths(sym)
            if not df.empty and df["revenue_growth"].notna().any():
                all_data.append(df)
            else:
                failed.append(sym)
            time.sleep(0.3)
        if failed:
            print(f"[WARN] 财务失败/无增速: {failed}")
        if all_data:
            res = pd.concat(all_data, ignore_index=True)
            out = res.copy()
            out["report_date"] = out["report_date"].dt.strftime("%Y-%m-%d")
            self.db.upsert_df(out, "financials")
            print(f"[OK] 财务 {out['code'].nunique()} 家, {len(out)} 行入库")
            return res
        return pd.DataFrame()

    def fetch_financials(self) -> pd.DataFrame:
        """CLI 兼容入口: 批量抓取同花顺财务."""
        return self.fetch_financials_batch()
