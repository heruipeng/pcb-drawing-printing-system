#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - PyQt5 GUI
=======================
从 print_notes.py 重构而来。

主要功能:
  - 层选择树（含标记子项）
  - 标记验证（类型、数值、阻抗匹配）
  - 优化顺序 / 获得原稿 / 保存数据 / 生成图纸
  - 历史数据继承
  - 阻抗信息展示

原始作者: Gf.zhang (print_notes.py v1.0, 2021-11-19)
"""

import os
import sys
from typing import Dict, List, Optional, Any

# ═══════════════════════════════════════════
# PyQt5 可选依赖
# ═══════════════════════════════════════════

_PYQT5_AVAILABLE = False
try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTreeWidget, QPushButton, QTreeWidgetItem,
        QMessageBox, QFileDialog, QShortcut,
        QComboBox, QLabel, QLineEdit, QMenu, QAction,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QColor, QKeySequence, QCursor
    _PYQT5_AVAILABLE = True
except ImportError:
    # 创建占位类使语法检查通过
    QApplication = QWidget = QVBoxLayout = QHBoxLayout = None
    QTreeWidget = QPushButton = QTreeWidgetItem = None
    QMessageBox = QFileDialog = QShortcut = None
    QComboBox = QLabel = QLineEdit = QMenu = QAction = None
    Qt = QFont = QColor = QKeySequence = QCursor = None

    print("[WARN] PyQt5 未安装，GUI 模式不可用。pip install PyQt5")


# 引用内部模块
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_SCRIPT_DIR)
_CAM_PATH = os.path.join(_PARENT_DIR, "gerber-tool")
if os.path.isdir(_CAM_PATH) and _CAM_PATH not in sys.path:
    sys.path.insert(0, _CAM_PATH)

from . import config
from . import geometry as _geom
from . import mi_extractor as _mi
from . import svg_renderer as _svg


# ═══════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════

class MIWindow(QWidget):
    """MI 图纸标注主窗口

    Args:
        job_name:  料号名
        step_name: Step 名（默认 "cad"）
    """

    def __init__(self, job_name: str = "",
                 step_name: str = "cad"):
        if not _PYQT5_AVAILABLE:
            raise ImportError("PyQt5 未安装")

        super().__init__()

        # 基本状态
        self.job_name = job_name
        self.step_name = step_name
        _mi.print_config[6] = self.step_name

        # 数据
        self.note_list: Dict[str, List] = {}
        self.all_datas: Dict[str, QTreeWidgetItem] = {}
        self.layer_check_state: Dict[str, Any] = {}
        self.load_dict: Dict = {}
        self.err_info: str = ""
        self.err_orig_info: str = ""
        self.opacity_v: int = 0
        self.combos: Dict[str, Any] = {}
        self.imp_info: List = []
        self.imp_info_run: int = 0
        self.zk_list: List = []
        self.show_change_info: List = []
        self.inplan_conn = None

        # JSON 文件
        self.json_file = _mi.get_json_name(self.job_name)
        self._read_json()

        # UI
        self.resize(1390, 860)
        _mi.get_host(self.job_name)
        self.setWindowTitle(
            f"测量及指示图纸标注({config.SVG_REVISION})"
            f"({self.job_name}~{self.step_name})"
        )

        # 快捷键
        self.check_state = 0
        self.check_state_new = 0
        self._setup_shortcuts()

        # 阻抗
        self.imp_count = 0
        self.imp_show_flag = True

        # 构建 UI
        self._setup_ui()

        # 加载数据
        self.show_info()

    # ═══════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════

    def _setup_shortcuts(self) -> None:
        """设置快捷键"""
        QShortcut(QKeySequence("Ctrl+A"), self, self.select_all)
        QShortcut(QKeySequence("Ctrl+F"), self, self.open_dir)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_changes)
        QShortcut(QKeySequence("Ctrl+P"), self, self.print_notes)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+C"), self, self._export_impedance)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._select_next)
        QShortcut(QKeySequence("Ctrl+X"), self, self.get_original)

    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        vbox = QVBoxLayout()
        self.setLayout(vbox)

        # 顶部工具栏
        cbox = QHBoxLayout()
        self._build_toolbar(cbox)
        vbox.addLayout(cbox, 0)

        # 主内容区
        hbox = QHBoxLayout()
        lay_box = QVBoxLayout()

        self.layer_tree = QTreeWidget()
        self.imp_tree = QTreeWidget()
        lay_box.addWidget(self.layer_tree, 2)
        lay_box.addWidget(self.imp_tree, 1)
        hbox.addLayout(lay_box, 3)

        vbox.addLayout(hbox, 1)
        self.imp_tree.setHidden(True)

        # 底部按钮
        btn_box = QHBoxLayout()
        self._build_buttons(btn_box)
        vbox.addLayout(btn_box, 0)

        # 初始化列
        self._set_layer_columns()
        self._set_imp_columns()
        self._setup_find_widget(vbox)

    def _build_toolbar(self, cbox: QHBoxLayout) -> None:
        """构建顶部工具栏"""
        bold_font = QFont("Roman times", 16, QFont.Bold)

        # 单位选择
        self.combo_unit_label = QLabel("单位:")
        self.combo_unit_label.setFont(bold_font)
        cbox.addWidget(QLabel("测量及指示图纸标注"), 2)

        self.btn_sort = QPushButton("优化顺序")
        self.btn_sort.setFont(bold_font)
        self.btn_imp = QPushButton("阻抗信息")
        self.btn_imp.setFont(bold_font)
        self.btn_imp.setToolTip("单击:展开和收回InPlan阻抗信息界面")

        cbox.addWidget(self.btn_sort, 0)
        cbox.addWidget(self.btn_imp, 0)

        self.combo_unit_label = QLabel("单位:")
        self.combo_unit_label.setFont(bold_font)
        self.combo_unit = QComboBox()
        self.combo_unit.setFont(bold_font)
        for item in ("mil", "um", "mm"):
            self.combo_unit.addItem(item)
        self.combo_unit.setCurrentText(_mi.print_config[1])

        self.combo_margin_label = QLabel("留白:")
        self.combo_margin_label.setFont(bold_font)
        self.combo_margin = QComboBox()
        self.combo_margin.setFont(bold_font)
        for item in ("0", "100", "200", "300", "500", "600", "800"):
            self.combo_margin.addItem(item)
        self.combo_margin.setCurrentText(_mi.print_config[9])

        # 继承
        self.btn_inherit = QPushButton("继承:")
        self.btn_inherit.setFont(bold_font)
        self.edit_search = QLineEdit(_mi.host_info.get("find_job", ""))
        self.edit_search.setFont(bold_font)

        cbox.addWidget(self.combo_unit_label, 0)
        cbox.addWidget(self.combo_unit, 0)
        cbox.addWidget(self.combo_margin_label, 0)
        cbox.addWidget(self.combo_margin, 0)
        cbox.addWidget(self.btn_inherit, 0)
        cbox.addWidget(self.edit_search, 0)

        mi_label = QLabel("MI制作:")
        mi_label.setFont(bold_font)
        self.edit_mi_maker = QLineEdit("")
        self.edit_mi_maker.setFont(bold_font)
        cbox.addWidget(mi_label, 0)
        cbox.addWidget(self.edit_mi_maker, 0)

        # 事件绑定
        self.combo_unit.currentIndexChanged.connect(self._on_unit_change)
        self.btn_sort.clicked.connect(self._sort_notes)
        self.btn_imp.clicked.connect(self._toggle_imp)
        self.btn_inherit.clicked.connect(self._toggle_find)

    def _build_buttons(self, btn_box: QHBoxLayout) -> None:
        """构建底部按钮"""
        bold_font = QFont("Roman times", 16, QFont.Bold)

        buttons = [
            ("生成图纸(Ctrl+P)", self.print_notes),
            ("导出阻抗(Ctrl+C)", self._export_impedance),
            ("获得原稿(Ctrl+X)", self.get_original),
            ("保存数据(Ctrl+S)", self.save_changes),
        ]

        self.button_run = None
        self.button_save = None

        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setFont(bold_font)
            btn.clicked.connect(handler)
            btn_box.addWidget(btn, 1)
            if "生成图纸" in text:
                self.button_run = btn
            if "保存数据" in text:
                self.button_save = btn

    def _set_layer_columns(self) -> None:
        """设置层树列"""
        l_list = ["层名", "页码"] + config.HO_TYPES[:]
        l_list.insert(4, "类型代码")
        l_list.insert(-1, "上参考层")
        l_list.insert(-1, "下参考层")
        self.layer_tree.setColumnCount(len(l_list))
        self.layer_tree.setHeaderLabels(l_list)
        self.layer_tree.header().setStyleSheet(
            "QHeaderView::section{background-color:skyblue;color:black;"
            "height:25px;padding-left:2px;border:1px solid #6c6c6c;font:15px}"
        )
        widths = [120, 50, 50, 120, 120, 60, 130, 130, 80, 80, 80, 900]
        for i, w in enumerate(widths):
            self.layer_tree.setColumnWidth(i, w)

        self.layer_tree.setContextMenuPolicy(3)
        self.layer_tree.customContextMenuRequested.connect(self._context_menu)

    def _set_imp_columns(self) -> None:
        """设置阻抗信息列"""
        labels = ["层名", "序号", "阻抗类型", "标记",
                  "成品值", "原稿值", "阻抗值", "参考层", "~"]
        self.imp_tree.setColumnCount(len(labels))
        self.imp_tree.setHeaderLabels(labels)
        self.imp_tree.header().setStyleSheet(
            "QHeaderView::section{background-color:skyblue;color:black;"
            "height:25px;padding-left:2px;border:1px solid #6c6c6c;font:15px}"
        )
        widths = [170, 50, 240, 60, 130, 130, 80, 160, 120]
        for i, w in enumerate(widths):
            self.imp_tree.setColumnWidth(i, w)

    def _setup_find_widget(self, vbox: QVBoxLayout) -> None:
        """设置查找/继承控件"""
        self.find_tree = QTreeWidget()
        self.find_tree.setToolTip("确认标记信息,双击所选的行继承")
        self._set_find_columns()
        self.find_visible = True
        self.find_text = ""
        self.find_results: List = []
        self.find_tree.setHidden(self.find_visible)
        self.edit_search.setToolTip("输入关键字,回车搜索结果")
        self.edit_search.returnPressed.connect(self._show_find_results)
        self.find_tree.itemDoubleClicked.connect(self._inherit_notes)

    def _set_find_columns(self) -> None:
        """设置查找树列"""
        labels = ["来源", "料号名", "版本", "个数", "尺寸(mm)",
                  "MI制作", "创建时间", "制作修改", "修改时间"]
        self.find_tree.setColumnCount(len(labels))
        self.find_tree.setHeaderLabels(labels)
        self.find_tree.header().setStyleSheet(
            "QHeaderView::section{background-color:skyblue;color:black;"
            "height:25px;padding-left:2px;border:1px solid #6c6c6c;font:15px}"
        )

    # ═══════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════

    def _read_json(self) -> None:
        """读取 JSON 配置"""
        self.load_dict = _mi.read_json(self.json_file)
        if "unit" in self.load_dict:
            _mi.print_config[1] = self.load_dict["unit"]
        else:
            self.load_dict["unit"] = _mi.print_config[1]

    def save_json(self) -> None:
        """保存 JSON 配置"""
        _mi.save_json(self.json_file, self.load_dict)

    def show_info(self) -> None:
        """初始化加载数据"""
        if not self.job_name or not self.step_name:
            self._info("Job或Step没有打开!!!")
            return

        # 添加已有 note
        _add_json_notes(self.load_dict, self.job_name, self.step_name)

        if self.step_name != "cad":
            self._info("请在cad上运行!!!")
            return

        self._show_layers()
        self._refresh_display()
        self._check_all(infomark=0)

        self.combo_unit.setCurrentText(_mi.print_config[1])
        _mi.GenesisAPI.get_user_name()
        self.combo_unit.currentIndexChanged.connect(self._on_unit_change)

    def _show_layers(self) -> None:
        """显示层列表"""
        self._save_check_state()
        self._populate_layers()
        self._init_layer_data()
        self._build_layer_tree()

        if self.layer_check_state:
            for lay in self.all_datas:
                root = self.all_datas[lay]
                if lay in self.layer_check_state:
                    root.setCheckState(0, self.layer_check_state[lay])

    def _save_check_state(self) -> None:
        """保存勾选状态"""
        self.layer_check_state = {}
        for lay in self.all_datas:
            root = self.all_datas[lay]
            if root.checkState(0):
                self.layer_check_state[lay] = Qt.Checked
            else:
                self.layer_check_state[lay] = Qt.Unchecked

    def _populate_layers(self) -> None:
        """获取层数据"""
        line_layers = _mi.get_layers(self.job_name)
        _mi.init_layers(self.load_dict, line_layers)

    def _init_layer_data(self) -> None:
        """初始化层文件映射"""
        for lay in self.load_dict.get("layer_file", {}):
            if lay not in self.load_dict.get("layer_dist", {}):
                continue
            dist = self.load_dict["layer_dist"][lay]
            if len(dist) > 1:
                dist[1] = self.load_dict["layer_file"][lay]

    def _build_layer_tree(self) -> None:
        """构建层树"""
        self.layer_tree.clear()
        self.all_datas = {}

        for lay, props in sorted(
            self.load_dict.get("layer_dist", {}).items(),
            key=lambda x: (config.LAYER_SORT_KEY.get(x[1][3], 100),
                           int(x[1][1]) if x[1][1].isdigit() else 100)
        ):
            root = QTreeWidgetItem(self.layer_tree)
            root.setText(0, lay)                # 层名
            root.setText(1, props[1])           # 页码
            root.setCheckState(0, Qt.Checked)
            self.layer_tree.addTopLevelItem(root)
            self.all_datas[lay] = root

    # ═══════════════════════════════════════
    # 标记刷新
    # ═══════════════════════════════════════

    def _refresh_display(self, layers: List[str] = None,
                         run_all: int = 1) -> None:
        """刷新标记显示"""
        if layers is None:
            layers = list(self.all_datas.keys())

        _mi.print_config[12] = ""
        run_layers = list(self.all_datas.keys()) if run_all else layers

        for lay in run_layers:
            self._show_layer_notes(self.all_datas[lay])

        if _mi.print_config[12]:
            self._disable_all_controls()

    def _show_layer_notes(self, root: QTreeWidgetItem) -> None:
        """显示单层的标记"""
        lay = root.text(0)
        # 清除旧子项
        while root.childCount() > 0:
            root.removeChild(root.child(0))

        self.note_list.setdefault(lay, [])

        # 从 Genesis 获取标记
        notelist = _mi.get_notes_new(self.job_name, self.step_name, lay)
        self.note_list[lay] = notelist

        # 同步到 load_dict
        _sync_notes_to_dict(notelist, lay, self.load_dict)

        # 添加子项
        for note in notelist:
            child = QTreeWidgetItem(root)
            for col_idx in range(12):
                val = ""
                if col_idx == 0:
                    val = str(root.text(1) or "")
                elif col_idx == 1:
                    val = str(note[0]) if len(note) > 0 else ""
                elif col_idx == 2:
                    val = str(note[1]) if len(note) > 1 else ""
                elif col_idx == 3:
                    val = str(note[3]) if len(note) > 3 else ""
                elif col_idx == 4:
                    val = str(note[2]) if len(note) > 2 else ""
                elif col_idx == 5:
                    val = str(note[4]) if len(note) > 4 else ""
                elif col_idx == 6:
                    val = str(note[5]) if len(note) > 5 else ""
                elif col_idx == 7:
                    val = str(note[6]) if len(note) > 6 else ""
                elif col_idx == 8:
                    val = str(note[7]) if len(note) > 7 else ""
                elif col_idx == 9:
                    val = str(note[8]) if len(note) > 8 else ""
                elif col_idx == 10:
                    val = str(note[9]) if len(note) > 9 else ""
                elif col_idx == 11:
                    val = str(note[9]) if len(note) > 9 else ""
                child.setText(col_idx, val)

            root.addChild(child)

    def _disable_all_controls(self) -> None:
        """禁用所有控件"""
        controls = [self.button_run, self.button_save,
                    self.btn_sort, self.btn_imp,
                    self.combo_unit]
        for c in controls:
            if c:
                c.setEnabled(False)

    # ═══════════════════════════════════════
    # 事件处理
    # ═══════════════════════════════════════

    def _on_unit_change(self) -> None:
        """单位切换"""
        if not self.job_name or not self.step_name:
            return
        self._apply_changes(infomark=0)
        _mi.print_config[1] = self.combo_unit.currentText()
        self._refresh_display()
        self._apply_changes(infomark=0)

    def select_all(self) -> None:
        """全选/取消全选 (Ctrl+A)"""
        if self.check_state:
            ch = Qt.Checked
            self.check_state = 0
        else:
            ch = Qt.Unchecked
            self.check_state = 1
        for lay in self.all_datas:
            self.all_datas[lay].setCheckState(0, ch)

    def _select_next(self) -> None:
        """选择下一页 (Ctrl+Z)"""
        pages = set()
        for lay in self.all_datas:
            pages.add(self.all_datas[lay].text(1))
        if str(self.check_state_new + 1) in pages:
            self.check_state_new += 1
        else:
            self.check_state_new = 1
        for lay in self.all_datas:
            root = self.all_datas[lay]
            if root.text(1) == str(self.check_state_new):
                root.setCheckState(0, Qt.Checked)
            else:
                root.setCheckState(0, Qt.Unchecked)

    def open_dir(self) -> None:
        """打开目录 (Ctrl+F)"""
        paths = os.path.join(
            config.SVG_DIR,
            _mi.host_info.get("job_name", "")
        )
        if os.path.isdir(paths):
            QFileDialog.getOpenFileName(self, "查看资料界面",
                                        paths, "Txt files(*.*)")

    def _toggle_imp(self) -> None:
        """切换阻抗面板"""
        self.imp_show_flag = not self.imp_show_flag
        self.imp_tree.setHidden(self.imp_show_flag)
        self._show_imp_info()

    def _toggle_find(self) -> None:
        """切换继承面板"""
        self.find_visible = not self.find_visible
        self.edit_search.setEnabled(not self.find_visible)
        self.find_tree.setHidden(self.find_visible)
        self._show_find_results()

    def _show_find_results(self) -> None:
        """显示查找结果"""
        if self.find_visible:
            return

        txt = self.edit_search.text()
        if self.find_text == txt:
            return
        self.find_text = txt

        self.find_results = []
        self.find_results += _mi.find_genesis_data(self.find_text)
        self.find_results += _mi.find_mysql_data(self.find_text)
        self.find_results.sort(
            key=lambda x: x[8] + x[0] if len(x) > 8 else "",
            reverse=True
        )

        self.find_tree.clear()
        if not self.find_results:
            return

        pro_size = _mi.get_board_size(self.load_dict)
        for row in self.find_results:
            item = QTreeWidgetItem(self.find_tree)
            for col in range(min(9, len(row))):
                item.setText(col, str(row[col]))
            if (len(row) > 4 and
                    str(row[4]) != pro_size):
                item.setToolTip(4, f"本JOB尺寸为:{pro_size}")
                item.setBackground(4, Qt.red)
            self.find_tree.addTopLevelItem(item)
        self.find_tree.expandAll()

    def _inherit_notes(self) -> None:
        """双击继承标记"""
        item = self.find_tree.currentIndex()
        if not item.isValid():
            return
        idx = item.row()
        if idx >= len(self.find_results):
            return

        loc_dist = self.find_results[idx][9]
        job_from = self.find_results[idx][1]
        job_src = self.find_results[idx][0]

        try:
            count = int(self.find_results[idx][3])
        except (ValueError, IndexError, KeyError):
            try:
                count = len(_mi._get_note_count(loc_dist))
            except Exception:
                count = 0

        if count < 1:
            self._info(f"\n{job_from}标记个数为 0 !!!")
            return

        if not self._question(
            f"\n您确定要继承 {job_src}的{job_from}吗?\n\n"
            "******请确保零点/方向/面向一致******"
        ):
            return

        self.load_dict = loc_dist.copy()
        self.save_json()
        _mi.get_move_offset(self.load_dict)
        _add_json_notes(self.load_dict, self.job_name, self.step_name, kkk=0)
        _mi.get_move_offset({})
        self._show_layers()
        self._refresh_display()
        self._apply_changes(infomark=0)
        self._info("\n继承标记添加完成\n\n请检查确认标记位置及内容,并修正确保无误")

    # ═══════════════════════════════════════
    # 操作
    # ═══════════════════════════════════════

    def _sort_notes(self) -> None:
        """优化顺序"""
        if not self._check_ready():
            return

        layers = self._get_checked_layers()
        if not layers:
            self._info("\n请选择需要排序的层!!!\n")
            return

        sortable = [l for l in layers
                    if l not in self.note_list or
                    len(self.note_list.get(l, [])) > 1]

        self._apply_changes(infomark=0)
        sorted_layers = _mi.sort_notes(
            self.job_name, self.step_name, sortable
        )
        self._refresh_display(sortable, run_all=0)
        self._apply_changes(infomark=0)

        if sorted_layers:
            self._info(f"\n{sorted_layers}优化顺序更新完成!!!\n")
        else:
            self._info("\n顺序已经优化!!!\n")

    def get_original(self) -> None:
        """获得原稿值 (Ctrl+X)"""
        if not self._check_ready():
            return

        layers = self._get_checked_layers()
        if not layers:
            self._info("\n请选择需要识别原稿的层!!!\n")
            return

        self._apply_changes(infomark=0)
        _mi.extract_original_data(
            self.job_name, self.step_name, layers
        )
        self._refresh_display(layers, run_all=0)
        self._apply_changes(infomark=0)
        self._show_imp_info()

        if layers:
            self._info(
                f"\n{self.job_name}\n{layers}原稿信息更新完成!!!"
            )

    def save_changes(self) -> None:
        """保存数据 (Ctrl+S)"""
        if not self._check_ready():
            return

        self._load_impedance()
        self._apply_changes(infomark=0)
        self._refresh_display()
        self._apply_changes(infomark=0)
        self._show_layers()
        self._refresh_display()
        self._apply_changes()
        self._show_imp_info()
        self._info(f"\n{self.job_name} Note信息保存完成!!!")

    def print_notes(self) -> None:
        """生成图纸 (Ctrl+P)"""
        self._load_impedance(force=True)
        self._apply_changes(infomark=0)
        self._refresh_display()
        self._apply_changes()

        if self.err_info:
            return

        self._show_imp_info()

        # 收集需要打印的层
        print_layers = {}
        for lay in self.all_datas:
            root = self.all_datas[lay]
            try:
                page = int(root.text(1).strip())
            except ValueError:
                root.setCheckState(0, Qt.Unchecked)
                continue

            if root.checkState(0) and page:
                print_layers.setdefault(page, []).append(lay)

        if not print_layers:
            self._info("\n请选择输出层!!!")
            return

        # 检查阻抗
        run_layers = []
        for page_layers in print_layers.values():
            run_layers += page_layers
        err = _mi.check_imp_note(run_layers)
        if err:
            self._info(err)

        # 保存 MI 信息
        _mi.save_load_dict(self.load_dict)

        # 计算 LIMITS
        _svg.calculate_limits(
            self.job_name, self.step_name, run_layers
        )

        # 生成 SVG
        gen = _svg.SVGGenerator(self.job_name, self.step_name)
        out_layers = [[], "", []]
        for page_num in sorted(print_layers.keys()):
            msg, err_msg = gen.generate(
                print_layers[page_num],
                output_dir=config.SVG_DIR,
                opacity_flag=self.opacity_v,
            )
            if err_msg:
                out_layers[1] += err_msg
            elif msg and ".svg" in msg:
                out_layers[2] += print_layers[page_num]
            else:
                out_layers[0] += print_layers[page_num]

        # 显示结果
        if out_layers[1]:
            self._info(out_layers[1])
        if out_layers[2]:
            self._info(
                f"\n{out_layers[2]}\n"
                f"Surface空洞转换PDF出现异常,请处理Surface再输出或检查确认!!!"
            )
        if out_layers[0]:
            self._info(f"\n{out_layers[0]}\n输出完成!!!")

        self.check_state = 0
        self.select_all()

    def _export_impedance(self) -> None:
        """导出阻抗 (Ctrl+C)"""
        self._apply_changes(infomark=0)
        self._refresh_display()
        self._apply_changes(infomark=0)
        if self.err_orig_info:
            self._info(self.err_orig_info)

    # ═══════════════════════════════════════
    # 上下文菜单
    # ═══════════════════════════════════════

    def _context_menu(self, pos) -> None:
        """右键菜单"""
        item = self.layer_tree.currentItem()
        item_at = self.layer_tree.itemAt(pos)
        if item is None or item_at is None:
            return

        menu = QMenu()
        menu.addAction(QAction('查看', self))

        if not item.text(2):
            menu.addAction(QAction('删除全部', self))
        else:
            menu.addAction(QAction('删除', self))

        menu.addAction(QAction('增加制作指示', self))
        menu.triggered[QAction].connect(self._handle_menu)
        menu.exec_(QCursor.pos())

    def _handle_menu(self, action: QAction) -> None:
        """右键菜单处理"""
        lay, item = self._get_current_item()
        if not item:
            return

        text = action.text()
        if "删除" in text:
            if not self._question(f"您确定要{text}吗?"):
                return
            idx_list = []
            if item.text(2):
                idx_list.append(item.text(2))
            else:
                for note in self.note_list.get(lay, []):
                    idx_list.append(note[0])

            if idx_list:
                self._apply_changes(infomark=0)
                _mi.GenesisAPI.delete_note(lay, idx_list[::-1])
                self._refresh_display([lay], run_all=0)
                self._apply_changes(infomark=0)
                self._refresh_display([lay], run_all=0)
                self._apply_changes(infomark=0)

        elif text == '增加制作指示':
            self._apply_changes(infomark=0)
            _mi.GenesisAPI.add_note(lay)
            self._refresh_display([lay], run_all=0)
            self._apply_changes(infomark=0)
            self._refresh_display([lay], run_all=0)
            self._apply_changes(infomark=0)

        elif text == '查看':
            if item.text(2):
                for note in self.note_list.get(lay, []):
                    if str(note[0]) == item.text(2):
                        self._apply_changes(infomark=0)
                        _mi.GenesisAPI.view_note(
                            self.job_name, self.step_name, lay,
                            note[10][3] / 25.4,
                            note[10][4] / 25.4,
                            item.text(7), 1,
                        )
                        self._refresh_display()
                        self._apply_changes(infomark=0)
                        self._refresh_display()
                        self._apply_changes(infomark=0)
                        break
            else:
                self._apply_changes(infomark=0)
                _mi.GenesisAPI.view_note(
                    self.job_name, self.step_name, lay
                )
                self._refresh_display()
                self._apply_changes(infomark=0)
                self._refresh_display()
                self._apply_changes(infomark=0)

            _svg._All_LIMITS = {}

    def _get_current_item(self) -> tuple:
        """获取当前选中的 item"""
        try:
            item = self.layer_tree.currentItem()
            lay = item.text(0)
            return (lay, item)
        except Exception:
            return ("", None)

    # ═══════════════════════════════════════
    # 验证
    # ═══════════════════════════════════════

    def _check_all(self, infomark: int = 1) -> None:
        """检查所有标记"""
        self.err_info = ""
        self.err_orig_info = ""

        for lay in self.all_datas:
            root = self.all_datas[lay]
            for i in range(root.childCount())[::-1]:
                child = root.child(i)
                self._check_one(child, lay)

            # 检查重复标记
            marks = {}
            for i in range(root.childCount()):
                child = root.child(i)
                mark = child.text(5)
                if mark.replace("/", "").replace("*", "").strip():
                    if not mark.strip().isalnum():
                        child.setBackground(5, Qt.red)
                        self.err_info = "错误字符,请更正!!!"
                    elif len(mark.strip()) > 3:
                        child.setBackground(5, Qt.red)
                        self.err_info = "标记过长,请更正!!!"
                    elif mark.upper() in marks:
                        if marks[mark.upper()] != _make_mark_key(child):
                            child.setBackground(5, Qt.red)
                            self.err_info = "重复标记,请更正!!!"
                    else:
                        marks[mark.upper()] = _make_mark_key(child)
                        child.setBackground(5, Qt.white)

                # Note 备注不能为空
                if child.text(3) == "制作指示":
                    if not child.text(11).strip("/").strip("*"):
                        for col in (3, 4, 5, 11):
                            child.setBackground(col, Qt.red)
                            child.setToolTip(col, "*制作指示备注不能为空*")
                        self.err_info = "*制作指示备注不能为空*"

        if self.err_info and infomark:
            self._info(self.err_info)

    def _check_one(self, child: QTreeWidgetItem, lay: str) -> None:
        """检查单个标记"""
        type_code = child.text(4).strip()

        # 层类型错误检查
        if type_code in config.NOTE_SELECT:
            layer_type = self.load_dict.get("layer_dist", {}).get(lay, ["", "", "", ""])[3]
            allowed = config.NOTE_SELECT[type_code][6]
            if layer_type not in allowed:
                child.setBackground(3, Qt.red)
                child.setBackground(4, Qt.red)
                self.err_info = f"{[child.text(3)]}添加的层错误,请删除!!!"

        # 数值验证
        for col in (6, 7):
            val = child.text(col).replace("*", "/").split("/")
            bad_count = 0
            nums = []
            for v in val:
                try:
                    nums.append(float(v))
                except ValueError:
                    bad_count += 1

            if bad_count:
                child.setBackground(col, Qt.red)
                self.err_info = "数值为空!!!"
                if (child.text(8).replace("*", "").replace("/", "").strip() and
                        col == 7):
                    self.err_orig_info = "数值为空,请更正!!!"
            elif nums:
                self._validate_value_range(child, col, nums)

        # 阻抗检查
        self._check_impedance(child, lay)

    def _validate_value_range(self, child: QTreeWidgetItem,
                              col: int, nums: List[float]) -> None:
        """验证数值范围"""
        unit = _mi.print_config[1]
        if unit == 'mil' and min(nums) < 0.5:
            child.setBackground(col, Qt.red)
            self.err_info = "数值输入错误,请更正!!!"
            if (child.text(8).replace("*", "").replace("/", "").strip() and
                    col == 7):
                self.err_orig_info = "原稿值输入错误,请更正!!!"
        elif unit == 'um' and max(nums) < 12:
            child.setBackground(col, Qt.red)
            self.err_info = "数值输入错误,请更正!!!"
        elif unit == 'mm' and max(nums) < 0.012:
            child.setBackground(col, Qt.red)
            self.err_info = "数值输入错误,请更正!!!"
        else:
            child.setBackground(col, Qt.white)

    def _check_impedance(self, child: QTreeWidgetItem,
                         lay: str) -> None:
        """校验阻抗信息"""
        imp_str = child.text(8).replace("*", "").replace("/", "").strip()
        if not imp_str:
            return

        if not child.text(7).replace("*", "").replace("/", "").strip():
            self.err_orig_info = "阻抗原稿值为空,请更正!!!"
            return

        info = [
            _mi.get_mm_new(child.text(6)),
            lay,
            _mi.get_mm_new(child.text(7)),
            child.text(8),
            child.text(4),
            child.text(5),
            child.text(2),
        ]

        imp_vals, imp_correct = _mi.check_impedance(
            self.imp_info, self.zk_list, info
        )

        if not self.imp_info or not self.zk_list:
            pass
        elif not imp_vals:
            self.err_info = "InPlan中没有找到对应的阻抗!!!"
            child.setToolTip(6, self.err_info)
            child.setBackground(6, Qt.red)
        elif _mi.get_mm_new(child.text(6)) not in imp_vals:
            if len(imp_vals) > 1:
                if imp_correct:
                    child.setText(6, _mi.get_mm_new(imp_correct, 1))
                    child.setToolTip(6, "自动同步InPlan阻抗成品值")
                    child.setBackground(6, Qt.white)
                else:
                    self.err_info = "参考层不匹配,请修正!!!"
                    child.setBackground(6, Qt.red)
                    child.setBackground(9, Qt.red)
                    child.setBackground(10, Qt.red)
                    child.setToolTip(6, f"InPlan:{imp_vals}")
            else:
                child.setText(6, _mi.get_mm_new(imp_vals[0], 1))
                child.setToolTip(6, "自动同步InPlan阻抗成品值")
                child.setBackground(6, Qt.white)
        elif imp_correct and imp_correct != _mi.get_mm_new(child.text(6)):
            child.setText(6, _mi.get_mm_new(imp_correct, 1))
            child.setToolTip(6, "自动同步InPlan阻抗成品值")
            child.setBackground(6, Qt.white)
        else:
            child.setBackground(6, Qt.white)

        if imp_vals and not imp_correct:
            for col in range(2, 12):
                child.setToolTip(col, "参考层不匹配,请修正!!!")

    def _show_imp_info(self) -> None:
        """显示阻抗信息"""
        self.imp_tree.clear()
        imp_list = _build_imp_display_list()
        if not imp_list:
            return

        for row in imp_list:
            item = QTreeWidgetItem(self.imp_tree)
            for col in range(min(len(row), self.imp_tree.columnCount())):
                item.setText(col, str(row[col]))
            self.imp_tree.addTopLevelItem(item)

    # ═══════════════════════════════════════
    # 保存/同步
    # ═══════════════════════════════════════

    def _apply_changes(self, infomark: int = 1) -> None:
        """应用所有变更到 Genesis 和 load_dict"""
        # 更新配置
        _mi.print_config[5] = self.edit_mi_maker.text()
        self.load_dict["job_name"] = _mi.host_info.get("job_name", "")
        self.load_dict["editer_name"] = _mi.print_config[5]
        self.load_dict["unit"] = self.combo_unit.currentText()
        self.load_dict["zkdc"] = "否"
        self.load_dict["tzlb"] = self.combo_margin.currentText()

        _mi.print_config[4] = self.load_dict["zkdc"]
        _mi.print_config[9] = self.load_dict["tzlb"]

        # 保存
        _mi.save_load_dict(self.load_dict)
        _mi.get_line_info()
        self.zk_list = _mi.get_impedance_list()
        self._check_all(infomark)

        # 同步变更到 Genesis
        self.show_change_info = []
        for lay in self.all_datas:
            root = self.all_datas[lay]
            if lay in self.load_dict.get("layer_file", {}):
                self.load_dict["layer_file"][lay] = root.text(1)

            for i in range(root.childCount()):
                child = root.child(i)
                child_id = child.text(2)

                for note in self.note_list.get(lay, []):
                    if str(note[0]) != child_id:
                        continue

                    # 更新备注
                    remark = child.text(11) if not child.text(11) else "/"
                    if remark.replace("*", "").replace("/", "").strip():
                        old_key = note[11]
                        new_val = remark.strip().replace("\n", "")
                        if old_key in self.load_dict.get("layer_note", {}):
                            if (self.load_dict["layer_note"][old_key] !=
                                    new_val):
                                new_key = _mi.get_code(self.load_dict)
                                self.load_dict["layer_note"][new_key] = new_val
                            remark = new_val
                        else:
                            new_key = _mi.get_code(self.load_dict)
                            self.load_dict["layer_note"][new_key] = new_val

                    # 构建新文本
                    if child.text(8).replace("*", "").replace("/", "").replace(".", "").strip().isdigit():
                        imp_v = child.text(8).replace("*", "").replace("/", "").strip(".").strip()
                        zk_info = f"&{imp_v}"
                    else:
                        zk_info = ""

                    new_text = " ".join([
                        child.text(4),           # 类型
                        child.text(5).upper(),   # 标记
                        _mi.get_mm_new(child.text(6)),  # 成品值
                        _mi.get_mm_new(child.text(7)),  # 原稿值
                        zk_info,
                        remark or "/",
                    ])

                    if note[10][5] != new_text:
                        _mi.GenesisAPI.change_note(
                            lay, int(note[0]), new_text
                        )
                        self.show_change_info.append(lay)

        self.show_change_info = list(set(self.show_change_info))
        if self.show_change_info:
            self._refresh_display(self.show_change_info, run_all=0)

        # 重新保存
        _mi.save_load_dict(self.load_dict)
        self.zk_list = _mi.get_impedance_list()
        self.save_json()
        _mi.get_line_info()
        _mi.get_editer()

    # ═══════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════

    def _check_ready(self) -> bool:
        """检查状态"""
        if not self.job_name or not self.step_name:
            self._info("\nJob或Step没有打开!!!")
            return False
        if self.step_name != "cad":
            self._info("\n请在cad上运行!!!")
            return False
        return True

    def _get_checked_layers(self) -> List[str]:
        """获取勾选的层"""
        result = []
        for lay in self.all_datas:
            if self.all_datas[lay].checkState(0):
                if (lay not in self.note_list or
                        len(self.note_list.get(lay, [])) > 0):
                    result.append(lay)
        return result

    def _load_impedance(self, force: bool = False) -> None:
        """加载阻抗表"""
        try:
            from .database import InPlanQuery
        except ImportError:
            self.inplan_conn = None
            return

        if not self.inplan_conn or force:
            try:
                self.inplan_conn = InPlanQuery(
                    _mi.host_info.get("job_name", "")
                )
            except Exception:
                self.inplan_conn = None

        self.imp_info = _mi.get_impedance_table(self.inplan_conn)

    def _info(self, msg: str) -> None:
        """显示信息框"""
        QMessageBox.information(self, "提示框", msg, QMessageBox.Cancel)

    def _question(self, msg: str) -> bool:
        """显示确认框"""
        result = QMessageBox.question(
            self, "确认框", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return result == QMessageBox.Yes


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _add_json_notes(load_dict: Dict, job_name: str,
                    step_name: str, kkk: int = 1) -> None:
    """从 load_dict 恢复标记到 Genesis"""
    notes = _get_json_notes(load_dict, step_name)
    if not notes:
        return

    notes_new = {}
    for lay in notes:
        existing = _mi.get_notes_new(job_name, step_name, lay)
        if kkk and existing and step_name == "cad":
            notes_new[lay] = notes[lay]
            break
        _mi.GenesisAPI.delete_note(
            lay, [x[0] for x in existing][::-1]
        )
        _mi.GenesisAPI.delete_note_all(lay)
        notes_new[lay] = notes[lay]

    if kkk and notes_new and step_name != "cad":
        return  # 未添加全部

    if not notes_new:
        return

    _mi.GenesisAPI.open_step(job_name, step_name)
    for lay in notes_new:
        for note in notes_new[lay]:
            offset = _mi.print_config[13]
            x = (note[3] + offset[0]) / 25.4
            y = (note[4] + offset[1]) / 25.4
            _mi.GenesisAPI.add_note(lay, x, y, note[5])


def _get_json_notes(load_dict: Dict,
                    step_name: str) -> Dict[str, List]:
    """从 load_dict 获取 step_note"""
    result = {}
    if "step_note" not in load_dict:
        return result

    valid_steps = ("yg", "org", "orig", "cad", "edit")
    if step_name not in valid_steps:
        return result

    for stp in load_dict.get("step_note", {}):
        if stp != "cad":
            continue
        for lay in load_dict["step_note"][stp]:
            mark_keys = [
                n[10] for n in load_dict["step_note"][stp][lay]
                if len(n) > 10
            ]
            if mark_keys:
                result[lay] = mark_keys

    return result


def _sync_notes_to_dict(notelist: List, lay: str,
                        load_dict: Dict) -> None:
    """同步标记到 load_dict"""
    if "layer_note" not in load_dict:
        load_dict["layer_note"] = {}
    if "step_note" not in load_dict:
        load_dict["step_note"] = {}
        load_dict["step_note"]["cad"] = {}

    load_dict["step_note"].setdefault("cad", {})
    load_dict["step_note"]["cad"][lay] = notelist


def _build_imp_display_list() -> List[List]:
    """构建阻抗显示列表"""
    result = []
    for key in _mi.print_config[8]:
        parts = str(key).replace("层", "").replace("原稿值", "")
        parts = parts.replace(_mi.print_config[2], "").replace("-->", ":")
        parts = parts.split(":")

        vals = _mi.print_config[8][key]
        row = [""] * 9
        row[0] = parts[0] if len(parts) > 0 else ""
        row[1] = vals[0] or ""
        row[3] = vals[3] or ""
        row[4] = "/".join(vals[1]).replace("//", "/").strip("/")
        row[5] = "/".join(parts[2:]).replace("//", "/").strip("/") if len(parts) > 2 else ""
        row[6] = parts[1] if len(parts) > 1 else ""
        row[7] = vals[2] or ""

        # 判断阻抗类型
        orig_parts = row[5].split("/")
        type_parts = ["", "", ""]
        if len(orig_parts) > 1 and orig_parts[0] and orig_parts[1]:
            type_parts[0] = "差分"
        elif orig_parts[0]:
            type_parts[0] = "单线"
        if len(orig_parts) > 2 and orig_parts[2]:
            type_parts[1] = "共面"
        row[8] = ""
        row[2] = "".join(type_parts) + "阻抗"

        # 参考层细节
        for ref in vals[4]:
            sub = row[:]
            sub[1] = vals[4][ref][0] or ""
            sub[3] = vals[4][ref][1] or ""
            sub[4] = "/".join(vals[4][ref][2]).replace("//", "/").strip("/")
            sub[7] = ref
            result.append(sub)

        if not vals[4]:
            result.append(row)

    return result


def _make_mark_key(child: QTreeWidgetItem) -> str:
    """生成标记唯一 key"""
    return "~".join([
        child.text(4),
        _mi.get_mm_new(child.text(6).strip("/").strip("*")),
        _mi.get_mm_new(child.text(7).strip("/").strip("*")),
        child.text(8).strip("/").strip("*"),
        child.text(11).strip("/").strip("*"),
    ])


# ═══════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════

__all__ = ['MIWindow']


def main():
    """CLI 入口 - 启动 GUI"""
    if not _PYQT5_AVAILABLE:
        print("ERROR: PyQt5 未安装，无法启动 GUI")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="MI 打印图纸 GUI")
    parser.add_argument("job", nargs="?", default="",
                        help="料号名")
    parser.add_argument("--step", default="cad",
                        help="Step 名 (默认: cad)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MIWindow(args.job, args.step)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
