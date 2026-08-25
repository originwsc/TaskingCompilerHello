# -*- coding: utf-8 -*-
# SCons build script for Infineon AURIX TC3xx (TriCore) project
# Based on AURIX Studio IDE's TASKING compiler invocation

import os
import sys

# ---------------------------------------------------------------------------
# 1. Project configuration
# ---------------------------------------------------------------------------
PROJECT_NAME = 'hello'
TARGET_CHIP  = 'tc33x'          # Target: TC33x (TASKING format)
OUTPUT_ELF   = 'hello'          # Output ELF name

# Build variant: 'debug' or 'release'
VARIANT = ARGUMENTS.get('variant', 'debug')

# ---------------------------------------------------------------------------
# 1.1 Auto-detect TASKING TriCore compiler (AURIX Studio bundled or standalone commercial)
# ---------------------------------------------------------------------------
def _make_tasking_info(bin_dir):
    """Build TASKING compiler info dict from a bin directory."""
    return {
        'bin_dir': bin_dir,
        'cc': os.path.join(bin_dir, 'cctc.exe'),
        'as': os.path.join(bin_dir, 'astc.exe'),
    }

def detect_tasking_compiler():
    """Auto-detect TASKING TriCore compiler from multiple installation sources.
    Priority: environment variables > standalone install > AURIX Studio bundled.
    """
    # Priority 1: Environment variables (commercial TASKING)
    env_vars = ['TASKING_HOME', 'TASKING_ROOT', 'CTC_BIN', 'TASKING_TOOL_PATH']
    for var in env_vars:
        val = os.environ.get(var)
        if val and os.path.isdir(val):
            # If pointing directly to ctc/bin, use it; otherwise look for ctc/bin underneath
            if os.path.isfile(os.path.join(val, 'cctc.exe')):
                return _make_tasking_info(val)
            bin_candidate = os.path.join(val, 'ctc', 'bin')
            if os.path.isfile(os.path.join(bin_candidate, 'cctc.exe')):
                return _make_tasking_info(bin_candidate)

    # Priority 2: Common standalone TASKING install directories (commercial)
    standalone_roots = [
        'C:\\TASKING',
        'C:\\Program Files\\TASKING',
        'C:\\Program Files (x86)\\TASKING',
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

    # Priority 3: AURIX Studio bundled TASKING
    search_roots = ['D:\\Infineon', 'C:\\Infineon']
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            if entry.startswith('AURIX-Studio'):
                studio_path = os.path.join(root, entry)
                tools_dir = os.path.join(studio_path, 'tools', 'Compilers')
                if not os.path.isdir(tools_dir):
                    continue
                for tasking_dir in os.listdir(tools_dir):
                    if tasking_dir.startswith('Tasking'):
                        bin_dir = os.path.join(tools_dir, tasking_dir, 'ctc', 'bin')
                        if os.path.isfile(os.path.join(bin_dir, 'cctc.exe')):
                            return _make_tasking_info(bin_dir)

    return None

TASKING_INFO = detect_tasking_compiler()

if TASKING_INFO is None:
    print('ERROR: TASKING TriCore compiler not found!')
    print('  Searched locations:')
    print('    1. Environment: TASKING_HOME, TASKING_ROOT, CTC_BIN, TASKING_TOOL_PATH')
    print('    2. Standalone: C:\\TASKING\\TriCore*, C:\\Program Files\\TASKING\\TriCore*')
    print('    3. AURIX Studio: D:\\Infineon\\AURIX-Studio-*\\tools\\Compilers\\Tasking_*')
    print('')
    print('  To use commercial TASKING, set an environment variable, e.g.:')
    print('    set TASKING_HOME=C:\\TASKING\\TriCore v6.3r1')
    print('')
    Exit(1)

# ---------------------------------------------------------------------------
# 2. Paths
# ---------------------------------------------------------------------------
PROJECT_DIR = Dir('.').abspath

# Include directories (from AURIX Studio .cproject)
INCLUDE_DIRS = [
    '.',
    'Configurations',
    'Configurations/Debug',
    'Libraries',
    'Libraries/Infra',
    'Libraries/Infra/Platform',
    'Libraries/Infra/Platform/Tricore',
    'Libraries/Infra/Platform/Tricore/Compilers',
    'Libraries/Infra/Sfr',
    'Libraries/Infra/Sfr/TC33x',
    'Libraries/Infra/Ssw',
    'Libraries/Infra/Ssw/TC3xx',
    'Libraries/Infra/Ssw/TC3xx/Tricore',
    'Libraries/Service',
    'Libraries/Service/CpuGeneric',
    'Libraries/Service/CpuGeneric/If',
    'Libraries/Service/CpuGeneric/If/Ccu6If',
    'Libraries/Service/CpuGeneric/StdIf',
    'Libraries/Service/CpuGeneric/SysSe',
    'Libraries/Service/CpuGeneric/SysSe/Bsp',
    'Libraries/Service/CpuGeneric/SysSe/Comm',
    'Libraries/Service/CpuGeneric/SysSe/General',
    'Libraries/Service/CpuGeneric/SysSe/Math',
    'Libraries/Service/CpuGeneric/SysSe/Time',
    'Libraries/Service/CpuGeneric/_Utilities',
    'Libraries/iLLD',
    'Libraries/iLLD/TC3xx',
    'Libraries/iLLD/TC3xx/Tricore',
]

# Dynamically add all subdirectories under iLLD/TC3xx/Tricore
illd_tricore_dir = os.path.join(PROJECT_DIR, 'Libraries', 'iLLD', 'TC3xx', 'Tricore')
if os.path.isdir(illd_tricore_dir):
    for root, dirs, files in os.walk(illd_tricore_dir):
        rel_path = os.path.relpath(root, PROJECT_DIR)
        INCLUDE_DIRS.append(rel_path.replace('\\', '/'))

# Deduplicate include directories
seen = set()
INCLUDE_DIRS = [d for d in INCLUDE_DIRS if not (d in seen or seen.add(d))]

# ---------------------------------------------------------------------------
# 3. Source files
# ---------------------------------------------------------------------------
def collect_sources(base_dir):
    """Recursively collect all .c files under base_dir."""
    sources = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith('.c'):
                rel_path = os.path.relpath(os.path.join(root, f), PROJECT_DIR)
                sources.append(rel_path)
    return sources

SOURCES = collect_sources(PROJECT_DIR)

# TASKING compiler on Windows uses backslashes; normalize all paths
SOURCES = [s.replace('/', '\\') for s in SOURCES]

# ---------------------------------------------------------------------------
# 4. Generate TASKING-style include path response file
# ---------------------------------------------------------------------------
def generate_task_include_rsp():
    """Generate a TASKING-style response file for include paths.
    TASKING format: all on one line, -I"path" with double backslashes.
    Example: -I"D:\\path\\to\\dir" -I"D:\\path\\to\\dir2"
    """
    rsp_path = os.path.join(PROJECT_DIR, 'include_paths.rsp')
    parts = []
    for inc in INCLUDE_DIRS:
        abs_inc = os.path.join(PROJECT_DIR, inc)
        # TASKING: double backslashes, quoted
        abs_inc = abs_inc.replace('/', '\\')
        parts.append('-I"' + abs_inc + '"')
    with open(rsp_path, 'w', newline='\n') as f:
        f.write(' '.join(parts) + '\n')
    return rsp_path

# ---------------------------------------------------------------------------
# 5. Build environment setup
# ---------------------------------------------------------------------------
env = Environment(ENV=os.environ)

# Embedded cross-compilation: no .exe suffix on Windows
env['PROGSUFFIX'] = '.elf'

# --- TASKING toolchain settings ---
CC   = TASKING_INFO['cc']
AS   = TASKING_INFO['as']
LINK = TASKING_INFO['cc']  # cctc is both compiler and linker driver

env.Replace(CC=CC, AS=AS, LINK=LINK)

# Override default SCons command templates to use TASKING-style flags
# (SCons on Windows defaults to MSVC-style /Fo /nologo)
env['CCCOM'] = '$CC -c -o $TARGET $CCFLAGS $_CPPINCFLAGS $SOURCES'
env['LINKCOM'] = '$LINK -o $TARGET $LINKFLAGS $SOURCES'
env['ASCOM'] = '$AS -o $TARGET $ASFLAGS $SOURCES'

# Remove MSVC-specific flags that SCons adds on Windows
env['CCFLAGS'] = [f for f in env['CCFLAGS'] if f != '/nologo']
env['LINKFLAGS'] = [f for f in env['LINKFLAGS'] if f != '/nologo']

# Generate TASKING include path response file
include_rsp = generate_task_include_rsp()

# --- Compiler flags (matching AURIX Studio IDE) ---
env.Append(CCFLAGS=[
    '-C' + TARGET_CHIP,           # CPU target: tc33x
    '-D__CPU__=' + TARGET_CHIP,   # Chip define
    '--iso=99',                   # C99 standard
    '--language=+volatile',       # Language extensions
    '--exceptions',               # Enable exceptions
    '--anachronisms',             # Allow anachronisms
    '--fp-model=3',               # Floating point model
    '--tradeoff=4',               # Speed vs size tradeoff
    '--compact-max-size=200',     # Compact optimization limit
    '-Y0',                        # No MISRA check
    '-N0',                        # No performance check
    '-Z0',                        # No certification check
    '--error-limit=42',           # Max errors
    '-f', include_rsp,            # Include path response file
])

# Debug / Release variant
if VARIANT == 'debug':
    env.Append(CCFLAGS=['-g', '-O0'])
else:
    env.Append(CCFLAGS=['-O2'])

# Suppress specific warnings (matching IDE)
env.Append(CCFLAGS=[
    '-Wc-w544',
    '-Wc-w557',
    '-Wc-w508',
])

# --- Linker flags (matching AURIX Studio IDE) ---
lsl_path = os.path.join(PROJECT_DIR, 'Lcf_Tasking_Tricore_Tc.lsl')
env.Append(LINKFLAGS=[
    '-C' + TARGET_CHIP,                        # CPU target
    '--lsl-file=' + lsl_path,                  # Linker script
    '--lsl-core=vtc',                          # LSL core
    '-Wl--map-file=' + OUTPUT_ELF + '.map',    # Map file
    '-Wl-Oc', '-Wl-OL', '-Wl-Ot', '-Wl-Ox', '-Wl-Oy',  # Linker optimizations
    '-Wl-mc', '-Wl-mf', '-Wl-mi', '-Wl-mk', '-Wl-ml', '-Wl-mm', '-Wl-md', '-Wl-mr', '-Wl-mu',  # Map file content
    '-Wl--error-limit=42',                     # Max linker errors
    '--fp-model=3',                            # FP model
    '-lrt',                                    # Runtime library
    '--exceptions',                            # Exceptions
    '--strict',                                # Strict mode
    '--anachronisms',                          # Anachronisms
    '--force-c++',                             # Force C++ linkage
])

# Generate HEX file alongside ELF
env.Append(LINKFLAGS=['-Wl-o' + OUTPUT_ELF + '.hex:IHEX'])

# Build output directory
build_dir = os.path.join('build', 'tasking', VARIANT)

# ---------------------------------------------------------------------------
# 6. Compile and link
# ---------------------------------------------------------------------------
# Build the ELF target
elf = env.Program(target=OUTPUT_ELF, source=SOURCES)

# Mark as default target
Default(elf)

# Clean target
env.Clean(elf, [build_dir])

# "all" target
env.Alias('all', [elf])

# ---------------------------------------------------------------------------
# 7. Print build info
# ---------------------------------------------------------------------------
print('')
print('=' * 60)
print('  AURIX TC3xx SCons Build System (TASKING)')
print('=' * 60)
print('  Project:   %s' % PROJECT_NAME)
print('  Variant:   %s' % VARIANT)
print('  Target:    %s' % TARGET_CHIP)
print('  Output:    %s' % OUTPUT_ELF)
print('  Sources:   %d files' % len(SOURCES))
print('  Compiler:  %s' % env['CC'])
print('=' * 60)
print('')