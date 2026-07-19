#define N_PLAT_NLM                                /* Define dest. platform */

#include <nwconio.h>                              /* ConsolePrintf */

#include "implicit_nlm_defs.h"
#include "vgamode.c"

#define CP437_SMILEY_FACE_CHAR 0x01
#define BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND 0x0A;

/* 
 * example for 320x200 VGA
 * Copied from https://wiki.osdev.org/Drawing_In_a_Linear_Framebuffer
 */
void putpixel(int pos_x, int pos_y, unsigned char VGA_COLOR)
{
    unsigned char* location = (unsigned char*)0xA0000 + 320 * pos_y + pos_x;
    *location = VGA_COLOR;
}

/**
 * Just write some characters directly to the text mode screen buffer.
 */
void putTextChars() {

  *(volatile char *)0xb8300 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8301 = BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8302 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8303 = BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8304 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8305 = BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8306 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8307 = BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND;
  *(volatile char *)0xb8308 = CP437_SMILEY_FACE_CHAR;
  *(volatile char *)0xb8309 = BRIGHT_GREEN_TEX_ON_BLACK_BACKGROUND;
}

/**
 * With thanks to https://dev.to/frosnerd/writing-my-own-vga-driver-22nn
 */
void set_vga_cursor(int offset) {

  #define VGA_CTRL_REGISTER 0x3d4
  #define VGA_DATA_REGISTER 0x3d5
  #define VGA_OFFSET_LOW 0x0f
  #define VGA_OFFSET_HIGH 0x0e

  offset /= 2;
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_HIGH);
    outp(VGA_DATA_REGISTER, (unsigned char) (offset >> 8));
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_LOW);
    outp(VGA_DATA_REGISTER, (unsigned char) (offset & 0xff));
}

/**
 * With thanks to https://dev.to/frosnerd/writing-my-own-vga-driver-22nn
 */
int get_vga_cursor() {
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_HIGH);
    int offset = inp(VGA_DATA_REGISTER) << 8;
    outp(VGA_CTRL_REGISTER, VGA_OFFSET_LOW);
    offset += inp(VGA_DATA_REGISTER);
    return offset * 2;
}

int
main (int argc, char **argv)
{
  int i;

  ConsolePrintf ("\rHello world! %c\n\n", CP437_SMILEY_FACE_CHAR);           /* print on system console */
  ConsolePrintf("\rBuild date: INSERT_TIMESTAMP_HERE\n");

  ConsolePrintf("\rArguments:\n");                  /* all arguments */
  for (i=0;i<argc;i++)
   ConsolePrintf("\rargv[%u]=\"%s\"\n",i, argv[i]);

  ConsolePrintf("\n\r"); // Make sure the command prompt starts at the beginning below an empty line when this application/module exits.

  putTextChars();
  int current_cursor_position = get_vga_cursor();
  ConsolePrintf ("\rCurrent cursor position: %d\n\n", current_cursor_position);
  // setVGACursor(320);

  /* turn off speaker */
  //outp (0x61,inp (0x61) & 0xFC);

  // Use VGA routines in modes.c
	// dump_state();
	// set_text_mode(1);
  // demo_graphics();
	// font512();

  putpixel(160,100, 0x10);
  putpixel(160,110, 0xff);

  const int delay_before_vga_switch_in_seconds = 3;
  ConsolePrintf("\n\rDelaying %d secs BEFORE switching to VGA graphics mode...\n\r", delay_before_vga_switch_in_seconds);
  delay(delay_before_vga_switch_in_seconds * 1000); // Delay x seconds.

  ConsolePrintf("\n\rSwitching to VGA graphics mode...\n\r");

  // Switch to VGA graphics code using code in vgamode.c
  int mode_switching_result = init_graph_vga(320, 200, 1);

  if (mode_switching_result == 1) {
    ConsolePrintf("Switch to VGA graphics mode successful. (This text might not even be readable.)\n\r");
  } else {
    ConsolePrintf("Switch to VGA graphics mode failed.\n\r");
  }

  return 0;                                       /* exit NLM */
}
