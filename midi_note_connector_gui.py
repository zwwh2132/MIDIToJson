#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI 音符连接器 (GUI 版)

自动合并同一音高上首尾相接的音符，输出处理后的 MIDI 文件。

依赖:
    pip install mido

用法:
    python midi_note_connector_gui.py
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import mido
except ImportError:
    print("=" * 50)
    print("错误: 缺少 mido 库!")
    print("请运行: pip install mido")
    print("=" * 50)
    try:
        tk.Tk().withdraw()
        messagebox.showerror("缺少依赖", "请先安装 mido：\npip install mido")
    except Exception:
        pass
    sys.exit(1)

from midi_note_connector import extract_notes, connect_notes, notes_to_midi, print_stats, _note_name, filter_short_notes


class MidiNoteConnectorGUI:

    def __init__(self):
        self.window = tk.Tk()
        self.window.title("MIDI 音符连接器")
        self.window.geometry("700x600")
        self.window.resizable(False, False)

        self.midi_path = None
        self._processing = False

        self._build_ui()

    def _build_ui(self):
        # ====== 文件选择区域 ======
        file_frame = ttk.LabelFrame(self.window, text="选择 MIDI 文件", padding=10)
        file_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(file_frame, text="浏览...", command=self._select_file).pack(side="right")

        # ====== 参数设置区域 ======
        param_frame = ttk.LabelFrame(self.window, text="合并参数", padding=10)
        param_frame.pack(fill="x", padx=10, pady=10)

        # Gap threshold
        gap_row = ttk.Frame(param_frame)
        gap_row.pack(fill="x", pady=2)
        ttk.Label(gap_row, text="间隙阈值 (tick):", width=18, anchor="e").pack(side="left", padx=(0, 10))
        self.gap_var = tk.IntVar(value=0)
        self.gap_spinbox = ttk.Spinbox(gap_row, from_=0, to=120, increment=1,
                                       textvariable=self.gap_var, width=8)
        self.gap_spinbox.pack(side="left")
        ttk.Label(gap_row, text="前后两个音符间隙 ≤ 此值时合并，0=仅刚好衔接时合并").pack(
            side="left", padx=(10, 0))

        # Merge overlap
        overlap_row = ttk.Frame(param_frame)
        overlap_row.pack(fill="x", pady=2)
        self.overlap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(overlap_row, text="合并重叠音符",
                        variable=self.overlap_var).pack(side="left", padx=(18, 0))
        ttk.Label(overlap_row, text="（后一个音符在前一个结束前开始）").pack(side="left", padx=(10, 0))

        # Any velocity
        vel_row = ttk.Frame(param_frame)
        vel_row.pack(fill="x", pady=2)
        self.any_vel_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(vel_row, text="不要求力度相同",
                        variable=self.any_vel_var).pack(side="left", padx=(18, 0))
        ttk.Label(vel_row, text="（即使 velocity 不同也合并）").pack(side="left", padx=(10, 0))

        # ====== 分隔线 ======
        sep = ttk.Separator(param_frame, orient="horizontal")
        sep.pack(fill="x", pady=6)

        # 过滤极短音符
        filter_row = ttk.Frame(param_frame)
        filter_row.pack(fill="x", pady=2)
        self.enable_filter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="过滤极短音符",
                        variable=self.enable_filter_var,
                        command=self._toggle_filter).pack(side="left", padx=(18, 0))
        self.min_dur_var = tk.IntVar(value=5)
        self.min_dur_spinbox = ttk.Spinbox(filter_row, from_=1, to=120, increment=1,
                                           textvariable=self.min_dur_var, width=8, state="disabled")
        self.min_dur_spinbox.pack(side="left", padx=(10, 5))
        self.min_dur_label = ttk.Label(filter_row, text="tick 以内的杂音音符将被删除",
                                       foreground="gray")
        self.min_dur_label.pack(side="left")

        # ====== 操作按钮 ======
        btn_frame = ttk.Frame(self.window, padding=5)
        btn_frame.pack(fill="x", padx=10)

        self.analyze_btn = ttk.Button(btn_frame, text="分析连接情况",
                                      command=self._analyze, state="disabled")
        self.analyze_btn.pack(side="left", padx=2)

        self.process_btn = ttk.Button(btn_frame, text="处理并保存 MIDI...",
                                      command=self._process, state="disabled")
        self.process_btn.pack(side="left", padx=2)

        # ====== 信息/日志区域 ======
        info_frame = ttk.LabelFrame(self.window, text="处理信息", padding=10)
        info_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.info_text = tk.Text(info_frame, height=28, width=80, state="disabled",
                                 font=("Consolas", 9), bg="#f5f5f5", wrap="none")
        self.info_text.pack(fill="both", expand=True)

        # 添加滚动条
        v_scroll = ttk.Scrollbar(self.info_text, orient="vertical", command=self.info_text.yview)
        v_scroll.pack(side="right", fill="y")
        self.info_text.config(yscrollcommand=v_scroll.set)

        h_scroll = ttk.Scrollbar(self.info_text, orient="horizontal", command=self.info_text.xview)
        h_scroll.pack(side="bottom", fill="x")
        self.info_text.config(xscrollcommand=h_scroll.set)

        # ====== 状态栏 ======
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.window, textvariable=self.status_var, relief="sunken",
                               anchor="w", padding=5)
        status_bar.pack(fill="x", padx=10, pady=(0, 10))

    # ======================== 事件处理 ========================

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="选择 MIDI 文件",
            filetypes=[("MIDI 文件", "*.mid *.midi"), ("所有文件", "*.*")]
        )
        if path:
            self.midi_path = path
            self.file_path_var.set(path)
            self.analyze_btn.config(state="normal")
            self.process_btn.config(state="normal")
            self._clear_info()
            self._log_info("已选择文件: %s" % path)
            self.status_var.set("已选择文件: %s" % os.path.basename(path))

    def _log_info(self, text):
        self.info_text.config(state="normal")
        self.info_text.insert("end", text + "\n")
        self.info_text.see("end")
        self.info_text.config(state="disabled")
        self.window.update_idletasks()

    def _clear_info(self):
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.config(state="disabled")

    def _set_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        self.analyze_btn.config(state=state)
        self.process_btn.config(state=state)

    def _toggle_filter(self):
        state = "normal" if self.enable_filter_var.get() else "disabled"
        self.min_dur_spinbox.config(state=state)
        self.min_dur_label.config(foreground="black" if self.enable_filter_var.get() else "gray")

    # ======================== 分析模式 ========================

    def _analyze(self):
        if not self.midi_path or self._processing:
            return
        self._clear_info()
        self._log_info("=" * 50)
        self._log_info("分析 MIDI 文件...")
        self._log_info("")
        self.status_var.set("正在分析...")
        self._set_buttons(False)

        t = threading.Thread(target=self._analyze_thread, daemon=True)
        t.start()
        self._poll_thread(t, "analyze")

    def _analyze_thread(self):
        try:
            mid = mido.MidiFile(self.midi_path)
            notes = extract_notes(mid)

            self._log_info("文件: %s" % self.midi_path)
            self._log_info("  格式: 类型 %d, %d 个轨道, %d ticks/拍" % (
                mid.type, len(mid.tracks), mid.ticks_per_beat))
            self._log_info("")

            if not notes:
                self._log_info("错误: 未找到任何音符事件!")
                self.status_var.set("分析失败: 无音符")
                return

            # 基本信息
            pitches = sorted(set(n[0] for n in notes))
            self._log_info("音符总数: %d" % len(notes))
            self._log_info("音高范围: %s(%d) ~ %s(%d)" % (
                _note_name(min(pitches)), min(pitches),
                _note_name(max(pitches)), max(pitches)))
            self._log_info("涉及音高: %d 个" % len(pitches))
            self._log_info("")

            # 获取参数
            gap = self.gap_var.get()
            merge_overlap = self.overlap_var.get()
            any_velocity = self.any_vel_var.get()
            enable_filter = self.enable_filter_var.get()
            min_duration = self.min_dur_var.get() if enable_filter else 0

            self._log_info("合并参数:")
            self._log_info("  间隙阈值: %d tick%s" % (gap, " (仅刚好衔接)" if gap == 0 else ""))
            self._log_info("  合并重叠: %s" % ("是" if merge_overlap else "否"))
            self._log_info("  力度限制: %s" % ("不限制" if any_velocity else "仅相同力度合并"))
            self._log_info("")

            # 过滤极短音符（先处理，再分析连接）
            original_count = len(notes)
            if enable_filter and min_duration > 0:
                notes = filter_short_notes(notes, min_duration)
                removed = original_count - len(notes)
                self._log_info("过滤极短音符: 删除 %d 个 (时长 < %d ticks)" % (removed, min_duration))
                self._log_info("")
                if not notes:
                    self._log_info("错误: 过滤后没有剩余音符!")
                    self.status_var.set("分析失败: 过滤后无音符")
                    return

            # 各音高连接分析
            by_pitch = {}
            for n in notes:
                by_pitch.setdefault(n[0], []).append(n)

            total_connectable = 0
            self._log_info("按音高分析:")
            for pitch in sorted(by_pitch.keys()):
                pitch_notes = sorted(by_pitch[pitch], key=lambda x: (x[1], x[2]))
                connections = 0
                max_gap = 0
                for i in range(1, len(pitch_notes)):
                    g = pitch_notes[i][1] - pitch_notes[i - 1][2]
                    if merge_overlap and g <= 0:
                        connections += 1
                    elif 0 < g <= gap:
                        connections += 1
                    if g > max_gap:
                        max_gap = g

                if connections > 0:
                    total_connectable += connections
                    self._log_info("  %s (MIDI %3d): %3d 个音符, %d 处可合并, 最大间隙 %d ticks" % (
                        _note_name(pitch), pitch, len(pitch_notes), connections, max_gap))

            if total_connectable == 0:
                self._log_info("  (无首尾相接或重叠的同音音符)")

            self._log_info("")
            self._log_info("可合并位置总数: %d" % total_connectable)
            self._log_info("")

            # 执行合并看结果
            connected = connect_notes(notes, gap, merge_overlap, not any_velocity)
            before_count = len(notes)
            after_count = len(connected)
            before_dur = sum(n[2] - n[1] for n in notes)
            after_dur = sum(n[2] - n[1] for n in connected)

            self._log_info("合并效果预估:")
            self._log_info("  %d → %d 个音符 (减少 %d, %.1f%%)" % (
                before_count, after_count,
                before_count - after_count,
                (before_count - after_count) / before_count * 100 if before_count else 0))
            self._log_info("  总时长: %d → %d ticks (+%d)" % (
                before_dur, after_dur, after_dur - before_dur))

            self.status_var.set("分析完成: 可合并 %d 处" % total_connectable)

        except Exception as e:
            self._log_info("分析出错: %s" % e)
            self.status_var.set("分析失败: %s" % e)

    # ======================== 处理模式 ========================

    def _process(self):
        if not self.midi_path or self._processing:
            return

        # 选择保存路径
        default_name = os.path.splitext(os.path.basename(self.midi_path))[0] + "_connected.mid"
        output_path = filedialog.asksaveasfilename(
            title="保存处理后的 MIDI 文件",
            defaultextension=".mid",
            initialfile=default_name,
            filetypes=[("MIDI 文件", "*.mid"), ("所有文件", "*.*")]
        )
        if not output_path:
            return

        self._clear_info()
        self._log_info("=" * 50)
        self._log_info("处理 MIDI 文件...")
        self._log_info("")
        self.status_var.set("正在处理...")
        self._set_buttons(False)

        self._output_path = output_path
        t = threading.Thread(target=self._process_thread, daemon=True)
        t.start()
        self._poll_thread(t, "process")

    def _process_thread(self):
        try:
            gap = self.gap_var.get()
            merge_overlap = self.overlap_var.get()
            any_velocity = self.any_vel_var.get()
            enable_filter = self.enable_filter_var.get()
            min_duration = self.min_dur_var.get() if enable_filter else 0

            mid = mido.MidiFile(self.midi_path)
            notes = extract_notes(mid)

            self._log_info("输入: %s" % self.midi_path)
            self._log_info("  轨道: %d, Ticks/拍: %d" % (len(mid.tracks), mid.ticks_per_beat))
            self._log_info("  提取到 %d 个音符" % len(notes))
            self._log_info("")

            # 过滤极短音符
            if enable_filter and min_duration > 0:
                original_count = len(notes)
                notes = filter_short_notes(notes, min_duration)
                removed = original_count - len(notes)
                self._log_info("过滤极短音符: 删除 %d 个 (时长 < %d ticks)" % (removed, min_duration))
                self._log_info("")
                if not notes:
                    self._log_info("错误: 过滤后没有剩余音符!")
                    self.status_var.set("处理失败: 过滤后无音符")
                    return

            self._log_info("参数: 间隙=%d, %s, %s" % (
                gap,
                "合并重叠" if merge_overlap else "不合并重叠",
                "任意力度" if any_velocity else "仅同力度"))
            self._log_info("")

            # 执行合并
            connected = connect_notes(notes, gap, merge_overlap, not any_velocity)

            # 统计
            before_count = len(notes)
            after_count = len(connected)
            before_dur = sum(n[2] - n[1] for n in notes)
            after_dur = sum(n[2] - n[1] for n in connected)

            self._log_info("合并结果:")
            self._log_info("  %d → %d 个音符 (合并 %d, 减少 %.1f%%)" % (
                before_count, after_count,
                before_count - after_count,
                (before_count - after_count) / before_count * 100 if before_count else 0))
            self._log_info("  总时长: %d → %d ticks (+%d)" % (
                before_dur, after_dur, after_dur - before_dur))
            self._log_info("")

            # 输出各音高详情
            if before_count != after_count:
                before_by_pitch = {}
                for n in notes:
                    before_by_pitch.setdefault(n[0], []).append(n)
                after_by_pitch = {}
                for n in connected:
                    after_by_pitch.setdefault(n[0], []).append(n)

                self._log_info("按音高合并详情:")
                for pitch in sorted(before_by_pitch.keys()):
                    bc = len(before_by_pitch[pitch])
                    ac = len(after_by_pitch.get(pitch, []))
                    if bc != ac:
                        self._log_info("  %s (MIDI %3d): %d → %d (合并 %d)" % (
                            _note_name(pitch), pitch, bc, ac, bc - ac))

            # 获取 tempo
            tempo = 500000
            for track in mid.tracks:
                for msg in track:
                    if msg.type == 'set_tempo':
                        tempo = msg.tempo
                        break

            # 生成并保存 MIDI
            out_mid = notes_to_midi(connected, mid.ticks_per_beat, tempo)
            out_mid.save(self._output_path)

            self._log_info("")
            self._log_info("已保存到: %s" % self._output_path)
            self._log_info("完成!")

            self.status_var.set("处理完成! %d → %d 音符, 已保存" % (before_count, after_count))

        except Exception as e:
            self._log_info("处理出错: %s" % e)
            self.status_var.set("处理失败: %s" % e)

    # ======================== 线程管理 ========================

    def _poll_thread(self, thread, mode):
        if thread.is_alive():
            self.window.after(200, lambda: self._poll_thread(thread, mode))
        else:
            self._set_buttons(True)

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = MidiNoteConnectorGUI()
    app.run()
