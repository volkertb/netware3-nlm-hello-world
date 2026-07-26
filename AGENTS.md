# netware3-hello-world

A "Hello World" NLM (NetWare Loadable Module) for Novell NetWare 3.11/3.12, built with a
period-correct cross-toolchain (patched binutils-2.30 `nlmconv` + modern `gcc -m32`) inside a
devcontainer. Original author and primary human maintainer: Volkert de Buisonjé.

## Build & verify

- `make` (repo root) builds two NLMs — `hello.nlm` (console output + text-buffer writes) and
  `hellovga.nlm` (320×200 VGA graphics-mode switch, fades an embedded picture in/out via DAC
  palette ramping, then restores 80×25 text mode before exiting) — deep-verifies each with
  `verify-nlm` (byte-checks every relocation and the NLM header, so toolchain corruption cannot
  slip through), and packs both into `floppy.img` via `mtools`. Works only inside the devcontainer
  (`/usr/nwsdk` + the patched `nlmconv`/`i386-netware-ld` toolchain).
- `*.def` files are the NLM header/link definitions consumed by `nlmconv`.
- Functional correctness still requires booting `floppy.img` on real or emulated NetWare
  3.11/3.12. `make deploy` builds if needed, starts the QEMU sidecar VM (idempotent), and mounts
  `floppy.img` into it — use this instead of running `vmctl on`/`vmctl floppy load` directly. The
  sidecar (`vmctl on|off|reset|status|screendump|floppy load|eject|type|vnc`,
  [docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md)) is boot-verified, including the graphics
  switch that used to abend — root cause was a toolchain relocation bug, not IOPL/`TYPE 9`/
  `OS_DOMAIN` (all dead 2025-era theories): [docs/nlm-toolchain-notes.md](docs/nlm-toolchain-notes.md).
- `.devcontainer/build_and_fetch_floppy_image.sh` builds the container image standalone and
  copies `/nlm_disk.img` to `~/Downloads/`, without opening a devcontainer session.

## Devcontainer

Details, stage rationale, and troubleshooting history: [docs/devcontainer.md](docs/devcontainer.md).
Two Compose services: `dev` (this repo's build/test environment) and `qemu` (the sidecar below).
`dev`'s image is a 4-stage Dockerfile (`downloader-and-patcher` → `binutils-builder` → `builder` →
`dev-env`). Downloads and binutils source patching happen on current Debian in
`downloader-and-patcher`; only `binutils-builder` uses EOL Debian 9, kept to configure+make of
binutils 2.30, whose obsolete `nlm32-i386` target won't build on newer toolchains and was removed
upstream after 2.31.

## Planned work

1. QEMU sidecar ([docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md)) — boot/shutdown, floppy
   load/eject, keyboard injection, and VNC all boot-verified. Only automatic hang/crash detection
   remains open.
2. Game platform, two tracks ([docs/ndk-independence.md](docs/ndk-independence.md)) — Track A
   (current): graphics/sound experiments on the NDK/CLIB toolchain as-is, period-developer style.
   Track B (deferred): drop the proprietary NDK (its real build-time surface is one 892-byte glue
   object plus one prototype) and a picolibc-based runtime, then redo Track A's experiments on it
   for comparison.

## Rules

- IMPORTANT: never name a specific coding agent in a committed `.devcontainer/` file. Agent-specific
  state/config belongs only in gitignored files (e.g. `.devcontainer/postCreate.local.sh`), driven by
  generic hooks in `devcontainer.json`.
- In Dockerfile/script comments, explain *why*, not *what* — match the existing terse style, don't
  add verbose restatements of the command above them.
- Verify non-obvious technical claims (tool support, dependency behavior) against a primary source
  before stating them as fact, rather than from memory or a search summary.
- After creating/editing a `.devcontainer/**` shell or Python script, run shellcheck / `ruff check`
  / `pylint` / `python3 -m py_compile` on it (config: `.devcontainer/pyproject.toml`) — same tools
  the Dockerfile's SCA gate enforces at build time. Not the C/NLM code under test — no linting set
  up there yet.
- Before reading the NetWare VM's console, check its mode first via `vmctl screendump`'s PPM header
  (`P6\n<width> <height>\n255\n`) — 720×400 is text, 320×200 is mode 13h graphics (no QMP
  mode-query command exists). Text → follow with `pmemsave` of `0xB8000` for exact characters.
  Graphics → the screendump itself, via `pnmtopng`. The console only *looks* hung after a
  graphics-mode test — it's still running, just not in text mode. Full detail:
  [docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md).
- IMPORTANT: never run a VirtualBox VM at the same time as this project's QEMU sidecar — a stock
  VirtualBox VM starting after a KVM guest is already running can seize VT-x anyway and crash it
  (`KVM: entry failed, hardware error 0x0`), corrupting `disk.qcow2` mid-write. Mechanism:
  [docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md)'s "Resolved: QEMU/KVM entry-failure
  crash" section.
- "Rebuild Container" never rebuilds/recreates the `qemu` sidecar, only `dev`. After a "rebuilt"
  claim, verify a `.devcontainer/qemu/**` edit actually took effect (e.g. a QMP-visible check)
  before trusting it. Fix needs host `docker`/`podman`, unavailable here:
  [docs/devcontainer.md](docs/devcontainer.md).
- Use Conventional Commits (`type: description` + explanatory body).
- See [docs/agents-md-style-guide.md](docs/agents-md-style-guide.md) before editing this file.
