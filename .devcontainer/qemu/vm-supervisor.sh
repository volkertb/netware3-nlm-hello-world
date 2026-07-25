#!/bin/sh
# vm-supervisor.sh - PID 1 for the qemu sidecar container.
#
# Owns the QEMU child process's lifecycle so vmctl (running in the dev container, which has no
# way to restart a sibling container) can still power a fully-off VM back on: the container
# itself never exits, only the QEMU process under it does. QMP dies with the QEMU process it
# controls, so QMP alone can't bring a stopped VM back - hence this second, supervisor-level
# control channel (port 4445) alongside QMP itself (port 4444). See docs/qemu-vm-debugging.md.
#
# No `set -e`: this is a long-running reconciliation loop where individual QMP/kill failures
# (VM already down, QMP not answering mid-boot, ...) are expected and handled explicitly below,
# not exit conditions for the supervisor itself.
set -u

DISK=${DISK:-/vm/disk.qcow2}
LOGDIR=${LOGDIR:-/vm/shared/logs}
FLOPPYDIR=${FLOPPYDIR:-/vm/shared/floppy}
STATE_FILE=/run/vm.state
PID_FILE=/run/qemu.pid
QMP_PORT=4444
CTL_PORT=4445
# QEMU's -vnc host:d syntax takes a display number, not a port - the port is always 5900+d.
# Deriving VNC_PORT from VNC_DISPLAY keeps that relationship explicit instead of two independent
# magic numbers that could drift apart.
VNC_DISPLAY=0
VNC_PORT=$((5900 + VNC_DISPLAY))
NOVNC_PORT=6080
SELF=/usr/local/bin/vm-supervisor.sh

mkdir -p "$LOGDIR" "$FLOPPYDIR"

qemu_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

# One-shot QMP round trip: capabilities handshake, then the single command named in $1. Good
# enough for reset/quit - nothing here needs a long-lived QMP connection.
qmp_command() {
    printf '{"execute":"qmp_capabilities"}{"execute":"%s"}' "$1" \
        | socat -T2 - TCP:127.0.0.1:$QMP_PORT
}

start_qemu() {
    if qemu_running; then
        return 0
    fi
    # -machine pc + if=ide matches the PIIX3/IDE chipset the disk was installed against under
    # VirtualBox. -nic none: no network needed. accel=kvm:tcg must be a `-machine` property, not
    # the standalone `-accel` flag (rejected outright), and -m 16 matches the source VirtualBox
    # VM's RAM exactly - more RAM broke NetWare's own loader. Both bugs and how they were
    # diagnosed: docs/qemu-vm-debugging.md ("Two real bugs").
    #
    # -device floppy,id=floppy0 with no drive= boots an empty, addressable floppy tray (verified
    # against QEMU 10.0.0 source: hw/block/fdc.c's floppy_drive_realize() falls back to
    # blk_create_empty_drive(); the `pc` machine already wires up the ISA FDC by default, so this
    # device has a bus to attach to). vmctl floppy load/eject fill and empty it at runtime over
    # QMP. -boot order=c pins boot to the hard disk only, so an inserted data floppy can never
    # get picked up as a boot device on a reset.
    #
    # -vnc 127.0.0.1:0: loopback-only inside THIS container - novnc_server (started below) is the
    # only thing that connects to it; nothing on sidecar-net can reach raw, unauthenticated VNC
    # directly. vmport=on (a -machine property) makes the `pc` machine auto-create and wire up a
    # `vmmouse` PS/2 device (verified against QEMU 10.0.0 source: hw/i386/pc.c's
    # pc_superio_init() creates TYPE_VMPORT + "vmmouse" and links it to the i8042 controller
    # whenever vmport is enabled - no separate -device flag needed). NetWare/DOS-era guests have
    # no USB stack (ruling out -device usb-tablet), but vmmouse's absolute-position protocol is a
    # legacy PS/2-port extension a period-correct DOS driver can use directly - not wired up to
    # anything guest-side yet, but there for whenever a driver like vbados's VBMOUSE.EXE
    # (https://git.javispedro.com/cgit/vbados.git/about/, confirmed vmmouse-compatible) gets
    # tried, to avoid VNC's usual relative-mouse cursor drift.
    #
    # stdout/stderr appended to the shared logs dir rather than left on the container's own
    # stdout: the dev container has no podman/docker access to read `podman logs` itself, so
    # this file is its only window onto why a start attempt failed.
    qemu-system-i386 \
        -machine pc,accel=kvm:tcg,vmport=on \
        -cpu pentium \
        -m 16 \
        -boot order=c \
        -drive file="$DISK",format=qcow2,if=ide \
        -device floppy,id=floppy0 \
        -qmp tcp:0.0.0.0:$QMP_PORT,server=on,wait=off \
        -serial file:"$LOGDIR"/serial.log \
        -vnc 127.0.0.1:$VNC_DISPLAY \
        -nic none >>"$LOGDIR"/qemu-stdouterr.log 2>&1 &
    echo $! > "$PID_FILE"
}

stop_qemu() {
    if ! qemu_running; then
        return 0
    fi
    # `quit` over QMP first - not a graceful NetWare DOWN (pre-ACPI, system_powerdown is a
    # no-op on this guest), but it lets QEMU flush the qcow2 write cache instead of a bare kill.
    qmp_command quit >/dev/null 2>&1
    i=0
    while qemu_running && [ "$i" -lt 20 ]; do
        sleep 1
        i=$((i + 1))
    done
    if qemu_running; then
        kill "$(cat "$PID_FILE")" 2>/dev/null
    fi
    rm -f "$PID_FILE"
}

apply() {
    case "$1" in
        on)
            echo on > "$STATE_FILE"
            echo ok
            ;;
        off)
            echo off > "$STATE_FILE"
            echo ok
            ;;
        reset)
            if qemu_running && qmp_command system_reset >/dev/null 2>&1; then
                echo ok
            else
                echo "error: vm not running or qmp command failed"
            fi
            ;;
        status)
            if qemu_running; then
                echo running
            else
                echo stopped
            fi
            ;;
        *)
            echo "error: unknown command: $1"
            ;;
    esac
}

case "${1:-run}" in
    apply)
        shift
        apply "$@"
        ;;
    run)
        echo on > "$STATE_FILE"
        # Control listener: one line in (on/off/reset/status), one line out - the wire protocol
        # vmctl (dev container) speaks over CTL_PORT. `fork` handles each connection in its own
        # child so a slow/stuck client can't block the reconciliation loop below. $line is
        # double-quoted in the nested command so shell metacharacters in it can't be
        # reinterpreted as a second command - this socket has no auth, so anything reaching it
        # (only the dev container, over the private compose network) gets exactly `apply <word>`
        # and nothing else.
        socat TCP-LISTEN:$CTL_PORT,reuseaddr,fork \
            SYSTEM:"read line; $SELF apply \"\$line\"" &
        # noVNC's web UI + WebSocket-to-raw-VNC proxy, started once and unconditionally - not
        # gated on the VM being on, so the page stays reachable (just failing to connect) even
        # while the VM is off. A connection attempt against a not-yet-up QEMU just fails; noVNC's
        # own client-side reconnect (vnc.html's ?reconnect=true&reconnect_delay=... - see
        # docs/qemu-vm-debugging.md) retries with no extra scripting needed here.
        novnc_server --vnc 127.0.0.1:$VNC_PORT --listen 0.0.0.0:$NOVNC_PORT \
            --web /usr/share/novnc >>"$LOGDIR"/novnc.log 2>&1 &
        # Reconciliation loop: desired state in $STATE_FILE vs the actual QEMU process. This is
        # what makes "power back on after off" possible without restarting this container.
        while true; do
            want=$(cat "$STATE_FILE" 2>/dev/null || echo on)
            if [ "$want" = on ]; then
                if ! qemu_running; then
                    start_qemu
                fi
            else
                stop_qemu
            fi
            sleep 2
        done
        ;;
    *)
        echo "usage: $0 [run|apply <on|off|reset|status>]" >&2
        exit 2
        ;;
esac
