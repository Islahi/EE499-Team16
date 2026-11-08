"""GoiEner distributed-load + NASA POWER viewer (Tkinter/Matplotlib)."""
from __future__ import annotations

import json
import queue
import calendar
from datetime import date
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from data_engine import (discover_networks,aggregate_distributed,load_aggregated_csv,
                         merge_nasa_monthly)
from plot_engine import plot_dashboard


def default_end_date(start: str | date, period: str) -> str:
    """Inclusive end date for one rolling day/week/calendar month/year."""
    beginning = pd.Timestamp(start).normalize()
    if period == 'Daily':
        end = beginning
    elif period == 'Weekly':
        end = beginning + pd.Timedelta(days=6)
    elif period == 'Monthly':
        end = beginning + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    elif period == 'Yearly':
        end = beginning + pd.DateOffset(years=1) - pd.Timedelta(days=1)
    else:
        raise ValueError(f'Unknown period: {period}')
    return str(end.date())


class DateSpinbox(ttk.Frame):
    """YYYY-MM-DD editor with arrow spinners for year, month, and day."""

    def __init__(self, master, value: tk.StringVar, on_change=None):
        super().__init__(master)
        self.value = value
        self.on_change = on_change
        self._updating = False
        self.y = tk.StringVar()
        self.m = tk.StringVar()
        self.d = tk.StringVar()
        specs = ((self.y,1900,2200,5,'%04.0f'),
                 (self.m,1,12,3,'%02.0f'),
                 (self.d,1,31,3,'%02.0f'))
        self.boxes=[]
        for i,(var,lo,hi,width,fmt) in enumerate(specs):
            if i:
                ttk.Label(self,text='-').pack(side=tk.LEFT)
            box=ttk.Spinbox(self,from_=lo,to=hi,width=width,format=fmt,
                             textvariable=var,command=self._commit)
            box.pack(side=tk.LEFT,padx=1)
            box.bind('<Return>',self._commit)
            box.bind('<FocusOut>',self._commit)
            self.boxes.append(box)
        self.value.trace_add('write',self._sync_from_iso)
        self._sync_from_iso()

    def _sync_from_iso(self,*unused):
        if self._updating:
            return
        try:
            current=date.fromisoformat(self.value.get())
        except ValueError:
            return
        self._updating=True
        try:
            self.y.set(str(current.year))
            self.m.set(f'{current.month:02d}')
            self.d.set(f'{current.day:02d}')
            self.boxes[2].configure(to=calendar.monthrange(current.year,current.month)[1])
        finally:
            self._updating=False

    def _commit(self,event=None):
        if self._updating:
            return
        try:
            yy=int(self.y.get());mm=int(self.m.get());dd=int(self.d.get())
            yy=max(1900,min(2200,yy));mm=max(1,min(12,mm))
            dd=max(1,min(calendar.monthrange(yy,mm)[1],dd))
            newdate=date(yy,mm,dd).isoformat()
        except ValueError:
            self._sync_from_iso()
            return
        changed=newdate!=self.value.get()
        self._updating=True
        try:
            self.y.set(str(yy));self.m.set(f'{mm:02d}');self.d.set(f'{dd:02d}')
            self.boxes[2].configure(to=calendar.monthrange(yy,mm)[1])
            self.value.set(newdate)
        finally:
            self._updating=False
        if changed and self.on_change:
            self.on_change()


class Plotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('BESS — Distributed Load & NASA POWER Plotter')
        self.geometry('1420x870')
        self.minsize(1040,690)
        self.queue:queue.Queue=queue.Queue()
        self.networks={}
        self.network_cache={}
        self.solar_groups={}
        self.plot_tables={}
        self.load_current=None
        self.solar_current=None
        self.active_network=None
        self.bus_checks={}
        self.solar_checks={}
        self._pending_redraw=None
        self._range_is_custom=False
        self._queue_after_id=None
        self._setup_style()
        self._build()
        self._queue_after_id=self.after(125,self._drain_queue)

    def destroy(self):
        """Clean up scheduled callbacks when the window is closed."""
        for callback_id in (self._pending_redraw,self._queue_after_id):
            if callback_id is not None:
                try:self.after_cancel(callback_id)
                except tk.TclError:pass
        self._pending_redraw=None
        self._queue_after_id=None
        super().destroy()

    def _setup_style(self):
        style=ttk.Style(self)
        if 'clam' in style.theme_names():style.theme_use('clam')
        style.configure('Heading.TLabel',font=('Segoe UI',13,'bold'))
        style.configure('Subheading.TLabel',font=('Segoe UI',10,'bold'))
        style.configure('TButton',padding=6)
        style.configure('TNotebook.Tab',padding=(12,8))

    def _build(self):
        outer=ttk.PanedWindow(self,orient=tk.HORIZONTAL)
        outer.pack(fill=tk.BOTH,expand=True,padx=8,pady=8)
        # Scrollable sidebar: all checkbox controls remain accessible on
        # laptops and at 100%+ display scaling, including start/end dates.
        sidebar=ttk.Frame(outer,width=380)
        outer.add(sidebar,weight=0)
        right=ttk.Frame(outer)
        outer.add(right,weight=1)
        sidebar.columnconfigure(0,weight=1)
        sidebar.rowconfigure(0,weight=1)
        self.left_canvas=tk.Canvas(sidebar,borderwidth=0,highlightthickness=0,
                                   background=ttk.Style(self).lookup('TFrame','background') or '#f0f0f0')
        self.left_canvas.grid(row=0,column=0,sticky='nsew')
        side_scroll=ttk.Scrollbar(sidebar,orient='vertical',command=self.left_canvas.yview)
        side_scroll.grid(row=0,column=1,sticky='ns')
        self.left_canvas.configure(yscrollcommand=side_scroll.set)
        left=ttk.Frame(self.left_canvas)
        panel_id=self.left_canvas.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:self.left_canvas.configure(scrollregion=self.left_canvas.bbox('all')))
        self.left_canvas.bind('<Configure>',lambda e:self.left_canvas.itemconfigure(panel_id,width=e.width))
        self.bind_all('<MouseWheel>',self._sidebar_wheel,add='+')
        self.bind_all('<Button-4>',self._sidebar_wheel,add='+')
        self.bind_all('<Button-5>',self._sidebar_wheel,add='+')

        ttk.Label(left,text='Data & plots',style='Heading.TLabel').pack(anchor='w',pady=(5,8))
        source_box=ttk.LabelFrame(left,text='1  Distributed network ZIPs',padding=8)
        source_box.pack(fill=tk.X,pady=5)
        controls=ttk.Frame(source_box); controls.pack(fill=tk.X)
        ttk.Button(controls,text='Add ZIP(s)',command=self.add_zips).pack(side=tk.LEFT)
        ttk.Button(controls,text='Add prepared CSV',command=self.add_prepared_csv).pack(side=tk.LEFT,padx=4)
        ttk.Label(source_box,text='Select feeder to plot:',foreground='#666').pack(anchor='w',pady=(6,3))
        lf=ttk.Frame(source_box);lf.pack(fill=tk.BOTH)
        self.net_tree=ttk.Treeview(lf,columns=('name','hours'),show='headings',height=5,selectmode='browse')
        self.net_tree.heading('name',text='Network');self.net_tree.heading('hours',text='Hours')
        self.net_tree.column('name',width=230);self.net_tree.column('hours',width=65,anchor='e')
        scroll=ttk.Scrollbar(lf,orient='vertical',command=self.net_tree.yview)
        self.net_tree.configure(yscrollcommand=scroll.set)
        self.net_tree.pack(side=tk.LEFT,fill=tk.BOTH,expand=True);scroll.pack(side=tk.RIGHT,fill=tk.Y)
        self.net_tree.bind('<<TreeviewSelect>>',self.choose_network)

        sun_box=ttk.LabelFrame(left,text='2  NASA POWER irradiance',padding=8)
        sun_box.pack(fill=tk.X,pady=5)
        ttk.Button(sun_box,text='Import NASA CSV(s) for one location',command=self.add_nasa).pack(fill=tk.X)
        self.time_mode=tk.StringVar(value='utc_to_spain')
        ttk.Radiobutton(sun_box,text='UTC → Europe/Madrid (assumption)',variable=self.time_mode,value='utc_to_spain').pack(anchor='w')
        ttk.Radiobutton(sun_box,text='Use CSV timestamps as written',variable=self.time_mode,value='as_is').pack(anchor='w')
        self.nasa_location=tk.StringVar()
        self.nasa_combo=ttk.Combobox(sun_box,textvariable=self.nasa_location,state='readonly')
        self.nasa_combo.pack(fill=tk.X,pady=4)
        self.nasa_combo.bind('<<ComboboxSelected>>',self.choose_solar)

        opts=ttk.LabelFrame(left,text='3  Plot controls',padding=8)
        opts.pack(fill=tk.X,pady=5)
        self.mode=tk.StringVar(value='Load');self.period=tk.StringVar(value='Daily')
        self.detail=tk.StringVar(value='Default');self.presentation=tk.StringVar(value='Energy')
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=3)
        ttk.Label(rr,text='Plot:').pack(side=tk.LEFT)
        mode=ttk.Combobox(rr,textvariable=self.mode,values=['Load','NASA','Compare'],state='readonly',width=16)
        mode.pack(side=tk.LEFT,padx=6)
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=3)
        ttk.Label(rr,text='Period:').pack(side=tk.LEFT)
        per=ttk.Combobox(rr,textvariable=self.period,values=['Daily','Weekly','Monthly','Yearly'],state='readonly',width=16)
        per.pack(side=tk.LEFT,padx=6)
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=3)
        ttk.Label(rr,text='Detail:').pack(side=tk.LEFT)
        det=ttk.Combobox(rr,textvariable=self.detail,values=['Default','Hourly','Daily','Weekly','Monthly'],state='readonly',width=16)
        det.pack(side=tk.LEFT,padx=6)
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=3)
        ttk.Label(rr,text='Measure:').pack(side=tk.LEFT)
        pre=ttk.Combobox(rr,textvariable=self.presentation,values=['Energy','Average power','Normalized'],state='readonly',width=16)
        pre.pack(side=tk.LEFT,padx=6)
        ttk.Label(opts,text='Date range (inclusive; YYYY-MM-DD):',style='Subheading.TLabel').pack(anchor='w',pady=(7,2))
        self.start_date=tk.StringVar(value='2018-06-01')
        self.end_date=tk.StringVar(value='2018-06-01')
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=2)
        ttk.Label(rr,text='Start',width=6).pack(side=tk.LEFT)
        self.start_entry=DateSpinbox(rr,self.start_date,on_change=self._on_start_changed)
        self.start_entry.pack(side=tk.LEFT,padx=4)
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=2)
        ttk.Label(rr,text='End',width=6).pack(side=tk.LEFT)
        self.end_entry=DateSpinbox(rr,self.end_date,on_change=self._on_end_changed)
        self.end_entry.pack(side=tk.LEFT,padx=4)
        rr=ttk.Frame(opts);rr.pack(fill=tk.X,pady=2)
        ttk.Button(rr,text='◀',width=3,command=lambda:self.move_date(-1)).pack(side=tk.LEFT)
        ttk.Button(rr,text='Use full available range',command=self.use_all_dates).pack(side=tk.LEFT,fill=tk.X,expand=True,padx=5)
        ttk.Button(rr,text='▶',width=3,command=lambda:self.move_date(1)).pack(side=tk.RIGHT)
        ttk.Label(opts,text='Switching period sets a 1-day / 1-week / 1-month / 1-year window. Edit End to override.',
                  foreground='#617183',wraplength=310).pack(anchor='w',pady=(1,2))

        self.bus_checks={col:tk.BooleanVar(value=col!='unclassified') for col in
                         ['residential','commercial','manufacturing','unclassified','total']}
        ttk.Label(opts,text='Distributed load categories:',style='Subheading.TLabel').pack(anchor='w',pady=(4,1))
        for col,txt in [('residential','Residential'),('commercial','Commercial'),
                        ('manufacturing','Manufacturing'),('total','Total feeder'),
                        ('unclassified','Unclassified')]:
            ttk.Checkbutton(opts,text=txt,variable=self.bus_checks[col],
                            command=self.request_redraw).pack(anchor='w')
        ttk.Label(opts,text='NASA irradiance to display:',style='Subheading.TLabel').pack(anchor='w',pady=(4,1))
        rr=ttk.Frame(opts);rr.pack(anchor='w')
        self.solar_checks={col:tk.BooleanVar(value=True) for col in ['GHI','DHI','DNI']}
        for col in self.solar_checks:
            ttk.Checkbutton(rr,text=col,variable=self.solar_checks[col],
                            command=self.request_redraw).pack(side=tk.LEFT,padx=(0,9))
        self.show_temp=tk.BooleanVar(value=False)
        ttk.Checkbutton(opts,text='Temperature (°C)',variable=self.show_temp,
                        command=self.request_redraw).pack(anchor='w',pady=2)

        actions=ttk.Frame(left);actions.pack(fill=tk.X,pady=8)
        ttk.Button(actions,text='Plot selected period',command=self.draw).pack(fill=tk.X,pady=2)
        ttk.Button(actions,text='Export PNG / SVG / plotted CSVs',command=self.export).pack(fill=tk.X,pady=2)
        self.summary=tk.StringVar(value='Import a network ZIP and choose a feeder.\nNASA CSVs can be added separately.')
        ttk.Label(left,textvariable=self.summary,wraplength=345,foreground='#526174',justify='left').pack(fill=tk.X,pady=6)

        self.fig=Figure(figsize=(10,7),dpi=100)
        self.ax=self.fig.add_subplot(111)
        self.ax.text(.5,.5,'Import a distributed-load ZIP to begin',va='center',ha='center',transform=self.ax.transAxes,fontsize=13)
        self.ax.axis('off')
        self.fig.tight_layout()
        self.canvas=FigureCanvasTkAgg(self.fig,master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH,expand=True)
        toolbar=NavigationToolbar2Tk(self.canvas,right,pack_toolbar=False)
        toolbar.update();toolbar.pack(fill=tk.X,side=tk.BOTTOM)
        self.status=tk.StringVar(value='Ready')
        ttk.Label(self,textvariable=self.status,anchor='w',relief=tk.SUNKEN).pack(side=tk.BOTTOM,fill=tk.X)
        for w in (mode,det,pre):w.bind('<<ComboboxSelected>>',lambda e:self.request_redraw())
        per.bind('<<ComboboxSelected>>',self.on_period_changed)

    def _sidebar_wheel(self,event):
        """Scroll only when the mouse is inside the left control sidebar."""
        canvas=self.left_canvas
        x,y=event.x_root,event.y_root
        if not (canvas.winfo_rootx() <= x < canvas.winfo_rootx()+canvas.winfo_width() and
                canvas.winfo_rooty() <= y < canvas.winfo_rooty()+canvas.winfo_height()):
            return
        if getattr(event,'num',None)==4:units=-3
        elif getattr(event,'num',None)==5:units=3
        else:units=int(-event.delta/120)*3 if event.delta else 0
        canvas.yview_scroll(units,'units')

    def _work(self,label,fn,callback):
        self.status.set(label+'…')
        def runner():
            try:self.queue.put(('success',label,callback,fn()))
            except Exception as e:self.queue.put(('error',label,str(e)))
        threading.Thread(target=runner,daemon=True).start()

    def _drain_queue(self):
        try:
            while True:
                event=self.queue.get_nowait()
                if event[0]=='success':
                    _,label,cb,data=event
                    try:cb(data)
                    except Exception as e:messagebox.showerror('Unexpected result',str(e))
                    self.status.set(label+' — complete')
                else:
                    _,label,error=event
                    self.status.set(label+' — failed')
                    messagebox.showerror('Import error',error)
        except queue.Empty:pass
        self._queue_after_id=self.after(125,self._drain_queue)

    def add_zips(self):
        files=filedialog.askopenfilenames(title='Open one or more distributed network ZIPs',filetypes=[('ZIP archives','*.zip')])
        if not files:return
        count=0
        for path in files:
            try:entries=discover_networks(path)
            except Exception as e:
                messagebox.showerror('Invalid ZIP',f'{path}\n{e}');continue
            for entry in entries:
                count+=1
                name=Path(entry['key']).name or Path(path).stem
                iid=f'net_{len(self.networks)+1}'
                self.networks[iid]={'zip':path,'entry':entry,'name':name}
                self.net_tree.insert('','end',iid=iid,values=(name,'—'))
        if not count:messagebox.showwarning('No feeders found','ZIP needs load_profile.csv and bus_assignments_used.csv in each network folder.')
        elif not self.net_tree.selection():
            iid=self.net_tree.get_children()[0];self.net_tree.selection_set(iid);self.choose_network()

    def add_prepared_csv(self):
        path=filedialog.askopenfilename(title='Import a previously aggregated CSV',filetypes=[('CSV files','*.csv')])
        if not path:return
        iid=f'net_{len(self.networks)+1}'
        self.networks[iid]={'csv':path,'name':Path(path).stem}
        self.net_tree.insert('','end',iid=iid,values=(Path(path).stem,'—'))
        self.net_tree.selection_set(iid);self.choose_network()

    def choose_network(self,event=None):
        sel=self.net_tree.selection()
        if not sel:return
        iid=sel[0];info=self.networks[iid]
        if iid in self.network_cache:
            self._set_network(iid,self.network_cache[iid]);return
        def job():
            if 'csv' in info:
                data=load_aggregated_csv(info['csv']);meta={'aggregated_hours':len(data),'start':str(data.index.min()),'end':str(data.index.max())}
            else:data,meta=aggregate_distributed(info['zip'],info['entry'])
            return data,meta
        def done(result):
            self.network_cache[iid]=result
            self._set_network(iid,result)
        self._work('Loading '+info['name'],job,done)

    def _set_network(self,iid,result):
        self.active_network=iid
        self.load_current,meta=result
        self.net_tree.set(iid,'hours',f'{len(self.load_current):,}')
        start,end=self.load_current.index.min(),self.load_current.index.max()
        self.start_date.set(str(start.date()))
        self._range_is_custom=False
        self._set_default_end()
        self.summary.set(f"Network: {self.networks[iid]['name']}\n{len(self.load_current):,} hours · {start} to {end}\n"
                         f"Load categories: {meta.get('load_sectors','provided CSV')}")
        self.draw(silent=True)

    def add_nasa(self):
        paths=filedialog.askopenfilenames(title='Select NASA CSV files for ONE location (multiple monthly files OK)',filetypes=[('NASA CSV','*.csv')])
        if not paths:return
        default=Path(paths[0]).parent.name or Path(paths[0]).stem
        location=simpledialog.askstring('NASA location','Name this NASA location (e.g. Bilbao):',initialvalue=default,parent=self)
        if not location:return
        location=location.strip()
        if location in self.solar_groups:
            messagebox.showerror('Duplicate name','Choose a distinct location name');return
        mode=self.time_mode.get()
        def done(result):
            self.solar_groups[location]=result
            self.nasa_combo['values']=list(self.solar_groups)
            self.nasa_location.set(location)
            self.solar_current=result
            if self.load_current is None:
                self.mode.set('NASA')
                self.start_date.set(str(result.index.min().date()))
                self._range_is_custom=False
                self._set_default_end()
            self.draw(silent=True)
        self._work(f'Importing NASA site {location}',lambda:merge_nasa_monthly(paths,time_mode=mode),done)

    def choose_solar(self,event=None):
        self.solar_current=self.solar_groups.get(self.nasa_location.get())
        self.draw(silent=True)

    def use_all_dates(self):
        """Set range from available data; Compare mode uses the overlapping span."""
        mode=self.mode.get()
        frames=([self.load_current] if mode=='Load' else
                [self.solar_current] if mode=='NASA' else
                [self.load_current,self.solar_current])
        frames=[f for f in frames if f is not None and not f.empty]
        if not frames:
            messagebox.showinfo('No data','Import a distributed network or NASA data first')
            return
        if mode=='Compare' and len(frames)==2:
            beginning=max(f.index.min() for f in frames)
            end=min(f.index.max() for f in frames)
            if beginning>end:
                messagebox.showwarning('No overlapping dates','Load and NASA data do not overlap.')
                return
        else:
            beginning=min(f.index.min() for f in frames)
            end=max(f.index.max() for f in frames)
        self.start_date.set(str(beginning.date()))
        self.end_date.set(str(end.date()))
        self._range_is_custom=True
        self.request_redraw()

    def _set_default_end(self):
        try:
            self.end_date.set(default_end_date(self.start_date.get(),self.period.get()))
        except (ValueError,TypeError):
            pass

    def on_period_changed(self,event=None):
        """Select one rolling calendar period and show its recommended resolution."""
        self._range_is_custom=False
        # A new period uses its own default resolution. The user can then
        # choose Hourly, Daily, Weekly or Monthly explicitly in Detail.
        self.detail.set('Default')
        self._set_default_end()
        self.request_redraw()

    def _on_start_changed(self):
        if not self._range_is_custom:
            self._set_default_end()
        self.request_redraw()

    def _on_end_changed(self):
        self._range_is_custom=True
        self.request_redraw()

    def move_date(self,n):
        try:
            start=pd.Timestamp(self.start_date.get()).normalize()
            end=pd.Timestamp(self.end_date.get()).normalize()
            if end<start:raise ValueError('End date precedes start date')
        except Exception:
            messagebox.showerror('Date error','Please enter valid start and end dates as YYYY-MM-DD')
            return
        p=self.period.get()
        offset={'Daily':pd.DateOffset(days=n),'Weekly':pd.DateOffset(weeks=n),
                'Monthly':pd.DateOffset(months=n),'Yearly':pd.DateOffset(years=n)}[p]
        self.start_date.set(str((start+offset).date()))
        if self._range_is_custom:
            self.end_date.set(str((end+offset).date()))
        else:
            self._set_default_end()
        self.request_redraw()

    def request_redraw(self):
        """Redraw automatically after the user toggles a control.

        A short debounce combines rapid clicks into a single Matplotlib render.
        """
        if self._pending_redraw is not None:
            self.after_cancel(self._pending_redraw)
        self._pending_redraw=self.after(90,self._draw_pending)

    def _draw_pending(self):
        self._pending_redraw=None
        self.draw(silent=True)

    def draw(self,silent=False):
        if self.load_current is None and self.mode.get()!='NASA':return
        if self.solar_current is None and self.mode.get()!='Load':
            if not silent:messagebox.showinfo('NASA data needed','Import NASA POWER CSV files first')
            return
        try:
            tables=plot_dashboard(self.fig,load=self.load_current,nasa=self.solar_current,
                period=self.period.get(),start_date=self.start_date.get(),
                end_date=self.end_date.get(),mode=self.mode.get(),
                detail=self.detail.get(),presentation=self.presentation.get(),
                load_cols=tuple(k for k,v in self.bus_checks.items() if v.get()),
                sun_cols=tuple(k for k,v in self.solar_checks.items() if v.get()),
                show_temperature=self.show_temp.get())
            self.plot_tables=tables
            self.canvas.draw_idle()
            self.status.set(f'Plotted {self.start_date.get()} through {self.end_date.get()} '
                            f'— {self.period.get()} / {self.detail.get()}')
        except Exception as e:
            self.status.set(str(e))
            if not silent:messagebox.showerror('Cannot draw plot',str(e))

    def export(self):
        if not self.plot_tables:
            messagebox.showinfo('Nothing to export','Plot a period first');return
        path=filedialog.askdirectory(title='Export chart images and data tables')
        if not path:return
        folder=Path(path)
        stem=(f"{self.mode.get().lower()}_{self.period.get().lower()}_"
              f"{self.start_date.get()}_to_{self.end_date.get()}")
        self.fig.savefig(folder/(stem+'.png'),dpi=200,facecolor='white')
        self.fig.savefig(folder/(stem+'.svg'),facecolor='white')
        for name,table in self.plot_tables.items():
            table.to_csv(folder/(stem+'_'+name+'.csv'),float_format='%.6f')
        self.status.set('Exported '+str(folder))
        messagebox.showinfo('Export complete',f'Saved PNG, SVG and {len(self.plot_tables)} CSV table(s) to:\n{folder}')


if __name__=='__main__':
    app=Plotter()
    app.mainloop()
