// Builds docs/diagram/progress.excalidraw: the StoreGear-on-Google-Cloud architecture, coloured by status.
// To update after closing a Linear issue: change the item's status below ('done' | 'wip' | 'todo') and run
//   node docs/diagram/build_progress_diagram.js
// Then open the .excalidraw file at excalidraw.com (menu > Open) or in Obsidian's Excalidraw plugin.
const fs = require('fs');
const path = require('path');

const UPDATED = '2026-10-27';
const HEADLINE = 'Phase 4 closed: endpoint failures handled (backup model in the EU), 22-model catalogue with search by model · next: jury week';

// ---------------------------------------------------------------- content (edit statuses here)
const LAPTOP = [
  ['done', 'VS Code + Claude Code'],
  ['done', 'uv · Python 3.12 · ADK 2.12'],
  ['done', 'hello_agent in adk web'],
  ['done', "gcloud profile 'storegear'"],
  ['done', 'ADC login (no key files)'],
  ['done', 'Repo · ADRs · runbook · SQL'],
];
const GCP = [ // [title, items]
  ['Cost guardrails', [
    ['done', 'Budget €30 + spend cap'],
    ['done', 'Only 6 APIs needed'],
    ['done', 'Cost per answer · weekly check'],
    ['done', 'Dashboard + failure alert'],
  ]],
  ['Identity & secrets', [
    ['done', 'sg-agent · 6 roles'],
    ['done', 'sg-ingestion · 4 roles'],
    ['done', 'Secret: DB admin password'],
    ['done', 'sg-api · login + roles · 7/7'],
    ['done', 'Guardrails + PII · 10/10'],
  ]],
  ['Agent Platform (eu endpoint)', [
    ['done', 'Gemini 3.8 Flash · tested'],
    ['done', 'Agent Runtime · eu · 3.0 s'],
    ['done', 'Sessions · 30-day TTL'],
    ['done', 'Traces · no message text'],
  ]],
  ['Data · Cloud SQL', [
    ['done', 'sg-catalog · PG18 · free trial'],
    ['done', 'Schema + least privilege'],
    ['done', 'Catalog v3 · cloud-built'],
  ]],
  ['Agent code', [
    ['done', 'Hybrid search · 17/17 · 0.6 s'],
    ['done', 'StoreGear agent · rules 1-12'],
    ['done', 'Eval gate passed · 4.95'],
    ['done', 'CI/CD · keyless · smoke checks'],
  ]],
  ['Ingestion pipeline', [
    ['done', 'Parser: Gemini + DocAI fallback'],
    ['done', 'Gate + queue · Cloud Run job'],
    ['done', 'Drive sync · every 15 min'],
  ]],
];
const SOURCES = [
  ['done', 'n8n catalog export ✓'],
  ['done', 'Price/stock Sheet · live'],
  ['done', 'Drive · 10 manuals'],
  ['done', 'n8n baseline · 22 q ✓'],
];
const PHASES = [
  ['done', 'Phase 0 · Foundations', '15-16 Oct'],
  ['done', 'Phase 1 · Working agent', '17-18 Oct'],
  ['done', 'Phase 2 · Ingestion', '19-21 Oct'],
  ['done', 'Phase 3 · Safety', '21-22 Oct'],
  ['done', 'Phase 4 · Ops', '22-29 Oct'],
  ['wip', 'Final · n8n vs GCP', '30-31 Oct'],
];

// ---------------------------------------------------------------- styling
const S = {
  done: { stroke: '#2f9e44', bg: '#d3f9d8', dash: 'solid', ink: '#1e1e1e', mark: '✓ ' },
  wip: { stroke: '#f59f00', bg: '#fff9db', dash: 'solid', ink: '#1e1e1e', mark: '◐ ' },
  todo: { stroke: '#868e96', bg: '#f8f9fa', dash: 'dashed', ink: '#495057', mark: '' },
};

let n = 0;
const els = [];
const base = (o) => ({
  id: `el${++n}`, angle: 0, strokeColor: '#1e1e1e', backgroundColor: 'transparent', fillStyle: 'solid',
  strokeWidth: 2, strokeStyle: 'solid', roughness: 1, opacity: 100, groupIds: [], frameId: null,
  roundness: null, boundElements: [], updated: 1, link: null, locked: false, seed: 1000 + n, version: 1,
  versionNonce: 2000 + n, isDeleted: false, ...o,
});
const rect = (x, y, w, h, o = {}) => els.push(base({ type: 'rectangle', x, y, width: w, height: h, roundness: { type: 3 }, ...o }));
const text = (x, y, w, t, o = {}) => {
  const size = o.fontSize || 16, lines = t.split('\n').length;
  els.push(base({ type: 'text', x, y, width: w, height: Math.round(size * 1.25 * lines), text: t, originalText: t,
    fontSize: size, fontFamily: o.fontFamily || 1, textAlign: o.textAlign || 'center', verticalAlign: 'top',
    containerId: null, lineHeight: 1.25, strokeColor: o.color || '#1e1e1e', autoResize: true }));
};
const arrow = (x, y, dx, dy, o = {}) => els.push(base({ type: 'arrow', x, y, width: Math.abs(dx), height: Math.abs(dy),
  points: [[0, 0], [dx, dy]], lastCommittedPoint: null, startBinding: null, endBinding: null, startArrowhead: null,
  endArrowhead: 'arrow', strokeColor: o.color || '#1e1e1e', strokeStyle: o.dash || 'solid', roundness: { type: 2 } }));
const item = (x, y, w, h, [st, label], size = 15) => {
  const s = S[st];
  rect(x, y, w, h, { strokeColor: s.stroke, backgroundColor: s.bg, strokeStyle: s.dash, strokeWidth: st === 'todo' ? 1 : 2 });
  text(x, y + (h - size * 1.25) / 2, w, s.mark + label, { fontSize: size, color: s.ink });
};
const container = (x, y, w, h, title, stroke, bg, size = 20) => {
  rect(x, y, w, h, { strokeColor: stroke, backgroundColor: bg });
  text(x, y + 10, w, title, { fontSize: size });
};

// ---------------------------------------------------------------- layout
text(40, 20, 1200, 'StoreGear on Google Cloud: progress', { fontSize: 34, textAlign: 'left' });
text(40, 68, 1200, `Updated ${UPDATED} · ${HEADLINE}`, { fontSize: 16, textAlign: 'left', color: '#868e96' });

// legend
[['done', 'Done'], ['wip', 'In progress'], ['todo', 'Planned']].forEach(([st, l], i) => {
  const x = 1170 + i * 130;
  rect(x, 30, 22, 22, { strokeColor: S[st].stroke, backgroundColor: S[st].bg, strokeStyle: S[st].dash, strokeWidth: st === 'todo' ? 1 : 2 });
  text(x + 28, 32, 75, l, { fontSize: 14, textAlign: 'left' });
});

const MAX_ITEMS = Math.max(...GCP.map(([, items]) => items.length));
const BOX_H = 45 + MAX_ITEMS * 51 + 6;           // a group box fits its longest list
const TOP = 120, H = Math.max(600, 50 + 2 * (BOX_H + 15) + 5);
// laptop
container(40, TOP, 280, H, 'Your laptop', '#495057', '#f8f9fa');
LAPTOP.forEach((it, i) => item(55, TOP + 55 + i * 85, 250, 60, it));

// GCP project
container(380, TOP, 860, H, 'Google Cloud · storegear-prod-ag26 · europe-west1', '#862e9c', '#f8f0fc');
GCP.forEach(([title, items], k) => {
  const col = k % 3, row = Math.floor(k / 3);
  const x = 395 + col * 280, y = TOP + 50 + row * (BOX_H + 15), w = 270, h = BOX_H;
  container(x, y, w, h, title, '#495057', '#ffffff', 17);
  items.forEach((it, i) => item(x + 12, y + 45 + i * 51, w - 24, 42, it, 14));
});

// sources
container(1300, TOP, 260, H, 'Data sources', '#1971c2', '#e7f5ff');
SOURCES.forEach((it, i) => item(1315, TOP + 55 + i * 85, 230, 60, it, 14));

// connectors
arrow(325, TOP + 290, 50, 0, { color: '#2f9e44' });
text(320, TOP + 262, 60, 'ADC ✓', { fontSize: 13, color: '#2f9e44' });
arrow(1295, TOP + 440, -50, 0, { color: '#2f9e44' });
text(1240, TOP + 412, 60, 'loaded ✓', { fontSize: 13, color: '#2f9e44' });

// timeline
text(40, TOP + H + 30, 600, 'Timeline (deadline 31 Oct)', { fontSize: 20, textAlign: 'left' });
PHASES.forEach(([st, label, dates], i) => item(40 + i * 256, TOP + H + 70, 240, 70, [st, `${label}\n${dates}`], 15));

const doc = { type: 'excalidraw', version: 2, source: 'https://excalidraw.com', elements: els,
  appState: { gridSize: null, viewBackgroundColor: '#ffffff' }, files: {} };
const out = path.join(__dirname, 'progress.excalidraw');
fs.writeFileSync(out, JSON.stringify(doc, null, 2));
console.log('wrote', out, els.length, 'elements');
