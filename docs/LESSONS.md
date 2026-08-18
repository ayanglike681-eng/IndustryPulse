# 经验教训 (LESSONS)

开发过程中积累的踩坑与决策记录. 持续更新.

## 数据源踩坑 (akshare)

### 东财源沙箱被反爬
- `stock_zh_a_hist` / `stock_board_industry_cons_em` 在沙箱返回 http=000, 加 UA 无效
- 不是技术问题, 是 IP/地域拦截
- 改用新浪源 `stock_zh_a_daily` (symbol 格式 sz300750 / sh600519), 已验证可用
- 固定股票池本身就是设计 (规避动态成分股接口不稳定)

### bond_china_yield 长区间返空
- 传 20200101~20260818 全区间返回 0 行, 服务端限制
- 改按月分段循环 (80 次), 单月≤31 天有数据, 月空则降级 10 天窗
- 信用利差 = AAA 中短期票据 10年 - 国债 10年 (中债, 比美联储 BAA-AAA 更贴 A 股)

## CSAD 计算坑

### dropna 吞交易日 (最隐蔽 bug)
- `pct_change(fill_method=None).dropna()` 过于激进: 30 家任一票停牌/未上市, 该交易日整行删
- 状态序列 56/80 月, 缺 24 月 (恰好是 2020-2021 暴涨段)
- 改 `mean(skipna=True)`, 保留停牌日, num_stocks 反映当日实际参与票数
- 直接验证: 序列 56→80 月

## 频率对齐坑

### groupby 丢月
- `groupby('year_month').last()` 吞掉无数据月份
- 改 `resample('ME').last()` 自动生成所有月份索引 + `ffill(limit=2)` 填缺失月

### phi 字符串 index join 后 to_period 报错
- macro_daily.date 是字符串, join 后 daily.index 变 object, `to_period('M')` 报 AttributeError
- 修: `_load_phi` 内 `pd.to_datetime(date)`, align_to_monthly 开头 `df.index = pd.to_datetime(df.index)`

### trade_date 月末纳秒
- `to_timestamp(how='end')` 产生 23:59:59.999999999, plotly 弃纳秒警告
- 改 `index.normalize()` 消除

## 分位数 look-ahead (方法论核心)

### 全历史分位数是数据窥探
- 用全历史分位数打分: 2020 年的 csad 用 2026 数据做参照 → 早期状态偏乐观
- 事件验证"精准命中"50% 是假象: look-ahead 让状态恰好对上事件
- 改 `expanding(min_periods=12)` 滚动分位数 (截至当月历史)
- 验证变化: 事件命中 50%→17%, CONTRACTION 33→3 (大量 CON 是假象)
- **CSAD 信号本身仍非随机** (置换 p<0.0001, 与 look-ahead 无关)

## 回测伪信号

### 丢月 bug 造成回测结论反转
- 56 月缺失恰好漏 2020-2021 暴涨段, 买入持有被算成 -34.7%
- 策略"少亏"显得跑赢 (夏普 -0.016 vs -0.107) ← 伪信号
- 修复后 80 月完整: 买入持有 +173.5%, 策略 +96.5%, **未跑赢**
- 教训: 数据缺失造成的回测优势必须警惕, 先验完整数据再下结论

## 状态机定位结论

### 描述工具非预测工具
- CSAD/Phi/momentum 能刻画"现在处于什么周期" (周期定位)
- 但对"事件何时发生"预测力弱 (样本内事件命中 17%)
- PE/VC 实用场景本就是判断"现在能不能投"而非预测事件, 定位价值仍在
- 当前状态 + 持续期统计 (半马尔可夫) 是实用产出

### BOTTOMING 难触发
- 需 momentum(-1)+dispersion(-1)+credit(-1)=-3 同时满足
- 当前数据下三负难凑齐, BOTTOMING 0 次
- 若要筑底信号可见, 可放边界 (-3→-2) 或补财务增强 momentum

## 已知问题与应对

### CSAD 成分股变动不可比
- 固定股票池 (30 家锁定) + skipna 保留停牌日

### 财务季度 vs 行情日度 频率不匹配
- 当前 momentum 用价格二阶导替代营收增速 (财务接口未通)
- 状态以月度为单位, 日度数据 resample 聚合
- 待补: 财务接口探测 (新浪/同花顺), momentum 增强为营收趋势

### 状态阈值主观性
- 滚动分位数 (expanding min_periods=12) 动态计算, 消 look-ahead
- config.yaml 暴露 high/low quantile 可配置
- 前 12 月 score=0 (历史不足), 诚实不判

## 验证报告实际结论 (2026-08-18)

- 事件验证 17% (样本内, 滚动分位数): 状态-事件时点对应弱
- 置换检验 p<0.0001: CSAD 信号非随机, regime 持续 3.66 月 vs 随机 2.00 月
- 策略回测: 夏普 0.438 未跑赢买入持有 0.561 (新能源周期整体上涨, 空仓错过收益)
- 当前状态 (2026-08): OVERHEAT, 健康度 +1
