#pragma once

#define SOMERANDOMASMMACRO() __asm volatile("pop {r4, pc}")
#define SOMERANDOMASMMACRO2() \
    __asm volatile( \
        "mov 0x234, r11 \n\t" \
        "mov 0x345, r13 \n\t" \
        "mov 0x123, r4 \n\t" \
        "bl _hellothere \n\t" \
    );
#define TESTASM 1