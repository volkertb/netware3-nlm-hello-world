# Devcontainer notes

Detail behind `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json` that's useful for
future changes but too long to keep in `AGENTS.md`.

## Stage layout

`.devcontainer/Dockerfile` is 4 stages, forming a DAG (each stage `COPY --from=` an earlier one;
apt-installed packages do **not** carry across a `COPY` — only explicitly copied paths do):

1. **`downloader-and-patcher`** (`debian:13.6`) — fetches all 4 large external downloads
   (binutils source, Novell NDK ISO, nlm-samples, nlm-kit) once into a
   `RUN --mount=type=cache,target=/downloads-cache` cache mount, copies them into `/Downloads` in
   the image, and also **extracts and patches the binutils source tree** (`/Downloads/binutils-2.30`).
   Every later stage that needs one of these does `COPY --from=downloader-and-patcher ...` instead
   of downloading/preparing it again. Consolidated here (rather than duplicated per-stage)
   specifically so downloading *and* source preparation happen on a current Debian where
   `wget`/`ca-certificates`/`tar`/`xz-utils`/`patch` install trivially — the EOL Debian 9 stage
   below is left with nothing but configure+make.
   - Each download is gated by a self-healing checksum check:
     `[ -f cached ] && sha256sum --status -c - || wget ... && sha256sum -c - && cp ...`. Because `&&`
     and `||` in POSIX shell are left-to-right, equal precedence, this redownloads automatically if
     the cached file is missing *or* fails its checksum (e.g. left partial by an interrupted build),
     rather than getting permanently stuck.
   - This uses `RUN --mount=type=cache` + `wget` rather than Dockerfile's built-in
     `ADD --checksum=`, because `ADD` doesn't support `--mount` at all — there'd be no way to cache
     the download itself, only re-fetch it (or bake it into a layer) on every build.
   - The binutils source is patched three ways before building (full background:
     [nlm-toolchain-notes.md](nlm-toolchain-notes.md)): `COPY`-replaced forks
     `.devcontainer/nlmconv.c` (verbose ld, clearer errors, and a fix for an upstream bug that
     mis-resolved internal PC-relative relocs from code sections at nonzero output offsets — the
     likely cause of the 2025 run-time abends) and `.devcontainer/bfd/nlm32-i386.c` (restores the
     "absolute internal relocs only" check that an earlier fork had disabled, with actionable
     error messages); plus `.devcontainer/patches/0001-nlmheader-bad-number-is-an-error.patch`,
     applied with `patch(1)`, which makes malformed `.def` numbers (e.g. `STACK bladiebla`) fail
     the build instead of silently writing 0 into the header. That patch covers both `nlmheader.y`
     and the shipped bison-generated `nlmheader.c`, and the `.c` is `touch`ed (again defensively in
     `binutils-builder` after the `COPY --from`, in case relative mtimes aren't preserved) so make
     never tries to invoke bison, which is installed nowhere in the Dockerfile.
2. **`binutils-builder`** (`debian:9.13`, "Stretch") — the *only* stage on EOL Debian 9, and kept
   to the bare minimum that actually needs it: configure+make of binutils 2.30 with
   `--enable-targets=i386-netware --enable-obsolete` to get `nlmconv` and the `nlm32-i386` BFD
   target. This support was removed from binutils upstream after 2.31, and nothing upstream tests
   these obsolete targets against modern GCC/glibc, hence the old-enough (period-matched)
   toolchain. The source arrives already extracted and patched via `COPY --from=downloader-and-patcher`.
   `RUN linux32 ./configure ...` fakes `uname -m` (via `config.guess`) during the *build-triple
   detection* step — this does not make the resulting `nlmconv`/`ld` 32-bit binaries; they're native
   x86_64 tools that happen to understand a 32-bit target object format, no different from any
   cross-toolchain. (Confirmed empirically: `builder`'s `RUN nlmconv --version && i386-netware-ld -v`
   sanity check succeeds immediately after copying `/usr/local` in, before `gcc-multilib`/any 32-bit
   runtime support is installed in that stage — a real 32-bit ELF couldn't have executed at that point.)
   Debian 9's archived apt repo (`archive.debian.org`) is enough here because this stage only needs
   `build-essential` and `texinfo` — no `debian-security`-only packages.
   - After `make install`, `/usr/local` is pruned to just `nlmconv`, `i386-netware-ld`, and
     `i386-netware-objdump` (~140 MB of libs/headers/tooldir copies deleted). The renames are
     load-bearing, not cosmetic: binutils 2.30 installs a full plain-named toolset, and gcc
     resolves subprograms via PATH where `/usr/local/bin` wins — on Debian ≥ 12 (gcc ≥ 11,
     DWARF 5 default) host compiles then die with `as: unrecognized option '--gdwarf-5'` because
     gas 2.30 predates it. Cross-tool-style names can never be picked up by accident; nlmconv's
     fork defaults `LD_NAME` to `i386-netware-ld`, so no Makefile changes were needed.
3. **`builder`** (`debian:13.6`) — everything else that used to require Debian 9 but doesn't:
   extracts the NDK ISO, builds `nlm-kit` (which is what actually produces `/usr/bin/nlmimp` — it's
   *not* part of binutils, despite living in `/usr/bin`; easy to misattribute), and does a full test
   build of the sample `hello` NLM plus packages `/nlm_disk.img` via `mtools`. Receives
   `/usr/local` (the binutils-builder output) via `COPY --from=binutils-builder`.
4. **`dev-env`** (`debian:13.6`) — the actual devcontainer image. Copies the built artifacts
   (`/nlm_disk.img`, `/usr/local`, `/usr/nwsdk`, `/usr/bin/nlmimp`) from `builder`, installs
   JetBrains dev-container prerequisites plus debugging/analysis CLI tools (python3, xxd, file,
   bsdextrautils, qemu-utils, socat, jq, ripgrep, shellcheck, strace — installed with
   `--no-install-recommends`; `qemu-system-x86` is deliberately absent, the QEMU VM itself is
   planned as a sidecar container), creates the non-root `dev-container-user`, installs Claude
   Code natively (`curl -fsSL https://claude.ai/install.sh | bash` — not the npm-based devcontainer
   Feature, which left a root-owned leftover that broke auto-update permissions for a non-root user),
   and repeats the sample-NLM test build as the non-root user as a smoke test.

## Debian base images (bumped to 13.6 on 2026-07-19)

The three non-Stretch stages run `debian:13.6` (trixie), bumped from `11.11` ahead of Debian 11's
LTS end (**2026-08-31**), after which bullseye's apt repos move to `archive.debian.org` and every
stage would have inherited the EOL-archive problems confined to `binutils-builder`. The bump's
fallout — the binutils 2.30 install shadowing the host toolchain once gcc ≥ 11 became the host
compiler — is covered in the `binutils-builder` stage notes above. Only `binutils-builder`
legitimately stays on Debian 9; when Debian 13 itself ages out, expect the same class of exercise
(and re-verify the nlm-kit and sample-NLM builds against the newer default gcc).

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
happened twice already, in the downloader stage and `binutils-builder`, during the stage split) —
check for it whenever adding a stage.

A related trap (hit 2026-07-19, "Unable to locate package patch"): appending a new
`apt -y install` layer to an already-built stage does **not** re-run that stage's earlier
`apt -y update` layer — it's a layer-cache hit — while the `/var/lib/apt` cache mount it once
populated may have been pruned since. The new layer then sees empty package lists. When adding an
install to an *existing* stage, either put `apt -y update &&` in the same `RUN` (the pattern the
`downloader-and-patcher` stage uses) or expect to bust the stage's layer cache.

For troubleshooting a stale/corrupt cache directly on the host: under rootless Podman, `--mount=type=cache`
data lives at `${TMPDIR:-/var/tmp}/buildah-cache-<uid>` on whichever machine actually runs
`podman build` (not inside any container) — this applies to the `/downloads-cache` mount too, not
just the apt ones.

## `binutils-builder`'s `sources.list`

Debian 9 is EOL and archived at `archive.debian.org`. Note `binutils-builder`'s `sources.list` is
deliberately just the plain archive main/contrib/non-free line — it does *not* need the
`debian-security` suite or `Acquire::Check-Valid-Until "false"` override, because it only ever
installs `build-essential`/`texinfo`, none of which happened to hit an unresolvable
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
