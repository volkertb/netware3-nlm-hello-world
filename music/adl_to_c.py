#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Convert a Westwood ADL music file into embeddable C code (a flat, pre-decoded stream of
OPL2 register writes + timing), for compiling directly into an NLM.

The ADL container format (header/pointer tables) is independently reverse-engineered from the
file bytes plus public wiki documentation (moddingwiki/vgmpf "ADL (Westwood)"). The per-channel
bytecode VM below - opcode table, register offsets, frequency/pitch-bend tables, and the effects
(slide/vibrato/secondary) - is a line-for-line Python port of AdPlug's adl.cpp (LGPL-2.1-or-later),
itself adapted from ScummVM's Kyra engine adlib.cpp. Only this build-time conversion tool carries
that derivation and its license; the runtime player it feeds (adlib_util.c) only walks a flat
array of (wait, register, value) triples and has no ADL-specific logic at all.

Build-time only - not part of the NLM's own toolchain, no NDK/NLM constraints apply here.
"""
import struct
import sys

BASE = 0x78              # _soundData starts right after the 120-byte primary index block
NUM_PROGRAMS = 250        # v2/v3 (EOB II / Kyrandia 1 / Dune II) pointer-array size
REG_OFFSET = [0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12]
FREQ_TABLE = [0x0134, 0x0147, 0x015A, 0x016F, 0x0184, 0x019C, 0x01B4, 0x01CE, 0x01E9,
              0x0207, 0x0225, 0x0246]

# fmt: off
PITCH_BEND_TABLES = [
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
     0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21],
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x06, 0x07, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11,
     0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x22, 0x24],
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x06, 0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13,
     0x14, 0x15, 0x16, 0x17, 0x19, 0x1A, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x24, 0x25, 0x26],
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x06, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13,
     0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x23, 0x25, 0x27, 0x28],
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x06, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x13, 0x15,
     0x16, 0x17, 0x18, 0x19, 0x1B, 0x1D, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x2A],
    [0x00, 0x01, 0x02, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x15,
     0x16, 0x17, 0x18, 0x19, 0x1B, 0x1D, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x25, 0x27, 0x29, 0x2B, 0x2D],
    [0x00, 0x01, 0x02, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x15,
     0x16, 0x17, 0x18, 0x1A, 0x1C, 0x1E, 0x21, 0x24, 0x25, 0x26, 0x27, 0x29, 0x2B, 0x2D, 0x2F, 0x30],
    [0x00, 0x01, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x15, 0x18,
     0x19, 0x1A, 0x1C, 0x1D, 0x1F, 0x21, 0x23, 0x25, 0x26, 0x27, 0x29, 0x2B, 0x2D, 0x2F, 0x30, 0x32],
    [0x00, 0x01, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x14, 0x17, 0x1A,
     0x19, 0x1A, 0x1C, 0x1E, 0x20, 0x22, 0x25, 0x28, 0x29, 0x2A, 0x2B, 0x2D, 0x2F, 0x31, 0x33, 0x35],
    [0x00, 0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0E, 0x0F, 0x10, 0x12, 0x14, 0x16, 0x18, 0x1A, 0x1B,
     0x1C, 0x1D, 0x1E, 0x20, 0x22, 0x24, 0x26, 0x29, 0x2A, 0x2C, 0x2E, 0x30, 0x32, 0x34, 0x36, 0x39],
    [0x00, 0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0E, 0x0F, 0x10, 0x12, 0x14, 0x16, 0x19, 0x1B, 0x1E,
     0x1F, 0x21, 0x23, 0x25, 0x27, 0x29, 0x2B, 0x2D, 0x2E, 0x2F, 0x31, 0x32, 0x34, 0x36, 0x39, 0x3C],
    [0x00, 0x01, 0x03, 0x05, 0x07, 0x0A, 0x0C, 0x0F, 0x10, 0x11, 0x13, 0x15, 0x17, 0x19, 0x1B, 0x1E,
     0x1F, 0x20, 0x22, 0x24, 0x26, 0x28, 0x2B, 0x2E, 0x2F, 0x30, 0x32, 0x34, 0x36, 0x39, 0x3C, 0x3F],
    [0x00, 0x02, 0x04, 0x06, 0x08, 0x0B, 0x0D, 0x10, 0x11, 0x12, 0x14, 0x16, 0x18, 0x1B, 0x1E, 0x21,
     0x22, 0x23, 0x25, 0x27, 0x29, 0x2C, 0x2F, 0x32, 0x33, 0x34, 0x36, 0x38, 0x3B, 0x34, 0x41, 0x44],
    [0x00, 0x02, 0x04, 0x06, 0x08, 0x0B, 0x0D, 0x11, 0x12, 0x13, 0x15, 0x17, 0x1A, 0x1D, 0x20, 0x23,
     0x24, 0x25, 0x27, 0x29, 0x2C, 0x2F, 0x32, 0x35, 0x36, 0x37, 0x39, 0x3B, 0x3E, 0x41, 0x44, 0x47],
]
# fmt: on

# (opcode name, number of operand bytes) - transcribed verbatim from _parserOpcodeTable in adl.cpp
PARSER_OPCODES = [
    ("setRepeat", 1), ("checkRepeat", 2), ("setupProgram", 1), ("setNoteSpacing", 1),
    ("jump", 2), ("jumpToSubroutine", 2), ("returnFromSubroutine", 0), ("setBaseOctave", 1),
    ("stopChannel", 0), ("playRest", 1), ("writeAdLib", 2), ("setupNoteAndDuration", 2),
    ("setBaseNote", 1), ("setupSecondaryEffect1", 5), ("stopOtherChannel", 1), ("waitForEndOfProgram", 1),
    ("setupInstrument", 1), ("setupPrimaryEffectSlide", 3), ("removePrimaryEffectSlide", 0), ("setBaseFreq", 1),
    ("stopChannel", 0), ("setupPrimaryEffectVibrato", 4), ("stopChannel", 0), ("stopChannel", 0),
    ("stopChannel", 0), ("stopChannel", 0), ("setPriority", 1), ("stopChannel", 0),
    ("setBeat", 1), ("waitForNextBeat", 1), ("setExtraLevel1", 1), ("stopChannel", 0),
    ("setupDuration", 1), ("playNote", 1), ("stopChannel", 0), ("stopChannel", 0),
    ("setFractionalNoteSpacing", 1), ("stopChannel", 0), ("setTempo", 1), ("removeSecondaryEffect1", 0),
    ("stopChannel", 0), ("setChannelTempo", 1), ("stopChannel", 0), ("setExtraLevel3", 1),
    ("setExtraLevel2", 2), ("changeExtraLevel2", 2), ("setAMDepth", 1), ("setVibratoDepth", 1),
    ("changeExtraLevel1", 1), ("stopChannel", 0), ("stopChannel", 0), ("clearChannel", 1),
    ("stopChannel", 0), ("changeNoteRandomly", 2), ("removePrimaryEffectVibrato", 0), ("stopChannel", 0),
    ("stopChannel", 0), ("pitchBend", 1), ("resetToGlobalTempo", 0), ("nop", 0),
    ("setDurationRandomness", 1), ("changeChannelTempo", 1), ("stopChannel", 0), ("callback46", 2),
    ("nop", 0), ("setupRhythmSection", 9), ("playRhythmSection", 1), ("removeRhythmSection", 0),
    ("setRhythmLevel2", 2), ("changeRhythmLevel1", 2), ("setRhythmLevel1", 2), ("setSoundTrigger", 1),
    ("setTempoReset", 1), ("callback56", 2), ("stopChannel", 0),
]

MAX_TICKS = 72 * 180  # 180s safety cap - real songs should end or loop-detect well before this


def to_int8(v):
    v &= 0xFF
    return v - 0x100 if v >= 0x80 else v


def to_int16le(lo, hi):
    v = lo | (hi << 8)
    return v - 0x10000 if v >= 0x8000 else v


def to_int16be(hi, lo):
    v = (hi << 8) | lo
    return v - 0x10000 if v >= 0x8000 else v


def clip(x, lo, hi):
    return lo if x < lo else min(x, hi)


def advance(state, timer_key, tempo_key):
    if isinstance(state, dict):
        old = state[timer_key]
        state[timer_key] = (old + state[tempo_key]) & 0xFF
        return state[timer_key] < old
    old = getattr(state, timer_key)
    new = (old + getattr(state, tempo_key)) & 0xFF
    setattr(state, timer_key, new)
    return new < old


def new_channel():
    return {
        "lock": False, "repeating": False, "opExtraLevel2": 0, "dataptr": None, "duration": 0,
        "repeatCounter": 0, "baseOctave": 0, "priority": 0, "dataptrStack": [], "baseNote": 0,
        "slideTempo": 0, "slideTimer": 0, "slideStep": 0, "vibratoStep": 0, "vibratoStepRange": 0,
        "vibratoStepsCountdown": 0, "vibratoNumSteps": 0, "vibratoDelay": 0, "vibratoTempo": 0,
        "vibratoTimer": 0, "vibratoDelayCountdown": 0, "opExtraLevel1": 0, "baseFreq": 0, "tempo": 0,
        "timer": 0, "regAx": 0, "regBx": 0, "primaryEffect": None, "secondaryEffect": None,
        "fractionalSpacing": 0, "opLevel1": 0, "opLevel2": 0, "opExtraLevel3": 0, "twoChan": 0,
        "spacing1": 1, "spacing2": 0, "durationRandomness": 0, "secondaryEffectTempo": 0,
        "secondaryEffectTimer": 0, "secondaryEffectSize": 0, "secondaryEffectPos": 0,
        "secondaryEffectRegbase": 0, "secondaryEffectData": 0, "tempoReset": 0, "rawNote": 0,
        "pitchBend": 0, "volumeModifier": 0,
    }


class AdlEmulator:
    def __init__(self, data):
        self.data = data
        self.soundsize = len(data) - BASE
        self.channels = [new_channel() for _ in range(10)]
        self.events = []  # (tick, reg, value)
        self.tick = 0
        self.rnd = 0x1234
        self.tempo = 0
        self.callbackTimer = 0xFF
        self.beatDivider = 0
        self.beatDivCnt = 0
        self.beatCounter = 0
        self.beatWaiting = 0
        self.vibratoAndAMDepthBits = 0
        self.rhythmSectionBits = 0
        self.curChannel = 0
        self.curRegOffset = 0
        self.soundTrigger = 0
        self.opLevelBD = self.opLevelHH = self.opLevelSD = self.opLevelTT = self.opLevelCY = 0
        self.opExtraLevel1HH = self.opExtraLevel2HH = 0
        self.opExtraLevel1CY = self.opExtraLevel2CY = 0
        self.opExtraLevel2TT = self.opExtraLevel1TT = 0
        self.opExtraLevel1SD = self.opExtraLevel2SD = 0
        self.opExtraLevel1BD = self.opExtraLevel2BD = 0

    # -- program/instrument lookup (mirrors AdLibDriver::getProgram/getInstrument) --

    def get_program(self, prog_id):
        if prog_id < 0 or prog_id >= self.soundsize // 2:
            return None
        offset = struct.unpack_from("<H", self.data, BASE + 2 * prog_id)[0]
        if offset == 0 or offset >= self.soundsize:
            return None
        return BASE + offset

    def get_instrument(self, instrument_id):
        return self.get_program(NUM_PROGRAMS + instrument_id)

    def valid_ptr(self, ptr):
        return ptr is not None and BASE <= ptr <= len(self.data)

    # -- low level --

    def write_opl(self, reg, val):
        self.events.append((self.tick, reg & 0xFF, val & 0xFF))

    def init_channel(self, ch):
        backup = ch["opExtraLevel2"]
        ch.clear()
        ch.update(new_channel())
        ch["opExtraLevel2"] = backup
        ch["tempo"] = 0xFF
        ch["priority"] = 0

    def note_off(self, ch):
        if self.curChannel >= 9:
            return
        if self.rhythmSectionBits and self.curChannel >= 6:
            return
        ch["regBx"] &= 0xDF
        self.write_opl(0xB0 + self.curChannel, ch["regBx"])

    def init_adlib_channel(self, chan):
        if chan >= 9:
            return
        if self.rhythmSectionBits and chan >= 6:
            return
        offset = REG_OFFSET[chan]
        self.write_opl(0x60 + offset, 0xFF)
        self.write_opl(0x63 + offset, 0xFF)
        self.write_opl(0x80 + offset, 0xFF)
        self.write_opl(0x83 + offset, 0xFF)
        self.write_opl(0xB0 + chan, 0x00)
        self.write_opl(0xB0 + chan, 0x20)

    def reset_adlib_state(self):
        self.rnd = 0x1234
        self.write_opl(0x01, 0x20)
        self.write_opl(0x08, 0x00)
        self.write_opl(0xBD, 0x00)
        self.init_channel(self.channels[9])
        for loop in range(8, -1, -1):
            self.write_opl(0x40 + REG_OFFSET[loop], 0x3F)
            self.write_opl(0x43 + REG_OFFSET[loop], 0x3F)
            self.init_channel(self.channels[loop])

    def get_random_nr(self):
        self.rnd = (self.rnd + 0x9248) & 0xFFFF
        low_bits = self.rnd & 7
        self.rnd >>= 3
        self.rnd = (self.rnd | (low_bits << 13)) & 0xFFFF
        return self.rnd

    def setup_duration(self, duration, ch):
        if ch["durationRandomness"]:
            ch["duration"] = (duration + (self.get_random_nr() & ch["durationRandomness"])) & 0xFF
            return
        if ch["fractionalSpacing"]:
            ch["spacing2"] = ((duration >> 3) * ch["fractionalSpacing"]) & 0xFF
        ch["duration"] = duration & 0xFF

    def setup_note(self, raw_note, ch, flag=False):
        if self.curChannel >= 9:
            return
        ch["rawNote"] = raw_note
        note = to_int8(((raw_note & 0x0F) + ch["baseNote"]) & 0xFF)
        octave = ((raw_note + ch["baseOctave"]) >> 4) & 0x0F
        if note >= 12:
            octave += note // 12
            note %= 12
        elif note < 0:
            octaves = (-(note + 1)) // 12 + 1
            octave -= octaves
            note += 12 * octaves
        freq = (FREQ_TABLE[note] + ch["baseFreq"]) & 0xFFFF
        if ch["pitchBend"] or flag:
            index_note = clip(raw_note & 0x0F, 0, 11)
            if ch["pitchBend"] >= 0:
                table = PITCH_BEND_TABLES[index_note + 2]
                freq = (freq + table[clip(ch["pitchBend"], 0, 31)]) & 0xFFFF
            else:
                table = PITCH_BEND_TABLES[index_note]
                freq = (freq - table[clip(-ch["pitchBend"], 0, 31)]) & 0xFFFF
        octave = clip(octave, 0, 7) << 2
        ch["regAx"] = freq & 0xFF
        ch["regBx"] = (ch["regBx"] & 0x20) | octave | ((freq >> 8) & 0x03)
        self.write_opl(0xA0 + self.curChannel, ch["regAx"])
        self.write_opl(0xB0 + self.curChannel, ch["regBx"])

    def calculate_op_level1(self, ch):
        value = ch["opLevel1"] & 0x3F
        if ch["twoChan"]:
            value = (value + ch["opExtraLevel1"]) & 0xFF
            value = (value + ch["opExtraLevel2"]) & 0xFF
            level3 = ((ch["opExtraLevel3"] ^ 0x3F) * ch["volumeModifier"]) & 0xFFFF
            if level3:
                level3 = (level3 + 0x3F) & 0xFFFF
                level3 >>= 8
            value = (value + (level3 ^ 0x3F)) & 0xFF
        value = clip(value, 0, 0x3F)
        if not ch["volumeModifier"]:
            value = 0x3F
        return (value | (ch["opLevel1"] & 0xC0)) & 0xFF

    def calculate_op_level2(self, ch):
        value = ch["opLevel2"] & 0x3F
        value = (value + ch["opExtraLevel1"]) & 0xFF
        value = (value + ch["opExtraLevel2"]) & 0xFF
        level3 = ((ch["opExtraLevel3"] ^ 0x3F) * ch["volumeModifier"]) & 0xFFFF
        if level3:
            level3 = (level3 + 0x3F) & 0xFFFF
            level3 >>= 8
        value = (value + (level3 ^ 0x3F)) & 0xFF
        value = clip(value, 0, 0x3F)
        if not ch["volumeModifier"]:
            value = 0x3F
        return (value | (ch["opLevel2"] & 0xC0)) & 0xFF

    def setup_instrument(self, reg_offset, ptr, ch):
        if self.curChannel >= 9:
            return
        if ptr is None or ptr + 11 > len(self.data):
            return
        b = self.data[ptr:ptr + 11]
        self.write_opl(0x20 + reg_offset, b[0])
        self.write_opl(0x23 + reg_offset, b[1])
        temp = b[2]
        self.write_opl(0xC0 + self.curChannel, temp)
        ch["twoChan"] = temp & 1
        self.write_opl(0xE0 + reg_offset, b[3])
        self.write_opl(0xE3 + reg_offset, b[4])
        ch["opLevel1"] = b[5]
        ch["opLevel2"] = b[6]
        self.write_opl(0x40 + reg_offset, self.calculate_op_level1(ch))
        self.write_opl(0x43 + reg_offset, self.calculate_op_level2(ch))
        self.write_opl(0x60 + reg_offset, b[7])
        self.write_opl(0x63 + reg_offset, b[8])
        self.write_opl(0x80 + reg_offset, b[9])
        self.write_opl(0x83 + reg_offset, b[10])

    def note_on(self, ch):
        if self.curChannel >= 9:
            return
        ch["regBx"] |= 0x20
        self.write_opl(0xB0 + self.curChannel, ch["regBx"])
        shift = 9 - clip(ch["vibratoStepRange"], 0, 9)
        freq = ((ch["regBx"] << 8) | ch["regAx"]) & 0x3FF
        ch["vibratoStep"] = (freq >> shift) & 0xFF
        ch["vibratoDelayCountdown"] = ch["vibratoDelay"]

    def adjust_volume(self, ch):
        if self.curChannel >= 9:
            return
        self.write_opl(0x43 + REG_OFFSET[self.curChannel], self.calculate_op_level2(ch))
        if ch["twoChan"]:
            self.write_opl(0x40 + REG_OFFSET[self.curChannel], self.calculate_op_level1(ch))

    # -- opcode handlers (op_* mirror AdLibDriver::update_*) --

    def op_setRepeat(self, ch, v):
        ch["repeatCounter"] = v[0]
        return 0

    def op_checkRepeat(self, ch, v):
        ch["repeatCounter"] = (ch["repeatCounter"] - 1) & 0xFF
        if ch["repeatCounter"] != 0:
            add = to_int16le(v[0], v[1])
            new_ptr = ch["dataptr"] + add
            if self.valid_ptr(new_ptr):
                ch["dataptr"] = new_ptr
        return 0

    def op_setupProgram(self, ch, v):
        if v[0] == 0xFF:
            return 0
        ptr = self.get_program(v[0])
        if ptr is None:
            return 0
        chan = self.data[ptr]
        priority = self.data[ptr + 1]
        if chan > 9:
            return 0
        ch2 = self.channels[chan]
        if priority >= ch2["priority"]:
            dataptr_backup = ch["dataptr"]
            self.init_channel(ch2)
            ch2["priority"] = priority
            ch2["dataptr"] = ptr + 2
            ch2["tempo"] = 0xFF
            ch2["timer"] = 0xFF
            ch2["duration"] = 1
            ch2["volumeModifier"] = 0xFF
            self.init_adlib_channel(chan)
            ch["dataptr"] = dataptr_backup
        return 0

    def op_setNoteSpacing(self, ch, v):
        ch["spacing1"] = v[0]
        return 0

    def op_jump(self, ch, v):
        add = to_int16le(v[0], v[1])
        new_ptr = ch["dataptr"] + add
        if not self.valid_ptr(new_ptr):
            return self.op_stopChannel(ch, v)
        ch["dataptr"] = new_ptr
        if add < 0:
            ch["repeating"] = True
        return 0

    def op_jumpToSubroutine(self, ch, v):
        add = to_int16le(v[0], v[1])
        if len(ch["dataptrStack"]) >= 4:
            return 0
        ch["dataptrStack"].append(ch["dataptr"])
        new_ptr = ch["dataptr"] + add
        if self.valid_ptr(new_ptr):
            ch["dataptr"] = new_ptr
        else:
            ch["dataptr"] = ch["dataptrStack"].pop()
        return 0

    def op_returnFromSubroutine(self, ch, v):
        if not ch["dataptrStack"]:
            return self.op_stopChannel(ch, v)
        ch["dataptr"] = ch["dataptrStack"].pop()
        return 0

    def op_setBaseOctave(self, ch, v):
        ch["baseOctave"] = to_int8(v[0])
        return 0

    def op_stopChannel(self, ch, v):
        ch["priority"] = 0
        if self.curChannel != 9:
            self.note_off(ch)
        ch["dataptr"] = None
        return 2

    def op_playRest(self, ch, v):
        self.setup_duration(v[0], ch)
        self.note_off(ch)
        return 1 if v[0] != 0 else 0

    def op_writeAdLib(self, ch, v):
        self.write_opl(v[0], v[1])
        return 0

    def op_setupNoteAndDuration(self, ch, v):
        self.setup_note(v[0], ch)
        self.setup_duration(v[1], ch)
        return 1 if v[1] != 0 else 0

    def op_setBaseNote(self, ch, v):
        ch["baseNote"] = to_int8(v[0])
        return 0

    def op_setupSecondaryEffect1(self, ch, v):
        ch["secondaryEffectTimer"] = ch["secondaryEffectTempo"] = v[0]
        ch["secondaryEffectSize"] = ch["secondaryEffectPos"] = to_int8(v[1])
        ch["secondaryEffectRegbase"] = v[2]
        raw16 = v[3] | (v[4] << 8)
        ch["secondaryEffectData"] = (raw16 - 191) & 0xFFFF
        ch["secondaryEffect"] = "effect1"
        start = ch["secondaryEffectData"] + ch["secondaryEffectSize"]
        if start < 0 or start >= self.soundsize:
            ch["secondaryEffect"] = None
        return 0

    def op_stopOtherChannel(self, ch, v):
        if v[0] > 9:
            return 0
        dataptr_backup = ch["dataptr"]
        ch2 = self.channels[v[0]]
        ch2["duration"] = 0
        ch2["priority"] = 0
        ch2["dataptr"] = None
        ch["dataptr"] = dataptr_backup
        return 0

    def op_waitForEndOfProgram(self, ch, v):
        ptr = self.get_program(v[0])
        if ptr is None:
            return 0
        chan = self.data[ptr]
        if chan > 9 or self.channels[chan]["dataptr"] is None:
            return 0
        if self.channels[chan]["repeating"]:
            ch["repeating"] = True
        ch["dataptr"] -= 2
        return 2

    def op_setupInstrument(self, ch, v):
        instrument = self.get_instrument(v[0])
        if instrument is None:
            return 0
        self.setup_instrument(self.curRegOffset, instrument, ch)
        return 0

    def op_setupPrimaryEffectSlide(self, ch, v):
        ch["slideTempo"] = v[0]
        ch["slideStep"] = to_int16be(v[1], v[2])
        ch["primaryEffect"] = "slide"
        ch["slideTimer"] = 0xFF
        return 0

    def op_removePrimaryEffectSlide(self, ch, v):
        ch["primaryEffect"] = None
        ch["slideStep"] = 0
        return 0

    def op_setBaseFreq(self, ch, v):
        ch["baseFreq"] = v[0]
        return 0

    def op_setupPrimaryEffectVibrato(self, ch, v):
        ch["vibratoTempo"] = v[0]
        ch["vibratoStepRange"] = v[1]
        ch["vibratoStepsCountdown"] = (v[2] + 1) & 0xFF
        ch["vibratoNumSteps"] = (v[2] << 1) & 0xFF
        ch["vibratoDelay"] = v[3]
        ch["primaryEffect"] = "vibrato"
        return 0

    def op_setPriority(self, ch, v):
        ch["priority"] = v[0]
        return 0

    def op_setBeat(self, ch, v):
        self.beatDivider = self.beatDivCnt = (v[0] >> 1) & 0xFF
        self.callbackTimer = 0xFF
        self.beatCounter = self.beatWaiting = 0
        return 0

    def op_waitForNextBeat(self, ch, v):
        if (self.beatCounter & v[0]) and self.beatWaiting:
            self.beatWaiting = 0
            return 0
        if not (self.beatCounter & v[0]):
            self.beatWaiting = (self.beatWaiting + 1) & 0xFF
        ch["dataptr"] -= 2
        ch["duration"] = 1
        return 2

    def op_setExtraLevel1(self, ch, v):
        ch["opExtraLevel1"] = v[0]
        self.adjust_volume(ch)
        return 0

    def op_setupDuration(self, ch, v):
        self.setup_duration(v[0], ch)
        return 1 if v[0] != 0 else 0

    def op_playNote(self, ch, v):
        self.setup_duration(v[0], ch)
        self.note_on(ch)
        return 1 if v[0] != 0 else 0

    def op_setFractionalNoteSpacing(self, ch, v):
        ch["fractionalSpacing"] = v[0] & 7
        return 0

    def op_setTempo(self, ch, v):
        self.tempo = v[0]
        return 0

    def op_removeSecondaryEffect1(self, ch, v):
        ch["secondaryEffect"] = None
        return 0

    def op_setChannelTempo(self, ch, v):
        ch["tempo"] = v[0]
        return 0

    def op_setExtraLevel3(self, ch, v):
        ch["opExtraLevel3"] = v[0]
        return 0

    def op_setExtraLevel2(self, ch, v):
        if v[0] > 9:
            return 0
        backup = self.curChannel
        self.curChannel = v[0]
        ch2 = self.channels[self.curChannel]
        ch2["opExtraLevel2"] = v[1]
        self.adjust_volume(ch2)
        self.curChannel = backup
        return 0

    def op_changeExtraLevel2(self, ch, v):
        if v[0] > 9:
            return 0
        backup = self.curChannel
        self.curChannel = v[0]
        ch2 = self.channels[self.curChannel]
        ch2["opExtraLevel2"] = (ch2["opExtraLevel2"] + v[1]) & 0xFF
        self.adjust_volume(ch2)
        self.curChannel = backup
        return 0

    def op_setAMDepth(self, ch, v):
        if v[0] & 1:
            self.vibratoAndAMDepthBits |= 0x80
        else:
            self.vibratoAndAMDepthBits &= 0x7F
        self.write_opl(0xBD, self.vibratoAndAMDepthBits)
        return 0

    def op_setVibratoDepth(self, ch, v):
        if v[0] & 1:
            self.vibratoAndAMDepthBits |= 0x40
        else:
            self.vibratoAndAMDepthBits &= 0xBF
        self.write_opl(0xBD, self.vibratoAndAMDepthBits)
        return 0

    def op_changeExtraLevel1(self, ch, v):
        ch["opExtraLevel1"] = (ch["opExtraLevel1"] + v[0]) & 0xFF
        self.adjust_volume(ch)
        return 0

    def op_clearChannel(self, ch, v):
        if v[0] > 9:
            return 0
        backup = self.curChannel
        self.curChannel = v[0]
        dataptr_backup = ch["dataptr"]
        ch2 = self.channels[self.curChannel]
        ch2["duration"] = 0
        ch2["priority"] = 0
        ch2["dataptr"] = None
        ch2["opExtraLevel2"] = 0
        if self.curChannel != 9:
            reg_off = REG_OFFSET[self.curChannel]
            self.write_opl(0xC0 + self.curChannel, 0x00)
            self.write_opl(0x43 + reg_off, 0x3F)
            self.write_opl(0x83 + reg_off, 0xFF)
            self.write_opl(0xB0 + self.curChannel, 0x00)
        self.curChannel = backup
        ch["dataptr"] = dataptr_backup
        return 0

    def op_changeNoteRandomly(self, ch, v):
        if self.curChannel >= 9:
            return 0
        mask = (v[0] << 8) | v[1]
        note = ((ch["regBx"] & 0x1F) << 8) | ch["regAx"]
        note = (note + (mask & self.get_random_nr())) & 0xFFFF
        note |= (ch["regBx"] & 0x20) << 8
        self.write_opl(0xA0 + self.curChannel, note & 0xFF)
        self.write_opl(0xB0 + self.curChannel, (note & 0xFF00) >> 8)
        return 0

    def op_removePrimaryEffectVibrato(self, ch, v):
        ch["primaryEffect"] = None
        return 0

    def op_pitchBend(self, ch, v):
        ch["pitchBend"] = to_int8(v[0])
        self.setup_note(ch["rawNote"], ch, True)
        return 0

    def op_resetToGlobalTempo(self, ch, v):
        ch["tempo"] = self.tempo
        return 0

    def op_nop(self, ch, v):
        return 0

    def op_setDurationRandomness(self, ch, v):
        ch["durationRandomness"] = v[0]
        return 0

    def op_changeChannelTempo(self, ch, v):
        ch["tempo"] = clip(ch["tempo"] + to_int8(v[0]), 1, 255)
        return 0

    def op_callback46(self, ch, v):
        return 0  # only ever touches an unused (in this driver) table; nothing audible

    def op_setupRhythmSection(self, ch, v):
        backup_chan, backup_reg = self.curChannel, self.curRegOffset
        self.curChannel = 6
        self.curRegOffset = REG_OFFSET[6]
        instr = self.get_instrument(v[0])
        if instr is not None:
            self.setup_instrument(self.curRegOffset, instr, ch)
        self.opLevelBD = ch["opLevel2"]
        self.curChannel = 7
        self.curRegOffset = REG_OFFSET[7]
        instr = self.get_instrument(v[1])
        if instr is not None:
            self.setup_instrument(self.curRegOffset, instr, ch)
        self.opLevelHH = ch["opLevel1"]
        self.opLevelSD = ch["opLevel2"]
        self.curChannel = 8
        self.curRegOffset = REG_OFFSET[8]
        instr = self.get_instrument(v[2])
        if instr is not None:
            self.setup_instrument(self.curRegOffset, instr, ch)
        self.opLevelTT = ch["opLevel1"]
        self.opLevelCY = ch["opLevel2"]
        self.channels[6]["regBx"] = v[3] & 0x2F
        self.write_opl(0xB6, self.channels[6]["regBx"])
        self.write_opl(0xA6, v[4])
        self.channels[7]["regBx"] = v[5] & 0x2F
        self.write_opl(0xB7, self.channels[7]["regBx"])
        self.write_opl(0xA7, v[6])
        self.channels[8]["regBx"] = v[7] & 0x2F
        self.write_opl(0xB8, self.channels[8]["regBx"])
        self.write_opl(0xA8, v[8])
        self.rhythmSectionBits = 0x20
        self.curRegOffset, self.curChannel = backup_reg, backup_chan
        return 0

    def op_playRhythmSection(self, ch, v):
        self.write_opl(0xBD, (self.rhythmSectionBits & (~(v[0] & 0x1F) & 0xFF)) | 0x20)
        self.rhythmSectionBits = (self.rhythmSectionBits | v[0]) & 0xFF
        self.write_opl(0xBD, self.vibratoAndAMDepthBits | 0x20 | self.rhythmSectionBits)
        return 0

    def op_removeRhythmSection(self, ch, v):
        self.rhythmSectionBits = 0
        self.write_opl(0xBD, self.vibratoAndAMDepthBits)
        return 0

    def _check_value(self, val):
        return clip(val, 0, 0x3F)

    def op_setRhythmLevel2(self, ch, v):
        ops, val = v[0], v[1]
        if ops & 1:
            self.opExtraLevel2HH = val
            self.write_opl(0x51, self._check_value(val + self.opLevelHH + self.opExtraLevel1HH + self.opExtraLevel2HH))
        if ops & 2:
            self.opExtraLevel2CY = val
            self.write_opl(0x55, self._check_value(val + self.opLevelCY + self.opExtraLevel1CY + self.opExtraLevel2CY))
        if ops & 4:
            self.opExtraLevel2TT = val
            self.write_opl(0x52, self._check_value(val + self.opLevelTT + self.opExtraLevel1TT + self.opExtraLevel2TT))
        if ops & 8:
            self.opExtraLevel2SD = val
            self.write_opl(0x54, self._check_value(val + self.opLevelSD + self.opExtraLevel1SD + self.opExtraLevel2SD))
        if ops & 16:
            self.opExtraLevel2BD = val
            self.write_opl(0x53, self._check_value(val + self.opLevelBD + self.opExtraLevel1BD + self.opExtraLevel2BD))
        return 0

    def op_changeRhythmLevel1(self, ch, v):
        ops, val = v[0], v[1]
        if ops & 1:
            self.opExtraLevel1HH = self._check_value(val + self.opLevelHH + self.opExtraLevel1HH + self.opExtraLevel2HH)
            self.write_opl(0x51, self.opExtraLevel1HH)
        if ops & 2:
            self.opExtraLevel1CY = self._check_value(val + self.opLevelCY + self.opExtraLevel1CY + self.opExtraLevel2CY)
            self.write_opl(0x55, self.opExtraLevel1CY)
        if ops & 4:
            self.opExtraLevel1TT = self._check_value(val + self.opLevelTT + self.opExtraLevel1TT + self.opExtraLevel2TT)
            self.write_opl(0x52, self.opExtraLevel1TT)
        if ops & 8:
            self.opExtraLevel1SD = self._check_value(val + self.opLevelSD + self.opExtraLevel1SD + self.opExtraLevel2SD)
            self.write_opl(0x54, self.opExtraLevel1SD)
        if ops & 16:
            self.opExtraLevel1BD = self._check_value(val + self.opLevelBD + self.opExtraLevel1BD + self.opExtraLevel2BD)
            self.write_opl(0x53, self.opExtraLevel1BD)
        return 0

    def op_setRhythmLevel1(self, ch, v):
        ops, val = v[0], v[1]
        if ops & 1:
            self.opExtraLevel1HH = val
            self.write_opl(0x51, self._check_value(val + self.opLevelHH + self.opExtraLevel2HH))
        if ops & 2:
            self.opExtraLevel1CY = val
            self.write_opl(0x55, self._check_value(val + self.opLevelCY + self.opExtraLevel2CY))
        if ops & 4:
            self.opExtraLevel1TT = val
            self.write_opl(0x52, self._check_value(val + self.opLevelTT + self.opExtraLevel2TT))
        if ops & 8:
            self.opExtraLevel1SD = val
            self.write_opl(0x54, self._check_value(val + self.opLevelSD + self.opExtraLevel2SD))
        if ops & 16:
            self.opExtraLevel1BD = val
            self.write_opl(0x53, self._check_value(val + self.opLevelBD + self.opExtraLevel2BD))
        return 0

    def op_setSoundTrigger(self, ch, v):
        self.soundTrigger = v[0]
        return 0

    def op_setTempoReset(self, ch, v):
        ch["tempoReset"] = v[0]
        return 0

    def op_callback56(self, ch, v):
        return 0

    # -- effects (run after opcode processing, once per tick, when result == 1) --

    def primary_effect_slide(self, ch):
        if self.curChannel >= 9:
            return
        if not advance(ch, "slideTimer", "slideTempo"):
            return
        freq = ((ch["regBx"] & 0x03) << 8) | ch["regAx"]
        octave = ch["regBx"] & 0x1C
        note_on = ch["regBx"] & 0x20
        freq += clip(ch["slideStep"], -0x3FF, 0x3FF)
        if ch["slideStep"] >= 0 and freq >= 734:
            freq >>= 1
            if not (freq & 0x3FF):
                freq += 1
            octave += 4
        elif ch["slideStep"] < 0 and freq < 388:
            if freq < 0:
                freq = 0
            freq <<= 1
            if not (freq & 0x3FF):
                freq -= 1
            octave -= 4
        ch["regAx"] = freq & 0xFF
        ch["regBx"] = (note_on | (octave & 0x1C) | ((freq >> 8) & 0x03)) & 0xFF
        self.write_opl(0xA0 + self.curChannel, ch["regAx"])
        self.write_opl(0xB0 + self.curChannel, ch["regBx"])

    def primary_effect_vibrato(self, ch):
        if self.curChannel >= 9:
            return
        if ch["vibratoDelayCountdown"]:
            ch["vibratoDelayCountdown"] = (ch["vibratoDelayCountdown"] - 1) & 0xFF
            return
        if advance(ch, "vibratoTimer", "vibratoTempo"):
            ch["vibratoStepsCountdown"] = (ch["vibratoStepsCountdown"] - 1) & 0xFF
            if ch["vibratoStepsCountdown"] == 0:
                ch["vibratoStep"] = -ch["vibratoStep"]
                ch["vibratoStepsCountdown"] = ch["vibratoNumSteps"]
            freq = (((ch["regBx"] << 8) | ch["regAx"]) & 0x3FF) + ch["vibratoStep"]
            freq &= 0xFFFF
            ch["regAx"] = freq & 0xFF
            ch["regBx"] = ((ch["regBx"] & 0xFC) | ((freq >> 8) & 0xFF)) & 0xFF
            self.write_opl(0xA0 + self.curChannel, ch["regAx"])
            self.write_opl(0xB0 + self.curChannel, ch["regBx"])

    def secondary_effect1(self, ch):
        if self.curChannel >= 9:
            return
        if advance(ch, "secondaryEffectTimer", "secondaryEffectTempo"):
            ch["secondaryEffectPos"] -= 1
            if ch["secondaryEffectPos"] < 0:
                ch["secondaryEffectPos"] = ch["secondaryEffectSize"]
            idx = ch["secondaryEffectData"] + ch["secondaryEffectPos"]
            val = self.data[BASE + idx] if 0 <= idx < self.soundsize else 0
            self.write_opl(ch["secondaryEffectRegbase"] + self.curRegOffset, val)

    # -- driver loop --

    def execute_programs(self):
        for cur in range(9, -1, -1):
            self.curChannel = cur
            ch = self.channels[cur]
            if ch["dataptr"] is None:
                continue
            if ch["lock"]:
                continue
            self.curRegOffset = 0 if cur == 9 else REG_OFFSET[cur]
            if ch["tempoReset"]:
                ch["tempo"] = self.tempo
            result = 1
            if advance(ch, "timer", "tempo"):
                ch["duration"] = (ch["duration"] - 1) & 0xFF
                if ch["duration"] != 0:
                    if ch["duration"] == ch["spacing2"]:
                        self.note_off(ch)
                    if ch["duration"] == ch["spacing1"] and cur != 9:
                        self.note_off(ch)
                else:
                    result = 0

            while result == 0 and ch["dataptr"] is not None:
                pos = ch["dataptr"]
                if pos is None or pos >= len(self.data):
                    opcode = 0xFF
                else:
                    opcode = self.data[pos]
                    ch["dataptr"] = pos + 1

                if opcode & 0x80:
                    idx = clip(opcode & 0x7F, 0, len(PARSER_OPCODES) - 1)
                    name, nvalues = PARSER_OPCODES[idx]
                    dp = ch["dataptr"]
                    if dp is None or dp + nvalues > len(self.data):
                        result = self.op_stopChannel(ch, [])
                        break
                    values = self.data[dp:dp + nvalues]
                    ch["dataptr"] = dp + nvalues
                    result = getattr(self, "op_" + name)(ch, values)
                else:
                    dp = ch["dataptr"]
                    if dp is None or dp >= len(self.data):
                        result = self.op_stopChannel(ch, [])
                        break
                    duration = self.data[dp]
                    ch["dataptr"] = dp + 1
                    self.setup_note(opcode, ch)
                    self.note_on(ch)
                    self.setup_duration(duration, ch)
                    result = 1 if duration != 0 else 0

            if result == 1:
                if ch["primaryEffect"] == "slide":
                    self.primary_effect_slide(ch)
                elif ch["primaryEffect"] == "vibrato":
                    self.primary_effect_vibrato(ch)
                if ch["secondaryEffect"] == "effect1":
                    self.secondary_effect1(ch)

    def callback_tick(self):
        self.execute_programs()
        if advance(self, "callbackTimer", "tempo"):
            self.beatDivCnt = (self.beatDivCnt - 1) & 0xFF
            if self.beatDivCnt == 0:
                self.beatDivCnt = self.beatDivider
                self.beatCounter = (self.beatCounter + 1) & 0xFF

    def start_program(self, ptr):
        chan = self.data[ptr]
        priority = self.data[ptr + 1]
        ch = self.channels[chan]
        self.init_channel(ch)
        ch["priority"] = priority
        ch["dataptr"] = ptr + 2
        ch["tempo"] = 0xFF
        ch["timer"] = 0xFF
        ch["duration"] = 1
        ch["volumeModifier"] = 0xFF
        self.init_adlib_channel(chan)

    def run(self, subsong_program_id, max_ticks=MAX_TICKS):
        for ch in self.channels:
            self.init_channel(ch)
        self.reset_adlib_state()
        ptr = self.get_program(subsong_program_id)
        if ptr is None:
            raise ValueError(f"program {subsong_program_id} has no valid data pointer")
        self.start_program(ptr)

        for self.tick in range(1, max_ticks + 1):
            self.callback_tick()
            if all(ch["dataptr"] is None for ch in self.channels):
                break
            if any(ch["repeating"] for ch in self.channels):
                break
        else:
            print(f"warning: hit MAX_TICKS ({max_ticks}) safety cap without a natural end or "
                  f"loop point", file=sys.stderr)

        return self.events


TICK_HZ = 72  # fixed Westwood ADL driver tick rate (AdLibDriver::CALLBACKS_PER_SECOND in adl.cpp)


def build_event_stream(events):
    """Collapse (tick, reg, value) triples into a flat (wait_ms, reg, value) stream - milliseconds,
    not ticks, so the NLM-side player needs no notion of the ADL format's 72Hz tick rate at all.
    Converting cumulatively (absolute tick -> absolute ms, then differencing) avoids the rounding
    drift that per-event tick*1000/72 division would accumulate over a multi-minute song. Gaps
    longer than 65535ms (unsigned short's range) are split with 0xFF-register no-op fillers (0xFF
    isn't a real OPL2 register, so it's a safe sentinel the runtime player just waits out)."""
    out = []
    last_ms = 0
    for tick, reg, value in events:
        cur_ms = (tick * 1000) // TICK_HZ
        gap = cur_ms - last_ms
        while gap > 0xFFFF:
            out.append((0xFFFF, 0xFF, 0))
            gap -= 0xFFFF
        out.append((gap, reg, value))
        last_ms = cur_ms
    return out


def write_song(c_path, h_path, array_name, macro_prefix, guard, stream, num_ticks):
    header_name = h_path.split("/")[-1]
    with open(h_path, "w", encoding="utf-8") as f:
        f.write(f"#ifndef {guard}\n#define {guard}\n\n")
        f.write('#include "opl2_event.h"\n\n')
        f.write(f"#define {macro_prefix.upper()}_EVENT_COUNT {len(stream)}\n")
        f.write(f"#define {macro_prefix.upper()}_TICK_COUNT {num_ticks}\n\n")
        f.write(f"extern const struct Opl2Event {array_name}[];\n\n")
        f.write("#endif\n")

    with open(c_path, "w", encoding="utf-8") as f:
        f.write(f'#include "{header_name}"\n\n')
        f.write(f"const struct Opl2Event {array_name}[{len(stream)}] = {{\n")
        for wait_ms, reg, value in stream:
            f.write(f"{{{wait_ms},{reg},{value}}},\n")
        f.write("};\n")


def write_opl2_event_header(output_dir):
    """The Opl2Event struct itself, shared by every generated song file (and by the C-side
    player) - kept separate so per-song headers don't each redefine it. wait_ms is already
    converted from the ADL format's native 72Hz tick rate (ADL_TICK_HZ, kept here purely for
    provenance) - the NLM-side player needs no notion of ticks or 72Hz at all, just milliseconds."""
    with open(f"{output_dir}/opl2_event.h", "w", encoding="utf-8") as f:
        f.write("#ifndef OPL2_EVENT_H\n#define OPL2_EVENT_H\n\n")
        f.write(f"#define ADL_TICK_HZ {TICK_HZ}\n\n")
        f.write("struct Opl2Event {\n")
        f.write("  unsigned short wait_ms;  /* real time, before the write below */\n")
        f.write("  unsigned char reg;       /* 0xFF: no OPL2 register, wait only */\n")
        f.write("  unsigned char value;\n")
        f.write("};\n\n")
        f.write("struct Opl2Song {\n")
        f.write("  int subsong_index;\n")
        f.write("  unsigned int event_count;\n")
        f.write("  unsigned int tick_count;\n")
        f.write("  const struct Opl2Event *events;\n")
        f.write("};\n\n")
        f.write("#endif\n")


def write_manifest(output_dir, base_name, songs):
    """songs: list of (subsong_index, program_id, file_base, array_name, event_count,
    tick_count)."""
    guard = f"{base_name.upper()}_SONGS_H"
    with open(f"{output_dir}/{base_name}_songs.h", "w", encoding="utf-8") as f:
        f.write(f"#ifndef {guard}\n#define {guard}\n\n")
        f.write('#include "opl2_event.h"\n\n')
        f.write(f"#define {base_name.upper()}_SONG_COUNT {len(songs)}\n\n")
        f.write(f"extern const struct Opl2Song {base_name}_songs[];\n\n")
        f.write("#endif\n")

    with open(f"{output_dir}/{base_name}_songs.c", "w", encoding="utf-8") as f:
        f.write(f'#include "{base_name}_songs.h"\n')
        for _, _, file_base, _, _, _ in songs:
            f.write(f'#include "{file_base}.h"\n')
        f.write("\n")
        f.write(f"const struct Opl2Song {base_name}_songs[{len(songs)}] = {{\n")
        for subsong_index, _program_id, _file_base, array_name, event_count, tick_count in songs:
            f.write(f"{{{subsong_index},{event_count},{tick_count},{array_name}}},\n")
        f.write("};\n")


def convert_one(data, primary_index, subsong_index, output_dir, base_name):
    program_id = primary_index[subsong_index]
    if program_id == 0xFF:
        raise ValueError(f"subsong index {subsong_index} is unused (0xFF)")

    emu = AdlEmulator(data)
    events = emu.run(program_id)
    num_ticks = emu.tick
    stream = build_event_stream(events)

    file_base = f"{base_name}_song{subsong_index}"
    array_name = f"{file_base}_events"
    c_path = f"{output_dir}/{file_base}.c"
    h_path = f"{output_dir}/{file_base}.h"
    guard = f"{file_base.upper()}_H"
    write_song(c_path, h_path, array_name, file_base, guard, stream, num_ticks)

    seconds = num_ticks / 72.0
    print(f"subsong {subsong_index} (program {program_id}): {len(events)} register writes over "
          f"{num_ticks} ticks ({seconds:.1f}s) -> {len(stream)} events -> {c_path}, {h_path}")

    return subsong_index, program_id, file_base, array_name, len(stream), num_ticks


def main():
    if len(sys.argv) not in (4, 5):
        print(f"usage: {sys.argv[0]} input.adl output_dir base_name [subsong_index]\n"
              "  subsong_index omitted: convert every named (non-0xFF) subsong and emit a "
              "manifest;\n  given: convert just that one subsong, no manifest.", file=sys.stderr)
        return 1

    adl_path, output_dir, base_name = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(adl_path, "rb") as f:
        data = f.read()
    primary_index = data[0:120]

    write_opl2_event_header(output_dir)

    if len(sys.argv) == 5:
        subsong_index = int(sys.argv[4], 0)
        if subsong_index < 0 or subsong_index >= 120:
            print(f"subsong index must be 0..119, got {subsong_index}", file=sys.stderr)
            return 1
        try:
            convert_one(data, primary_index, subsong_index, output_dir, base_name)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    songs = []
    for subsong_index in range(120):
        if primary_index[subsong_index] == 0xFF:
            continue
        songs.append(convert_one(data, primary_index, subsong_index, output_dir, base_name))

    if not songs:
        print(f"no named subsongs found in {adl_path}", file=sys.stderr)
        return 1

    write_manifest(output_dir, base_name, songs)
    print(f"{len(songs)} subsong(s) -> {output_dir}/{base_name}_songs.c, "
          f"{output_dir}/{base_name}_songs.h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
