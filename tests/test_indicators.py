# -*- coding: utf-8 -*-
"""indicators 模块单元测试骨架."""
import numpy as np
import pandas as pd
import pytest

from src.indicators import IndustryStateMachine


@pytest.fixture
def machine():
    cfg = {
        "data": {"db_path": ":memory:"},
        "indicators": {
            "csad": {"window": 5, "detrend": False},
            "phi": {"source": "credit_spread"},
            "vix": {"proxy": "ivix"},
        },
        "health_score": {
            "momentum_score": {"accel": 1, "decel": -1},
            "dispersion_score": {"high_quantile": 0.8, "low_quantile": 0.2},
            "credit_score": {"tight_quantile": 0.8, "loose_quantile": 0.2},
        },
        "state_machine": {
            "EXPANSION": {"score_range": [2, 3], "strategy": ""},
            "OVERHEAT": {"score_range": [0, 1], "strategy": ""},
            "CONTRACTION": {"score_range": [-2, -1], "strategy": ""},
            "BOTTOMING": {"score_range": [-3, 0], "strategy": ""},
            "semi_markov": {"duration_model": "weibull", "min_state_hold": 3},
        },
    }
    return IndustryStateMachine(cfg)


def test_csad_low_when_stocks_move_together(machine):
    """同涨同跌 → CSAD 低."""
    n_days, n_stocks = 30, 10
    common_shock = np.random.normal(0.01, 0.01, n_days)
    # 全行业同向 (共识强) → CSAD 应很低
    returns = pd.DataFrame(
        np.tile(common_shock.reshape(-1, 1), (1, n_stocks))
        + np.random.normal(0, 0.001, (n_days, n_stocks)),
        index=pd.date_range("2024-01-01", periods=n_days),
    )
    csad = machine.calculate_csad(returns)
    assert (csad.dropna() < 0.05).all()


def test_csad_high_when_stocks_diverge(machine):
    """个股分化 → CSAD 高."""
    n_days, n_stocks = 30, 10
    returns = pd.DataFrame(
        np.random.normal(0, 0.05, (n_days, n_stocks)),
        index=pd.date_range("2024-01-01", periods=n_days),
    )
    csad = machine.calculate_csad(returns)
    assert csad.dropna().mean() > 0.01


def test_classify_state_boundaries(machine):
    """健康度边界映射四状态."""
    scores = pd.Series([3, 1, -1, -3], name="health_score")
    states = machine.classify_state(scores)
    assert list(states) == ["EXPANSION", "OVERHEAT", "CONTRACTION", "BOTTOMING"]


def test_quantile_score_direction(machine):
    """分位数打分方向正确."""
    s = pd.Series([0, 1, 2, 3, 4, 5] * 10)
    # 低于 low_q → +1, 高于 high_q → -1 (invert)
    low_score = machine._quantile_score(-1, s, 0.2, 0.8, invert=True)
    high_score = machine._quantile_score(100, s, 0.2, 0.8, invert=True)
    assert low_score == -1   # CSAD 低 → 好 (+1) 再 invert? 见实现
    assert high_score == 1
