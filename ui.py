import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import concurrent.futures
import numpy as np
from datetime import datetime

import audio_capture as ac
import vad as vad_module
import transcriber
import speaker_id
import db_manager
import excel_writer

SAMPLE_RATE = 16000

# 信号レベルメーターのバー数
METER_BARS = 12


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("トランシーバ記録システム")
        self.root.geometry("700x640")
        self.root.resizable(True, True)

        self.is_recording = False
        self.is_db_recording = False
        self._result_queue: queue.Queue = queue.Queue()
        self._utterance_queue: queue.Queue = queue.Queue()

        self._pending_speaker = "不明"
        self._pending_timestamp = ""

        self._current_samples: list[tuple[np.ndarray, str]] = []
        self._db_capturer: ac.AudioCapture | None = None
        self._db_audio_buf: list[np.ndarray] = []

        self._capturer: ac.AudioCapture | None = None
        self._detector: vad_module.PTTDetector | vad_module.VAD | None = None
        self._vad_thread: threading.Thread | None = None

        self._device_options: list[tuple[int | None, str]] = []
        self._device_var = tk.StringVar()
        self._detect_mode = tk.StringVar(value="ptt")   # "ptt" or "vad"
        self._ptt_threshold_var = tk.StringVar(value="0.002")

        self._build_device_selector()
        self._build_ui()
        self._start_process_worker()
        self._poll_queue()

    # ─────────────────────────────── UI構築

    def _build_device_selector(self):
        import sounddevice as sd

        row = tk.Frame(self.root)
        row.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(row, text="入力デバイス：").pack(side="left")

        self._device_options = [(None, "デフォルト（システム設定に従う）")]
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                self._device_options.append((i, f"{i}: {d['name']}"))

        labels = [lbl for _, lbl in self._device_options]
        self._device_var.set(labels[0])

        ttk.Combobox(
            row, textvariable=self._device_var,
            values=labels, state="readonly", width=42
        ).pack(side="left", padx=6)

    def _get_selected_device(self) -> int | None:
        label = self._device_var.get()
        for idx, lbl in self._device_options:
            if lbl == label:
                return idx
        return None

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_db = ttk.Frame(notebook)
        notebook.add(self._tab_db, text="DB作成")
        self._build_db_tab()

        self._tab_rec = ttk.Frame(notebook)
        notebook.add(self._tab_rec, text="記録・出力")
        self._build_rec_tab()

    def _build_db_tab(self):
        f = self._tab_db

        row = tk.Frame(f)
        row.pack(fill="x", padx=10, pady=(12, 4))
        tk.Label(row, text="名前：").pack(side="left")
        self._db_name_var = tk.StringVar()
        tk.Entry(row, textvariable=self._db_name_var, width=28).pack(side="left", padx=6)

        row2 = tk.Frame(f)
        row2.pack(fill="x", padx=10, pady=4)
        self._btn_db_start = tk.Button(
            row2, text="録音開始", width=10, bg="#d2e6ff",
            command=self._db_start_recording
        )
        self._btn_db_start.pack(side="left", padx=4)
        self._btn_db_stop = tk.Button(
            row2, text="録音停止", width=10, bg="#e1e1e1",
            state="disabled", command=self._db_stop_recording
        )
        self._btn_db_stop.pack(side="left", padx=4)

        tk.Label(f, text="登録済みサンプル：", anchor="w").pack(fill="x", padx=10, pady=(6, 2))

        list_frame = tk.Frame(f)
        list_frame.pack(fill="both", expand=True, padx=10)
        sb = tk.Scrollbar(list_frame, orient="vertical")
        self._sample_lb = tk.Listbox(list_frame, height=7, yscrollcommand=sb.set)
        sb.config(command=self._sample_lb.yview)
        self._sample_lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tk.Button(f, text="削除", command=self._db_delete_sample).pack(anchor="e", padx=10)
        tk.Button(
            f, text="DBに保存", width=14, bg="#c8f0d8",
            font=("", 11, "bold"), command=self._db_save
        ).pack(pady=10)
        tk.Label(f, text="※ 名前ごとに手順を繰り返す", fg="gray").pack()

    def _build_rec_tab(self):
        f = self._tab_rec

        # ファイル選択
        row = tk.Frame(f)
        row.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(row, text="出力先：").pack(side="left")
        self._excel_path_var = tk.StringVar()
        tk.Entry(row, textvariable=self._excel_path_var, width=32).pack(side="left", padx=6)
        tk.Button(row, text="参照...", command=self._pick_excel).pack(side="left")

        # 検出設定フレーム
        det_frame = ttk.LabelFrame(f, text="検出設定")
        det_frame.pack(fill="x", padx=10, pady=(4, 4))

        # 検出モード
        mode_row = tk.Frame(det_frame)
        mode_row.pack(fill="x", padx=6, pady=(4, 2))
        tk.Label(mode_row, text="検出方式：").pack(side="left")
        tk.Radiobutton(
            mode_row, text="PTT信号（有線接続）",
            variable=self._detect_mode, value="ptt",
            command=self._on_mode_change
        ).pack(side="left", padx=4)
        tk.Radiobutton(
            mode_row, text="VAD（マイク/デバッグ）",
            variable=self._detect_mode, value="vad",
            command=self._on_mode_change
        ).pack(side="left", padx=4)

        # PTT閾値 + レベルメーター
        thr_row = tk.Frame(det_frame)
        thr_row.pack(fill="x", padx=6, pady=(2, 6))
        tk.Label(thr_row, text="PTT閾値：").pack(side="left")
        self._ptt_thr_entry = tk.Entry(
            thr_row, textvariable=self._ptt_threshold_var, width=7
        )
        self._ptt_thr_entry.pack(side="left", padx=(0, 10))

        tk.Label(thr_row, text="信号レベル：").pack(side="left")
        self._level_label = tk.Label(
            thr_row, text="─" * METER_BARS,
            font=("Courier", 11), fg="gray", width=METER_BARS + 2
        )
        self._level_label.pack(side="left")
        self._ptt_state_label = tk.Label(thr_row, text="", width=10)
        self._ptt_state_label.pack(side="left", padx=4)

        # 開始・停止ボタン
        row2 = tk.Frame(f)
        row2.pack(fill="x", padx=10, pady=4)
        self._btn_rec_start = tk.Button(
            row2, text="記録開始", width=10, bg="#aadcb4",
            font=("", 10, "bold"), command=self._rec_start
        )
        self._btn_rec_start.pack(side="left", padx=4)
        self._btn_rec_stop = tk.Button(
            row2, text="記録停止", width=10, bg="#e1e1e1",
            state="disabled", command=self._rec_stop
        )
        self._btn_rec_stop.pack(side="left", padx=4)

        # ステータスバー
        self._status_var = tk.StringVar(value="● 待機中")
        tk.Label(
            f, textvariable=self._status_var,
            bg="#d2e6fa", anchor="w", padx=10, pady=4
        ).pack(fill="x")

        # 直前の記録
        tk.Label(f, text="直前の記録（修正可）：", anchor="w").pack(fill="x", padx=10, pady=(6, 2))
        self._edit_text = tk.Text(f, height=3, wrap="word")
        self._edit_text.pack(fill="x", padx=10)

        fix_row = tk.Frame(f)
        fix_row.pack(fill="x", padx=10, pady=(2, 4))
        self._btn_fix = tk.Button(
            fix_row, text="直前を修正・再出力", bg="#ffe0b2",
            state="disabled", command=self._fix_last
        )
        self._btn_fix.pack(side="right")

        # ログ
        ttk.Separator(f, orient="horizontal").pack(fill="x", padx=6, pady=4)
        tk.Label(f, text="出力済みログ：", anchor="w").pack(fill="x", padx=10)

        log_frame = tk.Frame(f)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        log_scroll = tk.Scrollbar(log_frame, orient="vertical")
        self._log_text = tk.Text(
            log_frame, height=6, state="disabled",
            wrap="word", bg="#f8f8f8",
            yscrollcommand=log_scroll.set
        )
        log_scroll.config(command=self._log_text.yview)
        self._log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _on_mode_change(self):
        mode = self._detect_mode.get()
        state = "normal" if mode == "ptt" else "disabled"
        self._ptt_thr_entry.config(state=state)

    # ─────────────────────────────── DBタブ操作

    def _db_start_recording(self):
        name = self._db_name_var.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "名前を入力してください")
            return

        self._db_audio_buf = []
        self.is_db_recording = True
        self._db_capturer = ac.AudioCapture(device=self._get_selected_device())
        self._db_capturer.start()
        self._btn_db_start.config(state="disabled")
        self._btn_db_stop.config(state="normal")
        threading.Thread(target=self._db_accumulate, daemon=True).start()

    def _db_accumulate(self):
        import time
        while self.is_db_recording:
            chunk = self._db_capturer.get_chunk()
            if chunk is not None:
                self._db_audio_buf.append(chunk)
            else:
                time.sleep(0.005)

    def _db_stop_recording(self):
        self.is_db_recording = False
        if self._db_capturer:
            self._db_capturer.stop()
        self._btn_db_start.config(state="normal")
        self._btn_db_stop.config(state="disabled")

        if not self._db_audio_buf:
            return
        audio = np.concatenate(self._db_audio_buf)
        duration = len(audio) / SAMPLE_RATE
        name = self._db_name_var.get().strip()
        label = f"{name}：{duration:.1f}秒"
        self._current_samples.append((audio, label))
        self._sample_lb.insert("end", label)

    def _db_delete_sample(self):
        sel = self._sample_lb.curselection()
        if not sel:
            return
        del self._current_samples[sel[0]]
        self._sample_lb.delete(0, "end")
        for _, label in self._current_samples:
            self._sample_lb.insert("end", label)

    def _db_save(self):
        name = self._db_name_var.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "名前を入力してください")
            return
        if not self._current_samples:
            messagebox.showwarning("サンプルなし", "録音サンプルがありません")
            return

        def worker():
            try:
                embeddings = [speaker_id.get_embedding(a) for a, _ in self._current_samples]
                db_manager.add_speaker(name, embeddings)
                self.root.after(0, lambda: messagebox.showinfo("保存完了", f"「{name}」の声紋を保存しました"))
                self.root.after(0, self._db_reset)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("エラー", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _db_reset(self):
        self._current_samples = []
        self._sample_lb.delete(0, "end")
        self._db_name_var.set("")

    # ─────────────────────────────── 記録タブ操作

    def _pick_excel(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel ファイル", "*.xlsx *.xls"), ("すべて", "*.*")]
        )
        if path:
            self._excel_path_var.set(path)
            excel_writer.set_target(path)

    def _rec_start(self):
        if not self._excel_path_var.get():
            messagebox.showwarning("未設定", "出力先Excelファイルを指定してください")
            return

        excel_writer.set_target(self._excel_path_var.get())
        self.is_recording = True

        self._capturer = ac.AudioCapture(device=self._get_selected_device())

        mode = self._detect_mode.get()
        if mode == "ptt":
            try:
                thr = float(self._ptt_threshold_var.get())
            except ValueError:
                thr = 0.002
            self._detector = vad_module.PTTDetector(energy_threshold=thr)
        else:
            self._detector = vad_module.VAD()

        self._capturer.start()
        self._btn_rec_start.config(state="disabled")
        self._btn_rec_stop.config(state="normal")
        self._status_var.set("● 待受中　─　発言を検出したら自動で記録します")

        self._vad_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._vad_thread.start()

    def _rec_stop(self):
        self.is_recording = False
        if self._capturer:
            self._capturer.stop()
        if self._detector:
            self._detector.reset()

        self._btn_rec_start.config(state="normal")
        self._btn_rec_stop.config(state="disabled")
        self._status_var.set("● 待機中")
        self._update_level_meter(0.0, ptt_active=False)

    def _detect_loop(self):
        import time
        while self.is_recording:
            chunk = self._capturer.get_chunk()
            if chunk is not None:
                segment, level = self._detector.process(chunk)
                ptt = self._detector.is_ptt_active
                # レベルメーター更新はUIスレッドへ（100msに1回で十分）
                self._result_queue.put({"type": "level", "level": level, "ptt": ptt})
                if segment is not None:
                    self._utterance_queue.put(segment.copy())
            else:
                time.sleep(0.005)

    # ─────────────────────────────── 処理ワーカー（常時稼働・並列処理）

    def _start_process_worker(self):
        threading.Thread(target=self._process_worker, daemon=True).start()

    def _process_worker(self):
        while True:
            audio = self._utterance_queue.get()
            if audio is None:
                break
            try:
                self._result_queue.put({"type": "status", "text": "⏳ 解析中..."})

                # speaker IDとWhisperを並列実行
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                    f_spk = ex.submit(speaker_id.identify, audio)
                    f_txt = ex.submit(transcriber.transcribe, audio)
                    spk, sim = f_spk.result()
                    text = f_txt.result()

                ts = datetime.now().strftime("%H:%M:%S")
                self._result_queue.put({
                    "type": "result",
                    "speaker": spk,
                    "similarity": sim,
                    "text": text,
                    "timestamp": ts,
                })
            except Exception as e:
                self._result_queue.put({"type": "error", "message": str(e)})

    # ─────────────────────────────── キューポーリング

    def _poll_queue(self):
        # レベルメーターは最新値のみ使う（連続して積まれても最後だけ反映）
        latest_level = None
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item["type"] == "level":
                    latest_level = item
                elif item["type"] == "status":
                    self._status_var.set(f"● 待受中　{item['text']}")
                elif item["type"] == "result":
                    self._auto_output(item)
                elif item["type"] == "error":
                    self._status_var.set(f"エラー: {item['message']}")
        except queue.Empty:
            pass

        if latest_level is not None:
            self._update_level_meter(latest_level["level"], latest_level["ptt"])

        self.root.after(80, self._poll_queue)

    def _update_level_meter(self, rms: float, ptt_active: bool):
        try:
            thr = float(self._ptt_threshold_var.get())
        except ValueError:
            thr = 0.002

        # 0〜0.1 を METER_BARS本のバーにマッピング
        filled = min(METER_BARS, int(rms / 0.1 * METER_BARS))
        bar = "█" * filled + "─" * (METER_BARS - filled)

        if ptt_active:
            self._level_label.config(text=bar, fg="red")
            self._ptt_state_label.config(text="🔴 送信中", fg="red")
        elif rms > thr:
            self._level_label.config(text=bar, fg="orange")
            self._ptt_state_label.config(text="", fg="black")
        else:
            self._level_label.config(text=bar, fg="gray")
            self._ptt_state_label.config(text="", fg="black")

    # ─────────────────────────────── Excel出力

    def _auto_output(self, item: dict):
        spk = item["speaker"]
        text = item["text"]
        ts = item["timestamp"]
        sim_pct = int(item["similarity"] * 100)

        try:
            excel_writer.append_row(speaker=spk, text=text)
        except Exception as e:
            self._status_var.set(f"Excel書き込みエラー: {e}")
            return

        self._status_var.set(
            f"● 待受中　{ts}　{spk}（{sim_pct}%）→ 書き込み済"
        )

        self._edit_text.delete("1.0", "end")
        self._edit_text.insert("1.0", text)
        self._pending_speaker = spk
        self._pending_timestamp = ts
        self._btn_fix.config(state="normal")

        entry = f"{ts}　{spk}　{text}\n"
        self._log_text.config(state="normal")
        self._log_text.insert("end", entry)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _fix_last(self):
        text = self._edit_text.get("1.0", "end").strip()
        if not text:
            return
        try:
            excel_writer.update_last_row(speaker=self._pending_speaker, text=text)
        except Exception as e:
            messagebox.showerror("修正エラー", str(e))
            return

        self._log_text.config(state="normal")
        content = self._log_text.get("1.0", "end")
        lines = [l for l in content.split("\n") if l.strip()]
        if lines:
            lines[-1] = f"{self._pending_timestamp}　{self._pending_speaker}　{text}（修正済）"
        self._log_text.delete("1.0", "end")
        self._log_text.insert("1.0", "\n".join(lines) + "\n")
        self._log_text.see("end")
        self._log_text.config(state="disabled")
        self._btn_fix.config(state="disabled")
