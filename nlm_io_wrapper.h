#ifndef NLM_IO_WRAPPER_H
#define NLM_IO_WRAPPER_H

void outw(unsigned short port, unsigned short value);
void outb(unsigned short port, unsigned char value);
unsigned char inb(unsigned short port);

#endif
