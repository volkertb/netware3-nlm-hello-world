#include "implicit_nlm_defs.h"
#include "adlib_util.h"

void adlib_write_reg(unsigned char reg, unsigned char value) {
  int i;
  outp(ADLIB_INDEX_PORT, reg);
  for (i = 0; i < 6; i++) inp(ADLIB_INDEX_PORT);
  outp(ADLIB_DATA_PORT, value);
  for (i = 0; i < 35; i++) inp(ADLIB_INDEX_PORT);
}

void adlib_play_song(const struct Opl2Song *song) {
  unsigned int i;
  for (i = 0; i < song->event_count; i++) {
    const struct Opl2Event *ev = &song->events[i];
    if (ev->wait_ms) delay(ev->wait_ms);
    if (ev->reg != 0xFF) adlib_write_reg(ev->reg, ev->value);
  }
}

void adlib_silence(void) {
  int chan;
  for (chan = 0; chan <= 8; chan++) {
    adlib_write_reg(0xB0 + chan, 0x00);
  }
}
