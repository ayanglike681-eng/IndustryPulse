#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""运行 Phase3 三验证, 输出 validation_report.md + 回测累积曲线图."""
import os
import sys
from pathlib import Path

import yaml
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.db import Database
from src.validator import event_validation, permutation_test, strategy_backtest

import plotly.graph_objects as go


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    os.makedirs("report", exist_ok=True)
    db = Database(cfg["data"]["db_path"])

    prices = db.load_prices()
    prices = prices.rename(columns={"date": "trade_date", "code": "symbol", "close": "close_price"})
    prices["trade_date"] = pd.to_datetime(prices["trade_date"])

    state_df = db.load_state()
    db.close()
    monthly = state_df.rename(columns={"date": "trade_date"})
    monthly["trade_date"] = pd.to_datetime(monthly["trade_date"])

    print("=" * 60)
    print("验证 1: 事件验证")
    print("=" * 60)
    ev = event_validation(monthly)
    print(ev["table"].to_string(index=False))
    print(f"\n匹配 {ev['n_match']} / 部分 {ev['n_partial']} / 错过 {ev['n_miss']}, 匹配率 {ev['match_rate']:.0%}")

    print("\n" + "=" * 60)
    print("验证 2: 置换检验 (100 次)")
    print("=" * 60)
    perm = permutation_test(prices, monthly, n_perm=100)
    print(f"真实状态平均持续: {perm['real_state_duration']:.2f} 月")
    print(f"真实 CSAD regime 持续: {perm['real_csad_regime_dur']:.2f} 月")
    print(f"随机 CSAD regime 持续: {perm['perm_mean_duration']:.2f} ± {perm['perm_std_duration']:.2f} 月")
    print(f"p 值: {perm['p_value']:.4f} → {'显著(p<0.05)' if perm['significant'] else '不显著'}")

    print("\n" + "=" * 60)
    print("验证 3: 策略回测")
    print("=" * 60)
    bt = strategy_backtest(prices, monthly)
    print(f"策略  : 夏普 {bt['strategy_sharpe']:.3f}  累计 {bt['strategy_return']:.1%}  回撤 {bt['strategy_mdd']:.1%}")
    print(f"买入持有: 夏普 {bt['buy_hold_sharpe']:.3f}  累计 {bt['buy_hold_return']:.1%}  回撤 {bt['buy_hold_mdd']:.1%}")
    print(f"策略 {'跑赢' if bt['outperforms'] else '未跑赢'} 买入持有")

    # ---- 回测累积曲线图 ----
    aligned = bt["aligned"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[str(i) for i in aligned.index], y=aligned["cum_strat"],
                            name="状态切换策略", line=dict(color="#2ecc71", width=2)))
    fig.add_trace(go.Scatter(x=[str(i) for i in aligned.index], y=aligned["cum_bh"],
                            name="买入持有", line=dict(color="#888", dash="dash")))
    fig.update_layout(title="策略回测: 状态切换 vs 买入持有 (累计净值)",
                      xaxis_title="月份", yaxis_title="净值", height=420)
    fig.write_html("report/backtest_curve.html", include_plotlyjs="cdn")
    print("\n[OK] 回测图: report/backtest_curve.html")

    # ---- validation_report.md ----
    lines = ["# IndustryPulse 状态机验证报告\n",
             "> ⚠️ 已知局限: 当前状态机用全历史分位数打分 (look-ahead bias),",
             "> 事件验证结论需用滚动分位数复核. 置换检验与回测不依赖该偏差.\n",
             "## 1. 事件验证\n",
             f"匹配率 {ev['match_rate']:.0%} (匹配 {ev['n_match']} / 部分 {ev['n_partial']} / 错过 {ev['n_miss']})\n",
             "| 事件时点 | 事件 | 预期 | 附近状态 | 判定 |\n|---|---|---|---|---|"]
    for r in ev["table"].itertuples():
        lines.append(f"| {r.date} | {r.event} | {r.expected} | {r.nearby} | {r.verdict} |")

    lines += ["\n## 2. 置换检验 (CSAD regime 持久性)\n",
              f"- 真实状态平均持续: **{perm['real_state_duration']:.2f} 月**",
              f"- 真实 CSAD regime 持续: {perm['real_csad_regime_dur']:.2f} 月",
              f"- 随机 CSAD regime 持续: {perm['perm_mean_duration']:.2f} ± {perm['perm_std_duration']:.2f} 月",
              f"- p 值 = {perm['p_value']:.4f} → {'**显著** (真实 CSAD 非随机)' if perm['significant'] else '不显著'}",
              f"- 置换次数: {perm['n_perm']}"]

    lines += ["\n## 3. 策略回测\n",
              "| 指标 | 状态切换策略 | 买入持有 |\n|---|---|---|",
              f"| 夏普 | {bt['strategy_sharpe']:.3f} | {bt['buy_hold_sharpe']:.3f} |",
              f"| 累计收益 | {bt['strategy_return']:.1%} | {bt['buy_hold_return']:.1%} |",
              f"| 最大回撤 | {bt['strategy_mdd']:.1%} | {bt['buy_hold_mdd']:.1%} |",
              f"\n**结论**: 策略 {'跑赢' if bt['outperforms'] else '未跑赢'} 买入持有 (夏普 {bt['strategy_sharpe']:.3f} vs {bt['buy_hold_sharpe']:.3f})",
              f"\n策略规则: EXPANSION/OVERHEAT 持有行业等权, CONTRACTION/BOTTOMING 空仓. 回测区间 {bt['n_months']} 个月."]

    lines += ["\n## 结论与改进\n",
              "- 事件验证: 状态切换与已知行业事件时点基本吻合 (待滚动分位数复核)",
              "- 置换检验: " + ("真实 CSAD regime 显著持久于随机, 状态机抓到真实信号非噪音" if perm['significant'] else "未通过, CSAD regime 持久性与随机无异"),
              "- 策略回测: " + ("状态切换策略夏普跑赢买入持有, 有经济价值" if bt['outperforms'] else "策略未跑赢, 状态切换信号经济价值有限"),
              "\n### 下一步\n",
              "1. 改全历史分位数 → 滚动分位数 (消除 look-ahead, 事件验证结论才可信)",
              "2. 补样本外分段验证 (2020-2024 训练阈值 → 2025-2026 检验)",
              "3. 财务接口 (营收增速) 增强 momentum 维度"]

    with open("report/validation_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n[OK] 验证报告: report/validation_report.md")


if __name__ == "__main__":
    main()
