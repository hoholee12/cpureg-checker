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