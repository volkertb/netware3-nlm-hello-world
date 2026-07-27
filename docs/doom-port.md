# Doom port (plan, 2026-07-27)

Applies the game-platform's Track A direct-hardware work ([ndk-independence.md](ndk-independence.md))
to a real game instead of demos. Still Track A: NDK/CLIB toolchain as-is, no independence work.

## Chosen base: doomgeneric, not FastDoom/djdoom/doom-vanille

Considered forks and their lineage:

- **FastDoom** and **doom-vanille** both fork from nukeykt/PCDoom (a disassembly-accurate
  recreation of the retail `DOOM.EXE`). FastDoom optimizes for speed on 386/486 (hand-tuned NASM,
  a reduced-detail "potato mode", removed rendering limits, broad hardware support: VGA/EGA/CGA/
  VESA, SB/OPL2/OPL3/Tandy/CMS, MT-32/SC-55/General MIDI). doom-vanille optimizes for bug-for-bug
  fidelity to the original binary instead.
- **djdoom** forks from a different recreation lineage (gamesrc-ver-recreation); its actual goal
  is comparing DOS compilers (DJGPP/Watcom/Digital Mars/CC386) for speed, not portability.
- **doomgeneric** is independent of all three, built on id's original released Doom source. A
  port implements 5 functions (`DG_Init`, `DG_DrawFrame`, `DG_SleepMs`, `DG_GetTicksMs`,
  `DG_GetKey`) and supplies everything else itself — no DOS/BIOS/extender assumptions anywhere,
  proven across dozens of non-DOS, non-SDL targets (terminal, printer, e-ink, embedded).

**doomgeneric wins for this project** because none of the DOS-extender plumbing in the other
three transfers to an NLM anyway (no BIOS, no DPMI, different memory/IRQ model), so the deciding
factor is how much of that plumbing has to be stripped out of the *engine* before porting can even
start. FastDoom/doom-vanille require OpenWatcom + NASM throughout; doomgeneric is plain portable C
that already builds with this project's existing `gcc -m32` toolchain, and its 5-function
boundary is the smallest possible surface to replace.

This is a sequencing choice, not a rejection of FastDoom's optimizations: verified by reading its
actual source (not just its README) that `i_vga13h.c`'s screen writes and `ns_sb.c`'s Sound
Blaster DSP/mixer access are already plain 32-bit protected-mode `inp`/`outp`/linear-memory code —
only the thin OS-glue around them (`int 10h` mode-set, `_dos_setvect`/DPMI IRQ install) is
DOS-specific. That's exactly what makes FastDoom's `ns_sb.c` viable donor material for the Sound
Blaster phase below, and its rendering optimizations viable donor material for a later speed pass
once doomgeneric's plain-C renderer is verified correct on NetWare.

## Licensing: DOOM.NLM will be GPL-2.0 (confirmed 2026-07-27)

doomgeneric ships its own `LICENSE` file, GPLv2 — not just an inherited assumption, confirmed by
reading that file directly. id's original Doom source release is the same license, so this isn't
doomgeneric-specific: any Doom engine port carries it. Unlike the AdLib work's
[license boundary](sound.md) (copyleft confined to a build-time-only Python tool that never ships),
GPL-2.0 game-engine code ships *in* the runtime here, so it can't be isolated the same way — the
compiled `DOOM.NLM` binary as a whole must be distributed under GPL-2.0(-compatible) terms. This
only affects that one artifact; `hello.nlm`/`hellovga.nlm` and the rest of the repo are unaffected.

Consequence for code this project already has, checked against the current source (not the docs)
because `LICENSE.md` describes per-component licensing that matters a lot here:

- `adlib_util.c` currently ships under this project's own (unstated/all-rights-reserved) license,
  but it's Volkert de Buisonjé's own code — he can simply also license it GPL-2.0 for use inside
  `DOOM.NLM`. Not a blocker, just a `LICENSE.md` entry to add when it's wired in.
- `vgamode.c`/`nlm_io_wrapper.c`/`hello_vga.c`'s `putpixel`: resolved — see "VGA source
  provenance" below and `LICENSE.md`. Public-domain code is GPL-compatible, and all three are now
  confirmed public domain/CC0.
- The IWAD (`DOOM1.WAD`) is game data, not code — GPL doesn't apply to it, but it still needs to
  be the freely-redistributable shareware episode, not a commercial WAD (see MVP essentials below).
- When the Doom sources actually land (own subdirectory, presumably), add a `LICENSE.md` entry for
  it following the existing per-component pattern, and vendor the GPL-2.0 license text alongside
  the source (same as `nlm-kit`'s bundled `COPYING.LIB`).

## VGA source provenance: resolved (2026-07-27)

`hello_vga.c` uses `vgamode.h`'s `init_graph_vga()` for the actual mode-13h graphics switch (text
restore already goes through the unambiguous `modes.c`). All three files sourced from osdev.org
are now confirmed public domain (details and citations in `LICENSE.md`):

- **`vgamode.c`** (`p=69240`): the forum thread's original poster shared this code; another user
  replied in-thread identifying it as public domain, matching Chris Giese's already-vendored,
  Wayback-archived-PD `modes.c`.
- **`nlm_io_wrapper.c`** (`p=69241`, same thread): the original poster's very next post, one minute
  after the `vgamode.c` post, covered by that same in-thread public-domain reply.
- **`hello_vga.c`'s `putpixel`** (the OSDev wiki page): covered by the wiki's own CC0 policy for
  all content added since June 6, 2011 — this page was created in 2021, well after that cutoff.

The `modes.c` consolidation below remains worth doing on functional-parity grounds even though the
licensing question that originally motivated it is now closed — kept for reference:

- `write_regs(g_320x200x256)` is `modes.c`'s equivalent of `vgamode.c`'s
  `init_graph_vga(320, 200, 1)` — an exact canned register dump for mode 13h, not something
  reconstructed. `write_regs(g_320x200x256_modex)` covers the ModeX/planar case the same way.
- `write_pixel8`/`write_pixel8x` are `modes.c`'s equivalent of the wiki-sourced `putpixel`
  (currently dead code in `hello_vga.c` — "no call site to actually mix up x/y").
- `vgamode.c`'s only genuine advantage is resolutions `modes.c` has no canned dump for — it's a
  parametrized mode-setter across 5 widths × 11 heights (up to 400×600, both chain4 linear and
  planar) computed from lookup tables, versus `modes.c`'s fixed list of named dumps (`modes.c`
  even flags its own gap here directly: `/* g_360x480x256_modex - to do */`). Doom's MVP needs
  exactly 320×200×256 — nothing `modes.c` doesn't already have.

So: rebasing `hello_vga.c` (and `DOOM.NLM`'s platform layer) onto `modes.c` for the mode-13h switch
and pixel plot would be a no-op change in file count/dependencies, at zero functional cost for
anything this project currently does or plans — worth doing opportunistically, but no longer
blocking anything now that provenance is resolved.

## MVP scope

VGA graphics (mode 13h, reusing `vgamode.c`/`modes.c`), OPL2/AdLib music (reusing `adlib_util.c`,
already proven — see [sound.md](sound.md)), keyboard input only. No mouse, no Sound Blaster, no
General MIDI, no LAN yet.

## MVP essentials beyond graphics/music/keyboard

- **IWAD**: needs the shareware `DOOM1.WAD` specifically — freely redistributable, unlike a
  commercial WAD. It's several MB, larger than a single 1.44 MB floppy, so it can't ride along
  with the NLM on `floppy.img` the way this project's other artifacts do — deployment mechanism
  (second floppy, a hard-disk volume in the QEMU sidecar, or something else) needs its own
  decision, separate from the existing NLM build/floppy tooling.
- **Timing source**: `DG_GetTicksMs`/`DG_SleepMs` need a monotonic NetWare millisecond clock.
  Exact CLIB/kernel API TBD — open research item.
- **Keyboard model**: Doom needs to know which keys are *currently held* each tic, not a stream
  of keypress events — the original DOS version bypasses BIOS/DOS keystroke buffering entirely
  with its own IRQ1 handler reading port `0x60` for exactly this reason. CLIB's `conio`
  `getch()`/`kbhit()` likely only exposes buffered keystrokes (verify); if so, keyboard input
  needs the same hardware-interrupt hook confirmed below, moved into the MVP itself rather than
  deferred to the Sound Blaster phase. Hooking IRQ1 also steals input from NetWare's own console
  (already flagged in [ndk-independence.md](ndk-independence.md)) — chain to the existing handler
  (`shareFlag`) and restore it on exit, same discipline as the text-mode restore below.
- **Palette/blit path**: Doom's software renderer natively outputs an 8-bit palette-indexed
  320×200 buffer plus a palette lump (`I_SetPalette`) — exactly VGA mode 13h's native format.
  doomgeneric's existing ports (SDL/X11/etc.) convert this to 32-bit RGBA before calling
  `DG_DrawFrame`, since modern displays don't do palettized output. That conversion should be
  skipped entirely here: hook in before it, blit the raw indexed buffer straight to `0xA0000`,
  and drive the DAC palette from Doom's own palette data — the same direct-register approach
  `hellovga.nlm`'s fade code already uses. Needs checking exactly where in doomgeneric's source
  that conversion happens.
- **Cooperative scheduling**: already flagged in [ndk-independence.md](ndk-independence.md) — a
  tight, never-yielding main loop can starve the server / trip the CPU-hog watchdog. Doom's main
  loop needs a periodic yield call (exact 3.x export still an open research item there).
- **Exit discipline**: restore 80×25 text mode *and* any hooked keyboard IRQ vector before the
  NLM unloads, on both a clean quit and (as best as feasible) an abend path — same discipline
  `hellovga.nlm` already follows for text-mode restore.
- **Memory footprint**: a few MB of heap even for the shareware episode; period 3.x servers
  commonly had 8-32 MB RAM shared with every other loaded NLM. Not expected to be a blocker, worth
  watching.

## Hardware-interrupt API, confirmed (2026-07-27)

Resolves the "interrupt-hook exports" open item in [ndk-independence.md](ndk-independence.md):
`SetHardwareInterrupt`/`ClearHardwareInterrupt` (CLIB Advanced Services, declared in
`NLM/NOVH/ADVANCED.H` on the NDK SDK ISO) are the real mechanism LAN/disk driver NLMs use to hook
a hardware IRQ from an NLM — confirmed by reading the SDK's own reference documentation
(`DOC/ENGLISH/SERVER01/BOOKS/LIBREF/EBT/LIBREF.DAT` on `NOVSDKCD_4.iso`), not from memory.

```c
extern LONG SetHardwareInterrupt(
      BYTE   hardwareInterruptLevel,
      void (*InterruptProcedure)(void),
      LONG   RTag,
      BYTE   endOfChainFlag,
      BYTE   shareFlag,
      LONG  *EOIFlag);   /* Optional: NULL */

extern LONG ClearHardwareInterrupt(
      BYTE   hardwareInterruptLevel,
      void (*InterruptProcedure)(void));
```

Novell's own docs note it was dropped from documentation for SFT III (lockstep mirrored
fault-tolerant NetWare) compliance, since asynchronous interrupts break that product's
determinism guarantees — irrelevant for a plain NetWare 3.11/3.12 target; CLIB.NLM still exports
it, so existing/new NLMs using it keep working.

No dedicated NetWare DMA API was found anywhere in the SDK documentation (the only "DMA" hits are
unrelated, e.g. a LAN-board config string). 8237 DMA controller programming for Sound Blaster is
therefore direct port I/O, same pattern as this project's existing OPL2 driver.

**Mining the SDK ISO**: no `mount`/`7z`/`xorriso` available in the devcontainer without root, but
`pip install pycdlib` into a disposable venv (no root needed) reads the ISO9660 filesystem
directly. Bulk-extracting the whole disc once with `iso.walk()` + `get_file_from_iso()` and then
`grep -r`ing the result is far faster than fetching files one at a time — the DynaText `.DAT`
documentation files under `DOC/ENGLISH/*/BOOKS/*/EBT/*.DAT` are plain text with SGML tags, so
`grep -a` reads them directly without needing the original DynaText viewer. Worth reusing for the
other open research items in [ndk-independence.md](ndk-independence.md) (kernel export list,
`Alloc`/`AllocateResourceTag` signatures, the relinquish-control export).

## Next steps, in order

1. **MVP**: pull doomgeneric source, check its license/vendoring implications, scaffold the
   platform layer (`DG_*` implementations calling into the now-resolved VGA code/`adlib_util.c`),
   resolve the essentials above, boot-test in the QEMU sidecar.
2. **Sound Blaster**: port FastDoom's `ns_sb.c` DSP/mixer logic (already pure port I/O), replace
   its DOS-extender IRQ install (`_dos_setvect`/DPMI) with `SetHardwareInterrupt`/
   `ClearHardwareInterrupt`, hand-roll 8237 DMA programming via direct port I/O.
3. **General MIDI**: likely synchronous register/UART writes similar to OPL2 — no interrupt
   needed, TBD once reached.
4. **LAN support**: deferred; `NWIPXSPX.H` is already among the SDK headers this project uses.
