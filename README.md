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

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/VALIDATION.md](docs/VALIDATION.md)。
