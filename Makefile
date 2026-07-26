# makefile for "hello world" NLM

DUNE0_ADL_URL = https://github.com/katlogic/dunelegacy/raw/refs/heads/master/data/DUNE0.ADL
DUNE0_ADL_SHA256 = 674965c1a896617cca3d7cca5b69c7b9a2c93ced66db8f1f8df798f44aeb64e4

CC = gcc
# -fno-asynchronous-unwind-tables: gcc's .eh_frame carries PC-relative relocs the NLM format
# cannot represent (nlmconv rejects them; NetWare never reads .eh_frame anyway).
# -gdwarf-4: i386-netware-ld (binutils 2.30) predates DWARF 5, gcc's default since gcc 11.
CFLAGS = -m32 -fno-pic -fno-asynchronous-unwind-tables -Wall -Wextra -O2 -gdwarf-4 -I/usr/nwsdk/include/ -nostdinc -fno-builtin -fpack-struct

# This project's own hand-written/adapted C sources - not modes.c, which stays untouched to
# preserve diffability against its public-domain upstream (see AGENTS.md), and not the generated/
# or .devcontainer/ trees, which aren't this project's own code to lint or reformat either.
LINT_SOURCES = hello.c hello_vga.c vga_util.c vga_util.h adlib_util.c adlib_util.h \
	implicit_nlm_defs.h nlm_io_wrapper.c nlm_io_wrapper.h vgamode.c vgamode.h modes.h

all:		floppy.img

# __GNUC__/__i386__ match gcc -m32's own predefined macros (see CFLAGS) - cppcheck's bundled
# preprocessor needs them explicitly to pick the right branch of NDK headers like stdarg.h.
.PHONY: lint
lint:
	cppcheck --enable=warning,style,performance,portability --check-level=exhaustive \
		--error-exitcode=1 -I/usr/nwsdk/include/ -DN_PLAT_NLM -D__GNUC__ -D__i386__ $(LINT_SOURCES)
	flawfinder --error-level=2 $(LINT_SOURCES)
	clang-tidy --checks='bugprone-*' --warnings-as-errors='*' $(LINT_SOURCES) -- \
		-m32 -nostdinc -fno-builtin -fpack-struct -I/usr/nwsdk/include/

.PHONY: format format-check
format:
	clang-format -i $(LINT_SOURCES)

format-check:
	clang-format --dry-run --Werror $(LINT_SOURCES)

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

hellovga.nlm:	hello_vga.o hello_vga_pic.o vga_util.o dune0_song4.o adlib_util.o vgamode.o modes.o nlm_io_wrapper.o hello_vga.def
	nlmconv --output-target=nlm32-i386 -T hello_vga.def
	verify-nlm hello_vga.nlm hello_vga.def
	mv hello_vga.nlm hellovga.nlm

hello.o:	hello.c
	sed "s/INSERT_TIMESTAMP_HERE/$$(date)/g" hello.c > hello.tmp.c
	$(CC) $(CFLAGS) -c hello.tmp.c
	mv hello.tmp.o hello.o
	rm hello.tmp.c

hello_vga.o:	hello_vga.c generated/hello_vga_pic.h vga_util.h generated/dune0_song4.h adlib_util.h vgamode.h modes.h
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

# DUNE0.ADL is Westwood's copyrighted game data (see LICENSE.md), fetched here rather than
# committed to the repo - checksummed the same way the Dockerfile checksums its own downloads.
# The .PHONY check runs on every build (cheap - just a checksum of a 14KB file) so a corrupted or
# tampered downloads/DUNE0.ADL is caught immediately rather than silently miscompiled; downloads/ is
# gitignored and deliberately untouched by `make clean` so the download isn't repeated needlessly.
.PHONY: check-dune0-adl
check-dune0-adl:
	mkdir -p downloads
	if [ -f downloads/DUNE0.ADL ]; then \
		echo "$(DUNE0_ADL_SHA256)  downloads/DUNE0.ADL" | sha256sum --status -c - || { \
			echo "error: downloads/DUNE0.ADL does not match the expected SHA256 ($(DUNE0_ADL_SHA256))." >&2; \
			echo "Delete downloads/DUNE0.ADL and re-run make to re-download it." >&2; \
			exit 1; \
		}; \
	else \
		curl -sL -o downloads/DUNE0.ADL $(DUNE0_ADL_URL); \
		echo "$(DUNE0_ADL_SHA256)  downloads/DUNE0.ADL" | sha256sum -c -; \
	fi

downloads/DUNE0.ADL:	check-dune0-adl
	@:

# adl_to_c.py decodes the whole ADL file (every subsong) and emits one .c/.h pair per subsong
# plus a manifest (dune0_songs.*) - only subsong 4 (a short intro jingle; subsongs 0/1 are silent
# system triggers and subsong 2 is a ~148s full theme, too long for this NLM) actually gets
# compiled into the NLM below.
generated/dune0_songs.c generated/dune0_songs.h generated/opl2_event.h generated/dune0_song4.c generated/dune0_song4.h:	downloads/DUNE0.ADL music/adl_to_c.py | generated
	python3 music/adl_to_c.py downloads/DUNE0.ADL generated dune0

dune0_song4.o:	generated/dune0_song4.c generated/opl2_event.h
	$(CC) $(CFLAGS) -c generated/dune0_song4.c -o dune0_song4.o

adlib_util.o:	adlib_util.c adlib_util.h generated/opl2_event.h
	$(CC) $(CFLAGS) -c adlib_util.c

vga_util.o:	vga_util.c
	$(CC) $(CFLAGS) -c vga_util.c

vgamode.o:	vgamode.c vgamode.h nlm_io_wrapper.h
	$(CC) $(CFLAGS) -c vgamode.c

modes.o:	modes.c modes.h implicit_nlm_defs.h
	$(CC) $(CFLAGS) -c modes.c

nlm_io_wrapper.o:	nlm_io_wrapper.c nlm_io_wrapper.h implicit_nlm_defs.h
	$(CC) $(CFLAGS) -c nlm_io_wrapper.c

clean:
	rm -f *.nlm
	rm -f *.o
	rm -f *.img
	rm -f *.tmp.c
	rm -rf generated
