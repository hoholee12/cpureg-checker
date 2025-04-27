#include "test.h"

.global _hellothere
_hellothere:
.if (TESTASM == 1)
    pushsp r4-r4
    mov r4, r0  // to the arg0
    mov 1, r1   // to the arg1
    lr _jumphere
.endif