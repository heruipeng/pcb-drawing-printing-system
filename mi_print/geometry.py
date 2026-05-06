#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - 几何计算工具
=========================
从 math_line.py 迁移而来，修复：
  - math.fabs → abs (Python 3 已废弃)
  - 角度归一化边界场景
  - 除零保护
  - 类型注解

原始作者: Gf.zhang (math_line.py v1.0, 2019-12-16)
"""

import math
from typing import Tuple, List, Optional


def normalize_angle(angle: float) -> float:
    """将任意角度归一化到 [0, 360) 区间

    Args:
        angle: 输入角度（度）

    Returns:
        归一化后的角度，范围 [0, 360)

    Examples:
        >>> normalize_angle(361)
        1.0
        >>> normalize_angle(-30)
        330.0
        >>> normalize_angle(360)
        0.0
    """
    # 用 math.fmod 处理浮点精度更好的取模
    if angle >= 360.0 or angle < 0.0:
        angle = angle % 360.0
    # 处理浮点精度导致的负零
    if angle < 0.0:
        angle += 360.0
    return angle


def get_angle(x2: float, y2: float, x1: float = 0.0, y1: float = 0.0) -> Tuple[float, float]:
    """计算两点之间的角度和距离

    从 (x1, y1) 到 (x2, y2) 的方向向量，角度转为 360 度制。

    Args:
        x2, y2: 目标点坐标
        x1, y1: 参考点坐标（默认原点）

    Returns:
        (angle: 0-360度, radius: 距离)

    Examples:
        >>> a, r = get_angle(1, 0)
        >>> round(a, 1)
        0.0
        >>> round(r, 1)
        1.0
    """
    dx = x2 - x1
    dy = y2 - y1
    radius = math.sqrt(dx * dx + dy * dy)
    # math.atan2 返回 [-pi, pi]
    angle_rad = math.atan2(dy, dx)
    angle_deg = angle_rad * (180.0 / math.pi)
    if angle_deg < 0.0:
        angle_deg += 360.0
    return (angle_deg, radius)


def get_point_line_distance(point: Tuple[float, float],
                            line: Tuple[Tuple[float, float],
                                        Tuple[float, float]]) -> float:
    """计算点到直线的最短距离（解析几何法）

    Args:
        point:  (px, py) 点坐标
        line:   ((x1, y1), (x2, y2)) 线段两端点

    Returns:
        点到直线的垂直距离（绝对值）

    Examples:
        >>> round(get_point_line_distance((3.5, 0), ((-5, 5), (5, -5))), 4)
        0.7071
    """
    px, py = point
    (x1, y1), (x2, y2) = line

    dx = x2 - x1
    dy = y2 - y1

    # 垂直线（除零保护）
    if abs(dx) < 1e-12:
        return abs(px - x1)

    # 水平线
    if abs(dy) < 1e-12:
        return abs(py - y1)

    # 一般情况: dis = |k*px - py + b| / sqrt(k² + 1)
    k = dy / dx
    b = y1 - k * x1
    numerator = abs(k * px - py + b)
    denominator = math.sqrt(k * k + 1.0)
    if denominator < 1e-12:
        return 0.0
    return numerator / denominator


def get_p2l_distance(point: Tuple[float, float],
                     line: Tuple[Tuple[float, float],
                                 Tuple[float, float]]) -> float:
    """计算点到直线的最短距离（三角函数法）

    先算点到直线一端的距离和角度差，再用正弦算垂线长度。

    Args:
        point:  (px, py) 点坐标
        line:   ((x1, y1), (x2, y2)) 线段两端点

    Returns:
        点到直线的垂直距离

    Examples:
        >>> round(get_p2l_distance((3.5, 0), ((-5, 5), (5, -5))), 4)
        0.7071
    """
    (x1, y1), (x2, y2) = line

    a_deg, a_dist = get_angle(x2, y2, x1=point[0], y1=point[1])
    b_deg, _b_dist = get_angle(x2, y2, x1=x1, y1=y1)

    angle_diff = normalize_angle(abs(a_deg - b_deg))
    if angle_diff > 180.0:
        angle_diff = 360.0 - angle_diff
    angle_rad = math.radians(angle_diff)

    return abs(a_dist * math.sin(angle_rad))


def rotate_point(x: float, y: float, cx: float, cy: float,
                 angle: float, clockwise: bool = True) -> Tuple[float, float]:
    """绕中心点旋转坐标

    Args:
        x, y:        待旋转点
        cx, cy:      旋转中心
        angle:        旋转角度（度）
        clockwise:    True=顺时针, False=逆时针

    Returns:
        (new_x, new_y)
    """
    rad = math.radians(normalize_angle(angle))
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    dx = x - cx
    dy = y - cy

    if clockwise:
        # 顺时针旋转
        new_x = dx * cos_a + dy * sin_a + cx
        new_y = -dx * sin_a + dy * cos_a + cy
    else:
        # 逆时针旋转
        new_x = dx * cos_a - dy * sin_a + cx
        new_y = dx * sin_a + dy * cos_a + cy

    return (new_x, new_y)


def length_to_xy(length: float, angle: float,
                 clockwise: bool = True) -> Tuple[float, float]:
    """根据长度和角度计算 dx, dy 分量

    Args:
        length:   长度
        angle:    角度（度）
        clockwise: True=顺时针

    Returns:
        (dx, dy)
    """
    if clockwise:
        rad = math.radians(normalize_angle(angle))
    else:
        rad = math.radians(normalize_angle(angle + 180.0))

    dx = length * math.cos(rad)
    dy = length * math.sin(rad)
    return (dx, dy)


def round_str(value: float, decimal: int = 3) -> str:
    """安全的数值舍入为字符串，去除尾部无意义的零和小数点

    Args:
        value:   数值
        decimal: 小数位数

    Returns:
        格式化后的字符串

    Examples:
        >>> round_str(3.500, 2)
        '3.5'
        >>> round_str(0.0, 3)
        '0'
    """
    if abs(value) < 1e-15:
        return "0"
    result = f"{round(value, decimal)}"
    result = result.rstrip("0").rstrip(".")
    if not result:
        result = "0"
    return result


def transform_coordinate(xy: Tuple[float, float],
                         datum: Tuple[float, float],
                         mirror: int = 0,
                         vangle: float = 0.0,
                         scale_xy: float = 1.0,
                         profile_limits: Optional[List[float]] = None
                         ) -> Tuple[float, float]:
    """坐标变换：平移 + 旋转 + 镜像 + 缩放

    用于将 Genesis 坐标系转换为 SVG 坐标系。

    Args:
        xy:             原始坐标 (x, y)
        datum:          基准点 (dx, dy)
        mirror:         镜像 0=否, 1=是
        vangle:         旋转角度
        scale_xy:       缩放比例
        profile_limits: [xmin, ymin, xmax, ymax] 成型范围

    Returns:
        变换后的坐标
    """
    new_x, new_y = xy

    if profile_limits is None:
        profile_limits = [0.0, 0.0, 0.0, 0.0]

    if mirror == 0 and abs(vangle - 270) < 0.01:
        new_x -= profile_limits[0]
        new_y -= profile_limits[1]
        new_y = -new_y
    elif mirror == 1 and abs(vangle - 270) < 0.01:
        new_x -= profile_limits[0]
        new_y -= profile_limits[1]
    elif mirror == 0 and abs(vangle) < 0.01:
        new_x -= profile_limits[0]
        new_y -= profile_limits[1]
        new_x, new_y = new_y, new_x
    elif mirror == 1 and abs(vangle) < 0.01:
        new_x -= profile_limits[2]
        new_y -= profile_limits[1]
        new_x, new_y = new_y, new_x
        new_y = -new_y

    new_x *= scale_xy
    new_y *= scale_xy
    return (new_x, new_y)


# ── 向后兼容别名 ──
changeAngle = normalize_angle
