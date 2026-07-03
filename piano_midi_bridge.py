#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI 键盘 → 钢琴模组按键桥接

将外接 MIDI 键盘的实时输入转换成键盘按键事件，
让钢琴模组在游戏中响应 MIDI 键盘弹奏。

用法:
  1. 按 MIDI 键盘
  2. 确保《我的世界》窗口是激活状态
  3. 游戏中打开钢琴 UI
  4. 弹奏

依赖:
  pip install mido python-rtmidi
"""

import mido
import ctypes
import sys

# ======================== Windows 键盘模拟 (keybd_event) ========================

# 虚拟键码
VK_LSHIFT = 0xA0

# 钢琴模组用到的所有按键: 白键 + 黑键独立键
VK_MAP = {
    'Q': 0x51, 'W': 0x57, 'E': 0x45, 'R': 0x52, 'T': 0x54, 'Y': 0x59, 'U': 0x55,
    'A': 0x41, 'S': 0x53, 'D': 0x44, 'F': 0x46, 'G': 0x47, 'H': 0x48, 'J': 0x4A,
    'Z': 0x5A, 'X': 0x58, 'C': 0x43, 'V': 0x56, 'B': 0x42, 'N': 0x4E, 'M': 0x4D,
    '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
    '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39, '0': 0x30,
    'I': 0x49, 'O': 0x4F, 'P': 0x50, 'K': 0x4B, 'L': 0x4C,
}

user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002


def _key_down(vk_code):
    user32.keybd_event(vk_code, 0, 0, 0)


def _key_up(vk_code):
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def press_note(key_char, shift):
    """模拟按键按下"""
    if shift:
        _key_down(VK_LSHIFT)
    _key_down(VK_MAP[key_char])


def release_note(key_char, shift):
    """模拟按键抬起"""
    _key_up(VK_MAP[key_char])
    if shift:
        _key_up(VK_LSHIFT)


# ======================== MIDI 音符 → 按键映射 ========================
# 模组键位布局 (来自 core/keymap.py):
#   Q→C5 W→D5 E→E5 R→F5 T→G5 Y→A5 U→B5
#   A→C4 S→D4 D→E4 F→F4 G→G4 H→A4 J→B4
#   Z→C3 X→D3 C→E3 V→F3 B→G3 N→A3 M→B3
# 黑键 = Shift+对应白键的字母

# (keyChar, needsShift) for MIDI note 48-83
# 黑键使用独立按键: 1 2 . 3 4 5 | 6 7 . 8 9 0 | I O . P K L
_NOTE_MAP = {}

# Octave 5 (MIDI 72-83)
_OCTAVE_5 = {
    72: ('Q', False), 73: ('1', False),  # C5, C#5
    74: ('W', False), 75: ('2', False),  # D5, D#5
    76: ('E', False),                     # E5 (无黑键)
    77: ('R', False), 78: ('3', False),  # F5, F#5
    79: ('T', False), 80: ('4', False),  # G5, G#5
    81: ('Y', False), 82: ('5', False),  # A5, A#5
    83: ('U', False),                     # B5 (无黑键)
}

# Octave 4 (MIDI 60-71)
_OCTAVE_4 = {
    60: ('A', False), 61: ('6', False),  # C4, C#4
    62: ('S', False), 63: ('7', False),  # D4, D#4
    64: ('D', False),                     # E4 (无黑键)
    65: ('F', False), 66: ('8', False),  # F4, F#4
    67: ('G', False), 68: ('9', False),  # G4, G#4
    69: ('H', False), 70: ('0', False),  # A4, A#4
    71: ('J', False),                     # B4 (无黑键)
}

# Octave 3 (MIDI 48-59)
_OCTAVE_3 = {
    48: ('Z', False), 49: ('I', False),  # C3, C#3
    50: ('X', False), 51: ('O', False),  # D3, D#3
    52: ('C', False),                     # E3 (无黑键)
    53: ('V', False), 54: ('P', False),  # F3, F#3
    55: ('B', False), 56: ('K', False),  # G3, G#3
    57: ('N', False), 58: ('L', False),  # A3, A#3
    59: ('M', False),                     # B3 (无黑键)
}

_NOTE_MAP.update(_OCTAVE_5)
_NOTE_MAP.update(_OCTAVE_4)
_NOTE_MAP.update(_OCTAVE_3)


def note_name(midi_note):
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return '%s%d' % (names[midi_note % 12], (midi_note // 12) - 1)


# ======================== MIDI 输入处理 ========================

class MidiBridge(object):

    def __init__(self):
        self._inport = None
        self._active_notes = {}  # midiNote -> (keyChar, shift, isDown)
        self._running = False

    @staticmethod
    def _init_backend():
        """尝试所有可用 MIDI 后端，返回是否成功"""
        candidates = [
            'mido.backends.rtmidi',
            'mido.backends.winmm',
            'mido.backends.portmidi',
        ]
        for name in candidates:
            try:
                mido.set_backend(name)
                # 验证后端能正常工作
                mido.get_input_names()
                print('使用 MIDI 后端: %s' % name.rsplit('.', 1)[-1])
                return True
            except Exception:
                continue
        return False

    def start(self):
        # 自动选择可用后端
        if not self._init_backend():
            print('错误: 没有可用的 MIDI 后端')
            print('请安装: pip install python-rtmidi')
            sys.exit(1)

        ports = mido.get_input_names()
        if not ports:
            print('错误: 没有找到 MIDI 输入设备')
            print('请确认 MIDI 键盘已连接。')
            sys.exit(1)

        print('可用的 MIDI 输入端口:')
        for i, name in enumerate(ports):
            print('  [%d] %s' % (i, name))
        print()

        # 自动选择第一个，或让用户选
        if len(ports) == 1:
            idx = 0
        else:
            try:
                idx = int(input('选择端口号 [0]: ') or '0')
            except (ValueError, IndexError):
                idx = 0

        port_name = ports[idx]
        print('打开端口: %s' % port_name)
        self._inport = mido.open_input(port_name)

        self._running = True
        print('监听中... (Ctrl+C 退出)')
        print('MIDI note 范围: 48(C3) ~ 83(B5)')
        print()

        self._listen_loop()

    def _listen_loop(self):
        try:
            while self._running:
                msg = self._inport.receive()
                self._handle_msg(msg)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _handle_msg(self, msg):
        if msg.type == 'note_on' and msg.velocity > 0:
            self._note_on(msg.note, msg.velocity)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            self._note_off(msg.note)

    def _note_on(self, midi_note, velocity):
        if midi_note not in _NOTE_MAP:
            return  # 超出模组支持范围
        if midi_note in self._active_notes:
            return  # 防止重复按下

        key_char, shift = _NOTE_MAP[midi_note]
        self._active_notes[midi_note] = (key_char, shift)
        press_note(key_char, shift)
        print('  [+] %s (MIDI %d) → %s' % (
            note_name(midi_note), midi_note, key_char))

    def _note_off(self, midi_note):
        if midi_note not in self._active_notes:
            return
        key_char, shift = self._active_notes.pop(midi_note)
        release_note(key_char, shift)
        print('  [-] %s (MIDI %d)' % (note_name(midi_note), midi_note))

    def _cleanup(self):
        # 释放所有按住的键
        for midi_note, (key_char, shift) in list(self._active_notes.items()):
            release_note(key_char, shift)
        self._active_notes.clear()
        if self._inport:
            self._inport.close()
        print('\n已断开 MIDI 连接')


# ======================== 入口 ========================

def main():
    print('=' * 50)
    print('  MIDI 键盘 → 钢琴模组 桥接器')
    print('  支持 MIDI note 48(C3) ~ 83(B5)')
    print('=' * 50)
    print()
    print('提示: 确保《我的世界》窗口处于激活状态')
    print('      游戏中打开钢琴 UI 后即可弹奏')
    print()

    bridge = MidiBridge()
    bridge.start()


if __name__ == '__main__':
    main()
