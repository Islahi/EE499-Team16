const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function workspaceContext() {
  const ctx = vm.createContext({location:{hash:''},document:{readyState:'loading',addEventListener(){}},
    URLSearchParams, Blob, Response, DecompressionStream, TextDecoder, atob});
  for(const name of ['dashboard_gallery.js','dashboard_layout.js','dashboard_workspace.js','dashboard_health.js','dashboard.js'])
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/assets',name),'utf8'),ctx);
  return ctx;
}
const plain=x=>JSON.parse(JSON.stringify(x));

test('elapsed time viewport anchors wheel zoom and preserves a fixed engineering scale',()=>{
  const view=workspaceContext(),base=Date.UTC(2021,0,1),hour=3600000;
  const axis=Array.from({length:168},(_,i)=>new Date(base+(i+(i>=90?5:0))*hour).toISOString());
  const viewport=view.timeViewport(axis);
  const i=70,anchor=viewport.fraction(i),scale=view.seriesLimits(
    [{data:[130.00004,10]},{data:[0,50.123456],axis:'right',style:'bar'}],[],false,false,false,168);
  viewport.zoom(.8,anchor);
  assert.ok(Math.abs(viewport.fraction(i)-anchor)<1e-9);
  assert.ok(viewport.range[1]-viewport.range[0]<168);
  const [first,last]=viewport.limits;
  viewport.pan(.12);
  assert.ok(viewport.limits[0]>first);
  assert.equal(viewport.limits[1]-viewport.limits[0],last-first);
  viewport.pan(100);
  assert.equal(viewport.limits[1],viewport.high);
  viewport.pan(-200);
  assert.equal(viewport.limits[0],viewport.low);
  for(let n=0;n<30;n++)viewport.zoom(.8,.5);
  assert.ok(viewport.range[1]-viewport.range[0]>=2);
  viewport.set(0,168);
  assert.deepEqual(plain(viewport.range),[0,168]);
  assert.deepEqual(plain(scale),{left:[10,130.00004],right:[0,50.123456]});
  assert.equal(view.timeViewport(['Bus 1','Bus 2']),null);
  assert.equal(view.timeViewport([]),null);
  assert.deepEqual(plain(view.timeViewport([axis[0]]).range),[0,1]);
});

test('linked ranges use bucket coverage and preserve a separate independent viewport',()=>{
  const view=workspaceContext();
  const stamps=['2021-01-01','2021-02-01','2021-03-01','2021-04-01'];
  const periods=stamps.map((start,i)=>({start,end:['2021-01-31','2021-02-28','2021-03-31','2021-04-30'][i]}));
  assert.deepEqual(plain(view.linkedRange(stamps,['2021-01-22T01:00:00Z','2021-03-15T12:00:00Z'],periods)),[0,3]);
  assert.deepEqual(plain(view.linkedRange(stamps,['2021-08-01','2021-11-01'],periods)),[2,4]);
  const independent=view.timeViewport(stamps,[1,3]);
  const linked=view.timeViewport(stamps,view.linkedRange(stamps,['2021-01-22','2021-04-03'],periods));
  assert.deepEqual(plain(independent.range),[1,3]);
  assert.deepEqual(plain(linked.range),[0,4]);
});

test('category demand presets support drill-down and reject stacking with system totals',()=>{
  const view=workspaceContext(),group={fields:['p_kw','q_kvar'],entities:{Total:[],residential:[],commercial:[],6:[],18:[]},
    categories:{residential:{buses:['6']},commercial:{buses:['18']}}};
  const gallery={groups:{'load input':group}};
  const chart=view.presetChart('categoryPQ','Study Inputs',gallery);
  assert.equal(chart.series[1].axis,'right');
  assert.deepEqual(plain(view.entitiesFor(chart,chart.series[0],group,{kind:'bus',ids:['6']},
    {group:'bus',category:'residential'})),['6']);
  assert.deepEqual(plain(view.entitiesFor(chart,chart.series[0],group,{kind:'bus',ids:['6']},
    {group:'category',category:'commercial'})),['commercial']);
  const spec={group:'load input',field:'p_kw',style:'bar',unit:'kW',axis:'left',scenario:'manual',runKey:'current'};
  const residential={...spec,entity:'residential',category:'Residential'};
  assert.equal(view.canStack([residential,{...spec,entity:'commercial',category:'Commercial'}]),true);
  assert.equal(view.canStack([residential,{...spec,entity:'Total'}]),false);
});

test('chart events pan and reset without a miniature timeline and export visible raw rows',()=>{
  const view=workspaceContext(),events=[],frames=[],exports=[];
  class Element {
    constructor(tag){
      this.tagName=tag;this.children=[];this.style={};this.isConnected=true;
      this.clientWidth=640;this.clientHeight=275;this.listeners={};
    }
    append(...children){this.children.push(...children);children.forEach(child=>child.parent=this);}
    setAttribute(){}
    getBoundingClientRect(){return {left:0};}
    getContext(){return new Proxy({measureText:value=>({width:value.length*5})},{get:(target,key)=>target[key]||(()=>{})});}
    setPointerCapture(){}
    focus(){}
    addEventListener(type,listener){this.listeners[type]=listener;}
  }
  view.document.createElement=tag=>new Element(tag);
  view.window={devicePixelRatio:1};
  view.requestAnimationFrame=fn=>frames.push(fn);
  view.collect=(...args)=>exports.push(args);
  vm.runInContext('saveRows=collect',view);
  const root=new Element('main');
  const axis=Array.from({length:168},(_,i)=>new Date(Date.UTC(2021,0,1,i)).toISOString());
  const values=axis.map((_,i)=>i+.1234567);
  const chart=view.interactiveChart(root,'Load and shedding',axis,[
    {label:'Load',data:values},{label:'Shed',data:axis.map((_,i)=>i===120?10:0),style:'bar'}],'kW',
    {compact:true,onZoom:(a,b)=>events.push([a,b]),pick:i=>events.push(i)});
  const panel=root.children[0],canvas=panel.children[0].children[0];
  assert.equal(panel.children.map(node=>node.tagName).join(','),'div,output,div,details');
  const frame=()=>{while(frames.length)frames.shift()();};
  const pointer=(x,extra={})=>({offsetX:x,offsetY:125,clientX:x,clientY:125,pointerId:1,button:0,
    preventDefault(){},stopPropagation(){},...extra});
  let scrollPrevented=false;
  canvas.listeners.wheel(pointer(350,{offsetY:10,deltaY:-120,preventDefault(){scrollPrevented=true;}}));
  assert.equal(scrollPrevented,false);
  canvas.listeners.wheel(pointer(350,{deltaY:-120,preventDefault(){scrollPrevented=true;}}));
  frame();assert.equal(scrollPrevented,true);
  const zoom=events.at(-1);
  assert.ok(zoom[1]-zoom[0]<168);
  canvas.onpointerdown(pointer(400));canvas.onpointerup(pointer(400));
  assert.equal(typeof events.at(-1),'number');
  canvas.onpointerdown(pointer(400));canvas.onpointermove(pointer(340));canvas.onpointerup(pointer(340));
  frame();assert.notDeepEqual(events.at(-1),zoom);
  const [first,last]=events.at(-1);
  chart.saveCSV();
  assert.equal(exports[0][1].length,last-first);
  assert.equal(exports[0][1][0][0],axis[first]);
  assert.equal(exports[0][1][0][1],values[first]);
  canvas.onkeydown({key:'Escape',preventDefault(){}});
  frame();assert.deepEqual(events.at(-1),[0,168]);
});

test('summary tables retain exact deltas and distinguish zero and missing denominators',()=>{
  const view=workspaceContext();
  const data=plain(view.summaryRows([['Shed','shed','kWh'],['Price','cost','USD'],['Voltage','v','pu',false],
    ['Missing','missing','kWh'],['Complete','done','',false]],
    {shed:0,cost:1.123456789,v:.94999,done:true},
    {shed:3.4499999,cost:2.987654321,v:.95,missing:30,done:false},true));
  assert.equal(data[0].delta,3.4499999);
  assert.equal(data[0].change,null);
  assert.equal(data[1].delta,2.987654321-1.123456789);
  assert.equal(data[1].change,100*(2.987654321-1.123456789)/1.123456789);
  assert.equal(data[2].change,null);
  assert.equal(data[3].delta,null);
  assert.equal(data[4].delta,null);
  assert.equal(view.comparisonMetricRows({annual_total_cost:1,feasible:false},{annual_total_cost:2},true,'USD').length,0);
});

test('all display numbers have at most three decimal places and match exact export input',()=>{
  const view=workspaceContext();
  const files=[1,1.05,.967874,-1.84249,1234.56789,0,.00004,-.00004,null,NaN,Infinity,-.0004,.9496];
  const expected=['1','1.05','0.968','−1.842','1,234.568','0','≈0','≈−0','Not recorded','Not recorded','Not recorded','≈−0','0.95'];
  assert.deepEqual(plain(vm.runInContext('fmt',view) && files.map(value=>vm.runInContext('fmt',view)(value))),expected);
  assert.equal(view.csvLine([.9496,-.00004]),'"0.9496","-0.00004"\r\n');
  assert.equal(.9496<.95,true);
});

test('calendar windows and unlocked windows retain independent time ranges',()=>{
  const view=workspaceContext();
  const axis=['2020-02-29 23:00:00','2020-03-01 00:00:00','2020-03-01 01:00:00','2020-04-01 00:00:00'];
  const shared={period:'month',start:axis[1]},local={period:'custom',start:axis[0],end:axis[1]};
  assert.deepEqual(plain(view.chartWindow(axis,shared)),[1,3]);
  assert.deepEqual(plain(view.chartWindow(axis,local)),[0,2]);
  shared.start=axis[3];
  assert.deepEqual(plain(view.chartWindow(axis,shared)),[3,4]);
  assert.deepEqual(plain(view.chartWindow(axis,local)),[0,2]);
});

test('layout roundtrip keeps chart styles, independent axes, scope and persisted pin order',()=>{
  const view=workspaceContext();
  const state=view.emptyLayout('source'),a=view.newChart('a','Bus angle'),b=view.newChart('b','Load and shedding');
  a.selection.linked=false;a.time={linked:false,period:'24h',start:'2021-01-03 00:00:00'};
  a.series=[{group:'bus',field:'voltage_angle_deg',ids:['18'],style:'line',axis:'right',color:'#4488aa',dash:'dashed'}];
  b.series=[{group:'system',field:'load_input_kw',ids:[],style:'line'},{group:'system',field:'shedding_kw',ids:[],style:'bar'}];
  state.charts={a,b};state.time.zoom=['2021-01-01 03:00:00','2021-01-01 05:00:00'];state.pinned=['b','a'];
  state.time.cursor='2021-01-01 04:00:00';state.mode='engineering';
  const layout=view.layoutFromJSON(JSON.parse(JSON.stringify(state)),'destination');
  assert.equal(layout.runId,'destination');
  assert.equal(layout.mode,'engineering');
  assert.deepEqual(plain(layout.time.zoom),state.time.zoom);
  assert.deepEqual(plain(layout.pinned),['b','a']);
  assert.equal(layout.charts.a.time.linked,false);
  assert.equal(layout.charts.a.series[0].axis,'right');
  assert.equal(layout.charts.b.series[1].style,'bar');
  assert.throws(()=>view.layoutFromJSON({...state,version:99},'destination'),/version/);
});

test('entity linking selects compatible buses and preserves unlinked/system charts',()=>{
  const view=workspaceContext(),sel={kind:'bus',ids:['6']};
  const buses={entities:{6:[],18:[]}},system={entities:{System:[]}};
  const a=view.newChart('a'),override={group:'bus',ids:['18']};
  assert.deepEqual(plain(view.entitiesFor(a,override,buses,sel)),['6']);
  a.selection.linked=false;
  assert.deepEqual(plain(view.entitiesFor(a,override,buses,sel)),['18']);
  assert.deepEqual(plain(view.entitiesFor(a,{group:'system',ids:[]},system,sel)),['System']);
});

test('unit-safe stacking and energy integration preserve missing values',()=>{
  const view=workspaceContext(),a={style:'bar',unit:'kW',axis:'left',entity:'System',scenario:'no_bess',runKey:'current'};
  assert.equal(view.canStack([{...a,field:'load_input_kw'},{...a,field:'shedding_kw'}]),true);
  assert.equal(view.canStack([{...a,field:'requested_load_kw'},{...a,field:'load_input_kw'}]),false);
  assert.equal(view.canStack([{...a,field:'shedding_kw'},{...a,field:'shedding_kw',entity:'Bus 6'}]),false);
  const axis=['2021-01-01 00:00:00','2021-01-01 00:30:00','2021-01-02 00:00:00'];
  const data=view.bucketReadings(axis,[1.00004,3,null],'day','energy',.5,'kW');
  assert.deepEqual(plain(data.data),[(1.00004+3)*.5,null]);
  assert.equal(data.unit,'kWh');
  assert.equal(data.intervals[0].end,axis[1]);
  assert.deepEqual(plain(view.bucketReadings(axis,[1,null,2],'day','energy',.5,'kW').data),[null,1]);
});

test('comparison aligns exact timestamps and differences before display rounding',async()=>{
  const view=workspaceContext();
  const timestamps=['2021-01-01 00:00:00','2021-01-01 01:00:00','2021-01-01 02:00:00'];
  const ref=timestamps.slice(1);
  const manifest={run_id:'A',currency:'USD',clock:'UTC',dt_hours:1};
  const group={fields:['requested_load_kw','shedding_kw','grid_import_kw'],entities:{System:[[0,2,3]]}};
  view.fixture={manifest,metadata:{},scenarios:{best_bess:{label:'With BESS',gallery:{timestamps:1,groups:{system:group}}},
    no_bess:{label:'No BESS',gallery:{timestamps:2,groups:{system:group}}}}};
  const records={1:timestamps,2:ref,3:[[0,1,2],{requested_load_kw:[.99,1.00006,1.00015],shedding_kw:[0,.01,.02],grid_import_kw:[1,1,1]}]};
  view.fixture.readBlock=async id=>{
    if(id!==3)return records[id];
    return records[3];
  };
  const current=vm.runInContext("run=fixture; workspace.primary='best_bess'; workspace.state=emptyLayout('A'); workspace.state.time.period='all'; workspace",view);
  const chart=view.newChart('c');
  chart.series=[{group:'system',field:'requested_load_kw',ids:[],axis:'left',style:'line'}];
  chart.comparison={mode:'difference',run:'current',scenario:'no_bess'};
  const delta=await view.prepareWorkspaceChart(chart,current.state.selection);
  assert.deepEqual(plain(delta.axis),ref);
  assert.equal(delta.traces[0].data[0],1.00006-.99);
  assert.equal(delta.traces[0].data[1],1.00015-1.00006);
  assert.match(delta.notes[0],/1 candidate timestamps excluded/);
  chart.comparison.mode='side';
  const side=await view.prepareWorkspaceChart(chart,current.state.selection);
  assert.equal(side.traces[0].data[1],1.00015);
  assert.equal(side.reference[0].data[1],1.00006);
  chart.comparison.mode='overlay';
  const overlay=await view.prepareWorkspaceChart(chart,current.state.selection);
  assert.equal(overlay.traces.length,2);
  assert.equal(view.comparisonIssue(manifest,{...manifest,clock:'Asia/Riyadh'},'shedding_kw').includes('clock'),true);
  assert.equal(view.comparisonIssue(manifest,{...manifest,currency:'SAR'},'shedding_cost').includes('currency'),true);
  assert.equal(view.comparisonIssue(manifest,{...manifest,dt_hours:.5},'shedding_kw').includes('sample'),true);
});


test('Summary opens independently of saved tab while layout time, scope and pins survive migration',()=>{
  const view=workspaceContext();
  view.saved={version:1,tab:'BESS',controlsOpen:true,healthMode:'overall',time:{period:'year',start:'2022-01-01 00:00:00'},
    topics:{Overview:['Overview:load']},pinned:['Overview:load'],charts:{'Overview:load':{
      series:[{group:'system',field:'grid_import_kw'}],aggregation:'month',reducer:'mean'}}};
  view.localStorage={getItem:()=>JSON.stringify(view.saved)};
  view.fixture={manifest:{run_id:'run'},scenarios:{best_bess:{label:'Battery'}}};
  vm.runInContext('run=fixture; initWorkspace()',view);
  const result=vm.runInContext('({screen,state:workspace.state})',view);
  assert.equal(result.screen,'Summary');
  assert.equal(result.state.version,2);
  assert.equal(result.state.controlsOpen,true);
  assert.equal(result.state.healthMode,'overall');
  assert.equal(result.state.charts['Overview:load'].aggregation,'month');
  assert.deepEqual(plain(result.state.topics.Summary),['Overview:load']);
  assert.deepEqual(plain(result.state.pinned),['Overview:load']);
});

test('daily power weights durations and sums interval energy; weekly is Monday in recorded clock',()=>{
  const view=workspaceContext(),axis=['2024-02-29 00:00:00','2024-02-29 01:00:00','2024-03-04 00:00:00'];
  const weighted=view.bucketReadings(axis,[8,20,16],'day','auto',1,'kW','grid_import_kw',null,[1,3,1]);
  assert.deepEqual(plain(weighted.data),[17,16]);
  assert.equal(weighted.unit,'kW');
  assert.deepEqual(plain(view.bucketReadings(axis,[8,60,16],'day','auto',1,'kWh','grid_import_kwh').data),[68,16]);
  const weeks=view.bucketReadings(axis,[1,3,2],'week','auto',1,'kW');
  assert.deepEqual(plain(weeks.axis),['2024-02-26','2024-03-04']);
  assert.ok(weeks.intervals[0].partial);
  assert.equal(view.resolvedResolution('auto',24),'hourly');
  assert.equal(view.resolvedResolution('auto',8760),'day');
  assert.equal(view.resolvedResolution('auto',43824),'month');
  const summer=['2024-03-31T01:00:00+01:00','2024-03-31T03:00:00+02:00'];
  assert.equal(view.bucketReadings(summer,[1,2],'day','auto',1,'kWh').intervals[0].missing,0);
});

test('aggregation reports sparse intervals and preserves voltage extremes and angle wrap',()=>{
  const view=workspaceContext(),axis=['2024-01-01 00:00:00','2024-01-01 01:00:00','2024-01-01 03:00:00'];
  const data=view.bucketReadings(axis,[.971,.94999999,1.02],'month','auto',1,'pu','voltage_pu',{minimum:.95,maximum:1.05});
  assert.equal(data.intervals[0].minimum,.94999999);
  assert.equal(data.intervals[0].violationSamples,1);
  assert.equal(data.intervals[0].violationHours,1);
  assert.equal(data.intervals[0].missing,1);
  assert.equal(view.bucketReadings(axis,[1,2,3],'day','auto',1,'kWh').data[0],null);
  const angle=view.bucketReadings(axis,[179,-179,-179],'day','auto',1,'°','voltage_angle_deg').data[0];
  assert.ok(Math.abs(angle)>179);
});

test('independent resolution overrides and shared resolution resolve the same chart without conflating selection',()=>{
  const view=workspaceContext(),axis=Array.from({length:168},(_,i)=>new Date(Date.UTC(2024,0,1,i)).toISOString().slice(0,19).replace('T',' '));
  const fixture={manifest:{run_id:'a',clock:'UTC',dt_hours:1},metadata:{},scenarios:{no_bess:{label:'No BESS',
    gallery:{timestamps:0,groups:{system:{fields:['grid_import_kw'],entities:{System:[[0,167,1]]}}}}}},
    readBlock:async n=>n===0?axis:[axis.map((x,i)=>i),{grid_import_kw:axis.map((x,i)=>i)}]};
  view.fixture=fixture;
  const state=vm.runInContext("run=fixture; workspace.primary='no_bess'; workspace.state=emptyLayout('a'); workspace.state",view);
  state.time.resolution='day';
  const linked=view.newChart('hourly-day'),local=view.newChart('weekly');
  const spec={group:'system',field:'grid_import_kw',ids:[],axis:'left',style:'line'};
  linked.series=[spec];local.series=[spec];local.aggregation='week';
  assert.deepEqual(plain(view.chartWindow(axis,state.time)),[0,168]);
  return Promise.all([view.prepareWorkspaceChart(linked,state.selection),view.prepareWorkspaceChart(local,state.selection)]).then(([daily,weekly])=>{
    assert.equal(daily.axis.length,7);
    assert.equal(daily.traces[0].data[0],11.5);
    assert.equal(weekly.axis.length,1);
    assert.equal(weekly.traces[0].data[0],83.5);
    assert.equal(weekly.traces[0].unit,'kW');
  });
});

test('short-run bars omit annual cost and missing results and preserve signed deltas',()=>{
  const view=workspaceContext();
  const before={load_shedding_energy_kwh:15.0004,loss_energy_kwh:0,annual_total_cost:1000};
  const after={load_shedding_energy_kwh:10,loss_energy_kwh:0,annual_total_cost:500,grid_import_energy_kwh:2};
  const bars=view.comparisonMetricRows(before,after,false,'USD');
  assert.deepEqual(plain(bars.map(m=>m.label)),['Load shedding','Network losses']);
  assert.equal(bars[0].delta,10-15.0004);
  assert.equal(bars[1].delta,0);
  assert.equal(view.comparisonMetricRows(before,after,true,'USD')[0].unit,'USD/year');
  assert.equal(view.hasInstalledBess({scenario:'no_bess',data:{has_bess:true},archive:{}}),false);
  assert.equal(view.hasInstalledBess({scenario:'best_bess',data:{has_bess:true},archive:{}}),true);
  assert.equal(view.feederHealthClass({samples:8760,affected:300},8760),'some');
  assert.equal(view.feederHealthClass({samples:8760,affected:450},8760),'frequent');
  assert.equal(view.feederHealthClass({samples:8759,affected:0},8760),'unknown');
});

test('typed cells retain the complete details of long paths, hashes and nested values',()=>{
  const view=workspaceContext(),hash='a'.repeat(64);
  assert.equal(view.displayRecord(hash).full,hash);
  assert.equal(view.displayRecord(hash).label,'aaaaaaaaaaaa…');
  const raw={provider:'NASA POWER',url:'<script>unsafe</script>',site:{latitude:43.263}};
  assert.equal(view.displayRecord(raw).label,'3 recorded fields');
  assert.deepEqual(JSON.parse(view.displayRecord(raw).full),raw);
  assert.equal(view.displayRecord(null).label,'Not recorded');
  assert.equal(view.displayRecord(0).label,'0');
});


