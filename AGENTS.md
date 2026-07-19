# netware3-hello-world

A "Hello World" NLM (NetWare Loadable Module) for Novell NetWare 3.11/3.12, built with a
period-correct cross-toolchain (old binutils `nlmconv` + `gcc -m32 -fno-pic`) inside a devcontainer.
Original author and primary human maintainer: Volkert de Buisonjé.

## Build & verify

- Build: `make` (repo root). Produces two NLMs — `hello.nlm` (`hello.c` + `vga_util.c`: console
  output, text-buffer writes) and `helloold.nlm` (`hello_old.c`: additionally switches to 320×200
  VGA graphics via `vgamode.c` register programming) — deep-verifies each with `verify-nlm`, and
  packs both into `floppy.img` via `mtools`. Requires `/usr/nwsdk` and the patched
  `nlmconv`/`i386-netware-ld` toolchain — only available inside the devcontainer, not on a bare host.
- `hello.def`/`hello_old.def` are the NLM header/link definition files consumed by `nlmconv`.
- `.devcontainer/build_and_fetch_floppy_image.sh` builds the container image standalone and copies
  out `/nlm_disk.img` to `~/Downloads/`, without opening a full devcontainer session.
- Testing: `verify-nlm` (run automatically by `make`) byte-checks every relocation and the NLM
  header, so toolchain-level corruption cannot slip through — but functional correctness is still
  only confirmed by booting `floppy.img` on real or emulated NetWare 3.11/3.12, a manual step
  until the QEMU sidecar below exists. Last full boot verification: 2026-07-19, both NLMs work.

## Devcontainer

Full details, stage-by-stage rationale, and troubleshooting history: [docs/devcontainer.md](docs/devcontainer.md).

Quick summary: `.devcontainer/Dockerfile` is a 4-stage build (`downloader-and-patcher` →
`binutils-builder` → `builder` → `dev-env`). Only `binutils-builder` uses EOL Debian 9, and it is
kept to the bare minimum (configure+make of binutils) — required because binutils 2.30's obsolete
`nlm32-i386`/`i386-netware` target support won't build cleanly on newer toolchains, and upstream
removed that target support entirely after 2.31. Downloads and binutils source patching happen in
`downloader-and-patcher`; everything else runs on current Debian.

## Planned work

Current next step: the QEMU sidecar. [docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md) — not
yet implemented — captures requirements for a QEMU-based NetWare VM sidecar container with VNC
access for the human and a QMP control channel for the agent (keyboard input, screen reads,
crash/hang auto-recovery), replacing the manual build-boot-reset cycle with a fast joint
human+agent development loop.

After that: [docs/ndk-independence.md](docs/ndk-independence.md) — plan for removing the
proprietary Novell NDK from the build (its real surface is one 892-byte glue object and one
prototype) and growing a picolibc-based, license-clean runtime for low-level/game NLM development.

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

## Resolved: the 2025 abend saga

The 2025 abends (`Invalid TSS`, GPPE — logged in [README.md](README.md)/[NOTES.md](NOTES.md)) were
caused by a toolchain relocation bug that corrupted every cross-object call. Fixed 2026-07-19 in
the Dockerfile's binutils patches and **confirmed the same day by booting on NetWare 3.12**: both
NLMs run, including the VGA graphics-mode switch that used to abend — with plain `TYPE 0` and no
`OS_DOMAIN` (also verified; the 2025-era driver-flag theories are all dead). Mechanism, the
mandatory `-fno-asynchronous-unwind-tables` CFLAGS rule, and all closure evidence:
[docs/nlm-toolchain-notes.md](docs/nlm-toolchain-notes.md).
