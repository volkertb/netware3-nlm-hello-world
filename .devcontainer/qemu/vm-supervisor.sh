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
LOGDIR=${LOGDIR:-/vm/logs}
STATE_FILE=/run/vm.state
PID_FILE=/run/qemu.pid
QMP_PORT=4444
CTL_PORT=4445
SELF=/usr/local/bin/vm-supervisor.sh

mkdir -p "$LOGDIR"

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
    # -machine pc + if=ide matches the PIIX3/IDE chipset the disk was already installed against
    # under VirtualBox; -display none + -nic none because this is the headless MVP (no VNC, no
    # network yet - see docs/qemu-vm-debugging.md for what's deferred and why.
    # QEMU's own stdout/stderr (startup errors: bad disk path, KVM refusing the CPU model,
    # etc.) redirected into the shared logs/ dir, not left to the container's own stdout - the
    # dev container has no podman/docker access to read `podman logs` itself, so this is the
    # only channel it has onto why a start attempt failed. Appended, not truncated, so a
    # crash-restart loop's history survives.
    # accel=kvm:tcg is a `-machine` property (colon-list documented in qemu-options.hx: "accel=
    # accel1[:accel2[:...]] selects accelerator") - NOT the standalone `-accel` flag, which
    # takes exactly one accelerator name per occurrence and rejected a colon-joined value
    # outright ("invalid accelerator kvm:tcg", caught via qemu-stdouterr.log below).
    # -m 16 matches the confirmed-working VirtualBox VM's RAM exactly (16MB), not a guess: 64MB
    # made NetWare 386's own loader fail with "Insufficient memory... requires at least 3
    # megabytes of extended memory" - a DOS-era memory-detection quirk triggered by *more* RAM,
    # not a real shortfall (confirmed via QMP pmemsave of the VGA text buffer at 0xB8000).
    qemu-system-i386 \
        -machine pc,accel=kvm:tcg \
        -cpu pentium \
        -m 16 \
        -drive file="$DISK",format=qcow2,if=ide \
        -qmp tcp:0.0.0.0:$QMP_PORT,server=on,wait=off \
        -serial file:"$LOGDIR"/serial.log \
        -display none \
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
