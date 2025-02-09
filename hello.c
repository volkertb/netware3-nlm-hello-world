#define N_PLAT_NLM                                /* Define dest. platform */

#include <nwconio.h>                              /* ConsolePrintf */

int
main (int argc, char **argv)
{
  int i;

  ConsolePrintf ("\rHello world!\n\n");           /* print on system console */

  ConsolePrintf("Arguments:\n");                  /* all arguments */
  for (i=0;i<argc;i++)
   ConsolePrintf("argv[%u]=\"%s\"\n",i, argv[i]);

  return 0;                                       /* exit NLM */
}
