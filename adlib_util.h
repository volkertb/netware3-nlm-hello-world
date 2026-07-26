#ifndef ADLIB_UTIL_H
#define ADLIB_UTIL_H

#include "generated/opl2_event.h"

#define ADLIB_INDEX_PORT 0x388
#define ADLIB_DATA_PORT 0x389

/**
 * Write a single OPL2 register. Standard AdLib/OPL2 port convention (index port 0x388, data
 * port 0x389); the read-loops after each port write satisfy the chip's ~3.3us/~23us minimum
 * access delays, since NetWare gives no finer-grained timer than delay()'s milliseconds.
 */
void adlib_write_reg(unsigned char reg, unsigned char value);

/**
 * Replay a pre-decoded event stream (see generated/opl2_event.h) - wait_ms is already real
 * time, so this has no notion of whatever source format the stream was converted from.
 */
void adlib_play_song(const struct Opl2Song *song);

/** Key off every melodic channel (0-8) - call after playback so nothing keeps sustaining. */
void adlib_silence(void);

#endif
