# -*- coding: utf-8 -*-
"""
TASKING TriCore 栈使用分析工具 (完整版)
========================================

对构建产物（ELF / MAP 文件）进行静态分析，生成栈使用报告。
独立于 SCons，也可在 CI/CD 中直接调用。

功能:
  - 解析 MAP 文件中的栈配置、栈使用估算、内存使用、函数尺寸
  - 解析 ELF 中的 DWARF 调试信息 (通过 hldumptc -A) 获取:
      * 每个函数的栈消耗
      * 函数调用关系 (调用图)
  - 计算调用链最坏情况栈深度
  - 生成详细的栈使用分析报告

用法:
    python tools/stack_analyzer.py --project-dir=. --variant=debug
    python tools/stack_analyzer.py --project-dir=. --variant=release --verbose

输出:
    - 控制台输出概要报告
    - output/stack_report_<variant>.txt  详细报告
"""

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from datetime import datetime


# ===========================================================================
#  工具函数
# ===========================================================================

def _run(cmd, cwd=None, timeout=60):
    """运行命令并返回 stdout 文本。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return proc.stdout, proc.stderr, proc.returncode
    except FileNotFoundError:
        return "", f"命令未找到: {cmd}", -1
    except subprocess.TimeoutExpired:
        return "", f"命令超时 ({timeout}s): {cmd}", -1


def _parse_hex(s):
    """解析十六进制数字 (0x1234, 1234h, 1234)。"""
    if not s:
        return 0
    s = s.strip().replace(",", "").replace("_", "")
    if s.lower().endswith("h"):
        s = s[:-1]
    s = s.strip()
    if not s:
        return 0
    try:
        return int(s, 16) if (s.startswith("0x") or s.startswith("0X")) else int(s, 16)
    except ValueError:
        try:
            return int(s)
        except ValueError:
            return 0


def _format_bytes(b):
    """格式化字节数为可读字符串。"""
    if b >= 1024:
        return f"{b} ({b / 1024:.1f} KB)"
    return str(b)


def _split_table_row(line):
    """拆分 MAP 文件中的表格行。"""
    parts = [p.strip() for p in line.split("|")]
    # 去掉首尾空字符串
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


# ===========================================================================
#  解析器: MAP 文件
# ===========================================================================

class MapParser:
    """解析 TASKING 链接器生成的 .map 文件。"""

    def __init__(self, map_path):
        self.map_path = map_path
        self.text = ""
        self.lines = []
        self._load()

    def _load(self):
        if not os.path.isfile(self.map_path):
            raise FileNotFoundError(f"MAP 文件未找到: {self.map_path}")
        with open(self.map_path, "r", encoding="utf-8", errors="replace") as f:
            self.text = f.read()
        self.lines = self.text.splitlines()

    # ---- 1. 栈配置 (从 Locate Result 的 Sections 中提取) ----

    def parse_stack_sections(self):
        """
        从 "Locate Result > Sections > Space mpe:tcX:linear" 中提取栈段。
        MAP 格式:
            | mpe:dspr0 | | istack_tc0 (570) | 0x00000400 | ...
            | mpe:dspr0 | | ustack_tc0 (569) | 0x00004000 | ...
        """
        stacks = []
        in_locate = False
        in_sections = False
        in_tc_linear = False

        for line in self.lines:
            stripped = line.strip()

            # 进入 Locate Result 区域
            if "Locate Result" in stripped and stripped.startswith("***"):
                in_locate = True
                in_sections = False
                in_tc_linear = False
                continue

            if not in_locate:
                continue

            # 退出 Locate Result 区域 (遇到下一个 *** 标题)
            if stripped.startswith("***") and "Locate" not in stripped:
                break

            # 进入 Sections 子区域
            if stripped == "* Sections":
                in_sections = True
                continue

            if not in_sections:
                continue

            # 检测 Space mpe:tcX:linear 或 mpe:vtc:linear
            if "Space " in stripped and ":linear" in stripped:
                in_tc_linear = True
                continue

            # 检测其他 Space 退出
            if stripped.startswith("+ Space ") and ":linear" not in stripped:
                in_tc_linear = False
                continue

            if not in_tc_linear:
                continue

            # 解析表格行
            if "|" not in line:
                continue
            parts = _split_table_row(line)
            if len(parts) < 4:
                continue

            sec_info = parts[2]  # Section 列
            size_str = parts[3]  # Size (MAU) 列

            m = re.search(r"(ustack|istack)\S*", sec_info)
            if m:
                sec_name = m.group(0)
                size = _parse_hex(size_str)
                stype = "user" if "ustack" in sec_name else "interrupt"
                stacks.append({
                    "name": sec_name.split("(")[0].strip(),
                    "size": size,
                    "type": stype,
                })

        return stacks

    # ---- 2. 链接器估算的栈使用 ----

    def parse_estimated_stack_usage(self):
        """
        从 "Estimated stack usage" 表格中提取数据。
        MAP 格式:
            | ustack_tc0 | 0x00000018 | no | _START |
            | istack_tc0 | 0x0        | no |        |
        """
        in_section = False
        usages = []
        for line in self.lines:
            if "Estimated stack usage" in line:
                in_section = True
                continue
            if not in_section:
                continue
            if line.strip().startswith("***"):
                break
            if "|" not in line:
                continue
            parts = _split_table_row(line)
            if len(parts) >= 4 and parts[0] and "Stack" not in parts[0]:
                stack_name = parts[0]
                used = _parse_hex(parts[1]) if len(parts) > 1 and parts[1] else 0
                recursive = parts[2] if len(parts) > 2 else ""
                entry = parts[3] if len(parts) > 3 else ""
                usages.append({
                    "stack": stack_name,
                    "used": used,
                    "recursive": recursive,
                    "entry_points": entry,
                })
        return usages

    # ---- 3. 内存使用 ----

    def parse_memory_usage(self):
        """
        从 "Memory usage in bytes" 表格中提取数据。
        """
        in_section = False
        entries = []
        totals = {}
        for line in self.lines:
            if "Memory usage in bytes" in line:
                in_section = True
                continue
            if not in_section:
                continue
            if line.strip().startswith("***"):
                break
            if "|" not in line:
                continue
            parts = _split_table_row(line)
            if len(parts) >= 6:
                name = parts[0]
                if name in ("Memory", "Total") or name.startswith("-"):
                    if name == "Total":
                        totals = {
                            "name": "Total",
                            "code": _parse_hex(parts[1]) if len(parts) > 1 else 0,
                            "data": _parse_hex(parts[2]) if len(parts) > 2 else 0,
                            "reserved": _parse_hex(parts[3]) if len(parts) > 3 else 0,
                            "free": _parse_hex(parts[4]) if len(parts) > 4 else 0,
                            "total": _parse_hex(parts[5]) if len(parts) > 5 else 0,
                        }
                    continue
                if not name:
                    continue
                entry = {
                    "name": name,
                    "code": _parse_hex(parts[1]) if len(parts) > 1 else 0,
                    "data": _parse_hex(parts[2]) if len(parts) > 2 else 0,
                    "reserved": _parse_hex(parts[3]) if len(parts) > 3 else 0,
                    "free": _parse_hex(parts[4]) if len(parts) > 4 else 0,
                    "total": _parse_hex(parts[5]) if len(parts) > 5 else 0,
                }
                entries.append(entry)
        return entries, totals

    # ---- 4. 函数/节大小 (从 Link Result 中提取) ----

    def parse_function_sizes(self):
        """
        从 "Link Result" 表格中提取函数节大小。
        重点提取 .text 节 (代码段)。
        """
        in_section = False
        functions = []
        for line in self.lines:
            if "Link Result" in line:
                in_section = True
                continue
            if not in_section:
                continue
            if line.strip().startswith("***"):
                break
            if "|" not in line:
                continue
            parts = _split_table_row(line)
            if len(parts) < 4:
                continue
            obj_file = parts[0]
            sec_info = parts[1]
            size_str = parts[2]

            # 只提取 .text 节
            if not sec_info.startswith(".text"):
                continue

            size = _parse_hex(size_str)
            if size == 0:
                continue

            # 提取函数名: .text.xxx.main (56)  -> xxx.main
            # .text.cstart._start (7) -> _start
            func_name = sec_info
            func_name = re.sub(r"\s*\(\d+\)\s*$", "", func_name)
            func_name = re.sub(r"^\.text\.(?:libc\.)?", "", func_name)
            func_name = re.sub(r"\.(libcsw_fpu|libc|lib)\..*$", "", func_name)
            func_name = func_name.lstrip(".")

            if not func_name:
                continue

            functions.append({
                "object": os.path.basename(obj_file) if obj_file else "",
                "section": sec_info.split("(")[0].strip(),
                "function": func_name,
                "size": size,
            })
        return functions


# ===========================================================================
#  解析器: ELF ADX (hldumptc -A XML)
# ===========================================================================

class AdxParser:
    """
    解析 hldumptc -A 输出的 ADX XML 格式。
    包含:
      - 每个函数的栈消耗 (STACK-CONSUMPTION)
      - 调用关系 (CALLED-SYMBOLS)
      - 函数地址和大小
    """

    def __init__(self, xml_path):
        self.xml_path = xml_path
        self.functions = {}    # name -> info dict
        self.call_graph = []   # list of (caller, callee)
        self._parse()

    def _parse(self):
        if not os.path.isfile(self.xml_path):
            return

        tree = ET.parse(self.xml_path)
        root = tree.getroot()

        for elem in root.findall("MEMORY-ELEMENT"):
            category = elem.findtext("CATEGORY", "")
            if category != "FUNCTION":
                continue

            label = elem.findtext("LABEL-NAME", "")
            if not label:
                continue

            addr_str = elem.findtext("ABSOLUTE-ADDRESS", "0")
            size_str = elem.findtext("SIZE", "0")
            stack_str = elem.findtext("STACK-CONSUMPTION")
            comp_unit = elem.findtext("COMP-UNIT-NAME", "")

            # 收集调用信息
            called_symbols = []
            called_elem = elem.find("CALLED-SYMBOLS")
            if called_elem is not None:
                for cs in called_elem.findall("CALLED-SYMBOL"):
                    callee = cs.findtext("LABEL-NAME", "")
                    if callee:
                        called_symbols.append(callee)

            self.functions[label] = {
                "name": label,
                "address": _parse_hex(addr_str),
                "size": _parse_hex(size_str),
                "stack_consumption": _parse_hex(stack_str) if stack_str is not None else None,
                "comp_unit": comp_unit,
                "calls": called_symbols,
            }

            for callee in called_symbols:
                self.call_graph.append((label, callee))

    def has_data(self):
        return len(self.functions) > 0

    def get_functions_with_stack(self):
        """返回有栈消耗信息的函数列表。"""
        return [f for f in self.functions.values()
                if f["stack_consumption"] is not None and f["stack_consumption"] > 0]

    def compute_worst_case_stack_depth(self, entry_points=None):
        """
        计算从入口点到每个函数的调用链最坏情况栈深度。
        使用 BFS/拓扑排序算法。

        返回: {function_name: { "depth": int, "path": [func_names] }}
        """
        if entry_points is None:
            entry_points = ["_START", "main"]

        # 构建调用图 (caller -> [callees])
        call_map = defaultdict(list)
        for caller, callee in self.call_graph:
            call_map[caller].append(callee)

        # 反向调用图 (callee -> [callers])
        reverse_map = defaultdict(list)
        for caller, callee in self.call_graph:
            reverse_map[callee].append(caller)

        # 找出所有可达的入口点
        roots = []
        for ep in entry_points:
            if ep in self.functions:
                roots.append(ep)

        # 如果找不到指定入口点，找没有被调用的函数作为入口点
        if not roots:
            all_callees = {c for _, c in self.call_graph}
            for fname in self.functions:
                if fname not in all_callees:
                    roots.append(fname)

        if not roots:
            return {}

        # 计算每个函数从入口点可达的栈深度
        # 使用 BFS 遍历所有调用路径
        result = {}

        for root in roots:
            # 使用 DFS 计算所有路径
            visited_paths = set()
            stack = [(root, [root], self.functions[root]["stack_consumption"] or 0)]

            while stack:
                func, path, depth = stack.pop()

                # 更新结果
                if func not in result or depth > result[func]["depth"]:
                    result[func] = {"depth": depth, "path": list(path)}

                # 遍历子函数
                for callee in call_map.get(func, []):
                    if callee not in self.functions:
                        continue
                    # 检测循环 (防止无限递归)
                    if callee in path:
                        continue
                    callee_stack = self.functions[callee]["stack_consumption"] or 0
                    new_depth = depth + callee_stack
                    new_path = path + [callee]
                    stack.append((callee, new_path, new_depth))

        return result


# ===========================================================================
#  报告生成器
# ===========================================================================

class ReportGenerator:
    """生成栈使用分析报告。"""

    def __init__(self, project_name, variant, output_dir):
        self.project_name = project_name
        self.variant = variant
        self.output_dir = output_dir
        self.sections = []

    def add_section(self, title, content_lines):
        self.sections.append({"title": title, "lines": content_lines})

    def _build_text(self):
        lines = []
        sep = "=" * 68
        sub_sep = "-" * 68

        lines.append(sep)
        lines.append(f"  TASKING TriCore 栈使用分析报告")
        lines.append(sep)
        lines.append(f"  项目:      {self.project_name}")
        lines.append(f"  构建变体:  {self.variant}")
        lines.append(f"  生成时间:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(sep)
        lines.append("")

        for sec in self.sections:
            lines.append(sec["title"])
            lines.append(sub_sep)
            for line in sec["lines"]:
                lines.append(line)
            lines.append("")

        lines.append(sep)
        lines.append("  报告结束")
        lines.append(sep)
        return "\n".join(lines)

    def save(self):
        os.makedirs(self.output_dir, exist_ok=True)
        report_path = os.path.join(self.output_dir, f"stack_report_{self.variant}.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._build_text())
        return report_path

    def print_console(self):
        text = self._build_text()
        for line in text.splitlines():
            print(line, flush=True)


# ===========================================================================
#  主分析流程
# ===========================================================================

def analyze(project_dir, variant, tasking_bin_dir, output_dir, verbose=False):
    """
    执行完整的栈使用分析。

    参数:
        project_dir:    项目根目录 (SConstruct 所在目录)
        variant:        构建变体 (debug/release)
        tasking_bin_dir: TASKING 编译器 bin 目录
        output_dir:     报告输出目录
        verbose:        是否输出详细调试信息
    """
    errors = []
    project_name = os.path.basename(project_dir)

    # ---- 路径准备 ----
    build_dir = os.path.join(project_dir, "build", "tasking", variant)
    output_dir_abs = os.path.abspath(output_dir)

    # 查找 ELF 和 MAP 文件
    elf_path = None
    map_path = None
    for candidate_dir in [build_dir, output_dir_abs]:
        for fname in [f"{project_name}.elf", f"{project_name}.map"]:
            fpath = os.path.join(candidate_dir, fname)
            if os.path.isfile(fpath):
                if fname.endswith(".elf"):
                    elf_path = fpath
                else:
                    map_path = fpath

    hldump_path = os.path.join(tasking_bin_dir, "hldumptc.exe")
    elfsize_path = os.path.join(tasking_bin_dir, "elfsize.exe")

    report = ReportGenerator(project_name, variant, output_dir_abs)

    # ================================================================
    #  1. 产物检查
    # ================================================================
    sec_lines = []
    if elf_path:
        elf_size = os.path.getsize(elf_path)
        sec_lines.append(f"  ELF:     {elf_path}  ({_format_bytes(elf_size)})")
    else:
        sec_lines.append(f"  ELF:     未找到 (搜索路径: {build_dir})")
        errors.append("ELF 文件未找到，请先执行 scons 构建")

    if map_path:
        map_size = os.path.getsize(map_path)
        sec_lines.append(f"  MAP:     {map_path}  ({_format_bytes(map_size)})")
    else:
        sec_lines.append(f"  MAP:     未找到 (搜索路径: {build_dir})")
        errors.append("MAP 文件未找到，请先执行 scons 构建")
    report.add_section("[1] 分析产物", sec_lines)

    if errors:
        report.print_console()
        print("\n  错误: 请先执行 scons 构建生成产物!", flush=True)
        return False

    # ================================================================
    #  2. 解析 MAP 文件
    # ================================================================
    try:
        map_parser = MapParser(map_path)
    except FileNotFoundError as e:
        report.print_console()
        print(f"\n  错误: {e}", flush=True)
        return False

    # ---- 2a. 栈配置 ----
    stacks = map_parser.parse_stack_sections()
    sec_lines = []
    if stacks:
        for s in stacks:
            sec_lines.append(f"  {s['name']:<20}  {_format_bytes(s['size']):>10}  ({s['type']})")
        sec_lines.append("")
        total_stack = sum(s["size"] for s in stacks)
        sec_lines.append(f"  {'栈空间总计:':<20}  {_format_bytes(total_stack):>10}")
    else:
        sec_lines.append("  (未从 MAP 文件中提取到栈段声明)")
        sec_lines.append("  → 栈在 LSL 文件中定义，MAP 文件的 Locate Result 部分应有记录")
    report.add_section("[2] 栈空间配置", sec_lines)

    # ---- 2b. 链接器估算的栈使用 ----
    usages = map_parser.parse_estimated_stack_usage()
    sec_lines = []
    if usages:
        sec_lines.append(f"  {'栈名':<20} {'已使用':>10}  {'递归':>6}  入口点")
        sec_lines.append(f"  {'-'*20} {'-'*10} {'-'*6}  {'-'*20}")
        for u in usages:
            used_str = _format_bytes(u["used"])
            sec_lines.append(f"  {u['stack']:<20} {used_str:>10}  {u['recursive']:>6}  {u['entry_points']}")
        sec_lines.append("")
        sec_lines.append("  ⚠ 注意: 链接器估算仅涵盖静态可达路径,")
        sec_lines.append("    不包含间接调用、函数指针、中断嵌套等动态场景。")
    else:
        sec_lines.append("  (未找到链接器栈使用估算信息)")
    report.add_section("[3] 链接器估算的栈使用", sec_lines)

    # ---- 2c. 内存使用 ----
    mem_entries, mem_totals = map_parser.parse_memory_usage()
    sec_lines = []
    if mem_totals:
        sec_lines.append(f"  {'区域':<30} {'Code':>10} {'Data':>10} {'Total':>10}")
        sec_lines.append(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
        for e in mem_entries:
            if e["code"] > 0 or e["data"] > 0:
                sec_lines.append(
                    f"  {e['name']:<30} {_format_bytes(e['code']):>10} "
                    f"{_format_bytes(e['data']):>10} {_format_bytes(e['total']):>10}"
                )
        sec_lines.append(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
        t = mem_totals
        sec_lines.append(
            f"  {'总 计':<30} {_format_bytes(t['code']):>10} "
            f"{_format_bytes(t['data']):>10} {_format_bytes(t['total']):>10}"
        )
    else:
        sec_lines.append("  (未找到内存使用信息)")
    report.add_section("[4] 内存使用", sec_lines)

    # ---- 2d. 函数代码体积 ----
    functions = map_parser.parse_function_sizes()
    sec_lines = []
    if functions:
        functions.sort(key=lambda x: x["size"], reverse=True)
        top_n = min(30, len(functions))
        sec_lines.append(f"  Top {top_n} 大函数 (按代码体积排序):")
        sec_lines.append("")
        sec_lines.append(f"  {'排名':>4}  {'函数':<32} {'文件':<20} {'大小':>10}")
        sec_lines.append(f"  {'-'*4}  {'-'*32} {'-'*20} {'-'*10}")
        for i, f in enumerate(functions[:top_n], 1):
            sec_lines.append(
                f"  {i:>4}  {f['function']:<32} {f['object']:<20} {_format_bytes(f['size']):>10}"
            )
        sec_lines.append("")
        total_code = sum(f["size"] for f in functions)
        sec_lines.append(f"  代码段总计: {_format_bytes(total_code):>10}  ({len(functions)} 个函数)")
    else:
        sec_lines.append("  (未提取到函数尺寸信息)")
    report.add_section("[5] 函数代码体积 Top", sec_lines)

    # ================================================================
    #  3. 解析 ELF (ADX XML)
    # ================================================================
    adx_xml_path = os.path.join(build_dir, f"{project_name}.adx.xml")
    adx_available = False

    # 生成 ADX XML
    if os.path.isfile(hldump_path):
        out, err, rc = _run([hldump_path, "-A", elf_path])
        if rc == 0 and out:
            with open(adx_xml_path, "w", encoding="utf-8") as f:
                f.write(out)
            if verbose:
                print(f"  [ADX] XML 已生成: {adx_xml_path}", flush=True)

    adx = AdxParser(adx_xml_path)

    if adx.has_data():
        adx_available = True
        if verbose:
            print(f"  [ADX] 解析到 {len(adx.functions)} 个函数, "
                  f"{len(adx.call_graph)} 条调用关系", flush=True)

    # ================================================================
    #  6. 每个函数的栈消耗 (ADX)
    # ================================================================
    sec_lines = []
    if adx_available:
        funcs_with_stack = adx.get_functions_with_stack()
        if funcs_with_stack:
            funcs_with_stack.sort(key=lambda x: -x["stack_consumption"])
            sec_lines.append(f"  有栈消耗信息的函数: {len(funcs_with_stack)} 个")
            sec_lines.append("")
            sec_lines.append(f"  {'函数':<32} {'栈消耗':>10} {'代码大小':>10} {'源文件':<30}")
            sec_lines.append(f"  {'-'*32} {'-'*10} {'-'*10} {'-'*30}")
            total_stack = 0
            for f in funcs_with_stack:
                total_stack += f["stack_consumption"]
                sec_lines.append(
                    f"  {f['name']:<32} {_format_bytes(f['stack_consumption']):>10} "
                    f"{_format_bytes(f['size']):>10} {f['comp_unit']:<30}"
                )
            sec_lines.append("")
            sec_lines.append(f"  {'函数栈消耗总计:':<20} {_format_bytes(total_stack):>10}")
        else:
            sec_lines.append("  (所有函数栈消耗为 0, 或 DWARF 信息中无栈消耗数据)")
            sec_lines.append("  → 编译器优化可能消除了栈帧, 或编译选项未生成栈使用信息")
            sec_lines.append("  → 建议: 使用 -O0 编译可保留更完整的栈使用信息")
    else:
        sec_lines.append("  (ADX XML 不可用, 跳过栈消耗分析)")
        sec_lines.append("  → 需要 hldumptc.exe 工具和 ELF 中的 DWARF 调试信息")
    report.add_section("[6] 每个函数的栈消耗", sec_lines)

    # ================================================================
    #  7. 调用图分析 (ADX)
    # ================================================================
    sec_lines = []
    if adx_available and adx.call_graph:
        # 统计调用次数
        callee_count = defaultdict(int)
        caller_count = defaultdict(int)
        for caller, callee in adx.call_graph:
            callee_count[callee] += 1
            caller_count[caller] += 1

        # 找出入口点
        all_callers = {c for c, _ in adx.call_graph}
        all_callees = {c for _, c in adx.call_graph}
        roots = all_callers - all_callees
        if not roots:
            roots = {"_START", "main"} & set(adx.functions.keys())

        sec_lines.append(f"  总调用关系数: {len(adx.call_graph)}")
        sec_lines.append(f"  总函数数:     {len(adx.functions)}")
        sec_lines.append(f"  入口点:       {', '.join(sorted(roots)[:5])}")
        sec_lines.append("")

        # Top 10 被调用最多的函数
        sec_lines.append(f"  Top 10 被调用最多的函数:")
        sec_lines.append(f"  {'函数':<32} {'调用次数':>10}")
        sec_lines.append(f"  {'-'*32} {'-'*10}")
        for func, cnt in sorted(callee_count.items(), key=lambda x: -x[1])[:10]:
            sec_lines.append(f"  {func:<32} {cnt:>10}")

        sec_lines.append("")
        sec_lines.append(f"  Top 10 调用最多的函数:")
        sec_lines.append(f"  {'函数':<32} {'调用次数':>10}")
        sec_lines.append(f"  {'-'*32} {'-'*10}")
        for func, cnt in sorted(caller_count.items(), key=lambda x: -x[1])[:10]:
            sec_lines.append(f"  {func:<32} {cnt:>10}")

        # 打印完整的调用图 (if verbose)
        if verbose:
            sec_lines.append("")
            sec_lines.append("  --- 完整调用图 ---")
            # 按入口点分组打印
            for root in sorted(roots):
                sec_lines.append(f"  [{root}]")
                _print_call_tree(root, adx.call_graph, adx.functions, sec_lines, indent=4)
    else:
        sec_lines.append("  (调用图分析不可用)")
        if not adx_available:
            sec_lines.append("  → 原因: ADX XML 数据不可用")
        elif not adx.call_graph:
            sec_lines.append("  → 原因: ELF 中无调用关系信息")
        sec_lines.append("  → 建议: 使用 -g 编译选项启用 DWARF 调试信息")
    report.add_section("[7] 调用图分析", sec_lines)

    # ================================================================
    #  8. 调用链最坏情况栈深度 (ADX)
    # ================================================================
    sec_lines = []
    if adx_available:
        entry_points = ["_START", "main"]
        stack_depth = adx.compute_worst_case_stack_depth(entry_points)

        if stack_depth:
            # 按栈深度排序
            sorted_depth = sorted(stack_depth.items(), key=lambda x: -x[1]["depth"])

            sec_lines.append(f"  入口点: {', '.join(ep for ep in entry_points if ep in adx.functions)}")
            sec_lines.append("")
            sec_lines.append(f"  Top 20 调用链栈深度最大的函数:")
            sec_lines.append(f"  {'函数':<32} {'栈深度':>10} {'自身栈':>8} {'调用链长度':>10}")
            sec_lines.append(f"  {'-'*32} {'-'*10} {'-'*8} {'-'*10}")

            for func, info in sorted_depth[:20]:
                own_stack = adx.functions[func]["stack_consumption"] or 0
                chain_len = len(info["path"])
                sec_lines.append(
                    f"  {func:<32} {_format_bytes(info['depth']):>10} "
                    f"{_format_bytes(own_stack):>8} {chain_len:>10}"
                )

            sec_lines.append("")
            sec_lines.append("  ⚠ 注意: 栈深度 = 从入口点到该函数调用链上所有函数栈消耗之和")
            sec_lines.append("    此分析基于静态调用图, 不包含:")
            sec_lines.append("      - 函数指针 / 虚函数调用")
            sec_lines.append("      - 中断嵌套")
            sec_lines.append("      - 递归函数 (已跳过循环检测)")
        else:
            sec_lines.append("  (无法计算调用链栈深度)")
            sec_lines.append("  → 可能原因: 入口点未找到, 或栈消耗数据不全")
    else:
        sec_lines.append("  (ADX XML 不可用, 跳过调用链栈深度分析)")
    report.add_section("[8] 调用链最坏情况栈深度", sec_lines)

    # ================================================================
    #  9. ELF 总大小 (elfsize)
    # ================================================================
    elf_analyzer = ElfAnalyzer(elf_path, elfsize_path)
    elf_sizes, elf_err = elf_analyzer.get_elf_sizes()
    sec_lines = []
    if elf_sizes:
        sec_lines.append(f"  {'ROM 总计:':<20} {_format_bytes(elf_sizes.get('rom_total', 0)):>10}")
        sec_lines.append(f"    ├─ 代码:      {_format_bytes(elf_sizes.get('code', 0)):>10}")
        sec_lines.append(f"    └─ ROM 数据:  {_format_bytes(elf_sizes.get('romdata', 0)):>10}")
        sec_lines.append(f"  {'RAM 总计:':<20} {_format_bytes(elf_sizes.get('ram_total', 0)):>10}")
    else:
        sec_lines.append(f"  (elfsize 分析失败: {elf_err})")
    report.add_section("[9] ELF 尺寸 (elfsize)", sec_lines)

    # ================================================================
    #  10. 栈溢出风险评估
    # ================================================================
    sec_lines = []
    risks = []

    # 使用链接器估算
    for u in usages:
        stack_name = u["stack"]
        used = u["used"]
        stack_config = next((s for s in stacks if s["name"] == stack_name), None)
        if stack_config and stack_config["size"] > 0:
            usage_pct = (used / stack_config["size"]) * 100
            if usage_pct >= 80:
                risks.append(f"  [严重] {stack_name}: 已使用 {usage_pct:.0f}% "
                             f"({_format_bytes(used)} / {_format_bytes(stack_config['size'])})")
            elif usage_pct >= 50:
                risks.append(f"  [警告] {stack_name}: 已使用 {usage_pct:.0f}% "
                             f"({_format_bytes(used)} / {_format_bytes(stack_config['size'])})")
            else:
                sec_lines.append(f"  [正常] {stack_name}: 已使用 {usage_pct:.0f}% "
                                 f"({_format_bytes(used)} / {_format_bytes(stack_config['size'])})")

    # 使用 ADX 调用链深度
    if adx_available and stack_depth:
        for stack in stacks:
            # 找到入口点中栈深度最大的路径
            max_depth = 0
            max_func = ""
            for func, info in stack_depth.items():
                if info["depth"] > max_depth:
                    max_depth = info["depth"]
                    max_func = func

            if max_depth > 0 and stack["size"] > 0:
                depth_pct = (max_depth / stack["size"]) * 100
                if depth_pct >= 80:
                    risks.append(f"  [严重] {stack['name']}: 调用链最大栈深度 {depth_pct:.0f}% "
                                 f"({_format_bytes(max_depth)} / {_format_bytes(stack['size'])}), "
                                 f"函数: {max_func}")
                elif depth_pct >= 50:
                    risks.append(f"  [警告] {stack['name']}: 调用链最大栈深度 {depth_pct:.0f}% "
                                 f"({_format_bytes(max_depth)} / {_format_bytes(stack['size'])}), "
                                 f"函数: {max_func}")

    # 检查递归
    for u in usages:
        if u["recursive"].lower() == "yes":
            risks.append(f"  [警告] {u['stack']}: 检测到递归调用, 栈使用可能超出静态估算")

    if risks:
        sec_lines.append("  ⚠ 风险项:")
        for r in risks:
            sec_lines.append(r)
    else:
        if not sec_lines:
            sec_lines.append("  (栈使用率低于 50%, 当前风险较低)")
    report.add_section("[10] 栈溢出风险评估", sec_lines)

    # ================================================================
    #  11. 建议与注意事项
    # ================================================================
    sec_lines = []
    sec_lines.append("  [静态分析的局限性]")
    sec_lines.append("  • 链接器静态估算仅覆盖静态可达路径")
    sec_lines.append("  • 不包含以下场景:")
    sec_lines.append("    - 函数指针 / 虚函数调用链")
    sec_lines.append("    - 中断嵌套 (ISR 内调用函数)")
    sec_lines.append("    - 递归函数 (实际栈使用可能 > 估算)")
    sec_lines.append("")
    sec_lines.append("  [安全建议]")
    sec_lines.append("  • 建议留出 30-50% 的栈空间余量")
    sec_lines.append("  • 对于栈使用率超过 50% 的情况, 建议增加栈空间或优化代码")
    sec_lines.append("")
    sec_lines.append("  [深入分析手段]")
    sec_lines.append("  • 代码审查: 检查大局部变量 / 深层调用链")
    sec_lines.append("  • 运行时监控: 在任务入口/出口填充栈哨兵 (0xDEAD), 运行时检测最大使用深度")
    sec_lines.append("  • 硬件 MPU 保护: 配置 MPU 保护栈溢出, 触发 Trap 后定位")
    sec_lines.append("  • 使用 TASKING 的 --stack-usage 编译选项生成 .sa 文件, 获取更详细的栈分析")
    report.add_section("[11] 建议与注意事项", sec_lines)

    # ================================================================
    #  输出
    # ================================================================
    report_path = report.save()
    report.print_console()
    print(f"\n  报告已保存: {report_path}", flush=True)

    return True


def _print_call_tree(root, call_graph, funcs, sec_lines, indent=2, max_depth=5, visited=None):
    """递归打印调用树。"""
    if visited is None:
        visited = set()
    if root in visited or max_depth <= 0:
        return
    visited.add(root)

    callee_names = [callee for caller, callee in call_graph if caller == root]
    for callee in sorted(set(callee_names)):
        if callee not in funcs:
            continue
        stack_info = ""
        sc = funcs[callee].get("stack_consumption")
        if sc is not None and sc > 0:
            stack_info = f" [栈:{sc}B]"
        sec_lines.append(f"  {' ' * indent}-> {callee}{stack_info}")
        _print_call_tree(callee, call_graph, funcs, sec_lines,
                         indent + 2, max_depth - 1, visited)


# ===========================================================================
#  ELF 尺寸分析
# ===========================================================================

class ElfAnalyzer:
    """使用 TASKING 工具链对 ELF 文件进行分析。"""

    def __init__(self, elf_path, elfsize_path):
        self.elf_path = elf_path
        self.elfsize = elfsize_path

    def get_elf_sizes(self):
        """运行 elfsize 获取 ROM/RAM 总大小。"""
        out, err, rc = _run([self.elfsize, self.elf_path])
        if rc != 0:
            return None, err

        result = {}
        m_rom = re.search(r"ROM:\s+0x([0-9a-fA-F]+)\s+\(\d+\)", out)
        m_ram = re.search(r"RAM:\s+0x([0-9a-fA-F]+)\s+\(\d+\)", out)
        m_code = re.search(r"code:\s+0x([0-9a-fA-F]+)\s+\(\d+\)", out)
        m_romdata = re.search(r"romdata:\s+0x([0-9a-fA-F]+)\s+\(\d+\)", out)

        if m_rom:
            result["rom_total"] = int(m_rom.group(1), 16)
        if m_ram:
            result["ram_total"] = int(m_ram.group(1), 16)
        if m_code:
            result["code"] = int(m_code.group(1), 16)
        if m_romdata:
            result["romdata"] = int(m_romdata.group(1), 16)

        return result, None


# ===========================================================================
#  命令行入口
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="TASKING TriCore 栈使用分析工具 - 完整版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
    python tools/stack_analyzer.py --project-dir=. --variant=debug
    python tools/stack_analyzer.py --project-dir=. --variant=release --verbose
    python tools/stack_analyzer.py --project-dir=../MyProject --variant=debug --tasking-bin="D:/TASKING/tricore/ctc/bin"
        """,
    )
    parser.add_argument("--project-dir", default=".",
                        help="项目根目录 (默认: 当前目录)")
    parser.add_argument("--variant", default="debug",
                        choices=["debug", "release"],
                        help="构建变体 (默认: debug)")
    parser.add_argument("--tasking-bin", default=None,
                        help="TASKING 编译器 bin 目录 (默认: 自动检测)")
    parser.add_argument("--output-dir", default=None,
                        help="报告输出目录 (默认: <project-dir>/output)")
    parser.add_argument("--verbose", action="store_true",
                        help="输出详细调试信息")

    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)

    # 自动检测 TASKING 编译器
    tasking_bin = args.tasking_bin
    if not tasking_bin:
        candidates = [
            r"D:\Program Files\TASKING\TriCore v6.3r1\ctc\bin",
            r"C:\Program Files\TASKING\TriCore v6.3r1\ctc\bin",
        ]
        for c in candidates:
            if os.path.isfile(os.path.join(c, "hldumptc.exe")):
                tasking_bin = c
                break
        if not tasking_bin:
            # 自动搜索
            for root in [r"D:\Program Files\TASKING", r"C:\Program Files\TASKING"]:
                if os.path.isdir(root):
                    for entry in os.listdir(root):
                        if entry.lower().startswith("tricore"):
                            bin_dir = os.path.join(root, entry, "ctc", "bin")
                            if os.path.isfile(os.path.join(bin_dir, "hldumptc.exe")):
                                tasking_bin = bin_dir
                                break
    if not tasking_bin:
        print("ERROR: 未找到 TASKING 编译器, 请通过 --tasking-bin 指定", flush=True)
        sys.exit(1)

    output_dir = args.output_dir or os.path.join(project_dir, "output")
    output_dir = os.path.abspath(output_dir)

    success = analyze(
        project_dir=project_dir,
        variant=args.variant,
        tasking_bin_dir=tasking_bin,
        output_dir=output_dir,
        verbose=args.verbose,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()