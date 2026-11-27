// Interactive views over immutable, time-indexed report blocks.
const recordedNumber = value => typeof value==='number' && Number.isFinite(value);
const focusState = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
const galleryState = {group: focusState.group || 'load input', entity: focusState.entity || 'Total',
  field: '', hour: 0, first: 0, span: 168, mode: 'Time series', overlay: '', scenario: focusState.scenario || ''};
let galleryVersion = 0;
const groupsFor = {
  'Study inputs':['load input','PV input','solar source'],
  'Network':['bus','line','system'],
  'Network records':['bus','line','system'],
  'Demand & PV':['system','bus','load input','PV input'],
  'BESS':['battery','battery daily audit','bus','system'],
  'Economics':['system','bus'],
  'Forecast series':['forecast','forecast by bus']
};
const sensible = {
  bus:'voltage_pu',line:'current_a','load input':'p_kw','PV input':'p_kw',
  battery:'power_kw',system:'requested_load_kw','solar source':'irradiance_w_m2',forecast:'actual_kw'
};
function unitOf(name) {
  const units={kw:'kW',kvar:'kvar',kva:'kVA',kwh:'kWh',kvarh:'kvarh',a:'A',pu:'pu',deg:'°',kv:'kV',percent:'%',ohm:'Ω',hours:'h',m2:'W/m²'};
  if(name.includes('usd_per_hour'))return 'USD/h';
  if(name.endsWith('_cost')||name.endsWith('_credit'))return run.manifest.currency||'study currency';
  if(['soc_before','soc_after','soc_start','soc_end','bess_soc_before','bess_accepted_soc','soc_initial','capacity_factor'].includes(name)||name.endsWith('_fraction'))return 'fraction';
  return units[name.split('_').at(-1)]||'';
}
const readable = name=>({load_input_kw:'Served demand (kW)',load_input_kvar:'Served demand (kvar)',
  pv_input_kw:'Delivered PV (kW)',pv_input_kvar:'Delivered PV (kvar)',voltage_pu:'Voltage magnitude (pu)',
  pre_control_voltage_pu:'Controller reference voltage (pu)',uncontrolled_voltage_pu:'Uncontrolled voltage (pu)',
  before_correction_voltage_pu:'Voltage before final correction (pu)',voltage_angle_deg:'Voltage angle (°)',
  reference_pv_kw:'Historical common PV reference (kW)',p_kw:'Active power (kW)',q_kvar:'Reactive power (kvar)',
  minimum_voltage_bus:'Lowest-voltage bus ID',maximum_voltage_bus:'Highest-voltage bus ID'}[name]||
  name.replace(/_(kw|kva|kwh|kvar|deg|pu|percent|kv|ohm|a)$/i,'').replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())+(unitOf(name)?' ('+unitOf(name)+')':''));
function selectControl(parent,label,items,value,change) {
  const field=elem('label',label), input=elem('select');
  for(const [key,title] of items)input.add(new Option(title,key));
  input.value=value;field.append(input);parent.append(field);
  input.onchange=()=>change(input.value);return input;
}
function button(parent,name,action) {
  const b=elem('button',name);b.type='button';b.onclick=action;parent.append(b);return b;
}
function saveBlob(blob,name) {
  if(!blob)return;
  const url=URL.createObjectURL(blob),a=elem('a');a.download=name;a.href=url;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function csvLine(row) {
  function cell(x) {
    if(x==null)return '';
    let s=String(x);
    if(typeof x==='string'&&/^[=+@\-\t\r]/.test(s))s="'"+s;
    return '"'+s.replaceAll('"','""')+'"';
  }
  return row.map(cell).join(',')+'\r\n';
}
function saveRows(header,rows,filename) {
  saveBlob(new Blob(['\uFEFF',csvLine(header),...rows.map(csvLine)],{type:'text/csv;charset=utf-8'}),filename);
}
async function seriesValues(group,entity,field,first,last,read=block) {
  const result=Array(last-first).fill(null);
  for(const [begin,end,id] of group?.entities?.[entity]||[]) {
    if(end<first||begin>=last)continue;
    const [indices,fields]=await read(id),col=fields[field];
    if(col)indices.forEach((t,j)=>{if(t>=first&&t<last)result[t-first]=col[j]??null;});
  }
  return result;
}
function selectionPanel(root) {
  const controls=elem('div',undefined,'controls explorer-controls');root.append(controls);
  return controls;
}
function windowHours(state,axis){
  if(state.span!==-1)return state.span||axis.length;
  const month=axis[state.first].slice(0,7);
  return axis.reduce((count,t)=>count+Number(t.startsWith(month)),0);
}
function timeControls(parent,axis,refresh) {
  const state=galleryState;
  const windows=[24,168,336,-1,0], titles=['24 hours','7 days','14 days','Calendar month','Full run'];
  selectControl(parent,'Window',windows.map((v,i)=>[v,titles[i]]),state.span,v=>{
    state.span=Number(v);if(!state.span)state.first=0;refresh();
  });
  const size=windowHours(state,axis);
  const setFirst=i=>{
    state.first=Math.max(0,Math.min(Math.max(0,axis.length-size),i));
    state.hour=Math.max(state.first,Math.min(state.hour,state.first+size-1));refresh();
  };
  if(state.span===-1){
    const months=[...new Set(axis.map(t=>t.slice(0,7)))];
    const month=axis[state.first].slice(0,7),pos=months.indexOf(month);
    const showMonth=m=>{state.first=axis.findIndex(t=>t.startsWith(m));state.hour=state.first;refresh();};
    selectControl(parent,'Month',months.map(m=>[m,m]),month,showMonth);
    button(parent,'< Earlier',()=>showMonth(months[pos-1])).disabled=pos===0;
    button(parent,'Later >',()=>showMonth(months[pos+1])).disabled=pos===months.length-1;
  }else if(state.span>0){
    button(parent,'< Earlier',()=>setFirst(state.first-size)).disabled=state.first===0;
    button(parent,'Later >',()=>setFirst(state.first+size)).disabled=state.first+size>=axis.length;
  }
  if(axis.length>1&&state.span>0){
    const label=elem('label','Start'),date=elem('input');date.type='datetime-local';
    date.value=axis[state.first].slice(0,16).replace(' ','T');
    date.min=axis[0].slice(0,16).replace(' ','T');date.max=axis.at(-1).slice(0,16).replace(' ','T');
    date.onchange=()=>{const i=axis.findIndex(t=>t>=date.value.replace('T',' '));if(i>=0)setFirst(i);};label.append(date);parent.append(label);
  }
  button(parent,'Reset',()=>{state.first=0;state.hour=0;state.span=168;refresh();});
}
// Draw min/max within each pixel bin so zoomed-out peaks survive.
function drawTrace(ctx,data,x,y,pixels) {
  const stride=Math.max(1,Math.ceil(data.length/pixels));
  let started=false;ctx.beginPath();
  for(let i=0;i<data.length;i+=stride){
    let min=-1,max=-1;
    function flush() {
      if(min<0)return;
      const first=Math.min(min,max),last=Math.max(min,max);
      if(started)ctx.lineTo(x(first),y(data[first]));else{ctx.moveTo(x(first),y(data[first]));started=true;}
      if(last!==first)ctx.lineTo(x(last),y(data[last]));
      if(data.length===1)ctx.fillRect(x(first)-2,y(data[first])-2,4,4);
      min=-1;max=-1;
    }
    for(let j=i;j<Math.min(i+stride,data.length);j++){
      if(!Number.isFinite(data[j])){flush();started=false;continue;}
      if(min<0||data[j]<data[min])min=j;
      if(max<0||data[j]>data[max])max=j;
    }
    flush();
  }
  ctx.stroke();
}
function timeCoordinate(stamp) {
  if(typeof stamp!=='string'||!/^\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)?)?$/.test(stamp))return NaN;
  const iso=stamp.replace(' ','T');
  return Date.parse(iso.length===10||/(?:Z|[+-]\d\d:\d\d)$/.test(iso)?iso:iso+'Z');
}
function timeViewport(axis,range) {
  const coords=axis.map(timeCoordinate);
  if(!coords.length||coords.some((value,i)=>!Number.isFinite(value)||i>0&&value<=coords[i-1]))return null;
  const low=coords[0],high=coords.at(-1),full=high-low;
  let start=low,end=high;
  const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
  function nearest(value){
    const j=rangeIndex(coords,value);
    if(j===0||j===coords.length)return Math.min(j,coords.length-1);
    return value-coords[j-1]<=coords[j]-value?j-1:j;
  }
  function bounds(a,b){
    const width=Math.min(b-a,full);
    start=clamp(a,low,high-width);end=start+width;
    const first=rangeIndex(coords,start),last=rangeIndex(coords,end,true);
    if(last-first<2&&coords.length>1){
      const i=nearest((start+end)/2);
      const before=Math.max(0,i-1),after=Math.min(coords.length-1,i+1);
      const left=before!==i&&(after===i||coords[i]-coords[before]<=coords[after]-coords[i])?before:i;
      start=Math.min(start,coords[left]);end=Math.max(end,coords[left+1]);
    }
  }
  const set=(a,b)=>bounds(coords[a],coords[b-1]);
  if(range)set(...range);
  return {
    coords,low,high,full,nearest,bounds,set,
    get range(){return [rangeIndex(coords,start),rangeIndex(coords,end,true)];},
    get limits(){return [start,end];},
    fraction:i=>(coords[i]-start)/(end-start||1),
    index:f=>nearest(start+clamp(f,0,1)*(end-start)),
    zoom(factor,fraction){
      const f=clamp(fraction,0,1),width=Math.min(full,(end-start)*factor),anchor=start+f*(end-start);
      bounds(anchor-f*width,anchor+(1-f)*width);
    },
    pan(fraction,initial=[start,end]){
      const delta=fraction*(initial[1]-initial[0]);
      bounds(initial[0]+delta,initial[1]+delta);
    }
  };
}
function seriesLimits(all,displayed,bars,stack,zeroLine,size) {
  const limits={left:[Infinity,-Infinity],right:[Infinity,-Infinity]};
  function extent(side,value){
    limits[side][0]=Math.min(limits[side][0],value);
    limits[side][1]=Math.max(limits[side][1],value);
  }
  for(const s of all){
    const side=s.axis==='right'?'right':'left';
    if(s.style==='bar'||bars||zeroLine)extent(side,0);
    for(const value of s.data)if(recordedNumber(value))extent(side,value);
  }
  if(stack)for(let i=0;i<size;i++){
    let pos=0,neg=0;
    for(const s of displayed){const v=s.data[i];if(recordedNumber(v)){pos+=Math.max(v,0);neg+=Math.min(v,0);}}
    extent('left',pos);extent('left',neg);
  }
  return limits;
}
function interactiveChart(root,title,axis,series,unit,options={}) {
  const panel=elem('div',undefined,'chart explorer-chart'),cv=elem('canvas'),tip=elem('output'),legend=elem('div',undefined,'legend');
  cv.tabIndex=0;cv.setAttribute('aria-label',title);
  if(!options.compact)panel.append(elem('h3',title));
  const surface=elem('div',undefined,'canvas-surface'),marker=elem('span',undefined,'hover-cursor');
  marker.setAttribute('aria-hidden','true');marker.hidden=true;
  surface.append(cv,marker);panel.append(surface,tip,legend);root.append(panel);
  let [left,right]=options.range||[0,axis.length],drag=null,cursor=options.cursor,paintPending=false,fullPaint=false;
  const active=series.map(s=>s.visible!==false);
  const heat=options.mode==='Heatmap',stack=options.mode==='Stack elements',bars=options.mode==='Selected hour';
  const color=(s,i)=>s.color||palette[i%palette.length];
  const visible=()=>series.filter((s,i)=>active[i]);
  const margin=73, endMargin=series.some(s=>s.axis==='right')?73:17;
  const px=()=>Math.max(1,cv.clientWidth-margin-endMargin);
  const time=options.categorical||bars?null:timeViewport(axis,options.range);
  if(time){
    if(options.timeBounds)time.bounds(...options.timeBounds);
    [left,right]=time.range;
    if(time.full)cv.title='Wheel to zoom. Drag to pan. Shift + arrows to inspect.';
  }
  const coordinates=options.coordinates;
  const fraction=i=>coordinates?(coordinates[i]-coordinates[left])/
    (coordinates[right-1]-coordinates[left]||1):(i-left)/Math.max(1,right-left-1);
  const xpos=i=>margin+px()*(time?time.fraction(i):fraction(i));
  const limitsFor=()=>seriesLimits(options.scaleSeries||visible(),visible(),bars,stack,options.zeroLine,axis.length);
  let limits=limitsFor();
  const plotBottom=()=>cv.clientHeight-49;
  const isPlot=e=>e.offsetX>=margin&&e.offsetX<=margin+px()&&e.offsetY>=37&&e.offsetY<=plotBottom();
  function draw(exporting=false){
    if(!cv.isConnected||!axis.length)return;
    const w=Math.max(250,cv.clientWidth),h=heat?Math.min(650,Math.max(255,series.length*15+78)):(options.height||275);
    const dpr=Math.max(1.75,window.devicePixelRatio||1);
    cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);cv.style.height=h+'px';
    const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);
    ctx.font='600 12px Segoe UI';ctx.fillStyle='#1d3440';
    ctx.fillText(title,9,15,w-18);ctx.font='11px Segoe UI';
    const displayed=visible();
    if(!displayed.length||Object.values(limits).every(([low])=>low===Infinity)){
      ctx.fillText('No recorded values in this selection',25,64);return;
    }
    const upper=37,lower=h-49;
    if(heat){
      const [low,high]=limits.left,dy=(lower-upper)/Math.max(1,displayed.length),stride=Math.max(1,Math.ceil((right-left)/px()));
      displayed.forEach((s,r)=>{
        if(displayed.length<27||r%4===0){ctx.fillStyle='#345260';ctx.fillText(s.label.slice(0,10),4,upper+(r+.65)*dy);}
        for(let i=left;i<right;i+=stride){
          const bins=s.data.slice(i,Math.min(i+stride,right)).filter(recordedNumber);
          if(!bins.length)continue;
          const v=options.field==='voltage_pu'?Math.min(...bins):Math.max(...bins), z=(v-low)/(high-low||1);
          ctx.fillStyle='hsl('+(205-175*z)+' 58% '+(78-34*z)+'%)';
          ctx.fillRect(xpos(i),upper+r*dy,Math.max(1,stride*px()/Math.max(1,right-left-1)),dy);
        }
      });
      ctx.fillStyle='#345260';ctx.fillText(fmt(low)+' – '+fmt(high)+' '+unit,margin,h-28);
    }else{
      const scales={};
      for(const side of ['left','right']){
        let [low,high]=limits[side];
        if(low===Infinity)continue;
        if(low===high){const pad=Math.abs(low)*.03||1;low-=pad;high+=pad;}
        const y=v=>lower-(v-low)/(high-low)*(lower-upper);
        scales[side]=y;
        const label=displayed.find(s=>(s.axis||'left')===side)?.unit||unit;
        ctx.fillStyle='#345260';
        ctx.fillText(label||'Value',side==='left'?7:w-endMargin+6,30,endMargin+38);
        for(let j=0;j<=4;j++){
          const v=low+(high-low)*j/4;ctx.fillStyle='#415866';
          ctx.fillText(fmt(v),side==='left'?4:w-endMargin+6,y(v)+4,margin-8);
          if(side==='left'||!scales.left){ctx.strokeStyle='#dfe7ec';ctx.setLineDash([]);ctx.beginPath();ctx.moveTo(margin,y(v));ctx.lineTo(w-endMargin,y(v));ctx.stroke();}
        }
        if(options.zeroLine){
          ctx.strokeStyle='#6c8491';ctx.setLineDash([4,3]);ctx.beginPath();
          ctx.moveTo(margin,y(0));ctx.lineTo(w-endMargin,y(0));ctx.stroke();ctx.setLineDash([]);
        }
      }
      const positive=stack?new Float64Array(right-left):null,negative=stack?new Float64Array(right-left):null;
      const partialComposition=stack&&displayed.every(s=>s.category)?
        Array.from({length:right-left},(_,i)=>displayed.some(s=>!recordedNumber(s.data[left+i]))):null;
      const renderedBars=displayed.filter(s=>bars||s.style==='bar'),stride=Math.max(1,Math.ceil((right-left)/px()));
      series.forEach((s,j)=>{
        if(!active[j])return;
        ctx.strokeStyle=ctx.fillStyle=color(s,j);ctx.lineWidth=2;ctx.setLineDash(s.dash==='dashed'?[5,4]:[]);
        const y=scales[(s.axis||'left')];
        if(!y)return;
        if(stack){
          const width=Math.max(1,px()/Math.max(1,right-left)*.75);
          for(let i=left;i<right;i++){
            const v=s.data[i];if(partialComposition?.[i-left]||!recordedNumber(v)||v===0)continue;
            const sums=v>0?positive:negative,start=sums[i-left];sums[i-left]+=v;
            ctx.fillRect(xpos(i)-width/2,Math.min(y(start),y(start+v)),width,Math.abs(y(start+v)-y(start)));
          }
        }else if(bars||s.style==='bar'){
          const width=Math.max(1,px()*stride/Math.max(1,right-left)*.78/renderedBars.length);
          const offset=(renderedBars.indexOf(s)-(renderedBars.length-1)/2)*width;
          for(let i=left;i<right;i+=stride){
            let min=0,max=0;
            for(let k=i;k<Math.min(right,i+stride);k++){const v=s.data[k];if(recordedNumber(v)){min=Math.min(min,v);max=Math.max(max,v);}}
            if(min||max)ctx.fillRect(xpos(i)+offset-width/2,y(max),width,Math.abs(y(min)-y(max)));
          }
        }else {
          if(s.style!=='points')drawTrace(ctx,s.data.slice(left,right),i=>xpos(i+left),y,px());
          if(options.markers||s.style==='points'){
            for(let i=left;i<right;i++){
              if(!recordedNumber(s.data[i]))continue;
              ctx.beginPath();ctx.arc(xpos(i),y(s.data[i]),2.7,0,2*Math.PI);ctx.fill();
            }
          }
        }
      });
      ctx.setLineDash([]);
      if(!exporting&&cursor>=left&&cursor<right){
        ctx.strokeStyle='#526470';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(xpos(cursor),upper);
        ctx.lineTo(xpos(cursor),lower);ctx.stroke();ctx.setLineDash([]);
      }
    }
    ctx.fillStyle='#39535b';
    if(options.categorical&&options.axisLabel){
      const count=Math.min(right-left,Math.max(2,Math.floor(px()/65)));
      for(let j=0;j<count;j++){
        const i=left+Math.round(j*(right-left-1)/Math.max(1,count-1));
        ctx.textAlign=j===0?'left':j===count-1?'right':'center';
        const label=typeof axis[i]==='number'?fmt(axis[i]):String(axis[i]??'');
        ctx.fillText(label,xpos(i),h-32,65);
      }
      ctx.textAlign='center';ctx.fillText(options.axisLabel,margin+px()/2,h-19,px());ctx.textAlign='left';
    }else{
      ctx.fillText(String(axis[left]??''),margin,h-30,(w-margin-endMargin)/2);
      const end=String(axis[right-1]??'');
      if(right-left>1){ctx.textAlign='right';ctx.fillText(end,w-endMargin,h-30,(w-margin-endMargin)/2);ctx.textAlign='left';}
    }
    let x=8;
    for(const s of displayed){
      if(x+16>=w)break;
      ctx.fillStyle=color(s,series.indexOf(s));ctx.fillRect(x,h-16,9,4);
      ctx.fillStyle='#344d59';const max=Math.min(155,w-x-16);
      ctx.fillText(s.label,x+12,h-10,max);x+=16+Math.min(max,ctx.measureText(s.label).width);
    }
    updateCursor();
  }
  function updateCursor(){
    marker.hidden=!Number.isFinite(cursor)||cursor<left||cursor>=right;
    if(!marker.hidden)marker.style.left=xpos(cursor)+'px';
  }
  function schedule(paint=false){
    fullPaint ||= paint;
    if(paintPending)return;
    paintPending=true;requestAnimationFrame(()=>{
      const repaint=fullPaint;paintPending=false;fullPaint=false;
      if(repaint)draw();else updateCursor();
    });
  }
  function choose(i,notify=true) {
    if(i<0||i>=axis.length)return;
    tip.textContent=[axis[i],...visible().map(s=>s.label+' · '+(recordedNumber(s.data[i])?fmt(s.data[i])+' '+(s.unit||unit):'Not recorded'))].join('  |  ');
    if(notify&&options.hover)options.hover(i);
  }
  function setRange(begin,end,notify=true){
    if(!axis.length)return;
    left=Math.max(0,Math.min(begin,axis.length-1));right=Math.max(left+1,Math.min(end,axis.length));
    if(time)time.set(left,right);
    changed(notify);
  }
  function changed(notify=true){
    if(time)[left,right]=time.range;
    schedule(true);
    if(notify&&options.onZoom)options.onZoom(left,right,time?.limits);
  }
  series.forEach((s,i)=>{
    const item=button(legend,s.label,()=>{active[i]=!active[i];item.setAttribute('aria-pressed',active[i]);
      options.toggle?.(s,active[i]);limits=limitsFor();schedule(true);});
    item.style.borderBottom='3px solid '+color(s,i);item.setAttribute('aria-pressed',active[i]);
  });
  function index(e){
    const point=(e.offsetX-margin)/px();
    if(time)return Math.min(right-1,Math.max(left,time.index(point)));
    if(!coordinates)return Math.max(left,Math.min(right-1,left+Math.round(point*Math.max(1,right-left-1))));
    let lo=left,hi=right-1;
    while(lo<hi){
      const mid=(lo+hi)>>1;
      if(fraction(mid)<point)lo=mid+1;
      else hi=mid;
    }
    return lo>left&&Math.abs(fraction(lo-1)-point)<Math.abs(fraction(lo)-point)?lo-1:lo;
  }
  cv.onpointermove=e=>{
    if(drag&&time){
      const dx=e.clientX-drag.x;
      drag.moved ||= Math.abs(dx)>4||Math.abs(e.clientY-drag.y)>4;
      if(drag.moved){time.pan(-dx/px(),drag.initial);changed();}
    }else if(isPlot(e))choose(index(e));
  };
  cv.onpointerdown=e=>{
    if(e.button!==0||!isPlot(e))return;
    if(e.pointerType==='touch')return;
    drag={x:e.clientX,y:e.clientY,initial:time?.limits,moved:false};
    cv.focus({preventScroll:true});cv.setPointerCapture(e.pointerId);
    if(time)e.preventDefault();
  };
  cv.onpointerup=e=>{
    if((drag&&!drag.moved||e.pointerType==='touch'&&isPlot(e))&&options.pick)options.pick(index(e));
    drag=null;
  };
  cv.onpointercancel=cv.onlostpointercapture=()=>{drag=null;};
  cv.ondragstart=e=>e.preventDefault();
  if(time&&time.full)cv.addEventListener('wheel',e=>{
    if(!isPlot(e)||e.ctrlKey||e.metaKey||!e.deltaY)return;
    e.preventDefault();
    const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?220:1);
    time.zoom(Math.exp(Math.max(-.75,Math.min(.75,delta*.0023))),(e.offsetX-margin)/px());
    changed();
  },{passive:false});
  cv.onkeydown=e=>{
    let i=cursor??left;
    if(time&&(e.key==='+'||e.key==='='||e.key==='-')){
      e.preventDefault();time.zoom(e.key==='-'?1.25:.8,.5);changed();
    }else if(time&&!e.shiftKey&&(e.key==='ArrowRight'||e.key==='ArrowLeft')){
      e.preventDefault();time.pan(e.key==='ArrowRight'?.2:-.2);changed();
    }else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){
      e.preventDefault();cursor=Math.max(left,Math.min(right-1,i+(e.key==='ArrowRight'?1:-1)));choose(cursor);schedule();
    }else if(e.key==='Enter'&&options.pick){e.preventDefault();options.pick(i);}
    else if(e.key==='Escape'){e.preventDefault();setRange(0,axis.length);}
  };
  const savePNG=()=>{draw(true);cv.toBlob(blob=>{saveBlob(blob,(options.filename||'chart')+'.png');draw();});};
  const saveCSV=()=>{
    const list=visible(),intervals=options.intervals;
    const display=options.exportHeaders?list.map(s=>exactExportHeader(s,unit)):list.map(s=>s.label+(unit?' ['+unit+']':''));
    saveRows([options.exportHeaders?'Timestamp or period':'axis',...(intervals?['First retained timestamp','Last retained timestamp','Partial calendar bucket']:[]),...display],
      axis.slice(left,right).map((v,j)=>{
        const n=j+left,bucket=intervals?.[n];
        return [v,...(bucket?[bucket.start,bucket.end,bucket.partial]:[]),...list.map(s=>s.data[n])];
      }),(options.filename||'chart')+'.csv');
  };
  const controls=options.compact?elem('details',undefined,'chart-tools'):selectionPanel(panel);
  if(options.compact){controls.append(elem('summary','Zoom / export'));panel.append(controls);}
  if(time&&time.full){
    button(controls,'Reset zoom',()=>setRange(0,axis.length));
    for(const shift of [-1,1])button(controls,shift<0?'Pan left':'Pan right',()=>{time.pan(shift*.5);changed();});
    tip.textContent='Wheel to zoom · Drag to pan · Shift + arrow keys to inspect';
  }
  button(controls,'Save PNG',savePNG);button(controls,'Save CSV',saveCSV);
  const controller={draw,savePNG,saveCSV,publicationData(full=false){
    const a=full?0:left,b=full?axis.length:right;
    return {title,axis:axis.slice(a,b),coordinates:coordinates?.slice(a,b),axisLabel:options.axisLabel,unit,
      intervals:options.intervals?.slice(a,b),categorical:options.categorical,markers:options.markers,stack,
      traces:visible().map(s=>({...s,data:s.data.slice(a,b)}))};
  },setCursor(i){if(cursor!==i){cursor=i;schedule();}},setRange,
    setTimeBounds(bounds){if(time){time.bounds(...bounds);changed(false);}}};
  redraw.push(draw);draw();
  return controller;
}

function chooseScenario(controls) {
  const state=galleryState,options=Object.entries(run.scenarios);
  if(!run.scenarios[state.scenario])state.scenario=run.scenarios.best_bess?'best_bess':options[0][0];
  if(options.length>1)selectControl(controls,'Scenario',options.map(([k,s])=>[k,s.label]),state.scenario,v=>{state.scenario=v;render();});
  return run.scenarios[state.scenario];
}
function jump(group,entity,hour) {
  if(galleryState.span===-1||hour<galleryState.first||hour>=galleryState.first+(galleryState.span||Infinity))galleryState.first=hour;
  Object.assign(galleryState,{group,entity:String(entity),field:sensible[group],hour,mode:'Time series',overlay:''});
  if(typeof selectedEntity==='function' && run.scenarios[scenario]?.gallery){
    const ctx=chartContext('current',scenario);
    if(ctx){
      void timeline(ctx).then(axis=>{
        workspace.primary=ctx.scenario;workspace.state.scenario=ctx.scenario;
        screen='Network';tabs();selectedEntity(group,entity,axis[hour]);
      });
      return;
    }
  }
  screen='Network records';tabs();render();
}
function networkMap(root,topology,samples,group,field,onSelect,selection=null,health=null,equipment={}) {
  if(!run.metadata.layout?.positions)return;
  const positions=run.metadata.layout.positions,svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  const pts=Object.values(positions),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  if(!pts.length)return;
  svg.setAttribute('viewBox',[Math.min(...xs)-36,Math.min(...ys)-45,Math.max(...xs)-Math.min(...xs)+72,Math.max(...ys)-Math.min(...ys)+85].join(' '));
  svg.setAttribute('class','feeder');svg.setAttribute('aria-label',health?'Whole-study feeder health':'Clickable network at selected hour');
  const values=Object.values(samples).filter(Number.isFinite),lo=Math.min(...values),hi=Math.max(...values);
  const color=v=>Number.isFinite(v)?'hsl('+(200-165*(v-lo)/(hi-lo||1))+' 58% 45%)':'#a3b0b5';
  function node(tag,attrs,kind,id,text){
    const n=document.createElementNS(svg.namespaceURI,tag);
    for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);
    n.setAttribute('tabindex','0');n.setAttribute('role','button');n.setAttribute('aria-label',text);
    n.setAttribute('data-kind',kind);n.setAttribute('data-entity',id);
    if(selection?.kind===kind&&selection.ids.includes(String(id)))n.classList.add('selected-element');
    if(health?.[kind]?.[id]?.stress)n.classList.add('prior-stress');
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=text;n.append(title);
    n.onclick=()=>onSelect(kind,id);n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(kind,id);}};svg.append(n);return n;
  }
  for(const line of topology?.lines||[]){
    const pts=run.metadata.layout.routes?.[line.line_id]||[positions[line.from_bus],positions[line.to_bus]];
    const status=health?.line?.[line.line_id];
    if(pts.every(Boolean))node('polyline',{points:pts.map(p=>p.join(',')).join(' '),fill:'none',
      stroke:status?.color||(health?'#7d8995':group==='line'?color(samples[line.line_id]):'#71878c'),'stroke-width':7},'line',line.line_id,
      line.line_id+(health?' · '+(status?.label||'Insufficient data'):group==='line'?' · '+fmt(samples[line.line_id])+' '+unitOf(field):''));
  }
  for(const [id,[x,y]] of Object.entries(positions)){
    const status=health?.bus?.[id];
    const slack=topology?.buses?.find(bus=>String(bus.bus_id)===id)?.is_slack;
    node(slack?'rect':'circle',{...(slack?{x:x-12,y:y-12,width:24,height:24}:{cx:x,cy:y,r:13}),
      fill:status?.color||(health?'#7d8995':group==='bus'?color(samples[id]):'#3b6c78'),stroke:'#253d47','stroke-width':2},'bus',id,
      'Bus '+id+(health?' · '+(status?.label||'Insufficient data'):group==='bus'?' · '+fmt(samples[id])+' '+unitOf(field):''));
    const label=document.createElementNS(svg.namespaceURI,'text');label.setAttribute('x',x);label.setAttribute('y',y-17);
    label.setAttribute('text-anchor','middle');label.setAttribute('font-size','21');label.setAttribute('pointer-events','none');label.textContent=id;svg.append(label);
    const marks=[equipment.pv?.has(id)?'PV':'',equipment.bess?.has(id)?'BESS':''].filter(Boolean).join(' / ');
    if(marks){
      const badge=label.cloneNode(false);badge.setAttribute('y',y+32);badge.setAttribute('font-size','14');
      badge.textContent=marks;svg.append(badge);
    }
  }
  root.append(svg);
}
async function gallery() {
  const token=++galleryVersion, state=galleryState,panel=section($('content'),screen),controls=selectionPanel(panel);
  const selected=chooseScenario(controls),g=selected.gallery;
  if(!g?.timestamps&&g?.timestamps!==0){panel.append(elem('p','No timestamped series recorded.','empty'));return;}
  const axis=await block(g.timestamps);
  if(token!==galleryVersion||!panel.isConnected)return;
  if(focusState.timestamp){
    const i=axis.indexOf(focusState.timestamp.replace('T',' '));if(i>=0){state.hour=i;state.first=Math.max(0,i-12);}
    delete focusState.timestamp;
  }
  state.first=Math.min(state.first,axis.length-1);
  const size=windowHours(state,axis);
  if(state.span===-1){const month=axis[state.first].slice(0,7);state.first=axis.findIndex(t=>t.startsWith(month));}
  else state.first=Math.min(state.first,Math.max(0,axis.length-size));
  const end=Math.min(axis.length,state.first+size);
  state.hour=Math.max(state.first,Math.min(state.hour,end-1));
  timeControls(controls,axis,render);
  if(screen==='Decisions'){await decisionView(panel,g,axis,state.first,end);return;}
  if(screen==='BESS'&&!selected.has_bess&&!g.groups.battery){
    panel.append(elem('p','No battery operation was recorded for this scenario.','empty'));return;
  }
  if(screen==='Economics')economicView(panel,selected);
  const choices=(groupsFor[screen]||[]).filter(k=>g.groups[k]);
  if(!choices.length){panel.append(elem('p','No matching data were retained for this study.','empty'));return;}
  if(!choices.includes(state.group))state.group=choices[0];
  if(screen==='Study inputs'){
    const context=run.metadata.context||{},slack=run.metadata.topology?.buses?.find(b=>b.is_slack);
    const info=elem('details');info.append(elem('summary','Input provenance and workbook settings'));
    grid(info,['Input','Recorded value'],[['Clock',run.manifest.clock],['Clock provenance',run.input_info?.clock_status],
      ['Site latitude (°)',run.input_info?.site?.latitude],['Site longitude (°)',run.input_info?.site?.longitude],
      ['Slack voltage (pu)',slack?.v_set_pu],
      ['Workbook',context['Workbook provenance']],['Selected workbook SHA256',context['Network SHA256']||run.manifest.input_hashes?.['inputs/network.xlsx']],
      ['Distributor workbook SHA256',context['Distributor network SHA256']],['Irradiance (W/m²)',g.groups['solar source']?.fields.includes('irradiance_w_m2')?'Archived source available':'Not recorded']]);
    panel.append(info);
  }
  const filters=selectionPanel(panel);
  selectControl(filters,'Source',choices.map(x=>[x,readable(x)]),state.group,v=>{state.group=v;state.field='';state.entity='';state.overlay='';render();});
  const group=g.groups[state.group],ids=Object.keys(group.entities),fields=group.fields.filter(k=>
    screen==='Economics'?/cost|credit|tariff/.test(k):screen==='BESS'&&!state.group.startsWith('battery')?/bess/.test(k):true);
  if(!fields.length){panel.append(elem('p','No recorded quantities for this selection.','empty'));return;}
  if(!ids.includes(state.entity))state.entity=ids.includes('Total')?'Total':ids[0];
  if(!fields.includes(state.field))state.field=fields.includes(sensible[state.group])?sensible[state.group]:fields[0];
  selectControl(filters,'Element',ids.map(id=>[id,id]),state.entity,v=>{state.entity=v;render();});
  selectControl(filters,'Quantity',fields.map(k=>[k,readable(k)]),state.field,v=>{state.field=v;state.overlay='';render();});
  const unit=unitOf(state.field),modes=['Time series'];
  if(ids.length>1)modes.push('Selected hour','Ranked at hour','Heatmap','Overlay elements');
  if(ids.length>1&&['kW','kWh','kvar','kVA'].includes(unit))modes.push('Stack elements');
  if(state.field.endsWith('_kwh'))modes.push('Cumulative energy');
  if(!modes.includes(state.mode))state.mode=modes[0];
  selectControl(filters,'View',modes.map(v=>[v,v]),state.mode,v=>{state.mode=v;render();});
  const hourLabel=elem('label','Selected hour'),range=elem('input');range.type='range';range.min=state.first;range.max=end-1;range.value=state.hour;
  range.onchange=()=>{state.hour=Number(range.value);render();};hourLabel.append(range,elem('output',axis[state.hour]));filters.after(hourLabel);
  const series=[],labels=axis.slice(state.first,end);
  const field=state.field,entity=state.entity;
  const idList=ids.filter(id=>!['Total','residential','commercial','manufacturing'].includes(id));
  const samples={};
  if(screen==='Network records'&&['bus','line'].includes(state.group)||['Selected hour','Ranked at hour'].includes(state.mode)){
    for(const id of ids)samples[id]=(await seriesValues(group,id,field,state.hour,state.hour+1))[0];
  }
  if(token!==galleryVersion||!panel.isConnected)return;
  if(['Selected hour','Ranked at hour'].includes(state.mode)){
    if(state.mode==='Ranked at hour')ids.sort((a,b)=>(samples[b]??-Infinity)-(samples[a]??-Infinity));
    series.push({label:readable(field),data:ids.map(id=>samples[id])});
    if(field==='voltage_pu')for(const [label,k] of [['Lower limit','voltage_min_pu'],['Upper limit','voltage_max_pu']]){
      if(Number.isFinite(run.metadata.simulation?.[k]))series.push({label,data:ids.map(()=>run.metadata.simulation[k])});
    }
    interactiveChart(panel,axis[state.hour],ids,series,unit,{mode:'Selected hour',pick:i=>{state.entity=ids[i];state.mode='Time series';render();}});
  }else {
    const multi=['Heatmap','Overlay elements','Stack elements'].includes(state.mode);
    const keys=multi?idList:[entity];
    for(const id of keys){
      const data=await seriesValues(group,id,field,state.first,end);
      if(token!==galleryVersion||!panel.isConnected)return;
      let accumulated=0;
      if(state.mode==='Cumulative energy')data.forEach((v,i)=>{accumulated=v==null||accumulated==null?null:accumulated+v;data[i]=accumulated;});
      series.push({label:id+' · '+readable(field),data});
    }
    if(!multi&&state.mode==='Time series'){
      const overlay=new Map();
      for(const [groupName,other] of Object.entries(g.groups)){
        const id=other.entities[entity]?entity:other.entities.Total?'Total':other.entities.System?'System':null;
        if(!id)continue;
        for(const k of other.fields)if(unit&&unitOf(k)===unit&&(other!==group||k!==field)){
          overlay.set(groupName+' / '+id+' / '+readable(k),[other,id,k]);}
      }
      for(const [key,sc] of Object.entries(run.scenarios)){
        if(key===state.scenario||!sc.gallery?.groups?.[state.group]?.entities?.[entity])continue;
        const otherAxis=await block(sc.gallery.timestamps);
        if(otherAxis.length===axis.length&&otherAxis.every((v,i)=>v===axis[i]))
          overlay.set(sc.label+' / '+entity+' / '+readable(field),[sc.gallery.groups[state.group],entity,field]);
      }
      selectControl(filters,'Compare',[['','None'],...Array.from(overlay.keys(),x=>[x,x])],state.overlay,v=>{state.overlay=v;render();});
      const extra=overlay.get(state.overlay);
      if(extra)series.push({label:state.overlay,data:await seriesValues(...extra,state.first,end)});
    }
    if(state.group==='load input'&&['p_kw','q_kvar'].includes(field)&&run.metadata.topology?.loads){
      const loads=run.metadata.topology.loads.filter(l=>entity==='Total'||String(l.bus_id)===entity||run.input_info?.assignments?.[l.bus_id]===entity);
      if(loads.length&&!multi){
        const base=loads.reduce((a,l)=>a+l[field==='p_kw'?'p_base_kw':'q_base_kvar'],0);
        series.push({label:'Workbook base',data:labels.map(()=>base)});
      }
    }
    if(token!==galleryVersion||!panel.isConnected)return;
    interactiveChart(panel,state.mode==='Cumulative energy'?'Cumulative energy in selected window':readable(field),labels,series,unit,
      {mode:state.mode,field,cursor:state.hour-state.first,pick:i=>{state.hour=state.first+i;render();}});
  }
  if(!panel.isConnected)return;
  const info=elem('details');info.open=screen==='Network records';info.append(elem('summary',entity+' · '+axis[state.hour]));
  const rows=[];
  for(const k of group.fields)rows.push([readable(k),(await seriesValues(group,entity,k,state.hour,state.hour+1))[0],unitOf(k)]);
  grid(info,['Quantity','Selected value','Unit'],rows);panel.append(info);
  if(screen==='Demand & PV' && state.group==='bus'){
    const production=await seriesValues(group,entity,'pv_input_kw',state.first,end);
    const available=await seriesValues(group,entity,'available_pv_kw',state.first,end);
    const ratings=await seriesValues(group,entity,'installed_pv_kw',state.first,end);
    if(production.every(Number.isFinite)&&available.every(Number.isFinite)&&ratings.every(v=>v>0)){
      const sum=a=>a.reduce((s,v)=>s+v,0);
      cards(panel,[['PV utilization · delivered / available',sum(available)>0?fmt(100*sum(production)/sum(available))+'%':'No PV available'],
                   ['PV capacity factor · delivered / nameplate hours',fmt(100*sum(production)/sum(ratings))+'%']]);
    }
  }
  if(screen==='Network records'&&['bus','line'].includes(state.group))networkMap(panel,run.metadata.topology,samples,state.group,field,(k,id)=>jump(k,id,state.hour));
}
function economicView(panel,scenario) {
  const rows=(scenario.metrics||[]).filter(m=>/cost|annual_|credit|purchases/.test(m.metric)&&typeof m.value==='number');
  const prices=run.manifest.economics||{};
  if(rows.length)grid(panel,['Cost component','Value','Unit'],rows.map(m=>[readable(m.metric),m.value,m.unit]));
  const parts=rows.filter(m=>['annual_bess_capital_cost','annual_bess_om_cost','annual_grid_purchases','annual_export_credit','annual_shedding_cost','annual_curtailment_cost'].includes(m.metric));
  if(parts.length)interactiveChart(panel,'Annual cost components',parts.map(m=>readable(m.metric)),[{label:'Annual cost',data:parts.map(m=>m.metric==='annual_export_credit'?-m.value:m.value)}],parts[0].unit,{mode:'Selected hour'});
  const annual=Object.values(run.scenarios).filter(s=>Number.isFinite(asMetrics(s).annual_total_cost));
  if(annual.length){
    const components=[
      ['annual_grid_purchases','Grid purchases'],['annual_export_credit','Export credit'],
      ['annual_shedding_cost','Load shedding'],['annual_curtailment_cost','PV curtailment'],
      ['annual_bess_capital_cost','Annualized capital'],['annual_bess_om_cost','Annual O&M'],
      ['annual_terminal_inventory_adjustment','Terminal inventory adjustment']
    ];
    const series=components.map(([key,label])=>({label,data:annual.map(s=>{
      const v=asMetrics(s)[key];return Number.isFinite(v)?(key==='annual_export_credit'?-v:v):null;})}))
      .filter(s=>s.data.some(Number.isFinite));
    if(series.length)interactiveChart(panel,'Annual cost by scenario',annual.map(s=>s.label),series,
      (run.manifest.currency||'study currency')+'/year',{mode:'Stack elements'});
    const base=asMetrics(run.scenarios.no_bess).annual_total_cost,best=asMetrics(run.scenarios.best_bess).annual_total_cost;
    if(Number.isFinite(base)&&Number.isFinite(best)&&base>0)cards(panel,[['Annual saving versus No BESS',fmt(100*(base-best)/base,3)+'%']]);
  }
  const rates=Object.entries(prices).filter(([k,v])=>/tariff|penalty_per_kwh/.test(k)&&typeof v==='number');
  if(rates.length)grid(panel,['Assumed price','Value','Unit'],rates.map(([k,v])=>[readable(k),v,(run.manifest.currency||'study currency')+'/kWh']));
}
const eventFilter={bus:'',action:'',constraint:'',status:'',outcome:'',severity:0};
async function decisionView(panel,g,axis,first,last) {
  if(!g.controls){panel.append(elem('p','A control ledger was not recorded for this run.','empty'));return;}
  const filter=eventFilter;
  const filters=[['bus','Bus'],['action','Action'],['constraint','Constraint / element'],['status','Action status'],['outcome','Final state']];
  const choices=Object.fromEntries(filters.map(([key])=>[key,new Set()]));
  const counts=Array(last-first).fill(0),unresolved=counts.slice(),before=counts.slice(),after=counts.slice();
  const totals=new Map(),types=new Map(),byBus=new Map(),blocks=[];
  const inc=(map,key,n=1)=>map.set(key,(map.get(key)||0)+n);
  let total=0, unfiltered=0;
  function *records(hours,collect){
    for(const hour of hours){
      if(hour.step_index<first||hour.step_index>=last)continue;
      const constraints=hour.constraints||[],actions=hour.actions||[];
      const severity=constraints.reduce((v,c)=>Math.max(v,...[c.before,c.after_bess,c.final].map(s=>
        s?.excess>0?(c.limit===0?Infinity:100*s.excess/c.limit):0)),0);
      let counted=false;
      for(const action of actions.length?actions:[{action:'Unresolved hour',status:'unresolved'}]){
        const keys={bus:[String(action.bus_id??'')],action:[action.action],constraint:hour.triggers||[],status:[action.status],outcome:[hour.outcome]};
        if(collect){
          unfiltered++;
          for(const [key] of filters)for(const value of keys[key])if(value)choices[key].add(value);
        }
        if(severity<filter.severity||filters.some(([k])=>filter[k]&&!keys[k].includes(filter[k])))continue;
        if(collect){
          const i=hour.step_index-first;
          if(actions.length)counts[i]++;
          if(action.bus_id!=null)inc(byBus,action.bus_id);
          if(action.accepted!=null)inc(totals,action.action+' ('+action.unit+'h)',action.accepted*hour.dt_hours);
          if(!counted){
            counted=true;unresolved[i]=Number(!hour.feasible);
            before[i]=Object.keys(hour.stages?.before?.violations||{}).length;
            after[i]=Object.keys(hour.stages?.final?.violations||{}).length;
            for(const c of constraints)inc(types,c.type);
          }
        }
        yield {hour,action};
      }
    }
  }
  for(const [a,b,id] of g.controls){
    if(a>=last||b<first)continue;
    let count=0;
    for(const item of records(await block(id),true))count++;
    if(!panel.isConnected)return;
    if(count){blocks.push({id,offset:total,count});total+=count;}
  }
  if(!unfiltered){panel.append(elem('p','No control actions or unresolved hours in this window.','empty'));return;}
  const tools=selectionPanel(panel);
  for(const [key,title] of filters){
    const values=[...choices[key]].sort();
    // Keep a previous filter visible when another time window has no matching values.
    if(filter[key]&&!choices[key].has(filter[key]))values.unshift(filter[key]);
    selectControl(tools,title,[['','All'],...values.map(v=>[v,v])],filter[key],v=>{filter[key]=v;render();});
  }
  const label=elem('label','Minimum excess / limit (%)'),min=elem('input');min.type='number';min.min=0;min.value=filter.severity;
  min.onchange=()=>{filter.severity=Math.max(0,Number(min.value)||0);render();};label.append(min);tools.append(label);
  if(totals.size)grid(panel,['Selected actions','Interval total'],[...totals]);
  const stats=elem('details');stats.append(elem('summary','Affected buses and constraints'));
  if(byBus.size)grid(stats,['Bus','Action count'],[...byBus].sort((a,b)=>b[1]-a[1]));
  if(types.size)grid(stats,['Constraint type','Affected element-hours'],[...types]);
  panel.append(stats);
  interactiveChart(panel,'Constraints in filtered event hours',axis.slice(first,last),
    [{label:'Before',data:before},{label:'Final',data:after},{label:'Unresolved hours',data:unresolved}],'count');
  interactiveChart(panel,'Action timeline',axis.slice(first,last),[{label:'Actions',data:counts}],'count',{pick:i=>{galleryState.hour=first+i;render();}});
  const nav=selectionPanel(panel),page=elem('div'),detail=elem('div');
  panel.append(page,detail);
  const header=['Timestamp','Bus','Action','Requested','Accepted','Unit','Status','Final state'];
  const cells=({hour,action})=>[hour.timestamp,action.bus_id,action.action,action.requested,action.accepted,action.unit,action.status,hour.outcome];
  function showDetail({hour,action}){
    galleryState.hour=hour.step_index;
    detail.replaceChildren(elem('h3',hour.timestamp+' · '+action.action));
    detail.append(elem('p',[hour.policy,hour.attribution,...hour.reason_codes,...(hour.messages||[])].join(' · ')),
      elem('p','Constraints considered: '+(hour.considered||[]).join(', ')));
    grid(detail,['Constraint','Limit','Before','After BESS reference','Final','Unit'],(hour.constraints||[]).map(c=>[c.constraint,c.limit,c.before.measured,c.after_bess.measured,c.final.measured,c.unit]));
    if(action.bus_id!=null)button(detail,'Inspect bus at this hour',()=>jump('bus',action.bus_id,hour.step_index));
    for(const c of hour.constraints||[])if(c.type==='ampacity')button(detail,'Inspect line '+c.entity,()=>jump('line',c.entity,hour.step_index));
  }
  let offset=0,version=0;
  async function show(){
    const token=++version,items=[];
    for(const b of blocks){
      if(b.offset+b.count<=offset||b.offset>=offset+50)continue;
      let i=b.offset;
      for(const item of records(await block(b.id),false)){
        if(i>=offset)items.push(item);
        if(++i>=offset+50)break;
      }
    }
    if(token!==version||!panel.isConnected)return;
    page.replaceChildren(elem('p',total+' matching records · '+(total?offset+1:0)+'–'+Math.min(offset+50,total)));
    detail.replaceChildren();
    grid(page,header,items.map(cells));
    page.querySelectorAll('tbody tr').forEach((tr,i)=>{tr.tabIndex=0;tr.onclick=()=>showDetail(items[i]);tr.onkeydown=e=>{if(e.key==='Enter')tr.click();};});
    const selected=items.find(e=>e.hour.step_index===galleryState.hour);if(selected)showDetail(selected);
  }
  button(nav,'Previous',()=>{offset=Math.max(0,offset-50);show();});
  button(nav,'Next',()=>{if(offset+50<total){offset+=50;show();}});
  button(nav,'Export filtered CSV',async()=>{
    const columns=[...header,'Run','Scenario','Sequence','Controller','Attribution','Reason codes','Constraint readings (JSON)'];
    const parts=['\uFEFF',csvLine(columns)];
    for(const b of blocks){
      const lines=[];
      for(const item of records(await block(b.id),false)){
        const h=item.hour;
        lines.push(csvLine([...cells(item),h.run_id,h.scenario,item.action.sequence,h.policy,h.attribution,h.reason_codes.join(' | '),JSON.stringify(h.constraints||[])]));
      }
      parts.push(new Blob(lines));
    }
    saveBlob(new Blob(parts,{type:'text/csv;charset=utf-8'}),'control-decisions.csv');
  });
  await show();
}


async function compareCurves(root,snapshots){
  const panel=section(root,'Aligned run series'),controls=selectionPanel(panel),graph=elem('div');panel.append(graph);
  const runs=snapshots.flatMap((r,i)=>Object.entries(r.scenarios).filter(([,s])=>s.gallery?.groups)
    .map(([k,s])=>({label:(r.manifest.folder||'Run '+(i+1))+' · '+s.label+' · '+fmt(r.metadata?.topology?.buses?.find(b=>b.is_slack)?.v_set_pu)+' pu · '+String(r.manifest.run_id).slice(-8),sc:s,read:r.readBlock||block,clock:r.manifest.clock,currency:r.manifest.currency})));
  if(runs.length<2)return;
  if(!runs[0].clock||runs.some(r=>r.clock!==runs[0].clock)){panel.append(elem('p','A common recorded source clock is required to align curves.'));return;}
  const all=runs[0].sc.gallery.groups;
  const choices=Object.keys(all).filter(g=>runs.every(r=>r.sc.gallery.groups[g]));if(!choices.length)return;
  let group=choices.includes('load input')?'load input':choices[0],entity,field,version=0,span=168,first=0;
  async function paint(){
    const current=++version;controls.replaceChildren();graph.replaceChildren();
    const holders=runs.map(r=>r.sc.gallery.groups[group]);
    const ids=Object.keys(holders[0].entities).filter(id=>holders.every(h=>h.entities[id]));
    const fields=holders[0].fields.filter(k=>holders.every(h=>h.fields.includes(k)));
    selectControl(controls,'Source',choices.map(x=>[x,readable(x)]),group,v=>{group=v;paint();});
    if(!ids.length||!fields.length)return;
    if(!ids.includes(entity))entity=ids.includes('Total')?'Total':ids[0];
    if(!fields.includes(field))field=fields.includes(sensible[group])?sensible[group]:fields[0];
    selectControl(controls,'Element',ids.map(x=>[x,x]),entity,v=>{entity=v;paint();});
    selectControl(controls,'Quantity',fields.map(x=>[x,readable(x)]),field,v=>{field=v;paint();});
    if(/cost|credit/.test(field)&&runs.some(r=>!r.currency||r.currency!==runs[0].currency)){graph.append(elem('p','A common recorded currency is required.'));return;}
    const axes=await Promise.all(runs.map(r=>r.read(r.sc.gallery.timestamps)));
    const indices=axes.map(axis=>new Map(axis.map((t,i)=>[t,i])));
    const common=axes[0].filter(t=>indices.every(m=>m.has(t)));
    if(!common.length){graph.append(elem('p','No common timestamps.'));return;}
    selectControl(controls,'Window',[[24,'24 hours'],[168,'7 days'],[336,'14 days'],[0,'Full overlap']],span,v=>{span=Number(v);first=0;paint();});
    const size=span||common.length;
    first=Math.max(0,Math.min(first,common.length-size));
    button(controls,'< Earlier',()=>{first-=size;paint();}).disabled=first===0;
    button(controls,'Later >',()=>{first+=size;paint();}).disabled=first+size>=common.length;
    const axis=common.slice(first,first+size);
    const series=[];
    for(let i=0;i<runs.length;i++){
      const start=indices[i].get(axis[0]),end=indices[i].get(axis.at(-1))+1;
      const values=await seriesValues(holders[i],entity,field,start,end,runs[i].read);
      series.push({label:runs[i].label,data:axis.map(t=>values[indices[i].get(t)-start])});
    }
    if(current===version&&panel.isConnected)interactiveChart(graph,readable(field)+' · '+entity,axis,series,unitOf(field));
  }
  await paint();
}

