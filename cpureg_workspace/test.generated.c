       
extern void _hellothere_hello(
    int len,
    void * mydata[],
    int * mydata2);

volatile int myglobal1[10];
volatile int myglobal123[10];
static volatile int myglobal2 = 1;
volatile int * myglobal3 = &myglobal1;

void jumphere(int a,
    int b);
int jumpthere(void);
int testhere(void){return 0;}

void jumphere(int a, int b, int myglobal3){
    int myglobal2 = 2;
    printf("a = %d, b = %d, c = %d\n", a, b, myglobal3);
    myglobal123[0] = a;
    myglobal123[1] = b;

    __asm volatile("pop {r4, pc}");
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
    __asm volatile( "mov 0x234, r11 \n\t" "mov 0x345, r13 \n\t" "mov 0x123, r4 \n\t" "bl _hellothere_hello \n\t" );;

    printf("ive returned\n");

    return 0;
}
