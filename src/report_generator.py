# -*- coding: utf-8 -*-
"""报告生成: 仪表盘 + 状态历史 + 验证报告 + 投资建议摘要."""
import os


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
