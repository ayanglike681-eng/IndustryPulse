#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""运行: 30 家抓取 → 状态机 → 状态时间轴图 + 投资简报."""
import os
import sys
import sqlite3  # noqa: F401  (保留以备扩展)
from pathlib import Path

import yaml
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data_fetcher import DataFetcher
from src.indicators import IndustryStateMachine
from src.visualizer import plot_state_timeline
from src.report_generator import calculate_state_duration_stats, generate_investment_brief


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    os.makedirs("report", exist_ok=True)

    # 复用已抓取数据; 库为空时才抓取
    db_path = cfg["data"]["db_path"]
    from src.db import Database as _DB
    need_fetch = (not os.path.exists(db_path)) or _DB(db_path).load_prices().empty

    fetcher = DataFetcher(cfg)
    if need_fetch:
        print("=" * 60)
        print("Step 1: 30 家全量抓取 (新浪源, 2020-01-01 ~ 2026-08-18)")
        print("=" * 60)
        prices = fetcher.fetch_industry_batch()
        if not prices.empty:
            out = prices.rename(columns={
                "trade_date": "date", "symbol": "code",
                "close_price": "close", "outstanding_share": "market_cap",
            })
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            fetcher.db.upsert_df(
                out[["date", "code", "close", "volume", "market_cap"]], "daily_prices"
            )
        fetcher.fetch_macro()  # Phi CSV 导入
    else:
        print("[SKIP] 库已有数据, 跳过抓取")
    fetcher.db.close()

    # 统一从库重读价格 (列名对齐状态机要求)
    _r = _DB(db_path)
    prices = _r.load_prices()
    _r.close()
    prices = prices.rename(columns={"date": "trade_date", "code": "symbol", "close": "close_price"})
    prices["trade_date"] = pd.to_datetime(prices["trade_date"])
    print(f"行情数据: {len(prices)} 行, {prices['symbol'].nunique()} 家")

    if prices.empty:
        print("[ABORT] 无行情数据")
        return

    # ---- Step 2: 状态机 ----
    print("\n" + "=" * 60)
    print("Step 2: 状态机 (CSAD + momentum + Phi → 月度健康度 → 四状态)")
    print("=" * 60)
    machine = IndustryStateMachine(cfg)
    monthly = machine.run(price_df=prices)
    print(f"月度状态数: {len(monthly)}")
    print("\n状态分布:")
    print(monthly["state"].value_counts().to_string())
    print("\n最近 6 个月:")
    print(monthly[["trade_date", "csad", "health_score", "state"]].tail(6).to_string())

    # ---- Step 3: 出图 + 简报 ----
    print("\n" + "=" * 60)
    print("Step 3: 状态时间轴图 + 投资简报")
    print("=" * 60)
    html = plot_state_timeline(monthly, "report/state_timeline.html")

    stats = calculate_state_duration_stats(monthly)
    print("\n状态持续期统计:")
    for k, v in stats.items():
        print(f"  {k}: 均值 {v['mean_duration']:.1f} 月, 最长 {v['max_duration']} 月, 出现 {v['count']} 次")

    brief = generate_investment_brief(monthly, stats)
    with open("report/investment_brief.md", "w", encoding="utf-8") as f:
        f.write(brief)
    print(f"\n[OK] 状态图:   {html}")
    print("[OK] 投资简报: report/investment_brief.md")


if __name__ == "__main__":
    main()
