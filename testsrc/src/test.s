#include "test.h"
.extern _myglobal1
.global _hellothere_hello
.global _hellothere
.set customr, r10
_hellothere_hello:
.if (TESTASM == 1)
    push {r4, lr}
    mov r4, r0  // to the arg0
    mov 1, r1   // to the arg1
    MOV customr, R11
    MOV R12, R13
    LDR R1, [R2]
    ADD R3, R1, R4
    MUL R5, R3, R6
    SUB R7, R8, R9
    STR R5, [R7]
    STR R12, [R1]
    B _jumphere

    ADD R2, customr, R11
    LDR R14, [R3]
    STR R14, [R2]
    MOV R15, R0

    MOV _myglobal1, R1
    MOV _myglobal2, R2

    B _hellothere
.endif

_hellothere:
    push {r4, lr}
    nop