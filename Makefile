# makefile for "hello world" NLM

CC = gcc
# -fno-asynchronous-unwind-tables: gcc's .eh_frame carries PC-relative relocs the NLM format
# cannot represent (nlmconv rejects them; NetWare never reads .eh_frame anyway).
CFLAGS = -m32 -fno-pic -fno-asynchronous-unwind-tables -Wall -O2 -g -I/usr/nwsdk/include/ -nostdinc -fno-builtin -fpack-struct

all:		floppy.img

floppy.img: hello.nlm helloold.nlm
	dd if=/dev/zero of=floppy.img bs=1440k count=1
	mformat -C -f 1440 -i floppy.img ::
	mcopy -i floppy.img *.nlm ::
	mdir -i floppy.img ::

hello.nlm:	hello.o vga_util.o hello.def
	nlmconv --output-target=nlm32-i386 -T hello.def
	verify-nlm hello.nlm hello.def

helloold.nlm:	hello_old.o hello_old.def
	nlmconv --output-target=nlm32-i386 -T hello_old.def
	verify-nlm hello_old.nlm hello_old.def
	mv hello_old.nlm helloold.nlm

hello.o:	hello.c
	sed "s/INSERT_TIMESTAMP_HERE/$$(date)/g" hello.c > hello.tmp.c
	$(CC) $(CFLAGS) -c hello.tmp.c
	mv hello.tmp.o hello.o
	rm hello.tmp.c

hello_old.o:	hello_old.c
	sed "s/INSERT_TIMESTAMP_HERE/$$(date)/g" hello_old.c > hello_old.tmp.c
	$(CC) $(CFLAGS) -c hello_old.tmp.c
	mv hello_old.tmp.o hello_old.o
	rm hello_old.tmp.c

vga_util.o:	vga_util.c
	$(CC) $(CFLAGS) -c vga_util.c

clean:
	rm -f *.nlm
	rm -f *.o
	rm -f *.img
	rm -f *.tmp.c

