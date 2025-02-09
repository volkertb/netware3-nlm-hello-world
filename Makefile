# makefile for "hello world" NLM

CC = gcc
CFLAGS = -Wall -O2 -g -I/usr/nwsdk/include/ -nostdinc -fno-builtin -fpack-struct

all:		hello.nlm

hello.nlm:	hello.o hello.def
	nlmconv --output-target=nlm32-i386 -T hello.def

hello.o:	hello.c
	$(CC) $(CFLAGS) -c hello.c

clean:
	rm *.nlm
	rm *.o
