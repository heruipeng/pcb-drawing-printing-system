#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - MI 制程标记提取器
==============================
从 get_notes.py 核心逻辑提取而来。

核心流程：
  1. 从 Genesis CAM 中获取制程标记/备注 (get_notes / parseNotes)
  2. 查询 ERP/InPlan/MySQL 获取料号信息
  3. 分类、排序、验证标记
  4. 写入/读取 JSON 持久化

原始作者: Gf.zhang (get_notes.py v1.0, 2021-11-19)
"""

import os
import re
import sys
import json
import time
import socket
import getpass
import string as _string
from typing import Dict, List, Tuple, Optional, Any

try:
    from .cam_interface import CAM
except ImportError:
    CAM = None
    print("[WARN] cam_interface 不可用，Genesis 功能受限")

from . import config
from . import geometry as _geom

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════

# 打印配置
print_config = config.DEFAULT_PRINT_CONFIG[:]

# 主机信息
host_info: Dict[str, Any] = {}

# 全局 load_dict
load_dict_all: Dict[str, Any] = {}

# 线信息汇总
line_info_all: Dict[str, str] = {}

# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def round_str(value: float, decimal: int = 3) -> str:
    """数值舍入为字符串"""
    return _geom.round_str(value, decimal)


# ═══════════════════════════════════════════
# JSON 持久化
# ═══════════════════════════════════════════

def read_json(json_file: str) -> Dict:
    """读取 JSON 文件

    Args:
        json_file: JSON 文件路径

    Returns:
        字典，文件不存在或异常返回空字典
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {}


def save_json(json_file: str, data: Dict) -> None:
    """写入 JSON 文件

    Args:
        json_file: JSON 文件路径
        data:      待写入字典
    """
    try:
        os.makedirs(os.path.dirname(json_file), exist_ok=True)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_json_name(job_name: str) -> str:
    """获取料号的 job_notes.json 路径"""
    return os.path.join(
        config.GENESIS_DIR, "fw", "jobs",
        str(job_name), "user", "job_notes.json"
    ).replace("\\", "/")


# ═══════════════════════════════════════════
# 主机信息采集
# ═══════════════════════════════════════════

def get_host(job_name: str = "") -> None:
    """采集当前运行主机信息

    Args:
        job_name: 当前料号名
    """
    global host_info

    # Windows 用户
    try:
        host_info["win_user"] = getpass.getuser()
    except Exception:
        host_info["win_user"] = ""

    # 处理 BE 前缀用户名 (BE12345 → 12345)
    if host_info["win_user"].startswith("BE") and host_info["win_user"][2:].isdigit():
        host_info["win_user"] = host_info["win_user"][2:]

    # 主机名
    try:
        host_info["host_name"] = socket.gethostname()
    except Exception:
        host_info["host_name"] = ""

    # IP 地址
    try:
        host_info["host_ip"] = socket.gethostbyname(host_info["host_name"])
    except Exception:
        host_info["host_ip"] = ""

    # 料号名
    host_info["run_job"] = job_name if job_name else ""
    raw_name = host_info["run_job"].replace("-", "_")
    raw_name = raw_name.split("_mi")[0].replace("_", "").split(".")[0]
    host_info["job_name"] = raw_name

    # 模糊搜索关键字
    host_info["find_job"] = ""
    if len(host_info.get("job_name", "")) >= 13:
        jn = host_info["job_name"]
        host_info["find_job"] = f"*{jn[1:4]}*{jn[8:11]}*"

    # Step 名
    host_info["run_step"] = print_config[6] if print_config[6] else ""

    # 其他
    host_info.setdefault("jsonFile", "")
    host_info.setdefault("mysqlLogfile", "")
    host_info.setdefault("mi_maker", "")
    host_info.setdefault("emp_no", "")
    host_info.setdefault("mi_time", "")
    host_info.setdefault("if_cancle", "")

    if host_info["job_name"]:
        host_info["jsonFile"] = get_json_name(host_info["run_job"])


# ═══════════════════════════════════════════
# Genesis 接口封装
# ═══════════════════════════════════════════

class GenesisAPI:
    """Genesis CAM 操作统一接口

    封装 get_notes.py 中所有直接调用 genClasses 的操作。
    内部使用 cam_interface.CAM。
    """

    _cam: Any = None
    _mode: str = "embedded"
    _pid: Optional[int] = None

    @classmethod
    def init(cls, mode: str = "embedded", pid: Optional[int] = None) -> None:
        """初始化 Genesis 连接模式
        
        Args:
            mode: "embedded" (脚本面板内) 或 "gateway" (外部 Gateway)
            pid:  Gateway 模式下的 get.exe PID
        """
        cls._mode = mode
        cls._pid = pid
        cls._cam = None  # 重置以重新创建

    @classmethod
    def get_cam(cls) -> Any:
        """获取 CAM 实例（单例）"""
        if cls._cam is None:
            if CAM is not None:
                if cls._mode == "gateway" and cls._pid:
                    cls._cam = CAM(embedded=False, pid=cls._pid)
                else:
                    cls._cam = CAM(embedded=True)
            else:
                raise RuntimeError("cam_interface 不可用")
        return cls._cam

    @classmethod
    def _COM(cls, args: str) -> int:
        """执行 Genesis COM 命令"""
        cam = cls.get_cam()
        return cam._io.COM(args)

    @classmethod
    def _VOF(cls) -> None:
        """关闭视觉更新"""
        cls.get_cam().VOF()

    @classmethod
    def _VON(cls) -> None:
        """恢复视觉更新"""
        cls.get_cam().VON()

    @classmethod
    def _COMANS(cls) -> str:
        """获取上一条命令的返回值"""
        return cls.get_cam()._io.COMANS

    @classmethod
    def _STATUS(cls) -> int:
        """获取上一条命令的状态码"""
        return cls.get_cam()._io.STATUS

    @classmethod
    def get_user_name(cls) -> str:
        """获取当前 Genesis 用户名"""
        cls._COM('get_user_name')
        print_config[7] = cls._COMANS()
        return print_config[7]

    @classmethod
    def DO_INFO(cls, args: str, units: str = "mm") -> Dict:
        """DO_INFO 查询并解析为字典"""
        return cls.get_cam().DO_INFO(args)

    @classmethod
    def DO_info(cls, args: str, units: str = "mm") -> Dict:
        """DO_info 查询（LiuChuang 风格，带 units 参数）"""
        cam = cls.get_cam()
        return cam._io.DO_INFO(args, units=units)

    @classmethod
    def INFO(cls, args: str) -> List[str]:
        """INFO 查询返回行列表"""
        cam = cls.get_cam()
        return cam._io.INFO(args, units="mm")

    @classmethod
    def INFOMM(cls, args: str) -> List[str]:
        """INFO 查询（Gf.zhang 风格，固定 mm）"""
        return cls.INFO(args)

    @classmethod
    def GFDO_INFO(cls, args: str) -> Dict:
        """GFDO_INFO 查询（Gf.zhang 风格，保持字符串值）"""
        cam = cls.get_cam()
        info_list = cam._io.INFO(args, units="mm")
        return _gf_parse_info(info_list)

    @classmethod
    def DISP_INFO(cls, args: str) -> Dict:
        """显示模式 INFO"""
        cam = cls.get_cam()
        cls._COM(
            f'info,out_file={cam._io.tmpfile},write_mode=replace,'
            f'args=-m display {args}'
        )
        with open(cam._io.tmpfile, 'r') as f:
            lines = f.readlines()
        os.unlink(cam._io.tmpfile)
        return _parse_disp_info(lines)

    @classmethod
    def open_step(cls, job_name: str, step_name: str,
                  units: str = "inch") -> None:
        """打开 Step（完整初始化流程）"""
        cls._COM(f'open_entity,job={job_name},type=step,'
                 f'name={step_name},iconic=no')
        cls._COM(f'editor_group,job={job_name},is_step=yes,name={step_name}')
        ans = cls._COMANS()
        cls._COM('set_group,group=' + ans)  # Note: this is AUX in original
        cls._COM('origin,x=0,y=0')
        cls._COM(f'units,type={units}')
        cls._COM('affected_layer,mode=all,affected=no')
        cls._COM('clear_layers')
        cls._COM('filter_reset,filter_name=popup')
        cls._COM('adv_filter_reset,filter_name=popup')

    @classmethod
    def save_job(cls, job_name: str) -> None:
        """保存料号（跳过 hooks 加速）"""
        cls._VOF()
        cls._COM(f"config_edit,name=gen_line_skip_post_hooks,value=4,mode=user")
        cls._COM(f"config_edit,name=gen_line_skip_pre_hooks,value=4,mode=user")
        cls._COM(f"check_inout,mode=out,type=job,job={job_name}")
        cls._COM(f"save_job,job={job_name},override=no")
        cls._COM(f"config_edit,name=gen_line_skip_post_hooks,value=1,mode=user")
        cls._COM(f"config_edit,name=gen_line_skip_pre_hooks,value=1,mode=user")
        cls._VON()

    @classmethod
    def export_job(cls, job_name: str) -> int:
        """导出料号为 TGZ"""
        paths = os.path.join(config.SVG_DIR,
                             host_info.get("job_name", "").upper())
        tgz_file = os.path.join(paths, f"{job_name}.tgz")
        new_tgz_file = os.path.join(
            paths, f"{host_info.get('job_name', '')}_mi.tgz"
        )

        cls.save_job(job_name)

        try:
            os.makedirs(paths, exist_ok=True)
        except Exception:
            pass

        cls._VOF()
        cls._COM(f"config_edit,name=gen_line_skip_post_hooks,value=4,mode=user")
        cls._COM(f"config_edit,name=gen_line_skip_pre_hooks,value=4,mode=user")
        cls._COM(f"check_inout,mode=out,type=job,job={job_name}")
        cls._COM(
            f"export_job,job={job_name},path={paths},"
            f"mode=tar_gzip,submode=full,overwrite=yes"
        )
        status = cls._STATUS()
        cls._COM(f"config_edit,name=gen_line_skip_post_hooks,value=1,mode=user")
        cls._COM(f"config_edit,name=gen_line_skip_pre_hooks,value=1,mode=user")
        cls._VON()

        if status != 0:
            try:
                os.remove(tgz_file)
            except Exception:
                pass
        elif tgz_file != new_tgz_file:
            try:
                os.remove(new_tgz_file)
            except Exception:
                pass
            try:
                os.rename(tgz_file, new_tgz_file)
                print(new_tgz_file)
            except Exception:
                status = 1

        print([status, tgz_file, new_tgz_file])
        return status

    @classmethod
    def add_note(cls, layer: str, x: float = 0.0, y: float = 0.0,
                 text: str = "Note / *") -> None:
        """在层上添加制程标记"""
        cls._VOF()
        user = print_config[7]
        cls._COM(
            f"note_add,layer={layer},x={x},y={y},"
            f"user={user},text={text}"
        )
        cls._VON()

    @classmethod
    def delete_note(cls, layer: str, index_list: List[int]) -> None:
        """删除指定层上的标记"""
        for idx in index_list:
            cls._VOF()
            cls._COM(f"note_delete,layer={layer},note_ind={idx}")
            cls._VON()

    @classmethod
    def delete_note_all(cls, layer: str) -> None:
        """删除层上所有标记"""
        cls._VOF()
        cls._COM(
            f"note_delete_all,layer={layer},"
            f"note_from=0,note_to=2147483647,user="
        )
        cls._VON()

    @classmethod
    def change_note(cls, layer: str, note_n: int, text: str) -> None:
        """修改标记文本"""
        user = print_config[7]
        cls._COM(
            f"note_change,layer={layer},note_n={note_n},"
            f"user={user},text={text}"
        )

    @classmethod
    def view_note(cls, job_name: str, step_name: str, layer: str,
                  x: float = 0.0, y: float = 0.0,
                  text: str = "", kkk: int = 0) -> None:
        """在 Genesis 中定位查看标记"""
        cls._VOF()
        unit = "mm" if print_config[1] == "mil" else "inch"
        cls.open_step(job_name, step_name)
        cls._COM(f"display_layer,name={layer},display=yes,number=1")
        cls._COM(f"work_layer,name={layer}")
        cls._COM("note_page_close")
        cls._COM(f"note_page_show,layer={layer}")
        cls._VON()

        if kkk:
            cls._COM("zoom_factor,factor=30:1")
            cls._COM(f"pan_center,x={x},y={y}")
        else:
            cls._COM('zoom_home')

        cls._COM(f'units,type={unit}')
        if text:
            cls._COM_UNSAFE(f"PAUSE Orig {text} Pls view and verify !!!")
        else:
            cls._COM_UNSAFE("PAUSE Pls view and verify or modify!!!")

        cls._VOF()
        cls._COM("note_page_close")
        cls._VON()

    @classmethod
    def _COM_UNSAFE(cls, msg: str) -> None:
        """执行 PAUSE 命令（交互式）"""
        cam = cls.get_cam()
        cam._io.PAUSE(msg)

    @classmethod
    def delete_tmp_layer(cls) -> None:
        """删除临时层"""
        cls._VOF()
        cls._COM(f"delete_layer,layer={print_config[3]}")
        cls._VON()

    @classmethod
    def get_step_list(cls, job_name: str) -> List[str]:
        """获取料号中所有 Step 列表"""
        info = cls.GFDO_INFO(
            f'-t job -e {job_name} -d STEPS_LIST'
        )
        return info.get('gSTEPS_LIST', [])

    @classmethod
    def get_step_info(cls, job_name: str, step: str) -> List[str]:
        """获取 Step 的 REPEAT 子步骤"""
        info = cls.GFDO_INFO(
            f'-t step -e {job_name}/{step} -d REPEAT'
        )
        steps = {}
        for s in list(set(info.get('gREPEATstep', []))):
            steps[s] = 0
        return list(steps.keys())

    @classmethod
    def get_features(cls, features_spec: str) -> List[str]:
        """获取特征数据（DO_INFO display 模式）

        Args:
            features_spec: 例如 '-t layer -e job/step/layer -d FEATURES'
        """
        try:
            cls._VOF()
            lines = cls.INFO(features_spec)
            cls._VON()
        except Exception:
            lines = []
        return lines


# ═══════════════════════════════════════════
# 信息解析辅助
# ═══════════════════════════════════════════

def _gf_parse_info(info_list: List[str]) -> Dict:
    """Gf.zhang 风格的 INFO 解析（保持字符串值）

    解析 csh 格式: set KEY = ('val1' 'val2' ...)
    与标准 parseInfo 的区别: 保留字符串原样，不转换数字。
    """
    result = {}
    for line in info_list:
        parts = line.strip().split(' = ', 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        if key.startswith('set '):
            key = key[4:]
        val = parts[1]

        if val.startswith('(') and ')' in val:
            items = [m.group(1) for m in re.finditer(r"'([^']*)'", val)]
            result[key] = items
        elif val.startswith("'") and val.endswith("'"):
            result[key] = val[1:-1]
        else:
            result[key] = val
    return result


def _parse_disp_info(info_list: List[str]) -> Dict:
    """解析 display 模式 INFO 输出"""
    main = {}
    for line in info_list:
        line = line.strip()
        if not line:
            continue
        try:
            exec(line)
        except SyntaxError:
            # 处理数组格式: NOTE[1]:field=val,field2=val2
            key = line.split('[')[0]
            if key not in main:
                main[key] = []
            vals_str = line.split(':', 1)[1] if ':' in line else ''
            vals_parts = vals_str.split(',')
            item = {}
            for vp in vals_parts:
                kv = vp.split('=', 1)
                if len(kv) == 2:
                    try:
                        item[kv[0].strip()] = eval(kv[1])
                    except Exception:
                        item[kv[0].strip()] = kv[1]
            main[key].append(item)
    return main


# ═══════════════════════════════════════════
# 层信息
# ═══════════════════════════════════════════

def get_layers(job_name: str, step: str = "") -> List[List[str]]:
    """获取料号的所有层及其分类

    Args:
        job_name: 料号名
        step: Step 名（为空时从 print_config[6] 读取）

    Returns:
        [[name, order_num, polarity, type_code], ...]
        type_code: IN=内层线路, LL=外层线路, MM=绿油, CC=字符,
                   GO=金面, CA=碳油, DD=钻孔, SE=SET, NO=Note
    """
    gf = GenesisAPI
    step = step or print_config[6]

    # 获取成型范围
    try:
        host_info["run_profile"] = gf.DO_info(
            f'-t step -e {job_name}/{step} -d PROF_LIMITS', "mm"
        )
    except Exception:
        host_info["run_profile"] = {}

    # 获取基准点
    try:
        host_info["run_datum"] = gf.DO_info(
            f'-t step -e {job_name}/{step} -d DATUM', "mm"
        )
    except Exception:
        host_info["run_datum"] = {}

    layers = gf.GFDO_INFO(f'-t matrix -e {job_name}/matrix -d ROW')
    line_layers: List[List[str]] = []

    names = layers.get('gROWname', [])
    types = layers.get('gROWtype', [])
    contexts = layers.get('gROWcontext', [])
    layer_types = layers.get('gROWlayer_type', [])
    sides = layers.get('gROWside', [])
    polarities = layers.get('gROWpolarity', [])

    # 第一轮：处理标准层
    for i in range(len(names)):
        if (types[i] == 'layer' and
                contexts[i] == "board" and
                layer_types[i] == "silk_screen"):
            line_layers.append([names[i], "1", "", "CC"])
        elif (types[i] == 'layer' and
              contexts[i] == "board" and
              layer_types[i] == "solder_mask"):
            line_layers.append([names[i], "2", "", "MM"])
        elif (types[i] == 'layer' and
              contexts[i] == "board" and
              layer_types[i] in ("signal", "mixed", "power_ground")):
            if sides[i] == "inner":
                if (layer_types[i] == "power_ground" and
                        polarities[i] == "negative"):
                    line_layers.append([names[i], "IN", "n", "IN"])
                else:
                    line_layers.append([names[i], "IN", "", "IN"])
            else:
                line_layers.append([names[i], "3", "", "LL"])
        elif (types[i] == 'layer' and
              names[i].startswith("gold") and "+" not in names[i]):
            line_layers.append([names[i], "4", "", "GO"])
        elif (types[i] == 'layer' and
              names[i].startswith("carbon") and "+" not in names[i]):
            line_layers.append([names[i], "5", "", "CA"])

    # 第二轮：处理特殊层 (钻孔、SET、Note、HiPot)
    existing = {x[0] for x in line_layers}
    for i in range(len(names)):
        if (types[i] == 'layer' and
                names[i] not in existing and
                "_yg" not in names[i].replace("-", "_")):
            if names[i].startswith("dd") and "+" not in names[i]:
                line_layers.append([names[i], "DD", "", "DD"])
            elif names[i].startswith("set") and "+" not in names[i]:
                line_layers.append([names[i], "SE", "", "SE"])
            elif names[i].startswith("note") and "+" not in names[i]:
                line_layers.append([names[i], "NO", "", "NO"])
            elif names[i].startswith("hipot") and "+" not in names[i]:
                line_layers.append([names[i], "6", "", "HI"])

    return line_layers


def init_layers(load_dict: Dict, line_layers: List[List[str]]) -> None:
    """初始化并排序层信息，写入 load_dict

    主要是:
      1. 给内层线路编号 (如 第2层、第3层...)
      2. 给特殊层编号 (DD, SE, NO)
      3. 层排序：按类型 + 编号
      4. 清理不存在的层

    Args:
        load_dict:    全局数据字典（原地修改）
        line_layers:  get_layers() 返回值
    """
    if "layer_file" not in load_dict:
        load_dict["layer_file"] = {}
    if "layer_dist" not in load_dict:
        load_dict["layer_dist"] = {}

    # 初始化 layer_dist
    for item in line_layers:
        load_dict["layer_dist"][item[0]] = item[:]

    # 内层线路编号 (IN)
    _number_layers(load_dict, line_layers, "IN", 3)

    # 钻孔层编号 (DD)
    _number_layers(load_dict, line_layers, "DD", 4)

    # SET 层编号
    _number_layers(load_dict, line_layers, "SE", 4)

    # Note 层编号
    _number_layers(load_dict, line_layers, "NO", 4)

    # ── 排序 ──
    # 按 (type_sort_key, order_num) 排序
    sorted_items = []
    for item in line_layers:
        type_code = item[3]
        type_key = config.LAYER_SORT_KEY.get(type_code, 100)
        try:
            order_num = int(item[1])
        except ValueError:
            order_num = 100
        sorted_items.append((type_key, order_num, item))
    sorted_items.sort()

    # 重新赋予连续编号
    seen = set()
    zzz = 0
    for _, _, item in sorted_items:
        key = f"{item[3]}~{item[1]}"
        if key not in seen:
            seen.add(key)
            zzz += 1
        if item[0] in load_dict["layer_file"]:
            item[1] = load_dict["layer_file"][item[0]]
        else:
            item[1] = str(zzz)

    # 更新 layer_dist 和 layer_file
    for item in line_layers:
        load_dict["layer_dist"][item[0]] = item[:]
        load_dict["layer_file"][item[0]] = item[1]

    # 清理不存在的层
    all_names = {x[0] for x in line_layers}
    for key in list(load_dict["layer_dist"].keys()):
        if key not in all_names:
            del load_dict["layer_dist"][key]
    for key in list(load_dict["layer_file"].keys()):
        if key not in all_names:
            del load_dict["layer_file"][key]

    # 确保编号连续
    _renumber_layers(load_dict, line_layers)

    # 清理 note 引用
    _clear_notes_dist(load_dict)


def _number_layers(load_dict: Dict, line_layers: List[List[str]],
                   type_code: str, offset: int) -> None:
    """给指定类型的层连续编号"""
    tmp = {}
    cnt = 2
    for item in line_layers:
        if item[3] == type_code:
            idx = cnt // 2
            if idx in tmp:
                tmp[idx].append(item)
            else:
                tmp[idx] = [item]
            cnt += 1
    for idx in tmp:
        num = str(idx + offset)
        for item in tmp[idx]:
            item[1] = num


def _renumber_layers(load_dict: Dict,
                     line_layers: List[List[str]]) -> None:
    """确保层编号从 1 开始连续"""
    tmp = {}
    for item in line_layers:
        try:
            n = int(load_dict["layer_file"][item[0]])
        except (KeyError, ValueError):
            continue
        if n in tmp:
            tmp[n].append(item[0])
        else:
            tmp[n] = [item[0]]

    keys = sorted(tmp.keys())
    for expected in range(1, len(keys) + 1):
        actual = keys[expected - 1]
        if expected != actual:
            for name in tmp[actual]:
                load_dict["layer_dist"][name][1] = str(expected)
                load_dict["layer_file"][name] = str(expected)


def _clear_notes_dist(load_dict: Dict) -> None:
    """清理引用不存在的层的 note 标记"""
    if "step_note" not in load_dict or "layer_note" not in load_dict:
        return

    layers = list(load_dict.get("layer_dist", {}).keys())

    # 清理 step_note 中引用不存在的层
    for step_name in load_dict["step_note"]:
        lays = list(load_dict["step_note"][step_name].keys())
        for lay in lays:
            if lay not in layers:
                del load_dict["step_note"][step_name][lay]

    # 收集所有有效 note key
    valid_keys = set()
    for step_name in load_dict["step_note"]:
        for lay in load_dict["step_note"][step_name]:
            for note in load_dict["step_note"][step_name][lay]:
                if note[11]:
                    valid_keys.add(note[11])

    # 清理 layer_note 中不再引用的 key
    for key in list(load_dict["layer_note"].keys()):
        if key not in valid_keys:
            del load_dict["layer_note"][key]


# ═══════════════════════════════════════════
# Note 提取
# ═══════════════════════════════════════════

def get_notes(job_name: str, step: str, layer: str) -> List[List]:
    """获取层上的原始制程标记

    Returns:
        [[date, time, user, x, y, text], ...]
    """
    notes: List[List] = []
    try:
        GenesisAPI._VOF()
        note_dist = GenesisAPI.DO_info(
            f'-t notes -e {job_name}/{step}/{layer}/notes -d NOTE', "mm"
        )
        GenesisAPI._VON()
    except Exception:
        note_dist = {}

    if not note_dist:
        return notes

    dates = note_dist.get('gNOTEdate', [])
    times = note_dist.get('gNOTEtime', [])
    users = note_dist.get('gNOTEuser', [])
    xs = note_dist.get('gNOTEx', [])
    ys = note_dist.get('gNOTEy', [])
    texts = note_dist.get('gNOTEtext', [])

    for i in range(len(dates)):
        try:
            notes.append([
                dates[i], times[i], users[i],
                xs[i], ys[i], texts[i],
            ])
        except IndexError:
            print_config[12] += (
                f"\n{layer.upper()}层note{i}多行输入,请修改为单行!!!"
            )
            print(layer, i, "Note Enter Error !!!")

    return notes


def parseNotes(notes: List[List], kkk: int = 0) -> List[List]:
    """解析原始标记为结构化格式

    原始格式 (gNOTEtext): "Eagle-WS-M A1 0.1/0.1 0.100/0.100 Note备注"
    解析为: [date, time, user, x, y, [type, mark, finished, original,
                                        imp_val, remark], key]

    Args:
        notes: get_notes() 返回值
        kkk:   单位转换模式

    Returns:
        解析后的标记列表
    """
    notes_new = []
    zzz = 0
    for row in notes:
        zzz += 1
        if not row[5].strip():
            continue

        parts = row[5].strip().split()

        # 补全 Note 格式 Note text → Note * * 或 Note N *
        if parts[0] == "Note" and len(parts) < 3:
            if len(parts) == 1:
                row[5] += " N *"
            else:
                row[5] += " *"
            parts = row[5].split()

        # 解析 noteType
        if len(parts) > 2 and parts[0] in config.NOTE_TYPES:
            note_type = parts[0]
            mark = parts[1] if parts[1].isalnum() else ""

            # 提取最多 6 个字段
            tcount = 6 if note_type != "Note" else 3
            fields = []
            for x in range(tcount):
                try:
                    fields.append(parts[x])
                except IndexError:
                    fields.append("/")

            if len(fields) > 3:
                fields[2] = _get_mm(fields[2], kkk)  # 成品值
                fields[3] = _get_mm(fields[3], kkk)  # 原稿值

            notes_new.append(row[:] + [fields] + [mark] + [str(zzz)])

    return notes_new


def get_notes_new(job_name: str, step: str, layer: str) -> List[List]:
    """获取新版结构化标记列表

    Returns:
        [[order, type_display, type_code, finished_val, original_val,
          zk1, zk2, zk3, imp_val, remark, xy, note_key], ...]
    """
    notes = parseNotes(get_notes(job_name, step, layer))
    result = []

    for i, row in enumerate(notes):
        note_type = row[6][0]  # 类型代码
        fields = row[6]        # [type, mark, finished, original, imp_val, remark]
        xy = row[0:6]          # [date, time, user, x, y, text]
        text = fields[0]

        if note_type == "Note":
            result.append([
                row[8],                        # 序号
                _get_note_type_name(layer, row[6]),  # 类型显示名
                note_type,                     # 类型代码
                fields[1],                     # 标记
                "", "", "", "",                # 空值
                fields[-1],                    # 备注
                xy,                            # 坐标/时间
                fields[-1],                    # note key
            ])
        else:
            # 阻抗相关
            zk_parts = fields[4].split("&")
            zk_list = ["", "", ""]
            for k in range(3):
                try:
                    zk_list[k] = zk_parts[k]
                except IndexError:
                    zk_list[k] = ""

            result.append([
                row[8],
                _get_note_type_name(layer, row[6]),
                note_type,
                fields[1],
                fields[2],       # 成品值
                fields[3],       # 原稿值
                zk_list[0],      # 阻抗值
                zk_list[1],      # zk2
                zk_list[2],      # zk3
                fields[5],       # 备注
                xy,              # 坐标/时间
                fields[-1],      # note key
            ])

    return result


def _get_note_type_name(layer: str, fields: List[str]) -> str:
    """根据原始字段生成类型显示名"""
    typen = config.NOTE_TYPES.get(fields[0], fields[0])
    if len(fields) < 5:
        return typen

    # 判断是否包含阻抗值
    imp_str = fields[4].strip().split("&")[0]
    imp_has_val = imp_str.replace("/", "").replace("*", "").replace(".", "").isdigit()

    orig = fields[3].strip().strip("/").split("/")
    fin = fields[2].strip().strip("/").split("/")

    # 最小线宽/线距信息
    info = _get_min_line_info(layer, fin)

    if "宽" in typen and "距" in typen:
        return _build_ws_type(typen, imp_has_val, orig, fin, info)
    elif "宽" in typen:
        return _build_w_type(typen, imp_has_val, orig, fin, info)
    elif "距" in typen:
        if info["min_line"]:
            return typen + f"(最小{info['min_line']})"
        return typen

    return typen


def _build_ws_type(typen: str, imp: bool, orig: List[str],
                   fin: List[str], info: Dict[str, str]) -> str:
    """构建线宽/线距类型名称"""
    if imp:
        result = "差分阻抗"
        if max(len(orig), len(fin)) > 2:
            result = "差分共面阻抗"
        if info["min_line"]:
            result += f"({''.join(info.values())})"
        return result
    if info["min_line"]:
        return typen + f"({''.join(info.values())})"
    return typen


def _build_w_type(typen: str, imp: bool, orig: List[str],
                  fin: List[str], info: Dict[str, str]) -> str:
    """构建线宽类型名称"""
    if imp:
        result = "单线阻抗"
        if max(len(orig), len(fin)) > 1:
            result = "单线共面阻抗"
        if info["min_line"]:
            result += f"({''.join(info.values())})"
        return result
    if info["min_line"]:
        return typen + f"({''.join(info.values())})"
    return typen


def _get_min_line_info(layer: str,
                       fin: List[str]) -> Dict[str, str]:
    """获取层的最小线宽/线距信息"""
    result = {"min": "", "width": "", "spacing": ""}
    if layer not in line_info_all:
        return result
    kff = line_info_all[layer].split("/")
    if fin and kff:
        if kff[0] == fin[0]:
            result["min"] = "最小"
            result["width"] = "线宽"
        if len(kff) > 1 and len(fin) > 1:
            if kff[1] in fin[1:]:
                result["min"] = "最小"
                result["spacing"] = "线距"
    return result


# ═══════════════════════════════════════════
# 单位转换
# ═══════════════════════════════════════════

def _get_mm(text: str, kkk: int = 0) -> str:
    """数值单位转换

    kkk 模式:
      0: 不变
      1: mil → mm
      2: um → mil
      3: mil → um
      4: mm → mil
      5: mil → mm (5位精度)
      6: mil → mm (3位精度)
      7: mil → um
      8: 原值保留2位
    """
    if not text.replace("*", "").replace("/", "").strip():
        return text

    k_map = {
        0: (1.0, 3),
        1: (25.4 / 1000, 5),
        2: (1 / 25.4, 3),
        3: (25.4, 2),
        4: (1 / 25.4 * 1000, 3),
        5: (25.4 / 1000, 5),
        6: (25.4 / 1000, 3),
        7: (25.4, 0),
        8: (1.0, 2),
    }
    factor, decimal = k_map.get(kkk, (1.0, 3))

    parts = text.replace("*", "/").strip().split("/")
    new_parts = []
    for s in parts:
        try:
            new_parts.append(round_str(float(s) * factor, decimal))
        except ValueError:
            new_parts.append(s)

    if "*" in text:
        return "*".join(new_parts)
    return "/".join(new_parts)


def get_mm_new(text: str, kkk: int = 0) -> str:
    """根据当前单位设置进行数值转换

    与 _get_mm 不同，根据 print_config[1] 自动选择 kkk
    """
    unit = print_config[1]
    if unit == "um":
        return _get_mm(text, 3 if kkk else 2)
    elif unit == "mm":
        return _get_mm(text, 5 if kkk else 4)
    return text


# ═══════════════════════════════════════════
# 标记字符串生成
# ═══════════════════════════════════════════

def _get_string_s(texts: str, strint: int = 0) -> List[str]:
    """生成标记字符串列表 [Aa, Ab, ... Za, Zb, ...]"""
    marks = []
    for n in range(strint, 100):
        for a in texts:
            s = a + str(n)
            if len(s) == 2:
                s = s.rstrip("0")
            marks.append(s)
    return marks


def get_string_new(note_type: str, imp_val: str,
                   existing_map: Dict[str, str]) -> str:
    """为标记生成唯一标识字符串

    Args:
        note_type:    标记类型（如 Eagle-WS-M）
        imp_val:      阻抗值
        existing_map: 已存在的标记映射

    Returns:
        新的标识字符串，如 "E1", "D2" 等
    """
    existing_keys = set(existing_map.values())
    prefix = "N"
    strint = 1

    if note_type in config.NOTE_SELECT:
        prefix = config.NOTE_SELECT[note_type][9]
        strint = 0

        if prefix == "E" and imp_val.strip("/").strip("*"):
            prefix = "D"
            strint = 1
        elif prefix == "A" and imp_val.strip("/").strip("*"):
            prefix = "S"
            strint = 1

    marks = _get_string_s(prefix, strint)
    for m in marks:
        if m not in existing_keys:
            return m
    return "/"


# ═══════════════════════════════════════════
# 排序
# ═══════════════════════════════════════════

def sort_notes(job_name: str, step_name: str,
               layers: List[str]) -> List[str]:
    """对标记按优先级排序

    排序规则:
      1. 阻抗标记（差分>单线）优先
      2. 按最小线宽/线距的值排序
      3. BGA < SMD < PAD < 线

    Args:
        job_name:  料号名
        step_name: Step 名
        layers:    需要排序的层列表

    Returns:
        排序过的层列表
    """
    lay_alls = {}
    for lay in layers:
        notelist = get_notes_new(job_name, step_name, lay)
        if notelist:
            lay_alls[lay] = notelist

    if not lay_alls:
        return []

    sort_layers = {}
    for lay in lay_alls:
        indexs = []
        sorts = []
        mod_count = 0
        zzz = 0
        for note in lay_alls[lay]:
            zzz += 1
            indexs.append(int(note[0]))
            ps = [299, 99, 99, note[3], zzz, note, 0]

            if note[2] in config.NOTE_SELECT:
                ps[1] = config.NOTE_SELECT[note[2]][8]
                try:
                    imp_f = float(note[6])
                except (ValueError, TypeError):
                    imp_f = 0
                if imp_f:
                    if "差分" in note[1]:
                        ps[0] = 50
                    else:
                        ps[0] = 100
                try:
                    ps[2] = float(note[5].replace("*", "/").split("/")[0])
                except (ValueError, TypeError):
                    pass
            elif note[3].isalnum():
                ps[2] = 98

            sorts.append(ps)

        sorts.sort()
        zzz = 0
        for ps in sorts:
            zzz += 1
            ps[6] = zzz
            if ps[6] != ps[4]:
                mod_count += 1

        if mod_count:
            sort_layers[lay] = [sorts, indexs, mod_count]

    if not sort_layers:
        return []

    # 执行排序
    GenesisAPI.open_step(job_name, step_name)
    result = []
    for lay in sort_layers:
        result.append(lay)
        # 先全部删除
        for idx in sorted(sort_layers[lay][1], reverse=True):
            GenesisAPI._COM(f"note_delete,layer={lay},note_ind={idx}")
        # 按新顺序重新添加
        for ps in sort_layers[lay][0]:
            note = ps[5]
            GenesisAPI._COM(
                f"note_add,layer={lay},"
                f"x={note[10][3] / 25.4},"
                f"y={note[10][4] / 25.4},"
                f"user={print_config[7]},"
                f"text={note[10][5]}"
            )

    return result


# ═══════════════════════════════════════════
# 特征数据提取
# ═══════════════════════════════════════════

def get_pad_size(symbol: str) -> List[float]:
    """从 symbol 字符串解析 PAD 尺寸

    Args:
        symbol: 例如 "oval10x20", "rect5x10", "r12", "s5"

    Returns:
        [min_size, max_size] 列表
    """
    vf = [0.0]

    if ("x" in symbol and "+" not in symbol and
            (symbol.startswith("oval") or symbol.startswith("rect") or
             symbol.startswith("oct"))):
        idx = 4 if symbol.startswith("oval") or symbol.startswith("rect") else 3
        parts = (
            symbol[idx:]
            .replace("+", "_")
            .replace("-", "_")
            .split("_")[0]
            .split("x")
        )
        if len(parts) > 1:
            try:
                vf = [float(parts[0]), float(parts[1])]
                vf.sort()
            except ValueError:
                vf = [0.0, 0.0]
    elif symbol and symbol[0] in ("r", "s"):
        try:
            vf = [float(symbol[1:])]
        except ValueError:
            vf = [0.0]

    return vf


def _get_symbol_data(job_name: str, symbol: str,
                     type_map: dict) -> List[float]:
    """获取 symbol 的 PAD 尺寸，支持嵌套符号"""
    sizes = get_pad_size(symbol)
    if min(sizes) > 0.001:
        return sizes

    features = GenesisAPI.get_features(
        f'-t symbol -e {job_name}/{symbol} -d FEATURES'
    )
    sizes_list = []

    for f_line in features:
        parts = f_line.split()
        if not parts:
            continue
        if parts[0] in type_map:
            tc = type_map[parts[0]]
            if len(parts) > tc:
                sizes_list.append(get_pad_size(parts[tc]))

    if len(sizes_list) == 1:
        return sizes_list[0]
    return [0.0]


def get_feature_data(job_name: str, step_name: str, layer: str,
                     note: List) -> str:
    """从选中特征提取数据

    这是 get_fdata() 的核心逻辑：
    1. 获取层上选中的特征
    2. 根据 noteSelect 配置匹配特征类型
    3. 计算线宽/线距/PAD 尺寸等
    4. 返回格式化字符串

    Args:
        job_name:  料号名
        step_name: Step 名
        layer:     层名
        note:      标记数据 [order, type_name, type_code, mark,
                             finished, original, imp, zk2, zk3, remark, xy, key]

    Returns:
        计算出的数据字符串（空串表示计算失败）
    """
    if note[2] not in config.NOTE_SELECT:
        return ""

    cfg = config.NOTE_SELECT[note[2]]
    feat_type = cfg[1]      # 特征类型
    calc_mode = cfg[2]      # 计算模式
    min_sel = cfg[3]        # 最小选择数

    features = GenesisAPI.get_features(
        f'-t layer -e {job_name}/{step_name}/{layer} -d FEATURES -o select'
    )
    type_map = {"#A": 7, "#L": 5, "#P": 3}
    allowed_types = ["#L", "#A"] if feat_type != "pad" else ["#P"]

    all_data = []
    for f_line in features:
        parts = f_line.split()
        if not parts or parts[0] not in allowed_types:
            continue

        tc = type_map[parts[0]]
        if len(parts) <= tc:
            continue

        symbol = parts[tc]
        sizes = _get_symbol_data(job_name, symbol, type_map)
        if min(sizes) < 0.001:
            continue

        note_x = note[10][3] / 25.4
        note_y = note[10][4] / 25.4

        if tc == 3:  # PAD
            rd = _geom.get_angle(float(parts[1]), float(parts[2]),
                                 x1=note_x, y1=note_y)
            all_data.append([rd[1] * 1000, 0, sizes, 0,
                             [float(parts[1]), float(parts[2])]])
        elif tc == 5:  # LINE
            line = ((float(parts[1]), float(parts[2])),
                    (float(parts[3]), float(parts[4])))
            point = (note_x, note_y)
            rd = _geom.get_angle(float(parts[1]), float(parts[2]),
                                 x1=float(parts[3]), y1=float(parts[4]))
            rd1 = _geom.get_angle(float(parts[1]), float(parts[2]),
                                  x1=point[0], y1=point[1])
            rd2 = _geom.get_angle(float(parts[3]), float(parts[4]),
                                  x1=point[0], y1=point[1])
            rr = _geom.get_point_line_distance(point, line)
            edge_max = max(rd1[1], rd2[1])
            if rd[1] - edge_max > 0:
                all_data.append([
                    rr * 1000, round(rd[0], 1) % 180,
                    sizes, 1, rd[1] - edge_max,
                ])
        elif tc == 7:  # ARC
            rd = _geom.get_angle(note_x, note_y,
                                 x1=float(parts[5]), y1=float(parts[6]))
            rd1 = _geom.get_angle(float(parts[1]), float(parts[2]),
                                  x1=float(parts[5]), y1=float(parts[6]))
            rd2 = _geom.get_angle(float(parts[5]), float(parts[6]),
                                  x1=0, y1=0)
            all_data.append([
                abs(rd[1] - rd1[1]) * 1000,
                rd2[1], sizes, 2,
            ])

    # 按距离排序（最近的优先）
    all_data.sort(reverse=True)

    if len(all_data) < min_sel:
        return ""

    # 根据计算模式格式化结果
    units = 5 if print_config[1] == "mil" else 2
    info = ""

    if min_sel == 2:
        info = _calc_dual_data(all_data, calc_mode, units)
    elif min_sel == 1:
        if calc_mode == 0 and len(all_data[-1][2]) > 0:
            w = min(all_data[-1][2])
            info = str(round_str(w, units))
        elif calc_mode == 2 and len(all_data[-1][2]) > 1:
            w1 = min(all_data[-1][2])
            w2 = max(all_data[-1][2])
            info = f"{round_str(w1, units)}*{round_str(w2, units)}"

    if info and note[5].replace("/", "").strip():
        kkk1 = note[5].strip("/").split("/")
        kkk2 = info.split("/")
        if len(kkk1) > len(kkk2):
            info = "/".join(kkk2 + kkk1[len(kkk2):])

    print(info)
    return info


def _calc_dual_data(all_data: list, calc_mode: int,
                    units: int) -> str:
    """双特征计算（两个最近特征之间的距离/宽度）"""
    info = ""
    a = all_data[-1]
    b = all_data[-2]

    if calc_mode in (0, 1):  # 线距 / 线宽+线距
        # 两条平行线
        if a[3] == 1 and a[3] == b[3] and abs(a[1] - b[1]) < 1:
            spec = (a[0] + b[0]) - (min(a[2]) + min(b[2])) * 0.5
            if calc_mode == 0:
                info = str(round_str(spec, units))
            else:
                www = min(a[2])
                info = f"{round_str(www, units)}/{round_str(spec, units)}"
        elif a[3] == 2 and a[3] == b[3] and abs(a[1] - b[1]) < 0.002:
            spec = (a[0] + b[0]) - (min(a[2]) + min(b[2])) * 0.5
            if calc_mode == 0:
                info = str(round_str(spec, units))
            else:
                www = min(a[2])
                info = f"{round_str(www, units)}/{round_str(spec, units)}"
    elif calc_mode == 3:  # 中心距
        if a[3] == 0 and a[3] == b[3] and abs(min(a[2]) - min(b[2])) < 0.1:
            rd = _geom.get_angle(a[4][0], a[4][1],
                                 x1=b[4][0], y1=b[4][1])
            spec = rd[1] * 1000
            info = str(round_str(spec, units))
    elif calc_mode == 5:  # 中心距 - PAD 尺寸
        if a[3] == 0 and a[3] == b[3] and abs(min(a[2]) - min(b[2])) < 0.1:
            rd = _geom.get_angle(a[4][0], a[4][1],
                                 x1=b[4][0], y1=b[4][1])
            spec = rd[1] * 1000 - (min(a[2]) + min(b[2])) * 0.5
            info = str(round_str(spec, units))

    return info


# ═══════════════════════════════════════════
# 原稿数据提取（完整流程）
# ═══════════════════════════════════════════

def extract_original_data(job_name: str, step_name: str,
                          layers: List[str]) -> None:
    """从 Genesis 图形中提取原稿值

    对每个标记，在层上选择最近的特征并计算尺寸。
    与原始 get_note_data() 逻辑一致。
    """
    if not layers:
        return

    GenesisAPI._VOF()
    GenesisAPI._COM("config_edit,name=gen_line_skip_post_hooks,value=4,mode=user")
    GenesisAPI._COM("config_edit,name=gen_line_skip_pre_hooks,value=4,mode=user")
    GenesisAPI._VON()

    GenesisAPI.open_step(job_name, step_name, units="inch")
    GenesisAPI._COM('disp_off')

    for lay_info in _group_layered_notes(job_name, step_name, layers):
        lay = lay_info[0]
        notes_list = lay_info[1]

        GenesisAPI._COM(
            f'affected_layer,name={lay},mode=single,affected=yes'
        )

        for note in notes_list:
            # 极性处理
            try:
                polarity = load_dict_all["layer_dist"][lay][2]
            except KeyError:
                polarity = ""

            pol_info = "positive"
            if polarity == "n":
                pol_info = "negative"
                cfg = config.NOTE_SELECT[note[2]]
                if cfg[1] == "pad":
                    pol_info = "positive\\;negative"

            # 设置过滤器
            cfg = config.NOTE_SELECT[note[2]]
            GenesisAPI._COM(f'filter_reset,filter_name=popup')
            GenesisAPI._COM(
                f"filter_set,filter_name=popup,update_popup=no,"
                f"polarity={pol_info}"
            )
            GenesisAPI._COM(
                f"filter_set,filter_name=popup,update_popup=no,"
                f"feat_types={cfg[1]}"
            )

            # 渐进式区域选择
            countz = 9
            step_size = 0.0025
            if cfg[3] == 1:
                countz = 2
                step_size = 0.001
            if cfg[2] == 3:
                countz = 3
                step_size = 0.03

            note_x = note[10][3] / 25.4
            note_y = note[10][4] / 25.4

            for r in range(1, countz):
                offset = step_size * r
                GenesisAPI._COM("filter_area_strt")
                GenesisAPI._COM(
                    f"filter_area_xy,x={note_x - offset},y={note_y - offset}"
                )
                GenesisAPI._COM(
                    f"filter_area_xy,x={note_x + offset},y={note_y + offset}"
                )
                GenesisAPI._COM(
                    "filter_area_end,layer=,filter_name=popup,"
                    "operation=select,area_type=rectangle,"
                    "inside_area=yes,intersect_area=yes"
                )
                GenesisAPI._COM('get_select_count')
                sel_count = int(GenesisAPI._COMANS())
                print(r * step_size, sel_count, cfg[3])

                if sel_count < cfg[3]:
                    continue

                info = get_feature_data(
                    job_name, step_name, lay, note
                )
                GenesisAPI._COM("clear_highlight")
                GenesisAPI._COM("sel_clear_feat")
                print("--->", note[0], note[2:])

                if info:
                    note[5] = info  # 更新原稿值
                    if (not note[4].replace("/", "").replace("*", "").strip() and
                            not note[6].replace("/", "").replace("*", "").strip()):
                        note[4] = info  # 同步成品值

                    # 更新 note 文本
                    zk_info = "&".join(note[6:9]).strip("&")
                    new_text = " ".join([
                        note[3], note[5], note[4],
                        note[5], zk_info, note[9]
                    ])
                    if new_text != note[10][5]:
                        GenesisAPI.change_note(lay, int(note[0]), new_text)
                    break

        GenesisAPI._COM('filter_reset,filter_name=popup')
        GenesisAPI._COM('affected_layer,mode=all,affected=no')

    GenesisAPI._COM('disp_on')
    GenesisAPI._VOF()
    GenesisAPI._COM("config_edit,name=gen_line_skip_post_hooks,value=1,mode=user")
    GenesisAPI._COM("config_edit,name=gen_line_skip_pre_hooks,value=1,mode=user")
    GenesisAPI._VON()


def _group_layered_notes(job_name: str, step_name: str,
                         layers: List[str]) -> List[List]:
    """将标记按层分组"""
    result = []
    for lay in layers:
        notelist = get_notes_new(job_name, step_name, lay)
        ns = [n for n in notelist if n[2] in config.NOTE_SELECT]
        if ns:
            result.append([lay, ns])
    return result


# ═══════════════════════════════════════════
# 阻抗处理
# ═══════════════════════════════════════════

def get_impedance_table(inplan_conn=None) -> List[Dict]:
    """从 InPlan 获取阻抗表

    Args:
        inplan_conn: InPlanQuery 实例

    Returns:
        阻抗信息列表
    """
    if inplan_conn is None:
        try:
            from .database import InPlanQuery
            inplan_conn = InPlanQuery(
                host_info.get("job_name", "")
            )
        except Exception:
            return []

    try:
        imp_info = inplan_conn.get_impedance()
    except Exception:
        imp_info = []

    # 构建阻抗表到 print_config[8]
    print_config[8] = {}
    for imp in imp_info:
        imp_val_str = str(imp.get('CUSTOMER_REQUIRED_IMPEDANCE', ''))
        if not imp_val_str.replace(".", "").strip().isdigit():
            continue

        orig_vals = [
            imp.get('ORIGINAL_TRACE_WIDTH', 0),
            imp.get('DESIGN_TRACE_TRACE_SPACING', 0),
            imp.get('DESIGN_TRACE_GROUND_SPACING', 0),
        ]
        new_vals = [
            imp.get('FINISH_LW_', 0),
            imp.get('FINISH_LS_', 0),
            imp.get('COPPER_SPAC_', 0),
        ]

        for i in range(3):
            orig_vals[i] = round_str(orig_vals[i], 2) if orig_vals[i] else ""
            new_vals[i] = round_str(float(new_vals[i])) if new_vals[i] else ""

        trace_layer = imp.get('TRACE_LAYER_', '')
        if trace_layer:
            key = (f"{trace_layer.strip()}层:"
                   f"{round_str(float(imp_val_str), 2)}{config.DEFAULT_PRINT_CONFIG[2]}"
                   f"-->原稿值{'/'.join(orig_vals)}")
            ref_layer = imp.get('REF_LAYER_', '') or "@"
            if key not in print_config[8]:
                print_config[8][key] = ["", new_vals,
                                        imp.get('REF_LAYER_', ''), "", {}]
            print_config[8][key][4][ref_layer] = ["", "", new_vals]

        trace_layer2 = imp.get('TRACE_LAYER_2_', '')
        if trace_layer2:
            key = (f"{trace_layer2.strip()}层:"
                   f"{round_str(float(imp_val_str), 2)}{config.DEFAULT_PRINT_CONFIG[2]}"
                   f"-->原稿值{'/'.join(orig_vals)}")
            ref_layer2 = imp.get('REF_LAYER_2_', '') or "@"
            if key not in print_config[8]:
                print_config[8][key] = ["", new_vals,
                                        imp.get('REF_LAYER_2_', ''), "", {}]
            print_config[8][key][4][ref_layer2] = ["", "", new_vals]

    return imp_info


def check_impedance(imp_info: List[Dict],
                    zk_list: List[List],
                    info: List[str]) -> Tuple[List[str], str]:
    """校验阻抗信息

    Args:
        imp_info: InPlan 阻抗表
        zk_list:  当前标记的阻抗信息
        info:     [finished, layer, original, imp_value, type, mark, ...]

    Returns:
        (成品值列表, 正确成品值)
    """
    imp_values = []
    imp_correct = ""

    if not imp_info or not zk_list:
        return imp_values, imp_correct

    # 找到匹配的标记
    matched = []
    for zk in zk_list:
        if (zk[-1] == info[-1] and
                zk[1] == info[1].upper() and
                zk[10] == info[3]):
            matched = [zk[5]] + zk[8:10]
            ref_pairs = zk[2:4]
            for i in range(3):
                matched[i] = (round_str(float(matched[i]), 2)
                              if matched[i] else "")
            break

    if not matched:
        return imp_values, imp_correct

    # 构建参考层数组
    fra = "&".join(ref_pairs).strip().strip("&")
    frb = "&".join(ref_pairs[::-1]).strip().strip("&")
    refs = []
    if fra and frb:
        refs = [fra, frb]
    elif fra:
        refs = [fra]
    refs = list(set(refs))

    # 匹配 InPlan 阻抗表
    for imp in imp_info:
        trace_layer = imp.get('TRACE_LAYER_', '')
        if info[1].upper() not in (trace_layer,
                                   imp.get('TRACE_LAYER_2_', '')):
            continue

        try:
            diff = abs(float(imp.get('CUSTOMER_REQUIRED_IMPEDANCE', 0)) -
                       float(info[3]))
        except (ValueError, TypeError):
            diff = 100

        if diff >= 0.1:
            continue

        orig_vals = [
            imp.get('ORIGINAL_TRACE_WIDTH', 0),
            imp.get('DESIGN_TRACE_TRACE_SPACING', 0),
            imp.get('DESIGN_TRACE_GROUND_SPACING', 0),
        ]
        new_vals = [
            imp.get('FINISH_LW_', 0),
            imp.get('FINISH_LS_', 0),
            imp.get('COPPER_SPAC_', 0),
        ]
        for i in range(3):
            orig_vals[i] = round_str(orig_vals[i], 2) if orig_vals[i] else ""
            new_vals[i] = (round_str(float(new_vals[i]))
                           if new_vals[i] else "")

        if "/".join(matched) == "/".join(orig_vals):
            val_str = "/".join(new_vals).strip("/").replace("//", "/")
            imp_values.append(val_str)
            imp_values = list(set(imp_values))

            key = (f"{info[1].upper()}层:"
                   f"{round_str(float(imp.get('CUSTOMER_REQUIRED_IMPEDANCE', 0)), 2)}"
                   f"{config.DEFAULT_PRINT_CONFIG[2]}"
                   f"-->原稿值{'/'.join(orig_vals)}")

            if key in print_config[8]:
                print_config[8][key][0] = info[-1]
                print_config[8][key][3] = info[-2]
                for ref in print_config[8][key][4]:
                    if ref in refs:
                        print_config[8][key][4][ref][0] = info[-1]
                        print_config[8][key][4][ref][1] = info[-2]
                        imp_correct = (
                            "/".join(print_config[8][key][4][ref][2])
                            .strip("/").replace("//", "/")
                        )

    return imp_values, imp_correct


def check_imp_note(layers: List[str]) -> str:
    """检查是否有阻抗线未标注"""
    err = ""
    for key in print_config[8]:
        # 检查 key 中的层名是否在选中的层中
        found = sum(1 for lay in layers
                    if key.startswith(lay.upper() + "层"))
        if found:
            for ref in print_config[8][key][4]:
                if not print_config[8][key][4][ref][0]:
                    if len(print_config[8][key][4]) > 1:
                        err += f"\n{key}参考层{ref}的阻抗线-->没有标notes"
                    elif not print_config[8][key][0]:
                        pass
                    else:
                        err += f"\n{key}的阻抗线-->没有标notes"
    return err


# ═══════════════════════════════════════════
# 阻抗列表构建
# ═══════════════════════════════════════════

def get_impedance_list() -> List[List]:
    """从 load_dict_all 构建阻抗校验列表"""
    zk_list: List[List] = []
    for stp in load_dict_all.get("step_note", {}):
        if stp != print_config[6]:
            continue
        for lay in load_dict_all["step_note"][stp]:
            for note in load_dict_all["step_note"][stp][lay]:
                if (note[2] in config.NOTE_SELECT and
                        config.NOTE_SELECT[note[2]][4] and
                        note[6].replace("/", "").replace("*", "").replace(".", "").strip().isdigit()):
                    parts = note[5].split("/")
                    zk_val = load_dict_all.get("zkdc", "")

                    f = ["单线", lay.upper(),
                         note[7].replace("/", ""),
                         note[8].replace("/", ""),
                         zk_val,
                         parts[0] if parts else "",
                         "+", "-", "", "",
                         note[6], "+", "-", note[0]]

                    try:
                        f[6] = round_str(float(parts[0]) * 0.1)
                        f[7] = round_str(float(parts[0]) * 0.1)
                    except (ValueError, IndexError):
                        f[6] = ""
                        f[7] = ""

                    try:
                        f[11] = round_str(float(note[6]) * 0.1)
                        f[12] = round_str(float(note[6]) * 0.1)
                    except ValueError:
                        f[11] = ""
                        f[12] = ""

                    sel = config.NOTE_SELECT[note[2]]
                    if sel[4] == 1 and len(parts) == 1:
                        pass
                    elif sel[4] == 1 and len(parts) > 1:
                        f[9] = parts[1]
                    elif sel[4] == 2 and len(parts) == 1:
                        f[0] = ""
                    elif sel[4] == 2 and len(parts) == 2:
                        f[0] = "差分"
                        f[8] = parts[1]
                    elif sel[4] == 2 and len(parts) > 2:
                        f[0] = "差分"
                        f[8] = parts[1]
                        f[9] = parts[2]

                    if f[9]:
                        f[0] += "共面"
                    if f[0] and f[6] and f[11]:
                        zk_list.append(f)

    return zk_list


# ═══════════════════════════════════════════
# 线信息汇总
# ═══════════════════════════════════════════

def get_line_info() -> Dict[str, str]:
    """从 load_dict_all 计算每条线的最小线宽/线距"""
    global line_info_all

    result: Dict[str, Any] = {}
    if "step_note" not in load_dict_all:
        return result

    for stp in load_dict_all["step_note"]:
        if stp != print_config[6]:
            continue

        result["smd_min_etch"] = [[]]
        result["bga_min_etch"] = [[]]
        result["smd_min_mask"] = [[]]
        result["bga_min_mask"] = [[]]
        result["smd_min_pitch"] = [[]]
        result["bga_min_pitch"] = [[]]

        for lay in load_dict_all["step_note"][stp]:
            result[lay] = [[], []]
            for note in load_dict_all["step_note"][stp][lay]:
                if note[2] not in config.NOTE_SELECT:
                    continue
                sel = config.NOTE_SELECT[note[2]]

                try:
                    layer_type = load_dict_all["layer_dist"][lay][3]
                except KeyError:
                    continue

                parts = note[4].split("/")
                vals = []
                for p in parts:
                    try:
                        vals.append(float(p))
                    except ValueError:
                        pass

                if sel[5] == 1 and layer_type in ("IN", "LL"):
                    result[lay][0] += vals[0:1]
                    result[lay][1] += vals[1:]
                elif sel[5] == 2 and layer_type in ("IN", "LL"):
                    result[lay][1] += vals
                elif sel[5] == 3 and layer_type == "LL":
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["bga_min_etch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["bga_min_etch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                elif sel[5] == 3 and layer_type == "MM":
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["bga_min_mask"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["bga_min_mask"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                elif sel[5] == 4 and layer_type == "LL":
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["smd_min_etch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["smd_min_etch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                elif sel[5] == 4 and layer_type == "MM":
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["smd_min_mask"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["smd_min_mask"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                elif sel[5] == 5 and layer_type in ("LL", "MM"):
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["bga_min_pitch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["bga_min_pitch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                elif sel[5] == 6 and layer_type in ("LL", "MM"):
                    try:
                        v = float(note[4].replace("*", "/").split("/")[0])
                        result["smd_min_pitch"][0].append(v)
                    except (ValueError, IndexError):
                        pass
                    try:
                        v = float(note[4].replace("*", "/").split("/")[-1])
                        result["smd_min_pitch"][0].append(v)
                    except (ValueError, IndexError):
                        pass

    # 汇总
    line_info = {}
    for lay in result:
        if len(result[lay]) > 1:
            data = result[lay]
            if not data[0] and not data[1]:
                continue
            vals = ["", ""]
            if data[0]:
                vals[0] = round_str(min(data[0]))
            if data[1]:
                vals[1] = round_str(min(data[1]))
            line_info[lay] = "/".join(vals)
            line_info_all[lay] = line_info[lay]
        else:
            if result[lay][0]:
                line_info[lay] = round_str(min(result[lay][0]))
                line_info_all[lay] = line_info[lay]

    return line_info


# ═══════════════════════════════════════════
# 数据管理
# ═══════════════════════════════════════════

def save_load_dict(load_dict: Dict) -> None:
    """保存 load_dict 到全局并更新元数据"""
    global load_dict_all

    _clear_notes_dist(load_dict)
    host_info["mark_count"] = len(_get_note_count(load_dict))
    host_info["modify_time"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
    )

    for k in host_info:
        load_dict[k] = host_info[k]

    load_dict_all = load_dict


def _get_note_count(load_dict: Dict, layer_name: str = "",
                    step_name: str = "cad") -> List:
    """统计标记数量"""
    result = []
    if "step_note" not in load_dict:
        return result
    if "layer_file" not in load_dict:
        return result

    layers = list(load_dict["layer_file"].keys())
    for stp in load_dict["step_note"]:
        if step_name and stp != step_name:
            continue
        for lay in load_dict["step_note"][stp]:
            if layer_name and lay != layer_name:
                continue
            if lay not in layers:
                continue
            for note in load_dict["step_note"][stp][lay]:
                result.append(note[11])
    return result


def get_board_size(load_dict: Dict) -> str:
    """获取板面尺寸

    Returns:
        "width*height" 格式，失败返回 "/"
    """
    if "run_profile" not in load_dict:
        return "/"
    profile = load_dict["run_profile"]
    if not profile:
        return "/"

    try:
        fx = round(abs(profile['gPROF_LIMITSxmin'] -
                       profile['gPROF_LIMITSxmax']), 2)
    except (KeyError, TypeError):
        fx = 0
    try:
        fy = round(abs(profile['gPROF_LIMITSymin'] -
                       profile['gPROF_LIMITSymax']), 2)
    except (KeyError, TypeError):
        fy = 0

    if not (fx * fy):
        return "/"
    return f"{fx}*{fy}"


def get_move_offset(load_dict: Dict) -> None:
    """计算坐标偏移（继承时使用）"""
    print_config[13][0] = 0
    print_config[13][1] = 0

    a = get_board_size(load_dict)
    b = get_board_size(host_info)

    if "/" in (a, b):
        return
    if a != b:
        return

    pa = load_dict["run_profile"]
    pb = host_info["run_profile"]
    print_config[13][0] = pb['gPROF_LIMITSxmin'] - pa['gPROF_LIMITSxmin']
    print_config[13][1] = pb['gPROF_LIMITSymin'] - pa['gPROF_LIMITSymin']


def get_code(load_dict: Dict) -> str:
    """生成唯一的 note key（5 位数字）"""
    for x in range(100000):
        key = str(x).rjust(5, "0")
        if "layer_note" not in load_dict:
            return key
        if key not in load_dict["layer_note"]:
            return key
    return "00000"


def get_editer() -> None:
    """读取编辑者名称"""
    json_file = config.EDITOR_JSON
    data = read_json(json_file)
    name = data.get("editer_name", "")

    if print_config[5] and print_config[5] != name:
        data["editer_name"] = print_config[5]
        save_json(json_file, data)
    else:
        print_config[5] = name


# ═══════════════════════════════════════════
# 历史数据查找
# ═══════════════════════════════════════════

def find_genesis_data(job_name: str) -> List[List]:
    """在 Genesis 本地查找历史标记数据"""
    if not job_name:
        return []
    parts = job_name.strip("*").strip().split("*")
    if len(parts) < 2:
        return []

    jobs_dir = os.path.join(config.GENESIS_DIR, "fw", "jobs")
    try:
        dir_list = os.listdir(jobs_dir)
    except FileNotFoundError:
        dir_list = []

    results = []
    for name in dir_list:
        if (name[1:].find(parts[0]) == 0 and
                name[8:].find(parts[1]) == 0):
            load_dict = read_json(get_json_name(name))
            if len(parts) > 2 and ("?" in parts[2] or "？" in parts[2]):
                results += _find_genesis_old_data(name)
            if load_dict:
                row = ["Genesis", name, name[11:13].upper(),
                       "", "", "", "", "", "", load_dict]
                try:
                    row[8] = load_dict["modify_time"]
                except KeyError:
                    try:
                        row[8] = time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(
                                os.stat(get_json_name(name)).st_mtime
                            )
                        )
                    except Exception:
                        row[8] = "/"
                try:
                    row[3] = str(load_dict["mark_count"])
                except KeyError:
                    row[3] = "/"
                row[4] = get_board_size(load_dict)
                try:
                    row[5] = load_dict["mi_maker"]
                except KeyError:
                    row[5] = "/"
                try:
                    row[7] = load_dict["win_user"]
                except KeyError:
                    row[7] = "/"
                results.append(row)

    return results


def _find_genesis_old_data(job_name: str) -> List[List]:
    """查找旧版日志中的标记数据"""
    log_file = get_json_name(job_name).replace(
        "/job_notes.json", "/notes_mysql.log"
    )
    try:
        lines = open(log_file, 'r', encoding='gbk').readlines()
    except FileNotFoundError:
        return []

    # 按时间分组
    tmps = {}
    gfkey = ""
    for line in lines:
        if line.startswith("20") and "：" in line:
            gfkey = line.strip().split("：")[0]
        elif gfkey and line.strip():
            tmps.setdefault(gfkey, []).append(line.strip())

    # 提取 SQL
    all_dist = {}
    for gfkey in tmps:
        vvs = {}
        kkk = ""
        for line in tmps[gfkey]:
            if line.startswith("insert into mi_db.drawings_marked"):
                kkk = "insert"
            elif line.startswith("update mi_db.drawings_marked set"):
                kkk = "update"
            elif line.startswith("select "):
                kkk = ""
            elif line.startswith("mysql_info = "):
                kkk = "mysql_info"
                vvs[kkk] = [line[len("mysql_info = "):]]
            elif kkk:
                vvs.setdefault(kkk, []).append(line.strip(","))
        if vvs:
            all_dist[gfkey] = vvs

    # 解析数据
    data_info = []
    for gfkey in all_dist:
        for kkk in all_dist[gfkey]:
            if kkk == "insert" and "values" in all_dist[gfkey][kkk]:
                iii = all_dist[gfkey][kkk].index("values")
                ks = all_dist[gfkey][kkk][1:iii - 1]
                vs = all_dist[gfkey][kkk][iii + 2:-1]
                if len(ks) == len(vs):
                    tmp = {}
                    for j in range(len(ks)):
                        tmp[ks[j]] = vs[j].strip("'")
                    tmp["update_time"] = gfkey
                    tmp["barod_size"] = "/"
                    try:
                        tmp["rev"] = tmp["job_name"][11:13].upper()
                    except KeyError:
                        tmp["rev"] = ""
                    if len(tmp) > 9:
                        data_info.append(tmp)
            elif kkk == "update":
                tmp = {}
                for line in all_dist[gfkey][kkk]:
                    idx = line.find("=")
                    if idx > 2:
                        k = line[:idx].strip().split()[-1]
                        v = line[idx + 1:].strip().strip("'")
                        tmp[k] = v
                tmp["update_time"] = gfkey
                tmp["barod_size"] = "/"
                try:
                    tmp["rev"] = tmp["job_name"][11:13].upper()
                except KeyError:
                    tmp["rev"] = ""
                if len(tmp) > 9:
                    data_info.append(tmp)

    return _format_mysql_data(data_info, "")


def find_mysql_data(job_name: str) -> List[List]:
    """从 MySQL 查找历史标记数据"""
    if not job_name:
        return []
    parts = job_name.strip("*").strip().split("*")
    if len(parts) < 2:
        return []

    try:
        from .database import MySQLQuery
        db = MySQLQuery()
    except Exception:
        return []

    sql_like = f"_{parts[0]}____{parts[1]}*"
    data = db.get_data(sql_like)
    return _format_mysql_data(data, "数据库")


def _format_mysql_data(data: list, prefix: str) -> List[List]:
    """格式化 MySQL 数据为 UI 列表"""
    attr_list = """
        job_name, rev, mark_count, barod_size,
        create_by_name, create_time,
        update_by_name, update_time, marks_json
    """.replace(",", "").split()

    results = []
    for row in data:
        vals = [prefix]
        for attr in attr_list:
            val = row.get(attr, "")
            try:
                if isinstance(val, str) and "{" in val and "}" in val:
                    try:
                        val = eval(val.replace("\n", "")
                                   .replace(": null,", ": None,")
                                   .replace(":null,", ":None,"))
                    except Exception:
                        val = {}
                vals.append(val)
            except Exception:
                vals.append("")

        if vals[9]:
            vals[4] = get_board_size(vals[9])
            if not vals[7]:
                try:
                    vals[7] = vals[9].get("win_user", "/")
                except Exception:
                    vals[7] = "/"
            results.append(vals)

    return results


# ═══════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════

__all__ = [
    # 配置
    'print_config', 'host_info', 'load_dict_all', 'line_info_all',
    # 数据持久化
    'read_json', 'save_json', 'get_json_name',
    # 主机信息
    'get_host',
    # Genesis 接口
    'GenesisAPI',
    # 层信息
    'get_layers', 'init_layers',
    # Note 提取
    'get_notes', 'parseNotes', 'get_notes_new',
    # 排序
    'sort_notes',
    # 原稿提取
    'extract_original_data', 'get_feature_data', 'get_pad_size',
    # 阻抗
    'get_impedance_table', 'check_impedance', 'check_imp_note',
    'get_impedance_list',
    # 线信息
    'get_line_info',
    # 字符串生成
    'get_string_new',
    # 单位转换
    'get_mm_new',
    # 数据管理
    'save_load_dict', 'get_board_size', 'get_move_offset',
    'get_code', 'get_editer',
    # 查找
    'find_genesis_data', 'find_mysql_data',
]
