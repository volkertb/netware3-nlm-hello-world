# netware3-hello-world

A "Hello World" NLM (NetWare Loadable Module) for Novell NetWare 3.11/3.12, built with a
period-correct cross-toolchain (old binutils `nlmconv` + `gcc -m32 -fno-pic`) inside a devcontainer.
Original author and primary human maintainer: Volkert de Buisonjé.

## Build & verify

- Build: `make` (repo root). Produces `hello.nlm` from `hello.c` + `vga_util.c` + `hello.def`, then
  packs it into `floppy.img` via `mtools`. Requires `/usr/nwsdk` and a `gcc`/`nlmconv` that can
  target 32-bit x86 — only available inside the devcontainer, not on a bare host.
- `hello.def` is the NLM header/link definition file consumed by `nlmconv`.
- `.devcontainer/build_and_fetch_floppy_image.sh` builds the container image standalone and copies
  out `/nlm_disk.img` to `~/Downloads/`, without opening a full devcontainer session.
- There is no automated test suite. A clean `make` is the only automatic check; actual correctness
  can only be confirmed by booting `floppy.img` on real or emulated NetWare 3.11/3.12 and watching
  it load — a manual step, do not assume a clean build means the NLM works.

## Devcontainer

Full details, stage-by-stage rationale, and troubleshooting history: [docs/devcontainer.md](docs/devcontainer.md).

Quick summary: `.devcontainer/Dockerfile` is a 4-stage build (`downloader` → `binutils-builder` →
`builder` → `dev-env`). Only `binutils-builder` uses EOL Debian 9 — required because binutils 2.30's
obsolete `nlm32-i386`/`i386-netware` target support won't build cleanly on newer toolchains, and
upstream removed that target support entirely after 2.31. Everything else runs on current Debian.

## Planned work

[docs/qemu-vm-debugging.md](docs/qemu-vm-debugging.md) — not yet implemented — captures requirements
for a QEMU-based NetWare VM sidecar with VNC access for the human and a separate control channel for
the agent (keyboard input, screen reads, crash/hang auto-recovery), intended to remove the manual
build-boot-crash-reset cycle currently needed to debug the issue below.

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

## Known technical issues (in progress)

Current blocker, logged at the bottom of [README.md](README.md): an `Invalid TSS Processor Exception`
abend when the NLM attempts a graphics mode switch — suspected IOPL/ring-privilege issue, not yet
resolved. [NOTES.md](NOTES.md) has an earlier, separate note on a GPPE triggered by video memory
access, addressed by declaring the NLM a driver (`OS_DOMAIN` in `hello.def`).
