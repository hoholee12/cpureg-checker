#include "test.h"

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);

    SOMERANDOMASMMACRO();

}

int main(){
    printf("hello there\n");
    __asm (
        "mov 0x123,r4"
        "bl _hellothere"
    );

    printf("ive returned\n");

    return 0;
}