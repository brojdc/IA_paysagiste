'use strict';
/* =============================================
   app.js — Analyse terrain, rendu résultats
   ============================================= */

/* ── setLoading (A6) ─────────────────────────────────────────────── */
function setLoading(id, on) {
  document.getElementById(id)?.classList.toggle('skeleton', on);
}
window.setLoading = setLoading;

/* ── showToast ───────────────────────────────────────────────────── */
function showToast(msg, type = 'info', duration = 3500) {
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span>
                  <span class="toast-msg">${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; }, duration);
  setTimeout(() => el.remove(), duration + 350);
}
window.showToast = showToast;

/* ── lancerAnalyse ───────────────────────────────────────────────── */
async function lancerAnalyse() {
  const payload = window.terrainPayload;
  if (!payload || !payload.parcelle?.largeur) {
    showToast('Configurez le terrain dans l\'éditeur avant d\'analyser.', 'error');
    return;
  }

  const btn = document.getElementById('btn-analyser');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Analyse en cours…'; }

  showToast('Analyse en cours…', 'info', 5000);

  try {
    const headers = { 'Content-Type': 'application/json' };
    const body    = JSON.stringify(payload);

    const [surfacesRes, expoRes, planRes] = await Promise.all([
      fetch('/analyser',           { method: 'POST', headers, body }),
      fetch('/exposition_precise', { method: 'POST', headers, body }),
      fetch('/plan_2d',            { method: 'POST', headers, body }),
    ]);

    for (const r of [surfacesRes, expoRes, planRes]) {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `Erreur ${r.status}`);
      }
    }

    const [surfaces, exposition, plan] = await Promise.all([
      surfacesRes.json(),
      expoRes.json(),
      planRes.json(),
    ]);

    // Rendre dans le tab résultats
    renderSurfaces(surfaces);
    renderExposition(exposition, payload);
    renderPlan2D(plan, payload);

    // Mettre à jour le bandeau + cartes exposition
    showResults(surfaces, exposition, payload);

    // Révéler le tab résultats
    const analysisContent = document.getElementById('analysis-content');
    const noAnalysis      = document.getElementById('no-analysis-state');
    if (analysisContent) analysisContent.classList.remove('hidden');
    if (noAnalysis)      noAnalysis.style.display = 'none';

    // Date dans le sous-titre
    const dateEl = document.getElementById('results-date');
    if (dateEl) dateEl.textContent = new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });

    showToast('Analyse terminée ! Consultez l\'onglet Résultats.', 'success');

    // Mini résultats dans la sidebar
    _showSidebarMiniResults(exposition, payload);

  } catch (err) {
    showToast('Erreur : ' + err.message, 'error');
    console.error(err);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '☀️ Analyser le terrain'; }
  }
}
window.lancerAnalyse = lancerAnalyse;

/* ── showResults — bandeau + 3 cartes ───────────────────────────── */
function showResults(surfaces, exposition, payload) {
  const resume = exposition.resume || {};
  const pctSoleil   = resume.pct_plein_soleil ?? 0;
  const pctMiOmbre  = resume.pct_mi_ombre     ?? 0;
  const pctOmbre    = resume.pct_ombre         ?? 0;

  // Surfaces pour les cartes
  const surfTotale = payload?.parcelle
    ? payload.parcelle.largeur * payload.parcelle.hauteur
    : (surfaces?.surfaces_m2?.Parcelle || 0);
  const surfMaison  = surfaces?.surfaces_m2?.Maison  || 0;
  const surfTerr    = surfaces?.surfaces_m2?.Terrasse || 0;
  const surfJardin  = Math.max(0, surfTotale - surfMaison - surfTerr);

  const surfSoleil  = (pctSoleil  / 100 * surfJardin).toFixed(0);
  const surfMiOmbre = (pctMiOmbre / 100 * surfJardin).toFixed(0);
  const surfOmbre   = (pctOmbre   / 100 * surfJardin).toFixed(0);

  // Bandeau
  _setText('banner-soleil',  pctSoleil  + '%');
  _setText('banner-miombre', pctMiOmbre + '%');
  _setText('banner-ombre',   pctOmbre   + '%');

  // Cartes
  _setText('card-pct-soleil',   pctSoleil  + '%');
  _setText('card-surf-soleil',  surfSoleil  + ' m²');
  _setText('card-pct-miombre',  pctMiOmbre + '%');
  _setText('card-surf-miombre', surfMiOmbre + ' m²');
  _setText('card-pct-ombre',    pctOmbre   + '%');
  _setText('card-surf-ombre',   surfOmbre   + ' m²');
}

function _showSidebarMiniResults(exposition, payload) {
  const mini = document.getElementById('sidebar-mini-results');
  const banner = document.getElementById('mini-expo-banner');
  if (!mini || !banner) return;

  const resume = exposition.resume || {};
  const sol    = resume.pct_plein_soleil ?? '?';
  const mi     = resume.pct_mi_ombre     ?? '?';
  const om     = resume.pct_ombre         ?? '?';

  banner.innerHTML = `
    <div class="mini-expo-stats">
      <div class="mini-expo-chip soleil">☀️ ${sol}%</div>
      <div class="mini-expo-chip miombre">⛅ ${mi}%</div>
      <div class="mini-expo-chip ombre">🌑 ${om}%</div>
    </div>
    <div style="font-size:0.72rem;color:#666;">
      Jardin : plein soleil ${sol}% · mi-ombre ${mi}% · ombre ${om}%
    </div>`;

  mini.classList.remove('hidden');
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/* ── exportPdf ───────────────────────────────────────────────────── */
async function exportPdf() {
  const payload = window.terrainPayload;
  if (!payload) {
    showToast('Configurez et analysez le terrain avant d\'exporter.', 'error');
    return;
  }

  const btns = ['btn-pdf', 'btn-pdf-results'].map(id => document.getElementById(id)).filter(Boolean);
  btns.forEach(b => { b.disabled = true; b.textContent = '⏳ Génération…'; });

  try {
    const r = await fetch('/pdf-time-slices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        terrain: payload,
        nom_projet: 'Projet paysage',
        paysagiste: 'Paysagiste',
      }),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${r.status}`);
    }

    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `terrain_${new Date().toISOString().slice(0,10)}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('PDF exporté avec succès !', 'success');

  } catch (err) {
    showToast('Erreur PDF : ' + err.message, 'error');
    console.error(err);
  } finally {
    btns.forEach(b => {
      b.disabled = false;
      b.textContent = b.id === 'btn-pdf' ? '📄 Exporter plan PDF' : '📄 Exporter PDF';
    });
  }
}
window.exportPdf = exportPdf;

/* ── renderSurfaces ──────────────────────────────────────────────── */
function renderSurfaces(data) {
  const grid = document.getElementById('surfaces-grid');
  if (!grid) return;
  const surfaces = data.surfaces_m2 || {};
  grid.innerHTML = Object.entries(surfaces).map(([label, val]) => `
    <div class="metric-card">
      <div class="metric-value">${val} m²</div>
      <div class="metric-label">${label}</div>
    </div>
  `).join('');
}

/* ── renderExposition ────────────────────────────────────────────── */
function renderExposition(data, payload) {
  const canvas = document.getElementById('canvas-exposition');
  if (!canvas) return;
  const ctx   = canvas.getContext('2d');
  const cells = data.cells || [];
  const W     = data.largeur || payload.parcelle.largeur;
  const H     = data.hauteur || payload.parcelle.hauteur;

  const sc = Math.min(canvas.width / W, canvas.height / H);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#e8f2dc';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  cells.forEach(c => {
    const color = c.classe === 'ombre'     ? '#2d5016'
                : c.classe === 'mi_ombre'  ? '#87a96b'
                :                            '#f5c842';
    const cx = c.x * sc;
    const cy = canvas.height - (c.y + (data.pas_grille_m || 1)) * sc;
    const cw = (data.pas_grille_m || 1) * sc + 0.5;
    const ch = (data.pas_grille_m || 1) * sc + 0.5;
    ctx.fillStyle = color;
    ctx.fillRect(cx, cy, cw, ch);
  });

  // Bâtiments
  const maisons = payload.maisons || [];
  ctx.strokeStyle = '#404040';
  ctx.lineWidth   = 1.5;
  ctx.fillStyle   = 'rgba(80,80,80,0.55)';
  maisons.forEach(m => {
    const [mx, my] = m.origine;
    ctx.fillRect(mx * sc, canvas.height - (my + m.hauteur) * sc, m.largeur * sc, m.hauteur * sc);
    ctx.strokeRect(mx * sc, canvas.height - (my + m.hauteur) * sc, m.largeur * sc, m.hauteur * sc);
  });

  const t = payload.terrasse;
  if (t) {
    ctx.fillStyle   = 'rgba(180,140,90,0.45)';
    ctx.strokeStyle = '#8b6914';
    ctx.lineWidth   = 1;
    ctx.fillRect(t.origine[0] * sc, canvas.height - (t.origine[1] + t.hauteur) * sc, t.largeur * sc, t.hauteur * sc);
    ctx.strokeRect(t.origine[0] * sc, canvas.height - (t.origine[1] + t.hauteur) * sc, t.largeur * sc, t.hauteur * sc);
  }

  const resume  = data.resume || {};
  const legendEl = document.getElementById('expo-legend');
  if (legendEl) {
    legendEl.innerHTML = `
      <span class="legend-ombre">Ombre : ${resume.pct_ombre ?? 0} %</span>
      <span class="legend-mi-ombre">Mi-ombre : ${resume.pct_mi_ombre ?? 0} %</span>
      <span class="legend-soleil">Plein soleil : ${resume.pct_plein_soleil ?? 0} %</span>
    `;
  }

  const detailEl = document.getElementById('expo-details');
  if (detailEl && resume.location) {
    const loc = resume.location;
    detailEl.textContent = `${loc.city || ''}, ${loc.region || ''} · ${resume.plage || ''}`;
    detailEl.style.cssText = 'font-size:0.78rem;color:#888;margin-top:6px';
  }
}

/* ── renderPlan2D ────────────────────────────────────────────────── */
function renderPlan2D(plan, payload) {
  const canvas = document.getElementById('canvas-plan');
  if (!canvas) return;
  const ctx    = canvas.getContext('2d');
  const shapes = plan.shapes || [];
  const W      = payload.parcelle.largeur;
  const H      = payload.parcelle.hauteur;
  const sc     = Math.min(canvas.width / W, canvas.height / H);

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const palette = {
    Parcelle  : { fill: '#e8f0dc', stroke: '#2d5016', lw: 2 },
    Maison    : { fill: '#9e9e9e', stroke: '#424242', lw: 1 },
    Extension : { fill: '#bdbdbd', stroke: '#616161', lw: 1 },
    Terrasse  : { fill: '#d4b896', stroke: '#8b6914', lw: 1 },
    Trou      : { fill: '#c8e6c9', stroke: '#388e3c', lw: 1 },
  };

  shapes.forEach(s => {
    const key   = Object.keys(palette).find(k => s.label.startsWith(k)) || 'Parcelle';
    const color = palette[key];
    ctx.fillStyle   = color.fill;
    ctx.strokeStyle = color.stroke;
    ctx.lineWidth   = color.lw;

    if (s.type === 'rectangle') {
      const px = s.x * sc;
      const py = canvas.height - (s.y + s.h) * sc;
      const pw = s.w * sc;
      const ph = s.h * sc;
      ctx.fillRect(px, py, pw, ph);
      ctx.strokeRect(px, py, pw, ph);
      if (pw > 30 && ph > 14) {
        ctx.fillStyle    = key === 'Parcelle' ? '#2d5016' : '#fff';
        ctx.font         = `bold ${Math.min(12, pw * 0.15)}px Inter, sans-serif`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(s.label, px + pw / 2, py + ph / 2);
      }
    } else if (s.type === 'cercle' && s.r) {
      ctx.beginPath();
      ctx.arc(s.x * sc, canvas.height - s.y * sc, s.r * sc, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
  });
}
