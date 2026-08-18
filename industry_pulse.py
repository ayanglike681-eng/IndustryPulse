#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IndustryPulse CLI 入口.

串联: 数据采集 → 状态计算引擎 → 验证 → 仪表盘/报告

Usage:
    python industry_pulse.py --industry=新能源 --start=2020-01-01 --output=./report/
"""
import argparse
import os
import sys
from pathlib import Path

import yaml

# 确保可从项目根目录导入 src
sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="IndustryPulse — 行业景气度与风险状态监测仪表盘"
    )
    parser.add_argument("--industry", default="新能源", help="行业名称")
    parser.add_argument("--start", default="2020-01-01", help="起始日期")
    parser.add_argument("--end", default="2026-08-18", help="结束日期")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--output", default="./report/", help="输出目录")
    parser.add_argument(
        "--skip-fetch", action="store_true", help="跳过数据采集(使用已缓存数据)"
    )
    parser.add_argument(
        "--skip-validate", action="store_true", help="跳过验证环节"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.output, exist_ok=True)

    # 延迟导入, 加快 --help 响应
    from src.data_fetcher import DataFetcher
    from src.indicators import IndustryStateMachine
    from src.validator import Validator
    from src.visualizer import Visualizer
    from src.report_generator import ReportGenerator

    print(f"[IndustryPulse] 行业={args.industry} 区间={args.start}~{args.end}")

    # ---- Phase 1: 数据采集 ----
    if not args.skip_fetch:
        print("[1/5] 数据采集中...")
        fetcher = DataFetcher(cfg)
        fetcher.run()
        print("      数据已写入 SQLite")

    # ---- Phase 2: 核心指标计算 ----
    print("[2/5] 指标计算中 (CSAD / Phi / 健康度 / 状态机)...")
    machine = IndustryStateMachine(cfg)
    features = machine.run()
    print(f"      完成, 状态序列长度={len(features)}")

    # ---- Phase 3: 状态验证 ----
    if not args.skip_validate:
        print("[3/5] 多方法验证中 (样本外/置换/事件/回测)...")
        validator = Validator(cfg)
        validation_result = validator.run(features)
    else:
        validation_result = {}

    # ---- Phase 4: 可视化仪表盘 ----
    print("[4/5] 生成仪表盘...")
    viz = Visualizer(cfg)
    dashboard_html = viz.build_dashboard(features, validation_result, args)
    print(f"      仪表盘: {dashboard_html}")

    # ---- Phase 5: 报告生成 ----
    print("[5/5] 生成报告...")
    reporter = ReportGenerator(cfg)
    outputs = reporter.run(features, validation_result, args)
    for name, path in outputs.items():
        print(f"      {name}: {path}")

    print("[IndustryPulse] 全部完成。")


if __name__ == "__main__":
    main()
