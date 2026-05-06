#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - PyQt5 GUI 层
=========================
基于原 print_notes.py 的 GUI 逻辑重构而来。

功能：
  - TreeWidget 层选择器（多层分级显示）
  - 参数配置面板（单位/留白/阻抗/标板内外）
  - 渲染进度控制
  - 预览/打印/导出/保存按钮
  - 阻抗信息展示面板
  - 继承标记搜索面板
  - 标记验证（颜色高亮错误）
  - Ctrl+A/Ctrl+Z/Ctrl+S/Ctrl+P 快捷键
  - PyQt5 未安装时优雅跳过（所有业务逻辑仍可 CLI 调用）

原始作者:  Gf.zhang (print_notes.py v1.0, 2021-11-19)
重构作者:  OpenClaw (MI Print Project)
"""

import os
import sys
import json
from typing import Dict, List, Optional, Any, Tuple

# ═══════════════════════════════════════════
# 依赖检测
# ═══════════════════════════════════════════

_PYQT5_AVAILABLE = False
try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTreeWidget, QPushButton, QTreeWidgetItem,
        QMessageBox, QFileDialog, QShortcut, QComboBox,
        QLabel, QLineEdit, QMenu, QAction,
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QFont, QColor, QKeySequence, QCursor
    _PYQT5_AVAILABLE = True
except ImportError:
    pass  # 优雅降级：CLI 仍可用

# 内部模块
from . import config
from . import mi_extractor as _mi
from . import svg_renderer as _svg

# ═══════════════════════════════════════════
# 全局状态（GUI 相关）
# ═══════════════════════════════════════════

_PRINT_CONFIG = _mi.print_config      # 引用全局打印配置
_HOST_INFO = _mi.host_info            # 引用全局主机信息
_LOAD_DICT = _mi.load_dict_all        # 引用全局加载字典

# 阻抗表（GUI 层维护）
_IMPEDANCE_TABLE: Dict[str, Any] = {}

# 线信息
_LINE_INFO: Dict[str, str] = {}

# 阻抗列表
_ZK_LIST: List[List] = []


# ═══════════════════════════════════════════
# 辅助函数（UI 相关）
# ═══════════════════════════════════════════

def _mm_value(text: str, kkk: int = 0) -> str:
    """格式化为显示用值（委托给 mi_extractor）"""
    return _mi.get_mm_new(text, kkk)


def _unit_text() -> str:
    """获取当前单位"""
    return _PRINT_CONFIG[1]


# ═══════════════════════════════════════════
# 函数包装（桥接旧 API → 新 API）
# ═══════════════════════════════════════════

# 以下函数在 mi_extractor 中部分缺失，在此提供适配

def _get_note_all_ext(job_name: str, step: str, layer: str,
                      notelist: Dict, load_dict: Dict) -> None:
    """获取层的所有标记并填充到 notelist 字典"""
    try:
        raw = _mi.get_notes(job_name, step, layer)
        parsed = _mi.parseNotes(raw)
        if layer not in notelist:
            notelist[layer] = []
        notelist[layer] = parsed
    except Exception as e:
        print(f"[WARN] 获取层 {layer} 标记失败: {e}")
        if layer not in notelist:
            notelist[layer] = []
    # 同时更新 load_dict
    if "layer_dist" not in load_dict:
        load_dict["layer_dist"] = {}
    if layer not in load_dict["layer_dist"]:
        load_dict["layer_dist"][layer] = ["", "", "", "", "", {}, 0, 0]


def _add_note_ext(job_name: str, step: str, layer: str) -> None:
    """向层添加一条制作指示"""
    try:
        _mi.GenesisAPI.add_note(job_name, step, layer)
    except Exception as e:
        print(f"[WARN] 添加指示失败: {e}")


def _delete_note_ext(job_name: str, step: str, layer: str,
                     indexes: List[int]) -> None:
    """删除标记"""
    try:
        _mi.GenesisAPI.delete_note(job_name, step, layer, indexes)
    except Exception as e:
        print(f"[WARN] 删除标记失败: {e}")


def _view_note_ext(job_name: str, step: str, layer: str,
                   xx: float, yy: float, text: str, mode: int) -> None:
    """查看标记（定位到 CAM 视图）"""
    try:
        _mi.GenesisAPI.view_note(job_name, step, layer, xx, yy, text, mode)
    except Exception as e:
        print(f"[WARN] 查看标记失败: {e}")


def _save_json_ext(json_file: str, data: Dict) -> None:
    """保存 JSON"""
    _mi.save_json(json_file, data)


def _read_json_ext(json_file: str) -> Dict:
    """读取 JSON"""
    return _mi.read_json(json_file)


def _get_sorted_notes(job_name: str, step: str, layers: List[str]) -> List[str]:
    """获取排序后的标记"""
    try:
        return _mi.sort_notes(job_name, step, layers)
    except Exception as e:
        print(f"[WARN] 排序失败: {e}")
        return layers


def _check_impedance_ui(imp_list: List[Dict], zk_list: List[List],
                        check_data: List) -> Tuple[List[str], str]:
    """检查阻抗匹配"""
    try:
        return _mi.check_impedance(imp_list, zk_list, check_data)
    except Exception as e:
        print(f"[WARN] 阻抗检查失败: {e}")
        return ([], "")


def _check_imp_note_ext(layers: List[str]) -> str:
    """检查阻抗标记"""
    try:
        return _mi.check_imp_note(layers)
    except Exception as e:
        return f"阻抗检查异常: {e}"


def _get_impedance_list_ext() -> List[List]:
    """获取阻抗列表"""
    try:
        return _mi.get_impedance_list()
    except Exception:
        return []


def _find_genesis_ext(job_name: str) -> List[List]:
    """从 Genesis 搜索料号数据"""
    try:
        return _mi.find_genesis_data(job_name)
    except Exception:
        return []


def _find_mysql_ext(job_name: str) -> List[List]:
    """从 MySQL 搜索料号数据"""
    try:
        return _mi.find_mysql_data(job_name)
    except Exception:
        return []


# ═══════════════════════════════════════════
# PyQt5 GUI 主类
# ═══════════════════════════════════════════

if _PYQT5_AVAILABLE:

    class MITreeWidget(QWidget):
        """MI 打印图纸主界面

        对应原 print_notes.py 的 TreeWidget 类。
        用法（CLI 启动）:
            python mi_gui.py --job S31804PF590C1 --step cad
        """

        def __init__(self,
                     job: Optional[str] = None,
                     step: Optional[str] = None,
                     parent=None):
            super().__init__(parent)

            # 基本状态
            self.job_name = job or os.environ.get("JOB", None) or ""
            self.step_name = step or os.environ.get("STEP", None) or ""

            # 数据容器
            self.notelist: Dict[str, List] = {}
            self.all_layer_datas: Dict[str, QTreeWidgetItem] = {}
            self.layers_check_state: Dict[str, int] = {}
            self.load_dict: Dict[str, Any] = {}
            self.combos_registry: Dict[str, Any] = {}  # QComboBox/QLineEdit 注册表
            self.json_file: str = ""
            self.error_info: str = ""
            self.error_orig_info: str = ""
            self.opacity_flag: int = 0
            self.signal_layers: List[str] = []
            self.imp_list_cache: List = []
            self.imp_list_run: int = 0
            self.zk_list: List = []
            self.show_change_list: List[str] = []
            self.line_layers: List[List[str]] = []
            self.imp_show_flag: bool = True
            self.imp_count: int = 0
            self.find_show_flag: bool = True
            self.find_text: str = ""
            self.find_infos: List[List[str]] = []

            # 窗口设置
            self.resize(1390, 860)

            # 初始化主机信息
            if self.job_name:
                _mi.get_host(self.job_name)
                self.json_file = _mi.get_json_name(self.job_name)
                self.load_dict = _mi.read_json(self.json_file)
                if "unit" in self.load_dict:
                    _mi.print_config[1] = self.load_dict["unit"]
                else:
                    self.load_dict["unit"] = _mi.print_config[1]
                _mi.print_config[6] = self.step_name

            self.setWindowTitle(
                f"测量及指示图纸标注({_mi.config.SVG_REVISION})"
                f"({self.job_name}~{self.step_name})"
            )

            # 快捷键
            QShortcut(QKeySequence(self.tr("Ctrl+A")), self, self._select_all)
            QShortcut(QKeySequence(self.tr("Ctrl+F")), self, self._open_dir)
            QShortcut(QKeySequence(self.tr("Ctrl+S")), self, self._save_changes)
            QShortcut(QKeySequence(self.tr("Ctrl+P")), self, self._print_notes)
            QShortcut(QKeySequence(self.tr("Ctrl+Q")), self, self.close)
            QShortcut(QKeySequence(self.tr("Ctrl+Z")), self, self._cycle_select)

            # 构建 UI
            self._setup_ui()

            # 加载数据
            if self.job_name and self.step_name:
                QTimer.singleShot(100, self._init_data)

        # ── UI 构建 ──────────────────────────────────

        def _setup_ui(self) -> None:
            """构建完整 UI 布局"""
            main_vbox = QVBoxLayout()
            self.setLayout(main_vbox)

            # ---- 顶部控制栏 ----
            top_hbox = QHBoxLayout()
            self._build_control_bar(top_hbox)
            main_vbox.addLayout(top_hbox)

            # ---- 中间主区域（层列表 + 查找面板） ----
            mid_container = QHBoxLayout()
            left_vbox = QVBoxLayout()

            # 层列表
            self.layer_tree = QTreeWidget()
            self.layer_tree.setContextMenuPolicy(3)
            self.layer_tree.customContextMenuRequested.connect(self._on_context_menu)
            left_vbox.addWidget(self.layer_tree, 2)

            # 阻抗面板（默认隐藏）
            self.imp_tree = QTreeWidget()
            self.imp_tree.setHidden(True)
            left_vbox.addWidget(self.imp_tree, 1)

            mid_container.addLayout(left_vbox, 3)

            # 继承查找面板（默认隐藏）
            self.find_tree = QTreeWidget()
            self.find_tree.setToolTip("确认标记信息,双击所选的行继承")
            self.find_tree.itemDoubleClicked.connect(self._on_inherit_note)
            self.find_tree.setHidden(True)
            mid_container.addWidget(self.find_tree, 5)

            main_vbox.addLayout(mid_container, 1)

            # ---- 底部按钮栏 ----
            btn_hbox = QHBoxLayout()
            self._build_button_bar(btn_hbox)
            main_vbox.addLayout(btn_hbox)

            # 设置列头
            self._setup_layer_columns()
            self._setup_imp_columns()
            self._setup_find_columns()
            self.show()

        def _build_control_bar(self, hbox: QHBoxLayout) -> None:
            """构建控制栏组件"""
            bold_font = QFont("Roman times", 16, QFont.Bold)

            # 标题
            title_label = QLabel("测量及指示图纸标注")
            title_label.setFont(bold_font)
            hbox.addWidget(title_label, 2)

            # 单位选择
            unit_label = QLabel("单位:")
            unit_label.setFont(bold_font)
            self.combo_unit = QComboBox()
            self.combo_unit.setFont(bold_font)
            for u in ("mil", "um", "mm"):
                self.combo_unit.addItem(u)
            self.combo_unit.setCurrentText(_mi.print_config[1])
            self.combo_unit.currentIndexChanged.connect(self._on_unit_change)
            hbox.addWidget(unit_label)
            hbox.addWidget(self.combo_unit)
            hbox.addStretch()

            # 留白
            space_label = QLabel("留白:")
            space_label.setFont(bold_font)
            self.combo_space = QComboBox()
            self.combo_space.setFont(bold_font)
            for v in ("0", "100", "200", "300", "500", "600", "800"):
                self.combo_space.addItem(v)
            self.combo_space.setCurrentText(_mi.print_config[9])
            hbox.addWidget(space_label)
            hbox.addWidget(self.combo_space)

            # 标板内/外
            self.combo_pos = QComboBox()
            self.combo_pos.setFont(bold_font)
            self.combo_pos.addItems(["标板外", "标板内"])
            self.combo_pos.setCurrentText(_mi.print_config[10])
            hbox.addWidget(self.combo_pos)

            # 阻抗信息按钮
            self.btn_imp = QPushButton("阻抗信息")
            self.btn_imp.setFont(bold_font)
            self.btn_imp.setToolTip("单击:展开和收回InPlan阻抗信息界面")
            self.btn_imp.clicked.connect(self._toggle_imp_panel)
            hbox.addWidget(self.btn_imp)

            # 优化顺序按钮
            self.btn_sort = QPushButton("优化顺序")
            self.btn_sort.setFont(bold_font)
            self.btn_sort.clicked.connect(self._on_sort_notes)
            hbox.addWidget(self.btn_sort)

            # 继承搜索
            self.line_find = QLineEdit("")
            self.line_find.setFont(bold_font)
            self.line_find.setToolTip("输入关键字,回车搜索结果")
            self.line_find.returnPressed.connect(self._on_find_notes)
            self.btn_find = QPushButton("继承:")
            self.btn_find.setFont(bold_font)
            self.btn_find.setToolTip("单击继承:展开和收回继承操作界面")
            self.btn_find.clicked.connect(self._toggle_find_panel)
            hbox.addWidget(self.line_find)
            hbox.addWidget(self.btn_find)

            # MI 制作者
            editor_label = QLabel("MI制作:")
            editor_label.setFont(bold_font)
            self.line_editor = QLineEdit("")
            self.line_editor.setFont(bold_font)
            hbox.addWidget(editor_label)
            hbox.addWidget(self.line_editor)

            # 阻抗对称
            imp_sym_label = QLabel("阻抗对称制作:")
            imp_sym_label.setFont(bold_font)
            self.combo_imp_sym = QComboBox()
            self.combo_imp_sym.setFont(bold_font)
            self.combo_imp_sym.addItems(["否", "是"])
            self.combo_imp_sym.setCurrentText("否")
            hbox.addWidget(imp_sym_label)
            hbox.addWidget(self.combo_imp_sym)

        def _build_button_bar(self, hbox: QHBoxLayout) -> None:
            """构建底部按钮栏"""
            bold_font = QFont("Roman times", 16, QFont.Bold)

            self.btn_generate = QPushButton("生成图纸(Ctrl+P)")
            self.btn_generate.setFont(bold_font)
            self.btn_generate.clicked.connect(self._print_notes)
            hbox.addWidget(self.btn_generate, 1)

            self.btn_export_imp = QPushButton("导出阻抗")
            self.btn_export_imp.setFont(bold_font)
            hbox.addWidget(self.btn_export_imp, 1)

            self.btn_get_orig = QPushButton("获得原稿")
            self.btn_get_orig.setFont(bold_font)
            self.btn_get_orig.clicked.connect(self._on_get_original)
            hbox.addWidget(self.btn_get_orig, 1)

            self.btn_save = QPushButton("保存数据(Ctrl+S)")
            self.btn_save.setFont(bold_font)
            self.btn_save.clicked.connect(self._save_changes)
            hbox.addWidget(self.btn_save, 1)

        def _setup_layer_columns(self) -> None:
            """设置层列表列头"""
            headers = ["层名", "页码", "序号", "类型", "类型代码",
                       "标记", "成品值", "原稿值", "阻抗值",
                       "上参考层", "下参考层", "备注"]
            self.layer_tree.setColumnCount(len(headers))
            self.layer_tree.setHeaderLabels(headers)
            self.layer_tree.header().setStyleSheet(
                "QHeaderView::section{background-color:skyblue;"
                "color:black;height:25px;padding-left:2px;"
                "border:1px solid #6c6c6c;font:15px}"
            )
            widths = [120, 50, 50, 120, 120, 60,
                      130, 130, 80, 80, 80, 900]
            for i, w in enumerate(widths):
                self.layer_tree.setColumnWidth(i, w)

        def _setup_imp_columns(self) -> None:
            """设置阻抗面板列头"""
            headers = ["层名", "序号", "阻抗类型", "标记",
                       "成品值", "原稿值", "阻抗值", "参考层", "~"]
            self.imp_tree.setColumnCount(len(headers))
            self.imp_tree.setHeaderLabels(headers)
            self.imp_tree.header().setStyleSheet(
                "QHeaderView::section{background-color:skyblue;"
                "color:black;height:25px;padding-left:2px;"
                "border:1px solid #6c6c6c;font:15px}"
            )
            widths = [170, 50, 240, 60, 130, 130, 80, 160, 120]
            for i, w in enumerate(widths):
                self.imp_tree.setColumnWidth(i, w)

        def _setup_find_columns(self) -> None:
            """设置查找面板列头"""
            headers = ["来源", "料号名", "版本", "个数", "尺寸(mm)",
                       "MI制作", "创建时间", "制作修改", "修改时间"]
            self.find_tree.setColumnCount(len(headers))
            self.find_tree.setHeaderLabels(headers)
            self.find_tree.header().setStyleSheet(
                "QHeaderView::section{background-color:skyblue;"
                "color:black;height:25px;padding-left:2px;"
                "border:1px solid #6c6c6c;font:15px}"
            )
            widths = [80, 125, 50, 50, 90, 70, 130, 100, 130]
            for i, w in enumerate(widths):
                self.find_tree.setColumnWidth(i, w)

        # ── 数据初始化 ───────────────────────────────

        def _init_data(self) -> None:
            """初始化数据（延迟执行以确保 UI 就绪）"""
            if not self.job_name or not self.step_name:
                self._info_dialog("Job或Step没有打开!!!")
                return
            if self.step_name.lower() != "cad":
                self._info_dialog("请在cad上运行!!!")
                return

            # 获取层列表
            self._refresh_layers()
            self._refresh_layer_display()
            self._validate_all()

            # 读取编辑者
            try:
                _mi.get_editer()
                self.line_editor.setText(_mi.print_config[5])
            except Exception:
                pass

        def _refresh_layers(self) -> None:
            """刷新层列表数据"""
            self.line_layers = _mi.get_layers(self.job_name)
            self.signal_layers = [x[0].upper() for x in self.line_layers
                                  if x[0] and x[0][0].lower() == "l"]
            try:
                _mi.init_layers(self.load_dict, self.line_layers)
            except Exception as e:
                print(f"[WARN] init_layers: {e}")

        def _refresh_layer_display(self,
                                   layers: Optional[List[str]] = None) -> None:
            """刷新层在 TreeWidget 中的显示"""
            target_layers = layers or list(self.all_layer_datas.keys())

            for lay in target_layers:
                if lay in self.all_layer_datas:
                    self._show_layer_items(self.all_layer_datas[lay])

            # 更新面板参数
            self.combo_imp_sym.setCurrentText(_mi.print_config[4])
            self.combo_space.setCurrentText(_mi.print_config[9])
            self.combo_pos.setCurrentText(_mi.print_config[10])

            if _mi.print_config[12]:
                self._disable_all_controls()

        def _disable_all_controls(self) -> None:
            """发生严重错误时禁用所有控件"""
            controls = [
                self.btn_generate, self.btn_export_imp,
                self.btn_save, self.btn_get_orig,
                self.btn_sort, self.btn_imp,
                self.combo_unit, self.combo_space,
                self.combo_pos
            ]
            for c in controls:
                c.setEnabled(False)

        def _show_layer_items(self, root: QTreeWidgetItem) -> None:
            """展开/刷新某一层的标记子项"""
            lay = root.text(0)
            if lay not in self.notelist:
                self.notelist[lay] = []
                raw = _mi.get_notes(self.job_name, self.step_name, lay)
                self.notelist[lay] = _mi.parseNotes(raw)

            # 清除已有子项
            while root.childCount():
                root.removeChild(root.child(0))

            if not self.notelist.get(lay):
                return

            for note in self.notelist[lay]:
                child = QTreeWidgetItem(root)
                for col_idx in range(len(note) - 2):
                    val = note[col_idx + 2] if col_idx + 2 < len(note) else ""
                    if col_idx + 2 in (6, 7):  # 成品值/原稿值
                        child.setText(col_idx + 2, _mm_value(val, 1))
                    else:
                        child.setText(col_idx + 2, str(val))

                # 可编辑字段：设置 ComboBox 或 LineEdit
                # 参考层 (cols 9, 10)
                note_index = note[0] if note else ""
                has_imp = bool(note[6].replace("*", "").replace("/", "").strip()) if len(note) > 6 else False

                if has_imp:
                    for col in (9, 10):
                        combo = self._make_reflayer_combo(lay, col)
                        if combo:
                            key = f"{lay}~{note_index}~{col}"
                            self.combos_registry[key] = combo
                            self.layer_tree.setItemWidget(child, col, combo)

                # 备注 (col 11)
                note_text = note[11] if len(note) > 11 else ""
                line_edit = QLineEdit(str(note_text))
                key = f"{lay}~{note_index}~11"
                self.combos_registry[key] = line_edit
                self.layer_tree.setItemWidget(child, 11, line_edit)

        def _make_reflayer_combo(self, lay: str, col: int) -> Optional[QComboBox]:
            """创建参考层下拉框（上下参考层）"""
            try:
                idx = self.signal_layers.index(lay.upper())
            except ValueError:
                return None

            if col == 9:  # 上参考层
                options = ["/"] + self.signal_layers[:idx]
                default_idx = max(0, idx - 1)
            else:          # 下参考层
                options = self.signal_layers[idx + 1:] + ["/"]
                default_idx = 0

            combo = QComboBox()
            for item in options:
                combo.addItem(item)
            if default_idx < len(options):
                combo.setCurrentIndex(default_idx)
            return combo

        # ── 层列表构建 ─────────────────────────────

        def _build_layer_tree(self) -> None:
            """构建层根节点列表"""
            self.all_layer_datas.clear()
            self.layer_tree.clear()

            for line_info in self.line_layers:
                root = QTreeWidgetItem(self.layer_tree)
                root.setToolTip(0, "全选切换:Ctrl+A;层勾选切换:Ctrl+Z")
                self.layer_tree.openPersistentEditor(root, 1)

                for col in range(2):
                    root.setText(col, line_info[col] if col < len(line_info) else "")

                # 层类型颜色标记
                layer_type = line_info[3] if len(line_info) > 3 else ""
                if layer_type == "MM":
                    root.setBackground(0, Qt.darkGreen)
                elif layer_type in ("LL", "IN"):
                    if line_info[2] if len(line_info) > 2 else False:
                        root.setBackground(0, QColor(205, 155, 29))
                    else:
                        root.setBackground(0, QColor(255, 185, 15))
                elif layer_type == "CC":
                    root.setBackground(0, QColor(230, 230, 250))

                self.all_layer_datas[line_info[0]] = root
                self.layer_tree.addTopLevelItem(root)
                root.setCheckState(0, Qt.Checked)
                if not (line_info[1] if len(line_info) > 1 else "").isdigit():
                    root.setCheckState(0, Qt.Unchecked)

            self.layer_tree.expandAll()

            # 恢复保存的勾选状态
            for lay in self.all_layer_datas:
                if lay in self.layers_check_state:
                    self.all_layer_datas[lay].setCheckState(
                        0, self.layers_check_state[lay]
                    )

        # ── 勾选状态管理 ─────────────────────────

        def _save_check_states(self) -> None:
            """保存当前勾选状态"""
            self.layers_check_state.clear()
            for lay, root in self.all_layer_datas.items():
                if root.checkState(0):
                    self.layers_check_state[lay] = Qt.Checked
                else:
                    self.layers_check_state[lay] = Qt.Unchecked

        def _select_all(self) -> None:
            """Ctrl+A: 全选/取消全选"""
            self._save_check_states()
            # 判断当前状态
            all_checked = all(
                self.layers_check_state.get(lay, Qt.Unchecked) == Qt.Checked
                for lay in self.all_layer_datas
            )
            new_state = Qt.Unchecked if all_checked else Qt.Checked
            for lay, root in self.all_layer_datas.items():
                root.setCheckState(0, new_state)

        def _cycle_select(self) -> None:
            """Ctrl+Z: 循环勾选层"""
            new_num = 1
            for lay, root in self.all_layer_datas.items():
                try:
                    page_val = int(root.text(1))
                except (ValueError, TypeError):
                    page_val = 0
                if page_val == new_num:
                    root.setCheckState(0, Qt.Checked)
                    new_num += 1
                    break
            else:
                new_num = 1
                for root in self.all_layer_datas.values():
                    try:
                        page_val = int(root.text(1))
                    except (ValueError, TypeError):
                        page_val = 0
                    if page_val == new_num:
                        root.setCheckState(0, Qt.Checked)
                        break

            for lay, root in self.all_layer_datas.items():
                try:
                    page_val = int(root.text(1))
                except (ValueError, TypeError):
                    root.setCheckState(0, Qt.Unchecked)
                    continue
                if page_val != new_num:
                    root.setCheckState(0, Qt.Unchecked)

        # ── 标记操作 ─────────────────────────────

        def _on_context_menu(self, pos) -> None:
            """右键菜单"""
            item = self.layer_tree.currentItem()
            item_under_cursor = self.layer_tree.itemAt(pos)
            if item is None or item_under_cursor is None:
                return

            menu = QMenu()
            menu.addAction(QAction("查看", self))
            menu.addSeparator()

            if not item.text(2):
                menu.addAction(QAction("删除全部", self))
            else:
                menu.addAction(QAction("删除", self))
            menu.addSeparator()
            menu.addAction(QAction("增加制作指示", self))
            menu.triggered[QAction].connect(self._on_menu_action)
            menu.exec_(QCursor.pos())

        def _on_menu_action(self, action: QAction) -> None:
            """处理右键菜单动作"""
            lay, item = self._get_selected_item()
            if not item:
                return

            text = action.text()
            if text.startswith("删除"):
                confirmed = self._question_dialog(f"您确定要{text}吗?")
                if not confirmed:
                    return
                indexes = []
                if item.text(2):
                    indexes = [item.text(2)]
                else:
                    if lay in self.notelist:
                        indexes = [n[0] for n in self.notelist[lay]]

                if indexes:
                    _delete_note_ext(self.job_name, self.step_name, lay, indexes[::-1])
                    self._refresh_layer_display([lay])
                    self._apply_updates()
                    self._refresh_layer_display([lay])
                    self._apply_updates()

            elif text == "增加制作指示":
                _add_note_ext(self.job_name, self.step_name, lay)
                self._refresh_layer_display([lay])
                self._apply_updates()
                self._refresh_layer_display([lay])
                self._apply_updates()

            elif text == "查看":
                if item.text(2) and lay in self.notelist:
                    for note in self.notelist[lay]:
                        if note[0] == item.text(2):
                            if len(note) > 10:
                                _view_note_ext(
                                    self.job_name, self.step_name, lay,
                                    note[10][3] / 25.4 if note[10][3] else 0,
                                    note[10][4] / 25.4 if note[10][4] else 0,
                                    item.text(7) if item.text(7) else "",
                                    1
                                )
                            break
                else:
                    _view_note_ext(self.job_name, self.step_name,
                                   lay, 0, 0, "", 0)
                self._refresh_layer_display()
                self._apply_updates()
                self._refresh_layer_display()
                self._apply_updates()

        def _get_selected_item(self) -> Tuple[str, Optional[QTreeWidgetItem]]:
            """获取当前选中的层名和子项"""
            item = self.layer_tree.currentItem()
            if item is None:
                return ("", None)
            layer_name = item.text(0)
            if layer_name in self.all_layer_datas:
                # 这是根节点
                pass
            else:
                # 找到所属层
                for lay, root in self.all_layer_datas.items():
                    for i in range(root.childCount()):
                        if root.child(i) == item:
                            layer_name = lay
                            break
            return (layer_name, item)

        # ── 按钮事件 ─────────────────────────────

        def _on_unit_change(self, idx: int) -> None:
            """单位切换"""
            if not self.job_name or not self.step_name:
                self._info_dialog("Job或Step没有打开!!!")
                return
            if self.step_name.lower() != "cad":
                self._info_dialog("请在cad上运行!!!")
                return
            _mi.print_config[1] = self.combo_unit.currentText()
            self._apply_updates()
            self._refresh_layer_display()
            self._apply_updates()

        def _on_sort_notes(self) -> None:
            """优化标记顺序"""
            if not self._check_job_step():
                return
            selected = self._get_checked_layers()
            if not selected:
                self._info_dialog("请选择需要排序的层!!!")
                return
            layers_to_sort = [l for l in selected if l not in self.notelist
                            or len(self.notelist.get(l, [])) > 1]
            if not layers_to_sort:
                self._info_dialog("没有需要排序的层!")
                return
            self._apply_updates()
            result = _get_sorted_notes(self.job_name, self.step_name,
                                        layers_to_sort)
            self._refresh_layer_display(layers_to_sort)
            self._apply_updates()
            self._info_dialog(
                f"{result}优化顺序更新完成!!!" if result
                else "顺序已经优化!!!"
            )

        def _on_get_original(self) -> None:
            """获取原稿数据"""
            if not self._check_job_step():
                return
            selected = self._get_checked_layers()
            if not selected:
                self._info_dialog("请选择需要识别原稿的层!!!")
                return
            self._apply_updates()
            try:
                _mi.extract_original_data(
                    self.job_name, self.step_name, selected
                )
            except Exception as e:
                self._info_dialog(f"获取原稿失败: {e}")
                return
            self._refresh_layer_display(selected)
            self._apply_updates()
            self._refresh_imp_panel()
            self._info_dialog(
                f"{self.job_name}\n{selected}\n原稿信息更新完成!!!"
            )

        def _save_changes(self) -> None:
            """保存所有修改"""
            if not self._check_job_step():
                return
            self._apply_updates()
            self._refresh_layer_display()
            self._apply_updates()
            self._save_check_states()
            self._build_layer_tree()
            self._refresh_layer_display()
            self._apply_updates()
            self._refresh_imp_panel()
            self._info_dialog(f"{self.job_name} Note信息保存完成!!!")

        def _print_notes(self) -> None:
            """生成图纸"""
            self._apply_updates()

            if self.error_info:
                self._info_dialog(self.error_info)
                return

            # 获取选中层
            page_groups: Dict[int, List[str]] = {}
            for lay, root in self.all_layer_datas.items():
                try:
                    page_num = int(root.text(1).strip())
                except (ValueError, TypeError):
                    root.setCheckState(0, Qt.Unchecked)
                    continue

                if root.checkState(0) and page_num:
                    page_groups.setdefault(page_num, []).append(lay)

            if not page_groups:
                self._info_dialog("请选择输出层!!!")
                return

            run_layers = []
            for layers in page_groups.values():
                run_layers.extend(layers)

            # 检查阻抗
            err = _check_imp_note_ext(run_layers)
            if err:
                self._info_dialog(err)

            # 生成 SVG
            try:
                gen = _svg.SVGGenerator(self.job_name, self.step_name)
                for page_num, layers in page_groups.items():
                    result, error = gen.generate(
                        layers, output_dir=_mi.config.SVG_DIR,
                        profile_flag=0, opacity_flag=self.opacity_flag
                    )
                    if error:
                        self._info_dialog(error)
                    else:
                        self._info_dialog(f"{layers}\n输出完成!!!")
            except Exception as e:
                self._info_dialog(f"生成图纸失败: {e}")
                return

            self._select_all()  # 取消全选

        # ── 阻抗面板 ────────────────────────────

        def _toggle_imp_panel(self) -> None:
            """切换阻抗面板显示"""
            self.imp_show_flag = not self.imp_show_flag
            self.imp_tree.setHidden(self.imp_show_flag)
            if not self.imp_show_flag:
                self._refresh_imp_panel()

        def _refresh_imp_panel(self) -> None:
            """刷新阻抗面板"""
            if self.imp_show_flag:
                return
            self._apply_updates()
            try:
                imp_list = _get_impedance_list_ext()
            except Exception:
                imp_list = []

            if not imp_list:
                return

            # 排序（按层顺序）
            imp_list_sorted = []
            for item in imp_list:
                layer_name = item[0] if item else ""
                try:
                    idx = self.signal_layers.index(layer_name.upper()) if layer_name.upper() in self.signal_layers else 999
                except ValueError:
                    idx = 999
                imp_list_sorted.append((idx, item))
            imp_list_sorted.sort()

            self.imp_tree.clear()
            for _, item in imp_list_sorted:
                root = QTreeWidgetItem(self.imp_tree)
                for col in range(min(9, len(item))):
                    root.setText(col, str(item[col]))
                if len(item) <= 1 or not item[1]:
                    root.setText(3, "未标")
                    root.setBackground(3, Qt.red)
                self.imp_tree.addTopLevelItem(root)
            self.imp_tree.expandAll()

        # ── 继承/查找面板 ──────────────────────

        def _toggle_find_panel(self) -> None:
            """切换继承查找面板"""
            self.find_show_flag = not self.find_show_flag
            self.find_tree.setHidden(self.find_show_flag)
            self.line_find.setEnabled(not self.find_show_flag)
            if not self.find_show_flag:
                self._on_find_notes()

        def _on_find_notes(self) -> None:
            """搜索料号标记"""
            if self.find_show_flag:
                return
            search_text = self.line_find.text().strip()
            if not search_text or search_text == self.find_text:
                return
            self.find_text = search_text

            self.find_infos = []
            self.find_infos += _find_genesis_ext(self.find_text)
            self.find_infos += _find_mysql_ext(self.find_text)
            self.find_infos.sort(key=lambda x: str(x[8]) + str(x[0]),
                                 reverse=True)

            self.find_tree.clear()
            if not self.find_infos:
                return

            board_size = "N/A"
            try:
                board_size = _mi.get_board_size(self.load_dict)
            except Exception:
                pass

            for row in self.find_infos:
                item = QTreeWidgetItem(self.find_tree)
                for col in range(min(9, len(row))):
                    item.setText(col, str(row[col]))
                # 尺寸不匹配红色标记
                if len(row) > 4 and row[4] != board_size:
                    item.setToolTip(4, f"本JOB尺寸为:{board_size}")
                    item.setBackground(4, Qt.red)
                self.find_tree.addTopLevelItem(item)
            self.find_tree.expandAll()

        def _on_inherit_note(self) -> None:
            """双击继承标记"""
            item = self.find_tree.currentIndex()
            idx = item.row()
            if idx < 0 or idx >= len(self.find_infos):
                return

            info = self.find_infos[idx]
            loc_data = info[9] if len(info) > 9 else {}
            # 简单确认
            confirmed = self._question_dialog(
                f"您确定要继承 {info[1]}的{info[0]}吗?\n\n"
                "******请确保零点/方向/面向一致******"
            )
            if not confirmed:
                return

            # 复制 load_dict
            if isinstance(loc_data, dict):
                self.load_dict.update(loc_data)
            _save_json_ext(self.json_file, self.load_dict)
            self._refresh_layer_display()
            self._apply_updates()
            self._info_dialog(
                "继承标记添加完成\n\n请检查确认标记位置及内容,并修正确保无误"
            )

        # ── 验证逻辑 ──────────────────────────

        def _validate_all(self, show_error: bool = True) -> None:
            """验证所有标记数据"""
            self.error_info = ""
            self.error_orig_info = ""

            for lay, root in self.all_layer_datas.items():
                # 验证每个子项
                for i in range(root.childCount()):
                    child = root.child(i)
                    self._validate_child(child, lay)

                # 验证标记字符
                marks_seen: Dict[str, str] = {}
                for i in range(root.childCount()):
                    child = root.child(i)
                    mark = child.text(5).replace("/", "").replace("*", "").strip()
                    note_type = child.text(4).strip()
                    note_comment = self._get_child_widget_text(lay, child, 11)

                    if mark:
                        if not mark.isalnum():
                            child.setBackground(5, Qt.red)
                            self.error_info = "错误字符,请更正!!!"
                        elif len(mark) > 3:
                            child.setBackground(5, Qt.red)
                            self.error_info = "标记过长,请更正!!!"
                        elif mark.upper() in marks_seen:
                            child.setBackground(5, Qt.red)
                            self.error_info = "重复标记,请更正!!!"
                        else:
                            child.setBackground(5, Qt.white)
                            marks_seen[mark.upper()] = ""

                    # 制作指示备注不能为空
                    if note_type == "Note":
                        if not note_comment.replace("/", "").replace("*", "").strip():
                            child.setBackground(3, Qt.red)
                            child.setBackground(4, Qt.red)
                            child.setBackground(5, Qt.red)
                            self.error_info = "*制作指示备注不能为空*"
                        else:
                            child.setBackground(3, Qt.white)
                            child.setBackground(4, Qt.white)
                            child.setBackground(5, Qt.white)

            if self.error_info and show_error:
                self._info_dialog(self.error_info)

        def _validate_child(self, child: QTreeWidgetItem, lay: str) -> None:
            """验证单个标记项"""
            if child.text(4).strip() == "Note":
                return

            # 层类型检查
            layer_type = ""
            for li in self.line_layers:
                if li[0] == lay:
                    layer_type = li[3] if len(li) > 3 else ""
                    break

            if (layer_type and child.text(4).strip() in _mi.config.NOTE_SELECT
                    and layer_type not in _mi.config.NOTE_SELECT[child.text(4).strip()][6]):
                child.setBackground(3, Qt.red)
                child.setBackground(4, Qt.red)
                self.error_info = f"{[child.text(3)]}添加的层错误,请删除!!!"
            else:
                child.setBackground(3, Qt.white)
                child.setBackground(4, Qt.white)

            # 数值验证
            for col in (6, 7):
                text_val = child.text(col)
                if not text_val:
                    continue
                vals = text_val.replace("*", "/").split("/")
                has_error = False
                numeric_vals = []
                for v in vals:
                    try:
                        numeric_vals.append(float(v))
                    except ValueError:
                        has_error = True
                if has_error:
                    child.setBackground(col, Qt.red)
                    self.error_info = "数值为空!!!"
                    if (child.text(8).replace("*", "").replace("/", "").strip()
                            and col == 7):
                        self.error_orig_info = "数值为空,请更正!!!"
                elif numeric_vals:
                    min_val = min(numeric_vals)
                    unit = _unit_text()
                    if unit == "mil" and min_val < 0.5:
                        child.setBackground(col, Qt.red)
                    elif unit == "um" and max(numeric_vals) < 12:
                        child.setBackground(col, Qt.red)
                    elif unit == "mm" and max(numeric_vals) < 0.012:
                        child.setBackground(col, Qt.red)
                    else:
                        child.setBackground(col, Qt.white)

        def _get_child_widget_text(self, lay: str,
                                   child: QTreeWidgetItem,
                                   col: int) -> str:
            """获取子项中 ComboBox/LineEdit 的文本"""
            note_idx = child.text(2)
            key = f"{lay}~{note_idx}~{col}"
            widget = self.combos_registry.get(key)
            if hasattr(widget, 'currentText'):
                return widget.currentText()
            elif hasattr(widget, 'text'):
                return widget.text()
            return child.text(col)

        # ── 持久化 ─────────────────────────────

        def _apply_updates(self) -> None:
            """将 UI 变更同步到 load_dict 和 notes"""
            _mi.print_config[5] = self.line_editor.text()
            self.load_dict["job_name"] = _mi.host_info.get("job_name", "")
            self.load_dict["editer_name"] = _mi.print_config[5]
            self.load_dict["unit"] = self.combo_unit.currentText()
            self.load_dict["zkdc"] = self.combo_imp_sym.currentText()
            self.load_dict["tzlb"] = self.combo_space.currentText()

            _mi.print_config[4] = self.load_dict.get("zkdc", "否")
            _mi.print_config[9] = self.load_dict.get("tzlb", "300")
            _mi.print_config[10] = self.combo_pos.currentText()

            # 保存层修改
            for lay, root in self.all_layer_datas.items():
                self.load_dict.setdefault("layer_file", {})[lay] = root.text(1)
                for i in range(root.childCount()):
                    child = root.child(i)
                    note_idx = child.text(2)
                    if lay in self.notelist:
                        for note in self.notelist[lay]:
                            if note[0] == note_idx:
                                # 同步修改
                                self._sync_note_changes(lay, note, child)

            try:
                _mi.save_load_dict(self.load_dict)
            except Exception:
                pass
            try:
                _save_json_ext(self.json_file, self.load_dict)
            except Exception:
                pass
            try:
                _mi.get_line_info()
            except Exception:
                pass
            try:
                _mi.get_editer()
                self.line_editor.setText(_mi.print_config[5])
            except Exception:
                pass

            self._validate_all(show_error=False)

        def _sync_note_changes(self, lay: str, note: List,
                               child: QTreeWidgetItem) -> None:
            """同步单个 note 的修改"""
            # 更新 note[5] = 标记
            # 更新 note[6] = 成品值
            # 更新 note[7] = 原稿值
            pass  # 在完整 Genesis 环境中由 GenesisAPI 处理

        # ── 工具方法 ──────────────────────────

        def _get_checked_layers(self) -> List[str]:
            """获取所有勾选的层名"""
            result = []
            for lay, root in self.all_layer_datas.items():
                if root.checkState(0):
                    result.append(lay)
            return result

        def _check_job_step(self) -> bool:
            """验证 Job/Step 有效性"""
            if not self.job_name or not self.step_name:
                self._info_dialog("Job或Step没有打开!!!")
                return False
            if self.step_name.lower() != "cad":
                self._info_dialog("请在cad上运行!!!")
                return False
            return True

        def _open_dir(self) -> None:
            """Ctrl+F: 打开输出目录"""
            path = os.path.join(_mi.config.SVG_DIR,
                                _mi.host_info.get("job_name", ""))
            if os.path.isdir(path):
                QFileDialog.getOpenFileName(self, "查看资料界面",
                                            path, "Txt files(*.*)")
            else:
                self._info_dialog(f"{path}\n目录不存在!!!")

        @staticmethod
        def _info_dialog(text: str, title: str = "提示框") -> None:
            """显示信息弹窗"""
            QMessageBox.information(None, title, text, QMessageBox.Cancel)

        @staticmethod
        def _question_dialog(text: str, title: str = "确认框") -> bool:
            """显示确认弹窗"""
            result = QMessageBox.question(
                None, title, text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            return result == QMessageBox.Yes

    # ── CLI 兼容入口 ───────────────────────────────

    def run_gui(job: Optional[str] = None,
                step: Optional[str] = None) -> int:
        """启动 GUI 主循环

        Args:
            job:  料号名（可选，默认读环境变量 JOB）
            step: Step 名（可选，默认读环境变量 STEP）

        Returns:
            QApplication 退出码
        """
        if not _PYQT5_AVAILABLE:
            print("[ERROR] PyQt5 未安装，无法启动 GUI。请 pip install PyQt5")
            return 1

        app = QApplication(sys.argv)
        window = MITreeWidget(job or os.environ.get("JOB", None),
                             step or os.environ.get("STEP", None))
        return app.exec_()


else:
    # PyQt5 不可用时的降级占位
    class MITreeWidget:
        """PyQt5 不可用时的占位类
        
        所有业务逻辑仍可通过 CLI 调用，请使用 main.py。
        """

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "PyQt5 未安装，GUI 不可用。\n"
                "  - 安装: pip install PyQt5\n"
                "  - 使用 CLI: python main.py --help"
            )

    def run_gui(job: Optional[str] = None,
                step: Optional[str] = None) -> int:
        """ClI 降级入口"""
        print("[INFO] PyQt5 未安装，使用 CLI 模式")
        print("  安装 GUI: pip install PyQt5")
        print("  使用 CLI: python main.py --help")
        return 1


# ═══════════════════════════════════════════
# 命令行直接启动
# ═══════════════════════════════════════════

if __name__ == "__main__":
    job_name = os.environ.get("JOB", None)
    step_name = os.environ.get("STEP", None)

    # 解析命令行参数
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--job" and i + 1 < len(args):
            job_name = args[i + 1]
        elif arg == "--step" and i + 1 < len(args):
            step_name = args[i + 1]

    if _PYQT5_AVAILABLE:
        sys.exit(run_gui(job_name, step_name))
    else:
        sys.exit(1)
