# NLM toolchain findings (2026-07-19)

Hard-won facts about the `gcc` → `ld -Ur` → `nlmconv` pipeline used here. Established empirically
in-container; read this before debugging NLM crashes or touching the binutils patches in
`.devcontainer/`. The live, dated debugging log is `NOTES.md` (untracked WIP); this file keeps the
durable conclusions.

## The relocation bug (likely root cause of the 2025 abends)

**Every multi-object NLM built between 2025-04-20 and 2026-07-19 contained a corrupted internal
call.** Verified by disassembly (`objdump -d -j .text hello.nlm`): `main`'s call to `putTextChars`
pointed at `main` itself — infinite recursion, one `delay(3000)` pause per loop, until the ring-0
stack overflowed into adjacent memory. NetWare 3.x has no ring-0 guard pages, so the overflow
trashes whatever lies below the stack and the abend flavor varies (GPPE, Invalid TSS with a
garbage selector like `0000CCCC`). The GPPE "on video memory access" (NOTES.md 2025-06-07) and the
Invalid TSS "on graphics mode switch" (README 2025-06-08) most likely were this one bug — the
crash struck at the first cross-object call, which happened to be a vga_util function, so it
*looked* like the video code was at fault. The IOPL/ring-privilege theory was never confirmed and
should be considered unsupported until the fixed toolchain reproduces a failure.

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
  `objdump -d -j .text hello.nlm` and confirm cross-object `call` targets land on the callee
  (compare against `nm` output of the `ld -Ur` intermediate; reproduce that intermediate with
  `ld -Ur -o test.O hello.o vga_util.o /usr/nwsdk/lib/prelude.o && objdump -r test.O`).

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
("symbol delay imported but not in import list") — nlmconv adds the imports anyway. On NetWare
3.x, CLIB.NLM is monolithic; whether it exports these three at load time is confirmed or denied by
the server's load screen (expected to work, unverified). Do not add `MODULE THREADS` for a 3.x
target — there is no separate THREADS.NLM there.

## APIs that do not exist (checked against the whole SDK)

- **`Int68` does not exist** — no header, no `.imp` mentions it (nor `int86` or any
  real-mode-interrupt helper). It originated in an LLM (Gemini) suggestion and only ever compiled
  as an implicit declaration; it would be an unresolved import at load time. The graphics-mode
  switch needs a different mechanism (e.g. direct VGA register programming via `outp`, cf.
  `modes.c`).
- `inp`/`outp`/`delay` have no SDK header declarations either (hence `implicit_nlm_defs.h`); they
  resolve at load time as imports.

## Open questions (unverified — do not state as fact)

- `TYPE 9` in `hello.def` ("Custom device module", a NetWare 4.1x NWPA concept) vs `TYPE 0` on a
  3.11/3.12 target: unknown whether the 3.x loader honors, ignores, or misparses type 9, and CDMs
  conventionally use a `.cdm` extension. The GPPE-on-video-memory fix attributed to "declaring the
  NLM a driver" conflates `TYPE` (module kind) with `OS_DOMAIN` (ring/domain flag); which one (if
  either) actually mattered was never isolated — and the reloc bug above may have been the real
  variable all along.
- Whether `OS_DOMAIN` has any effect on NetWare 3.x (domains were primarily a 4.x feature) is
  unverified.

## Re-baseline plan for the next NetWare boot (after the 2026-07-19 toolchain fixes)

1. Set a real `STACK` value in `hello.def`, rebuild everything with the rebuilt toolchain, and
   confirm via disassembly that internal calls are correct.
2. Boot the plain hello + `putTextChars` NLM *without* touching `TYPE`/`OS_DOMAIN` — expectation:
   the old GPPE/TSS abends do not reproduce.
3. Only then reintroduce the graphics-mode work, one variable at a time.
