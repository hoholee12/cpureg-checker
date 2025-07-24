# 1 "testsrc/rh850_inc/test.h" 1
       

volatile int myglobal1[10];
static volatile int myglobal2 = 1;
volatile int * myglobal3 = &myglobal1;

void jumphere(int a, int b){
    printf("a = %d, b = %d\n", a, b);
    myglobal1[0] = a;
    myglobal1[1] = b;

    __asm volatile("popsp r4-r4");
    jumpthere();

}
int jumpthere(void)
{
    printf("jumping there\n");
    return 0;
}

int main(){
    printf("hello there\n");
    __asm volatile( "mov 0x234, r11 \n\t" "mov 0x345, r13 \n\t" "mov 0x123, r4 \n\t" "jr _hellothere_hello \n\t" );;

    printf("ive returned\n");

    return 0;
}
