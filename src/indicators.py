# -*- coding: utf-8 -*-
"""状态计算引擎: 原始数据 → 指标 → 状态 → 信号.

核心指标 (从 GENESIS 迁移):
    CSAD  横截面绝对离散度 → 行业分化度
    Phi   信用利差         → 信用环境指数
    VIX   波动率           → 市场情绪/流动性

综合健康度 = momentum_score + dispersion_score + credit_score  (范围 -3 ~ +3)

行业周期四状态机:
    EXPANSION   [+2, +3]  营收加速 + 分化低 + 信用宽松  → 积极投资
    OVERHEAT    [ 0, +1]  营收仍好但分化扩大 + 信用收紧  → 谨慎
    CONTRACTION [-2, -1]  营收下滑 + 分化高 + 信用紧缩  → 观望/抄底
    BOTTOMING   [-3,  0]  营收止跌 + 分化收窄 + 信用改善 → 布局
"""
import numpy as np
import pandas as pd

from .db import Database


class IndustryStateMachine:
    """行业周期状态机: 指标 → 健康度 → 四状态."""

    # 状态机定义 (与 config 对应)
    STATES = {
        "EXPANSION":  {"range": (2, 3),   "color": "green"},
        "OVERHEAT":   {"range": (0, 1),   "color": "yellow"},
        "CONTRACTION": {"range": (-2, -1), "color": "red"},
        "BOTTOMING":  {"range": (-3, 0),  "color": "blue"},
    }

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ind_cfg = cfg["indicators"]
        self.score_cfg = cfg["health_score"]
        self.sm_cfg = cfg["state_machine"]
        self.db = Database(cfg["data"]["db_path"])

    def run(self) -> pd.DataFrame:
        """串联: CSAD → Phi → momentum → health_score → state."""
        prices = self.db.load_prices()
        macro = self.db.load_macro()
        financials = self.db.load_financials()

        returns = self._compute_returns(prices)
        csad = self.calculate_csad(returns)
        phi = self.calculate_phi(macro)
        momentum = self.calculate_momentum(financials)

        features = self._align_frequency(csad, phi, momentum)
        features["health_score"] = self.calculate_health_score(features)
        features["state"] = self.classify_state(features["health_score"])

        # 状态防抖: 最小保持期平滑, 避免短期抖动
        features["state"] = self._smooth_state(
            features["state"], self.sm_cfg["semi_markov"]["min_state_hold"]
        )

        # 持久化
        self.db.upsert_df(
            features.reset_index().rename(columns={"index": "date"}), "industry_state"
        )
        self.db.close()
        return features

    # ============ 2.1 行业分化度 CSAD ============
    def calculate_csad(self, returns: pd.DataFrame) -> pd.Series:
        """横截面绝对离散度.

        CSAD_t = (1/N) * Σ |r_i,t - r_m,t|
          r_i,t = 个股 i 在 t 日收益率
          r_m,t = 行业等权平均收益率

        低 = 行业共识强 (趋势明确); 高 = 分歧大 (可能拐点)
        迁移自 GENESIS csad_calculator, 输入从 60 资产改为 N 家同业公司.
        """
        r_m = returns.mean(axis=1)                      # 行业等权平均
        csad = returns.sub(r_m, axis=0).abs().mean(axis=1)
        if self.ind_cfg["csad"]["detrend"]:
            # 去趋势: CSAD / 历史均值, 解决成分股变动导致的跨期不可比
            csad = csad / csad.rolling(252, min_periods=60).mean()
        # 滚动平滑
        csad = csad.rolling(self.ind_cfg["csad"]["window"], min_periods=1).mean()
        return csad.rename("csad")

    # ============ 2.2 信用环境指数 Phi ============
    def calculate_phi(self, macro: pd.DataFrame) -> pd.Series:
        """信用利差 = BAA_yield - AAA_yield (海外) 或 AA-AAA 利差 (国内).

        低 = 信用宽松 (PE/VC 好募资); 高 = 信用紧缩 (估值承压, 退出难)
        """
        phi = macro.set_index("date")["credit_spread"].rename("phi")
        return phi

    # ============ 营收增速动量 ============
    def calculate_momentum(self, financials: pd.DataFrame) -> pd.Series:
        """行业营收增速趋势: 加速(+1) / 减速(-1).

        季度财务 → 前向填充至日度 (混频处理).
        """
        # TODO: 按报告期聚合营收, 计算同比增速二阶导判断加速/减速
        return pd.Series(name="momentum", dtype=float)

    # ============ 2.3 综合健康度 ============
    def calculate_health_score(self, features: pd.DataFrame) -> pd.Series:
        """三维度打分 (每维 -1/0/+1), 综合 -3 ~ +3.

        momentum_score   营收加速=+1, 减速=-1
        dispersion_score CSAD 高位=-1, 低位=+1   (基于历史分位数)
        credit_score     Phi  紧缩=-1, 宽松=+1  (基于历史分位数)
        """
        sc = self.score_cfg

        dispersion_score = features["csad"].apply(
            lambda x: self._quantile_score(
                x, features["csad"], sc["dispersion_score"]["low_quantile"],
                sc["dispersion_score"]["high_quantile"], invert=True,
            )
        )
        credit_score = features["phi"].apply(
            lambda x: self._quantile_score(
                x, features["phi"], sc["credit_score"]["loose_quantile"],
                sc["credit_score"]["tight_quantile"], invert=True,
            )
        )
        # momentum 已是 +1/-1
        momentum_score = features["momentum"].fillna(0)

        return momentum_score + dispersion_score + credit_score

    @staticmethod
    def _quantile_score(value, series, low_q, high_q, invert=False):
        """分位数打分: 低于 low_q → +1, 高于 high_q → -1, 中间 → 0.

        invert=True 时方向反转 (CSAD 越高越差 → 高位得 -1).
        """
        lo = series.quantile(low_q)
        hi = series.quantile(high_q)
        if value <= lo:
            score = 1
        elif value >= hi:
            score = -1
        else:
            score = 0
        return -score if invert else score

    # ============ 2.4 状态分类 ============
    def classify_state(self, health_score: pd.Series) -> pd.Series:
        """健康度 → 四状态."""
        def _map(s):
            for name, info in self.STATES.items():
                lo, hi = info["range"]
                if lo <= s <= hi:
                    return name
            return "BOTTOMING"  # 默认
        return health_score.apply(_map).rename("state")

    # ============ 辅助: 收益率 / 频率对齐 / 状态平滑 ============
    def _compute_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        pivot = prices.pivot(index="date", columns="code", values="close")
        return pivot.pct_change()

    def _align_frequency(self, csad, phi, momentum) -> pd.DataFrame:
        """混频对齐: 日度市场指标 + 季度财务 → 月度状态判断基准.

        日度数据用于平滑, 状态以月度为单位 (config freq.state=M).
        """
        df = pd.concat([csad, phi, momentum], axis=1).sort_index()
        # 财务前向填充至日度
        df["momentum"] = df["momentum"].ffill()
        # 降频至月度 (config freq.state=M)
        df = df.resample("M").last()
        return df.dropna(subset=["csad", "phi"])

    def _smooth_state(self, state: pd.Series, min_hold: int) -> pd.Series:
        """状态防抖: 最小保持期, 消除短期抖动 (半马尔可夫记忆性体现)."""
        # TODO: 实现状态保持期平滑
        return state
