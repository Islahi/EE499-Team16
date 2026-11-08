"""Small standalone desktop front-end for the GoiEner three-sector cleaner."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from goiener_prepare import prepare


class CleanerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GoiEner | Three-Sector Load Preparer")
        self.geometry("950x570")
        self.minsize(780, 500)
        self.jobs = queue.Queue()
        self.v_meta = tk.StringVar(value=str(Path.home() / 'Downloads' / 'GoiEner_Multiyear_Download_Extractor' / 'goiener_original' / 'metadata.csv'))
        self.v_arch = tk.StringVar(value=str(Path.home() / 'Downloads' / 'GoiEner_Multiyear_Download_Extractor' / 'goiener_original' / 'imp-pre.tzst'))
        self.v_out = tk.StringVar(value=str(Path.home() / 'Downloads' / 'GoiEner_cleaned_profiles'))
        self.v_proxy = tk.BooleanVar(value=False)
        self.v_wide = tk.StringVar(value='average')
        ttk.Label(self, text='Prepare 3 Multi-year Load Profiles', font=('Segoe UI', 16, 'bold')).pack(anchor='w', padx=18, pady=(16, 6))
        ttk.Label(self, text='No date filter or customer-count cap. Original source files remain untouched.').pack(anchor='w', padx=18)
        form = ttk.Frame(self, padding=16)
        form.pack(fill='x')
        self._path(form, 'GoiEner customer metadata.csv', self.v_meta, 0, is_dir=False)
        self._path(form, 'GoiEner imp-pre.tzst archive', self.v_arch, 1, is_dir=False)
        self._path(form, 'Output folder', self.v_out, 2, is_dir=True)
        settings = ttk.Frame(self, padding=(18, 0, 18, 10))
        settings.pack(fill='x')
        ttk.Checkbutton(settings, text='Include unclassified 2.x-tariff meters as residential proxies (UNVERIFIED)', variable=self.v_proxy).pack(anchor='w', pady=5)
        row = ttk.Frame(settings)
        row.pack(anchor='w', pady=(5, 0))
        ttk.Label(row, text='Profile value sent to distribution GUI:').pack(side='left')
        ttk.Combobox(row, textvariable=self.v_wide, values=('average', 'sum'), state='readonly', width=15).pack(side='left', padx=10)
        ttk.Label(row, text='Average reduces false jumps when customer participation changes.').pack(side='left')
        self.btn = ttk.Button(self, text='Clean and Aggregate Full Archive', command=self.launch)
        self.btn.pack(anchor='w', padx=18, pady=(6, 8))
        self.log = tk.Text(self, height=16, wrap='word')
        self.log.pack(fill='both', expand=True, padx=18, pady=(0, 14))
        self.after(200, self.poll)

    def _path(self, parent, label, var, row, is_dir):
        ttk.Label(parent, text=label, width=31).grid(row=row, column=0, sticky='w', pady=6)
        ttk.Entry(parent, textvariable=var, width=65).grid(row=row, column=1, sticky='ew', padx=(8, 8))
        if is_dir:
            command = lambda: var.set(filedialog.askdirectory() or var.get())
        else:
            command = lambda: var.set(filedialog.askopenfilename() or var.get())
        ttk.Button(parent, text='Browse…', command=command).grid(row=row, column=2)
        parent.columnconfigure(1, weight=1)

    def launch(self):
        meta, arch, out = (Path(x.get()).expanduser() for x in (self.v_meta, self.v_arch, self.v_out))
        if not meta.is_file() or not arch.is_file():
            messagebox.showerror('Input missing', 'Choose valid metadata.csv and imp-pre.tzst files.')
            return
        if out.resolve() in (meta.parent.resolve(), arch.parent.resolve()):
            messagebox.showerror('Separate output folder', 'Please choose an output folder different from your source folder.')
            return
        self.btn.configure(state='disabled')
        self.log.insert('end', 'Processing source files. Large archives can take significant disk I/O.\n')
        self.log.see('end')
        threading.Thread(target=self.worker, args=(meta, arch, out, self.v_proxy.get(), self.v_wide.get()), daemon=True).start()

    def worker(self, meta, arch, out, proxy, wide):
        try:
            result = prepare(meta, arch, out, proxy, wide, logger=lambda m: self.jobs.put(('log', m)))
            self.jobs.put(('success', result))
        except Exception as exc:
            self.jobs.put(('error', str(exc)))

    def poll(self):
        try:
            while True:
                kind, msg = self.jobs.get_nowait()
                if kind == 'log':
                    self.log.insert('end', str(msg) + '\n')
                elif kind == 'success':
                    self.btn.configure(state='normal')
                    self.log.insert('end', 'COMPLETE. Output folder contains 3 category CSVs and quality reports.\n')
                    if not msg['distributor_ready_file']:
                        messagebox.showwarning('No common period', 'All 3 files were produced but no continuous 24-hour overlap was found. Check report and sector classification.')
                    else:
                        messagebox.showinfo('Done', 'Three category profiles and distributor-ready file generated.')
                elif kind == 'error':
                    self.btn.configure(state='normal')
                    self.log.insert('end', 'ERROR: ' + msg + '\n')
                    messagebox.showerror('Processing failed', str(msg))
                self.log.see('end')
        except queue.Empty:
            pass
        self.after(200, self.poll)


if __name__ == '__main__':
    CleanerGUI().mainloop()
