#include "test.h"

VOVAR(int, MYVAR) myglobal1[10];
VOVAR(int, MYVAR) myglobal123[10];
SVAR(int, MYVAR) myglobal2 = 1;
PVAR(int, MYVAR) myglobal3 = &myglobal1;

void jumphere(int a, 
    int b);
int jumpthere(void);
int testhere(void){return 0;}

void jumphere(int a, int b){
    int myglobal2 = 2; // this must not be picked up as global
    printf("a = %d, b = %d\n", a, b);
    myglobal123[0] = a;
    myglobal123[1] = b;

    SOMERANDOMASMMACRO();
    jumpthere();

}
const int myglobal4[10] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9
};
int jumpthere(void)
{
    printf("jumping there %d\n", myglobal4[3]);
    return 0;
}

int main(){
    printf("hello there\n");
    SOMERANDOMASMMACRO2();

    printf("ive returned\n");

    return 0;
}