#!/usr/bin/env python3
"""Minimal QMP client for the NetWare QEMU sidecar. Installed on PATH as `qmp`.

Usage: qmp <command> [key=value ...]
Examples: qmp system_reset
          qmp query-status
          qmp screendump filename=/vm/logs/boot.ppm

QMP is JSON objects over a raw TCP stream - not guaranteed one object per line - so this reads a
growing buffer and repeatedly tries json.JSONDecoder().raw_decode() rather than assuming
newline framing. `filename=...` for screendump is a path inside the qemu sidecar's OWN
filesystem (/vm/logs there), not the dev container's - it lands in ./logs here because both
containers bind-mount the same host directory to those two different paths. See
docs/qemu-vm-debugging.md.
"""
import json
import socket
import sys

HOST = "qemu"
PORT = 4444


class QMPStream:
    def __init__(self, sock):
        self._sock = sock
        self._buf = ""
        self._decoder = json.JSONDecoder()

    def read_object(self):
        while True:
            self._buf = self._buf.lstrip()
            if self._buf:
                try:
                    obj, idx = self._decoder.raw_decode(self._buf)
                    self._buf = self._buf[idx:]
                    return obj
                except json.JSONDecodeError:
                    pass
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("QMP connection closed by qemu")
            self._buf += chunk.decode("utf-8")

    def send_object(self, obj):
        self._sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


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


def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <command> [key=value ...]", file=sys.stderr)
        return 2
    command = sys.argv[1]
    arguments = parse_arguments(sys.argv[2:])

    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        stream = QMPStream(sock)
        stream.read_object()  # greeting banner
        stream.send_object({"execute": "qmp_capabilities"})
        stream.read_object()  # {"return": {}}

        request = {"execute": command}
        if arguments:
            request["arguments"] = arguments
        stream.send_object(request)
        reply = stream.read_object()
        print(json.dumps(reply, indent=2))
        return 1 if "error" in reply else 0


if __name__ == "__main__":
    sys.exit(main())
