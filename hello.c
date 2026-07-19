#define N_PLAT_NLM                                /* Define dest. platform */

#include <nwconio.h>                              /* ConsolePrintf */

#include "implicit_nlm_defs.h"
#include "vga_util.h"

int
main (int argc, char **argv)
{
  int i;

  ConsolePrintf ("\rHello world! %c\n\n", CP437_SMILEY_FACE_CHAR);
  ConsolePrintf("\rBuild date: INSERT_TIMESTAMP_HERE\n");

  ConsolePrintf("\rArguments:\n");                  /* all arguments */
  for (i=0;i<argc;i++) {
    ConsolePrintf("\r  %cargv[%u]=\"%s\"\n", CP437_BULLET_ITEM_CHAR,i, argv[i]);
  }

  /* turn off speaker */
  outp (0x61,inp (0x61) & 0xFC);

  /* try accessing the VGA registers */
  // outp(VGA_CTRL_REGISTER, VGA_OFFSET_HIGH);
  // int offset = inp(VGA_DATA_REGISTER) << 8;
  // outp(VGA_CTRL_REGISTER, VGA_OFFSET_LOW);
  // offset += inp(VGA_DATA_REGISTER);

  // int current_cursor_position = offset * 2;
  //int current_cursor_position = get_vga_cursor();

  //ConsolePrintf ("\rCurrent cursor position: %d\n", current_cursor_position);

  ConsolePrintf("\n\r"); // Make sure the command prompt starts at the beginning below an empty line when this application/module exits.

  delay(3000);

  putTextChars();

  return 0;                                       /* exit NLM */
}
