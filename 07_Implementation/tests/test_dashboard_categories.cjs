const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Element {
  constructor(tag){
    this.tagName=tag;this.children=[];this.textContent='';this.value='';this.dataset={};this.style={};
    this.isConnected=true;this.attributes={};this.clientWidth=640;this.clientHeight=275;
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  add(option){this.append(option);}
  addEventListener(){}
  setAttribute(key,value){this.attributes[key]=value;}
  createTHead(){const item=new Element('thead');this.append(item);return item;}
  createTBody(){const item=new Element('tbody');this.append(item);return item;}
  insertRow(){const item=new Element('tr');this.append(item);return item;}
}
const descendants=node=>[node,...node.children.flatMap(descendants)];
const button=(root,label)=>descendants(root).find(el=>el.tagName==='button'&&el.textContent===label);
const select=(root,label)=>descendants(root).find(el=>el.tagName==='label'&&el.textContent===label)
  ?.children.find(el=>el.tagName==='select');
const choose=(el,value)=>{assert.ok(el,value);el.value=value;el.onchange();};
const plain=value=>JSON.parse(JSON.stringify(value));

function runtime(){
  const captures=[];
  const context=vm.createContext({document:{readyState:'loading',addEventListener(){},
    createElement:tag=>new Element(tag),getElementById:()=>null},location:{hash:''},
    Option:class extends Element {constructor(label,value){super('option');this.textContent=label;this.value=value;}},
    URLSearchParams,Blob,Response,DecompressionStream,TextDecoder,atob,
    recordCSV:(...args)=>captures.push(args)});
  for(const filename of ['dashboard_gallery.js','dashboard_layout.js','dashboard_workspace.js','dashboard_health.js','dashboard.js'])
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/assets',filename),'utf8'),context);
  const call=expr=>vm.runInContext(expr,context);
  call('refreshWorkspace=()=>{}; saveRows=recordCSV;');
  return {context,call,captures};
}

function fixture(){
  const hours=['2021-01-01 00:00:00','2021-01-01 01:00:00','2021-01-02 00:00:00'];
  const labels={residential:{label:'Residential',buses:['2','3']},commercial:{label:'Commercial',buses:['9']},
    manufacturing:{label:'Manufacturing',buses:['5']}};
  const blocks=[hours];
  const add=data=>{blocks.push(data);return blocks.length-1;};
  function group(records,categories){
    const entities={},entity_fields={};
    for(const [id,data] of Object.entries(records)){
      entities[id]=[[0,2,add([[0,1,2],data])]];entity_fields[id]=Object.keys(data);
    }
    return {entities,fields:[...new Set(Object.values(entity_fields).flat())],entity_fields,
      ...(categories?{categories,category_source:'Archived bus assignments'}:{})};
  }
  const variants={};
  for(const [key,increment] of [['no_bess',2],['best_bess',1],['uncontrolled',0],['controlled',3]]){
    const record=(base,omit=false)=>({requested_load_kw:[base,base+1,base+2],requested_load_kwh:[base,base+1,base+2],
      ...(omit?{}:{load_input_kw:[base-increment,base+1-increment,base+2-increment]}),
      shedding_kw:[increment,increment,increment],shed_kwh:[increment,increment,increment]});
    const r=record(20),c=record(10),m=record(7,key==='uncontrolled');
    variants[key]={label:key,gallery:{timestamps:0,groups:{
      system:group({System:{shedding_kw:[3*increment,3*increment,3*increment]}}),
      bus:group({9:c}),
      'load output':group({residential:r,commercial:c,manufacturing:m,Total:record(37)},labels),
      'load input':group({residential:{p_kw:r.requested_load_kw},commercial:{p_kw:c.requested_load_kw},
        manufacturing:{p_kw:m.requested_load_kw}},labels),
      forecast:group({commercial:{actual_kw:[1,2,3],forecast_kw:[2,3,4]},solar_pv:{actual_kw:[1,2,3]}}),
    }}};
  }
  return {manifest:{run_id:'fixture',dt_hours:1,clock:'UTC',currency:'USD',topology_sha256:'network'},
    scenarios:variants,metadata:{},readBlock:async id=>blocks[id]};
}

function selectMeasurement(editor,scope,measurement,category){
  choose(select(editor,'Series scope'),scope);
  const option=button(editor,'+ '+measurement);assert.ok(option,measurement);option.onclick();
  if(scope==='system')return;
  if(scope==='bus'){
    choose(select(editor,'Bus'),category);button(editor,'Add bus series').onclick();return;
  }
  if(category==='all')button(editor,'Select all categories').onclick();
  else{
    const toggle=descendants(editor).find(el=>el.tagName==='label'&&el.children.some(n=>n.textContent===category));
    assert.ok(toggle,category);
    toggle.children[0].checked=true;toggle.children[0].onchange();
  }
  const submit=button(editor,'Add selected series');assert.ok(!submit.disabled);submit.onclick();
}

test('Add chart and Edit chart build independent custom category series through the scope picker',async()=>{
  const {context,call}=runtime();
  context.fixture=fixture();
  const state=call("run=fixture; workspace.primary='controlled'; workspace.state=emptyLayout(run.manifest.run_id); workspace.state");
  state.time.period='all';state.time.resolution='hourly';
  const ctx=call("chartContext()");
  const toolbar=new Element('main');context.workspaceToolbar(toolbar,'Power & Energy',ctx);
  button(toolbar,'Add chart').onclick();
  const chart=state.charts[state.active];
  const editor=new Element('aside');
  const edit=()=>context.chartEditor(editor,chart,'Power & Energy',ctx);
  edit();selectMeasurement(editor,'category','Requested demand (kW)','Residential');
  edit();selectMeasurement(editor,'category','Load shedding (kW)','Residential');
  edit();selectMeasurement(editor,'category','Served demand (kW)','Commercial');
  edit();selectMeasurement(editor,'category','Served demand (kW)','Manufacturing');
  edit();selectMeasurement(editor,'bus','Requested load (kW)','9');
  edit();selectMeasurement(editor,'system','Shedding (kW)');
  assert.deepEqual(plain(chart.series).map(s=>[s.scope,s.ids[0]]),
    [['category','residential'],['category','residential'],['category','commercial'],['category','manufacturing'],
     ['bus','9'],['system','System']]);
  const prepared=await context.prepareWorkspaceChart(chart,{kind:'bus',ids:['3']});
  assert.deepEqual(plain(prepared.traces).map(s=>s.label),[
    'Residential · Requested demand (kW)','Residential · Load shedding (kW)',
    'Commercial · Served demand (kW)','Manufacturing · Served demand (kW)',
    'Bus 9 · Requested load (kW)','System total · Shedding (kW)',
  ]);
  assert.deepEqual(plain(prepared.traces[2].data),[7,8,9]);
  edit();
  const commercial=descendants(editor).find(el=>el.tagName==='details'&&el.children[0]?.textContent==='Commercial · Served demand (kW)');
  choose(select(commercial,'Category quantity'),'load output|requested_load_kw');
  assert.equal(chart.series[2].field,'requested_load_kw');
  assert.equal(chart.series[3].field,'load_input_kw');
  assert.equal(chart.series[4].ids[0],'9');
  button(commercial,'Move series up').onclick();
  assert.equal(chart.series[1].ids[0],'commercial');
  context.storePinned(chart);
  const loaded=context.layoutFromJSON(JSON.parse(JSON.stringify(state)),'new-run');
  assert.equal(loaded.charts[chart.id].series[1].scope,'category');
  assert.deepEqual(plain(loaded.pinned),[chart.id]);
  assert.ok(context.categoryMeasurements(ctx).some(item=>item.field==='actual_kw'&&item.ids.join()==='commercial'));
});

test('Select all creates additive bars, with no substitution across corrective and BESS scenarios',async()=>{
  const {context,call}=runtime();
  context.fixture=fixture();
  const state=call("run=fixture; workspace.primary='controlled'; workspace.state=emptyLayout(run.manifest.run_id); workspace.state");
  state.time.period='all';state.time.resolution='hourly';
  const ctx=call('chartContext()'),editor=new Element('aside');
  const chart=context.newChart('stack');
  context.chartEditor(editor,chart,'My Dashboard',ctx);
  selectMeasurement(editor,'category','Requested energy (kWh)','all');
  assert.equal(chart.series.length,3);
  chart.series.forEach(s=>s.style='bar');
  const stacked=await context.prepareWorkspaceChart(chart,{ids:[]});
  assert.ok(context.canStack(stacked.traces));
  assert.ok(stacked.traces.every(trace=>!!trace.category&&trace.entity!=='Total'));
  const compare=context.newChart('comparison');
  const served=context.categoryMeasurements(ctx).find(item=>item.field==='load_input_kw');
  context.insertWorkspaceSeries(compare,ctx,served,['manufacturing']);
  compare.comparison={mode:'side',run:'current',scenario:'uncontrolled'};
  const compared=await context.prepareWorkspaceChart(compare,{ids:[]});
  assert.deepEqual(plain(compared.traces[0].data),[4,5,6]);
  assert.deepEqual(plain(compared.reference[0].data),[null,null,null]);
  assert.ok(compared.notes.some(note=>note.includes('not recorded for the reference')));
  compare.sourceScenario='best_bess';compare.comparison.scenario='no_bess';
  const optimizedPair=await context.prepareWorkspaceChart(compare,{ids:[]});
  assert.deepEqual(plain(optimizedPair.traces[0].data),[6,7,8]);
  assert.deepEqual(plain(optimizedPair.reference[0].data),[5,6,7]);
  const preset=context.presetChart('categoryLoad','Study Inputs',ctx.gallery);
  assert.equal((await context.prepareWorkspaceChart(preset,{ids:[]})).traces.length,3);
});

test('consumption Summary renders category and bus tables with filters and exact period CSV',async()=>{
  const {context,call,captures}=runtime();
  context.fixture=fixture();
  call("run=fixture; workspace.primary='controlled'; workspace.state=emptyLayout(run.manifest.run_id)");
  const sc=call('chartContext()');
  const records=[
    {id:'2',category:'residential',requested_kwh:50.123456789,served_kwh:11,shed_kwh:1,coverage:{requested_kwh:3}},
    {id:'9',category:'commercial',requested_kwh:12,served_kwh:10,shed_kwh:2,coverage:{requested_kwh:3}},
    {id:'11',category:'residential',requested_kwh:58,served_kwh:55,shed_kwh:3,coverage:{requested_kwh:3}},
  ];
  const report={buses:records,categories:[{id:'residential',bus_count:2,coverage:{}},{id:'Total',bus_count:3,coverage:{}}],
    labels:{residential:'Residential',commercial:'Commercial'},expected:3,tariff:.17234567,start:'2021-01-01',last:'2021-01-02'};
  sc.gallery.consumption=10;
  sc.archive.readBlock=async()=>report;
  const root=new Element('section');
  await context.renderLoadConsumption(root,[sc]);
  assert.ok(descendants(root).some(el=>el.textContent==='By load profile category'));
  assert.ok(descendants(root).some(el=>el.textContent==='Individual bus consumption'));
  assert.ok(descendants(root).some(el=>el.textContent.includes('study grid-import tariff')));
  choose(select(root,'Profile category'),'residential');
  choose(select(root,'Sort by'),'consumption');
  button(root,'Download bus CSV').onclick();
  const [head,rows]=captures.at(-1);
  assert.equal(head[0],'Bus ID');
  assert.deepEqual(plain(rows).map(row=>row[0]),['11','2']);
  assert.equal(rows[1][2],50.123456789*.001);
  assert.ok(head.includes('Scenario ID')&&head.includes('Expected samples'));
  button(root,'Download category CSV').onclick();
  assert.equal(captures.at(-1)[0][0],'Category');
});
