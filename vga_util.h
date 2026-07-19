#ifndef VGA_UTIL_H
#define VGA_UTIL_H

#define CP437_SMILEY_FACE_CHAR 0x01
#define CP437_BULLET_ITEM_CHAR 0xf9

unsigned int get_vga_cursor();

/**
 * Just write some characters directly to the text mode screen buffer.
 */
void putTextChars();

#endif
