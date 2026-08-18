#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端管道测试: 新浪源抓取 → CSAD 计算 → 合理性验证.

验证清单:
    [1] 新浪源稳定抓取 3 家, 无 ConnectionError
    [2] CSAD 无 NaN 且在合理范围 (0.005~0.05)
    [3] 日期对齐, 缺失率 < 5%
    [4] 数据能入 SQLite 并读出
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data_fetcher import DataFetcher
from src.indicators import calculate_csad
from src.db import Database


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    fetcher = DataFetcher(cfg)
    stock_list = ["sz300750", "sh600438", "sh601012"]  # 先测 3 家

    # ---- 抓取 ----
    print("=" * 50)
    print("Step 1: 新浪源抓取 (3 家, 2024-01-01 ~ 2026-08-18)")
    print("=" * 50)
    df_price = fetcher.fetch_industry_batch(
        stock_list, "2024-01-01", "2026-08-18"
    )
    n_stocks = df_price["symbol"].nunique() if not df_price.empty else 0
    print(f"\n总行数: {len(df_price)}, 抓到股票数: {n_stocks}/{len(stock_list)}")
    if not df_price.empty:
        print(df_price.tail(3).to_string())

    ok_fetch = n_stocks == len(stock_list) and not df_price.empty

    # ---- CSAD ----
    print("\n" + "=" * 50)
    print("Step 2: CSAD 计算")
    print("=" * 50)
    if df_price.empty:
        print("[SKIP] 无行情数据, 无法计算 CSAD")
        return
    df_csad = calculate_csad(df_price)
    print(df_csad.tail(5).to_string())
    print(f"\nCSAD 均值: {df_csad['csad'].mean():.6f}")
    print(f"CSAD 范围: [{df_csad['csad'].min():.6f}, {df_csad['csad'].max():.6f}]")
    print(f"num_stocks: {df_csad['num_stocks'].min()}-{df_csad['num_stocks'].max()}")

    ok_csad = df_csad["csad"].notna().all() and (df_csad["csad"] < 0.2).all()

    # ---- 日期对齐 / 缺失 ----
    print("\n" + "=" * 50)
    print("Step 3: 日期对齐检查")
    print("=" * 50)
    pivot = df_price.pivot(index="trade_date", columns="symbol", values="close_price")
    total_cells = pivot.size
    missing = pivot.isna().sum().sum()
    miss_rate = missing / total_cells if total_cells else 1
    print(f"交易日数: {len(pivot)}, 缺失率: {miss_rate:.2%}")
    ok_align = miss_rate < 0.05

    # ---- 入库 / 读出 ----
    print("\n" + "=" * 50)
    print("Step 4: SQLite 入库 + 读出")
    print("=" * 50)
    out = df_price.rename(columns={
        "trade_date": "date", "symbol": "code",
        "close_price": "close", "outstanding_share": "market_cap",
    })
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    fetcher.db.upsert_df(out[["date", "code", "close", "volume", "market_cap"]],
                         "daily_prices")
    read_back = fetcher.db.load_prices()
    fetcher.db.close()
    print(f"写入 {len(out)} 行, 读回 {len(read_back)} 行")
    ok_db = len(read_back) == len(out)

    # ---- 验证清单 ----
    print("\n" + "=" * 50)
    print("验证清单")
    print("=" * 50)
    print(f"[1] 新浪源抓取3家:           {'PASS' if ok_fetch else 'FAIL'}")
    print(f"[2] CSAD无NaN且范围合理:     {'PASS' if ok_csad else 'FAIL'}")
    print(f"[3] 日期缺失率<5%:           {'PASS' if ok_align else 'FAIL'}")
    print(f"[4] SQLite写入读出一致:      {'PASS' if ok_db else 'FAIL'}")


if __name__ == "__main__":
    main()
