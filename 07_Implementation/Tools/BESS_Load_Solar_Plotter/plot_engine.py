"""Matplotlib plots of distributed feeder demand and NASA POWER radiation."""
from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from data_engine import slice_period, slice_date_range, aggregate_period, SOLAR_COLS

LOAD_COLORS = {'residential':'#1d77bd','commercial':'#e49b33',
               'manufacturing':'#369d79','unclassified':'#a78bba','total':'#323d4b'}
SUN_COLORS = {'GHI':'#df8538','DHI':'#3996bd','DNI':'#a96b39'}


def _bucket_average(frame, interval):
    if interval=='Hourly':return frame
    if interval=='Daily': key=frame.index.normalize()
    elif interval=='Weekly': key=frame.index.normalize()-pd.to_timedelta(frame.index.weekday,unit='d')
    elif interval=='Monthly': key=frame.index.to_period('M').to_timestamp()
    else:raise ValueError(interval)
    return frame.groupby(key).mean()


def interval_plan(period: str, detail: str) -> list[str]:
    """Resolve time-window choice and aggregation resolution independently.

    Default is a single plot: daily -> hourly, weekly -> daily,
    monthly -> weekly, yearly -> monthly. Any explicit resolution overrides
    the default, even for custom date ranges spanning multiple years.
    """
    defaults = {
        'Daily': 'Hourly',
        'Weekly': 'Daily',
        'Monthly': 'Weekly',
        'Yearly': 'Monthly',
    }
    resolutions = {'Hourly', 'Daily', 'Weekly', 'Monthly'}
    if period not in defaults:
        raise ValueError(f'Unknown plotting period: {period}')
    if detail == 'Default':
        return [defaults[period]]
    if detail not in resolutions:
        raise ValueError(f'Unknown plotting resolution: {detail}')
    return [detail]


def _load_data(frame, interval, presentation):
    if presentation=='Average power':
        out = _bucket_average(frame,interval)
        unit='kW'
    else:
        out=aggregate_period(frame,interval,quantity='load')
        unit='kW' if interval=='Hourly' else 'kWh'
    if presentation=='Normalized':
        out=out.div(out.max().replace(0,np.nan)).fillna(0.0)
        unit='Relative (0–1)'
    return out,unit


def _sun_data(frame,interval):
    out=aggregate_period(frame,interval,quantity='irradiance')
    unit='W/m²' if interval=='Hourly' else 'kWh/m²'
    return out,unit


def _axis_date_style(ax, interval, date_range):
    if interval=='Hourly':
        span=(date_range[1]-date_range[0]).days if date_range else 1
        if span<=3:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M'))
        elif span<=12:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        elif span<=45:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        else:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4,maxticks=11))
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    elif interval=='Daily':
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4,maxticks=9))
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    elif interval=='Weekly':
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=8))
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    else:
        # A multi-year selection needs visible year labels, not repeated Jan-Dec.
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4,maxticks=12))
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.grid(True,axis='y',alpha=.22)
    ax.tick_params(axis='x',rotation=15,labelsize=9)
    ax.spines[['top','right']].set_visible(False)


def _plot_load(ax,frame,interval,presentation,chosen):
    vals,unit=_load_data(frame,interval,presentation)
    cols=[c for c in chosen if c in vals]
    if not cols:
        ax.text(.5,.5,'Select one or more load categories',ha='center',va='center',transform=ax.transAxes)
        ax.set_axis_off()
        return vals.iloc[:,0:0]
    max_val=float(vals[cols].max().max()) if not vals.empty else 0.
    scale = 1000.0 if (unit=='kWh' and max_val >= 10000) else 1.0
    display_unit = 'MWh' if scale==1000 else unit
    for c in cols:
        ax.plot(vals.index,vals[c]/scale,lw=2.1 if c=='total' else 1.5,
                alpha=.95 if c=='total' else .85,label=c.title(),color=LOAD_COLORS.get(c))
    ax.set_ylabel(f'Load ({display_unit})')
    ax.set_title(f'Distributed load — {interval.lower()} view',fontsize=12,loc='left',fontweight='bold')
    ax.legend(loc='upper right',ncol=2,fontsize=9,frameon=False)
    _axis_date_style(ax,interval,(vals.index.min(),vals.index.max()))
    return vals[cols]


def _plot_sun(ax,frame,interval,chosen,temperature=False):
    vals,unit=_sun_data(frame,interval)
    cs=[c for c in chosen if c in vals]
    if not cs and not (temperature and 'T2M' in vals):
        ax.text(.5,.5,'Select GHI, DHI, DNI, or temperature',ha='center',va='center',transform=ax.transAxes)
        ax.set_axis_off()
        return vals.iloc[:,0:0]
    for c in cs:
        ax.plot(vals.index,vals[c],lw=1.75,label=c,color=SUN_COLORS.get(c))
    ax.set_ylabel(f'Irradiance ({unit})' if interval=='Hourly' else f'Irradiation ({unit})')
    ax.set_title(f'NASA solar — {interval.lower()} view',fontsize=12,loc='left',fontweight='bold')
    h,l=ax.get_legend_handles_labels()
    if temperature and 'T2M' in vals:
        ax2=ax.twinx()
        ax2.plot(vals.index,vals['T2M'],lw=1.2,alpha=.75,color='#bd4c77',ls='--',label='T2M')
        ax2.set_ylabel('Temperature (°C)',color='#bd4c77')
        h2,l2=ax2.get_legend_handles_labels()
        h+=h2;l+=l2
    if h:ax.legend(h,l,loc='upper right',ncol=min(4,len(h)),fontsize=9,frameon=False)
    _axis_date_style(ax,interval,(vals.index.min(),vals.index.max()))
    selected = cs + (['T2M'] if temperature and 'T2M' in vals else [])
    return vals[selected]


def plot_dashboard(fig:Figure, *, load:Optional[pd.DataFrame], nasa:Optional[pd.DataFrame],
                   period:str, selected:str|None=None, mode:str='Load',detail:str='Default',
                   load_cols:tuple=('residential','commercial','manufacturing','total'),
                   sun_cols:tuple=('GHI','DHI','DNI'), show_temperature:bool=False,
                   presentation:str='Energy', start_date:str|None=None,
                   end_date:str|None=None) -> dict[str,pd.DataFrame]:
    """Plot a single calendar period (legacy) or an inclusive arbitrary date range.

    Period controls the default *resolution*, not a date-window limit, when
    start_date/end_date are set. Returns only columns actually visible.
    """
    if (start_date is None) != (end_date is None):
        raise ValueError('Provide both start and end dates')
    if start_date is None and selected is None:
        raise ValueError('Select a date or an inclusive date range')
    if start_date is not None:
        # Validate once, even when the corresponding series is unavailable.
        slice_date_range(pd.DataFrame(index=pd.DatetimeIndex([])),start_date,end_date)
    def take_range(frame):
        return (slice_date_range(frame,start_date,end_date)
                if start_date is not None else slice_period(frame,period,selected))
    plots=[]
    if mode in ('Load','Compare'):
        if load is None:raise ValueError('Please import a distributed-network ZIP first')
        lf=take_range(load)
        if lf.empty:raise ValueError('No distributed load data between the selected dates')
    else:lf=None
    if mode in ('NASA','Compare'):
        if nasa is None:raise ValueError('Please import NASA POWER CSV files first')
        sf=take_range(nasa)
        if sf.empty:raise ValueError('No NASA POWER data between the selected dates')
    else:sf=None
    intervals=interval_plan(period,detail)
    for interval in intervals:
        if lf is not None:plots.append(('Load',interval,lf))
        if sf is not None:plots.append(('NASA',interval,sf))
    fig.clear()
    n=len(plots)
    if n==1:axs=[fig.add_subplot(111)]
    else:
        # Single-panel per data source; future multi-resolution layouts remain supported.
        cols=2 if n==4 else 1
        rows=(n+cols-1)//cols
        axs=[fig.add_subplot(rows,cols,i+1) for i in range(n)]
    result={}
    for ax,(kind,interval,data) in zip(axs,plots):
        if kind=='Load':
            out=_plot_load(ax,data,interval,presentation,load_cols)
        else:
            out=_plot_sun(ax,data,interval,sun_cols,show_temperature)
        result[kind.lower()+'_'+interval.lower()]=out
    fig.set_facecolor('#ffffff')
    fig.subplots_adjust(left=.085,right=.91,bottom=.13,top=.92,hspace=.46,wspace=.27)
    # Multi-month/year windows often start or end partway through a calendar
    # bucket. Such totals are correct for the selected window, but should not
    # be mistaken for complete-month/complete-week totals.
    if start_date is not None and any(k.endswith(('_weekly','_monthly')) for k in result):
        first, last = pd.Timestamp(start_date), pd.Timestamp(end_date)
        partial = (first.day != 1 or last.day != last.days_in_month)
        if partial:
            fig.text(.5,.018,'Note: first/last month may be partial; totals include only selected dates.',
                     ha='center',va='center',fontsize=8,color='#687383')
    return result
