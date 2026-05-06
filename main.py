#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸系统 — 命令行入口
===========================
胜宏科技（惠州）MI (Manufacturing Instruction) 制程指示系统

用法示例:
    # 列出可用层
    python main.py --job S31804PF590C1 --step cad --list-layers

    # 生成指定层的 SVG 图纸
    python main.py --job S31804PF590C1 --step cad --layers sig_top,sig_bot --output ./output

    # 生成所有层的 SVG 图纸
    python main.py --job S31804PF590C1 --step cad --all

    # 启动 GUI 界面
    python main.py --gui --job S31804PF590C1 --step cad

    # 搜索料号
    python main.py --search S31804

    # 导出 JSON
    python main.py --job S31804PF590C1 --step cad --export-json job_notes.json

    # 查看阻抗表
    python main.py --job S31804PF590C1 --step cad --show-imp

环境变量:
    JOB      — 料号名（等价于 --job）
    STEP     — Step 名（等价于 --step）
"""

import os
import sys
import json
import argparse
from typing import List, Optional

# 确保导入路径正确
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# 内部模块
from mi_print import config
from mi_print import mi_extractor as _mi

# svg_renderer / database 按需懒加载（避免 Windows 无 cairo 时崩溃）
_svg = None
_db = None

# ═══════════════════════════════════════════
# 命令处理器
# ═══════════════════════════════════════════


def cmd_list_layers(job: str, step: str) -> int:
    """列出料号的可用层"""
    print(f"\n{'='*60}")
    print(f"  料号: {job}")
    print(f"  Step: {step}")
    print(f"{'='*60}\n")

    try:
        layers = _mi.get_layers(job)
    except Exception as e:
        print(f"[ERROR] 获取层列表失败: {e}")
        return 1

    if not layers:
        print("[WARN] 没有找到层数据（需要 Genesis 环境）")
        return 1

    from mi_print.config import LAYER_SORT_KEY

    print(f"{'层名':<12} {'页码':<8} {'电镀':<6} {'类型':<6}")
    print("-" * 40)
    for row in layers:
        name = row[0] if len(row) > 0 else ""
        page = row[1] if len(row) > 1 else ""
        plated = "是" if (len(row) > 2 and row[2]) else "否"
        ltype = row[3] if len(row) > 3 else ""
        print(f"  {name:<10} {page:<6} {plated:<4} {ltype:<6}")
    print()
    return 0


def cmd_generate(job: str, step: str, layers: List[str],
                 output_dir: str = "",
                 all_layers: bool = False) -> int:
    """生成 SVG 图纸

    Args:
        job:        料号名
        step:       Step 名
        layers:     层名列表（逗号分隔或列表）
        output_dir: 输出目录
        all_layers: 是否导出所有层

    Returns:
        退出码
    """
    print(f"\n{'='*60}")
    print(f"  MI 打印图纸生成")
    print(f"  料号: {job}  |  Step: {step}")
    print(f"{'='*60}\n")

    # 获取主机信息
    _mi.get_host(job)
    job_upper = _mi.host_info.get("job_name", job).upper()
    print(f"  JOB: {job_upper}")
    print(f"  输出目录: {output_dir or config.SVG_DIR}")

    # 确定目标层
    if all_layers:
        try:
            all_layer_data = _mi.get_layers(job)
            layers = [row[0] for row in all_layer_data if row[0]]
        except Exception as e:
            print(f"[ERROR] 获取层列表失败: {e}")
            return 1

    if not layers:
        print("[ERROR] 没有指定层，使用 --layers 或 --all")
        return 1

    print(f"  目标层: {', '.join(layers)}\n")

    # 生成 SVG
    try:
        from mi_print import svg_renderer as _svg
        gen = _svg.SVGGenerator(job, step)
        result, error = gen.generate(
            layers,
            output_dir=output_dir or config.SVG_DIR
        )
    except Exception as e:
        print(f"[ERROR] SVG 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    if error:
        print(f"[ERROR] {error}")
        return 1

    print(f"[OK] 图纸已生成: {result}")
    print(f"  路径: {output_dir or config.SVG_DIR}/{job_upper}/")
    print()
    return 0


def cmd_search(job_name: str) -> int:
    """搜索料号标记数据

    Args:
        job_name: 搜索关键字
    """
    print(f"\n{'='*60}")
    print(f"  搜索料号: {job_name}")
    print(f"{'='*60}\n")

    results = []
    try:
        results += _mi.find_genesis_data(job_name)
        print(f"  Genesis: 找到 {len(results)} 条记录")
    except Exception as e:
        print(f"  Genesis: 错误 - {e}")

    mysql_count = 0
    try:
        mysql_results = _mi.find_mysql_data(job_name)
        results += mysql_results
        mysql_count = len(mysql_results)
        print(f"  MySQL:   找到 {mysql_count} 条记录")
    except Exception as e:
        print(f"  MySQL:   错误 - {e}")

    if not results:
        print("\n[INFO] 没有找到匹配数据")
        return 0

    print(f"\n  共 {len(results)} 条结果:\n")
    for row in results:
        source = row[0] if len(row) > 0 else ""
        name = row[1] if len(row) > 1 else ""
        version = row[2] if len(row) > 2 else ""
        count = row[3] if len(row) > 3 else ""
        size = row[4] if len(row) > 4 else ""
        mi_maker = row[5] if len(row) > 5 else ""
        created = row[6] if len(row) > 6 else ""
        modified_by = row[7] if len(row) > 7 else ""
        modified_time = row[8] if len(row) > 8 else ""

        print(f"  [{source}] {name} v{version} | {count}个标记 | "
              f"{size} | {mi_maker} | {created}")

    print()
    return 0


def cmd_show_imp(job: str, step: str) -> int:
    """显示阻抗表"""
    print(f"\n{'='*60}")
    print(f"  阻抗表 - {job}")
    print(f"{'='*60}\n")

    try:
        imp_list = _mi.get_impedance_list()
    except Exception as e:
        print(f"[ERROR] 获取阻抗表失败: {e}")
        return 1

    if not imp_list:
        print("[INFO] 没有阻抗数据（需要 Oracle/InPlan 连接）")
        return 0

    print(f"{'层名':<12} {'序号':<6} {'类型':<20} {'成品值':<12} {'参考层':<16}")
    print("-" * 70)
    for row in imp_list:
        layer = row[0] if len(row) > 0 else ""
        seq = row[1] if len(row) > 1 else ""
        imp_type = row[2] if len(row) > 2 else ""
        value = row[4] if len(row) > 4 else ""
        ref = row[7] if len(row) > 7 else ""
        print(f"  {layer:<10} {seq:<4} {imp_type:<18} {value:<10} {ref:<14}")

    print()
    return 0


def cmd_export_json(job: str, step: str, output_path: str) -> int:
    """导出 JSON 数据

    Args:
        job:         料号名
        step:        Step 名
        output_path: 输出文件路径
    """
    print(f"\n{'='*60}")
    print(f"  导出 JSON - {job}")
    print(f"{'='*60}\n")

    _mi.get_host(job)
    json_file = _mi.get_json_name(job)

    data = {}
    if os.path.isfile(json_file):
        data = _mi.read_json(json_file)

    if not data:
        print(f"[WARN] 源 JSON 为空或不存在: {json_file}")
        # 构建基本数据
        data = {
            "job_name": _mi.host_info.get("job_name", job),
            "step": step,
            "unit": _mi.print_config[1],
            "editer_name": "",
            "layer_file": {},
            "layer_note": {},
            "layer_dist": {},
        }

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON 已导出到: {output_path}")
        print(f"  大小: {os.path.getsize(output_path)} 字节")
    except Exception as e:
        print(f"[ERROR] 写入失败: {e}")
        return 1

    print()
    return 0


def cmd_import_json(job: str, step: str, input_path: str) -> int:
    """导入 JSON 数据

    Args:
        job:        料号名
        step:       Step 名
        input_path: 输入文件路径
    """
    print(f"\n{'='*60}")
    print(f"  导入 JSON - {job}")
    print(f"{'='*60}\n")

    if not os.path.isfile(input_path):
        print(f"[ERROR] 文件不存在: {input_path}")
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] JSON 解析失败: {e}")
        return 1

    _mi.get_host(job)
    target_file = _mi.get_json_name(job)
    _mi.save_json(target_file, data)
    print(f"[OK] JSON 已导入到: {target_file}")
    print(f"  包含 {len(data)} 个顶级键")
    print()
    return 0


def cmd_gui(job: Optional[str] = None,
            step: Optional[str] = None) -> int:
    """启动 GUI 界面"""
    from mi_print import mi_gui as _gui
    return _gui.run_gui(job, step)


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════


def main() -> int:
    """命令行主入口

    Returns:
        退出码
    """
    parser = argparse.ArgumentParser(
        description="MI 打印图纸系统 - 胜宏科技制程指示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --job S31804PF590C1 --step cad --list-layers
  python main.py --job S31804PF590C1 --step cad --layers sig_top,sig_bot
  python main.py --job S31804PF590C1 --step cad --all --output ./output
  python main.py --gui --job S31804PF590C1 --step cad
  python main.py --search S31804
        """
    )

    # 基本参数
    parser.add_argument("--job", "-j",
                        default=os.environ.get("JOB", None),
                        help="料号名（或设置环境变量 JOB）")
    parser.add_argument("--step", "-s",
                        default=os.environ.get("STEP", "cad"),
                        help="Step 名（默认: cad，或设置环境变量 STEP）")
    parser.add_argument("--output", "-o",
                        default="",
                        help="输出目录（默认: 配置文件中的 SVG_DIR）")

    # 操作模式
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list-layers", action="store_true",
                       help="列出可用层")
    group.add_argument("--search", metavar="KEYWORD",
                       help="搜索料号标记数据")
    group.add_argument("--show-imp", action="store_true",
                       help="显示阻抗表")
    group.add_argument("--export-json", metavar="PATH",
                       help="导出 JSON 数据到指定文件")
    group.add_argument("--import-json", metavar="PATH",
                       help="从指定文件导入 JSON 数据")
    group.add_argument("--gui", action="store_true",
                       help="启动 GUI 界面")

    # 生成参数
    parser.add_argument("--layers", "-l",
                        help="目标层名列表（逗号分隔）")
    parser.add_argument("--all", "-a", action="store_true",
                        help="生成所有层的图纸")

    args = parser.parse_args()

    # 检查 job
    if not args.job and not args.search and not args.gui:
        parser.error("必须指定 --job（或设置环境变量 JOB）")

    # 分发命令
    if args.list_layers:
        return cmd_list_layers(args.job, args.step)

    elif args.search:
        return cmd_search(args.search)

    elif args.show_imp:
        return cmd_show_imp(args.job, args.step)

    elif args.export_json:
        return cmd_export_json(args.job, args.step, args.export_json)

    elif args.import_json:
        return cmd_import_json(args.job, args.step, args.import_json)

    elif args.gui:
        return cmd_gui(args.job, args.step)

    # 默认：生成图纸
    layers = []
    if args.layers:
        layers = [l.strip() for l in args.layers.split(",") if l.strip()]

    return cmd_generate(
        args.job, args.step, layers,
        output_dir=args.output,
        all_layers=args.all or (not layers)
    )


if __name__ == "__main__":
    sys.exit(main())
