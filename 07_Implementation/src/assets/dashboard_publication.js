// Offline publication exports. SVG, PDF and PNG share the same figure geometry.
const publicationSizes={
  single:[89,68],double:[183,111],report:[160,104],slides:[254,142.875],custom:[160,104]
};
const publicationOptions={size:'report',width:160,height:104,dpi:300,full:false,caption:true};
const publicationUTF8=new TextEncoder();
const publicationXml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const publicationName=s=>safeFilename(s).replace(/^[.]*/,'')||'figure';
const publicationColor=['#17628c','#a84b21','#316f54','#734785','#48496b','#916812','#9e3555','#52636e'];
const publicationMath=s=>String(s??'').replace(/[−–—]/g,'-').replace(/·/g,' / ').replace(/²/g,'^2')
  .replace(/³/g,'^3').replace(/≥/g,'>=').replace(/≤/g,'<=').replace(/×/g,'x').replace(/→/g,'->').replace(/ε/g,'epsilon')
  .replace(/[^\x20-\x7e\xb0]/g,'?');
function publicationDimensions(options=publicationOptions){
  if(options.size==='custom')return [options.width,options.height];
  return publicationSizes[options.size]||publicationSizes.report;
}
function publicationControls(root){
  const tools=elem('div',undefined,'controls publication-settings');root.append(tools);
  const custom=elem('div',undefined,'controls');
  selectControl(tools,'Figure dimensions',[
    ['single','IEEE single column · 89 mm'],['double','IEEE double column · 183 mm'],
    ['report','SDP report · 160 mm'],['slides','Widescreen slides'],['custom','Custom dimensions']
  ],publicationOptions.size,v=>{publicationOptions.size=v;custom.hidden=v!=='custom';});
  selectControl(tools,'PNG resolution',[['300','300 dpi'],['600','600 dpi']],String(publicationOptions.dpi),v=>{publicationOptions.dpi=Number(v);});
  checkControl(tools,'Include caption',publicationOptions.caption,v=>{publicationOptions.caption=v;});
  checkControl(tools,'Full selected period',publicationOptions.full,v=>{publicationOptions.full=v;});
  for(const [field,label] of [['width','Width (mm)'],['height','Height (mm)']]){
    const wrapper=elem('label',label),input=elem('input');input.type='number';input.min=60;input.max=300;input.step='any';
    input.value=publicationOptions[field];
    input.onchange=()=>{if(input.checkValidity())publicationOptions[field]=Number(input.value);else input.value=publicationOptions[field];};
    wrapper.append(input);custom.append(wrapper);
  }
  custom.hidden=publicationOptions.size!=='custom';root.append(custom);
}
function publicationGuard(parent,task){
  return async()=>{
    let feedback=parent.querySelector('.publication-feedback');
    if(!feedback){feedback=elem('output',undefined,'publication-feedback');parent.append(feedback);}
    feedback.textContent='Preparing export…';
    try{await task();feedback.textContent='Export ready.';}
    catch(error){feedback.textContent='Export failed: '+error.message;}
  };
}
function publicationWrap(value,max){
  const text=String(value??''),size=Math.max(5,Math.floor(max)),lines=[];
  for(const word of text.split(/\s+/)){
    const prior=lines.at(-1);
    if(prior!==undefined&&prior.length+word.length+1<=size){lines[lines.length-1]+=' '+word;continue;}
    for(let i=0;i<Math.max(1,word.length);i+=size)lines.push(word.slice(i,i+size));
  }
  return lines;
}
function publicationReadout(data,meta){
  const head=[data.axisLabel||'Timestamp or category',
    ...(data.intervals?['First retained timestamp','Last retained timestamp','Partial calendar bucket']:[]),
    ...data.traces.map(s=>exactExportHeader(s,data.unit))];
  const rows=data.axis.map((x,i)=>[x,...(data.intervals?[data.intervals[i]?.start,data.intervals[i]?.end,data.intervals[i]?.partial]:[]),
    ...data.traces.map(s=>s.data[i])]);
  return {head,rows,caption:meta.caption};
}
function publicationGeometry(data,meta,options=publicationOptions){
  const [mmW,mmH]=publicationDimensions(options);
  const w=mmW*4,h=mmH*4,ops=[];
  const line=(points,color='#242d36',thickness=1,dash=[])=>ops.push({type:'line',points,color,thickness,dash});
  const rect=(x,y,width,height,color)=>ops.push({type:'rect',x,y,width,height,color});
  const text=(x,y,value,size=9,color='#17202c',anchor='start')=>ops.push({type:'text',x,y,value:String(value),size,color,anchor});
  const dot=(x,y,r,color)=>ops.push({type:'circle',x,y,r,color});
  const fillWhite=()=>rect(0,0,w,h,'#ffffff');
  fillWhite();
  const title=publicationWrap(meta.title||data.title,(w-34)/7.4);
  title.forEach((s,i)=>text(14,20+i*14,s,13));
  const traces=data.traces.map((s,i)=>({...s,color:/^#[0-9a-f]{6}$/i.test(s.color||'')?s.color:publicationColor[i%publicationColor.length],
    glyph:i%3,dashes:s.dash==='dashed'?[5,3]:[[],[5,3],[2,2],[8,3,2,3]][i%4]}));
  let y=24+14*title.length;
  const keyWidth=traces.length>1?(w-24)/2:w-24;
  const keys=traces.map(s=>publicationWrap(s.label,(keyWidth-28)/5));
  for(let j=0;j<keys.length;j+=2){
    const lines=Math.max(keys[j].length,keys[j+1]?.length||0);
    for(let i=j;i<Math.min(j+2,keys.length);i++){
      const s=traces[i],x=12+(i-j)*keyWidth;
      if(s.style==='bar')rect(x,y+4,14,6,s.color);
      else if(s.style==='points')dot(x+7,y+7,2.4,s.color);
      else line([[x,y+7],[x+16,y+7]],s.color,1.6,s.dashes);
      keys[i].forEach((part,k)=>text(x+20,y+10+10*k,part,9));
    }
    y+=lines*10+3;
  }
  const caption=options.caption&&meta.caption?publicationWrap(meta.caption,(w-30)/5):[];
  const xtitle=data.axisLabel||(data.categorical?'Selected category':'Time / period');
  const footerHeight=42+caption.length*10,plotBottom=h-footerHeight;
  const left=53,right=w-(traces.some(s=>s.axis==='right')?50:19),top=y+18;
  if(plotBottom-top<46||right-left<65)throw Error('Increase the figure size to fit the selected legend, caption and axes.');
  const axis=data.axis,n=axis.length;
  const raw=data.coordinates||(!data.categorical?axis.map(stamp=>typeof stamp==='string'?timeCoordinate(stamp):NaN):null);
  const numeric=raw?.length===n&&raw.every(Number.isFinite),a=numeric?raw[0]:0,b=numeric?raw.at(-1):n-1;
  const anyBars=traces.some(s=>s.style==='bar')||data.stack||data.waterfall;
  const x=i=>left+(right-left)*(numeric?(b===a?.5:(raw[i]-a)/(b-a)):
    anyBars?(i+.5)/Math.max(1,n):n===1?.5:i/Math.max(1,n-1));
  const low={left:Infinity,right:Infinity},high={left:-Infinity,right:-Infinity};
  const track=(v,side)=>{if(academicNumber(v)){low[side]=Math.min(low[side],v);high[side]=Math.max(high[side],v);}};
  for(const s of traces){
    const side=s.axis||'left';
    s.data.forEach(v=>track(v,side));if(s.style==='bar'||data.stack||data.waterfall)track(0,side);
  }
  if(data.waterfall)data.waterfall.forEach(v=>track(v,'left'));
  if(data.stack)for(let i=0;i<n;i++){
    for(const side of ['left','right']){
      const values=traces.filter(s=>(s.axis||'left')===side).map(s=>s.data[i]).filter(academicNumber);
      track(academicSum(values.filter(v=>v>0)),side);track(academicSum(values.filter(v=>v<0)),side);
    }
  }
  const scales={};
  for(const side of ['left','right']){
    if(low[side]===Infinity)continue;
    if(low[side]===high[side]){
      const pad=Math.abs(low[side])*.035||1;low[side]-=pad;high[side]+=pad;
    }
    const a=low[side],b=high[side],p=(b-a)*.045,min=a-p,max=b+p;
    const coord=v=>plotBottom-(plotBottom-top)*(v-min)/(max-min);scales[side]=coord;
    const unit=traces.find(s=>(s.axis||'left')===side)?.unit||data.unit;
    text(side==='left'?left:right,top-7,unit||'Value',9,'#263e4c',side==='left'?'start':'end');
    for(let j=0;j<=4;j++){
      const value=min+(max-min)*j/4,py=coord(value);
      if(side==='left'||!scales.left)line([[left,py],[right,py]],'#d5dee5',.7);
      text(side==='left'?left-6:right+5,py+3,fmt(value),8,'#263e4c',side==='left'?'end':'start');
    }
  }
  line([[left,top],[left,plotBottom],[right,plotBottom]],'#314150');
  const bars=traces.filter(s=>s.style==='bar'),barWidth=Math.min(33,(right-left)/Math.max(1,n)*.78);
  const positive=Array(n).fill(0),negative=Array(n).fill(0);
  for(const [j,s] of traces.entries()){
    const yy=scales[s.axis||'left'];
    if(!yy)continue;
    if(s.style==='bar'||data.stack||data.waterfall){
      s.data.forEach((v,i)=>{
        if(!academicNumber(v))return;
        const bucket=v<0?negative:positive;
        const prior=data.waterfall?data.waterfall[i]:data.stack?bucket[i]:0;
        const value=data.waterfall?v:prior+v;
        if(data.stack)bucket[i]+=v;
        const width=data.stack||data.waterfall?barWidth:barWidth/Math.max(1,bars.length);
        const offset=data.stack||data.waterfall?0:(bars.indexOf(s)-(bars.length-1)/2)*width;
        const xx=x(i)+offset,py=yy(value),base=yy(prior);
        rect(xx-width/2,Math.min(py,base),width,Math.max(.45,Math.abs(py-base)),s.color);
        if(data.waterfall&&i<n-1)line([[xx+width/2,py],[x(i+1)-width/2,py]],'#52636e',.6,[3,2]);
      });continue;
    }
    let segment=[];
    s.data.forEach((v,i)=>{
      if(!academicNumber(v)){if(segment.length>1&&s.style!=='points')line(segment,s.color,1.45,s.dashes);segment=[];return;}
      const p=[x(i),yy(v)];segment.push(p);
      if(data.markers||s.style==='points'||n===1){
        if(s.glyph===1)rect(p[0]-1.8,p[1]-1.8,3.6,3.6,s.color);
        else if(s.glyph===2)line([[p[0]-2,p[1]+2],[p[0],p[1]-2],[p[0]+2,p[1]+2],[p[0]-2,p[1]+2]],s.color,.8);
        else dot(...p,1.85,s.color);
      }
    });
    if(segment.length>1&&s.style!=='points')line(segment,s.color,1.45,s.dashes);
  }
  const count=Math.max(2,Math.min(n,Math.floor((right-left)/(n<=14&&data.categorical?54:83))));
  const ticks=[...new Set(Array.from({length:count},(_,i)=>Math.round(i*(n-1)/(count-1))))];
  ticks.forEach((i,j)=>{
    const stamp=typeof axis[i]==='number'?fmt(axis[i]):String(axis[i]??''),max=(right-left)/(count-1)/4.5;
    const val=stamp.length>max?stamp.slice(0,Math.max(4,Math.floor(max)-1))+'…':stamp;
    text(x(i),plotBottom+12,val,8,'#263e4c',j===0?'start':j===ticks.length-1?'end':'middle');
    line([[x(i),plotBottom],[x(i),plotBottom+4]],'#52636e',.75);
  });
  text((left+right)/2,plotBottom+28,xtitle,9,'#263e4c','middle');
  caption.forEach((part,i)=>text(14,plotBottom+43+i*10,part,9));
  return {w,h,mmW,mmH,ops};
}
function publicationSvg(geometry){
  const {w,h,mmW,mmH,ops}=geometry;
  const body=ops.map(op=>{
    const {type,x,y,color}=op;
    if(type==='rect')return '<rect x="'+x+'" y="'+y+'" width="'+op.width+'" height="'+op.height+'" fill="'+color+'"/>';
    if(type==='circle')return '<circle cx="'+x+'" cy="'+y+'" r="'+op.r+'" fill="'+color+'"/>';
    if(type==='text')return '<text x="'+x+'" y="'+y+'" text-anchor="'+op.anchor+'" fill="'+color+'" font-size="'+op.size+'">'+publicationXml(op.value)+'</text>';
    return '<polyline points="'+op.points.map(p=>p.join(',')).join(' ')+'" stroke="'+color+'" stroke-width="'+op.thickness+
      '" stroke-dasharray="'+op.dash.join(' ')+'" fill="none"/>';
  }).join('');
  return '<svg xmlns="http://www.w3.org/2000/svg" width="'+mmW+'mm" height="'+mmH+'mm" viewBox="0 0 '+w+' '+h+
    '" font-family="Arial, sans-serif">'+body+'</svg>';
}
function publicationPdf({w,h,mmW,mmH,ops}){
  const f=x=>Number(x.toFixed(4)),scale=72/25.4/4;
  const rgb=color=>[1,3,5].map(i=>f(parseInt(color.slice(i,i+2),16)/255)).join(' ');
  const p=(x,y)=>f(x)+' '+f(h-y);
  const escape=s=>publicationMath(s).replace(/[\\()]/g,c=>'\\'+c).replace(/°/g,'\\260');
  const stream=['q '+scale+' 0 0 '+scale+' 0 0 cm'];
  for(const op of ops){
    const {type,x,y,color}=op;
    if(type==='rect')stream.push(rgb(color)+' rg '+p(x,y+op.height)+' '+f(op.width)+' '+f(op.height)+' re f');
    else if(type==='circle'){
      const points=Array.from({length:12},(_,i)=>[x+op.r*Math.cos(i*Math.PI/6),y+op.r*Math.sin(i*Math.PI/6)]);
      stream.push(rgb(color)+' rg '+points.map(([x,y],i)=>p(x,y)+(i?' l':' m')).join(' ')+' h f');
    }else if(type==='text'){
      const width=publicationMath(op.value).length*op.size*.48;
      const at=x-(op.anchor==='middle'?width/2:op.anchor==='end'?width:0);
      stream.push(rgb(color)+' rg BT /F1 '+op.size+' Tf '+p(at,y)+' Td ('+escape(op.value)+') Tj ET');
    }else stream.push(rgb(color)+' RG '+op.thickness+' w ['+op.dash.join(' ')+'] 0 d '+
      op.points.map(([x,y],i)=>p(x,y)+(i?' l':' m')).join(' ')+' S');
  }
  const contents=stream.join('\n')+'\nQ\n';
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 '+f(mmW*72/25.4)+' '+f(mmH*72/25.4)+
      '] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    '<< /Length '+contents.length+' >>\nstream\n'+contents+'endstream'];
  let pdf='%PDF-1.4\n',positions=[0];
  objects.forEach((s,i)=>{positions.push(pdf.length);pdf+=(i+1)+' 0 obj\n'+s+'\nendobj\n';});
  const start=pdf.length;
  pdf+='xref\n0 '+positions.length+'\n0000000000 65535 f \n'+positions.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+
    'trailer\n<< /Size '+positions.length+' /Root 1 0 R >>\nstartxref\n'+start+'\n%%EOF\n';
  return new Blob([pdf],{type:'application/pdf'});
}
const publicationCrcTable=Uint32Array.from({length:256},(_,i)=>{
  for(let bit=0;bit<8;bit++)i=i&1?0xedb88320^(i>>>1):i>>>1;
  return i>>>0;
});
function publicationCrc(bytes){
  let c=0xffffffff;
  for(const b of bytes)c=publicationCrcTable[(c^b)&255]^(c>>>8);
  return (c^0xffffffff)>>>0;
}
async function publicationPng(geometry,dpi){
  const svg=new Blob([publicationSvg(geometry)],{type:'image/svg+xml'}),url=URL.createObjectURL(svg),img=new Image();
  try{
    await new Promise((ok,fail)=>{img.onload=ok;img.onerror=()=>fail(Error('SVG could not be rasterized.'));img.src=url;});
    const cv=elem('canvas');
    cv.width=Math.round(geometry.mmW*dpi/25.4);cv.height=Math.round(geometry.mmH*dpi/25.4);
    cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);
    const blob=await new Promise(resolve=>cv.toBlob(resolve,'image/png'));
    if(!blob)throw Error('PNG encoder failed.');
    const original=new Uint8Array(await blob.arrayBuffer()),chunk=new Uint8Array(21),view=new DataView(chunk.buffer);
    view.setUint32(0,9);chunk.set(publicationUTF8.encode('pHYs'),4);
    const scale=Math.round(dpi/.0254);view.setUint32(8,scale);view.setUint32(12,scale);chunk[16]=1;
    view.setUint32(17,publicationCrc(chunk.subarray(4,17)));
    const data=new DataView(original.buffer),parts=[original.subarray(0,8)];
    for(let i=8;i<original.length;){
      const n=data.getUint32(i),tag=String.fromCharCode(...original.subarray(i+4,i+8));
      if(tag!=='pHYs')parts.push(original.subarray(i,i+n+12));
      if(tag==='IHDR')parts.push(chunk);
      i+=n+12;
    }
    return new Blob(parts,{type:'image/png'});
  }finally{URL.revokeObjectURL(url);}
}
const publicationCSV=(head,rows)=>'\uFEFF'+csvLine(head)+rows.map(csvLine).join('');
function publicationZip(entries){
  const local=[],central=[];
  let offset=0,centralSize=0;
  for(const [name,value] of entries){
    const key=publicationUTF8.encode(name),bytes=typeof value==='string'?publicationUTF8.encode(value):value;
    const crc=publicationCrc(bytes),loc=new Uint8Array(30),lh=new DataView(loc.buffer),rec=new Uint8Array(46),rh=new DataView(rec.buffer);
    lh.setUint32(0,0x04034b50,true);lh.setUint16(4,20,true);lh.setUint16(6,0x800,true);
    lh.setUint16(12,33,true);lh.setUint32(14,crc,true);lh.setUint32(18,bytes.length,true);lh.setUint32(22,bytes.length,true);
    lh.setUint16(26,key.length,true);
    rh.setUint32(0,0x02014b50,true);rh.setUint16(4,20,true);rh.setUint16(6,20,true);rh.setUint16(8,0x800,true);
    rh.setUint16(14,33,true);rh.setUint32(16,crc,true);rh.setUint32(20,bytes.length,true);rh.setUint32(24,bytes.length,true);
    rh.setUint16(28,key.length,true);rh.setUint32(42,offset,true);
    local.push(loc,key,bytes);central.push(rec,key);
    offset+=loc.length+key.length+bytes.length;centralSize+=rec.length+key.length;
  }
  const end=new Uint8Array(22),eh=new DataView(end.buffer);
  eh.setUint32(0,0x06054b50,true);eh.setUint16(8,entries.length,true);eh.setUint16(10,entries.length,true);
  eh.setUint32(12,centralSize,true);eh.setUint32(16,offset,true);
  return new Blob([...local,...central,end],{type:'application/zip'});
}
function publicationXlsx(head,rows){
  const quote='http://schemas.openxmlformats.org/';
  const contents='<Types xmlns="'+quote+'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+
    '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>';
  const relationships=(type,target)=>'<Relationships xmlns="'+quote+'package/2006/relationships"><Relationship Id="rId1" Type="'+
    quote+'officeDocument/2006/relationships/'+type+'" Target="'+target+'"/></Relationships>';
  const workbook='<workbook xmlns="'+quote+'spreadsheetml/2006/main" xmlns:r="'+quote+'officeDocument/2006/relationships">'+
    '<sheets><sheet name="Results" sheetId="1" r:id="rId1"/></sheets></workbook>';
  function address(i){
    let out='';
    for(i++;i>0;i=Math.floor((i-1)/26))out=String.fromCharCode(65+(i-1)%26)+out;
    return out;
  }
  const records=[head,...rows].map((row,i)=>'<row r="'+(i+1)+'">'+row.map((value,j)=>{
    if(value==null)return '';
    const pos=address(j)+(i+1);
    if(academicNumber(value))return '<c r="'+pos+'"><v>'+value+'</v></c>';
    const safe=String(value).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g,'');
    return '<c r="'+pos+'" t="inlineStr"><is><t xml:space="preserve">'+publicationXml(safe)+'</t></is></c>';
  }).join('')+'</row>').join('');
  const sheet='<worksheet xmlns="'+quote+'spreadsheetml/2006/main"><sheetData>'+records+'</sheetData></worksheet>';
  return publicationZip([['[Content_Types].xml',contents],['_rels/.rels',relationships('officeDocument','xl/workbook.xml')],
    ['xl/_rels/workbook.xml.rels',relationships('worksheet','worksheets/sheet1.xml')],
    ['xl/workbook.xml',workbook],['xl/worksheets/sheet1.xml',sheet]]);
}
function publicationTex(head,rows){
  const escapes={'\\':'\\textbackslash{}','&':'\\&','%':'\\%','$':'\\$','#':'\\#','_':'\\_',
    '{':'\\{','}':'\\}','~':'\\textasciitilde{}','^':'\\textasciicircum{}','°':'\\textdegree{}'};
  const cell=v=>String(v??'').replace(/[\\&%$#_{}~^°]/g,c=>escapes[c]).replace(/[\r\n]+/g,' ');
  return '% Compile with a Unicode-capable LaTeX engine for archived text.\n\\begin{tabular}{'+head.map(()=> 'l').join('')+'}\n'+
    [head,...rows].map(row=>row.map(cell).join(' & ')+' \\\\').join('\n')+'\n\\end{tabular}\n';
}
function publicationMark(root,record){root.publicationRecord=record;}
function publicationActions(root,controller,meta,specialGeometry=null){
  const exports=elem('details',undefined,'publication-menu');
  exports.append(elem('summary','Publication export'));root.append(exports);
  publicationControls(exports);
  const tools=elem('div',undefined,'controls');exports.append(tools);
  const name=publicationName([shortRun(meta.ctx.archive),meta.ctx.data.label,meta.title].join('_'));
  for(const kind of ['SVG','PNG','Vector PDF','CSV']){
    button(tools,kind,publicationGuard(exports,async()=>{
      const data=controller.publicationData(publicationOptions.full);
      if(kind==='CSV'){
        const exact=publicationReadout(data,meta);saveRows(exact.head,exact.rows,name+'.csv');return;
      }
      const geometry=specialGeometry?specialGeometry(publicationOptions):publicationGeometry(data,meta);
      const [blob,ext]=kind==='SVG'?[new Blob([publicationSvg(geometry)],{type:'image/svg+xml'}),'svg']:
        kind==='PNG'?[await publicationPng(geometry,publicationOptions.dpi),'png']:[publicationPdf(geometry),'pdf'];
      saveBlob(blob,name+'.'+ext);
    }));
  }
  publicationMark(root,{type:'chart',title:meta.title,meta,controller,geometry:specialGeometry});
}
function publicationTable(root,title,head,rows,ctx,note){
  const menu=elem('div',undefined,'controls publication-table-tools');root.append(menu);
  const name=publicationName(title);
  button(menu,'CSV',()=>saveRows(head,rows,name+'.csv'));
  button(menu,'XLSX',publicationGuard(menu,()=>saveBlob(publicationXlsx(head,rows),name+'.xlsx')));
  button(menu,'LaTeX',publicationGuard(menu,()=>saveBlob(new Blob([publicationTex(head,rows)],{type:'text/plain'}),name+'.tex')));
  publicationMark(root,{type:'table',title,head,rows,meta:{ctx,caption:note||''}});
}
function publicationNetwork(svg,ctx,stamp){
  const clone=svg.cloneNode(true);
  clone.removeAttribute('class');
  clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
  clone.setAttribute('font-family','Arial, sans-serif');
  for(const n of clone.querySelectorAll('[tabindex]')){
    n.removeAttribute('tabindex');n.removeAttribute('role');
    if(n.classList.contains('academic-path'))n.setAttribute('stroke','#9d5308');
    n.removeAttribute('class');
  }
  const desc=document.createElementNS(svg.namespaceURI,'desc');
  desc.textContent=shortRun(ctx.archive)+' · '+ctx.data.label+' · '+stamp;clone.prepend(desc);
  saveBlob(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml'}),publicationName(shortRun(ctx.archive))+'_single_line.svg');
}
function publicationRenderSpecial(root,title,geometry,meta,data,heading,titleNote){
  const card=elem('article',undefined,'workspace-card academic-figure');root.append(card);
  card.append(elem('h3',title),elem('p',titleNote||meta.caption,'fine'));
  const preview=elem('img',undefined,'publication-preview');
  preview.alt=heading;
  preview.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(publicationSvg(geometry(publicationOptions)));
  card.append(preview);
  publicationActions(card,{publicationData:()=>data},meta,geometry);
}
function publicationSankey(root,ctx,title,left,right,note){
  const supply=academicSum(left.map(r=>r[1])),uses=academicSum(right.map(r=>r[1])),scale=Math.max(supply,uses);
  if(!(scale>0)||[...left,...right].some(r=>!academicNumber(r[1])||r[1]<0))return academicMissing(root,'A positive, complete energy ledger is required.');
  const meta={title,ctx,caption:note};
  function geometry(options){
    const [mmW,mmH]=publicationDimensions(options),w=mmW*4,h=mmH*4,ops=[];
    const rect=(x,y,width,height,color)=>ops.push({type:'rect',x,y,width,height,color});
    const text=(x,y,value,size=9,anchor='start')=>ops.push({type:'text',x,y,value,size,anchor,color:'#17202c'});
    const line=(points,color,thickness)=>ops.push({type:'line',points,color,thickness,dash:[]});
    rect(0,0,w,h,'#ffffff');text(14,20,title,13);
    const top=61,bottom=h-61,span=Math.max(25,bottom-top);
    const labels=(rows,mirror)=>{
      let flow=0;
      rows.forEach(([label,value],i)=>{
        const leftX=mirror?w*.74:w*.26,midX=mirror?w*.52:w*.48,size=value/scale*span,center=top+flow+size/2;
        if(size>0)line([[leftX,top+(i+.5)*span/rows.length],[midX,center]],publicationColor[i%publicationColor.length],size);
        flow+=size;
      });
      rows.forEach(([label,value],i)=>{
        const x=mirror?w*.75:12,y=top+(i+.5)*span/rows.length;
        const name=publicationWrap(label,(w*.23-13)/4.4);
        name.forEach((part,j)=>text(x,y-4+j*8,part,8.5));
        text(x,y+5+(name.length-1)*8,fmt(value)+' kWh',8);
      });
    };
    labels(left,false);labels(right,true);
    rect(w*.48,top,w*.04,supply/scale*span,'#40556a');
    rect(w*.50,top,w*.02,uses/scale*span,'#687d8a');
    text(w*.5,44,'AC bus',10,'middle');
    text(12,h-34,'Supply − uses: '+fmt(supply-uses)+' kWh',9);
    if(options.caption)publicationWrap(note,(w-24)/5).forEach((part,i)=>text(12,h-22+i*10,part,8.5));
    return {w,h,mmW,mmH,ops};
  }
  const rows=[...left,...right],data={title,axis:rows.map(r=>r[0]),traces:[{label:'AC energy',unit:'kWh',data:rows.map(r=>r[1])}],
    unit:'kWh',axisLabel:'Energy component',categorical:true};
  publicationRenderSpecial(root,title,geometry,meta,data,'Energy flow through the AC bus',note);
}
function publicationWaterfall(root,ctx,title,start,changes,end,unit,reference){
  let previous=start;
  const starts=[0],axis=['Reference'],steps=[start];
  for(const [label,delta] of changes){starts.push(previous);previous+=delta;axis.push(label);steps.push(previous);}
  starts.push(0);axis.push('Candidate');steps.push(end);
  const data={title,axis,unit,categorical:true,axisLabel:'Ledger component',waterfall:starts,
    traces:[{label:'Cumulative annual cost',unit,data:steps,style:'bar'}]};
  const meta={ctx,title,caption:'Reference: '+reference+' · Candidate: '+ctx.data.label+' · Signed changes use archived ledger components.'};
  publicationRenderSpecial(root,title,options=>publicationGeometry(data,meta,options),meta,data,'Signed annual cost waterfall');
  academicTable(root,'Waterfall numerical data',['Component','Start ('+unit+')','End ('+unit+')','Signed change ('+unit+')'],
    axis.map((name,i)=>[name,starts[i],steps[i],(i===0||i===steps.length-1)?null:steps[i]-starts[i]]),ctx);
}
async function publicationPackage(records,ctx,topic,formats){
  const prefix=academicConfig[topic]||'10_Methodology_and_Provenance',index=[],failures=[],entries=[];
  const options={...publicationOptions},used=new Map();
  for(const item of records){
    const base=publicationName(item.title),count=(used.get(base)||0)+1;used.set(base,count);
    const file=prefix+'/'+base+(count>1?'_'+count:''),meta=item.meta;
    try{
      if(item.type==='table'){
        entries.push([file+'.csv',publicationCSV(item.head,item.rows)]);
        if(formats.has('xlsx'))entries.push([file+'.xlsx',new Uint8Array(await publicationXlsx(item.head,item.rows).arrayBuffer())]);
        if(formats.has('tex'))entries.push([file+'.tex',publicationTex(item.head,item.rows)]);
        continue;
      }
      const data=item.controller.publicationData(options.full),exact=publicationReadout(data,meta);
      const geometry=item.geometry?item.geometry(options):publicationGeometry(data,meta,options);
      entries.push([file+'.svg',publicationSvg(geometry)],[file+'.csv',publicationCSV(exact.head,exact.rows)]);
      if(formats.has('pdf'))entries.push([file+'.pdf',new Uint8Array(await publicationPdf(geometry).arrayBuffer())]);
      if(formats.has('png'))entries.push([file+'.png',new Uint8Array(await (await publicationPng(geometry,options.dpi)).arrayBuffer())]);
      index.push([index.length+1,file+'.svg',meta.caption,meta.ctx.archive.manifest.run_id,meta.ctx.data.label,
        data.traces.map(s=>s.unit||data.unit).filter(Boolean).join(', '),data.axis[0],data.axis.at(-1),
        [...new Set(data.traces.map(s=>s.aggregation).filter(Boolean))].join('; '),file+'.csv',
        data.traces.map(s=>s.data.filter(academicNumber).length+'/'+data.axis.length).join('; ')]);
    }catch(error){failures.push(item.title+': '+error.message);}
  }
  if(!entries.length)throw Error('The selected artifacts could not be generated. '+failures.join(' '));
  entries.push(['Figure_Index.csv',publicationCSV(['Figure ID','Figure','Caption','Study ID','Scenario','Units','First label','Last label',
      'Aggregation','Underlying CSV','Valid plotted values per series'],index)],
    ['Study_Manifest.json',JSON.stringify({study:ctx.archive.manifest,scenario:ctx.scenario,options,failed:failures},null,2)],
    ['01_Study_Configuration/Archived_Configuration.json',JSON.stringify({settings:ctx.archive.metadata?.simulation,
      economics:ctx.archive.manifest.economics,solver:ctx.archive.manifest.solver,inputs:ctx.archive.input_info},null,2)],
    ['README.md','# Academic figure and table exports\n\nSelected active view: '+(academicTopicLabels[topic]||topic)+
      '. CSVs retain selected numerical precision. Use the accompanying original portable report for canonical data and methodology.\n\n'+
      (failures.length?'## Skipped / errors\n\n'+failures.map(e=>'- '+e).join('\n'):'All selected artifacts generated.')+'\n']);
  return publicationZip(entries);
}
function publicationBatchControl(tools,scope,ctx,topic){
  const menu=elem('details',undefined,'publication-menu');
  menu.append(elem('summary','Academic ZIP'));scope.append(menu);
  const choices=elem('div'),formats=elem('div',undefined,'controls');
  const selected=new Set(['pdf','xlsx','tex']);
  let items=[],checks=[];
  menu.append(choices,formats);
  publicationControls(menu);
  for(const [key,label] of [['pdf','Vector PDFs'],['png','High-resolution PNGs'],['xlsx','XLSX tables'],['tex','LaTeX tables']])
    checkControl(formats,label,selected.has(key),value=>{if(value)selected.add(key);else selected.delete(key);});
  menu.ontoggle=()=>{
    if(!menu.open)return;
    const container=scope.parentElement;
    items=[...container.querySelectorAll('.workspace-card,.academic-table')].map(node=>node.publicationRecord).filter(Boolean);
    choices.replaceChildren();
    if(!items.length)choices.append(elem('p','No exportable artifacts in the active view.','fine'));
    checks=items.map(item=>checkControl(choices,item.title,true,()=>{}));
  };
  button(menu,'Save selected ZIP',publicationGuard(menu,async()=>{
    const records=items.filter((record,i)=>checks[i]?.checked);
    if(!records.length)throw Error('Select at least one available figure or table.');
    saveBlob(await publicationPackage(records,ctx,topic,selected),publicationName(shortRun(ctx.archive))+'_academic_'+publicationName(topic)+'.zip');
  }));
}
