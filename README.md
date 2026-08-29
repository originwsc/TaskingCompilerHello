# Hello - TASKING TriCore SCons 构建工程

基于 SCons 的 TASKING TriCore 编译器构建工程，适配大型 AUTOSAR 代码库的 CI/CD 编译。

## 目录结构

```
Hello/
├── SConstruct              # SCons 构建脚本（可复制到其他工程使用）
├── README.md               # 本文件
├── rules.md                # 踩坑记录 / 最佳实践
├── Log/                    # 构建日志
│   └── build_log.txt
├── App/                    # 应用源码目录
│   ├── Hello.c
│   ├── cstart.c
│   └── ...
├── Bsw/                    # BSW 层源码目录
│   ├── cstart_tc1.c
│   └── sync_on_halt.c
├── Linker/
│   └── Hello.lsl           # 链接器脚本
├── build/                  # 编译中间产物（自动生成）
│   └── tasking/
│       ├── debug/          # Debug 构建产物
│       │   ├── Hello.elf / .hex / .map
│       │   ├── App/        # 镜像 App 目录结构
│       │   │   └── *.obj
│       │   └── Bsw/        # 镜像 Bsw 目录结构
│       │       └── *.obj
│       └── release/        # Release 构建产物
└── output/                 # 最终输出产物（自动生成）
    ├── Hello.elf
    ├── Hello.hex
    └── Hello.map
```

## 前置条件

- Python 3.9+
- SCons 4.x
- TASKING VX-toolset for TriCore v6.3r1（商业版）
  - 安装路径: `D:\Program Files\TASKING\TriCore v6.3r1\ctc\bin`

## 快速开始

```bash
# Debug 构建（默认）
scons variant=debug

# Release 构建
scons variant=release

# 并行编译（4 核）
scons -j4

# 清理构建产物
scons -c
```

## CI/CD 集成

```bash
# 设置编译器路径（环境变量方式）
set TASKING_BIN_DIR=D:\Program Files\TASKING\TriCore v6.3r1\ctc\bin

# 执行构建
scons variant=release -j4

# 检查退出码
echo Exit code: %ERRORLEVEL%
```

## 移植到新工程

将 `Hello` 目录整体复制，修改 `SConstruct` 中的以下变量：

```python
PROJECT_NAME = 'YourProject'                    # 输出文件名（行 92）
TARGET_CHIP  = 'tc36x'                          # 目标芯片型号（行 93）
SOURCE_DIRS  = [r'App', r'Bsw', r'Rte']        # 源码目录列表（行 101）
LSL_FILE     = os.path.join(PROJECT_DIR, 'Linker', 'YourProject.lsl')  # 链接脚本（行 129）
```

> - `INCLUDE_DIRS` 自动从 `SOURCE_DIRS` 派生，无需重复维护
> - 产物路径（`output/`、`build/`）基于 `SConstruct` 所在目录自动生成，**无需修改**
> - 构建信息 banner 中显示的 项目名称 / 目标芯片 / 源文件数 / 路径 等均使用变量，自动跟随上述配置

## 构建产物说明

| 产物 | 路径 | 说明 |
|------|------|------|
| `*.elf` | `output/` | 可执行文件（调试/烧录） |
| `*.hex` | `output/` | Intel HEX 格式（烧录） |
| `*.map` | `output/` | 链接映射文件（内存布局分析） |
| `*.obj` | `build/tasking/<variant>/<dir>/` | 编译中间文件（按源码目录结构镜像） |

## 编译器选项说明

| 选项 | Debug | Release | 说明 |
|------|-------|---------|------|
| 优化等级 | `-O0`（无优化） | `-O2`（高级优化） | 在 `CCFLAGS_DEBUG` / `CCFLAGS_RELEASE` 中修改 |
| 调试信息 | `-g` | 无 | 生成 DWARF 调试符号 |
| 目标芯片 | `-Ctc36x` | `-Ctc36x` | 在 `TARGET_CHIP` 中修改 |
| C 标准 | `--iso=99` | `--iso=99` | C99 标准 |
| 浮点模型 | `--fp-model=3` | `--fp-model=3` | 快速单精度 |

## 构建信息说明

执行 `scons` 时，会自动打印以下信息（**全部动态生成，随配置变化**）：

```
============================================================
  TASKING TriCore SCons Build System
============================================================

  [项目]
    名称:        Hello                ← 来自 PROJECT_NAME
    目标芯片:    tc36x                ← 来自 TARGET_CHIP
    构建变体:    debug                ← 来自 variant 参数
    源文件数:    4                    ← 自动统计

  [编译器]
    路径:        D:\...\ctc\bin       ← 自动检测

  [目录结构]
    SConstruct:  E:\...\SConstruct    ← 当前路径
    中间文件:    E:\...\build\...\    ← 来自 BUILD_DIR
    最终输出:    E:\...\output\       ← 来自 OUTPUT_DIR

  [产物]
    ELF:         E:\...\output\Hello.elf   ← 来自 PROJECT_NAME
    HEX:         E:\...\output\Hello.hex
    MAP:         E:\...\output\Hello.map
```

复制到新工程后，只需修改 `PROJECT_NAME` / `TARGET_CHIP` / `SOURCE_DIRS` / `LSL_FILE`，banner 信息会自动更新。

## 参考

- [rules.md](rules.md) - 构建踩坑记录与最佳实践
- [SCons 官方文档](https://scons.org/documentation.html)
- [TASKING VX-toolset for TriCore 用户指南](https://www.tasking.com/support/tricore/)