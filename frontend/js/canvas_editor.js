'use strict';
/**
 * canvas_editor.js — Éditeur visuel de terrain interactif
 * A1: stabilité drag, A2: vitesse solaire + slider heure, A3: undo/redo,
 * A4: suppression éléments, B1-B7: nouveaux outils de dessin.
 * Vanilla JS + <canvas> — aucune dépendance.
 */

// ─── CONSTANTES ─────────────────────────────────────────────────────────────
const SNAP_M   = 0.1;
const MARGIN   = 80;
const HANDLE_R = 7;
const HEDGE_W  = 6;
const MIN_DIM  = 0.5;

const HEATMAP_STOPS = ["#0a1f3d","#1a4f8a","#5b2d8e","#8b4513","#e07020","#d4a020","#fff3a0"];

const COL = {
  parcel    : { fill: '#e8f0dc', stroke: '#2d5016', lw: 2 },
  grid      : 'rgba(0,0,0,0.045)',
  house     : { fill: '#9e9e9e', stroke: '#333', selStroke: '#1565c0', lw: 1.5 },
  extension : { fill: '#bdbdbd', stroke: '#616161', selStroke: '#1e88e5', lw: 1.5 },
  terrace   : { fill: 'rgba(212,184,150,0.85)', stroke: '#8b6914', selStroke: '#e65100', lw: 1.5 },
  abri      : { fill: 'rgba(160,120,80,0.75)', stroke: '#5d3b1e', selStroke: '#bf6c0a', lw: 1.5 },
  potager   : { fill: 'rgba(120,200,80,0.35)', stroke: '#558b2f', selStroke: '#7cb342', lw: 1.5 },
  hedge     : { stroke: '#2e7d32', selStroke: '#43a047' },
  massif    : { fill: 'rgba(76,175,80,0.22)', stroke: '#388e3c', selStroke: '#66bb6a' },
  massifRond: { fill: 'rgba(76,175,80,0.22)', stroke: '#388e3c', selStroke: '#66bb6a' },
  trou      : { fill: 'rgba(100,180,255,0.30)', stroke: '#1976d2', selStroke: '#42a5f5', lw: 1.5 },
  arbreV    : { fill: 'rgba(100,60,20,0.18)', stroke: '#5d3b1e', selStroke: '#8d5524', crown: 'rgba(40,120,40,0.25)', crownSel: 'rgba(40,120,40,0.45)' },
  shadow    : 'rgba(15,15,30,0.30)',
  dimLine   : '#1565c0',
  handle    : { fill: '#fff', stroke: '#1565c0' },
};

// ─── ÉTAT ───────────────────────────────────────────────────────────────────
const E = {
  parcel    : { w: 20, h: 15 },
  northDeg  : 0,
  house     : { x: 2, y: 2, w: 10, h: 8, hM: 6 },
  terrace   : null,            // B1 : terrasse optionnelle
  extensions: [],              // B2 : { id, x, y, w, h, hM }
  abris     : [],              // B3 : { id, x, y, w, h, hM }
  potagers  : [],              // B4 : { id, x, y, w, h } (pas d'ombre)
  hedges    : [],              // { id, x1, y1, x2, y2, hM }
  massifs   : [],              // { id, pts:[{x,y}], closed, plantes:[] }
  massifsRonds: [],            // B5 : { id, cx, cy, rx, ry, plantes:[] }
  trous     : [],              // B6 : { id, x, y, r }
  arbresV   : [],              // B7 : { id, x, y, trunkR:0.2, crownR, hM }

  lat: 48.8566, lon: 2.3522, tz: 'Europe/Paris', dateRef: '2026-06-21',
  sol: null, climat: null, pas: 1,

  tool : 'select',
  sel  : null,   // { type, id? }
  drag : null,

  // tracé en cours
  hedgePt1     : null,
  hedgePreview : null,
  massifPts    : null,
  massifPreview: null,
  _drawRectState  : null,  // { tool, startTX, startTY } pour Terrasse/Extension/Abri/Potager
  _drawCircleState: null,  // { tool, startTX, startTY } pour MassifRond/Trou/ArbreV

  heatmapCells: null,
  showHeatmap : false,

  sunPositions: [],
  sunIdx      : 0,
  sunPlaying  : false,
  sunTimer    : null,
  sunSpeed    : 1,           // multiplicateur vitesse (0.5/1/2/4)
  sunManualH  : null,        // heure manuelle (null = animation)

  zoom   : 1,
  panOffX: 0,
  panOffY: 0,

  _id           : 0,
  _historyStack : [],
  _redoStack    : [],
};

let canvas, ctx, scale = 20;

// Pan clic-droit
let _isPanning = false, _panStartSX = 0, _panStartSY = 0;

function nextId() { return ++E._id; }

// ─── UNDO / REDO (A3) ────────────────────────────────────────────────────────
function _stateSnapshot() {
  return JSON.stringify({
    parcel: E.parcel, northDeg: E.northDeg,
    house: E.house, terrace: E.terrace,
    extensions: E.extensions, abris: E.abris, potagers: E.potagers,
    hedges: E.hedges, massifs: E.massifs,
    massifsRonds: E.massifsRonds, trous: E.trous, arbresV: E.arbresV,
  });
}

function pushHistory() {
  const snap = _stateSnapshot();
  if (E._historyStack.length && E._historyStack[E._historyStack.length - 1] === snap) return;
  E._historyStack.push(snap);
  if (E._historyStack.length > 60) E._historyStack.shift();
  E._redoStack = [];
}

function undo() {
  if (E._historyStack.length < 2) return;
  E._redoStack.push(E._historyStack.pop());
  _applySnapshot(E._historyStack[E._historyStack.length - 1]);
}

function redo() {
  if (!E._redoStack.length) return;
  const snap = E._redoStack.pop();
  E._historyStack.push(snap);
  _applySnapshot(snap);
}

function _applySnapshot(snap) {
  const s = JSON.parse(snap);
  E.parcel = s.parcel; E.northDeg = s.northDeg;
  E.house = s.house; E.terrace = s.terrace;
  E.extensions = s.extensions; E.abris = s.abris; E.potagers = s.potagers;
  E.hedges = s.hedges; E.massifs = s.massifs;
  E.massifsRonds = s.massifsRonds; E.trous = s.trous; E.arbresV = s.arbresV;
  E.sel = null;
  rebuildHedgeList();
  fitCanvas();
  afterChange();
}

// ─── CONVERSIONS COORDS ─────────────────────────────────────────────────────
function effectiveScale() { return scale * E.zoom; }

function t2s(tx, ty) {
  const sc = effectiveScale();
  return {
    x: MARGIN + tx * sc + E.panOffX,
    y: MARGIN + (E.parcel.h - ty) * sc + E.panOffY,
  };
}
function s2t(sx, sy) {
  const sc = effectiveScale();
  return {
    x: (sx - MARGIN - E.panOffX) / sc,
    y: E.parcel.h - (sy - MARGIN - E.panOffY) / sc,
  };
}
function snap(v) { return Math.round(v / SNAP_M) * SNAP_M; }
function clampV(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// ─── INIT ───────────────────────────────────────────────────────────────────
function initEditor() {
  canvas = document.getElementById('terrain-canvas');
  if (!canvas) return;
  ctx = canvas.getContext('2d');

  fitCanvas();
  const ro = new ResizeObserver(fitCanvas);
  ro.observe(document.getElementById('editor-wrapper'));

  canvas.addEventListener('mousedown',  onDown);
  canvas.addEventListener('mousemove',  onMove);
  canvas.addEventListener('mouseup',    onUp);
  canvas.addEventListener('mouseleave', onLeave);
  canvas.addEventListener('dblclick',   onDblClick);
  canvas.addEventListener('wheel',      onWheel, { passive: false });
  canvas.addEventListener('contextmenu', e => e.preventDefault());

  canvas.addEventListener('touchstart', e => { e.preventDefault(); onDown(e.changedTouches[0]); }, { passive: false });
  canvas.addEventListener('touchmove',  e => { e.preventDefault(); onMove(e.changedTouches[0]); }, { passive: false });
  canvas.addEventListener('touchend',   e => { onUp(e.changedTouches[0]); });

  // Boutons outils : fall-back pour les appels inline onclick
  document.querySelectorAll('.editor-tool-btn[data-tool]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tool = btn.dataset.tool;
      if (tool) selectTool(tool);
    });
  });
  document.querySelectorAll('button[onclick="undo()"], button[title*="Ctrl+Z"], button[title*="Annuler"]').forEach(btn => btn.addEventListener('click', undo));
  document.querySelectorAll('button[onclick="redo()"], button[title*="Ctrl+Y"], button[title*="Rétablir"]').forEach(btn => btn.addEventListener('click', redo));
  document.querySelectorAll('button[onclick="finishDraw()"], button[onclick="cancelDraw()"], button[onclick="fitToScreen()"], button[onclick="resetEditor()"]')
    .forEach(btn => {
      const action = btn.getAttribute('onclick');
      if (action === 'finishDraw()') btn.addEventListener('click', finishDraw);
      if (action === 'cancelDraw()') btn.addEventListener('click', cancelDraw);
      if (action === 'fitToScreen()') btn.addEventListener('click', fitToScreen);
      if (action === 'resetEditor()') btn.addEventListener('click', resetEditor);
    });
  // toggleSunSimulation : géré uniquement via onclick= dans le HTML (pas de double-listener)

  // Clavier : Suppr (A4), Ctrl+Z/Y (A3)
  document.addEventListener('keydown', onKeyDown);

  bindInput('editor-parcel-w', v => { E.parcel.w = parseFloat(v) || 20; pushHistory(); fitCanvas(); afterChange(); });
  bindInput('editor-parcel-h', v => { E.parcel.h = parseFloat(v) || 15; pushHistory(); fitCanvas(); afterChange(); });

  // Dimensions maison (sync bidirectionnel w×h ↔ surface)
  bindInput('editor-house-w', v => {
    E.house.w = Math.max(1, parseFloat(v) || 10);
    setVal('editor-house-surf', (E.house.w * E.house.h).toFixed(0));
    pushHistory(); afterChange();
  });
  bindInput('editor-house-h', v => {
    E.house.h = Math.max(1, parseFloat(v) || 8);
    setVal('editor-house-surf', (E.house.w * E.house.h).toFixed(0));
    pushHistory(); afterChange();
  });
  bindInput('editor-house-surf', v => {
    const surf = Math.max(4, parseFloat(v) || 80);
    // Garde le ratio actuel w/h et redimensionne à la nouvelle surface
    const ratio = E.house.w / E.house.h;
    E.house.h = Math.round(Math.sqrt(surf / ratio) * 2) / 2;
    E.house.w = Math.round((surf / E.house.h) * 2) / 2;
    setVal('editor-house-w', E.house.w);
    setVal('editor-house-h', E.house.h);
    pushHistory(); afterChange();
  });

  const northSlider = document.getElementById('editor-north');
  if (northSlider) {
    northSlider.addEventListener('input', () => {
      E.northDeg = parseFloat(northSlider.value) || 0;
      setElText('editor-north-val', Math.round(E.northDeg) + '°');
      afterChange();
    });
    northSlider.addEventListener('change', () => pushHistory());
  }

  ['editor-lat','editor-lon','editor-tz','editor-date','editor-sol','editor-climat','editor-pas']
    .forEach(id => document.getElementById(id)?.addEventListener('change', syncLocFromInputs));

  // Vitesse solaire (A2)
  document.getElementById('sun-speed-select')?.addEventListener('change', e => {
    E.sunSpeed = parseFloat(e.target.value) || 1;
  });

  // Slider heure manuelle (A2)
  const hourSlider = document.getElementById('sun-hour-slider');
  if (hourSlider) {
    hourSlider.addEventListener('input', () => {
      if (E.sunPlaying) stopSunSimulation();  // drag manuel = pause simulation
      const h = parseFloat(hourSlider.value);
      E.sunManualH = h;
      setElText('sun-hour-label', _formatHour(h));
      _applySunByHour(h);
    });
  }

  syncStateToInputs();
  pushHistory();
  afterChange();
  loadSunCourse();
}

function _formatHour(h) {
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return `${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
}

function _applySunByHour(h) {
  if (!E.sunPositions.length) return;
  let best = 0, bestDiff = Infinity;
  E.sunPositions.forEach((p, i) => {
    const [ph, pm] = p.time.split(':').map(Number);
    const ph_dec = ph + pm / 60;
    const diff = Math.abs(ph_dec - h);
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  });
  E.sunIdx = best;
  const sun = E.sunPositions[best];
  const disp = document.getElementById('sun-time-display');
  if (disp && sun) {
    disp.textContent = `${sun.time} — Az: ${sun.az}° — Haut: ${sun.alt}°`;
    disp.style.display = '';
  }
  render();
}

function bindInput(id, fn) {
  const el = document.getElementById(id);
  if (el) el.addEventListener('input', () => fn(el.value));
}

function fitCanvas() {
  const wrapper = document.getElementById('editor-wrapper');
  if (!wrapper || !canvas) return;
  const W = wrapper.clientWidth  || 800;
  const H = wrapper.clientHeight || 500;
  canvas.width  = W;
  canvas.height = H;
  const availW = W - 2 * MARGIN;
  const availH = H - 2 * MARGIN;
  // Parcelle occupe ~70% de l'espace dispo, entre 18 et 60 px/m
  scale = Math.min(availW * 0.70 / E.parcel.w, availH * 0.70 / E.parcel.h);
  scale = Math.max(18, Math.min(scale, 60));
  // Centrage de la parcelle dans le canvas
  E.zoom   = 1;
  E.panOffX = (W - E.parcel.w * scale) / 2 - MARGIN;
  E.panOffY = (H - E.parcel.h * scale) / 2 - MARGIN;
  render();
}

function fitToScreen() {
  E.zoom = 1; E.panOffX = 0; E.panOffY = 0;
  fitCanvas();
}

function syncStateToInputs() {
  setVal('editor-parcel-w', E.parcel.w);
  setVal('editor-parcel-h', E.parcel.h);
  setVal('editor-house-w',  E.house.w);
  setVal('editor-house-h',  E.house.h);
  setVal('editor-house-surf', (E.house.w * E.house.h).toFixed(0));
  setVal('editor-north',    E.northDeg);
  setElText('editor-north-val', Math.round(E.northDeg) + '°');
  setVal('editor-lat',  E.lat);
  setVal('editor-lon',  E.lon);
  setVal('editor-date', E.dateRef);
}

function syncLocFromInputs() {
  E.lat     = parseFloat(getVal('editor-lat'))  || 48.8566;
  E.lon     = parseFloat(getVal('editor-lon'))  || 2.3522;
  E.tz      = getVal('editor-tz')               || 'Europe/Paris';
  E.dateRef = getVal('editor-date')             || '2026-06-21';
  E.sol     = getVal('editor-sol')     || null;
  E.climat  = getVal('editor-climat')  || null;
  E.pas     = parseFloat(getVal('editor-pas'))  || 1;
  afterChange();
  loadSunCourse();
}

function setVal(id, v)    { const el = document.getElementById(id); if (el) el.value = v; }
function getVal(id)       { return document.getElementById(id)?.value ?? ''; }
function setElText(id, t) { const el = document.getElementById(id); if (el) el.textContent = t; }

// A1 : afterChange ne doit PAS être appelé pendant le drag — uniquement render()
function afterChange() { render(); updateSynthesis(); notifyPayloadChange(); }

// ─── ZOOM / PAN ──────────────────────────────────────────────────────────────
function onWheel(e) {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 0.90;
  E.zoom = Math.max(0.2, Math.min(8, E.zoom * factor));
  render();
}

// ─── CLAVIER (A3 undo/redo, A4 suppr) ───────────────────────────────────────
function onKeyDown(e) {
  const tag = document.activeElement?.tagName?.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); undo(); return; }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Z')) { e.preventDefault(); redo(); return; }
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteSelected(); return; }
}

// A4 : supprimer l'élément sélectionné
function deleteSelected() {
  if (!E.sel) return;
  const { type, id } = E.sel;
  if (type === 'terrace')  { E.terrace = null; }
  else if (type === 'extension') { E.extensions = E.extensions.filter(x => x.id !== id); }
  else if (type === 'abri')      { E.abris = E.abris.filter(x => x.id !== id); }
  else if (type === 'potager')   { E.potagers = E.potagers.filter(x => x.id !== id); }
  else if (type === 'hedge')     { E.hedges = E.hedges.filter(x => x.id !== id); document.getElementById(`hedge-ctrl-${id}`)?.remove(); }
  else if (type === 'massif')    { E.massifs = E.massifs.filter(x => x.id !== id); }
  else if (type === 'massifRond'){ E.massifsRonds = E.massifsRonds.filter(x => x.id !== id); }
  else if (type === 'trou')      { E.trous = E.trous.filter(x => x.id !== id); }
  else if (type === 'arbreV')    { E.arbresV = E.arbresV.filter(x => x.id !== id); }
  else return; // house ne peut pas être supprimée
  E.sel = null;
  pushHistory();
  afterChange();
}

// ─── HIT TESTING ────────────────────────────────────────────────────────────
function getHitTarget(tx, ty) {
  // Handles de resize (priorité max)
  if (E.sel?.type === 'house') {
    const h = getResizeHandle(E.house, tx, ty);
    if (h) return { type: 'resize-house', handle: h };
  }
  if (E.sel?.type === 'terrace' && E.terrace) {
    const h = getResizeHandle(E.terrace, tx, ty);
    if (h) return { type: 'resize-terrace', handle: h };
  }
  if (E.sel?.type === 'extension') {
    const ext = E.extensions.find(x => x.id === E.sel.id);
    if (ext) { const h = getResizeHandle(ext, tx, ty); if (h) return { type: 'resize-extension', id: ext.id, handle: h }; }
  }
  if (E.sel?.type === 'abri') {
    const ab = E.abris.find(x => x.id === E.sel.id);
    if (ab) { const h = getResizeHandle(ab, tx, ty); if (h) return { type: 'resize-abri', id: ab.id, handle: h }; }
  }
  if (E.sel?.type === 'potager') {
    const pt = E.potagers.find(x => x.id === E.sel.id);
    if (pt) { const h = getResizeHandle(pt, tx, ty); if (h) return { type: 'resize-potager', id: pt.id, handle: h }; }
  }

  // Éléments surface (reverse order = dernier dessiné en premier)
  for (let i = E.arbresV.length - 1; i >= 0; i--) {
    const a = E.arbresV[i];
    if (Math.hypot(tx - a.x, ty - a.y) < a.crownR + 0.5) return { type: 'arbreV', id: a.id };
  }
  for (let i = E.trous.length - 1; i >= 0; i--) {
    const t = E.trous[i];
    if (Math.hypot(tx - t.x, ty - t.y) < t.r + 0.3) return { type: 'trou', id: t.id };
  }
  for (let i = E.massifsRonds.length - 1; i >= 0; i--) {
    const mr = E.massifsRonds[i];
    const dx = (tx - mr.cx) / mr.rx, dy = (ty - mr.cy) / mr.ry;
    if (dx*dx + dy*dy <= 1.1) return { type: 'massifRond', id: mr.id };
  }
  for (let i = E.massifs.length - 1; i >= 0; i--) {
    const ms = E.massifs[i];
    if (ms.closed && pointInPoly(tx, ty, ms.pts)) return { type: 'massif', id: ms.id };
  }
  for (const hg of [...E.hedges].reverse()) {
    if (distToSeg(tx, ty, hg.x1, hg.y1, hg.x2, hg.y2) < 0.5) return { type: 'hedge', id: hg.id };
  }
  for (const pt of [...E.potagers].reverse()) {
    if (tx >= pt.x && tx <= pt.x + pt.w && ty >= pt.y && ty <= pt.y + pt.h) return { type: 'potager', id: pt.id };
  }
  for (const ab of [...E.abris].reverse()) {
    if (tx >= ab.x && tx <= ab.x + ab.w && ty >= ab.y && ty <= ab.y + ab.h) return { type: 'abri', id: ab.id };
  }
  for (const ext of [...E.extensions].reverse()) {
    if (tx >= ext.x && tx <= ext.x + ext.w && ty >= ext.y && ty <= ext.y + ext.h) return { type: 'extension', id: ext.id };
  }
  if (E.terrace) {
    const tr = E.terrace;
    if (tx >= tr.x && tx <= tr.x + tr.w && ty >= tr.y && ty <= tr.y + tr.h) return { type: 'terrace' };
  }
  const hs = E.house;
  if (tx >= hs.x && tx <= hs.x + hs.w && ty >= hs.y && ty <= hs.y + hs.h) return { type: 'house' };
  return null;
}

function getResizeHandle(rect, tx, ty) {
  const handles = {
    nw: { x: rect.x,            y: rect.y + rect.h },
    n : { x: rect.x + rect.w/2, y: rect.y + rect.h },
    ne: { x: rect.x + rect.w,   y: rect.y + rect.h },
    e : { x: rect.x + rect.w,   y: rect.y + rect.h/2 },
    se: { x: rect.x + rect.w,   y: rect.y },
    s : { x: rect.x + rect.w/2, y: rect.y },
    sw: { x: rect.x,            y: rect.y },
    w : { x: rect.x,            y: rect.y + rect.h/2 },
  };
  const thresh = (HANDLE_R + 3) / effectiveScale();
  for (const [name, pt] of Object.entries(handles)) {
    if (Math.hypot(tx - pt.x, ty - pt.y) < thresh) return name;
  }
  return null;
}

function distToSeg(px, py, ax, ay, bx, by) {
  const abx = bx - ax, aby = by - ay;
  const l2  = abx * abx + aby * aby;
  if (l2 < 1e-10) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / l2));
  return Math.hypot(px - (ax + t * abx), py - (ay + t * aby));
}

function pointInPoly(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x, yi = pts[i].y, xj = pts[j].x, yj = pts[j].y;
    if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

// ─── ÉVÉNEMENTS SOURIS ───────────────────────────────────────────────────────
function canvasPos(e) {
  const r = canvas.getBoundingClientRect();
  return { sx: (e.clientX ?? e.pageX) - r.left, sy: (e.clientY ?? e.pageY) - r.top };
}

function onDown(e) {
  if (e.button === 2) {
    _isPanning = true;
    _panStartSX = (e.clientX ?? e.pageX) - E.panOffX;
    _panStartSY = (e.clientY ?? e.pageY) - E.panOffY;
    return;
  }
  if (e.button && e.button !== 0) return;

  const { sx, sy } = canvasPos(e);
  const raw = s2t(sx, sy);
  const tx = snap(raw.x), ty = snap(raw.y);

  // ── Outil sélection ──
  if (E.tool === 'select') {
    const hit = getHitTarget(tx, ty);
    E.sel = hit ? { type: hit.type.replace('resize-', ''), id: hit.id } : null;

    if (hit) {
      const baseType = hit.type.replace('resize-', '');
      if (baseType === 'house') {
        E.drag = { type: 'house', handle: hit.handle || null,
          startTX: tx, startTY: ty,
          startX: E.house.x, startY: E.house.y, startW: E.house.w, startH: E.house.h };
      } else if (baseType === 'terrace' && E.terrace) {
        E.drag = { type: 'terrace', handle: hit.handle || null,
          startTX: tx, startTY: ty,
          startX: E.terrace.x, startY: E.terrace.y, startW: E.terrace.w, startH: E.terrace.h };
      } else if (baseType === 'extension') {
        const ext = E.extensions.find(x => x.id === hit.id);
        if (ext) E.drag = { type: 'extension', id: ext.id, handle: hit.handle || null,
          startTX: tx, startTY: ty, startX: ext.x, startY: ext.y, startW: ext.w, startH: ext.h };
      } else if (baseType === 'abri') {
        const ab = E.abris.find(x => x.id === hit.id);
        if (ab) E.drag = { type: 'abri', id: ab.id, handle: hit.handle || null,
          startTX: tx, startTY: ty, startX: ab.x, startY: ab.y, startW: ab.w, startH: ab.h };
      } else if (baseType === 'potager') {
        const pt = E.potagers.find(x => x.id === hit.id);
        if (pt) E.drag = { type: 'potager', id: pt.id, handle: hit.handle || null,
          startTX: tx, startTY: ty, startX: pt.x, startY: pt.y, startW: pt.w, startH: pt.h };
      } else if (baseType === 'hedge') {
        const hg = E.hedges.find(h => h.id === hit.id);
        if (hg) E.drag = { type: 'hedge', id: hg.id, startTX: tx, startTY: ty,
          sx1: hg.x1, sy1: hg.y1, sx2: hg.x2, sy2: hg.y2 };
      } else if (baseType === 'massif') {
        const ms = E.massifs.find(m => m.id === hit.id);
        if (ms) {
          const cx = ms.pts.reduce((s, p) => s + p.x, 0) / ms.pts.length;
          const cy = ms.pts.reduce((s, p) => s + p.y, 0) / ms.pts.length;
          E.drag = { type: 'massif', id: ms.id, startTX: tx, startTY: ty, origPts: ms.pts.map(p => ({...p})), cx, cy };
        }
      } else if (baseType === 'massifRond') {
        const mr = E.massifsRonds.find(m => m.id === hit.id);
        if (mr) E.drag = { type: 'massifRond', id: mr.id, startTX: tx, startTY: ty, origCx: mr.cx, origCy: mr.cy };
      } else if (baseType === 'trou') {
        const tr = E.trous.find(t => t.id === hit.id);
        if (tr) E.drag = { type: 'trou', id: tr.id, startTX: tx, startTY: ty, origX: tr.x, origY: tr.y };
      } else if (baseType === 'arbreV') {
        const av = E.arbresV.find(a => a.id === hit.id);
        if (av) E.drag = { type: 'arbreV', id: av.id, startTX: tx, startTY: ty, origX: av.x, origY: av.y };
      }
    }
    showPropsPanel();
    render();
    return;
  }

  // ── Outil haie ──
  if (E.tool === 'haie') {
    if (!E.hedgePt1) {
      E.hedgePt1 = { x: tx, y: ty };
      _showDrawControls(true);
    } else {
      const hg = { id: nextId(), x1: E.hedgePt1.x, y1: E.hedgePt1.y, x2: tx, y2: ty, hM: 2, wM: 0.5 };
      E.hedges.push(hg);
      E.hedgePt1 = null; E.hedgePreview = null;
      addHedgeControl(hg);
      _showDrawControls(false);
      pushHistory();
      afterChange();
    }
    render();
    return;
  }

  // ── Outil massif polygone ──
  if (E.tool === 'massif') {
    if (!E.massifPts) { E.massifPts = []; _showDrawControls(true); }
    E.massifPts.push({ x: tx, y: ty });
    render();
    return;
  }

  // ── Outils dessin par drag rect ── (terrasse / extension / abri / potager)
  const RECT_TOOLS = ['terrasse', 'extension', 'abri', 'potager'];
  if (RECT_TOOLS.includes(E.tool)) {
    E._drawRectState = { tool: E.tool, startTX: tx, startTY: ty };
    render();
    return;
  }

  // ── Outils dessin par drag cercle ── (massif-rond, trou, arbre-voisin)
  const CIRCLE_TOOLS = ['massif-rond', 'trou', 'arbre-voisin'];
  if (CIRCLE_TOOLS.includes(E.tool)) {
    E._drawCircleState = { tool: E.tool, startTX: tx, startTY: ty };
    render();
    return;
  }
}

function onMove(e) {
  if (_isPanning) {
    E.panOffX = (e.clientX ?? e.pageX) - _panStartSX;
    E.panOffY = (e.clientY ?? e.pageY) - _panStartSY;
    render();
    return;
  }
  const { sx, sy } = canvasPos(e);
  const raw = s2t(sx, sy);
  const tx = snap(raw.x), ty = snap(raw.y);

  // Curseur
  if (E.tool === 'select') {
    const hit = getHitTarget(tx, ty);
    canvas.style.cursor = hit ? (hit.type.includes('resize') ? 'nwse-resize' : 'grab') : 'default';
  } else {
    canvas.style.cursor = 'crosshair';
  }

  // Previews tracé
  if (E.tool === 'haie' && E.hedgePt1) { E.hedgePreview = { x: tx, y: ty }; render(); return; }
  if (E.tool === 'massif' && E.massifPts?.length) { E.massifPreview = { x: tx, y: ty }; render(); return; }
  if (E._drawRectState) { E._drawRectState.curTX = tx; E._drawRectState.curTY = ty; render(); return; }
  if (E._drawCircleState) { E._drawCircleState.curTX = tx; E._drawCircleState.curTY = ty; render(); return; }

  // A1 : pendant le drag → uniquement render(), pas afterChange()
  if (!E.drag) return;
  const dx = tx - E.drag.startTX;
  const dy = ty - E.drag.startTY;

  if (E.drag.type === 'house') {
    if (E.drag.handle) applyResize(E.house, E.drag, dx, dy);
    else {
      E.house.x = snap(clampV(E.drag.startX + dx, 0, E.parcel.w - E.house.w));
      E.house.y = snap(clampV(E.drag.startY + dy, 0, E.parcel.h - E.house.h));
    }
    // Sync temps réel des inputs maison pendant le drag
    setVal('editor-house-w', E.house.w.toFixed(1));
    setVal('editor-house-h', E.house.h.toFixed(1));
    setVal('editor-house-surf', (E.house.w * E.house.h).toFixed(0));
  } else if (E.drag.type === 'terrace' && E.terrace) {
    if (E.drag.handle) applyResize(E.terrace, E.drag, dx, dy);
    else {
      E.terrace.x = snap(clampV(E.drag.startX + dx, 0, E.parcel.w - E.terrace.w));
      E.terrace.y = snap(clampV(E.drag.startY + dy, 0, E.parcel.h - E.terrace.h));
    }
  } else if (E.drag.type === 'extension') {
    const ext = E.extensions.find(x => x.id === E.drag.id);
    if (ext) {
      if (E.drag.handle) applyResize(ext, E.drag, dx, dy);
      else { ext.x = snap(E.drag.startX + dx); ext.y = snap(E.drag.startY + dy); }
    }
  } else if (E.drag.type === 'abri') {
    const ab = E.abris.find(x => x.id === E.drag.id);
    if (ab) {
      if (E.drag.handle) applyResize(ab, E.drag, dx, dy);
      else { ab.x = snap(E.drag.startX + dx); ab.y = snap(E.drag.startY + dy); }
    }
  } else if (E.drag.type === 'potager') {
    const pt = E.potagers.find(x => x.id === E.drag.id);
    if (pt) {
      if (E.drag.handle) applyResize(pt, E.drag, dx, dy);
      else { pt.x = snap(E.drag.startX + dx); pt.y = snap(E.drag.startY + dy); }
    }
  } else if (E.drag.type === 'hedge') {
    const hg = E.hedges.find(h => h.id === E.drag.id);
    if (hg) {
      hg.x1 = snap(E.drag.sx1 + dx); hg.y1 = snap(E.drag.sy1 + dy);
      hg.x2 = snap(E.drag.sx2 + dx); hg.y2 = snap(E.drag.sy2 + dy);
    }
  } else if (E.drag.type === 'massif') {
    const ms = E.massifs.find(m => m.id === E.drag.id);
    if (ms) ms.pts = E.drag.origPts.map(p => ({ x: snap(p.x + dx), y: snap(p.y + dy) }));
  } else if (E.drag.type === 'massifRond') {
    const mr = E.massifsRonds.find(m => m.id === E.drag.id);
    if (mr) { mr.cx = snap(E.drag.origCx + dx); mr.cy = snap(E.drag.origCy + dy); }
  } else if (E.drag.type === 'trou') {
    const tr = E.trous.find(t => t.id === E.drag.id);
    if (tr) { tr.x = snap(E.drag.origX + dx); tr.y = snap(E.drag.origY + dy); }
  } else if (E.drag.type === 'arbreV') {
    const av = E.arbresV.find(a => a.id === E.drag.id);
    if (av) { av.x = snap(E.drag.origX + dx); av.y = snap(E.drag.origY + dy); }
  }
  render(); // A1 : render seulement pendant le drag
}

function applyResize(rect, drag, dx, dy) {
  const { startX: ox, startY: oy, startW: ow, startH: oh, handle: h } = drag;
  if (h === 'n' || h === 'nw' || h === 'ne') { rect.h = Math.max(MIN_DIM, snap(oh + dy)); }
  if (h === 's' || h === 'sw' || h === 'se') { rect.y = snap(oy + dy); rect.h = Math.max(MIN_DIM, snap(oh - dy)); }
  if (h === 'e' || h === 'ne' || h === 'se') { rect.w = Math.max(MIN_DIM, snap(ow + dx)); }
  if (h === 'w' || h === 'nw' || h === 'sw') { rect.x = snap(ox + dx); rect.w = Math.max(MIN_DIM, snap(ow - dx)); }
  if (rect.x < 0) { rect.w += rect.x; rect.x = 0; }
  if (rect.y < 0) { rect.h += rect.y; rect.y = 0; }
  rect.w = Math.max(MIN_DIM, Math.min(rect.w, E.parcel.w - rect.x));
  rect.h = Math.max(MIN_DIM, Math.min(rect.h, E.parcel.h - rect.y));
}

function onUp(e) {
  if (e?.button === 2) { _isPanning = false; return; }

  // Fin drag → afterChange + pushHistory (A1)
  if (E.drag) {
    E.drag = null;
    pushHistory();
    afterChange();
    return;
  }

  // Fin dessin rect (B1-B4)
  if (E._drawRectState) {
    const { tool, startTX, startTY } = E._drawRectState;
    let { curTX, curTY } = E._drawRectState;
    E._drawRectState = null;
    if (curTX === undefined) {
      curTX = startTX + MIN_DIM;
      curTY = startTY + MIN_DIM;
    }
    const x = snap(Math.min(startTX, curTX));
    const y = snap(Math.min(startTY, curTY));
    const w = snap(Math.abs(curTX - startTX));
    const h = snap(Math.abs(curTY - startTY));
    if (w >= MIN_DIM && h >= MIN_DIM) {
      if (tool === 'terrasse') {
        E.terrace = { x, y, w, h };
      } else if (tool === 'extension') {
        E.extensions.push({ id: nextId(), x, y, w, h, hM: 6 });
      } else if (tool === 'abri') {
        E.abris.push({ id: nextId(), x, y, w: Math.min(w, 5), h: Math.min(h, 4), hM: 2.2 });
      } else if (tool === 'potager') {
        E.potagers.push({ id: nextId(), x, y, w, h });
      }
      pushHistory();
      afterChange();
    }
    render();
    return;
  }

  // Fin dessin cercle (B5-B7)
  if (E._drawCircleState) {
    const { tool, startTX, startTY, curTX, curTY } = E._drawCircleState;
    E._drawCircleState = null;
    if (curTX !== undefined) {
      const r = snap(Math.max(0.3, Math.hypot(curTX - startTX, curTY - startTY)));
      if (tool === 'massif-rond') {
        E.massifsRonds.push({ id: nextId(), cx: startTX, cy: startTY, rx: r, ry: r, plantes: [] });
      } else if (tool === 'trou') {
        const clampedR = Math.max(0.3, Math.min(r, 1.5));
        E.trous.push({ id: nextId(), x: startTX, y: startTY, r: clampedR });
      } else if (tool === 'arbre-voisin') {
        const clampedR = Math.max(1, Math.min(r, 8));
        E.arbresV.push({ id: nextId(), x: startTX, y: startTY, trunkR: 0.2, crownR: clampedR, hM: 8 });
      }
      pushHistory();
      afterChange();
    }
    render();
    return;
  }

  E.hedgePreview = null;
  E.massifPreview = null;
}

function onLeave(e) {
  if (_isPanning) _isPanning = false;
  if (E.drag) { E.drag = null; pushHistory(); afterChange(); }
  E.hedgePreview = null; E.massifPreview = null;
  if (E._drawRectState) E._drawRectState = null;
  if (E._drawCircleState) E._drawCircleState = null;
}

function onDblClick(e) {
  if (E.tool === 'massif' && E.massifPts?.length >= 3) finishMassif();
}

// ─── TERMINER / ANNULER TRACÉ ────────────────────────────────────────────────
function _showDrawControls(show) {
  document.getElementById('draw-controls')?.classList.toggle('hidden', !show);
}

function finishDraw() {
  if (E.tool === 'massif' && E.massifPts?.length >= 3) { finishMassif(); return; }
  cancelDraw();
}

function finishMassif() {
  if (!E.massifPts?.length) return;
  const ms = { id: nextId(), pts: [...E.massifPts], closed: true, plantes: [] };
  E.massifs.push(ms);
  E.massifPts = null; E.massifPreview = null;
  _showDrawControls(false);
  pushHistory();
  afterChange();
}

function cancelDraw() {
  E.hedgePt1 = null; E.hedgePreview = null;
  E.massifPts = null; E.massifPreview = null;
  E._drawRectState = null; E._drawCircleState = null;
  _showDrawControls(false);
  render();
}

// ─── RENDU ──────────────────────────────────────────────────────────────────
function render() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawParcel();
  drawGrid();
  if (E.showHeatmap && E.heatmapCells) drawHeatmap();
  // Potagers (pas d'ombre)
  E.potagers.forEach(pt => drawRectElement(pt, COL.potager, E.sel?.id === pt.id, 'Potager'));
  // Massifs polygon + ronds
  drawMassifs();
  drawMassifsRonds();
  // Trous plantation
  E.trous.forEach(tr => drawTrou(tr));
  // Terrasse
  if (E.terrace) drawTerrace();
  // Extensions
  E.extensions.forEach(ext => drawRectElement(ext, COL.extension, E.sel?.id === ext.id, 'Extension'));
  // Abris
  E.abris.forEach(ab => drawRectElement(ab, COL.abri, E.sel?.id === ab.id, 'Abri'));
  // Haies
  drawHedges();
  // Maison
  drawHouse();
  // Arbres voisins (dessus pour visibilité)
  E.arbresV.forEach(av => drawArbreVoisin(av));
  // Ombres solaires
  if (E.sunPositions.length) drawSunShadows();
  // UI
  drawRoseDVents();
  drawAxisLabels();
  drawScaleBar();
  // Distances pendant resize/drag
  if (E.drag?.type === 'house' || E.drag?.type === 'terrace') drawDistances();
  // Previews tracé
  if (E.tool === 'haie' && E.hedgePt1 && E.hedgePreview) drawHedgePreview();
  if (E.tool === 'massif' && E.massifPts?.length && E.massifPreview) drawMassifPreview();
  if (E._drawRectState?.curTX !== undefined) drawRectPreview();
  if (E._drawCircleState?.curTX !== undefined) drawCirclePreview();
}

function drawParcel() {
  const { x: sx, y: sy } = t2s(0, E.parcel.h);
  const pw = E.parcel.w * effectiveScale();
  const ph = E.parcel.h * effectiveScale();
  ctx.fillStyle = COL.parcel.fill;
  ctx.fillRect(sx, sy, pw, ph);
  ctx.strokeStyle = COL.parcel.stroke; ctx.lineWidth = COL.parcel.lw;
  ctx.strokeRect(sx, sy, pw, ph);
}

function drawGrid() {
  ctx.strokeStyle = COL.grid; ctx.lineWidth = 0.5;
  ctx.setLineDash([2, 4]);
  const sc = effectiveScale();
  for (let x = 0; x <= E.parcel.w; x++) {
    const sx = MARGIN + x * sc + E.panOffX;
    ctx.beginPath(); ctx.moveTo(sx, MARGIN + E.panOffY);
    ctx.lineTo(sx, MARGIN + E.parcel.h * sc + E.panOffY); ctx.stroke();
  }
  for (let y = 0; y <= E.parcel.h; y++) {
    const sy = MARGIN + y * sc + E.panOffY;
    ctx.beginPath(); ctx.moveTo(MARGIN + E.panOffX, sy);
    ctx.lineTo(MARGIN + E.parcel.w * sc + E.panOffX, sy); ctx.stroke();
  }
  ctx.setLineDash([]);
}

function drawRect(rect, col, selected) {
  const { x: sx, y: sy } = t2s(rect.x, rect.y + rect.h);
  const pw = rect.w * effectiveScale();
  const ph = rect.h * effectiveScale();
  ctx.fillStyle   = col.fill;
  ctx.strokeStyle = selected ? col.selStroke : col.stroke;
  ctx.lineWidth   = selected ? 2.5 : col.lw;
  ctx.fillRect(sx, sy, pw, ph);
  ctx.strokeRect(sx, sy, pw, ph);
  return { sx, sy, pw, ph };
}

function drawRectElement(rect, col, selected, label) {
  const { sx, sy, pw, ph } = drawRect(rect, col, selected);
  if (pw > 28) {
    ctx.fillStyle = '#fff';
    ctx.font = `${Math.min(11, pw * 0.12)}px Inter,sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(label, sx + pw / 2, sy + ph / 2);
  }
  if (selected) drawHandles(rect);
}

function drawHouse() {
  const sel = E.sel?.type === 'house';
  const { sx, sy, pw, ph } = drawRect(E.house, COL.house, sel);
  ctx.fillStyle = '#fff';
  ctx.font = `bold ${Math.min(13, pw * 0.12)}px Inter,sans-serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  if (pw > 30) ctx.fillText('Maison', sx + pw / 2, sy + ph / 2);
  if (sel) drawHandles(E.house);
}

function drawTerrace() {
  if (!E.terrace) return;
  const sel = E.sel?.type === 'terrace';
  const { sx, sy, pw, ph } = drawRect(E.terrace, COL.terrace, sel);
  ctx.fillStyle = '#7a5c1e';
  ctx.font = `${Math.min(11, pw * 0.11)}px Inter,sans-serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  if (pw > 30) ctx.fillText('Terrasse', sx + pw / 2, sy + ph / 2);
  if (sel) drawHandles(E.terrace);
}

function drawTrou(tr) {
  const sel = E.sel?.type === 'trou' && E.sel.id === tr.id;
  const { x: sx, y: sy } = t2s(tr.x, tr.y);
  const sr = tr.r * effectiveScale();
  ctx.fillStyle   = sel ? 'rgba(100,180,255,0.5)' : COL.trou.fill;
  ctx.strokeStyle = sel ? COL.trou.selStroke : COL.trou.stroke;
  ctx.lineWidth   = sel ? 2 : COL.trou.lw;
  ctx.setLineDash([3, 2]);
  ctx.beginPath(); ctx.arc(sx, sy, sr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#1976d2'; ctx.font = '8px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText(`∅${(tr.r*2).toFixed(1)}m`, sx, sy - sr - 2);
}

function drawArbreVoisin(av) {
  const sel = E.sel?.type === 'arbreV' && E.sel.id === av.id;
  const { x: sx, y: sy } = t2s(av.x, av.y);
  const sc = effectiveScale();
  // Couronne
  ctx.fillStyle   = sel ? COL.arbreV.crownSel : COL.arbreV.crown;
  ctx.strokeStyle = sel ? COL.arbreV.selStroke : COL.arbreV.stroke;
  ctx.lineWidth   = sel ? 2 : 1.5;
  ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.arc(sx, sy, av.crownR * sc, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.setLineDash([]);
  // Tronc
  ctx.fillStyle = '#5d3b1e';
  ctx.beginPath(); ctx.arc(sx, sy, av.trunkR * sc, 0, Math.PI * 2); ctx.fill();
  // Label
  ctx.fillStyle = '#3d2b00'; ctx.font = 'bold 9px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(`Arbre R=${av.crownR.toFixed(1)}m`, sx, sy + av.crownR * sc + 2);
}

function drawHandles(rect) {
  const pts = [
    t2s(rect.x,            rect.y + rect.h),
    t2s(rect.x + rect.w/2, rect.y + rect.h),
    t2s(rect.x + rect.w,   rect.y + rect.h),
    t2s(rect.x + rect.w,   rect.y + rect.h/2),
    t2s(rect.x + rect.w,   rect.y),
    t2s(rect.x + rect.w/2, rect.y),
    t2s(rect.x,            rect.y),
    t2s(rect.x,            rect.y + rect.h/2),
  ];
  ctx.fillStyle = COL.handle.fill; ctx.strokeStyle = COL.handle.stroke; ctx.lineWidth = 1.5;
  for (const { x, y } of pts) {
    ctx.beginPath(); ctx.arc(x, y, HANDLE_R, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
}

function drawHedges() {
  for (const hg of E.hedges) {
    const { x: sx1, y: sy1 } = t2s(hg.x1, hg.y1);
    const { x: sx2, y: sy2 } = t2s(hg.x2, hg.y2);
    const sel = E.sel?.id === hg.id;
    ctx.strokeStyle = sel ? COL.hedge.selStroke : COL.hedge.stroke;
    ctx.lineWidth = HEDGE_W; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();
    ctx.fillStyle = sel ? COL.hedge.selStroke : COL.hedge.stroke;
    [{ x: sx1, y: sy1 }, { x: sx2, y: sy2 }].forEach(p => {
      ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
    });
    const len = Math.hypot(hg.x2 - hg.x1, hg.y2 - hg.y1).toFixed(1);
    ctx.fillStyle = '#1b5e20'; ctx.font = '10px Inter,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.fillText(`${len}m / h=${hg.hM}m`, (sx1+sx2)/2, Math.min(sy1,sy2) - 2);
  }
  ctx.lineCap = 'butt';
}

function drawHedgePreview() {
  const { x: sx1, y: sy1 } = t2s(E.hedgePt1.x, E.hedgePt1.y);
  const { x: sx2, y: sy2 } = t2s(E.hedgePreview.x, E.hedgePreview.y);
  ctx.strokeStyle = COL.hedge.stroke; ctx.lineWidth = HEDGE_W;
  ctx.lineCap = 'round'; ctx.setLineDash([6, 3]);
  ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();
  ctx.setLineDash([]); ctx.lineCap = 'butt';
}

function drawMassifs() {
  for (const ms of E.massifs) {
    if (!ms.pts.length) continue;
    const sel = E.sel?.id === ms.id;
    ctx.beginPath();
    const f = t2s(ms.pts[0].x, ms.pts[0].y); ctx.moveTo(f.x, f.y);
    for (let i = 1; i < ms.pts.length; i++) {
      const p = t2s(ms.pts[i].x, ms.pts[i].y); ctx.lineTo(p.x, p.y);
    }
    if (ms.closed) ctx.closePath();
    ctx.fillStyle   = sel ? 'rgba(102,187,106,0.3)' : COL.massif.fill;
    ctx.strokeStyle = sel ? COL.massif.selStroke : COL.massif.stroke;
    ctx.lineWidth = 2;
    if (ms.closed) ctx.fill();
    ctx.stroke();
    if (ms.closed && ms.pts.length >= 3) {
      const area = polyArea(ms.pts).toFixed(1);
      const cx = ms.pts.reduce((s, p) => s + p.x, 0) / ms.pts.length;
      const cy = ms.pts.reduce((s, p) => s + p.y, 0) / ms.pts.length;
      const { x: lx, y: ly } = t2s(cx, cy);
      ctx.fillStyle = '#1b5e20'; ctx.font = '10px Inter,sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(`${area} m²`, lx, ly);
    }
  }
}

function drawMassifsRonds() {
  for (const mr of E.massifsRonds) {
    const sel = E.sel?.id === mr.id;
    const { x: sx, y: sy } = t2s(mr.cx, mr.cy);
    const sc = effectiveScale();
    ctx.fillStyle   = sel ? 'rgba(102,187,106,0.3)' : COL.massifRond.fill;
    ctx.strokeStyle = sel ? COL.massifRond.selStroke : COL.massifRond.stroke;
    ctx.lineWidth   = 2;
    ctx.beginPath();
    ctx.ellipse(sx, sy, mr.rx * sc, mr.ry * sc, 0, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
    const area = (Math.PI * mr.rx * mr.ry).toFixed(1);
    ctx.fillStyle = '#1b5e20'; ctx.font = '10px Inter,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(`${area} m²`, sx, sy);
  }
}

function drawMassifPreview() {
  if (!E.massifPts?.length) return;
  ctx.beginPath();
  const f = t2s(E.massifPts[0].x, E.massifPts[0].y); ctx.moveTo(f.x, f.y);
  E.massifPts.slice(1).forEach(p => { const s = t2s(p.x, p.y); ctx.lineTo(s.x, s.y); });
  const { x: px, y: py } = t2s(E.massifPreview.x, E.massifPreview.y); ctx.lineTo(px, py);
  ctx.strokeStyle = COL.massif.stroke; ctx.lineWidth = 2; ctx.setLineDash([4, 2]);
  ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = COL.massif.stroke;
  E.massifPts.forEach(p => {
    const s = t2s(p.x, p.y);
    ctx.beginPath(); ctx.arc(s.x, s.y, 4, 0, Math.PI * 2); ctx.fill();
  });
}

function drawRectPreview() {
  const { startTX, startTY, curTX, curTY, tool } = E._drawRectState;
  const x = Math.min(startTX, curTX), y = Math.min(startTY, curTY);
  const w = Math.abs(curTX - startTX), h = Math.abs(curTY - startTY);
  const { x: sx, y: sy } = t2s(x, y + h);
  const sc = effectiveScale();
  const col = tool === 'terrasse' ? COL.terrace
            : tool === 'extension' ? COL.extension
            : tool === 'abri'      ? COL.abri
            : COL.potager;
  ctx.fillStyle = col.fill; ctx.strokeStyle = col.stroke || col.selStroke;
  ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
  ctx.fillRect(sx, sy, w * sc, h * sc);
  ctx.strokeRect(sx, sy, w * sc, h * sc);
  ctx.setLineDash([]);
  ctx.fillStyle = '#333'; ctx.font = '10px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(`${w.toFixed(1)} × ${h.toFixed(1)} m`, sx + w * sc / 2, sy + h * sc + 2);
}

function drawCirclePreview() {
  const { startTX, startTY, curTX, curTY, tool } = E._drawCircleState;
  const r = Math.max(0.3, Math.hypot(curTX - startTX, curTY - startTY));
  const { x: sx, y: sy } = t2s(startTX, startTY);
  const sc = effectiveScale();
  const col = tool === 'massif-rond' ? COL.massifRond
            : tool === 'trou'         ? COL.trou
            : COL.arbreV;
  ctx.fillStyle = col.fill || col.crown;
  ctx.strokeStyle = col.stroke;
  ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.arc(sx, sy, r * sc, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#333'; ctx.font = '10px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(`R=${r.toFixed(1)}m`, sx, sy + r * sc + 2);
}

function drawRoseDVents() {
  const cx = MARGIN + 38, cy = MARGIN + 38, r = 26;
  const nRad = E.northDeg * Math.PI / 180;
  ctx.fillStyle = 'rgba(255,255,255,0.88)';
  ctx.beginPath(); ctx.arc(cx, cy, r + 5, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = '#ddd'; ctx.lineWidth = 1; ctx.stroke();
  const nx = cx + r * Math.sin(nRad);
  const ny = cy - r * Math.cos(nRad);
  ctx.strokeStyle = '#d32f2f'; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(nx, ny); ctx.stroke();
  const ang = Math.atan2(ny - cy, nx - cx);
  ctx.fillStyle = '#d32f2f';
  ctx.beginPath();
  ctx.moveTo(nx, ny);
  ctx.lineTo(nx - 9 * Math.cos(ang - 0.4), ny - 9 * Math.sin(ang - 0.4));
  ctx.lineTo(nx - 9 * Math.cos(ang + 0.4), ny - 9 * Math.sin(ang + 0.4));
  ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#d32f2f'; ctx.font = 'bold 11px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('N', nx + 11 * Math.sin(nRad), ny - 11 * Math.cos(nRad));
  ctx.fillStyle = '#555'; ctx.font = '9px Inter,sans-serif';
  [['S', nRad + Math.PI], ['E', nRad + Math.PI / 2], ['O', nRad - Math.PI / 2]].forEach(([label, a]) => {
    ctx.fillText(label, cx + (r - 4) * Math.sin(a), cy - (r - 4) * Math.cos(a));
  });
}

function drawAxisLabels() {
  const sc = effectiveScale();
  function niceStep(dim) {
    if (dim <= 8)  return 1;
    if (dim <= 20) return 2;
    if (dim <= 50) return 5;
    return 10;
  }
  const stepX = niceStep(E.parcel.w);
  const stepY = niceStep(E.parcel.h);
  const py0 = MARGIN + E.parcel.h * sc + E.panOffY;
  const px0 = MARGIN + E.panOffX;

  if (stepX > 1) {
    ctx.strokeStyle = 'rgba(0,0,0,0.11)'; ctx.lineWidth = 0.5;
    for (let x = 1; x < E.parcel.w; x++) {
      if (x % stepX === 0) continue;
      const sx = MARGIN + x * sc + E.panOffX;
      ctx.beginPath(); ctx.moveTo(sx, py0); ctx.lineTo(sx, py0 + 3); ctx.stroke();
    }
  }
  if (stepY > 1) {
    ctx.strokeStyle = 'rgba(0,0,0,0.11)'; ctx.lineWidth = 0.5;
    for (let y = 1; y < E.parcel.h; y++) {
      if (y % stepY === 0) continue;
      const sy = MARGIN + (E.parcel.h - y) * sc + E.panOffY;
      ctx.beginPath(); ctx.moveTo(px0, sy); ctx.lineTo(px0 - 3, sy); ctx.stroke();
    }
  }
  ctx.fillStyle = '#666'; ctx.font = '10px Inter,sans-serif';
  ctx.strokeStyle = 'rgba(0,0,0,0.25)'; ctx.lineWidth = 1;
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  for (let x = 0; x <= E.parcel.w; x += stepX) {
    const sx = MARGIN + x * sc + E.panOffX;
    ctx.beginPath(); ctx.moveTo(sx, py0); ctx.lineTo(sx, py0 + 5); ctx.stroke();
    ctx.fillText(x + 'm', sx, py0 + 7);
  }
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (let y = 0; y <= E.parcel.h; y += stepY) {
    const sy = MARGIN + (E.parcel.h - y) * sc + E.panOffY;
    ctx.beginPath(); ctx.moveTo(px0, sy); ctx.lineTo(px0 - 5, sy); ctx.stroke();
    ctx.fillText(y + 'm', px0 - 7, sy);
  }
}

function drawScaleBar() {
  const sc = effectiveScale();
  const barM = 5;
  const barPx = barM * sc;
  // Position : sous la parcelle, alignée à gauche
  const { x: px0, y: py0 } = t2s(0, 0);
  const x0 = px0 + 4;
  const y0 = py0 + 22;
  if (y0 > canvas.height - 6 || x0 + barPx + 60 > canvas.width) return;

  ctx.save();
  ctx.strokeStyle = '#444'; ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x0, y0 - 5); ctx.lineTo(x0, y0 + 5);
  ctx.moveTo(x0, y0); ctx.lineTo(x0 + barPx, y0);
  ctx.moveTo(x0 + barPx, y0 - 5); ctx.lineTo(x0 + barPx, y0 + 5);
  ctx.stroke();

  ctx.fillStyle = '#333'; ctx.font = 'bold 10px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(`${barM} m`, x0 + barPx / 2, y0 + 7);

  // Échelle 1:X (basée sur 96 dpi)
  const ratio = Math.round(1000 * 96 / (sc * 25.4));
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  ctx.fillText(`1 : ${ratio}`, x0 + barPx + 6, y0);
  ctx.restore();
}

function drawDistances() {
  const rect = E.drag?.type === 'house' ? E.house : E.terrace;
  if (!rect) return;
  const P = E.parcel;
  const dims = [
    { label: (rect.y).toFixed(1) + 'm',                tx: rect.x + rect.w/2,                              ty: rect.y / 2 },
    { label: (P.h - rect.y - rect.h).toFixed(1) + 'm', tx: rect.x + rect.w/2,                              ty: rect.y + rect.h + (P.h - rect.y - rect.h) / 2 },
    { label: (rect.x).toFixed(1) + 'm',                tx: rect.x / 2,                                     ty: rect.y + rect.h/2 },
    { label: (P.w - rect.x - rect.w).toFixed(1) + 'm', tx: rect.x + rect.w + (P.w - rect.x - rect.w) / 2, ty: rect.y + rect.h/2 },
  ];
  ctx.font = 'bold 11px Inter,sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  dims.forEach(({ label, tx, ty }) => {
    const { x: sx, y: sy } = t2s(tx, ty);
    if (sx < 0 || sy < 0 || sx > canvas.width || sy > canvas.height) return;
    const tw = ctx.measureText(label).width + 10;
    ctx.fillStyle = 'rgba(21,101,192,0.12)';
    roundRect(ctx, sx - tw / 2, sy - 9, tw, 18, 4); ctx.fill();
    ctx.fillStyle = COL.dimLine; ctx.fillText(label, sx, sy);
  });
}

function roundRect(c, x, y, w, h, r) {
  c.beginPath(); c.moveTo(x + r, y);
  c.lineTo(x + w - r, y); c.arcTo(x + w, y, x + w, y + r, r);
  c.lineTo(x + w, y + h - r); c.arcTo(x + w, y + h, x + w - r, y + h, r);
  c.lineTo(x + r, y + h); c.arcTo(x, y + h, x, y + h - r, r);
  c.lineTo(x, y + r); c.arcTo(x, y, x + r, y, r); c.closePath();
}

// ─── HEATMAP ─────────────────────────────────────────────────────────────────
function _heatmapColor(ratio) {
  const stops = HEATMAP_STOPS;
  const n = stops.length - 1;
  const idx = Math.min(n - 1, Math.floor(ratio * n));
  const t   = ratio * n - idx;
  const c0  = _hexToRgb(stops[idx]);
  const c1  = _hexToRgb(stops[idx + 1]);
  return `rgb(${Math.round(c0[0]+(c1[0]-c0[0])*t)},${Math.round(c0[1]+(c1[1]-c0[1])*t)},${Math.round(c0[2]+(c1[2]-c0[2])*t)})`;
}
function _hexToRgb(hex) {
  return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
}

function drawHeatmap() {
  const cells = E.heatmapCells;
  const maxMin = cells.reduce((m, c) => Math.max(m, c.score), 0) || 1;
  const sc = effectiveScale();
  const cellSz = E.pas * sc + 0.5;
  ctx.globalAlpha = 0.65;
  for (const c of cells) {
    const ratio = Math.min(1, c.score / maxMin);
    const { x: sx, y: sy } = t2s(c.x, c.y + E.pas);
    ctx.fillStyle = _heatmapColor(ratio);
    ctx.fillRect(sx, sy, cellSz, cellSz);
  }
  ctx.globalAlpha = 1;
  _drawHeatmapLegend(maxMin);
}

function _drawHeatmapLegend(maxMin) {
  const legendH = Math.min(180, E.parcel.h * effectiveScale() * 0.7);
  const legendW = 14;
  const lx = MARGIN + E.parcel.w * effectiveScale() + E.panOffX + 10;
  const ly = MARGIN + E.panOffY + 20;
  if (lx + legendW + 40 > canvas.width) return;
  const grad = ctx.createLinearGradient(0, ly, 0, ly + legendH);
  [...HEATMAP_STOPS].reverse().forEach((c, i) => grad.addColorStop(i / (HEATMAP_STOPS.length - 1), c));
  ctx.fillStyle = grad;
  ctx.fillRect(lx, ly, legendW, legendH);
  ctx.strokeStyle = '#ccc'; ctx.lineWidth = 0.5;
  ctx.strokeRect(lx, ly, legendW, legendH);
  ctx.fillStyle = '#333'; ctx.font = '9px Inter,sans-serif';
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  const maxH = maxMin / 60;
  [0, 2, 4, 6, 8].forEach(h => {
    const ratio = Math.min(1, h / Math.max(maxH, 8));
    const y = ly + legendH - ratio * legendH;
    ctx.beginPath(); ctx.moveTo(lx + legendW, y); ctx.lineTo(lx + legendW + 3, y); ctx.stroke();
    ctx.fillText(h === 8 ? '8h+' : `${h}h`, lx + legendW + 5, y);
  });
}

// ─── OMBRES SOLAIRES ────────────────────────────────────────────────────────
function convexHull(pts) {
  if (pts.length < 3) return pts;
  pts = pts.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower = [], upper = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop();
    lower.push(p);
  }
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop();
    upper.push(p);
  }
  upper.pop(); lower.pop();
  return [...lower, ...upper];
}

function drawSunShadows() {
  if (!E.sunPositions.length || E.sunIdx >= E.sunPositions.length) return;
  const sun = E.sunPositions[E.sunIdx];
  if (!sun || sun.alt <= 1) return;

  const altRad = Math.max(0.02, sun.alt * Math.PI / 180);
  const azPlan = ((sun.az - E.northDeg) + 360) % 360;
  const azRad  = azPlan * Math.PI / 180;
  const sdx    = -Math.sin(azRad);
  const sdy    = -Math.cos(azRad);

  function projectShadow(corners, heightM) {
    const sLen = heightM / Math.tan(altRad);
    const projected = corners.map(c => ({ x: c.x + sdx * sLen, y: c.y + sdy * sLen }));
    return convexHull([...corners, ...projected]);
  }

  ctx.fillStyle = COL.shadow;
  // Maison
  const h = E.house;
  fillPoly(projectShadow([
    { x: h.x, y: h.y }, { x: h.x+h.w, y: h.y }, { x: h.x+h.w, y: h.y+h.h }, { x: h.x, y: h.y+h.h }
  ], h.hM));
  // Extensions
  E.extensions.forEach(ext => fillPoly(projectShadow([
    { x: ext.x, y: ext.y }, { x: ext.x+ext.w, y: ext.y }, { x: ext.x+ext.w, y: ext.y+ext.h }, { x: ext.x, y: ext.y+ext.h }
  ], ext.hM)));
  // Abris
  E.abris.forEach(ab => fillPoly(projectShadow([
    { x: ab.x, y: ab.y }, { x: ab.x+ab.w, y: ab.y }, { x: ab.x+ab.w, y: ab.y+ab.h }, { x: ab.x, y: ab.y+ab.h }
  ], ab.hM)));
  // Haies
  for (const hg of E.hedges) {
    const n = 4, pts = [];
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      pts.push({ x: hg.x1 + t*(hg.x2-hg.x1), y: hg.y1 + t*(hg.y2-hg.y1) });
    }
    fillPoly(projectShadow(pts, hg.hM));
  }
  // Arbres voisins (ombre de couronne)
  E.arbresV.forEach(av => {
    const steps = 8;
    const cPts = Array.from({ length: steps }, (_, i) => {
      const a = i * Math.PI * 2 / steps;
      return { x: av.x + av.crownR * Math.cos(a), y: av.y + av.crownR * Math.sin(a) };
    });
    fillPoly(projectShadow(cPts, av.hM));
  });

  drawSunIndicator(sun);
}

function fillPoly(pts) {
  if (!pts.length) return;
  ctx.beginPath();
  const f = t2s(pts[0].x, pts[0].y); ctx.moveTo(f.x, f.y);
  for (let i = 1; i < pts.length; i++) { const p = t2s(pts[i].x, pts[i].y); ctx.lineTo(p.x, p.y); }
  ctx.closePath(); ctx.fill();
}

function drawSunIndicator(sun) {
  const R = 18;
  const azRad = sun.az * Math.PI / 180;
  const d = Math.min(E.parcel.w, E.parcel.h) / 2 + 4;
  const stx = E.parcel.w / 2 + d * Math.sin(azRad);
  const sty = E.parcel.h / 2 + d * Math.cos(azRad);
  const { x: sx, y: sy } = t2s(stx, sty);
  if (sx < 0 || sx > canvas.width || sy < 0 || sy > canvas.height) return;
  const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, R);
  g.addColorStop(0, 'rgba(255,220,0,1)'); g.addColorStop(1, 'rgba(255,160,0,0)');
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(sx, sy, R, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#555'; ctx.font = 'bold 10px Inter,sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText(sun.time, sx, sy - R - 1);
}

// ─── SIMULATION SOLAIRE (A2) ──────────────────────────────────────────────────
async function loadSunPositions() {
  try {
    const r = await fetch('/sun-positions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude: E.lat, longitude: E.lon, date: E.dateRef, timezone: E.tz, step_minutes: 20 }),
    });
    const d = await r.json();
    E.sunPositions = (d.positions || []).map(p => ({ time: p.time, alt: p.alt, az: p.az }));
    E.sunIdx = 0;
  } catch { E.sunPositions = []; }
}

function stopSunSimulation() {
  const btn = document.getElementById('btn-sun-sim');
  if (!E.sunPlaying) return;
  console.log('[SUN] stop — idx:', E.sunIdx);
  E.sunPlaying = false;
  clearTimeout(E.sunTimer);
  E.sunTimer = null;
  // sunPositions conservé : la dernière frame reste affichée
  if (btn) {
    btn.innerHTML = '<span class="tool-icon">☀️</span> Simuler';
    btn.classList.remove('active');
  }
  render();
}

async function toggleSunSimulation() {
  const btn = document.getElementById('btn-sun-sim');
  if (E.sunPlaying) {
    stopSunSimulation();
    return;
  }
  if (btn) btn.textContent = 'Chargement…';
  await loadSunPositions();
  if (!E.sunPositions.length) {
    if (btn) btn.textContent = 'Simuler la journée';
    return;
  }
  console.log('[SUN] start —', E.sunPositions.length, 'positions');
  E.sunPlaying = true; E.sunIdx = 0;
  if (btn) { btn.innerHTML = '<span class="tool-icon">⏹</span> Arrêter'; btn.classList.add('active'); }

  // durée totale 30 s à 1× → step = 30000 / n / speed
  const TOTAL_MS = 30000;
  function step() {
    if (!E.sunPlaying) return;
    E.sunIdx++;
    if (E.sunIdx >= E.sunPositions.length) {
      stopSunSimulation();  // auto-stop en fin de journée
      return;
    }
    const sun = E.sunPositions[E.sunIdx];
    const disp = document.getElementById('sun-time-display');
    if (disp && sun) {
      disp.textContent = `${sun.time} — Az: ${sun.az}° — Haut: ${sun.alt}°`;
      disp.style.display = '';
    }
    render();
    const delay = Math.max(50, (TOTAL_MS / E.sunPositions.length) / (E.sunSpeed || 1));
    E.sunTimer = setTimeout(step, delay);
  }
  step();
}

// ─── COURSE SOLAIRE ──────────────────────────────────────────────────────────
async function loadSunCourse() {
  try {
    const r = await fetch(`/sun-course?lat=${E.lat}&lon=${E.lon}&tz=${encodeURIComponent(E.tz)}`);
    if (!r.ok) return;
    const d = await r.json();
    const ete = d.ete || {}, hiver = d.hiver || {};
    setSynth('synth-soleil-ete',
      ete.lever ? `Lever ${ete.lever} az ${ete.az_lever}° / Coucher ${ete.coucher} az ${ete.az_coucher}° / Hmax ${ete.hauteur_max}°` : '—');
    setSynth('synth-soleil-hiver',
      hiver.lever ? `Lever ${hiver.lever} az ${hiver.az_lever}° / Coucher ${hiver.coucher} az ${hiver.az_coucher}° / Hmax ${hiver.hauteur_max}°` : '—');
    setSynth('synth-diff-eclairement', d.diff_eclairement_pct != null ? `${d.diff_eclairement_pct}%` : '—');
    if (window.terrainPayload) window.terrainPayload._sun_course = d;
  } catch { /* silencieux */ }
}

// ─── HEATMAP EXPOSITION ───────────────────────────────────────────────────────
async function toggleHeatmap() {
  const btn = document.getElementById('btn-heatmap');
  if (E.showHeatmap) {
    E.showHeatmap = false; E.heatmapCells = null;
    if (btn) { btn.textContent = 'Carte solaire'; btn.classList.remove('active'); }
    render(); return;
  }
  if (btn) btn.textContent = 'Chargement…';
  try {
    const r = await fetch('/exposition_precise', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(getPayload()),
    });
    const d = await r.json();
    E.heatmapCells = d.cells || [];
    E.pas = d.pas_grille_m || 1;
    E.showHeatmap = true;
    if (btn) { btn.textContent = 'Masquer heatmap'; btn.classList.add('active'); }
    render();
  } catch (ex) {
    if (btn) btn.textContent = 'Carte solaire';
    typeof showToast !== 'undefined' && showToast('Erreur heatmap : ' + ex.message, 'error');
  }
}

// ─── HAIES — CONTRÔLES ───────────────────────────────────────────────────────
function addHedgeControl(hg) {
  const list = document.getElementById('hedge-list');
  if (!list) return;
  const ang = Math.round(Math.atan2(hg.y2 - hg.y1, hg.x2 - hg.x1) * 180 / Math.PI);
  const len = Math.hypot(hg.x2 - hg.x1, hg.y2 - hg.y1).toFixed(1);
  const div = document.createElement('div');
  div.className = 'hedge-control-item'; div.id = `hedge-ctrl-${hg.id}`;
  const wM = hg.wM ?? 0.5;
  div.innerHTML = `
    <div class="hedge-ctrl-header">
      <span class="hedge-ctrl-label">Haie ${len} m &mdash; angle ${ang}°</span>
      <button class="btn-icon-del" onclick="deleteHedge(${hg.id})" title="Supprimer">&#10005;</button>
    </div>
    <label class="hedge-height-label">
      Hauteur <input type="range" min="0.5" max="6" step="0.1" value="${hg.hM}"
        oninput="updateHedgeH(${hg.id},this.value)">
      <span id="hedge-hval-${hg.id}">${hg.hM} m</span>
    </label>
    <label class="hedge-height-label">
      Largeur <input type="range" min="0.2" max="3" step="0.1" value="${wM}"
        oninput="updateHedgeW(${hg.id},this.value)">
      <span id="hedge-wval-${hg.id}">${wM.toFixed(1)} m</span>
    </label>`;
  list.appendChild(div);
}

function rebuildHedgeList() {
  const list = document.getElementById('hedge-list');
  if (!list) return;
  list.querySelectorAll('.hedge-control-item').forEach(el => el.remove());
  E.hedges.forEach(hg => addHedgeControl(hg));
}

function updateHedgeH(id, val) {
  const hg = E.hedges.find(h => h.id === id);
  if (hg) { hg.hM = parseFloat(val); setElText(`hedge-hval-${id}`, hg.hM.toFixed(1) + ' m'); }
  afterChange();
}

function updateHedgeW(id, val) {
  const hg = E.hedges.find(h => h.id === id);
  if (hg) { hg.wM = parseFloat(val); setElText(`hedge-wval-${id}`, hg.wM.toFixed(1) + ' m'); }
  afterChange();
}

function deleteHedge(id) {
  E.hedges = E.hedges.filter(h => h.id !== id);
  document.getElementById(`hedge-ctrl-${id}`)?.remove();
  if (E.sel?.id === id) E.sel = null;
  pushHistory();
  afterChange();
}

function deleteMassif(id) {
  E.massifs = E.massifs.filter(m => m.id !== id);
  if (E.sel?.id === id) E.sel = null;
  pushHistory();
  afterChange();
}

// ─── PANNEAU PROPRIÉTÉS ─────────────────────────────────────────────────────
function showPropsPanel() {
  const panel   = document.getElementById('props-panel');
  const section = document.getElementById('props-section');
  const title   = document.getElementById('props-title');
  const content = document.getElementById('props-content');
  if (!panel || !title || !content) return;

  if (!E.sel) {
    panel.classList.add('hidden');
    if (section) section.style.display = 'none';
    return;
  }

  panel.classList.remove('hidden');
  if (section) section.style.display = '';

  const { type, id } = E.sel;
  let html = '';

  if (type === 'house') {
    title.textContent = 'Maison';
    html = `
      <div class="props-row"><span>Largeur</span><strong>${E.house.w.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Profondeur</span><strong>${E.house.h.toFixed(1)} m</strong></div>
      <div class="props-row">
        <label>Hauteur bâtiment (m)
          <input type="number" min="2" max="20" step="0.5" value="${E.house.hM}"
            oninput="E.house.hM=parseFloat(this.value)||6; render();"
            onchange="pushHistory(); afterChange();">
        </label>
      </div>`;
  } else if (type === 'terrace' && E.terrace) {
    title.textContent = 'Terrasse';
    html = `
      <div class="props-row"><span>Largeur</span><strong>${E.terrace.w.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Profondeur</span><strong>${E.terrace.h.toFixed(1)} m</strong></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'extension') {
    const ext = E.extensions.find(x => x.id === id);
    title.textContent = 'Extension';
    if (ext) html = `
      <div class="props-row"><span>Largeur</span><strong>${ext.w.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Profondeur</span><strong>${ext.h.toFixed(1)} m</strong></div>
      <div class="props-row"><label>Hauteur (m)
        <input type="number" min="1" max="15" step="0.5" value="${ext.hM}"
          oninput="E.extensions.find(x=>x.id===${id}).hM=parseFloat(this.value)||6; render();"
          onchange="pushHistory(); afterChange();">
      </label></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'abri') {
    const ab = E.abris.find(x => x.id === id);
    title.textContent = 'Abri de jardin';
    if (ab) html = `
      <div class="props-row"><span>Largeur</span><strong>${ab.w.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Profondeur</span><strong>${ab.h.toFixed(1)} m</strong></div>
      <div class="props-row"><label>Hauteur (m)
        <input type="number" min="1" max="5" step="0.1" value="${ab.hM}"
          oninput="E.abris.find(x=>x.id===${id}).hM=parseFloat(this.value)||2.2; render();"
          onchange="pushHistory(); afterChange();">
      </label></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'potager') {
    const pt = E.potagers.find(x => x.id === id);
    title.textContent = 'Potager';
    if (pt) html = `
      <div class="props-row"><span>Largeur</span><strong>${pt.w.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Profondeur</span><strong>${pt.h.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Surface</span><strong>${(pt.w*pt.h).toFixed(1)} m²</strong></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'massif') {
    const ms = E.massifs.find(m => m.id === id);
    title.textContent = 'Massif';
    if (ms) html = `
      <div class="props-row"><span>Surface</span><strong>${polyArea(ms.pts).toFixed(1)} m²</strong></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'massifRond') {
    const mr = E.massifsRonds.find(m => m.id === id);
    title.textContent = 'Massif rond';
    if (mr) html = `
      <div class="props-row"><span>Rayon X</span><strong>${mr.rx.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Rayon Y</span><strong>${mr.ry.toFixed(1)} m</strong></div>
      <div class="props-row"><span>Surface</span><strong>${(Math.PI*mr.rx*mr.ry).toFixed(1)} m²</strong></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'trou') {
    const tr = E.trous.find(t => t.id === id);
    title.textContent = 'Trou de plantation';
    if (tr) html = `
      <div class="props-row"><span>Rayon</span><strong>${tr.r.toFixed(2)} m</strong></div>
      <div class="props-row"><label>Rayon (m)
        <input type="number" min="0.15" max="1.5" step="0.05" value="${tr.r}"
          oninput="E.trous.find(t=>t.id===${id}).r=parseFloat(this.value)||0.3; render();"
          onchange="pushHistory(); afterChange();">
      </label></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else if (type === 'arbreV') {
    const av = E.arbresV.find(a => a.id === id);
    title.textContent = 'Arbre voisin';
    if (av) html = `
      <div class="props-row"><span>Rayon couronne</span><strong>${av.crownR.toFixed(1)} m</strong></div>
      <div class="props-row"><label>Rayon couronne (m)
        <input type="number" min="1" max="10" step="0.5" value="${av.crownR}"
          oninput="E.arbresV.find(a=>a.id===${id}).crownR=parseFloat(this.value)||4; render();"
          onchange="pushHistory(); afterChange();">
      </label></div>
      <div class="props-row"><label>Hauteur (m)
        <input type="number" min="2" max="25" step="1" value="${av.hM}"
          oninput="E.arbresV.find(a=>a.id===${id}).hM=parseFloat(this.value)||8; render();"
          onchange="pushHistory(); afterChange();">
      </label></div>
      <button class="btn btn-danger" onclick="deleteSelected()">Supprimer</button>`;
  } else {
    panel.classList.add('hidden');
    if (section) section.style.display = 'none';
    return;
  }
  content.innerHTML = html;
}

// ─── SYNTHÈSE TECHNIQUE ─────────────────────────────────────────────────────
function polyArea(pts) {
  let a = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++)
    a += (pts[j].x + pts[i].x) * (pts[j].y - pts[i].y);
  return Math.abs(a) / 2;
}

function cardinalFromDeg(deg) {
  const c = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSO','SO','OSO','O','ONO','NO','NNO'];
  return c[Math.round(((deg % 360) + 360) % 360 / 22.5) % 16];
}

function updateSynthesis() {
  const P = E.parcel, H = E.house;
  const T = E.terrace;
  const surfP = +(P.w * P.h).toFixed(1);
  const surfH = +(H.w * H.h).toFixed(1);
  const surfExt = E.extensions.reduce((s, e) => s + e.w * e.h, 0);
  const surfT = T ? +(T.w * T.h).toFixed(1) : 0;
  const surfJ = Math.max(0, surfP - surfH - surfExt - surfT).toFixed(1);
  const pct   = ((surfH + surfExt) / surfP * 100).toFixed(0);
  const haiesLen  = E.hedges.reduce((s, hg) => s + Math.hypot(hg.x2-hg.x1, hg.y2-hg.y1), 0).toFixed(1);
  const haiesSurf = E.hedges.reduce((s, hg) => s + Math.hypot(hg.x2-hg.x1, hg.y2-hg.y1) * (hg.wM ?? 0.5), 0).toFixed(1);
  const closedMs = E.massifs.filter(m => m.closed && m.pts.length >= 3);
  const surfMs   = (closedMs.reduce((s, m) => s + polyArea(m.pts), 0) +
                    E.massifsRonds.reduce((s, m) => s + Math.PI * m.rx * m.ry, 0)).toFixed(1);
  const facadeDir = cardinalFromDeg(E.northDeg + 180);

  // Sync inputs maison si redimensionnée par drag
  setVal('editor-house-w',    H.w);
  setVal('editor-house-h',    H.h);
  setVal('editor-house-surf', (H.w * H.h).toFixed(0));

  setSynth('synth-surf-parc',   `${surfP} m²`);
  setSynth('synth-surf-maison', `${surfH} m² (${pct}% du terrain)`);
  setSynth('synth-surf-jard',   `${surfJ} m²`);
  setSynth('synth-surf-terr',   T ? `${surfT} m²` : '—');
  setSynth('synth-orient-parc', `N + ${Math.round(E.northDeg)}°`);
  setSynth('synth-orient-mais', `Façade principale → ${facadeDir}`);
  setSynth('synth-haies',       `${haiesLen} m lin. — ${haiesSurf} m²`);
  setSynth('synth-massifs',     `${closedMs.length + E.massifsRonds.length} massif(s) — ${surfMs} m²`);

  showPropsPanel();
}

function setSynth(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }

// ─── OUTILS ─────────────────────────────────────────────────────────────────
function selectTool(tool) {
  if (tool !== E.tool) {
    E.hedgePt1 = null; E.massifPts = null;
    E.hedgePreview = null; E.massifPreview = null;
    E._drawRectState = null; E._drawCircleState = null;
    _showDrawControls(false);
  }
  E.tool = tool; E.sel = null;
  document.querySelectorAll('.editor-tool-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tool === tool));
  canvas.style.cursor = tool === 'select' ? 'default' : 'crosshair';
  document.getElementById('props-panel')?.classList.add('hidden');
  document.getElementById('props-section') && (document.getElementById('props-section').style.display = 'none');

  const hints = {
    extension: 'Cliquez sur le plan, glissez et relâchez pour dessiner l\'extension.',
    terrasse:  'Cliquez sur le plan, glissez et relâchez pour dessiner la terrasse.',
    abri:      'Cliquez sur le plan, glissez et relâchez pour placer l\'abri de jardin.',
    potager:   'Cliquez sur le plan, glissez et relâchez pour tracer le potager.',
    haie:      'Cliquez deux points sur le plan pour tracer la haie.',
    massif:    'Cliquez 3 fois sur le plan pour placer les sommets du massif.',
    'massif-rond': 'Cliquez, glissez et relâchez pour définir le massif rond.',
    trou:      'Cliquez, glissez et relâchez pour définir le trou de plantation.',
    'arbre-voisin': 'Cliquez, glissez et relâchez pour placer l\'arbre voisin.',
  };
  const hint = hints[tool];
  if (hint && window.showToast) showToast(hint, 'info', 3000);

  render();
}

// ─── GÉOLOCALISATION ─────────────────────────────────────────────────────────
function useMyLocation() {
  if (!navigator.geolocation) {
    typeof showToast !== 'undefined' && showToast('Géolocalisation non disponible', 'error');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    pos => {
      E.lat = +pos.coords.latitude.toFixed(5);
      E.lon = +pos.coords.longitude.toFixed(5);
      setVal('editor-lat', E.lat); setVal('editor-lon', E.lon);
      typeof showToast !== 'undefined' && showToast(`Position : ${E.lat}, ${E.lon}`, 'success');
      afterChange();
      loadSunCourse();
    },
    () => typeof showToast !== 'undefined' && showToast('Position GPS indisponible', 'error')
  );
}

// ─── EXPORT PAYLOAD ─────────────────────────────────────────────────────────
function getPayload() {
  const slopeEnabled = document.getElementById('slope-enabled')?.checked || false;
  const slopePct     = slopeEnabled ? (parseFloat(document.getElementById('slope-steepness')?.value) || 10) : 0;
  const slopeOr      = slopeEnabled ? (parseFloat(document.getElementById('slope-orientation')?.value) || 180) : 0;

  // Blocs maison : maison principale + extensions
  const maisons = [
    { origine: [E.house.x, E.house.y], largeur: E.house.w, hauteur: E.house.h, hauteur_batiment: E.house.hM },
    ...E.extensions.map(ext => ({ origine: [ext.x, ext.y], largeur: ext.w, hauteur: ext.h, hauteur_batiment: ext.hM })),
    ...E.abris.map(ab => ({ origine: [ab.x, ab.y], largeur: ab.w, hauteur: ab.h, hauteur_batiment: ab.hM })),
  ];

  return {
    parcelle : { origine: [0, 0], largeur: E.parcel.w, hauteur: E.parcel.h },
    maisons,
    terrasse : E.terrace
      ? { origine: [E.terrace.x, E.terrace.y], largeur: E.terrace.w, hauteur: E.terrace.h }
      : null,
    trous_terrasse: [],
    haies_auto    : [],
    obstacles     : E.hedges.map(hg => ({ type: 'haie', a: [hg.x1, hg.y1], b: [hg.x2, hg.y2], hauteur: hg.hM })),
    orientation_nord_deg: E.northDeg,
    latitude : E.lat, longitude: E.lon,
    pas_grille_m : parseFloat(getVal('editor-pas')) || 1,
    timezone     : E.tz, date_ref: E.dateRef,
    pas_minutes  : 10, heure_debut: 6, heure_fin: 21,
    haie_position: 'À la lisière de la parcelle (recommandé)',
    zone_analyse : null,
    slope_pct    : slopePct,
    slope_orientation_deg: slopeOr,
  };
}

function notifyPayloadChange() {
  window.terrainPayload = getPayload();
}

// ─── PENTE ───────────────────────────────────────────────────────────────────
function toggleSlope() {
  const section = document.getElementById('slope-section');
  if (section) section.style.display = section.style.display === 'none' ? '' : 'none';
}

function onSlopeToggle(enabled) {
  document.getElementById('slope-fields').style.display = enabled ? '' : 'none';
  afterChange();
}

function setSlopeVal(v) {
  const el = document.getElementById('slope-pct');
  if (el) el.textContent = v + '%';
  afterChange();
}

// ─── DIAGNOSTIQUE LLM ───────────────────────────────────────────────────────
async function checkLLMStatus() {
  const statusEl = document.getElementById('llm-status-msg');
  if (!statusEl) return;
  const setText = t => {
    const inner = statusEl.querySelector('.llm-status-text');
    if (inner) inner.textContent = t; else statusEl.textContent = t;
  };
  setText('Vérification…');
  statusEl.className = 'llm-status loading';
  try {
    const r = await fetch('/llm-status');
    const d = await r.json();
    if (d.ok) {
      setText(d.message || `Agent IA opérationnel (${d.model})`);
      statusEl.className = 'llm-status ok';
    } else {
      setText(d.message || 'Agent IA : erreur');
      statusEl.className = 'llm-status error';
    }
  } catch {
    setText('Statut agent indisponible');
    statusEl.className = 'llm-status error';
  }
}

// ─── DÉMARRAGE ───────────────────────────────────────────────────────────────

// Bloque le zoom navigateur : molette+Ctrl, pinch trackpad, raccourcis clavier
window.addEventListener('wheel', e => {
  if (e.ctrlKey) e.preventDefault();
}, { passive: false });
window.addEventListener('gesturestart',  e => e.preventDefault(), { passive: false });
window.addEventListener('gesturechange', e => e.preventDefault(), { passive: false });
window.addEventListener('keydown', e => {
  if (e.ctrlKey && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
    e.preventDefault(); // bloque Ctrl+/- zoom navigateur
  }
}, { capture: true });

document.addEventListener('DOMContentLoaded', () => {
  initEditor();
  checkLLMStatus();

  window.selectTool = selectTool;
  window.undo = undo;
  window.redo = redo;
  window.finishDraw = finishDraw;
  window.cancelDraw = cancelDraw;
  window.fitToScreen = fitToScreen;
  window.toggleSunSimulation = toggleSunSimulation;
  window.stopSunSimulation = stopSunSimulation;

  document.addEventListener('click', e => {
    if (!e.target.closest('[data-tooltip]') && !e.target.closest('.tooltip-bubble'))
      closeAllTooltips();
  }, true);
});

function closeAllTooltips() {
  document.querySelectorAll('.tooltip-bubble').forEach(t => t.remove());
}
