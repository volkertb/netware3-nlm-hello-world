FROM debian:9.13 AS builder

# Debian 9 (Stretch) is the last Debian release that has a binutils lower than version 2.31, but no nlmconv by default.
# GNU ld (GNU Binutils for Debian) 2.28

ADD --checksum=sha256:6e46b8aeae2f727a36f0bd9505e405768a72218f1796f0d09757d45209871ae6 \
    https://ftp.gnu.org/gnu/binutils/binutils-2.30.tar.xz /Downloads/

ADD --checksum=sha256:4255e7426002007fffc60cb6167230ecbd2207772d54481bbeb9da6ee7005193 \
    https://archive.org/download/novsdkcd-4/NOVSDKCD_4.iso \
    /Downloads/

ADD --checksum=sha256:72cd8a19d06558a0e6704a489c806b9ccb050e59321393f7b6dd11b944f0fdb4 \
    https://web.archive.org/web/20050227034206if_/http://www.penguin.cz:80/~mhi/ftp/nlm/nlm-samples.tar.bz2 \
    /Downloads/

ADD --checksum=sha256:0e407c3f231e5ceb47ca387a7c0e82b64e81620df3871e2110290fb0effa3fe1 \
    https://web.archive.org/web/20050227034206if_/http://www.penguin.cz:80/~mhi/ftp/nlm/nlm-kit-0.1.tar.bz2 \
    /Downloads/

# With thanks to https://unix.stackexchange.com/a/743863
RUN echo "deb http://archive.debian.org/debian stretch main contrib non-free" > /etc/apt/sources.list

RUN apt -y update

RUN apt -y install xz-utils
WORKDIR /Downloads
RUN tar xf binutils-2.30.tar.xz

# Patch error output in nlmconv to help with debugging
WORKDIR /Downloads/binutils-2.30/
RUN ls -lh binutils/nlmconv.c
COPY nlmconv.c binutils/
RUN cat binutils/nlmconv.c | grep stderr

# Comment out a check that causes nlmconv to fail with an Internal Error, apparently unnecessarily:
RUN ls /Downloads/binutils-2.30/bfd/nlm32-i386.c
RUN rm /Downloads/binutils-2.30/bfd/nlm32-i386.c
COPY bfd/nlm32-i386.c /Downloads/binutils-2.30/bfd/
RUN ls /Downloads/binutils-2.30/bfd/nlm32-i386.c

WORKDIR /Downloads/binutils-2.30/
# With thanks to https://soufianebouchaa.medium.com/how-to-compile-binutils-on-ubuntu-debian-ec268674b759
# Also thanks to https://www.experts-exchange.com/questions/20145508/nlmconv-not-working.html (--enable-targets=all)
RUN apt -y install build-essential
# `makeinfo` is apparently needed when any of the binutils sources and/or texi files have been changed:
RUN apt -y install texinfo
# For nlncomv to work properly, we need to fake 32-bit Linux when running configure before building binutils.
RUN linux32 ./configure --prefix=/usr/local --enable-targets=i386-netware --enable-obsolete
RUN make
RUN make install
#RUN man nlmconv
RUN nlmconv --version
RUN ld -v

WORKDIR /Downloads

RUN apt -y install xorriso
RUN xorriso -osirrox on -indev ./NOVSDKCD_4.iso -extract / /Downloads/NOVSDKCD_4
WORKDIR /Downloads/NOVSDKCD_4/FUTURES/NWSDK/NLMNIT
RUN ls -lh
RUN apt -y install zip
RUN zip -r /tmp/ndk.zip .
WORKDIR /usr/nwsdk
# Unpack NDK directories and files in lower case:
RUN unzip -LL /tmp/ndk.zip
RUN ls -lh /usr/nwsdk/include/nwconio.h

WORKDIR /Downloads

RUN apt -y install bzip2
RUN tar xf nlm-kit-0.1.tar.bz2
WORKDIR /Downloads/nlm-kit-0.1

# Force the compiler on 64-bit x86 OS to compile for 32-bit x86 architecture (i386)
# (Not needed if building the Dockerfile on/for a 32-bit x86 architecture, but doesn't hurt there either)
# The `-fno-pic` option is needed to ensure that we get a Global Offset Table, see https://stackoverflow.com/a/45422495
RUN sed -i.bak 's/gcc /gcc -m32 -fno-pic /g' src/Makefile

# Now that we built binutils 2.3.0 with nlmconv, remove the binutils installed with apt, while keeping its dependencies:
#RUN dpkg -r --force-depends binutils

RUN nlmconv --help

RUN apt -y install gcc-multilib

RUN make all install

RUN make install-include

# Allows curl to be installed with apt-get.
# With thanks to https://unix.stackexchange.com/a/749304
RUN echo "deb http://archive.debian.org/debian-security stretch/updates main" >> /etc/apt/sources.list
RUN apt -y update

# Install dependencies required to allow this to be used as a Dev Container
# (see https://www.jetbrains.com/help/rider/Prerequisites_for_dev_containers.html#remote_container)
RUN apt -y install curl unzip libxext6 libxrender1 libxtst6 libxi6 libfreetype6 procps  # FIXME
# gcompat is only needed on non-glibc systems, such as Alpine Linux

# Perform a test build
WORKDIR /Downloads
RUN tar xf nlm-samples.tar.bz2
WORKDIR /Downloads/nlm-samples/hello
# Change the standard `Hello world!` message to a custom one, to make it clear it's the one from this build.
RUN sed -i.bak "s/Hello world!/Well, hello there! (built at $(date))/g" hello.c
# Force the compiler on 64-bit x86 OS to compile for 32-bit x86 architecture (i386)
# The `-fno-pic` option is needed to ensure that we get a Global Offset Table, see https://stackoverflow.com/a/45422495
RUN sed -i.bak 's/CFLAGS = /CFLAGS = -m32 -fno-pic /g' Makefile
# Enable debugging in nlmconv for troubleshooting weird `Invalid operation` error
RUN sed -i.bak 's/nlmconv --output-target/nlmconv --debug --output-target/g' Makefile
RUN mv hello.o hello_orig.o
RUN mv hello.nlm hello_orig.nlm
RUN make
RUN ls -lh hello.o
RUN ls -lh hello.nlm
RUN ls -lh hello*

# Package the built NLM file in a ready-to-mount floppy image
RUN apt -y install mtools
# With thanks to https://labex.io/tutorials/linux-linux-mtools-command-with-practical-examples-422829
RUN dd if=/dev/zero of=/tmp/nlm_disk.img bs=1440k count=1
# With thanks to https://msfn.org/board/topic/120444-how-to-install-windows-from-usb-winsetupfromusb-with-gui/page/108/
RUN mformat -C -f 1440 -i /nlm_disk.img ::
RUN mcopy -i /nlm_disk.img *.nlm ::
RUN mcopy -i /nlm_disk.img /usr/nwsdk/lib/smp/threads.nlm ::
RUN mdir -i /nlm_disk.img ::

FROM --platform=${BUILDPLATFORM} debian:9.13
COPY --from=builder /nlm_disk.img /nlm_disk.img
