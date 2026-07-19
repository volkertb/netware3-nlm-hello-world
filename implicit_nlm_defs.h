#ifndef IMPLICIT_NLM_DEFS_H
#define IMPLICIT_NLM_DEFS_H

/*
 * Explicit declarations of functions that the NLM SDK will implicitly provide. 
 * Apparently, `outp`, `inp` and such as "public symbols" in NetWare, and don't need to be declared in any header files.
 * For documentation on these I/O functions, see https://www.novell.com/documentation/developer/clib/pdfdoc/ndev_enu/ndev_enu.pdf
 */

void delay(int milliseconds);

/**
 * Reads a byte from the specified I/O port
 * 
 * @return the value that was read from the device
 * 
 * (Should have been provided explicitly by nwconio.h)
 */
unsigned int inp(int port);

/**
 * Writes a byte to the specified I/O port
 * 
 * @return the value that was sent to the device
 * 
 * (Should have been provided explicitly by nwconio.h)
 */
unsigned char outp(int port, unsigned char value);

/**
 * Writes a word (2 bytes) to the specified I/O port
 * 
 * @return the value that was sent to the device
 * 
 * (Should have been provided explicitly by nwconio.h)
 */
unsigned short outpw(int port, unsigned short value);

#endif
