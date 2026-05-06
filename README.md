# pcb-drawing-printing-system

胜宏科技（惠州）MI (Manufacturing Instruction) 制程指示系统 v2.0

PCB 行业 MI 图纸自动生成系统。从 Genesis/InCAMPro CAM 软件中自动提取制程标记、查询 ERP 阻抗数据、渲染 SVG 图纸、生成 PDF 打印输出。

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    mi_gui.py (PyQt5 GUI)               │
│                     run_gui.py (入口)                    │
├─────────────────────────────────────────────────────────┤
│  mi_extractor.py          │  svg_renderer.py            │
│  · 标记提取/解析           │  · SVG 图形渲染             │
│  · 层信息管理              │  · 阻抗颜色映射             │
│  · 原稿数据获取            │  · PDF 转换 (cairosvg)      │
│  · 阻抗校验                │  · 标注线绘制               │
├─────────────────────────────────────────────────────────┤
│  database.py              │  geometry.py                │
│  · Oracle ERP 查询         │  · 几何计算                 │
│  · Oracle InPlan 查询      │  · 坐标变换                 │
│  · MySQL 标记持久化        │  · 距离/角度计算            │
├─────────────────────────────────────────────────────────┤
│  config.py                                              │
│  · 全局配置 · 颜色表 · 厂区映射 · Note 类型定义          │
├─────────────────────────────────────────────────────────┤
│        cam_interface.py (外部引用, gerber-tool/)         │
│        · Genesis/InCAMPro COM 通信                     │
│        · DO_INFO/INFO 封装                              │
└─────────────────────────────────────────────────────────┘
```

## 核心流程

1. **标记提取** (`mi_extractor.py`): 从 Genesis CAM 的制程标记/备注中提取结构化数据
2. **数据库查询** (`database.py`): 从 ERP/InPlan/MySQL 获取料号、阻抗、制作者信息
3. **图形渲染** (`svg_renderer.py`): 将 CAM 图形数据转为 SVG 矢量图
4. **GUI 交互** (`mi_gui.py`): PyQt5 界面进行标记验证、排序、生成图纸

## 项目结构

```
pcb-drawing-printing-system/
├── mi_print/           # 核心包
│   ├── __init__.py     # 包声明
│   ├── config.py       # 全局配置
│   ├── geometry.py     # 几何计算
│   ├── database.py     # Oracle + MySQL
│   ├── mi_extractor.py # MI 标记提取
│   ├── svg_renderer.py # SVG 渲染
│   └── mi_gui.py       # PyQt5 GUI
├── main.py             # CLI 入口
├── run_gui.py          # GUI 入口
├── requirements.txt    # 依赖列表
└── README.md           # 本文件
```

## 依赖

### 核心依赖
- Python 3.7+
- `svgwrite` - SVG 图形生成

### 可选依赖
- `PyQt5` - GUI 界面（无此依赖仅 CLI 可用）
- `cx_Oracle` - Oracle 数据库（ERP/InPlan 查询）
- `pymysql` - MySQL 数据库（标记持久化）
- `cairosvg` - SVG 转 PDF（无此依赖仅输出 SVG）
- `xlwt` - Excel 导出（阻抗表）

### 外部依赖
- `cam_interface.py` - Genesis/InCAMPro COM 通信接口
  - 路径: `../gerber-tool/cam_interface.py`（相对于本包）
  - 需在 Genesis/InCAMPro 环境中运行或通过 Gateway 远程连接

### 安装

```bash
# 基础安装
pip install svgwrite

# 完整安装
pip install -r requirements.txt

# Oracle 驱动（需要 Oracle Instant Client）
pip install cx_Oracle
```

## 使用方式

### CLI 模式

```bash
# 基本用法
python main.py --job <料号名> --step <step名> [选项]

# 示例
python main.py --job H50208GN013A1 --step cad                    # 生成所有层图纸
python main.py --job H50208GN013A1 --step cad --layers c1,s1      # 只输出指定层
python main.py --job H50208GN013A1 --step cad --output /tmp/mi    # 输出目录
python main.py --job H50208GN013A1 --step cad --unit mm           # 毫米单位
python main.py --job H50208GN013A1 --step cad --no-pdf            # 仅 SVG
python main.py --job H50208GN013A1 --step cad --profile           # 含成型轮廓
python main.py --job H50208GN013A1 --step cad --list-layers       # 列出可用层
```

### GUI 模式

```bash
# 在 Genesis/InCAMPro 脚本面板中运行
python run_gui.py <料号名> [--step cad]

# 或通过 Gateway 远程连接（需指定 PID）
python run_gui.py <料号名> --step cad
```

### GUI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+P` | 生成图纸 |
| `Ctrl+S` | 保存数据 |
| `Ctrl+X` | 获得原稿 |
| `Ctrl+C` | 导出阻抗 |
| `Ctrl+A` | 全选/取消全选 |
| `Ctrl+Z` | 选择下一页 |
| `Ctrl+F` | 打开目录 |
| `Ctrl+Q` | 关闭 |

## 关键设计

### 料号编码规则
- 13 位编码：如 `H50208GN013A1`
  - 位置 1-4: 厂内代号
  - 位置 5-6: 层数
  - 位置 7-11: 流水号
  - 位置 12-13: 版本

### 厂区映射
胜宏科技 6 个厂区：
- S0101: 胜宏一厂
- S0102: 胜宏二厂
- S0103: 胜宏三厂
- S0104: 胜宏四厂
- S0105: 胜宏五厂
- S0106: 胜宏六厂

### Note 类型
系统支持 18 种制程标记类型：
- 线宽/线距 (Eagle-WS-M)
- BGA/SMD/PAD 尺寸
- 铜桥/隔离环
- IC 间距
- 光点大小/开窗
- 阻抗标记（差分/单线/共面）

### 优雅降级
- `cx_Oracle` 未安装 → Oracle 查询不可用，警告但不崩溃
- `pymysql` 未安装 → MySQL 查询不可用
- `PyQt5` 未安装 → GUI 不可用，CLI 正常
- `cairosvg` 未安装 → 仅输出 SVG，不输出 PDF

## 变更记录

### v2.0 (重构版)
- 模块化重构：8 个参考文件 → 7 个独立模块
- 移除 genClasses.py，统一使用 cam_interface.py
- 修复 `math.fabs` → `abs` 废弃警告
- DO_INFO 格式统一验证
- 类型注解全覆盖
- 优雅降级处理
- 中文注释

### 原始版本
- genClasses.py v1.0 (Gf.zhang, 2019-12-12)
- math_line.py v1.0 (Gf.zhang, 2019-12-16)
- Oracle_DB.py v1.0.0 (LiuChuang, 2019-01-15)
- MySQL_DB.py v2.1.0 (LiuChuang, 2022-01-06)
- get_DB.py v1.0 (Gf.zhang, 2021-12-01)
- get_notes.py v1.0 (Gf.zhang, 2021-11-19)
- create_svg.py v1.0 (Gf.zhang, 2019-12-16)
- print_notes.py v1.0 (Gf.zhang, 2021-11-19)

## 许可证

本程序服务于胜宏科技（惠州），任何其他团体或个人如需使用，须经胜宏科技（惠州）相关负责人及作者批准。

## 作者

- 原始作者: Gf.zhang & LiuChuang (VTG.SH Software Group)
- 重构: 自动化重构 (2026-05)
