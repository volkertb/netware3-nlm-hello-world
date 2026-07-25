#!/usr/bin/env python3
"""Convert an 8bpp/256-color PCX file into a C source+header pair of const arrays
(raw chunky pixel indices + RGB palette), for compiling directly into an NLM.
Build-time only - not part of the NLM's own toolchain, no NDK/NLM constraints apply here.
"""
import struct
import sys


def decode_pcx(data):
    if data[0] != 10:
        raise ValueError("not a PCX file (bad manufacturer byte)")
    if data[3] != 8 or data[65] != 1:
        raise ValueError("only 8bpp single-plane (256-color) PCX is supported")
    if data[-769] != 0x0C:
        raise ValueError("missing 256-color VGA palette trailer")

    xmin, ymin, xmax, ymax = struct.unpack("<HHHH", data[4:12])
    width = xmax - xmin + 1
    height = ymax - ymin + 1
    bytes_per_line = struct.unpack("<H", data[66:68])[0]

    pixels = bytearray()
    pos = 128
    for _ in range(height):
        row = bytearray()
        while len(row) < bytes_per_line:
            b = data[pos]
            pos += 1
            if (b & 0xC0) == 0xC0:
                count = b & 0x3F
                value = data[pos]
                pos += 1
                row.extend([value] * count)
            else:
                row.append(b)
        pixels.extend(row[:width])

    palette = data[-768:]
    return width, height, bytes(pixels), bytes(palette)


def write_output(c_path, h_path, guard, width, height, pixels, palette):
    with open(h_path, "w", encoding="utf-8") as f:
        f.write(f"#ifndef {guard}\n#define {guard}\n\n")
        f.write(f"#define EMBEDDED_PIC_WIDTH {width}\n")
        f.write(f"#define EMBEDDED_PIC_HEIGHT {height}\n\n")
        f.write("extern const unsigned char embedded_pic_pixels[];\n")
        f.write("extern const unsigned char embedded_pic_palette[];\n\n")
        f.write("#endif\n")

    with open(c_path, "w", encoding="utf-8") as f:
        f.write(f'#include "{h_path.split("/")[-1]}"\n\n')
        f.write(
            f"const unsigned char embedded_pic_pixels[{len(pixels)}] = {{\n"
        )
        for i in range(0, len(pixels), 20):
            f.write(",".join(str(b) for b in pixels[i:i + 20]) + ",\n")
        f.write("};\n\n")
        f.write(f"const unsigned char embedded_pic_palette[{len(palette)}] = {{\n")
        for i in range(0, len(palette), 20):
            f.write(",".join(str(b) for b in palette[i:i + 20]) + ",\n")
        f.write("};\n")


def main():
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} input.pcx output.c output.h", file=sys.stderr)
        return 1

    pcx_path, c_path, h_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(pcx_path, "rb") as f:
        data = f.read()

    width, height, pixels, palette = decode_pcx(data)
    guard = h_path.split("/")[-1].upper().replace(".", "_")
    write_output(c_path, h_path, guard, width, height, pixels, palette)
    print(f"{pcx_path}: {width}x{height}, {len(pixels)} pixel bytes, "
          f"{len(palette)} palette bytes -> {c_path}, {h_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
