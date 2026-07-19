#include "implicit_nlm_defs.h"

/**
 * Copied from https://forum.osdev.org/viewtopic.php?p=69241#p69241
 */
void outw(unsigned short port, unsigned short value)
{
    // ConsolePrintf("\rPerforming outw(%d,%d) in assembly routine now...\n", port, value);
    // asm volatile ("outw %%ax,%%dx": :"dN"(port), "a"(value));
    outpw(port, value);
} 

/**
 * Copied from https://forum.osdev.org/viewtopic.php?p=69241#p69241
 */
void outb(unsigned short port, unsigned char value)
{
    // ConsolePrintf("\rPerforming outb(%d,%d) in assembly routine now...\n", port, value);
    // asm volatile ("outb %%al,%%dx": :"dN"(port), "a"(value));
    outp(port, value);
}

unsigned char inb(unsigned short port) {
    return inp(port);
}