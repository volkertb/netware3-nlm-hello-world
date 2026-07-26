# Applicable licenses in this project and dependencies of this project

## Novell NDK

Copyright owned by whomever owns Novell nowadays (OpenText, I believe). Dockerfile pulls it in from the Internet Archive.

Although Novell only ever offered the NDK behind a registration wall, none of the original download sites are on-line anymore as of April 2025. The only site where I could find a copy was the Internet Archive. When building the dev container for this project, the Dockerfile pulls the ISO from there.

## "Yes, it runs with NetWare" logo (pics/yes_netware_320x200.png)

Copyright owned by whomever owns Novell nowadays (see "Novell NDK" above). Used here purely as an
homage to NetWare in a graphics-mode experiment - this project is not officially certified or
endorsed by Novell (or its current rights holder) in any way.

## nlm-kit and nlm-samples

Copyright Martin Hinner, released under LGPLv2.

See `COPYING.LIB` file that comes with nlm-kit and the `COPYING` file that comes with nlm-samples.

## binutils 2.3.0

From the `README`:

> Much of the code and documentation enclosed is copyright by
> the Free Software Foundation, Inc.  See the file COPYING or
> COPYING.LIB in the various directories, for a description of the
> GNU General Public License terms under which you can copy the files.

## Dockerfile

Copyright 2025, Volkert de Buisonjé, released under the Apache License 2.0.

## NLM sources in the repo root (hello.c, hello_vga.c, *.def, Makefile)

Derived from Martin Hinner's nlm-samples "hello" (LGPLv2, see above), substantially modified by
Volkert de Buisonjé.

## VGA mode-setting code (vgamode.c, nlm_io_wrapper.c, putpixel in hello_vga.c)

Copied/adapted from osdev.org forum posts and the OSDev wiki's "Drawing In a Linear Framebuffer"
page; exact source URLs are kept in the file headers. The forum posts state no explicit license,
so treat these files as attribution-only reference code rather than clearly-licensed. If license
clarity ever matters, equivalent register-programming code exists in Chris Giese's explicitly
public-domain modes.c (mirror link in README.md), which these could be rebased onto.

## Music asset (downloads/DUNE0.ADL)

Copyright Westwood Studios (Dune II: The Building of a Dynasty, 1992) / its current rights
holder - unlike `pics/yes_netware_320x200.png` above, not committed to this repo. The Makefile
fetches it at build time (checksum-verified, same pattern the Dockerfile uses for its own
downloads) from
https://github.com/katlogic/dunelegacy/raw/refs/heads/master/data/DUNE0.ADL - the `dunelegacy`
project (a GPLv2 Dune II engine reimplementation) purely as a convenient mirror of the original
game data file; `dunelegacy`'s own GPLv2 license does not apply to this asset, only to that
project's own engine code. Used here as a period-correct sound test, the audio equivalent of the
"Yes, it runs with NetWare" logo homage above - not a claim of rights over the asset.

## ADL-format conversion tool (music/adl_to_c.py)

Copyright Volkert de Buisonjé, licensed LGPL-2.1-or-later. Written by Claude (Anthropic) under
the human maintainer's direction/review - the header/pointer-table layout of the Westwood ADL
container was reverse-engineered by Claude from the raw file bytes plus public wiki documentation
(moddingwiki/vgmpf "ADL (Westwood)", both GFDL); the per-channel bytecode VM inside it - the
opcode table, register-offset/frequency/pitch-bend tables, and the slide/vibrato/secondary-effect
algorithms - is a line-for-line Python port Claude made of AdPlug's `src/adl.cpp` (Copyright
1999-2025 Simon Peter et al., LGPL-2.1-or-later), itself adapted from ScummVM's Kyra engine
`adlib.cpp`; `src/adl.h`, `src/composer.h`, and `src/rol.h` were also read for API shape and the
72Hz tick rate. Only this build-time conversion tool carries that derivation and its license -
the NLM-side player it feeds (adlib_util.c) has no ADL-specific logic at all, just a generic
OPL2 register-write/timing player, and ships under this project's normal license.
