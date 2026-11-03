"""Minimal native Windows desktop GUI using built-in Tkinter."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from .pipeline import process


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AVI Independent Auto Editor 0.3.4 Consolidated | Qwen + Whisper + CLIP')
        self.geometry('950x930')
        self.minsize(830, 790)
        self.running = False
        self.stop_flag = threading.Event()
        self.events = queue.Queue()
        self.source = tk.StringVar()
        self.audio = tk.StringVar()
        self.output = tk.StringVar()
        self.render = tk.BooleanVar(value=False)
        self.prefer_motion = tk.BooleanVar(value=True)
        self.ai_enabled = tk.BooleanVar(value=True)
        self.qwen_enabled = tk.BooleanVar(value=True)
        self.qwen_model = tk.StringVar(value='qwen3-vl:4b-instruct')
        self.qwen_samples = tk.StringVar(value='3')
        self.qwen_limit = tk.StringVar(value='10')
        self.whisper_model = tk.StringVar(value='small')
        self.ai_device = tk.StringVar(value='auto')
        self.language = tk.StringVar(value='en')
        self.tags_file = tk.StringVar(value='')
        self.review_threshold = tk.StringVar(value='0.21')
        self.resolution = tk.StringVar(value='1920x1080 (YouTube 16:9)')
        self.seed = tk.StringVar(value='404')
        self.threshold = tk.StringVar(value='0.42')
        self.intro = tk.StringVar(value='30')
        self.intro_min = tk.StringVar(value='1.2')
        self.intro_max = tk.StringVar(value='2.0')
        self.body_min = tk.StringVar(value='3.0')
        self.body_max = tk.StringVar(value='6.0')
        self.hardware_status = tk.StringVar(value='Dang quet phan cung...')
        self._draw()
        self._scan_hardware()
        self.after(80, self._poll)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _draw(self):
        self.configure(bg='#eef2f7')
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#eef2f7')
        style.configure('TLabel', background='#eef2f7', font=('Segoe UI', 10))
        style.configure('Title.TLabel', background='#eef2f7', foreground='#102a43',
                        font=('Segoe UI', 19, 'bold'))
        style.configure('Sub.TLabel', background='#eef2f7', foreground='#486581',
                        font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=7)
        style.configure('Accent.TButton', background='#1765c1', foreground='white',
                        font=('Segoe UI', 11, 'bold'), padding=9)
        style.configure('TCheckbutton', background='#eef2f7', font=('Segoe UI', 10))
        main = ttk.Frame(self, padding=(24, 16))
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='AVI  /  AUTO EDITOR', style='Title.TLabel').pack(anchor='w')
        ttk.Label(main, text='v0.3.4 — Qwen mô tả footage + Whisper đọc voice + CLIP matching',
                  style='Sub.TLabel').pack(anchor='w', pady=(0, 15))
        for title, value, folder in [
            ('Folder footage (video nguồn)', self.source, True),
            ('Audio thuyết minh (.mp3 / .wav / .m4a...)', self.audio, False),
            ('Folder xuất (rỗng)', self.output, True),
        ]:
            ttk.Label(main, text=title).pack(anchor='w', pady=(5, 4))
            row = ttk.Frame(main)
            row.pack(fill='x')
            ttk.Entry(row, textvariable=value).pack(side='left', fill='x', expand=True)
            ttk.Button(row, text='Chọn...', command=lambda v=value, f=folder: self._browse(v, f)).pack(side='left', padx=(8, 0))
        opts = ttk.LabelFrame(main, text='Thông số dựng', padding=10)
        opts.pack(fill='x', pady=(16, 6))
        row = ttk.Frame(opts)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text='Kích thước:').pack(side='left')
        ttk.Combobox(row, textvariable=self.resolution, state='readonly', width=30,
                     values=['1920x1080 (YouTube 16:9)', '1280x720 (Preview nhanh)',
                             '1080x1920 (Shorts 9:16)', '640x360 (Test)']).pack(side='left', padx=(7, 16))
        ttk.Label(row, text='Random seed:').pack(side='left')
        ttk.Entry(row, textvariable=self.seed, width=8).pack(side='left', padx=(8, 0))
        ttk.Label(row, text='Scene threshold:').pack(side='left', padx=(15, 0))
        ttk.Entry(row, textvariable=self.threshold, width=7).pack(side='left', padx=(8, 0))
        row2 = ttk.Frame(opts)
        row2.pack(fill='x', pady=(9, 4))
        for label, variable in [('Intro (s)', self.intro), ('Intro min', self.intro_min),
                                ('Intro max', self.intro_max), ('Body min', self.body_min),
                                ('Body max', self.body_max)]:
            ttk.Label(row2, text=label).pack(side='left')
            ttk.Entry(row2, textvariable=variable, width=5).pack(side='left', padx=(4, 12))
        ttk.Checkbutton(opts, text='Ưu tiên các cảnh có chuyển động', variable=self.prefer_motion).pack(anchor='w', pady=5)
        ttk.Checkbutton(opts, text='Render final.mp4 (có thể tốn nhiều thời gian)', variable=self.render).pack(anchor='w', pady=5)
        ai_frame = ttk.LabelFrame(main, text='Đồng bộ voice - footage bằng AI (offline sau khi tải model)', padding=10)
        ai_frame.pack(fill='x', pady=(7, 4))
        ttk.Checkbutton(ai_frame, text='Bật Whisper + CLIP (chạy thật, cần requirements-ai.txt)',
                        variable=self.ai_enabled).pack(anchor='w', pady=(1, 5))
        ar = ttk.Frame(ai_frame)
        ar.pack(fill='x', pady=3)
        ttk.Label(ar, text='Whisper:').pack(side='left')
        ttk.Combobox(ar, textvariable=self.whisper_model, width=9, state='readonly',
                     values=['tiny', 'base', 'small', 'medium', 'large-v3']).pack(side='left', padx=(5, 16))
        ttk.Label(ar, text='Thiết bị AI:').pack(side='left')
        ttk.Combobox(ar, textvariable=self.ai_device, width=8, state='readonly',
                     values=['auto', 'cuda', 'cpu']).pack(side='left', padx=(5, 15))
        ttk.Label(ar, text='Language:').pack(side='left')
        ttk.Combobox(ar, textvariable=self.language, width=7, state='readonly',
                     values=['en', 'vi', 'auto']).pack(side='left', padx=(5, 15))
        ttk.Label(ar, text='Ngưỡng review:').pack(side='left')
        ttk.Entry(ar, textvariable=self.review_threshold, width=6).pack(side='left', padx=(5, 0))
        qr = ttk.Frame(ai_frame)
        qr.pack(fill='x', pady=(5, 3))
        ttk.Checkbutton(qr, text='Qwen mô tả mọi cảnh (cần Ollama)', variable=self.qwen_enabled).pack(side='left')
        ttk.Label(qr, text='Model:').pack(side='left', padx=(13, 4))
        ttk.Combobox(qr, textvariable=self.qwen_model, width=23,
                     values=['qwen3-vl:2b-instruct', 'qwen3-vl:4b-instruct', 'qwen3-vl:8b-instruct']).pack(side='left')
        ttk.Label(qr, text='Frames/cảnh:').pack(side='left', padx=(9, 5))
        ttk.Combobox(qr, textvariable=self.qwen_samples, width=3, state='readonly',
                     values=['1', '2', '3', '4', '5']).pack(side='left')
        sr = ttk.Frame(ai_frame)
        sr.pack(fill='x', pady=(4, 2))
        ttk.Label(sr, text='Test nhanh:').pack(side='left')
        ttk.Entry(sr, textvariable=self.qwen_limit, width=6).pack(side='left', padx=(6, 8))
        ttk.Label(sr, text='cảnh (để trống = toàn bộ)').pack(side='left')
        ttk.Button(sr, text='QUÉT FOOTAGE BẰNG QWEN (chưa dựng)',
                   command=self._scan_qwen).pack(side='left', padx=12)
        hr = ttk.Frame(ai_frame)
        hr.pack(fill='x', pady=4)
        ttk.Label(hr, textvariable=self.hardware_status, style='Sub.TLabel').pack(side='left', fill='x', expand=True)
        ttk.Button(hr, text='Quet lai GPU', command=self._scan_hardware).pack(side='right')
        tr = ttk.Frame(ai_frame)
        tr.pack(fill='x', pady=(6, 0))
        ttk.Label(tr, text='CSV nhãn nhân vật (nếu có):').pack(side='left')
        ttk.Entry(tr, textvariable=self.tags_file).pack(side='left', fill='x', expand=True, padx=(8, 6))
        ttk.Button(tr, text='Chọn CSV...', command=lambda: self._browse_csv()).pack(side='left')
        actions = ttk.Frame(main)
        actions.pack(fill='x', pady=(11, 8))
        self.run_button = ttk.Button(actions, text='▶ BẮT ĐẦU AUTO EDIT', style='Accent.TButton', command=self._start)
        self.run_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='DỪNG', command=self._stop, state='disabled')
        self.stop_button.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(actions, maximum=100, mode='determinate')
        self.progress.pack(side='left', fill='x', expand=True, padx=(8, 0))
        ttk.Label(main, text='Nhật ký xử lý').pack(anchor='w', pady=(10, 5))
        frame = ttk.Frame(main)
        frame.pack(fill='both', expand=True)
        self.logs = tk.Text(frame, font=('Consolas', 9), bg='#152234', fg='#dce6f0',
                            insertbackground='white', height=12, relief='flat', state='disabled', wrap='word')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.logs.yview)
        self.logs.config(yscrollcommand=scrollbar.set)
        self.logs.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        ttk.Label(main, text='Qwen không xác nhận danh tính; dùng CSV nhãn người để giảm nhầm. XML tham chiếu media gốc.',
                  style='Sub.TLabel').pack(anchor='w', pady=(8, 0))

    def _scan_hardware(self):
        self.hardware_status.set('Dang quet GPU, PyTorch va CTranslate2...')
        def worker():
            try:
                from .hardware import probe_cuda, describe_hardware
                result = probe_cuda()
                self.events.put(('hardware', describe_hardware(result)))
                for note in result['notes']:
                    self.events.put(('log', '[GPU] ' + note))
            except Exception as e:
                self.events.put(('hardware', 'Khong quet duoc: ' + str(e)[:150]))
        threading.Thread(target=worker, daemon=True).start()

    def _browse_csv(self):
        chosen = filedialog.askopenfilename(title='Chọn footage_tags.csv',
                                             filetypes=[('CSV', '*.csv'), ('All files', '*.*')])
        if chosen:
            self.tags_file.set(chosen)

    def _browse(self, variable, folder):
        if folder:
            chosen = filedialog.askdirectory(title='Chọn thư mục', mustexist=False)
        else:
            chosen = filedialog.askopenfilename(title='Chọn narration', filetypes=[
                ('Audio', '*.mp3 *.wav *.m4a *.flac *.ogg *.aac'), ('All files', '*.*')])
        if chosen:
            variable.set(chosen)

    def _start(self):
        if self.running:
            return
        try:
            if not self.source.get() or not self.audio.get() or not self.output.get():
                raise ValueError('Hãy chọn đủ Folder footage, Audio, Folder xuất.')
            width, height = map(int, self.resolution.get().split()[0].split('x'))
            kwargs = dict(source_dir=self.source.get().strip(), narration_path=self.audio.get().strip(),
                          output_dir=self.output.get().strip(), render=self.render.get(),
                          seed=int(self.seed.get()), threshold=float(self.threshold.get()),
                          intro_seconds=float(self.intro.get()),
                          intro_min=float(self.intro_min.get()), intro_max=float(self.intro_max.get()),
                          body_min=float(self.body_min.get()), body_max=float(self.body_max.get()),
                          width=width, height=height, prefer_moving=self.prefer_motion.get(),
                          ai_enabled=self.ai_enabled.get(), whisper_model=self.whisper_model.get(),
                          ai_device=self.ai_device.get(), language=self.language.get(),
                          review_threshold=float(self.review_threshold.get()),
                          tags_file=self.tags_file.get().strip() or None,
                          qwen_enabled=self.qwen_enabled.get(),
                          qwen_model=self.qwen_model.get().strip(),
                          qwen_samples=int(self.qwen_samples.get()))
        except Exception as e:
            messagebox.showerror('Thiếu hoặc sai thông số', str(e))
            return
        self.running = True
        self.stop_flag.clear()
        self.progress['value'] = 0
        self.run_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self._log('--- BẮT ĐẦU ---')
        def work():
            try:
                plan = process(**kwargs, stop=self.stop_flag,
                               log=lambda s: self.events.put(('log', s)),
                               progress=lambda x: self.events.put(('progress', round(x*100, 1))))
                self.events.put(('success', f"Hoàn thành {plan['stats']['shot_count']} shot.\nKết quả: {kwargs['output_dir']}"))
            except InterruptedError as e:
                self.events.put(('stopped', str(e)))
            except Exception as e:
                self.events.put(('error', str(e)))
            finally:
                self.events.put(('finished', None))
        threading.Thread(target=work, daemon=True).start()

    def _scan_qwen(self):
        if self.running:
            return
        try:
            if not self.source.get() or not self.output.get():
                raise ValueError('Cần chọn thư mục footage và thư mục báo cáo.')
            n = int(self.qwen_limit.get()) if self.qwen_limit.get().strip() else None
            if n is not None and n < 1:
                raise ValueError('Số cảnh test phải lớn hơn 0 hoặc để trống.')
            kwargs = dict(source_dir=self.source.get().strip(), output_dir=self.output.get().strip(),
                          qwen_model=self.qwen_model.get().strip(), qwen_samples=int(self.qwen_samples.get()),
                          limit=n, threshold=float(self.threshold.get()))
        except Exception as exc:
            messagebox.showerror('Sai thông số', str(exc))
            return
        self.running = True
        self.stop_flag.clear()
        self.run_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.progress['value'] = 0
        self._log('--- QUÉT THƯ VIỆN QWEN ---')
        def work():
            try:
                from .pipeline import scan_footage
                rows = scan_footage(**kwargs, stop=self.stop_flag,
                                    log=lambda s: self.events.put(('log', s)),
                                    progress=lambda x: self.events.put(('progress', round(x * 100, 1))))
                self.events.put(('success', f'Đã mô tả {len(rows)} cảnh. Xem footage_catalog.csv trong folder xuất.'))
            except InterruptedError as exc:
                self.events.put(('stopped', str(exc)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('finished', None))
        threading.Thread(target=work, daemon=True).start()

    def _stop(self):
        self.stop_flag.set()
        self._log('Đang yêu cầu dừng...')
        self.stop_button.config(state='disabled')

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'hardware':
                    self.hardware_status.set(value)
                elif kind == 'log':
                    self._log(value)
                elif kind == 'progress':
                    self.progress['value'] = value
                elif kind == 'success':
                    self._log('✓ ' + value)
                    messagebox.showinfo('Hoàn thành', value)
                elif kind == 'error':
                    self._log('LỖI: ' + value)
                    messagebox.showerror('Lỗi xử lý', value)
                elif kind == 'stopped':
                    self._log('ĐÃ DỪNG: ' + value)
                elif kind == 'finished':
                    self.running = False
                    self.run_button.config(state='normal')
                    self.stop_button.config(state='disabled')
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _log(self, message):
        self.logs.config(state='normal')
        self.logs.insert('end', str(message) + '\n')
        self.logs.see('end')
        self.logs.config(state='disabled')

    def _close(self):
        if self.running:
            if not messagebox.askyesno('Đang xử lý', 'Dừng tác vụ và đóng phần mềm?'):
                return
            self.stop_flag.set()
        self.destroy()


def start_gui():
    MainWindow().mainloop()
