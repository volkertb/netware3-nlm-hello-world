# NetWare VM debugging (planned, not yet implemented)

Captured now so a future session doesn't have to re-derive these requirements from scratch.

## Goal

The current hard blocker (see [NOTES.md](../NOTES.md) — `Invalid TSS Processor Exception`) needs many
build-boot-crash-reset cycles to debug, and resetting a VM by hand after every crash/hang is slow.
The goal is a QEMU-based NetWare VM the agent can drive end-to-end without a human in the loop for
each iteration — send keystrokes, read the screen, detect a crash/hang, reset automatically — while
the human keeps a live view via VNC.

## Requirements (as stated by the user, 2026-07-19)

- A QEMU instance running a NetWare 3.x VM, spun up alongside the devcontainer (in-container or
  sidecar — undecided; see "Other `devcontainer.json` settings" in [devcontainer.md](devcontainer.md)).
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

- `/dev/kvm` is already passed through in `devcontainer.json`'s `runArgs` for KVM acceleration —
  unused until this lands. See [devcontainer.md](devcontainer.md).
- `README.md` has links for manually installing/running NetWare 3.12 in a VM (VirtualBox-based) —
  useful as an install/config reference even though the target here is QEMU, not VirtualBox.
- `NOTES.md` has the live debugging log for the bug motivating this (a suspected IOPL/ring-0 issue
  on graphics mode switch) — this is specifically what the automated reset-and-retry loop is for.

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
