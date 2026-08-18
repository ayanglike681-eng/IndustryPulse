# -*- coding: utf-8 -*-
"""可视化仪表盘: 4 张核心图 (Plotly).

    图1  行业周期定位雷达图  (营收增速/分化度/信用环境/估值水平)
    图2  状态迁移时间轴      (EXP/OVH/CON/BOT 彩色色块)
    图3  风险热力图          (30 家公司 × 财务健康度/估值分位/...)
    图4  状态持续性分析      (半马尔可夫: 平均持续期 + 转移概率)
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class Visualizer:
    """4 张核心图 + 仪表盘组装."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def build_dashboard(self, features, validation_result, args) -> str:
        """组装单一 HTML 仪表盘."""
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                "图1 行业周期定位雷达图",
                "图2 状态迁移时间轴",
                "图3 风险热力图",
                "图4 状态持续性分析",
            ),
            specs=[
                [{"type": "scatterpolar"}, {"type": "scatter"}],
                [{"type": "heatmap"}, {"type": "bar"}],
            ],
        )
        fig.add_trace(*self.plot_radar(features).data, row=1, col=1)
        fig.add_trace(*self.plot_state_timeline(features).data, row=1, col=2)
        fig.add_trace(*self.plot_risk_heatmap(features).data, row=2, col=1)
        fig.add_trace(*self.plot_state_persistence(features).data, row=2, col=2)

        fig.update_layout(
            title=f"IndustryPulse 仪表盘 — {args.industry}",
            height=1200, showlegend=False,
        )
        out = f"{args.output}industry_pulse_{args.industry}_{args.end.replace('-', '')}.html"
        fig.write_html(out, include_plotlyjs="cdn")
        return out

    # ---- 图1 雷达图 ----
    def plot_radar(self, features) -> go.Figure:
        """行业周期定位雷达图. 当前位置红点, 历史轨迹虚线."""
        categories = ["营收增速", "分化度", "信用环境", "估值水平"]
        # TODO: 计算各维度当前分位与历史轨迹
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[0.5] * len(categories), theta=categories,
            fill="toself", name="当前",
            line=dict(color="red", width=3), marker=dict(size=10),
        ))
        return fig

    # ---- 图2 状态迁移时间轴 ----
    def plot_state_timeline(self, features) -> go.Figure:
        """状态迁移时间轴: 绿/黄/红/蓝 色块."""
        color_map = {
            "EXPANSION": "green", "OVERHEAT": "yellow",
            "CONTRACTION": "red", "BOTTOMING": "blue",
        }
        # TODO: 按 state 着色绘制时间轴
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=features.index, y=features["health_score"],
            mode="lines+markers",
            marker=dict(color=features["state"].map(color_map)),
        ))
        return fig

    # ---- 图3 风险热力图 ----
    def plot_risk_heatmap(self, features) -> go.Figure:
        """30 家公司 × (财务健康度/估值分位/营收增速/异常) 绿→黄→红."""
        # TODO: 读取个股财务 + 估值, 构造热力矩阵
        fig = go.Figure()
        fig.add_heatmap(z=[[0]], colorscale="RdYlGn")
        return fig

    # ---- 图4 状态持续性分析 (半马尔可夫) ----
    def plot_state_persistence(self, features) -> go.Figure:
        """各状态历史平均持续期 + 转移概率."""
        # TODO: 估计转移矩阵 + Weibull 停留时间
        fig = go.Figure()
        fig.add_bar(x=list(features["state"].unique()), y=[8, 6, 10, 7])  # 占位持续期
        return fig
