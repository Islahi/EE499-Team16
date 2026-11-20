"""GUI for the saved C2 2021 benchmark forecasts (no model rerun).

Open from C2_FullHistory_2021 beside data/ and results/.
Repository: https://github.com/Islahi/EE499-Team16.git
"""
from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.dates import num2date
import pandas as pd

from c2_plotter_core import C2Results, VIRTUAL, FORMATS, hourly_metrics, resample, window, available_root_candidates
from c2_plotter_ranking import Ranking, SORT_OPTIONS, pretty_number


class ForecastPlotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('EE499 Team 16 — C2 Forecast Viewer')
        self.geometry('1300x860')
        self.minsize(940,670)
        self.db=None
        self.ranker=None
        self._model_iid_to_key={}
        self.sort_by=tk.StringVar(value='RMSE (smallest)')
        self.rank_summary=tk.StringVar(value='Rankings use completed forecasts; lower error is better.')
        self.dataset=tk.StringVar(value='')
        self.bus=tk.StringVar(value='Total')
        self.resolution=tk.StringVar(value='Daily mean')
        self.begin=tk.StringVar(value='')
        self.end=tk.StringVar(value='')
        self.show_error=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='Select a C2 experiment folder containing results/ and data/.')
        self.note=tk.StringVar(value='')
        self.metrics=tk.StringVar(value='')
        self.current_export=None
        self.has_plot=False
        self._redraw_after_id=None
        self._redraw_preserve_xlim=False
        self._redraw_reorder=False
        self._redraw_choose_best=False
        self._redraw_suspended=True
        self._build()
        # Date entries update while typing, so redraw only after a short pause.
        self.begin.trace_add('write',lambda *_:self._schedule_plot(reorder=True))
        self.end.trace_add('write',lambda *_:self._schedule_plot(reorder=True))
        self._redraw_suspended=False
        for root in available_root_candidates(Path(__file__).parent):
            try:
                self.load_root(root)
                break
            except (OSError,ValueError):
                pass

    def _build(self):
        page=ttk.Frame(self,padding=12)
        page.pack(fill='both',expand=True)
        header=ttk.Frame(page)
        header.pack(fill='x',pady=(0,8))
        ttk.Button(header,text='Open C2 experiment folder…',command=self.choose_root).pack(side='left')
        self.root_label=ttk.Label(header,text='No folder selected',width=85)
        self.root_label.pack(side='left',padx=12)
        line=ttk.Frame(page)
        line.pack(fill='x',pady=(0,6))
        ttk.Label(line,text='Dataset').pack(side='left')
        self.dataset_box=ttk.Combobox(line,textvariable=self.dataset,state='readonly',width=48)
        self.dataset_box.pack(side='left',padx=(5,16),fill='x',expand=True)
        self.dataset_box.bind('<<ComboboxSelected>>',lambda e:self.dataset_changed())
        ttk.Label(line,text='Bus').pack(side='left')
        self.bus_box=ttk.Combobox(line,textvariable=self.bus,state='readonly',width=12)
        self.bus_box.pack(side='left',padx=(5,16))
        self.bus_box.bind('<<ComboboxSelected>>',lambda e:self._bus_changed())
        ttk.Label(line,text='Resolution').pack(side='left')
        self.res_box=ttk.Combobox(line,textvariable=self.resolution,state='readonly',width=23,
                                 values=list(FORMATS))
        self.res_box.pack(side='left',padx=(5,0))
        self.res_box.bind('<<ComboboxSelected>>',lambda e:self._schedule_plot())
        dates=ttk.Frame(page)
        dates.pack(fill='x',pady=(0,6))
        ttk.Label(dates,text='From').pack(side='left')
        ttk.Entry(dates,textvariable=self.begin,width=20).pack(side='left',padx=(5,12))
        ttk.Label(dates,text='To').pack(side='left')
        ttk.Entry(dates,textvariable=self.end,width=20).pack(side='left',padx=(5,12))
        ttk.Label(dates,text='YYYY-MM-DD (or YYYY-MM-DD HH:MM)').pack(side='left',padx=(0,12))
        ttk.Button(dates,text='Full year',command=self.full_year).pack(side='right',padx=(4,0))
        ttk.Button(dates,text='First week',command=self.first_week).pack(side='right',padx=(4,0))
        ttk.Button(dates,text='First month',command=self.first_month).pack(side='right',padx=(4,0))
        ranking_bar=ttk.Frame(page)
        ranking_bar.pack(fill='x',pady=(0,3))
        ttk.Label(ranking_bar,text='Rank completed forecasts by').pack(side='left')
        self.sort_box=ttk.Combobox(ranking_bar,textvariable=self.sort_by,state='readonly',width=33,
                                  values=list(SORT_OPTIONS))
        self.sort_box.pack(side='left',padx=(6,12))
        self.sort_box.bind('<<ComboboxSelected>>',lambda e:self._sort_changed())
        ttk.Button(ranking_bar,text='Plot #1 (best)',command=self.plot_best).pack(side='left',padx=(0,9))
        ttk.Label(ranking_bar,text='Sort uses selected bus + date window; click a column heading to rank.',
                  foreground='#5c6571').pack(side='left')
        ttk.Label(page,text='Completed models (Ctrl+click for multiple overlays; highlighted row is plotted automatically)')\
           .pack(anchor='w')
        select_frame=ttk.Frame(page)
        select_frame.pack(fill='x',pady=(3,3))
        columns=['rank','config','rmse','mae','wape','mase','bias','smape','fit','predict','warnings']
        self.models=ttk.Treeview(select_frame,columns=columns,show='headings',selectmode='extended',height=7)
        column_info={
            'rank':('#',40,None),
            'config':('Model / seasonality',325,None),
            'rmse':('RMSE',85,'RMSE (smallest)'),
            'mae':('MAE',85,'MAE (smallest)'),
            'wape':('WAPE %',79,'WAPE (smallest)'),
            'mase':('MASE',68,'MASE (smallest)'),
            'bias':('Bias',87,'|Bias| (closest to zero)'),
            'smape':('sMAPE %',83,'sMAPE (smallest)'),
            'fit':('Fit s',74,'Fit time (fastest)'),
            'predict':('Predict s',77,'Forecast time (fastest)'),
            'warnings':('Warnings',68,'Fewest warnings'),
        }
        for name in columns:
            label,width,choice=column_info[name]
            self.models.heading(name,text=label,command=(lambda c=choice:self._click_column(c)) if choice else '')
            self.models.column(name,width=width,minwidth=max(45,width//2),stretch=(name=='config'),
                               anchor='w' if name=='config' else 'e')
        sb=ttk.Scrollbar(select_frame,orient='vertical',command=self.models.yview)
        self.models.configure(yscrollcommand=sb.set)
        self.models.pack(side='left',fill='both',expand=True)
        sb.pack(side='left',fill='y')
        self.models.bind('<<TreeviewSelect>>',lambda e:self._schedule_plot())
        buttons=ttk.Frame(select_frame)
        buttons.pack(side='left',padx=(10,0),fill='y')
        ttk.Button(buttons,text='Refresh plot',command=lambda:self.plot(interactive=True)).pack(fill='x',pady=(0,4))
        ttk.Button(buttons,text='Save PNG…',command=self.save_png).pack(fill='x',pady=(0,4))
        ttk.Button(buttons,text='Export current CSV…',command=self.export_csv).pack(fill='x',pady=(0,4))
        ttk.Button(buttons,text='Zoom in',command=lambda:self.zoom(.7)).pack(fill='x',pady=(0,4))
        ttk.Button(buttons,text='Zoom out',command=lambda:self.zoom(1.5)).pack(fill='x')
        ttk.Checkbutton(buttons,text='Show error panel',variable=self.show_error,
                        command=lambda:self._schedule_plot(preserve_xlim=True)).pack(anchor='w',pady=(6,0))
        ttk.Label(buttons,text='Updates automatically',foreground='#39754b').pack(anchor='w',pady=(3,0))
        ttk.Label(page,textvariable=self.rank_summary,wraplength=1200,foreground='#39754b')\
           .pack(anchor='w',pady=(0,4))
        ttk.Label(page,textvariable=self.note,wraplength=1200,foreground='#9b5f12').pack(anchor='w',pady=(0,4))
        ttk.Label(page,textvariable=self.metrics,wraplength=1200).pack(anchor='w',pady=(0,4))
        self.fig=Figure(figsize=(12,5.5),dpi=100)
        self.ax=self.fig.add_subplot(111)
        self.ax.set_title('Select a dataset and forecast; the plot updates automatically')
        self.ax.grid(alpha=.25)
        self.canvas=FigureCanvasTkAgg(self.fig,master=page)
        self.canvas.get_tk_widget().pack(fill='both',expand=True)
        self.toolbar=NavigationToolbar2Tk(self.canvas,page,pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(fill='x',pady=(2,0))
        self.canvas.mpl_connect('scroll_event',self.scroll)
        ttk.Label(page,textvariable=self.status,anchor='w').pack(fill='x',pady=(5,0))

    def _schedule_plot(self,preserve_xlim=False,reorder=False,choose_best=False):
        """Debounce control changes; keep a usable zoom when toggling error panel."""
        if self._redraw_suspended or self.db is None:
            return
        if self._redraw_after_id is None:
            self._redraw_preserve_xlim=bool(preserve_xlim)
        else:
            self._redraw_preserve_xlim=self._redraw_preserve_xlim and bool(preserve_xlim)
            self.after_cancel(self._redraw_after_id)
        self._redraw_reorder |= bool(reorder)
        self._redraw_choose_best |= bool(choose_best)
        self._redraw_after_id=self.after(400,self._run_scheduled_plot)

    def _run_scheduled_plot(self):
        self._redraw_after_id=None
        preserve=self._redraw_preserve_xlim
        rerank=self._redraw_reorder
        choose_best=self._redraw_choose_best
        self._redraw_preserve_xlim=False
        self._redraw_reorder=False
        self._redraw_choose_best=False
        if rerank:
            try:
                self._populate_ranked_models(choose_best=choose_best)
            except Exception as exc:
                self.status.set(f'Cannot refresh ranking: {exc}')
                return
        self.plot(interactive=False,preserve_xlim=preserve)

    def _bus_changed(self):
        self._refresh_note()
        self._schedule_plot(reorder=True)

    def _sort_changed(self):
        # Changing the ranking metric automatically selects and plots the best.
        self._schedule_plot(reorder=True,choose_best=True)

    def _click_column(self,choice):
        if choice:
            self.sort_by.set(choice)
            self._sort_changed()

    def plot_best(self):
        children=self.models.get_children()
        if not children:return
        self.models.selection_set(children[0])
        self.models.focus(children[0]);self.models.see(children[0])
        self._schedule_plot()

    def _populate_ranked_models(self,choose_best=False):
        if not self.db:return
        dataset,bus=self.dataset.get(),self.bus.get()
        options=self.db.options(dataset)
        old_keys=set(self.selected_models())
        rows,failures=self.ranker.rank(dataset,bus,self.sort_by.get(),self.begin.get(),self.end.get())
        was=self._redraw_suspended
        self._redraw_suspended=True
        try:
            all_ids=self.models.get_children()
            if all_ids:self.models.delete(*all_ids)
            self._model_iid_to_key.clear()
            for idx,r in enumerate(rows,1):
                iid=f'forecast{idx}'
                self._model_iid_to_key[iid]=r.key
                values=(idx,r.key,pretty_number(r.rmse),pretty_number(r.mae),
                        pretty_number(r.wape),pretty_number(r.mase,3),
                        pretty_number(r.bias),pretty_number(r.smape),
                        pretty_number(r.fit),pretty_number(r.predict),
                        pretty_number(r.warnings,0))
                self.models.insert('', 'end', iid=iid,values=values)
            candidates=[iid for iid,key in self._model_iid_to_key.items() if key in old_keys]
            if choose_best or not candidates:
                candidates=list(self._model_iid_to_key)[:1]
            if candidates:
                self.models.selection_set(candidates)
                self.models.focus(candidates[0]);self.models.see(candidates[0])
        finally:
            self._redraw_suspended=was
        first=rows[0] if rows else None
        column=SORT_OPTIONS[self.sort_by.get()]
        best=('Best: '+first.key+' — '+column+' '+pretty_number(first.metric(column),3)) if first else 'No rankable configurations'
        note='Date window' if self.begin.get().strip() or self.end.get().strip() else 'Full forecast year'
        self.rank_summary.set(f'{note} | {len(rows)} ranked, {len(failures)} unavailable | {best}'+
                              (' | MASE uses a common weekly training baseline.' if column=='MASE' else '')+
                              (' | Bias ranked by absolute value.' if column=='Bias' else '')+
                              (' | Category-derived timing sums three model runs.' if dataset==VIRTUAL and column in ('Fit','Predict','Total') else ''))
        if failures:self.status.set('Some results cannot be ranked: '+failures[0])

    def _clear_plot(self, message):
        self.fig.clear()
        self.ax=self.fig.add_subplot(111)
        self.ax.set_title(message)
        self.ax.grid(alpha=.25)
        self.canvas.draw_idle()
        self.current_export=None
        self.has_plot=False
        self.metrics.set('')

    def choose_root(self):
        directory=filedialog.askdirectory(title='Choose C2_FullHistory_2021 folder (contains data/ and results/)')
        if directory:
            try:self.load_root(directory)
            except Exception as e:messagebox.showerror('Cannot read results',str(e))

    def load_root(self,path):
        db=C2Results(path)
        if self._redraw_after_id is not None:
            self.after_cancel(self._redraw_after_id)
            self._redraw_after_id=None
        self._redraw_suspended=True
        self.db=db
        self.ranker=Ranking(db)
        self.root_label.configure(text=str(db.root))
        datasets=db.datasets()
        self.dataset_box['values']=datasets
        # Prefer the actual direct distributed benchmark when it exists; reconstructed version is user-selectable.
        name='Distributed_15Bus_Load' if 'Distributed_15Bus_Load' in datasets else datasets[0]
        self.dataset.set(name)
        self.dataset_changed()
        self._redraw_suspended=False
        self._schedule_plot()
        self.status.set(f'Loaded {sum(len(j) for k,j in db.jobs.items() if k!=VIRTUAL)} completed forecasts. '
                        f'Category-derived runs available: {len(db.options(VIRTUAL)) if db.has_network_data else 0}.')

    def dataset_changed(self):
        if not self.db:return
        name=self.dataset.get()
        names=self.db.bus_options(name)
        self.bus_box['values']=names
        self.bus.set(names[0])
        self._refresh_note()
        self._populate_ranked_models(choose_best=True)
        if self.db.options(name):
            self._schedule_plot()
        else:
            self._clear_plot('No completed matching model + seasonality forecasts for this dataset')
            self.status.set('No complete matching forecasts. Category-derived mode needs completed residential, '
                            'commercial and manufacturing results with the same model and seasonality.')

    def _refresh_note(self):
        if self.dataset.get()==VIRTUAL:
            self.note.set('CATEGORY-DERIVED RECONSTRUCTION: Bus forecasts are computed from the SAVED three-category '
                          'predictions and fixed bus multipliers estimated using 2017–2020 training data. '
                          'These are NOT independently fitted bus-level forecasts. No forecasting models are rerun.')
        elif self.dataset.get()=='Distributed_15Bus_Load':
            self.note.set('DIRECT AGGREGATE FORECAST: This model was fitted to TOTAL 15-bus demand. '
                          'Its forecast cannot be broken into independently predicted bus loads. '
                          'Select the category-derived dataset above to display reconstructed buses.')
        elif self.dataset.get()=='Bilbao_Modelled_PV':
            self.note.set('Bilbao PV is MODELED from NASA POWER irradiance, not measured plant output. '
                          'The site is not distributed across individual buses in this benchmark.')
        else:self.note.set('Single directly fitted benchmark series. No separate bus-level forecast exists for this dataset.')

    def full_year(self):
        self.begin.set('');self.end.set('')

    def first_week(self):
        self.begin.set('2021-01-01');self.end.set('2021-01-07')

    def first_month(self):
        self.begin.set('2021-01-01');self.end.set('2021-01-31')

    def selected_models(self):
        return [self._model_iid_to_key[i] for i in self.models.selection()
                if i in self._model_iid_to_key]

    def plot(self, interactive=False, preserve_xlim=False):
        if not self.db:
            if interactive:
                messagebox.showinfo('No experiment folder','Open a C2_FullHistory_2021 folder first.')
            return
        selection=self.selected_models()
        if not selection:
            self.status.set('Select one or more completed forecasts from the model list.')
            if interactive:
                messagebox.showinfo('No forecast selected','Select one or more completed models.')
            return
        try:
            name,bus=self.dataset.get(),self.bus.get()
            series={key:window(self.db.series(name,key,bus),self.begin.get(),self.end.get())
                    for key in selection}
            common=next(iter(series.values())).index
            for frame in series.values():common=common.intersection(frame.index)
            if len(common)==0:raise ValueError('The selected model results have no common timestamps')
            all_hourly={key:frame.loc[common] for key,frame in series.items()}
            # The actual observations must be consistent across model runs.
            orig=next(iter(all_hourly.values()))['actual']
            for k,frame in all_hourly.items():
                if not np.allclose(frame.actual.to_numpy(),orig.to_numpy(),atol=1e-5,rtol=1e-8):
                    raise ValueError(f'Actual observations differ between model files ({k}); cannot overlay safely')
            fmt=self.resolution.get()
            old_limits=self.ax.get_xlim() if (preserve_xlim and self.has_plot) else None
            actual_plot=resample(pd.DataFrame({'actual':orig}),fmt)['actual']
            self.fig.clear()
            if self.show_error.get():
                axes=self.fig.subplots(2,1,sharex=True,gridspec_kw={'height_ratios':[3,1]})
                self.ax,err_ax=axes
            else:
                self.ax=self.fig.add_subplot(111);err_ax=None
            self.ax.plot(actual_plot.index,actual_plot.to_numpy(),label='Actual',color='black',
                         linewidth=1.75,zorder=9)
            metrics_list=[];csv=pd.DataFrame(index=common);csv.index.name='timestamp'
            csv['actual']=orig
            for key,frame in all_hourly.items():
                pred=resample(frame,fmt)['forecast'].reindex(actual_plot.index)
                line,=self.ax.plot(pred.index,pred.to_numpy(),label=key,linewidth=1.0,alpha=.9)
                if err_ax is not None:
                    e=frame['actual']-frame['forecast']
                    # Plot mean signed error for average aggregates, total signed energy for energy aggregates.
                    a=resample(pd.DataFrame({'error':e}),fmt)['error'].reindex(actual_plot.index)
                    err_ax.plot(a.index,a.to_numpy(),label=key,linewidth=.9,color=line.get_color())
                m=hourly_metrics(frame)
                metrics_list.append(f'{key}: RMSE {m["RMSE"]:,.3f}, MAE {m["MAE"]:,.3f}, '
                                    f'WAPE {m["WAPE (%)"]:.2f}%, Bias {m["Bias (A−F)"]:,.3f}')
                csv[f'forecast__{key}']=frame.forecast
                csv[f'actual_minus_forecast__{key}']=frame.actual-frame.forecast
            unit=self.db.unit(name,fmt)
            title=name+' — '+(bus if name==VIRTUAL else 'all measured hours')
            self.ax.set_title(title+' | '+fmt,fontsize=11)
            self.ax.set_ylabel(unit)
            self.ax.grid(alpha=.3)
            self.ax.legend(fontsize=8,loc='best')
            if err_ax is not None:
                err_ax.axhline(0,color='grey',lw=.7)
                err_ax.set_ylabel('A − F\n'+unit)
                err_ax.set_xlabel('Timestamp')
                err_ax.grid(alpha=.25)
            else:self.ax.set_xlabel('Timestamp')
            self.fig.autofmt_xdate()
            self.fig.tight_layout()
            if old_limits is not None:
                self.ax.set_xlim(old_limits)
            self.canvas.draw()
            self.toolbar.update();self.toolbar.push_current()
            self.metrics.set('Hourly metrics for selected dates (not resampled):  '+'   |   '.join(metrics_list[:4])+
                             (f'   |   +{len(metrics_list)-4} more models' if len(metrics_list)>4 else ''))
            self.current_export=csv.reset_index()
            self.has_plot=True
            self.status.set(f'{len(common):,} actual/forecast hourly pairs; plotted {len(selection)} models. '
                            'Mouse wheel: horizontal zoom. Toolbar: pan / box zoom. Export CSV saves all selected hours.')
        except Exception as exc:
            self.status.set(f'Could not update plot: {exc}')
            self.metrics.set('Fix the selected options or date range to redraw.')
            self.current_export=None
            if interactive:
                messagebox.showerror('Plotting failed',str(exc))

    def zoom(self,factor,center=None):
        if not self.has_plot:return
        l,r=self.ax.get_xlim()
        if center is None:center=(l+r)/2
        self.ax.set_xlim(center+(l-center)*factor,center+(r-center)*factor)
        self.canvas.draw_idle();self.toolbar.push_current()

    def scroll(self,event):
        if event.inaxes is None or not self.has_plot:return
        x=event.xdata if event.xdata is not None else None
        self.zoom(.7 if event.button=='up' else 1.5,x)

    def save_png(self):
        if not self.has_plot:return messagebox.showinfo('Nothing to save','Plot a forecast first.')
        filename=filedialog.asksaveasfilename(defaultextension='.png',filetypes=[('PNG image','*.png')],
                 initialfile='C2_actual_vs_forecast.png')
        if filename:self.fig.savefig(filename,dpi=170,bbox_inches='tight');self.status.set(f'Saved {filename}')

    def export_csv(self):
        if self.current_export is None:return messagebox.showinfo('Nothing to export','Plot a forecast first.')
        filename=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],
                 initialfile='C2_selected_hourly_comparison.csv')
        if filename:self.current_export.to_csv(filename,index=False);self.status.set(f'Exported {filename}')

if __name__=='__main__':
    app=ForecastPlotter()
    if len(sys.argv)>1:
        try:app.load_root(sys.argv[1])
        except Exception as e:messagebox.showerror('Cannot open supplied folder',str(e))
    app.mainloop()
