#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - GUI 入口
=====================
启动 PyQt5 GUI 界面。

用法:
  python run_gui.py <job_name> [--step cad]
"""

import sys
import os

# 确保包路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from mi_print.mi_gui import main
    main()
