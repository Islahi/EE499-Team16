// Run with node --test tests/test_dashboard_blocks.cjs. No browser or network required.
const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {gzipSync} = require('node:zlib');
const vm = require('node:vm');

function viewer() {
  const context = vm.createContext({
    location: {hash: ''}, document: {readyState: 'loading', addEventListener() {}},
    atob, Blob, Response, DecompressionStream, TextDecoder, URLSearchParams,
  });
  for (const name of ['dashboard_gallery.js', 'dashboard.js']) {
    vm.runInContext(readFileSync(join(__dirname, '../src/assets', name), 'utf8'), context);
  }
  return context;
}

function tag(id, data) {
  const encoded = gzipSync(JSON.stringify(data)).toString('base64');
  return '<script id="' + id + '" type="application/octet-stream">' + encoded + '</script>';
}

test('a local comparison reads byte-indexed blocks across chunk boundaries', async () => {
  const ctx = viewer();
  // Split an opening tag at 1 MiB after multibyte UTF-8 text.
  const prefix = 'Ω'.repeat(524285);
  const html = new Blob([prefix, tag('report-data', {manifest: {schema_version: 4}, scenarios: {}}),
    tag('report-block-42', [[11, 12], {p_kw: [15, null]}])]);
  const run = await ctx.readSavedReport(html);
  assert.equal(run.manifest.schema_version, 4);
  const values = await ctx.seriesValues({entities: {B2: [[11, 12, 42]]}}, 'B2', 'p_kw', 10, 14, run.readBlock);
  assert.deepEqual(Array.from(values), [null, 15, null, null]);
});

test('chart data exports retain units, negative power, empty readings and exact precision', () => {
  const ctx = viewer();
  assert.equal(ctx.unitOf('voltage_angle_deg'), '°');
  assert.equal(ctx.unitOf('bess_charge_kwh'), 'kWh');
  assert.equal(ctx.csvLine(['Load [kW]', -8.123456, null, 'PV "A"']), '"Load [kW]","-8.123456",,"PV ""A"""\r\n');
});

test('plot reduction preserves a narrow peak and trough in their original order', () => {
  const ctx = viewer(), points = [];
  const canvas = {beginPath(){}, stroke(){}, moveTo(x,y){points.push([x,y]);}, lineTo(x,y){points.push([x,y]);}};
  ctx.drawTrace(canvas, [0, 9, -4, 1, 0, 1, 0, 2], x => x, y => y, 2);
  assert.deepEqual(points.slice(0, 2), [[1,9],[2,-4]]);
});
