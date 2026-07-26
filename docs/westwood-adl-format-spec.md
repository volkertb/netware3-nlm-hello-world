# Westwood ADL Music Format — Implementation Specification

Description of the `.ADL` music/sound-effect format used by several early 1990s Westwood Studios
DOS games (Eye of the Beholder I/II, The Legend of Kyrandia 1/2, Dune II, Lands of Lore), written
as a standalone specification a human or an LLM with no other context could use to implement a
parser and OPL2 player from scratch, in any language.

**Provenance, honestly stated:** the file container layout (§2: primary index, pointer tables,
their relative-offset convention) was reverse-engineered independently - byte-level analysis of a
real `.ADL` file cross-checked against public wiki documentation (moddingwiki/vgmpf's "ADL
(Westwood)" pages, which cover the container layout but not the opcode stream). The playback
algorithm (§3, §6-§10 - the opcode table, register-offset/frequency tables, instrument level
formula, and effect algorithms) could not be worked out from the file bytes or any public
documentation alone; that part was derived by reading AdPlug's `src/adl.cpp`/`adl.h` (itself
adapted from ScummVM's Kyra engine `adlib.cpp`) and `src/composer.h`/`rol.h`, and is described
here in original prose/pseudocode - no source code is reproduced. See this repo's `LICENSE.md`
for the full derivation chain of `music/adl_to_c.py`, the actual implementation this spec
document is distilled from. One table (pitch-bend correction curves, §9) is deliberately *not*
reproduced here, specifically because it's the one piece that would mean transcribing another
project's specific derived data rather than describing the format - see §9 for how to approximate
or independently derive it.

## 1. Scope and format variants

Westwood reused this format, with minor size changes, across several games:

| Game(s)                                   | Primary index | Track pointers | Instrument pointers |
|--------------------------------------------|---------------|----------------|----------------------|
| Eye of the Beholder 1                      | 120 × 8-bit   | 150 × 16-bit   | 150 × 16-bit         |
| Eye of the Beholder 2 / Kyrandia 1 / Dune II | 120 × 8-bit  | 250 × 16-bit   | 250 × 16-bit         |
| Lands of Lore / Kyrandia 2                 | 250 × 16-bit  | 500 × 16-bit   | 500 × 16-bit         |

This spec describes the middle variant (EOB2/Kyrandia1/Dune II) in full, concrete detail; the
other two follow the same structure with the table sizes above substituted in (Lands of Lore's
16-bit primary index is the only structural difference beyond size - see §2).

## 2. File layout

A file is four contiguous regions, back to back, no gaps:

```
+----------------------+----------------------+----------------------+----------------------+
| 1. Primary index     | 2. Track pointer      | 3. Instrument         | 4. Track data +      |
|    (120 bytes)        |    table              |    pointer table      |    instrument data    |
|                        |    (250 x uint16 LE)  |    (250 x uint16 LE)  |    (rest of file)     |
+----------------------+----------------------+----------------------+----------------------+
offset 0x000            offset 0x078            offset 0x26C            offset 0x460
```

- **Primary index** (120 bytes): a lookup table mapping an externally-meaningful "sound/subsong
  number" (0-119 - this is the number a game's own code would ask to play) to a slot in the track
  pointer table. Byte value `0xFF` means "this sound number is not used in this file." Any other
  byte value `N` means "play track-pointer-table slot `N`." Multiple sound numbers may point at
  the same slot. Most slots in the pointer tables are never referenced by the primary index at
  all - they exist only to be jumped to *from within* another track's own data (see §8, the
  "jump to subroutine" and "start another channel's program" opcodes).

- **Track pointer table** (250 × 16-bit little-endian, right after the primary index): each
  entry is either `0xFFFF` ("unused") or an offset. **All offsets in both pointer tables are
  relative to the start of the track pointer table itself** (i.e. relative to file offset
  `0x078`), not to the start of the file. So a track pointer's absolute file offset is
  `0x078 + pointer_value`. (A pointer value of `0` is also effectively "unused" in practice - it
  would point at the pointer table itself, never valid track data.)

- **Instrument pointer table** (250 × 16-bit little-endian, immediately after the track pointer
  table): same encoding and same relative-offset base as the track pointer table (i.e. also
  relative to `0x078`, *not* to its own start at `0x26C`). Entry `i` is instrument number `i`.

- **Track data / instrument data**: everything after the instrument pointer table. There is no
  further internal structure separating "track data" from "instrument data" - they're just bytes
  at whatever offsets the two pointer tables resolve to. In practice, track data tends to be
  stored before instrument data, but a correct reader should never assume this and should only
  ever access these bytes via a resolved pointer.

**Validation without a magic number**: this format has no signature bytes. To confirm a file is
this format (and pick the right table-size variant), read the first track pointer table entry: it
should resolve to a plausible absolute offset (greater than the combined header size, less than
the file size). A file that fails this sanity check for all three known variants is not this
format, or is corrupted.

## 3. Instrument data (11 bytes per instrument)

Each instrument is exactly 11 bytes, mirroring OPL2 hardware operator registers directly (see §5
for the OPL2 register primer). An OPL2 "instrument" here always means a 2-operator FM voice: a
*modulator* operator and a *carrier* operator.

| Byte | Meaning                                                                          |
|------|-----------------------------------------------------------------------------------|
| 0    | Modulator: AM/vibrato/sustain/KSR/frequency-multiplier bits (OPL2 register group `0x20`) |
| 1    | Carrier: same bit layout as byte 0 (OPL2 register group `0x20`)                   |
| 2    | Feedback level (bits 1-3) and operator-connection/algorithm bit (bit 0) - OPL2 register group `0xC0` |
| 3    | Modulator: waveform select (OPL2 register group `0xE0`)                          |
| 4    | Carrier: waveform select (OPL2 register group `0xE0`)                            |
| 5    | Modulator: base output level (6 bits) - combined with runtime volume/effect state (see below) before being written to OPL2 register group `0x40` |
| 6    | Carrier: base output level (6 bits) - same, register group `0x40`                  |
| 7    | Modulator: attack rate / decay rate (OPL2 register group `0x60`)                  |
| 8    | Carrier: attack rate / decay rate (OPL2 register group `0x60`)                    |
| 9    | Modulator: sustain level / release rate (OPL2 register group `0x80`)              |
| 10   | Carrier: sustain level / release rate (OPL2 register group `0x80`)                |

Byte 5 and byte 6 are **not** written to the OPL2 chip verbatim. At runtime they're combined with
several additive "extra level" modifiers (set by dedicated opcodes, see §8) and a volume
modifier, clipped to a 6-bit range, before being written to the chip's key-scaling/output-level
registers. Concretely, for each operator: `final_level = clip(base_level + extra_level_1 +
extra_level_2 + volume_correction, 0, 63)`, where `volume_correction` is derived from a third
"extra level" value and a 0-255 volume/velocity scalar (`volume_correction = ((extra_level_3 XOR
63) * volume) >> 8`, then XORed with 63 again - i.e. it scales smoothly from "no reduction" at
full volume to "fully attenuated" at zero). The exact rounding behavior only matters for
bit-perfect fidelity with the original driver; a reader aiming for "sounds right" can simplify
this to a linear volume scale.

## 4. Logical channels

The player has **10 logical channels**, numbered 0-9:

- **Channels 0-8** each map to one OPL2 hardware voice (OPL2 has 9 two-operator voices in
  non-rhythm mode). Each has its own frequency/octave registers and its own operator pair.
- When the OPL2 rhythm/percussion mode is active, **channels 6, 7, and 8 stop being melodic
  voices** and instead drive the bass drum, snare/hi-hat, and tom/cymbal percussion voices
  respectively - a hardware-level OPL2 behavior, not a format-specific one (see §5).
- **Channel 9 is not a hardware voice at all.** It's a "control" channel: a program running on
  channel 9 can dispatch (start) programs on channels 0-8, and is commonly used as the entry
  point a sound/subsong number in the primary index actually points to, which then starts several
  real channels playing in sync.

Each channel independently runs its own **program** - a byte stream of notes and opcodes (§7, §8)
- read from wherever a track pointer resolves to. There's no separate "how many channels does
this song use" field; that's implicit in however many channels get started, directly or via the
"start another channel's program" opcode.

## 5. OPL2 register primer

For context - this is standard Yamaha OPL2 (YM3812) hardware documentation, not specific to this
file format. Registers are accessed via two I/O ports (on AdLib-compatible hardware, port pairs
`0x388`/`0x389`): write the register number to the index port, wait, write the value to the data
port, wait again (the chip needs on the order of a few microseconds to latch each write).

Per-operator registers are laid out in groups of 8 bytes across the two operators of each of the
9 voices, indexed by an "operator offset" table:

```
voice(channel)   0    1    2    3    4    5    6    7    8
operator offset 0x00 0x01 0x02 0x08 0x09 0x0A 0x10 0x11 0x12
```

The modulator operator of voice N uses `base_register + offset[N]`; the carrier operator uses
`base_register + offset[N] + 3`. Relevant base registers:

| Base   | Purpose                                                    |
|--------|-------------------------------------------------------------|
| `0x20` | Amplitude/vibrato/sustain/KSR/frequency-multiplier          |
| `0x40` | Key-scaling level / output level                            |
| `0x60` | Attack rate / decay rate                                    |
| `0x80` | Sustain level / release rate                                |
| `0xE0` | Waveform select                                              |
| `0xA0`+voice | Frequency number, low 8 bits (per-voice, not per-operator) |
| `0xB0`+voice | Key-on bit, octave, frequency number high 2 bits (per-voice) |
| `0xC0`+voice | Feedback level / operator connection (per-voice)      |
| `0x01` | Enable waveform-select control (write `0x20` once at startup)|
| `0x08` | CSM/note-select mode (write `0x00` once at startup for normal mode) |
| `0xBD` | Tremolo/vibrato depth, rhythm-mode enable, and (in rhythm mode) the 5 percussion key-on bits |

Turning a note on/off is done by writing `0xB0`+voice with bit 5 (`0x20`) set/clear; the octave
occupies bits 2-4 and the top 2 frequency bits occupy bits 0-1 of that same register.

## 6. Timing model

Playback advances at a **fixed 72 Hz tick rate** - this is a constant of the driver, not
per-file data; every file uses the same rate.

Each channel has a **tempo** and a **timer** byte (both 0-255, wrapping). On every tick: `timer =
(timer + tempo) mod 256`; if the addition wrapped around past 255 (i.e. the new value is smaller
than the old one), the channel is "due" this tick and its **duration** counter is decremented. A
channel only reads its next note/opcode when its duration counter reaches zero - so tempo
controls how often the channel is checked at all, and duration controls how many "due" ticks a
note or rest lasts for once played. This two-level structure (outer tempo/timer gate, inner
duration countdown) is what lets each channel have its own independent tempo/note-length behavior
even though every channel is ticked at the same fixed 72 Hz.

There is also a global tempo value that individual channels can be pointed at (a "use the global
tempo" mode per channel, see the opcode table), letting one program-wide tempo change affect
several channels at once.

## 7. Program byte stream grammar

Each channel's program is a byte stream, read sequentially, with an implicit "instruction
pointer" that starts at the resolved track pointer and advances as bytes are consumed. There is
no explicit length prefix or end marker required by the grammar itself - the stream is simply
read until a "stop channel" condition is reached (either an explicit opcode, or the instruction
pointer running out of valid file data).

Each unit in the stream is:

- **If the next byte's high bit (`0x80`) is 0**: it's a **note**. The low 7 bits encode a note
  value: bits 0-3 are a semitone offset (0-11, wrapping into the octave via a per-channel "base
  note" adjustment - see §8's `set base note`), bits 4-6 combine with a per-channel "base octave"
  adjustment to select the octave. The byte immediately following the note byte is its
  **duration** (in the tempo/timer "due tick" units described in §6). Reading a note: sets the
  channel's frequency/octave registers, turns the note on, and starts the duration countdown. If
  duration is 0, the channel immediately becomes due again next tick (effectively "no delay, keep
  reading").

- **If the next byte's high bit is 1**: it's an **opcode**. Mask off the high bit (`opcode_index
  = byte & 0x7F`) and look it up in the opcode table (§8), which specifies how many further
  operand bytes to consume and what to do with them. Every opcode indicates whether reading
  should continue immediately (more opcodes this same tick) or stop (wait for the next due tick).

Multi-byte operands are almost always little-endian; two vibrato/slide opcodes' operands are
notable exceptions (see their entries in §8).

**Relative addressing convention**: every opcode that jumps or calls (jump, jump-to-subroutine,
conditional repeat-jump) computes its target as `(current instruction pointer, already advanced
past this opcode's own operand bytes) + (signed 16-bit operand)`. In other words, offsets are
relative to the position immediately *after* the 2-byte offset operand itself, not to the opcode
byte. A negative offset that jumps backward is how looping/repeating songs are implemented - a
reader wanting to detect "this song loops forever" rather than play it indefinitely can watch for
a backward jump being taken as the natural stopping point for a single playthrough.

## 8. Opcode table

Every opcode below is invoked as `byte & 0x7F` (i.e. table index 0 corresponds to byte value
`0x80`, index 1 to `0x81`, and so on). "Operand bytes" lists how many bytes follow the opcode
byte itself. Where a description says "this channel," it means the OPL2 channel currently running
this program (0-8; some opcodes are no-ops when running on the control channel 9). Descriptions
say "stop reading" when the channel should wait for its next due tick rather than immediately
processing another byte from the stream.

| # | Operands | Effect |
|---|----------|--------|
| 0 | 1 | Set a repeat counter to the operand value. |
| 1 | 2 (signed offset) | Decrement the repeat counter; if it's still non-zero, jump by the offset (see §7's addressing convention). Used for "repeat this section N times" loops. |
| 2 | 1 | Start another channel's program (see §4/§7): operand is a track/program number (looked up via the pointer tables exactly like a primary-index-selected sound, not through the primary index itself). Only takes effect if the requested channel isn't already busy with something higher-priority (see opcode 26's priority value). |
| 3 | 1 | Set this channel's "note spacing" - a duration threshold (see opcode 28's note-off timing) used to shorten notes relative to their nominal duration, for a detached/staccato feel. |
| 4 | 2 (signed offset) | Unconditional jump (see §7). A negative offset here is how most songs loop. |
| 5 | 2 (signed offset) | Call a subroutine: push the current position, then jump (see §7). Up to 4 nested calls are supported. |
| 6 | 0 | Return from the most recent subroutine call. |
| 7 | 1 | Set this channel's "base octave" adjustment (added into every subsequent note's octave calculation, see §7). |
| 8 | 0 | Stop this channel: turn its note off, mark it idle, stop reading further opcodes this program. (Several unused opcode slots also alias to this behavior - see the "reserved" note below.) |
| 9 | 1 | Rest: turn the note off and wait for the given duration, then continue. |
| 10 | 2 | Write an arbitrary OPL2 register directly: operand bytes are (register, value). An escape hatch for effects the rest of the opcode set doesn't cover. |
| 11 | 2 | Combined "play this note, with this duration" in one opcode (equivalent to a plain note byte, just reachable from inside an opcode dispatch rather than as the implicit non-opcode case). |
| 12 | 1 | Set this channel's "base note" adjustment (added into every subsequent note's semitone calculation). |
| 13 | 5 | Configure a low-frequency "secondary effect": periodically re-writes one register using a repeating sequence of bytes taken from elsewhere in the sound data (a crude LFO/arbitrary-waveform modulation effect). Operands: update-rate, sequence length, target register, and a 16-bit pointer to the byte sequence to cycle through. |
| 14 | 1 | Stop a specific other channel (by number) immediately. |
| 15 | 1 | Wait until a specific other channel/program (given by number, same lookup as opcode 2) has finished playing before continuing; if that channel doesn't exist or already isn't playing, this is a no-op. |
| 16 | 1 | Load an instrument (by instrument number, resolved via the instrument pointer table) onto this channel - writes all 11 instrument bytes to the appropriate OPL2 registers for this channel's operator pair (see §3). |
| 17 | 3 | Start a pitch "slide" effect: operands are update-rate and a 16-bit (big-endian) signed step size added to the frequency on every update, with automatic octave-shift when the frequency would over/underflow the OPL2's 10-bit range. |
| 18 | 0 | Stop the pitch slide effect. |
| 19 | 1 | Set a per-channel frequency bias added into every note's frequency calculation. |
| 21 | 4 | Start a vibrato effect: operands are update-rate, a "step range" (controls how much of the note's own frequency feeds into the vibrato depth), a step-count (how many updates before reversing direction), and a delay (ticks before the effect starts after a note is triggered). |
| 26 | 1 | Set this channel's priority (used when deciding whether opcode 2 / opcode 22-family channel-starts are allowed to interrupt what's currently playing). |
| 28 | 1 | Configure a global "beat" divider - ties this channel's rate of firing a shared beat counter to the given value; other channels can synchronize to that beat (opcode 29). |
| 29 | 1 | Wait for the next shared "beat" (as configured by opcode 28) before continuing, using a bitmask operand to select which beat-counter bits must change. |
| 30 | 1 | Add a level offset to this channel's carrier operator level, applied only when a "two-operator" (both operators audible) instrument is loaded, and only after the base output level. |
| 32 | 1 | Set the duration for the *next* read without playing a note (distinct from opcode 33, which also turns the note on). |
| 33 | 1 | Turn the current note on again with a new duration, without changing pitch (a "restrike"/legato continuation). |
| 36 | 1 | Set this channel's fine-grained note-spacing divisor (see opcode 3). |
| 38 | 1 | Set the *global* tempo value (affects every channel currently in "use global tempo" mode). |
| 39 | 0 | Disable the secondary effect (see opcode 13). |
| 41 | 1 | Set this channel's own tempo directly (independent of the global tempo). |
| 43 | 1 | Set a third additive level offset (applied to both operators, see §3's level formula) for this channel. |
| 44 | 2 | Set another channel's (given by number) carrier-level offset directly, then re-apply its level formula immediately. |
| 45 | 2 | Same as 44, but adds to the existing offset instead of replacing it. |
| 46 | 1 | Globally enable/disable amplitude-modulation depth (a chip-wide OPL2 tremolo-depth flag, register `0xBD` bit). |
| 47 | 1 | Globally enable/disable vibrato depth (same register, different bit). |
| 48 | 1 | Add to this channel's own level offset (see opcode 30), then re-apply the level formula. |
| 51 | 1 | Fully reset another channel (given by number): stop it, clear its level offsets, silence its OPL2 voice. |
| 53 | 2 | Randomly perturb the current note's frequency: operands are a 16-bit (big-endian) mask combined with an internal pseudo-random value, added to the current frequency/octave bits. Used for a "detuned" or chorus-like effect. |
| 54 | 0 | Stop the vibrato effect (see opcode 21). |
| 57 | 1 | Set this channel's pitch-bend amount (a signed value) and immediately recompute the current note's frequency with it applied (see §9 on pitch bend). |
| 58 | 0 | Reset this channel's own tempo to track the global tempo again (undoes opcode 41). |
| 59 | 0 | No-op. |
| 60 | 1 | Set a "duration randomness" mask - subsequent note/rest durations get a random value ANDed with this mask added on top, for a humanized/randomized rhythm. |
| 61 | 1 | Adjust (add to, with clamping to 1-255) this channel's own tempo. |
| 63 | 2 | Internal/rarely-used table lookup effect; safe to implement as a no-op - see the "reserved" note below. |
| 65 | 9 | Configure the OPL2 rhythm/percussion section: loads three instruments (for the bass-drum, snare/hi-hat, and tom/cymbal voice pairs) and sets their initial frequency/octave, then enables rhythm mode chip-wide. Only meaningful when run on the control channel. |
| 66 | 1 | Trigger one or more percussion instruments (bitmask operand: bass drum/snare/tom/cymbal/hi-hat) by briefly re-triggering their key-on bits. |
| 67 | 0 | Disable the rhythm/percussion section chip-wide, returning channels 6-8 to normal melodic voices. |
| 68 | 2 | Set a percussion voice's level offset (bitmask of which percussion voices, plus a value), replacing any existing offset. |
| 69 | 2 | Same as 68, but additive rather than replacing. |
| 70 | 2 | Same as 68, but using a different base level (see the "reserved" note - two near-identical opcodes exist for historical reasons). |
| 71 | 1 | Set a "sound trigger" flag the surrounding game can poll (a way for the music to signal game events, e.g. "cue the next line of dialogue"). |
| 72 | 1 | Set whether this channel's tempo automatically resyncs to the global tempo every tick (a persistent version of opcode 58). |

**Reserved/unused opcode indices** (20, 22-25, 27, 31, 34-35, 37, 40, 42, 49-50, 52, 55-56, 62,
64): in the original driver these all alias to the same "stop channel" behavior as opcode 8 (or,
for two of them, a plain no-op) - simply because the opcode dispatch table has no gaps and unused
slots were filled with a safe default rather than left undefined. A from-scratch implementation
can treat any opcode index outside the ones explicitly listed above as "stop this channel."

## 9. Note frequencies and pitch bend

Notes are drawn from a fixed one-octave, 12-semitone table of OPL2 "F-numbers" (10-bit values
written to the frequency registers described in §5), one entry per semitone starting at the note
the format calls semitone 0:

```
0x0134, 0x0147, 0x015A, 0x016F, 0x0184, 0x019C, 0x01B4, 0x01CE, 0x01E9, 0x0207, 0x0225, 0x0246
```

A note's final frequency is `table[semitone] + per_channel_frequency_bias` (the bias set by
opcode 19), then optionally adjusted by pitch bend (below) before being split into the register's
low-8-bits/high-2-bits fields alongside the octave (opcode 7's base octave, combined with the
note byte's own octave bits per §7, clamped to 0-7 and shifted into its register position).

**Pitch bend** (opcode 57): when a non-zero pitch-bend amount is active, the note frequency is
further adjusted by looking up a correction value in a per-semitone, per-bend-amount table (a
larger table than the base frequency one - one row per semitone, one column per bend-amount step,
32 columns) and adding or subtracting it depending on the bend's sign. This document deliberately
does not reproduce that table's contents (see the provenance note at the top) - it's not
derivable from the file bytes or public docs, only from another project's source, and unlike the
container layout and opcode table (facts about the format itself, necessary for any compatible
implementation), the exact tuning-correction curve is a specific derived artifact. A from-scratch
implementation has two reasonable paths: approximate it with a linear interpolation between
semitone frequencies scaled by the bend amount (works for "sounds right," won't be bit-exact), or
derive the real curve independently by observing pitch-bent note output against real/emulated
OPL2 hardware and back-solving the per-step correction values.

## 10. Practical implementation notes

- **Subsong classification without listening**: a file's primary index (§2) typically names far
  more "system" entries (stop, fade, or other short non-musical triggers - conventionally the
  first few entries) than genuine songs. A cheap, reliable way to tell them apart programmatically
  is to run the decode and count note-on events: entries with zero note-on events are pure
  control/setup tracks, not music, regardless of how many OPL2 register writes they contain.
- **Distinguishing a short jingle from a long theme**: among entries that do contain notes,
  duration is usually a good proxy for "sound effect vs. full theme" - looping background themes
  in these games commonly run into minutes, while stingers/jingles/SFX are single-digit seconds.
- **Loop detection**: watch for a backward jump (§7) being taken; that's the natural end of one
  full playthrough for a looping song, distinct from "ran out of data" (a bug) or an explicit stop
  opcode (a genuinely one-shot sound).
- **A file has no explicit total-duration field anywhere** - the only way to know how long a
  track runs is to actually execute its program (or a subset of channels' programs) until a
  terminating condition (§7, this section) is reached.
