# makefile for "hello world" NLM

CC = gcc
# -fno-asynchronous-unwind-tables: gcc's .eh_frame carries PC-relative relocs the NLM format
# cannot represent (nlmconv rejects them; NetWare never reads .eh_frame anyway).
# -gdwarf-4: i386-netware-ld (binutils 2.30) predates DWARF 5, gcc's default since gcc 11.
CFLAGS = -m32 -fno-pic -fno-asynchronous-unwind-tables -Wall -O2 -gdwarf-4 -I/usr/nwsdk/include/ -nostdinc -fno-builtin -fpack-struct

all:		floppy.img

# Starts the QEMU sidecar VM (idempotent - a no-op if already on) and mounts the built floppy
# image into it, ready for `vmctl type $'LOAD A:HELLOVGA.NLM\n'` - see docs/qemu-vm-debugging.md.
deploy:	floppy.img
	vmctl on
	vmctl floppy load floppy.img

floppy.img: hello.nlm hellovga.nlm
	dd if=/dev/zero of=floppy.img bs=1440k count=1
	mformat -C -f 1440 -i floppy.img ::
	mcopy -i floppy.img *.nlm ::
	mdir -i floppy.img ::

hello.nlm:	hello.o vga_util.o hello.def
	nlmconv --output-target=nlm32-i386 -T hello.def
	verify-nlm hello.nlm hello.def

hellovga.nlm:	hello_vga.o hello_vga_pic.o vga_util.o hello_vga.def
	nlmconv --output-target=nlm32-i386 -T hello_vga.def
	verify-nlm hello_vga.nlm hello_vga.def
	mv hello_vga.nlm hellovga.nlm

hello.o:	hello.c
	sed "s/INSERT_TIMESTAMP_HERE/$$(date)/g" hello.c > hello.tmp.c
	$(CC) $(CFLAGS) -c hello.tmp.c
	mv hello.tmp.o hello.o
	rm hello.tmp.c

hello_vga.o:	hello_vga.c generated/hello_vga_pic.h vga_util.h
	sed "s/INSERT_TIMESTAMP_HERE/$$(date)/g" hello_vga.c > hello_vga.tmp.c
	$(CC) $(CFLAGS) -c hello_vga.tmp.c
	mv hello_vga.tmp.o hello_vga.o
	rm hello_vga.tmp.c

# Generated from the source asset at build time, not committed (see .gitignore) - regenerate
# instead of hand-editing if the picture ever changes.
generated:
	mkdir -p generated

generated/hello_vga_pic.c generated/hello_vga_pic.h:	pics/yes_netware_320x200.png pcx_to_c.py | generated
	gm convert -compress RLE pics/yes_netware_320x200.png generated/yes_netware_320x200.pcx
	python3 pcx_to_c.py generated/yes_netware_320x200.pcx generated/hello_vga_pic.c generated/hello_vga_pic.h

hello_vga_pic.o:	generated/hello_vga_pic.c
	$(CC) $(CFLAGS) -c generated/hello_vga_pic.c -o hello_vga_pic.o

vga_util.o:	vga_util.c
	$(CC) $(CFLAGS) -c vga_util.c

clean:
	rm -f *.nlm
	rm -f *.o
	rm -f *.img
	rm -f *.tmp.c
	rm -rf generated
