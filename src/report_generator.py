# -*- coding: utf-8 -*-
"""报告生成: 仪表盘 + 状态历史 + 验证报告 + 投资建议摘要."""
import os

import pandas as pd


def calculate_state_duration_stats(df_monthly: pd.DataFrame) -> dict:
    """统计各状态历史平均/最长持续时长 (半马尔可夫简化版).

    找状态切换点 → 切分 episode → 按状态聚合持续月数.
    """
    df = df_monthly.copy()
    df["state_change"] = df["state"] != df["state"].shift(1)
    df["episode_id"] = df["state_change"].cumsum()
    stats = {}
    for state in ["EXPANSION", "OVERHEAT", "CONTRACTION", "BOTTOMING"]:
        episodes = df[df["state"] == state].groupby("episode_id").size()
        if len(episodes) > 0:
            stats[state] = {
                "mean_duration": float(episodes.mean()),
                "max_duration": int(episodes.max()),
                "count": int(len(episodes)),
            }
    return stats


def generate_investment_brief(df_monthly: pd.DataFrame, stats: dict) -> str:
    """自动生成投资建议摘要 (文字分析)."""
    current = df_monthly.iloc[-1]
    state = current["state"]
    trade_date = pd.to_datetime(current["trade_date"])
    duration = df_monthly.groupby(
        (df_monthly["state"] != df_monthly["state"].shift()).cumsum()
    ).size().iloc[-1]

    brief = f"""# 新能源行业投资简报 ({trade_date.strftime('%Y-%m')})

## 当前状态：{state}

- 健康度指数：{current['health_score']:.0f} / +3
- 行业分化度(CSAD)：{current['csad']:.4f}
- 当前状态已持续：{duration} 个月

## 历史参考
- {state} 历史上平均持续 {stats.get(state, {}).get('mean_duration', 'N/A')} 个月
- 最长持续 {stats.get(state, {}).get('max_duration', 'N/A')} 个月

## 投资建议
"""
    if state == "EXPANSION":
        brief += "行业处于扩张期，趋势明确且共识强。可考虑积极配置，但关注分化度是否开始扩大（过热信号）。"
    elif state == "OVERHEAT":
        brief += "行业处于过热期，基本面仍好但分歧加大。建议控制仓位，关注估值安全边际。"
    elif state == "CONTRACTION":
        brief += "行业处于收缩期，情绪低迷。建议观望或寻找困境反转标的，等待筑底信号。"
    else:
        brief += "行业处于筑底期，情绪边际改善。可考虑左侧布局，但需确认信用环境同步宽松。"
    brief += "\n\n## 风险提示\n- 健康度基于历史分位数动态计算，勿外推至极端 regime\n- Phi 信用环境暂为占位，补真实利差后需复核\n"
    return brief


class ReportGenerator:
    """一键生成全部交付物."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def run(self, features, validation_result, args) -> dict:
        outputs = {}
        outputs["state_history"] = self.generate_state_history_csv(features, args)
        outputs["validation_report"] = self.generate_validation_report(
            validation_result, args
        )
        outputs["investment_brief"] = self.generate_investment_brief(
            features, validation_result, args
        )
        return outputs

    def generate_state_history_csv(self, features, args) -> str:
        out = f"{args.output}state_history.csv"
        features.reset_index().rename(columns={"index": "date"}).to_csv(out, index=False)
        return out

    def generate_validation_report(self, validation_result, args) -> str:
        out = f"{args.output}validation_report.md"
        lines = [
            f"# IndustryPulse 验证报告 — {args.industry}",
            "",
            "## 1. 样本外验证",
            f"- 样本内/外: {validation_result.get('out_of_sample', {})}",
            "",
            "## 2. 置换检验",
            f"- {validation_result.get('permutation', {})}",
            "",
            "## 3. 事件验证",
            f"- {validation_result.get('event', {})}",
            "",
            "## 4. 策略回测",
            f"- {validation_result.get('backtest', {})}",
            "",
            "## 结论",
            "TODO: 状态机可信度综合评价",
        ]
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return out

    def generate_investment_brief(self, features, validation_result, args) -> str:
        """自动生成投资建议摘要 (文字分析)."""
        out = f"{args.output}investment_brief.md"
        current_state = features["state"].iloc[-1] if not features.empty else "N/A"
        strategy = self.cfg["state_machine"].get(current_state, {}).get("strategy", "")
        lines = [
            f"# 投资建议摘要 — {args.industry}",
            "",
            f"## 当前状态: {current_state}",
            f"**策略建议**: {strategy}",
            "",
            "## 关键指标快照",
            "TODO: 最近一期 CSAD / Phi / 健康度分位",
            "",
            "## 半马尔可夫持续性",
            "TODO: 当前状态已持续 X 月, 转移概率",
            "",
            "## 风险提示",
            "- 样本外数据有限 (新能源 2020-2021 暴涨, 2022-2024 暴跌, 周期不对称)",
            "- 状态阈值基于 2020-2024 历史分位数, 勿外推至极端 regime",
        ]
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return out
