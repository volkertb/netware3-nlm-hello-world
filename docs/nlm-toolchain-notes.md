# NLM toolchain findings (2026-07-19)

Hard-won facts about the `gcc` → `ld -Ur` → `nlmconv` pipeline. Established empirically
in-container; read this before debugging NLM crashes or touching the binutils patches in
`.devcontainer/`. The dated debugging log is `NOTES.md` (untracked WIP); this file keeps the
durable conclusions.

## The relocation bug (root cause of the 2025 abends — confirmed and closed)

**Every multi-object NLM built between 2025-04-20 and 2026-07-19 contained a corrupted internal
call**: `main`'s call to `putTextChars` pointed at `main` itself (verified by disassembly) —
infinite recursion until the ring-0 stack overflowed into adjacent memory. NetWare 3.x has no
ring-0 guard pages, so the abend flavor varied (GPPE, Invalid TSS with garbage selectors like
`0000CCCC`). The 2025 "video memory access" GPPE and "graphics mode switch" TSS abends were this
one bug — it struck at the first cross-object call, which happened to be a vga_util function, so
the video code *looked* guilty.

Mechanism, two layers:

1. **Upstream nlmconv bug** (`i386_mangle_relocs`): when resolving PC-relative relocs against
   defined symbols (the NLM format has no PC-relative internal fixup), it subtracted the
   *input-section-relative* site address instead of the output-section one — every displacement
   short by the input section's `output_offset`. Harmless in the 1990s (all code in one `.text`
   at offset 0); fatal once gcc ≥ 4.6 put `main` in a separate `.text.startup` section. Fixed in
   the `.devcontainer/nlmconv.c` fork (`addend -= rel->address`).
2. **A 2025-04-20 fork of `bfd/nlm32-i386.c` disabled the safety net** — the check that rejects
   unresolvable PC-relative internal relocs ("Invalid operation", the historical build blocker).
   The actual trigger was gcc's `.eh_frame`: PC32 records against `.text` from a data section,
   genuinely unrepresentable in the NLM format. Disabling the check made builds "succeed" while
   writing load-time-corrupting fixups. The check is restored; `.eh_frame` is suppressed at the
   source with `-fno-asynchronous-unwind-tables` in every CFLAGS (NetWare never reads it; period
   compilers didn't emit it).

**Closure, 2026-07-19, two boots of NetWare 3.12 in a VM:** both NLMs run end-to-end, including
`helloold.nlm`'s 320×200 VGA switch via direct register programming — the exact operation that
used to abend ([screenshot](images/netware312-vga-mode13h-2026-07-19.png); the pixel noise is old
text-buffer data reinterpreted as pixels — success, nothing clears VRAM yet). Direct video memory
access (`0xA0000`/`0xB8000`) and `inp`/`outp` all work from a plain NLM; the IOPL theory is dead.
Nothing from the 2025 saga remains open. Anything that passes `verify-nlm` but misbehaves on
NetWare is, by construction, not this bug class.

**Rules that follow:**

- `-fno-asynchronous-unwind-tables` is mandatory in CFLAGS for anything fed to nlmconv.
- Never disable checks in `nlm_i386_write_import`: if it errors, the input contains something the
  NLM format can't express — fix the input.
- **`verify-nlm <file.nlm> <file.def>`** (from `.devcontainer/verify_nlm.py`; run in the build
  directory so the `.def`'s INPUT paths resolve) is the automated gate, run by `make` and by the
  Dockerfile's sample build: it re-runs nlmconv's `-Ur` pre-link, replicates its image-layout
  math, and byte-verifies every relocation site plus the signature and STACK header field. If it
  reports a *layout replication mismatch*, its model of nlmconv has drifted — fix the script
  before trusting anything else it says. Manual spot-check, if ever needed:
  `i386-netware-objdump -d -j .text hello.nlm` and confirm cross-object `call` targets hit their
  callees (callee addresses via `nm` on an `i386-netware-ld -Ur` intermediate of the same inputs).
- Tool naming: the binutils-2.30 tools are `nlmconv`, `i386-netware-ld`, `i386-netware-objdump` —
  cross-style names so they can't shadow host tools (see devcontainer.md for the breakage that
  motivated this). `i386-netware-objdump` is the only objdump that reads `nlm32-i386` files; the
  host objdump handles the ELF intermediates. nlmconv finds `i386-netware-ld` by itself (fork's
  `LD_NAME` default); no Makefile passes `-l`.

## Watch list: modern-gcc landmines that have NOT bitten yet (predictions, not verified)

The `.eh_frame` story generalizes: gcc defaults postdating NetWare can inject things the NLM
pipeline can't handle. Check these first when a bigger NLM misbehaves despite clean `verify-nlm`:

- `-fstack-protector-strong` (Debian default) triggers on arrays/large locals and references
  `__stack_chk_fail`/`__stack_chk_guard` → unresolved imports at load. Remedy:
  `-fno-stack-protector`.
- `-fcf-protection` emits an allocatable `.note.gnu.property` section → junk in the NLM data
  image. Remedy: `-fcf-protection=none`.
- gcc ≥ 14 makes implicit function declarations hard errors; vintage sources may need
  `-std=gnu89`.
- nlmconv leaves a partial output `.nlm` behind on failure — judge success only by exit status
  (the `verify-nlm` make step already enforces this).

## `.def` numbers and `STACK`

Stock nlmconv treats a malformed number (e.g. `STACK bladiebla`) as a warning, exits 0, and
silently stores strtol's fallback 0 in the header. Patched to a fatal error
(`.devcontainer/patches/0001-nlmheader-bad-number-is-an-error.patch`; covers `nlmheader.y` and
the shipped bison-generated `nlmheader.c`, so bison isn't needed).

- Stack-size field: file offset 164, little-endian u32
  (`hexdump -s 164 -n 4 -e '1/4 "%u\n"' hello.nlm`).
- Omitting `STACK` also yields 0 — nlmconv has no default. Historical builds all shipped 0 and
  NetWare 3.12 ran them anyway (loader minimum or CLIB-thread stacks — unverified which). Set a
  real value regardless.
- Sizing: `STACK` covers only stack frames — heap (`malloc`/`Alloc`) and globals don't go through
  it. Size for the deepest call chain plus large on-stack buffers, and err large: no ring-0 guard
  pages means overflow corrupts silently with delayed, misleading abends. `hello.def` uses
  `STACK 131072` (128 KiB) — ample even for a large (1–4 MB working set) application, negligible
  on period hardware. Bump further if code puts big scratch buffers on the stack.

## Imports: the SDK is NetWare 4.11-vintage, the target is 3.x

The `.imp` files were generated (by Hinner's free `nlmimp`) from NetWare 4.11 NLMs, where CLIB
was split — so `delay`/`inp`/`outp` live in `threads.imp`, not `clib.imp`, and importing only
`@clib.imp` produces "imported but not in import list" warnings. Harmless, confirmed 2026-07-19:
3.12's monolithic CLIB.NLM resolves them at load time. Do not add `MODULE THREADS` for a 3.x
target — no separate THREADS.NLM exists there.

## APIs that do not exist (checked against the whole SDK)

- **`Int68`** — no header or `.imp` mentions it (nor `int86` or any real-mode-interrupt helper);
  it came from an LLM (Gemini) hallucination and would be an unresolved import. The working
  mechanism for mode switching is direct VGA register programming via `outp` (`vgamode.c`'s
  `init_graph_vga`, boot-confirmed).
- `inp`/`outp`/`delay` have no SDK header declarations (hence `implicit_nlm_defs.h`); they
  resolve at load time as imports.

## `TYPE 9` / `OS_DOMAIN`: not needed (resolved 2026-07-19, second boot test)

`hello_old.def` with `TYPE 0` and `OS_DOMAIN` commented out behaves identically
([screenshot](images/netware312-vga-mode13h-type0-no-osdomain-2026-07-19.png)) — both settings
were dead weight from the 2025 misdiagnosis. Use `TYPE 0` for ordinary NLMs. Why `OS_DOMAIN`
changes nothing: NetWare 3.x runs every NLM in ring 0 in one unprotected address space;
protected domains (ring-3 loading via DOMAIN.NLM, which the flag opts out of) are a NetWare 4.x
feature, so on 3.x there is nothing to opt out of. (Inference from feature history plus observed
equivalence — not verified against Novell loader docs; moot in practice.)
