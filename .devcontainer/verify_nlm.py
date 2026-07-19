#!/usr/bin/env python3
"""Deep sanity check for an NLM produced by this repo's nlmconv toolchain.

Usage: verify-nlm <file.nlm> <file.def>

Independently re-derives what the NLM's code/data images *should* contain and
compares against what nlmconv actually wrote. Catches the whole class of
relocation-corruption bugs behind the 2025 NetWare abends (see
docs/nlm-toolchain-notes.md) without needing to boot anything:

  1. NLM signature and a nonzero stack-size header field (offset 164), matched
     against the .def's STACK value when present.
  2. Re-runs the same `i386-netware-ld -Ur` pre-link nlmconv performs (inputs
     taken from the .def's INPUT lines, resolved from the working directory),
     then parses the resulting ELF intermediate directly - sections, symbols,
     relocations - with no dependency on objdump's text output.
  3. Replicates nlmconv's section-placement math (code sections concatenated
     with alignment into the code image, loadable data sections into the data
     image, .bss appended after the data image) and cross-checks the computed
     image sizes against the NLM header's - a mismatch means the replication
     no longer matches nlmconv and all bets are off, so that is itself fatal.
  4. For every relocation in every loadable section, computes the exact bytes
     the NLM must contain at that site and compares:
       - R_386_PC32 vs defined symbol: S + A - P (resolved at convert time;
         the 2025 bug wrote these short by the section's output offset).
       - R_386_PC32 / R_386_32 vs undefined symbol (import): bytes unchanged
         from the intermediate (the loader patches them via import fixups).
       - R_386_32 vs defined symbol: S + A in image-relative coordinates
         (the loader adds the image base via an internal relocation fixup).
     Any other relocation type in a loadable section is an error.

Exit status: 0 = all checks passed, 1 = verification failure, 2 = usage/setup.
"""

import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

STACK_SIZE_HEADER_OFFSET = 164  # empirically located; see nlm-toolchain-notes.md

R_386_32 = 1
R_386_PC32 = 2

SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB, SHT_REL, SHT_NOBITS, SHT_NOTE = 1, 2, 3, 9, 8, 7
SHF_ALLOC, SHF_EXECINSTR = 0x2, 0x4
SHN_UNDEF, SHN_ABS, SHN_COMMON = 0, 0xFFF1, 0xFFF2

failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL: {msg}", file=sys.stderr)


def parse_def(def_path):
    inputs, stack = [], None
    for line in Path(def_path).read_text().splitlines():
        # Keyword/argument separators may be tabs (the nlm-samples .def uses
        # them), and vintage files are CRLF; split on any whitespace.
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if fields[0] == "INPUT":
            inputs.extend(fields[1:])
        elif fields[0] in ("STACK", "STACKSIZE") and len(fields) > 1:
            stack = int(fields[1])
    return inputs, stack


class Elf32:
    """Minimal little-endian ELF32 REL reader - just what this check needs."""

    def __init__(self, path):
        self.data = Path(path).read_bytes()
        if self.data[:6] != b"\x7fELF\x01\x01":
            raise ValueError(f"{path}: not a little-endian ELF32 file")
        (e_shoff,) = struct.unpack_from("<I", self.data, 0x20)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", self.data, 0x2E)
        raw = [
            struct.unpack_from("<10I", self.data, e_shoff + i * e_shentsize)
            for i in range(e_shnum)
        ]
        shstr = raw[e_shstrndx]
        self.sections = [
            {
                "name": self._cstr(shstr[4] + s[0]),
                "type": s[1], "flags": s[2], "offset": s[4],
                "size": s[5], "link": s[6], "info": s[7], "addralign": s[8],
            }
            for s in raw
        ]

    def _cstr(self, off):
        end = self.data.index(b"\0", off)
        return self.data[off:end].decode()

    def symbols(self, symtab_index):
        symtab = self.sections[symtab_index]
        strtab = self.sections[symtab["link"]]
        for off in range(symtab["offset"], symtab["offset"] + symtab["size"], 16):
            st_name, st_value, st_size, st_info, _, st_shndx = struct.unpack_from(
                "<IIIBBH", self.data, off
            )
            yield {"name": self._cstr(strtab["offset"] + st_name),
                   "value": st_value, "shndx": st_shndx}

    def relocations(self, rel_index):
        rel = self.sections[rel_index]
        for off in range(rel["offset"], rel["offset"] + rel["size"], 8):
            r_offset, r_info = struct.unpack_from("<II", self.data, off)
            yield {"offset": r_offset, "sym": r_info >> 8, "type": r_info & 0xFF}

    def u32(self, sec, off):
        return struct.unpack_from("<I", self.data, self.sections[sec]["offset"] + off)[0]


def align_up(value, alignment):
    return value if alignment <= 1 else -(-value // alignment) * alignment


def nlm_section_table(nlm_path):
    """File offset + size of the NLM's merged .text/.data, via the only
    objdump that still reads nlm32-i386. Only the first (merged) row of each
    name counts - later rows echo the input sections."""
    out = subprocess.run(
        ["i386-netware-objdump", "-h", str(nlm_path)],
        capture_output=True, text=True, check=True,
    ).stdout
    table = {}
    for m in re.finditer(
        r"^\s*\d+\s+(\.\w+)\s+([0-9a-f]{8})\s+[0-9a-f]{8}\s+[0-9a-f]{8}\s+([0-9a-f]{8})",
        out, re.M,
    ):
        table.setdefault(m.group(1), (int(m.group(3), 16), int(m.group(2), 16)))
    return table  # name -> (file_offset, size)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    nlm_path, def_path = Path(sys.argv[1]), Path(sys.argv[2])
    nlm = nlm_path.read_bytes()

    # -- 1: header checks ----------------------------------------------------
    if nlm[:23] != b"NetWare Loadable Module":
        fail("bad NLM signature")
    inputs, def_stack = parse_def(def_path)
    (stack,) = struct.unpack_from("<I", nlm, STACK_SIZE_HEADER_OFFSET)
    if stack == 0:
        fail("stack size in header is 0 (missing/unparsed STACK in .def)")
    if def_stack is not None and stack != def_stack:
        fail(f"header stack size {stack} != .def STACK {def_stack}")

    # -- 2: reproduce nlmconv's pre-link and parse the intermediate -----------
    with tempfile.TemporaryDirectory() as tmp:
        linked = Path(tmp, "linked.O")
        subprocess.run(
            ["i386-netware-ld", "-Ur", "-o", str(linked)] + inputs, check=True
        )
        elf = Elf32(linked)

        # -- 3: replicate nlmconv's image layout ------------------------------
        # setup_sections: concatenate with per-section start alignment, and
        # raise each output section's alignment to the max input alignment.
        place, code_end, data_end, bss_end = {}, 0, 0, 0  # shndx -> (img, off)
        code_align, data_align, bss_align = 1, 1, 2  # nlmconv makes .bss 2^1
        for idx, sec in enumerate(elf.sections):
            if not sec["flags"] & SHF_ALLOC:
                continue
            if sec["flags"] & SHF_EXECINSTR:
                code_end = align_up(code_end, sec["addralign"])
                place[idx] = ("code", code_end)
                code_end += sec["size"]
                code_align = max(code_align, sec["addralign"])
            elif sec["type"] != SHT_NOBITS:
                data_end = align_up(data_end, sec["addralign"])
                place[idx] = ("data", data_end)
                data_end += sec["size"]
                data_align = max(data_align, sec["addralign"])
            else:
                bss_end = align_up(bss_end, sec["addralign"])
                place[idx] = ("bss", bss_end)
                bss_end += sec["size"]
                bss_align = max(bss_align, sec["addralign"])
        # nlmconv main pads .data to .bss alignment; the BFD backend
        # (nlmcode.h, BFD_ALIGN in compute_section_file_positions) then rounds
        # every output section's size up to that section's own alignment.
        code_end = align_up(code_end, code_align)
        data_end = align_up(align_up(data_end, bss_align), data_align)

        images = nlm_section_table(nlm_path)
        for image, end in ((".text", code_end), (".data", data_end)):
            if image not in images:
                fail(f"NLM has no {image} section")
                return 1
            if images[image][1] != end:
                fail(
                    f"layout replication mismatch: computed {image} size "
                    f"{end:#x} != NLM's {images[image][1]:#x} - script and "
                    f"nlmconv disagree, all further results would be unreliable"
                )
                return 1

        def image_addr(shndx, value):
            if shndx in place:
                image, off = place[shndx]
                base = data_end if image == "bss" else 0
                return image, base + off + value
            if shndx == SHN_ABS:
                return None, value
            return None, None

        # -- 4: verify every relocation site ----------------------------------
        counts = {"pcrel-internal": 0, "import": 0, "abs-internal": 0, "skipped": 0}
        symtab_idx = next(
            i for i, s in enumerate(elf.sections) if s["type"] == SHT_SYMTAB
        )
        syms = list(elf.symbols(symtab_idx))
        for rel_idx, rel_sec in enumerate(elf.sections):
            if rel_sec["type"] != SHT_REL:
                continue
            target_idx = rel_sec["info"]
            if target_idx not in place:
                continue  # relocs for debug/non-alloc sections
            site_image, site_base = place[target_idx]
            image_fileoff = images[".text" if site_image == "code" else ".data"][0]
            for r in elf.relocations(rel_idx):
                sym = syms[r["sym"]]
                where = f"{elf.sections[target_idx]['name']}+{r['offset']:#x} ({sym['name'] or '<section>'})"
                addend = elf.u32(target_idx, r["offset"])
                site = site_base + r["offset"]
                actual = struct.unpack_from("<I", nlm, image_fileoff + site)[0]
                if sym["shndx"] == SHN_COMMON:
                    counts["skipped"] += 1  # nlmconv-private .bss placement
                    continue
                if sym["shndx"] == SHN_UNDEF:  # import: loader patches at load
                    expected, kind = addend, "import"
                else:
                    _, s_addr = image_addr(sym["shndx"], sym["value"])
                    if s_addr is None:
                        fail(f"{where}: symbol in unplaced section {sym['shndx']}")
                        continue
                    if r["type"] == R_386_PC32:
                        expected, kind = (s_addr + addend - site) & 0xFFFFFFFF, "pcrel-internal"
                    elif r["type"] == R_386_32:
                        expected, kind = (s_addr + addend) & 0xFFFFFFFF, "abs-internal"
                    else:
                        fail(f"{where}: unsupported reloc type {r['type']}")
                        continue
                if actual != expected:
                    fail(
                        f"{where}: NLM contains {actual:#010x}, expected "
                        f"{expected:#010x} ({kind}) - relocation corrupted"
                    )
                else:
                    counts[kind] += 1

    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    if failures:
        print(f"verify-nlm: {nlm_path}: {len(failures)} FAILURE(S) ({summary})")
        return 1
    print(f"verify-nlm: {nlm_path}: OK (stack={stack}, {summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
