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

Boot-verified end to end: boot/shutdown (2026-07-21), floppy `load`/`eject` (2026-07-22), keyboard
injection (2026-07-25), VNC (2026-07-25) — recipes and verification detail live in each feature's
own `###` section below, not repeated here. Still open: automatic hang/crash detection (`vmctl
status` only checks the process is alive, not that the guest is responsive).

What exists now, deliberately scoped down from the full requirements below:

- `.devcontainer/docker-compose.yml` turns the devcontainer into two Compose services: `dev`
  (the existing image) and `qemu` (the sidecar, `.devcontainer/qemu/`). `devcontainer.json`
  points at the compose file instead of building `Dockerfile` directly.
- `qemu/Dockerfile` is **Alpine**, not Debian — no toolchain-parity requirement with the NLM
  build, so `qemu-system-i386` + `socat` + `novnc` is the whole package list.
- The agent controls the VM from the `dev` container via two client commands installed on
  `PATH` (same pattern as `verify-nlm`): `vmctl on|off|reset|status|screendump|floppy|type|vnc`
  and `qmp <command> [key=value ...]` for raw QMP.

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
"externally managed".

`qmp.py`'s shebang points directly at `/opt/qmp-venv/bin/python3` (absolute path), same as pip's
own generated shebangs for `ruff`/`pylint`/`pip-audit`. An earlier version tried keeping the
shebang as a plain `#!/usr/bin/env python3` with the venv prepended onto `PATH` instead, which
turned out unreliable: shells that source `/etc/profile` (Debian's own, shipped by the base
image) reset `PATH` from scratch, discarding this image's `ENV PATH` before `qmp` ever runs — the
absolute shebang is self-contained at exec time regardless of which shell invokes it.

Boot-verified 2026-07-25: `qmp query-status` and everything built on it (`pmemsave`, `type`,
`vnc`) work cleanly post-rebuild, confirming the absolute shebang resolves correctly.

### NetWare's console is VGA text, not serial

`-serial file:/vm/shared/logs/serial.log` is wired up, but **stays empty** — NetWare 3.x writes
its console to the VGA text buffer, not the serial line, unless remote console is separately
configured in the guest.

**When the guest is in text mode, `pmemsave` is the preferred read, not `screendump`.** QMP
`pmemsave` of the VGA text buffer at physical address `0xB8000` (`753664` decimal), size `4000`
(80×25 cells × 2 bytes: character + attribute) — `qmp pmemsave val=753664 size=4000
filename=/vm/shared/logs/vgatext.bin`, then read every even byte as a character — gives exact
characters directly: no image tokens, no OCR, no risk of misreading a rendered bitmap. This is
what confirmed the verified boot above.

That's conditional on actually being in text mode, though, and the agent can't always be certain
of that. A graphics-mode NLM test leaves the guest only *looking* hung afterward (see "Existing
groundwork" below): the console keeps running, but the display has switched away from text mode,
so the VGA text buffer stops being actively written — `pmemsave`-ing `0xB8000` in that state would
silently return stale or meaningless bytes, with no signal that the read is bad.

**Detect the mode first, cheaply, via `screendump`'s own output dimensions — no QOM/QMP mode query
exists, but this doesn't need one.** Verified against QEMU 10.0.0 source: `vga_draw_text()` and
`vga_draw_graphic()` (`hw/display/vga.c`) each call `qemu_console_resize()` with the *actual
current* mode's dimensions on every redraw, so the console's `DisplaySurface` genuinely tracks live
VGA mode. `qmp_screendump()` (`ui/ui-qmp-cmds.c`) forces a fresh redraw (`qemu_console_co_wait_
update()`) and *then* reads that just-resized surface — so a screendump's PPM header
(`P6\n<width> <height>\n255\n`, its first ~15 bytes) is a live, accurate mode signal, not a guess.
This project's observed text-mode dump is 720×400; mode 13h graphics would be 320×200. (A QOM
property or dedicated QMP command for this was checked for and doesn't exist — `hw/display/
vga-pci.c`'s only properties are static config (`vgamem_mb`, `mmio`, `qemu-extended-regs`, `edid`,
`global-vmstate`, `big-endian-framebuffer`), and neither `qapi/ui.json`/`machine.json`/`misc.json`
nor the HMP `info` command table (`hmp-commands-info.hx`) expose the device's internal
`graphic_mode` state.)

The resulting pattern: `vmctl screendump` first, read just the PPM header to determine mode, then
either trust the already-fetched screendump (`pnmtopng` → PNG, small enough for the Read tool's
256KB cap) if it's graphics, or follow up with `pmemsave` of `0xB8000` if it's confirmed text —
cheaper and more decodable than a bitmap once mode is actually known. VNC (`vmctl vnc`, see below)
gives the human a live equivalent of either, continuously.

This isn't only a "which read tool" decision, either. Whenever a mode switch is itself the
functionality under test — an NLM that's supposed to switch into a particular graphics mode, for
instance — the same header read is a precise, cheap pass/fail: compare the observed
`width`×`height` against the resolution that mode is supposed to produce (e.g. 320×200 for mode
13h), rather than eyeballing a rendered image to guess whether the switch actually took effect.

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

### VNC (2026-07-25)

`vmctl vnc` prints a URL for the human to open on the Docker/Podman **host's** own browser — not
reachable from inside the dev container itself:

```
http://localhost:6080/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=2000
```

**Copy/paste this URL into the browser rather than clicking it in an agent chat UI** (boot-verified
gotcha, 2026-07-25): a coding agent's chat interface running inside this devcontainer may rewrite
the *link target* for a detected `localhost:PORT` URL to route through its own port-forwarding
(scoped to the primary `dev` container, where nothing listens on 6080 - it's published on the
actual Docker/Podman host, not `dev`) while leaving the *displayed text* as the original URL, so
the link visibly reads `localhost:6080` but actually points somewhere else and fails
(`NS_ERROR_NET_EMPTY_RESPONSE` in Firefox). Copy/paste bypasses whatever that rewriting is and
hits the host's own loopback directly, which is where the published port actually is - confirmed
working that way. The exact rewriting mechanism is inferred by analogy to VS Code's own
remote-port-forwarding link rewriting, not confirmed against the specific tool's internals.

**Browser-based (noVNC), not a native VNC viewer.** Alpine's `novnc` package (`community`,
confirmed via aports) bundles noVNC's static web client + `websockify` behind one launcher,
`novnc_server` (upstream's `utils/novnc_proxy`, confirmed from the noVNC v1.6.0 source this
package installs). One process serves the web UI *and* proxies WebSocket↔raw-VNC — no native
viewer install needed on the host, and it works the same from VS Code, JetBrains, or a
browser-based client.

**Raw VNC never leaves the container.** `qemu-system-i386` gets `-vnc 127.0.0.1:0` (port 5900,
per QEMU's `host:d` → `5900+d` syntax, `qemu-options.hx`) — loopback-only *inside* the `qemu`
container, so nothing on `sidecar-net` can reach the unauthenticated VNC protocol directly.
`novnc_server`, in the same container, is the only thing that connects to it; its own port (6080)
is the one thing published, bound to the Docker/Podman **host's** loopback interface
(`127.0.0.1:6080:6080` in `docker-compose.yml`) — same "network boundary is the control, no
password/TLS configured" reasoning as QMP's unpublished ports. On Docker Desktop (macOS/Windows),
where containers run inside an internal VM, whether that loopback binding is enforced all the way
through to the real host's network stack is unconfirmed — verify empirically on that platform
rather than assume it behaves like native Linux Docker/Podman.

**Starts before QEMU, reconnects on its own.** `novnc_server` starts once, unconditionally, in
`vm-supervisor.sh`'s `run)` mode — not gated on the VM's on/off state, so the page stays reachable
(just failing to connect) even while the VM is off. A connection attempt against a not-yet-up QEMU
just fails; noVNC's own client-side `reconnect`/`reconnect_delay` query params (confirmed real,
current `vnc.html` features via noVNC's `docs/EMBEDDING.md`) retry with no extra scripting needed.
This satisfies the original "starts before QEMU, auto-connects when it comes up, auto-reconnects
after every reset" requirement for free.

**No VNC password/TLS**, and **no `-device usb-tablet`** — that device needs a guest USB stack
(confirmed against QEMU's own USB docs) for absolute mouse positioning, and DOS/NetWare 3.x guests
predate USB entirely, so it'd be dead configuration for this project's actual guest OS.

**Forward-looking, not yet used: `vmport=on`.** A `-machine` property that makes the `pc` machine
auto-create and wire up a `vmmouse` PS/2 device — verified against QEMU 10.0.0 source:
`hw/i386/pc.c`'s `pc_superio_init()` creates `TYPE_VMPORT` + `"vmmouse"` and links it to the
i8042 controller whenever vmport is enabled, no separate `-device` flag needed. Unlike
`usb-tablet`, this is a legacy PS/2-port protocol extension a period-correct DOS driver can use
directly. Not wired up to anything guest-side yet, but there for when a driver like
[vbados's VBMOUSE.EXE](https://git.javispedro.com/cgit/vbados.git/about/) (confirmed
vmmouse-compatible, via its own README) gets tried — the point being to avoid VNC's usual
relative-mouse cursor drift for whatever mouse-driven experiments come later (this project's
ambitions go beyond NetWare-console use — graphics mode, sound, NetWare 3.x as a retro game
platform are all in view, and this sidecar may get reused for other DOS-era projects too).

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
passthrough for debugging, keyboard injection (`vmctl type`/`qmp type`), and VNC (`vmctl vnc`).
Still open: automatic hang detection (`vmctl status` only checks the process is alive, not that
the guest is responsive).

- A QEMU instance running a NetWare 3.x VM, spun up alongside the devcontainer as a sidecar
  container (decided; see "Other `devcontainer.json` settings" in [devcontainer.md](devcontainer.md)
  — the `/dev/kvm` `runArgs` passthrough moved to the sidecar's Compose service).
- A separate, agent-usable control channel to inject keyboard input, read the screen
  buffer/contents, perform debugging operations, and detect/recover from crashes or hangs.
- VNC access for the human — not just passive viewing: full interactive keyboard/mouse control of
  the VM, usable concurrently with the agent's own control channel, so the human can drive the
  VM directly or intervene mid-session without needing to tear down or reconfigure anything first.
  Done — see "VNC" below. Mouse control is present at the QEMU/protocol level (`vmport=on`'s
  `vmmouse` device); no DOS-side driver has been tried against it yet.
- A helper script/instructions so the human's VNC viewer starts *before* QEMU itself, then
  auto-connects the moment QEMU comes up — and auto-reconnects after every reboot/reset. Done —
  see "VNC" below.
- Text-mode/console output logged to a file as well (`-serial file:` is wired up but, per above,
  stays empty for this guest — `pmemsave`/`screendump` remain the reliable path; VNC is for a human
  watching and interacting live, alongside the agent's own control channel, not a log).

## Existing groundwork already in place

- `/dev/kvm` passthrough now lives on the `qemu` Compose service (`docker-compose.yml`), not
  `dev` — see [devcontainer.md](devcontainer.md).
- `README.md` has links for manually installing/running NetWare 3.12 in a VM (VirtualBox-based) —
  useful as an install/config reference even though the target here is QEMU. The current
  `vm-images/netware-3x.qcow2` was itself converted from a confirmed-working VirtualBox VDI.
- **Text-mode restore on exit: done (2026-07-25).** `hello_vga.c` now `#include`s `modes.c` for
  its `set_text_mode(0)` and calls it after a 5-second view of the 320×200 graphics mode, right
  before returning — boot-verified via `pmemsave` of `0xB8000` showing "Restored 80x25 text mode."
  and a clean console prompt afterward, no VM reset needed. `set_text_mode()`'s canned CRTC
  register table also hardcodes the cursor-location registers, stomping wherever NetWare's own
  console prompt had the cursor; fixed by snapshotting the cursor (`get_vga_cursor()`, already in
  `hello_vga.c`) immediately before the graphics switch and restoring it (`set_vga_cursor()`)
  right after `set_text_mode(0)` — boot-verified the cursor lands back exactly where it was.
  `hello.nlm` never switches modes, so it doesn't need any of this.

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
- `-vnc host:d` publishes VNC on TCP port `5900+d`; `usb-tablet` needs a guest USB stack (confirmed
  against QEMU's own USB device docs) so it doesn't apply to a DOS-era guest; `vmport=on` (a
  `-machine` property) auto-creates a `vmmouse` PS/2 device with no separate `-device` flag needed
  — verified against QEMU 10.0.0 source (`hw/i386/pc.c`'s `pc_superio_init()`) — see "VNC" above.
