# 1 "testsrc\\src\\test.c"
# 1 "<built-in>"
# 1 "<command-line>"
# 1 "testsrc\\src\\test.c"
# 1 "testsrc/rh850_inc/test.h" 1
       
# 2 "testsrc\\src\\test.c" 2

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);

    __asm volatile("popsp r4-r4");

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
