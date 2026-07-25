#!/usr/bin/env python3
"""Minimal QMP client for the NetWare QEMU sidecar. Installed on PATH as `qmp`.

Usage: qmp <command> [key=value ...]
       qmp type <text>
Examples: qmp system_reset
          qmp query-status
          qmp screendump filename=/vm/shared/logs/boot.ppm
          qmp blockdev-change-medium id=floppy0 filename=/vm/shared/floppy/floppy.img format=raw
          qmp type "LOAD A:HELLO.NLM\n"

Transport is `qemu.qmp` (PyPI, see qemu/requirements.txt) - the QEMU project's own maintained QMP
client library, via its `legacy.QEMUMonitorProtocol` sync wrapper. `filename=...` above is a path
inside the qemu sidecar's OWN filesystem (/vm/shared/... there), not the dev container's - it
lands in ./shared here because both containers bind-mount the same host directory to those two
different paths. See docs/qemu-vm-debugging.md.

`type` is not a real QMP command - it's a meta-command handled entirely client-side, translating
each character of <text> into one QMP `send-key` call (QKeyCode names verified against QEMU
10.0.0's qapi/ui.json). A literal "\n" in <text> sends `ret` (Enter). Characters are sent one at a
time, sequentially, over a single connection - `send-key`'s own `keys` array is for simultaneous
chords (e.g. ctrl+alt+delete), not a way to type a string in one call.
"""
import json
import sys

# pylint/astroid can't resolve this: qemu.qmp ships as a PEP 420 implicit namespace package (no
# qemu/__init__.py, by design - it lets qemu.qmp/qemu.machine/etc. coexist), which is a
# long-standing astroid limitation, not a real missing import - it resolves fine at runtime.
from qemu.qmp.legacy import QEMUMonitorProtocol  # pylint: disable=import-error,no-name-in-module

HOST = "qemu"
PORT = 4444

# QKeyCode names, verified against qapi/ui.json (QEMU 10.0.0 tag) - not from a docs summary.
# Maps an ASCII character to (qcode, needs_shift). US keyboard layout only - the only layout that
# matters here, since nothing about the NetWare console cares about locale.
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"
CHAR_KEYS = {}
for _c in _LOWER:
    CHAR_KEYS[_c] = (_c, False)
    CHAR_KEYS[_c.upper()] = (_c, True)
for _d in _DIGITS:
    CHAR_KEYS[_d] = (_d, False)
CHAR_KEYS.update({
    " ": ("spc", False),
    ".": ("dot", False),
    ":": ("semicolon", True),
    ";": ("semicolon", False),
    ",": ("comma", False),
    "-": ("minus", False),
    "_": ("minus", True),
    "=": ("equal", False),
    "/": ("slash", False),
    "\\": ("backslash", False),
    "\n": ("ret", False),
})


def parse_arguments(pairs):
    arguments = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            print(f"error: expected key=value, got {pair!r}", file=sys.stderr)
            sys.exit(2)
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass  # plain string, e.g. a filesystem path
        arguments[key] = value
    return arguments


def connect():
    qmp = QEMUMonitorProtocol((HOST, PORT))
    qmp.connect()
    return qmp


def keys_for_char(ch):
    try:
        qcode, needs_shift = CHAR_KEYS[ch]
    except KeyError:
        print(f"error: no key mapping for {ch!r}", file=sys.stderr)
        sys.exit(2)
    keys = [{"type": "qcode", "data": qcode}]
    if needs_shift:
        keys.insert(0, {"type": "qcode", "data": "shift"})
    return keys


def type_text(qmp, text):
    for ch in text:
        reply = qmp.cmd_raw("send-key", {"keys": keys_for_char(ch)})
        if "error" in reply:
            print(json.dumps(reply, indent=2), file=sys.stderr)
            return 1
    print(json.dumps({"return": {}}, indent=2))
    return 0


def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <command> [key=value ...]", file=sys.stderr)
        print(f"       {sys.argv[0]} type <text>", file=sys.stderr)
        return 2
    command = sys.argv[1]

    if command == "type":
        if len(sys.argv) != 3:
            print(f"usage: {sys.argv[0]} type <text>", file=sys.stderr)
            return 2
        with connect() as qmp:
            return type_text(qmp, sys.argv[2])

    arguments = parse_arguments(sys.argv[2:])
    with connect() as qmp:
        reply = qmp.cmd_raw(command, arguments or None)
        print(json.dumps(reply, indent=2))
        return 1 if "error" in reply else 0


if __name__ == "__main__":
    sys.exit(main())
