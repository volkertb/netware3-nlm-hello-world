# Sound

Part of the game-platform's Track A direct-hardware experiments
([ndk-independence.md](ndk-independence.md)) — proves out sound on the existing NDK/CLIB
toolchain, no NDK-independence work involved.

## AdLib (OPL2): done, 2026-07-26

`hellovga.nlm` plays a short jingle (decoded from Westwood's ADL music format) while its logo is
displayed; fade-out and the text-mode restore correctly block until playback finishes. Boot-tested
end-to-end in the QEMU sidecar (no abend across the full graphics + sound + fade-out cycle).

Architecture, two pieces with different provenance/licensing (full detail: `LICENSE.md`):

- `music/adl_to_c.py` — build-time-only Python tool. Decodes every named subsong in a `.ADL` file
  into a flat, pre-resolved stream of OPL2 register writes + timing, emitted as embeddable C.
  Licensed LGPL-2.1-or-later (it ports AdPlug's `adl.cpp` opcode VM); never linked into the
  shipped NLM. Format itself: [westwood-adl-format-spec.md](westwood-adl-format-spec.md) — a
  from-scratch, language-agnostic spec suitable for reimplementing a parser/player without
  reference to this project's code.
- `adlib_util.c`/`.h` — the NLM-side runtime. Format-agnostic: just walks a flat
  `Opl2Event`/`Opl2Song` stream and writes OPL2 registers with the standard AdLib port-timing
  convention (ports `0x388`/`0x389`). No ADL-specific knowledge, ships under this project's normal
  license.

The source asset (`DUNE0.ADL`, Westwood's copyrighted Dune II game data) isn't committed — the
Makefile downloads and SHA256-verifies it into `downloads/` (gitignored, survives `make clean`).

**Known issue, not yet root-caused:** tested on a separate VM with real OPL2 emulation enabled —
plays correctly overall, but tempo felt slightly too fast in places. Candidate causes, none
confirmed: a rounding bug in `adl_to_c.py`'s tick→millisecond conversion, NetWare `delay()`'s
millisecond-only granularity, or that VM's own OPL2 emulation being imprecise. Deferred until
tested against a more accurate emulator or real hardware.

## Sound Blaster: not started

Port I/O + DMA controller programming + IRQ hook (harder than AdLib's pure port I/O).

## QEMU sidecar has no audio device wired up

`qemu-system-i386`'s invocation has no `-audiodev`/`-device` for sound at all — confirmed harmless
for testing purposes (unmapped x86 port I/O is a safe no-op/no-hang, not a crash or hang, so
`hellovga.nlm` boot-tests fine there regardless; audio has to be verified on a separate VM with
sound configured instead). To wire one up: an `-audiodev` backend plus `-device
adlib,audiodev=<id>` (OPL2 at port `0x388`), later `-device sb16,audiodev=<id>` for Sound Blaster.
