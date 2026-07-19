# SPDX-License-Identifier: Apache-2.0

# All large downloads fetched once, up front, into a cache mount and reused across builds by
# every later stage that needs one - a current Debian release with clean apt repos, so wget just
# works with no EOL-archive workarounds needed.
FROM debian:11.11 AS downloader

ARG DOWNLOAD_BINUTILS_FILE_NAME=binutils-2.30.tar.xz
ARG DOWNLOAD_BINUTILS_INTERNET_PATH=https://ftp.gnu.org/gnu/binutils/$DOWNLOAD_BINUTILS_FILE_NAME
ARG DOWNLOAD_BINUTILS_SHA256=6e46b8aeae2f727a36f0bd9505e405768a72218f1796f0d09757d45209871ae6

ARG DOWNLOAD_NOVSDKCD_4_FILE_NAME=NOVSDKCD_4.iso
ARG DOWNLOAD_NOVSDKCD_4_INTERNET_PATH=https://archive.org/download/novsdkcd-4/$DOWNLOAD_NOVSDKCD_4_FILE_NAME
ARG DOWNLOAD_NOVSDKCD_4_SHA256=4255e7426002007fffc60cb6167230ecbd2207772d54481bbeb9da6ee7005193

ARG DOWNLOAD_NLM_SAMPLES_FILE_NAME=nlm-samples.tar.bz2
ARG DOWNLOAD_NLM_SAMPLES_INTERNET_PATH=https://web.archive.org/web/20050227034206if_/http://www.penguin.cz:80/~mhi/ftp/nlm/$DOWNLOAD_NLM_SAMPLES_FILE_NAME
ARG DOWNLOAD_NLM_SAMPLES_SHA256=72cd8a19d06558a0e6704a489c806b9ccb050e59321393f7b6dd11b944f0fdb4

ARG DOWNLOAD_NLM_KIT_FILE_NAME=nlm-kit-0.1.tar.bz2
ARG DOWNLOAD_NLM_KIT_INTERNET_PATH=https://web.archive.org/web/20050227034206if_/http://www.penguin.cz:80/~mhi/ftp/nlm/$DOWNLOAD_NLM_KIT_FILE_NAME
ARG DOWNLOAD_NLM_KIT_SHA256=0e407c3f231e5ceb47ca387a7c0e82b64e81620df3871e2110290fb0effa3fe1

# Keep apt's downloaded .deb files and package lists in cache mounts across builds, instead of
# baking them into image layers or re-downloading them every time. Debian images delete
# downloaded packages after each install by default, hence removing docker-clean here.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y update \
    && apt -y install wget ca-certificates

RUN mkdir -p /Downloads

# Each of these is fetched once into a cache mount and reused across builds. The skip-download
# check is gated on checksum success, not just file presence, so a partial/corrupt cached file
# (e.g. from a build that got interrupted mid-download) is redownloaded rather than getting
# stuck failing forever.
RUN --mount=type=cache,target=/downloads-cache \
    [ -f /downloads-cache/$DOWNLOAD_BINUTILS_FILE_NAME ] && echo "$DOWNLOAD_BINUTILS_SHA256  /downloads-cache/$DOWNLOAD_BINUTILS_FILE_NAME" | sha256sum --status -c - \
    || wget -q -O /downloads-cache/$DOWNLOAD_BINUTILS_FILE_NAME $DOWNLOAD_BINUTILS_INTERNET_PATH \
    && echo "$DOWNLOAD_BINUTILS_SHA256  /downloads-cache/$DOWNLOAD_BINUTILS_FILE_NAME" | sha256sum -c - \
    && cp /downloads-cache/$DOWNLOAD_BINUTILS_FILE_NAME /Downloads/

RUN --mount=type=cache,target=/downloads-cache \
    [ -f /downloads-cache/$DOWNLOAD_NOVSDKCD_4_FILE_NAME ] && echo "$DOWNLOAD_NOVSDKCD_4_SHA256  /downloads-cache/$DOWNLOAD_NOVSDKCD_4_FILE_NAME" | sha256sum --status -c - \
    || wget -q -O /downloads-cache/$DOWNLOAD_NOVSDKCD_4_FILE_NAME $DOWNLOAD_NOVSDKCD_4_INTERNET_PATH \
    && echo "$DOWNLOAD_NOVSDKCD_4_SHA256  /downloads-cache/$DOWNLOAD_NOVSDKCD_4_FILE_NAME" | sha256sum -c - \
    && cp /downloads-cache/$DOWNLOAD_NOVSDKCD_4_FILE_NAME /Downloads/

RUN --mount=type=cache,target=/downloads-cache \
    [ -f /downloads-cache/$DOWNLOAD_NLM_SAMPLES_FILE_NAME ] && echo "$DOWNLOAD_NLM_SAMPLES_SHA256  /downloads-cache/$DOWNLOAD_NLM_SAMPLES_FILE_NAME" | sha256sum --status -c - \
    || wget -q -O /downloads-cache/$DOWNLOAD_NLM_SAMPLES_FILE_NAME $DOWNLOAD_NLM_SAMPLES_INTERNET_PATH \
    && echo "$DOWNLOAD_NLM_SAMPLES_SHA256  /downloads-cache/$DOWNLOAD_NLM_SAMPLES_FILE_NAME" | sha256sum -c - \
    && cp /downloads-cache/$DOWNLOAD_NLM_SAMPLES_FILE_NAME /Downloads/

RUN --mount=type=cache,target=/downloads-cache \
    [ -f /downloads-cache/$DOWNLOAD_NLM_KIT_FILE_NAME ] && echo "$DOWNLOAD_NLM_KIT_SHA256  /downloads-cache/$DOWNLOAD_NLM_KIT_FILE_NAME" | sha256sum --status -c - \
    || wget -q -O /downloads-cache/$DOWNLOAD_NLM_KIT_FILE_NAME $DOWNLOAD_NLM_KIT_INTERNET_PATH \
    && echo "$DOWNLOAD_NLM_KIT_SHA256  /downloads-cache/$DOWNLOAD_NLM_KIT_FILE_NAME" | sha256sum -c - \
    && cp /downloads-cache/$DOWNLOAD_NLM_KIT_FILE_NAME /Downloads/

# Debian 9 (Stretch) is the last Debian release that has a binutils lower than version 2.31, but no nlmconv by default.
# GNU ld (GNU Binutils for Debian) 2.28
#
# Compiling binutils 2.30's obsolete NLM target support needs an old-enough toolchain - nothing
# upstream tests --enable-obsolete targets like nlm32-i386 against newer GCC/glibc, and even here
# (a period-matched toolchain) the source needs patching below to build and work correctly. Only
# the binutils build itself needs Debian 9, so this stage is kept to just that: everything else
# that used to happen alongside it runs in the "builder" stage below instead, on a current Debian
# release with working, non-archived apt repos.
FROM debian:9.13 AS binutils-builder

COPY --from=downloader /Downloads/binutils-2.30.tar.xz /Downloads/

# With thanks to https://unix.stackexchange.com/a/743863
RUN echo "deb http://archive.debian.org/debian stretch main contrib non-free" > /etc/apt/sources.list

# Keep apt's downloaded .deb files and package lists in cache mounts across builds, instead of
# baking them into image layers or re-downloading them every time. Debian images delete
# downloaded packages after each install by default, hence removing docker-clean here.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y update

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install xz-utils
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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install build-essential
# `makeinfo` is apparently needed when any of the binutils sources and/or texi files have been changed:
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install texinfo
# For nlncomv to work properly, we need to fake 32-bit Linux when running configure before building binutils.
RUN linux32 ./configure --prefix=/usr/local --enable-targets=i386-netware --enable-obsolete
RUN make
RUN make install
#RUN man nlmconv
RUN nlmconv --version
RUN ld -v

# A current Debian release with normal, non-archived apt repos - avoids the whole class of
# archive.debian.org/EOL-dependency problems for everything that doesn't actually need Debian 9.
# Old (Debian 9-compiled) binaries run fine on a newer glibc, so the nlmconv/ld built above just
# gets copied in and used here as-is.
FROM debian:11.11 AS builder

COPY --from=binutils-builder /usr/local /usr/local
RUN nlmconv --version && ld -v

# Keep apt's downloaded .deb files and package lists in cache mounts across builds, instead of
# baking them into image layers or re-downloading them every time. Debian images delete
# downloaded packages after each install by default, hence removing docker-clean here.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y update

RUN mkdir -p /Downloads
COPY --from=downloader /Downloads/NOVSDKCD_4.iso /Downloads/
COPY --from=downloader /Downloads/nlm-samples.tar.bz2 /Downloads/
COPY --from=downloader /Downloads/nlm-kit-0.1.tar.bz2 /Downloads/

WORKDIR /Downloads

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install xorriso
RUN xorriso -osirrox on -indev ./NOVSDKCD_4.iso -extract / /Downloads/NOVSDKCD_4
WORKDIR /Downloads/NOVSDKCD_4/FUTURES/NWSDK/NLMNIT
RUN ls -lh
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install zip
RUN zip -r /tmp/ndk.zip .
WORKDIR /usr/nwsdk
# Unpack NDK directories and files in lower case:
RUN unzip -LL /tmp/ndk.zip
RUN ls -lh /usr/nwsdk/include/nwconio.h

WORKDIR /Downloads

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install bzip2
RUN tar xf nlm-kit-0.1.tar.bz2
WORKDIR /Downloads/nlm-kit-0.1

# Force the compiler on 64-bit x86 OS to compile for 32-bit x86 architecture (i386)
# (Not needed if building the Dockerfile on/for a 32-bit x86 architecture, but doesn't hurt there either)
# The `-fno-pic` option is needed to ensure that we get a Global Offset Table, see https://stackoverflow.com/a/45422495
RUN sed -i.bak 's/gcc /gcc -m32 -fno-pic /g' src/Makefile

# Now that we built binutils 2.3.0 with nlmconv, remove the binutils installed with apt, while keeping its dependencies:
#RUN dpkg -r --force-depends binutils

RUN nlmconv --help

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install build-essential gcc-multilib

RUN make all install

RUN make install-include

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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install mtools
# With thanks to https://labex.io/tutorials/linux-linux-mtools-command-with-practical-examples-422829
RUN dd if=/dev/zero of=/tmp/nlm_disk.img bs=1440k count=1
# With thanks to https://msfn.org/board/topic/120444-how-to-install-windows-from-usb-winsetupfromusb-with-gui/page/108/
RUN mformat -C -f 1440 -i /nlm_disk.img ::
RUN mcopy -i /nlm_disk.img *.nlm ::
RUN mcopy -i /nlm_disk.img /usr/nwsdk/lib/smp/threads.nlm ::
RUN mdir -i /nlm_disk.img ::

FROM debian:11.11 AS dev-env

ARG USERNAME=dev-container-user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

COPY --from=builder /nlm_disk.img /nlm_disk.img
COPY --from=builder /usr/local /usr/local
COPY --from=builder /usr/nwsdk /usr/nwsdk
COPY --from=builder /usr/bin/nlmimp /usr/bin/nlmimp

# Keep apt's downloaded .deb files and package lists in cache mounts across builds, instead of
# baking them into image layers or re-downloading them every time. Debian images delete
# downloaded packages after each install by default, hence removing docker-clean here.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y update

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install build-essential gcc-multilib

# Install dependencies required to allow this to be used as a Dev Container
# (see https://www.jetbrains.com/help/rider/Prerequisites_for_dev_containers.html#remote_container)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install curl unzip libxext6 libxrender1 libxtst6 libxi6 libfreetype6 procps git
# gcompat is only needed on non-glibc systems, such as Alpine Linux

# Create the default user. See https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m -s /bin/bash $USERNAME

# Make mtools available in the dev container, so built NLM files can be packaged in ready-to-mount floppy images
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install mtools

# Workaround for the issue with Background task "Starting ReSharper C++ Engine..." hanging in the JetBrains client IDE
# With thanks to https://youtrack.jetbrains.com/issue/IJPL-191705/Start-Failed-PluginException-empty-file-Plugin-com.intellij#focus=Comments-27-12184816.0-0
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install libicu-dev

# Debugging/analysis helpers: binary inspection (xxd, file; bsdextrautils for hexdump -e's
# custom format strings, e.g. extracting single NLM header fields), VM disk-image work (qemu-utils),
# QMP scripting against the planned QEMU sidecar (python3, socat, jq — see docs/qemu-vm-debugging.md),
# faster searching and script/syscall troubleshooting (ripgrep, shellcheck, strace).
# --no-install-recommends because qemu-utils otherwise pulls in desktop-oriented Recommends.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install --no-install-recommends python3 xxd file bsdextrautils qemu-utils socat jq ripgrep shellcheck strace

# Copy the NLM samples from the builder stage and make them available to the non-root user for the test build below
COPY --from=builder /Downloads/nlm-samples /home/$USERNAME/Downloads/nlm-samples
RUN chown -R $USERNAME /home/$USERNAME/Downloads/nlm-samples

# Switch from root to the default user. See https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user
USER $USERNAME

# Debian's skel files add ~/.local/bin to PATH via ~/.profile, but that's only sourced by
# login shells - not the non-login shells VS Code's integrated terminal (and most tooling)
# actually spawns. Set it via ENV instead, so user-installed binaries under ~/.local/bin are
# on PATH for every shell and process in this image, login or not.
ENV PATH="/home/$USERNAME/.local/bin:$PATH"

# Install Claude Code natively as this user (not via the npm-based devcontainer feature,
# which leaves a root-owned leftover that later breaks auto-update permissions).
RUN curl -fsSL https://claude.ai/install.sh | bash

# Perform a test build as the non-root user
WORKDIR /home/$USERNAME/Downloads/nlm-samples/hello
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

# Make the (current) non-root user's home directory the default work directory for this container image.
WORKDIR /home/$USERNAME
