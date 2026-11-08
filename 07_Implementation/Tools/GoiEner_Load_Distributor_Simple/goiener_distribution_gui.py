#!/usr/bin/env python3
"""Simple GoiEner-only GUI for assigning 3 clean sector profiles to many radial feeders."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import distribution_engine as core


class SectorEditor(tk.Toplevel):
    def __init__(self, parent, network: core.NetworkData, initial: dict[int, str] | None, on_save):
        super().__init__(parent)
        self.title(f"Bus types — {network.source.name}")
        self.geometry("920x650")
        self.minsize(730, 490)
        self.transient(parent)
        self.net = network
        self.mapping = dict(initial or {})
        self.on_save = on_save
        self.filter_text = tk.StringVar()
        self.range_text = tk.StringVar()
        self.category = tk.StringVar(value="residential")
        top = ttk.Frame(self, padding=14)
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="Assign customer types to load buses", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(top, text="One GoiEner profile per type • select multiple rows or type bus ranges (e.g. 2-50, 74, 90-136)",
                  style="Subtle.TLabel").pack(anchor="w", pady=(0, 12))
        line = ttk.Frame(top)
        line.pack(fill="x", pady=(0, 8))
        ttk.Label(line, text="Filter:").pack(side="left")
        ttk.Entry(line, textvariable=self.filter_text, width=24).pack(side="left", padx=(7, 12))
        ttk.Button(line, text="Select visible", command=self.select_visible).pack(side="left")
        ttk.Button(line, text="Clear selection", command=lambda: self.tree.selection_remove(*self.tree.selection())).pack(side="left", padx=8)
        self.filter_text.trace_add("write", lambda *_: self.refresh())
        cols = ("bus", "p", "q", "category")
        area = ttk.Frame(top)
        area.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(area, columns=cols, show="headings", selectmode="extended", height=15)
        for col, label, width in [("bus", "Bus ID", 95), ("p", "Base P (kW)", 140), ("q", "Base Q (kvar)", 150),
                                  ("category", "Assigned category", 245)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="center" if col == "bus" else "w")
        self.tree.pack(side="left", fill="both", expand=True)
        sc = ttk.Scrollbar(area, orient="vertical", command=self.tree.yview)
        sc.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sc.set)
        control = ttk.Frame(top)
        control.pack(fill="x", pady=12)
        ttk.Label(control, text="Type:").pack(side="left")
        ttk.Combobox(control, textvariable=self.category, values=core.CATEGORIES, state="readonly", width=19).pack(side="left", padx=8)
        ttk.Button(control, text="Apply to selected", command=self.apply_selection).pack(side="left")
        ttk.Button(control, text="Fill unassigned", command=self.fill_unassigned).pack(side="left", padx=8)
        row2 = ttk.Frame(top)
        row2.pack(fill="x")
        ttk.Label(row2, text="Bus IDs / ranges:").pack(side="left")
        ttk.Entry(row2, textvariable=self.range_text, width=33).pack(side="left", padx=(7, 6))
        ttk.Button(row2, text="Assign range", command=self.apply_ranges).pack(side="left")
        ttk.Button(row2, text="Example cycle", command=self.cycle_demo).pack(side="left", padx=9)
        self.count_label = ttk.Label(top, text="", style="Subtle.TLabel")
        self.count_label.pack(anchor="w", pady=(8, 3))
        buttons = ttk.Frame(top)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Import assignments CSV…", command=self.import_csv).pack(side="left")
        ttk.Button(buttons, text="Save assignments CSV…", command=self.export_csv).pack(side="left", padx=8)
        ttk.Button(buttons, text="Save mapping and close", command=self.finish, style="Accent.TButton").pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.refresh()
        self.grab_set()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = self.filter_text.get().strip().lower()
        for row in self.net.loads.itertuples():
            bus = int(row.bus_id)
            if bus not in self.net.load_ids:
                continue
            category = self.mapping.get(bus, "UNASSIGNED")
            values = (bus, f"{row.p_base_kw:.3f}", f"{row.q_base_kvar:.3f}", category)
            if query and query not in " ".join(map(str, values)).lower():
                continue
            self.tree.insert("", "end", iid=str(bus), values=values)
        self.count_label.configure(text=f"{len(self.mapping)} / {len(self.net.load_ids)} load buses assigned")

    def select_visible(self):
        self.tree.selection_set(*self.tree.get_children())

    def _update(self, ids):
        selected = set(ids)
        invalid = selected - set(self.net.load_ids)
        if invalid:
            messagebox.showerror("Invalid buses", f"These IDs are not load buses: {sorted(invalid)[:15]}", parent=self)
            return
        for bus in selected:
            self.mapping[bus] = self.category.get()
        self.refresh()

    def apply_selection(self):
        ids = [int(i) for i in self.tree.selection()]
        if not ids:
            messagebox.showinfo("Select buses", "Select one or more bus rows first.", parent=self)
            return
        self._update(ids)

    def apply_ranges(self):
        try:
            ids = core.parse_bus_range(self.range_text.get())
            if not ids:
                raise ValueError("Enter bus IDs or ranges")
            self._update(ids)
        except Exception as e:
            messagebox.showerror("Bus range", str(e), parent=self)

    def fill_unassigned(self):
        self._update(set(self.net.load_ids) - set(self.mapping))

    def cycle_demo(self):
        if messagebox.askyesno("Synthetic scenario", "Assign residential/commercial/manufacturing in round-robin order?\n\nThese are DEMO labels, not documented real bus types.", parent=self):
            self.mapping = core.demo_cycle(self.net)
            self.refresh()

    def import_csv(self):
        filename = filedialog.askopenfilename(parent=self, title="Open bus assignments", filetypes=[("CSV", "*.csv")])
        if filename:
            try:
                self.mapping = core.load_mapping(Path(filename), self.net)
                self.refresh()
            except Exception as e:
                messagebox.showerror("Invalid assignments", str(e), parent=self)

    def export_csv(self):
        filename = filedialog.asksaveasfilename(parent=self, title="Save bus assignments", defaultextension=".csv",
                                                 initialfile=f"{self.net.source.stem}_assignments.csv", filetypes=[("CSV", "*.csv")])
        if filename:
            try:
                core.validate_mapping(self.net, self.mapping)
                with Path(filename).open("w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(("bus_id", "category"))
                    w.writerows((i, self.mapping[i]) for i in sorted(self.mapping))
            except Exception as e:
                messagebox.showerror("Cannot save", str(e), parent=self)

    def finish(self):
        try:
            core.validate_mapping(self.net, self.mapping)
        except Exception as e:
            messagebox.showerror("Incomplete mapping", str(e), parent=self)
            return
        self.on_save(dict(self.mapping))
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BESS | GoiEner Load Distributor")
        self.geometry("1100x790")
        self.minsize(860, 640)
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure("Heading.TLabel", font=("Segoe UI", 15, "bold"))
        self.style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        self.style.configure("Subtle.TLabel", foreground="#5C6570", font=("Segoe UI", 10))
        self.style.configure("Accent.TButton", padding=(18, 10))
        self.style.configure("TButton", padding=(9, 5))
        self.style.configure("TNotebook.Tab", padding=(15, 8))
        self.source: core.SectorData | None = None
        self.networks: dict[str, core.NetworkData] = {}
        self.maps: dict[str, dict[int, str]] = {}
        self.events: queue.Queue = queue.Queue()
        self.profile_path = tk.StringVar()
        self.value_choice = tk.StringVar(value="average")
        self.source_summary = tk.StringVar(value="No cleaned profiles loaded")
        self.frequency = tk.StringVar(value="60")
        self.anchor = tk.StringVar(value="mean")
        self.mapping_style = tk.StringVar(value="saved")
        self.map_folder = tk.StringVar()
        self.output_root = tk.StringVar(value=str(Path.home() / "Documents"))
        self.zero_pv = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Load your cleaned GoiEner profiles, then add networks.")
        self._build()
        self.after(150, self._poll)

    def _build(self):
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="GoiEner Load Distributor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="One dataset • three customer classes • any supported feeder size • complete shared historical period",
                  style="Subtle.TLabel").pack(anchor="w", pady=(2, 14))
        tabs = ttk.Notebook(container)
        tabs.pack(fill="both", expand=True)
        self.p1 = ttk.Frame(tabs, padding=16)
        self.p2 = ttk.Frame(tabs, padding=16)
        self.p3 = ttk.Frame(tabs, padding=16)
        tabs.add(self.p1, text="1  Profiles")
        tabs.add(self.p2, text="2  Networks & bus types")
        tabs.add(self.p3, text="3  Export")
        self._build_profiles()
        self._build_networks()
        self._build_export()
        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, textvariable=self.status, style="Subtle.TLabel", wraplength=950).pack(anchor="w")

    def _build_profiles(self):
        page = self.p1
        ttk.Label(page, text="Load cleaned GoiEner demand data", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(page, text="Use the output from the Three-Category Cleaner. Do not select imp-pre.tzst or metadata.csv here.",
                  style="Subtle.TLabel", wraplength=920).pack(anchor="w", pady=(4, 20))
        field = ttk.LabelFrame(page, text="Profile source", padding=14)
        field.pack(fill="x")
        ttk.Entry(field, textvariable=self.profile_path).pack(side="left", fill="x", expand=True)
        ttk.Button(field, text="Choose cleaner output folder…", command=self._pick_profile_folder).pack(side="left", padx=(10, 0))
        ttk.Button(field, text="Choose prepared wide CSV…", command=self._pick_wide).pack(side="left", padx=(7, 0))
        opt = ttk.Frame(page)
        opt.pack(fill="x", pady=(22, 9))
        ttk.Label(opt, text="Profile value:").pack(side="left")
        ttk.Combobox(opt, textvariable=self.value_choice, values=("average", "sum"), width=15,
                     state="readonly").pack(side="left", padx=(10, 15))
        ttk.Label(opt, text="Average is recommended when contributing customer counts vary.",
                  style="Subtle.TLabel").pack(side="left")
        ttk.Button(page, text="Load and validate profiles", command=self._load_profiles,
                   style="Accent.TButton").pack(anchor="w", pady=(8, 18))
        report = ttk.LabelFrame(page, text="Loaded dataset", padding=14)
        report.pack(fill="both", expand=True)
        ttk.Label(report, textvariable=self.source_summary, wraplength=900,
                  justify="left").pack(anchor="w")
        ttk.Label(report, text="All three types must share the timestamps used for distribution. The source files are read-only.\n"
                  "No arbitrary 24-hour, one-year, or three-year cutoff is applied.",
                  style="Subtle.TLabel", wraplength=900).pack(anchor="w", pady=(16, 0))

    def _pick_profile_folder(self):
        name = filedialog.askdirectory(title="Select folder from GoiEner cleaner")
        if name:
            self.profile_path.set(name)

    def _pick_wide(self):
        name = filedialog.askopenfilename(title="Select goiener_distributor_ready.csv or goiener_three_profiles.csv",
                                          filetypes=[("CSV", "*.csv")])
        if name:
            self.profile_path.set(name)

    def _load_profiles(self):
        try:
            source = core.load_profiles(Path(self.profile_path.get().strip()), self.value_choice.get())
            self.source = source
            frame = source.frame
            self.source_summary.set(f"✓ Loaded {source.hours:,} consecutive hours\n"
                                    f"From {frame.timestamp.iloc[0]}  to  {frame.timestamp.iloc[-1]}\n\n"
                                    f"Source: {source.source}\n"
                                    f"Values: {source.value_choice}\n\n{source.note}\n\n"
                                    "Available: Residential  •  Commercial  •  Manufacturing")
            self.status.set("GoiEner profiles ready. Add one or more network workbooks.")
        except Exception as e:
            messagebox.showerror("Profile import failed", str(e))

    def _build_networks(self):
        page = self.p2
        ttk.Label(page, text="Import networks and assign bus types", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(page, text="Supports the existing Working_RDS Excel format (5–136+ buses), plus generic bus-load CSVs.",
                  style="Subtle.TLabel").pack(anchor="w", pady=(3, 12))
        buttons = ttk.Frame(page)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add network files…", command=self._add_files).pack(side="left")
        ttk.Button(buttons, text="Add whole folder…", command=self._add_folder).pack(side="left", padx=8)
        ttk.Button(buttons, text="Remove selected", command=self._remove_networks).pack(side="left")
        ttk.Label(buttons, text="Frequency:").pack(side="left", padx=(20, 5))
        ttk.Combobox(buttons, textvariable=self.frequency, values=("50", "60"), width=6,
                     state="readonly").pack(side="left")
        box = ttk.Frame(page)
        box.pack(fill="both", expand=True, pady=(14, 9))
        cols = ("name", "buses", "loads", "pv", "slack", "map")
        self.case_tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="extended", height=13)
        for c, heading, width in [("name", "Network", 400), ("buses", "Buses", 65), ("loads", "Load buses", 92),
                                  ("pv", "PV buses", 77), ("slack", "Slack", 65), ("map", "Bus type map", 118)]:
            self.case_tree.heading(c, text=heading)
            self.case_tree.column(c, width=width, anchor="w" if c == "name" else "center")
        self.case_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(box, orient="vertical", command=self.case_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.case_tree.configure(yscrollcommand=scrollbar.set)
        controls = ttk.Frame(page)
        controls.pack(fill="x")
        ttk.Button(controls, text="Edit selected network's bus types…", command=self._edit_network,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(controls, text="Import one assignment CSV…", command=self._load_single_map).pack(side="left", padx=8)
        ttk.Label(page, text="Bus categories cannot be inferred from bus numbers. Assignments are assumptions unless supported by network documentation.",
                  wraplength=930, style="Subtle.TLabel").pack(anchor="w", pady=(12, 0))

    def _add_files(self):
        names = filedialog.askopenfilenames(title="Choose feeder workbooks or CSVs",
                                            filetypes=[("Networks", "*.xlsx *.csv")])
        if names:
            self._add_paths(names)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Choose Working_RDS or other network folder")
        if folder:
            p = Path(folder)
            self._add_paths([str(x) for x in sorted(p.iterdir()) if x.suffix.lower() in (".xlsx", ".csv")])

    def _add_paths(self, paths):
        errors = []
        for name in paths:
            path = str(Path(name).resolve())
            if path in self.networks:
                continue
            try:
                case = core.load_network(Path(path), frequency_hz=float(self.frequency.get()))
                self.networks[path] = case
            except Exception as e:
                errors.append(f"{Path(path).name}: {e}")
        self._refresh_cases()
        self.status.set(f"{len(self.networks)} networks loaded" + (f"; {len(errors)} rejected" if errors else ""))
        if errors:
            messagebox.showwarning("Some networks could not be loaded", "\n".join(errors[:12]))

    def _refresh_cases(self):
        self.case_tree.delete(*self.case_tree.get_children())
        for path, case in self.networks.items():
            mapped = len(self.maps.get(path, {}))
            txt = f"{mapped}/{len(case.load_ids)}" if mapped else "Not mapped"
            self.case_tree.insert("", "end", iid=path,
                                  values=(case.source.name, len(case.loads), len(case.load_ids), case.pv_count, case.slack, txt))

    def _selected_paths(self):
        return [str(p) for p in self.case_tree.selection()]

    def _one_selected(self):
        paths = self._selected_paths()
        if len(paths) != 1:
            messagebox.showinfo("Select network", "Select exactly one network in the table.")
            return None
        return paths[0]

    def _remove_networks(self):
        for path in self._selected_paths():
            self.networks.pop(path, None)
            self.maps.pop(path, None)
        self._refresh_cases()

    def _edit_network(self):
        path = self._one_selected()
        if path is not None:
            SectorEditor(self, self.networks[path], self.maps.get(path),
                         lambda mapping: self._save_mapping(path, mapping))

    def _save_mapping(self, path, mapping):
        self.maps[path] = mapping
        self._refresh_cases()

    def _load_single_map(self):
        path = self._one_selected()
        if path is None:
            return
        file = filedialog.askopenfilename(title="Open mapping CSV", filetypes=[("CSV", "*.csv")])
        if file:
            try:
                self._save_mapping(path, core.load_mapping(Path(file), self.networks[path]))
            except Exception as e:
                messagebox.showerror("Invalid mapping", str(e))

    def _build_export(self):
        page = self.p3
        ttk.Label(page, text="Generate simulation-ready load CSVs", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(page, text="The full common timeline is exported. Large networks can produce multi-million-row CSVs.",
                  style="Subtle.TLabel").pack(anchor="w", pady=(3, 16))
        settings = ttk.LabelFrame(page, text="Distribution settings", padding=14)
        settings.pack(fill="x")
        line = ttk.Frame(settings)
        line.pack(fill="x")
        ttk.Label(line, text="Base load interpreted as:").pack(side="left")
        ttk.Radiobutton(line, text="Average demand (mean)", variable=self.anchor, value="mean").pack(side="left", padx=16)
        ttk.Radiobutton(line, text="Peak demand", variable=self.anchor, value="peak").pack(side="left")
        ttk.Label(settings, text="The selected reference scales all three profiles to each bus's original P and Q without modifying the feeder file.",
                  style="Subtle.TLabel").pack(anchor="w", pady=(8, 0))
        setting2 = ttk.LabelFrame(page, text="Customer-type assignment rule", padding=14)
        setting2.pack(fill="x", pady=14)
        ttk.Radiobutton(setting2, text="Use individually edited/saved assignments (recommended)",
                        variable=self.mapping_style, value="saved").pack(anchor="w", pady=3)
        ttk.Radiobutton(setting2, text="Treat all load buses as residential (declared hypothetical scenario)",
                        variable=self.mapping_style, value="all_residential").pack(anchor="w", pady=3)
        ttk.Radiobutton(setting2, text="Cycle residential / commercial / manufacturing (synthetic demo only)",
                        variable=self.mapping_style, value="demo_cycle").pack(anchor="w", pady=3)
        row = ttk.Frame(setting2)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="Optional folder with <network_name>_assignments.csv:").pack(side="left")
        ttk.Entry(row, textvariable=self.map_folder).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Browse…", command=self._pick_map_folder).pack(side="left")
        ttk.Checkbutton(page, text="I understand: for networks containing PV units, export ZERO-PV placeholders for load-only tests.",
                        variable=self.zero_pv).pack(anchor="w", pady=(8, 3))
        ttk.Label(page, text="GoiEner has no PV measurements. PV curtailment / BESS economics must NOT be evaluated using a zero-PV placeholder as real PV generation.",
                  style="Subtle.TLabel", wraplength=950).pack(anchor="w")
        pathrow = ttk.Frame(page)
        pathrow.pack(fill="x", pady=(20, 15))
        ttk.Label(pathrow, text="Destination folder:").pack(side="left")
        ttk.Entry(pathrow, textvariable=self.output_root).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(pathrow, text="Browse…", command=self._pick_output).pack(side="left")
        self.export_button = ttk.Button(page, text="Export all loaded networks", command=self._export,
                                        style="Accent.TButton")
        self.export_button.pack(anchor="w", pady=5)
        self.progress = ttk.Progressbar(page, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=10)
        self.log_box = tk.Text(page, height=7, state="disabled", wrap="word", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True)

    def _pick_map_folder(self):
        value = filedialog.askdirectory(title="Choose assignment CSV folder")
        if value:
            self.map_folder.set(value)

    def _pick_output(self):
        value = filedialog.askdirectory(title="Choose destination folder")
        if value:
            self.output_root.set(value)

    def _export(self):
        if not self.source:
            messagebox.showerror("Missing source", "Load the cleaned GoiEner profiles in tab 1 first.")
            return
        if not self.networks:
            messagebox.showerror("Missing network", "Add one or more networks in tab 2 first.")
            return
        style = self.mapping_style.get()
        mappings = {}
        errors = []
        for path, case in self.networks.items():
            try:
                if style == "all_residential":
                    mapping = core.all_residential(case)
                elif style == "demo_cycle":
                    mapping = core.demo_cycle(case)
                else:
                    mapping = self.maps.get(path)
                    if mapping is None and self.map_folder.get().strip():
                        file = Path(self.map_folder.get()) / f"{case.source.stem}_assignments.csv"
                        mapping = core.load_mapping(file, case)
                    if mapping is None:
                        raise ValueError("No saved or imported bus map. Edit it in tab 2 or choose an explicit scenario assignment.")
                core.validate_mapping(case, mapping)
                if case.pv_count and not self.zero_pv.get():
                    raise ValueError("Has PV units; explicitly check ZERO-PV placeholder if this is a load-only test")
                mappings[path] = mapping
            except Exception as exc:
                errors.append(f"{case.source.name}: {exc}")
        if errors:
            messagebox.showerror("Correct before export", "\n".join(errors[:15]))
            return
        output_base = Path(self.output_root.get()).expanduser()
        if not output_base.is_dir():
            messagebox.showerror("Invalid output folder", "Choose an existing destination folder")
            return
        run_folder = output_base / f"GoiEner_Distributed_{datetime.now():%Y%m%d_%H%M%S_%f}"
        self.export_button.configure(state="disabled")
        self.progress.configure(value=0)
        self._append_log(f"Exporting {len(self.networks)} network(s) from {self.source.hours:,} GoiEner hours…")
        args = (dict(self.networks), mappings, self.source, run_folder,
                self.anchor.get(), bool(self.zero_pv.get()), style)
        threading.Thread(target=self._worker, args=args, daemon=True).start()

    def _worker(self, cases, mappings, source, root, anchor, zero_pv, style):
        results = []
        root.mkdir(parents=True)
        for index, (path, case) in enumerate(cases.items(), 1):
            clean = core._safe_filename(case.source.stem)
            folder = root / clean
            if folder.exists():
                folder = root / f"{clean}_{index:02d}"
            try:
                manifest = core.export_network(case, source, mappings[path], folder, anchor, zero_pv,
                                                progress=lambda msg: self.events.put(("log", msg)) if msg.endswith(f"{source.hours:,} hours exported") else None)
                results.append({"network": case.source.name, "status": "ok", "folder": str(folder),
                                "message": f"{manifest['hours']:,} hours x {manifest['bus_count']} buses"})
            except Exception as e:
                results.append({"network": case.source.name, "status": "failed", "folder": "", "message": str(e)})
            self.events.put(("progress", int(100 * index / len(cases))))
            self.events.put(("log", f"{case.source.name}: {results[-1]['status']} — {results[-1]['message']}"))
        with (root / "batch_summary.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["network", "status", "folder", "message"])
            writer.writeheader()
            writer.writerows(results)
        (root / "SCENARIO_CLASSIFICATION.txt").write_text(
            "Customer-sector assignments are selected study assumptions and are not inferred from static feeder topology.\n"
            f"Assignment rule: {style}.\n"
            "No PV generation data is included; any exported pv_profile.csv is a ZERO placeholder.\n",
            encoding="utf-8")
        self.events.put(("finish", (root, results)))

    def _append_log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "progress":
                    self.progress.configure(value=data)
                elif kind == "log":
                    self._append_log(str(data))
                elif kind == "finish":
                    folder, results = data
                    successes = sum(row["status"] == "ok" for row in results)
                    self.status.set(f"Export complete: {successes}/{len(results)} networks. Results at {folder}")
                    self.export_button.configure(state="normal")
                    messagebox.showinfo("Export finished", f"Generated {successes} of {len(results)} networks.\n\nOutput: {folder}\nSee batch_summary.csv for details.")
        except queue.Empty:
            pass
        self.after(150, self._poll)


if __name__ == "__main__":
    App().mainloop()
