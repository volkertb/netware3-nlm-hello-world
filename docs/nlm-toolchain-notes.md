# NLM toolchain findings (2026-07-19)

Hard-won facts about the `gcc` → `ld -Ur` → `nlmconv` pipeline used here. Established empirically
in-container; read this before debugging NLM crashes or touching the binutils patches in
`.devcontainer/`. The live, dated debugging log is `NOTES.md` (untracked WIP); this file keeps the
durable conclusions.

## The relocation bug (root cause of the 2025 abends — confirmed)

**Every multi-object NLM built between 2025-04-20 and 2026-07-19 contained a corrupted internal
call.** Verified by disassembly (`i386-netware-objdump -d -j .text hello.nlm`): `main`'s call to `putTextChars`
pointed at `main` itself — infinite recursion, one `delay(3000)` pause per loop, until the ring-0
stack overflowed into adjacent memory. NetWare 3.x has no ring-0 guard pages, so the overflow
trashes whatever lies below the stack and the abend flavor varies (GPPE, Invalid TSS with a
garbage selector like `0000CCCC`). The GPPE "on video memory access" (NOTES.md 2025-06-07) and the
Invalid TSS "on graphics mode switch" (README 2025-06-08) were this one bug — the crash struck at
the first cross-object call, which happened to be a vga_util function, so it *looked* like the
video code was at fault.

**Closure, 2026-07-19: fix confirmed by booting NetWare 3.12 in a VM.** Both NLMs load and run
end-to-end: `hello.nlm` prints, writes the text buffer, exits cleanly; `helloold.nlm` additionally
switches to 320×200 VGA graphics via direct register programming (`vgamode.c`) — the exact
operation that used to abend
([screenshot](images/netware312-vga-mode13h-2026-07-19.png); the pixel noise is leftover text-buffer
data reinterpreted as pixels, i.e. the switch worked and nothing cleared VRAM). The IOPL/ring-privilege
theory is dead: mode switching and port I/O work. Direct video memory access (`0xA0000`/`0xB8000`)
and `inp`/`outp` all function from an NLM. A second boot the same day with `TYPE 0` and no
`OS_DOMAIN` in `hello_old.def` behaved identically
([screenshot](images/netware312-vga-mode13h-type0-no-osdomain-2026-07-19.png)), so **neither
`TYPE 9` nor `OS_DOMAIN` is needed** for VGA register/memory access on 3.12 — plain `TYPE 0` NLMs
have full hardware access.

Mechanism, two layers deep:

1. **Upstream nlmconv bug** (`binutils/nlmconv.c`, `i386_mangle_relocs`): it resolves PC-relative
   relocs against defined symbols itself (the NLM format has no PC-relative internal fixup), but
   subtracted the *input-section-relative* site address instead of the output-section one, leaving
   every displacement short by the input section's `output_offset`. Harmless in the 1990s when all
   code sat in one `.text` at offset 0 — but gcc ≥ 4.6 places `main` in a separate `.text.startup`
   section (offset 0xC0 here), so `main`'s outgoing calls all missed by 0xC0. Fixed in the
   `.devcontainer/nlmconv.c` fork (`addend -= rel->address` instead of `addend -= address`).
2. **A 2025-04-20 fork of `bfd/nlm32-i386.c` disabled the safety net.** Pristine nlmconv rejects
   PC-relative internal relocs it cannot resolve ("Invalid operation" — the historical build
   blocker). The real trigger was gcc's `.eh_frame` section: PC32 records pointing at `.text` from
   a *data* section, genuinely unrepresentable in the NLM format. Commenting out the check made
   the build "succeed" while writing load-time-corrupting fixups. The check is now restored (with
   an actionable error message), and `.eh_frame` is suppressed at the source with
   `-fno-asynchronous-unwind-tables` in every CFLAGS (repo `Makefile` + both Dockerfile sample
   builds). NetWare never reads `.eh_frame`; period compilers didn't emit it.

**Rules that follow:**

- `-fno-asynchronous-unwind-tables` is mandatory in CFLAGS for anything fed to nlmconv.
- Never disable checks in `nlm_i386_write_import`; if it errors, the input contains something the
  NLM format can't express — fix the input.
- After any toolchain change, verify internal calls before booting: build, then
  `i386-netware-objdump -d -j .text hello.nlm` and confirm cross-object `call` targets land on
  the callee (compare against `nm` output of the `ld -Ur` intermediate; reproduce that
  intermediate with
  `i386-netware-ld -Ur -o test.O hello.o vga_util.o /usr/nwsdk/lib/prelude.o && objdump -r test.O`).
- All of that verification is automated by **`verify-nlm <file.nlm> <file.def>`** (installed from
  `.devcontainer/verify_nlm.py`; run it from the build directory so the `.def`'s INPUT paths
  resolve). It re-runs nlmconv's `-Ur` pre-link, replicates its image-layout math, and
  byte-verifies every relocation site in the finished NLM (internal PC-relative, internal
  absolute, and import placeholders), plus the signature and STACK header field. The Dockerfile
  runs it against the dev-env sample build, so a toolchain regression of the 2025 class fails the
  image build itself. If it ever reports a *layout replication mismatch*, the script's model of
  nlmconv has drifted — fix the script before trusting anything else it says.
- Tool naming: the binutils-2.30 tools are installed as `i386-netware-ld` and
  `i386-netware-objdump` (plus `nlmconv` itself) — cross-tool-style names so they can never
  shadow the host toolchain (gas 2.30 shadowing the host `as` broke Debian 13 builds with
  `--gdwarf-5`; see docs/devcontainer.md). `i386-netware-objdump` is the only objdump that still
  reads `nlm32-i386` files — the host objdump cannot dump NLMs, only the ELF `.o`/`.O`
  intermediates. nlmconv finds `i386-netware-ld` by itself (its fork's `LD_NAME` default, sibling
  directory or PATH); no Makefile needs to pass `-l`.

## nlmconv `.def` parsing: bad numbers

Stock binutils-2.30 nlmconv treats a malformed number (e.g. `STACK bladiebla`) as a *warning*
("`hello.def:26: bad number`"), exits 0, and stores `strtol`'s fallback — so the header field
silently becomes 0. Patched to a fatal error via
`.devcontainer/patches/0001-nlmheader-bad-number-is-an-error.patch` (patches both `nlmheader.y`
and the shipped bison-generated `nlmheader.c`, so bison isn't needed).

Related facts:

- The NLM header's stack-size field sits at file offset 164 (little-endian u32):
  `hexdump -s 164 -n 4 -e '1/4 "%u\n"' hello.nlm`.
- Omitting `STACK` entirely also yields 0 — nlmconv applies no default. All historical builds of
  this project shipped stack size 0 and NetWare 3.12 loaded and ran them anyway, so the loader
  evidently tolerates it (own minimum, or CLIB threads bring their own stacks — unverified which).
  Still, set a real value rather than relying on that.

### Sizing `STACK`

`STACK` sizes only the stack — heap allocations (`malloc`/`Alloc`) come from NetWare's memory
pools at runtime, and globals live in `.data`/`.bss`, so an application's overall RAM footprint
(even megabytes) does not go through this number. What does: the deepest call chain's stack
frames, dominated by any large on-stack buffers/arrays.

Size it generously: NetWare 3.x ring-0 stacks have no guard pages, so overflow silently corrupts
adjacent memory and produces delayed, misleading abends (exactly the failure class of the 2025
debugging saga). `hello.def` uses `STACK 131072` (128 KiB) — far above the CLIB-era 8–16 KiB
defaults, ample for deep call chains and large locals even in a fairly big (1–4 MB working set)
application, and negligible on a machine with megabytes of RAM. Bump it further if code ever
puts big scratch buffers on the stack (e.g. a 64 KiB buffer as a local); going to 256 KiB costs
nothing meaningful, whereas undersizing is catastrophic and hard to diagnose.

## Imports: this SDK is NetWare 4.11-vintage, the target is 3.x

The `.imp` files under `/usr/nwsdk/imports/` were generated from NetWare 4.11 NLMs, where CLIB was
split (CLIB/THREADS/NLMLIB/…). `delay`, `inp`, `outp` therefore live in `threads.imp`, not
`clib.imp`. A `.def` that imports only `@clib.imp` gets nlmconv warnings
("symbol delay imported but not in import list") — nlmconv adds the imports anyway, and they are
harmless: **confirmed 2026-07-19** — both NLMs import only `@clib.imp` and NetWare 3.12's
monolithic CLIB.NLM resolved `delay`/`inp`/`outp` at load time. Do not add `MODULE THREADS` for a
3.x target — there is no separate THREADS.NLM there.

## APIs that do not exist (checked against the whole SDK)

- **`Int68` does not exist** — no header, no `.imp` mentions it (nor `int86` or any
  real-mode-interrupt helper). It originated in an LLM (Gemini) suggestion and only ever compiled
  as an implicit declaration; it would be an unresolved import at load time. Direct VGA register
  programming via `outp` is the working mechanism (`vgamode.c`'s `init_graph_vga`, confirmed on
  NetWare 3.12).
- `inp`/`outp`/`delay` have no SDK header declarations either (hence `implicit_nlm_defs.h`); they
  resolve at load time as imports.

## `TYPE 9` / `OS_DOMAIN`: not needed (resolved 2026-07-19, second boot test)

`hello_old.def` with `TYPE 0` and `OS_DOMAIN` commented out loads and switches to graphics mode
exactly as before — so neither setting is needed for hardware access, and both were dead weight
from the 2025 misdiagnosis (the reloc bug was the real variable all along). Use `TYPE 0` for
ordinary NLMs. On why `OS_DOMAIN` made no difference: NetWare 3.x runs every NLM in ring 0 in a
single unprotected address space; protected domains (ring-3 loading via DOMAIN.NLM, which the
`OS_DOMAIN` header flag opts out of) are a NetWare 4.x feature, so on 3.x the flag has nothing to
opt out of and is presumably ignored by the loader. (Inference from feature history plus the
identical observed behavior — not verified against Novell loader documentation; it doesn't
matter in practice now.)

## Re-baseline (completed 2026-07-19)

The post-fix re-baseline plan was executed the same day: real `STACK` values set, everything
rebuilt on the fixed toolchain, `verify-nlm` clean, and both NLMs boot-tested on NetWare 3.12 —
no abends, graphics mode switch works, and the `TYPE 9`/`OS_DOMAIN` variable was isolated the
same day (see above: not needed). Nothing from the 2025 saga remains open. Future regressions
should be caught by `verify-nlm` at build time; anything that passes it but still misbehaves on
NetWare is, by construction, not the 2025 relocation-corruption class.
