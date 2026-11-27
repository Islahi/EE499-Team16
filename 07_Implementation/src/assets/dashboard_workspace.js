/* Multi-chart report workspace. Saved study files are read only. */
const workspace = {state:null, imports:new Map(), axes:new WeakMap(), scope:new Map(), epoch:0,
  primary:'', editor:'', inspected:null, drawerToken:0, pendingSave:null, pendingHover:null, zoomFrame:null};
const workspacePages=[...Object.keys(chartTopics),'My Dashboard','Compare Runs'];
const layoutKey=()=> 'ee499.dashboard.layout.'+(run.manifest.run_id||run.manifest.timestamp_sha256||'archive');
const storedStatus=()=>focusState._viewer==='qt'?'Saved in this Qt window · export to keep':'Saved for this report';
const readings=ctx=>ctx.archive.readBlock||block;
const selectedWindow=chart=>chart.time.linked?workspace.state.time:chart.time;
const asLocalInput=stamp=>stamp?.replace(' ','T').slice(0,16)||'';
const hourInput=stamp=>stamp?stamp.replace('T',' ')+(stamp.length===16?':00':''):'';
const safeFilename=value=>String(value||'chart').replace(/[^\w.-]+/g,'_').slice(0,105)||'chart';
const shortRun=archive=>archive.manifest.folder||archive.manifest.kind||'Saved run';
const selectedArchive=key=>key==='current'?run:workspace.imports.get(key);
const topicOf=()=>screen==='Compare Runs'?'Compare Runs':screen;
function focusChart(chart) {
  workspace.state.active=chart.id;
  workspace.state.mode='focus';
  refreshWorkspace();
}
function workspaceNumber(value, unit) {
  return isObservation(value)?fmt(value)+(unit?' '+unit:''):'Not recorded';
}
function recordLabel(value){return value==null?'Unknown':value?'Yes':'No';}
function saveLayout() {
  clearTimeout(workspace.pendingSave);
  const status=$('layout-status');
  if(status)status.textContent='Unsaved';
  workspace.pendingSave=setTimeout(()=>{
    let message=storedStatus();
    try{localStorage.setItem(layoutKey(),JSON.stringify(workspace.state));}
    catch(_){message='Storage unavailable · export a layout to keep changes';}
    workspace.saveStatus=message;
    const current=$('layout-status');
    if(current)current.textContent=message;
  },210);
}
function refreshWorkspace() {saveLayout();render();}
function initWorkspace() {
  const id=run.manifest.run_id||run.manifest.timestamp_sha256;
  workspace.primary=Object.hasOwn(run.scenarios,'controlled')?'controlled':
    Object.hasOwn(run.scenarios,'best_bess')?'best_bess':Object.keys(run.scenarios)[0];
  workspace.state=emptyLayout(id);
  try {
    const saved=localStorage.getItem(layoutKey());
    if(saved)workspace.state=layoutFromJSON(JSON.parse(saved),id);
    workspace.saveStatus=saved?storedStatus():'Unsaved';
  } catch(_) {workspace.saveStatus='Storage unavailable · layouts can be imported and exported';}
  screen='Summary';
  workspace.state.tab='Summary';
  if(workspace.state.scenario&&Object.hasOwn(run.scenarios,workspace.state.scenario))workspace.primary=workspace.state.scenario;
  if(focusState.scenario&&Object.hasOwn(run.scenarios,focusState.scenario))workspace.primary=focusState.scenario;
  if(focusState.group){
    const kind=focusState.group==='line'?'line':focusState.group==='bus'?'bus':'';
    if(kind){screen='Network';workspace.state.selection={kind,ids:[String(focusState.entity||'')]};}
    if(focusState.timestamp){
      const timestamp=hourInput(focusState.timestamp);
      workspace.state.time={...workspace.state.time,period:'7d',start:timestamp,end:'',cursor:timestamp};
      workspace.inspected={key:'current',scenario:workspace.primary,stamp:timestamp,kind,id:String(focusState.entity||'')};
    }
  }
}
function otherScenario(archive, primary) {
  const keys=Object.keys(archive.scenarios);
  if(primary==='controlled'&&keys.includes('uncontrolled'))return 'uncontrolled';
  if(primary==='uncontrolled'&&keys.includes('controlled'))return 'controlled';
  return keys.find(key=>key==='no_bess'&&key!==primary)??keys.find(key=>key!==primary)??keys[0];
}

function chartContext(key='current',scenario='') {
  const archive=selectedArchive(key);
  if(!archive)return null;
  const selected=scenario&&archive.scenarios[scenario]?scenario:
    key==='current'?workspace.primary:Object.keys(archive.scenarios)[0];
  const data=archive.scenarios[selected];
  if(!data)return null;
  const source=data.gallery;
  const groups={...source?.groups};
  if(archive.convergence?.some(row=>isObservation(row.best_annual_cost)))
    groups.optimization={fields:['best_annual_cost'],entities:{'GA':[]}};
  const yearly=(data.metrics||[]).filter(row=>/^annual_(grid_purchases|export_credit|shedding_cost|curtailment_cost|bess_capital_cost|bess_om_cost)$/.test(row.metric)&&isObservation(row.value));
  if(yearly.length)groups.economics={fields:['annual_component_cost'],entities:{'Annual components':[]}};
  const topology=archive.metadata?.topology||{};
  const definitions=[
    ['load input',['workbook_base_p_kw','workbook_base_q_kvar'],topology.loads],
    ['PV input',['workbook_nameplate_kw'],archive.metadata?.pv_installations],
  ];
  for(const [group,fields,equipment] of definitions){
    if(groups[group]&&equipment?.length)groups[group]={...groups[group],fields:[...groups[group].fields,...fields]};
  }
  return {key,archive,scenario:selected,data,gallery:{...source,groups},yearly};
}

async function timeline(ctx) {
  if(!ctx?.data.gallery||ctx.gallery.timestamps==null)return [];
  if(!workspace.axes.has(ctx.data))workspace.axes.set(ctx.data,readings(ctx)(ctx.gallery.timestamps));
  try{return await workspace.axes.get(ctx.data);}
  catch(error){workspace.axes.delete(ctx.data);throw error;}
}
function recordedEquipment(ctx,group,id,field) {
  const topology=ctx.archive.metadata?.topology||{};
  const assignments=ctx.archive.input_info?.assignments||{};
  const isPV=group==='PV input',elements=isPV?ctx.archive.metadata?.pv_installations:topology.loads;
  if(!Array.isArray(elements))return null;
  if(id!=='Total'&&!Object.hasOwn(assignments,id)&&!topology.buses?.some(bus=>String(bus.bus_id)===id)&&
      !Object.values(assignments).includes(id))return null;
  const tag=field==='workbook_nameplate_kw'?'p_rated_kw':field==='workbook_base_q_kvar'?'q_base_kvar':'p_base_kw';
  return elements.filter(l=>id==='Total'||String(l.bus_id)===id||assignments[l.bus_id]===id)
    .reduce((sum,row)=>sum==null||!isObservation(row[tag])?null:sum+row[tag],0);
}
async function sampleValues(ctx,series,entity,first,last) {
  if(series.field.startsWith('workbook_'))return Array(last-first).fill(recordedEquipment(ctx,series.group,entity,series.field));
  return seriesValues(ctx.gallery.groups[series.group],entity,series.field,first,last,readings(ctx));
}
function seriesName(series,entity) {
  const name=({workbook_base_p_kw:'Workbook base P',workbook_base_q_kvar:'Workbook base Q',
    workbook_nameplate_kw:'Installed PV nameplate',annual_component_cost:'Annual cost',best_annual_cost:'Best recorded objective'})[series.field]||readable(series.field);
  return ['System','Total','GA','Annual components'].includes(entity)?name:entityKind(series.group)==='bus'?'Bus '+entity+' · '+name:entity+' · '+name;
}
function chartTrace(ctx,series,entity,values,unit) {
  const group=ctx.gallery.groups[series.group], category=group?.categories?.[entity];
  const scopedCategory=series.scope==='category';
  const label=scopedCategory?categoryName(group,entity)+' · '+(demandFields[series.group]?.[series.field]||readable(series.field)):
    series.scope==='system'?'System total · '+seriesName(series,'System'):
    group?.categories?categoryLabel(group,entity)+' · '+seriesName(series,'Total'):
    seriesName(series,entity);
  return {...series,label,category:category?.label||(scopedCategory?categoryName(group,entity):null),data:values,unit,entity,runKey:ctx.key,
    runLabel:shortRun(ctx.archive),runId:ctx.archive.manifest.run_id,scenario:ctx.scenario,scenarioLabel:ctx.data.label};
}

async function prepareWorkspaceChart(chart, selection) {
  const ctx=chartContext('current',chart.sourceScenario);
  if(!ctx || !chart.series.length)return {note:'Add a recorded series in Edit.'};
  if(chart.series.some(s=>s.group==='optimization'||s.group==='economics')){
    if(chart.series.length!==1)return {note:'Annual cost and GA charts each use their own recorded axis.'};
    const s=chart.series[0],annual=s.group==='economics';
    const rows=annual?ctx.yearly:ctx.archive.convergence||[];
    const value=annual?'value':'best_annual_cost';
    return {ctx,axis:rows.map((row,i)=>annual?readable(row.metric):String(row.iteration??i+1)),
      traces:[chartTrace(ctx,s,annual?'Annual components':'GA',rows.map(r=>r[value]),chartUnit(s.field,ctx.archive.manifest))],
      categorical:true,note:rows.length?'':'No applicable records.'};
  }
  const sourceAxis=await timeline(ctx);
  const dt=ctx.archive.manifest.dt_hours;
  const [first,last]=chartWindow(sourceAxis,selectedWindow(chart),dt);
  let axis=sourceAxis.slice(first,last);
  if(!axis.length)return {note:'No data in the selected time window.'};
  if(chart.preset==='rank' && chart.series.length===1 && chart.series[0].group==='bus' && chart.comparison.mode==='none'){
    const s=chart.series[0],buses=ctx.gallery.groups.bus,stamp=selectedWindow(chart).cursor||axis[0];
    const index=sourceAxis.indexOf(stamp);
    if(index<0||!buses?.fields.includes(s.field))return {note:'No recorded bus values at this hour.'};
    const pairs=[];
    for(const bus of Object.keys(buses.entities)){
      const [value]=await sampleValues(ctx,s,bus,index,index+1);
      pairs.push({bus,value});
    }
    pairs.sort((a,b)=>(a.value??Infinity)-(b.value??Infinity));
    const trace=chartTrace(ctx,s,'All buses',pairs.map(p=>p.value),chartUnit(s.field,ctx.archive.manifest));
    return {ctx,axis:pairs.map(p=>'Bus '+p.bus),traces:[trace],categorical:true,rank:{stamp,pairs}};
  }
  const primary=[],reference=[],notes=new Set(),axisUnits={};
  let ref=null,refIndices=[],candidateIndices=null,sharedFirst=0,sharedEnd=0,aligned=false;
  if(chart.comparison.mode!=='none') {
    const key=chart.comparison.run;
    const archive=selectedArchive(key);
    const scId=chart.comparison.scenario||(archive?otherScenario(archive,key==='current'?ctx.scenario:''):'');
    if(archive&&scId&&archive.scenarios[scId])ref=chartContext(key,scId);
    if(!ref)notes.add('Reopen the reference report or choose another scenario in Edit.');
    else if (ref.key===ctx.key&&ref.scenario===ctx.scenario){notes.add('Choose a different reference scenario.');ref=null;}
    else {
      const referenceAxis=await timeline(ref);
      const issue=comparisonIssue(ctx.archive.manifest,ref.archive.manifest,'requested_load_kw',{sameRun:ref.key===ctx.key});
      if(issue){notes.add(issue);ref=null;}
      else {
        const matches=correspondingHours(axis,referenceAxis);
        if(!matches.matched.length){notes.add('The selected reports have no common timestamps in this window.');ref=null;}
        else {
          if(matches.excluded)notes.add(fmt(matches.matched.length)+' matched timestamps · '+fmt(matches.excluded)+' candidate timestamps excluded.');
          candidateIndices=matches.candidates;refIndices=matches.matched;
          axis=candidateIndices.map(i=>axis[i]);sharedFirst=refIndices[0];sharedEnd=refIndices.at(-1)+1;aligned=true;
        }
      }
    }
  }
  for(const [specIndex,spec] of chart.series.entries()){
    const group=ctx.gallery.groups[spec.group];
    if(!group?.fields.includes(spec.field)){notes.add(readable(spec.field)+' was not recorded for this scenario.');continue;}
    const unit=chartUnit(spec.field,ctx.archive.manifest),side=spec.axis||'left';
    if(Object.hasOwn(axisUnits,side)&&axisUnits[side]!==unit){
      notes.add('Assign '+readable(spec.field)+' its own unit axis in Edit.');continue;
    }
    axisUnits[side]=unit;
    const ids=entitiesFor(chart,spec,group,selection,chart.loadScope||workspace.state.loadScope);
    if(ids.some(id=>Object.hasOwn(group.categories||{},id))){
      notes.add(group.category_source==='Category not provided'?'Category not provided. Recorded demand is Unclassified.':
        'Category demand sums the buses in the archived assignments. A missing bus sample leaves a gap.');
    }
    if(!ids.length){notes.add('The selected entities are unavailable for '+readable(spec.field)+'.');continue;}
    if(!spec.scope&&chart.selection.linked&&selection.ids.length&&entityKind(spec.group)&&
      (selection.kind!==entityKind(spec.group)||!ids.some(id=>selection.ids.includes(id))))
      notes.add('Other entity types retain their own selection.');
    for(const id of ids){
      if(primary.length>=SERIES_LIMIT){notes.add('Only the first '+SERIES_LIMIT+' series are displayed.');break;}
      let data=await sampleValues(ctx,spec,id,first,last);
      if(aligned)data=candidateIndices.map(i=>data[i]);
      const trace=chartTrace(ctx,{...spec,specIndex},id,data,unit);
      primary.push(trace);
      if(!ref)continue;
      const issue=comparisonIssue(ctx.archive.manifest,ref.archive.manifest,spec.field,{sameRun:ref.key===ctx.key});
      const groupOther=ref.gallery.groups[spec.group];
      let values=Array(axis.length).fill(null);
      const referenceHasEntity=spec.scope?entitiesFor(chart,spec,groupOther,selection).includes(id):
        Boolean(groupOther?.fields.includes(spec.field)&&Object.hasOwn(groupOther.entities,id));
      if(!issue&&referenceHasEntity){
        const exact=await sampleValues(ref,spec,id,sharedFirst,sharedEnd);
        values=refIndices.map(i=>exact[i-sharedFirst]);
        if(group.categories?.[id]&&JSON.stringify(group.categories[id].buses)!==JSON.stringify(groupOther.categories?.[id]?.buses))
          notes.add('Buses assigned to this profile category differ between reports.');
      }else notes.add(issue||readable(spec.field)+' was not recorded for the reference entity.');
      reference.push(chartTrace(ref,{...spec,specIndex},id,values,unit));
    }
  }
  const deltas=ref?primary.map((s,i)=>s.data.map((value,j)=>
    isObservation(value)&&isObservation(reference[i]?.data[j])?value-reference[i].data[j]:null)):[];
  const traces=chart.comparison.mode==='difference'&&ref?primary.map((s,i)=>({...s,
    label:s.label+' · Candidate − Reference',comparison:'Candidate − '+reference[i].runLabel+' / '+reference[i].scenarioLabel,data:deltas[i]})):primary;
  const intervals={axis,values:null};
  const resolution=resolvedResolution(chart.aggregation==='linked'?(selectedWindow(chart).resolution||
    workspace.state.time.resolution||'auto'):chart.aggregation,axis.length);
  const bounds=ctx.archive.metadata?.simulation||{};
  const applicableLimits=isObservation(bounds.voltage_min_pu)&&isObservation(bounds.voltage_max_pu)&&chart.comparison.mode!=='difference'?
    {minimum:bounds.voltage_min_pu,maximum:bounds.voltage_max_pu}:null;
  let durations=null;
  if(resolution!=='hourly'&&ctx.gallery.groups.system?.fields.includes('dt_hours')){
    const exact=await sampleValues(ctx,{group:'system',field:'dt_hours'},'System',first,last);
    durations=aligned?candidateIndices.map(i=>exact[i]):exact;
  }
  for(const s of [...traces,...(ref&&chart.comparison.mode!=='difference'?reference:[])]){
    const limits=s.runKey===ctx.key&&s.scenario===ctx.scenario?applicableLimits:null;
    const agg=bucketReadings(axis,s.data,resolution,chart.reducer,dt,s.unit,s.field,limits,durations);
    if(s.category&&agg.intervals)agg.data=agg.data.map((value,i)=>agg.intervals[i].missing?null:value);
    const label=resolution==='hourly'?'Recorded samples':resolutionLabels[resolution]+' · '+agg.operation;
    Object.assign(s,{data:agg.data,unit:agg.unit,aggregation:label,buckets:agg.intervals});
    if(resolution!=='hourly')s.label+=' · '+agg.operation;
    intervals.axis=agg.axis;intervals.values=agg.intervals;
  }
  if(!ref&&resolution!=='hourly'&&chart.reducer==='auto'){
    for(const s of traces.slice()){
      if(!s.buckets||s.field!=='voltage_pu')continue;
      for(const edge of ['minimum','maximum']){
        if(traces.length>=SERIES_LIMIT)break;
        traces.push({...s,label:seriesName(s,s.entity)+' · '+edge,data:s.buckets.map(b=>b[edge]),dash:'dashed',
          aggregation:resolutionLabels[resolution]+' · '+edge});
      }
    }
  }
  if(ref&&chart.comparison.mode==='overlay'){
    const scope=s=>s.scenarioLabel+' · '+s.runLabel;
    traces.forEach(s=>s.label+=' · '+scope(s));
    reference.forEach(s=>s.label+=' · '+scope(s));
    traces.push(...reference.map(s=>({...s,dash:'dashed',color:s.color||'#ad6840'})));
  }
  if(chart.preset==='voltage'&&chart.comparison.mode!=='difference'){
    for(const [name,k] of [['Lower voltage limit','voltage_min_pu'],['Upper voltage limit','voltage_max_pu']]){
      const limit=ctx.archive.metadata?.simulation?.[k];
      if(isObservation(limit))traces.push({label:name,data:intervals.axis.map(()=>limit),unit:'pu',style:'line',dash:'dashed',color:'#9e5331',field:k,runLabel:shortRun(ctx.archive),scenarioLabel:ctx.data.label});
    }
  }
  return {ctx,ref,axis:intervals.axis,traces,reference,intervals:intervals.values,resolution,
    notes:[...notes],matched:deltas.map(d=>d.filter(isObservation))};
}

function selectChart(card,chart) {
  workspace.state.active=chart.id;
  workspace.editor=chart.id;
  refreshWorkspace();
}
function storePinned(chart) {
  const pins=workspace.state.pinned;
  workspace.state.pinned=pins.includes(chart.id)?pins.filter(id=>id!==chart.id):[...pins,chart.id];
  refreshWorkspace();
}
function reorderChart(chart,direction,topic) {
  const list=topic==='My Dashboard'?workspace.state.pinned:workspace.state.topics[topic];
  const i=list.indexOf(chart.id),j=i+direction;
  if(i>=0&&j>=0&&j<list.length){[list[i],list[j]]=[list[j],list[i]];refreshWorkspace();}
}
function addChart(topic,template) {
  const id=globalThis.crypto?.randomUUID?.()||'chart-'+Date.now()+'-'+Object.keys(workspace.state.charts).length;
  const chart=template?{...plainClone(template),id}:newChart(id);
  workspace.state.charts[id]=chart;
  if(topic==='My Dashboard')workspace.state.pinned.push(id);
  else(workspace.state.topics[topic]||=[]).push(id);
  workspace.state.active=id;workspace.editor=id;refreshWorkspace();
}
function defaultCharts(topic,ctx) {
  const state=workspace.state;
  if(topic==='My Dashboard')return state.pinned;
  if(state.topics[topic])return state.topics[topic];
  if(topic==='Summary'||academicSections[topic])return [];
  const base=topicPresetKeys(topic);
  const selected=[];
  for(const preset of base){
    if(topic==='Summary'&&['bessSOC','fleetSoc'].includes(preset)&&!hasInstalledBess(ctx))continue;
    const chart=presetChart(preset,topic,ctx.gallery);
    if(!chart)continue;
    if(['bessSOC','bessPQ','bessQ','bessRating'].includes(preset)){
      const bus=Object.keys(ctx.gallery.groups.battery?.entities||{})[0]||
        ctx.archive.metadata?.context?.['Manual BESS Fleet']?.[0]?.bus_id||
        ctx.archive.metadata?.context?.['Manual BESS']?.bus_id;
      if(bus!=null)chart.series.forEach(series=>series.ids=[String(bus)]);
    }
    if(['fleetSoc','fleetPower'].includes(preset)){
      const units=Object.keys(ctx.gallery.groups.battery?.entities||{}).slice(0,SERIES_LIMIT);
      if(units.length)chart.series.forEach(series=>series.ids=units);
    }
    if(topic==='Compare Runs')chart.comparison.mode='overlay';
    if(topic==='Summary'&&selected.length>=4)break;
    state.charts[chart.id]=chart;selected.push(chart.id);
  }
  if(selected.length)state.topics[topic]=selected;
  return selected;
}
function topicPresetKeys(topic) {
  return topic==='Compare Runs'?['load','voltage','actions','grid','categoryLoad','categoryOutput']:topicPresets[topic]||[];
}
function resetPresets(topic) {
  workspace.state.time.zoom=null;
  if(topic!=='My Dashboard')delete workspace.state.topics[topic];
  else workspace.state.pinned=[];
  workspace.editor='';workspace.state.active='';refreshWorkspace();
}


function timeSettings(parent,state,change) {
  selectControl(parent,'Period',[
    ['24h','24 hours'],['7d','7 days'],['14d','14 days'],['month','Calendar month'],
    ['year','Calendar year'],['all','Full history'],['custom','Custom'],
  ],state.period,value=>{state.period=value;state.zoom=null;change();});
  for(const key of ['start','end']){
    if(key==='end'&&state.period!=='custom'||state.period==='all')continue;
    const label=elem('label',key==='start'?'From':'Through');
    const input=elem('input');input.type='datetime-local';input.step=3600;input.value=asLocalInput(state[key]);
    input.onchange=()=>{state[key]=hourInput(input.value);state.zoom=null;change();};
    label.append(input);parent.append(label);
  }
}
function checkControl(parent,label,value,update){
  const wrap=elem('label'),input=elem('input');input.type='checkbox';input.checked=value;
  input.onchange=()=>update(input.checked);wrap.append(input,elem('span',label));parent.append(wrap);return input;
}
function lineInput(parent,label,value,update){
  const wrap=elem('label',label),input=elem('input');input.type='text';input.value=value||'';
  input.onchange=()=>update(input.value);wrap.append(input);parent.append(wrap);return input;
}
function scenarioChoices(ctx,except='') {
  return Object.entries(ctx.scenarios).filter(([key])=>key!==except).map(([key,data])=>[key,data.label]);
}
async function addComparisons(files,feedback) {
  const errors=[];
  for(const file of files){
    try{
      const saved=await readSavedReport(await comparisonReportFile(file)),identity=saved.manifest.run_id||file.name;
      if(identity===run.manifest.run_id)continue;
      if(workspace.imports.size>=8&&!workspace.imports.has(identity)){
        errors.push('At most eight external reports can be open in a session.');break;
      }
      const cache=new Map();
      const reader=saved.readBlock;
      saved.readBlock=async id=>{
        if(!cache.has(id)){
          if(cache.size>=32)cache.delete(cache.keys().next().value);
          cache.set(id,reader(id));
        }
        try{return await cache.get(id);}
        catch(error){cache.delete(id);throw error;}
      };
      workspace.imports.set(identity,saved);
    }catch(error){errors.push(file.name+' · '+error.message);}
  }
  workspace.importMessage=errors.length?errors.join(' '):'';
  if(feedback.isConnected)refreshWorkspace();
}
async function comparisonReportFile(file){
  if(!file.name.toLowerCase().endsWith('.zip'))return file;
  // The portable report writer stores the HTML uncompressed. Read its slice
  // directly so a large study remains lazy and other ZIP entries stay unopened.
  const begin=Math.max(0,file.size-65557);
  const end=new DataView(await file.slice(begin).arrayBuffer());
  let directory=-1,directorySize=0;
  for(let i=end.byteLength-22;i>=0;i--){
    if(end.getUint32(i,true)===0x06054b50&&i+22+end.getUint16(i+20,true)===end.byteLength){
      directory=end.getUint32(i+16,true);directorySize=end.getUint32(i+12,true);break;
    }
  }
  if(directory<0||directorySize>16*1024*1024||directory+directorySize>file.size)
    throw Error('Unable to read the portable ZIP index.');
  const central=new DataView(await file.slice(directory,directory+directorySize).arrayBuffer());
  for(let i=0;i+46<=central.byteLength;){
    if(central.getUint32(i,true)!==0x02014b50)break;
    const n=central.getUint16(i+28,true),extra=central.getUint16(i+30,true),comment=central.getUint16(i+32,true);
    if(i+46+n+extra+comment>central.byteLength)break;
    const name=new TextDecoder().decode(new Uint8Array(central.buffer,i+46,n));
    if(name==='dashboard.html'){
      const off=central.getUint32(i+42,true),size=central.getUint32(i+20,true);
      const local=new DataView(await file.slice(off,off+30).arrayBuffer());
      if(local.byteLength!==30||central.getUint16(i+10,true)!==0||local.getUint32(0,true)!==0x04034b50)
        throw Error('Extract dashboard.html from this ZIP before importing it.');
      const start=off+30+local.getUint16(26,true)+local.getUint16(28,true);
      if(start+size>file.size)throw Error('The portable report ZIP is incomplete.');
      return file.slice(start,start+size,'text/html');
    }
    i+=46+n+extra+comment;
  }
  throw Error('The ZIP does not contain a saved dashboard.html entry.');
}
function browserSources(ctx,query='',firstGroups=[]) {
  const matching=[];
  const groups=Object.entries(ctx.gallery.groups).sort(([a],[b])=>Number(firstGroups.includes(b))-Number(firstGroups.includes(a)));
  for(const [group,fields] of groups)
    for(const field of fields.fields)
      if((group+' '+field+' '+readable(field)).toLowerCase().includes(query.toLowerCase()))matching.push([group,field]);
  return matching;
}
function seriesBrowser(sidebar,ctx,topic,add) {
  const search=elem('input');search.type='search';search.placeholder='Find a measurement';search.setAttribute('aria-label','Find a measurement');
  const choices=elem('div',undefined,'series-choices');
  const picker=elem('div',undefined,'series-source-picker');
  const controls=elem('div',undefined,'scope-inline');
  const scopes=[['','All measurements'],['category','Load profile category'],['system','System total'],['bus','Individual bus']];
  let scope='';
  selectControl(controls,'Series scope',scopes,scope,value=>{scope=value;giveChoices();});
  controls.append(search);sidebar.append(controls,picker,choices);
  const categories=categoryMeasurements(ctx);
  function pick(measure){
    picker.replaceChildren();
    const group=ctx.gallery.groups[measure.group];
    if(!measure.scope||measure.scope==='system'){
      add(measure,measure.scope==='system'?['System']:[]);return;
    }
    picker.append(elem('strong',measure.label));
    if(measure.scope==='bus'){
      const present=workspace.state.selection.kind==='bus'?workspace.state.selection.ids[0]:null;
      const buses=Object.keys(group.entities).filter(bus=>entityHasField(group,bus,measure.field));
      if(!buses.length){picker.append(elem('p','No bus readings for this quantity.','fine'));return;}
      const current=buses.includes(present)?present:buses[0];
      const input=selectControl(picker,'Bus',buses.map(id=>[id,'Bus '+id]),current,()=>{});
      button(picker,'Add bus series',()=>add(measure,[input.value]));
      return;
    }
    const fieldset=elem('fieldset');fieldset.append(elem('legend','Select load profile categories'));
    const boxes=measure.ids.map(id=>{
      const label=elem('label'),input=elem('input');input.type='checkbox';
      label.append(input,elem('span',categoryName(group,id)));fieldset.append(label);
      return [id,input];
    });
    picker.append(fieldset);
    const actions=elem('div',undefined,'scope-inline');picker.append(actions);
    const submit=button(actions,'Add selected series',()=>add(measure,boxes.filter(([,input])=>input.checked).map(([id])=>id)));
    const update=()=>{submit.disabled=!boxes.some(([,input])=>input.checked);};
    button(actions,'Select all categories',()=>{boxes.forEach(([,input])=>{input.checked=true;});update();});
    boxes.forEach(([,input])=>{input.onchange=update;});update();
  }
  function giveChoices(){
    choices.replaceChildren();
    picker.replaceChildren();
    const query=search.value.trim().toLowerCase();
    const generic=browserSources(ctx,query,chartTopics[topic])
      .filter(([group])=>!scope||group===scope)
      .map(([group,field])=>({group,field,label:readable(field),scope}));
    const terms=query.split(/\s+/).filter(Boolean);
    const scoped=categories.filter(entry=>{
      const record=['load profile category',entry.group,entry.field,entry.label,
        ...entry.ids.map(id=>categoryName(ctx.gallery.groups[entry.group],id))].join(' ').toLowerCase();
      return terms.every(term=>record.includes(term));
    });
    const matching=scope==='category'?scoped:!scope&&query?[...scoped,...generic]:generic;
    for(const measure of matching.slice(0,28)){
      const label=(scopes.find(([key])=>key===measure.scope)?.[1]||measure.group);
      const source=measure.scope?label:measure.group;
      const row=button(choices,'+ '+measure.label,()=>pick(measure));
      row.title=source;row.append(elem('small',source));
    }
    if(!matching.length)choices.append(elem('p',scope==='category'&&!categories.length?
      'No category readings were retained. Regenerate from saved bus results and assignments if available.':
      'No matching recorded fields.','empty'));
    if(matching.length>28)choices.append(elem('small','Search to see all '+matching.length+' measurements.'));
  }
  search.oninput=giveChoices;giveChoices();
}
function availableSeriesAxis(chart,unit,manifest,preferred='left',index=-1){
  const remaining=chart.series.filter((_,i)=>i!==index);
  const options=[preferred,preferred==='right'?'left':'right'];
  return options.find(side=>remaining.every(s=>s.axis!==side||chartUnit(s.field,manifest)===unit));
}
function insertWorkspaceSeries(chart,ctx,measure,ids){
  const selected=measure.scope?[...new Set(ids)].filter(Boolean):[null];
  if(!selected.length)return 'Select at least one recorded entity.';
  if(chart.series.length+selected.length>SERIES_LIMIT)return 'A chart can contain up to '+SERIES_LIMIT+' series. Choose fewer entities or remove an existing series.';
  const unit=chartUnit(measure.field,ctx.archive.manifest),axis=availableSeriesAxis(chart,unit,ctx.archive.manifest);
  if(!axis)return 'This chart already uses both axes for different units.';
  for(const id of selected)chart.series.push({group:measure.group,field:measure.field,ids:id?[id]:[],
    ...(measure.scope?{scope:measure.scope}:{}),color:'',dash:'solid',axis,
    style:/shed|curt|cost/.test(measure.field)?'bar':'line',visible:true});
  return '';
}
function chartEditor(sidebar,chart,topic,ctx) {
  sidebar.replaceChildren();
  const header=elem('div',undefined,'workspace-subhead');
  header.append(elem('h2','Edit chart'));
  button(header,'Close',()=>{workspace.editor='';refreshWorkspace();});
  sidebar.append(header);
  const fields=elem('div',undefined,'editor-fields');sidebar.append(fields);
  lineInput(fields,'Title',chart.title,value=>{chart.title=value.trim()||'Custom chart';refreshWorkspace();});
  selectControl(fields,'Scenario',[['','Workspace scenario'],...scenarioChoices(run)],chart.sourceScenario,value=>{chart.sourceScenario=value;refreshWorkspace();});
  selectControl(fields,'Size',[['medium','Standard'],['wide','Full width'],['large','Full width · tall']],chart.size,value=>{chart.size=value;refreshWorkspace();});
  checkControl(fields,'Link time',chart.time.linked,value=>{
    setTimeLink(chart,value);
  });
  if(!chart.time.linked)timeSettings(fields,chart.time,refreshWorkspace);
  checkControl(fields,'Link bus / line selection',chart.selection.linked,value=>{chart.selection.linked=value;refreshWorkspace();});
  selectControl(fields,'Resolution',[['linked','Use linked/default resolution'],...resolutionChoices],chart.aggregation,
    value=>{chart.aggregation=value;chart.zoom=null;refreshWorkspace();});
  if(chart.aggregation!=='hourly')selectControl(fields,'Aggregate using',[
    ['auto','Metric default'],['mean','Mean of recorded values'],['peak','Maximum'],['minimum','Minimum'],
    ['end','Last recorded value'],['energy','Integrate power to energy'],
  ],chart.reducer,value=>{chart.reducer=value;refreshWorkspace();});
  checkControl(fields,'Stack additive bars',chart.stack,value=>{chart.stack=value;refreshWorkspace();});
  selectControl(fields,'Comparison',[['none','None'],['overlay','Overlay'],['side','Side by side'],['difference','Difference']],
    chart.comparison.mode,value=>{chart.comparison.mode=value;refreshWorkspace();});
  if(chart.comparison.mode!=='none'){
    const archive=selectedArchive(chart.comparison.run);
    selectControl(fields,'Reference run',[['current',shortRun(run)],...Array.from(workspace.imports,([key,item])=>[key,shortRun(item)])],
      chart.comparison.run,value=>{chart.comparison.run=value;chart.comparison.scenario='';refreshWorkspace();});
    selectControl(fields,'Reference scenario',[['','Automatic reference'],...(archive?scenarioChoices(archive):[])],
      chart.comparison.scenario,value=>{chart.comparison.scenario=value;refreshWorkspace();});
    if(!archive)fields.append(elem('p','Open the saved reference again from Compare Runs.','fine'));
  }
  const specContext=chartContext('current',chart.sourceScenario)||ctx;
  const categorySource=specContext.gallery.groups['load input']||specContext.gallery.groups['load output'];
  if(categorySource?.categories&&chart.series.some(series=>!series.scope&&categoryGroup(series.group))){
    selectControl(fields,'Demand grouping',[['','Use workspace grouping'],['total','System total'],
      ['category','Profile category'],['bus','Individual bus']],chart.loadScope?.group||'',group=>{
      chart.loadScope=group?{group,category:chart.loadScope?.category||''}:null;refreshWorkspace();
    });
    if(chart.loadScope)selectControl(fields,'Profile category',[['','All categories'],
      ...Object.keys(categorySource.categories).map(id=>[id,categoryLabel(categorySource,id)])],
      chart.loadScope.category,category=>{chart.loadScope.category=category;refreshWorkspace();});
  }
  const categoryOptions=categoryMeasurements(specContext);
  for(const [i,s] of chart.series.entries()){
    const group=specContext.gallery.groups[s.group],row=elem('details',undefined,'series-edit');
    const entity=s.ids[0];
    const label=s.scope==='category'?categoryName(group,entity||'category')+' · '+(demandFields[s.group]?.[s.field]||readable(s.field)):
      s.scope==='bus'?'Bus '+entity+' · '+readable(s.field):
      s.scope==='system'?'System total · '+readable(s.field):readable(s.field)+' · '+s.group;
    row.open=i===chart.series.length-1;row.append(elem('summary',label));
    const content=elem('div',undefined,'editor-fields');row.append(content);sidebar.append(row);
    selectControl(content,'Draw as',[['line','Line'],['bar','Bar']],s.style,value=>{s.style=value;refreshWorkspace();});
    selectControl(content,'Axis',[['left','Left'],['right','Right']],s.axis,value=>{s.axis=value;refreshWorkspace();});
    if(s.style==='line')selectControl(content,'Line style',[['solid','Solid'],['dashed','Dashed']],s.dash,value=>{s.dash=value;refreshWorkspace();});
    const color=elem('input');color.type='color';color.value=s.color||palette[i%palette.length];
    const wrap=elem('label','Color');wrap.append(color);content.append(wrap);
    color.onchange=()=>{s.color=color.value;refreshWorkspace();};
    checkControl(content,'Show series',s.visible,value=>{s.visible=value;refreshWorkspace();});
    if(s.scope==='category'){
      const available=new Map(categoryOptions.flatMap(option=>option.ids.map(id=>[id,categoryName(specContext.gallery.groups[option.group],id)])));
      if(entity&&!available.has(entity))available.set(entity,categoryName(group,entity)+' (unavailable)');
      const sameField=categoryOptions.find(option=>option.group===s.group&&option.field===s.field);
      const compatible=new Set(sameField?.ids||[]);
      const choices=[...available].filter(([id])=>id===entity||compatible.has(id));
      selectControl(content,'Load profile category',choices,entity,value=>{s.ids=[value];refreshWorkspace();});
      const quantities=categoryOptions.filter(option=>option.ids.includes(entity));
      const key=measure=>measure.group+'|'+measure.field;
      const options=quantities.map(option=>[key(option),option.label]);
      if(!options.some(([value])=>value===key(s)))options.unshift([key(s),'Current quantity (unavailable)']);
      selectControl(content,'Category quantity',options,key(s),value=>{
        const choice=quantities.find(option=>key(option)===value);
        if(!choice)return;
        const axis=availableSeriesAxis(chart,chartUnit(choice.field,specContext.archive.manifest),
          specContext.archive.manifest,s.axis,i);
        if(!axis){content.append(elem('p','This chart already uses both axes for different units.','warning'));return;}
        Object.assign(s,{group:choice.group,field:choice.field,axis});refreshWorkspace();
      });
    }else if(s.scope==='bus'&&group){
      const buses=Object.keys(group.entities).filter(id=>entityHasField(group,id,s.field));
      if(entity&&!buses.includes(entity))buses.unshift(entity);
      selectControl(content,'Bus',buses.map(id=>[id,'Bus '+id]),entity,value=>{s.ids=[value];refreshWorkspace();});
    }else if(!s.scope&&group&&Object.keys(group.entities).length>1){
      const label=elem('label',group.categories?'Profile categories and buses':'Override entities'),input=elem('select');
      input.multiple=true;input.size=4;
      for(const id of Object.keys(group.entities)){
        const option=new Option(group.categories?categoryLabel(group,id):id,id);
        option.selected=s.ids.includes(id);input.add(option);
      }
      input.onchange=()=>{s.ids=[...input.selectedOptions].slice(0,SERIES_LIMIT).map(x=>x.value);chart.selection.linked=false;refreshWorkspace();};
      label.append(input,elem('small','Use Ctrl or Shift to choose several.'));content.append(label);
      if(s.ids.length)button(content,'Use default entity',()=>{s.ids=[];refreshWorkspace();});
    }
    if(i>0)button(content,'Move series up',()=>{
      [chart.series[i-1],chart.series[i]]=[chart.series[i],chart.series[i-1]];refreshWorkspace();
    });
    if(i<chart.series.length-1)button(content,'Move series down',()=>{
      [chart.series[i+1],chart.series[i]]=[chart.series[i],chart.series[i+1]];refreshWorkspace();
    });
    button(content,'Remove series',()=>{chart.series.splice(i,1);refreshWorkspace();});
  }
  sidebar.append(elem('h3','Add series'));
  seriesBrowser(sidebar,specContext,topic,(measure,ids)=>{
    const message=insertWorkspaceSeries(chart,specContext,measure,ids);
    if(message){sidebar.append(elem('p',message,'warning'));return;}
    refreshWorkspace();
  });
}
function setTimeLink(chart,linked){
  if(!linked){
    chart.time={...workspace.state.time,linked:false};
    chart.zoom=workspace.state.time.zoom?.slice()||null;
  }else chart.time={...chart.time,linked:true};
  refreshWorkspace();
}
function changeZoom(chart,data,left,right,limits,source){
  const axis=data.axis,intervals=data.intervals;
  const whole=left===0&&right===axis.length&&(!limits||
    limits[0]===timeCoordinate(axis[0])&&limits[1]===timeCoordinate(axis.at(-1)));
  const zoom=whole?null:intervals?[intervals[left].start,intervals[right-1].end]:
    limits?limits.map(value=>new Date(value).toISOString()):[axis[left],axis[right-1]];
  if(chart.time.linked)workspace.state.time.zoom=zoom;
  else chart.zoom=zoom;
  const own=workspace.scope.get(chart.id);
  own?.controllers.filter(controller=>controller!==source).forEach(controller=>{
    if(limits)controller.setTimeBounds(limits);
    else controller.setRange(left,right,false);
  });
  if(chart.time.linked){
    if(workspace.zoomFrame!==null)cancelAnimationFrame(workspace.zoomFrame);
    workspace.zoomFrame=requestAnimationFrame(()=>{
      workspace.zoomFrame=null;
      for(const [id,entry] of workspace.scope){
        if(id===chart.id||!entry.timeLinked)continue;
        const [first,last]=visibleRange(entry.chart,entry.axis,entry.intervals);
        const precise=preciseTimeBounds(entry.chart,entry.axis,entry.intervals);
        entry.controllers.forEach(controller=>{
          if(precise)controller.setTimeBounds(precise);
          else controller.setRange(first,last,false);
        });
      }
    });
  }
  saveLayout();
}
function visibleRange(chart,axis,intervals) {
  const zoom=chart.time.linked?workspace.state.time.zoom:chart.zoom;
  if(!zoom)return [0,axis.length];
  return linkedRange(axis,zoom,intervals);
}
function preciseTimeBounds(chart,axis,intervals){
  if(intervals)return null;
  const zoom=chart.time.linked?workspace.state.time.zoom:chart.zoom;
  const limits=zoom?.map(timeCoordinate);
  return limits?.every(Number.isFinite)&&limits[0]<timeCoordinate(axis.at(-1))&&
    limits[1]>timeCoordinate(axis[0])?limits:null;
}
function syncHover(stamp){
  if(workspace.pendingHover===stamp)return;
  workspace.pendingHover=stamp;
  requestAnimationFrame(()=>{
    if(workspace.pendingHover!==stamp)return;
    for(const entry of workspace.scope.values()){
      if(!entry.linked)continue;
      const i=rangeIndex(entry.axis,stamp);
      if(entry.axis[i]===stamp)entry.controllers.forEach(chart=>chart.setCursor(i));
    }
  });
}
function inspectClick(chart,data,i,trace) {
  const bucket=(trace.buckets||data.intervals)?.[i], stamp=data.axis[i];
  const kind=entityKind(trace.group)||(categoryGroup(trace.group)&&/^\d+$/.test(trace.entity)?'bus':'');
  if(data.rank){
    selectedEntity('bus',data.rank.pairs[i].bus,data.rank.stamp,data.ctx.scenario);
    return;
  }else if(data.categorical){
    workspace.inspected={key:data.ctx.key,scenario:data.ctx.scenario,label:stamp,field:trace.field,unit:trace.unit,
      value:trace.data[i],categorical:true};
  }else if(bucket){
    workspace.inspected={bucket,field:trace.field,unit:trace.unit,value:trace.data[i],chart:chart.id,
      key:data.ctx.key,scenario:data.ctx.scenario,kind,id:trace.entity,category:trace.category,
      group:trace.group,aggregation:trace.aggregation};
  }else{
    const inspected={key:data.ctx.key,scenario:data.ctx.scenario,stamp,kind,category:trace.category,
      id:trace.entity,group:trace.group,field:trace.field,unit:trace.unit,value:trace.data[i]};
    workspace.inspected=inspected;
    if(chart.time.linked){workspace.state.time.cursor=stamp;syncHover(stamp);}
    else chart.time.cursor=stamp;
  }
  workspace.state.active=chart.id;saveLayout();
  const drawer=$('point-drawer');
  if(drawer)void pointDrawer(drawer).catch(error=>drawer.append(elem('p',error.message,'warning')));
}
function scopeFilename(ctx,chart,axis){
  return safeFilename([shortRun(ctx.archive),ctx.data.label,chart.title,axis[0]?.slice(0,10)].join('_'));
}
function workspaceChart(card,chart,data,topic) {
  const header=elem('div',undefined,'workspace-subhead');
  header.append(elem('h3',chart.title));
  const actions=elem('div',undefined,'card-actions');header.append(actions);card.append(header);
  button(actions,'Edit',()=>selectChart(card,chart));
  button(actions,workspace.state.mode==='focus'?'Return':'Expand',()=>workspace.state.mode==='focus'?
    (workspace.state.mode='grid',refreshWorkspace()):focusChart(chart));
  const sync=elem('details',undefined,'card-menu');sync.append(elem('summary','Sync'));actions.append(sync);
  checkControl(sync,'Time',chart.time.linked,value=>{
    setTimeLink(chart,value);
  });
  checkControl(sync,'Bus / line',chart.selection.linked,value=>{chart.selection.linked=value;refreshWorkspace();});
  const exports=elem('details',undefined,'card-menu');exports.append(elem('summary','Export'));actions.append(exports);
  const more=elem('details',undefined,'card-menu');more.append(elem('summary','More'));actions.append(more);
  button(more,workspace.state.pinned.includes(chart.id)?'Unpin':'Pin to My Dashboard',()=>storePinned(chart));
  button(more,'Duplicate',()=>addChart(topic,chart));
  button(more,'Move earlier',()=>reorderChart(chart,-1,topic));button(more,'Move later',()=>reorderChart(chart,1,topic));
  button(more,'Remove from view',()=>{
    if(topic==='My Dashboard')workspace.state.pinned=workspace.state.pinned.filter(id=>id!==chart.id);
    else workspace.state.topics[topic]=workspace.state.topics[topic].filter(id=>id!==chart.id);
    if(workspace.editor===chart.id)workspace.editor='';refreshWorkspace();
  });
  if(!data?.traces?.length||!data.axis?.length){
    exports.remove();card.append(elem('p',data?.note||data?.notes?.join(' ')||'No applicable records.','empty'));return;
  }
  if(data.note)card.append(elem('p',data.note,'fine'));
  const caption=[data.ctx.data.label, data.axis.at(0)+(data.axis.length>1?' → '+data.axis.at(-1):''),
    chart.time.linked?'Shared time':'Independent time'];
  if(data.ref)caption.push('Reference · '+shortRun(data.ref.archive)+' / '+data.ref.data.label);
  if(data.resolution){
    const automatic=(chart.aggregation==='linked'?selectedWindow(chart).resolution:chart.aggregation)==='auto';
    caption.push((automatic?'Auto · ':'')+resolutionLabels[data.resolution]);
  }
  if(data.rank)caption.push(data.rank.stamp);
  card.append(elem('p',caption.join('  ·  '),'chart-context'));
  for(const note of data.notes||[])card.append(elem('p',note,'fine'));
  const stack=chart.stack&&!data.ref&&canStack(data.traces);
  if(chart.stack&&!stack)card.append(elem('p','Stacking requires compatible additive bars or distinct categories of one metric.','fine'));
  const controllers=[],axis=data.axis;
  const chartBox=elem('div',undefined,'paired-plots');card.append(chartBox);
  const side=chart.comparison.mode==='side'&&data.ref;
  if(side)chartBox.classList.add('paired');
  const activeTime=selectedWindow(chart);
  const cursor=axis.indexOf(activeTime.cursor);
  function createPane(traces, title, reference=false) {
    const instance=interactiveChart(chartBox,title,axis,traces,traces[0]?.unit,{
      compact:true,mode:stack?'Stack elements':'Time series',cursor,height:chart.size==='large'||workspace.state.mode==='focus'?335:255,
      zeroLine:chart.comparison.mode==='difference'&&Boolean(data.ref),
      range:visibleRange(chart,axis,data.intervals),exportHeaders:true,filename:scopeFilename(reference?data.ref:data.ctx,chart,axis),
      timeBounds:preciseTimeBounds(chart,axis,data.intervals),
      scaleSeries:side?[...data.traces,...data.reference]:null,intervals:data.intervals,categorical:data.categorical,
      pick:i=>{
        const source=traces.find(t=>t.visible!==false&&isObservation(t.data[i]))||traces[0];
        if(reference)inspectClick(chart,{...data,ctx:data.ref},i,source);
        else inspectClick(chart,data,i,source);
      },
      hover:data.categorical||!chart.time.linked||data.intervals?null:i=>syncHover(axis[i]),
      onZoom:data.categorical?null:(a,b,bounds)=>changeZoom(chart,data,a,b,bounds,instance),
      toggle:(trace,shown)=>{
        const spec=chart.series[trace.specIndex]||chart.series.find(s=>s.group===trace.group&&s.field===trace.field);
        if(spec){spec.visible=shown;saveLayout();}
      },
    });
    controllers.push(instance);
  }
  createPane(data.traces,side?data.ctx.data.label:chart.title);
  if(side&&data.reference.length)createPane(data.reference,data.ref.data.label,true);
  workspace.scope.set(chart.id,{axis,intervals:data.intervals,chart,timeLinked:chart.time.linked&&!data.categorical,
    linked:chart.time.linked&&!data.categorical&&!data.intervals,controllers});
  button(exports,'PNG',()=>controllers.forEach(chart=>chart.savePNG()));
  button(exports,'Exact CSV',()=>controllers.forEach(chart=>chart.saveCSV()));
  if(typeof publicationActions==='function')controllers.forEach((controller,i)=>{
    const ctx=i===0?data.ctx:data.ref;
    publicationActions(card,controller,{title:side?chart.title+' · '+ctx.data.label:chart.title,
      caption:caption.join(' · '),ctx});
  });
  if(data.matched?.some(values=>values.length)&&data.ref){
    const summaries=[];
    for(let i=0;i<data.matched.length;i++){
      const values=data.matched[i];if(!values.length)continue;
      let min=Infinity,max=-Infinity,sum=0;
      for(const x of values){sum+=x;min=Math.min(min,x);max=Math.max(max,x);}
      summaries.push([data.traces[i]?.label,values.length,sum/values.length,min,max,data.traces[i]?.unit]);
    }
    const details=elem('details');details.append(elem('summary','Matched sampled differences · candidate minus reference'));
    grid(details,['Series','Matched','Mean','Minimum','Maximum','Unit'],summaries);card.append(details);
  }
  if(workspace.state.mode==='engineering'){
    const tr=elem('details');tr.open=true;tr.append(elem('summary','Visible data · first 24 rows'));
    const [a,b]=visibleRange(chart,axis);
    grid(tr,['Timestamp or period',...data.traces.map(s=>s.label)],axis.slice(a,Math.min(b,a+24)).map((stamp,i)=>[stamp,...data.traces.map(s=>s.data[a+i])]));
    card.append(tr);
  }
}



function selectedEntity(kind,id,stamp,scenario=workspace.primary) {
  workspace.state.selection={kind,ids:[String(id)]};
  workspace.inspected={key:'current',scenario,kind,id:String(id),stamp:stamp||workspace.state.time.cursor};
  refreshWorkspace();
}
async function workspaceFeeder(root,ctx,axis) {
  if(!axis.length){
    root.append(elem('p','No chronological feeder readings were retained in this archive.','empty'));
    return;
  }
  const holder=elem('details',undefined,'workspace-feeder');holder.open=true;
  holder.append(elem('summary','Feeder · select a bus or line'));root.append(holder);
  const toggles=elem('div',undefined,'scope-inline');holder.append(toggles);
  const health=await peekHealth(ctx);
  if(!holder.isConnected)return;
  const mode=health?workspace.state.healthMode:'snapshot';
  for(const [key,label] of [['snapshot','Snapshot (selected hour)'],['overall','Overall Health (full study)']]){
    const control=button(toggles,label,()=>{
      workspace.state.healthMode=key;workspace.inspected=null;refreshWorkspace();
    });
    control.setAttribute('aria-pressed',mode===key);
    if(key==='overall'&&!health)control.disabled=true;
  }
  if(!health)holder.append(elem('p','Whole-study health requires recorded hourly electrical rows. Snapshot is available for this report.','fine'));
  if(mode==='overall'){
    if(workspace.state.healthPhase==='pre'&&!Object.values(health.bus).some(row=>row.pre_violation?.samples))
      workspace.state.healthPhase='final';
    overallFeeder(holder,health,ctx,axis);
    return;
  }
  const worker=elem('div',undefined,'scope-inline');holder.append(worker);
  const select=workspace.state.selection;
  const cursor=workspace.state.time.cursor||axis[0], i=axis.indexOf(cursor);
  const index=Math.max(0,i);
  worker.append(elem('output',axis[index]+' · '+(ctx.archive.manifest.clock||'Clock not recorded')));
  for(const kind of ['bus','line']){
    const ids=Object.keys(ctx.gallery.groups[kind]?.entities||{});
    if(ids.length)selectControl(worker,kind==='bus'?'Bus':'Line',
      [['','Select'],...ids.map(id=>[id,id])],select.kind===kind?select.ids[0]:'',
      id=>{if(id)selectedEntity(kind,id,axis[index]);});
  }
  const equipment={pv:new Set((ctx.archive.metadata?.pv_buses||[]).map(String)),
    bess:new Set(hasInstalledBess(ctx)?(manualUnits(ctx.archive.metadata).length?manualUnits(ctx.archive.metadata):
      ctx.archive.metadata?.optimizer?.fleet||[]).map(u=>String(u.bus_id)):[])};
  const overlays=[['bus','voltage_pu'],['bus','voltage_angle_deg'],['line','sending_p_kw'],['line','sending_q_kvar'],
    ['line','p_kw'],['line','q_kvar'],['line','current_a'],['line','loading_percent'],['line','loss_p_kw'],
    ['line','loss_kw'],['line','loss_q_kvar'],['bus','shedding_kw'],['bus','bess_input_kw'],['bus','bess_soc_percent']]
    .filter(([group,field])=>academicHas(ctx,group,field));
  const state=academicState.Network||=(Object.create(null));
  const overlayOptions=[['','Single-line diagram'],...overlays.map(([g,f])=>[g+'|'+f,(g==='line'?'Branch: ':'Bus: ')+readable(f)])];
  const categoryMap=Object.fromEntries(Object.entries(ctx.gallery.groups['load input']?.categories||{}).flatMap(
    ([,category])=>category.buses.map(id=>[id,category.label])));
  if(Object.keys(categoryMap).length)overlayOptions.push(['category','Bus: Load profile category']);
  const currentOverlay=overlayOptions.some(([key])=>key===state.overlay)?state.overlay||'':'';
  selectControl(worker,'Electrical overlay',overlayOptions,currentOverlay,value=>{state.overlay=value;refreshWorkspace();});
  const [group,field]=currentOverlay==='category'?['bus','category']:currentOverlay.split('|');
  const ids=academicIds(ctx,group),samples={};
  if(field==='category'){
    Object.assign(samples,categoryMap);
  }else if(field){
    await Promise.all(ids.map(async id=>{
      const [value]=await sampleValues(ctx,{group,field},id,index,index+1);
      samples[id]=value;
    }));
  }
  if(!holder.isConnected)return;
  networkMap(holder,ctx.archive.metadata?.topology,samples,group,field,
    (kind,id)=>selectedEntity(kind,id,workspace.state.time.cursor||axis[index]),select,null,equipment);
  if(state.pathActive)highlightAcademicPath(state.pathActive,holder);
  holder.append(elem('p','Square: slack · Circle: bus · PV / BESS: archived installations'+
    (field==='loading_percent'?' · Gray branches: loading unavailable without a rating.':''),'fine'));
  const svg=holder.querySelector('svg.feeder');
  if(svg)button(holder,'Export single-line SVG',()=>publicationNetwork(svg,ctx,axis[index]));
}

async function controlDetails(ctx,stamp,index) {
  const range=ctx.gallery.controls?.find(([a,b])=>a<=index&&index<=b);
  if(!range)return null;
  return (await readings(ctx)(range[2])).find(row=>row.timestamp.replace('T',' ')===stamp)||null;
}
async function systemDetails(ctx,index) {
  if(!ctx.data.hour_windows?.length) {
    const rows=ctx.data.hours_block!=null?await readings(ctx)(ctx.data.hours_block):ctx.data.hours;
    return rows?.[index]||{};
  }
  const range=ctx.data.hour_windows.find(([i])=>index>=i&&index<i+168);
  return range?(await readings(ctx)(range[1]))[index-range[0]]||{}:{};
}
function rowEvidence(root,record,ctx,selectedStamp) {
  const items=elem('section');items.append(elem('h3','Recorded correction evidence'));root.append(items);
  if(!record){
    items.append(elem('p',ctx.gallery.controls?.length?'No control action recorded at this timestamp.':'Control evidence was not archived.','empty'));
    return;
  }
  items.append(elem('p',[record.policy,record.outcome,record.attribution,
    (record.reason_codes||[]).join(', ')].filter(Boolean).join(' · '),'fine'));
  const evidence=(record.constraints||[]).map(s=>[s.type,s.entity,s.limit,s.unit,s.before?.measured,s.after_bess?.measured,s.final?.measured,
    s.final?.excess==null?'Unknown':s.final.excess>0?'Violation remains':'Within recorded limit']);
  if(evidence.length)grid(items,['Constraint','Element','Limit','Unit','Before','After BESS','Final','Final status'],evidence);
  const actions=(record.actions||[]).map(a=>[a.sequence,a.action,a.bus_id,a.requested,a.accepted,a.unit,a.p_kw,a.q_kvar,a.s_kva,a.status]);
  if(actions.length)grid(items,['#','Action','Bus','Requested','Applied','Unit','P (kW)','Q (kvar)','S (kVA)','Status'],actions);
  else items.append(elem('p','No control action recorded.','fine'));
  const buttons=selectionPanel(items);
  if(ctx.key==='current'){
    for(const bus of new Set((record.actions||[]).map(a=>a.bus_id).filter(x=>x!=null)))
      button(buttons,'Select bus '+bus,()=>selectedEntity('bus',bus,selectedStamp,ctx.scenario));
    for(const line of new Set((record.constraints||[]).filter(c=>c.type==='ampacity').map(c=>c.entity)))
      button(buttons,'Select line '+line,()=>selectedEntity('line',line,selectedStamp,ctx.scenario));
  }
  button(buttons,'Export exact decision JSON',()=>saveJSON(record,'control_'+safeFilename(selectedStamp)+'.json'));
}
function saveJSON(data,name){saveBlob(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),name);}
async function itemRows(ctx,pick,index) {
  const rows=[];
  const types=pick.kind?[[pick.kind,pick.id],['system','System']]:[[pick.group||'system',pick.id||'System']];
  if(pick.kind==='bus'&&ctx.gallery.groups.battery)types.push(['battery',pick.id]);
  for(const [group,id] of types){
    const g=ctx.gallery.groups[group];if(!g?.entities?.[id])continue;
    for(const name of g.fields){
      const [value]=await sampleValues(ctx,{group,field:name},id,index,index+1);
      rows.push({group,id,field:name,value,unit:chartUnit(name,ctx.archive.manifest)});
    }
  }
  const lines=ctx.archive.metadata?.topology?.lines;
  if(pick.kind==='line'){
    const line=lines?.find(l=>String(l.line_id)===pick.id);
    const prefix=[['from_bus',line?.from_bus],['to_bus',line?.to_bus]];
    if(line)for(const [field,value] of prefix)rows.unshift({group:'line',id:pick.id,field,value,unit:''});
  }
  return rows;
}
function exactTable(root,rows,pick) {
  const section=elem('section');section.append(elem('h3','Selected records'));root.append(section);
  const tools=selectionPanel(section),filter=elem('input');filter.type='search';filter.placeholder='Filter measurements';filter.setAttribute('aria-label','Filter measurements');
  tools.append(filter);
  let order='recorded';
  selectControl(tools,'Order',[['recorded','Recorded'],['name','Field name'],['value','Highest numeric value']],order,v=>{order=v;paint();});
  const table=elem('div');section.append(table);
  const results=()=>rows.filter(r=>(r.group+' '+r.id+' '+r.field+' '+readable(r.field)).toLowerCase().includes(filter.value.toLowerCase()));
  function paint(){
    table.replaceChildren();
    const list=results().slice();
    if(order==='name')list.sort((a,b)=>a.field.localeCompare(b.field));
    if(order==='value')list.sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity));
    grid(table,['Source','Element','Field','Value','Unit'],list.map(r=>[r.group,r.id,readable(r.field),r.value,r.unit]));
  }
  button(tools,'Exact CSV',()=>saveRows(['Run','Scenario','Timestamp','Source','Entity','Field','Value','Unit'],
    results().map(r=>[pick.key,pick.scenario,pick.stamp,r.group,r.id,r.field,r.value,r.unit]),'records_'+safeFilename(pick.stamp)+'.csv'));
  button(tools,'Exact JSON',()=>saveJSON({selection:pick,rows:results()},'records_'+safeFilename(pick.stamp)+'.json'));
  filter.oninput=paint;paint();
}
async function pointDrawer(root) {
  const pick=workspace.inspected,pending=++workspace.drawerToken;
  root.replaceChildren();root.hidden=!pick;
  if(!pick)return;
  const heading=elem('div',undefined,'workspace-subhead');heading.append(elem('h2','Point details'));
  button(heading,'Close',()=>{workspace.inspected=null;pointDrawer(root);});
  root.append(heading);
  const ctx=chartContext(pick.key,pick.scenario);
  if(!ctx){root.append(elem('p','The selected report is unavailable.','empty'));return;}
  root.append(elem('p',[shortRun(ctx.archive),ctx.data.label,ctx.archive.manifest.clock||'Clock not recorded',
    pick.category||(pick.kind&&pick.id?pick.kind+' '+pick.id:'System')].join(' · '),'fine'));
  if(pick.field)root.append(elem('p',readable(pick.field)+' · '+workspaceNumber(pick.value,pick.unit)));
  if(pick.categorical){root.append(elem('p',pick.label,'fine'));return;}
  if(pick.bucket){
    const bucket=pick.bucket, caption=bucket.start+' → '+bucket.end+' · '+bucket.count+' valid samples';
    root.append(elem('p',caption,'fine'));
    if(pick.aggregation)root.append(elem('p',pick.aggregation+(bucket.partial?' · partial calendar bucket':''),'fine'));
    if(bucket.violationSamples!==null&&bucket.violationSamples!==undefined)
      root.append(elem('p',fmt(bucket.violationSamples)+' samples outside voltage limits · '+fmt(bucket.violationHours)+' h','fine'));
    if(bucket.missing)root.append(elem('p',bucket.missing+' timestamps unavailable in this bucket.','fine'));
    const input=elem('input');input.type='datetime-local';input.setAttribute('aria-label','Hour to inspect in this bucket');
    input.value=asLocalInput(bucket.start);input.min=asLocalInput(bucket.start);input.max=asLocalInput(bucket.end);
    root.append(input);button(root,'Inspect recorded hour',()=>{
      const stamp=hourInput(input.value);
      if(stamp>=bucket.start&&stamp<=bucket.end){
        workspace.inspected={...pick,stamp,bucket:null,field:null};
        void pointDrawer(root);
      }
    });return;
  }
  const axis=await timeline(ctx);
  const index=axis.indexOf(pick.stamp);
  if(!root.isConnected||pending!==workspace.drawerToken)return;
  if(index<0){root.append(elem('p','The timestamp has no recorded sample.','empty'));return;}
  const [raw,events,rows]=await Promise.all([systemDetails(ctx,index),controlDetails(ctx,pick.stamp,index),itemRows(ctx,pick,index)]);
  if(!root.isConnected||pending!==workspace.drawerToken)return;
  root.append(elem('p',pick.stamp+' · Converged '+recordLabel(raw.converged)+' · Feasible '+recordLabel(raw.feasible),'fine'));
  if(raw.diagnostic_only||raw.fbs_message)root.append(elem('p',raw.fbs_message||'Diagnostic hour','warning'));
  rowEvidence(root,events,ctx,pick.stamp);
  if(ctx.key==='current'&&ctx.archive.metadata?.layout?.positions){
    const topology=elem('details');topology.append(elem('summary','Feeder at this timestamp'));root.append(topology);
    topology.ontoggle=()=>{
      if(!topology.open||topology.childElementCount>1)return;
      const chosen=pick.kind&&pick.id?{kind:pick.kind,ids:[pick.id]}:workspace.state.selection;
      networkMap(topology,ctx.archive.metadata.topology,{},'topology','voltage_pu',
        (kind,id)=>selectedEntity(kind,id,pick.stamp,ctx.scenario),chosen);
    };
  }
  exactTable(root,rows,pick);
}
function workspaceToolbar(root,topic,ctx) {
  const toolbar=elem('div',undefined,'workspace-toolbar');
  root.append(toolbar);
  const compact=elem('div',undefined,'workspace-compact');
  toolbar.append(compact);
  const layout=elem('div',undefined,'scope-inline mode-picker');
  compact.append(layout);
  for(const [key,name] of [['grid','Grid'],['focus','Focus'],['engineering','Engineering']]){
    const control=button(layout,name,()=>{workspace.state.mode=key;refreshWorkspace();});
    control.setAttribute('aria-pressed',key===workspace.state.mode);
  }
  const time=workspace.state.time;
  const range=time.start?(time.start+(time.end?' through '+time.end:'')):({all:'Full study','24h':'24 hours',
    '7d':'7 days','14d':'14 days',month:'Calendar month',year:'Calendar year',custom:'Custom period'}[time.period]);
  compact.append(elem('span',[ctx.data.label,range,resolutionLabels[time.resolution||'auto']].filter(Boolean).join(' · '),'compact-scope'));
  const disclosure=button(compact,workspace.state.controlsOpen?'Hide chart controls':'Show chart controls',()=>{
    workspace.state.controlsOpen=!workspace.state.controlsOpen;
    row.hidden=!workspace.state.controlsOpen;
    disclosure.textContent=workspace.state.controlsOpen?'Hide chart controls':'Show chart controls';
    disclosure.setAttribute('aria-expanded',workspace.state.controlsOpen);
    saveLayout();
  });
  disclosure.setAttribute('aria-controls','advanced-chart-controls');
  disclosure.setAttribute('aria-expanded',workspace.state.controlsOpen);
  const row=elem('div',undefined,'workspace-advanced');
  row.id='advanced-chart-controls';row.hidden=!workspace.state.controlsOpen;toolbar.append(row);
  function group(heading){
    const fieldset=elem('fieldset');fieldset.append(elem('legend',heading));row.append(fieldset);return fieldset;
  }
  const studyControls=group('Study');
  const timeControls=group('Time and resolution');
  const layoutControls=group('Layout');
  if(topic!=='Summary')selectControl(studyControls,'Scenario',scenarioChoices(run),workspace.primary,value=>{
    workspace.primary=value;workspace.state.scenario=value;workspace.state.time.zoom=null;refreshWorkspace();
  });
  if(ctx.archive.manifest.kind!=='base case'){
    timeSettings(timeControls,time,refreshWorkspace);
    selectControl(timeControls,'Resolution',resolutionChoices,time.resolution||'auto',value=>{
      time.resolution=value;time.zoom=null;refreshWorkspace();
    });
  }
  if(['Study Inputs','Power & Energy'].includes(topic)){
    const input=ctx.gallery.groups['load input']||ctx.gallery.groups['load output'];
    if(input?.categories){
      const demand=group('Demand groups'),scope=workspace.state.loadScope;
      selectControl(demand,'Group by',[['total','System total'],['category','Profile category'],['bus','Individual bus']],
        scope.group,value=>{scope.group=value;refreshWorkspace();});
      selectControl(demand,'Profile category',[['','All categories'],...Object.keys(input.categories).map(id=>[id,categoryLabel(input,id)])],
        scope.category,value=>{scope.category=value;refreshWorkspace();});
      if(scope.group==='bus'){
        const buses=(input.categories[scope.category]?.buses||Object.values(input.categories).flatMap(category=>category.buses))
          .filter(id=>Object.hasOwn(input.entities,id));
        const selected=workspace.state.selection.kind==='bus'?workspace.state.selection.ids[0]:'';
        selectControl(demand,'Bus',buses.map(id=>[id,'Bus '+id]),buses.includes(selected)?selected:buses[0],
          id=>{workspace.state.selection={kind:'bus',ids:[id]};refreshWorkspace();});
      }
      demand.append(elem('p',input.category_source==='Category not provided'?
        'Category not provided. Recorded demand is Unclassified.':
        'Archived bus assignments may describe study assumptions rather than observed customer classes.','fine'));
    }else if(ctx.archive.manifest.kind!=='base case'){
      studyControls.append(elem('p','Category not provided in this archived dashboard.','fine'));
    }
  }
  if(ctx.archive.manifest.timestamp_count>0 && ctx.archive.manifest.kind!=='base case'){
    const label=elem('label','Inspect hour'),input=elem('input');
    input.type='datetime-local';input.step=3600;input.value=asLocalInput(workspace.state.time.cursor);
    input.onchange=async()=>{
      const stamp=hourInput(input.value),axis=await timeline(ctx);
      if(!input.isConnected)return;
      if(!axis.includes(stamp)){input.setCustomValidity('The archive has no sample at this timestamp.');input.reportValidity();return;}
      input.setCustomValidity('');
      workspace.state.time.cursor=stamp;
      const selected=workspace.state.selection;
      workspace.inspected={stamp,key:'current',scenario:ctx.scenario,kind:selected.kind,id:selected.ids[0]||'System'};
      const [first,last]=chartWindow(axis,workspace.state.time,ctx.archive.manifest.dt_hours);
      if(!(stamp>=axis[first]&&stamp<=axis[last-1])){
        if(workspace.state.time.period==='custom')workspace.state.time.end=stamp;
        workspace.state.time.start=stamp;workspace.state.time.zoom=null;
      }
      refreshWorkspace();
    };
    label.append(input);timeControls.append(label);
  }
  if(workspace.state.selection.kind)button(studyControls,'Clear '+workspace.state.selection.kind+' filter',()=>{
    workspace.state.selection={kind:'',ids:[]};refreshWorkspace();
  });
  button(layoutControls,'Add chart',()=>addChart(topic));
  const details=elem('details',undefined,'workspace-layout-menu');details.append(elem('summary','Layouts'));layoutControls.append(details);
  const controls=elem('div',undefined,'layout-dropdown');details.append(controls);
  button(controls,'Export layout JSON',()=>saveJSON({...workspace.state,savedAt:new Date().toISOString(),
    clock:run.manifest.clock,topology:run.manifest.topology_sha256},safeFilename(shortRun(run))+'_layout.json'));
  button(controls,'Export reusable template',()=>{
    const template=plainClone(workspace.state);
    template.runId=null;template.scenario='';template.time={period:template.time.period,resolution:template.time.resolution};
    template.selection={kind:'',ids:[]};
    for(const chart of Object.values(template.charts)){
      chart.sourceScenario='';chart.zoom=null;chart.time={period:chart.time.period,resolution:chart.time.resolution,linked:chart.time.linked};
      if(chart.comparison.run!=='current')chart.comparison={mode:'none',run:'current',scenario:''};
    }
    saveJSON(template,'ee499_chart_template.json');
  });
  const label=elem('label','Import layout JSON'),input=elem('input');input.type='file';input.accept='.json,application/json';label.append(input);controls.append(label);
  input.onchange=async()=>{
    try{
      const layout=input.files[0];if(!layout)return;
      if(layout.size>4*1024*1024)throw Error('The layout exceeds the supported size.');
      workspace.state=layoutFromJSON(JSON.parse(await layout.text()),run.manifest.run_id);
      if(workspace.state.scenario&&Object.hasOwn(run.scenarios,workspace.state.scenario))workspace.primary=workspace.state.scenario;
      if(workspacePages.includes(workspace.state.tab)){screen=workspace.state.tab;tabs();}
      workspace.editor='';refreshWorkspace();
    }catch(error){controls.append(elem('p',error.message,'warning'));}
  };
  button(controls,'Restore topic presets',()=>resetPresets(topic));
  const status=elem('output',workspace.saveStatus||'Unsaved','layout-status');
  status.id='layout-status';status.setAttribute('aria-live','polite');layoutControls.append(status);
}
function compareWorkspace(root,ctx){
  const pane=elem('section',undefined,'comparison-intro');root.append(pane);
  const title=elem('label','Open saved dashboards for comparison'),file=elem('input');
  file.type='file';file.accept='.html,.zip,text/html,application/zip';file.multiple=true;title.append(file);pane.append(title);
  file.onchange=()=>{file.disabled=true;void addComparisons([...file.files],pane);};
  if(workspace.importMessage)pane.append(elem('p',workspace.importMessage,'warning'));
  pane.append(elem('p','Choose the reference and comparison style in a chart’s Edit sidebar. Candidate is the current report.','fine'));
  const info=[];
  for(const [key,archive] of [['current',run],...workspace.imports]){
    const slack=archive.metadata?.topology?.buses?.find(bus=>bus.is_slack);
    for(const scenario of Object.values(archive.scenarios))info.push([shortRun(archive),scenario.label,archive.manifest.clock,
      slack?.v_set_pu,scenario.hour_count??archive.manifest.timestamp_count,archive.manifest.currency,
      archive.input_info?.selected_network_sha256||archive.manifest.input_hashes?.['inputs/network.xlsx'],
      key==='current'?'Current report':'Opened reference']);
  }
  grid(pane,['Report','Scenario','Clock','Slack (pu)','Samples','Currency','Workbook SHA-256','Role'],info);
}

async function renderWorkspace(root,epoch) {
  const topic=topicOf(),state=workspace.state;
  let ctx=chartContext();
  if(!ctx){root.append(elem('p','No archived scenario.','empty'));return;}
  if(topic==='Summary'){
    const [first,second]=selectedSummaryScenarios(ctx);
    ctx=second||first;
    workspace.primary=ctx.scenario;
  }
  state.tab=topic;workspace.scope.clear();
  workspaceToolbar(root,topic,ctx);
  if(topic==='Summary'){
    const summary=elem('div');root.append(summary);
    renderStudySummary(summary,ctx);
  }
  if(topic==='Compare Runs')compareWorkspace(root,ctx);
  if(topic==='Study Inputs'){
    const provenance=elem('details',undefined,'comparison-intro');
    provenance.append(elem('summary','Source, interval and workbook provenance'));
    const manifest=ctx.archive.manifest,metadata=ctx.archive.metadata;
    grid(provenance,['Recorded input','Value'],[
      ['Clock',manifest.clock],['Clock provenance',ctx.archive.input_info?.clock_status],['Input mode',manifest.source],
      ['Study start',manifest.interval?.start],['Study end',manifest.interval?.end_exclusive??manifest.interval?.last],
      ['Slack setpoint (pu)',metadata?.topology?.buses?.find(b=>b.is_slack)?.v_set_pu],
      ['Selected workbook hash',ctx.archive.input_info?.selected_network_sha256??manifest.input_hashes?.['inputs/network.xlsx']],
      ['Distributor workbook hash',ctx.archive.input_info?.distributor_network_sha256],
      ['Recorded irradiance',ctx.gallery.groups['solar source']?.fields.includes('irradiance_w_m2')?'Available':'Not recorded'],
      ['Load profile categories',ctx.gallery.groups['load input']?.category_source||'Category not provided'],
    ]);
    root.append(provenance);
  }
  const supporting={
    'Control Decisions':['Open filterable decision ledger','Decisions'],
    Network:['Open selected-hour heatmap and electrical records','Network records'],
    Forecasting:['Open forecasting error tables','Forecast accuracy'],
    Optimization:['Open ranked candidates and placement details','Technical summary'],
  }[topic];
  if(supporting){
    const area=elem('div',undefined,'controls');button(area,supporting[0],()=>{
      galleryState.scenario=workspace.primary;
      scenario=workspace.primary;
      screen=supporting[1];tabs();render();
    });root.append(area);
  }
  if(topic==='BESS'&&!hasInstalledBess(ctx)){
    const state=section(root,'Battery operation');
    state.append(elem('p',ctx.scenario==='no_bess'||ctx.data.has_bess===false?'No BESS installed in this scenario':
      'No verified BESS installation is recorded for this scenario.','empty'));
    const verified=Object.keys(run.scenarios).find(key=>key!==ctx.scenario&&hasInstalledBess(chartContext('current',key)));
    if(verified)button(state,'View BESS scenario',()=>{
      workspace.primary=verified;workspace.state.scenario=verified;refreshWorkspace();
    });
    button(state,'View network conditions',()=>{screen='Network';tabs();render();});
    return;
  }
  const ids=defaultCharts(topic,ctx);
  const saved=ids.map(id=>state.charts[id]).filter(Boolean);
  const active=saved.find(c=>c.id===state.active)||saved[0];
  const editor=saved.find(c=>c.id===workspace.editor)||(state.mode==='engineering'?active:null);
  const shell=elem('div',undefined,'workspace-shell');root.append(shell);
  if(editor)shell.classList.add('with-editor');
  const area=elem('div',undefined,'workspace-main');shell.append(area);
  const feeder=elem('div');area.append(feeder);
  const plots=elem('div',undefined,'workspace-grid '+(state.mode==='grid'?'grid-view':'single-view'));area.append(plots);
  const drawer=elem('aside',undefined,'point-drawer');drawer.id='point-drawer';drawer.hidden=true;area.append(drawer);
  if(editor){
    const sidebar=elem('aside',undefined,'workspace-sidebar');sidebar.setAttribute('aria-label','Chart editor');
    shell.append(sidebar);chartEditor(sidebar,editor,topic,ctx);
  }
  if(!saved.length&&topic==='My Dashboard')plots.append(elem('p','Pin charts from any topic, or add your own.','empty'));
  if(topic==='Network'){
    const select=state.selection;
    const axis=await timeline(ctx);
    if(epoch!==workspace.epoch||!shell.isConnected)return;
    if(state.healthMode!=='overall'&&!workspace.inspected&&select.kind&&axis.length)
      workspace.inspected={key:'current',scenario:ctx.scenario,kind:select.kind,id:select.ids[0],stamp:state.time.cursor||axis[0]};
    void workspaceFeeder(feeder,ctx,axis).catch(error=>feeder.append(elem('p',error.message,'warning')));
  }
  if(workspace.inspected)void pointDrawer(drawer).catch(error=>drawer.append(elem('p',error.message,'warning')));
  if(academicSections[topic]){
    const academic=elem('div');area.insertBefore(academic,plots);
    renderAcademic(academic,ctx,topic);
  }
  if(topic==='My Dashboard'||academicSections[topic]){
    const library=elem('details',undefined,'preset-picker');library.append(elem('summary','Add a preset chart'));area.insertBefore(library,plots);
    const keys=topic==='My Dashboard'?Object.keys(presetCharts):[...new Set([
      ...topicPresetKeys(topic),...(topic==='Study Inputs'?topicPresetKeys('Forecasting'):[]),
      ...(topic==='Power & Energy'?topicPresetKeys('Control Decisions'):[])])];
    for(const key of keys){
      const template=presetChart(key,topic,ctx.gallery);
      if(template)button(library,presetCharts[key][0],()=>addChart(topic,template));
    }
  }
  for(const chart of state.mode==='focus'&&active?[active]:saved){
    const card=elem('article',undefined,'workspace-card size-'+chart.size);plots.append(card);
    if(topic==='My Dashboard'){
      card.draggable=true;
      card.ondragstart=e=>{
        if(e.target.closest?.('canvas'))e.preventDefault();
        else e.dataTransfer.setData('text/plain',chart.id);
      };
      card.ondragover=e=>e.preventDefault();
      card.ondrop=e=>{
        e.preventDefault();const from=state.pinned.indexOf(e.dataTransfer.getData('text/plain')),to=state.pinned.indexOf(chart.id);
        if(from>=0&&to>=0&&from!==to){state.pinned.splice(to,0,state.pinned.splice(from,1)[0]);refreshWorkspace();}
      };
    }
    try{
      const data=await prepareWorkspaceChart(chart,state.selection);
      if(epoch!==workspace.epoch||!card.isConnected)return;
      workspaceChart(card,chart,data,topic);
    }catch(error){
      if(epoch===workspace.epoch&&card.isConnected)workspaceChart(card,chart,{note:error.message},topic);
    }
  }
}


