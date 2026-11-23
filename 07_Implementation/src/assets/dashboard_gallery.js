// Interactive views over immutable, time-indexed report blocks.
const focusState = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
const galleryState = {group: focusState.group || 'load input', entity: focusState.entity || 'Total',
  field: '', hour: 0, first: 0, span: 168, mode: 'Time series', overlay: '', scenario: focusState.scenario || ''};
let galleryVersion = 0;
const groupsFor = {
  'Study inputs':['load input','PV input','solar source'],
  'Network':['bus','line','system'],
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
    for(let j=i;j<Math.min(i+stride,data.length);j++){
      if(!Number.isFinite(data[j]))continue;
      if(min<0||data[j]<data[min])min=j;
      if(max<0||data[j]>data[max])max=j;
    }
    if(min<0){started=false;continue;}
    for(const j of [...new Set([Math.min(min,max),Math.max(min,max)])]){
      if(started)ctx.lineTo(x(j),y(data[j]));else{ctx.moveTo(x(j),y(data[j]));started=true;}
      if(data.length===1)ctx.fillRect(x(j)-2,y(data[j])-2,4,4);
    }
  }
  ctx.stroke();
}
function interactiveChart(root,title,axis,series,unit,options={}) {
  const panel=elem('div',undefined,'chart explorer-chart'),cv=elem('canvas'),tip=elem('output'),legend=elem('div',undefined,'legend');
  cv.tabIndex=0;cv.setAttribute('aria-label',title);panel.append(elem('h3',title),cv,tip,legend);root.append(panel);
  let left=0,right=axis.length,drag=null;
  const active=series.map(()=>true);
  const heat=options.mode==='Heatmap',stack=options.mode==='Stack elements',bars=options.mode==='Selected hour';
  const visible=()=>series.filter((s,i)=>active[i]);
  function px(){return Math.max(1,cv.clientWidth-84);}
  const xpos=i=>65+(i-left)*px()/Math.max(1,right-left-1);
  function draw() {
    if(!cv.isConnected)return;
    const w=Math.max(240,cv.clientWidth),h=heat?Math.min(650,Math.max(240,series.length*15+60)):300,dpr=window.devicePixelRatio||1;
    cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);cv.style.height=h+'px';
    const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);
    ctx.font='12px Segoe UI';let low=Infinity,high=-Infinity;
    for(const s of visible())for(let i=left;i<right;i++)if(Number.isFinite(s.data[i])){low=Math.min(low,s.data[i]);high=Math.max(high,s.data[i]);}
    if(!Number.isFinite(low)){ctx.fillStyle='#435c64';ctx.fillText('No recorded values in this selection',25,48);return;}
    if(stack){
      low=high=0;
      for(let i=left;i<right;i++){
        let pos=0,neg=0;
        for(const s of visible()){const v=s.data[i];if(Number.isFinite(v)){pos+=Math.max(v,0);neg+=Math.min(v,0);}}
        high=Math.max(high,pos);low=Math.min(low,neg);
      }
    }
    if(heat) {
      const rows=visible(),dy=(h-50)/Math.max(1,rows.length),stride=Math.max(1,Math.ceil((right-left)/px()));
      rows.forEach((s,r)=>{
        if(rows.length<27||r%4===0){ctx.fillStyle='#345260';ctx.fillText(s.label.slice(0,9),3,16+(r+.55)*dy);}
        for(let i=left;i<right;i+=stride){
          const bins=s.data.slice(i,Math.min(i+stride,right)).filter(Number.isFinite);
          if(!bins.length)continue;
          // Use the lowest voltage or highest magnitude in each bin, as appropriate.
          const v=options.field==='voltage_pu'?Math.min(...bins):Math.max(...bins);
          const z=(v-low)/(high-low||1);ctx.fillStyle='hsl('+(205-175*z)+' 58% '+(78-34*z)+'%)';
          ctx.fillRect(xpos(i),12+r*dy,Math.max(1,stride*px()/Math.max(1,right-left-1)),dy);
        }
      });
      ctx.fillStyle='#345260';ctx.fillText(fmt(low,4)+' – '+fmt(high,4)+' '+unit,65,h-4);
    } else {
      if(bars){low=Math.min(0,low);high=Math.max(0,high);}
      if(low===high){const pad=Math.abs(low)*.03||1;low-=pad;high+=pad;}
      const y=v=>h-44-(v-low)/(high-low)*(h-70);
      for(let j=0;j<=4;j++){const v=low+(high-low)*j/4;ctx.fillStyle='#415866';ctx.fillText(fmt(v,4),1,y(v)+4);
        ctx.strokeStyle='#dee5e6';ctx.beginPath();ctx.moveTo(64,y(v));ctx.lineTo(w-12,y(v));ctx.stroke();}
      const positive=new Float64Array(right-left), negative=new Float64Array(right-left);
      series.forEach((s,j)=>{if(!active[j])return;ctx.strokeStyle=ctx.fillStyle=palette[j%palette.length];ctx.lineWidth=2;
        if(stack){
          const width=Math.max(1,px()/Math.max(1,right-left)*.85);
          for(let i=left;i<right;i++){
            const v=s.data[i];if(!Number.isFinite(v)||v===0)continue;
            const sums=v>0?positive:negative,start=sums[i-left];
            sums[i-left]+=v;
            ctx.fillRect(xpos(i)-width/2,Math.min(y(start),y(start+v)),width,Math.abs(y(start+v)-y(start)));
          }
        } else if(bars){for(let i=left;i<right;i++)if(Number.isFinite(s.data[i]))ctx.fillRect(xpos(i)-2,Math.min(y(0),y(s.data[i])),Math.max(2,px()/(right-left)*.60),Math.max(1,Math.abs(y(0)-y(s.data[i]))));}
        else drawTrace(ctx,s.data.slice(left,right),i=>xpos(i+left),y,px());
      });
      if(options.cursor>=left&&options.cursor<right){ctx.strokeStyle='#74818a';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(xpos(options.cursor),18);ctx.lineTo(xpos(options.cursor),h-40);ctx.stroke();}
    }
    ctx.fillStyle='#39535b';ctx.fillText(axis[left]||'',65,h-22);const end=axis[right-1]||'';ctx.fillText(end,w-12-ctx.measureText(end).width,h-22);
  }
  series.forEach((s,i)=>{const b=button(legend,s.label,()=>{active[i]=!active[i];b.setAttribute('aria-pressed',active[i]);draw();});
    b.style.borderBottom='3px solid '+palette[i%palette.length];b.setAttribute('aria-pressed','true');});
  function index(e){return Math.max(left,Math.min(right-1,left+Math.round((e.offsetX-65)/px()*Math.max(1,right-left-1))));}
  cv.onpointermove=e=>{const i=index(e);let a=visible();
    if(heat){const id=Math.floor((e.offsetY-12)/(cv.clientHeight-50)*a.length);a=a.slice(Math.max(0,id),Math.max(0,id)+1);}
    tip.textContent=[axis[i],...a.map(s=>s.label+' '+(s.data[i]==null?'Not recorded':String(s.data[i])+' '+unit))].join(' · ');};
  cv.onpointerdown=e=>{drag=index(e);cv.setPointerCapture(e.pointerId);};
  cv.onpointerup=e=>{const i=index(e);if(drag!=null&&Math.abs(i-drag)>1){[left,right]=[Math.min(i,drag),Math.max(i,drag)+1];draw();}
    else if(options.pick)options.pick(i);drag=null;};
  cv.ondblclick=()=>{left=0;right=axis.length;draw();};
  const actions=selectionPanel(panel);
  button(actions,'Reset zoom',()=>{left=0;right=axis.length;draw();});
  button(actions,'Pan left',()=>{const n=Math.min(left,Math.ceil((right-left)/2));left-=n;right-=n;draw();});
  button(actions,'Pan right',()=>{const n=Math.min(axis.length-right,Math.ceil((right-left)/2));left+=n;right+=n;draw();});
  button(actions,'Save PNG',()=>cv.toBlob(blob=>saveBlob(blob,'chart.png')));
  button(actions,'Save CSV',()=>saveRows(['axis',...visible().map(s=>s.label+(unit?' ['+unit+']':''))],
    axis.slice(left,right).map((v,j)=>[v,...visible().map(s=>s.data[j+left])]),'chart.csv'));
  redraw.push(draw);draw();return draw;
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
  screen='Network';tabs();render();
}
function networkMap(root,topology,samples,group,field,onSelect) {
  if(!run.metadata.layout?.positions)return;
  const positions=run.metadata.layout.positions,svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  const pts=Object.values(positions),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  if(!pts.length)return;
  svg.setAttribute('viewBox',[Math.min(...xs)-36,Math.min(...ys)-45,Math.max(...xs)-Math.min(...xs)+72,Math.max(...ys)-Math.min(...ys)+85].join(' '));
  svg.setAttribute('class','feeder');svg.setAttribute('aria-label','Clickable network at selected hour');
  const values=Object.values(samples).filter(Number.isFinite),lo=Math.min(...values),hi=Math.max(...values);
  const color=v=>Number.isFinite(v)?'hsl('+(200-165*(v-lo)/(hi-lo||1))+' 58% 45%)':'#a3b0b5';
  function node(tag,attrs,kind,id,text){
    const n=document.createElementNS(svg.namespaceURI,tag);
    for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);
    n.setAttribute('tabindex','0');n.setAttribute('role','button');n.setAttribute('aria-label',kind+' '+id);
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=text;n.append(title);
    n.onclick=()=>onSelect(kind,id);n.onkeydown=e=>{if(e.key==='Enter')onSelect(kind,id);};svg.append(n);return n;
  }
  for(const line of topology?.lines||[]){
    const pts=run.metadata.layout.routes?.[line.line_id]||[positions[line.from_bus],positions[line.to_bus]];
    if(pts.every(Boolean))node('polyline',{points:pts.map(p=>p.join(',')).join(' '),fill:'none',stroke:group==='line'?color(samples[line.line_id]):'#71878c','stroke-width':7},'line',line.line_id,
      line.line_id+(group==='line'?' · '+(samples[line.line_id]??'Not recorded')+' '+unitOf(field):''));
  }
  for(const [id,[x,y]] of Object.entries(positions)){
    node('circle',{cx:x,cy:y,r:13,fill:group==='bus'?color(samples[id]):'#3b6c78',stroke:'#253d47','stroke-width':2},'bus',id,
      'Bus '+id+(group==='bus'?' · '+(samples[id]??'Not recorded')+' '+unitOf(field):''));
    const label=document.createElementNS(svg.namespaceURI,'text');label.setAttribute('x',x);label.setAttribute('y',y-17);
    label.setAttribute('text-anchor','middle');label.setAttribute('font-size','21');label.setAttribute('pointer-events','none');label.textContent=id;svg.append(label);
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
      ['Site',run.input_info?.site?JSON.stringify(run.input_info.site):null],['Slack voltage (pu)',slack?.v_set_pu],
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
  if(screen==='Network'&&['bus','line'].includes(state.group)||['Selected hour','Ranked at hour'].includes(state.mode)){
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
  const info=elem('details');info.open=screen==='Network';info.append(elem('summary',entity+' · '+axis[state.hour]));
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
  if(screen==='Network'&&['bus','line'].includes(state.group))networkMap(panel,run.metadata.topology,samples,state.group,field,(k,id)=>jump(k,id,state.hour));
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
    .map(([k,s])=>({label:(r.manifest.folder||'Run '+(i+1))+' · '+s.label+' · '+(r.metadata?.topology?.buses?.find(b=>b.is_slack)?.v_set_pu??'?')+' pu · '+String(r.manifest.run_id).slice(-8),sc:s,read:r.readBlock||block,clock:r.manifest.clock,currency:r.manifest.currency})));
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

