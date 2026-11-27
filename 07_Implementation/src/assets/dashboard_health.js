/* Whole-period network views and compact study comparisons. */
const healthColors={
  clear:['#258168','No recorded violations'],
  some:['#b66b16','Some violations'],
  frequent:['#ab3b42','Frequent violations (≥5% of valid coverage)'],
  unknown:['#7d8995','Insufficient data or unrated line'],
};
const readingHours=stat=>stat?.samples&&stat.timed===stat.samples?stat.hours:null;
function feederHealthClass(stats, expected) {
  if(!stats?.samples)return 'unknown';
  const share=stats.timed_samples===stats.samples&&stats.observed_hours>0?
    stats.affected_hours/stats.observed_hours:stats.affected/stats.samples;
  if(share>=.05)return 'frequent';
  if(share>0)return 'some';
  return stats.samples<expected?'unknown':'clear';
}
function healthPercentage(stats){
  if(!stats?.samples)return null;
  if(stats.timed_samples!==stats.samples||!stats.observed_hours)return 100*stats.affected/stats.samples;
  return 100*stats.affected_hours/stats.observed_hours;
}
function violationHours(stats){
  return stats?.samples&&stats.timed_samples===stats.samples?stats.affected_hours:null;
}
function hasInstalledBess(ctx){
  if(!ctx||ctx.scenario==='no_bess')return false;
  const meta=ctx.archive.metadata||{};
  if(ctx.scenario==='best_bess'&&meta.optimizer?.no_bess_selected===true)return false;
  return ctx.data.has_bess===true || ctx.scenario==='best_bess'&&Boolean(meta.optimizer?.fleet?.length) ||
    Boolean(meta.context?.['Manual BESS Fleet']?.length||meta.context?.['Manual BESS']?.power_rating_kw>0);
}
const peekHealth=async ctx=>ctx.gallery.health==null?null:readings(ctx)(ctx.gallery.health);

function navigateHealth(){
  workspace.state.healthMode='overall';
  screen='Network';
  tabs();refreshWorkspace();
}
function appendHealthStatus(root,health,ctx){
  const bucket=asMetrics(ctx.data);
  if(!health){
    root.append(elem('p','Whole-study feeder health is unavailable for this report. Snapshot and recorded totals remain available.','fine'));
    return;
  }
  const buses=Object.values(health.bus),lines=Object.values(health.line);
  const busCount=buses.filter(row=>row.violation?.affected>0).length;
  const preCount=buses.filter(row=>row.pre_violation?.affected>0).length;
  const overloads=lines.filter(row=>row.overload?.affected>0).length;
  const rated=lines.filter(row=>row.overload?.samples>0).length;
  const minimum=Object.entries(health.bus).filter(([,r])=>r.voltage_pu?.samples)
    .reduce((a,b)=>!a||b[1].voltage_pu.min<a[1].voltage_pu.min?b:a,null);
  const peak=Object.entries(health.line).filter(([,r])=>r.loading_percent?.samples)
    .reduce((a,b)=>!a||b[1].loading_percent.max>a[1].loading_percent.max?b:a,null);
  const both=buses.some(row=>row.violation?.samples);
  const pre=buses.some(row=>row.pre_violation?.samples);
  const durationKnown=health.converged+health.failed>0;
  grid(root,['Whole-study status','Recorded value'],[
    ['Converged / attempted samples',durationKnown?fmt(health.converged)+' / '+fmt(health.samples):'Not recorded'],
    ['Failed samples',durationKnown?health.failed:null],['Expected samples',health.expected],
    ['Buses outside limits after control',both?busCount:null],
    ['Hours with a recorded final voltage violation',both?
      (health.affected_hours?.violation??(busCount===0?0:null)):null],
    ['Buses outside limits before control',pre?preCount:null],
    ['Lines over rated ampacity',rated?fmt(overloads)+' of '+fmt(rated)+' with thermal readings':null],
    ['Hours with a recorded rated-line overload',rated?
      (health.affected_hours?.overload??(overloads===0?0:null)):null],
    ['Thermal assessment of unrated/missing lines',lines.length>rated?fmt(lines.length-rated)+' unavailable':'All recorded lines assessed'],
    ['Worst final voltage',minimum?'Bus '+minimum[0]+' · '+fmt(minimum[1].voltage_pu.min)+' pu':null],
    ['Highest rated line loading',peak?peak[0]+' · '+fmt(peak[1].loading_percent.max)+' %':null],
    ['Load shedding',workspaceNumber(bucket.load_shedding_energy_kwh,'kWh')],
    ['PV curtailment',workspaceNumber(bucket.curtailment_energy_kwh,'kWh')],
    ['Active network losses',workspaceNumber(bucket.loss_energy_kwh,'kWh')],
  ]);
}

function healthInspector(root,health,kind,id,axis,ctx){
  root.replaceChildren();
  const entity=health[kind]?.[id];
  const title=elem('h3',kind==='bus'?'Bus '+id:id);
  root.append(title);
  if(!entity){root.append(elem('p','No recorded measurements for this element.','empty'));return;}
  const voltage=entity.voltage_pu,preVoltage=entity.pre_voltage_pu,current=entity.current_a;
  const coverage=ctx.archive.manifest.clock||'Clock not recorded';
  root.append(elem('p',health.first+' → '+health.last+' · '+coverage,'fine'));
  const metric=(label,value,unit)=>[label,workspaceNumber(value,unit)];
  const info=[['Attempted / study samples',fmt(entity.attempted)+' / '+fmt(health.samples)]];
  if(kind==='bus'){
    info.push(['Valid final voltage samples',voltage?.samples],
      metric('Valid final voltage hours',readingHours(voltage),'h'),
      metric('Minimum final voltage',voltage?.min,'pu'),metric('Maximum final voltage',voltage?.max,'pu'),
      metric('Mean final voltage ('+(readingHours(voltage)?'time-weighted':'sample mean')+')',
        readingHours(voltage)?voltage.weighted/voltage.hours:voltage?.samples?voltage.sum/voltage.samples:null,'pu'),
      metric('Lowest final margin',entity.margin_pu?.min,'pu'),metric('Highest final margin',entity.margin_pu?.max,'pu'),
      ['Final violation samples / valid checks',entity.violation?fmt(entity.violation.affected)+' / '+fmt(entity.violation.samples):null],
      metric('Final violation hours',violationHours(entity.violation),'h'),
      metric('Final affected share of checked coverage',healthPercentage(entity.violation),'%'),
      ['Valid uncontrolled voltage samples',preVoltage?.samples],
      metric('Minimum uncontrolled voltage',preVoltage?.min,'pu'),metric('Maximum uncontrolled voltage',preVoltage?.max,'pu'),
      metric('Lowest uncontrolled voltage margin',entity.pre_margin_pu?.min,'pu'),
      ['Pre-control violation samples / valid checks',entity.pre_violation?fmt(entity.pre_violation.affected)+' / '+fmt(entity.pre_violation.samples):null],
      metric('Pre-control violation hours',violationHours(entity.pre_violation),'h'),
      metric('Pre-control affected share of checked coverage',healthPercentage(entity.pre_violation),'%'),
      ['Archived before-correction reference',entity.reference_voltage_pu?'Available as a separate control stage':null],
      metric('Minimum archived reference voltage',entity.reference_voltage_pu?.min,'pu'),
      metric('Archived reference violation hours',violationHours(entity.reference_violation),'h'),
      metric('Recorded shedding subtotal',entity.shed_kwh?.sum,'kWh'),['Shedding subtotal samples',entity.shed_kwh?.samples],
      metric('Recorded curtailment subtotal',entity.curtailed_kwh?.sum,'kWh'),['Curtailment subtotal samples',entity.curtailed_kwh?.samples]);
  }else{
    info.push(['Valid current samples',current?.samples],metric('Peak current',current?.max,'A'),
      metric('Valid current hours',readingHours(current),'h'),
      ['Ampacity evidence',entity.rated?'Rating recorded':'Unknown / not rated'],
      metric('Maximum observed utilization',entity.loading_percent?.max,'%'),
      ['Overload samples / valid checks',entity.overload?fmt(entity.overload.affected)+' / '+fmt(entity.overload.samples):null],
      metric('Thermal overload hours',violationHours(entity.overload),'h'),
      metric('Thermal overload share of checked coverage',healthPercentage(entity.overload),'%'),
      metric('Recorded active loss subtotal',entity.loss_kwh?.sum,'kWh'),['Active loss subtotal samples',entity.loss_kwh?.samples],
      metric('Recorded reactive loss subtotal',entity.loss_kvarh?.sum,'kvarh'),['Reactive loss subtotal samples',entity.loss_kvarh?.samples]);
  }
  grid(root,['Recorded measure','Value'],info);
  const tools=elem('div',undefined,'scope-inline');root.append(tools);
  button(tools,'View full-period charts',()=>{
    workspace.state.time={...workspace.state.time,period:'all',zoom:null};
    selectedEntity(kind,id,workspace.state.time.cursor||axis[0],ctx.scenario);
  });
  button(tools,'Inspect selected-hour records',()=>{
    workspace.state.healthMode='snapshot';
    selectedEntity(kind,id,workspace.state.time.cursor||axis[0],ctx.scenario);
  });
  button(tools,'Open decision ledger',()=>{
    galleryState.scenario=ctx.scenario;
    eventFilter.bus=kind==='bus'?String(id):'';
    screen='Decisions';tabs();render();
  });
  button(tools,'Exact health JSON',()=>saveJSON({kind,id,first:health.first,last:health.last,entity},'health_'+safeFilename(id)+'.json'));
}

function overallFeeder(holder,health,ctx,axis){
  const preAvailable=Object.values(health.bus).some(row=>row.pre_violation?.samples);
  const referenceAvailable=Object.values(health.bus).some(row=>row.reference_violation?.samples);
  const phase=workspace.state.healthPhase==='pre'&&preAvailable?'pre':
    workspace.state.healthPhase==='reference'&&referenceAvailable?'reference':'final';
  const field=phase==='pre'?'pre_violation':phase==='reference'?'reference_violation':'violation';
  const expected=health.expected??health.samples;
  const summary=elem('p','Entire recorded study · '+health.first+' → '+health.last+
    ' · '+fmt(health.converged)+' converged / '+fmt(health.samples)+' attempted'+
    (health.expected!=null?' / '+fmt(health.expected)+' expected':''),'fine');
  holder.append(summary);
  const filters=elem('div',undefined,'scope-inline');holder.append(filters);
  selectControl(filters,'Bus condition',[['final','Final after control'],...(preAvailable?[['pre','Uncontrolled before correction']]:[]),
    ...(referenceAvailable?[['reference','Before final correction (archived reference)']]:[])],
    phase,value=>{workspace.state.healthPhase=value;refreshWorkspace();});
  if(!preAvailable)filters.append(elem('span','Pre-control voltages unavailable','fine'));
  const legend=elem('div',undefined,'health-legend');
  for(const [color,label] of Object.values(healthColors)){
    const mark=elem('span',undefined,'health-key');
    const dot=elem('i');dot.style.background=color;mark.append(dot,elem('span',label));legend.append(mark);
  }
  holder.append(legend,elem('p','Line colors use final current against recorded ampacity. Green requires full coverage. A dashed orange outline marks a restored bus with recorded uncontrolled stress.','fine'));
  const symbols={bus:{},line:{}};
  for(const kind of ['bus','line']){
    for(const [id,row] of Object.entries(health[kind])){
      const stats=row[kind==='bus'?field:'overload'];
      const cls=feederHealthClass(stats,expected);
      const [color,label]=healthColors[cls];
      const residual=phase==='final'&&kind==='bus'&&row.pre_violation?.affected>0?
        ' · Before control '+fmt(row.pre_violation.affected)+' affected samples':'';
      symbols[kind][id]={color,label:label+(stats?' · '+fmt(stats.affected)+' / '+fmt(stats.samples)+' checked samples':'')+residual,
        stress:Boolean(residual)&&cls==='clear'};
    }
  }
  const inspector=elem('div',undefined,'health-inspector');
  const select=workspace.state.selection;
  const click=(kind,id)=>{
    workspace.state.selection={kind,ids:[String(id)]};
    workspace.inspected=null;
    refreshWorkspace();
  };
  const nav=elem('div',undefined,'scope-inline');
  for(const kind of ['bus','line']){
    const ids=Object.keys(health[kind]);
    if(ids.length)selectControl(nav,kind==='bus'?'Inspect bus':'Inspect line',[['','Select'],...ids.map(id=>[id,id])],
      select.kind===kind?select.ids[0]:'',id=>{if(id)click(kind,id);});
  }
  holder.append(nav);
  networkMap(holder,ctx.archive.metadata?.topology,{},'health','',click,select,symbols);
  holder.append(inspector);
  if(select.kind&&select.ids[0])healthInspector(inspector,health,select.kind,select.ids[0],axis,ctx);
  else inspector.append(elem('p','Select a bus or line to see its full-period evidence.','fine'));
}


function comparisonMetricRows(before,after,wholeYear,currency,diagnostic=false){
  const definitions=[
    ...(wholeYear&&currency&&!diagnostic&&before.feasible!==false&&after.feasible!==false?
      [['Annual total cost','annual_total_cost',currency+'/year',true]]:[]),
    ['Load shedding','load_shedding_energy_kwh','kWh',true],
    ['PV curtailment','curtailment_energy_kwh','kWh',true],
    ['Grid import','grid_import_energy_kwh','kWh',null],
    ['Network losses','loss_energy_kwh','kWh',true],
    ['Voltage violation time','voltage_violation_hours','h',true],
    ['Served energy','served_load_energy_kwh','kWh',false],
  ];
  return definitions.filter(([,key])=>isObservation(before[key])&&isObservation(after[key]))
    .map(([label,key,unit,lowerBetter])=>({label,unit,lowerBetter:diagnostic?null:lowerBetter,
      before:before[key],after:after[key],delta:after[key]-before[key]}));
}
function signedValue(value,unit){
  return (value>0?'+':'')+workspaceNumber(value,unit);
}
function beforeAfterCards(root,rows,labels=['No BESS','With BESS']){
  const panel=elem('div',undefined,'comparison-bars');
  root.append(panel);
  for(const m of rows){
    const tile=elem('article',undefined,'comparison-metric');
    tile.append(elem('h3',m.label));
    const low=Math.min(0,m.before,m.after),high=Math.max(0,m.before,m.after);
    const span=high-low||1;
    for(const [label,value,kind] of [[labels[0],m.before,'before'],[labels[1],m.after,'after']]){
      const row=elem('div',undefined,'comparison-value');
      row.append(elem('span',label),elem('strong',workspaceNumber(value,m.unit)));
      const track=elem('div',undefined,'comparison-track');
      const bar=elem('i',undefined,kind);
      bar.style.left=(100*(Math.min(0,value)-low)/span)+'%';
      bar.style.width=(100*Math.abs(value)/span)+'%';
      track.setAttribute('aria-hidden','true');
      track.append(bar);row.append(track);tile.append(row);
    }
    const outcome=m.delta===0?'No change':m.lowerBetter===null?'Observed change':
      (m.delta<0)===m.lowerBetter?'Improvement':'Deterioration';
    tile.append(elem('p',outcome+' · Δ '+signedValue(m.delta,m.unit),'fine'));
    panel.append(tile);
  }
}
function completeYear(axis,dt,start,end){
  if(!axis.length||!isObservation(dt)||!(dt>0)||!start||!end)return false;
  const year=axis[0].slice(0,4);
  const startOfYear=year+'-01-01 00:00:00', next=(Number(year)+1)+'-01-01 00:00:00';
  const from=stampMillis(start),until=stampMillis(end);
  return start.replace('T',' ').slice(0,19)===startOfYear&&end.replace('T',' ').slice(0,19)===next&&
    stampMillis(axis[0])===from&&stampMillis(axis.at(-1))+dt*3600000===until&&
    axis.length*dt*3600000===until-from;
}
function continuousCoverage(axis,dt) {
  if(!axis.length||!isObservation(dt)||dt<=0)return false;
  const duration=dt*3600000;
  for(let i=1;i<axis.length;i++){
    const elapsed=stampMillis(axis[i])-stampMillis(axis[i-1]);
    if(!Number.isFinite(elapsed)||Math.abs(elapsed-duration)>.1)return false;
  }
  return Number.isFinite(stampMillis(axis[0]));
}
const summaryElectrical=[
  ['Requested load','requested_load_energy_kwh','kWh'],
  ['Demand applied in the power flow','served_load_energy_kwh','kWh'],
  ['Load shed by control','load_shedding_energy_kwh','kWh'],
  ['Available PV','available_pv_energy_kwh','kWh'],
  ['PV used','pv_generation_energy_kwh','kWh'],
  ['PV curtailed by control','curtailment_energy_kwh','kWh'],
  ['Grid import','grid_import_energy_kwh','kWh'],['Grid export','grid_export_energy_kwh','kWh'],
  ['Network losses','loss_energy_kwh','kWh'],
  ['Reactive network losses','reactive_loss_energy_kvarh','kvarh'],
  ['Service rate','service_rate_percent','%',false],
  ['Minimum raw voltage','raw_minimum_pu','pu',false],['Maximum raw voltage','raw_maximum_pu','pu',false],
  ['Raw voltage violation time','raw_voltage_violation_hours','h'],
  ['Maximum raw voltage violation','raw_maximum_voltage_violation_pu','pu',false],
  ['Minimum final voltage','voltage_min_pu','pu',false],['Maximum final voltage','voltage_max_pu','pu',false],
  ['Final voltage violation time','voltage_violation_hours','h'],
  ['Share of study hours with final voltage violations','voltage_violation_percent','%',false],
  ['Maximum final voltage violation','final_maximum_voltage_violation_pu','pu',false],
  ['Voltage violations across buses','voltage_violation_bus_hours','bus-hours'],
  ['Line overload time (rated lines)','overload_hours','h'],
  ['Grid import limit violation time','import_violation_hours','h'],
  ['Grid export limit violation time','export_violation_hours','h'],
  ['Expected coverage','expected_hours','h'],['Hours processed','processed_hours','h'],
  ['Hours converged','converged_hours','h'],['Unsolved hours','failed_hours','h'],
  ['Feasibility','feasible','',false],
];

function numericSummary(ctx){
  const data=ctx.data, evidence=data.comparison||{}, descriptor=data.descriptor||{};
  const record={...asMetrics(data),...evidence};
  record.feasible=descriptor.feasible??record.feasible;
  if(isObservation(record.served_load_energy_kwh)&&record.requested_load_energy_kwh>0)
    record.service_rate_percent=100*record.served_load_energy_kwh/record.requested_load_energy_kwh;
  record.voltage_violation_hours??=evidence.final_voltage_violation_hours;
  if(isObservation(record.voltage_violation_hours)&&record.duration_hours>0)
    record.voltage_violation_percent=100*record.voltage_violation_hours/record.duration_hours;
  record.processed_hours??=data.hour_count;
  if(data.diagnostic?.known_status&&isObservation(data.diagnostic.nonconverged)){
    record.failed_hours??=data.diagnostic.nonconverged;
    record.converged_hours??=data.hour_count-record.failed_hours;
  }
  return record;
}
function summaryRows(definitions,a,b,comparable){
  return definitions.map(([label,key,unit,relative=true])=>{
    const first=a[key],second=b?.[key];
    const delta=comparable&&isObservation(first)&&isObservation(second)?second-first:null;
    const change=relative&&delta!==null&&first!==0?100*delta/first:null;
    return {label,key,unit,first,second,delta,change};
  }).filter(row=>row.first!=null||row.second!=null);
}
function numericTable(root,title,definitions,a,b,scenarios,comparable){
  const rows=summaryRows(definitions,a,b,comparable),[first,second]=scenarios;
  if(!rows.length)return;
  const holder=section(root,title);
  const label=value=>typeof value==='boolean'?statusLabel(value):isObservation(value)?fmt(value):'Not recorded';
  const head=['Metric','Unit',first.data.label,...(second?[second.data.label,'Δ (B − A)','Change (%)']:[])];
  grid(holder,head,rows.map(row=>[row.label,row.unit||'—',label(row.first),...(second?
    [label(row.second),row.delta==null?'N/A':signedValue(row.delta,''),row.change==null?'N/A':signedValue(row.change,'%')]:[])]));
  const controls=elem('div',undefined,'summary-actions');
  button(controls,'Download CSV',()=>saveRows(
    ['Metric','Unit',first.data.label+' ['+first.scenario+']',...(second?
      [second.data.label+' ['+second.scenario+']','Delta B - A','Change (%)']:[])],
    rows.map(row=>[row.label,row.unit,row.first,...(second?[row.second,row.delta,row.change]:[])]),
    title.toLowerCase().replace(/[^a-z]+/g,'_')+'.csv'));
  holder.append(controls);
}
function summaryEconomics(currency,annual){
  const period=[
    ['Grid purchases','study_grid_purchase_cost'],['Grid export credit','study_grid_export_credit'],
    ['Modeled load shedding penalty','study_shedding_cost'],['Modeled PV curtailment penalty','study_curtailment_cost'],
    ['Study-period operating cost','study_operating_cost'],
  ];
  const year=[
    ['Grid purchases','annual_grid_purchases'],['Grid export credit','annual_export_credit'],
    ['Net grid cost','annual_grid_cost'],['Modeled load shedding penalty','annual_shedding_cost'],
    ['Modeled PV curtailment penalty','annual_curtailment_cost'],
    ['Terminal inventory adjustment','annual_terminal_inventory_adjustment'],
    ['Operating cost','annual_operating_cost'],['Capital recovery','annual_bess_capital_cost'],
    ['Operations and maintenance','annual_bess_om_cost'],['BESS ownership cost','annualized_bess_cost'],
    ['Feasible annual total cost','annual_total_cost'],
  ];
  return [...(annual?year:period).map(([label,key])=>[label,key,currency+(annual?'/year':'')]),
    ['One-time BESS investment','bess_cost',currency]];
}
function selectedSummaryScenarios(ctx){
  const options=ctx.archive.scenarios, saved=workspace.summaryPair;
  if(saved&&Object.hasOwn(options,saved[0]))return [chartContext('current',saved[0]),
    saved[1]&&saved[0]!==saved[1]&&Object.hasOwn(options,saved[1])?chartContext('current',saved[1]):null];
  if(options.uncontrolled&&options.controlled)return [chartContext('current','uncontrolled'),chartContext('current','controlled')];
  const best=options.best_bess?chartContext('current','best_bess'):null;
  if(options.no_bess&&hasInstalledBess(best))return [chartContext('current','no_bess'),best];
  return [ctx,null];
}
function isUncontrolled(ctx){return ctx?.data?.descriptor?.control_mode==='uncontrolled'||ctx?.scenario==='uncontrolled';}
async function renderSummaryComparison(root,first,second){
  const [axis,other]=await Promise.all([timeline(first),second?timeline(second):null]);
  if(!root.isConnected)return;
  const manifest=first.archive.manifest,dt=manifest.dt_hours,interval=manifest.interval||{};
  const a=numericSummary(first),b=second?numericSummary(second):null;
  const verified=(record,timestamps)=>record.converged_hours===timestamps.length&&
    (record.expected_hours==null||record.expected_hours===timestamps.length);
  const same=Boolean(second&&axis.length===other.length&&axis.every((stamp,i)=>stamp===other[i])&&
    continuousCoverage(axis,dt)&&verified(a,axis)&&verified(b,other));
  const annual=completeYear(axis,dt,interval.start,interval.end_exclusive)||
    [8760,8784].includes(a.duration_hours)&&isObservation(a.annual_operating_cost);
  const control=isUncontrolled(first)||isUncontrolled(second);
  if(second){
    const pair=section(root,control?'Corrective-action comparison':'Scenario comparison');
    if(same){
      const rows=comparisonMetricRows(a,b,annual,manifest.currency,control||a.feasible===false||b.feasible===false);
      if(rows.length)beforeAfterCards(pair,rows,[first.data.label,second.data.label]);
      pair.append(elem('p',fmt(axis.length)+' matching hourly samples. The comparison uses the entire recorded period.','fine'));
    }else pair.append(elem('p','The scenarios lack equal, complete, converged coverage. Values are shown separately.','fine'));
  }
  if(control)root.append(elem('p','Uncontrolled FBS uses prescribed load and PV with installed batteries idle. Zero automatic shedding does not establish feasible service. Operating costs for this scenario are diagnostic.','treatment'));
  numericTable(root,'Energy, voltage and coverage',summaryElectrical,a,b,[first,second],same);
  if(manifest.currency){
    const costs=section(root,annual?'Annual economics':'Study-period economics');
    if(a.feasible===false||isUncontrolled(first))a.annual_total_cost=null;
    if(b&&(b.feasible===false||isUncontrolled(second)))b.annual_total_cost=null;
    numericTable(costs,'Recorded costs',summaryEconomics(manifest.currency,annual),a,b,[first,second],same);
    costs.append(elem('p','Tariff purchases and export credits are shown separately from modeled penalties. See Model & Assumptions for the recorded inputs and formulas.','fine'));
  }
  await renderSummaryFleet(root,[first,second].filter(Boolean));
  renderSummaryVerification(root,first.archive);
}
function manualUnits(metadata){
  const context=metadata.context||{};
  return context['Manual BESS Fleet']||(context['Manual BESS']?[context['Manual BESS']]:[]);
}
function summaryFleet(ctx){
  if(!hasInstalledBess(ctx))return [];
  const meta=ctx.archive.metadata||{},opt=meta.optimizer||{};
  const installed=ctx.data.descriptor?.installed_fleet;
  const manual=manualUnits(meta);
  return installed?.length?installed:manual.length?manual:opt.fleet?.length?opt.fleet:
    opt.best_bess_candidate?[opt.best_bess_candidate]:[];
}
async function renderSummaryFleet(root,scenarios){
  const holder=section(root,'Battery installations');
  for(const ctx of scenarios){
    const units=summaryFleet(ctx),meta=ctx.archive.metadata||{};
    holder.append(elem('h3',ctx.data.label));
    if(!units.length){
      holder.append(elem('p',hasInstalledBess(ctx)?'Battery ratings were not archived.':'No battery installation recorded.','fine'));
      continue;
    }
    const manual=manualUnits(meta).length>0;
    const ratio=meta.context?.['Effective inverter sizing (kVA/kW)']??meta.optimizer?.inverter_kva_per_kw??
      meta.context?.['Economic inputs']?.inverter_kva_per_kw;
    const last=ctx.data.hour_count;
    const group=ctx.gallery.groups.battery, audit=ctx.gallery.groups['battery daily audit'];
    const rows=await Promise.all(units.map(async(unit,index)=>{
      const bus=String(unit.bus_id),p=unit.power_rating_kw,e=unit.energy_capacity_kwh;
      const kva=unit.inverter_rating_kva??(isObservation(p)&&isObservation(ratio)?p*ratio:null);
      let soc=null,energy=null,restored=null;
      if(last&&group?.entities[bus]){
        [soc]=await sampleValues(ctx,{group:'battery',field:'soc_after'},bus,last-1,last);
        [energy]=await sampleValues(ctx,{group:'battery',field:'energy_after_kwh'},bus,last-1,last);
      }else if(last&&ctx.gallery.groups.bus?.fields.includes('bess_soc_percent')){
        const [value]=await sampleValues(ctx,{group:'bus',field:'bess_soc_percent'},bus,last-1,last);
        if(isObservation(value))soc=value/100;
      }
      if(last&&audit?.entities[bus]&&audit.fields.includes('soc_restored')){
        const values=await sampleValues(ctx,{group:'battery daily audit',field:'soc_restored'},bus,0,last);
        const recorded=values.filter(isObservation);
        if(recorded.length)restored=recorded.filter(value=>value===1).length+' / '+recorded.length;
      }
      const initial=unit.soc_initial??meta.context?.['Fleet battery parameters']?.soc_initial;
      const difference=isObservation(initial)&&isObservation(e)&&isObservation(energy)?energy-initial*e:null;
      return [index+1,'Bus '+bus,p,e,kva,isObservation(p)&&p>0&&isObservation(e)?e/p:null,
        isObservation(soc)?soc*100:null,difference,restored];
    }));
    if(!holder.isConnected)return;
    holder.append(elem('p',(manual?'Manual fleet':'Optimized fleet')+(isUncontrolled(ctx)?' · Idle by study policy':''),'fine'));
    const sum=column=>rows.every(row=>isObservation(row[column]))?rows.reduce((total,row)=>total+row[column],0):null;
    rows.push(['Total','',sum(2),sum(3),sum(4),null,null,sum(7),null]);
    grid(holder,['Unit','Bus','kW','kWh','kVA','Duration (h)','Final SOC (%)','Terminal Δ (kWh)','SOC audit passed'],
      rows.map(row=>row.map(value=>isObservation(value)?fmt(value):value??'—')));
  }
}
function renderSummaryVerification(root,archive){
  const opt=archive.metadata?.optimizer||{}, stages=opt.stages||[], duration=opt.bess_duration_constraint;
  if(!stages.length&&!archive.ranked?.length&&!duration)return;
  const detail=elem('details',undefined,'summary-verification');
  detail.append(elem('summary','Battery sizing and optimization verification'));
  root.append(detail);
  if(duration)grid(detail,['Sizing constraint','Value'],[
    ['Minimum duration',workspaceNumber(duration.minimum_hours,'h')],
    ['Maximum duration',workspaceNumber(duration.maximum_hours,'h')],
    ['Feasible power/energy pairs per bus',fmt(duration.feasible_pairs_per_bus)],
  ]);
  const year=archive.manifest.currency?archive.manifest.currency+'/year':'';
  const checks=stages.flatMap(stage=>(stage.full_year_candidates||[]).map(row=>[
    stage.index,(row.fleet||[]).map(unit=>'Bus '+unit.bus_id).join(', ')||(row.bus==null?'—':'Bus '+row.bus),
    row.annual_processed_hours==null?'—':fmt(row.annual_processed_hours)+' / '+fmt(row.annual_expected_hours),
    row.verification_status||row.technical_reason||statusLabel(row.feasible),
    workspaceNumber(row.annual_cost,year),
  ]));
  if(checks.length)grid(detail,['Stage','Fleet / bus','Chronological hours','Decision','Annual cost'],checks);
  if(archive.ranked?.length)grid(detail,['Ranked candidate','Power (kW)','Energy (kWh)','Recorded annual cost'],
    archive.ranked.map(row=>['Bus '+row.bus_id,fmt(row.power_rating_kw),fmt(row.energy_capacity_kwh),workspaceNumber(row.annual_cost,year)]));
}
function consumptionLabel(report,id){return id==='Total'?'Total':report.labels[id]||'Unclassified';}
function selectConsumptionBuses(report,{category='',query='',sort='bus'}={}){
  const term=query.trim().toLowerCase();
  const key=row=>consumptionLabel(report,row.category);
  const byBus=(a,b)=>a.id.localeCompare(b.id,undefined,{numeric:true});
  return report.buses.filter(row=>(!category||row.category===category)&&
      ('Bus '+row.id+' '+key(row)).toLowerCase().includes(term)).sort((a,b)=>{
    if(sort==='consumption')return (b.served_kwh??-Infinity)-(a.served_kwh??-Infinity)||byBus(a,b);
    if(sort==='category')return key(a).localeCompare(key(b))||byBus(a,b);
    return byBus(a,b);
  });
}
const consumptionMeasures=[
  ['requested_kwh','Requested (MWh)',.001],['served_kwh','Served (MWh)',.001],
  ['shed_kwh','Shed (MWh)',.001],['share_percent','Requested share (%)',1],
  ['peak_kw','Peak requested (kW)',1],['tariff_estimate','Estimated cost',1],
];
function consumptionBasis(sc){
  return sc.archive.manifest.source==='forecast'?'Forecast input profiles':
    sc.archive.manifest.source==='historical'?'Historical input profiles':'Archived input profiles';
}
function consumptionCsv(report,sc,rows,buses){
  const label=(row)=>consumptionLabel(report,buses?row.category:row.id);
  const head=[...(buses?['Bus ID','Category']:['Category','Demand buses']),
    ...consumptionMeasures.map(([,name])=>name==='Estimated cost'&&sc.archive.manifest.currency?
      name+' ('+sc.archive.manifest.currency+')':name),...(buses?['Recorded shedding penalty']:[]),
    'Scenario ID','Scenario','First retained timestamp','Last retained timestamp','Clock','Input basis',
    'Cost basis','Study import tariff per kWh','Expected samples','Requested energy samples','Served energy samples',
    'Shed energy samples','Requested power samples'];
  const values=rows.map(row=>[...(buses?[row.id,label(row)]:[label(row),row.bus_count]),
    ...consumptionMeasures.map(([key,,factor])=>isObservation(row[key])?row[key]*factor:null),
    ...(buses?[row.shedding_penalty]:[]),sc.scenario,sc.data.label,report.start,report.last,sc.archive.manifest.clock,
    consumptionBasis(sc),report.tariff!=null?'Illustrative study grid-import tariff × served energy':'Unavailable',report.tariff,report.expected,
    ...['requested_kwh','served_kwh','shed_kwh','peak_kw'].map(key=>row.coverage[key]??0)]);
  return [head,values];
}
async function renderLoadConsumption(holder,scenarios){
  const reports=await Promise.all(scenarios.map(async sc=>[sc,sc.gallery.consumption==null?null:await readings(sc)(sc.gallery.consumption)]));
  if(!holder.isConnected)return;
  const controls=elem('div',undefined,'controls summary-actions'),body=elem('div');
  holder.append(controls,body);
  if(reports.length>1)selectControl(controls,'Consumption scenario',reports.map(([sc])=>[sc.scenario,sc.data.label]),
    reports.at(-1)[0].scenario,id=>paint(reports.find(([sc])=>sc.scenario===id)));
  function paint([sc,report]){
    body.replaceChildren();
    body.append(elem('p',sc.data.label+' · Entire study','muted'));
    if(!report){
      body.append(elem('p','Bus consumption totals are unavailable for this scenario. Regenerate from saved hourly bus results if available.','fine'));return;
    }
    body.append(elem('p',[report.start+' through '+report.last,sc.archive.manifest.clock,
      consumptionBasis(sc),
      fmt(report.expected)+' expected samples'].filter(Boolean).join(' · '),'fine'));
    body.append(elem('p',report.tariff!=null?
      'Estimated cost applies the study grid-import tariff to served energy. This is an illustrative estimate of spending, separate from the system cost ledger.':
      'Estimated cost is unavailable because no valid grid-import tariff was recorded.','fine'));
    if(isUncontrolled(sc))body.append(elem('p','Served energy here describes the demand applied in the uncontrolled power flow. Infeasible readings are diagnostic.','fine'));
    const incomplete=[...report.categories,...report.buses].some(row=>
      ['requested_kwh','served_kwh','shed_kwh','peak_kw'].some(key=>row.coverage[key]!==report.expected));
    if(incomplete)body.append(elem('p','Some quantities have incomplete coverage. Full-period values are N/A where readings are missing. Coverage counts are included in the CSV.','fine'));
    const headers=consumptionMeasures.map(([,name])=>name==='Estimated cost'&&sc.archive.manifest.currency?
      name+' ('+sc.archive.manifest.currency+')':name);
    const measurements=row=>consumptionMeasures.map(([key,,factor])=>isObservation(row[key])?row[key]*factor:'N/A');
    const cats=report.categories.slice().sort((a,b)=>Number(a.id==='Total')-Number(b.id==='Total')||
      consumptionLabel(report,a.id).localeCompare(consumptionLabel(report,b.id)));
    body.append(elem('h3','By load profile category'));
    grid(body,['Category','Demand buses',...headers],
      cats.map(row=>[consumptionLabel(report,row.id),row.bus_count,...measurements(row)]));
    const categoryTools=elem('div',undefined,'summary-actions');
    button(categoryTools,'Download category CSV',()=>{
      const [head,rows]=consumptionCsv(report,sc,cats,false);saveRows(head,rows,'category_consumption.csv');
    });body.append(categoryTools);
    const detail=elem('details',undefined,'summary-verification');
    detail.append(elem('summary','Individual bus consumption'));
    body.append(detail);
    const filters=elem('div',undefined,'controls summary-actions'),table=elem('div');
    detail.append(filters,table);
    const filter={category:'',query:'',sort:'bus'};
    const classes=[...new Set(report.buses.map(row=>row.category))]
      .sort((a,b)=>consumptionLabel(report,a).localeCompare(consumptionLabel(report,b)));
    selectControl(filters,'Profile category',[['','All categories'],...classes.map(id=>[id,consumptionLabel(report,id)])],
      '',id=>{filter.category=id;showBuses();});
    selectControl(filters,'Sort by',[['bus','Bus ID'],['category','Category'],['consumption','Served energy (highest first)']],
      filter.sort,sort=>{filter.sort=sort;showBuses();});
    const search=elem('input');search.type='search';search.placeholder='Find a bus or category';
    search.setAttribute('aria-label','Find a bus or category');filters.append(search);
    search.oninput=()=>{filter.query=search.value;showBuses();};
    button(filters,'Download bus CSV',()=>{
      const [head,rows]=consumptionCsv(report,sc,selectConsumptionBuses(report,filter),true);saveRows(head,rows,'bus_consumption.csv');
    });
    function showBuses(){
      const rows=selectConsumptionBuses(report,filter);
      table.replaceChildren();
      if(!rows.length){table.append(elem('p','No recorded demand buses match this filter.','fine'));return;}
      grid(table,['Bus','Category',...headers,'Shed penalty'+(sc.archive.manifest.currency?' ('+sc.archive.manifest.currency+')':'')],
        rows.map(row=>[row.id,consumptionLabel(report,row.category),...measurements(row),row.shedding_penalty??'N/A']),{
          renderCell(cell,id,column){
            if(column!==0)return false;
            button(cell,'Bus '+id,()=>{
              workspace.primary=sc.scenario;workspace.state.scenario=sc.scenario;
              workspace.state.time.cursor=report.last;screen='Network';tabs();
              selectedEntity('bus',id,report.last,sc.scenario);
            });
            return true;
          },
        });
    }
    showBuses();
  }
  paint(reports.at(-1));
}
function renderStudySummary(root,ctx){
  const [first,second]=selectedSummaryScenarios(ctx);
  ctx=second||first;
  const manifest=ctx.archive.manifest,meta=ctx.archive.metadata||{},m=asMetrics(ctx.data);
  const interval=manifest.interval||{};
  const summary=section(root,meta.context?.Network||manifest.folder||'Saved study');
  const topology=meta.topology;
  if(manifest.kind==='base case'||meta.static){
    const snapshot=meta.static||ctx.data.first||{};
    academicTable(summary,'Instantaneous electrical result',['Measurement','Value','Unit'],[
      ['Converged',snapshot.converged,''],
      ['Minimum voltage',snapshot.voltage_min_pu,'pu'],['Maximum voltage',snapshot.voltage_max_pu,'pu'],
      ['Slack active power',snapshot.slack_p_kw,'kW'],['Slack reactive power',snapshot.slack_q_kvar,'kvar'],
      ['Active network loss',snapshot.loss_p_kw,'kW'],['FBS iterations',snapshot.fbs_iterations,''],
    ],ctx,{open:true,note:'Static workbook base case.'});
    button(summary,'Inspect bus voltage and feeder',()=>{screen='Network';tabs();render();});
    return;
  }
  const start=interval.start??ctx.data.first?.timestamp;
  const end=interval.end_exclusive??interval.last;
  const coverage=[start&&String(start),end&&(String(end)+(interval.end_exclusive?' (exclusive)':' (last reading)')),
    manifest.clock].filter(Boolean);
  if(coverage.length)summary.append(elem('p',coverage.join(' · '),'muted'));
  const source=[manifest.source,meta.context?.['Workbook provenance']].filter(v=>typeof v==='string');
  if(source.length)summary.append(elem('p',source.join(' · '),'fine'));
  const entries=Object.entries(ctx.archive.scenarios);
  if(entries.length>1){
    const controls=elem('div',undefined,'controls summary-actions');
    const choices=entries.map(([key,data])=>[key,data.label]);
    selectControl(controls,'Scenario A',choices,first.scenario,key=>{
      workspace.summaryPair=[key,second?.scenario===key?'':second?.scenario||''];refreshWorkspace();
    });
    selectControl(controls,'Scenario B',[['','Single scenario'],...choices.filter(([key])=>key!==first.scenario)],
      second?.scenario||'',key=>{workspace.summaryPair=[first.scenario,key];refreshWorkspace();});
    summary.append(controls);
  }
  const stats=[
    ['Scenario',ctx.data.label],['Network',topology?fmt(topology.buses?.length)+' buses · '+fmt(topology.lines?.length)+' lines':'Topology not recorded'],
    ['Recorded duration',workspaceNumber(m.duration_hours,'h')],['Feasibility',statusLabel(m.feasible)],
    ['Minimum voltage',workspaceNumber(m.voltage_min_pu,'pu')],['Load shedding',workspaceNumber(m.load_shedding_energy_kwh,'kWh')],
    ['Grid import',workspaceNumber(m.grid_import_energy_kwh,'kWh')],['Network losses',workspaceNumber(m.loss_energy_kwh,'kWh')],
  ];
  if(ctx.data.descriptor?.control_mode)stats.push(['Corrective actions',isUncontrolled(ctx)?'Disabled':'Enabled']);
  if(!isUncontrolled(ctx)&&m.feasible!==false&&isObservation(m.annual_total_cost)&&
    isObservation(m.duration_hours)&&[8760,8784].includes(m.duration_hours)&&manifest.currency)
    stats.push(['Annual total cost',workspaceNumber(m.annual_total_cost,manifest.currency+'/year')]);
  if(meta.optimizer?.experimental_enabled)stats.push(['Optimizer','Experimental Joint GA · max '+fmt(meta.optimizer.requested_max_units)]);
  if(hasInstalledBess(ctx)){
    const units=manualUnits(meta).length?manualUnits(meta):meta.optimizer?.fleet||[];
    if(units.length)stats.push(['Installed BESS',fmt(units.length)+' · '+
      workspaceNumber(units.reduce((total,unit)=>total+unit.power_rating_kw,0),'kW')+' · '+
      workspaceNumber(units.reduce((total,unit)=>total+unit.energy_capacity_kwh,0),'kWh')]);
    if(isObservation(m.bess_cost))stats.push(['Initial BESS investment',workspaceNumber(m.bess_cost,manifest.currency)]);
    const recorded=m.bess_soc_min;
    if(isObservation(recorded))stats.push(['Minimum recorded SOC',workspaceNumber(recorded*100,'%')]);}
  cards(summary,stats);
  const comparisons=elem('div');
  root.append(comparisons);
  void renderSummaryComparison(comparisons,first,second).catch(error=>{
    if(comparisons.isConnected)comparisons.append(elem('p',error.message,'warning'));
  });
  if(manifest.kind!=='base case'){
    const consumption=section(root,'Load profile and electricity consumption');
    void renderLoadConsumption(consumption,[first,second].filter(Boolean)).catch(error=>{
      if(consumption.isConnected)consumption.append(elem('p',error.message,'warning'));
    });
  }
  const health=section(root,'Network condition');
  button(health,'Inspect whole-study feeder health',()=>{
    workspace.primary=ctx.scenario;workspace.state.scenario=ctx.scenario;navigateHealth();
  });
  if(ctx.gallery.health!=null)void peekHealth(ctx).then(info=>{
    if(health.isConnected)appendHealthStatus(health,info,ctx);
  }).catch(error=>{if(health.isConnected)health.append(elem('p',error.message,'warning'));});
  else health.append(elem('p','Whole-study electrical health was not recorded in this report.','fine'));
}


