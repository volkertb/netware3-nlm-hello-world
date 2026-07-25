#include "implicit_nlm_defs.h"
#include "vga_util.h"

#include <nwadv.h>                                /* unused; see docs/ndk-independence.md Tier 1 */

#define BRIGHT_GREEN_TEXT_ON_BLACK_BACKGROUND 0x0A;

#define VGA_CTRL_REGISTER 0x3d4
#define VGA_DATA_REGISTER 0x3d5
#define VGA_OFFSET_LOW 0x0f
#define VGA_OFFSET_HIGH 0x0e

#define VGA_DAC_WRITE_INDEX 0x3c8
#define VGA_DAC_READ_INDEX 0x3c7
#define VGA_DAC_DATA 0x3c9

#define TEXT_BUFFER_SIZE (80 * 25 * 2)

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
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_HIGH);
    unsigned int offset = inp(VGA_DATA_REGISTER) << 8;
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_LOW);
    offset += inp(VGA_DATA_REGISTER);
    const unsigned int multiplier = 2;
    return offset * multiplier;
}

static unsigned char saved_text_buffer[TEXT_BUFFER_SIZE];

void save_text_buffer() {
  unsigned char *text_buffer = (unsigned char *)0xB8000;
  int i;
  for (i = 0; i < TEXT_BUFFER_SIZE; i++) {
    saved_text_buffer[i] = text_buffer[i];
  }
}

void restore_text_buffer() {
  unsigned char *text_buffer = (unsigned char *)0xB8000;
  int i;
  for (i = 0; i < TEXT_BUFFER_SIZE; i++) {
    text_buffer[i] = saved_text_buffer[i];
  }
}

/**
 * Stored as the DAC's own raw 6-bit-per-channel values (not rescaled 8-bit), so restoring is a
 * direct write-back with no further shifting.
 */
static unsigned char saved_dac_palette[256 * 3];

void save_vga_palette() {
  int i;
  outp(VGA_DAC_READ_INDEX, 0);
  for (i = 0; i < 256 * 3; i++) {
    saved_dac_palette[i] = inp(VGA_DAC_DATA);
  }
}

void restore_vga_palette() {
  int i;
  outp(VGA_DAC_WRITE_INDEX, 0);
  for (i = 0; i < 256 * 3; i++) {
    outp(VGA_DAC_DATA, saved_dac_palette[i]);
  }
}
