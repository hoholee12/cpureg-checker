#include "test.h"

.global _hellothere
_hellothere:
    push {r4, lr}
    mov r4, r0  -- to the arg0
    mov 1, r1   -- to the arg1
    b _jumphere