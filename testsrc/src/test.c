#include "test.h"

VOVAR(int, MYVAR) myglobal1[10];
SVAR(int, MYVAR) myglobal2 = 1;
PVAR(int, MYVAR) myglobal3 = &myglobal1;

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);
    myglobal1[0] = a;
    myglobal1[1] = b;

    SOMERANDOMASMMACRO();

}

int main(){
    printf("hello there\n");
    SOMERANDOMASMMACRO2();

    printf("ive returned\n");

    return 0;
}