# SPDX-License-Identifier: Apache-2.0

# Alpine, not the dev image's Debian: this sidecar has no toolchain-parity requirement with the
# NLM build (docs/nlm-toolchain-notes.md doesn't apply here), so it can stay minimal -
# qemu-system-i386 + socat is the entire package list. qemu-system-i386 lives in Alpine's
# "community" repo (enabled by default in the official image); socat is in "main".
FROM alpine:3.22

RUN apk add --no-cache qemu-system-i386 socat

COPY --chmod=755 vm-supervisor.sh /usr/local/bin/vm-supervisor.sh

# No CMD arg: vm-supervisor.sh defaults to its "run" (supervisor loop) mode when started with no
# arguments. `docker/podman exec` calls from vmctl pass "apply <word>" explicitly instead.
ENTRYPOINT ["/usr/local/bin/vm-supervisor.sh"]
