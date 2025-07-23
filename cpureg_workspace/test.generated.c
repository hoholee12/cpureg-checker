# 1 "testsrc/rh850_inc/test.h" 1
       

volatile int hello[10];
static volatile int world = 1;
volatile int * pointer_to_hello = &hello;

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);
    hello[0] = a;
    hello[1] = b;

    __asm volatile("popsp r4-r4");

}

int main(){
    printf("hello there\n");
    __asm volatile( "mov 0x234, r11 \n\t" "mov 0x345, r13 \n\t" "mov 0x123, r4 \n\t" "jr _hellothere_hello \n\t" );;

    printf("ive returned\n");

    return 0;
}
