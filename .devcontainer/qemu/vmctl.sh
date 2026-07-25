#!/usr/bin/env bash
# vmctl - dev-container control client for the NetWare QEMU sidecar. Installed on PATH.
#
# on/off/status talk to vm-supervisor.sh's own control listener (it owns the QEMU process
# lifecycle so a fully-off VM can be turned back on - QMP dies with the QEMU process it
# controls, so QMP alone can't do that). reset/screendump go straight to QMP via `qmp`. Both
# ports are reachable only as the `qemu` compose service, never published to the host - see
# docs/qemu-vm-debugging.md.
set -euo pipefail

HOST=qemu
CTL_PORT=4445
# WORKSPACE_FOLDER comes from devcontainer.json's containerEnv, which mirrors its own
# workspaceFolder - the one place the repo's mount path is actually defined. Falls back to $PWD
# for anything run outside the devcontainer CLI's env injection.
WORKSPACE_FOLDER=${WORKSPACE_FOLDER:-$PWD}
SHARED_DIR=${NETWARE_VM_SHARED_DIR:-$WORKSPACE_FOLDER/shared}
LOGS_DIR="$SHARED_DIR/logs"
FLOPPY_DIR="$SHARED_DIR/floppy"

usage() {
    echo "usage: $(basename "$0") on|off|reset|status|screendump [name.ppm]" >&2
    echo "       $(basename "$0") floppy load [image] | floppy eject | floppy status" >&2
    echo "       $(basename "$0") type <text>" >&2
    exit 2
}

if [ $# -lt 1 ]; then
    usage
fi

case "$1" in
    on|off|status)
        printf '%s\n' "$1" | socat -T5 - "TCP:${HOST}:${CTL_PORT}"
        ;;
    reset)
        qmp system_reset
        ;;
    type)
        text=${2:-}
        if [ -z "$text" ]; then
            usage
        fi
        qmp type "$text"
        ;;
    screendump)
        name=${2:-screendump.ppm}
        mkdir -p "$LOGS_DIR"
        # The path after filename= is resolved inside the qemu sidecar's OWN filesystem
        # (/vm/shared/logs there) - it shows up here because both containers bind-mount the same
        # host directory to those two different paths.
        qmp screendump "filename=/vm/shared/logs/$name"
        echo "written to $LOGS_DIR/$name"
        ;;
    floppy)
        case "${2:-}" in
            load)
                # Defaults to the repo-root build artifact; an explicit path may point anywhere
                # readable in the dev container. Copied into the shared bind (rather than pointed
                # at directly) so the source repo tree never needs to be mounted into `qemu` - see
                # docker-compose.yml's comment on that decision.
                src=${3:-$WORKSPACE_FOLDER/floppy.img}
                if [ ! -f "$src" ]; then
                    echo "error: $src not found (build it first, e.g. \`make\`)" >&2
                    exit 1
                fi
                mkdir -p "$FLOPPY_DIR"
                name=$(basename "$src")
                cp "$src" "$FLOPPY_DIR/$name"
                # Requires the VM running - QMP only exists while QEMU does. `qmp` reports a
                # connect failure clearly if it's off.
                qmp blockdev-change-medium "id=floppy0" "filename=/vm/shared/floppy/$name" "format=raw"
                echo "loaded $name"
                ;;
            eject)
                qmp eject id=floppy0
                ;;
            status)
                qmp query-block
                ;;
            *)
                usage
                ;;
        esac
        ;;
    *)
        usage
        ;;
esac
