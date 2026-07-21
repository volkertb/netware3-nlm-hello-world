# netware3-hello-world

A "Hello World" NLM (NetWare Loadable Module) for Novell NetWare 3.11/3.12, built with a
period-correct cross-toolchain (patched binutils-2.30 `nlmconv` + modern `gcc -m32`) inside a
devcontainer. Original author and primary human maintainer: Volkert de Buisonjé.

## Build & verify

- `make` (repo root) builds two NLMs — `hello.nlm` (console output + text-buffer writes) and
  `helloold.nlm` (adds a 320×200 VGA graphics-mode switch) — deep-verifies each with `verify-nlm`
  (byte-checks every relocation and the NLM header, so toolchain corruption cannot slip through),
  and packs both into `floppy.img` via `mtools`. Works only inside the devcontainer
  (`/usr/nwsdk` + the patched `nlmconv`/`i386-netware-ld` toolchain).
- `*.def` files are the NLM header/link definitions consumed by `nlmconv`.
- Functional correctness still requires booting `floppy.img` on real or emulated NetWare
  3.11/3.12. The QEMU sidecar (`vmctl on|off|reset|status`,
  [docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md)) boots/stops the VM, but getting
  `floppy.img` into it is still a manual step until floppy load/eject lands. Last full boot
  verification: 2026-07-19, both NLMs work, including the graphics switch that used to abend. Root cause of
  the 2025 abends was a toolchain relocation bug; every 2025-era theory (IOPL, `TYPE 9`,
  `OS_DOMAIN`) is dead. History, mechanism, and the mandatory CFLAGS rules:
  [docs/nlm-toolchain-notes.md](docs/nlm-toolchain-notes.md).
- `.devcontainer/build_and_fetch_floppy_image.sh` builds the container image standalone and
  copies `/nlm_disk.img` to `~/Downloads/`, without opening a devcontainer session.

## Devcontainer

Details, stage rationale, and troubleshooting history: [docs/devcontainer.md](docs/devcontainer.md).
Summary: 4-stage Dockerfile (`downloader-and-patcher` → `binutils-builder` → `builder` →
`dev-env`). Downloads and binutils source patching happen on current Debian in
`downloader-and-patcher`; only `binutils-builder` uses EOL Debian 9, kept to configure+make of
binutils 2.30, whose obsolete `nlm32-i386` target won't build on newer toolchains and was removed
upstream after 2.31.

## Planned work

1. QEMU sidecar ([docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md)) — boot/shutdown MVP
   landed and boot-verified 2026-07-21 (`vmctl on|off|reset|status`, `qmp <command>`). VNC for
   the human and floppy load/eject into the running VM are still open.
2. NDK independence and game platform ([docs/ndk-independence.md](docs/ndk-independence.md)) —
   drop the proprietary NDK (its real build-time surface is one 892-byte glue object plus one
   prototype), then a picolibc-based runtime for low-level/game NLM development.

## Rules

- IMPORTANT: never name a specific coding agent in a committed `.devcontainer/` file. Agent-specific
  state/config belongs only in gitignored files (e.g. `.devcontainer/postCreate.local.sh`), driven by
  generic hooks in `devcontainer.json`.
- In Dockerfile/script comments, explain *why*, not *what* — match the existing terse style, don't
  add verbose restatements of the command above them.
- Verify non-obvious technical claims (tool support, dependency behavior) against a primary source
  before stating them as fact, rather than from memory or a search summary.
- Use Conventional Commits (`type: description` + explanatory body).
- See [docs/agents-md-style-guide.md](docs/agents-md-style-guide.md) before editing this file.
