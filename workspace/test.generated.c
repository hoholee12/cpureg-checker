# 0 "testsrc/src/test.c"
# 0 "<built-in>"
# 0 "<command-line>"
# 1 "testsrc/src/test.c"
# 1 "testsrc/inc/test.h" 1
       
# 2 "testsrc/src/test.c" 2

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);

    __asm volatile("pop {r4, pc}");;

}

int main(){
    printf("hello there\n");
    __asm volatile (
        "mov 0x123,r4"
        "bl _hellothere"
    );

    printf("ive returned\n");

    return 0;
}
