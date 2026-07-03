#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI 音符连接器 - 自动合并首尾相接的同音音符

功能：
  将 MIDI 文件中同一音高上"首尾相接"的音符合并为一个长音符。
  对于同音反复的旋律线（如弦乐、管乐的连奏），这能生成更自然的连音效果。
  
  合并条件（可配置）：
  - 音符 A 的结束位置 >= 音符 B 的开始位置（重叠）
  - 音符 B 的开始位置 - 音符 A 的结束位置 <= 间隙阈值（默认 0，即刚好衔接）
  
用法：
  # 命令行：处理 MIDI 文件并输出新的 MIDI
  python midi_note_connector.py input.mid output.mid
  
  # 仅查看分析结果
  python midi_note_connector.py input.mid --analyze
  
  # 作为模块导入使用
  from midi_note_connector import connect_notes
  
依赖:
  pip install mido
"""

import argparse
import sys
import os

try:
    import mido
except ImportError:
    print("请先安装 mido: pip install mido")
    sys.exit(1)


# ======================== 音符连接核心逻辑 ========================


def extract_notes(mid, min_note=0, max_note=127):
    """从 MIDI 文件中提取所有 (note, start_tick, end_tick, velocity) 元组

    Args:
        mid: mido.MidiFile 对象
        min_note: 最小音符编号（含）
        max_note: 最大音符编号（含）

    Returns:
        list: [(note, start_tick, end_tick, velocity), ...]
    """
    # 收集音符事件
    ongoing = {}  # note -> (start_tick, velocity)
    notes = []    # (note, start_tick, end_tick, velocity)

    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                note = msg.note
                if note < min_note or note > max_note:
                    continue
                ongoing[note] = (abs_tick, msg.velocity)

            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                note = msg.note
                if note in ongoing:
                    start_tick, velocity = ongoing.pop(note)
                    notes.append((note, start_tick, abs_tick, velocity))

    # 处理未关闭的音符（在 MIDI 文件结尾处）
    last_tick = max((n[2] for n in notes), default=0) + mid.ticks_per_beat * 4
    for note, (start_tick, velocity) in ongoing.items():
        notes.append((note, start_tick, last_tick, velocity))

    return notes


def connect_notes(notes, gap_threshold=0, merge_overlap=True, same_velocity=True):
    """合并同一音高上首尾相接的音符

    Args:
        notes: [(note, start_tick, end_tick, velocity), ...]
        gap_threshold: 允许合并的最大间隙（tick 数）。
                       0 = 仅当结束=开始时合并，
                       正数 = 允许指定 tick 内的间隙也合并。
        merge_overlap: 是否合并重叠音符（默认 True）
        same_velocity: 仅合并且 velocity 相同的音符（默认 True）

    Returns:
        list: [(note, start_tick, end_tick, velocity), ...] 合并后的音符列表
    """
    if not notes:
        return []

    # 按音高分组，同音高内按开始时间排序
    by_pitch = {}
    for note in notes:
        pitch = note[0]
        by_pitch.setdefault(pitch, []).append(note)

    for pitch in by_pitch:
        by_pitch[pitch].sort(key=lambda x: (x[1], x[2]))

    result = []
    for pitch in sorted(by_pitch.keys()):
        merged = _merge_single_pitch(by_pitch[pitch], gap_threshold, merge_overlap, same_velocity)
        result.extend(merged)

    return result


def _merge_single_pitch(notes, gap_threshold, merge_overlap, same_velocity):
    """合并同一音高的一组音符"""
    merged = []
    current = None  # (note, start, end, velocity)

    for note, start, end, velocity in notes:
        if current is None:
            current = [note, start, end, velocity]
            continue

        prev_note, prev_start, prev_end, prev_vel = current
        gap = start - prev_end

        # 判断是否可以合并
        can_merge = False
        if merge_overlap and gap <= 0:
            # 重叠或刚好衔接
            if not same_velocity or prev_vel == velocity:
                can_merge = True
        elif 0 < gap <= gap_threshold:
            # 间隙在阈值内
            if not same_velocity or prev_vel == velocity:
                can_merge = True

        if can_merge:
            # 合并：起始取最早，结束取最晚，velocity 取第一个
            current = [
                current[0],  # note
                current[1],  # start (最早)
                max(current[2], end),  # end (最晚)
                current[3],  # velocity (保留第一个)
            ]
        else:
            merged.append(tuple(current))
            current = [note, start, end, velocity]

    if current is not None:
        merged.append(tuple(current))

    return merged


# ======================== 过滤极短音符 ========================


def filter_short_notes(notes, min_duration):
    """过滤掉时长小于 min_duration tick 的音符（杂音/幽灵音符）

    Args:
        notes: [(note, start_tick, end_tick, velocity), ...]
        min_duration: 最小时长阈值（tick），时长 < 此值的音符被删除

    Returns:
        list: 过滤后的音符列表
    """
    if min_duration <= 0:
        return notes
    return [n for n in notes if n[2] - n[1] >= min_duration]


# ======================== MIDI 文件写入 ========================


def notes_to_midi(notes, ticks_per_beat=480, tempo=500000):
    """将音符列表转换为 mido.MidiFile 对象

    Args:
        notes: [(note, start_tick, end_tick, velocity), ...]
        ticks_per_beat: 每拍 tick 数
        tempo: 微秒数/拍 (500000 = 120 BPM)

    Returns:
        mido.MidiFile
    """
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # 添加 tempo 事件
    track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
    track.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0))

    # 按音高、开始时间排序
    sorted_notes = sorted(notes, key=lambda x: (x[1], x[0]))

    # 将 (note, start, end, vel) 转换为 note_on / note_off 事件流
    events = []  # (tick, type, note, velocity)
    for note, start, end, velocity in sorted_notes:
        events.append((start, 'note_on', note, velocity))
        events.append((end, 'note_off', note, 0))

    events.sort(key=lambda x: (x[0], 0 if x[1] == 'note_off' else 1))

    abs_tick = 0
    for tick, ev_type, note, velocity in events:
        delta = tick - abs_tick
        abs_tick = tick
        msg = mido.Message(ev_type, note=note, velocity=velocity, time=delta)
        track.append(msg)

    return mid


# ======================== 分析报告 ========================


def analyze_notes(notes, gap_threshold=0):
    """分析并打印音符连接情况"""
    by_pitch = {}
    for note in notes:
        by_pitch.setdefault(note[0], []).append(note)

    for pitch in sorted(by_pitch.keys()):
        pitch_notes = sorted(by_pitch[pitch], key=lambda x: (x[1], x[2]))
        connections = 0
        total_gap = 0
        max_gap = 0
        for i in range(1, len(pitch_notes)):
            gap = pitch_notes[i][1] - pitch_notes[i - 1][2]
            if gap <= 0:
                connections += 1
            elif gap <= gap_threshold:
                connections += 1
            if gap > 0:
                total_gap += gap
                max_gap = max(max_gap, gap)

        if connections > 0:
            print("  音高 %d (%s): %d 个音符, %d 处可合并, 最大间隙 %d ticks" % (
                pitch, _note_name(pitch), len(pitch_notes), connections, max_gap))


def _note_name(midi_note):
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return '%s%d' % (names[midi_note % 12], (midi_note // 12) - 1)


def print_stats(notes_before, notes_after):
    """打印合并前后的统计信息"""
    before_count = len(notes_before)
    after_count = len(notes_after)
    before_duration = sum(n[2] - n[1] for n in notes_before)
    after_duration = sum(n[2] - n[1] for n in notes_after)

    print("")
    print("=" * 50)
    print("合并统计:")
    print("  处理前: %d 个音符" % before_count)
    print("  处理后: %d 个音符" % after_count)
    print("  合并了: %d 个音符 (减少 %.1f%%)" % (
        before_count - after_count,
        (before_count - after_count) / before_count * 100 if before_count else 0))
    print("  总时长: %d ticks → %d ticks (+%d)" % (
        before_duration, after_duration, after_duration - before_duration))
    print("=" * 50)


# ======================== 集成辅助: 给现有转换工具使用 ========================


def preprocess_midi(midi_path, gap_threshold=0, merge_overlap=True, same_velocity=True):
    """预处理 MIDI 文件，返回连接后的音符列表

    这个函数供现有转换工具（midi_to_musicbox.py 等）导入使用。
    
    用法:
        from midi_note_connector import preprocess_midi
        notes = preprocess_midi("input.mid", gap_threshold=0)
    """
    mid = mido.MidiFile(midi_path)
    notes = extract_notes(mid)
    connected = connect_notes(notes, gap_threshold, merge_overlap, same_velocity)
    return connected, mid.ticks_per_beat


# ======================== CLI 入口 ========================


def main():
    parser = argparse.ArgumentParser(
        description="MIDI 音符连接器 - 自动合并首尾相接的同音音符",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s input.mid output.mid          # 处理并输出新 MIDI
  %(prog)s input.mid output.mid -g 10    # 允许 10 tick 间隙的合并
  %(prog)s input.mid --analyze           # 仅分析，不输出文件
  %(prog)s input.mid output.mid -nv      # 不限制 velocity 必须相同
  %(prog)s input.mid output.mid -d 5     # 过滤掉时长 < 5 tick 的杂音音符
        """)
    parser.add_argument("input", help="输入 MIDI 文件路径")
    parser.add_argument("output", nargs="?", help="输出 MIDI 文件路径（不指定则仅分析）")
    parser.add_argument("-g", "--gap", type=int, default=0,
                        help="允许合并的最大间隙（tick 数），默认 0")
    parser.add_argument("-d", "--min-duration", type=int, default=0,
                        help="过滤极短音符：时长小于此 tick 数的音符被删除，默认 0（不过滤）")
    parser.add_argument("--no-overlap", action="store_true",
                        help="不合并重叠音符")
    parser.add_argument("--any-velocity", action="store_true",
                        help="不要求 velocity 相同也可以合并")
    parser.add_argument("--analyze", action="store_true",
                        help="仅分析连接情况，不输出文件")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("文件不存在: %s" % args.input)
        sys.exit(1)

    # 读取 MIDI 文件
    print("读取 MIDI 文件: %s" % args.input)
    mid = mido.MidiFile(args.input)
    print("  格式: %s, 曲数: %d" % (
        "类型 0" if mid.type == 0 else "类型 1", len(mid.tracks)))
    print("  Ticks/拍: %d" % mid.ticks_per_beat)
    for i, track in enumerate(mid.tracks):
        print("  轨道 %d: %s (%d 条消息)" % (i, track.name, len(track)))

    # 提取音符
    notes = extract_notes(mid)
    if not notes:
        print("错误: 未找到任何音符事件")
        sys.exit(1)

    print("\n提取到 %d 个音符" % len(notes))
    print("音高范围: %s(%d) ~ %s(%d)" % (
        _note_name(min(n[0] for n in notes)), min(n[0] for n in notes),
        _note_name(max(n[0] for n in notes)), max(n[0] for n in notes)))

    # 过滤极短音符
    if args.min_duration > 0:
        filtered_count = len(notes)
        notes = filter_short_notes(notes, args.min_duration)
        removed = filtered_count - len(notes)
        print("过滤极短音符: 删除 %d 个 (时长 < %d ticks)" % (removed, args.min_duration))
        if not notes:
            print("错误: 过滤后没有剩余音符!")
            sys.exit(1)

    # 仅分析模式
    if args.analyze:
        print("\n各音高连接分析 (间隙阈值: %d ticks):" % args.gap)
        analyze_notes(notes, args.gap)

        connected = connect_notes(
            notes, args.gap, not args.no_overlap, not args.any_velocity)
        print_stats(notes, connected)

        print("\n（仅分析模式，未生成文件）")
        return

    # 执行连接
    print("\n正在连接音符 (间隙阈值=%d, %s, %s)..." % (
        args.gap,
        "合并重叠" if not args.no_overlap else "不合并重叠",
        "仅同 velocity" if not args.any_velocity else "任意 velocity"))

    connected = connect_notes(
        notes, args.gap, not args.no_overlap, not args.any_velocity)

    print_stats(notes, connected)

    # 输出详细信息
    if len(notes) - len(connected) > 0:
        print("\n按音高合并详情:")
        before_by_pitch = {}
        for n in notes:
            before_by_pitch.setdefault(n[0], []).append(n)
        after_by_pitch = {}
        for n in connected:
            after_by_pitch.setdefault(n[0], []).append(n)

        for pitch in sorted(before_by_pitch.keys()):
            before_count = len(before_by_pitch[pitch])
            after_count = len(after_by_pitch.get(pitch, []))
            if before_count != after_count:
                print("  %s (MIDI %d): %d → %d (合并 %d)" % (
                    _note_name(pitch), pitch,
                    before_count, after_count, before_count - after_count))

    # 输出 MIDI 文件
    if args.output:
        # 获取 tempo
        tempo = 500000  # 默认 120 BPM
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break

        out_mid = notes_to_midi(connected, mid.ticks_per_beat, tempo)
        out_mid.save(args.output)
        print("\n已输出 MIDI 文件: %s" % args.output)
    else:
        print("\n（未指定输出文件，未保存）")


if __name__ == "__main__":
    main()
