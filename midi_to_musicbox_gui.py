#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI → 八音盒乐谱 JSON 转换工具 (GUI 版)

依赖:
    pip install mido

用法:
    python midi_to_musicbox_gui.py
"""

import json
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


# MIDI 音符 → keyIndex 映射表（仅白键 C4-B6）
MIDI_TO_KEY_INDEX = {
    60: 14, 62: 15, 64: 16, 65: 17, 67: 18, 69: 19, 71: 20,
    72: 7,  74: 8,  76: 9,  77: 10, 79: 11, 81: 12, 83: 13,
    84: 0,  86: 1,  88: 2,  89: 3,  91: 4,  93: 5,  95: 6,
}
WHITE_NOTES = set(MIDI_TO_KEY_INDEX.keys())

NOTE_NAMES = {
    60: "C4", 62: "D4", 64: "E4", 65: "F4", 67: "G4", 69: "A4", 71: "B4",
    72: "C5", 74: "D5", 76: "E5", 77: "F5", 79: "G5", 81: "A5", 83: "B5",
    84: "C6", 86: "D6", 88: "E6", 89: "F6", 91: "G6", 93: "A6", 95: "B6",
}


class MidiToMusicBoxGUI:

    def __init__(self):
        self.window = tk.Tk()
        self.window.title("MIDI → 八音盒乐谱转换器")
        self.window.geometry("700x600")
        self.window.resizable(False, False)

        self.midi_path = None
        self.result = None
        self.compact_json = ""

        self._build_ui()

    def _build_ui(self):
        # ====== 文件选择区域 ======
        file_frame = ttk.LabelFrame(self.window, text="选择 MIDI 文件", padding=10)
        file_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(file_frame, text="浏览...", command=self._select_file).pack(side="right")

        # ====== 信息区域 ======
        info_frame = ttk.LabelFrame(self.window, text="转换信息", padding=10)
        info_frame.pack(fill="x", padx=10, pady=10)

        self.info_text = tk.Text(info_frame, height=8, width=80, state="disabled",
                                 font=("Consolas", 9), bg="#f5f5f5")
        self.info_text.pack(fill="x")

        # ====== 操作按钮 ======
        btn_frame = ttk.Frame(self.window, padding=5)
        btn_frame.pack(fill="x", padx=10)

        self.convert_btn = ttk.Button(btn_frame, text="开始转换", command=self._convert,
                                      state="disabled")
        self.convert_btn.pack(side="left", padx=2)

        self.copy_btn = ttk.Button(btn_frame, text="复制到剪贴板", command=self._copy_to_clipboard,
                                   state="disabled")
        self.copy_btn.pack(side="left", padx=2)

        self.save_btn = ttk.Button(btn_frame, text="保存为 JSON 文件...", command=self._save_file,
                                   state="disabled")
        self.save_btn.pack(side="left", padx=2)

        self.import_guide_btn = ttk.Button(btn_frame, text="游戏导入说明", command=self._show_guide)
        self.import_guide_btn.pack(side="right", padx=2)

        # ====== 预览区域 ======
        preview_frame = ttk.LabelFrame(self.window, text="乐谱 JSON 预览", padding=10)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.preview_text = tk.Text(preview_frame, height=20, width=80, state="disabled",
                                    font=("Consolas", 9), wrap="none")
        self.preview_text.pack(fill="both", expand=True)

        # ====== 状态栏 ======
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.window, textvariable=self.status_var, relief="sunken",
                               anchor="w", padding=5)
        status_bar.pack(fill="x", padx=10, pady=(0, 10))

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="选择 MIDI 文件",
            filetypes=[("MIDI 文件", "*.mid *.midi"), ("所有文件", "*.*")]
        )
        if path:
            self.midi_path = path
            self.file_path_var.set(path)
            self.convert_btn.config(state="normal")
            self.status_var.set("已选择文件: %s" % os.path.basename(path))

    def _log_info(self, text):
        self.info_text.config(state="normal")
        self.info_text.insert("end", text + "\n")
        self.info_text.see("end")
        self.info_text.config(state="disabled")
        self.window.update_idletasks()

    def _set_preview(self, text):
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.config(state="disabled")

    def _convert_thread(self):
        try:
            self._log_info("正在解析 MIDI 文件...")
            self._log_info("曲名: %s" % os.path.splitext(os.path.basename(self.midi_path))[0])

            mid = mido.MidiFile(self.midi_path)

            # 获取 BPM
            bpm = 120
            for track in mid.tracks:
                for msg in track:
                    if msg.type == 'set_tempo':
                        bpm = mido.tempo2bpm(msg.tempo)
                        break
            self._log_info("BPM: %d" % bpm)
            self._log_info("MIDI 精度: %d ticks/拍" % mid.ticks_per_beat)

            # 收集音符事件
            note_events = {}
            ongoing = {}
            total = 0
            skipped_black = 0
            skipped_range = 0

            for track in mid.tracks:
                abs_tick = 0
                for msg in track:
                    abs_tick += msg.time
                    total += 1

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

            # 关闭未关闭的音符
            for note, (start_tick, velocity) in ongoing.items():
                if note not in note_events:
                    note_events[note] = []
                note_events[note].append((start_tick, start_tick + mid.ticks_per_beat * 2, velocity))

            # 展开所有音符
            all_notes = []
            for note, events in note_events.items():
                for start_tick, end_tick, velocity in events:
                    all_notes.append((note, start_tick, end_tick, velocity))

            self._log_info("MIDI 消息总数: %d" % total)
            self._log_info("跳过黑键: %d | 跳过范围外: %d" % (skipped_black, skipped_range))
            self._log_info("有效白键音符: %d" % len(all_notes))

            if not all_notes:
                self._log_info("错误: 没有找到可转换的音符!")
                self._log_info("提示: 音频范围必须在 C4(60)~B6(95) 的白键内")
                self.status_var.set("转换失败: 没有有效音符")
                return

            min_tick = min(n[1] for n in all_notes)
            ms_per_tick = 60000.0 / bpm / mid.ticks_per_beat

            notes_output = []
            note_details = []
            for note, start_tick, end_tick, velocity in all_notes:
                key_index = MIDI_TO_KEY_INDEX[note]
                start_ms = int((start_tick - min_tick) * ms_per_tick)
                duration_ms = max(100, int((end_tick - start_tick) * ms_per_tick))
                vol = max(0.3, min(1.0, velocity / 127.0))
                notes_output.append([key_index, start_ms, duration_ms, round(vol, 2)])
                note_details.append("%s(idx=%d) @%dms dur=%dms vol=%.1f" % (
                    NOTE_NAMES.get(note, "?"), key_index, start_ms, duration_ms, vol))

            notes_output.sort(key=lambda x: (x[1], x[0]))

            total_ms = max(n[1] + n[2] for n in notes_output) if notes_output else 0
            self._log_info("输出音符: %d 个" % len(notes_output))
            self._log_info("总时长: %.1f 秒" % (total_ms / 1000.0))
            self._log_info("")

            # 显示前 10 个音符详情
            self._log_info("前 %d 个音符:" % min(10, len(note_details)))
            for d in note_details[:10]:
                self._log_info("  " + d)
            if len(note_details) > 10:
                self._log_info("  ... 共 %d 个" % len(note_details))

            # 构建结果（v2 毫秒格式）
            song_name = os.path.splitext(os.path.basename(self.midi_path))[0]
            self.result = {
                "v": 2,
                "n": song_name,
                "t": notes_output,
            }
            self.compact_json = json.dumps(self.result, ensure_ascii=False, separators=(",", ":"))
            pretty_json = json.dumps(self.result, ensure_ascii=False, indent=2, sort_keys=False)

            self._set_preview(pretty_json)
            self.copy_btn.config(state="normal")
            self.save_btn.config(state="normal")
            self.status_var.set("转换完成! (%d 个音符, 约 %.1f 秒)" % (len(notes_output), duration_seconds))

        except Exception as e:
            self._log_info("转换出错: %s" % e)
            self.status_var.set("转换失败: %s" % e)

    def _convert(self):
        if not self.midi_path:
            return
        self._log_info("=" * 40)
        self._log_info("开始转换...")
        self.convert_btn.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self._set_preview("")
        self.status_var.set("正在转换...")

        t = threading.Thread(target=self._convert_thread, daemon=True)
        t.start()

        # 轮询等待完成
        self._poll_thread(t)

    def _poll_thread(self, thread):
        if thread.is_alive():
            self.window.after(200, lambda: self._poll_thread(thread))
        else:
            self.convert_btn.config(state="normal")

    def _copy_to_clipboard(self):
        if not self.compact_json:
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(self.compact_json)
        self.status_var.set("已复制到剪贴板! 可以进游戏导入乐谱了")

    def _save_file(self):
        if not self.result:
            return
        default_name = os.path.splitext(os.path.basename(self.midi_path))[0] + "_musicbox.json"
        path = filedialog.asksaveasfilename(
            title="保存乐谱 JSON",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.result, f, ensure_ascii=False, indent=2, sort_keys=False)
            self.status_var.set("已保存到: %s" % path)

    def _show_guide(self):
        guide = (
            "游戏导入步骤:\n\n"
            "1. 点击「开始转换」转换 MIDI 文件\n"
            "2. 点击「复制到剪贴板」\n"
            "3. 进入游戏，手持「空白乐谱」\n"
            "4. 右键「八音盒」打开界面\n"
            "5. 点击「导入乐谱」按钮\n"
            "6. 空白乐谱会变成「自定义乐谱」\n"
            "7. 点击「开始播放」试听！\n\n"
            "提示:\n"
            "- 乐谱数据同时支持导出分享（导出按钮）\n"
            "- 仅支持 C4-B6 范围内的白键音符\n"
            "- 黑键和超出范围的音符会被自动跳过"
        )
        messagebox.showinfo("游戏导入说明", guide, parent=self.window)

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = MidiToMusicBoxGUI()
    app.run()
