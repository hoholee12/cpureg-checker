       
.extern _myglobal1
.global _hellothere_hello
.global _hellothere

_hellothere_hello:

    push {r4, lr}
    mov r4, r0
    mov 1, r1
    MOV r10, R11
    MOV R12, R13
    LDR R1, [R2]
    ADD R3, R1, R4
    MUL R5, R3, R6
    SUB R7, R8, R9
    STR R5, [R7]
    STR R12, [R1]
    B _jumphere

    ADD R2, r10, R11
    LDR R14, [R3]
    STR R14, [R2]
    MOV R15, R0

    MOV _myglobal1, R1
    MOV _myglobal2, R2

    B _hellothere


_hellothere:
    push {r4, lr}
    nop
