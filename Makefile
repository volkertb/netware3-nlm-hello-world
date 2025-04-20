# makefile for "hello world" NLM

CC = gcc
CFLAGS = -m32 -fno-pic -Wall -O2 -g -I/usr/nwsdk/include/ -nostdinc -fno-builtin -fpack-struct

all:		floppy.img

floppy.img: hello.nlm
	dd if=/dev/zero of=floppy.img bs=1440k count=1
	mformat -C -f 1440 -i floppy.img ::
	mcopy -i floppy.img *.nlm ::
	mcopy -i floppy.img /usr/nwsdk/lib/smp/threads.nlm ::
	mdir -i floppy.img ::

hello.nlm:	hello.o hello.def
	nlmconv --output-target=nlm32-i386 -T hello.def

hello.o:	hello.c
	$(CC) $(CFLAGS) -c hello.c

clean:
	rm *.nlm
	rm *.o
	rm *.img
