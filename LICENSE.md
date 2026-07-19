# Applicable licenses in this project and dependencies of this project

## Novell NDK

Copyright owned by whomever owns Novell nowadays (OpenText, I believe). Dockerfile pulls it in from the Internet Archive.

Although Novell only ever offered the NDK behind a registration wall, none of the original download sites are on-line anymore as of April 2025. The only site where I could find a copy was the Internet Archive. When building the dev container for this project, the Dockerfile pulls the ISO from there.

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

## NLM sources in the repo root (hello.c, hello_old.c, *.def, Makefile)

Derived from Martin Hinner's nlm-samples "hello" (LGPLv2, see above), substantially modified by
Volkert de Buisonjé.

## VGA mode-setting code (vgamode.c, nlm_io_wrapper.c, putpixel in hello_old.c)

Copied/adapted from osdev.org forum posts and the OSDev wiki's "Drawing In a Linear Framebuffer"
page; exact source URLs are kept in the file headers. The forum posts state no explicit license,
so treat these files as attribution-only reference code rather than clearly-licensed. If license
clarity ever matters, equivalent register-programming code exists in Chris Giese's explicitly
public-domain modes.c (mirror link in README.md), which these could be rebased onto.
