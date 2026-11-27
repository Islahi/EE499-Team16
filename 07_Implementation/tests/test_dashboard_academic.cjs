const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const context = vm.createContext({
  location: {hash: ''}, document: {readyState: 'loading', addEventListener() {}},
  URLSearchParams, Blob, Response, TextDecoder, TextEncoder, DecompressionStream, atob
});
for (const file of ['dashboard_gallery.js', 'dashboard_layout.js', 'dashboard_workspace.js', 'dashboard_health.js',
  'dashboard_academic.js', 'dashboard_academic_topics.js', 'dashboard_publication.js', 'dashboard.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/assets', file), 'utf8'), context);
}
const clone = value => JSON.parse(JSON.stringify(value));

test('electrical path follows branches while profile ordering follows bus IDs', () => {
  const topology = {buses: [{bus_id: 1, is_slack: true}, {bus_id: 2}, {bus_id: 10}], lines: [
    {line_id: 'A', from_bus: 10, to_bus: 1}, {line_id: 'B', from_bus: 10, to_bus: 2}
  ]};
  assert.deepEqual(clone(context.academicPath(topology, 2)), {buses: ['1', '10', '2'], lines: ['A', 'B']});
  assert.equal(context.academicPath(topology, 9), null);
  assert.deepEqual(['10', '2', '1'].sort(vm.runInContext('academicNumeric', context)), ['1', '2', '10']);
});

test('duration weighted statistics retain missing intervals and measured zero', () => {
  const axis = ['2020-02-29 00:00:00', '2020-02-29 00:30:00', '2020-02-29 03:00:00', '2020-03-01 00:00:00'];
  const range = {axis, durations: [.5, 2.5, null, 1], valid: [true, true, false, true]};
  const values = [0, 12, 999, null];
  assert.deepEqual(clone(context.academicStats(values, range)), {
    count: 2, hours: 3, timed: 2, minimum: 0, maximum: 12, peak: axis[1], mean: 10, energy: 30
  });
  const curve = context.academicDuration(values, range);
  assert.deepEqual(clone(curve), {hours: 3, axis: [2.5 * 100 / 3, 100], data: [12, 0]});
  const bins = context.academicBuckets(axis, range.durations, [values], undefined, true, range.valid);
  assert.deepEqual(clone(bins).map(r => [r.label,r.sum]), [['2020-02',[30]], ['2020-03',[null]]]);
});

test('holdout scores use paired denominators and positive underprediction bias', () => {
  assert.deepEqual(clone(context.academicForecastScores([0, 20, null, 5], [0, 10, 900, 10])),
    [3, 5, Math.sqrt(125/3), 60, 5/3, (200 * 10 / 30 + 200 * 5 / 15) / 2, 2]);
  assert.deepEqual(clone(context.academicForecastScores([0], [0])), [1, 0, 0, null, 0, null, 0]);
});

test('conversion loss accounts for inventory change and ignores disjoint time coverage', () => {
  const u = {cfg: {p: 10, e: 40, eta_discharge: .9, soc_min: .1, soc_max: .9},
    p: [-10, 5], charge: [10, 0], discharge: [0, 5], pre: [.5, .7], post: [.7, .6]};
  const range = {axis: ['2021-01-01 00:00:00','2021-01-01 01:00:00'], durations: [1, 1], valid: [true, true]};
  const result = context.academicBatteryStats(u, range);
  assert.ok(Math.abs(result.conversion - 1) < 1e-12);
  assert.equal(result.cycles, 5 / .9 / 40);
  assert.equal(context.academicBatteryStats(u, {...range, axis: [range.axis[0], '2021-01-01 02:00:00']}).conversion, null);
});

test('figures retain gaps, units, physical dimensions and vector-only PDF', async () => {
  const data = {axis: [1, 2, 10], unit: 'pu', categorical: true, markers: true,
    axisLabel: 'Bus number', traces: [{data: [1, null, .953123456789], label: 'Final & verified', unit: 'pu'}]};
  const meta = {title: 'Bus voltage', caption: 'Static snapshot'};
  const geom = context.publicationGeometry(data,meta,{size:'single',caption:true});
  assert.equal(geom.mmW,89);
  const svg = context.publicationSvg(geom), pdf=await context.publicationPdf(geom).text();
  assert.match(svg,/width="89mm"/);
  assert.match(svg,/Final &amp; verified/);
  assert.equal((svg.match(/<circle/g)||[]).length,2);
  assert.match(pdf,/^%PDF-1\.4/);
  assert.doesNotMatch(pdf,/\/Subtype \/Image/);
  assert.deepEqual(clone(context.publicationReadout(data,meta).rows), [[1,1],[2,null],[10,.953123456789]]);
});

test('portable ZIP comparison uses only the stored dashboard entry', async () => {
  const zip = context.publicationZip([['dashboard.html','<html>archived</html>'],['original.csv','x,y']]);
  zip.name = 'portable.zip';
  assert.equal(await (await context.comparisonReportFile(zip)).text(), '<html>archived</html>');
  assert.equal(await (await context.comparisonReportFile(Object.assign(new Blob(['old html']),{name:'old.html'}))).text(), 'old html');
});
