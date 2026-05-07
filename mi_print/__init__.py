#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcb-drawing-printing-system
===========================
胜宏科技（惠州）MI (Manufacturing Instruction) 制程指示系统

版本: 2.0 (重构版)
原始作者: Gf.zhang, LiuChuang

公开 API:
  CAM              — Genesis/InCAMPro 统一操作接口
  GenesisAPI       — MI 标记提取的 Genesis 封装
  SVGGenerator     — SVG 图纸渲染器
  DBOperator       — 数据库统一接口
  main             — CLI 入口 (python -m mi_print main)
"""

import logging
import sys

__version__ = "2.0.0"
__author__ = "Gf.zhang & LiuChuang (VTG.SH Software Group)"

# ═══════════════════════════════════════════
# 日志初始化
# ═══════════════════════════════════════════

_log_format = logging.Formatter(
    '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 控制台 handler
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_format)
_console_handler.setLevel(logging.WARNING)

# 默认 logger
logger = logging.getLogger('mi_print')
logger.addHandler(_console_handler)
logger.setLevel(logging.WARNING)


def get_logger(name: str = 'mi_print', level: int = logging.WARNING) -> logging.Logger:
    """获取配置好的 logger 实例

    Args:
        name:  logger 名称
        level: 日志级别

    Returns:
        logging.Logger 实例
    """
    lg = logging.getLogger(name)
    lg.setLevel(level)
    return lg

# 公开导出（按需懒加载，避免未安装依赖时崩溃）
def __getattr__(name):
    if name == "CAM":
        from .cam_interface import CAM
        return CAM
    if name == "GenesisAPI":
        from .mi_extractor import GenesisAPI
        return GenesisAPI
    if name == "SVGGenerator":
        from .svg_renderer import SVGGenerator
        return SVGGenerator
    if name == "DBOperator":
        from .database import DBOperator
        return DBOperator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
