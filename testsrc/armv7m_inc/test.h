#pragma once

#define SOMERANDOMASMMACRO() __asm volatile("pop {r4, pc}")
#define SOMERANDOMASMMACRO2() \
    __asm volatile( \
        "mov 0x234, r11 \n\t" \
        "mov 0x345, r13 \n\t" \
        "mov 0x123, r4 \n\t" \
        "bl _hellothere_hello \n\t" \
        "ldr r0, =_myVectorTable \n\t" \
        "ldr r1, =0xE000ED08 \n\t" \
        "str r0, [r1] \n\t" \
    );
#define TESTASM 1

// test for macro'd variable definitions
#define VOVAR(x, y) volatile x
#define SVAR(x, y) static volatile x
#define VAR(x, y) x
#define PVAR(x, y) volatile x *
#define MYVAR 1

#define NULLPTR (void*)0

#ifdef CVAR
int* myVectorTable[] = {
    NULLPTR,
    NULLPTR,
    NULLPTR,
};

extern void _hellothere_hello(
    SomeType len, 
    void * mydata[],
    int * mydata2);

typedef struct _SomeType {
    int hello;
} SomeType;
#endif