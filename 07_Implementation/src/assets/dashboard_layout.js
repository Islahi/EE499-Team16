/* Declarative chart settings and windowed reads over the archived measurements. */
const LAYOUT_VERSION = 2;
const resolutionLabels={auto:'Auto',hourly:'Hourly',day:'Daily',week:'Weekly',month:'Monthly',year:'Yearly'};
const resolutionChoices=Object.entries(resolutionLabels);
const aggregateLabels={auto:'Metric default',mean:'Mean',peak:'Maximum',minimum:'Minimum',end:'Last recorded value',
  total:'Sum',energy:'Integrated energy',count:'Affected samples'};

const SERIES_LIMIT = 12;
const chartTopics = {
  'Study Inputs': ['load input', 'load output', 'PV input', 'solar source', 'forecast', 'forecast by bus'],
  Network: ['bus', 'line', 'system'],
  'Power & Energy': ['system', 'bus', 'line', 'load input', 'load output', 'PV input'],
  'Control Decisions': ['system', 'bus', 'line'],
  BESS: ['battery', 'battery daily audit', 'bus', 'system'],
  Economics: ['system', 'bus', 'economics'],
  Optimization: ['optimization'],
  Forecasting: ['forecast', 'forecast by bus'],
  Summary: ['system', 'bus', 'line', 'battery', 'load input', 'PV input'],
};

const presetCharts = {
  load: ['Requested, served and shed load', 'system', ['requested_load_kw', 'load_input_kw', 'shedding_kw'], ['shedding_kw']],
  pv: ['Available, delivered and curtailed PV', 'system', ['available_pv_kw', 'pv_input_kw', 'curtailment_kw'], ['curtailment_kw']],
  grid: ['Grid exchange', 'system', ['grid_import_kw', 'grid_export_kw', 'slack_p_kw']],
  voltage: ['Feeder voltage envelope', 'system', ['voltage_min_pu', 'voltage_mean_pu', 'voltage_max_pu']],
  rawVoltage: ['Voltage before any control in this scenario', 'system',
    ['uncontrolled_voltage_min_pu','uncontrolled_voltage_max_pu']],
  voltageViolations: ['Voltage constraint violations', 'system', ['voltage_violation_bus_count'], ['voltage_violation_bus_count']],
  voltageExcess: ['Maximum voltage violation', 'system', ['voltage_violation_max_pu']],
  bus: ['Selected bus voltage', 'bus', ['voltage_pu']],
  angle: ['Selected bus voltage angle', 'bus', ['voltage_angle_deg']],
  busLoad: ['Selected bus demand', 'bus', ['requested_load_kw', 'load_input_kw', 'shedding_kw'], ['shedding_kw']],
  busQ: ['Selected bus reactive demand', 'bus', ['requested_load_kvar', 'load_input_kvar', 'shedding_kvar'], ['shedding_kvar']],
  line: ['Selected line current and rating', 'line', ['current_a', 'ampacity_a']],
  lineFlow: ['Selected line active power', 'line', ['sending_p_kw', 'receiving_p_kw']],
  lineReactive: ['Selected line reactive power', 'line', ['sending_q_kvar', 'receiving_q_kvar']],
  lineLoss: ['Selected line losses', 'line', ['loss_p_kw']],
  rank: ['Bus voltage ranking at the inspected hour', 'bus', ['voltage_pu'], ['voltage_pu']],
  inputsP: ['Archived demand', 'load input', ['p_kw', 'workbook_base_p_kw']],
  inputsQ: ['Archived reactive demand', 'load input', ['q_kvar', 'workbook_base_q_kvar']],
  categoryLoad: ['Load by profile category', 'load input', ['p_kw']],
  categoryPQ: ['Active and reactive demand by category', 'load input', ['p_kw','q_kvar']],
  categoryComposition: ['Demand composition by category', 'load input', ['p_kw'], ['p_kw']],
  categoryShare: ['Selected category versus total demand', 'load input', ['p_kw']],
  categoryOutput: ['Served and shed demand by category', 'load output', ['served_load_kwh','shed_kwh'], ['shed_kwh']],
  solar: ['Archived PV availability', 'PV input', ['p_kw', 'workbook_nameplate_kw']],
  irradiance: ['Archived irradiance', 'solar source', ['irradiance_w_m2']],
  actions: ['Shedding and curtailment', 'system', ['shedding_kw', 'curtailment_kw'], ['shedding_kw', 'curtailment_kw']],
  actionsCount: ['Buses affected by shedding', 'system', ['affected_load_buses'], ['affected_load_buses']],
  bess: ['Battery charge and discharge', 'system', ['bess_charge_kw', 'bess_discharge_kw']],
  bessSOC: ['Selected battery state of charge', 'bus', ['bess_soc_percent']],
  bessPQ: ['Selected battery power', 'bus', ['bess_input_kw']],
  bessQ: ['Selected battery reactive power', 'bus', ['bess_input_kvar']],
  bessRating: ['Inverter loading', 'bus', ['inverter_loading_percent']],
  bessDaily: ['Daily SOC restoration', 'battery daily audit', ['soc_start', 'soc_end']],
  fleetPower: ['Battery power at recorded installation', 'battery', ['power_kw']],
  fleetSoc: ['Battery SOC at recorded installation (fraction)', 'battery', ['soc_after']],
  operating: ['Recorded hourly costs and credit', 'system',
    ['grid_purchase_cost', 'grid_export_credit', 'shedding_cost', 'curtailment_cost'],
    ['grid_purchase_cost', 'grid_export_credit', 'shedding_cost', 'curtailment_cost']],
  annual: ['Recorded annual cost components', 'economics', ['annual_component_cost'], ['annual_component_cost']],
  genetic: ['GA convergence', 'optimization', ['best_annual_cost']],
  prediction: ['Holdout actual and forecast', 'forecast', ['actual_kw', 'forecast_kw']],
  residual: ['Holdout forecast residuals', 'forecast', ['residual_kw']],
  energy: ['Delivered, shed and grid energy', 'system', ['served_load_kwh', 'shed_kwh', 'grid_import_kwh'], ['shed_kwh']],
};

const topicPresets = {
  Summary: ['load','grid','voltage','bessSOC','fleetSoc','pv','bus','actions'],
  'Study Inputs': ['inputsP','inputsQ','categoryLoad','categoryPQ','categoryComposition','categoryShare','solar','irradiance'],
  Network: ['voltage','rawVoltage','voltageViolations','voltageExcess','bus','angle','line','lineFlow','lineReactive','lineLoss','busLoad','busQ','rank'],
  'Power & Energy': ['load','pv','grid','energy','categoryOutput','categoryLoad','categoryShare'],
  'Control Decisions': ['actions','actionsCount','voltage'],
  BESS: ['bess','bessSOC','bessPQ','bessQ','bessRating','bessDaily','fleetPower','fleetSoc'],
  Economics: ['annual','operating'],
  Optimization: ['genetic'],
  Forecasting: ['prediction','residual'],
};

const entityKind = group => ['bus','line'].includes(group) ? group : group === 'battery' || group === 'battery daily audit' ? 'bus' : '';
const isObservation = value => typeof value === 'number' && Number.isFinite(value);
const moneyField = field => /cost|credit|penalty|purchases/.test(field);
const annualField = field => field === 'annual_component_cost' || field === 'best_annual_cost';
const categoryGroup = group => group==='load input'||group==='load output';
const categoryLabel = (group,id) => group.categories?.[id]?.label||(id==='Total'?'System total':/^\d+$/.test(id)?'Bus '+id:id);
const categoryName = (group,id) => group?.categories?.[id]?.label||id.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const demandFields={
  'load output':{
    requested_load_kw:'Requested demand (kW)',load_input_kw:'Served demand (kW)',shedding_kw:'Load shedding (kW)',
    requested_load_kvar:'Requested reactive demand (kvar)',load_input_kvar:'Served reactive demand (kvar)',
    shedding_kvar:'Shed reactive demand (kvar)',requested_load_kwh:'Requested energy (kWh)',
    served_load_kwh:'Served energy (kWh)',shed_kwh:'Shed energy (kWh)',
  },
  'load input':{p_kw:'Archived input demand (kW)',q_kvar:'Archived input reactive demand (kvar)',
    p_kwh:'Archived input energy (kWh)'},
  forecast:{actual_kw:'Observed demand at holdout (kW)',forecast_kw:'Forecast demand at holdout (kW)'},
};
function entityHasField(group,id,field){
  return Boolean(group?.fields.includes(field)&&Object.hasOwn(group.entities,id)&&
    (!group.entity_fields||group.entity_fields[id]?.includes(field)));
}
function categoryEntities(group,name,field){
  if(!group)return [];
  const keys=Object.keys(group.categories||{});
  const ids=name==='forecast'?Object.keys(group.entities).filter(key=>!['solar_pv','total','system'].includes(key.toLowerCase())):keys;
  return ids.filter(id=>entityHasField(group,id,field));
}
function categoryMeasurements(ctx){
  return Object.entries(demandFields).flatMap(([group,fields])=>Object.entries(fields).flatMap(([field,label])=>{
    const catalogue=ctx.gallery.groups[group],ids=categoryEntities(catalogue,group,field);
    return ids.length?[{group,field,label,scope:'category',ids}]:[];
  }));
}
const exactExportHeader = (series, fallbackUnit) =>
  [series.runLabel, series.runId, series.scenarioLabel, series.scope, series.group, series.entity, series.field||series.label, series.aggregation, series.comparison]
    .filter(Boolean).join(' / ') + ' [' + (series.unit || fallbackUnit || 'unitless') + ']';

function chartUnit(field, manifest) {
  if (annualField(field)) return (manifest.currency || 'Unrecorded currency') + '/year';
  if (field.endsWith('_usd_per_hour')) return 'USD/h';
  if (moneyField(field)) return manifest.currency || 'Unrecorded currency';
  return unitOf(field);
}

function plainClone(value) { return JSON.parse(JSON.stringify(value)); }
function newChart(id, title = 'Custom chart') {
  return {id,title,series:[],time:{linked:true},selection:{linked:true},comparison:{mode:'none',run:'current',scenario:''},
    aggregation:'linked',reducer:'auto',size:'medium',stack:false,sourceScenario:'',zoom:null,loadScope:null};
}
function presetChart(key, topic, gallery) {
  const [title,baseGroup,fields,bars=[]] = presetCharts[key];
  const group=topic==='Power & Energy'&&key==='load'&&gallery?.groups?.['load output']?'load output':baseGroup;
  const catalogue = gallery?.groups?.[group];
  if (!catalogue || !fields.some(field => catalogue.fields.includes(field))) return null;
  const chart = newChart(topic + ':' + key,title);
  chart.preset = key;
  chart.series = fields.filter(field => catalogue.fields.includes(field)).map(field => ({
    group,field,ids:[],style:bars.includes(field)?'bar':'line',color:'',dash:'solid',axis:'left',visible:true,
  }));
  if(key.startsWith('category')){
    if(!catalogue.categories)return null;
    for(const series of chart.series)if(series.field==='q_kvar')series.axis='right';
    chart.stack=key==='categoryComposition';
  }
  return chart;
}
function emptyLayout(runId) {
  return {version:LAYOUT_VERSION,runId,mode:'grid',tab:'Summary',active:'',
    time:{period:'7d',resolution:'auto',start:'',end:'',cursor:''},loadScope:{group:'total',category:''},controlsOpen:false,healthMode:'snapshot',healthPhase:'final',selection:{kind:'',ids:[]},charts:{},topics:{},pinned:[]};
}
function layoutFromJSON(input, runId) {
  if (!input || ![0,1,LAYOUT_VERSION].includes(input.version) || !input.charts || Array.isArray(input.charts))
    throw Error('Unsupported dashboard layout version');
  const state = emptyLayout(runId);
  const limitText = (value,n=120) => typeof value==='string'?value.slice(0,n):'';
  const strings = (value,n=SERIES_LIMIT) => Array.isArray(value)?value.slice(0,n).map(s=>limitText(s)).filter(Boolean):[];
  const window = data => ({start:limitText(data?.start),end:limitText(data?.end),cursor:limitText(data?.cursor),
    zoom:strings(data?.zoom,2).length===2?strings(data.zoom,2):null,
    period:['24h','7d','14d','month','year','all','custom'].includes(data?.period)?data.period:'7d',
    resolution:Object.hasOwn(resolutionLabels,data?.resolution)?data.resolution:'auto'});
  state.mode = ['grid','focus','engineering'].includes(input.mode)?input.mode:'grid';
  state.tab = limitText(input.tab)||'Summary';
  if(state.tab==='Overview')state.tab='Summary';
  state.controlsOpen=input.controlsOpen===true;
  state.healthMode=input.healthMode==='overall'?'overall':'snapshot';
  state.healthPhase=['pre','reference'].includes(input.healthPhase)?input.healthPhase:'final';
  state.active = limitText(input.active);
  state.scenario = limitText(input.scenario);
  state.time = window(input.time);
  state.loadScope={group:['total','category','bus'].includes(input.loadScope?.group)?input.loadScope.group:'total',
    category:limitText(input.loadScope?.category)};
  state.selection = {kind:limitText(input.selection?.kind),ids:strings(input.selection?.ids)};
  for (const [id,source] of Object.entries(input.charts).slice(0,200)) {
    if (!id || id.length>120 || ['constructor','__proto__','prototype'].includes(id) || !Array.isArray(source?.series)) continue;
    const chart = newChart(id,limitText(source.title)||'Custom chart');
    chart.preset = Object.hasOwn(presetCharts,source.preset)?source.preset:null;
    chart.sourceScenario = limitText(source.sourceScenario);
    if(['total','category','bus'].includes(source.loadScope?.group))
      chart.loadScope={group:source.loadScope.group,category:limitText(source.loadScope.category)};
    chart.time = {...window(source.time),linked:source.time?.linked!==false};
    chart.selection = {linked:source.selection?.linked!==false};
    chart.size = ['medium','wide','large'].includes(source.size)?source.size:'medium';
    chart.aggregation = Object.hasOwn(resolutionLabels,source.aggregation)?source.aggregation:'linked';
    if(input.version<2&&source.aggregation==='hourly')chart.aggregation='linked';
    chart.reducer = Object.hasOwn(aggregateLabels,source.reducer)?source.reducer:'auto';
    if(input.version<2&&source.aggregation==='hourly'&&source.reducer==='mean')chart.reducer='auto';
    chart.stack = source.stack===true;
    chart.comparison = {mode:['none','overlay','side','difference'].includes(source.comparison?.mode)?source.comparison.mode:'none',
      run:limitText(source.comparison?.run)||'current',scenario:limitText(source.comparison?.scenario)};
    chart.series = source.series.slice(0,SERIES_LIMIT).filter(s=>s && typeof s==='object').map(s=>({
      group:limitText(s.group),field:limitText(s.field),ids:strings(s.ids),style:s.style==='bar'?'bar':'line',axis:s.axis==='right'?'right':'left',
      color:/^#[0-9a-f]{6}$/i.test(s.color)?s.color:'',dash:s.dash==='dashed'?'dashed':'solid',visible:s.visible!==false,
      ...(['category','bus','system'].includes(s.scope)?{scope:s.scope}:{}),
    })).filter(s=>s.group&&s.field);
    if (Array.isArray(source.zoom) && source.zoom.length===2) chart.zoom=strings(source.zoom,2);
    state.charts[id]=chart;
  }
  for (const [topic,ids] of Object.entries(input.topics||{})) {
    const key=topic==='Overview'?'Summary':topic;
    if (Object.hasOwn(chartTopics,key)||key==='My Dashboard'||key==='Compare Runs')
      state.topics[key]=[...new Set([...(state.topics[key]||[]),...strings(ids,200)])].filter(id=>Object.hasOwn(state.charts,id));
  }
  state.pinned = [...new Set(strings(input.pinned,200))].filter(id=>Object.hasOwn(state.charts,id));
  return state;
}

function entitiesFor(chart, series, group, selection, loadScope={group:'total',category:''}) {
  if(series.scope==='category'){
    const ids=categoryEntities(group,series.group,series.field);
    return series.ids.filter(id=>ids.includes(id));
  }
  if(series.scope==='system')return ['System'].filter(id=>entityHasField(group,id,series.field));
  if(series.scope==='bus')return series.ids.filter(id=>entityHasField(group,id,series.field));
  if(series.ids.length&&(group.categories||categoryGroup(series.group)))return series.ids.filter(id=>Object.hasOwn(group.entities,id));
  if(group.categories){
    const keys=Object.keys(group.categories).filter(id=>Object.hasOwn(group.entities,id));
    const filtered=keys.includes(loadScope.category)?[loadScope.category]:keys;
    if(chart.preset==='categoryShare')return ['Total',...filtered.slice(0,1)].filter(id=>Object.hasOwn(group.entities,id));
    if(chart.preset==='categoryComposition')return keys;
    if(loadScope.group==='bus'){
      const buses=(loadScope.category&&group.categories[loadScope.category]?group.categories[loadScope.category].buses:
        Object.values(group.categories).flatMap(category=>category.buses)).filter(id=>Object.hasOwn(group.entities,id));
      const selected=(selection?.ids||[]).filter(id=>selection.kind==='bus'&&buses.includes(id));
      if(!series.field.startsWith('workbook_'))return selected.length?selected:buses.slice(0,1);
    }
    const byCategory=loadScope.group==='category'||chart.preset?.startsWith('category')&&!chart.loadScope;
    if(byCategory&&!series.field.startsWith('workbook_'))return filtered;
  }
  const wanted = selection?.ids || [];
  const compatible = chart.selection.linked && entityKind(series.group) && entityKind(series.group)===selection?.kind;
  const found = compatible?wanted.filter(id=>Object.hasOwn(group.entities,id)):[];
  if(found.length) return found;
  if(series.ids.length) return series.ids.filter(id=>Object.hasOwn(group.entities,id));
  const ids=Object.keys(group.entities);
  return [ids.includes('System')?'System':ids.includes('Total')?'Total':ids[0]].filter(Boolean);
}

function rangeIndex(axis,value,after=false) {
  let low=0,high=axis.length;
  while(low<high){
    const mid=(low+high)>>1;
    if(axis[mid]<value || after&&axis[mid]===value) low=mid+1;
    else high=mid;
  }
  return low;
}
function linkedRange(axis,zoom,intervals=null) {
  if(axis.length<2)return [0,axis.length];
  const [start,end]=zoom.map(timeCoordinate);
  if(!Number.isFinite(start)||!Number.isFinite(end))return [0,axis.length];
  function search(value,edge,after){
    let low=0,high=axis.length;
    while(low<high){
      const mid=(low+high)>>1,v=timeCoordinate(intervals?.[mid]?.[edge]||axis[mid]);
      if(!Number.isFinite(v))return null;
      if(v<value||after&&v===value)low=mid+1;else high=mid;
    }
    return low;
  }
  const left=search(start,'end',false),right=search(end,'start',true);
  if(left===null||right===null)return [0,axis.length];
  if(right-left>=2)return [left,right];
  const boundary=Math.max(0,Math.min(left,axis.length-2));
  return [boundary,boundary+2];
}
function nextCalendar(stamp,period) {
  if(!/^\d{4}-\d{2}/.test(stamp)) return '\uffff';
  const [year,month]=stamp.slice(0,7).split('-').map(Number);
  if(period==='year') return (year+1)+'-01';
  return month===12?(year+1)+'-01':year+'-'+String(month+1).padStart(2,'0');
}
function chartWindow(axis, window, dt=1) {
  if(!axis.length) return [0,0];
  const first=window.start?Math.min(axis.length,rangeIndex(axis,window.start)):0;
  if(window.period==='all') return [0,axis.length];
  if(window.period==='custom') return [first,window.end?Math.max(first,rangeIndex(axis,window.end,true)):axis.length];
  if(window.period==='month'||window.period==='year'){
    const stamp=axis[Math.min(first,axis.length-1)];
    const start=stamp.slice(0,window.period==='month'?7:4);
    return [rangeIndex(axis,start),rangeIndex(axis,nextCalendar(stamp,window.period))];
  }
  const hours={'24h':24,'7d':168,'14d':336}[window.period]||168;
  return [first,Math.min(axis.length,first+Math.max(1,Math.round(hours/(dt>0?dt:1))))];
}
function correspondingHours(axis, reference) {
  const candidates=[], matched=[];
  let j=rangeIndex(reference,axis[0]||'');
  for(let i=0;i<axis.length&&j<reference.length;i++) {
    while(j<reference.length&&reference[j]<axis[i])j++;
    if(reference[j]===axis[i]){candidates.push(i);matched.push(j);j++;}
  }
  return {candidates,matched,excluded:axis.length-matched.length};
}
function comparisonIssue(a,b,field,{sameRun=false}={}) {
  if (!sameRun && (!a.clock || !b.clock || a.clock!==b.clock)) return 'Comparison requires matching recorded study clocks.';
  if (!sameRun && (!(a.dt_hours>0) || a.dt_hours!==b.dt_hours)) return 'Comparison requires equal recorded sample durations.';
  if (chartUnit(field,a)!==chartUnit(field,b)||moneyField(field)&&(!a.currency||!b.currency||a.currency!==b.currency))
    return 'Comparison requires matching units and recorded currency.';
  return '';
}
function resolvedResolution(choice, length) {
  if(choice!=='auto')return choice;
  return length<=336?'hourly':length<=9000?'day':'month';
}

function civilDate(stamp) {
  if(!/^\d{4}-\d{2}-\d{2}/.test(stamp))return null;
  return new Date(stamp.slice(0,10)+'T00:00:00Z');
}
function calendarBucket(stamp, period) {
  const start=civilDate(stamp);
  if(!start||!Number.isFinite(start.getTime()))return [stamp,stamp,null];
  if(period==='week')start.setUTCDate(start.getUTCDate()-(start.getUTCDay()+6)%7);
  if(period==='month'||period==='year')start.setUTCDate(1);
  if(period==='year')start.setUTCMonth(0);
  const end=new Date(start);
  if(period==='week'||period==='day')end.setUTCDate(end.getUTCDate()+(period==='week'?7:1));
  else if(period==='month')end.setUTCMonth(end.getUTCMonth()+1);
  else end.setUTCFullYear(end.getUTCFullYear()+1);
  return [start.toISOString().slice(0,10),end.toISOString().slice(0,10),(end-start)/3600000];
}
function stampMillis(stamp) {
  const text=stamp.replace(' ','T');
  return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(text)?text:text+'Z');
}
function aggregationFor(unit,field,reducer) {
  if(field==='voltage_violation_bus_count'||field==='voltage_violation_max_pu')return 'peak';
  if(/(^|_)(violation|overloaded|converged|feasible|limited|disconnected)$/.test(field))return 'count';
  if(unit==='°')return 'circular';
  if(reducer==='energy'&&['kW','kvar'].includes(unit))return 'energy';
  if(/^(kWh|kvarh)$/.test(unit)||moneyField(field)&&!unit.includes('/'))return 'total';
  if(['peak','minimum','end'].includes(reducer))return reducer;
  if(field==='voltage_min_pu')return 'minimum';
  if(field==='voltage_max_pu')return 'peak';
  return 'mean';
}

function bucketReadings(axis,values,period,reducer,dt,unit,field='',limits=null,durations=null) {
  if(period==='hourly')return {axis,data:values,intervals:null,unit,operation:'Recorded samples'};
  const operation=aggregationFor(unit,field,reducer);
  const outputUnit=operation==='energy'?unit+'h':operation==='count'?'samples':unit;
  const groups=new Map();
  let previous=null;
  const fixed=Number.isFinite(dt)&&dt>0?dt:null;
  for(let i=0;i<axis.length;i++){
    const stamp=axis[i],value=values[i],date=stamp.slice(0,10);
    if(!previous||previous.date!==date)previous={date,key:calendarBucket(stamp,period)};
    const [key,exclusive,nominal]=previous.key;
    if(!groups.has(key))groups.set(key,{key,exclusive,nominal,start:stamp,end:stamp,count:0,missing:0,
      observations:0,knownHours:0,timed:0,powerHours:0,sum:0,min:Infinity,max:-Infinity,
      affected:0,affectedHours:0,sine:0,cosine:0,latest:null});
    const group=groups.get(key),duration=durations?durations[i]:fixed;
    group.end=stamp;
    group.observations++;
    if(!isObservation(value)){group.missing++;continue;}
    group.sum+=value;group.count++;group.latest=value;
    group.max=Math.max(group.max,value);group.min=Math.min(group.min,value);
    const violates=limits&&unit==='pu'&&(/voltage(?:_(?:min|max))?_pu$/.test(field))&&
      (value<limits.minimum||value>limits.maximum);
    if(violates)group.affected++;
    if(Number.isFinite(duration)&&duration>0){
      group.timed++;group.knownHours+=duration;group.powerHours+=value*duration;
      if(violates)group.affectedHours+=duration;
    }
    if(operation==='circular'){
      const radians=value*Math.PI/180;
      group.sine+=Math.sin(radians)*(duration||1);
      group.cosine+=Math.cos(radians)*(duration||1);
    }
  }
  const weighted=Boolean(durations)||Boolean(fixed);
  const label={mean:weighted?'Time-weighted mean':'Sample mean (duration unavailable)',
    circular:'Circular mean',total:'Sum',energy:'Integrated energy',count:'Affected samples',
    minimum:'Minimum',peak:'Maximum',end:'Last recorded value'}[operation];
  const intervals=[],data=[];
  for(const g of groups.values()){
    const first=stampMillis(g.start),last=stampMillis(g.end);
    const expected=fixed&&Number.isFinite(last-first)?Math.round((last-first)/(fixed*3600000))+1:null;
    const gaps=expected==null?0:Math.max(0,expected-g.observations);
    const startCivil=Date.parse(g.start.slice(0,19).replace(' ','T')+'Z');
    const endCivil=Date.parse(g.end.slice(0,19).replace(' ','T')+'Z');
    const partial=fixed&&g.nominal!=null&&Number.isFinite(startCivil+endCivil)?
      startCivil>Date.parse(g.key)||endCivil+fixed*3600000<Date.parse(g.exclusive):null;
    const missing=g.missing+gaps;
    let result=null;
    if(g.count){
      if(operation==='peak')result=g.max;
      else if(operation==='minimum')result=g.min;
      else if(operation==='end')result=g.latest;
      else if(operation==='count')result=g.sum;
      else if(operation==='total')result=missing?null:g.sum;
      else if(operation==='energy')result=missing||g.timed!==g.count?null:g.powerHours;
      else if(operation==='circular')result=Math.hypot(g.sine,g.cosine)<1e-10?null:Math.atan2(g.sine,g.cosine)*180/Math.PI;
      else result=g.timed===g.count?g.powerHours/g.knownHours:weighted?null:g.sum/g.count;
    }
    data.push(result);
    intervals.push({key:g.key,start:g.start,end:g.end,count:g.count,expected,missing,partial,
      validHours:g.timed===g.count&&g.count?g.knownHours:null,minimum:g.count?g.min:null,maximum:g.count?g.max:null,
      violationSamples:limits&&unit==='pu'&&/voltage(?:_(?:min|max))?_pu$/.test(field)?g.affected:null,
      violationHours:limits&&g.timed===g.count&&g.count?g.affectedHours:null});
  }
  return {axis:intervals.map(g=>g.key),data,intervals,unit:outputUnit,operation:label};
}

const additiveStacks = [
  ['load_input_kw','shedding_kw'],['served_load_kwh','shed_kwh'],['pv_input_kw','curtailment_kw'],
  ['pv_generation_kwh','curtailed_kwh'], ['grid_purchase_cost','shedding_cost','curtailment_cost'],
];
function canStack(series) {
  const groups=series.filter(s=>s.visible!==false);
  return groups.length>1&&groups.every(s=>s.style==='bar'&&s.unit===groups[0].unit&&s.axis===groups[0].axis&&
    s.scenario===groups[0].scenario&&s.runKey===groups[0].runKey)&&(
    groups.every(s=>s.category&&s.field===groups[0].field&&s.group===groups[0].group)&&
      new Set(groups.map(s=>s.entity)).size===groups.length ||
    groups.every(s=>s.entity===groups[0].entity)&&new Set(groups.map(s=>s.field)).size===groups.length&&
      additiveStacks.some(fields=>groups.every(s=>fields.includes(s.field))));
}

