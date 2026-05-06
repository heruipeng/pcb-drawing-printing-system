#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - 全局配置
=====================
胜宏科技（惠州）MI (Manufacturing Instruction) 制程指示系统

本文件包含所有可配置项：
  - 数据库连接参数
  - 文件路径
  - 单位/渲染选项
  - note 类型定义
  - 厂区映射
  - SVG 样式表
"""

import os
import platform

# ═══════════════════════════════════════════
# 系统环境
# ═══════════════════════════════════════════

IS_WINDOWS: bool = platform.system() == "Windows"
IS_LINUX: bool = platform.system() == "Linux"

# Genesis 环境变量
GENESIS_DIR: str = os.environ.get(
    "GENESIS_DIR",
    r"D:\genesis" if IS_WINDOWS else "/genesis"
).replace("\\", "/")

GENESIS_EDIR: str = os.environ.get("GENESIS_EDIR", "")
GENESIS_TMP: str = os.environ.get(
    "GENESIS_TMP",
    r"C:\tmp" if IS_WINDOWS else "/tmp"
)

# cam_interface.py 路径（用于 sys.path 引用）
CAM_INTERFACE_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gerber-tool"
)

# ═══════════════════════════════════════════
# 路径配置
# ═══════════════════════════════════════════

# SVG 输出目录
SVG_DIR: str = r"D:\disk" if IS_WINDOWS else "/tmp/mi_svg"

# TGZ 备份路径
TGZ_DIR: str = (
    r"\\192.168.2.57\临时文件夹\MI自动标注图纸TGZ位置路径"
    if IS_WINDOWS else
    "/tmp/mi_tgz"
)

# EDITER 名称 JSON
EDITOR_JSON: str = os.path.join(
    GENESIS_DIR, "fw", "lib", "user", "editer_name.json"
).replace("\\", "/")


def get_json_path(job_name: str) -> str:
    """根据料号名获取 job_notes.json 路径"""
    return os.path.join(
        GENESIS_DIR, "fw", "jobs", str(job_name), "user", "job_notes.json"
    ).replace("\\", "/")


# ═══════════════════════════════════════════
# 数据库配置
# ═══════════════════════════════════════════

# MySQL 配置（工程管理系统）
MYSQL_CONFIG: dict = {
    "host": "192.168.2.19",
    "port": 3306,
    "username": "root",
    "password": "k06931!",
    "database": "project_status",
    "charset": "utf8",
}

# Oracle ERP 配置（Tiptop ERP）
ORACLE_ERP_CONFIG: dict = {
    "host": "172.20.218.247",
    "port": 1521,
    "username": "zygc",
    "password": "ZYGC@2019",
    "service_name": "topprod",
    "sid": "topprod1",
}

# Oracle InPlan 配置
ORACLE_INPLAN_CONFIG: dict = {
    "host": "192.168.2.18",
    "port": 1521,
    "username": "GETDATA",
    "password": "InplanAdmin",
    "service_name": "inmind.fls",
}

# NLS_LANG 环境
os.environ.setdefault("NLS_LANG", "AMERICAN_AMERICA.UTF8")

# ═══════════════════════════════════════════
# 厂区映射（胜宏 6 个厂区）
# ═══════════════════════════════════════════

SITE_MAP: dict = {
    "S0101": "胜宏一厂",
    "S0102": "胜宏二厂",
    "S0103": "胜宏三厂",
    "S0104": "胜宏四厂",
    "S0105": "胜宏五厂",
    "S0106": "胜宏六厂",
}

# ═══════════════════════════════════════════
# 默认打印参数
# ═══════════════════════════════════════════
# 格式: [导出PDF, 单位, 阻抗单位, PDF后缀, 阻抗对称制作, 编辑者, Step名,
#        Genesis用户名, 阻抗表, 留白, 标板外/内, 优化数据, 错误信息, 移动偏移]

DEFAULT_PRINT_CONFIG: list = [
    1,          # 导出PDF 0/1
    "mil",      # 单位 mil/mm/um
    "Ω",        # 阻抗单位
    "_pdf_+_",  # PDF 后缀
    "否",       # 阻抗对称制作
    "",         # 编辑者
    "",         # Step名
    "",         # Genesis 用户名
    {},         # 阻抗表 {key: [layer, values, ref_layer, ...]}
    "300",      # 留白
    "标板外",    # 标注位置
    1,          # 优化数据 0/1/2
    "",         # 错误信息
    [0, 0],     # 移动偏移 [x, y]
]

# ═══════════════════════════════════════════
# Note 类型定义
# ═══════════════════════════════════════════

NOTE_TYPES: dict = {
    "Note":             "制作指示",
    "Eagle-WS-M":       "线宽/线距",
    "Eagle-Line-M1":    "线宽",
    "Eagle-LineDis-M1": "线距",
    "Eagle-BGA-M1":     "BGA",
    "Eagle-SMT-M":      "SMD",
    "Eagle-PAD-M1":     "PAD",
    "Eagle-Bridge-M1":  "铜桥",
    "Eagle-Ring-M1":    "隔离环",
    "Eagle-BGA-M2":     "椭圆BGA",
    "Eagle-PAD-M2":     "椭圆PAD",
    "Eagle-WS-M2":      "蛇形线宽/线距",
    "Eagle-Line-M2":    "蛇形线宽",
    "Eagle-LineDis-M2": "蛇形线距",
    "BGA-PITCH":        "BGA中心距",
    "SMT-PITCH":        "SMD中心距",
    "IC-SPECING":       "IC间距",
    "IC-SPACING":       "IC间距",
    "MARK-SIZE":        "光点大小",
    "MARK-OPEN":        "光点开窗",
}

# Note 选择映射
# 格式: [显示名, 特征类型, 计算模式, 最小选择数, 值模式, 最小值索引,
#        层类型列表, 阻焊标志, 排序号, 标记字母]
# 计算模式: 0=单值, 1=两值(宽/距), 2=椭圆, 3=中心距, 4=间距, 5=IC间距
NOTE_SELECT: dict = {
    "Eagle-WS-M":       ["线宽/线距",    "line\\;arc",   1, 2, 2, 1, ["IN", "LL"],               0, 1,  "E"],
    "Eagle-WS-M2":      ["蛇形线宽/线距", "line\\;arc",  1, 2, 2, 1, ["IN", "LL"],               0, 1,  "E"],
    "Eagle-Line-M1":    ["线宽",          "line\\;arc",   0, 1, 1, 1, ["IN", "LL"],               0, 0,  "A"],
    "Eagle-LineDis-M1": ["线距",          "line\\;arc",   0, 2, 0, 2, ["IN", "LL"],               0, 1,  "B"],
    "Eagle-BGA-M1":     ["BGA",           "pad",          0, 1, 0, 3, ["LL", "MM"],               1, 3,  "G"],
    "Eagle-SMT-M":      ["SMD",           "pad",          0, 1, 0, 4, ["LL", "MM"],               1, 2,  "C"],
    "Eagle-PAD-M1":     ["PAD",           "pad",          0, 1, 0, 9, ["LL", "MM", "IN"],         1, 5,  "P"],
    "Eagle-BGA-M2":     ["椭圆BGA",       "pad",          2, 1, 0, 3, ["LL", "MM"],               1, 4,  "G"],
    "Eagle-PAD-M2":     ["椭圆PAD",       "pad",          2, 1, 0, 9, ["LL", "MM", "IN"],         1, 6,  "P"],
    "Eagle-Line-M2":    ["蛇形线宽",      "line\\;arc",   0, 1, 1, 1, ["IN", "LL"],               0, 0,  "A"],
    "Eagle-LineDis-M2": ["蛇形线距",      "line\\;arc",   0, 2, 0, 2, ["IN", "LL"],               0, 1,  "B"],
    "BGA-PITCH":        ["BGA中心距",     "pad",          3, 2, 0, 5, ["LL", "MM"],               0, 9,  "G"],
    "SMT-PITCH":        ["SMD中心距",     "pad",          3, 2, 0, 6, ["LL", "MM"],               0, 8,  "C"],
    "Eagle-Bridge-M1":  ["铜桥",          "line\\;arc",   4, 2, 0, 1, ["IN", "LL"],               0, 10, "Q"],
    "Eagle-Ring-M1":    ["隔离环",        "pad",          4, 2, 0, 7, ["IN", "LL"],               0, 11, "H"],
    "IC-SPECING":       ["IC间距",        "pad",          5, 2, 0, 8, ["LL"],                     0, 7,  "I"],
    "IC-SPACING":       ["IC间距",        "pad",          5, 2, 0, 8, ["LL"],                     0, 7,  "I"],
    "MARK-SIZE":        ["光点大小",      "pad",          0, 1, 0, 0, ["LL", "MM"],               2, 12, "M"],
    "MARK-OPEN":        ["光点开窗",      "pad",          0, 1, 0, 0, ["MM"],                     0, 12, "M"],
}

# ═══════════════════════════════════════════
# 表格列定义
# ═══════════════════════════════════════════

# 表头
HO_TYPES: list = ["序号", "类型", "标记", "成品值", "原稿值", "阻抗值", "备注"]
HO_TYPE_COLS: list = [50, 80, 60, 120, 120, 120, 560]

# ═══════════════════════════════════════════
# SVG 渲染配置
# ═══════════════════════════════════════════

SVG_REVISION: str = "1.52"

# SVG 最小尺寸
MIN_SVG_WIDTH: int = 1200
MIN_SVG_HEIGHT: int = 600

# 颜色表（用于阻抗区分）
COLOR_LIST: list = [
    "#FF1493",  # 深粉色
    "#4169E1",  # 皇军蓝
    "#DAA520",  # 秋麒麟
    "#008B8B",  # 深青色
    "#00FF00",  # 酸橙色
    "#00BFFF",  # 深天蓝
    "#FFA500",  # 橙色
    "#008000",  # 纯绿
    "#8B008B",  # 深洋红色
    "#D2691E",  # 巧克力
    "#FFFF00",  # 纯黄
    "#00FFFF",  # 青色
    "#808000",  # 橄榄
    "#BC8F8F",  # 玫瑰棕色
    "#7FFFAA",  # 绿玉/碧绿色
    "#D2B48C",  # 晒黑
    "#8B0000",  # 深红色
    "#1E90FF",  # 道奇蓝
]

# 层类型颜色
LAYER_COLOR_SIGNAL: str = "#FF0E32"       # 线路层
LAYER_COLOR_SOLDER_MASK: str = "#2C8634"  # 绿油层

# ═══════════════════════════════════════════
# 层排序键（用于层列表排序）
# ═══════════════════════════════════════════

LAYER_SORT_KEY: dict = {
    "IN": 1,   # 内层线路
    "LL": 2,   # 外层线路
    "MM": 3,   # 绿油
    "CC": 4,   # 字符
    "GO": 5,   # 金面
    "CA": 6,   # 碳油
    "DD": 7,   # 钻孔
    "SE": 8,   # SET 层
    "NO": 9,   # Note 层
}

# ═══════════════════════════════════════════
# 单位转换
# ═══════════════════════════════════════════

UNITS_MAP: dict = {
    # (from, to): (factor, decimal_places)
    ("mil", "mil"):  (1.0, 3),
    ("mil", "um"):   (25.4, 0),
    ("mil", "mm"):   (25.4 / 1000, 3),
    ("mm", "mm"):    (1.0, 5),
    ("mm", "mil"):   (1 / 25.4 * 1000, 3),
    ("mm", "um"):    (1000, 2),
    ("um", "um"):    (1.0, 2),
    ("um", "mil"):   (1 / 25.4, 3),
    ("um", "mm"):    (1 / 1000, 5),
}
