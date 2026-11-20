"""EE499 Team 16 — interactive CSV profile plotter.

Run: python plot_profiles.py
Choose ONE OR MORE CSVs; files overlaid together must have matching formats.
The app supports original long-format load/PV files and prepared irradiance files.
"""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parent
LOAD_REQUIRED = {'timestamp','bus_id','p_kw','q_kvar'}
SOLAR_REQUIRED = {'timestamp','irradiance_w_m2'}


def detect_format(path):
    header = set(pd.read_csv(path,nrows=0,encoding='utf-8-sig').columns)
    if LOAD_REQUIRED.issubset(header):
        return 'load'
    if SOLAR_REQUIRED.issubset(header):
        return 'irradiance'
    raise ValueError(f'{Path(path).name}: unsupported columns.\n\nExpected either:\n'
                     'timestamp,bus_id,p_kw,q_kvar\n'
                     'or timestamp,irradiance_w_m2')


def read_profile(path):
    """Validate and return original-format data, without altering the CSV."""
    kind=detect_format(path)
    data=pd.read_csv(path,encoding='utf-8-sig')
    data['timestamp']=pd.to_datetime(data.timestamp,errors='raise')
    if data.timestamp.isna().any():
        raise ValueError(f'{Path(path).name}: timestamps cannot be empty')
    if kind=='load':
        data['bus_id']=pd.to_numeric(data.bus_id,errors='raise').astype('int64')
        if data.duplicated(['timestamp','bus_id']).any():
            raise ValueError(f'{Path(path).name}: duplicate timestamp/bus_id')
        for column in ('p_kw','q_kvar'):
            data[column]=pd.to_numeric(data[column],errors='raise')
    else:
        if data.duplicated(['timestamp']).any():
            raise ValueError(f'{Path(path).name}: duplicate timestamps')
        data['irradiance_w_m2']=pd.to_numeric(data.irradiance_w_m2,errors='raise')
    return kind, data.sort_values('timestamp')


def zoom_axes(ax, scale, center_x=None, center_y=None):
    """Zoom both axes around a point; scale <1 zooms in, >1 zooms out.

    Keep this independent of Tk so the math is easy to validate.
    """
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    if center_x is None:
        center_x = (xmin + xmax) / 2
    if center_y is None:
        center_y = (ymin + ymax) / 2
    # Preserve the cursor's relative position within the visible area.
    xratio = (center_x - xmin) / (xmax - xmin)
    yratio = (center_y - ymin) / (ymax - ymin)
    xspan = (xmax - xmin) * scale
    yspan = (ymax - ymin) * scale
    ax.set_xlim(center_x - xratio * xspan, center_x + (1 - xratio) * xspan)
    ax.set_ylim(center_y - yratio * yspan, center_y + (1 - yratio) * yspan)


def make_series(data,kind,quantity='p_kw',bus='Total (all buses)',period='Daily mean',begin='',end=''):
    if kind=='load':
        if quantity not in ('p_kw','q_kvar'):raise ValueError('Load quantity must be P or Q')
        if bus!='Total (all buses)':
            data=data.loc[data.bus_id==int(bus)]
        # Sum multiple buses at each timestamp (not the average bus demand).
        y=data.groupby('timestamp')[quantity].sum()
    else:
        y=data.set_index('timestamp')['irradiance_w_m2']
    if begin:
        y=y.loc[y.index>=pd.Timestamp(begin)]
    if end:
        # If a date-only end was entered, include the whole day.
        t=pd.Timestamp(end)
        if len(end.strip())<=10:t+=pd.Timedelta(days=1)-pd.Timedelta(nanoseconds=1)
        y=y.loc[y.index<=t]
    if y.empty:
        raise ValueError('No data in the selected bus and time range')
    rules={
        'Hourly':None,
        'Daily mean':('D','mean'),
        'Daily peak':('D','max'),
        'Weekly mean':('W','mean'),
        'Monthly mean':('MS','mean'),
    }
    if period not in rules:raise ValueError('Unknown plot resolution')
    if rules[period]:
        freq,agg=rules[period]
        y=getattr(y.resample(freq),agg)().dropna()
    return y


class ProfilePlotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('EE499 Team 16 — Profile Comparison Plotter')
        self.geometry('1160x780')
        self.minsize(850,620)
        self.files=[]
        self.kind=None
        self.quantity=tk.StringVar(value='p_kw')
        self.bus=tk.StringVar(value='Total (all buses)')
        self.resolution=tk.StringVar(value='Daily mean')
        self.begin=tk.StringVar()
        self.end=tk.StringVar()
        self.status=tk.StringVar(value='Add one or more CSVs; mouse wheel to zoom, toolbar to pan.')
        self.has_plot=False
        self._build()

    def _build(self):
        top=ttk.Frame(self,padding=12)
        top.pack(fill='x')
        controls=ttk.Frame(top)
        controls.pack(fill='x',pady=(0,6))
        ttk.Button(controls,text='Add CSV files…',command=self.add_files).pack(side='left',padx=(0,7))
        ttk.Button(controls,text='Remove selected',command=self.remove_files).pack(side='left',padx=(0,7))
        ttk.Button(controls,text='Clear',command=self.clear).pack(side='left',padx=(0,7))
        ttk.Button(controls,text='Plot files',command=self.plot_files).pack(side='right',padx=(7,0))
        ttk.Button(controls,text='Save PNG…',command=self.save_image).pack(side='right',padx=(7,0))
        ttk.Button(controls,text='Reset View',command=self.reset_view).pack(side='right',padx=(7,0))
        ttk.Button(controls,text='Zoom Out −',command=self.zoom_out).pack(side='right',padx=(7,0))
        ttk.Button(controls,text='Zoom In +',command=self.zoom_in).pack(side='right',padx=(7,0))
        frame=ttk.Frame(top)
        frame.pack(fill='x')
        self.table=ttk.Treeview(frame,columns=('name','format','path'),show='headings',height=4,selectmode='extended')
        self.table.heading('name',text='File name')
        self.table.heading('format',text='Format')
        self.table.heading('path',text='Folder')
        self.table.column('name',width=280)
        self.table.column('format',width=115,anchor='center')
        self.table.column('path',width=580)
        self.table.pack(fill='x')
        settings=ttk.Frame(top)
        settings.pack(fill='x',pady=(11,7))
        ttk.Label(settings,text='Quantity').pack(side='left')
        self.quantity_box=ttk.Combobox(settings,textvariable=self.quantity,
                                      values=['p_kw','q_kvar'],state='readonly',width=17)
        self.quantity_box.pack(side='left',padx=(6,14))
        ttk.Label(settings,text='Bus').pack(side='left')
        self.bus_box=ttk.Combobox(settings,textvariable=self.bus,
                                 values=['Total (all buses)'],state='readonly',width=20)
        self.bus_box.pack(side='left',padx=(6,14))
        ttk.Label(settings,text='Resolution').pack(side='left')
        ttk.Combobox(settings,textvariable=self.resolution,
                    values=['Hourly','Daily mean','Daily peak','Weekly mean','Monthly mean'],
                    state='readonly',width=17).pack(side='left',padx=(6,0))
        dates=ttk.Frame(top)
        dates.pack(fill='x',pady=(0,4))
        ttk.Label(dates,text='From (optional)').pack(side='left')
        ttk.Entry(dates,textvariable=self.begin,width=18).pack(side='left',padx=(6,16))
        ttk.Label(dates,text='To (optional)').pack(side='left')
        ttk.Entry(dates,textvariable=self.end,width=18).pack(side='left',padx=(6,16))
        ttk.Label(dates,text='YYYY-MM-DD or YYYY-MM-DD HH:MM').pack(side='left')
        self.figure=Figure(figsize=(10,5.4),dpi=100)
        self.ax=self.figure.add_subplot(111)
        self.ax.set_title('Select one or more CSV files and click Plot files')
        self.ax.grid(alpha=0.3)
        self.canvas=FigureCanvasTkAgg(self.figure,master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both',expand=True,padx=12,pady=(2,0))
        self.toolbar=NavigationToolbar2Tk(self.canvas,self,pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side='bottom',fill='x',padx=12)
        self.canvas.mpl_connect('scroll_event', self.on_mouse_wheel)
        ttk.Label(self,textvariable=self.status,anchor='w',padding=(12,5)).pack(side='bottom',fill='x')

    def add_files(self):
        paths=filedialog.askopenfilenames(title='Select one or more compatible CSV files',
                                          initialdir=str(ROOT/'C2_annual_results'),
                                          filetypes=[('CSV files','*.csv'),('All files','*.*')])
        if not paths:return
        try:
            new=[]
            for name in paths:
                path=Path(name).resolve()
                if path in self.files:continue
                kind=detect_format(path)
                if self.kind is not None and kind!=self.kind:
                    raise ValueError('Cannot mix load/PV and irradiance files in one graph.\n'
                                     'Clear the list first, then select files of the same format.')
                if new and kind!=detect_format(new[0]):
                    raise ValueError('All selected files must use the same CSV format.')
                new.append(path)
            for path in new:
                self.files.append(path)
                self.table.insert('', 'end',iid=str(path),values=(path.name,detect_format(path),str(path.parent)))
            if self.files:self.kind=detect_format(self.files[0])
            self.refresh_options()
            self.status.set(f'{len(self.files)} file(s) selected. Ready to plot.')
        except Exception as exc:messagebox.showerror('Invalid CSV selection',str(exc))

    def refresh_options(self):
        if not self.files:
            self.kind=None
            self.bus.set('Total (all buses)')
            self.bus_box.configure(values=['Total (all buses)'])
            self.quantity.set('p_kw')
            self.quantity_box.configure(values=['p_kw','q_kvar'],state='readonly')
            return
        if self.kind=='irradiance':
            self.quantity.set('irradiance_w_m2')
            self.quantity_box.configure(values=['irradiance_w_m2'],state='readonly')
            self.bus.set('N/A')
            self.bus_box.configure(values=['N/A'],state='disabled')
        else:
            self.quantity_box.configure(values=['p_kw','q_kvar'],state='readonly')
            if self.quantity.get() not in ('p_kw','q_kvar'):self.quantity.set('p_kw')
            available=set()
            for file in self.files:
                ids=pd.read_csv(file,usecols=['bus_id']).bus_id.dropna().astype(int).unique()
                available.update(int(x) for x in ids)
            values=['Total (all buses)']+[str(x) for x in sorted(available)]
            self.bus_box.configure(values=values,state='readonly')
            if self.bus.get() not in values:self.bus.set(values[0])

    def remove_files(self):
        for item in self.table.selection():
            self.files.remove(Path(item))
            self.table.delete(item)
        self.kind=detect_format(self.files[0]) if self.files else None
        self.refresh_options()
        self.status.set(f'{len(self.files)} files selected.')

    def clear(self):
        self.files.clear()
        for item in self.table.get_children():self.table.delete(item)
        self.refresh_options()
        self.status.set('File list cleared. Any existing plot remains visible until you plot new files.')

    def plot_files(self):
        if not self.files:
            messagebox.showinfo('No files selected','Please select at least one CSV file.')
            return
        try:
            self.ax.clear()
            for path in self.files:
                kind, data=read_profile(path)
                if kind!=self.kind:raise ValueError('CSV formats are not compatible')
                s=make_series(data,kind,quantity=self.quantity.get(),bus=self.bus.get(),
                              period=self.resolution.get(),begin=self.begin.get().strip(),
                              end=self.end.get().strip())
                self.ax.plot(s.index,s.values,label=f"{path.parent.name} / {path.stem.replace('_',' ')}",linewidth=1.25)
            unit='W/m²' if self.kind=='irradiance' else ('kW' if self.quantity.get()=='p_kw' else 'kVAr')
            self.ax.set_title(f'{self.quantity.get()} — {self.bus.get()} — {self.resolution.get()}')
            self.ax.set_xlabel('Date/time')
            self.ax.set_ylabel(unit)
            self.ax.legend(fontsize=9)
            self.ax.grid(alpha=0.3)
            self.figure.autofmt_xdate()
            self.figure.tight_layout()
            self.canvas.draw()
            self.has_plot=True
            # Establish this newly drawn graph as the Home/reset view.
            self.toolbar.update()
            self.toolbar.push_current()
            self.status.set(f'Plotted {len(self.files)} file(s). Scroll to zoom; use Pan in the toolbar to move.')
        except Exception as exc:
            self.status.set(f'Plot failed: {exc}')
            messagebox.showerror('Could not plot',str(exc))

    def _zoom(self, scale, x=None, y=None):
        if not self.has_plot:
            self.status.set('Plot at least one file before zooming.')
            return
        zoom_axes(self.ax, scale, center_x=x, center_y=y)
        self.toolbar.push_current()  # Back/Home navigation remains available
        self.canvas.draw_idle()

    def zoom_in(self):
        self._zoom(0.7)

    def zoom_out(self):
        self._zoom(1 / 0.7)

    def reset_view(self):
        if self.has_plot:
            self.toolbar.home()
            self.canvas.draw_idle()

    def on_mouse_wheel(self, event):
        if self.has_plot and event.inaxes == self.ax and event.button in ('up', 'down'):
            scale = 0.7 if event.button == 'up' else 1 / 0.7
            self._zoom(scale, x=event.xdata, y=event.ydata)

    def save_image(self):
        path=filedialog.asksaveasfilename(title='Save plot as PNG',defaultextension='.png',
                                          filetypes=[('PNG image','*.png')])
        if path:
            self.figure.savefig(path,dpi=200,bbox_inches='tight')
            self.status.set(f'Saved {path}')


if __name__=='__main__':
    ProfilePlotter().mainloop()
