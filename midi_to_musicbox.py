#!/usr/bin/env python3
"""
MIDI → 八音盒乐谱 JSON 转换工具

用法:
    python midi_to_musicbox.py input.mid [output.json]

如果不指定输出文件，结果会打印到终端并复制到剪贴板。

依赖:
    pip install mido

映射范围:
    MIDI 60-95 (C4-B6 的白键) → keyIndex 0-20
    黑键（半音）会被跳过
"""

import json
import sys
import os

try:
    import mido
except ImportError:
    print("请先安装 mido: pip install mido")
    sys.exit(1)


# MIDI 音符 → keyIndex 映射表 （仅白键）
# piano config.py 中的 KEY_NOTES:
#   C6(84)→0  D6(86)→1  E6(88)→2  F6(89)→3  G6(91)→4  A6(93)→5  B6(95)→6
#   C5(72)→7  D5(74)→8  E5(76)→9  F5(77)→10 G5(79)→11 A5(81)→12 B5(83)→13
#   C4(60)→14 D4(62)→15 E4(64)→16 F4(65)→17 G4(67)→18 A4(69)→19 B4(71)→20
MIDI_TO_KEY_INDEX = {
    60: 14, 62: 15, 64: 16, 65: 17, 67: 18, 69: 19, 71: 20,
    72: 7,  74: 8,  76: 9,  77: 10, 79: 11, 81: 12, 83: 13,
    84: 0,  86: 1,  88: 2,  89: 3,  91: 4,  93: 5,  95: 6,
}

# 白键 MIDI 音符集合（用于判断）
WHITE_NOTES = {60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83, 84, 86, 88, 89, 91, 93, 95}

# 音符名映射（仅用于调试输出）
NOTE_NAMES = {
    60: "C4", 62: "D4", 64: "E4", 65: "F4", 67: "G4", 69: "A4", 71: "B4",
    72: "C5", 74: "D5", 76: "E5", 77: "F5", 79: "G5", 81: "A5", 83: "B5",
    84: "C6", 86: "D6", 88: "E6", 89: "F6", 91: "G6", 93: "A6", 95: "B6",
}


def midi_to_musicbox(midi_path, song_name=None, ticks_per_beat=480):
    """将 MIDI 文件转换为八音盒乐谱数据
    
    Args:
        midi_path: MIDI 文件路径
        song_name: 曲名（不指定则用文件名）
        ticks_per_beat: 一拍多少 tick（输出格式中用 1 tick = 1/4 拍）
    
    Returns:
        dict: 乐谱 JSON 数据
    """
    mid = mido.MidiFile(midi_path)
    
    if song_name is None:
        song_name = os.path.splitext(os.path.basename(midi_path))[0]
    
    # 获取 BPM
    bpm = 120  # 默认
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                bpm = mido.tempo2bpm(msg.tempo)
                break
    
    print("曲名: %s" % song_name)
    print("BPM: %d" % bpm)
    print("MIDI ticks per beat: %d" % mid.ticks_per_beat)
    print()
    
    # 收集所有音符事件（note_on 且 velocity > 0）
    # 格式: {note: [(start_tick, velocity), ...]}
    note_events = {}  # note -> [(start_tick, end_tick, velocity)]
    ongoing = {}      # note -> (start_tick, velocity)
    
    total_messages = 0
    skipped_black = 0
    skipped_range = 0
    
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            total_messages += 1
            
            if msg.type == 'note_on' and msg.velocity > 0:
                note = msg.note
                if note not in WHITE_NOTES:
                    skipped_black += 1
                    continue
                if note < 60 or note > 95:
                    skipped_range += 1
                    continue
                ongoing[note] = (abs_tick, msg.velocity)
            
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                note = msg.note
                if note in ongoing:
                    start_tick, velocity = ongoing.pop(note)
                    if note not in note_events:
                        note_events[note] = []
                    note_events[note].append((start_tick, abs_tick, velocity))
    
    # 将剩余未关闭的音符也加入
    for note, (start_tick, velocity) in ongoing.items():
        if note not in note_events:
            note_events[note] = []
        note_events[note].append((start_tick, start_tick + mid.ticks_per_beat * 2, velocity))
    
    print("MIDI 消息总数: %d" % total_messages)
    print("跳过的黑键音符: %d" % skipped_black)
    print("跳过的范围外音符: %d" % skipped_range)
    print("有效白键音符数: %d" % sum(len(v) for v in note_events.values()))
    
    # 找到最小 tick，对齐到 0
    all_notes = []
    for note, events in note_events.items():
        for start_tick, end_tick, velocity in events:
            all_notes.append((note, start_tick, end_tick, velocity))
    
    if not all_notes:
        print("\n错误: 没有找到任何在 C4-B6 范围内的白键音符！")
        print("提示: 你的 MIDI 文件可能音域不在这个范围内。")
        print("你可以考虑用 MuseScore 等工具将乐曲移调后再试。")
        return None
    
    min_tick = min(n[1] for n in all_notes)
    
    # 转换为输出格式：
    # 将 MIDI ticks 转换为 1/4 拍 tick（每拍 = ticks_per_beat）
    # 这里使用 4 ticks 对应 1 拍，即 1 tick = 1/4 拍
    OUTPUT_TICKS_PER_BEAT = 4
    
    notes_output = []
    for note, start_tick, end_tick, velocity in all_notes:
        key_index = MIDI_TO_KEY_INDEX[note]
        
        # 缩放 tick
        adjusted_start = int((start_tick - min_tick) * OUTPUT_TICKS_PER_BEAT / mid.ticks_per_beat)
        duration = max(1, int((end_tick - start_tick) * OUTPUT_TICKS_PER_BEAT / mid.ticks_per_beat))
        
        # 音量映射 velocity 0-127 → 0.3-1.0
        vol = max(0.3, min(1.0, velocity / 127.0))
        
        notes_output.append([key_index, adjusted_start, duration, round(vol, 2)])
    
    # 按 start_tick 排序
    notes_output.sort(key=lambda x: (x[1], x[0]))
    
    # 计算总时长（tick数）
    max_end_tick = max(n[1] + n[2] for n in notes_output)
    duration_seconds = max_end_tick * (60.0 / bpm / OUTPUT_TICKS_PER_BEAT)
    
    print("\n输出音符数: %d" % len(notes_output))
    print("总时长: %.1f 秒 (%d ticks @ %d BPM)" % (duration_seconds, max_end_tick, bpm))
    
    # 构建输出 JSON
    result = {
        "v": 1,
        "n": song_name,
        "b": bpm,
        "t": notes_output,
    }
    
    return result


def try_set_clipboard(text):
    """尝试将文本复制到剪贴板（跨平台）"""
    try:
        import subprocess
        if sys.platform == 'win32':
            # Windows: 使用 clip 命令
            subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
            return True
        elif sys.platform == 'darwin':
            # macOS
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True)
            return True
        else:
            # Linux (需要 xclip)
            subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True)
            return True
    except Exception:
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    midi_path = sys.argv[1]
    if not os.path.exists(midi_path):
        print("文件不存在: %s" % midi_path)
        sys.exit(1)
    
    song_name = None
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = None
    
    result = midi_to_musicbox(midi_path, song_name)
    
    if result is None:
        sys.exit(1)
    
    json_str = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    pretty_json = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False)
    
    print("\n" + "=" * 50)
    print("转换结果 (JSON):")
    print("=" * 50)
    print(pretty_json)
    
    print("\n" + "=" * 50)
    print("紧凑格式 (可导入游戏):")
    print("=" * 50)
    print(json_str)
    
    # 尝试复制到剪贴板
    if try_set_clipboard(json_str):
        print("\n✓ 已复制紧凑格式 JSON 到剪贴板！")
        print("  进入游戏，手持空白乐谱右键八音盒，点击「导入乐谱」即可。")
    else:
        print("\n! 请手动复制上面的紧凑格式 JSON 到剪贴板。")
    
    # 写入文件
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=False)
        print("已写入文件: %s" % output_path)


if __name__ == "__main__":
    main()
