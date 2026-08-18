# IndustryPulse — 行业景气度与风险状态监测仪表盘

构建可复用的行业景气度监测框架,整合市场分化度、信用环境、流动性指标,识别行业周期状态(扩张/过热/收缩/筑底),为 PE/VC 投资决策提供状态判断依据。

## 核心能力

- **行业分化度 (CSAD)**:同行业公司收益率横截面绝对离散度,分化越大越可能处于周期拐点
- **信用环境指数 (Phi)**:信用利差扩大 = 融资环境收紧,影响 PE/VC 募资与退出
- **市场情绪/流动性 (VIX)**:高波动率下 IPO 窗口关闭、并购估值承压
- **行业周期四状态机**:EXPANSION / OVERHEAT / CONTRACTION / BOTTOMING
- **多方法验证**:样本外、置换检验、事件验证、策略回测,避免单一指标误判
- **半马尔可夫持续时间**:分析各状态历史平均持续期,判断煎熬期长度

## 目录结构

```
industry-pulse/
├── industry_pulse.py          # CLI 入口
├── config.yaml                # 配置 (行业/股票池/阈值/状态机)
├── requirements.txt
├── src/
│   ├── data_fetcher.py        # 数据采集 (akshare → SQLite)
│   ├── db.py                  # SQLite 管理
│   ├── indicators.py          # CSAD / Phi / 健康度 / 状态机
│   ├── validator.py           # 多方法验证
│   ├── visualizer.py          # 4 张核心图
│   └── report_generator.py    # 报告生成
├── docs/                      # 方法学文档
├── examples/                  # 示例输出
└── tests/
```

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python industry_pulse.py --industry=新能源 --start=2020-01-01 --output=./report/
```

输出:
- `industry_pulse_新能源_YYYYMMDD.html` — 仪表盘
- `state_history.csv` — 每日状态记录
- `validation_report.md` — 验证报告
- `investment_brief.md` — 投资建议摘要

## 设计取舍

- **固定股票池 + CSAD 去趋势**:解决成分股变动导致的跨期不可比
- **混频处理**:日度市场指标捕捉短期情绪,季度财务确认基本面,前向填充 + 月度聚合对齐
- **分位数动态阈值**:基于 2020-2024 历史数据计算,配置化,避免主观拍脑袋

## 验证结果

**样本外框架**: 滚动历史分位数 (expanding, min_periods=12), 排除 look-ahead bias.

- **CSAD 信号真实性**: 置换检验 p < 0.0001, 状态持续性 (3.66 月) 显著高于随机噪音 (2.00 月)
- **周期方向一致性**: 2024-01 碳酸锂暴跌, 模型进 CONTRACTION (MATCH); 但 2023-04 光伏产能过剩暴露时模型仍判 OVH, 滞后约 9 月才转 CON — 价格 momentum 对基本面反应滞后
- **事件匹配**: ±2 月窗口匹配率 17% (1 MATCH / 2 PARTIAL / 2 MISS), 状态-事件时点对应弱
- **风险规避价值**: 2020-2026 状态切换策略回撤 -51.1% vs 买入持有 -61.4% (夏普 0.438 vs 0.561, 未跑赢但回撤更小)

**方法论声明**: v1.0 全历史分位数存在 look-ahead bias (事件匹配率虚高至 50%), 已修正为滚动窗口. 修正后事件时点匹配率下降, 但 regime 方向判断仍与基本面方向一致. 状态机定位为**周期描述工具** (判断"现在处于什么周期"), 非事件预测工具.

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/VALIDATION.md](docs/VALIDATION.md).
