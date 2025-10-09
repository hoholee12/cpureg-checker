#include "test.h"
.extern _myglobal1
.global _hellothere_hello
.global _hellothere
#define customr r10
_hellothere_hello:
#if (TESTASM == 1)
    pushsp r4
    mov r4, r0
    mov 1, r1
    mov     customr, r11
    mov     r12, r13
    ld.w    r1, [r2]
    add     r3, r1, r4
    mul     r5, r3, r6
    sub     r7, r8, r9
    st.w    r5, [r7]
    st.w    r12, [r1]
    br      _jumphere

    add     r2, customr, r11
    ld.w    r14, [r3]
    st.w    r14, [r2]
    mov     r15, r0

    mov     _myglobal1, r1
    mov     _myglobal2, r2

    jr      _hellothere
#endif

_hellothere:
    pushsp r4
    nop
