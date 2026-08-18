# -*- coding: utf-8 -*-
"""状态计算引擎: 价格 → CSAD/momentum/Phi → 月度健康度 → 四状态(防抖).

核心指标 (从 GENESIS 迁移):
    CSAD      横截面绝对离散度 → 行业分化度
    momentum  行业等权价格趋势加速度 (一阶+二阶导)
    Phi       信用利差         → 信用环境

综合健康度 = momentum + dispersion_score + credit_score  (范围 -3 ~ +3)

行业周期四状态机 (带最小保持期防抖, 半马尔可夫记忆性):
    EXPANSION   [+2,+3]  趋势强+分化低 → 积极投资
    OVERHEAT    [ 0,+1]  基本面好但分歧/减速 → 谨慎
    CONTRACTION [-2,-1]  下行+分化高 → 观望
    BOTTOMING   [-3, 0]  止跌+分化收窄 → 布局
"""
import numpy as np
import pandas as pd

from .db import Database


def calculate_csad(price_df: pd.DataFrame) -> pd.DataFrame:
    """CSAD 横截面绝对离散度. 输入 [symbol, trade_date, close_price].

    CSAD_t = (1/N) Σ |r_i,t - r_m,t|, r_m = 行业等权平均
    低=共识强, 高=分歧大(可能拐点)
    返回 [trade_date, csad, industry_return, num_stocks]
    """
    price_pivot = price_df.pivot(index="trade_date", columns="symbol", values="close_price")
    # 不整行 dropna (会因任一票停牌删掉整交易日, 丢月), 改用 skipna 保留停牌日
    returns = price_pivot.pct_change(fill_method=None)
    industry_return = returns.mean(axis=1, skipna=True)
    csad = returns.sub(industry_return, axis=0).abs().mean(axis=1, skipna=True)
    # 仅丢弃无效行 (如首行全 NaN)
    valid = industry_return.notna() & csad.notna()
    return pd.DataFrame({
        "trade_date": csad.index[valid],
        "csad": csad.values[valid],
        "industry_return": industry_return.values[valid],
        "num_stocks": returns.count(axis=1).values[valid],
    })


class IndustryStateMachine:
    """行业周期状态机."""

    STATES = {
        "EXPANSION":   {"color": "#2ecc71"},
        "OVERHEAT":    {"color": "#f1c40f"},
        "CONTRACTION": {"color": "#e74c3c"},
        "BOTTOMING":   {"color": "#3498db"},
    }

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.score_cfg = cfg["health_score"]
        self.sm_cfg = cfg["state_machine"]
        self.min_hold = self.sm_cfg["semi_markov"]["min_state_hold"]
        self.db = Database(cfg["data"]["db_path"])

    def run(self, price_df: pd.DataFrame = None) -> pd.DataFrame:
        """价格 → CSAD/momentum/Phi → 月度健康度 → 四状态(防抖)."""
        if price_df is None:
            prices = self.db.load_prices()
            price_df = prices.rename(
                columns={"date": "trade_date", "code": "symbol", "close": "close_price"}
            )
            price_df["trade_date"] = pd.to_datetime(price_df["trade_date"])

        # 日度 CSAD
        csad_df = calculate_csad(price_df).set_index("trade_date")
        # 日度 momentum (价格二阶导)
        momentum = self.calculate_momentum(price_df)
        # Phi (信用利差, 可缺失)
        phi = self._load_phi()

        # 合并日度
        daily = csad_df.join(momentum.rename("momentum"), how="left")
        daily = daily.join(phi.rename("phi"), how="left")
        daily["momentum"] = daily["momentum"].fillna(0)
        daily["phi"] = daily["phi"].ffill().fillna(0)

        # 月度对齐 + 分位数打分
        monthly = self.align_to_monthly(daily)

        # 综合健康度
        monthly["health_score"] = (
            monthly["momentum"] + monthly["dispersion_score"] + monthly["credit_score"]
        )
        # 四状态 (最小保持期防抖)
        monthly["state"] = self._classify_with_smoothing(monthly["health_score"])

        self._save_state(monthly)
        self.db.close()
        return monthly

    # ============ momentum: 价格趋势加速度 ============
    def calculate_momentum(self, price_df: pd.DataFrame, lookback: int = 60) -> pd.Series:
        """行业等权价格趋势加速度.

        一阶导: lookback 日收益率 (趋势方向)
        二阶导: 一阶导的变化 (加速/减速)
        打分: 强涨=+1, 强跌=-1, 震荡=0; 减速上涨=0 (过热预警)
        """
        pivot = price_df.pivot(index="trade_date", columns="symbol", values="close_price")
        industry_index = pivot.mean(axis=1)
        r1 = industry_index.pct_change(lookback)
        r2 = r1 - r1.shift(lookback)
        score = pd.Series(0.0, index=industry_index.index)
        score[r1 > 0.05] = 1
        score[r1 < -0.05] = -1
        # 减速的上涨 → 0 (动量衰减, 过热信号)
        score[(r1 > 0.05) & (r2 < -0.03)] = 0
        return score

    # ============ 混频对齐: 日度 → 月度 ============
    def align_to_monthly(self, daily: pd.DataFrame) -> pd.DataFrame:
        """日度 → 月度 (resample 不丢月) + 滚动分位数打分 (消 look-ahead).

        resample('ME').last() 自动生成所有月份索引, 不丢月;
        ffill(limit=2) 填停牌/缺失月; normalize 消 23:59:59 纳秒.
        分位数用 expanding (截至当月历史), 不用全历史, 消除样本内 look-ahead.
        """
        df = daily.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        monthly = df.resample("ME").last()      # 不丢月
        monthly = monthly.ffill(limit=2)        # 缺失月用前值, 最多连填2月
        monthly = monthly.dropna()               # 丢开头无效月
        monthly["trade_date"] = monthly.index.normalize()  # 消纳秒

        sc = self.score_cfg
        min_p = 12  # 滚动窗口最小月数, 不足则 score=0
        # CSAD 滚动分位数 (高分化=-1, 低分化=+1)
        csad_hi = monthly["csad"].expanding(min_periods=min_p).quantile(
            sc["dispersion_score"]["high_quantile"])
        csad_lo = monthly["csad"].expanding(min_periods=min_p).quantile(
            sc["dispersion_score"]["low_quantile"])
        monthly["dispersion_score"] = 0
        monthly.loc[monthly["csad"] > csad_hi, "dispersion_score"] = -1
        monthly.loc[monthly["csad"] < csad_lo, "dispersion_score"] = 1

        # Phi 滚动分位数 (紧缩=-1, 宽松=+1); 数据缺失则全 0
        monthly["credit_score"] = 0
        if monthly["phi"].abs().sum() > 0:
            phi_hi = monthly["phi"].expanding(min_periods=min_p).quantile(
                sc["credit_score"]["tight_quantile"])
            phi_lo = monthly["phi"].expanding(min_periods=min_p).quantile(
                sc["credit_score"]["loose_quantile"])
            monthly.loc[monthly["phi"] > phi_hi, "credit_score"] = -1
            monthly.loc[monthly["phi"] < phi_lo, "credit_score"] = 1
        return monthly

    # ============ 四状态 (带防抖) ============
    def _raw_state(self, h: float) -> str:
        if h >= 2:
            return "EXPANSION"
        if h >= 0:
            return "OVERHEAT"
        if h >= -2:
            return "CONTRACTION"
        return "BOTTOMING"

    def _classify_with_smoothing(self, health_score: pd.Series) -> pd.Series:
        """健康度 → 四状态, 最小保持期防抖 (半马尔可夫记忆性).

        未达最小保持期时不切换, 消除短期抖动.
        """
        states, prev, duration = [], None, 0
        for s in health_score:
            raw = self._raw_state(s)
            if prev is None:
                cur, duration = raw, 1
            elif raw != prev and duration < self.min_hold:
                cur, duration = prev, duration + 1  # 维持原状态
            else:
                cur = raw
                duration = duration + 1 if cur == prev else 1
            states.append(cur)
            prev = cur
        return pd.Series(states, index=health_score.index, name="state")

    # ============ Phi ============
    def _load_phi(self) -> pd.Series:
        try:
            macro = self.db.load_macro()
        except Exception:
            return pd.Series(dtype=float)
        if macro.empty or "credit_spread" not in macro.columns:
            return pd.Series(dtype=float)
        macro = macro.copy()
        macro["date"] = pd.to_datetime(macro["date"])
        return macro.set_index("date")["credit_spread"].astype(float)

    def _save_state(self, monthly: pd.DataFrame):
        self.db.conn.execute("DELETE FROM industry_state")
        out = monthly[["trade_date", "csad", "phi", "health_score", "state"]].copy()
        out["date"] = pd.to_datetime(out["trade_date"]).dt.strftime("%Y-%m-%d")
        out["health_score"] = out["health_score"].astype(int)
        self.db.upsert_df(
            out[["date", "csad", "phi", "health_score", "state"]], "industry_state"
        )
