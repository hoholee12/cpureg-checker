#include "test.h"

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);

    SOMERANDOMASMMACRO();

}

int main(){
    printf("hello there\n");
    SOMERANDOMASMMACRO2();

    printf("ive returned\n");

    return 0;
}