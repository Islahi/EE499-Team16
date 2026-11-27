// Read-only engineering views over archived profiles, dispatch and ledgers.
const academicForecast=ctx=>academicHas(ctx,'forecast','actual_kw')||academicHas(ctx,'forecast by bus','actual_kw');
const academicPV=ctx=>ctx.archive.metadata?.pv_buses?.length||academicMetric(ctx,'available_pv_energy_kwh')>0;
const academicValidPairs=(a,b)=>a.map((v,i)=>[v,b[i],i]).filter(row=>row.slice(0,2).every(academicNumber));
const academicRunUnits=ctx=>hasInstalledBess(ctx)?(manualUnits(ctx.archive.metadata).length?manualUnits(ctx.archive.metadata):
  ctx.archive.metadata?.optimizer?.fleet||[]):[];
const academicSimpleStats=values=>values.filter(academicNumber);
const academicDelta=(a,b)=>academicNumber(a)&&academicNumber(b)?a-b:null;
function academicPeriodKey(range) {
  return range.axis[0]?.slice(0,7)===range.axis.at(-1)?.slice(0,7)?s=>s.slice(0,10):s=>s.slice(0,7);
}

async function academicInputLoad(root,ctx,range,mode) {
  const group=ctx.gallery.groups['load input']?'load input':'load output',source=ctx.gallery.groups[group];
  const field=group==='load input'?'p_kw':'requested_load_kw';
  if(!source)return academicMissing(root,'Archived hourly load profiles and bus demand are unavailable.');
  const ids=Object.keys(source.categories||{}).filter(id=>source.entities[id]);
  const label=id=>categoryLabel(source,id);
  if(mode==='default'){
    const cats=ids.length?ids:['Total'];
    const values=await Promise.all(cats.map(id=>academicSeries(ctx,group,id,field,range)));
    const resolution=resolvedResolution(workspace.state.time.resolution||'auto',range.axis.length);
    const bundles=values.map(v=>bucketReadings(range.axis,v,resolution,'auto',null,'kW',field,null,range.durations));
    academicPlot(root,'Requested demand by archived category',bundles[0].axis,
      bundles.map((v,i)=>academicTrace(label(cats[i]),v.data)),'kW',ctx,
      {note:resolutionLabels[resolution]+' · '+bundles[0].operation+' · Missing category samples are gaps.'});
    const energy=academicBuckets(range.axis,range.durations,values,academicPeriodKey(range),true,range.valid);
    academicPlot(root,'Energy demand by calendar period',energy.map(x=>x.label),
      cats.map((id,i)=>academicTrace(label(id),energy.map(r=>r.sum[i]),'bar')),'kWh',ctx,
      {categorical:true,note:'Each value integrates retained samples with recorded durations.'});
    academicTable(root,'Category energy and valid hours',['Period',...cats.map(id=>label(id)+' (kWh)'),...cats.map(id=>label(id)+' (h)')],
      energy.map(r=>[r.label,...r.sum,...r.hours]),ctx);
    return;
  }
  const state=academicState['Study Inputs'],choices=['Total',...ids,...academicIds(ctx,group).filter(id=>/^\d+$/.test(id))];
  const entity=choices.includes(state.loadEntity)?state.loadEntity:'Total';
  academicPicker(root,'Demand scope',choices,entity,value=>{state.loadEntity=value;refreshWorkspace();},label);
  const p=await academicSeries(ctx,group,entity,field,range);
  const served=await academicSeries(ctx,'load output',entity,'load_input_kw',range);
  if(mode==='duration'){
    for(const [name,values] of [['Requested',p],['Served',served]]){
      const d=academicDuration(values,range);
      if(d.hours>0)academicPlot(root,name+' demand duration',d.axis,[academicTrace(name,d.data)],'kW',ctx,
        {categorical:true,coordinates:d.axis,axisLabel:'Elapsed exceedance (%)',
          note:fmt(d.hours)+' h of valid samples. Chronology and storage sequencing are lost.'});
    }
    return;
  }
  if(mode==='peaks'){
    const by=new Map();
    p.forEach((v,i)=>{
      if(!academicNumber(v)||!range.valid[i])return;
      const key=range.axis[i].slice(0,7);
      if(!by.has(key))by.set(key,[]);
      by.get(key).push([v,range.axis[i],range.durations[i]]);
    });
    const rows=Array.from(by,([month,values])=>{
      const peak=values.reduce((a,b)=>b[0]>a[0]?b:a),hours=academicSum(values.map(row=>row[2]||0));
      const mean=values.every(row=>row[2]>0)?academicSum(values.map(row=>row[0]*row[2]))/hours:null;
      return [month,peak[0],peak[1],mean,hours,academicRatio(mean,peak[0])];
    });
    academicPlot(root,'Calendar monthly coincident peak',rows.map(r=>r[0]),[academicTrace(label(entity),rows.map(r=>r[1]),'bar')],'kW',ctx,{categorical:true});
    academicTable(root,'Demand peak and load factor',['Month','Peak (kW)','First peak timestamp','Mean (kW)','Covered hours','Load factor'],
      rows,ctx,{note:'The reported peak is the peak of the selected summed profile.'});
    return;
  }
  if(mode==='statistics'){
    const report=ctx.gallery.consumption==null?null:await readings(ctx)(ctx.gallery.consumption);
    if(!report)return academicMissing(root,'Consumption statistics were unavailable.');
    const load='load output',tariff=ctx.archive.manifest.economics?.grid_import_tariff_per_kwh;
    const total=academicStats(await academicSeries(ctx,load,'Total','requested_load_kw',range),range);
    const rows=[];
    for(const row of [...report.categories,...report.buses]){
      const [r,s,d,penalty]=await Promise.all(['requested_load_kw','load_input_kw','shedding_kw','shedding_cost'].map(f=>
        academicSeries(ctx,load,row.id,f,range)));
      const [request,served,shed]=[r,s,d].map(values=>academicStats(values,range));
      const amounts=penalty.filter((v,i)=>academicNumber(v)&&range.valid[i]);
      const same=request.count===total.count&&request.hours===total.hours;
      rows.push([row.id,/^\d+$/.test(row.id)?consumptionLabel(report,row.category):consumptionLabel(report,row.id),row.bus_count,
        request.energy,served.energy,shed.energy,request.mean,request.minimum,request.maximum,request.peak,
        same&&academicNumber(request.energy)?academicRatio(100*request.energy,total.energy):null,
        academicRatio(request.mean,request.maximum),academicNumber(served.energy)&&academicNumber(tariff)?served.energy*tariff:null,
        amounts.length?academicSum(amounts):null,request.hours,served.hours,shed.hours]);
    }
    academicTable(root,'Selected-period consumption statistics',['Scope','Category','Bus count','Requested (kWh)','Served (kWh)','Shed (kWh)',
      'Mean (kW)','Minimum (kW)','Peak (kW)','Peak timestamp','Requested share (%)','Load factor','Illustrative import tariff proxy',
      'Recorded shedding penalty','Requested hours','Served hours','Shed hours'],rows,ctx,
      {open:true,note:'Recorded period and valid coverage. The illustrative tariff proxy prices served energy at the grid import rate.'});
    return;
  }
  const clock=ctx.archive.manifest.clock||'Archive clock unspecified';
  const months=[...new Set(range.axis.filter((_,i)=>range.valid[i]).map(t=>t.slice(0,7)))];
  academicPicker(root,'Month',['',...months],state.typicalMonth||'',value=>{state.typicalMonth=value;refreshWorkspace();},id=>id||'All months');
  selectControl(root,'Scale',[['absolute','Active power (kW)'],['relative','Share of selected-period peak (%)']],
    state.typicalScale||'absolute',value=>{state.typicalScale=value;refreshWorkspace();});
  const peak=academicStats(p,range).maximum,relative=state.typicalScale==='relative';
  const groups=['Weekday','Weekend'],slots=groups.map(()=>Array.from({length:24},()=>({sum:0,dt:0,n:0,min:Infinity,max:-Infinity})));
  p.forEach((value,i)=>{
    const stamp=range.axis[i],dt=range.durations[i];
    if(!academicNumber(value)||!(dt>0)||(state.typicalMonth&&!stamp.startsWith(state.typicalMonth)))return;
    const hour=Number(stamp.slice(11,13)),day=civilDate(stamp)?.getUTCDay(),scaled=relative?academicRatio(value*100,peak):value;
    if(!academicNumber(scaled)||!slots[0][hour])return;
    const slot=slots[day===0||day===6?1:0][hour];slot.sum+=scaled*dt;slot.dt+=dt;slot.n++;
    slot.min=Math.min(slot.min,scaled);slot.max=Math.max(slot.max,scaled);
  });
  const hours=Array.from({length:24},(_,i)=>i),unit=relative?'%':'kW';
  const note=clock+' · Weekends are Saturday and Sunday on the recorded calendar. Normalization uses the selected period peak.';
  academicPlot(root,'Typical day by local archive hour',hours,groups.map((name,j)=>
    academicTrace(name,slots[j].map(row=>academicRatio(row.sum,row.dt)))),unit,ctx,{categorical:true,axisLabel:'Hour of day',note});
  academicTable(root,'Typical day coverage and variability',['Day type','Hour','Timed samples','Valid hours','Mean ('+unit+')','Minimum','Maximum'],
    groups.flatMap((name,j)=>hours.map(hour=>{
      const x=slots[j][hour];return [name,hour,x.n,x.dt,academicRatio(x.sum,x.dt),academicValid(x.min),academicValid(x.max)];
    })),ctx,{note});
}

function academicForecastScores(actual,forecast) {
  const paired=academicValidPairs(actual,forecast),n=paired.length;
  if(!n)return null;
  let absolute=0,square=0,bias=0,den=0,symmetric=0,symmetricCount=0;
  for(const [a,f] of paired){
    const err=a-f;absolute+=Math.abs(err);square+=err*err;bias+=err;den+=Math.abs(a);
    const d=Math.abs(a)+Math.abs(f);
    if(d>0){symmetric+=200*Math.abs(err)/d;symmetricCount++;}
  }
  return [n,absolute/n,Math.sqrt(square/n),academicRatio(100*absolute,den),bias/n,
    academicRatio(symmetric,symmetricCount),symmetricCount];
}
async function academicForecastView(root,ctx,range,mode) {
  if(!academicForecast(ctx))return academicMissing(root,'Forecast verification requires timestamp-matched holdout actuals. This archive has no such evidence.');
  const state=academicState['Study Inputs'];
  const groups=['forecast','forecast by bus'].filter(group=>academicHas(ctx,group,'actual_kw')&&academicHas(ctx,group,'forecast_kw'));
  const group=groups.includes(state.forecastGroup)?state.forecastGroup:groups[0];
  const ids=academicIds(ctx,group).filter(id=>entityHasField(ctx.gallery.groups[group],id,'actual_kw')&&entityHasField(ctx.gallery.groups[group],id,'forecast_kw'));
  const primary=ids.find(id=>/^(total|system)$/i.test(id))||ids[0];
  const entity=ids.includes(state.forecastEntity)?state.forecastEntity:primary;
  const controls=elem('div',undefined,'controls');root.append(controls);
  academicPicker(controls,'Holdout scope',groups,group,value=>{state.forecastGroup=value;state.forecastEntity='';refreshWorkspace();});
  academicPicker(controls,'Series',ids,entity,value=>{state.forecastEntity=value;refreshWorkspace();});
  const fields=['actual_kw','forecast_kw'];
  const data=async id=>Promise.all(fields.map(field=>academicSeries(ctx,group,id,field,range).then(values=>
    values.map((v,i)=>range.valid[i]?v:null))));
  if(!entity)return academicMissing(root,'No aligned actual and forecast series were archived.');
  const [a,f]=await data(entity),pairs=academicValidPairs(a,f),errors=a.map((v,i)=>academicDelta(v,f[i]));
  if(!pairs.length)return academicMissing(root,'The selected period has no matched actuals and forecasts.');
  const note='Held-out timestamps · Error = actual minus forecast. Positive values indicate underprediction.';
  if(mode==='default'){
    academicPlot(root,'Actual and forecast',range.axis,[academicTrace('Holdout actual',a),academicTrace('Issued forecast',f)],'kW',ctx,{note});
    academicPlot(root,'Chronological forecast error',range.axis,[academicTrace('Actual − forecast',errors)],'kW',ctx,{note,zeroLine:true});
  }else if(mode==='scores'){
    const rows=[];
    for(const id of ids){
      const [x,y]=await data(id),scores=academicForecastScores(x,y);
      if(scores)rows.push([id,...scores,null]);
    }
    academicTable(root,'Accuracy by archived scope',['Series','Matched samples','MAE (kW)','RMSE (kW)','WAPE (%)','Bias (kW)',
      'sMAPE (%)','Positive sMAPE denominators','MASE'],rows,ctx,{open:true,note:
      'WAPE divides by summed absolute actual demand. sMAPE excludes pairs where both values are zero. Selected-window MASE requires the recorded training denominator.'});
    const saved=(ctx.archive.forecast_errors||[]).filter(row=>String(row.model||'').toUpperCase().indexOf('ARIMA')<0);
    if(saved.length){
      const keys=Object.keys(saved[0]);
      academicTable(root,'Saved full-holdout model metrics',keys.map(readable),saved.map(row=>keys.map(key=>row[key])),ctx,
        {note:'Original full-holdout metric scope and sign are defined by the saved model record.'});
    }
  }else if(mode==='peaks'){
    const days=new Map();
    for(const pair of pairs){
      const key=range.axis[pair[2]].slice(0,10);
      if(!days.has(key))days.set(key,[]);
      days.get(key).push(pair);
    }
    const rows=Array.from(days,([day,values])=>{
      const max=(side)=>values.reduce((x,y)=>y[side]>x[side]?y:x);
      const observed=max(0),predicted=max(1),aStamp=range.axis[observed[2]],fStamp=range.axis[predicted[2]];
      const validDuration=values.every(row=>range.durations[row[2]]>0);
      return [day,values.length,observed[0],predicted[1],observed[0]-predicted[1],aStamp,fStamp,
        (stampMillis(aStamp)-stampMillis(fStamp))/3600000,
        validDuration?academicSum(values.map(([x,y,i])=>(x-y)*range.durations[i])):null,Math.max(...values.map(([x,y])=>x-y))];
    });
    academicPlot(root,'Daily peak magnitude error',rows.map(r=>r[0]),[academicTrace('Actual peak − forecast peak',rows.map(r=>r[4]),'bar')],
      'kW',ctx,{categorical:true,zeroLine:true,note:'Earliest timestamp wins ties. Peak and timing use only matched samples.'});
    academicTable(root,'Daily peak and energy errors',['Day','Pairs','Actual peak (kW)','Forecast peak (kW)','Magnitude error (kW)',
      'Actual peak time','Forecast peak time','Timing error (h)','Energy error (kWh)','Largest actual minus forecast (kW)'],rows,ctx);
  }else{
    const sorted=pairs.slice().sort((x,y)=>x[0]-y[0]),axis=sorted.map(([actual])=>actual);
    academicPlot(root,'Actual vs forecast scatter',axis,[academicTrace('Forecast',sorted.map(([,forecast])=>forecast),'points'),
      academicTrace('1:1 reference',axis,'line',{dash:'dashed'})],'kW',ctx,
      {categorical:true,coordinates:axis,axisLabel:'Actual (kW)',note});
    const duration=academicDuration(errors,range);
    academicPlot(root,'Forecast residual distribution',duration.axis,[academicTrace('Error',duration.data)],'kW',ctx,
      {categorical:true,coordinates:duration.axis,axisLabel:'Elapsed exceedance (%)',note});
    const byMonth=new Map();
    pairs.forEach(pair=>{const month=range.axis[pair[2]].slice(0,7);if(!byMonth.has(month))byMonth.set(month,[]);byMonth.get(month).push(pair);});
    academicTable(root,'Monthly matched accuracy',['Month','Pairs','MAE (kW)','RMSE (kW)','WAPE (%)','Bias (kW)','sMAPE (%)','Valid sMAPE pairs'],
      Array.from(byMonth,([month,rows])=>[month,...academicForecastScores(rows.map(r=>r[0]),rows.map(r=>r[1]))]),ctx);
  }
}

async function academicPvView(root,ctx,range,mode) {
  const fields=[['available_pv_kw','Available PV'],['pv_input_kw','Utilized PV'],['curtailment_kw','Curtailed PV']];
  const units=ctx.archive.metadata?.pv_installations||[];
  const control=stamp=>academicLink('bus',String(units[0]?.bus_id||ctx.archive.metadata?.pv_buses?.[0]||''),stamp,ctx);
  const selected=academicState['Power & Energy'],ids=(ctx.archive.metadata?.pv_buses||[]).map(String).sort(academicNumeric);
  if(mode==='default'||mode==='events'){
    const picker=elem('div',undefined,'controls');root.append(picker);
    academicPicker(picker,'PV scope',['System',...ids],selected.pvEntity||'System',value=>{selected.pvEntity=value;refreshWorkspace();},
      id=>id==='System'?'System total':'Bus '+id);
    const entity=ids.includes(selected.pvEntity)?selected.pvEntity:'System',group=entity==='System'?'system':'bus';
    const inspect=stamp=>entity==='System'?control(stamp):academicLink('bus',entity,stamp,ctx);
    await academicChronology(root,ctx,range,'Available and utilized PV','kW',fields.slice(0,2),{group,entity,pick:inspect});
    await academicChronology(root,ctx,range,'PV curtailment over time','kW',[fields[2]],{group,entity,pick:inspect});
    if(mode==='events'){
      if(academicHas(ctx,'solar source','irradiance_w_m2'))await academicChronology(root,ctx,range,'Archived solar irradiance','W/m²',
        [['irradiance_w_m2','Irradiance']],{group:'solar source',entity:'System',pick:inspect});
      await academicChronology(root,ctx,range,'Associated grid and battery operation','kW',
        [['grid_export_kw','Grid export'],['bess_charge_kw','Gross charge'],['load_input_kw','Served demand']],{pick:inspect});
      await academicChronology(root,ctx,range,'Associated final voltage','pu',
        [['voltage_min_pu','Minimum'],['voltage_max_pu','Maximum']],{pick:inspect});
      root.append(elem('p','Select a timestamp to inspect retained control decisions. Irradiance provenance is listed under Inputs & Forecasting.','fine'));
    }
    return;
  }
  const energy=async(group,id)=>Promise.all(fields.map(([field])=>academicSeries(ctx,group,id,field,range)));
  const total=await energy('system','System');
  if(mode==='monthly'){
    const grouped=academicBuckets(range.axis,range.durations,total,academicPeriodKey(range),true,range.valid);
    const rows=grouped.map(r=>{
      const common=r.samples.every(n=>n===r.count);
      return [r.label,...r.sum,...(common?[academicRatio(r.sum[1]*100,r.sum[0]),academicRatio(r.sum[2]*100,r.sum[0])]:[null,null]),...r.hours];
    });
    academicPlot(root,'PV energy and curtailment by calendar period',rows.map(r=>r[0]),fields.map(([,name],i)=>
      academicTrace(name,rows.map(r=>r[i+1]),'bar')),'kWh',ctx,{categorical:true});
    academicTable(root,'PV energy and utilization',['Period','Available (kWh)','Utilized (kWh)','Curtailed (kWh)',
      'Utilization (%)','Curtailment (%)','Available hours','Utilized hours','Curtailed hours'],rows,ctx,{open:true});
    return;
  }
  const summarize=(id,values)=>{
    const matched=values[0].map((v,i)=>values.every(row=>academicNumber(row[i]))?v:null);
    const stats=values.map(row=>academicStats(row.map((v,i)=>academicNumber(matched[i])?v:null),range));
    const loads=units.filter(u=>id==='System'||String(u.bus_id)===id);
    const installed=loads.length&&loads.every(u=>academicNumber(u.p_rated_kw))?academicSum(loads.map(u=>u.p_rated_kw)):null;
    const [a,u,c]=stats.map(v=>v.energy),hours=stats[0].hours;
    return [id,installed,a,u,c,academicRatio(academicNumber(c)?100*c:null,a),academicRatio(academicNumber(u)?100*u:null,installed*hours),
      stats[1].maximum,hours,academicNumber(a)?a-u-c:null,academicSum(values[2].map((v,i)=>v>0?range.durations[i]||0:0))];
  };
  const rows=[summarize('System',total)];
  for(const id of ids)rows.push(summarize(id,await energy('bus',id)));
  academicPlot(root,'Curtailment by PV installation bus',ids,[academicTrace('Curtailed PV',rows.slice(1).map(r=>r[4]),'bar')],
    'kWh',ctx,{categorical:true,axisLabel:'Bus number',pick:i=>academicLink('bus',ids[i],range.axis[0],ctx)});
  academicTable(root,'PV system and installation statistics',['Scope','Installed (kW)','Available (kWh)','Used (kWh)','Curtailed (kWh)',
    'Curtailment (%)','Capacity factor (%)','Peak used (kW)','Matched hours','Available − used − curtailed (kWh)','Curtailing hours'],
    rows,ctx,{note:'Capacity factor uses utilized energy divided by rated capacity × matched hours.'});
}

const activeBalance=[['grid_import_kw','Grid import'],['pv_input_kw','Utilized PV'],['bess_discharge_kw','Battery discharge'],
  ['load_input_kw','Served load',-1],['bess_charge_kw','Battery charge',-1],['grid_export_kw','Grid export',-1],['loss_p_kw','Network losses',-1]];
const reactiveBalance=[['slack_q_kvar','Grid Q'],['pv_reactive_power_kvar','PV Q'],['bess_reactive_power_kvar','BESS Q'],
  ['served_load_kvar','Served load Q',-1],['loss_q_kvar','Network Q loss',-1]];
async function academicBalance(root,ctx,range,mode) {
  if(mode==='default'){
    for(const [unit,title,list] of [['kW','Signed active power balance',activeBalance],['kvar','Signed reactive power balance',reactiveBalance]]){
      const present=list.filter(([field])=>academicHas(ctx,'system',field));
      if(present.length)await academicChronology(root,ctx,range,title,unit,present,{stack:true,zeroLine:true});
      const missing=list.filter(([field])=>!academicHas(ctx,'system',field));
      if(missing.length)root.append(elem('p','Components unavailable: '+missing.map(([,label])=>label).join(', ')+'.','fine'));
    }
    return;
  }
  if(mode==='residual'){
    const rows=[];
    for(const [field,unit] of [['power_balance_residual_kw','kW'],['reactive_balance_residual_kvar','kvar']]){
      const values=await academicSys(ctx,field,range),v=academicSimpleStats(values.filter((_,i)=>range.valid[i]));
      if(!v.length)continue;
      const abs=v.map(Math.abs),stats=academicStats(values,range);
      rows.push([unit,v.length,stats.hours,Math.max(...abs),academicSum(abs)/v.length,Math.sqrt(academicSum(v.map(x=>x*x))/v.length)]);
      await academicChronology(root,ctx,range,'Recorded '+unit+' balance residual',unit,[[field,'Residual']],{zeroLine:true});
    }
    academicTable(root,'Balance residual checks',['Unit','Valid samples','Timed hours','Maximum absolute','Mean absolute','RMSE'],rows,ctx,
      {open:true,note:'Residuals are recorded solver outputs. The archived report does not define a separate balance residual acceptance tolerance.'});
    return;
  }
  const descriptors=mode==='grid'?activeBalance.filter(([f])=>['grid_import_kw','grid_export_kw','load_input_kw'].includes(f)):activeBalance;
  const values=await Promise.all(descriptors.map(([field])=>academicSys(ctx,field,range)));
  const matched=range.axis.map((_,i)=>range.valid[i]&&values.every(row=>academicNumber(row[i]))&&range.durations[i]>0);
  const stats=values.map(values=>academicStats(values.map((v,i)=>matched[i]?v:null),range));
  const rows=descriptors.map(([,label,sign=1],i)=>[label,stats[i].energy,stats[i].maximum,stats[i].peak,stats[i].hours,sign]);
  if(!matched.some(Boolean))return academicMissing(root,'There are no matched, timed readings for all components in this view.');
  if(mode==='grid'){
    const fraction=academicRatio(rows[0][1],rows[1][1]);
    await academicChronology(root,ctx,range,'Grid import and export','kW',[activeBalance[0],activeBalance[5]]);
    academicTable(root,'Grid dependency and extremes',['Quantity','Energy (kWh)','Peak (kW)','First peak','Matched hours'],
      rows.map(r=>r.slice(0,5)).concat([['Import energy / served energy (%)',fraction===null?null:100*fraction,null,null,stats[0].hours]]),ctx,
      {open:true,note:'Import-to-served ratio can exceed 100% because imports also supply losses and storage.'});
    return;
  }
  const supply=rows.filter(r=>r[5]===1),use=rows.filter(r=>r[5]===-1);
  const residual=academicSum(supply.map(r=>r[1]))-academicSum(use.map(r=>r[1]));
  const residualRecorded=await academicSys(ctx,'power_balance_residual_kw',range);
  const recorded=academicStats(residualRecorded.map((v,i)=>matched[i]?v:null),range);
  const note='AC energy on common valid steps · No source attribution to battery charging.';
  publicationSankey(root,ctx,'AC energy flow',supply.map(r=>r.slice(0,2)),use.map(r=>r.slice(0,2)),note);
  academicTable(root,'AC energy balance ledger',['Component','Energy (kWh)','Peak (kW)','First peak','Matched hours','Balance sign'],
    rows.concat([['Supply − uses',residual,null,null,stats[0].hours,null],
      ['Integrated recorded residual',recorded.energy,null,null,recorded.hours,null]]),ctx,{note});
}

async function academicService(root,ctx,range,mode) {
  const fields=[['requested_load_kw','Requested'],['load_input_kw','Served'],['shedding_kw','Shed']];
  if(mode==='default'){
    await academicChronology(root,ctx,range,'Requested, served and shed demand','kW',fields);
    const cases=Object.keys(ctx.archive.scenarios).map(id=>chartContext(ctx.key,id));
    const aligned=await Promise.all(cases.map(async ref=>{
      const stamps=await timeline(ref),f=stamps.indexOf(range.axis[0]),l=stamps.indexOf(range.axis.at(-1))+1;
      if(f<0||l<=f||stamps.slice(f,l).length!==range.axis.length||!stamps.slice(f,l).every((v,i)=>v===range.axis[i]))return null;
      const [shed,durations]=await Promise.all([academicSys(ref,'shedding_kw',{first:f,last:l}),
        academicSys(ref,'dt_hours',{first:f,last:l})]);
      const valid=range.valid.map((v,i)=>v&&durations[i]===range.durations[i]);
      return [ref,shed.map((v,i)=>valid[i]?v:null)];
    }));
    const picked=aligned.filter(Boolean);
    if(picked.length){
      const sameCoverage=range.valid.map((v,i)=>v&&picked.every(([,values])=>academicNumber(values[i])));
      const grouped=academicBuckets(range.axis,range.durations,picked.map(([,data])=>data),academicPeriodKey(range),true,sameCoverage);
      academicPlot(root,'ENS by calendar period',grouped.map(r=>r.label),picked.map(([ref],i)=>academicTrace(ref.data.label,
        grouped.map(r=>r.sum[i]),'bar',{scenarioLabel:ref.data.label})),'kWh',ctx,{categorical:true,note:'Matched valid time steps for the displayed cases.'});
    }
    return;
  }
  const group=ctx.gallery.groups['load output'];
  if(!group)return academicMissing(root,'Bus and category service records are unavailable.');
  const buses=academicIds(ctx,'load output').filter(id=>/^\d+$/.test(id)),cats=Object.keys(group.categories||{}).filter(id=>group.entities[id]);
  const ids=mode==='spatial'?['Total',...cats,...buses]:['Total',...buses];
  const system=Array.from({length:range.axis.length},()=>({known:0,affected:0,full:0}));
  const rows=[];
  const bins=[0,0,0,0],eps=1e-6,relative=1e-6;
  let nested50=0,nested80=0,validDemandBusHours=0;
  const feasible=await academicSys(ctx,'feasible',range);
  for(const id of ids){
    const values=await Promise.all(fields.map(([field])=>academicSeries(ctx,'load output',id,field,range)));
    const [requested,served,shed]=values,matched=range.valid.map((valid,i)=>valid&&values.every(row=>academicNumber(row[i])));
    const stats=values.map(row=>academicStats(row.map((v,i)=>matched[i]?v:null),range));
    const [r,s,d]=stats.map(v=>v.energy),rate=academicRatio(academicNumber(s)?100*s:null,r);
    let affected=0,full=0;
    const actualBus=buses.includes(id);
    const archivedOutage=actualBus?await academicSeries(ctx,'bus',id,'fully_disconnected',range):[];
    for(let i=0;i<range.axis.length;i++){
      const dt=range.durations[i];
      if(!matched[i]||!(dt>0)||(feasible[i]!==1&&feasible[i]!==true))continue;
      if(actualBus)system[i].known++;
      if(requested[i]<=eps)continue;
      const ratio=1-Math.min(1,Math.max(0,served[i]/requested[i]));
      const disconnected=academicNumber(archivedOutage[i])?archivedOutage[i]===1:
        served[i]<=Math.max(eps,relative*requested[i]);
      if(shed[i]>eps){affected+=dt;if(actualBus)system[i].affected++;}
      if(disconnected){full+=dt;if(actualBus)system[i].full++;}
      if(!actualBus)continue;
      validDemandBusHours+=dt;
      if(shed[i]>eps)bins[disconnected?3:ratio>.8+relative?2:ratio>.5+relative?1:0]+=dt;
      if(ratio>.5+relative)nested50+=dt;
      if(ratio>.8+relative)nested80+=dt;
    }
    rows.push([id,categoryLabel(group,id),r,s,d,rate,stats[2].maximum,stats[2].peak,affected,full,stats[0].hours,
      academicNumber(r)?r-s-d:null]);
  }
  const stamp=range.axis[0];
  if(mode==='spatial'){
    const spatial=rows.filter(r=>buses.includes(r[0]));
    academicPlot(root,'ENS by bus',spatial.map(r=>r[0]),[academicTrace('Unserved energy',spatial.map(r=>r[4]),'bar')],
      'kWh',ctx,{categorical:true,axisLabel:'Bus number',pick:i=>academicLink('bus',spatial[i][0],spatial[i][7]||stamp,ctx)});
  }else{
    const axis=['Up to 50%','Over 50–80%','Over 80%, partial','Full disconnection'];
    academicPlot(root,'Shedding severity by affected bus-hour',axis,[academicTrace('Disjoint bins',
      validDemandBusHours?bins:bins.map(()=>null),'bar')],'bus-hours',ctx,
      {categorical:true,note:'Uses 1e−6 kW activity tolerance and 1e−6 relative threshold padding. Nested thresholds are tabulated separately.'});
  }
  let events=0,longest=0,length=0,end=null,validHours=0,affectedHours=0,fullHours=0,busHours=0;
  system.forEach((step,i)=>{
    const dt=range.durations[i],start=stampMillis(range.axis[i]);
    if(!buses.length||step.known!==buses.length||!(dt>0)){length=0;end=null;return;}
    validHours+=dt;busHours+=step.affected*dt;
    if(step.full>0)fullHours+=dt;
    if(!step.affected){length=0;end=null;return;}
    affectedHours+=dt;
    if(end!==start){events++;length=0;}
    length+=dt;end=start+dt*3600000;longest=Math.max(longest,length);
  });
  academicTable(root,'System service and severity',['Measure','Value'],[
    ['System observed hours with shedding',validHours?affectedHours:null],['Observed affected bus-hours',validHours?busHours:null],
    ['System hours with complete disconnection of any bus',validHours?fullHours:null],
    ['Valid full-bus coverage (h)',validHours],['Valid positive-demand bus-hours',validDemandBusHours],
    ['Nested >50% bus-hours',validDemandBusHours?nested50:null],['Nested >80% bus-hours',validDemandBusHours?nested80:null],
    ['Observed shedding events',validHours?events:null],['Longest observed event (h)',validHours?longest:null]],
    ctx,{open:true,note:'Gaps, invalid hours and zero-shedding hours split events. Incomplete coverage can split a real interruption.'});
  academicTable(root,'Service and energy not supplied',['ID','Scope','Requested (kWh)','Served (kWh)','ENS (kWh)','Service (%)',
    'Peak shed (kW)','First peak timestamp','Shedding hours','Disconnection hours','Matched hours','Requested − served − shed (kWh)'],
    rows,ctx,{renderCell(cell,id,i){
      if(i!==0||!buses.includes(String(id)))return false;
      button(cell,String(id),()=>academicLink('bus',id,rows.find(r=>r[0]===id)?.[7]||stamp,ctx));return true;
    }});
  button(root,'Open recorded corrective-decision ledger',()=>{galleryState.scenario=ctx.scenario;screen='Decisions';tabs();render();});
}
function academicBatterySettings(ctx,unit) {
  const meta=ctx.archive.metadata||{},economic=ctx.archive.manifest.economics||{};
  const defaults=meta.context?.['Fleet battery parameters']||{};
  const p=unit.power_rating_kw,e=unit.energy_capacity_kwh;
  const factor=meta.optimizer?.inverter_kva_per_kw??meta.context?.['Effective inverter sizing (kVA/kW)']??economic.inverter_kva_per_kw;
  return {...defaults,...unit,p,e,kva:unit.inverter_rating_kva??(academicNumber(factor)&&academicNumber(p)?factor*p:null)};
}
function academicBatteryStats(u,range){
  const cfg=u.cfg,charge=academicStats(u.charge,range),discharge=academicStats(u.discharge,range);
  const before=u.pre[0],after=u.post.at(-1),change=academicNumber(before)&&academicNumber(after)&&academicNumber(cfg.e)?
    (after-before)*cfg.e:null;
  const complete=range.durations.every((dt,i)=>dt>0&&(i===0||
    stampMillis(range.axis[i])===stampMillis(range.axis[i-1])+range.durations[i-1]*3600000));
  const conversion=complete&&charge.count===range.axis.length&&discharge.count===range.axis.length&&academicNumber(change)?
    charge.energy-discharge.energy-change:null;
  const stats=academicStats(u.post,range),samples=[...u.pre,...u.post].filter(academicNumber);
  const lo=samples.length?Math.min(...samples):null,hi=samples.length?Math.max(...samples):null;
  const capacity=[cfg.soc_min,cfg.soc_max,cfg.e].every(academicNumber)?cfg.e*(cfg.soc_max-cfg.soc_min):null;
  const span=academicNumber(capacity)&&academicNumber(hi)&&academicNumber(lo)?(hi-lo)*cfg.e:null;
  const hours=test=>stats.count?academicSum(u.p.map((v,i)=>academicNumber(v)&&test(v,i)?range.durations[i]||0:0)):null;
  const eps=1e-9,cycles=academicNumber(discharge.energy)&&cfg.eta_discharge>0&&cfg.e>0?discharge.energy/cfg.eta_discharge/cfg.e:null;
  return {lo,hi,capacity,span,stats,charge,discharge,before,after,change,conversion,cycles,nearRated:cfg.p>0?
    hours(v=>Math.abs(v)>=.9*cfg.p):null,charging:hours(v=>v<-eps),discharging:hours(v=>v>eps),idle:hours(v=>Math.abs(v)<=eps),
    atMin:academicNumber(cfg.soc_min)?hours((_,i)=>academicNumber(u.post[i])&&Math.abs(u.post[i]-cfg.soc_min)<=eps):null,
    atMax:academicNumber(cfg.soc_max)?hours((_,i)=>academicNumber(u.post[i])&&Math.abs(u.post[i]-cfg.soc_max)<=eps):null};
}
async function academicBessView(root,ctx,range,mode) {
  const state=academicState.BESS,units=academicRunUnits(ctx).map(unit=>academicBatterySettings(ctx,unit));
  const ids=units.length?units.map(u=>String(u.bus_id)).sort(academicNumeric):academicIds(ctx,'battery');
  if(!ids.length)return academicMissing(root,'No archived battery unit data are available.');
  const unit=ids.includes(state.bessEntity)?state.bessEntity:'Fleet';
  academicPicker(root,'Battery',['Fleet',...ids],unit,value=>{state.bessEntity=value;refreshWorkspace();},id=>id==='Fleet'?'Fleet':'Bus '+id);
  const selected=unit==='Fleet'?ids:[unit],batteries=[];
  const read=async(id,field)=>academicSeries(ctx,'battery',id,field,range).then(values=>values.map((v,i)=>range.valid[i]?v:null));
  for(const id of selected){
    const cfg=units.find(u=>String(u.bus_id)===id)||{};
    let [p,q,pre,post]=await Promise.all(['power_kw','reactive_power_kvar','soc_before','soc_after'].map(field=>read(id,field)));
    if(!p.some(academicNumber)&&ids.length===1){
      p=await academicSeries(ctx,'bus',id,'bess_input_kw',range);
      q=await academicSeries(ctx,'bus',id,'bess_input_kvar',range);
      post=(await academicSeries(ctx,'bus',id,'bess_soc_percent',range)).map(v=>academicNumber(v)?v/100:null);
    }
    batteries.push({id,cfg,p,q,pre,post,charge:p.map(v=>academicNumber(v)?Math.max(0,-v):null),
      discharge:p.map(v=>academicNumber(v)?Math.max(0,v):null)});
  }
  const gross=field=>range.axis.map((_,i)=>batteries.every(u=>academicNumber(u[field][i]))?
    academicSum(batteries.map(u=>u[field][i])):null);
  const stats=batteries.map(u=>academicBatteryStats(u,range)),axis=batteries.map(u=>u.id);
  const inspect=i=>academicLink('bus',batteries[0].id,range.axis[i],ctx);
  if(mode==='default'){
    const power=unit==='Fleet'?[academicTrace('Gross AC charge',gross('charge').map(v=>academicNumber(v)?-v:null)),
      academicTrace('Gross AC discharge',gross('discharge'))]:batteries.map(u=>academicTrace('Bus '+u.id,u.p));
    academicPlot(root,'Battery dispatch',range.axis,power,'kW',ctx,{note:'Charging is negative. Discharging is positive.',zeroLine:true,pick:inspect});
    const weight=academicSum(batteries.map(u=>u.cfg.e||0));
    const soc=weight>0&&batteries.every(u=>u.cfg.e>0)&&unit==='Fleet'?
      [academicTrace('Capacity-weighted fleet SOC',range.axis.map((_,i)=>batteries.every(u=>academicNumber(u.post[i]))?
        100*academicSum(batteries.map(u=>u.post[i]*u.cfg.e))/weight:null))]:
      batteries.map(u=>academicTrace('Bus '+u.id+' end SOC',u.post.map(v=>academicNumber(v)?100*v:null)));
    if(unit!=='Fleet'){
      const u=batteries[0];
      soc.unshift(academicTrace('Start SOC',u.pre.map(v=>academicNumber(v)?100*v:null),'line',{dash:'dashed'}));
      for(const [field,name] of [['soc_min','Minimum SOC'],['soc_max','Maximum SOC'],['soc_initial','Initial reference']]){
        if(academicNumber(u.cfg[field]))soc.push(academicTrace(name,range.axis.map(()=>100*u.cfg[field]),'line',{dash:'dashed'}));
      }
    }
    academicPlot(root,'Battery state of charge',range.axis,soc,'%',ctx,{note:'SOC boundaries follow each recorded step.',pick:inspect});return;
  }
  if(mode==='reactive'){
    const first=batteries[0],sim=academicLimits(ctx);
    academicPlot(root,'Battery reactive power',range.axis,batteries.map(u=>academicTrace('Bus '+u.id,u.q)),'kvar',ctx,
      {zeroLine:true,pick:inspect});
    const points=academicValidPairs(first.p,first.q).sort(([p],[q])=>p-q);
    const pf=sim.minimum_discharge_pf,s=first.cfg.kva,p=first.cfg.p;
    const canDraw=pf>0&&pf<=1&&s>0&&p>0&&sim.fleet_dispatch_mode==='daily_milp_dispatch';
    const cap=canDraw?Array.from({length:61},(_,i)=>Math.min(p,s)*i/60):[];
    const top=cap.map(p=>Math.min(Math.sqrt(Math.max(0,s*s-p*p)),p*Math.sqrt(1/(pf*pf)-1)));
    const marks=points.map(([p,q])=>({p,q}));
    for(const v of cap)marks.push({p:v,q:null});
    if(canDraw)marks.push({p:-p,q:null});
    marks.sort((a,b)=>a.p-b.p);
    const positions=marks.map(mark=>mark.p);
    const upper=new Map(cap.map((p,i)=>[p,top[i]]));
    const traces=[academicTrace('Operating points',marks.map(mark=>mark.q),'points')];
    if(canDraw){
      traces.push(academicTrace('Maximum discharge Q',positions.map(v=>{
        if(v<0||v>Math.min(p,s))return null;
        return upper.get(v)??Math.min(Math.sqrt(Math.max(0,s*s-v*v)),v*Math.sqrt(1/(pf*pf)-1));
      })));
      traces.push(academicTrace('Q = 0',positions.map(v=>v>=-Math.min(p,s)&&v<=Math.min(p,s)?0:null),'line',{dash:'dashed'}));
    }
    academicPlot(root,'Recorded P–Q operation at bus '+first.id,positions,traces,'kvar',ctx,
      {categorical:true,coordinates:positions,axisLabel:'AC active power (kW)',note:'Archived inverter '+workspaceNumber(s,'kVA')+
        ' · Minimum discharge PF '+(pf??'unavailable')+' · '+(canDraw?'Inverter and discharge PF bounds; other dispatch limits may apply.':'Capability boundary unavailable for this archived dispatch policy.')});
    academicTable(root,'P/Q and power factor',['Timestamp','Active (kW)','Reactive (kvar)','Apparent (kVA)','Power factor'],
      points.map(([p,q,i])=>[range.axis[i],p,q,Math.hypot(p,q),academicRatio(Math.abs(p),Math.hypot(p,q))]),ctx);
    return;
  }
  if(mode==='restoration'){
    const fields=['soc_start','soc_end','energy_difference_kwh','soc_restored','pf_violation_hours','hours'];
    const rows=[],daily=ctx.gallery.groups['battery daily audit'],span=[];
    for(const u of batteries){
      const by=new Map();
      range.axis.forEach((stamp,i)=>{
        const vals=[u.pre[i],u.post[i]].filter(academicNumber),dt=range.durations[i];
        if(!vals.length||!(dt>0))return;
        const d=stamp.slice(0,10),r=by.get(d)||{low:Infinity,high:-Infinity,h:0};
        r.low=Math.min(r.low,...vals);r.high=Math.max(r.high,...vals);r.h+=dt;by.set(d,r);
      });
      for(const [d,r] of by)span.push([u.id,d,r.h,r.low*100,r.high*100,(r.high-r.low)*100]);
      if(!daily?.entities[u.id])continue;
      const data=await Promise.all(fields.map(field=>academicSeries(ctx,'battery daily audit',u.id,field,range)));
      range.axis.forEach((stamp,i)=>{
        if(academicNumber(data[0][i]))rows.push([u.id,stamp,data[5][i],data[0][i],data[1][i],data[2][i],
          data[3][i]===1?'Verified':data[3][i]===0?'Failed':'Unavailable',data[4][i],academicLimits(ctx).daily_soc_tolerance_kwh]);
      });
    }
    const first=span.filter(r=>r[0]===batteries[0].id);
    academicPlot(root,'Intraday SOC extrema at bus '+batteries[0].id,first.map(r=>r[1]),[academicTrace('Minimum',first.map(r=>r[3])),
      academicTrace('Maximum',first.map(r=>r[4]))],'%',ctx,{categorical:true,note:'Recorded start and end step boundaries.'});
    academicTable(root,'Daily SOC range',['Bus ID','Day','Valid hours','Minimum SOC (%)','Maximum SOC (%)','Range (pp)'],span,ctx);
    academicTable(root,'Recorded restoration audit',['Bus ID','Closing timestamp','Duration (h)','Initial SOC','Final SOC',
      'Energy deviation (kWh)','Saved status','PF violation hours','Configured duration tolerance (kWh)'],rows,ctx,
      {open:true,note:'Uses the saved daily audit. Missing days do not establish compliance.'});return;
  }
  if(mode==='monthly'){
    const grouped=academicBuckets(range.axis,range.durations,[gross('charge'),gross('discharge'),gross('q')],s=>s.slice(0,7),true,range.valid);
    academicPlot(root,'Monthly gross AC throughput',grouped.map(r=>r.label),[academicTrace('Charge',grouped.map(r=>r.sum[0]),'bar'),
      academicTrace('Discharge',grouped.map(r=>r.sum[1]),'bar')],'kWh',ctx,{categorical:true});
    academicTable(root,'Monthly battery throughput',['Month','Charge (kWh)','Discharge (kWh)','Reactive (kvarh)','Charge hours',
      'Discharge hours','Reactive hours'],grouped.map(r=>[r.label,...r.sum,...r.hours]),ctx);return;
  }
  if(mode==='duration'){
    for(const [field,name] of [['charge','Gross AC charge'],['discharge','Gross AC discharge']]){
      const d=academicDuration(gross(field),range);
      academicPlot(root,name+' duration',d.axis,[academicTrace(name,d.data)],'kW',ctx,
        {categorical:true,coordinates:d.axis,axisLabel:'Elapsed exceedance (%)',note:fmt(d.hours)+' h of valid timed samples.'});
    }
    academicTable(root,'Operation duration and equivalent full cycles',['Bus ID','Charge hours','Discharge hours','Idle hours',
      'Hours ≥90% of rated power','Hours at SOC minimum','Hours at SOC maximum','Stored-energy-side full cycles'],
      batteries.map((u,i)=>{const s=stats[i];return [u.id,s.charging,s.discharging,s.idle,s.nearRated,s.atMin,s.atMax,s.cycles];}),ctx,
      {open:true,note:'Active power tolerance 1e−9 kW. Cycles divide AC discharge by discharge efficiency and nameplate energy.'});return;
  }
  if(mode==='sizing'){
    academicPlot(root,'Rated power and observed peaks',axis,[academicTrace('Rated',batteries.map(u=>u.cfg.p),'bar'),
      academicTrace('Peak charge',stats.map(s=>s.charge.maximum),'bar'),academicTrace('Peak discharge',stats.map(s=>s.discharge.maximum),'bar')],
      'kW',ctx,{categorical:true,axisLabel:'Battery bus'});
    academicPlot(root,'Rated, usable and observed storage span',axis,[academicTrace('Nameplate',batteries.map(u=>u.cfg.e),'bar'),
      academicTrace('Usable energy',stats.map(s=>s.capacity),'bar'),academicTrace('Observed SOC span',stats.map(s=>s.span),'bar')],
      'kWh',ctx,{categorical:true,axisLabel:'Battery bus'});
  }
  academicTable(root,'Per-unit operation, sizing and storage balance',['Bus ID','Rated kW','Rated kWh','Inverter kVA','Duration (h)',
    'C-rate (1/h)','Usable (kWh)','Observed span (kWh)','Span / usable','Peak charge (kW)','Peak discharge (kW)','Peak discharge / rated',
    'Gross AC charge (kWh)','Gross AC discharge (kWh)','SOC min','SOC max','Mean end SOC','First start SOC','Last end SOC',
    'Stored energy change (kWh)','Conversion loss (kWh)','Valid dispatch hours'],batteries.map((u,i)=>{
    const c=u.cfg,s=stats[i];
    return [u.id,c.p,c.e,c.kva,academicRatio(c.e,c.p),academicRatio(c.p,c.e),s.capacity,s.span,academicRatio(s.span,s.capacity),
      s.charge.maximum,s.discharge.maximum,academicRatio(s.discharge.maximum,c.p),s.charge.energy,s.discharge.energy,s.lo,s.hi,
      s.stats.mean,s.before,s.after,s.change,s.conversion,s.charge.hours];
  }),ctx,{open:true,note:'Conversion loss = gross AC charge − gross AC discharge − stored-energy change over continuous covered steps.'});
  if(mode==='audit'){
    const rows=batteries.map(u=>{
      const sim=academicLimits(ctx),cfg=u.cfg,tests=[[],[],[],[]];
      u.p.forEach((p,i)=>{
        const q=u.q[i],s=u.post[i],dt=range.durations[i],a=academicNumber(p)&&academicNumber(q)?Math.hypot(p,q):null;
        if(!(dt>0))return;
        const v=[academicNumber(p)&&academicNumber(cfg.p)?Math.abs(p)-cfg.p:null,academicNumber(a)&&academicNumber(cfg.kva)?a-cfg.kva:null,
          [s,cfg.soc_min,cfg.soc_max].every(academicNumber)?Math.max(cfg.soc_min-s,s-cfg.soc_max):null,
          p>1e-9&&academicNumber(a)&&academicNumber(sim.minimum_discharge_pf)?sim.minimum_discharge_pf-p/a:null];
        v.forEach((x,j)=>{if(academicNumber(x))tests[j].push([x,dt]);});
      });
      return [u.id,...tests.flatMap(list=>[list.length?academicSum(list.filter(([v])=>v>0).map(([,dt])=>dt)):null,
        academicSum(list.map(([,dt])=>dt))])];
    });
    academicTable(root,'Strict observed limits',['Bus ID','P outside (h)','P checked (h)','kVA outside (h)','kVA checked (h)',
      'SOC outside (h)','SOC checked (h)','Discharge PF outside (h)','Discharge PF checked (h)'],rows,ctx,
      {note:'Strict comparisons retain roundoff. The recorded daily audit provides the tolerance-based status.'});
    button(root,'Inspect recorded dispatch and corrective actions',()=>{galleryState.scenario=ctx.scenario;screen='Decisions';tabs();render();});
  }
}
const academicLedger=[
  ['annual_grid_purchases','Grid purchases',1],['annual_export_credit','Export credit',-1],
  ['annual_shedding_cost','Shedding penalty',1],['annual_curtailment_cost','Curtailment penalty',1],
  ['annual_terminal_inventory_adjustment','Terminal inventory',1],['annual_bess_capital_cost','Capital recovery',1],
  ['annual_bess_om_cost','Annual O&M',1]
];
function academicLedgerRows(ctx){
  const m=asMetrics(ctx.data);
  return academicLedger.map(([key,name,sign])=>[name,academicNumber(m[key])?m[key]*sign:
    key==='annual_terminal_inventory_adjustment'&&academicNumber(m.annual_operating_cost)&&m.annual_operating_cost===
      m.annual_grid_cost+m.annual_curtailment_cost+m.annual_shedding_cost?0:null]);
}
function academicCapitalFactor(e){
  if(!(e.lifetime_years>0))return null;
  if(e.annualization_method==='straight_line')return 1/e.lifetime_years;
  if(e.annualization_method!=='real_crf'||!academicNumber(e.nominal_interest_rate)||!academicNumber(e.annual_inflation_rate)||
    e.annual_inflation_rate<=-1)return null;
  const r=(1+e.nominal_interest_rate)/(1+e.annual_inflation_rate)-1,n=e.lifetime_years;
  if(Math.abs(r)<1e-12)return 1/n;
  return r>-1?r/(1-Math.pow(1+r,-n)):null;
}
async function academicEconomics(root,ctx,range,mode){
  const currency=ctx.archive.manifest.currency||'Archived currency',e=ctx.archive.manifest.economics||{},unit=currency+'/year';
  const ledger=academicLedgerRows(ctx),total=academicMetric(ctx,'annual_total_cost'),state=academicState.Economics;
  const verifiedYear=[8760,8784].includes(academicMetric(ctx,'duration_hours'))&&ctx.data.diagnostic?.known_status&&
    ctx.data.diagnostic.nonconverged===0&&ctx.data.descriptor?.control_mode!=='uncontrolled'&&
    asMetrics(ctx.data).feasible===true;
  if(mode==='default'&&!verifiedYear){
    root.append(elem('p','The archived coverage does not establish a verified annual objective. Showing period operating costs.','fine'));
    return academicEconomics(root,ctx,range,'monthly');
  }
  if(mode==='monthly'){
    const values=await Promise.all(['grid_purchase_cost','grid_export_credit','shedding_cost','curtailment_cost']
      .map(field=>academicSys(ctx,field,range)));
    const groups=academicBuckets(range.axis,range.durations,values,s=>s.slice(0,7),false,range.valid);
    const rows=groups.map(r=>[r.label,r.sum[0],academicNumber(r.sum[1])?-r.sum[1]:null,r.sum[2],r.sum[3],
      r.samples.every(n=>n===r.count)?r.sum[0]-r.sum[1]+r.sum[2]+r.sum[3]:null,...r.samples]);
    academicPlot(root,'Monthly operating ledger',rows.map(r=>r[0]),['Purchases','Export credit','ENS penalty','Curtailment penalty']
      .map((name,i)=>academicTrace(name,rows.map(r=>r[i+1]),'bar')),currency,ctx,{categorical:true,zeroLine:true});
    academicTable(root,'Recorded monthly operating costs',['Month','Purchases','Export credit','Shedding penalty','Curtailment penalty',
      'Net operating cost','Purchase samples','Export samples','Shedding samples','Curtailment samples'],rows,ctx,{note:'Currency: '+currency+
      '. Uses recorded hourly amounts. Annual ownership and terminal inventory stay in the annual ledger.'});return;
  }
  if(mode==='investment'){
    const rows=academicRunUnits(ctx).map(unit=>{
      const b=academicBatterySettings(ctx,unit),power=e.power_cost_basis==='kva'?b.kva:e.power_cost_basis==='kw'?b.p:null;
      const p=academicNumber(power)&&academicNumber(e.cost_per_kw)?power*e.cost_per_kw:null;
      const k=academicNumber(b.e)&&academicNumber(e.cost_per_kwh)?b.e*e.cost_per_kwh:null;
      return [b.bus_id,b.p,b.e,b.kva,e.power_cost_basis,p,k,academicNumber(p)&&academicNumber(k)?p+k:null];
    });
    academicTable(root,'Initial investment by battery',['Bus ID','Rating (kW)','Capacity (kWh)','Inverter (kVA)','Cost basis',
      'Power CAPEX','Energy CAPEX','Initial investment'],rows,ctx,{open:true,note:currency+' · Coefficients from the archived study.'});
    academicTable(root,'Archived economic assumptions',['Parameter','Value'],Object.entries(e).map(([k,v])=>[readable(k),displayRecord(v)])
      .concat([['Effective real interest',academicNumber(e.nominal_interest_rate)&&academicNumber(e.annual_inflation_rate)&&e.annual_inflation_rate>-1?
        (1+e.nominal_interest_rate)/(1+e.annual_inflation_rate)-1:null],['Capital recovery factor',academicCapitalFactor(e)],
        ['Recorded initial CAPEX',academicMetric(ctx,'bess_cost')]]),ctx,{note:'Uses the archived real-discount capital recovery or straight-line method.'});return;
  }
  if(mode==='sensitivity'){
    if(!verifiedYear||!academicNumber(total)||!academicNumber(e.grid_import_tariff_per_kwh))
      return academicMissing(root,'Accounting sensitivity requires a verified annual ledger and an archived import tariff.');
    const inventory=ledger.find(([label])=>label==='Terminal inventory')[1];
    const imported=academicMetric(ctx,'grid_import_energy_kwh'),exported=academicMetric(ctx,'grid_export_energy_kwh');
    const specs=[
      ['grid_import_tariff_per_kwh','Import tariff',inventory===0?imported:null],
      ['grid_export_tariff_per_kwh','Export tariff',academicNumber(exported)?-exported:null],
      ['shedding_penalty_per_kwh','ENS penalty',academicMetric(ctx,'load_shedding_energy_kwh')],
      ['curtailment_penalty_per_kwh','Curtailment penalty',academicMetric(ctx,'curtailment_energy_kwh')]
    ].filter(([key,,energy])=>academicNumber(e[key])&&academicNumber(energy));
    const capex=academicMetric(ctx,'bess_cost'),cap=academicMetric(ctx,'annual_bess_capital_cost'),om=academicMetric(ctx,'annual_bess_om_cost');
    const allowOwnership=[capex,cap,om,e.annual_om_fraction,academicCapitalFactor(e)].every(academicNumber);
    const controls=elem('div',undefined,'controls');root.append(controls);
    const available=specs.concat(allowOwnership?[
      ['lifetime_years','Lifetime (years)',null],['annual_om_fraction','Annual O&M fraction',null],['capex_multiplier','Initial CAPEX multiplier',null]]:[]);
    const inputs=available.map(([key,label])=>{
      const name=elem('label',label),input=elem('input');input.type='number';input.step='any';
      input.min=key==='lifetime_years'?1:0;
      input.value=state.accounting?.[key]??e[key]??1;name.append(input);controls.append(name);return input;
    });
    const result=elem('div');root.append(result);
    function paint(){
      if(inputs.some(input=>!input.value||!input.checkValidity()))return;
      const trial=state.accounting=Object.fromEntries(available.map(([key],i)=>[key,Number(inputs[i].value)]));
      const rows=specs.map(([key,label,energy])=>[label,e[key],trial[key],energy,(trial[key]-e[key])*energy]);
      if(allowOwnership){
        const rate=academicCapitalFactor({...e,...trial}),newCapex=capex*trial.capex_multiplier;
        rows.push(['Capital recovery',academicCapitalFactor(e),rate,null,newCapex*rate-cap],
          ['Annual O&M',e.annual_om_fraction,trial.annual_om_fraction,null,newCapex*trial.annual_om_fraction-om]);
      }
      const delta=academicSum(rows.map(r=>r[4]));
      result.replaceChildren();
      academicTable(result,'Fixed-dispatch accounting sensitivity',['Component','Archived coefficient','Trial coefficient','Signed annual energy (kWh)',
        'Cost change ('+unit+')'],rows.concat([['Archived annual total',null,null,null,total],['Trial annual total',null,null,null,total+delta]]),
        ctx,{open:true,note:'Physical results and optimization are held fixed. Import tariff is editable only where terminal inventory is verified zero.'});
    }
    inputs.forEach(input=>{input.onchange=paint;});paint();
    button(controls,'Restore archived rates',()=>{state.accounting={};refreshWorkspace();});return;
  }
  academicPlot(root,'Annualized cost breakdown',ledger.map(r=>r[0]),[academicTrace('Signed components',ledger.map(r=>r[1]),'bar')],
    unit,ctx,{categorical:true,zeroLine:true,note:'Credit is negative. Initial investment is listed separately.'});
  const sum=ledger.every(r=>academicNumber(r[1]))?academicSum(ledger.map(r=>r[1])):null;
  academicTable(root,'Annual cost reconciliation',['Component','Value ('+unit+')'],
    ledger.concat([['Sum of complete ledger',sum],['Recorded annual objective',total],['Recorded total minus sum',academicDelta(total,sum)]]),
    ctx,{note:'Missing ledger items are unavailable. This report applies no additional time scaling.'});
  const alternatives=Object.keys(ctx.archive.scenarios).filter(id=>id!==ctx.scenario);
  if(!alternatives.length)return;
  const ref=chartContext(ctx.key,alternatives.includes(state.reference)?state.reference:alternatives[0]);
  academicPicker(root,'Waterfall reference scenario',alternatives,ref.scenario,value=>{state.reference=value;refreshWorkspace();},
    id=>ctx.archive.scenarios[id].label);
  const refTotal=academicMetric(ref,'annual_total_cost'),base=academicLedgerRows(ref);
  const deltas=ledger.map(([name,value],i)=>[name,academicDelta(value,base[i][1])]);
  if(academicMetric(ref,'duration_hours')!==academicMetric(ctx,'duration_hours')||asMetrics(ref.data).feasible!==true||
    ref.data.diagnostic?.nonconverged!==0||!academicNumber(refTotal)||!academicNumber(total)||!deltas.every(r=>academicNumber(r[1])))
    return academicMissing(root,'A complete signed annual ledger is required for both waterfall cases.');
  const residual=total-refTotal-academicSum(deltas.map(r=>r[1]));
  publicationWaterfall(root,ctx,'Annual cost benefit waterfall',refTotal,deltas.concat([['Reconciliation residual',residual]]),total,unit,ref.data.label);
  const served=academicMetric(ctx,'served_load_energy_kwh');
  academicTable(root,'Economic change against reference',['Measure','Value'],[
    ['Reference annual cost',refTotal],['Candidate annual cost',total],['Net modeled benefit',refTotal-total],
    ['Avoided operating cost',academicDelta(academicMetric(ref,'annual_operating_cost'),academicMetric(ctx,'annual_operating_cost'))],
    ['Candidate initial CAPEX',academicMetric(ctx,'bess_cost')],['Candidate annual cost per served MWh',academicRatio(total,served>0?served/1000:null)],
    ['Reconciliation residual',residual]],ctx,{note:unit+' except initial CAPEX and cost per served MWh.'});
}

const academicCompareMeasures=[
  ['ENS (kWh)','load_shedding_energy_kwh'],['Served demand (kWh)','served_load_energy_kwh'],
  ['PV curtailment (kWh)','curtailment_energy_kwh'],['Active losses (kWh)','loss_energy_kwh'],
  ['Minimum voltage (pu)','voltage_min_pu'],['Maximum voltage (pu)','voltage_max_pu'],
  ['Voltage violation hours','voltage_violation_hours'],['Grid import (kWh)','grid_import_energy_kwh'],
  ['Grid export (kWh)','grid_export_energy_kwh'],['Annual cost','annual_total_cost'],
  ['Study duration (h)','duration_hours'],['Requested demand (kWh)','requested_load_energy_kwh'],
  ['Severe >80% shedding (bus-hours)','buses_shed_over_80_percent_hours'],['Disconnected bus-hours','fully_disconnected_bus_hours'],
  ['Installed BESS power (kW)','fleet_power'],['Installed BESS energy (kWh)','fleet_energy'],
  ['Run time (s)','runtime'],['GA generations','generations'],
];
function academicCompareValue(ctx,key){
  const units=academicRunUnits(ctx);
  if(key.startsWith('fleet_')){
    const field=key==='fleet_power'?'power_rating_kw':'energy_capacity_kwh';
    return units.length?academicSum(units.map(u=>u[field])):ctx.data.has_bess===false?0:null;
  }
  if(key==='runtime')return academicValid(ctx.archive.metadata?.context?.['Run duration (seconds)']);
  if(key==='generations')return academicValid(ctx.archive.metadata?.optimizer?.fleet_ga_optimizer?.generations);
  return academicMetric(ctx,key)??academicValid(ctx.data.first?.[key]);
}
function academicComparable(a,b){
  const x=a.archive.manifest,y=b.archive.manifest;
  const input=(m,key)=>m.input_hashes?.['inputs/'+key+'.csv'];
  return [
    ['Topology',x.topology_sha256,y.topology_sha256],['Clock',x.clock,y.clock],['Sample duration',x.dt_hours,y.dt_hours],
    ['Time coverage',x.timestamp_sha256,y.timestamp_sha256],['Load input',input(x,'load_profile'),input(y,'load_profile')],
    ['PV input',input(x,'pv_profile'),input(y,'pv_profile')],['Source mode',x.source,y.source],['Forecast model',x.forecast,y.forecast],
    ['Dispatch',a.data.descriptor?.dispatch_policy??x.dispatch,b.data.descriptor?.dispatch_policy??y.dispatch],
    ['Economics',x.economics,y.economics],['Voltage limits',x.simulation&&[x.simulation.voltage_min_pu,x.simulation.voltage_max_pu],
      y.simulation&&[y.simulation.voltage_min_pu,y.simulation.voltage_max_pu]],
    ['Slack voltage',academicTopology(a).buses?.find(bus=>bus.is_slack)?.v_set_pu,academicTopology(b).buses?.find(bus=>bus.is_slack)?.v_set_pu],
    ['Control mode',a.data.descriptor?.control_mode,b.data.descriptor?.control_mode]
  ].map(([name,p,q])=>[name,p,q,p==null||q==null?'Unknown':JSON.stringify(p)===JSON.stringify(q)?'Matches':'Differs']);
}
async function academicCompare(root,ctx,range,mode) {
  const state=academicState['Compare Runs'];
  const list=[['current',run],...workspace.imports].flatMap(([key,archive])=>Object.keys(archive.scenarios)
    .map(scenario=>[key+'|'+scenario,chartContext(key,scenario)]));
  if(list.length<2)return academicMissing(root,'Open a saved dashboard or choose a report with multiple scenarios.');
  const name=([,ref])=>shortRun(ref.archive)+' · '+ref.data.label;
  const ref=list.find(row=>row[0]===state.reference)||list[0],candidate=list.find(row=>row[0]===state.candidate&&row[0]!==ref[0])||
    list.find(row=>row[0]!==ref[0]);
  const tools=elem('div',undefined,'controls');root.append(tools);
  selectControl(tools,'Reference',list.map(row=>[row[0],name(row)]),ref[0],value=>{state.reference=value;refreshWorkspace();});
  selectControl(tools,'Candidate',list.filter(row=>row[0]!==ref[0]).map(row=>[row[0],name(row)]),candidate[0],value=>{state.candidate=value;refreshWorkspace();});
  const a=ref[1],b=candidate[1],aStatic=academicStatic(a),bStatic=academicStatic(b);
  const currency=a.archive.manifest.currency===b.archive.manifest.currency?a.archive.manifest.currency:null;
  const differences=academicComparable(a,b),scopeIssues=differences.filter(row=>['Clock','Time coverage','Sample duration'].includes(row[0]));
  const timeComparable=!aStatic&&!bStatic&&scopeIssues.every(row=>row[3]==='Matches')&&
    academicMetric(a,'duration_hours')!==null&&academicMetric(a,'duration_hours')===academicMetric(b,'duration_hours')&&
    a.data.diagnostic?.known_status&&b.data.diagnostic?.known_status&&
    a.data.diagnostic?.nonconverged===0&&b.data.diagnostic?.nonconverged===0;
  const sourceIssues=differences.filter(row=>['Topology','Load input','PV input','Source mode','Forecast model','Slack voltage'].includes(row[0])&&row[3]!=='Matches');
  const confidence=(timeComparable?'Matching reported time basis. ':'Time basis or solved coverage differs or cannot be verified. ')+
    (sourceIssues.length?'Input or network equivalence is incomplete. Use descriptive comparisons.':'Review control and economic differences before attributing changes.');
  root.append(elem('p',confidence,'fine'));
  if(mode==='provenance'){
    academicTable(root,'Saved study compatibility',['Evidence',name(ref),name(candidate),'Status'],differences.map(r=>[
      r[0],displayRecord(r[1]),displayRecord(r[2]),r[3]]),ctx,{open:true,note:'Unknown evidence does not establish a match.'});return;
  }
  if(mode==='cases'){
    const rows=list.map(row=>{
      const c=row[1],fleet=academicRunUnits(c),control=c.data.descriptor?.control_mode??(isUncontrolled(c)?'uncontrolled':null);
      const installed=fleet.length>0,known=installed||c.data.has_bess===false;
      const letter=!control||!known?'Unclassified':control==='uncontrolled'?(installed?'C':'A'):(installed?'D':'B');
      return [letter,name(row),control,installed?fleet.map(u=>u.bus_id).join(', '):known?'No BESS':null,
        c.data.descriptor?.dispatch_policy??c.archive.manifest.dispatch,academicMetric(c,'load_shedding_energy_kwh'),
        academicMetric(c,'loss_energy_kwh'),academicMetric(c,'annual_total_cost')];
    });
    academicTable(root,'Four-case study evidence',['Case','Scenario','Control','Battery buses','Recorded dispatch','ENS (kWh)',
      'Loss (kWh)','Annual cost'],rows,ctx,{open:true,note:'A/B are no BESS with control disabled/enabled. C/D have BESS with control disabled/enabled.'});return;
  }
  if(mode==='sensitivity'){
    academicTable(root,'Saved study sensitivity points',['Case','Buses','Slack (pu)','P (kW)','E (kWh)','ENS (kWh)','Minimum V (pu)',
      'Loss (kWh)','Annual cost','Currency','GA seed','Population','Max generations','Mutation','Representative days'],list.map(row=>{
        const c=row[1],opt=c.archive.metadata?.optimizer,conf=opt?.fleet_ga_optimizer?.config||{};
        return [name(row),academicTopology(c).buses?.length,academicTopology(c).buses?.find(b=>b.is_slack)?.v_set_pu,
          academicCompareValue(c,'fleet_power'),academicCompareValue(c,'fleet_energy'),academicMetric(c,'load_shedding_energy_kwh'),
          academicMetric(c,'voltage_min_pu'),academicMetric(c,'loss_energy_kwh'),academicMetric(c,'annual_total_cost'),c.archive.manifest.currency,
          conf.seed,conf.population_size,conf.max_generations,conf.mutation_rate,opt?.representative_days?.days?.length];
      }),ctx,{open:true,note:'Actual saved points. Differences in other assumptions can confound sensitivity.'});return;
  }
  if(mode==='forecastPlan'){
    const rows=list.map(row=>{
      const c=row[1];
      return [name(row),c.archive.manifest.source,c.archive.manifest.forecast,academicFleetName(academicRunUnits(c)),
        academicMetric(c,'load_shedding_energy_kwh'),academicMetric(c,'voltage_min_pu'),academicMetric(c,'annual_total_cost')];
    }).filter(row=>row[1]==='historical'||row[1]==='forecast');
    academicTable(root,'Historical and forecast planning evidence',['Saved case','Input basis','Forecast model','Selected fleet',
      'ENS (kWh)','Minimum V (pu)','Annual cost'],rows,ctx,{open:true,note:
      'Values retain each study’s operating input basis. Comparison on common realized profiles requires both outcomes to have been verified against them.'});
    return;
  }
  if(mode==='normalized'){
    const stats=c=>{
      const demand=academicMetric(c,'requested_load_energy_kwh'),served=academicMetric(c,'served_load_energy_kwh'),
        loss=academicMetric(c,'loss_energy_kwh'),imported=academicMetric(c,'grid_import_energy_kwh'),
        pv=academicMetric(c,'pv_generation_energy_kwh'),battery=academicMetric(c,'bess_discharge_energy_kwh');
      const supply=[imported,pv,battery].every(academicNumber)?imported+pv+battery:null;
      return [academicRatio(academicMetric(c,'load_shedding_energy_kwh'),demand),academicRatio(loss,supply),
        academicRatio(academicMetric(c,'annual_total_cost'),served>0?served/1000:null)];
    };
    const p=stats(a),q=stats(b);
    academicTable(root,'Normalized cross-network metrics',['Measure',name(ref),name(candidate)],
      ['ENS / requested energy','Network loss / AC supply','Annual cost per served MWh'].map((label,i)=>[label,p[i],q[i]]),ctx,
      {open:true,note:'AC supply is imports + utilized PV + gross BESS discharge. Each case retains its own represented coverage.'});return;
  }
  const measures=academicCompareMeasures.filter(([,key])=>!aStatic&&!bStatic||['voltage_min_pu','voltage_max_pu'].includes(key));
  const metricKey=measures.some(([,key])=>key===state.metric)?state.metric:measures[0][1];
  selectControl(tools,'Metric',measures.map(([label,key])=>[key,label]),metricKey,value=>{state.metric=value;refreshWorkspace();});
  const rows=measures.map(([label,key])=>{
    const x=academicCompareValue(a,key),y=academicCompareValue(b,key),money=key==='annual_total_cost';
    const comparable=(timeComparable||aStatic&&bStatic)&&(!money||currency)&&academicNumber(x)&&academicNumber(y);
    return [label,x,y,comparable?y-x:null,comparable&&x!==0?(y-x)/Math.abs(x)*100:null];
  });
  const measure=rows[measures.findIndex(([,key])=>key===metricKey)];
  if(metricKey!=='annual_total_cost'||currency)
    academicPlot(root,measure[0],[name(ref),name(candidate)],[academicTrace(measure[0],measure.slice(1,3),'bar')],
      metricKey==='annual_total_cost'?currency+'/year':(measure[0].match(/\(([^)]+)\)/)?.[1]||''),ctx,{categorical:true,note:confidence});
  academicTable(root,'Saved study comparison and deltas',['Measure',name(ref),name(candidate),'Candidate − reference','Change (%)'],rows,
    ctx,{open:true,note:'Percent change divides by the absolute reference. Zero or unavailable denominator yields N/A.'});
}

registerAcademic('Study Inputs',{
  load:['Category demand and calendar energy',academicInputLoad,'default'],
  typical:['Typical day profiles',academicInputLoad,'typical'],
  peaks:['Monthly peak demand',academicInputLoad,'peaks'],
  loadDuration:['Load duration curves',academicInputLoad,'duration'],
  consumption:['Bus and category consumption tables',academicInputLoad,'statistics'],
  forecast:['Forecast and chronological error',academicForecastView,'default'],
  scores:['Forecast accuracy by scope',academicForecastView,'scores',false,academicForecast],
  forecastPeaks:['Forecast daily peak errors',academicForecastView,'peaks',false,academicForecast],
  forecastScatter:['Forecast scatter and residual distribution',academicForecastView,'scatter',false,academicForecast],
});
registerAcademic('Power & Energy',{
  service:['Demand served and energy not supplied',academicService,'default'],
  severity:['Service reliability and shedding severity',academicService,'severity'],
  serviceSpatial:['Shedding by bus and category',academicService,'spatial'],
  activeReactive:['Active and reactive power balance',academicBalance,'default'],
  sankey:['Delivered energy flow',academicBalance,'sankey'],
  balanceResidual:['Active/reactive numerical residuals',academicBalance,'residual'],
  grid:['Grid dependency and import/export peaks',academicBalance,'grid'],
  pv:['PV utilization and curtailment',academicPvView,'default',false,academicPV],
  pvMonthly:['Calendar PV energy and utilization',academicPvView,'monthly',false,academicPV],
  pvSpatial:['PV installations and spatial curtailment',academicPvView,'spatial',false,academicPV],
  pvEvents:['Solar resource and corrective-action investigation',academicPvView,'events',false,academicPV],
  losses:['Network loss totals and branch losses',academicLosses,'branches'],
});
registerAcademic('BESS',{
  dispatch:['Dispatch and state of charge',academicBessView,'default'],
  sizing:['Rated vs utilized power and energy',academicBessView,'sizing'],
  reactive:['Reactive dispatch and P–Q operating points',academicBessView,'reactive'],
  closure:['Daily restoration and intraday SOC span',academicBessView,'restoration'],
  throughput:['Monthly gross throughput',academicBessView,'monthly'],
  utilization:['Duration curves and utilization',academicBessView,'duration'],
  audit:['Operation, compliance and conversion losses',academicBessView,'audit'],
});
registerAcademic('Economics',{
  cost:['Annualized cost and benefit waterfall',academicEconomics,'default'],
  monthly:['Monthly operating ledger',academicEconomics,'monthly'],
  capex:['Investment and effective assumptions',academicEconomics,'investment'],
  sensitivity:['Fixed-dispatch accounting sensitivity',academicEconomics,'sensitivity'],
});
registerAcademic('Compare Runs',{
  compare:['Numerical comparison',academicCompare,'default',true],
  cases:['Controlled and uncontrolled cases',academicCompare,'cases'],
  sensitivity:['Saved case-study sensitivity',academicCompare,'sensitivity',true],
  normalized:['Normalized cross-network results',academicCompare,'normalized'],
  forecastPlan:['Historical and forecast planning',academicCompare,'forecastPlan'],
  provenance:['Provenance and comparability',academicCompare,'provenance',true],
});
const academicFleetName=fleet=>fleet?.length?fleet.map(u=>'('+u.bus_id+', '+u.power_rating_kw+' kW, '+u.energy_capacity_kwh+' kWh)').join(' · '):'Empty fleet';
async function academicGa(root,ctx,range,mode){
  const opt=ctx.archive.metadata?.optimizer||{},ga=opt.fleet_ga_optimizer||{},cfg=ga.config||{};
  if(!ctx.archive.metadata?.optimizer&&!ctx.archive.convergence?.length)
    return academicMissing(root,'This study has no saved optimization evidence.');
  const trace=ctx.archive.ga_diagnostics_block==null?null:await readings(ctx)(ctx.archive.ga_diagnostics_block);
  const captured=trace?.status==='recorded',generations=captured?trace.generations:[],candidates=captured?trace.candidates:[];
  const money=(ctx.archive.manifest.currency||'Archive currency')+'/year';
  const scoreMap=new Map(candidates.map(c=>[c.id,c]));
  const recorded=captured?'Recorded generation evidence is available.':
    opt.academic_ga_diagnostics_status==='write_failed'||trace?.status==='capture_failed'?
      'Generation diagnostic capture failed. Saved study results are available.':
      'This run has no recorded generation membership. Rerendering an archive cannot reconstruct it.';
  if(mode==='default'){
    const old=(ctx.archive.convergence||[]).filter(row=>row.axis==='generation'||opt.history_axis==='generation');
    const axis=captured?generations.map(g=>g.index):old.map((r,i)=>r.index??i+1);
    const specs=[['best_so_far','Best so far'],['best','Current-generation best'],['mean','Current-generation mean'],
      ['median','Current-generation median']];
    academicPlot(root,'Generation convergence',axis,captured?specs.map(([f,label])=>academicTrace(label,generations.map(g=>g[f]))):
      [academicTrace('Best recorded objective',old.map(r=>r.best_annual_cost))],money,ctx,{categorical:true,markers:true,
        axisLabel:'Generation',note:'Representative-day estimated cost. Feasible finite objectives only.'});
    academicTable(root,'Selected verified fleet',['Fleet (bus, rated P, rated E)','Verified cost ('+money+')','Selected units','Generations',
      'Unique evaluations','GA wall clock (s)','Stop reason','Effective workers'],[
      [academicFleetName(opt.fleet),opt.best_bess_annual_cost??opt.no_bess_annual_cost,opt.fleet?.length,
        ga.generations,ga.unique_evaluated,ga.elapsed_seconds,ga.stop_reason,trace?.effective_workers??cfg.workers]],ctx,{open:true,note:recorded});
    const checks=(opt.stages||[]).flatMap(stage=>(stage.full_year_candidates||[]).map(c=>[stage.index,
      academicFleetName(c.fleet),c.scenario_estimated_annual_cost,c.annual_cost,c.feasible,c.economic_acceptable,
      c.annual_processed_hours,c.annual_expected_hours,c.verification_status||c.technical_reason]));
    academicTable(root,'Screening estimate vs chronological verification',['Stage','Verified candidate fleet','Screened estimate ('+money+
      ')','Chronological annual cost ('+money+')','Feasible','Saving accepted','Processed hours','Expected hours','Status'],checks,ctx,
      {note:opt.annual_verification_policy||'Annual verification policy unavailable.'});
    return;
  }
  if(mode==='settings'){
    const definitions=[
      ['Solution / chromosome','One complete stationary fleet of (bus ID, power rating kW, energy capacity kWh) tuples. The empty fleet can represent no BESS.'],
      ['Population','A collection of candidate fleet slots in the current generation. Duplicate fleets can occupy separate slots.'],
      ['Generation','One population evaluation/ranking cycle, including reuse of a previously evaluated canonical fleet.'],
      ['Selection','Rank-based roulette among feasible finite candidates. Objective is minimized subject to feasibility.'],
      ['Operators','Scattered transfer of padded per-unit tuples. Gaussian mutation and discrete add/drop can change size or location. Repair enforces eligible buses and catalog/duration constraints.'],
      ['Elitism','Best-ranked fleets seed the next generation before offspring are added.'],
      ['Stall','Significant improvement requires Fnew < Fref − ε × max(1, |Fref|). A smaller improvement still consumes one stall generation.'],
      ['Verification','Representative-day screening → independent stress screen → progressive chronological verification under the archived policy.'],
      ['Selection scope','The selected result is the outcome of the recorded search and verification budget.'],
    ];
    academicTable(root,'GA terminology and methodology',['Term','Description'],definitions,ctx,{open:true});
    academicTable(root,'Archived optimizer settings',['Setting','Value'],[
      ...Object.entries(cfg).map(([key,v])=>[readable(key),v]),['Effective workers',trace?.effective_workers??cfg.workers],
      ['Eligible buses',opt.eligible_bus_ids?.join(', ')],['Visited buses',opt.ga_visited_bus_ids?.join(', ')],
      ['Maximum fleet size',opt.maximum_bess_units],['Verification budget',opt.annual_verification_fallback_budget],
      ['Verification policy',opt.annual_verification_policy],['Duration bounds',displayRecord(opt.bess_duration_constraint)],
      ['Catalogs',displayRecord(ctx.archive.metadata?.context?.['Search catalogs'])],
    ],ctx);
    return;
  }
  if(mode==='days'){
    const scenarios=opt.representative_days,days=Array.isArray(scenarios?.days)?scenarios.days:[];
    academicTable(root,'Representative days and weights',['Cluster','Day index','Start','Weight (represented days)','Saved stress score'],
      days.map(day=>[day.cluster_id,day.day_index,day.start,day.weight_days,day.stress_score]),ctx,{open:true,
        note:'Saved screening hours: '+(scenarios?.total_screened_hours??'unavailable')+
          '. The existing screening inventory ledger prices depletion at import tariff and credits surplus at export tariff. Chronological verification uses its own archived ledger.'});
    if(candidates.length)academicTable(root,'Total weighted screening metrics',['Screen rank','Fleet','Weighted operating cost ('+money+
      ')','Annual fixed cost ('+money+')','Estimated objective ('+money+')','Weighted ENS (kWh)','Weighted PV curtailment (kWh)'],
      candidates.map(c=>[c.screen_rank,academicFleetName(c.fleet),c.annual_operational_cost,c.annual_fixed_cost,c.objective,
        c.annual_shedding_kwh,c.annual_curtailment_kwh]),ctx,
        {note:'Per-day component contributions are unavailable. The study kept candidate totals.'});
    return;
  }
  if(!captured)return academicMissing(root,recorded);
  if(mode==='runtime'){
    const axis=generations.map(g=>g.index);
    academicPlot(root,'Generation evaluation and ranking wall time',axis,[academicTrace('Wall clock',generations.map(g=>g.seconds))],
      's',ctx,{categorical:true,axisLabel:'Generation'});
    academicPlot(root,'Generation slot accounting',axis,[['new','New distinct fleets'],['previous','Previous-cache distinct fleets'],
      ['duplicates','Same-generation duplicate slots']].map(([f,l])=>academicTrace(l,generations.map(g=>g[f]),'bar')),
      'slots',ctx,{categorical:true,stack:true,axisLabel:'Generation'});
    academicTable(root,'GA generation evidence',['Generation','Wall time (s)','Slots','New','Previous cache','Duplicate slots',
      'Cumulative unique','Feasible slots','Invalid slots','Significant reference','Stall count'],
      generations.map(g=>[g.index,g.seconds,g.slots,g.new,g.previous,g.duplicates,g.unique_total,g.feasible_slots,
        g.invalid_slots,g.significant_reference,g.stall]),ctx,{open:true,note:'New + previous distinct + same-generation duplicates = recorded population slots.'});
    return;
  }
  if(mode==='search'){
    const values=candidates.map(c=>[academicSum(c.fleet.map(u=>u.power_rating_kw)),academicSum(c.fleet.map(u=>u.energy_capacity_kwh)),c])
      .sort((a,b)=>a[0]-b[0]);
    const x=values.map(row=>row[0]),counts=[...new Set(candidates.map(c=>c.fleet.length))].sort((a,b)=>a-b);
    academicPlot(root,'Screened fleet power and energy',x,counts.map(n=>academicTrace(n+' installed units',values.map(([,e,c])=>c.fleet.length===n?e:null),'points')),
      'kWh',ctx,{categorical:true,coordinates:x,axisLabel:'Fleet power (kW)',note:'Distinct evaluated fleet keys. Includes infeasible fleets.'});
    const trade=candidates.filter(c=>c.feasible&&academicNumber(c.annual_shedding_kwh)&&academicNumber(c.objective))
      .sort((a,b)=>a.annual_shedding_kwh-b.annual_shedding_kwh);
    const ens=trade.map(c=>c.annual_shedding_kwh);
    academicPlot(root,'Screened cost and ENS trade-offs',ens,[academicTrace('Feasible fleet',trade.map(c=>c.objective),'points')],
      money,ctx,{categorical:true,coordinates:ens,axisLabel:'Representative-day weighted ENS (kWh)',note:'Screening evidence from the single-objective search.'});
    const countsByBus=new Map();
    for(const c of candidates)for(const u of c.fleet)countsByBus.set(u.bus_id,(countsByBus.get(u.bus_id)||0)+1);
    academicTable(root,'Eligible bus search coverage',['Bus','Evaluated unique fleets containing bus'],
      (opt.eligible_bus_ids||[...countsByBus.keys()]).slice().sort(academicNumeric).map(id=>[id,countsByBus.get(id)||0]),ctx);
    return;
  }
  const state=academicState.Optimization,controls=elem('div',undefined,'controls'),body=elem('div');
  root.append(controls,body);
  const options=generations.map(g=>[String(g.index),'Generation '+g.index]);
  options.push(['unique','All unique evaluated fleets']);
  const chosen=options.some(([key])=>key===state.gaGeneration)?state.gaGeneration:'1';
  const pick=selectControl(controls,'Population view',options,chosen,()=>paint());
  const filter=selectControl(controls,'Feasibility',[['','All'],['yes','Feasible'],['no','Infeasible']],'',()=>paint());
  const search=elem('input');search.type='search';search.placeholder='Search ID or fleet';search.setAttribute('aria-label','Search candidate ID or fleet');
  search.oninput=()=>paint();controls.append(search);
  function paint(){
    body.replaceChildren();
    const gen=generations.find(g=>String(g.index)===pick.value);
    const rows=(gen?gen.ranked.map(id=>scoreMap.get(id)):candidates).flatMap((c,i)=>{
      if(!c||filter.value&&(filter.value==='yes')!==c.feasible)return [];
      const name=academicFleetName(c.fleet);
      if(search.value&&!String(c.id).concat(' ',name).toLowerCase().includes(search.value.trim().toLowerCase()))return [];
      return [[c.id,gen?i+1:null,c.screen_rank,name,c.feasible,c.objective,c.annual_operational_cost,c.annual_fixed_cost,
        gen?(gen.new_ids.includes(c.id)?'New this generation':'Previous cache'):null,c.message]];
    });
    state.gaGeneration=pick.value;
    academicTable(body,'Recorded candidate ranking',['ID','Population rank','Unique-screen rank','Fleet tuple','Feasible','Objective ('+money+
      ')','Operating ('+money+')','Fixed ownership ('+money+')','Distinct cache status','Evaluation status'],rows,ctx,
      {open:true,note:'Multiple population slots can reference one candidate ID. Ties retain saved order.'});
    if(trace.level==='detail'&&gen){
      academicTable(body,'Recorded parent and offspring transitions',['Generation','New population slot','Parent IDs','Post-crossover tuple','Repaired child ID'],
        (trace.lineage||[]).filter(row=>row[0]===gen.index).map(row=>[row[0],row[1],row[2].join(', '),academicFleetName(row[3]),row[4]]),
        ctx,{note:'Fetched only for opt-in detailed runs. The crossed tuple is followed by the actual evaluated child after mutation and repair.'});
    }else body.append(elem('p','Detailed operator transitions are available for opt-in runs using EE499_GA_DIAGNOSTICS=detail.','fine'));
  }
  paint();
}
registerAcademic('Optimization',{
  convergence:['Convergence, selected fleet and verification',academicGa,'default'],
  settings:['GA terminology and effective settings',academicGa,'settings'],
  population:['Recorded population and candidate rankings',academicGa,'population'],
  days:['Representative days and weighted ledger',academicGa,'days'],
  search:['Search diversity and sizing trade-offs',academicGa,'search'],
  performance:['Runtime and cache accounting',academicGa,'runtime'],
});
