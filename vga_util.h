#ifndef VGA_UTIL_H
#define VGA_UTIL_H

#define CP437_SMILEY_FACE_CHAR 0x01
#define CP437_BULLET_ITEM_CHAR 0xf9

unsigned int get_vga_cursor();

/**
 * Just write some characters directly to the text mode screen buffer.
 */
void putTextChars();

/**
 * Save/restore the 80x25 text buffer (0xB8000) and the VGA DAC palette around a graphics-mode
 * excursion - set_text_mode()-style register reprogramming alone doesn't touch either, and
 * 0xA0000/0xB8000 are different addressing views of the same physical VRAM, so a graphics-mode
 * NLM that writes its own framebuffer stomps what text mode reads back afterward otherwise.
 */
void save_text_buffer();
void restore_text_buffer();
void save_vga_palette();
void restore_vga_palette();

/**
 * Load a 256-entry RGB palette (8-bit-per-channel) into the VGA DAC, or fade it linearly to/from
 * black over `steps` steps (see vga_util.c for exact semantics).
 */
void set_vga_palette(const unsigned char *rgb_palette, int num_colors);
void set_vga_palette_black();
void fade_palette(const unsigned char *target_rgb_palette,
                  int num_colors,
                  int steps,
                  int step_delay_ms,
                  int fade_in);

#endif
