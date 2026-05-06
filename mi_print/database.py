#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MI 打印图纸 - 数据库层
=====================
合并 Oracle_DB.py 和 MySQL_DB.py 为统一接口。

支持三种数据库连接：
  1. ERP (Oracle/Tiptop)   — 查询厂区、料号
  2. InPlan (Oracle)        — 查询阻抗表、铜厚
  3. MySQL                  — 标记数据持久化、工程管理

原始作者:
  - LiuChuang (Oracle_DB.py v1.0.0, MySQL_DB.py v2.1.0)
  - Gf.zhang (get_DB.py v1.0)

优雅降级: cx_Oracle / pymysql 未安装时警告但不崩溃
"""

import os
import re
import time
import platform
from typing import Optional, List, Dict, Any, Tuple

# ═══════════════════════════════════════════
# 依赖检测（优雅降级）
# ═══════════════════════════════════════════

_CX_ORACLE_AVAILABLE = False
_PYMYSQL_AVAILABLE = False

try:
    import cx_Oracle
    _CX_ORACLE_AVAILABLE = True
except ImportError:
    print("[WARN] cx_Oracle 未安装，Oracle 数据库功能不可用。"
          "请运行: pip install cx_Oracle")

try:
    import pymysql
    _PYMYSQL_AVAILABLE = True
except ImportError:
    print("[WARN] pymysql 未安装，MySQL 数据库功能不可用。"
          "请运行: pip install pymysql")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def rows_as_dicts(cursor) -> List[Dict]:
    """将 cursor 查询结果转为字典列表（Oracle 用）"""
    col_names = [d[0] for d in cursor.description]
    return [dict(zip(col_names, row)) for row in cursor]


def is_select_sql(sql: str) -> bool:
    """判断 SQL 是否为 SELECT 语句"""
    return bool(re.match(r'^(?:\s*\n*)?select', sql, re.I))


# ═══════════════════════════════════════════
# Oracle 连接器
# ═══════════════════════════════════════════

class OracleDB:
    """Oracle 数据库连接器

    支持 service_name 和 SID 两种连接方式。
    底层驱动: cx_Oracle

    Examples:
        >>> db = OracleDB()
        >>> db.connect(host='192.168.2.18', service_name='inmind.fls',
        ...            username='GETDATA', password='InplanAdmin')
        >>> result = db.select_dict('SELECT ...')
        >>> db.close()
    """

    def __init__(self, log_file: Optional[str] = None,
                 tns_name: str = 'service_name'):
        """
        Args:
            log_file: 日志文件路径（None 则不写文件）
            tns_name: 'service_name' 或 'sid'
        """
        if not _CX_ORACLE_AVAILABLE:
            raise ImportError("cx_Oracle 未安装")
        self.dbc = None
        self.tns = None
        self.tns_name = tns_name
        self.system = platform.system()
        self.log_file = log_file

    # ── 连接 / 关闭 ──

    def connect(self, host: str, port: int = 1521,
                username: str = '', password: str = '',
                service_name: str = '', sid: str = '') -> bool:
        """连接 Oracle 数据库

        Args:
            host:          主机名
            port:          端口
            username:      用户名
            password:      密码
            service_name:  服务名（tns_name='service_name' 时使用）
            sid:           SID（tns_name='sid' 时使用）

        Returns:
            连接成功返回 True，失败返回 False
        """
        try:
            if self.tns_name == 'service_name':
                self.tns = cx_Oracle.makedsn(
                    host, port, service_name=service_name
                )
                self.dbc = cx_Oracle.connect(username, password, self.tns)
            else:
                self.tns = cx_Oracle.makedsn(host, port, sid=sid)
                self.dbc = cx_Oracle.connect(username, password, self.tns)
            self._log(f"Oracle (Host:{host}) 连接成功")
            return True
        except Exception as e:
            self._log(f"Oracle (Host:{host}) 连接失败: {e}")
            self.dbc = None
            return False

    def close(self) -> None:
        """关闭数据库连接"""
        if self.dbc:
            try:
                self.dbc.close()
                self._log("Oracle 连接已关闭")
            except Exception:
                pass
            finally:
                self.dbc = None

    # ── SQL 执行 ──

    def execute(self, sql: str) -> Optional[List[Tuple]]:
        """执行 SQL，SELECT 返回结果列表，其他返回 True/False"""
        if not self.dbc:
            return None
        cursor = self.dbc.cursor()
        try:
            cursor.execute(sql)
            self._log(sql)
            if is_select_sql(sql):
                return cursor.fetchall()
            else:
                self.dbc.commit()
                return True
        except Exception:
            return False

    def select_dict(self, sql: str) -> List[Dict]:
        """SELECT 返回字典列表（键为列名）"""
        if not self.dbc:
            return []
        cursor = self.dbc.cursor()
        try:
            cursor.execute(sql)
            self._log(sql)
            if is_select_sql(sql):
                return rows_as_dicts(cursor)
            return []
        except Exception:
            return []

    # ── 日志 ──

    def _log(self, msg: str) -> None:
        """记录日志（控制台 + 可选文件）"""
        now = time.strftime('%Y-%m-%d %H:%M:%S',
                            time.localtime(time.time()))
        log_line = f"{now}: {msg}"
        print(log_line)
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_line + '\n')
            except Exception:
                pass


# ═══════════════════════════════════════════
# MySQL 连接器
# ═══════════════════════════════════════════

class MySQLDB:
    """MySQL 数据库连接器

    底层驱动: pymysql
    主要用于标记数据的持久化。

    Examples:
        >>> db = MySQLDB()
        >>> db.connect(host='192.168.2.19', database='project_status',
        ...            username='root', password='k06931!')
        >>> result = db.select_dict('SELECT ...')
        >>> db.close()
    """

    # 默认配置
    DEFAULT_CONFIG = {
        'host': "192.168.2.19",
        'port': 3306,
        'username': "root",
        'password': "k06931!",
        'database': "project_status",
        'charset': "utf8",
    }

    def __init__(self, log_file: Optional[str] = None,
                 log_code: str = 'utf-8'):
        """
        Args:
            log_file:  日志文件路径
            log_code:  日志编码
        """
        if not _PYMYSQL_AVAILABLE:
            raise ImportError("pymysql 未安装")
        self.log_file = log_file
        self.log_code = log_code
        self.dbc = None

    # ── 连接 / 关闭 ──

    def connect(self, host: str = '', database: str = '',
                port: int = 3306, username: str = '',
                password: str = '', print_log: bool = True) -> bool:
        """连接 MySQL 数据库"""
        host = host or self.DEFAULT_CONFIG['host']
        database = database or self.DEFAULT_CONFIG['database']
        port = port or self.DEFAULT_CONFIG['port']
        username = username or self.DEFAULT_CONFIG['username']
        password = password or self.DEFAULT_CONFIG['password']
        charset = self.DEFAULT_CONFIG['charset']

        try:
            self.dbc = pymysql.connect(
                host=host, port=port, user=username,
                passwd=password, db=database, charset=charset
            )
            self._log(f"MySQL (Host:{host}) 连接成功", print_log)
            return True
        except Exception as e:
            self._log(f"MySQL (Host:{host}) 连接失败: {e}", print_log)
            self.dbc = None
            return False

    def close(self) -> None:
        """关闭连接"""
        if self.dbc:
            try:
                self.dbc.close()
            except Exception:
                pass
            finally:
                self.dbc = None

    # ── SQL 执行 ──

    def execute(self, sql: str) -> Optional[Any]:
        """执行 SQL"""
        if not self.dbc:
            return None
        cursor = self.dbc.cursor()
        try:
            cursor.execute(sql)
            self._log(sql)
            if is_select_sql(sql):
                result = cursor.fetchall()
                cursor.close()
                return result
            else:
                self.dbc.commit()
                return True
        except Exception:
            return False

    def select_dict(self, sql: str) -> List[Dict]:
        """SELECT 返回字典列表"""
        if not self.dbc:
            return []
        cursor = self.dbc.cursor(cursor=pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            self._log(sql)
            if is_select_sql(sql):
                return cursor.fetchall()
            return []
        except Exception:
            return []

    # ── 日志 ──

    def _log(self, msg: str, print_log: bool = True) -> None:
        """记录日志"""
        if not print_log:
            return
        now = time.strftime('%Y-%m-%d %H:%M:%S',
                            time.localtime(time.time()))
        # 纯换行不添加时间戳
        if re.match(r'^\n(?:\n+)?$', msg):
            log_line = msg
        else:
            log_line = f"{now}：{msg}"

        try:
            print(log_line.encode(self.log_code).decode(self.log_code,
                                                        errors='replace'))
        except Exception:
            print(log_line)

        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding=self.log_code,
                          errors='replace') as f:
                    f.write(log_line + '\n')
            except Exception:
                pass


# ═══════════════════════════════════════════
# 业务数据库操作类
# ═══════════════════════════════════════════

class PublicQuery:
    """公共查询基类 — 料号解析

    13 位料号编码规则:
      位置 1-4:  厂内代号
      位置 5-6:  层数
      位置 7-11: 流水号
      位置 12-13: 版本
    """

    def __init__(self, job_name: str):
        self.JOB = job_name
        # 截取前 13 位
        self.JOB_SQL = self.JOB.upper()[:13]
        # 阻抗条料号 (如 K65308GN238A1-C)
        if self.JOB == self.JOB[:13] + "-c":
            self.JOB_SQL = self.JOB.upper()
        self.JOB_LIKE = f'%{self.JOB_SQL}%'

        # 解析层数
        if len(self.JOB_SQL) >= 13:
            try:
                self.layer_number = int(self.JOB[4:6])
            except (ValueError, IndexError):
                self.layer_number = -1
        else:
            self.layer_number = -1


class ERPQuery(PublicQuery):
    """ERP 查询（Oracle/Tiptop）

    功能:
      - get_site(): 查询厂区
    """

    def __init__(self, job_name: str, erp_config: Optional[dict] = None):
        """
        Args:
            job_name:   料号名
            erp_config: Oracle 连接配置
        """
        super().__init__(job_name)
        self._config = erp_config or {
            'host': "172.20.218.247",
            'port': 1521,
            'username': "zygc",
            'password': "ZYGC@2019",
            'service_name': "topprod",
            'sid': "topprod1",
        }
        self.db = OracleDB()
        self.dbc = None

        # 连接 — 先试 service_name，再试 SID
        if not self.db.connect(
            host=self._config['host'],
            port=self._config['port'],
            username=self._config['username'],
            password=self._config['password'],
            service_name=self._config['service_name'],
        ):
            self.db = OracleDB(tns_name='sid')
            self.db.connect(
                host=self._config['host'],
                port=self._config['port'],
                username=self._config['username'],
                password=self._config['password'],
                sid=self._config.get('sid', ''),
            )
        self.dbc = self.db.dbc

    def __del__(self):
        if self.dbc:
            self.db.close()

    def get_site(self) -> str:
        """查询厂区

        Returns:
            厂区中文名，失败返回空字符串
        """
        from .config import SITE_MAP
        sql = (
            "SELECT TC_AAC01 AS JOB_NAME, TC_AAC05 AS SITE_ "
            "FROM TC_AAC_FILE "
            f"WHERE TC_AAC01 = '{self.JOB_SQL}'"
        )
        query_result = self.db.select_dict(sql)
        if not query_result:
            return ""
        site_code = query_result[0].get('SITE_', '')
        return SITE_MAP.get(site_code, site_code)


class InPlanQuery(PublicQuery):
    """InPlan 查询（Oracle）

    功能:
      - get_impedance(): 获取阻抗表
      - get_job_exist():  检查料号是否存在
    """

    def __init__(self, job_name: str, inplan_config: Optional[dict] = None):
        """
        Args:
            job_name:     料号名
            inplan_config: Oracle 连接配置
        """
        super().__init__(job_name)
        self._config = inplan_config or {
            'host': "192.168.2.18",
            'port': 1521,
            'username': "GETDATA",
            'password': "InplanAdmin",
            'service_name': "inmind.fls",
        }
        self.db = OracleDB()
        self.dbc = None
        print("Open--->DB")
        self.db.connect(
            host=self._config['host'],
            port=self._config['port'],
            username=self._config['username'],
            password=self._config['password'],
            service_name=self._config['service_name'],
        )
        self.dbc = self.db.dbc

    def __del__(self):
        if self.dbc:
            self.db.close()
            print("Close--->DB")

    def get_impedance(self) -> List[Dict]:
        """从 InPlan 获取铜厚及层别正反数据

        Returns:
            阻抗信息字典列表
        """
        sql = (
            "SELECT "
            "  i.IMP_TYPE_, i.TRACE_LAYER_, i.REF_LAYER_, "
            "  i.TRACE_LAYER_2_, i.REF_LAYER_2_, "
            "  i.FINISH_LW_, i.FINISH_LS_, i.COPPER_SPAC_, "
            "  i.ORIGINAL_TRACE_WIDTH, "
            "  i.DESIGN_TRACE_TRACE_SPACING, "
            "  i.DESIGN_TRACE_GROUND_SPACING, "
            "  i.CUSTOMER_REQUIRED_IMPEDANCE, "
            "  i.COMPENSATE_VALUE_, i.CALCULATED_TRACE_WIDTH, "
            "  i.IS_SYMMETRY_IMP_ "
            "FROM VGT.RPT_JOB_IMPEDANCE_CONST_LIST i "
            f"WHERE i.job_name='{self.JOB_SQL}'"
        )
        return self.db.select_dict(sql)

    def job_exists(self) -> bool:
        """检查料号是否在 InPlan 中"""
        sql = (
            "SELECT I.ITEM_NAME AS JOB_NAME "
            "FROM VGT.PUBLIC_ITEMS I "
            "WHERE I.ITEM_TYPE = 2 "
            f"AND I.ITEM_NAME = '{self.JOB_SQL}'"
        )
        result = self.db.select_dict(sql)
        return len(result) > 0


class MySQLQuery(MySQLDB):
    """MI 标记数据 MySQL 查询

    继承 MySQLDB，提供业务 SQL:
      - get_data():     根据料号查询历史标记
      - add_data():     新增/更新标记
      - get_mi():       查询 MI 制作人员
      - get_edit_name(): 查询工号
    """

    def __init__(self, log_file: Optional[str] = None):
        super().__init__(log_file)
        print("mysql_open--->")
        self.connect()

    def __del__(self):
        try:
            if self.dbc:
                self.close()
                print("mysql_close--->")
        except Exception:
            pass

    # ── 历史标记查询 ──

    def get_data(self, job_name: str) -> List[Dict]:
        """查询标记历史数据

        Args:
            job_name: 料号名（13 位精确匹配或通配符 * 模糊匹配）

        Returns:
            标记数据字典列表
        """
        if not job_name:
            return []

        job_sql = job_name[0:13].upper()
        like_sql = "="

        if "*" in job_sql:
            job_sql = job_sql.replace("**", "*").replace("**", "*")
            job_sql = job_sql.replace("*", "%%")
            like_sql = "like"
        elif len(job_sql) < 13:
            return []

        sql = (
            "SELECT dm.job_name, "
            "  SUBSTRING(dm.job_name,12,2) rev, "
            "  dm.marks_json, dm.mark_count, "
            "  dm.create_by_name, dm.create_time, "
            "  dm.update_by_name, dm.update_time, "
            "  '1' barod_size "
            "FROM mi_db.drawings_marked dm "
            f"WHERE dm.job_name {like_sql} '{job_sql}' "
            "  AND LENGTH(dm.job_name) = 13 "
            "  AND dm.marks_json IS NOT NULL "
            "ORDER BY dm.update_time DESC"
        )
        return self.select_dict(sql)

    # ── 添加 / 更新标记 ──

    def add_data(self, mysql_info: dict) -> bool:
        """新增或更新标记数据

        Args:
            mysql_info: {
                job_name, marks_json, mark_count,
                create_by, create_by_name,
                update_by, update_by_name,
                update_time
            }

        Returns:
            执行结果
        """
        existing = self.get_data(mysql_info["job_name"])
        if existing:
            sql = (
                "UPDATE mi_db.drawings_marked SET "
                f"marks_json = '{mysql_info['marks_json']}', "
                f"mark_count = {mysql_info['mark_count']}, "
                f"create_by = '{mysql_info['create_by']}', "
                f"create_by_name = '{mysql_info['create_by_name']}', "
                f"update_by = '{mysql_info['update_by']}', "
                f"update_by_name = '{mysql_info['update_by_name']}', "
                f"update_time = {mysql_info['update_time']} "
                f"WHERE job_name = '{mysql_info['job_name']}'"
            )
            result = self.execute(sql)
            print("update--->", result)
        else:
            sql = (
                "INSERT INTO mi_db.drawings_marked "
                "(job_name, marks_json, mark_count, "
                " create_by, create_by_name, "
                " update_by, update_by_name, update_time) "
                "VALUES "
                f"('{mysql_info['job_name']}', "
                f"'{mysql_info['marks_json']}', "
                f"{mysql_info['mark_count']}, "
                f"'{mysql_info['create_by']}', "
                f"'{mysql_info['create_by_name']}', "
                f"'{mysql_info['update_by']}', "
                f"'{mysql_info['update_by_name']}', "
                f"{mysql_info['update_time']})"
            )
            result = self.execute(sql)
            print("insert--->", result)
        return bool(result)

    # ── MI 制作人员查询 ──

    def get_mi(self, job_name: str) -> Dict:
        """查询料号的 MI 制作人员信息

        Returns:
            {job, if_cancle, mi_maker, emp_no, department, mobile, email, mi_time}
        """
        if not job_name:
            return {}
        sql = (
            "SELECT T.job, T.if_cancle, T.mi_maker, "
            "  N.emp_no, N.department, N.mobile, N.email, "
            "  T.mi_time "
            "FROM project_status.project_status_jobmanage T, "
            "  project_status.project_status_usermanage N "
            f"WHERE T.job = '{job_name[0:13].upper()}' "
            "  AND N.name = T.mi_maker "
            "ORDER BY T.mi_time"
        )
        result = self.select_dict(sql)
        return result[0] if result else {}

    # ── 工号查询 ──

    def get_edit_name(self, names: list,
                      dept: str = "MI%",
                      orgc: str = "多层事业部") -> list:
        """根据姓名/工号查询用户工号

        Args:
            names: [type, value]  type='emp_no' 或 'name'
            dept:  部门匹配
            orgc:  事业部

        Returns:
            [emp_no, name]
        """
        result = ["", ""]
        if not names or not names[1]:
            return result
        sql = (
            "SELECT N.emp_no, N.name "
            "FROM project_status.project_status_usermanage N "
            f"WHERE N.{names[0]} = '{names[1]}' "
            f"  AND N.department LIKE '{dept}' "
            f"  AND N.Org_Code = '{orgc}'"
        )
        rows = self.select_dict(sql)
        if rows:
            result[0] = rows[0].get("emp_no", "")
            result[1] = rows[0].get("name", "")
        return result


# ── 模块导出 ──
__all__ = [
    'OracleDB', 'MySQLDB',
    'PublicQuery', 'ERPQuery', 'InPlanQuery', 'MySQLQuery',
    'rows_as_dicts', 'is_select_sql',
]
