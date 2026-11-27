// Academic presets read the same indexed blocks as the chart editor.
const academicTopicLabels={'Study Inputs':'Inputs & Forecasting','Power & Energy':'System Operation','Compare Runs':'Compare Studies'};
const academicState={};
const academicSections={Network:{},'Study Inputs':{},'Power & Energy':{},BESS:{},Economics:{},Optimization:{},'Compare Runs':{}};
const academicNumber=value=>typeof value==='number'&&Number.isFinite(value);
const academicSum=values=>values.reduce((a,b)=>a+b,0);
const academicRatio=(a,b)=>academicNumber(a)&&academicNumber(b)&&b!==0?a/b:null;
const academicNumeric=(a,b)=>String(a).localeCompare(String(b),'en',{numeric:true});
const academicValid=value=>academicNumber(value)?value:null;
const academicMetric=(ctx,key)=>academicValid(asMetrics(ctx.data)[key]);
const academicStatic=ctx=>ctx.archive.manifest.kind==='base case'||ctx.archive.metadata?.static!=null;
const academicHas=(ctx,group,field)=>ctx.gallery.groups[group]?.fields.includes(field);
const academicIds=(ctx,group)=>Object.keys(ctx.gallery.groups[group]?.entities||{}).sort(academicNumeric);
const academicTopology=ctx=>ctx.archive.metadata?.topology||{};
const academicLimits=ctx=>ctx.archive.metadata?.simulation||ctx.archive.manifest.simulation||{};
const academicSeries=(ctx,group,entity,field,range)=>sampleValues(ctx,{group,field},entity,range.first,range.last);
const academicSys=(ctx,field,range)=>academicSeries(ctx,'system','System',field,range);
const academicTrace=(label,data,style='line',other={})=>({label,data,style,...other});
const academicConfig=Object.freeze({
  Network:'02_Network_and_Voltage','Study Inputs':'03_Load_and_Forecasting',
  'Power & Energy':'04_PV_and_System_Operation',BESS:'06_BESS_Performance',
  Economics:'07_Economics',Optimization:'08_Optimization','Compare Runs':'09_Comparative_Studies'
});

async function academicRange(ctx,full=false) {
  const whole=await timeline(ctx),dt=ctx.archive.manifest.dt_hours;
  const [first,last]=full?[0,whole.length]:chartWindow(whole,workspace.state.time,dt);
  const axis=whole.slice(first,last);
  const durations=academicHas(ctx,'system','dt_hours')?
    await academicSys(ctx,'dt_hours',{first,last}):axis.map(()=>dt);
  const counts=new Map();
  for(const stamp of whole)counts.set(stamp,(counts.get(stamp)||0)+1);
  const valid=axis.map(stamp=>!academicStatic(ctx)&&Number.isFinite(stampMillis(stamp))&&counts.get(stamp)===1);
  return {whole,axis,first,last,durations:durations.map((dt,i)=>valid[i]&&dt>0?dt:null),valid};
}

function academicStats(values,range) {
  let count=0,hours=0,sum=0,minimum=null,maximum=null,peak=null,timed=0;
  for(const [i,v] of values.entries()){
    if(!academicNumber(v)||range.valid?.[i]===false)continue;
    count++;
    if(maximum===null||v>maximum){maximum=v;peak=range.axis[i];}
    if(minimum===null||v<minimum)minimum=v;
    const dt=range.durations[i];
    if(dt>0){timed++;hours+=dt;sum+=v*dt;}
  }
  return {count,hours,timed,minimum,maximum,peak,mean:timed&&timed===count?sum/hours:null,energy:timed?sum:null};
}

function academicBuckets(axis,durations,series,key=stamp=>stamp.slice(0,7),power=true,observed=null) {
  const buckets=new Map();
  for(const [i,stamp] of axis.entries()){
    if(observed?.[i]===false||!Number.isFinite(stampMillis(stamp)))continue;
    const label=key(stamp);
    if(!buckets.has(label))buckets.set(label,{sum:series.map(()=>0),samples:series.map(()=>0),hours:series.map(()=>0),count:0});
    const row=buckets.get(label),dt=durations[i];row.count++;
    series.forEach((values,j)=>{
      if(!academicNumber(values[i])||(power&&!(dt>0)))return;
      row.sum[j]+=values[i]*(power?dt:1);row.samples[j]++;if(dt>0)row.hours[j]+=dt;
    });
  }
  return [...buckets].map(([label,row])=>({label,...row,sum:row.sum.map((v,i)=>row.samples[i]?v:null)}));
}

function academicDuration(values,range) {
  const sorted=values.flatMap((value,i)=>academicNumber(value)&&range.durations[i]>0?
    [{value,dt:range.durations[i]}]:[]).sort((a,b)=>b.value-a.value);
  const hours=academicSum(sorted.map(p=>p.dt));let elapsed=0;
  return {hours,axis:sorted.map(point=>(elapsed+=point.dt)*100/hours),data:sorted.map(point=>point.value)};
}

function academicPath(topology,destination) {
  const slack=topology.buses?.find(bus=>bus.is_slack);
  if(!slack)return null;
  const edges=new Map();
  for(const line of topology.lines||[]){
    for(const [a,b] of [[line.from_bus,line.to_bus],[line.to_bus,line.from_bus]]){
      const key=String(a);
      if(!edges.has(key))edges.set(key,[]);
      edges.get(key).push([String(b),String(line.line_id)]);
    }
  }
  const source=String(slack.bus_id),queue=[source],previous=new Map([[source,null]]);
  for(let i=0;i<queue.length&&!previous.has(String(destination));i++){
    const from=queue[i];
    for(const [bus,line] of edges.get(from)||[]){
      if(previous.has(bus))continue;
      previous.set(bus,{from,line});queue.push(bus);
    }
  }
  if(!previous.has(String(destination)))return null;
  const buses=[],lines=[];
  for(let bus=String(destination);bus!==null;){
    buses.push(bus);
    const link=previous.get(bus);
    if(link)lines.push(link.line);
    bus=link?.from??null;
  }
  return {buses:buses.reverse(),lines:lines.reverse()};
}

function academicTable(root,title,head,rows,ctx,extras={}) {
  const holder=elem('details',undefined,'academic-table');
  holder.open=extras.open===true;
  holder.append(elem('summary',title));root.append(holder);
  if(extras.note)holder.append(elem('p',extras.note,'fine'));
  if(!rows.length){holder.append(elem('p','Unavailable in this archive.','empty'));return;}
  grid(holder,head,rows,{renderCell(cell,value,column,row){
    if(extras.renderCell?.(cell,value,column,row))return true;
    if(academicNumber(value)&&value!==0&&Math.abs(value)<.0005){
      cell.textContent=value.toExponential(3);return true;
    }
    return false;
  }});
  publicationTable(holder,title,head,rows,ctx,extras.note);
}

function academicPlot(root,title,axis,traces,unit,ctx,options={}) {
  if(!axis.length||!traces.some(t=>t.data.some(academicNumber))){
    root.append(elem('p',title+' is unavailable for the selected scenario and period.','empty'));return null;
  }
  const plot=elem('article',undefined,'workspace-card academic-figure');root.append(plot);
  plot.append(elem('h3',title));
  const caption=[ctx.data.label,options.note,options.categorical?null:[axis[0],axis.at(-1)].join(' through ')]
    .filter(Boolean).join(' · ');
  plot.append(elem('p',caption,'chart-context'));
  const series=traces.map((t,i)=>({...t,unit,color:t.color||palette[i%palette.length],dash:t.dash||(i%2?'dashed':'solid'),
    runLabel:shortRun(ctx.archive),runId:ctx.archive.manifest.run_id,scenarioLabel:t.scenarioLabel||ctx.data.label}));
  const controller=interactiveChart(plot,title,axis,series,unit,{compact:true,zeroLine:options.zeroLine,
    categorical:options.categorical,coordinates:options.coordinates,axisLabel:options.axisLabel,
    intervals:options.intervals,
    mode:options.stack?'Stack elements':'Time series',pick:options.pick,
    markers:options.markers,filename:safeFilename(shortRun(ctx.archive)+'_'+title),exportHeaders:true});
  publicationActions(plot,controller,{title,caption,ctx,topic:options.topic});
  requestAnimationFrame(()=>controller.draw());
  return controller;
}

function academicMissing(root,message) {root.append(elem('p',message,'empty'));}
function academicLink(kind,id,stamp,ctx) {
  workspace.state.time.cursor=stamp;
  selectedEntity(kind,id,stamp,ctx.scenario);
}
function academicPicker(root,label,ids,initial,change,name=id=>id) {
  if(!ids.length)return null;
  return selectControl(root,label,ids.map(id=>[String(id),name(id)]),initial,change);
}

async function academicChronology(root,ctx,range,title,unit,fields,{group='system',entity='System',pick=null,stack=false,zeroLine=false}={}) {
  const selected=fields.filter(([field])=>academicHas(ctx,group,field));
  const arrays=await Promise.all(selected.map(([field])=>academicSeries(ctx,group,entity,field,range)));
  const resolution=resolvedResolution(workspace.state.time.resolution||'auto',range.axis.length);
  const traces=arrays.map((values,i)=>{
    const [field,name,sign=1,style='line']=selected[i];
    return {...academicTrace(name,values.map((v,j)=>academicNumber(v)&&range.valid[j]?v*sign:null),style),field};
  });
  let axis=range.axis,intervals=null;
  if(resolution!=='hourly'){
    for(const trace of traces){
      const aggregated=bucketReadings(range.axis,trace.data,resolution,'auto',null,unit,trace.field,null,range.durations);
      axis=aggregated.axis;intervals=aggregated.intervals;
      trace.data=aggregated.data;trace.aggregation=aggregated.operation;
      trace.label+=' · '+aggregated.operation;
    }
  }
  academicPlot(root,title,axis,traces,unit,ctx,{stack,zeroLine,intervals,
    note:resolution==='hourly'?'Recorded samples':resolutionLabels[resolution]+' aggregation',
    pick:pick&&((i)=>pick(intervals?.[i]?.start||axis[i]))});
}

async function academicHour(ctx,range,mode) {
  if(academicStatic(ctx))return range.whole.length?0:-1;
  const cursor=range.whole.indexOf(workspace.state.time.cursor);
  if(mode==='selected')return cursor<0?range.first:cursor;
  const field={low:'voltage_min_pu',high:'voltage_max_pu',severity:'voltage_violation_max_pu'}[mode];
  const data=await academicSys(ctx,field,range);
  let i=-1;
  data.forEach((value,index)=>{
    if(academicNumber(value)&&range.valid[index]&&(i<0||(mode==='low'?value<data[i]:value>data[i])))i=index;
  });
  return i<0?-1:range.first+i;
}

async function academicVoltageProfile(root,ctx,range,mode) {
  const topology=academicTopology(ctx),ids=(topology.buses?.map(bus=>String(bus.bus_id))||academicIds(ctx,'bus')).sort(academicNumeric);
  const controls=elem('div',undefined,'controls');root.append(controls);
  const options=[['selected','Selected hour'],['low','Lowest recorded minimum'],['high','Highest recorded maximum'],['severity','Largest recorded violation']];
  const pairs=Object.entries(ctx.archive.scenarios).filter(([id])=>id!==ctx.scenario);
  const state=academicState.Network||{},body=elem('div');root.append(body);
  if(!academicStatic(ctx)&&mode!=='statistics'){
    selectControl(controls,'Hour criterion',options,state.voltageHour||'selected',value=>{state.voltageHour=value;void repaint();});
    selectControl(controls,'Overlay',[['','Current scenario'],...pairs.map(([id,s])=>[id,s.label]),['raw','Same-scenario uncontrolled voltages']],
      state.voltageReference||'',value=>{state.voltageReference=value;void repaint();});
  }
  let ticket=0;
  async function paint(update){
    const field=mode==='angle'?'voltage_angle_deg':'voltage_pu';
    const data=elem('div');
    const values=(target,field,window)=>Promise.all(ids.map(id=>academicSeries(target,'bus',id,field,window)));
    let note='Numeric bus order includes the slack. Read the single-line diagram for physical connectivity.',traces=[],rows=[];
    let head=['Bus ID'],stamp='',profileIndex=-1;
    if(mode==='statistics'){
      const series=await values(ctx,field,range);
      const stats=series.map(values=>academicStats(values,range));
      for(const [key,label] of [['minimum','Minimum'],['mean','Time-weighted mean'],['maximum','Maximum']])
        traces.push(academicTrace(label,stats.map(s=>s[key])));
      head.push('Minimum (pu)','Time-weighted mean (pu)','Maximum (pu)','Observed hours','Maximum timestamp');
      rows=ids.map((id,i)=>[id,stats[i].minimum,stats[i].mean,stats[i].maximum,stats[i].hours,stats[i].peak]);
      note+=' Extrema can occur at different times. Covered hours are listed by bus.';
    }else{
      const i=profileIndex=await academicHour(ctx,range,state.voltageHour||'selected');
      if(i<0||i>=range.whole.length){academicMissing(data,'The selected voltage criterion has no retained readings.');return data;}
      stamp=range.whole[i];
      const measurements=(await values(ctx,field,{first:i,last:i+1})).map(([v])=>v);
      traces=[academicTrace(ctx.data.label,measurements)];
      head.push(ctx.data.label+(mode==='angle'?' (degrees)':' (pu)'));
      rows=ids.map((id,j)=>[id,measurements[j]]);
      note+=' '+stamp+(academicStatic(ctx)?'':' · '+options.find(([id])=>id===(state.voltageHour||'selected'))?.[1])+'.';
      if(mode==='angle')note+=' Angles use the archived solver slack reference.';
      if(pairs.some(([id])=>id===state.voltageReference)){
        const ref=chartContext(ctx.key,state.voltageReference),axis=await timeline(ref),j=axis.indexOf(stamp);
        const issue=comparisonIssue(ctx.archive.manifest,ref.archive.manifest,field,{sameRun:true});
        if(j>=0&&!issue&&axis.lastIndexOf(stamp)===j&&range.whole.lastIndexOf(stamp)===i){
          const paired=(await values(ref,field,{first:j,last:j+1})).map(([v])=>v);
          traces.push(academicTrace(ref.data.label,paired,'line',{scenarioLabel:ref.data.label}));
          head.push(ref.data.label+(mode==='angle'?' (degrees)':' (pu)'));rows.forEach((r,k)=>r.push(paired[k]));
          note+=' Common timestamp across both scenarios.';
        }else note+=' Reference unavailable: '+(issue||'no unique matching timestamp.');
      }else if(state.voltageReference==='raw'&&mode!=='angle'){
        const raw=(await values(ctx,'uncontrolled_voltage_pu',{first:i,last:i+1})).map(([v])=>v);
        if(raw.some(academicNumber)){
          traces.push(academicTrace('Same-scenario uncontrolled',raw));
          head.push('Uncontrolled (pu)');rows.forEach((r,k)=>r.push(raw[k]));
        }else note+=' Same-scenario uncontrolled bus readings are unavailable.';
      }
    }
    if(mode!=='angle'){
      const limits=academicLimits(ctx);
      for(const [field,label] of [['voltage_min_pu','Lower limit'],['voltage_max_pu','Upper limit']]){
        if(academicNumber(limits[field]))traces.push(academicTrace(label,ids.map(()=>limits[field]),'line',{dash:'dashed'}));
      }
    }
    academicPlot(data,mode==='angle'?'Bus voltage phase angle':mode==='statistics'?'Bus voltage statistics':'Voltage magnitude by bus number',
      ids,traces,mode==='angle'?'degrees':'pu',ctx,{categorical:true,markers:true,axisLabel:'Bus number',note,
        pick:i=>academicLink('bus',ids[i],stamp||range.axis[0],ctx)});
    academicTable(data,'Bus profile data',head,rows,ctx,{note,renderCell(cell,id,column){
      if(column!==0)return false;
      button(cell,String(id),()=>academicLink('bus',id,profileIndex<0?range.axis[0]:stamp,ctx));return true;
    }});
    return data;
  }
  async function repaint(){
    const update=++ticket;
    try{const data=await paint(update);if(update===ticket)body.replaceChildren(data);}
    catch(error){if(update===ticket){body.replaceChildren();academicMissing(body,error.message);}}
  }
  await repaint();
}

async function academicVoltageTime(root,ctx,range,mode) {
  const limits=academicLimits(ctx);
  const fields=[['voltage_min_pu','Minimum'],['voltage_mean_pu','Mean across all buses incl. slack'],['voltage_max_pu','Maximum']];
  if(mode==='envelope'){
    const mins=await academicSys(ctx,'voltage_min_pu',range),maxs=await academicSys(ctx,'voltage_max_pu',range);
    const minBus=await academicSys(ctx,'minimum_voltage_bus',range),maxBus=await academicSys(ctx,'maximum_voltage_bus',range);
    const means=await academicSys(ctx,'voltage_mean_pu',range);
    const resolution=resolvedResolution(workspace.state.time.resolution||'auto',range.axis.length);
    const bundle=(array,field)=>bucketReadings(range.axis,array,resolution,'auto',null,'pu',field,null,range.durations);
    const main=[mins,means,maxs].map((values,i)=>bundle(values,fields[i][0]));
    const overallAxis=main[0].axis,base=main.map((data,i)=>academicTrace(fields[i][1],data.data));
    const state=academicState.Network,possible=Object.keys(ctx.archive.scenarios).filter(id=>id!==ctx.scenario);
    const refs=elem('div',undefined,'controls');root.append(refs);
    if(possible.length)selectControl(refs,'Independent scenario overlay',[['','Current scenario'],...possible.map(id=>[id,ctx.archive.scenarios[id].label])],
      possible.includes(state.timeReference)?state.timeReference:'',value=>{state.timeReference=value;refreshWorkspace();});
    let match=null;
    if(possible.includes(state.timeReference)){
      const reference=chartContext(ctx.key,state.timeReference),axis=await timeline(reference);
      const offset=axis.indexOf(range.axis[0]),end=offset+range.axis.length;
      if(offset>=0&&range.axis.every((stamp,i)=>axis[offset+i]===stamp)&&range.valid.every(Boolean)){
        const win={first:offset,last:end};
        const durations=await academicSys(reference,'dt_hours',win);
        if(durations.every((dt,i)=>dt===range.durations[i])){
          match={reference,win};
          for(const [field,label] of [fields[0],fields[2]]){
            const values=await academicSys(reference,field,win);
            base.push(academicTrace(reference.data.label+' · '+label,bundle(values,field).data,'line',
              {dash:'dashed',scenarioLabel:reference.data.label}));
          }
        }
      }
      if(!match)root.append(elem('p','Independent overlay requires the same retained timestamps and step durations.','fine'));
    }
    for(const [field,label] of [['voltage_min_pu','Lower limit'],['voltage_max_pu','Upper limit']]){
      if(academicNumber(limits[field]))base.push(academicTrace(label,overallAxis.map(()=>limits[field]),'line',{dash:'dashed'}));
    }
    academicPlot(root,'Feeder voltage envelope',overallAxis,base,'pu',ctx,
      {note:resolutionLabels[resolution]+' · Min/max preserve period extremes. Mean includes the slack.',intervals:main[0].intervals,
        pick:i=>{
          const interval=main[0].intervals?.[i], first=interval?range.axis.indexOf(interval.start):i;
          const last=interval?range.axis.indexOf(interval.end):i;
          let current=first;
          for(let j=first;j<=last;j++)if(academicNumber(mins[j])&&(!academicNumber(mins[current])||mins[j]<mins[current]))current=j;
          if(minBus[current]!=null)academicLink('bus',String(minBus[current]),range.axis[current],ctx);
        }});
    const a=mins.indexOf(academicStats(mins,range).minimum),b=maxs.indexOf(academicStats(maxs,range).maximum);
    const ids=academicIds(ctx,'bus'),last=academicState.Network;
    const selected=(last.critical||[String(minBus[a]??''),String(maxBus[b]??'')]).filter((id,i,list)=>ids.includes(id)&&list.indexOf(id)===i);
    const controls=elem('div',undefined,'controls');root.append(controls);
    for(let i=0;i<2;i++)academicPicker(controls,'Critical bus '+(i+1),['',...ids],selected[i]||'',value=>{
      last.critical=[selected[0],selected[1]];last.critical[i]=value;refreshWorkspace();
    },id=>id?'Bus '+id:'None');
    const rows=await Promise.all(selected.map(id=>academicSeries(ctx,'bus',id,'voltage_pu',range)));
    const traces=rows.map((row,i)=>academicTrace('Bus '+selected[i],row));
    if(selected.length&&academicHas(ctx,'bus','uncontrolled_voltage_pu')){
      const before=await Promise.all(selected.map(id=>academicSeries(ctx,'bus',id,'uncontrolled_voltage_pu',range)));
      traces.push(...before.map((row,i)=>academicTrace('Bus '+selected[i]+' · uncontrolled reference',row,'line',{dash:'dashed'})));
    }
    if(match){
      const reference=match.reference;
      const readings=await Promise.all(selected.map(id=>academicSeries(reference,'bus',id,'voltage_pu',match.win)));
      traces.push(...readings.map((row,i)=>academicTrace('Bus '+selected[i]+' · '+reference.data.label,row,'line',
        {dash:'dashed',scenarioLabel:reference.data.label})));
    }
    for(const [field,label] of [['voltage_min_pu','Lower limit'],['voltage_max_pu','Upper limit']]){
      if(academicNumber(limits[field]))traces.push(academicTrace(label,range.axis.map(()=>limits[field]),'line',{dash:'dashed'}));
    }
    if(selected.length)academicPlot(root,'Critical-bus voltage comparison',range.axis,traces,'pu',ctx,
      {note:'Raw readings. Automatic selection uses buses at the selected period minimum and maximum.',
        pick:i=>academicLink('bus',selected[0],range.axis[i],ctx)});
    return;
  }
  if(mode==='duration'){
    for(const [field,label] of [fields[0],fields[2]]){
      const result=academicDuration(await academicSys(ctx,field,range),range);
      academicPlot(root,label+' voltage duration',result.axis,[academicTrace(label,result.data)],'pu',ctx,
        {categorical:true,coordinates:result.axis,axisLabel:'Elapsed exceedance (%)',note:fmt(result.hours)+' h with valid timed values.'});
    }
    return;
  }
  if(!academicNumber(limits.voltage_min_pu)||!academicNumber(limits.voltage_max_pu)){
    academicMissing(root,'Configured voltage limits are unavailable.');return;
  }
  const ids=academicIds(ctx,'bus'),topologyIds=academicTopology(ctx).buses?.map(bus=>String(bus.bus_id))||ids;
  if(!ids.length){academicMissing(root,'Bus-hour voltage readings are unavailable.');return;}
  const rows=[];
  for(const [field,stage] of [['voltage_pu','Final'],['uncontrolled_voltage_pu','Before control']]){
    if(!academicHas(ctx,'bus',field))continue;
    const low=Array(range.axis.length).fill(0),high=low.slice(),verified=low.slice();
    let lowBus=0,highBus=0,lowSeverity=0,highSeverity=0;
    for(const id of topologyIds){
      const values=await academicSeries(ctx,'bus',id,field,range);
      for(const [i,value] of values.entries()){
        const dt=range.durations[i];if(!academicNumber(value)||!(dt>0))continue;
        verified[i]++;
        if(value<limits.voltage_min_pu){low[i]=1;lowBus+=dt;lowSeverity+=(limits.voltage_min_pu-value)*dt;}
        if(value>limits.voltage_max_pu){high[i]=1;highBus+=dt;highSeverity+=(value-limits.voltage_max_pu)*dt;}
      }
    }
    const actual=range.durations.map((dt,i)=>verified[i]===topologyIds.length?dt||0:0);
    const offsets=actual.map((dt,i)=>dt*(low[i]||high[i]));
    rows.push([stage,academicSum(actual),academicSum(range.durations.map(v=>v||0))-academicSum(actual),
      actual.some(dt=>dt>0)?academicSum(actual.map((dt,i)=>dt*low[i])):null,rows.length||lowBus||verified.some(x=>x)?lowBus:null,
      actual.some(dt=>dt>0)?academicSum(actual.map((dt,i)=>dt*high[i])):null,verified.some(x=>x)?highBus:null,
      actual.some(dt=>dt>0)?academicSum(offsets):null,verified.some(x=>x)?lowSeverity:null,verified.some(x=>x)?highSeverity:null]);
  }
  academicTable(root,'Voltage violation duration', ['Stage','Verified system hours','Unverified retained hours','Undervoltage hours',
    'Undervoltage bus-hours','Overvoltage hours','Overvoltage bus-hours','Any violation hours','Deficit (pu·h)','Excess (pu·h)'],
    rows,ctx,{open:true,note:'Strict comparison to archived bounds. System hours require complete bus coverage. Bus-hours and severity use known readings only.'});
}

const academicLineFields=[
  ['sending_p_kw','p_kw','Sending P (kW)'],['sending_q_kvar','q_kvar','Sending Q (kvar)'],
  ['receiving_p_kw','','Receiving P (kW)'],['receiving_q_kvar','','Receiving Q (kvar)'],
  ['current_a','','Current (A)'],['ampacity_a','','Rating (A)'],['loading_percent','','Loading (%)'],
  ['loss_p_kw','loss_kw','Active loss (kW)'],['loss_q_kvar','','Reactive loss (kvar)']
];
function academicLineField(ctx,first,fallback){return academicHas(ctx,'line',first)?first:fallback||first;}
function academicBranches(ctx){
  return [...(academicTopology(ctx).lines||[])].sort((a,b)=>academicNumeric(a.from_bus,b.from_bus)||
    academicNumeric(a.to_bus,b.to_bus)||academicNumeric(a.line_id,b.line_id));
}
async function academicNetworkRecords(root,ctx,range) {
  const i=await academicHour(ctx,range,'selected'),win={first:i,last:i+1},stamp=range.whole[i];
  if(i<0)return academicMissing(root,'No snapshot is available.');
  const busFields=['voltage_pu','voltage_angle_deg','requested_load_kw','requested_load_kvar','load_input_kw',
    'load_input_kvar','shedding_kw','shedding_kvar','available_pv_kw','pv_input_kw','pv_input_kvar','bess_input_kw','bess_input_kvar','bess_soc_percent'];
  const buses=academicTopology(ctx).buses||[];
  const busRows=await Promise.all(buses.slice().sort((a,b)=>academicNumeric(a.bus_id,b.bus_id)).map(async bus=>[
    bus.bus_id,bus.is_slack?'Slack':'Bus',...(await Promise.all(busFields.map(field=>
      academicSeries(ctx,'bus',String(bus.bus_id),field,win).then(v=>v[0]))))]));
  const lines=academicBranches(ctx);
  const lineRows=await Promise.all(lines.map(async line=>[line.line_id,line.from_bus,line.to_bus,
    ...(await Promise.all(academicLineFields.map(([first,alias])=>
      academicSeries(ctx,'line',String(line.line_id),academicLineField(ctx,first,alias),win).then(v=>v[0]))))]));
  const link=kind=>(cell,id,column)=>{
    if(column!==0)return false;
    button(cell,String(id),()=>academicLink(kind,id,stamp,ctx));return true;
  };
  academicTable(root,'Bus electrical records',['Bus ID','Type',...busFields.map(readable)],busRows,ctx,{open:true,note:stamp,renderCell:link('bus')});
  academicTable(root,'Branch electrical records',['Branch ID','From','To',...academicLineFields.map(field=>field[2])],
    lineRows,ctx,{note:stamp+' · Flow sign follows recorded From → To orientation. Blank ratings are unavailable.',renderCell:link('line')});
}
async function academicFeederPath(root,ctx,range) {
  const topology=academicTopology(ctx),state=academicState.Network,i=await academicHour(ctx,range,'selected');
  const ids=(topology.buses||[]).filter(bus=>!bus.is_slack).map(bus=>String(bus.bus_id)).sort(academicNumeric);
  if(!ids.length||i<0)return academicMissing(root,'Slack, topology, or snapshot readings are unavailable.');
  const destination=ids.includes(state.destination)?state.destination:ids.at(-1);
  academicPicker(root,'Destination bus',ids,destination,value=>{state.destination=value;refreshWorkspace();},id=>'Bus '+id);
  const path=academicPath(topology,destination),win={first:i,last:i+1},stamp=range.whole[i];
  if(!path)return academicMissing(root,'No connected path exists from the slack to this bus.');
  if(root.isConnected)state.pathActive=path;
  highlightAcademicPath(path);
  const power=await Promise.all(path.lines.map(id=>academicSeries(ctx,'line',id,academicLineField(ctx,'sending_p_kw','p_kw'),win).then(v=>v[0])));
  const volts=await Promise.all(path.buses.map(id=>academicSeries(ctx,'bus',id,'voltage_pu',win).then(v=>v[0])));
  const current=await Promise.all(path.lines.map(id=>academicSeries(ctx,'line',id,'current_a',win).then(v=>v[0])));
  const loss=await Promise.all(path.lines.map(id=>academicSeries(ctx,'line',id,academicLineField(ctx,'loss_p_kw','loss_kw'),win).then(v=>v[0])));
  let cumulative=0;
  const sum=loss.map(v=>(cumulative=academicNumber(v)&&cumulative!==null?cumulative+v:null));
  const opt={categorical:true,markers:true,note:stamp+' · Actual connected slack-to-destination path.'};
  academicPlot(root,'Feeder-path voltage',path.buses,[academicTrace('Voltage',volts)],'pu',ctx,{...opt,axisLabel:'Bus along path',
    pick:j=>academicLink('bus',path.buses[j],stamp,ctx)});
  academicPlot(root,'Path branch active power and cumulative loss',path.lines,[academicTrace('Sending P',power),academicTrace('Cumulative active loss',sum)],
    'kW',ctx,{...opt,axisLabel:'Branch along path',pick:j=>academicLink('line',path.lines[j],stamp,ctx)});
  academicTable(root,'Path branch readings',['Branch','Sending P (kW)','Current (A)','Active loss (kW)','Cumulative loss (kW)'],
    path.lines.map((id,j)=>[id,power[j],current[j],loss[j],sum[j]]),ctx,{note:stamp});
}
function highlightAcademicPath(path,scope=$('content')){
  for(const node of scope.querySelectorAll('.feeder [data-entity]')){
    const ids=node.dataset.kind==='bus'?path.buses:path.lines;
    node.classList.toggle('academic-path',ids.includes(node.dataset.entity));
  }
}
async function academicLosses(root,ctx,range,mode) {
  const lines=academicBranches(ctx);
  if(mode==='time'&&!academicStatic(ctx)){
    await academicChronology(root,ctx,range,'Active network loss','kW',[['loss_p_kw','Active loss']]);
    await academicChronology(root,ctx,range,'Reactive network loss','kvar',[['loss_q_kvar','Reactive loss']]);
    return;
  }
  const staticRun=academicStatic(ctx),isSnapshot=staticRun||mode==='snapshot';
  if(mode==='monthly'&&!staticRun){
    const p=await academicSys(ctx,'loss_p_kw',range),q=await academicSys(ctx,'loss_q_kvar',range);
    const rows=academicBuckets(range.axis,range.durations,[p,q]).map(r=>[r.label,...r.sum,...r.hours]);
    academicPlot(root,'Monthly active network energy loss',rows.map(r=>r[0]),[academicTrace('Active loss',rows.map(r=>r[1]),'bar')],
      'kWh',ctx,{categorical:true});
    academicPlot(root,'Monthly reactive network energy loss',rows.map(r=>r[0]),[academicTrace('Reactive loss',rows.map(r=>r[2]),'bar')],
      'kvarh',ctx,{categorical:true});
    academicTable(root,'Monthly loss data',['Month','Active (kWh)','Reactive (kvarh)','Active valid hours','Reactive valid hours'],rows,ctx);
    return;
  }
  const i=isSnapshot?await academicHour(ctx,range,'selected'):-1;
  const win=isSnapshot?{first:i,last:i+1}:range;
  const rows=await Promise.all(lines.map(async l=>{
    const id=String(l.line_id),[p,q]=await Promise.all([
      academicSeries(ctx,'line',id,academicLineField(ctx,'loss_p_kw','loss_kw'),win),
      academicSeries(ctx,'line',id,'loss_q_kvar',win)]);
    if(isSnapshot)return [id,l.from_bus,l.to_bus,p[0],q[0]];
    const s=academicStats(p,range),t=academicStats(q,range);
    return [id,l.from_bus,l.to_bus,s.energy,t.energy,s.hours,t.hours,s.mean,s.maximum,s.peak];
  }));
  const unit=isSnapshot?'kW':'kWh',qUnit=isSnapshot?'kvar':'kvarh';
  const note=isSnapshot?range.whole[i]:'Integrated over valid retained steps. Branch totals can have different coverage.';
  if(!isSnapshot){
    const [p,q,served,grid,pv,discharge]=await Promise.all(['loss_p_kw','loss_q_kvar','load_input_kw','grid_import_kw','pv_input_kw','bess_discharge_kw']
      .map(field=>academicSys(ctx,field,range)));
    const common=p.map((v,j)=>[v,served[j],grid[j],pv[j],discharge[j]].every(academicNumber)?v:null);
    const sum=values=>academicStats(values,range),pStats=sum(p),qStats=sum(q);
    const shared=values=>sum(values.map((v,j)=>academicNumber(common[j])?v:null)).energy;
    const supply=grid.map((v,j)=>v+pv[j]+discharge[j]);
    const ratio1=academicRatio(shared(p),shared(served)),ratio2=academicRatio(shared(p),shared(supply));
    const price=ctx.archive.manifest.economics?.grid_import_tariff_per_kwh;
    const branchComplete=rows.length&&rows.every(r=>r[5]===pStats.hours&&r[6]===qStats.hours)&&pStats.hours>0&&qStats.hours>0;
    academicTable(root,'System loss totals',['Measure','Value'],[
      ['Network active energy loss (kWh)',pStats.energy],['Network reactive energy loss (kvarh)',qStats.energy],
      ['Active × import tariff proxy',academicNumber(price)&&academicNumber(pStats.energy)?pStats.energy*price:null],
      ['Active loss / served demand (%)',ratio1===null?null:100*ratio1],['Active loss / supplied energy (%)',ratio2===null?null:100*ratio2],
      ['Matched hours for ratios',sum(common).hours],['Active coverage (h)',pStats.hours],['Reactive coverage (h)',qStats.hours],
      ['Peak active loss (kW)',pStats.maximum],['Peak timestamp',pStats.peak],
      ['Highest active loss branch',rows.filter(r=>academicNumber(r[3])).sort((a,b)=>b[3]-a[3])[0]?.[0]],
      ['Sum of branch active less system active (kWh)',branchComplete?academicSum(rows.map(r=>r[3]))-pStats.energy:null],
      ['Sum of branch reactive less system reactive (kvarh)',branchComplete?academicSum(rows.map(r=>r[4]))-qStats.energy:null],
    ],ctx,{open:true,note:'Supply is grid import + utilized PV + AC battery discharge. Tariff proxy is part of electricity cost.'});
  }
  academicPlot(root,'Active loss by branch',rows.map(r=>r[0]),[academicTrace('Active loss',rows.map(r=>r[3]),'bar')],unit,ctx,
    {categorical:true,note,pick:j=>academicLink('line',rows[j][0],range.whole[i]||range.axis[0],ctx)});
  academicTable(root,'Branch loss data',['Branch ID','From','To','Active ('+unit+')','Reactive ('+qUnit+')',
    ...(!isSnapshot?['Active coverage (h)','Reactive coverage (h)','Mean active (kW)','Peak active (kW)','Peak timestamp']:[])],rows,ctx,{note});
}

function registerAcademic(topic,presets) {Object.assign(academicSections[topic],presets);}
registerAcademic('Network',{
  profile:['Voltage magnitude by bus',academicVoltageProfile,'magnitude',true],
  envelope:['Voltage over time and critical buses',academicVoltageTime,'envelope'],
  voltageStats:['Bus voltage statistics',academicVoltageProfile,'statistics'],
  angle:['Bus phase angle',academicVoltageProfile,'angle',true],
  voltageHours:['Voltage violation duration',academicVoltageTime,'hours'],
  voltageDuration:['Voltage duration curves',academicVoltageTime,'duration'],
  paths:['Electrical feeder path',academicFeederPath,null,true],
  records:['Bus and branch electrical tables',academicNetworkRecords,null,true],
  loss:['Network losses over time',academicLosses,'time'],
  lossBranches:['Network loss totals and branches',academicLosses,'branches',true],
  lossMonthly:['Monthly network energy losses',academicLosses,'monthly'],
  lossSnapshot:['Branch loss snapshot',academicLosses,'snapshot',true],
});

function renderAcademic(root,ctx,topic) {
  const presets=academicSections[topic],state=academicState[topic]||=(Object.create(null));
  const choices=Object.entries(presets).filter(([,p])=>(!academicStatic(ctx)||p[3])&&(!p[4]||p[4](ctx)));
  if(!choices.length)return;
  const defaultKey=choices[0][0];
  const choose=choices.some(([key])=>key===state.preset)?state.preset:defaultKey;
  if(topic==='Network'&&choose!=='paths')state.pathActive=null;
  const sectionNode=elem('section',undefined,'academic-topic');root.append(sectionNode);
  const tools=elem('div',undefined,'controls academic-controls');sectionNode.append(tools);
  selectControl(tools,'Engineering view',choices.map(([key,p])=>[key,p[0]]),choose,value=>{
    state.preset=value;refreshWorkspace();
  });
  const body=elem('div',undefined,'academic-body');sectionNode.append(body);
  const [,preset]=choices.find(([key])=>key===choose);
  academicRange(ctx).then(range=>{
    if(body.isConnected)return preset[1](body,ctx,range,preset[2]);
  }).catch(error=>{if(body.isConnected)academicMissing(body,'Unable to read engineering data: '+error.message);});
  if(typeof publicationBatchControl==='function')publicationBatchControl(tools,sectionNode,ctx,topic);
}
