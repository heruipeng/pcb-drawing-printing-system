#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - CLI 入口
=====================
胜宏科技（惠州）MI 制程指示系统命令行入口。

用法:
  python -m mi_print.main <job_name> [options]

示例:
  # 生成所有层的图纸
  python -m mi_print.main K65308GN238A1 --step cad

  # 指定输出目录
  python -m mi_print.main K65308GN238A1 --output /tmp/mi_output

  # 仅输出指定层
  python -m mi_print.main K65308GN238A1 --layers top,bot
"""

import os
import sys
import argparse
from typing import List

# 确保包路径正确
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from . import config
from . import mi_extractor as _mi
from . import svg_renderer as _svg


def parse_args(args: List[str] = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MI (Manufacturing Instruction) 图纸生成系统 - 胜宏科技",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s H50208GN013A1                    # 生成料号的所有层图纸
  %(prog)s H50208GN013A1 --step cad          # 指定 Step
  %(prog)s H50208GN013A1 --layers c1,s1      # 只输出指定层
  %(prog)s H50208GN013A1 --output /tmp/mi    # 指定输出目录
  %(prog)s H50208GN013A1 --unit mm           # 使用 mm 单位
  %(prog)s H50208GN013A1 --no-pdf            # 不生成 PDF
  %(prog)s H50208GN013A1 --profile           # 包含成型轮廓
        """,
    )

    parser.add_argument(
        "job", nargs="?", default="",
        help="料号名 (13位编码，如 H50208GN013A1)"
    )
    parser.add_argument(
        "--step", "-s", default="cad",
        help="Step 名 (默认: cad)"
    )
    parser.add_argument(
        "--layers", "-l", default="",
        help="指定层名，逗号分隔 (默认: 所有层)"
    )
    parser.add_argument(
        "--output", "-o", default="",
        help="输出目录 (默认: D:\\disk 或 /tmp/mi_svg)"
    )
    parser.add_argument(
        "--unit", "-u", default="mil",
        choices=("mil", "mm", "um"),
        help="单位 (默认: mil)"
    )
    parser.add_argument(
        "--no-pdf", action="store_true",
        help="不生成 PDF (仅 SVG)"
    )
    parser.add_argument(
        "--profile", "-p", action="store_true",
        help="包含成型轮廓线"
    )
    parser.add_argument(
        "--margin", "-m", default="300",
        choices=("0", "100", "200", "300", "500", "600", "800"),
        help="留白大小 (默认: 300)"
    )

    return parser.parse_args(args)


def main(argv: List[str] = None) -> int:
    """CLI 主函数

    Returns:
        0 成功，1 失败
    """
    args = parse_args(argv)

    # 验证料号
    if not args.job:
        print("ERROR: 请指定料号名")
        print("用法: python -m mi_print.main <job_name> [options]")
        return 1

    # 配置
    _mi.print_config[1] = args.unit
    _mi.print_config[0] = 0 if args.no_pdf else 1
    _mi.print_config[9] = args.margin
    if args.output:
        config.SVG_DIR = args.output

    # 初始化主机信息
    _mi.get_host(args.job)
    print(f"料号: {_mi.host_info.get('job_name', args.job)}")
    print(f"Step: {args.step}")
    print(f"单位: {args.unit}")
    print(f"输出: {config.SVG_DIR}")

    # 获取层列表
    try:
        all_layers = _mi.get_layers(args.job)
    except Exception as e:
        print(f"ERROR: 获取层列表失败: {e}")
        return 1

    if not all_layers:
        print("ERROR: 未找到层数据，请确认料号存在且已打开")
        return 1

    # 初始化层数据
    load_dict = {}
    _mi.init_layers(load_dict, all_layers)
    _mi.save_load_dict(load_dict)

    # 选择要输出的层
    if args.layers:
        selected = [n.strip() for n in args.layers.split(",")]
        layer_names = [
            n for n in selected
            if n in load_dict.get("layer_file", {})
        ]
    else:
        layer_names = list(load_dict.get("layer_file", {}).keys())

    if not layer_names:
        print("ERROR: 指定的层不存在")
        print(f"可用层: {list(load_dict.get('layer_file', {}).keys())}")
        return 1

    print(f"选中层: {layer_names}")

    # 获取 note 数据
    for lay in layer_names:
        try:
            notes = _mi.get_notes_new(args.job, args.step, lay)
            if notes:
                load_dict.setdefault("step_note", {}).setdefault(
                    args.step, {}
                )[lay] = notes
        except Exception as e:
            print(f"WARN: 获取 {lay} 标记失败: {e}")

    # 计算 LIMITS
    profile_flag = 1 if args.profile else 0
    _svg.calculate_limits(args.job, args.step, layer_names)

    # 生成 SVG
    print("正在生成图纸...")
    gen = _svg.SVGGenerator(args.job, args.step)
    msg, err = gen.generate(
        layer_names,
        output_dir=config.SVG_DIR,
        profile_flag=profile_flag,
    )

    if err:
        print(f"ERROR: {err}")
        return 1

    print(f"完成: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
