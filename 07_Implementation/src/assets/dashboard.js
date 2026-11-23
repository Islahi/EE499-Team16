'use strict';
// Offline-only dashboard. Canonical CSVs and detailed event logs remain in the saved session.
const $=id=>document.getElementById(id);
const palette=['#167c80','#d17645','#445e99','#96649a'];
const fmt=(value,digits=2)=>typeof value==='number'&&Number.isFinite(value)?
  new Intl.NumberFormat('en-US',{maximumFractionDigits:digits}).format(value):'Unavailable';
const money=value=>typeof value==='number'&&Number.isFinite(value)?'$'+fmt(value,0):'Unavailable';
const energy=value=>typeof value==='number'&&Number.isFinite(value)?fmt(value/1000,2)+' MWh':'Unavailable';
function elem(tag,content,cls){const x=document.createElement(tag);if(content!==undefined)x.textContent=content;if(cls)x.className=cls;return x;}
function section(root,title){const s=elem('section');s.append(elem('h2',title));root.append(s);return s;}
function cards(root,items){const grid=elem('div',undefined,'grid');for(const [name,value] of items){const tile=elem('div',undefined,'tile');tile.append(elem('span',name,'label'),elem('strong',value));grid.append(tile);}root.append(grid);}
function grid(root,head,rows){const wrap=elem('div',undefined,'tablebox');const table=elem('table');const tr=table.createTHead().insertRow();head.forEach(h=>tr.append(elem('th',h)));const body=table.createTBody();rows.forEach(row=>{const r=body.insertRow();row.forEach(value=>r.append(elem('td',value==null?'—':String(value))));});wrap.append(table);root.append(wrap);}
const asMetrics=sc=>Object.fromEntries((sc?.metrics||[]).map(row=>[row.metric,row.value]));
async function inflate(value){const raw=atob(value.trim());const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));const data=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));return new Response(data).json();}
let run,screen='Summary',scenario='best_bess';
const cache=new Map();
let cachedBytes=0;
async function block(id){
  if(id==null)return null;
  if(cache.has(id))return cache.get(id).data;
  const el=$('report-block-'+id);if(!el)throw Error('Missing report block '+id);
  const size=Number(el.dataset.bytes)||0,data=await inflate(el.textContent);
  if(size<=16*1024*1024&&!cache.has(id)){
    while(cache.size&&(cache.size>=64||cachedBytes+size>16*1024*1024)){
      const oldest=cache.keys().next().value;cachedBytes-=cache.get(oldest).size;cache.delete(oldest);
    }
    cache.set(id,{data,size});cachedBytes+=size;
  }
  return data;
}
const sc=key=>run.scenarios[key]||null;
const selected=()=>sc(scenario)||Object.values(run.scenarios)[0];
async function hourWindow(s, first, end){
  if(!s.hour_windows?.length)return (s.hours_block!=null?await block(s.hours_block):s.hours||[]).slice(first,end);
  const rows=[];
  for(const [i,id] of s.hour_windows){
    if(i>=end)break;
    if(i+168>first)rows.push(...(await block(id)).slice(Math.max(0,first-i),end-i));
  }
  return rows;
}
function plot(parent,title,series,labels){
  const unit=title.match(/\(([^()]*)\)$/)?.[1] || (title.includes('voltage')?'pu':'');
  return interactiveChart(parent,title,labels,series.map(s=>({label:s.name,data:s.data})),unit);
}
function statusLabel(value){return value===true?'Feasible':value===false?'Infeasible':'Not recorded';}
function summary(){const root=$('content');const b=asMetrics(sc('no_bess')),c=asMetrics(sc('best_bess')),a=asMetrics(selected());const opt=run.metadata.optimizer||{};
  const economics=run.metadata.context?.['Economic inputs']||{};
  const manual=run.metadata.context?.['Manual BESS'];
  const runLabel=manual?'Manual BESS':run.manifest.kind==='optimization'?'Joint BESS optimization':selected()?.label||run.manifest.kind;
  const ratio=opt.inverter_kva_per_kw??economics.inverter_kva_per_kw??1;
  const block=section(root,'Study and installed batteries');const fleet=manual?[manual]:opt.fleet||[];const candidate=opt.best_bess_candidate;cards(block,[['Network',run.metadata.topology?.buses?.length?run.metadata.topology.buses.length+' buses':'Recorded study'],['Run',runLabel],['Installed BESS units',fleet.length?String(fleet.length):opt.no_bess_selected?'No BESS':'—'],['Total BESS power',fleet.length?fmt(fleet.reduce((a,b)=>a+b.power_rating_kw,0),0)+' kW':candidate?fmt(candidate.power_rating_kw,0)+' kW':'—'],['Total BESS energy',fleet.length?fmt(fleet.reduce((a,b)=>a+b.energy_capacity_kwh,0),0)+' kWh':candidate?fmt(candidate.energy_capacity_kwh,0)+' kWh':'—'],['Installed inverter capacity',fleet.length?fmt(fleet.reduce((a,b)=>a+b.power_rating_kw,0)*ratio,1)+' kVA':candidate?fmt(candidate.power_rating_kw*ratio,1)+' kVA':'—'],['Initial BESS investment',money(c.bess_cost??a.bess_cost)]]);
  if(fleet.length){const units=section(root,manual?'Manual battery installation':'Optimized battery installations');grid(units,['Unit','Bus','Battery P (kW)','Battery E (kWh)','Inverter S (kVA)','E/P (h)'],fleet.map((unit,index)=>[index+1,'Bus '+unit.bus_id,fmt(unit.power_rating_kw,0),fmt(unit.energy_capacity_kwh,0),fmt(unit.power_rating_kw*ratio,1),fmt(unit.energy_capacity_kwh/unit.power_rating_kw,2)]));}
  const limits=opt.bess_duration_constraint;if(limits){const duration=section(root,'Battery sizing constraint');cards(duration,[["Minimum nameplate duration",fmt(limits.minimum_hours,2)+' h'],["Maximum nameplate duration",fmt(limits.maximum_hours,2)+' h'],["Feasible P/E pairs per bus",fmt(limits.feasible_pairs_per_bus,0)]]);duration.append(elem('p','Duration = rated energy capacity (kWh) / rated active power (kW). Only matching search candidates are simulated.','fine'));}
  const stages=opt.stages||[];if(stages.length && opt.initial_ranking_applied===false){const proof=section(root,'Joint GA placement and annual verification');grid(proof,['Fleet','Buses','Power / inverter / energy','Verification','Hours','Annual cost'],(stages[0].full_year_candidates||[]).map(x=>[String(x.unit_count)+' BESS',(x.fleet||[]).map(u=>'Bus '+u.bus_id).join(', '),(x.fleet||[]).reduce((s,u)=>s+u.power_rating_kw,0)+' kW / '+fmt((x.fleet||[]).reduce((s,u)=>s+u.power_rating_kw,0)*ratio,1)+' kVA / '+fmt((x.fleet||[]).reduce((s,u)=>s+u.energy_capacity_kwh,0),0)+' kWh',x.feasible?(x.economic_acceptable?'Accepted':'No annual saving'):'Rejected',String(x.annual_processed_hours)+' / '+String(x.annual_expected_hours),money(x.annual_cost)]));}
  if(stages.length && opt.initial_ranking_applied!==false){const progress=section(root,'Placement decisions');grid(progress,['Stage','Candidate buses','Selected','Lateral shedding','Voltage deficit','Annual cost difference'],stages.map(row=>[row.index,(row.shortlist||[]).length,row.selected?'Bus '+row.selected.bus_id+' ('+(row.selected_lateral||'lateral unknown')+')':row.status,row.technical_check?.shedding_improvement_percent==null?'—':fmt(row.technical_check.shedding_improvement_percent,1)+'%',row.technical_check?.voltage_improvement_percent==null?'—':fmt(row.technical_check.voltage_improvement_percent,1)+'%',row.annual_saving_vs_previous==null?'Not installed':(row.annual_saving_vs_previous>=0?'Saved ':'Added cost ')+money(Math.abs(row.annual_saving_vs_previous))]));
    progress.append(elem('p','Annual acceptance requires measurable improvement in target-lateral shedding or pre-control voltage, verified full-year network feasibility, no material shedding deterioration elsewhere, and reduced annual cost. Pre-control voltage deterioration is reported, not a veto when shedding improves. The configured 10% levels are cumulative reporting targets, not per-placement gates.','fine'));
    const diagnostics=stages.filter(st=>st.gwo_stop_reason).map(st=>'Stage '+st.index+': '+(st.gwo_stop_reason==='converged_no_meaningful_improvement'?'GWO converged':'GWO reached iteration limit')+' after '+(st.screening_iterations??'?')+' iterations, '+(st.annual_finalists_verified??'?')+' annual finalists ('+(st.screening_hours_per_candidate??'?')+' h screened per candidate; '+(st.annual_hours_required??'?')+' h required per annual finalist)');
    if(diagnostics.length)progress.append(elem('p','Optimization runtime decisions — '+diagnostics.join('; ')+'. Cached No-BESS baseline: '+(opt.no_bess_cache_hit?'yes':'no')+'. Reused accepted annual results: '+(opt.accepted_annual_results_reused??0)+'.','fine'));
    for(const st of stages){
      if(!st.full_year_candidates?.length)continue;
      const block=section(root,'Annual finalists — placement '+st.index);
      grid(block,['Bus','Lateral','kW / kWh','Duration (h)','Shed improvement','Voltage improvement','Technical decision','Hours simulated','Cumulative goal','Annual cost'],st.full_year_candidates.map(x=>['Bus '+x.bus,x.lateral,fmt(x.power_kw,0)+' / '+fmt(x.energy_kwh,0),fmt(x.energy_kwh/x.power_kw,2),x.shedding_improvement_percent==null?'—':fmt(x.shedding_improvement_percent,1)+'%',x.voltage_improvement_percent==null?'—':fmt(x.voltage_improvement_percent,1)+'%',x.technical_acceptable?'Incremental pass':x.technical_reason,x.annual_processed_hours==null?'Not verified':String(x.annual_processed_hours)+' / '+String(x.annual_expected_hours),x.cumulative_target_met==null?'—':x.cumulative_target_met?'Met':'Not yet',money(x.annual_cost)]));
    }
  }
  if(opt.initial_ranking_applied===false){const info=section(root,'Search and annual verification');cards(info,[['Eligible bus locations',fmt(opt.eligible_bus_count||0,0)],['Buses explored by GA',fmt(opt.ga_visited_bus_count||0,0)],['Stress-screened fleets',fmt(opt.independent_stress_candidate_count||0,0)],['Stress days',fmt((opt.independent_stress_days||[]).length,0)],['Annual full-year finalists',fmt(opt.stages?.[0]?.annual_finalists_verified||0,0)]]);info.append(elem('p','All eligible non-slack buses were available to the Joint GA. Independent extreme and seasonal holdouts precede sequential full-year verification; only a completed year is an annual result.','fine'));}
  const paired=Boolean(sc('no_bess')&&sc('best_bess'));
  const first=paired?b:sc('no_bess')?b:a;
  const second=paired?c:{};
  const headings=paired?['Without BESS','With BESS']:[sc('no_bess')?'No BESS':runLabel];
  const addMetrics=(target, title, rows)=>grid(target,[title,...headings],
    paired?rows:rows.map(row=>row.slice(0,2)));
  const comparison=section(root,'Energy and voltage');
  addMetrics(comparison,'Measure',[
    ['Requested demand',energy(first.requested_load_energy_kwh),energy(second.requested_load_energy_kwh)],
    ['Demand served',energy(first.served_load_energy_kwh),energy(second.served_load_energy_kwh)],
    ['Solar available',energy(first.available_pv_energy_kwh),energy(second.available_pv_energy_kwh)],
    ['Solar used',energy(first.pv_generation_energy_kwh),energy(second.pv_generation_energy_kwh)],
    ['Grid imported',energy(first.grid_import_energy_kwh),energy(second.grid_import_energy_kwh)],
    ['Load shedding',energy(first.load_shedding_energy_kwh),energy(second.load_shedding_energy_kwh)],
    ['PV curtailment',energy(first.curtailment_energy_kwh),energy(second.curtailment_energy_kwh)],
    ['Network losses',energy(first.loss_energy_kwh),energy(second.loss_energy_kwh)],
    ['Minimum voltage',first.voltage_min_pu==null?'—':fmt(first.voltage_min_pu,4)+' pu',second.voltage_min_pu==null?'—':fmt(second.voltage_min_pu,4)+' pu'],
  ]);
  const capitalLabel=economics.annualization_method==='real_crf'?'Annual capital: initial investment × recovery factor':'Annual capital: initial BESS cost / useful life';
  const costs=section(root,'Annual costs (USD/year)');
  if(first.annual_total_cost==null && second.annual_total_cost==null)
    costs.append(elem('p','Annual cost requires a complete calendar year and confirmed tariffs.','fine'));
  else addMetrics(costs,'Calculation',[
    ['Grid electricity: imported kWh × tariff − export credit',money(first.annual_grid_cost),money(second.annual_grid_cost)],
    ['Unserved kWh × load-shedding penalty',money(first.annual_shedding_cost),money(second.annual_shedding_cost)],
    ['Curtailed kWh × PV-curtailment penalty',money(first.annual_curtailment_cost),money(second.annual_curtailment_cost)],
    ['Annual operating cost (grid + penalties)',money(first.annual_operating_cost),money(second.annual_operating_cost)],
    [capitalLabel,money(first.annual_bess_capital_cost),money(second.annual_bess_capital_cost)],
    ['Annual O&M: initial BESS cost × O&M percentage',money(first.annual_bess_om_cost),money(second.annual_bess_om_cost)],
    ['Annual BESS ownership (capital + O&M)',money(first.annualized_bess_cost),money(second.annualized_bess_cost)],
    ['Total annual cost (operating + BESS ownership)',money(first.annual_total_cost),money(second.annual_total_cost)],
    ['Initial BESS installation (one-time reference)',money(first.bess_cost),money(second.bess_cost)]
  ]);
  const em=run.metadata?.economic_inputs||run.metadata?.context?.['Economic inputs']||{};
  const life=opt.bess_lifetime_years??em.lifetime_years;
  const om=opt.annual_om_percent_of_capex??(em.annual_om_fraction!=null?em.annual_om_fraction*100:null);
  const explanation=elem('p',`Battery cost = energy (kWh) × USD/kWh + inverter apparent power (kVA) × USD/kVA in daily MILP dispatch mode. Capital is annualized with ${opt.economic_configuration?.annualization_method==='real_crf'?'the discounted real capital-recovery factor':'the configured recovery method'} over ${life??'configured'} years; annual O&M = ${om==null?'configured':fmt(om,2)+'%'} of original investment. Shedding and curtailment penalties are modeled costs, not bills.`,'treatment');costs.append(explanation);
  // Compact stage-by-stage placement evidence: all candidate rows are kept in
  // the saved metadata and canonical CSV, but only the shortlisted third is
  // displayed here to keep the dashboard focused.
  const stageRanks=opt.initial_ranking_applied===false?[]:(opt.stages||[]).filter(stage=>Array.isArray(stage.weakness_ranking)&&stage.weakness_ranking.length);
  const singleRanks=Array.isArray(opt.screened_locations)?opt.screened_locations:[];
  if(stageRanks.length || singleRanks.length){
    const ranking=section(root,'BESS placement ranking');
    ranking.append(elem('p','Combined priority = 50% voltage weakness rank + 50% load-shedding rank. Lower is better. A roughly one-third shortlist is balanced across affected electrical laterals. Rankings are recalculated after each accepted battery. The GWO screening score prioritizes technical relief; annual cost chooses among candidates passing annual lateral-improvement requirements.','fine'));
    const displayStage=(number,rows,stageRow)=>{
      const kept=rows.filter(r=>r.retained).sort((a,b)=>a.rank-b.rank);
      const heading=number===1?'Before BESS 1 (No BESS)':'After BESS '+(number-1);
      const box=elem('div',undefined,'ranking-stage');ranking.append(box);
      box.append(elem('h3',heading));
      box.append(elem('p',`${kept.length} of ${rows.length} eligible buses shortlisted`+(stageRow?.selected?' · Selected Bus '+stageRow.selected.bus_id:' · '+(stageRow?.status||'candidate ranking')),'fine'));
      grid(box,['Rank','Bus','Lateral','Voltage rank','Shedding rank','Combined score','Voltage deficit (pu·h)','Shed (MWh)'],
           kept.map(r=>[r.rank,'Bus '+r.bus,r.lateral??'—',r.voltage_rank??'—',r.shedding_rank??'—',fmt(r.combined_score,1),fmt(r.voltage_deficit_pu_hours,2),energy(r.local_baseline_shedding_kwh)]));
    };
    if(stageRanks.length){for(const st of stageRanks)displayStage(st.index,st.weakness_ranking,st);}
    else displayStage(1,singleRanks,null);
    ranking.append(elem('p','Complete ranked buses for every stage are exported in bus_ranking_by_stage.csv. Shedding is measured after corrective control; voltage weakness is measured before correction.','fine'));
  }
  const finish=section(root,'Run validity and final battery energy');finish.append(elem('p',paired?'No BESS: '+statusLabel(b.feasible)+' · With BESS: '+statusLabel(c.feasible):runLabel+': '+statusLabel(first.feasible),'fine'));
  const terminal=paired?c:first;
  if((terminal.load_shedding_energy_kwh||0)>0) {
    finish.append(elem('p','Demand unserved: '+energy(terminal.load_shedding_energy_kwh)+'. Network feasibility includes the corrective actions used to serve the remaining load.','warning'));
  }
  if(terminal.terminal_energy_change_kwh!=null){
    finish.append(elem('p','Battery stored-energy change (final − initial): '+fmt(terminal.terminal_energy_change_kwh,2)+' kWh. Largest absolute SOC change: '+fmt(100*Math.abs(terminal.final_soc_deviation||0),3)+' percentage points.','fine'));
    if(terminal.terminal_soc_details)finish.append(elem('p',String(terminal.terminal_soc_details),'fine'));
    if(run.metadata.simulation?.fleet_dispatch_mode==='daily_milp_dispatch')
      finish.append(elem('p','Daily MILP dispatch operation requires daily SOC restoration. The per-day audit is included in the numerical exports.','fine'));
    else finish.append(elem('p','No terminal SOC closure is required in this archived operating mode.','fine'));
  }
  if(run.ranked?.length){
    const details=elem('details');
    details.append(elem('summary','Ranked annual candidates'));
    root.append(details);
    grid(details,['Rank','Location','Power (kW)','Energy (kWh)','Annual cost'],
      run.ranked.map((item,index)=>[index+1,'Bus '+item.bus_id,fmt(item.power_rating_kw),fmt(item.energy_capacity_kwh),money(item.annual_cost)]));
  }

}
let redraw=[];
async function charts(){const root=$('content');const control=section(root,'Power and voltage');const options=Object.keys(run.scenarios).filter(key=>sc(key)?.hour_count);const select=elem('select');options.forEach(key=>select.add(new Option(sc(key).label,key)));scenario=options.includes(galleryState.scenario)?galleryState.scenario:options[0];select.value=scenario;const date=elem('input');date.type='date';const chooser=elem('div',undefined,'controls');chooser.append(elem('span','Scenario'),select,elem('span','First day of 14-day view'),date);control.append(chooser);const graph=elem('div',undefined,'charts');control.append(graph);
  async function paint(){
    scenario=select.value;galleryState.scenario=scenario;
    const s=selected(),axis=s.gallery?.timestamps!=null?await block(s.gallery.timestamps):[];
    graph.replaceChildren();redraw=[];
    if(!axis.length){graph.append(elem('p','No hourly simulation records were saved.','empty'));return;}
    date.min=axis[0].slice(0,10);date.max=axis.at(-1).slice(0,10);
    if(!date.value)date.value=axis[Math.min(galleryState.hour,axis.length-1)].slice(0,10);
    const begin=Math.max(0,axis.findIndex(t=>t.slice(0,10)>=date.value));
    const arr=await hourWindow(s,begin,begin+336),dates=arr.map(r=>r.timestamp);
    for(const [i,row] of arr.entries())if(row.converged===false)arr[i]={timestamp:row.timestamp,converged:false};
  plot(graph,'Hourly demand, solar, and grid import (kW)',[
   {name:'Demand served',data:arr.map(r=>r.load_input_kw)},
   {name:'PV used',data:arr.map(r=>r.pv_input_kw)},
   {name:'Grid import (+) / export (−)',data:arr.map(r=>r.slack_p_kw)}],dates);
  plot(graph,'Minimum / maximum bus voltage (pu)',[
   {name:'Minimum voltage',data:arr.map(r=>r.voltage_min_pu)},
   {name:'Maximum voltage',data:arr.map(r=>r.voltage_max_pu)}],dates);
  const fleet=s.gallery.groups.battery;
  if(fleet){
    const ids=Object.keys(fleet.entities);
    for(const [field,title,factor] of [['soc_after','Battery SOC per installation (%)',100],['power_kw','Battery active power (kW)',1],['reactive_power_kvar','Battery reactive power (kvar)',1]]){
      if(!fleet.fields.includes(field))continue;
      const traces=await Promise.all(ids.map(async id=>({name:'Bus '+id,data:(await seriesValues(fleet,id,field,begin,begin+arr.length)).map((v,i)=>v==null||arr[i].converged===false?null:v*factor)})));
      plot(graph,title,traces,dates);
    }
    const bus=s.gallery.groups.bus;
    if(bus?.fields.includes('bess_s_kva')){
      const traces=await Promise.all(ids.map(async id=>({name:'Bus '+id,data:await seriesValues(bus,id,'bess_s_kva',begin,begin+arr.length)})));
      plot(graph,'BESS inverter apparent power (kVA)',traces,dates);
    }
  }
  if(arr.some(r=>r.bess_accepted_soc!=null))plot(graph,'Battery state of charge (%)',[
    {name:'SOC',data:arr.map(r=>r.bess_accepted_soc==null?null:100*r.bess_accepted_soc)}],dates);
  // At the worst recorded hour, show the actual per-bus voltage profile.
  const worst=s.diagnostic?.worst_timestamp;
  if(worst){const voltages=s.worst_bus_voltages||{};const busIDs=Object.keys(voltages).sort((a,b)=>Number(a)-Number(b));if(busIDs.length){const vals=busIDs.map(id=>voltages[id]);plot(graph,'Bus voltages at worst hour: '+worst,[{name:'Bus voltage (pu)',data:vals}],busIDs.map(b=>'Bus '+b));}}
  if(arr.some(r=>r.shedding_kw!=null||r.curtailment_kw!=null))
    plot(graph,'Shedding and curtailment (kW)',[
      {name:'Load shedding',data:arr.map(r=>r.shedding_kw)},
      {name:'PV curtailment',data:arr.map(r=>r.curtailment_kw)}],dates);
  await feederView(graph,s,axis,begin,arr.length);
  if(run.convergence?.length){plot(graph,'Optimizer convergence: scenario-cost objective (USD/year)',[{name:'Best screening objective',data:run.convergence.map(r=>r.best_annual_cost)}],run.convergence.map((r,i)=>String(r.iteration??i+1)));}
  }
  select.addEventListener('change',paint);date.addEventListener('change',paint);await paint();}
async function forecast(){const root=$('content');const rows=run.forecast_errors||[];const s=section(root,'Forecasting errors — observed holdout');if(!rows.length){s.append(elem('p','Unavailable: this run has no matched post-training actual observations. Run the forecast for a historical holdout (for example 2021 trained through 2020) and optimize using that forecast. Training error is not substituted.','empty'));return;}
  const perBus=rows.every(r=>r.bus_count!=null);
  s.append(elem('p',perBus?'MAE, RMSE, and WAPE are first calculated separately at each bus, then averaged equally within its load or PV category. The chart remains total sector power. Only matching post-training actual timestamps are evaluated.':'Legacy report: MAE and RMSE were calculated on the summed sector profile, not averaged over buses. Generate a new run to view per-bus average errors.','fine'));
  grid(s,perBus?['Profile','Buses','Hours','Avg bus MAE (kW)','Avg bus RMSE (kW)','Avg bus WAPE (%)']:['Profile','Hours','Aggregate MAE (kW)','Aggregate RMSE (kW)','WAPE (%)'],
       rows.map(r=>perBus?[r.category,r.bus_count,r.hours,fmt(r.mae_kw,2),fmt(r.rmse_kw,2),r.wape_percent==null?'Undefined':fmt(r.wape_percent,2)+'%']:[r.category,r.hours,fmt(r.mae_kw,2),fmt(r.rmse_kw,2),r.wape_percent==null?'Undefined':fmt(r.wape_percent,2)+'%']));
  if(run.forecast_comparison_block==null)return;
  const recorded=await block(run.forecast_comparison_block);const control=section(root,'Actual vs forecast (14 days)');const row=elem('div',undefined,'controls');const category=elem('select');const names=[...new Set(recorded.map(r=>r.category))];names.forEach(n=>category.add(new Option(n.replaceAll('_',' '),n)));const date=elem('input');date.type='date';row.append(elem('span','Profile'),category,elem('span','First day'),date);control.append(row);const graph=elem('div',undefined,'charts');control.append(graph);
  function paint(){graph.replaceChildren();redraw=[];const subset=recorded.filter(r=>r.category===category.value);if(!subset.length)return;date.min=subset[0].timestamp.slice(0,10);date.max=subset.at(-1).timestamp.slice(0,10);if(!date.value)date.value=date.min;let start=subset.findIndex(r=>r.timestamp.slice(0,10)>=date.value);start=Math.max(0,start);const a=subset.slice(start,start+14*24);plot(graph,'Hourly actual and forecast (kW)',[{name:'Actual',data:a.map(r=>r.actual_kw)},{name:'Forecast',data:a.map(r=>r.forecast_kw)}],a.map(r=>r.timestamp));}
  category.addEventListener('change',()=>{date.value='';paint();});date.addEventListener('change',paint);paint();}
async function feederView(parent, selectedScenario, hourly, start, length) {
  const positions=run.metadata.layout?.positions;
  if(!positions||!length)return;
  const series=selectedScenario.gallery.groups;
  async function readingsFor(group,field){
    if(!group?.fields.includes(field))return {};
    const entries=await Promise.all(Object.keys(group.entities).map(async id=>[id,await seriesValues(group,id,field,start,start+length)]));
    return Object.fromEntries(entries);
  }
  const readings=await readingsFor(series.bus,'voltage_pu'),currents=await readingsFor(series.line,'current_a');
  if(!Object.keys(readings).length)return;
  const panel=section(parent,'Hourly feeder');
  const slider=elem('input');slider.type='range';slider.min=0;slider.max=length-1;slider.value=Math.max(0,Math.min(length-1,galleryState.hour-start));
  slider.setAttribute('aria-label','Hour within the selected window');
  const stamp=elem('output');
  const controls=elem('div',undefined,'controls');
  controls.append(slider,stamp);panel.append(controls);
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  const vertex=Object.values(positions);
  const xs=vertex.map(point=>point[0]), ys=vertex.map(point=>point[1]);
  const minX=Math.min(...xs)-45,maxX=Math.max(...xs)+45,minY=Math.min(...ys)-45,maxY=Math.max(...ys)+45;
  svg.setAttribute('viewBox',[minX,minY,maxX-minX,maxY-minY].join(' '));
  svg.setAttribute('class','feeder');
  svg.setAttribute('role','img'); svg.setAttribute('aria-label','Feeder voltages and branch currents');
  const branches=new Map(), buses=new Map();
  function append(name, properties, caption) {
    const node=document.createElementNS(ns,name);
    for(const [key,value] of Object.entries(properties))node.setAttribute(key,value);
    const label=document.createElementNS(ns,'title');label.textContent=caption;node.append(label);svg.append(node);
    return [node,label];
  }
  function linkElement(shape,group,id,caption){
    shape.setAttribute('role','button');shape.setAttribute('tabindex','0');
    shape.setAttribute('aria-label',caption);
    shape.onclick=()=>{galleryState.scenario=scenario;jump(group,id,start+Number(slider.value));};
    shape.onkeydown=e=>{
      if(e.key==='Enter'||e.key===' '){e.preventDefault();shape.onclick();}
    };
  }
  for(const branch of run.metadata.topology?.lines||[]) {
    const route=run.metadata.layout.routes?.[branch.line_id]||[positions[branch.from_bus],positions[branch.to_bus]];
    if(!route.every(Boolean))continue;
    const [shape, title]=append('polyline',{points:route.map(point=>point.join(',')).join(' '),fill:'none',stroke:'#728697','stroke-width':6},branch.line_id);
    linkElement(shape,'line',branch.line_id,'Plot line '+branch.line_id);
    branches.set(branch.line_id,{shape,title,ampacity:branch.ampacity_a});
  }
  for(const [bus,[x,y]] of Object.entries(positions)) {
    const [shape,title]=append('circle',{cx:x,cy:y,r:15,stroke:'#1d3440','stroke-width':3},'Bus '+bus);
    const label=document.createElementNS(ns,'text');
    label.setAttribute('x',x);label.setAttribute('y',y-22);label.setAttribute('text-anchor','middle');
    label.setAttribute('font-size',27);label.textContent=bus;svg.append(label);
    linkElement(shape,'bus',bus,'Plot bus '+bus);
    buses.set(bus,{shape,title});
  }
  const min=run.metadata.simulation?.voltage_min_pu, max=run.metadata.simulation?.voltage_max_pu;
  function showHour() {
    const index=start+Number(slider.value);
    galleryState.hour=index;stamp.textContent=hourly[index];
    for(const [bus,{shape,title}] of buses) {
      const value=readings[bus]?.[index-start];
      const outside=Number.isFinite(value)&&(value<min||value>max);
      shape.setAttribute('fill',outside?'#b54c21':Number.isFinite(value)?'#208582':'#adb6bb');
      title.textContent='Bus '+bus+' · '+fmt(value,4)+' pu';
    }
    for(const [line,{shape,title,ampacity}] of branches) {
      const value=currents[line]?.[index-start];
      const loading=Number.isFinite(value)&&ampacity?100*value/ampacity:null;
      shape.setAttribute('stroke',loading>100?'#b54c21':'#728697');
      title.textContent=line+' · '+fmt(value,2)+' A'+(loading==null?'':' · '+fmt(loading,1)+'% of rating');
    }
  }
  panel.append(svg);slider.addEventListener('input',showHour);showHour();
}

async function readSavedReport(file){
  // Byte offsets let a comparison read only the selected blocks from a local File.
  const offsets=new Map(),tag=/<script id="(report-data|report-block-\d+)"[^>]*>/g;
  const decoder=new TextDecoder('latin1'),size=1024*1024;
  let tail='',active=null;
  for(let start=0;start<file.size;start+=size){
    const bytes=await file.slice(start,start+size).arrayBuffer();
    const chunk=tail+decoder.decode(bytes),base=start-tail.length;
    let pos=0;tail='';
    while(pos<chunk.length){
      if(active){
        const end=chunk.indexOf('<',pos);
        if(end<0)break;
        offsets.set(active.key,[active.begin,base+end]);active=null;pos=end;
      }
      tag.lastIndex=pos;
      const next=tag.exec(chunk);
      if(!next){
        const last=chunk.lastIndexOf('<');
        if(last>=pos&&!chunk.slice(last).includes('>'))tail=chunk.slice(last);
        break;
      }
      pos=tag.lastIndex;active={key:next[1],begin:base+pos};
    }
  }
  async function read(key){
    const extent=offsets.get(key);
    if(!extent)throw Error('Missing saved report block '+key);
    return inflate(await file.slice(...extent).text());
  }
  const saved=await read('report-data');
  if(!saved?.manifest||!saved.scenarios)throw Error('Report is incomplete');
  saved.readBlock=id=>read('report-block-'+id);
  return saved;
}

function compareRuns() {
  const root=$('content'), panel=section(root,'Compare saved reports');
  const label=elem('label','Saved dashboard HTML files');
  const files=elem('input');files.type='file';files.accept='.html,text/html';files.multiple=true;label.append(files);
  const table=elem('div');panel.append(label,table);
  files.addEventListener('change',async()=>{
    table.replaceChildren();
    const snapshots=[run];
    for(const file of files.files) {
      try {
        const saved=await readSavedReport(file);
        if(!snapshots.some(candidate=>candidate.manifest.run_id===saved.manifest.run_id)){
          snapshots.push(saved);
        }
      } catch(error) { table.append(elem('p',file.name+' · '+error.message,'warning')); }
    }
    const rows=[];
    for(const saved of snapshots) {
      const manifest=saved.manifest;
      const sameHours=Boolean(manifest.timestamp_sha256&&manifest.clock&&manifest.clock===run.manifest.clock&&manifest.timestamp_sha256===run.manifest.timestamp_sha256&&manifest.timestamp_count===run.manifest.timestamp_count);
      const sameTopology=manifest.topology_sha256&&manifest.topology_sha256===run.manifest.topology_sha256;
      const sameBasis=Boolean(manifest.currency&&manifest.currency===run.manifest.currency);
      for(const result of Object.values(saved.scenarios)) {
        const metrics=asMetrics(result);
        rows.push([manifest.folder||manifest.kind,result.label,saved.metadata?.topology?.buses?.find(b=>b.is_slack)?.v_set_pu,fmt(metrics.voltage_min_pu,5),fmt(metrics.duration_hours,0),
          statusLabel(metrics.feasible),energy(metrics.load_shedding_energy_kwh),
          energy(metrics.curtailment_energy_kwh),metrics.annual_total_cost==null?'Unavailable':fmt(metrics.annual_total_cost)+' '+(manifest.currency||'unrecorded currency')+'/year',
          sameHours&&sameTopology&&sameBasis?'Same feeder, hours and currency':'Review comparability']);
      }
    }
    grid(table,['Run','Scenario','Slack (pu)','Minimum V (pu)','Hours','Feasibility','Shedding','Curtailment','Annual cost','Comparison basis'],rows);
    if(snapshots.length>1)await compareCurves(table,snapshots);
  });
}

async function render(){
  const root=$('content');root.replaceChildren();redraw=[];
  try {
    if(screen==='Summary')summary();
    else if(screen==='Charts')await charts();
    else if(screen==='Forecast accuracy')await forecast();
    else if(screen==='Compare runs')compareRuns();
    else await gallery();
  } catch(error) {root.append(elem('p','Unable to read saved report: '+error.message,'warning'));}
}
async function start(){
  run=await inflate($('report-data').textContent);
  if(!run?.manifest||!run.scenarios)throw Error('Incomplete report payload');
  const labels=['Summary','Charts'];
  labels.push('Study inputs','Network','Demand & PV','Decisions','BESS','Economics');
  if(focusState.group)screen=groupsFor['Study inputs'].includes(focusState.group)?'Study inputs':'Network';
  if(run.forecast_errors?.length)labels.push('Forecast accuracy');
  if(Object.values(run.scenarios).some(s=>s.gallery?.groups?.forecast))labels.push('Forecast series');
  labels.push('Compare runs');
  for(const name of labels){
    const button=elem('button',name);button.type='button';
    button.addEventListener('click',()=>{screen=name;tabs();render();});$('tabs').append(button);
  }
  $('tabs').hidden=false;
  $('study-label').textContent=[run.manifest.folder,run.manifest.clock,run.manifest.timestamp_count?run.manifest.timestamp_count+' hours':null].filter(Boolean).join(' · ');
  $('notice').textContent=run.metadata?.legacy?'Archived results: some details may be unavailable.':'';
  $('print').addEventListener('click',()=>window.print());
  const methodology=document.querySelector('.model-information');
  let methodologyWasOpen=false;
  window.addEventListener('beforeprint',()=>{methodologyWasOpen=methodology.open;methodology.open=true;});
  window.addEventListener('afterprint',()=>{methodology.open=methodologyWasOpen;});
  window.addEventListener('resize',()=>redraw.forEach(draw=>draw()));
  tabs();await render();
}
function tabs(){[...$('tabs').children].forEach(button=>button.setAttribute('aria-selected',button.textContent===screen));}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>start().catch(error=>$('notice').textContent=error.message),{once:true});else start().catch(error=>$('notice').textContent=error.message);
