# Devcontainer notes

Detail behind `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json` that's useful for
future changes but too long to keep in `AGENTS.md`.

## Stage layout

`.devcontainer/Dockerfile` is 4 stages, forming a DAG (each stage `COPY --from=` an earlier one;
apt-installed packages do **not** carry across a `COPY` — only explicitly copied paths do):

1. **`downloader`** (`debian:11.11`) — fetches all 4 large external downloads (binutils source,
   Novell NDK ISO, nlm-samples, nlm-kit) once into a `RUN --mount=type=cache,target=/downloads-cache`
   cache mount, and copies them into `/Downloads` in the image. Every later stage that needs one of
   these files does `COPY --from=downloader /Downloads/<file> ...` instead of downloading it again.
   Consolidated here (rather than duplicated per-stage) specifically so the binutils download,
   needed only by `binutils-builder`, could also be cached without installing `wget`/`ca-certificates`
   a second time on Debian 9.
   - Each download is gated by a self-healing checksum check:
     `[ -f cached ] && sha256sum --status -c - || wget ... && sha256sum -c - && cp ...`. Because `&&`
     and `||` in POSIX shell are left-to-right, equal precedence, this redownloads automatically if
     the cached file is missing *or* fails its checksum (e.g. left partial by an interrupted build),
     rather than getting permanently stuck.
   - This uses `RUN --mount=type=cache` + `wget` rather than Dockerfile's built-in
     `ADD --checksum=`, because `ADD` doesn't support `--mount` at all — there'd be no way to cache
     the download itself, only re-fetch it (or bake it into a layer) on every build.
2. **`binutils-builder`** (`debian:9.13`, "Stretch") — the *only* stage on EOL Debian 9. Compiles
   binutils 2.30 with `--enable-targets=i386-netware --enable-obsolete` to get `nlmconv` and the
   `nlm32-i386` BFD target. This support was removed from binutils upstream after 2.31, and nothing
   upstream tests these obsolete targets against modern GCC/glibc — even on this period-matched
   toolchain, `nlmconv.c` and `bfd/nlm32-i386.c` need source patches (applied via `COPY` from
   `.devcontainer/nlmconv.c` and `.devcontainer/bfd/nlm32-i386.c`) to build and behave correctly.
   `RUN linux32 ./configure ...` fakes `uname -m` (via `config.guess`) during the *build-triple
   detection* step — this does not make the resulting `nlmconv`/`ld` 32-bit binaries; they're native
   x86_64 tools that happen to understand a 32-bit target object format, no different from any
   cross-toolchain. (Confirmed empirically: `builder`'s `RUN nlmconv --version && ld -v` sanity check
   succeeds immediately after copying `/usr/local` in, before `gcc-multilib`/any 32-bit runtime
   support is installed in that stage — a real 32-bit ELF couldn't have executed at that point.)
   Debian 9's archived apt repo (`archive.debian.org`) is enough here because this stage only needs
   `xz-utils`, `build-essential`, and `texinfo` — no `debian-security`-only packages.
3. **`builder`** (`debian:11.11`) — everything else that used to require Debian 9 but doesn't:
   extracts the NDK ISO, builds `nlm-kit` (which is what actually produces `/usr/bin/nlmimp` — it's
   *not* part of binutils, despite living in `/usr/bin`; easy to misattribute), and does a full test
   build of the sample `hello` NLM plus packages `/nlm_disk.img` via `mtools`. Receives
   `/usr/local` (the binutils-builder output) via `COPY --from=binutils-builder`.
4. **`dev-env`** (`debian:11.11`) — the actual devcontainer image. Copies the built artifacts
   (`/nlm_disk.img`, `/usr/local`, `/usr/nwsdk`, `/usr/bin/nlmimp`) from `builder`, installs
   JetBrains dev-container prerequisites, creates the non-root `dev-container-user`, installs Claude
   Code natively (`curl -fsSL https://claude.ai/install.sh | bash` — not the npm-based devcontainer
   Feature, which left a root-owned leftover that broke auto-update permissions for a non-root user),
   and repeats the sample-NLM test build as the non-root user as a smoke test.

## apt caching pattern (every stage)

Every stage that uses apt does two things:

```dockerfile
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt -y install ...
```

Debian base images delete downloaded `.deb`s after every `apt install` by default (`docker-clean`
hook) specifically to keep image layers small — but that's counterproductive with cache mounts,
which live outside the image layers anyway. Without disabling it, the cache mount would stay
perpetually empty. `sharing=locked` is required (not just `sharing=shared`) because concurrent stage
builds can race on the same apt cache; this is supported by Podman/buildah (added in
[containers/buildah#3820](https://github.com/containers/buildah/pull/3820), merged March 2022) —
don't assume otherwise without checking a primary source, an earlier AI-generated summary claimed
the opposite incorrectly.

Forgetting the `keep-cache` step in any *new* apt-using stage is an easy mistake to reintroduce (it's
happened twice already, in `downloader` and `binutils-builder`, during the stage split) — check for
it whenever adding a stage.

For troubleshooting a stale/corrupt cache directly on the host: under rootless Podman, `--mount=type=cache`
data lives at `${TMPDIR:-/var/tmp}/buildah-cache-<uid>` on whichever machine actually runs
`podman build` (not inside any container) — this applies to the `/downloads-cache` mount too, not
just the apt ones.

## `binutils-builder`'s `sources.list`

Debian 9 is EOL and archived at `archive.debian.org`. Note `binutils-builder`'s `sources.list` is
deliberately just the plain archive main/contrib/non-free line — it does *not* need the
`debian-security` suite or `Acquire::Check-Valid-Until "false"` override, because it only ever
installs `xz-utils`/`build-essential`/`texinfo`, none of which happened to hit an unresolvable
point-release-pinned transitive dependency. If a future change adds a package here that does hit that
class of failure (seen previously with `curl`→`libcurl3` and `wget`→`libgnutls30` in the old,
single-stage Dockerfile), the fix is adding the `debian-security stretch/updates` suite line plus the
`Check-Valid-Until` override — not swapping tools.

## Session/agent-state persistence

`devcontainer.json` mounts a generically-named volume at `~/.agent-state` and runs
`.devcontainer/postCreate.local.sh` if present — a **gitignored**, per-developer script, so
`devcontainer.json` itself names no specific coding agent. That script (not committed; recreate it
per machine) symlinks `~/.claude` and `~/.claude.json` into the volume so a coding agent's session/
auth state survives container rebuilds. It's written to prefer already-persisted state over a fresh
image's state on conflict (`mv`-then-fallback-to-`rm`, not an unconditional overwrite), including the
case where both a pre-existing symlink target *and* a fresh unlinked copy exist post-rebuild — an
earlier, simpler version of the script nested the fresh copy inside the persisted one instead of
discarding it.

## Other `devcontainer.json` settings

- `containerUser: "dev-container-user"` silences a "user was not specified" error at the end of the
  JetBrains/Podman container image build; it must match the `USER` the Dockerfile actually switches
  to (or be `"root"` if the Dockerfile sets no explicit `USER`).
- `runArgs: ["--device=/dev/kvm"]` passes the host's KVM device through so a QEMU instance could use
  KVM acceleration to emulate a NetWare 3.x machine for end-to-end testing (booting `floppy.img` for
  real, rather than just confirming a clean `make`). No QEMU setup exists in this repo yet — this is
  forward-looking, not dead config — either running QEMU inside this container or in a sidecar this
  container talks to are both viable and undecided. Needs `/dev/kvm` to already be host-accessible
  (mode 0666 here via systemd's default udev rule); a host where it's `kvm`-group-locked instead
  would additionally need Podman's `--group-add=keep-groups`.

## `~/.local/bin` on `PATH`

`dev-env` sets `ENV PATH="/home/$USERNAME/.local/bin:$PATH"` explicitly rather than relying on
Debian's `~/.profile` skel default, because that default is only sourced by *login* shells — VS
Code's integrated terminal and most tooling spawn non-login shells. This isn't agent-specific: any
user-installed CLI under `~/.local/bin` (Claude Code's native installer included) needs this.

## Local build/test loop

`.devcontainer/build_and_fetch_floppy_image.sh` builds the image with `podman` (swap `OCI_TOOL` for
`docker` if needed), creates a throwaway container, and copies `/nlm_disk.img` out to
`~/Downloads/nlm_disk.img` without needing a full devcontainer session — useful for quick Dockerfile
iteration.
