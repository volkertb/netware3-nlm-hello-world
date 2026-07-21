# Devcontainer notes

Detail behind `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json` that's useful for
future changes but too long to keep in `AGENTS.md`.

## Stage layout

`.devcontainer/Dockerfile` is 4 stages, forming a DAG (each stage `COPY --from=` an earlier one;
apt-installed packages do **not** carry across a `COPY` — only explicitly copied paths do):

1. **`downloader-and-patcher`** (`debian:13.6`) — fetches all 4 large downloads (binutils source,
   Novell NDK ISO, nlm-samples, nlm-kit) once into a `--mount=type=cache,target=/downloads-cache`
   cache mount, copies them into `/Downloads`, and extracts + patches the binutils source tree.
   Consolidated here so downloading *and* source prep happen on current Debian, where
   `wget`/`tar`/`xz-utils`/`patch` install trivially — the EOL Debian 9 stage is left with
   nothing but configure+make.
   - Each download is gated by a self-healing checksum check:
     `[ -f cached ] && sha256sum --status -c - || wget ... && sha256sum -c - && cp ...`. `&&` and
     `||` are left-to-right, equal precedence, so a missing *or* checksum-failing cached file
     (e.g. left partial by an interrupted build) is redownloaded instead of failing forever.
   - `RUN --mount=type=cache` + `wget` rather than `ADD --checksum=`, because `ADD` doesn't
     support `--mount` — there'd be no way to cache the download itself.
   - Binutils patches (why they exist: [nlm-toolchain-notes.md](nlm-toolchain-notes.md)):
     `COPY`-replaced forks `.devcontainer/nlmconv.c` (upstream reloc-resolution bugfix, verbose
     ld, `LD_NAME` default) and `.devcontainer/bfd/nlm32-i386.c` (restores the reloc safety check
     with actionable messages), plus `.devcontainer/patches/0001-*` making malformed `.def`
     numbers fatal. That patch covers `nlmheader.y` *and* the shipped bison-generated
     `nlmheader.c`, which is then `touch`ed (again defensively after the `COPY --from` in
     `binutils-builder`, in case relative mtimes aren't preserved) so make never invokes bison —
     it's installed nowhere in this Dockerfile.
2. **`binutils-builder`** (`debian:9.13`, "Stretch") — the *only* stage on EOL Debian 9, kept to
   configure+make of binutils 2.30 (`--enable-targets=i386-netware --enable-obsolete`) for
   `nlmconv` and the `nlm32-i386` BFD target: removed upstream after 2.31, untested against
   modern GCC/glibc, hence the period-matched toolchain. Its archived apt repo suffices — only
   `build-essential`/`texinfo` are installed (see sources.list section below).
   - `linux32 ./configure` fakes `uname -m` during build-triple detection. The resulting tools
     are still native x86_64 binaries (confirmed: they run in `builder` before any 32-bit runtime
     is installed) — but the i686 triple makes the built ld default to `elf_i386`, which the
     NLM link path requires.
   - After `make install`, `/usr/local` is pruned to `nlmconv` + `i386-netware-ld` +
     `i386-netware-objdump` (~140 MB of libs/headers/tooldir copies deleted). The renames are
     load-bearing: binutils installs a full plain-named toolset, gcc resolves subprograms via
     PATH where `/usr/local/bin` wins, and on Debian ≥ 12 (gcc ≥ 11, DWARF 5) host compiles die
     with `as: unrecognized option '--gdwarf-5'` from the shadowing 2018-era gas. Cross-style
     names can't be picked up by accident; nlmconv's fork hardwires `LD_NAME` to
     `i386-netware-ld` (a `grep` guard fails the build if that ever reverts), so no Makefile
     changes were needed.
3. **`builder`** (`debian:13.6`) — everything that doesn't need Debian 9: extracts the NDK ISO,
   builds `nlm-kit` (the actual source of `/usr/bin/nlmimp` — not part of binutils, easy to
   misattribute), test-builds the sample `hello` NLM, and packages `/nlm_disk.img` via `mtools`.
4. **`dev-env`** (`debian:13.6`) — the devcontainer image. Copies `/nlm_disk.img`, `/usr/local`,
   `/usr/nwsdk`, `/usr/bin/nlmimp` from `builder`; installs JetBrains dev-container prerequisites
   and debugging/analysis tools (python3, xxd, file, bsdextrautils, qemu-utils, socat, jq,
   ripgrep, shellcheck, strace — `--no-install-recommends`; `qemu-system-x86` deliberately absent,
   the VM runs in a sidecar); creates non-root `dev-container-user`; installs Claude Code
   natively (`curl -fsSL https://claude.ai/install.sh | bash` — the npm-based devcontainer
   Feature left a root-owned leftover that broke auto-updates); repeats the sample-NLM build as
   the non-root user and gates it with `verify-nlm` (installed from `.devcontainer/verify_nlm.py`
   to `/usr/local/bin`; what it checks: [nlm-toolchain-notes.md](nlm-toolchain-notes.md)). The
   sample `.def` gets `STACK 32768` appended first — it ships without one, and verify-nlm rejects
   the resulting 0-stack header.

## Debian base images (bumped to 13.6 on 2026-07-19)

The three non-Stretch stages were bumped from `11.11` ahead of Debian 11's LTS end
(**2026-08-31**), after which bullseye's repos move to `archive.debian.org` and every stage would
inherit the EOL-archive problems confined to `binutils-builder`. The bump's fallout (the
toolchain-shadowing story above) is the template for the next such bump: expect gcc-default
landmines and re-verify the nlm-kit and sample-NLM builds.

## apt caching pattern (every stage)

Every apt-using stage does two things:

```dockerfile
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install ...
```

Debian images delete downloaded `.deb`s after each install (`docker-clean` hook) to keep layers
small — counterproductive with cache mounts, which live outside layers; without the `keep-cache`
override the mount stays empty. `sharing=locked` is required (concurrent stage builds race on the
cache) and **is** supported by Podman/buildah
([containers/buildah#3820](https://github.com/containers/buildah/pull/3820)) — an earlier
AI-generated summary claimed the opposite; check primary sources.

Two traps, both already hit once:

- Forgetting `keep-cache` in a *new* apt-using stage (happened twice during the stage split).
- Appending an `apt install` layer to an already-built stage: the stage's earlier `apt update`
  layer is a cache hit and doesn't re-run, while the `/var/lib/apt` cache mount it once populated
  may have been pruned — the new layer then sees empty package lists ("Unable to locate package",
  2026-07-19). Either put `apt -y update &&` in the same `RUN` (as `downloader-and-patcher` does)
  or expect to bust the stage cache.

Host-side cache location under rootless Podman: `${TMPDIR:-/var/tmp}/buildah-cache-<uid>` on the
machine running `podman build` (applies to `/downloads-cache` too).

## `binutils-builder`'s `sources.list`

Deliberately just the plain `archive.debian.org` main/contrib/non-free line — no
`debian-security` suite or `Acquire::Check-Valid-Until "false"` override needed, because
`build-essential`/`texinfo` happen not to hit point-release-pinned transitive dependencies. If a
future package here does (seen previously with `curl`→`libcurl3`, `wget`→`libgnutls30`), the fix
is adding the `debian-security stretch/updates` line plus the `Check-Valid-Until` override — not
swapping tools.

## Session/agent-state persistence

`devcontainer.json` mounts a generically-named volume at `~/.agent-state` and runs
`.devcontainer/postCreate.local.sh` if present — gitignored and per-developer, so
`devcontainer.json` names no specific coding agent. That script (recreate per machine) symlinks
`~/.claude` and `~/.claude.json` into the volume so agent session/auth state survives rebuilds.
It prefers already-persisted state on conflict (`mv`-then-fallback-to-`rm`, not unconditional
overwrite) — an earlier version nested the fresh copy inside the persisted one instead of
discarding it.

The volume's name is pinned explicitly (`name: netware3-hello-world-agent-state` in
`docker-compose.yml`, 2026-07-20) rather than left for Compose to derive. Compose otherwise
prefixes named volumes with its project name (e.g.
`netware3-hello-world_devcontainer_agent-state`), which is a *different* literal volume than the
one the old single-container `mounts` config created (`source=${localWorkspaceFolderBasename}-agent-state`)
— the Compose migration silently orphaned it on first rebuild and lost coding-agent session/auth
state, recovered only because the old volume was still sitting there under its old name
(`podman volume ls`).

**Deferred**: the pinned name is a single fixed string, so two checkouts of this repo on the same
host would collide/leak session state into the same volume. Not fixed now (single-checkout use
today), but the fix if it's ever needed is a per-checkout suffix — `${devcontainerId}` is the
spec-sanctioned mechanism for exactly this (the docker-in-docker Feature uses it the same way),
but it only substitutes inside devcontainer.json's own properties (`mounts`, `runArgs`, ... - the
same single-container-only list `runArgs` is on), not inside a referenced `docker-compose.yml`,
and its hash algorithm isn't documented anywhere to replicate independently. The practical
equivalent: an `initializeCommand` that hashes `${localWorkspaceFolder}` (host-side, stable per
checkout) into a short suffix written to a gitignored `.devcontainer/.env`, which Compose's own
`.env` loading then substitutes into the volume `name:`. Doing this later means another one-time
`podman volume` copy, same as this one.

## Other `devcontainer.json` settings

- `containerUser: "dev-container-user"` silences a JetBrains/Podman "user was not specified"
  error; must match the Dockerfile's `USER` (or be `"root"` if none).
- `dockerComposeFile`/`service`/`workspaceFolder` (2026-07-20): the devcontainer now builds via
  `docker-compose.yml` instead of a single-container `build`, so the QEMU sidecar
  ([qemu-vm-debugging.md](qemu-vm-debugging.md)) can run as a second Compose service.
  `/dev/kvm` passthrough moved with it — from devcontainer.json's old single-container `runArgs`
  to the `qemu` service's `devices:` in `docker-compose.yml` (also removes the old "dev
  container won't start on KVM-less hosts" side effect, since `dev` no longer touches
  `/dev/kvm` at all). Requires host-accessible `/dev/kvm` (mode 0666 here); a `kvm`-group-locked
  host would need Podman's `--group-add=keep-groups` added to the `qemu` service.
- `updateRemoteUserUID: false` (2026-07-20) works around a Podman bug, still open:
  `--platform` on a `podman build` makes Podman distrust an already-local image and try to
  re-resolve it instead of using local storage, which is exactly what the devcontainer CLI's
  post-build UID-sync step does (a second `podman build --platform ...` with `FROM
  $BASE_IMAGE=<the image just built>`) — it fails outright instead of the interactive registry
  prompt the same bug produces in a terminal.
  [microsoft/vscode-remote-release#9748](https://github.com/microsoft/vscode-remote-release/issues/9748)
  shows it hitting a plain single-Dockerfile devcontainer too, not just Compose ones; this
  repo's prior single-Dockerfile `build` just hadn't exercised it before this migration. Root
  cause and maintainer discussion:
  [podman-container-tools/podman#23055](https://github.com/podman-container-tools/podman/issues/23055)
  (a mirror of containers/podman — the commenters are Podman core maintainers). Disabling the
  setting is the workaround taken here, since the Dockerfile already bakes `dev-container-user`
  in at UID/GID 1000 (the common default for a first Linux user account) — if that ever stops
  matching the host user, bind-mounted files may show up host-side-owned by a different UID.
  **Host-level alternative**, if UID auto-sync matters more than avoiding this setting: add
  `"localhost"` to `unqualified-search-registries` in the host's `/etc/containers/registries.conf`
  (confirmed working in the linked issue thread), then set `updateRemoteUserUID` back to `true`
  (or remove it — `true` is the spec default). That's a per-host change outside this repo, so
  it isn't scripted here. This repo's config is a single shared `devcontainer.json`, and unlike
  `dockerComposeFile` below, devcontainer.json has no merge/override mechanism to isolate a
  Podman-only setting like this one — [devcontainers/spec#22](https://github.com/devcontainers/spec/issues/22)
  proposes an `extends` property for exactly that, but it's still unimplemented. Docker users
  should just flip this back to `true` by hand.
- `docker-compose.podman-rootless.yml` (2026-07-20): a second, Podman-only compose file, named
  in `dockerComposeFile`'s array form and merged on top of `docker-compose.yml` (later files
  override/add to earlier ones, like multiple `-f` flags). Adds `userns_mode: "keep-id"` to the
  `dev` service — needed because `devcontainers/cli` only auto-injects `--userns=keep-id` for
  single-container Podman builds
  ([devcontainers/cli#1004](https://github.com/devcontainers/cli/issues/1004), fixed by
  [#1018](https://github.com/devcontainers/cli/pull/1018) — but only in `singleContainer.ts`),
  never for Compose-based ones. Without it, rootless Podman's default UID mapping puts container
  UID 0 at the host user, so the bind-mounted workspace shows up owned by `root` inside the
  container and non-root `dev-container-user` can't write to it (silent under `ls`-level
  checking — permissions look plausible until you try to build). `keep-id` is Podman-specific:
  Docker's `--userns`/`userns_mode` only supports `"host"`, so merging this file would likely
  hard-error under real Docker rather than no-op — it's a separate file specifically so a Docker
  user's fix is deleting one `dockerComposeFile` array entry, not editing YAML in place.

## `~/.local/bin` on `PATH`

Set via `ENV` in `dev-env` rather than relying on Debian's `~/.profile` skel default, which only
login shells source — VS Code terminals and most tooling spawn non-login shells. Not
agent-specific: any user-installed CLI under `~/.local/bin` needs it.

## Locale warnings in VS Code terminals

`bash: warning: setlocale: LC_CTYPE: cannot change locale (en_US.UTF-8): No such file or
directory` on every new integrated-terminal shell (2026-07-20, first seen right after the
13.6 base-image bump, though the underlying gap — no locale ever generated in this image —
predates it). Two things had to both be true, neither obvious from the container side alone:

- VS Code Server forwards the *client machine's* `LANG` into every terminal it spawns inside the
  container. This is IDE-level behavior, not container-runtime-level — a Docker-based dev
  container hits it identically; Podman isn't implicated. Confirmed by process tree: the
  container's own PID 1 has no `LANG` in its environment at all, but every bash the pty host
  spawns already has `LANG=en_US.UTF-8` set before `.bashrc` runs.
- Debian's `locale-gen` (`/usr/sbin/locale-gen`, `locales` package) **ignores CLI arguments
  entirely** — the only argument it inspects is `--keep-existing`. It reads exclusively from
  `/etc/locale.gen`, which ships with every locale commented out. `locale-gen en_US.UTF-8`
  therefore "succeeds" (exit 0) while silently generating nothing — verify with
  `locale -a`/`ls /usr/lib/locale`, not the exit code.

Fix (`dev-env` stage): `echo "$LOCALE UTF-8" >> /etc/locale.gen && locale-gen`, where `LOCALE`
is a build `ARG` defaulting to `en_US.UTF-8` (override with `--build-arg LOCALE=...` to match a
host forwarding a different locale — not hardcoded because the forwarded value is a property of
whoever's host, not of this image).

## Local build/test loop

`.devcontainer/build_and_fetch_floppy_image.sh` builds the image with `podman` (swap `OCI_TOOL`
for `docker`), creates a throwaway container, and copies `/nlm_disk.img` to
`~/Downloads/nlm_disk.img` — quick Dockerfile iteration without a devcontainer session.
