from prepare import *
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import calendar
D=pd.date_range('2021-01-01',periods=8760,freq='h');S=D.get_loc(pd.Timestamp('2021-07-01'));E=S+336
B={name:np.flatnonzero(np.r_[True,a[1:]!=a[:-1],True]) for name,f in [('Daily','D'),('Weekly','W-SUN'),('Monthly','M')] for a in [D.to_period(f)]}
season=[('HourOfDay',D.hour,'Hour of day'),('DayOfWeek',D.dayofweek,'Weekday'),('WeekOfYear',D.isocalendar().week.to_numpy(dtype=int),'ISO week of year'),('MonthOfYear',D.month,'Calendar month')]
palette=['ffffff','16374a','007f75','be5527','8055a8','397abb','59717c','dbe4e8','f0f4f5','b64857','92a6aa','a6b7bc','c9d5d7','e6edef','393c45','607479']
RGB=[v for c in palette for v in bytes.fromhex(c)]
@lru_cache(None)
def font(n,b=False):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if b else '')+'.ttf',n)
def write(d,x,y,t,n=20,ix=1,b=False,anc=None):d.text((x,y),str(t),font=font(n,b),fill=ix,anchor=anc)
def nums(v):return f'{v:,.0f}' if abs(v)>=1000 else f'{v:.3g}'
def time_ticks(idx):
 n=len(idx);pos=np.unique(np.linspace(0,n-1,min(8,n)).round().astype(int));fmt='%d %b' if idx[-1]-idx[0]>24 else '%d %b %Hh'
 if idx[-1]-idx[0]<30:fmt='%H:%M'
 return list(zip(pos,[D[idx[i]].strftime(fmt) for i in pos]))
def nice_name(name):return name.replace('__',' / ').replace('_',' + ')
def render(path,ds,title,subtitle,ys,names,yunit,xtitle,ticks,meta,kind='line',colors=None,zero=False):
 # Single plotting rectangle. Each file carries machine-readable proof of its input range.
 im=Image.new('P',(1680,650),0);im.putpalette(RGB);d=ImageDraw.Draw(im)
 write(d,48,20,ds.replace('_',' '),23,2,True);write(d,48,50,title,31,1,True);write(d,48,93,subtitle,20,6)
 colors=colors or ([1,2] if len(names)==2 else [1,3,2,4,5]);x=50;y=136
 for j,name in enumerate(names):
  s=nice_name(name);sw=d.textlength(s,font=font(18))+73
  if x+sw>1645:x=50;y+=28
  d.line((x,y+11,x+30,y+11),fill=colors[j],width=4);write(d,x+40,y,s,18);x+=sw
 x0,x1,y0,y1=119,1625,220,553
 write(d,49,188,yunit,19,6,True)
 ys=np.atleast_2d(ys);lo,hi=float(ys.min()),float(ys.max())
 if zero:lo=min(lo,0);hi=max(hi,0)
 if lo==hi:pad=max(abs(hi)*.05,0.5);lo-=pad;hi+=pad
 else:pad=(hi-lo)*.055;hi+=pad;lo-=pad
 if kind=='hist':lo=0
 for v in np.linspace(lo,hi,5):
  yp=round(y1-(v-lo)/(hi-lo)*(y1-y0));d.line((x0,yp,x1,yp),fill=7,width=1);write(d,x0-12,yp,nums(v),19,6,anc='rm')
 if lo<0<hi:d.line((x0,y1+lo/(hi-lo)*(y1-y0),x1,y1+lo/(hi-lo)*(y1-y0)),fill=10,width=2)
 n=ys.shape[1]
 for arr,col in zip(ys,colors):
  xx=(np.arange(n)+.5)/n if kind=='hist' else np.linspace(0,1,n)
  xx=x0+xx*(x1-x0);yy=y1-(arr-lo)/(hi-lo)*(y1-y0)
  if kind=='hist':
   dx=(x1-x0)/n*.44
   for a,b in zip(xx,yy):d.rectangle((round(a-dx),round(b),round(a+dx),y1),fill=col)
  else:d.line(np.rint(np.column_stack([xx,yy])).astype('i4').ravel().tolist(),fill=col,width=3)
 for j,label in ticks:
  xp=x0+((j+.5)/n if kind=='hist' else j/max(n-1,1))*(x1-x0);d.line((xp,y1,xp,y1+5),fill=6);write(d,xp,y1+10,label,18,6,anc='ma')
 write(d,(x0+x1)//2,600,xtitle,19,1,True,anc='ma')
 info=PngImagePlugin.PngInfo();info.add_text('C2_plot',json.dumps(meta,separators=(',',':')))
 im.save(path,compress_level=3,bits=4,pnginfo=info)
def summarize(a,key,energy=False):
 ix=B[key];s=np.add.reduceat(a,ix[:-1],axis=1);return s if energy else s/np.diff(ix)
def generate(ds,tag,arr,names,folder,u,compare):
 folder.mkdir(exist_ok=True,parents=True)
 def emit(stem,title,sub,v,legend,vu,xt,ticks,st=0,en=8760,**kwargs):
  meta=dict(dataset=ds,config=tag,chart=stem,start=str(D[st]),end=str(D[en-1]),input_hours=int(en-st),axes=1)
  render(folder/(stem+'.png'),ds,title,sub,v,legend,vu,xt,ticks,meta,**kwargs)
 heading='Actual, ARIMA and three leading candidates' if compare and ds!='Bus_01' else ('Actual and ARIMA baseline' if compare else 'Actual and forecast')
 name='Full 2021 evaluation'
 emit('Forecast_Hourly_14Days',heading,'Hourly power   /   01–14 July 2021   /   336 observations',arr[:,S:E],names,u,'Date in 2021',time_ticks(np.arange(S,E)),S,E)
 for key,ix in B.items():
  for energy in [False,True]:
   v=summarize(arr,key,energy);q='total energy' if energy else 'average power';vu=u.replace('kW','kWh') if energy else u
   sub=key+' '+q+'   /   January–December 2021'+('   /   boundary weeks: 72 and 120 h' if key=='Weekly' else '')
   emit('Forecast_'+key+'_2021_'+('kWh' if energy else 'kW'),heading,sub,v,names,vu,'Period start in 2021',time_ticks(ix[:-1]))
 err=arr[0]-arr[1:];ab=np.abs(err).mean(axis=0)
 for key,ix in B.items():
  va=np.add.reduceat(ab,ix[:-1])/np.diff(ix);valid=np.where(np.diff(ix)==168)[0] if key=='Weekly' else np.arange(len(va))
  for wh,i in [('High',valid[np.argmax(va[valid])]),('Low',valid[np.argmin(va[valid])])]:
   st,en=int(ix[i]),int(ix[i+1]);emit('Zoom_'+wh+'MAE_'+key,wh+'est-error '+{'Daily':'day','Weekly':'week','Monthly':'month'}[key]+' · hourly detail',f'Additional error-selected window   /   {D[st]:%d %b} – {D[en-1]:%d %b %Y}   /   MAE {nums(va[i])} {u}',arr[:,st:en],names,u,'Time in selected period',time_ticks(np.arange(st,en)),st,en)
 if compare:return
 e=err[0];desc=nice_name(tag)
 for absolute in [False,True]:
  what='Absolute error' if absolute else 'Signed residual';v=np.abs(e) if absolute else e;col=[2 if absolute else 9]
  emit(('Absolute_Error' if absolute else 'Residual')+'_Hourly_14Days',what,desc+'   /   01–14 July 2021   /   336 observations',v[S:E],[what],u,'Date in 2021',time_ticks(np.arange(S,E)),S,E,colors=col,zero=True)
  emit(('Absolute_Error' if absolute else 'Residual')+'_Weekly_Mean','Weekly mean '+what.lower(),desc+'   /   complete 2021   /   Monday–Sunday weeks',summarize(v[None,:],'Weekly'),[what],u,'Week start in 2021',time_ticks(B['Weekly'][:-1]),colors=col,zero=True)
 hist,edges=np.histogram(e,bins=40);mid=(edges[1:]+edges[:-1])/2
 emit('Residual_Distribution_2021','Hourly residual distribution',desc+'   /   full year 2021   /   8,760 residuals',hist,['Hourly observations'],'Number of hours','Actual minus forecast ('+u+')',[(i,nums(mid[i])) for i in [0,8,16,24,32,39]],kind='hist',colors=[5],zero=True)
 for tag2,groups,xt in season:
  labs=sorted(set(groups));v=np.asarray([arr[:,groups==j].mean(axis=1) for j in labs]).T
  ticks=[(j,calendar.day_abbr[labs[j]] if tag2=='DayOfWeek' else calendar.month_abbr[labs[j]] if tag2=='MonthOfYear' else str(labs[j])) for j in (range(len(labs)) if len(labs)<=12 else np.unique(np.linspace(0,len(labs)-1,9).round().astype(int)))]
  emit('Seasonal_'+tag2,xt+' profile',desc+'   /   mean hourly power grouped over full 2021',v,names,u,xt,ticks)
def run(ds):
 selection=json.loads((TMP/'selection.json').read_text())[ds];folder=OUT/selection['folder']/'PNG';folder.mkdir(parents=True,exist_ok=True);u=selection['unit']
 ids=json.loads(Path('cache',ds+'.json').read_text());a=np.load(Path('cache',ds+'.npy'),mmap_mode='r');names=selection['names']
 generate(ds,'Main',a[[ids.index(n) for n in names]],names,folder/'Main_Comparison',u,True)
 for i,n in enumerate(ids[1:],1):generate(ds,n,a[[0,i]],['Actual',n],folder/n,u,False)
 print(ds,flush=True)
if __name__=='__main__':
 sel=json.loads((TMP/'selection.json').read_text())
 with ProcessPoolExecutor(max_workers=8) as pool:list(pool.map(run,sel))
