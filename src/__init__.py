# -*- coding: utf-8 -*-
"""IndustryPulse 核心模块包.

模块:
    data_fetcher     数据采集 (akshare → SQLite)
    db               SQLite 管理
    indicators       CSAD / Phi / 健康度 / 状态机
    validator        多方法验证
    visualizer       4 张核心图
    report_generator 报告生成
"""

__version__ = "0.1.0"
__all__ = [
    "data_fetcher",
    "db",
    "indicators",
    "validator",
    "visualizer",
    "report_generator",
]
