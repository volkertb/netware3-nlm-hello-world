# NetWare VM debugging (planned, not yet implemented)

Captured now so a future session doesn't have to re-derive these requirements from scratch.

## Goal

Functional testing of an NLM means booting NetWare and loading it — today a manual VM round-trip
per iteration (a cycle time that helped stretch the since-resolved 2025 abend saga to over a
year). The goal: a QEMU-based NetWare VM the agent drives end-to-end — send keystrokes, read the
screen, detect crash/hang, reset automatically — while the human keeps a live VNC view, for fast
joint human+agent development. Decided: QEMU runs in a **sidecar container**, not in the dev
container (`qemu-system-x86` is deliberately absent from the dev image; the QMP client side —
python3/socat/jq — is already installed).

## Requirements (as stated by the user, 2026-07-19)

- A QEMU instance running a NetWare 3.x VM, spun up alongside the devcontainer as a sidecar
  container (decided; see "Other `devcontainer.json` settings" in [devcontainer.md](devcontainer.md)
  — the `/dev/kvm` `runArgs` passthrough should move to the sidecar's config when it lands).
- VNC access for the human — not just passive viewing: full interactive keyboard/mouse control of
  the VM, usable concurrently with the agent's own control channel below, so the human can drive the
  VM directly or intervene mid-session (e.g. to take over during a stuck debugging loop) without
  needing to tear down or reconfigure anything first.
- A separate, agent-usable control channel to:
  - inject keyboard input,
  - read the screen buffer/contents,
  - perform debugging operations,
  - detect and automatically recover from crashes or hangs (reset the VM without human intervention).
- A helper script/instructions so the human's VNC viewer can be started *before* the QEMU instance
  itself, then auto-connects the moment QEMU comes up — and auto-reconnects after every reboot/reset
  — instead of the human connecting manually and risking missing fast-moving output (e.g. the boot
  screen, or a test that completes in well under a second).
- Text-mode/console output logged to a file as well, for the same reason (not missing fast output) and
  so past runs can be reviewed after the fact instead of only observed live.

## Existing groundwork already in place

- `/dev/kvm` is already passed through in `devcontainer.json`'s `runArgs` — unused until this
  lands ([devcontainer.md](devcontainer.md)).
- `README.md` has links for manually installing/running NetWare 3.12 in a VM (VirtualBox-based) —
  useful as an install/config reference even though the target here is QEMU.
- Worth doing in the NLM *before* building the automation: restore 80×25 text mode before exiting
  (e.g. `set_text_mode()` in `modes.c`, or reprogram the registers back). After a graphics-mode
  test the server only *looks* hung — the console keeps running and writing to the invisible text
  buffer (observed 2026-07-19; blind-typed commands would likely still work) — but without the
  restore, every automated graphics test ends in a VM reset instead of a clean next iteration.

## Starting point for research

QEMU's QMP (QEMU Machine Protocol — a JSON-based monitor socket) is the standard mechanism for
external, scriptable control of a running QEMU instance: keystroke injection, screen capture, reset,
snapshot/restore. QEMU's `-vnc` flag can run alongside it on the same instance for the human-facing
view, and QEMU also supports redirecting the serial/text console to a file. How to make the VNC
viewer reliably auto-connect on startup and auto-reconnect after a reset (a fixed/predictable
address, a wrapper script that retries/polls, some other mechanism) is an open implementation
question — not decided here, and not necessarily QEMU's own job to solve; it may end up being purely
about how the viewer is launched/wrapped rather than a QEMU flag at all. Verify current QMP command
names and console-logging options against QEMU's own docs before implementing — treat this paragraph
as a starting pointer, not a confirmed design.
