# 🔍 MI 打印图纸项目深度审计报告

> 审计日期: 2026-05-07 | 审计范围: 6个参考文件 → 6个新文件的逐方法对比

---

## 📊 审计总览

| 类别 | 数量 |
|------|------|
| 🔴 严重问题 | 8 |
| 🟡 中等问题 | 12 |
| 🟢 建议改进 | 6 |
| ✅ 已正确迁移 | ~60+ |

---

## 🔴 严重问题（影响核心功能）

### 1. `get_note_all()` 核心逻辑缺失 — 标记分类/合并完全丢失

- **文件**: mi_extractor.py、mi_gui.py
- **问题**: 原始 `ref_get_notes:get_note_all()` 是整个系统的核心函数（约70行），负责：
  1. 从 raw notes 读取并解析为结构化格式
  2. 分类标记：线宽/线距 → 差分阻抗/单线阻抗/单线共面阻抗/差分共面阻抗
  3. 阻焊定义PAD 检测（`noteSelect[iii[2]][7] == 1`）
  4. 光点开窗检测（`noteSelect[iii[2]][7] == 2`）
  5. 设置 load_dict["unit"]、load_dict["zkdc"]、load_dict["tzlb"] 等关键参数
  6. 初始化 load_dict["layer_note"] 和 load_dict["step_note"] 结构
  7. 管理 layer_note key 映射
  8. 最小线宽/线距信息合并到备注

  新版 `mi_gui.py:_get_note_all_ext()` 仅是一个空包装，缺少上述所有核心逻辑。


- **修复代码**（需在 mi_extractor.py 中新增）:

```python
def get_note_all(job_name: str, step_name: str, layer: str,
                 notelist: Dict, load_dict: Dict) -> None:
    """获取层的所有标记并完成分类、参数设置、数据结构初始化

    这是原 get_note_all() 的完整迁移。
    """
    global print_config

    # 1. 读取原始标记
    raw_notes = get_notes(job_name, step_name, layer)
    parsed = get_notes_new(job_name, step_name, layer)
    notelist[layer] = parsed

    # 2. 初始化 load_dict 参数
    load_dict.setdefault("unit", "mil")
    load_dict.setdefault("zkdc", "否")
    load_dict.setdefault("tzlb", "300")
    print_config[1] = load_dict["unit"]
    print_config[4] = load_dict["zkdc"]
    print_config[9] = load_dict["tzlb"]

    # 3. 初始化数据结构
    load_dict.setdefault("layer_note", {})
    load_dict.setdefault("step_note", {})
    load_dict["step_note"].setdefault(step_name, {})

    # 4. 处理每条标记
    for note in parsed:
        note_key = note[9]

        # 4a. 恢复已保存的备注
        if note_key in load_dict["layer_note"]:
            note[9] = load_dict["layer_note"][note_key]

        # 4b. 线宽/线距/阻抗标记分类
        if "线" in note[1] or "阻抗" in note[1]:
            note[9] = note[9].replace("最小线宽线距", "").replace("最小线宽", "").replace("最小线距", "").strip(";")

            # 从类型名中提取最小线宽/线距信息
            if "(" in note[1]:
                parts = note[1].strip(")").split("(")
                note[9] = (parts[1] + ";" + note[9]).strip("*").strip("/").strip(";")
                note[1] = parts[0]

        # 4c. 阻焊定义PAD 检测
        if note[2] in config.NOTE_SELECT:
            if config.NOTE_SELECT[note[2]][7] == 1 and load_dict["layer_dist"].get(layer, ["", "", "", "MM"])[3] == "MM":
                if "阻焊定义PAD" not in note[9]:
                    note[9] = ("阻焊定义PAD;" + note[9].replace("*", "")).strip(";")

            # 4d. 光点开窗检测
            if config.NOTE_SELECT[note[2]][7] == 2 and load_dict["layer_dist"].get(layer, ["", "", "", "MM"])[3] == "MM":
                if "光点开窗" not in note[9]:
                    note[9] = ("光点开窗;" + note[9].replace("*", "")).strip(";")

    # 5. 写入 step_note
    load_dict["step_note"][step_name][layer] = parsed
```

### 2. `get_mi_info()` 完全遗漏 — MySQL 数据同步不可用

- **文件**: mi_extractor.py
- **问题**: 原始函数负责将标记数据同步到 MySQL 数据库 (`mi_db.drawings_marked`)，包括：
  1. 从 MySQL 获取 MI 制作者信息
  2. 解析工号/部门/手机/邮箱
  3. 构建 insert/update SQL
  4. 调用 `add_data()` 持久化
  
  新版完全没有这个功能，标记数据无法保存到数据库，其他用户无法共享标记。

- **修复代码**:

```python
def sync_to_mysql(load_dict: Dict, host_info: Dict) -> bool:
    """将标记数据同步到 MySQL 数据库（替换原 get_mi_info）"""
    if not load_dict.get("job_name"):
        return False
    if not load_dict.get("win_user"):
        return False

    try:
        from .database import MySQLQuery
    except ImportError:
        print("[WARN] MySQL 不可用，跳过数据同步")
        return False

    try:
        mysql = MySQLQuery(log_file=host_info.get("mysqlLogfile"))
    except Exception:
        return False

    if not mysql.dbc:
        return False

    job_name = load_dict["job_name"].upper()

    # 获取 MI 制作者信息
    mi_info = mysql.get_mi(job_name)
    for k, v in mi_info.items():
        load_dict[k] = v

    # 更新修改时间
    load_dict["modify_time"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime()
    )
    save_json(host_info["jsonFile"], load_dict)

    # 构建 MySQL 数据
    mysql_data = {
        "job_name": job_name,
        "marks_json": json.dumps(load_dict, ensure_ascii=False),
        "mark_count": load_dict.get("mark_count", 0),
        "create_by": mi_info.get("emp_no", ""),
        "create_by_name": mi_info.get("mi_maker", ""),
        "update_by": load_dict["win_user"],
        "update_by_name": load_dict.get("editer_name", ""),
        "update_time": "NOW()",
    }

    # 完善用户信息
    new_names = mysql.get_edit_name(["emp_no", mysql_data["update_by"]])
    if new_names[0]:
        mysql_data["update_by"] = new_names[0]
        mysql_data["update_by_name"] = new_names[1]
    else:
        new_names = mysql.get_edit_name(
            ["name", mysql_data["update_by_name"]]
        )
        mysql_data["update_by"] = new_names[0]
        mysql_data["update_by_name"] = new_names[1]

    if mysql_data["create_by_name"] and mysql_data["update_by"] and mysql_data["update_by_name"]:
        result = mysql.add_data(mysql_data)
    else:
        print(f'Not uploaded: {mysql_data}')
        result = False

    return result
```

### 3. `get_josn_notes()` / `add_josn_notes()` 缺失 — 标记恢复功能不可用

- **文件**: mi_extractor.py
- **问题**: 
  - `get_josn_notes()` 从 load_dict 中提取已保存的 note key 列表
  - `add_josn_notes()` 将保存的标记恢复到 Genesis 层上
  - 这是"保存→重新打开料号→恢复标记"功能的基石
  
  缺失导致：关闭料号后重新打开时，之前保存的标记无法恢复到 Genesis 中。

- **修复代码**:

```python
def get_saved_notes(load_dict: Dict, step_name: str) -> Dict[str, List[str]]:
    """从 load_dict 中提取已保存的标记（对应 get_josn_notes）"""
    notes = {}
    valid_steps = ["yg", "org", "orig", "cad", "edit"]

    if step_name not in valid_steps:
        return notes
    if "step_note" not in load_dict:
        return notes

    for step in load_dict["step_note"]:
        if step != step_name:
            continue
        for layer in load_dict["step_note"][step]:
            keys = [n[10] for n in load_dict["step_note"][step][layer] if len(n) > 10 and n[10]]
            if keys:
                notes[layer] = keys

    return notes


def restore_saved_notes(load_dict: Dict, job_name: str,
                        step_name: str, check_first: bool = True) -> None:
    """将保存的标记恢复到 Genesis 层上（对应 add_josn_notes）"""
    saved = get_saved_notes(load_dict, step_name)
    if not saved:
        return

    # 检查是否已有标记（避免重复）
    if check_first:
        for layer in saved:
            existing = get_notes(job_name, step_name, layer)
            if existing:
                return  # 已有标记，不重复添加

    GenesisAPI.open_step(job_name, step_name)
    for layer in saved:
        # 先清除旧标记
        GenesisAPI.delete_note_all(layer)
        for note_data in load_dict["step_note"][step_name][layer]:
            x = (note_data[3] + print_config[13][0]) / 25.4
            y = (note_data[4] + print_config[13][1]) / 25.4
            GenesisAPI.add_note(layer, x, y, note_data[5])
```

### 4. Gateway 协议实现缺陷 — 可能导致数据丢失

- **文件**: cam_interface.py，`_GatewayCOM.COM()` 方法
- **行号**: ~304
- **问题**: 原始 `Gateway.py` 的 COM 协议：
  1. `COM <args>` → 读取 `STATUS`
  2. `COMANS` → 读取 `COMANS`
  3. 读取 `answer` 行（第3行）
  
  新代码只读 STATUS 和 COMANS，**跳过了 answer 行**。这会导致下一次读取时拿到上一轮的残留数据，造成协议失步。

- **修复代码**:

```python
def COM(self, args):
    """执行 Genesis COM 命令（修复版协议）"""
    self.COMANS = ''
    self.STATUS = 0
    try:
        self.STATUS = int(self.__in_out(f'COM {args}'))
        self.COMANS = self.__in_out('COMANS')
        # ⚠️ 关键修复：读取 answer 行避免协议失步
        _answer = self.__in_out('COMANS')  # Gateway 在 COMANS 后多返回一行
    except (ConnectionError, ValueError, OSError):
        self.STATUS = -2
    return self.STATUS
```

### 5. `_EmbeddedCOM.PAUSE()` 返回解析不完整

- **文件**: cam_interface.py，`_EmbeddedCOM.PAUSE()`
- **行号**: ~145
- **问题**: 原始 `genClasses.PAUSE()` 读取 3 行:
  ```python
  self.STATUS = int(input())
  self.READANS = input()
  self.PAUSANS = input()
  ```
  新代码只读取 STATUS 和 READANS，**缺少 PAUSANS**。虽然 PAUSANS 不常用，但在某些用户交互场景下可能包含关键返回值。

- **修复代码**:

```python
def PAUSE(self, msg):
    self._send('PAUSE', msg)
    self.STATUS = int(sys.stdin.readline())
    self.READANS = sys.stdin.readline().strip()
    self.PAUSANS = sys.stdin.readline().strip()
    return self.STATUS
```

### 6. `_EmbeddedCOM` 缺少 `AUX()` 方法

- **文件**: cam_interface.py
- **问题**: 原始代码使用 `gengf.AUX('set_group,group=xxx')` 来设置 AUX group。新代码直接用 `COM` 执行 `set_group` 命令。但在 Genesis 中，AUX 和 COM 是不同的命令管道。
  
  在 Embededded 模式下，`open_step()` 中的 `_COM('set_group,group=' + ans)` 应该使用 AUX 而不是 COM。

- **修复代码**:

```python
# 在 _EmbeddedCOM 类中添加:
def AUX(self, args):
    self._send('AUX', args)
    self.STATUS = int(sys.stdin.readline())
    self.READANS = sys.stdin.readline().strip()
    self.COMANS = self.READANS[:]
    return self.STATUS

# 在 _GatewayCOM 类中添加:
def AUX(self, args):
    return self.COM(args)
```

### 7. `check_imp()` 逻辑变更 — print_PDF[8] 双向更新缺失

- **文件**: mi_extractor.py，`check_impedance()`
- **问题**: 原始 `check_imp()` 在匹配到阻抗后，会双向更新 `print_PDF[8]`（阻抗表）：
  ```python
  print_PDF[8][gfkey][0] = infos[-1]  # 更新标记信息
  print_PDF[8][gfkey][3] = infos[-2]
  for reflay in print_PDF[8][gfkey][4].keys():
      if reflay in frs:
          print_PDF[8][gfkey][4][reflay][0] = infos[-1]
          print_PDF[8][gfkey][4][reflay][1] = infos[-2]
  ```
  新代码 `check_impedance()` 只返回匹配结果，但**不更新阻抗表**。这会导致后续 `get_impedance_list()` / `show_imp()` 显示不完整数据。

- **修复代码**:

```python
def check_impedance(imp_info: List[Dict], zk_list: List[List],
                    check_data: List) -> Tuple[List[str], str]:
    """检查阻抗匹配（修复版：包含 print_PDF[8] 更新）"""
    results = []
    matched_str = ""
    if not imp_info or not zk_list:
        return results, matched_str

    fff = ["", ""]
    ref_layers = ["", ""]

    # 从 zk_list 中匹配数据
    for zk in zk_list:
        if zk[-1] == check_data[-1] and zk[1] == check_data[1].upper() \
                and zk[10] == check_data[3]:
            fff = [zk[5]] + zk[8:10]
            ref_layers = zk[2:4]
            for i in range(3):
                if fff[i]:
                    fff[i] = round_str(float(fff[i]), 2)
                else:
                    fff[i] = ""

    if not fff:
        return results, matched_str

    # 构建参考层集合
    fra = "&".join(ref_layers).strip().strip("&")
    frb = "&".join(ref_layers[::-1]).strip().strip("&")
    frs = [fra, frb] if fra and frb else ["@"]
    frs = list(set(frs))

    # 匹配 InPlan 阻抗表
    for imp in imp_info:
        if check_data[1].upper() in (imp.get('TRACE_LAYER_', ''),
                                     imp.get('TRACE_LAYER_2_', '')):
            try:
                imp_diff = abs(float(imp['CUSTOMER_REQUIRED_IMPEDANCE'])
                               - float(check_data[3]))
            except (ValueError, TypeError):
                imp_diff = 100
            if imp_diff < 0.1:
                orig_vals = [imp['ORIGINAL_TRACE_WIDTH'],
                             imp['DESIGN_TRACE_TRACE_SPACING'],
                             imp['DESIGN_TRACE_GROUND_SPACING']]
                for i in range(3):
                    orig_vals[i] = round_str(orig_vals[i], 2) if orig_vals[i] else ""

                new_vals = [imp['FINISH_LW_'], imp['FINISH_LS_'], imp['COPPER_SPAC_']]
                for i in range(3):
                    new_vals[i] = round_str(float(new_vals[i])) if new_vals[i] else ""

                if "/".join(fff) == "/".join(orig_vals):
                    results.append("/".join(new_vals).strip("/").replace("//", "/"))

                    # ⚠️ 关键修复：更新 print_PDF[8]
                    gfkey = (f"{check_data[1].upper()}层:"
                             f"{round_str(float(imp['CUSTOMER_REQUIRED_IMPEDANCE']), 2)}"
                             f"{print_config[2]}-->原稿值{'/'.join(orig_vals)}")
                    results = list(set(results))
                    if gfkey in print_config[8]:
                        print_config[8][gfkey][0] = check_data[-1]
                        print_config[8][gfkey][3] = check_data[-2]
                        for reflay in print_config[8][gfkey][4]:
                            if reflay in frs:
                                print_config[8][gfkey][4][reflay][0] = check_data[-1]
                                print_config[8][gfkey][4][reflay][1] = check_data[-2]
                                matched_str = "/".join(
                                    print_config[8][gfkey][4][reflay][2]
                                ).strip("/").replace("//", "/")

    return results, matched_str
```

### 8. `get_string()` 工具函数缺失

- **文件**: mi_extractor.py
- **问题**: 原始 `get_string()` 生成 A0-Z9 的组合键列表:
  ```python
  def get_string():
      marks = []
      for b in string.digits:
          for a in string.ascii_uppercase:
              marks.append((a+b).rstrip("0"))
      return marks
  ```
  虽然新代码有 `_get_string_s()`，但它的参数化方式和原始 `get_string()` 不同（新的是 `_get_string_s(texts, strint)`，返回 `[A0, A1, ..., Z99]` 格式）。
  原始 `get_string_s()` 的参数名是 `texts` (字符串列表) vs 新 `_get_string_s(texts: str, ...)` (单个字符串)。
  
  原始函数接收的是**字符列表**（如 `["A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z"]`），新函数接收的是**单个字符串**。这导致调用方式不兼容。

- **修复代码**:

```python
def get_string() -> List[str]:
    """生成 A0-Z9 组合键列表（对应原 get_string()）"""
    import string as _string_module
    marks = []
    for b_char in _string_module.digits:
        for a_char in _string_module.ascii_uppercase:
            marks.append((a_char + b_char).rstrip("0"))
    return marks
```

---

## 🟡 中等问题（影响部分功能）

### 9. `get_note_zj()` 阻抗注解生成缺失

- **文件**: mi_extractor.py
- **问题**: 原始生成类似 `"注解: 单线阻抗测量:线宽;差分阻抗测量:线宽/线距"` 的注解文本，用于图纸底部说明。
- **修复代码**:

```python
def get_note_zj(notelist: List[List]) -> List[str]:
    """生成阻抗测量注解文本"""
    keys = []
    for note in notelist:
        if "单线阻抗" in note[1]:
            key = "单线阻抗测量:线宽"
            if key not in keys:
                keys.append(key)
        elif "差分阻抗" in note[1]:
            key = "差分阻抗测量:线宽/线距"
            if key not in keys:
                keys.append(key)
        elif "单线共面阻抗" in note[1]:
            key = "单线共面阻抗测量:线宽/线到铜"
            if key not in keys:
                keys.append(key)
        elif "差分共面阻抗" in note[1]:
            key = "差分共面阻抗测量:线宽/线距/线到铜"
            if key not in keys:
                keys.append(key)
    if not keys:
        return []
    return ["注解: " + ";".join(keys)]
```

### 10. `get_zk()` Excel 阻抗导出缺失

- **文件**: mi_extractor.py
- **问题**: 原始使用 `xlwt` 库导出阻抗 Excel 表格。新代码中 `get_impedance_list()` 返回数据但**不导出 Excel**。
- **修复代码**:

```python
def export_impedance_xls(job_name: str, zk_list: List[List]) -> str:
    """导出阻抗数据为 Excel（对应原 get_zk()）"""
    if not zk_list:
        return "\n没有定义阻抗信息!!!"

    # 去重
    seen = set()
    unique = []
    for fff in zk_list:
        key = ";".join([fff[1], fff[2], fff[3], fff[5]] + fff[8:11])
        if key not in seen:
            unique.append(fff)
            seen.add(key)

    header = "模型	测试层	上参考层	下参考层	对称制作	线宽	线宽(+)	线宽(-)	线距	线到铜	客规阻值	客规阻值(+)	客规阻值(-)"
    headers = header.split()
    unique.insert(0, headers)

    paths = os.path.join(config.SVG_DIR, job_name.upper())
    os.makedirs(paths, exist_ok=True)
    xls_file = os.path.join(paths, job_name.upper() + ".xls")

    try:
        import xlwt
        xl = xlwt.Workbook(encoding='utf-8')
        sheet = xl.add_sheet('ImpDatas', cell_overwrite_ok=False)
        style = xlwt.XFStyle()
        font = xlwt.Font()
        font.name = 'Times New Roman'
        font.bold = True
        style.font = font
        for row in range(len(unique)):
            for col in range(len(headers)):
                try:
                    sheet.write(row, col, unique[row][col])
                except IndexError:
                    sheet.write(row, col, "")
        xl.save(xls_file)
    except ImportError:
        xls_file = "\nxlwt 未安装，无法导出 Excel"
    except Exception as e:
        xls_file = f"\n写入表格错误: {e}"

    return xls_file
```

### 11. `cr_line_file()` 线信息文件导出缺失

- **文件**: mi_extractor.py
- **问题**: 原始导出最线宽/线距信息到文本文件，供 InPlan 使用。
- **修复代码**:

```python
def export_line_info_file(load_dict: Dict) -> str:
    """导出最小线宽/线距文件（对应原 cr_line_file()）"""
    job_name = load_dict.get("job_name", "").upper()
    if not job_name:
        return ""

    line_info = get_line_info()
    if not line_info:
        return ""

    file_path = os.path.join(config.SVG_DIR, job_name, job_name + ".txt")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    lines = []
    report = ""
    for layer in sorted(line_info.keys()):
        line = f"{layer}\t{line_info[layer]}\n"
        lines.append(line)
        report += line

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception as e:
        return f"\n{os.path.basename(file_path)}写入错误: {e}"

    return f"\n{report}\n\n数据来源于notes录入的成品值,可用于上传InPlan\n文件:{file_path}"
```

### 12. `openstep()` 中 AUX set_group 调用不正确

- **文件**: mi_extractor.py, `GenesisAPI.open_step()`, ~248行
- **问题**: 原始代码:
  ```python
  gengf.COM('editor_group,job=%s,is_step=yes,name=%s' % (jjj,p))
  gengf.AUX('set_group,group='+ gengf.COMANS)  # ← AUX, 不是 COM!
  ```
  新代码:
  ```python
  cls._COM('set_group,group=' + ans)  # ← 使用了 COM，应该用 AUX
  ```
  在 Genesis 中，`set_group` 是 AUX 命令，在嵌入式模式下调用 COM 可能导致 group 设置失败。

### 13. `EDITOR_GROUP` 返回值保护不完整

- **文件**: mi_extractor.py, `GenesisAPI.open_step()`, ~250行
- **问题**: 新代码有空值检查:
  ```python
  if not ans or not ans.strip():
      raise RuntimeError(...)
  ```
  但原始代码没有这个异常抛出。虽然增加保护是好的，但 `raise RuntimeError` 会中断流程。原始代码用 `gengf.AUX('set_group,group=' + gengf.COMANS)`，如果 COMANS 为空，AUX 会收到无效参数但不会崩溃。
  
  建议改为警告而不是异常:

```python
if not ans or not ans.strip():
    print(f"[WARN] editor_group 返回空，当前 group 可能无效")
else:
    cls._AUX('set_group,group=' + ans)
```

### 14. `ref_genClasses.Step.COM()` 自动 setGroup 机制缺失

- **文件**: cam_interface.py
- **问题**: 原始 `Step.COM()` 重载了 `COM()`，每次调用前自动执行 `setGroup()`:
  ```python
  def COM(self, args):
      if self.group:
          self.setGroup()
      self.sendCmd('COM', args)
      ...
  ```
  新版 CAM 没有 step 级别的 COM 重载，这意味着在 open_step 后，后续的 filter/select 命令不会自动设置 group。不过由于 `CAM` 设计为无状态模式（每次命令独立），这个差异影响有限。

### 15. `parseInfo` vs `gfparseInfo` 差异

- **文件**: cam_interface.py, `_parse_info_lines()`
- **问题**: 原始 genClasses 有两个解析方法:
  - `parseInfo()`: 将值转换为 int/float
  - `gfparseInfo()`: 保留字符串原值（不转换数字）
  
  新版 `_parse_info_lines()` 统一使用 `re.finditer(r"'([^']*)'")` 提取，**不转换数字**，行为接近 `gfparseInfo`。对于需要数字类型的场景（如 `Gf.zhang` 代码中比较坐标值），可能导致类型比较出错。

  同时在 `mi_extractor.py:_gf_parse_info()` 中又有一个几乎相同的实现，存在代码重复。

### 16. `convertToNumber` 异常处理不一样

- **文件**: cam_interface.py
- **问题**: 原始代码:
  ```python
  def convertToNumber(self,value):
      convert_value = value
      try:
          convert_value = int(value)
      except:
          try:
              convert_value = float(value)
          except:
              pass
      return convert_value
  ```
  新版:
  ```python
  @staticmethod
  def convertToNumber(val):
      if val is None:
          return 0
      if isinstance(val, (int, float)):
          return val
      try:
          return int(val)
      except (ValueError, TypeError):
          try:
              return float(val)
          except (ValueError, TypeError):
              return 0
  ```
  功能相同但新版在失败时返回 0 而不是原值。原始代码保留原字符串值（如非数字字符串仍返回"abc"），新版返回 0。这对 `parseInfo` 结果有差异：原始代码遇到非数字保留原样，新版强制返回 0。

### 17. `get_move_note()` 逻辑正确但尺寸比较边界有问题

- **文件**: mi_extractor.py, `get_move_offset()`
- **问题**: 原始 `get_move_note()` 使用 `"/" in [a,b]` 检查（a,b 是板尺寸字符串如 "100.0*200.0"），当尺寸为 "/" 时跳过。新版 `get_move_offset()` 使用相同的逻辑，但字符串比较 `a != b` 对新旧料号不同尺寸时正确。这个逻辑本身没问题，只是之前已修复的版本中说已修复，确认无新增问题。

### 18. `_mm_value` 单位转换不完整

- **文件**: mi_extractor.py, `_get_mm()` / `get_mm_new()`
- **问题**: 原始 `get_mm_new()` 当 `print_PDF[1] == "um"` 且 `kkk=True` 时使用 `get_mm(text, 3)` (mil→um)。新代码一致。但原始代码还有 `kkk=2` 场景（um→mil），这在 GUI 显示时可能用到。新代码 `get_mm_new()` 调用路径与原始一致，无新增问题。

### 19. `ref_genClasses.dbutil()` 实现差异

- **文件**: cam_interface.py
- **问题**: 原始 `dbutil()`:
  ```python
  def dbutil(self, *args):
      binary = os.path.join(self.edir, 'misc', 'dbutil')
      args = string.join(args)
      fd = os.popen(binary + ' ' + args)
      res = fd.readlines()
      return res
  ```
  新版:
  ```python
  def dbutil(self, *args):
      arg_str = ','.join(str(a) for a in args)
      return self.COM(f'dbutil,{arg_str}')
  ```
  **完全不同的实现**。原始是调用外部 `dbutil` 命令行二进制工具，新版是通过 COM 命令调用。参数格式也从空格分隔变为逗号分隔。如果 Genesis 不支持 `COM dbutil,...` 格式，这个功能将完全不可用。

  查询 `dbutil` 的使用位置（`ref_genClasses:dbutil` 被 Job.dbName/dbPath/dbStat 调用），新版 CAM 中这些方法不存在，所以实际影响有限。

### 20. `all_symbol_dist` 初始化顺序差异

- **文件**: svg_renderer.py, `_init_symbol_styles()`
- **问题**: 原始代码中 `all_symbol_dist` 在模块顶层初始化，新代码通过 `_init_symbol_styles()` 延迟初始化。但原始代码中有一个微妙之处：
  ```python
  all_symbol_dist["circle.profile"] = all_symbol_dist["path.profile"]
  # 注意：这是引用赋值，修改一个会影响另一个
  ```
  新代码使用 `.copy()`:
  ```python
  _all_symbol_dist["circle.profile"] = _all_symbol_dist["path.profile"].copy()
  ```
  新代码更安全但行为与原始不一样。原始代码中修改 `circle.profile` 也会影响 `path.profile`，这是原作者的**有意设计**（共享样式）。

---

## 🟢 建议改进

### 21. 添加 `get_note_count()` 缺失的 sort 逻辑

- **文件**: mi_extractor.py, `_get_note_count()`
- **问题**: 原始 `get_note_count()` 返回 note key 列表（用于计数和去重）。新代码 `_get_note_count()` 行为一致，但未用到。建议在 `save_load_dict()` 中显式设置 `mark_count`。

### 22. `doinfostep()` 递归 Step 查询未完全暴露

- **文件**: mi_extractor.py
- **问题**: 原始 `doinfostep()` 递归获取所有子步骤。新代码 `GenesisAPI.get_step_info()` 只获取一层，递归版本在 svg_renderer.py 的 `_get_step_info()` 中。建议统一到 mi_extractor。

### 23. 缺少 CLI 参数文档

- **文件**: mi_gui.py
- **问题**: 原 `ref_print_notes` 在 Genesis 环境中通过 Script 面板运行，有特定的参数约定。新版 CLI 支持 `--job/--step` 但没有完整的命令文档。

### 24. `show_imp()` 显示阻抗列表功能未完全暴露

- **文件**: mi_extractor.py, `get_impedance_list()`
- **问题**: 原始 `show_imp()` 从 `print_PDF[8]` 构建显示用的阻抗列表（含参考层拆分）。新代码 `get_impedance_list()` 实现了类似功能，但原始对每个参考层单独生成一行（`for iii in print_PDF[8][gfkey][4].keys()`），新代码是否完全覆盖需验证。

### 25. `parseNotes` 中 `get_mm()` 调用位置差异

- **文件**: mi_extractor.py, `parseNotes()`
- **问题**: 原始 `parseNotes()` 在解析时调用 `get_mm(texts[2], kkk)` 转换单位。新代码也调用 `_get_mm()`。逻辑一致，但 `kkk` 参数的传递链需要确认。在 `get_notes_new()` 中调用 `parseNotes(notes)` 时未传 `kkk` 参数（默认 0），意味着不转换单位。原始代码中某些调用场景下 `kkk` 不为 0。

### 26. 重复代码: `_parse_info_lines` 和 `_gf_parse_info`

- **文件**: cam_interface.py + mi_extractor.py
- **问题**: 两个文件中各有一个几乎相同的 `_parse_info_lines` / `_gf_parse_info` 实现。建议统一到一个位置。

---

## ✅ 已验证正确的迁移

以下功能已正确迁移，无需修改：

1. ✅ `get_host()` → mi_extractor.get_host() — 完整
2. ✅ `get_layers()` → mi_extractor.get_layers() — 完整
3. ✅ `init_lays()` → mi_extractor.init_layers() — 完整（重构为更清晰的多个子函数）
4. ✅ `get_notes()` → mi_extractor.get_notes() — 完整
5. ✅ `parseNotes()` → mi_extractor.parseNotes() — 完整
6. ✅ `get_notes_new()` → mi_extractor.get_notes_new() — 完整
7. ✅ `get_notetype()` → mi_extractor._get_note_type_name() — 完整（子函数拆分）
8. ✅ `get_sort()` → mi_extractor.sort_notes() — 完整
9. ✅ `get_pad_size()` → mi_extractor.get_pad_size() — 完整
10. ✅ `get_fdata()` → mi_extractor.get_feature_data() — 完整
11. ✅ `get_sdata()` → mi_extractor._get_symbol_data() — 完整
12. ✅ `extract_original_data()` — 完整替代 `get_note_data()`
13. ✅ `get_features()` → GenesisAPI.get_features() — 完整
14. ✅ `read_json()` / `save_json()` — 完整
15. ✅ `get_json_name()` — 完整
16. ✅ `round_str()` — 完整（委托给 geometry）
17. ✅ `get_user_name()` → GenesisAPI.get_user_name() — 完整
18. ✅ `stepinfo()` → GenesisAPI.get_step_info() — 完整
19. ✅ `get_step_all()` → GenesisAPI.get_step_list() — 完整
20. ✅ `save_job()` → GenesisAPI.save_job() — 完整
21. ✅ `export_job()` → GenesisAPI.export_job() — 完整
22. ✅ `openstep()` → GenesisAPI.open_step() — 仅AUX调用需修复
23. ✅ `delete_tmp_layer()` → GenesisAPI.delete_tmp_layer() — 完整
24. ✅ `add_note()` / `delete_note()` / `delete_note_all()` / `change_notes()` / `view_note()` — 完整
25. ✅ `find_genesis_data()` / `find_genesis_old_data()` / `find_mysql_data()` / `mod_mysql_data()` — 完整
26. ✅ `get_editer()` / `get_code()` — 完整
27. ✅ `geometry.py` → ref_math_line 全部几何函数 — 完整
28. ✅ `database.py` OracleDB / MySQLDB 基础连接器 — 完整
29. ✅ `database.py` ERPQuery / InPlanQuery / MySQLQuery 业务查询 — 完整
30. ✅ svg_renderer.py 图形提取和 SVG 渲染核心 — 基本完整

---

## 📋 修复优先级建议

| 优先级 | 问题编号 | 影响范围 |
|--------|---------|---------|
| 🔴 P0 | #1 get_note_all() | 标记分类和合并完全损坏 |
| 🔴 P0 | #2 get_mi_info() | 数据库同步不可用 |
| 🔴 P0 | #4 Gateway 协议 | 外部连接时可能数据失步 |
| 🔴 P1 | #3 add_josn_notes() | 关闭后重开无法恢复标记 |
| 🔴 P1 | #7 check_imp() 阻抗表更新 | 阻抗数据显示不完整 |
| 🔴 P1 | #5 PAUSE 解析 | 用户交互响应可能不完整 |
| 🔴 P1 | #6 AUX 命令缺失 | set_group 可能失败 |
| 🟡 P2 | #10 get_zk() Excel 导出 | 阻抗数据无法导出 Excel |
| 🟡 P2 | #11 cr_line_file() | InPlan 数据上传功能缺失 |
| 🟡 P2 | #12 AUX set_group | open_step 中 group 设置路径错误 |
| 🟡 P2 | #15 parseInfo 行为差异 | 坐标比较可能类型错误 |
| 🟡 P2 | #19 dbutil 实现差异 | 如果用到则完全不可用 |
| 🟢 P3 | #9 get_note_zj() | 图纸注解缺失 |
| 🟢 P3 | #8 get_string() | 键生成不兼容 |
| 🟢 P3 | #20 样式引用 | 颜色样式可能异常 |
