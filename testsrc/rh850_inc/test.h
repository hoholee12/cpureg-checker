#pragma once

#define SOMERANDOMASMMACRO() __asm volatile("popsp r4-r4")
#define SOMERANDOMASMMACRO2() \
    __asm volatile( \
        "mov 0x234, r11 \n\t" \
        "mov 0x345, r13 \n\t" \
        "mov 0x123, r4 \n\t" \
        "jr _hellothere_hello \n\t" \
    );
#define TESTASM 1

// test for macro'd variable definitions
#define VOVAR(x, y) volatile x
#define SVAR(x, y) static volatile x
#define VAR(x, y) x
#define PVAR(x, y) volatile x *
#define MYVAR 1

extern void _hellothere_hello(
    SomeType len, 
    void * mydata[],
    int * mydata2);

typedef struct _SomeType {
    int hello;
} SomeType;