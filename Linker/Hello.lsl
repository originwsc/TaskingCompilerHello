// TASKING VX-toolset for TriCore
// Eclipse project linker script file
//
#if defined(__PROC_TC36X__)
#include "tc36x.lsl"
derivative my_tc36x extends tc36x
{
}
#else
#include <cpu.lsl>
#endif
