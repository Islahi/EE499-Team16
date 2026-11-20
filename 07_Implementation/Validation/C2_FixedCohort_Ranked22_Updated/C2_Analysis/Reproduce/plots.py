"""Build dataset-specific PNG sheets from exact samples. Aggregations use sample count and a one-hour step."""
from numerical import *
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ProcessPoolExecutor
import calendar,os
from functools import lru_cache
DTS=pd.date_range('2021-01-01',periods=8760,freq='h')
def boundaries(f):
 labels=DTS.to_period(f);return np.flatnonzero(np.r_[True,labels[1:]!=labels[:-1],True])
B={x:boundaries(y) for x,y in [('Daily','D'),('Weekly','W-SUN'),('Monthly','M')]}
styles=['#25374b','#008a83','#d36b25','#8467aa','#4878b7','#b43d58'];ink='#172c40';gray='#637789'
@lru_cache(None)
def font(sz,bold=False):return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',sz)
def txt(p,xy,s,sz=15,color=ink,bold=False,anchor=None):p.text(xy,str(s),font=font(sz,bold),fill=color,anchor=anchor)
def vals(ys,name,energy=False):
 ix=B[name];v=np.add.reduceat(ys,ix[:-1],axis=1);return v if energy else v/np.diff(ix)
def num(x):return f'{x:,.0f}' if abs(x)>=100 else f'{x:.3g}'
def panel(draw,box,ys,title,unit,ends,colors=None,hist=False):
 x,y,w,h=box;left=x+75;right=x+w-17;top=y+48;bottom=y+h-29
 txt(draw,(x+9,y+4),title,17,bold=True);txt(draw,(x+10,y+28),unit,13,gray)
 ys=np.atleast_2d(ys);vmin=min(0,float(ys.min()));vmax=max(0,float(ys.max()))
 if vmax-vmin<1e-12:vmax=vmin+1
 for v in np.linspace(vmin,vmax,4):
  yp=round(bottom-(bottom-top)*(v-vmin)/(vmax-vmin));draw.line((left,yp,right,yp),fill='#d9e3e9');txt(draw,(left-6,yp),num(v),12,gray,anchor='rm')
 for arr,col in zip(ys,colors or styles):
  xx=np.linspace(left,right,len(arr));yy=bottom-(bottom-top)*(arr-vmin)/(vmax-vmin);pts=np.round(np.column_stack([xx,yy])).astype(int).ravel().tolist()
  if hist:
   step=(right-left)/max(1,len(arr)-1)
   for xp,yp in zip(xx,yy):draw.rectangle((xp-step*.41,yp,xp+step*.41,bottom),fill=col)
  else:draw.line(pts,fill=col,width=2)
 txt(draw,(left,bottom+4),ends[0],13,gray);txt(draw,(right,bottom+4),ends[1],13,gray,anchor='ra')
def page(ds,label,ys,names,cols,rows,subtitle):
 w=1380;h=150+rows*210;im=Image.new('RGB',(w,h),'white');d=ImageDraw.Draw(im)
 d.rectangle((0,0,9,112),fill='#008a83');txt(d,(25,12),ds.replace('_',' '),27,bold=True);txt(d,(25,49),label,20,bold=True);txt(d,(25,79),subtitle,14,gray)
 for i,name in enumerate(names):
  xp=25+(i%3)*450;yp=110+(i//3)*18
  d.line((xp,yp+7,xp+19,yp+7),fill=styles[i],width=3);txt(d,(xp+25,yp),name.replace('__',' / '),12)
 def plot(i,yy,title,unit,ends,**kw):
  ww=w//cols;panel(d,((i%cols)*ww,151+(i//cols)*210,ww,206),yy,title,unit,ends,**kw)
 return im,plot
def save(im,path):
 # Palette export keeps text antialiasing while limiting file size.
 pal=Image.new('P',(1,1)); colors=[tuple(bytes.fromhex(c[1:])) for c in [*styles,ink,gray,'#d9e3e9','#a34451','#4776a6']]
 pal.putpalette([v for c in colors for v in c]+[v for j in range(256-len(colors)) for v in (round(255*j/(255-len(colors))),)*3]);im.quantize(palette=pal,dither=Image.Dither.NONE).save(path,compress_level=2)
def chart(ds,arr,names,path,unit,tag):
 power=unit;energy=unit.replace('kW','kWh');label=names[1] if len(names)==2 else 'Five leading configurations';prefix=ds+'__'+tag+'__'
 im,plot=page(ds,label,arr,names,2,4,'Actual and forecast across 2021. Weekly bins run Monday–Sunday. Edge weeks contain 72 and 120 hours.')
 ends=('Jan 01','Dec 31')
 plot(0,arr,'Hourly power',power,ends)
 for i,key in enumerate(B):
  for j,e in enumerate([False,True]):
   plot(1+2*i+j,vals(arr,key,e),key+(' total energy' if e else ' average power'),energy if e else power,ends)
 save(im,path/(prefix+'Year_Hourly_Daily_Weekly_Monthly_Power_Energy.png'))
 # Zoom by mean absolute error; an ensemble comparison uses average absolute error across the shown candidate forecasts.
 err=np.abs(arr[1:]-arr[0]).mean(axis=0)
 fixed=[('Winter month','2021-01-01',31),('Summer month','2021-07-01',31),('Winter week','2021-01-11',7),('Summer week','2021-07-12',7),('Winter day','2021-01-13',1),('Summer day','2021-07-14',1)]
 zoom=[(name,DTS.get_loc(pd.Timestamp(dt)),DTS.get_loc(pd.Timestamp(dt))+24*nd) for name,dt,nd in fixed]
 stats=[]
 for key,ix in B.items():
  v=np.add.reduceat(err,ix[:-1])/np.diff(ix);valid=np.flatnonzero(np.diff(ix)==168) if key=='Weekly' else np.arange(len(v))
  for which,j in [('highest',valid[np.argmax(v[valid])]),('lowest',valid[np.argmin(v[valid])])]:
   zoom.append((key+' / '+which+' MAE',ix[j],ix[j+1]));stats.append(dict(dataset=ds,config=tag,period=key,extreme=which,start=str(DTS[ix[j]]),end=str(DTS[ix[j+1]-1]),mae=v[j]))
 im,plot=page(ds,label,arr,names,2,6,'Representative periods and complete calendar periods with highest or lowest hourly MAE. Equal errors use the earliest period.')
 for i,(name,st,en) in enumerate(zoom):
  plot(i,arr[:,st:en],name+'   '+DTS[st].strftime('%b %d'),power,(DTS[st].strftime('%b %d · %Hh'),DTS[en-1].strftime('%b %d · %Hh')))
 save(im,path/(prefix+'Zoom_Common_High_Low_MAE.png'))
 if len(names)==2:
  e=arr[0]-arr[1];im,plot=page(ds,label,arr,names,2,4,'Residual = actual minus forecast. Positive residuals indicate underprediction. Seasonal profiles use average power.')
  plot(0,e,'Hourly signed residual',power,ends,colors=['#a34451'])
  hist,edges=np.histogram(e,bins=40);plot(1,hist,'Residual distribution','count · horizontal axis in '+unit,(num(edges[0]),num(edges[-1])),colors=['#4776a6'],hist=True)
  plot(2,vals(e[None,:],'Weekly')[0],'Weekly mean signed residual',power,ends,colors=['#a34451'])
  plot(3,vals(abs(e)[None,:],'Weekly')[0],'Weekly mean absolute error',power,ends,colors=['#4776a6'])
  for i,(labels,tt,edge) in enumerate([(DTS.hour,'Hour of day',('00h','23h')),(DTS.dayofweek,'Day of week',('Mon','Sun')),(DTS.isocalendar().week.to_numpy(dtype=int),'ISO week number',('1','53')),(DTS.month,'Month of year',('Jan','Dec'))]):
   v=np.stack([arr[:,labels==z].mean(axis=1) for z in sorted(set(labels))],axis=1);plot(4+i,v,tt,power,edge)
  save(im,path/(prefix+'Residuals_Distribution_Trend_Seasonality.png'))
 return stats
def job(ds):
 allvals=np.load(C/(ds+'.npy'),mmap_mode='r');ids=json.loads((C/(ds+'.json')).read_text());path=dest(ds)/'PNG';path.mkdir(exist_ok=True);u='kW/customer' if ds in ['Cohort_Residential','Cohort_Commercial','Cohort_Manufacturing'] else 'kW';stats=[]
 for i,name in enumerate(ids[1:],1):stats+=chart(ds,allvals[[0,i]],['Actual',name],path,u,name)
 top=pd.read_csv(dest(ds)/'top_five.csv').config.tolist()
 if top:stats+=chart(ds,allvals[[0,*[ids.index(n) for n in top]]],['Actual',*top],path,u,'Top5')
 csv(pd.DataFrame(stats),dest(ds)/'zoom_periods.csv')
 print(ds,'done',flush=True)
if __name__=='__main__':
 with ProcessPoolExecutor(max_workers=7) as pool:list(pool.map(job,sorted(x.stem for x in C.glob('*.npy'))))
