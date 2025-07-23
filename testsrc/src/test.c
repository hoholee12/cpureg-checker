#include "test.h"

VOVAR(int, MYVAR) hello[10];
SVAR(int, MYVAR) world = 1;
PVAR(int, MYVAR) pointer_to_hello = &hello;

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);
    hello[0] = a;
    hello[1] = b;

    SOMERANDOMASMMACRO();

}

int main(){
    printf("hello there\n");
    SOMERANDOMASMMACRO2();

    printf("ive returned\n");

    return 0;
}