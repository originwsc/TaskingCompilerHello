# SCons + TASKING TriCore 构建踩坑记录

## 1. 编译器路径含空格（坑: 命令行解析错误）

**现象**: `'D:\Program' 不是内部或外部命令，也不是可运行的程序`

**原因**: Windows 路径 `D:\Program Files\TASKING\...` 含有空格，SCons 拼接命令行时未加引号。

**解决**: 在 `env.Replace()` 中为编译器路径加引号:

```python
env.Replace(
    CC   = '"' + TASKING_INFO['cc'] + '"',
    AS   = '"' + TASKING_INFO['as'] + '"',
    LINK = '"' + TASKING_INFO['cc'] + '"',
    AR   = '"' + TASKING_INFO['ar'] + '"',
)
```

---

## 2. 链接脚本路径解析错误（坑: 相对路径变根目录）

**现象**: `ltc E821: cannot open "\Linker\Hello.lsl"`

**原因**: 使用相对路径 `\Linker\Hello.lsl` 时，开头的 `\` 被 Windows 解析为**驱动器根目录**，而不是当前目录。

**解决**: 永远使用 `os.path.join(PROJECT_DIR, ...)` 生成绝对路径:

```python
# ❌ 错误: 会被解析为 D:\Linker\Hello.lsl
LSL_FILE = r'\Linker\Hello.lsl'

# ✅ 正确: 生成 E:\workspace\scons\Hello\Linker\Hello.lsl
LSL_FILE = os.path.join(PROJECT_DIR, 'Linker', 'Hello.lsl')
```

---

## 3. HEX 文件是链接器的副作用（坑: SCons 找不到 Source）

**现象**: `Source 'Hello.hex' not found, needed by target 'output'`

**原因**: HEX 文件是链接器通过 `-Wl-o` 参数生成的副作用产物，SCons 默认不会跟踪此类产物。

**解决**: 使用 `SideEffect()` 告知 SCons HEX 文件是 ELF 目标的副作用:

```python
hex_path = os.path.join(BUILD_DIR, PROJECT_NAME + '.hex')
hex_target = env.File(hex_path)
env.Append(LINKFLAGS=['-Wl-o' + hex_path + ':IHEX'])
env.SideEffect(hex_target, elf_target)   # 告诉 SCons: hex 是 elf 的副作用
```

---

## 4. 源文件管理（坑: 手动列举不可维护）

**现象**: 每次新增源文件都要修改 SConstruct，十几万个文件不可能手动列举。

**解决**: 使用 Python 的 `glob.glob()` 递归扫描（**不要用 SCons 自带的 `Glob()`**）:

```python
# ❌ 错误: 手动列举，不可维护
SOURCE_FILES = ['App/Hello.c', 'App/cstart.c']

# ❌ 错误: SCons 的 Glob() 不支持 ** 递归
SOURCE_FILES = Glob('App/**/*.c')     # 返回 0 个文件!

# ✅ 正确: 使用 Python 的 glob 模块
import glob as py_glob

SOURCE_DIRS = [r'App']
SOURCE_FILES = []
for d in SOURCE_DIRS:
    for f in py_glob.glob(d.replace('\\', '/') + '/**/*.c', recursive=True):
        SOURCE_FILES.append(File(f))
```

**为什么 SCons 的 `Glob()` 不行？** 在 Windows 上，SCons 的 `Glob()` 函数对 `**` 递归通配符支持有问题，即使传 `App/**/*.c` 也返回空列表。

---

## 5. 产物路径都用 PROJECT_DIR（坑: 路径绑定了项目名）

**现象**: 把 SConstruct 复制到其他工程，产物路径里还带着旧项目名。

**原因**: 使用了 `TOP_DIR = os.path.dirname(PROJECT_DIR)` 或硬编码了项目名在路径中。

**解决**: 所有产物路径都以 `PROJECT_DIR` 为基准，不要引入 `TOP_DIR`:

```python
# ❌ 错误: 产物在 E:\workspace\scons\output\ 和 E:\workspace\scons\build\
TOP_DIR = os.path.dirname(PROJECT_DIR)
BUILD_DIR  = os.path.join(TOP_DIR, 'build', 'tasking', variant_suffix)
OUTPUT_DIR = os.path.join(TOP_DIR, 'output')

# ✅ 正确: 产物在 E:\workspace\scons\Hello\output\ 和 E:\workspace\scons\Hello\build\
#           复制到其他工程时无需修改路径
BUILD_DIR  = os.path.join(PROJECT_DIR, 'build', 'tasking', variant_suffix)
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')
```

---

## 6. obj 文件路径应镜像源文件目录结构（坑: 所有 obj 挤在一起）

**现象**: 多个目录下的同名源文件（如 `App/foo.c` 和 `RTE/foo.c`）的 obj 文件互相覆盖。

**原因**: obj 文件名没有包含源文件的相对路径前缀。

**解决**: 使用 `os.path.relpath()` 保留源文件相对目录结构:

```python
for src in SOURCE_FILES:
    src_path = src.srcnode().abspath
    rel_path = os.path.relpath(src_path, PROJECT_DIR)    # 如 App/Hello.c
    obj_path = os.path.join(BUILD_DIR, rel_path.replace('.c', '.obj'))  # build/tasking/debug/App/Hello.obj
    obj = env.Object(target=obj_path, source=src)
    obj_files.append(obj)
```

---

## 7. 编译器检测优先级（坑: 用了错误的编译器路径）

**现象**: 明明安装了商业版 TASKING，却用了 AURIX Studio 自带的版本。

**原因**: 检测优先级不对，先搜到了 AURIX Studio 的路径。

**解决**: 按优先级: 手动指定 > 环境变量 > 独立安装 > AURIX Studio。并且删除 AURIX Studio 相关检测，因为 SCons 工程和 AURIX 无关。

---

## 8. 文件编码问题（坑: GBK 解码失败）

**现象**: `UnicodeDecodeError: 'gbk' codec can't decode byte 0xaf`

**原因**: 在 Windows 上，不指定编码时 `open()` 默认使用系统编码（GBK），而 SConstruct 文件是 UTF-8 编码。

**解决**: 在文件头部添加 `# -*- coding: utf-8 -*-`，并在 `open()` 时指定 `encoding='utf-8'` 参数。

---

## 快速自查清单

复制 SConstruct 到新工程时，检查以下 4 项:

- [ ] `PROJECT_NAME` 是否改为新项目名?
- [ ] `TARGET_CHIP` 是否匹配目标芯片?
- [ ] `SOURCE_DIRS` 是否包含所有源码目录?
- [ ] `LSL_FILE` 路径是否正确指向新的 `.lsl` 文件?

**产物路径不需要改**，因为所有路径都以 `PROJECT_DIR` 为基准。