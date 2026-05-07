#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - SVG 渲染器
=======================
从 create_svg.py 核心逻辑提取而来。

功能:
  1. 从 Genesis CAM 提取图形数据
  2. 渲染为 SVG（使用 svgwrite 库）
  3. 可选 cairosvg 转换为 PDF

原始作者: Gf.zhang (create_svg.py v1.0, 2019-12-16)
"""

import os
import sys
import math
import time
from typing import Dict, List, Tuple, Optional, Any

# svgwrite - 必需依赖
try:
    import svgwrite
except ImportError:
    svgwrite = None
    print("[WARN] svgwrite 未安装，SVG 渲染不可用。pip install svgwrite")

# cairosvg - 可选依赖（需要系统安装 libcairo C 库）
try:
    import cairosvg
except (ImportError, OSError):
    cairosvg = None

try:
    from .cam_interface import CAM
except ImportError:
    CAM = None

from . import config
from . import geometry as _geom
from . import mi_extractor as _mi

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════

# SVG 样式库
_all_symbol_dist: Dict[str, Dict[str, str]] = {}
# 阻抗颜色映射
_color_dist: Dict[str, List[str]] = {"imp": []}
# Step 数据
_all_steps_dist: Dict[str, Any] = {}
# Symbol 数据
_symbols_datas: Dict[str, Dict] = {}
# Mask 信息
_mask_info: Dict[str, int] = {"tol": 0}
# 全局 LIMITS
_All_LIMITS: Dict[str, Any] = {}
# 最小尺寸
_min_limits = [1200, 600, 0]

# 颜色类型
_color_type: Dict[str, int] = {"col": 0}
_color_types: List[str] = ["red", "green", "blue", "yellow"]


# ═══════════════════════════════════════════
# Genesis 接口（SVG 专用）
# ═══════════════════════════════════════════

def _get_step_info(job: str, step: str, visited=None, depth=0) -> List[str]:
    """获取 Step 的子步骤列表（递归，含循环检测）"""
    if visited is None:
        visited = set()
    if step in visited or depth > 10:
        return []
    visited.add(step)
    gf = _mi.GenesisAPI
    steps = gf.GFDO_INFO(f'-t step -e {job}/{step} -d REPEAT')
    all_steps = list(set(steps.get('gREPEATstep', [])))
    for s in all_steps:
        sub = _get_step_info(job, s, visited, depth + 1)
        all_steps += sub
    return all_steps


# ═══════════════════════════════════════════
# SVG 样式初始化
# ═══════════════════════════════════════════

def _init_symbol_styles() -> None:
    """初始化 SVG 符号样式表"""
    global _all_symbol_dist, _color_types
    _all_symbol_dist.clear()

    _all_symbol_dist["path.profile"] = {
        "fill": "none",
        "stroke": "black",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "stroke-width": "0.1",
    }
    _all_symbol_dist["circle.profile"] = _all_symbol_dist["path.profile"]

    _all_symbol_dist["line.markgf"] = {
        "fill": "none",
        "stroke": "blue",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "stroke-width": "1",
        "opacity": "0.75",
    }
    _all_symbol_dist["circle.markgf"] = {
        "fill": "none",
        "stroke": "blue",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "stroke-width": "1",
        "opacity": "0.75",
    }
    _all_symbol_dist["rect.markgf"] = {
        "fill": "none",
        "stroke": "black",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "stroke-width": "1",
    }

    _color_type["col"] = 0
    _color_types[0] = "black"


# ═══════════════════════════════════════════
# 几何辅助
# ═══════════════════════════════════════════

def _rs_type(karck: list) -> list:
    """解析形状类型和参数

    Returns:
        [dummy, dummy, size, shape_variant, linecap, fill, stroke,
         feat_id, base_type, arc_angle, arc_r]
    """
    result = ["", "", "", "", "", "none",
              _color_types[_color_type["col"]], "", karck[2], 0, ""]

    if karck[2] == "N":  # 负性
        result[6] = "#ffffff"
    if karck[3] in ("#P", "#S"):
        result[5] = result[6]

    result[7] = karck[3].replace("#", "") + "_" + str(karck[4])

    if karck[1].startswith("s"):
        result[3] = "square"
        result[4] = ""
    elif karck[1].startswith("r"):
        result[3] = "round"
        result[4] = "round"

    try:
        result[2] = str(round(float(karck[1][1:]) / 1000.0, 3))
    except (ValueError, IndexError):
        result[2] = ""
        result[3] = ""
        result[4] = ""

    if result[2] in ("0.0", "0"):
        result[2] = "0.1000001"

    return result


def _get_imp_info(attrs: list) -> str:
    """从属性中提取阻抗信息"""
    for attr in attrs[1:]:
        for part in attr.split(","):
            if part.strip().startswith(".imp_info="):
                return part.replace(".imp_info=", "").strip()
    return ""


def _get_imp_color(attrs: list) -> str:
    """获取阻抗对应的颜色"""
    imp = _get_imp_info(attrs)
    if not imp:
        return ""
    try:
        idx = _color_dist["imp"].index(imp)
        return config.COLOR_LIST[idx % len(config.COLOR_LIST)]
    except ValueError:
        return ""


def _get_symbol(layer_type: str, shape_type: str,
                karc_texts: list, attrs: list = None) -> str:
    """生成 SVG 符号名（symbol 引用）"""
    if attrs is None:
        attrs = []

    name = (
        karc_texts[7].split("_")[0].replace("A", "L") +
        "_" + karc_texts[8] +
        "_" + karc_texts[3][0] +
        str(int(round(float(karc_texts[2]) * 10000)))
    ).lower()

    c_info = ""
    if karc_texts[2] == "0.1000001":
        name += "_mark"
    else:
        c_info = _get_imp_color(attrs)
        if c_info:
            c_info = '#000000'
            name += f"_c_{c_info[1:]}"
            karc_texts[6] = c_info
            if karc_texts[5] != "none":
                karc_texts[5] = c_info
        elif layer_type in ('signal', 'power_ground'):
            c_info = config.LAYER_COLOR_SIGNAL
            name += f"_c_{c_info[1:]}"
            karc_texts[6] = c_info
            if karc_texts[5] != "none":
                karc_texts[5] = c_info
        elif layer_type == 'solder_mask':
            c_info = config.LAYER_COLOR_SOLDER_MASK
            name += f"_c_{c_info[1:]}"
            karc_texts[6] = c_info
            if karc_texts[5] != "none":
                karc_texts[5] = c_info

    symbol_t = shape_type + "." + name
    if symbol_t not in _all_symbol_dist:
        _all_symbol_dist[symbol_t] = {}
        if c_info:
            _all_symbol_dist[symbol_t]["opacity"] = "0.75"
        _all_symbol_dist[symbol_t]["fill"] = karc_texts[5]

        if name[0] == 'l':
            _all_symbol_dist[symbol_t]["stroke"] = karc_texts[6]
            _all_symbol_dist[symbol_t]["stroke-linecap"] = karc_texts[3]
            if karc_texts[4]:
                _all_symbol_dist[symbol_t]["stroke-linejoin"] = karc_texts[4]
            _all_symbol_dist[symbol_t]["stroke-width"] = karc_texts[2]
            if "_mark" in name:
                _all_symbol_dist[symbol_t]["stroke"] = "red"
                _all_symbol_dist[symbol_t]["opacity"] = "0.75"
                _all_symbol_dist[symbol_t]["stroke-width"] = "0.1"
        elif name[0] == 'p':
            if shape_type == "rect":
                _all_symbol_dist[symbol_t]["width"] = str(karc_texts[1][0])
                _all_symbol_dist[symbol_t]["height"] = str(karc_texts[1][1])
            else:
                _all_symbol_dist[symbol_t]["r"] = str(karc_texts[1])

    return symbol_t


# ═══════════════════════════════════════════
# 特征数据解析
# ═══════════════════════════════════════════

def _get_arc_angle(karcs: list) -> list:
    """检查圆弧弧度（用于 SVG 大弧/小弧判断）"""
    karc_texts = _rs_type(karcs[1:])

    (faa, rda) = _geom.get_angle(karcs[0][0], karcs[0][1],
                                 karcs[0][4], karcs[0][5])
    (fab, rdb) = _geom.get_angle(karcs[0][2], karcs[0][3],
                                 karcs[0][4], karcs[0][5])
    fac = 360.0

    if faa > fab and karcs[2] == "Y":
        fac = faa - fab
    elif faa < fab and karcs[2] == "Y":
        fac = 360.0 - (fab - faa)
    elif faa > fab and karcs[2] == "N":
        fac = 360.0 - (faa - fab)
    elif faa < fab and karcs[2] == "N":
        fac = fab - faa

    karc_texts[9] = fac
    karc_texts[10] = "r" + str(round(rda * 2000.0, 1))

    sweep_flag = "1" if fac > 180 else "0"
    arc_dir = "1" if karcs[2] == "Y" else "0"

    karc_texts[0] = f"M{karcs[0][1]} {karcs[0][0]} "
    karc_texts[1] = (
        f"A{str(rda)} {str(rda)},"
        f"{sweep_flag},{arc_dir} "
        f"{karcs[0][3]} {karcs[0][2]}"
    )

    return karc_texts


def _get_line_info(karcs: list) -> list:
    """解析直线/PAD 信息"""
    # 处理退化的线（长度为零的线视为 PAD）
    if (len(karcs[0]) == 4 and karcs[4] == "#L" and
            abs(karcs[0][0] - karcs[0][2]) < 0.001 and
            abs(karcs[0][1] - karcs[0][3]) < 0.001):
        coords = karcs[0][0:2]
        karcs[4] = "#P"
    else:
        coords = karcs[0]

    karc_texts = _rs_type(karcs[1:])

    if len(coords) == 4:
        karc_texts[1] = [[coords[1], coords[0]],
                          [coords[3], coords[2]]]
    elif len(coords) == 2:
        karc_texts[0] = (coords[1], coords[0])
        try:
            karc_texts[1] = round(float(karc_texts[2]) * 0.5, 3)
        except (ValueError, TypeError):
            karc_texts[1] = -1
        if karc_texts[3] == 'square':
            karc_texts[0] = (coords[1] - karc_texts[1],
                             coords[0] - karc_texts[1])
            karc_texts[1] = (karc_texts[1] * 2, karc_texts[1] * 2)

    return karc_texts


# ═══════════════════════════════════════════
# 核心 SVG 生成
# ═══════════════════════════════════════════

def _add_svg_data(job: str, step: str, dwg: Any, dwg_g: Any,
                  feature_lines: List[str], mask_num: str = "",
                  layer_name: str = "") -> int:
    """解析特征行并添加 SVG 图形

    Args:
        job:            料号名
        step:           Step 名
        dwg:            svgwrite Drawing 实例
        dwg_g:          目标 Group 元素
        feature_lines:  Genesis 特征输出行列表
        mask_num:       遮罩编号
        layer_name:     层名

    Returns:
        处理的特征行数
    """
    row_count = 0
    profile = 0
    mask_dist = {}
    cam_dist = []
    layer_type = ''

    # 获取层类型
    if layer_name:
        info = _mi.GenesisAPI.DO_INFO(
            f"-t layer -e {job}/{step}/{layer_name} -m script -d BASE_TYPE"
        )
        base = info.get('gBASE_TYPE', '')
        if base in ('signal', 'power_ground'):
            layer_type = 'signal'
        elif base == 'solder_mask':
            layer_type = 'solder_mask'

    # 初始化 karcs
    karcs: list = [[]] + ["", "", "", "", ""]

    for line in feature_lines:
        attrs = line.strip().split(";")
        parts = attrs[0].split()

        if not parts:
            continue

        # 检查 profile 标记
        clean = line.replace(" ", "")
        if clean.startswith("###Stepprofiledata"):
            profile += 1

        elif parts[0] == "#A":  # 圆弧
            row_count += 1
            karcs = [
                [round(float(x), 5) for x in parts[1:7]]
            ] + [parts[10], parts[7], parts[8], parts[0], row_count]

            karc_texts = _get_arc_angle(karcs)

            if round(karc_texts[9], 1) == 360.0:
                # 360° 弧 → 用圆表示
                tmp = karcs[:]
                tmp[0] = karcs[0][4:]
                tmp[2] = karc_texts[10]
                karc_texts2 = _get_line_info(tmp)
                karc_texts2[2] = karc_texts[2]
                sym = _get_symbol(layer_type, "circle", karc_texts2, attrs)
                cam_dist.append([
                    dwg.circle(center=karc_texts2[0],
                               r=karc_texts2[1], class_=sym)
                ])
            else:
                sym = _get_symbol(layer_type, "path", karc_texts, attrs)
                cam_dist.append([
                    dwg.path(d="".join(karc_texts[0:2]), class_=sym)
                ])

        elif parts[0] == "#L":  # 直线
            row_count += 1
            karcs = [
                [round(float(x), 2) for x in parts[1:5]]
            ] + ["", parts[5], parts[6], parts[0], row_count]

            karc_texts = _get_line_info(karcs)

            if not karc_texts[0]:
                sym = _get_symbol(layer_type, "line", karc_texts, attrs)
                cam_dist.append([
                    dwg.line(start=karc_texts[1][0],
                             end=karc_texts[1][1], class_=sym)
                ])
            elif karc_texts[3] == 'square':
                c = _get_imp_color(attrs)
                fill = c or (config.LAYER_COLOR_SIGNAL
                             if layer_type == 'signal'
                             else (config.LAYER_COLOR_SOLDER_MASK
                                   if layer_type == 'solder_mask'
                                   else "#000000"))
                cam_dist.append([
                    dwg.rect(insert=karc_texts[0],
                             size=karc_texts[1], fill=fill)
                ])
            elif karc_texts[3] == 'round':
                c = _get_imp_color(attrs)
                fill = c or (config.LAYER_COLOR_SIGNAL
                             if layer_type == 'signal'
                             else (config.LAYER_COLOR_SOLDER_MASK
                                   if layer_type == 'solder_mask'
                                   else "#000000"))
                cam_dist.append([
                    dwg.circle(center=karc_texts[0],
                               r=karc_texts[1], fill=fill)
                ])

        elif parts[0] == "#P":  # PAD
            row_count += 1
            karcs = [
                [round(float(x), 2) for x in parts[1:3]]
            ] + ["", parts[3], parts[4], parts[0], row_count]

            karc_texts = _get_line_info(karcs)
            c = _get_imp_color(attrs)
            fill = c or (config.LAYER_COLOR_SIGNAL
                         if layer_type == 'signal'
                         else (config.LAYER_COLOR_SOLDER_MASK
                               if layer_type == 'solder_mask'
                               else "#000000"))
            karc_texts[5] = fill

            if karc_texts[3] == 'square':
                cam_dist.append([
                    dwg.rect(insert=karc_texts[0],
                             size=karc_texts[1], fill=karc_texts[5])
                ])
            elif karc_texts[3] == 'round':
                cam_dist.append([
                    dwg.circle(center=karc_texts[0],
                               r=karc_texts[1], fill=karc_texts[5])
                ])
            else:
                # 奇怪形状的 symbol
                _handle_complex_symbol(job, step, layer_name,
                                       parts, karc_texts,
                                       cam_dist, dwg)

        elif parts[0] == "#S":  # 多边形起始
            row_count += 1
            kmask = f"mask_{mask_num}_{row_count}"
            karcs = [[]] + ["", "", parts[1], parts[0],
                            row_count, parts[1], "",
                            f"url(#{kmask})"]
            mask_dist[karcs[8]] = [dwg.mask(id=kmask), 0]
            c = _get_imp_color(attrs)

        elif parts[0] == "#OB":  # 多边形接点开始
            karcs[7] = parts[3]
            karc_texts = _get_line_info(karcs)
            karcs[0] = [round(float(x), 5) for x in parts[1:3]]
            karc_texts[0] = f"M{karcs[0][1]} {karcs[0][0]} "

        elif parts[0] == "#OS":  # 多边形直线接点
            karcs[0] = [round(float(x), 5) for x in parts[1:3]]
            karc_texts = _get_line_info(karcs)
            karc_texts[1] += f"L{karcs[0][1]} {karcs[0][0]} "

        elif parts[0] == "#OC":  # 多边形圆弧接点
            karcs[0] += [round(float(x), 5) for x in parts[1:5]]
            karcs[1] = parts[5]
            arc_info = _get_arc_angle(karcs)
            karc_texts[1] += arc_info[1]
            karc_texts[9] = arc_info[9]
            karc_texts[10] = arc_info[10]
            karcs[0] = [round(float(x), 5) for x in parts[1:3]]
            if arc_info[9] == 360.0:
                karcs[0] = [round(float(x), 5) for x in parts[3:5]]

        elif parts[0] == "#OE":  # 多边形结束
            c = _get_imp_color(attrs)
            fill = c or (config.LAYER_COLOR_SIGNAL
                         if layer_type == 'signal'
                         else (config.LAYER_COLOR_SOLDER_MASK
                               if layer_type == 'solder_mask'
                               else "#000000"))
            karc_texts[5] = fill
            karc_texts[1] += "Z"

            if profile:
                karc_texts[7] = "profile"
                karc_texts[5] = "none"
                karc_texts[2] = 0.1
                karc_texts[6] = "black"
                karc_texts[3] = "round"
                karc_texts[4] = "round"
                if karc_texts[9] == 360:
                    karcs.append(karc_texts[10])
                    kt = _get_line_info(karcs)
                    cam_dist.append([
                        dwg.circle(center=kt[0], r=kt[1],
                                   class_=karc_texts[7])
                    ])
                else:
                    cam_dist.append([
                        dwg.path(d="".join(karc_texts[0:2]),
                                 class_=karc_texts[7])
                    ])
            elif karc_texts[9] == 360:
                karcs.append(karc_texts[10])
                kt = _get_line_info(karcs)
                if karcs[7] == "H":
                    mask_dist[karcs[8]][0].add(
                        dwg.circle(center=kt[0], r=kt[1],
                                   fill=_color_types[0])
                    )
                    mask_dist[karcs[8]][1] += 1
                else:
                    mask_dist[karcs[8]][0].add(
                        dwg.circle(center=kt[0], r=kt[1],
                                   fill="white")
                    )
                    cam_dist.append([dwg.circle, kt[:],
                                     karcs[:], 0])
            else:
                if karcs[7] == "H":
                    mask_dist[karcs[8]][0].add(
                        dwg.path(d="".join(karc_texts[0:2]),
                                 fill=_color_types[0])
                    )
                    mask_dist[karcs[8]][1] += 1
                else:
                    mask_dist[karcs[8]][0].add(
                        dwg.path(d="".join(karc_texts[0:2]),
                                 fill="white")
                    )
                    cam_dist.append([dwg.path, karc_texts[:],
                                     karcs[:], 1])

            karcs[0] = []
            karc_texts[0] = ""
            karc_texts[1] = ""

    # 添加 mask
    for key in mask_dist:
        if mask_dist[key][1]:
            dwg_g.add(mask_dist[key][0])
            _mask_info["tol"] += 1

    # 添加图形元素（分批写入，每 10000 个元素 flush 一次）
    _BATCH_SIZE = 10000
    _batch = []
    for item in cam_dist:
        _batch.append(item)
        if len(_batch) >= _BATCH_SIZE:
            _flush_cam_batch(dwg_g, _batch, mask_dist)
            _batch = []
    if _batch:
        _flush_cam_batch(dwg_g, _batch, mask_dist)
    cam_dist.clear()

    return row_count


def _flush_cam_batch(dwg_g: Any, items: list, mask_dist: dict) -> None:
    """将一批 cam_dist 元素写入 dwg group"""
    for item in items:
        if len(item) == 1:
            dwg_g.add(item[0])
        elif item[2][8] in mask_dist:
            if mask_dist[item[2][8]][1]:
                if item[3] == 1:
                    dwg_g.add(item[0](
                        d="".join(item[1][0:2]),
                        fill=item[1][5], mask=item[2][8]
                    ))
                else:
                    dwg_g.add(item[0](
                        center=item[1][0], r=item[1][1],
                        fill=item[1][5], mask=item[2][8]
                    ))
            else:
                if item[3] == 1:
                    dwg_g.add(item[0](
                        d="".join(item[1][0:2]),
                        fill=item[1][5]
                    ))
                else:
                    dwg_g.add(item[0](
                        center=item[1][0], r=item[1][1],
                        fill=item[1][5]
                    ))


def _handle_complex_symbol(job: str, step: str, layer_name: str,
                           parts: list, karc_texts: list,
                           cam_dist: list, dwg: Any) -> None:
    """处理复杂形状的 symbol（如 oval、oct 等）"""
    global _symbols_datas

    if layer_name not in _symbols_datas:
        return

    lrkey = parts[3]
    if parts[4] == "N":
        lrkey += "_neg"

    oldlyr = lrkey
    mirrorf = 1 if parts[7] != "Y" else -1
    suffix = f"_{parts[6]}_{parts[7].lower()}".replace("_0_n", "")
    lrkey += suffix

    transform = f"scale(1,{mirrorf}) rotate({parts[6]})"

    if lrkey not in _symbols_datas[layer_name]:
        _symbols_datas[layer_name][oldlyr][2] += 1
        uid = f"s_{layer_name}_{int(time.time() * 1000)}"
        _symbols_datas[layer_name][lrkey] = [
            uid, dwg.g(id=uid), 0,
        ]
        _symbols_datas[layer_name][lrkey][1].add(
            dwg.use(href="#" + _symbols_datas[layer_name][oldlyr][0],
                    insert=(0, 0), transform=transform)
        )

    _symbols_datas[layer_name][lrkey][2] += 1
    cam_dist.append([
        dwg.use(href="#" + _symbols_datas[layer_name][lrkey][0],
                insert=karc_texts[0])
    ])


# ═══════════════════════════════════════════
# REPEAT 处理
# ═══════════════════════════════════════════

def _get_repeat(job: str, step: str) -> List[List]:
    """获取 Step 的 REPEAT 数据"""
    info = _mi.GenesisAPI.DO_info(
        f'-t step -e {job}/{step} -d REPEAT', "mm"
    )

    step_list = []
    steps = info.get('gREPEATstep', [])
    xa = info.get('gREPEATxa', [])
    ya = info.get('gREPEATya', [])
    angles = info.get('gREPEATangle', [])
    mirrors = info.get('gREPEATmirror', [])

    for i in range(len(steps)):
        step_list.append([
            steps[i],
            xa[i] if i < len(xa) else 0,
            ya[i] if i < len(ya) else 0,
            angles[i] if i < len(angles) else 0,
            mirrors[i] if i < len(mirrors) else "no",
        ])

    return step_list


# ═══════════════════════════════════════════
# Symbol 预处理
# ═══════════════════════════════════════════

def _get_symbols(job: str, step: str, layer_names: list,
                 dwg: Any, break_feat: str = "") -> None:
    """收集并预处理 layer 中的 symbol"""
    global _symbols_datas

    _symbols_datas[layer_names[0]] = {}
    if break_feat:
        return

    try:
        _mi.GenesisAPI._VOF()
        symbs = _mi.GenesisAPI.DO_info(
            f"-t layer -e {job}/{step}/{layer_names[0]} "
            f"-d SYMS_HIST -o break_sr", "mm"
        )
        _mi.GenesisAPI._VON()
    except Exception as e:
        print(f"[WARN] SVG symbol 数据获取失败 ({layer_names[0]}): {e}", file=sys.stderr)
        symbs = {}

    if not symbs:
        return

    symbols = {}
    sym_names = symbs.get('gSYMS_HISTsymbol', [])
    sym_counts = symbs.get('gSYMS_HISTpad', [])
    for i in range(len(sym_names)):
        symbols[str(sym_names[i])] = sym_counts[i]

    # 过滤简单符号
    filtered = {}
    for name, count in symbols.items():
        if count == 0:
            continue
        if name and name[0] in ("s", "r"):
            try:
                if float(name[1:]) > 0:
                    continue
            except ValueError:
                pass
        filtered[name] = count

    if not filtered:
        return

    # 创建符号并渲染
    _mi.GenesisAPI._VOF()
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_post_hooks,value=4,mode=user"
    )
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_pre_hooks,value=4,mode=user"
    )
    _mi.GenesisAPI._VON()

    _mi.GenesisAPI.open_step(job, step, "mm")
    tmp_layer = "symbol_info_tmp+++"
    _mi.GenesisAPI._VOF()
    _mi.GenesisAPI._COM(f'delete_layer,layer={tmp_layer}')
    _mi.GenesisAPI._VON()
    _mi.GenesisAPI._COM(
        f'create_layer,layer={tmp_layer},context=misc,'
        f'type=signal,polarity=positive,ins_layer='
    )
    _mi.GenesisAPI._COM(
        f'affected_layer,name={tmp_layer},mode=single,affected=yes'
    )

    for name in filtered:
        _mi.GenesisAPI._COM(
            f"add_pad,attributes=no,x=0,y=0,"
            f"symbol={name},polarity=positive"
        )

        try:
            _mi.GenesisAPI._VOF()
            _mi.GenesisAPI._COM("sel_break")
            syms = _mi.GenesisAPI.DO_info(
                f"-t layer -e {job}/{step}/{tmp_layer} -d FEAT_HIST", "mm"
            )
            _mi.GenesisAPI._VON()
            symbc = syms.get('gFEAT_HISTtotal', 0)
        except Exception as e:
            print(f"[WARN] SVG symbol 统计失败 ({name}): {e}", file=sys.stderr)
            symbc = 0

        if (filtered[name] * symbc) > 100000:
            _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
            _mi.GenesisAPI._COM(
                "filter_set,filter_name=popup,"
                "update_popup=no,polarity=negative"
            )
            _mi.GenesisAPI._COM("filter_area_strt")
            _mi.GenesisAPI._COM(
                'filter_area_end,layer=,filter_name=popup,'
                'operation=select,area_type=none,'
                'inside_area=no,intersect_area=no'
            )

    _mi.GenesisAPI._COM(
        f'affected_layer,name={tmp_layer},mode=single,affected=yes'
    )

    for name in filtered:
        _mi.GenesisAPI._COM('sel_delete')
        _mi.GenesisAPI._COM(
            f"add_pad,attributes=no,x=0,y=0,"
            f"symbol={name},polarity=positive"
        )
        try:
            _mi.GenesisAPI._VOF()
            features = _mi.GenesisAPI.INFO(
                f'-t layer -e {job}/{step}/{tmp_layer} -d FEATURES'
            )
            _mi.GenesisAPI._VON()
        except Exception as e:
            print(f"[WARN] get_symbols features {job}/{step}/{tmp_layer}: {e}")
            features = []

        if features:
            uid = f"s_{layer_names[0]}_{name}"
            g = dwg.g(id=uid)
            _add_svg_data(job, step, dwg, g, features, "", tmp_layer)
            _symbols_datas[layer_names[0]][name] = [uid, g, 0]

    _mi.GenesisAPI._COM(f'delete_layer,layer={tmp_layer}')
    _mi.GenesisAPI._VOF()
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_post_hooks,value=1,mode=user"
    )
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_pre_hooks,value=1,mode=user"
    )
    _mi.GenesisAPI._VON()


# ═══════════════════════════════════════════
# Step 级别 SVG 生成
# ═══════════════════════════════════════════

def _get_svg_data(job: str, step: str, layer_names: list,
                  dwg: Any, profile_flag: int = 0,
                  break_sr: str = "") -> List:
    """为一个 Step 生成 SVG defs"""
    step_list = []
    datums = _mi.GenesisAPI.DO_info(
        f'-t step -e {job}/{step} -d DATUM', "mm"
    )
    transform = f"translate({0 - datums.get('gDATUMy', 0)},"
    transform += f" {0 - datums.get('gDATUMx', 0)})"

    dwg_step = dwg.g(
        transform=transform,
        id="_".join(["step", step, layer_names[0]])
    )

    all_steps = _get_repeat(job, step)
    sr_list = [[], []]

    for item in all_steps:
        mirrorf = 1
        if item[4] == "yes":
            mirrorf = -1
        transform_info = (
            f"scale(1,{mirrorf}) rotate({item[3]})"
        )
        key = "_".join([
            "step", item[0], str(item[3]),
            item[4], layer_names[0]
        ])
        if key not in sr_list[1]:
            sr_list[1].append(key)
            dwg_sr = dwg.g(id=key)
            dwg_sr.add(dwg.use(
                href="_".join(["#step", item[0], layer_names[0]]),
                insert=(0, 0), transform=transform_info
            ))
            sr_list[0].append(dwg_sr)
        dwg_step.add(dwg.use(
            href="".join(["#", key]),
            insert=(item[2], item[1])
        ))

    # 添加层图形数据
    if _mi.print_config[0]:
        _mi.GenesisAPI.open_step(job, step)
        _mi.GenesisAPI._VOF()
        _mi.GenesisAPI._COM(
            "config_edit,name=gen_line_skip_post_hooks,value=4,mode=user"
        )
        _mi.GenesisAPI._COM(
            "config_edit,name=gen_line_skip_pre_hooks,value=4,mode=user"
        )
        _mi.GenesisAPI._COM(
            "config_edit,name=edt_decompose_overlap_method,value=2,mode=user"
        )
        _mi.GenesisAPI._COM(
            "config_edit,name=edt_decompose_overlap_size,value=1,mode=user"
        )
        _mi.GenesisAPI._VON()
        _mi.GenesisAPI._COM('disp_off')

        _color_type["col"] = 0
        for layer_name in layer_names:
            if _mi.print_config[0]:
                pdf_layer = layer_name + _mi.print_config[3]
                _process_layer_for_svg(job, step, layer_name,
                                       pdf_layer, dwg,
                                       layer_names, break_sr)

            # 提取特征数据
            features_spec = (
                f'-t layer -e {job}/{step}/{pdf_layer} '
                f'-d FEATURES{break_sr}'
            )
            features = _mi.GenesisAPI.get_features(features_spec)
            _add_svg_data(job, step, dwg, dwg_step,
                          features, "", layer_name)

        _mi.GenesisAPI._COM('disp_on')

    # 添加 profile
    if profile_flag:
        features_spec = f'-t step -e {job}/{step} -d PROF'
        profiles = _mi.GenesisAPI.get_features(features_spec)
        dwg_profile = dwg.g(id="profile", opacity="0.6")
        _add_svg_data(job, step, dwg, dwg_profile, profiles)
        dwg_step.add(dwg_profile)

    sr_list[0].append(dwg_step)
    return sr_list[0]


def _process_layer_for_svg(job: str, step: str, layer_name: str,
                           pdf_layer: str, dwg: Any,
                           layer_names: list, break_sr: str) -> None:
    """处理单层的 SVG 渲染流程"""
    # 创建临时层并合并
    _mi.GenesisAPI._VOF()
    _mi.GenesisAPI._COM(f'delete_layer,layer={pdf_layer}')
    _mi.GenesisAPI._COM(
        f'create_layer,layer={pdf_layer},context=misc,'
        f'type=signal,polarity=positive,ins_layer='
    )
    _mi.GenesisAPI._COM(
        f"merge_layers,source_layer={layer_name},"
        f"dest_layer={pdf_layer},invert=no"
    )
    _mi.GenesisAPI._COM(
        f'affected_layer,name={pdf_layer},mode=single,affected=yes'
    )

    # 过滤文本
    _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
    _mi.GenesisAPI._COM("adv_filter_reset,filter_name=popup")
    _mi.GenesisAPI._COM(
        "filter_set,filter_name=popup,"
        "update_popup=no,feat_types=text"
    )
    _mi.GenesisAPI._COM(
        "adv_filter_set,filter_name=popup,"
        "update_popup=yes,fontname=standard"
    )

    # 简化表面
    _modify_surface(job, step, pdf_layer)

    # 删除小线条
    _remove_pad_line(pdf_layer)

    # 处理 symbol
    _mi.GenesisAPI.get_features(
        f'-t layer -e {job}/{step}/{pdf_layer} -d FEATURES'
    )
    _get_symbol_count(job, step, pdf_layer)

    # 清理解剖
    _mi.GenesisAPI._COM('affected_layer,mode=all,affected=no')
    _mi.GenesisAPI._COM(
        f'affected_layer,name={pdf_layer},mode=single,affected=yes'
    )
    _mi.GenesisAPI._COM("sel_design2rout,det_tol=1,con_tol=1,rad_tol=1.1")
    _mi.GenesisAPI._COM('sel_decompose,overlap=yes')
    _mi.GenesisAPI._COM(
        "sel_clean_surface,accuracy=1,clean_size=3,"
        "clean_mode=x_and_y,max_fold_len=5"
    )

    _mi.GenesisAPI._VOF()
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_post_hooks,value=1,mode=user"
    )
    _mi.GenesisAPI._COM(
        "config_edit,name=gen_line_skip_pre_hooks,value=1,mode=user"
    )
    _mi.GenesisAPI._COM(
        "config_edit,name=edt_decompose_overlap_method,value=1,mode=user"
    )
    _mi.GenesisAPI._COM(
        "config_edit,name=edt_decompose_overlap_size,"
        "value=1.62,mode=user"
    )
    _mi.GenesisAPI._VON()


def _modify_surface(job: str, step: str, pdf_layer: str) -> None:
    """清理表面空洞"""
    _mi.GenesisAPI._VOF()
    nnns = []
    for nnn in range(6):
        features = _mi.GenesisAPI.get_features(
            f'-t layer -e {job}/{step}/{pdf_layer} '
            f'-d FEATURES -o feat_index'
        )
        _get_imp_dist(features, nnn)

        sdist = {}
        gfkey = ""
        for line in features:
            if line.startswith("#"):
                if "#S P" in line and line[1].isdigit():
                    parts = line.split("#")
                    if (len(parts) > 2 and
                            parts[2].startswith("S P") and
                            parts[1].strip().isdigit()):
                        gfkey = parts[1].strip()
                        sdist[gfkey] = [0, 0]
                elif "#S N" in line and line[1].isdigit():
                    gfkey = ""
                elif "#OB " in line and gfkey:
                    parts = line.split("#")
                    if (len(parts) > 2 and
                            parts[2].startswith("OB ") and
                            " H" in parts[2]):
                        if gfkey in sdist:
                            sdist[gfkey][1] += 1
                    elif (len(parts) > 2 and
                          parts[2].startswith("OB ") and
                          " I" in parts[2]):
                        if gfkey in sdist:
                            sdist[gfkey][0] += 1

        min_holes = 0
        if sdist:
            candidates = [
                sdist[x][1] for x in sdist
                if sdist[x][0] < 2 and
                sdist[x][1] > 200 and
                sdist[x][1] not in nnns
            ]
            min_holes = max(candidates) if candidates else 0

        if min_holes == 0:
            break
        nnns.append(min_holes)

        _mi.GenesisAPI._COM("adv_filter_reset,filter_name=popup")
        _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
        _mi.GenesisAPI._COM(
            "filter_set,filter_name=popup,"
            "update_popup=no,polarity=positive"
        )
        _mi.GenesisAPI._COM(
            "filter_set,filter_name=popup,"
            "update_popup=no,feat_types=surface"
        )
        _mi.GenesisAPI._COM(
            f"adv_filter_set,filter_name=popup,"
            f"update_popup=yes,srf_values=yes,min_islands=0,"
            f"max_islands=1,min_holes={min_holes},"
            f"max_holes={min_holes},min_edges=0,max_edges=0"
        )
        _mi.GenesisAPI._COM(
            f"sel_ref_feat,layers={pdf_layer},use=filter,"
            f"mode=disjoint,pads_as=shape,"
            f"f_types=line\\;pad\\;surface\\;arc\\;text,"
            f"polarity=negative,include_syms=,exclude_syms="
        )
        _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
        _mi.GenesisAPI._COM("adv_filter_reset,filter_name=popup")
        _mi.GenesisAPI._COM('get_select_count')
        count = int(_mi.GenesisAPI._COMANS())

        if count < 1:
            continue

        _process_surface_mod(job, step, pdf_layer)

    _mi.GenesisAPI._VOF()


def _process_surface_mod(job: str, step: str, pdf_layer: str) -> None:
    """处理表面修改"""
    mod = pdf_layer + "+++"
    mod_a = mod + "a"
    mod_b = mod + "b"

    _mi.GenesisAPI._VOF()
    for layer in (mod, mod_a, mod_b):
        _mi.GenesisAPI._COM(f'delete_layer,layer={layer}')
        _mi.GenesisAPI._COM(
            f'create_layer,layer={layer},context=misc,'
            f'type=signal,polarity=positive,ins_layer='
        )

    _mi.GenesisAPI._COM(
        f'sel_move_other,target_layer={mod},invert=no'
    )
    _mi.GenesisAPI._COM("clear_highlight")
    _mi.GenesisAPI._COM("sel_clear_feat")
    _mi.GenesisAPI._COM('affected_layer,mode=all,affected=no')
    _mi.GenesisAPI._COM(
        f'affected_layer,name={mod},mode=single,affected=yes'
    )
    _mi.GenesisAPI._COM(
        f"sel_break_isl_hole,islands_layer={mod_a},"
        f"holes_layer={mod_b}"
    )
    status = _mi.GenesisAPI._STATUS()
    _mi.GenesisAPI._COM('affected_layer,mode=all,affected=no')

    if status == 0:
        _mi.GenesisAPI._COM(
            f'affected_layer,name={mod_b},mode=single,affected=yes'
        )
        _mi.GenesisAPI._COM(
            "sel_cont2pad,match_tol=1,"
            "restriction=Symmetric\\;Standard\\;Rotated,"
            "min_size=5,max_size=100,suffix=+++"
        )
        _mi.GenesisAPI._COM('affected_layer,mode=all,affected=no')
        _mi.GenesisAPI._COM(
            f"merge_layers,source_layer={mod_b},"
            f"dest_layer={mod_a},invert=yes"
        )
    else:
        _mi.GenesisAPI._COM(
            f"merge_layers,source_layer={mod},"
            f"dest_layer={mod_a},invert=no"
        )

    _mi.GenesisAPI._COM(
        f"merge_layers,source_layer={pdf_layer},"
        f"dest_layer={mod_a},invert=no"
    )
    _mi.GenesisAPI._COM(f'delete_layer,layer={pdf_layer}')
    _mi.GenesisAPI._COM(
        f'create_layer,layer={pdf_layer},context=misc,'
        f'type=signal,polarity=positive,ins_layer='
    )
    _mi.GenesisAPI._COM(
        f"merge_layers,source_layer={mod_a},"
        f"dest_layer={pdf_layer},invert=no"
    )
    for layer in (mod, mod_a, mod_b, mod_b + "+++"):
        _mi.GenesisAPI._COM(f'delete_layer,layer={layer}')
    _mi.GenesisAPI._COM(
        f'affected_layer,name={pdf_layer},mode=single,affected=yes'
    )


def _get_imp_dist(features: list, nnn: int) -> None:
    """收集阻抗分布"""
    if nnn:
        return
    tmp = []
    for line in features:
        if not line.startswith("#"):
            continue
        if not line[1:2].isdigit():
            continue
        attrs = line.strip().split(";")
        imp = _get_imp_info(attrs)
        if imp:
            tmp.append(imp)
    tmp = list(set(tmp))
    for imp in tmp:
        if imp not in _color_dist["imp"]:
            _color_dist["imp"].append(imp)


def _remove_pad_line(pdf_layer: str) -> None:
    """清理 PAD 中的线状伪影"""
    _mi.GenesisAPI._COM(
        "chklist_single,action=valor_dfm_nfpr,show=no"
    )
    _mi.GenesisAPI._COM(
        "chklist_cupd,chklist=valor_dfm_nfpr,nact=1,params="
        "((pp_layer=.affected)(pp_delete=Duplicate\\;Covered)"
        "(pp_work=Copper)(pp_drill=)"
        "(pp_non_drilled=No)(pp_in_selected=All)"
        "(pp_remove_mark=Remove)),mode=regular"
    )
    _mi.GenesisAPI._COM(
        "chklist_run,chklist=valor_dfm_nfpr,nact=1,area=global"
    )
    _mi.GenesisAPI._COM(
        "chklist_close,chklist=valor_dfm_nfpr,mode=hide"
    )

    # 清理覆盖线条
    _mi.GenesisAPI._COM(
        "chklist_single,action=valor_dfm_nflr,show=no"
    )
    _mi.GenesisAPI._COM(
        "chklist_cupd,chklist=valor_dfm_nflr,nact=1,params="
        "((pp_layer=.affected)(pp_min_line=0)(pp_max_line=20)"
        "(pp_margin=1)(pp_remove_item=Line\\;Arc)"
        "(pp_delete=Covered)(pp_work=Copper)"
        "(pp_remove_mark=Remove)),mode=regular"
    )
    _mi.GenesisAPI._COM(
        "chklist_run,chklist=valor_dfm_nflr,nact=1,area=global"
    )
    _mi.GenesisAPI._COM(
        "chklist_close,chklist=valor_dfm_nflr,mode=hide"
    )

    _mi.GenesisAPI._COM("sel_design2rout,det_tol=1,con_tol=1,rad_tol=0.5")
    _mi.GenesisAPI._COM(f'delete_layer,layer={pdf_layer}+++')


def _get_symbol_count(job: str, step: str,
                      pdf_layer: str) -> Dict[str, str]:
    """统计并优化高密度 symbol"""
    try:
        info = _mi.GenesisAPI.DO_info(
            f'-t layer -e {job}/{step}/{pdf_layer} -d SYMS_HIST'
        )
    except Exception as e:
        print(f"[WARN] calculate_limits SYMS_HIST {job}/{step}/{pdf_layer}: {e}")
        info = {}

    if "gSYMS_HISTsymbol" not in info:
        return {}

    symbols = {}
    names = info['gSYMS_HISTsymbol']
    counts = info['gSYMS_HISTpad']
    for i in range(len(names)):
        if counts[i] <= 0:
            continue
        symbols[str(names[i])] = counts[i]

    new_symbols = _optimize_high_density_symbols(
        job, step, pdf_layer, symbols
    )
    return new_symbols


def _optimize_high_density_symbols(job: str, step: str,
                                   pdf_layer: str,
                                   symbols: dict) -> dict:
    """将高密度简单 symbol 优化为自定义符号"""
    if not symbols:
        return {}

    rad_tol = 0.5 if _mi.print_config[11] else 0.25
    mod = f"sym_{pdf_layer}+"

    _mi.GenesisAPI._COM('affected_layer,mode=all,affected=no')
    _mi.GenesisAPI._COM(f'delete_layer,layer={mod}')
    _mi.GenesisAPI._COM(
        f'create_layer,layer={mod},context=misc,'
        f'type=signal,polarity=positive,ins_layer='
    )
    _mi.GenesisAPI._COM(
        f'affected_layer,name={mod},mode=single,affected=yes'
    )

    new_symbols = {}
    for name in list(symbols.keys())[:30]:  # 限制处理数量
        _mi.GenesisAPI._COM('sel_delete')
        _mi.GenesisAPI._COM(
            f"add_pad,attributes=no,x=0,y=0,"
            f"symbol={name},polarity=positive"
        )
        try:
            _mi.GenesisAPI._COM("sel_break")
            syms = _mi.GenesisAPI.DO_info(
                f"-t layer -e {job}/{step}/{mod} -d FEAT_HIST", "mm"
            )
            symbc = syms.get('gFEAT_HISTtotal', 0)
        except Exception as e:
            print(f"[WARN] get_symbol_count {job}/{step}/{mod}: {e}")
            symbc = 0

        if symbols[name] * symbc > 1000 and symbc > 2:
            new_name = f"new{name}-{time.time()}"
            _mi.GenesisAPI._COM(
                f'sel_contourize,accuracy={rad_tol},'
                f'break_to_islands=yes,clean_hole_size=1.5,'
                f'clean_hole_mode=x_or_y'
            )
            _mi.GenesisAPI._COM(
                "sel_clean_surface,accuracy=1,clean_size=3,"
                "clean_mode=x_and_y,max_fold_len=5"
            )
            _mi.GenesisAPI._COM('sel_decompose,overlap=yes')
            _mi.GenesisAPI._COM(
                "sel_clean_surface,accuracy=1,clean_size=3,"
                "clean_mode=x_and_y,max_fold_len=5"
            )
            _mi.GenesisAPI._COM(
                f"sel_create_sym,symbol={new_name},"
                f"x_datum=0,y_datum=0,delete=yes"
            )
            if _mi.GenesisAPI._STATUS() == 0:
                new_symbols[name] = new_name

    _mi.GenesisAPI._COM(f'delete_layer,layer={mod}')
    _mi.GenesisAPI._COM(
        f'affected_layer,name={pdf_layer},mode=single,affected=yes'
    )

    # 替换原始 symbol
    for old_name, new_name in new_symbols.items():
        _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
        _mi.GenesisAPI._COM(
            "filter_set,filter_name=popup,"
            "update_popup=no,feat_types=pad"
        )
        _mi.GenesisAPI._COM(
            f"filter_set,filter_name=popup,"
            f"update_popup=no,include_syms={old_name}"
        )
        _mi.GenesisAPI._COM('filter_area_strt')
        _mi.GenesisAPI._COM(
            'filter_area_end,layer=,filter_name=popup,'
            'operation=select,area_type=none,'
            'inside_area=no,intersect_area=no'
        )
        _mi.GenesisAPI._COM('filter_reset,filter_name=popup')
        _mi.GenesisAPI._COM('get_select_count')
        if _mi.GenesisAPI._COMANS() != '0':
            _mi.GenesisAPI._COM(
                f"sel_change_sym,symbol={new_name},reset_angle=no"
            )
        _mi.GenesisAPI._COM("clear_highlight")
        _mi.GenesisAPI._COM("sel_clear_feat")

    return new_symbols


# ═══════════════════════════════════════════
# 全局 LIMITS 计算
# ═══════════════════════════════════════════

def calculate_limits(job: str, step: str,
                     layers: List[str]) -> None:
    """计算各层的图形范围（用于 SVG 布局）

    结果存储在 _All_LIMITS 中
    """
    global _All_LIMITS
    _All_LIMITS = {}

    _init_symbol_styles()
    all_steps = _get_step_info(job, step)[::-1] + [step]

    for layer_name in layers:
        _All_LIMITS[layer_name] = [[], [], 100]

        for stp in all_steps:
            try:
                lims = _mi.GenesisAPI.DO_info(
                    f'-t layer -e {job}/{stp}/{layer_name} '
                    f'-d LIMITS', "mm"
                )
            except Exception as e:
                print(f"[WARN] get_layer_limits {job}/{stp}/{layer_name}: {e}")
                lims = {}

            if not lims:
                continue

            xmin = lims.get('gLIMITSxmin', 0)
            ymin = lims.get('gLIMITSymin', 0)
            xmax = lims.get('gLIMITSxmax', 0)
            ymax = lims.get('gLIMITSymax', 0)

            _All_LIMITS[layer_name][0].append([xmin, ymin])
            _All_LIMITS[layer_name][1].append([xmax, ymax])

        if _All_LIMITS[layer_name][0]:
            xs = [x[0] for x in _All_LIMITS[layer_name][0]]
            ys = [x[1] for x in _All_LIMITS[layer_name][0]]
            _All_LIMITS[layer_name][0] = [min(xs), min(ys)]

        if _All_LIMITS[layer_name][1]:
            xs = [x[0] for x in _All_LIMITS[layer_name][1]]
            ys = [x[1] for x in _All_LIMITS[layer_name][1]]
            _All_LIMITS[layer_name][1] = [max(xs), max(ys)]


# ═══════════════════════════════════════════
# SVG 文件生成
# ═══════════════════════════════════════════

class SVGGenerator:
    """SVG 图纸生成器

    用法:
        gen = SVGGenerator(job, step)
        files = gen.generate(layers)
    """

    def __init__(self, job: str, step: str):
        self.job = job
        self.step = step
        self._init_globals()

    def _init_globals(self) -> None:
        """初始化全局状态"""
        global _all_symbol_dist, _color_dist, _all_steps_dist
        global _symbols_datas, _mask_info, _All_LIMITS

        _init_symbol_styles()
        _color_dist = {"imp": []}
        _all_steps_dist = {}
        _symbols_datas = {}
        _mask_info = {"tol": 0}
        _All_LIMITS.clear()

    def generate(self, layers: List[str],
                 output_dir: str = "",
                 profile_flag: int = 0,
                 opacity_flag: int = 0) -> Tuple[str, str]:
        """为选中的层生成 SVG 文件

        Args:
            layers:        层名列表
            output_dir:   输出目录（默认 config.SVG_DIR）
            profile_flag: 是否包含成型轮廓
            opacity_flag: 是否高透明度

        Returns:
            (成功消息, 错误消息)
        """
        if svgwrite is None:
            return ("", "svgwrite 未安装")

        if not layers:
            return ("", "没有选中层")

        output_dir = output_dir or config.SVG_DIR
        job_upper = _mi.host_info.get("job_name", self.job).upper()
        out_path = os.path.join(output_dir, job_upper)

        try:
            os.makedirs(out_path, exist_ok=True)
        except Exception:
            pass

        # 生成 SVG
        try:
            svg_list = self._render_svgs(layers, profile_flag, opacity_flag)
        except Exception as e:
            return ("", f"SVG 渲染失败: {e}")

        # 写入文件
        errors = []
        success = []
        for svg_path, dwg in svg_list:
            try:
                dwg.save()
            except Exception as e:
                errors.append(f"{svg_path}: {e}")
            else:
                success.append(os.path.basename(svg_path))
                self._try_convert_pdf(svg_path)

        if errors:
            return (", ".join(success), "\n".join(errors))
        return (", ".join(success), "")

    def _render_svgs(self, layers: List[str],
                     profile_flag: int,
                     opacity_flag: int) -> List[Tuple[str, Any]]:
        """渲染 SVG 文件列表"""
        job_upper = _mi.host_info.get("job_name", self.job).upper()
        out_path = os.path.join(
            config.SVG_DIR if config.SVG_DIR else "/tmp",
            job_upper
        )
        os.makedirs(out_path, exist_ok=True)

        # 按页码分组
        layer_map = self._group_layers_by_page(layers)

        results = []
        for page_num in sorted(layer_map.keys()):
            page_layers = layer_map[page_num]
            svg_file = os.path.join(out_path, f"{page_layers[0]}.svg")

            dwg = svgwrite.Drawing(
                svg_file,
                size=(str(config.MIN_SVG_WIDTH),
                      str(config.MIN_SVG_HEIGHT))
            )

            # 为每层添加 defs
            all_size = self._add_layer_defs(
                dwg, page_layers, profile_flag,
                opacity_flag, page_num
            )

            # 调整 SVG 尺寸
            dwg['width'] = str(
                config.MIN_SVG_WIDTH + _mi.print_config[9] + 100
            )
            dwg['height'] = str(all_size + 100)

            results.append((svg_file, dwg))

        # 清理临时层
        _mi.GenesisAPI.delete_tmp_layer()

        return results

    def _group_layers_by_page(self, layers: List[str]) -> Dict[int, List[str]]:
        """按页码分组层"""
        result = {}
        for lay in layers:
            try:
                page = int(
                    _mi.load_dict_all.get("layer_file", {}).get(lay, "1").strip()
                )
            except (ValueError, TypeError):
                page = 1
            result.setdefault(page, []).append(lay)
        return result

    def _add_layer_defs(self, dwg: Any, layers: List[str],
                        profile_flag: int, opacity_flag: int,
                        page_num: int) -> int:
        """为层添加 SVG defs"""
        break_feat = " -o break_feat"

        for layer_name in layers:
            _get_symbols(self.job, self.step, [layer_name],
                         dwg, break_feat)

        all_size = 0
        for layer_name in layers:
            # 获取变换信息
            lim_xy, vangle, scale_xy, mirror, fnum = \
                self._calc_infodata(layer_name)
            transform = self._build_transform(
                vangle, mirror, scale_xy, lim_xy
            )

            # 生成 defs
            defs_list = _get_svg_data(
                self.job, self.step, [layer_name],
                dwg, profile_flag, break_feat
            )

            # 添加 symbol
            syms = []
            if layer_name in _symbols_datas:
                for key in _symbols_datas[layer_name]:
                    if _symbols_datas[layer_name][key][2]:
                        syms.append(_symbols_datas[layer_name][key])
            for s in syms:
                dwg.defs.add(s[1])

            # 添加 step defs
            for d in defs_list:
                dwg.defs.add(d)

            # 添加标记和注解
            info_data = (lim_xy, vangle, scale_xy, mirror, fnum)
            layer_size = _add_marks_block(
                dwg, layer_name, info_data, transform, page_num
            )
            all_size = max(all_size, layer_size)

        return all_size

    def _calc_infodata(self, layer_name: str) -> tuple:
        """计算层的变换参数"""
        lim_xy = self._get_layer_limits(layer_name)
        prof = _All_LIMITS.get(layer_name, [None, None, 100])

        # 计算缩放
        scale_xy = 1.0
        if prof[0] and prof[1]:
            xsize = abs(prof[1][0] - prof[0][0])
            if xsize > 0:
                scale_xy = _min_limits[0] / xsize if (
                    _min_limits[0] / xsize < 1.0
                ) else 2.0

        vangle = 0
        mirror = 0

        # 计算每页数量
        fnum = 2
        if lim_xy:
            xscale = (lim_xy[2] - lim_xy[1] - 50) / _min_limits[0]
            if xscale < 2:
                fnum = 1

        return (lim_xy, vangle, scale_xy, mirror, fnum)

    def _get_layer_limits(self, layer_name: str) -> list:
        """获取层的变换边界"""
        prof = _All_LIMITS.get(layer_name, [None, None, 100])

        lim_xy = [0, 0, config.MIN_SVG_WIDTH, 0, 0]
        if prof[0] and prof[1]:
            xsize = abs(prof[1][0] - prof[0][0])
            ysize = abs(prof[1][1] - prof[0][1])
            scale = _min_limits[0] / xsize if xsize > 0 else 1.0

            lim_xy[2] = (xsize * scale) if (
                _min_limits[0] / xsize < 1.0
            ) else (xsize * 2)
            lim_xy[3] = (ysize * scale) if (
                _min_limits[0] / xsize < 1.0
            ) else (ysize * 2)
            lim_xy[4] = 50
        else:
            lim_xy[2] = config.MIN_SVG_WIDTH
            lim_xy[3] = config.MIN_SVG_HEIGHT
            lim_xy[4] = 50

        return lim_xy

    def _build_transform(self, vangle: float, mirror: int,
                         scale_xy: float, lim_xy: list) -> str:
        """构建 SVG transform 字符串"""
        return f"scale({scale_xy},{scale_xy}) translate(0,0) rotate(0)"

    def _try_convert_pdf(self, svg_path: str) -> None:
        """尝试将 SVG 转换为 PDF"""
        if cairosvg is None:
            return
        pdf_path = svg_path.replace('.svg', '.pdf')
        try:
            cairosvg.svg2pdf(url=svg_path, write_to=pdf_path)
        except Exception as e:
            print(f"[WARN] SVG → PDF 转换失败 ({os.path.basename(svg_path)}): {e}", file=sys.stderr)


# ═══════════════════════════════════════════
# 标记和注解渲染
# ═══════════════════════════════════════════

def _add_marks_block(dwg: Any, layer_name: str,
                     info_data: tuple, transform: str,
                     page_num: int) -> int:
    """添加标记和注解 block"""
    (lim_xy, vangle, scale_xy, mirror, fnum) = info_data

    # 获取 note 数据
    marklist, notelist, all_size, hotypec = \
        _get_notes_data(layer_name, info_data)

    # 添加注解
    dwg_note = _add_notes_block(dwg, notelist, hotypec, layer_name)

    # 添加总 group
    dwg_all = dwg.g(id=f'f_all_data_{layer_name}')
    dwg_all.add(dwg.use(
        href="_".join(["#step", "cad", layer_name]),
        insert=(0, 0), transform=transform
    ))

    # 添加表头
    layer_type_info = _get_layer_display_name(layer_name)
    form_txt = (
        f"{_mi.host_info.get('job_name', '').upper()} "
        f"{layer_type_info} "
        f"{time.strftime('%Y/%m/%d', time.localtime())} "
    ).split()
    fx = 0
    positions = [0, 0, 0, 0, 0]
    for i in range(min(4, len(form_txt))):
        positions[i] = fx
        fx += len(form_txt[i]) * 20 + 60
    fx -= 60
    offset = (1000 - fx) / 2
    for i in range(min(4, len(form_txt))):
        positions[i] += offset
        _add_text(dwg, dwg_all, form_txt[i],
                  positions[i], positions[i],
                  0 - lim_xy[4] - 20.5,
                  angle=0, fill="black", font_size=40, move_x=2)

    # 添加注解
    if dwg_note:
        note_transform = (
            f"scale(1,1) translate({-50}, {lim_xy[3] + 60.5}) rotate(0)"
        )
        dwg_all.add(dwg.use(
            href=f"#f_note_data_{layer_name}",
            insert=(0, 0), transform=note_transform
        ))

    # 添加测量标记
    if _mi.print_config[10] == "标板外":
        _calc_marklist(dwg, dwg_all, marklist, lim_xy)
    else:
        add_xy_log = []
        for mark in marklist:
            _add_mark(dwg, dwg_all, mark[0], mark[1],
                      mark[2], mark[3], [], add_xy_log)

    dwg.defs.add(dwg_all)

    # 添加到主文档
    pos_transform = (
        f"scale(1,1) translate({(page_num % fnum) * lim_xy[2] + lim_xy[4]}, "
        f"{(page_num // fnum) * all_size + lim_xy[4] + 20.5}) rotate(0)"
    )
    dwg.add(dwg.use(
        href=f"#f_all_data_{layer_name}",
        insert=(0, 0), transform=pos_transform
    ))

    return all_size


def _get_layer_display_name(layer_name: str) -> str:
    """获取层的显示名称"""
    try:
        info = _mi.GenesisAPI.DO_info(
            f'-t matrix -e {_mi.host_info.get("job_name", "")}/matrix '
            f'-m script -d ROW'
        )
    except Exception as e:
        print(f"[WARN] PDF 层名获取失败 ({layer_name}): {e}", file=sys.stderr)
        return layer_name

    names = info.get('gROWname', [])
    layer_types = info.get('gROWlayer_type', [])
    sides = info.get('gROWside', [])
    polarities = info.get('gROWpolarity', [])

    for i in range(len(names)):
        if names[i] != layer_name:
            continue

        if layer_types[i] in ('signal', 'power_ground'):
            if sides[i] == 'inner':
                return f'内层[{layer_name}]'
            elif sides[i] == 'top':
                return f'线路TOP面[{layer_name}]'
            elif sides[i] == 'bottom':
                return f'线路BOT面[{layer_name}]'
        elif layer_types[i] == 'solder_mask':
            if sides[i] == 'top':
                return f'绿油TOP面[{layer_name}]'
            elif sides[i] == 'bottom':
                return f'绿油BOT面[{layer_name}]'
        elif layer_types[i] == 'silk_screen':
            if sides[i] == 'top':
                return f'字符TOP面[{layer_name}]'
            elif sides[i] == 'bottom':
                return f'字符BOT面[{layer_name}]'

    return layer_name


def _get_notes_data(layer_name: str,
                    info_data: tuple) -> tuple:
    """获取层的 note 数据"""
    from . import mi_extractor as _mi

    (lim_xy, vangle, scale_xy, mirror, fnum) = info_data

    notelist = []
    marklist = []
    all_size = config.MIN_SVG_HEIGHT

    # 尝试构建 notelist
    try:
        step_notes = _mi.load_dict_all.get("step_note", {})
        cad_notes = step_notes.get("cad", {})
        layer_notes = cad_notes.get(layer_name, [])
        if layer_notes:
            notelist = [config.HO_TYPES[:]] + [
                [note[0], note[1], note[3],  # 序号, 类型, 标记
                 note[4], note[5], note[6],  # 成品值, 原稿值, 阻抗值
                 note[9]]                     # 备注
                for note in layer_notes
            ]
    except Exception as e:
        print(f"[WARN] 标记参数解析失败 ({layer_name}): {e}", file=sys.stderr)

    # 排序标记
    tmp_marklist = []
    for mark in marklist:
        (ab, rd) = _geom.get_angle(mark[0][0], mark[0][1])
        tmp_marklist.append([rd, mark])
    tmp_marklist.sort()
    marklist = [x[1] for x in tmp_marklist]

    # 计算总高度
    yyyy = 0
    if notelist:
        yyyy += 10
        for row in notelist:
            klist_sizes = _get_note_line_height(row, config.HO_TYPE_COLS, (200, 26))
            yyyy += klist_sizes[1][1]

    all_size = (
        lim_xy[3] + yyyy + lim_xy[4] + 60.5 + 20.5 +
        max(int(_mi.print_config[9] or 50), 50)
    )
    if all_size < config.MIN_SVG_HEIGHT:
        all_size = config.MIN_SVG_HEIGHT

    return (marklist, notelist, all_size, config.HO_TYPE_COLS[:])


def _add_notes_block(dwg: Any, notelist: list,
                     hotypec: list, layer_name: str) -> Any:
    """添加 annotation block"""
    err_imp = _mi.check_imp_note([layer_name])

    if not notelist and not err_imp:
        return None

    dwg_note = dwg.g(id=f'f_note_data_{layer_name}')
    lf = 0
    if notelist:
        lf = _add_notes_grid(dwg, dwg_note, notelist, hotypec)

    if err_imp:
        err_lines = ["阻抗未标提醒,请做好标注再生成图纸:"] + err_imp.split()
        for line in err_lines:
            _add_text(dwg, dwg_note, line, 50, 50,
                      lf + 15, angle=0, fill="red",
                      font_size=9, move_x=2)
            lf += 15

    return dwg_note


def _add_notes_grid(dwg: Any, parent: Any,
                    notelist: list, hotypec: list) -> int:
    """绘制 note 表格网格"""
    cell_size = (200, 26)
    y = 0
    for row in notelist:
        x = 0
        klist_sizes = _get_note_line_height(row, hotypec, cell_size)
        for col_idx, val in enumerate(row):
            w = (hotypec[col_idx] if col_idx < len(hotypec)
                 else hotypec[-1])
            h = klist_sizes[1][1]
            fill = "black"

            move_x = 0.4
            if val.startswith("注解:"):
                w = sum(hotypec[col_idx:])
                move_x = 2
                fill = "red"
            elif (row[1] == "制作指示" and
                  len(row) == 4 and col_idx == 3):
                w = sum(hotypec[col_idx:])
                move_x = 2
            elif y == 0 or col_idx == 1:
                move_x = 1
                if y == 0 and col_idx in (3, 4, 5):
                    move_x = 0.6
                    if col_idx == 5:
                        move_x = 0.8
                elif col_idx == 1:
                    move_x = 3
            elif col_idx in (3, 4, 5):
                move_x = 0.5
            elif col_idx == 6:
                move_x = 2

            parent.add(dwg.rect(
                insert=(x, y), size=(w, h),
                class_="markgf"
            ))

            font_size = 20
            if move_x == 2 and len(klist_sizes[0]) > 1:
                for li, kb in enumerate(klist_sizes[0]):
                    _add_text(dwg, parent, kb,
                              x, x + w, y + li * cell_size[1],
                              fill=fill, font_size=font_size, move_x=move_x)
            else:
                _add_text(dwg, parent, str(val),
                          x, x + w, y + (len(klist_sizes[0]) - 1) * cell_size[1] * 0.5,
                          fill=fill, font_size=font_size, move_x=move_x)

            x += w
        y += klist_sizes[1][1]

    return y


def _get_note_line_height(row: list, hotypec: list,
                          cell_size: tuple,
                          font_size: int = 20) -> tuple:
    """计算 note 行需要多少行高"""
    sizes = [hotypec[-1], cell_size[1]]
    if row[0].startswith("注解:"):
        sizes = [sum(hotypec), cell_size[1]]
    elif row[1] == "制作指示":
        sizes = [sum(hotypec[3:]), cell_size[1]]

    max_chars = int(sizes[0] / font_size)
    if len(str(row[-1])) < max_chars:
        return ([str(row[-1])], sizes)

    # 换行
    lines = {}
    lnf = 0
    gfk = 0
    for ch in str(row[-1]):
        w = font_size * (0.5 if ch.isascii() else 1.0)
        lnf += w
        if lnf > (sizes[0] - 3.1):
            lnf = w
            gfk += 1
        lines.setdefault(gfk, "")
        lines[gfk] += ch

    keys = sorted(lines.keys())
    line_list = [lines[k] for k in keys]
    sizes[1] = cell_size[1] * len(line_list)
    return (line_list, sizes)


def _add_text(dwg: Any, parent: Any, text: str,
              x1: float, x2: float, y: float,
              angle: float = 0, fill: str = "black",
              font_size: int = 20, move_x: float = 1,
              opacity: float = 1.0) -> None:
    """添加居中文本"""
    if move_x == 2:
        text_anchor = "start"
        x_pos = x1 + 2
    elif move_x >= 1:
        text_anchor = "middle"
        x_pos = (x1 + x2) / 2
    else:
        text_anchor = "middle"
        x_pos = (x1 + x2) / 2

    parent.add(dwg.text(
        str(text),
        insert=(x_pos, y + font_size * 0.35),
        fill=fill,
        font_size=str(font_size),
        text_anchor=text_anchor,
        opacity=str(opacity) if opacity < 1.0 else None,
    ))


def _calc_marklist(dwg: Any, parent: Any,
                   marklist: list, lim_xy: list) -> None:
    """计算标注位置并添加到 SVG"""
    limxf = [
        [0, [0, 0], [lim_xy[2], 0], 60, [], 0],
        [1, [lim_xy[2], 0], [lim_xy[2], lim_xy[3]], 50, [], 1],
        [2, [lim_xy[2], lim_xy[3]], [0, lim_xy[3]], 60, [], 0],
        [3, [0, lim_xy[3]], [0, 0], 50, [], 1],
    ]

    for mark in marklist:
        tmp = []
        for lim in limxf:
            rd = _geom.get_point_line_distance(mark[0], lim[1:3])
            tmp.append([rd, lim])
        tmp.sort()
        tmp[0][1][4].append([0, mark, [0, 0, 0, 0, 0]])

    for lim in limxf:
        for item in lim[4]:
            if lim[0] in (0, 3):
                item[2][2] = -1
                item[2][4] = -5
                if lim[0] == 3:
                    item[2][3] = -30
                    item[2][4] = 5
            elif lim[0] == 1:
                item[2][2] = -1
                item[2][3] = 15
                item[2][4] = 5

            ax = lim[5]
            if lim[0] in (0, 2):
                item[0] = (round(abs(lim[1][0] - item[1][0][0]) / 2.0) +
                           abs(lim[1][1] - item[1][0][1]) / 1000.0)
                if lim[0] == 0:
                    item[2][0] = item[1][0][0]
                    item[2][1] = lim[1][1] - 20
                else:
                    item[2][0] = item[1][0][0]
                    item[2][1] = lim[1][1] + 20
            else:
                item[0] = (round(abs(lim[1][1] - item[1][0][1]) / 2.0) +
                           abs(lim[1][0] - item[1][0][0]) / 1000.0)
                if lim[0] == 1:
                    item[2][0] = lim[1][0] + 20
                    item[2][1] = item[1][0][1]
                else:
                    item[2][0] = lim[1][0] - 20
                    item[2][1] = item[1][0][1]

        lim[4].sort()
        _distribute_marks(lim)

    for lim in limxf:
        for item in lim[4]:
            _add_mark(dwg, parent, item[1][0], item[1][1],
                      item[1][2], item[1][3], item[2])


def _distribute_marks(lim: list) -> None:
    """分布标记以避免重叠"""
    ax = lim[5]
    spacing = lim[3]

    for pass_num in range(1, 5):
        if lim[0] in (0, 1):
            strxy = lim[1][ax] - 60
            for item in lim[4]:
                if item[2][ax] - strxy < spacing * (0.2 * pass_num):
                    item[2][ax] = strxy + spacing * (0.2 * pass_num)
                strxy = item[2][ax]
            strxy = lim[2][ax] + 60
            for item in reversed(lim[4]):
                if item[2][ax] - strxy > -spacing * (0.4 * pass_num):
                    item[2][ax] = strxy - spacing * (0.4 * pass_num)
                strxy = item[2][ax]
        else:
            strxy = lim[1][ax] + 60
            for item in lim[4]:
                if item[2][ax] - strxy > -spacing * (0.2 * pass_num):
                    item[2][ax] = strxy - spacing * (0.2 * pass_num)
                strxy = item[2][ax]
            strxy = lim[2][ax] - 60
            for item in reversed(lim[4]):
                if item[2][ax] - strxy < spacing * (0.4 * pass_num):
                    item[2][ax] = strxy + spacing * (0.4 * pass_num)
                strxy = item[2][ax]


def _add_mark(dwg: Any, parent: Any,
              xy: tuple, text: str, radius: float,
              fonts: Any, coords: list = None,
              add_xy_log: list = None) -> None:
    """添加单个测量标记"""
    if coords is None:
        coords = []
    if add_xy_log is None:
        add_xy_log = []

    if not coords:
        new_xys = _get_text_xy(xy, radius, add_xy_log)
        style = [0, fonts * new_xys[2], "red"]
    else:
        new_xys = coords
        style = [new_xys[3], fonts * new_xys[2] + new_xys[4], "blue"]

    parent.add(dwg.line(start=new_xys[0:2], end=xy, class_="markgf"))
    parent.add(dwg.circle(center=xy, r=radius * 0.25, class_="markgf"))
    parent.add(dwg.circle(center=xy, r=0.1, fill=style[2], opacity="0.5"))

    _add_text(dwg, parent, text,
              new_xys[0] + style[0], new_xys[0] + style[0],
              new_xys[1] + style[1],
              fill=style[2], font_size=fonts)
    _add_text(dwg, parent, text,
              xy[0], xy[0], xy[1],
              angle=0, move_x=0.5,
              fill=style[2], font_size=1, opacity=0.75)

    add_xy_log.append(list(xy))
    add_xy_log.append(list(new_xys))


def _get_text_xy(new_xy: tuple, radius: float,
                 add_xy_log: list) -> list:
    """寻找不重叠的文本位置"""
    d = 2 * radius
    candidates = [
        [new_xy[0] - d, new_xy[1] - d, -1],
        [new_xy[0] + d, new_xy[1] - d, -1],
        [new_xy[0] + d, new_xy[1] + d, 0],
        [new_xy[0] - d, new_xy[1] + d, 0],
    ]

    for candidate in candidates:
        overlap = 0
        for existing in add_xy_log:
            dist = math.sqrt(
                (candidate[0] - existing[0]) ** 2 +
                (candidate[1] - existing[1]) ** 2
            )
            if dist < (2 * radius):
                overlap += 1
        if overlap == 0:
            return candidate
    return candidates[0]


# ═══════════════════════════════════════════
# 模块导出
# ═══════════════════════════════════════════

__all__ = [
    'SVGGenerator',
    'calculate_limits',
    '_All_LIMITS',
]
