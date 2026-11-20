import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=process.cwd(),data=JSON.parse(await fs.readFile(path.join(root,'cache/workbook.json'),'utf8')),wb=Workbook.create();
const theme='#173c49', sea='#e3f1ec';
function col(i){let s='';for(i++;i;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s}
for(const [name,m] of Object.entries(data)){
 const s=wb.worksheets.add(name),n=m.length,k=m[0].length;s.showGridLines=false;
 const title=s.getRangeByIndexes(0,0,1,k);title.merge();title.values=[[name==='Summary'?'EE499  •  C2 forecasting benchmark':name]];title.format.fill=theme;title.format.font.color='#ffffff';title.format.font.bold=true;title.format.font.size=15;title.format.rowHeight=32;
 const head=s.getRangeByIndexes(2,0,1,k);head.values=[m[0]];head.format.font.bold=true;head.format.fill=sea;head.format.font.color=theme;head.format.rowHeight=26;
 s.getRangeByIndexes(3,0,n-1,k).values=m.slice(1);
 for(let j=0;j<k;j++){
  let item=m[0][j],wid=Math.max(item.length+3,Math.min(item==='Definition'?108:item==='reason'?95:65,Math.max(...m.slice(1).map(row=>typeof row[j]==='string'?row[j].length+2:0))),12);
  let region=s.getRangeByIndexes(2,j,n,1);region.format.columnWidth=wid;
  if(m.slice(1).some(row=>typeof row[j]==='number'))s.getRangeByIndexes(3,j,n-1,1).setNumberFormat(/rank|rows|warning_count|forecast_blocks|_hours|bus_id|^FAILED$|^OK$|incomplete|skipped|configuration_count/.test(item)?'0.####':'#,##0.0000');
 }
 if(name==='Full ranking'){
  const formulas=m.slice(1).map((r,i)=>[r[0]==='Bus_01'?null:`=(5*E${i+4}+5*F${i+4}+5*G${i+4}+2*H${i+4}+4*I${i+4}+3*J${i+4})/24`]);
  const start=m.slice(1).findIndex(r=>r[0]==='Bus_01');for(let i=0;i<formulas.length;){if(formulas[i][0]===null){i++;continue}let j=i+1;while(j<formulas.length&&formulas[j][0]!==null)j++;s.getRangeByIndexes(3+i,10,j-i,1).formulas=formulas.slice(i,j);i=j}
 }
 if(name==='Overall ranking'){let j=m[0].indexOf('score');s.getRangeByIndexes(3,j,n-1,1).formulas=m.slice(1).map((_,i)=>[`=(2*B${i+4}+C${i+4}+D${i+4}+E${i+4}+3*F${i+4}+G${i+4})/9`])}
 s.freezePanes.freezeRows(3);
}
wb.recalculate();
await fs.mkdir('cache/xls_renders',{recursive:true});for(const name of Object.keys(data)){
 let blob=await wb.render({sheetName:name,range:'A1:F8',scale:0.75});await fs.writeFile(path.join('cache/xls_renders',name+'.png'),new Uint8Array(await blob.arrayBuffer()));
}
console.log((await wb.inspect({kind:'table',range:"'Overall ranking'!A3:I5",include:'values,formulas',tableMaxRows:3,tableMaxCols:9})).ndjson);
const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(root,'C2_Analysis/00_Overview/C2_Rankings.xlsx'));
