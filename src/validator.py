# -*- coding: utf-8 -*-
"""状态验证与信号质量: 多方法证据评级 (GENESIS V9.0 迁移).

解决"状态机是否事后诸葛亮"问题:
    事件验证   已知行业事件 ↔ 状态切换     切换领先/同步于事件
    置换检验   打乱收益率重算 CSAD          真实 CSAD regime 显著持久
    策略回测   扩张持有/收缩空仓            夏普 > 买入持有

⚠️ 已知局限: 当前状态机用全历史分位数打分 (look-ahead bias),
   事件验证结论需用滚动分位数复核. 本报告如实标注.
"""
import numpy as np
import pandas as pd

from .indicators import calculate_csad

# 新能源行业 2020-2026 关键事件
EVENTS = [
    {"date": "2021-09", "event": "宁德时代见顶, 新能源泡沫破裂", "expected": "OVH->CON"},
    {"date": "2022-04", "event": "上海疫情, 供应链中断", "expected": "CON"},
    {"date": "2022-11", "event": "疫情放开, 市场反弹", "expected": "CON->OVH"},
    {"date": "2023-04", "event": "光伏产能过剩暴露", "expected": "OVH->CON"},
    {"date": "2024-01", "event": "碳酸锂价格暴跌", "expected": "CON"},
    {"date": "2025-11", "event": "模型 EXPANSION (待样本外验证)", "expected": "EXP?"},
]

STATE_ABBR = {
    "EXPANSION": "EXP", "OVERHEAT": "OVH",
    "CONTRACTION": "CON", "BOTTOMING": "BOT",
}


def _state_durations(states) -> list:
    """状态序列 → 各 episode 持续长度 (月)."""
    if not states:
        return []
    durs, cur, c = [], states[0], 1
    for s in states[1:]:
        if s == cur:
            c += 1
        else:
            durs.append(c)
            cur, c = s, 1
    durs.append(c)
    return durs


# ============ 事件验证 ============
def event_validation(monthly: pd.DataFrame) -> dict:
    """关键事件 ↔ 状态切换. 检查事件 ±2 月状态是否匹配预期."""
    df = monthly.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["ym"] = df["trade_date"].dt.to_period("M")
    df = df.sort_values("ym")

    rows = []
    for ev in EVENTS:
        ev_ym = pd.Period(ev["date"], freq="M")
        nearby = df[(df["ym"] >= ev_ym - 2) & (df["ym"] <= ev_ym + 2)]
        abbr = [STATE_ABBR[s] for s in nearby["state"].tolist()]
        nearby_str = " ".join(f"{r.ym}-{STATE_ABBR[r.state]}" for r in nearby.itertuples())

        exp = ev["expected"]
        if exp.endswith("?"):
            verdict = "PENDING"
        elif "->" in exp:
            frm, to = exp.split("->")
            if frm in abbr and to in abbr and abbr.index(frm) <= abbr.index(to):
                verdict = "MATCH"
            elif to in abbr:
                verdict = "PARTIAL"
            else:
                verdict = "MISS"
        else:
            verdict = "MATCH" if exp in abbr else "PARTIAL"

        rows.append({
            "date": ev["date"], "event": ev["event"],
            "expected": exp, "nearby": nearby_str, "verdict": verdict,
        })

    results = pd.DataFrame(rows)
    match_rate = (results["verdict"] == "MATCH").sum() / len(results)
    return {"table": results, "match_rate": match_rate,
            "n_match": (results["verdict"] == "MATCH").sum(),
            "n_partial": (results["verdict"] == "PARTIAL").sum(),
            "n_miss": (results["verdict"] == "MISS").sum()}


# ============ 置换检验 ============
def permutation_test(prices: pd.DataFrame, monthly: pd.DataFrame,
                     n_perm: int = 100) -> dict:
    """打乱个股收益率重算 CSAD, 检验真实 CSAD regime 是否显著持久.

    通过标准: 真实 regime 平均持续时长 显著 > 随机 (p < 0.05).
    """
    rng = np.random.default_rng(42)
    # 真实状态持续
    real_durs = _state_durations(monthly.sort_values("trade_date")["state"].tolist())
    real_mean = float(np.mean(real_durs)) if real_durs else 0.0

    pivot = prices.pivot(index="trade_date", columns="symbol", values="close_price")
    pivot.index = pd.to_datetime(pivot.index)
    rets = pivot.pct_change(fill_method=None).dropna()

    # 真实 csad 二态 regime (高中位数=HIGH) 的平均持续, 作为同口径基线
    real_csad = calculate_csad(prices).set_index("trade_date")["csad"]
    real_regime = (real_csad > real_csad.median()).astype(int).tolist()
    real_regime_dur = float(np.mean(_state_durations(real_regime))) if real_regime else 0

    perm_durs = []
    for _ in range(n_perm):
        shuf = rets.copy()
        for col in shuf.columns:
            shuf[col] = rng.permutation(shuf[col].values)
        ind = shuf.mean(axis=1)
        csad_p = shuf.sub(ind, axis=0).abs().mean(axis=1)
        regime = (csad_p > csad_p.median()).astype(int).tolist()
        perm_durs.append(float(np.mean(_state_durations(regime))) if regime else 0)

    perm_arr = np.array(perm_durs)
    # 单尾: 真实是否显著大于随机
    p_value = float(np.mean(perm_arr >= real_regime_dur))
    return {
        "real_state_duration": real_mean,
        "real_csad_regime_dur": real_regime_dur,
        "perm_mean_duration": float(perm_arr.mean()),
        "perm_std_duration": float(perm_arr.std()),
        "p_value": p_value,
        "n_perm": n_perm,
        "significant": p_value < 0.05,
    }


# ============ 策略回测 ============
def strategy_backtest(prices: pd.DataFrame, monthly: pd.DataFrame) -> dict:
    """扩张/过热期持有行业等权, 收缩/筑底期空仓. 对比买入持有."""
    pivot = prices.pivot(index="trade_date", columns="symbol", values="close_price")
    pivot.index = pd.to_datetime(pivot.index)
    industry_idx = pivot.mean(axis=1)

    month_end = industry_idx.resample("ME").last()
    ret = month_end.pct_change().dropna()
    ret.index = ret.index.to_period("M")

    m = monthly.copy()
    m["trade_date"] = pd.to_datetime(m["trade_date"])
    m["ym"] = m["trade_date"].dt.to_period("M")
    m = m.sort_values("ym").drop_duplicates("ym").set_index("ym")

    aligned = m[["state"]].join(pd.DataFrame({"ret": ret}))
    aligned["ret"] = aligned["ret"].fillna(0.0)
    # 持有: EXPANSION / OVERHEAT; 空仓: CONTRACTION / BOTTOMING
    hold = aligned["state"].isin(["EXPANSION", "OVERHEAT"])
    aligned["strat"] = aligned["ret"].where(hold, 0.0)

    aligned["cum_strat"] = (1 + aligned["strat"]).cumprod()
    aligned["cum_bh"] = (1 + aligned["ret"]).cumprod()

    def _sharpe(s):
        s = s.dropna()
        if s.std() == 0:
            return 0.0
        return float(s.mean() / s.std() * np.sqrt(12))

    def _mdd(cum):
        return float((cum / cum.cummax() - 1).min())

    return {
        "strategy_sharpe": _sharpe(aligned["strat"]),
        "buy_hold_sharpe": _sharpe(aligned["ret"]),
        "strategy_return": float(aligned["cum_strat"].iloc[-1] - 1),
        "buy_hold_return": float(aligned["cum_bh"].iloc[-1] - 1),
        "strategy_mdd": _mdd(aligned["cum_strat"]),
        "buy_hold_mdd": _mdd(aligned["cum_bh"]),
        "n_months": len(aligned),
        "outperforms": _sharpe(aligned["strat"]) > _sharpe(aligned["ret"]),
        "aligned": aligned,
    }


class Validator:
    """多方法验证框架 (CLI 兼容)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def run(self, prices: pd.DataFrame, monthly: pd.DataFrame) -> dict:
        return {
            "event": event_validation(monthly),
            "permutation": permutation_test(prices, monthly, n_perm=100),
            "backtest": strategy_backtest(prices, monthly),
        }
