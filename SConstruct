# -*- coding: utf-8 -*-
"""
SCons build script for TASKING TriCore project.
====================================================================

适配大型 AUTOSAR 代码库的 CI/CD 编译环境。
- 编译器: TASKING VX-toolset for TriCore (商业版)
- 所有产物路径均以 SConstruct 所在目录为基准
- 配置项见下方 PROJECT_NAME / TARGET_CHIP / SOURCE_DIRS 等变量

用法:
    scons variant=debug          # Debug 构建 (默认)
    scons variant=release        # Release 构建
    scons -c                     # 清理
    scons -j4                    # 并行编译

CI/CD 示例:
    set TASKING_BIN_DIR=D:\Program Files\TASKING\TriCore v6.3r1\ctc\bin
    scons variant=release -j4
    echo Exit code: %ERRORLEVEL%
"""

import os
import sys
import shutil
import glob as py_glob

# ===========================================================================
#  0. 环境检测与辅助函数
# ===========================================================================

def _make_tasking_info(bin_dir):
    return {
        'bin_dir': bin_dir,
        'cc':  os.path.join(bin_dir, 'cctc.exe'),
        'as':  os.path.join(bin_dir, 'astc.exe'),
        'ar':  os.path.join(bin_dir, 'artc.exe'),
    }

def detect_tasking_compiler():
    manual_bin = COMPILER_BIN_DIR
    if manual_bin and os.path.isdir(manual_bin) and os.path.isfile(os.path.join(manual_bin, 'cctc.exe')):
        return _make_tasking_info(manual_bin)

    env_bin = os.environ.get('TASKING_BIN_DIR')
    if env_bin and os.path.isdir(env_bin) and os.path.isfile(os.path.join(env_bin, 'cctc.exe')):
        return _make_tasking_info(env_bin)

    env_vars = ['TASKING_HOME', 'TASKING_ROOT', 'CTC_BIN']
    for var in env_vars:
        val = os.environ.get(var)
        if val and os.path.isdir(val):
            if os.path.isfile(os.path.join(val, 'cctc.exe')):
                return _make_tasking_info(val)
            bin_candidate = os.path.join(val, 'ctc', 'bin')
            if os.path.isfile(os.path.join(bin_candidate, 'cctc.exe')):
                return _make_tasking_info(bin_candidate)

    standalone_roots = [
        'D:\\Program Files\\TASKING',
        'C:\\Program Files\\TASKING',
        'C:\\Program Files (x86)\\TASKING',
        'C:\\TASKING',
        'D:\\TASKING',
    ]
    for root in standalone_roots:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            if entry.lower().startswith('tricore'):
                bin_dir = os.path.join(root, entry, 'ctc', 'bin')
                if os.path.isfile(os.path.join(bin_dir, 'cctc.exe')):
                    return _make_tasking_info(bin_dir)

    return None

# ===========================================================================
#  1. 项目配置
# ===========================================================================

# --- 1.0 编译器路径 ---
COMPILER_BIN_DIR = r'D:\Program Files\TASKING\TriCore v6.3r1\ctc\bin'

# --- 1.1 项目基本信息 ---
# ★ SConstruct 所在目录, 所有产物路径均以此为基准
# ★ 不要使用任何与项目名绑定的路径, 以便直接复制到其他工程使用
PROJECT_DIR  = Dir('.').abspath

PROJECT_NAME = 'Hello'                     # 输出文件名
TARGET_CHIP  = 'tc36x'                     # 目标芯片
VARIANT      = ARGUMENTS.get('variant', 'debug')  # 构建变体

# 构建目录 (提前定义, 供链接器标志使用)
BUILD_DIR = os.path.join(PROJECT_DIR, 'build', 'tasking', VARIANT)

# --- 1.2 源文件 (Glob 自动递归发现, 无需手动列举) ---
# 只需指定源码根目录, SCons 自动递归扫描所有 .c 文件
# 新增目录直接往 SOURCE_DIRS 里添加即可
SOURCE_DIRS = [
    r'App',
    r'Bsw',
]

# 需要排除的源文件 (可选, 匹配路径末尾)
SOURCE_EXCLUDE_PATTERNS = []

# 使用 Python glob 递归扫描所有 .c 文件 (SCons Glob 不支持 ** 递归)
SOURCE_FILES = []
for d in SOURCE_DIRS:
    for f in py_glob.glob(d.replace('\\', '/') + '/**/*.c', recursive=True):
        SOURCE_FILES.append(File(f))

# 排除规则
if SOURCE_EXCLUDE_PATTERNS:
    SOURCE_FILES = [
        f for f in SOURCE_FILES
        if not any(p in f.srcnode().abspath for p in SOURCE_EXCLUDE_PATTERNS)
    ]

# --- 1.3 头文件搜索路径 ---
# ★ 自动从 SOURCE_DIRS 派生, 无需重复维护
# ★ 如果某个头文件目录内没有 .c 文件, 手动追加即可
INCLUDE_DIRS = ['.'] + [d for d in SOURCE_DIRS]

# --- 1.4 链接脚本 ---
LSL_FILE = os.path.join(PROJECT_DIR, 'Linker', 'Hello.lsl')

# --- 1.5 预处理器宏定义 ---
CPPDEFINES = [
    ('__CPU__', TARGET_CHIP),
]

# ===========================================================================
#  2. 编译器标志
# ===========================================================================

CCFLAGS_COMMON = [
    '-C' + TARGET_CHIP,
    '--iso=99',
    '--language=+volatile',
    '--exceptions',
    '--anachronisms',
    '--fp-model=3',
    '--tradeoff=4',
    '--compact-max-size=200',
    '-Y0', '-N0', '-Z0',
    '--error-limit=42',
    '-Wc-w544', '-Wc-w557', '-Wc-w508',
]

CCFLAGS_DEBUG = ['-g', '-O0']
CCFLAGS_RELEASE = ['-O2']

ASFLAGS = ['-C' + TARGET_CHIP, '-g']

# ===========================================================================
#  3. 链接器标志
# ===========================================================================

LINKFLAGS = [
    '-C' + TARGET_CHIP,
    '--lsl-file=' + LSL_FILE,
    '--lsl-core=vtc',
    '-Wl--map-file=' + os.path.join(BUILD_DIR, PROJECT_NAME + '.map'),
    '-Wl-Oc', '-Wl-OL', '-Wl-Ot', '-Wl-Ox', '-Wl-Oy',
    '-Wl-mc', '-Wl-mf', '-Wl-mi', '-Wl-mk', '-Wl-ml',
    '-Wl-mm', '-Wl-md', '-Wl-mr', '-Wl-mu',
    '--fp-model=3', '-lrt',
    '--exceptions', '--strict', '--anachronisms', '--force-c++',
    '--error-limit=42',
]

# ===========================================================================
#  4. 编译器自动检测
# ===========================================================================

TASKING_INFO = detect_tasking_compiler()

if TASKING_INFO is None:
    print('')
    print('=' * 60)
    print('  ERROR: TASKING TriCore compiler not found!')
    print('=' * 60)
    print('  To fix: set TASKING_BIN_DIR=D:\\Program Files\\TASKING\\TriCore v6.3r1\\ctc\\bin')
    print('')
    Exit(1)

# ===========================================================================
#  5. SCons 环境配置
# ===========================================================================

env = Environment(ENV=os.environ)

env.Replace(
    CC   = '"' + TASKING_INFO['cc'] + '"',
    AS   = '"' + TASKING_INFO['as'] + '"',
    LINK = '"' + TASKING_INFO['cc'] + '"',
    AR   = '"' + TASKING_INFO['ar'] + '"',
)

env['PROGSUFFIX'] = '.elf'
env['CCCOM']     = '$CC -c -o $TARGET $CCFLAGS $_CPPINCFLAGS $SOURCES'
env['LINKCOM']   = '$LINK -o $TARGET $LINKFLAGS $SOURCES'
env['ASCOM']     = '$AS -o $TARGET $ASFLAGS $SOURCES'
env['ARCOM']     = '$AR -r -o $TARGET $SOURCES'

env['CCFLAGS']   = [f for f in env['CCFLAGS']   if f not in ('/nologo',)]
env['LINKFLAGS'] = [f for f in env['LINKFLAGS'] if f not in ('/nologo',)]
env['ASFLAGS']   = []

env['INCPREFIX']  = '-I'
env['INCSUFFIX']  = ''
env['_CPPINCFLAGS'] = '$( ${_concat(INCPREFIX, CPPPATH, INCSUFFIX, __env__, RDirs, TARGET, SOURCE)} $)'

# ===========================================================================
#  6. 构建变体配置
# ===========================================================================

if VARIANT == 'debug':
    variant_flags = CCFLAGS_DEBUG
    variant_suffix = 'debug'
elif VARIANT == 'release':
    variant_flags = CCFLAGS_RELEASE
    variant_suffix = 'release'
else:
    print('ERROR: Unknown variant "%s". Use "debug" or "release".' % VARIANT)
    Exit(1)

env.Append(CCFLAGS=CCFLAGS_COMMON + variant_flags)
env.Append(ASFLAGS=ASFLAGS)
env.Append(LINKFLAGS=LINKFLAGS)
env.Append(CPPDEFINES=CPPDEFINES)

for inc_dir in INCLUDE_DIRS:
    abs_inc = os.path.join(PROJECT_DIR, inc_dir)
    if os.path.isdir(abs_inc):
        env.Append(CPPPATH=[abs_inc])

# ===========================================================================
#  7. 构建目标
# ===========================================================================

# 编译 .c -> .obj (镜像源文件目录结构)
obj_files = []
for src in SOURCE_FILES:
    src_path = src.srcnode().abspath
    rel_path = os.path.relpath(src_path, PROJECT_DIR)
    obj_path = os.path.join(BUILD_DIR, rel_path.replace('.c', '.obj'))
    obj = env.Object(target=obj_path, source=src)
    obj_files.append(obj)

# 链接 ELF
elf_target = env.Program(target=os.path.join(BUILD_DIR, PROJECT_NAME),
                         source=obj_files)

# 生成 HEX
hex_path = os.path.join(BUILD_DIR, PROJECT_NAME + '.hex')
hex_target = env.File(hex_path)
env.Append(LINKFLAGS=['-Wl-o' + hex_path + ':IHEX'])
env.SideEffect(hex_target, elf_target)

# ===========================================================================
#  8. 输出产物到 output/ 目录 (以 SConstruct 所在目录为基准)
# ===========================================================================

OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')

def _copy_to_output_and_analyze(target, source, env):
    """复制产物到 output/ 目录, 并运行栈使用分析工具。"""
    src_dir = BUILD_DIR
    dst_dir = OUTPUT_DIR
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    artifacts = [
        (PROJECT_NAME + '.elf', PROJECT_NAME + '.elf'),
        (PROJECT_NAME + '.hex', PROJECT_NAME + '.hex'),
        (PROJECT_NAME + '.map', PROJECT_NAME + '.map'),
    ]
    copied = []
    for src_name, dst_name in artifacts:
        src_path = os.path.join(src_dir, src_name)
        dst_path = os.path.join(dst_dir, dst_name)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)
            copied.append(dst_name)
    print('')
    print('  [Output] 产物已复制到: %s' % dst_dir)
    for name in copied:
        print('           - %s' % name)
    print('')

    # ---- 运行栈使用分析工具 ----
    analyzer_script = os.path.join(PROJECT_DIR, 'tools', 'stack_analyzer.py')
    if not os.path.isfile(analyzer_script):
        print('  [Stack] 警告: 栈分析工具未找到: %s' % analyzer_script)
        return
    print('  [Stack] 正在生成栈使用分析报告...')
    import subprocess
    py_exe = sys.executable if hasattr(sys, 'executable') else 'python'
    ret = subprocess.run(
        [py_exe, analyzer_script,
         '--project-dir=' + PROJECT_DIR,
         '--variant=' + VARIANT,
         '--tasking-bin=' + TASKING_INFO['bin_dir'],
         '--output-dir=' + OUTPUT_DIR],
        cwd=PROJECT_DIR,
        capture_output=False,
        text=False,
    )
    if ret.returncode != 0:
        print('  [Stack] 警告: 栈分析工具返回错误码 %d' % ret.returncode)
    print('')

output_stamp = env.Command(
    target=os.path.join(OUTPUT_DIR, '.output_stamp'),
    source=elf_target,
    action=_copy_to_output_and_analyze,
)
env.AlwaysBuild(output_stamp)

# ===========================================================================
#  9. 默认目标与别名
# ===========================================================================

env.Default(elf_target, output_stamp)

output_alias = env.Alias('output', [elf_target, output_stamp])
env.AlwaysBuild(output_alias)

env.Clean(elf_target, [BUILD_DIR, OUTPUT_DIR])

# ===========================================================================
#  10. 构建信息打印
# ===========================================================================

print('')
print('=' * 60)
print('  TASKING TriCore SCons Build System')
print('=' * 60)
print('')
print('  [项目]')
print('    名称:        %s' % PROJECT_NAME)
print('    目标芯片:    %s' % TARGET_CHIP)
print('    构建变体:    %s' % VARIANT)
print('    源文件数:    %d' % len(SOURCE_FILES))
print('')
print('  [编译器]')
print('    路径:        %s' % TASKING_INFO['bin_dir'])
print('')
print('  [目录结构]')
print('    SConstruct:  %s\\SConstruct' % PROJECT_DIR)
print('    中间文件:    %s\\' % BUILD_DIR)
print('    最终输出:    %s\\' % OUTPUT_DIR)
print('')
print('  [产物]')
print('    ELF:         %s\\%s.elf' % (OUTPUT_DIR, PROJECT_NAME))
print('    HEX:         %s\\%s.hex' % (OUTPUT_DIR, PROJECT_NAME))
print('    MAP:         %s\\%s.map' % (OUTPUT_DIR, PROJECT_NAME))
print('')
print('  [用法]')
print('    scons variant=debug            # Debug 构建')
print('    scons variant=release          # Release 构建')
print('    scons -c                       # 清理')
print('    scons -j4                      # 4 核并行编译')
print('')
print('=' * 60)
print('')