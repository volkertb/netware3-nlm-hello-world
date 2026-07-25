# NetWare VM debugging

## Goal

Functional testing of an NLM means booting NetWare and loading it — before this landed, a manual
VM round-trip per iteration (a cycle time that helped stretch the since-resolved 2025 abend saga
to over a year). The goal: a QEMU-based NetWare VM the agent drives end-to-end — send keystrokes,
read the screen, detect crash/hang, reset automatically — while the human keeps a live VNC view,
for fast joint human+agent development. QEMU runs in a **sidecar container**, not the dev
container (`qemu-system-x86` is deliberately absent from the dev image; the QMP client side lives
in the dev image as `vmctl`/`qmp`).

## Status

**2026-07-21, boot-verified**: `vmctl on` boots NetWare 3.12 to a live console prompt
(`HELLO_THERE:`, volume `APPS` mounted, `NW4-IDLE.NLM` loaded) confirmed via QMP `pmemsave` of the
VGA text buffer (see below) — `vmctl off` then `vmctl on` again confirmed a clean stop and a fresh
reboot, with the sidecar container itself staying up across both. Two real bugs surfaced getting
there, both now fixed in `vm-supervisor.sh` (details further down): the accelerator fallback flag,
and the VM's RAM size.

**2026-07-25, boot-verified**: floppy `load`/`eject` (`vmctl floppy load|eject|status`), letting
the agent get a built `floppy.img` into the running VM instead of a human hand-carrying it in.
Confirmed against a live VM: `load` copies the image into `shared/floppy/` and QMP-inserts it
(`query-block` showed the right file, size, and format on `floppy0`); `eject` empties the tray
(`query-block` showed no `inserted` key afterward); `vmctl reset` with the floppy still inserted
booted straight into NetWare from the hard disk, confirming `-boot order=c` actually prevents the
data floppy from being picked up as a boot device. Screendumps (`vmctl screendump`) are now
converted PPM→PNG via `pnmtopng` (netpbm, added to the `dev-env` Dockerfile stage) to get under the
Read tool's 256KB size cap, letting the agent inspect the console directly instead of only
pixel-diffing the raw PPM.

**2026-07-25, boot-verified**: keyboard injection (`vmctl type <text>` / `qmp type <text>`),
closing the gap the floppy entry above left open. `type` is a client-side meta-command (not a real
QMP command) that translates each character into a QMP `send-key` call (QKeyCode names verified
against QEMU 10.0.0's `qapi/ui.json`) and sends them sequentially over one connection. Confirmed
against a live VM with the real end-to-end scenario this whole sidecar exists for: with
`floppy.img` already loaded, `vmctl type $'LOAD A:HELLO.NLM\n'` typed the command at the
`HELLO_THERE:` prompt, and NetWare printed `Loading module HELLO.NLM` followed by the NLM's own
`Hello world!` output — read back via QMP `pmemsave` of the VGA text buffer (see below), not a
screendump, since decoded text is the right tool for a text-mode console. Still open: automatic
hang/crash detection, and everything VNC-related.

What exists now, deliberately scoped down from the full requirements below:

- `.devcontainer/docker-compose.yml` turns the devcontainer into two Compose services: `dev`
  (the existing image) and `qemu` (the sidecar, `.devcontainer/qemu/`). `devcontainer.json`
  points at the compose file instead of building `Dockerfile` directly.
- `qemu/Dockerfile` is **Alpine**, not Debian — no toolchain-parity requirement with the NLM
  build, so `qemu-system-i386` + `socat` is the whole package list.
- The agent controls the VM from the `dev` container via two client commands installed on
  `PATH` (same pattern as `verify-nlm`): `vmctl on|off|reset|status|screendump|floppy` and `qmp
  <command> [key=value ...]` for raw QMP.
- **Still deferred**: VNC (human-facing live view). Has a seam left for it (see below) but wasn't
  part of either slice so far.

### Why a supervisor process, not just QMP

QMP dies the moment QEMU exits, and the agent has no way to restart a sibling container (no
docker/podman inside the dev container) — so QMP alone can't turn a *fully powered-off* VM back
on. `qemu/vm-supervisor.sh` runs as the sidecar's PID 1, outlives QEMU, and reconciles a desired
power state (`/run/vm.state`, set over its own unpublished control port, 4445) against the actual
QEMU process — starting or `quit`-ing it as needed. `vmctl on/off` talks to this port; `vmctl
reset/screendump` go straight to QMP (4444), since QEMU is already running for those to make
sense.

### QMP transport: TCP, deliberately unpublished

`-qmp tcp:0.0.0.0:4444,server=on,wait=off` (verified against qemu.org's docs). Reachable only as
`qemu:4444` on the Compose network `sidecar-net` — the `qemu` service has **no** `ports:` entry
for it. This is a **Compose-file property**, not something enforced at the QEMU/socat level: QMP
has no authentication of its own, so publishing that port would hand VM control to anything that
can reach the host. Chosen over a Unix socket on a shared volume specifically to dodge rootless
Podman UID/permission alignment between the two containers' users — see
[devcontainer.md](devcontainer.md) for other rootless-Podman friction already hit in this repo.
That same reasoning ruled out a named volume for the floppy image below too — it's a host bind
(`../shared:/vm/shared`) for the same UID-alignment reason, not a new decision.

### `qmp`'s client library: `qemu.qmp`

`qmp` (`.devcontainer/qemu/qmp.py`) talks QMP via `qemu.qmp` (PyPI, `qemu/requirements.txt`) — the
QEMU project's own maintained client library, specifically its `legacy.QEMUMonitorProtocol` sync
wrapper — rather than a hand-rolled socket/JSON-framing loop. Installed into an isolated venv
(`/opt/qmp-venv`, `dev-env` Dockerfile stage) since Debian 13's system python3 is PEP 668
"externally managed"; the venv is put on `PATH` ahead of the system python3 so `qmp`'s ordinary
`#!/usr/bin/env python3` shebang resolves there, keeping the script itself free of any
environment-specific path. Landed 2026-07-25; not yet boot-verified (needs a devcontainer rebuild
to pick up the venv, same as any other Dockerfile change here).

### NetWare's console is VGA text, not serial

`-serial file:/vm/shared/logs/serial.log` is wired up, but **stays empty** — NetWare 3.x writes
its console to the VGA text buffer, not the serial line, unless remote console is separately
configured in the guest. `vmctl screendump [name.ppm]` (QMP `screendump`) works with
`-display none` and proves *something* is rendering, but for a text-mode guest it's a bitmap you
have to eyeball or OCR — `pnmtopng` (netpbm, in the `dev-env` Dockerfile) converts the raw PPM to a
PNG small enough for the Read tool's 256KB cap, so the agent can look at it directly rather than
only pixel-diffing. Faster, decodable path used to confirm the verified boot above: QMP
`pmemsave` of the VGA text buffer at physical address `0xB8000` (`753664` decimal), size `4000`
(80×25 cells × 2 bytes: character + attribute) — `qmp pmemsave val=753664 size=4000
filename=/vm/shared/logs/vgatext.bin`, then read every even byte as a character. VNC (deferred)
will give the human a live equivalent of either.

### Two real bugs found getting the first boot working (2026-07-21)

- **`-accel kvm:tcg` doesn't exist as a standalone flag** — QEMU rejected it outright:
  `invalid accelerator kvm:tcg`. The colon-separated fallback list is real, but it's a `-machine`
  property (`-machine pc,accel=kvm:tcg`; qemu-options.hx: `accel=accel1[:accel2[:...]]`) — the
  standalone `-accel` flag takes exactly one accelerator name per occurrence. A doc-fetch
  described the `-machine` property's behavior and got misapplied to the wrong flag; confirmed
  correct by reading the option's actual `DEF(...)` string in qemu-options.hx instead of trusting
  a summarized fetch. Only diagnosable at all because QEMU's own stdout/stderr is redirected into
  `shared/logs/qemu-stdouterr.log` — the dev container has no `podman`/`docker` access to read
  the sidecar's container log directly.
- **`-m 64` (more RAM than the source VM) broke NetWare's own loader**: `Insufficient memory to
  run NetWare 386 (requires at least 3 megabytes of extended memory)`, despite 64MB being far
  more than 3MB — a DOS-era memory-detection quirk, not a real shortfall (root cause not chased
  further). Fixed by matching the confirmed-working VirtualBox VM's RAM exactly (`-m 16`) instead
  of guessing QEMU values.

### Seam left for VNC

Add `-vnc :0` (or similar) to the `qemu-system-i386` invocation in `vm-supervisor.sh`, then
*deliberately* publish that port in `docker-compose.yml` — the one port meant to reach the host,
unlike QMP/4445 above.

### Floppy load/eject (2026-07-22)

`vmctl floppy load [image]` copies a built image (default: the repo-root `floppy.img`) into
`shared/floppy/` — the same host-bind pattern `shared/logs/` already used, now generalized to
`../shared:/vm/shared` with `logs`/`floppy` subdirs, rather than mounting the repo into `qemu` or
introducing a named volume (ruled out above for the same rootless-Podman UID reason as the QMP
transport choice). It then inserts the copy over QMP. `vmctl floppy eject`/`status` round out the
verb set.

The recipe, verified against **QEMU 10.0.0 source** (the version Alpine 3.22 ships) rather than
docs summaries, since the accelerator-flag bug above was originally caused by exactly that kind of
summarized-fetch mistake:

- **Boot with an empty floppy tray**: `-device floppy,id=floppy0`, no `drive=`. In
  `hw/block/fdc.c`, `floppy_drive_realize()` falls back to `blk_create_empty_drive()` when no
  backend is given — a real, addressable, empty tray. The `pc` machine already instantiates the
  ISA FDC by default (`hw/i386/pc.c`, `pc_superio_init()`: `create_fdctrl = !no_floppy`, true for
  `pc`), so the device has a bus to attach to without any other machine changes.
- **Insert**: QMP `blockdev-change-medium id=floppy0 filename=/vm/shared/floppy/<img>
  format=raw` — not deprecated in 10.0 (`qapi/block.json`).
- **Eject**: QMP `eject id=floppy0` — also not deprecated; succeeds even on an already-empty tray.
- **`-boot order=c`** added alongside this so an inserted (non-bootable) data floppy can never get
  picked up as a boot device on a `vmctl reset` — NetWare boots from the IDE disk regardless of
  what's in the floppy drive.

Boot-verified 2026-07-25: `load`/`eject`/`status` round-tripped correctly against a live VM, and a
`reset` with the floppy inserted still booted from disk, confirming the `-boot order=c` hardening.
NetWare reading the inserted floppy (`LOAD A:HELLO.NLM`) is now confirmed too, via `vmctl type` —
see "Keyboard injection" below.

### Keyboard injection (2026-07-25)

`vmctl type <text>` / `qmp type <text>` — not a real QMP command, a client-side meta-command that
translates each character of `<text>` into one QMP `send-key` call and sends them sequentially over
a single connection (`send-key`'s own `keys` array is for simultaneous chords, e.g.
ctrl+alt+delete, not a way to type a string in one call). QKeyCode names (`a`-`z`, `0`-`9`, `spc`,
`dot`, `semicolon`, `ret`, ...) verified against **QEMU 10.0.0**'s `qapi/ui.json`, not a docs
summary. Uppercase and shifted punctuation (e.g. `:` = shift+`semicolon`) send `shift` alongside
the base key. A literal `\n` in `<text>` sends `ret` (Enter).

Boot-verified 2026-07-25 with the actual end-to-end scenario this sidecar exists for: with
`floppy.img` already loaded (see above), `vmctl type $'LOAD A:HELLO.NLM\n'` typed the command at
the `HELLO_THERE:` prompt, and NetWare responded with `Loading module HELLO.NLM` followed by the
NLM's own `Hello world!` output. Read back via QMP `pmemsave` of the VGA text buffer (see "NetWare's
console is VGA text, not serial" above) rather than a screendump — decoded text is the right tool
to verify a text-mode console, not a bitmap.

## Requirements (as stated by the user, 2026-07-19)

Done: the sidecar-container decision, screen reads (`pmemsave`/`screendump`) plus generic QMP
passthrough for debugging, and keyboard injection (`vmctl type`/`qmp type`). Still open: automatic
hang detection (`vmctl status` only checks the process is alive, not that the guest is responsive),
and everything VNC-related.

- A QEMU instance running a NetWare 3.x VM, spun up alongside the devcontainer as a sidecar
  container (decided; see "Other `devcontainer.json` settings" in [devcontainer.md](devcontainer.md)
  — the `/dev/kvm` `runArgs` passthrough moved to the sidecar's Compose service).
- A separate, agent-usable control channel to inject keyboard input, read the screen
  buffer/contents, perform debugging operations, and detect/recover from crashes or hangs.
- VNC access for the human — not just passive viewing: full interactive keyboard/mouse control of
  the VM, usable concurrently with the agent's own control channel, so the human can drive the
  VM directly or intervene mid-session without needing to tear down or reconfigure anything first.
- A helper script/instructions so the human's VNC viewer starts *before* QEMU itself, then
  auto-connects the moment QEMU comes up — and auto-reconnects after every reboot/reset.
- Text-mode/console output logged to a file as well (`-serial file:` is wired up but, per above,
  stays empty for this guest — `pmemsave`/`screendump` are the real path until VNC lands).

## Existing groundwork already in place

- `/dev/kvm` passthrough now lives on the `qemu` Compose service (`docker-compose.yml`), not
  `dev` — see [devcontainer.md](devcontainer.md).
- `README.md` has links for manually installing/running NetWare 3.12 in a VM (VirtualBox-based) —
  useful as an install/config reference even though the target here is QEMU. The current
  `vm-images/netware-3x.qcow2` was itself converted from a confirmed-working VirtualBox VDI.
- Worth doing in the NLM *before* relying on automation for graphics-mode tests: restore 80×25
  text mode before exiting (e.g. `set_text_mode()` in `modes.c`, or reprogram the registers back).
  After a graphics-mode test the server only *looks* hung — the console keeps running and writing
  to the invisible text buffer (observed 2026-07-19) — but without the restore, every automated
  graphics test would end in a VM reset instead of a clean next iteration. Not yet done; matters
  now that `vmctl floppy load` (above) can get a graphics-mode test onto the VM.

## Considered and rejected: Vagrant

Vagrant (managed from inside the dev container) was weighed against the sidecar and rejected — its
value-add doesn't apply here, and it hides the interface the agent needs:

- Vagrant's lifecycle machinery assumes a *cooperative guest* it can SSH/WinRM into to provision,
  key, and detect "booted." NetWare 3.x has none of that, so it'd run with `communicator: none`,
  synced folders off, and boot-timeout hacks — i.e. most of Vagrant disabled, used as a bare
  "launch this disk" wrapper. No NetWare box exists either, so the box ecosystem is moot.
- Vagrant doesn't expose QMP — the exact channel this loop is built on (keystroke injection,
  screendump, `system_reset`). Its providers spawn QEMU/libvirt themselves without handing back a
  stable QMP socket, so the agent would reach *around* Vagrant straight to QEMU anyway.
- Vagrant manages a *local* provider, so it implies the VM running inside the dev container
  (libvirt/vagrant-qemu; VirtualBox-in-a-container isn't realistic) — reintroducing exactly what
  the sidecar decision rejected (`qemu-system-x86` back in the lean dev image, plus `libvirtd` and
  a Ruby/Vagrant stack), on the under-trodden Vagrant + rootless-Podman + nested-container path.

The sidecar keeps the QEMU command line (period-correct `-machine`/`-cpu`/NIC, `-qmp`, `-vnc`,
`-serial file:`) under direct control, gives two reset primitives (QMP `system_reset` plus a
container restart for a wedged VM), and stays reproducible via a Compose service — the declarative
benefit a `Vagrantfile` would offer, without the extra runtime.

## QMP/QEMU facts, verified against qemu.org before implementing

- Commands used: `system_reset`, `quit` (VM power-off — not graceful; NetWare 3.x is pre-ACPI, so
  `system_powerdown` would be a no-op on this guest), `screendump`, `pmemsave`, `send-key`
  (keystrokes, wired into `vmctl type`/`qmp type` — see "Keyboard injection" above).
- `-qmp tcp:HOST:PORT,server=on,wait=off` opens a QMP TCP listener without blocking VM boot on a
  client connecting (`server,nowait` is the older, equivalent spelling).
- `-serial file:PATH` logs the serial line to a file — see the VGA-not-serial caveat above for why
  this alone doesn't give console output for this guest.
- Accelerator fallback is a `-machine` property, not the standalone `-accel` flag — see "Two real
  bugs" above.
- `-device floppy,id=<id>` with no `drive=` boots an empty, addressable removable drive;
  `blockdev-change-medium`/`eject` (QMP) insert/remove media at runtime — verified against QEMU
  10.0.0 source (`hw/block/fdc.c`, `hw/i386/pc.c`, `qapi/block.json`), not a docs summary — see
  "Floppy load/eject" above.

How to make the VNC viewer reliably auto-connect on startup and auto-reconnect after a reset (a
fixed/predictable address, a wrapper script that retries/polls, some other mechanism) is still an
open implementation question for when that work starts.
