# -*- coding: utf-8 -*-
"""可视化: 状态迁移时间轴 (Plotly)."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 状态配色 (绿/黄/红/蓝)
STATE_COLORS = {
    "EXPANSION": "#2ecc71",
    "OVERHEAT": "#f1c40f",
    "CONTRACTION": "#e74c3c",
    "BOTTOMING": "#3498db",
}


def plot_state_timeline(df_monthly: pd.DataFrame, output_path: str) -> str:
    """状态迁移时间轴 + 健康度/CSAD 曲线.

    上图: 每月状态色块 (EXP/OVH/CON/BOT)
    下图: 健康度指数(左轴) + CSAD 分化度(右轴)
    """
    df = df_monthly.copy()
    if "trade_date" not in df.columns:
        df["trade_date"] = df.index.to_timestamp(how="end")
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.3, 0.7],
        subplot_titles=("行业周期状态", "健康度指数 与 CSAD 分化度"),
        vertical_spacing=0.08,
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]],
    )

    # 上: 状态色块 (每月一段粗线)
    for _, row in df.iterrows():
        st = row["state"]
        x0 = row["trade_date"]
        x1 = x0 + pd.Timedelta(days=25)
        fig.add_trace(
            go.Scatter(
                x=[x0, x1], y=[1, 1], mode="lines",
                line=dict(color=STATE_COLORS.get(st, "gray"), width=20),
                showlegend=False, hoverinfo="text",
                text=f"{st} | 健康度 {row['health_score']:.0f} | {x0.strftime('%Y-%m')}",
            ),
            row=1, col=1,
        )

    # 下左: 健康度
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=df["health_score"], mode="lines+markers",
            name="健康度", line=dict(color="black", width=2),
        ),
        row=2, col=1, secondary_y=False,
    )
    # 下右: CSAD
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"], y=df["csad"], mode="lines", name="CSAD(分化度)",
            line=dict(color="orange", width=1.5),
        ),
        row=2, col=1, secondary_y=True,
    )

    fig.update_layout(
        title="新能源行业景气度与周期状态 (2020-2026)",
        height=620, hovermode="x unified",
        showlegend=True,
    )
    fig.update_yaxes(title_text="状态", row=1, col=1, showticklabels=False, range=[0.5, 1.5])
    fig.update_yaxes(title_text="健康度", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="CSAD", row=2, col=1, secondary_y=True)

    fig.write_html(output_path, include_plotlyjs="cdn")
    print(f"[OK] 状态时间轴已保存: {output_path}")
    return output_path


class Visualizer:
    """仪表盘组装 (CLI 兼容)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def plot_state_timeline(self, df_monthly, output_path):
        return plot_state_timeline(df_monthly, output_path)

    def build_dashboard(self, features, validation_result, args) -> str:
        out = f"{args.output}industry_pulse_{args.industry}_{args.end.replace('-', '')}.html"
        return plot_state_timeline(features, out)
