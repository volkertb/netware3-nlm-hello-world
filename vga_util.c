#include "implicit_nlm_defs.h"
#include "vga_util.h"

#include <nwadv.h>                                /* Int68, NetWare's safe proxy for BIOS Int 10h */

#define BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND 0x0A;

#define VGA_CTRL_REGISTER 0x3d4
#define VGA_DATA_REGISTER 0x3d5
#define VGA_OFFSET_LOW 0x0f
#define VGA_OFFSET_HIGH 0x0e

/**
 * Just write some characters directly to the text mode screen buffer.
 */
inline void putTextChars() {

  *(volatile char *)0xb8300 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8301 = BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8302 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8303 = BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8304 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8305 = BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8306 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8307 = BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8308 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8309 = BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND;
}

/**
 * With thanks to https://dev.to/frosnerd/writing-my-own-vga-driver-22nn
 */
inline unsigned int get_vga_cursor() {
    return 0; // FIXME
    // outp(VGA_CTRL_REGISTER, VGA_OFFSET_HIGH);
    // int offset = inp(VGA_DATA_REGISTER) << 8;
    // outp(VGA_CTRL_REGISTER, VGA_OFFSET_LOW);
    // offset += inp(VGA_DATA_REGISTER);
    // const unsigned int multiplier = 2;
    // return offset * multiplier;
}
