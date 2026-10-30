"""Página do visualizador completo (HTML + JS, sem bibliotecas, funciona offline)."""

from __future__ import annotations

import json

# textos que aparecem no visualizador exportado (ficam no catálogo e são traduzidos ao gerar a página)
_UI_TEXTS = (
    'EXAMES',
    'Filtro',
    'Nitidez',
    'Suavizado',
    'Filtro da imagem: nitidez ou suavização (S)',
    'Carregando…',
    ' (reconstrução)',
    '0 · Do arquivo',
    '10 mm',
    '1–6 janelas prontas · 0 janela do arquivo · I inverter · espaço cine · PgUp/PgDn ±10',
    '20 mm',
    '3 mm',
    '40 mm',
    '5 mm',
    'Ajuda',
    'Ampliar / voltar (duplo clique, F)',
    'Apaga as medidas desta imagem (Del apaga a última)',
    'Apagar medidas',
    'Axial',
    'Axial / Coronal / Sagital: reconstrói só o plano escolhido',
    'Cine (espaço)',
    'Como juntar os cortes do slab',
    'Coronal',
    'Cérebro',
    'Elipse',
    'Espessura (slab) + MIP/Média/MinIP: vale para a imagem ativa',
    'Espessura da imagem ativa (slab): junta vários cortes',
    'Esquerdo: ferramenta escolhida · Direito arrastado: zoom · Meio arrastado: mover',
    'Este exame não tem mamografia com lado e incidência.',
    'Este navegador é antigo. Use Chrome, Edge, Firefox ou Safari atualizados.',
    'Fino',
    'Fígado',
    'Imagens como foram adquiridas',
    'Inverter',
    'Inverter (I)',
    'Janela',
    'Janela calculada só no tecido da mama (sem o fundo)',
    'Janela da mama',
    'Janela/nível (W)',
    'Janelas prontas (teclas 1–6; 0 = do arquivo)',
    'Janelas…',
    'MIP',
    'MPR 3 planos',
    'MPR oblíquo: trace uma linha numa imagem; o plano perpendicular a ela abre ao lado (O)',
    'Mamografia',
    'Mamografia: as incidências lado a lado, parede torácica para o centro, com a janela do tecido',
    'Mamografia: monta CC e MLO das duas mamas lado a lado, com a parede torácica voltada\npara o centro e a janela do tecido · Quadrante (Q): amplia o quadrante posterior e superior, depois o\nposterior e inferior, e volta à imagem inteira — nos quadros juntos · Janela da mama: refaz a janela só\nno tecido',
    'Marcar o valor de um ponto (V)',
    'Medidas',
    'Medidas do exame',
    'MinIP',
    'Mostrar medidas e anotações feitas no Ipê',
    'Mouse',
    'Mover',
    'Mover (P)',
    'Média',
    'No MPR: clique (sem arrastar) numa vista move a cruz nas outras; duplo clique (ou ⤢, ou F) amplia a vista\npara a tela toda e volta',
    'Não destinado a uso diagnóstico.',
    'O zoom por quadrante é da mamografia (use o botão Mamografia).',
    'Oblíquo',
    'Oblíquo (O): trace uma linha numa imagem; abre ao lado o plano perpendicular que passa por ela (rodinha move o plano)',
    'Original',
    'Ponto',
    'Pulmão',
    'Quadrante',
    'ROI elíptica: área, média, DP (E)',
    'ROI retangular (R)',
    'Reconstrução só no plano axial',
    'Reconstrução só no plano coronal',
    'Reconstrução só no plano sagital',
    'Restaurar',
    'Restaurar (duplo clique)',
    'Retângulo',
    'Rodinha / setas: trocar a imagem · Ctrl+rodinha: zoom · Duplo clique: restaurar',
    'Régua',
    'Régua (M)',
    'Régua e ROIs em mm (quando o exame informa o tamanho do pixel). ROI mostra área, média, DP, mín./máx.\nna unidade do exame (HU na TC). Ângulo: 3 cliques. Del apaga a última; Esc cancela.',
    'Sagital',
    'Série grande demais para reconstruir no navegador.',
    'Teclas',
    'Três planos com cruz sincronizada; duplo clique (ou ⤢) amplia uma vista',
    'Zoom',
    'Zoom (Z)',
    'Zoom por quadrante da mama: posterior e superior → posterior e inferior → imagem inteira (Q)',
    'não achei ',
    'plano oblíquo',
    'Ângulo',
    'Ângulo: 3 cliques (A)',
    '▶ Cine',
)


TEMPLATE = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Visualizador — Ipê</title>
<style>
:root{--bg:#141517;--panel:#1d1f23;--line:#33363d;--fg:#e6e8eb;--dim:#9aa0a8;--acc:#4fb3ff;--on:#27405e}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
font:13px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden}
#app{display:flex;height:100%}
#side{width:240px;min-width:240px;background:var(--panel);border-right:1px solid var(--line);overflow:auto}
#side h1{font-size:12px;margin:0;padding:10px 12px;color:var(--dim);font-weight:600;letter-spacing:.4px}
.study{padding:8px 10px 4px;border-top:1px solid var(--line)}.study b{display:block;font-size:14px}
.study small{color:var(--dim)}
.ser{display:flex;gap:8px;align-items:center;margin:6px 0;padding:4px;border-radius:6px;cursor:pointer}
.ser:hover{background:#2a2d33}.ser.on{background:var(--on)}
.ser img{width:52px;height:52px;object-fit:contain;background:#000;border-radius:4px;flex:none}
.ser span{font-size:12px}.ser em{display:block;color:var(--dim);font-style:normal;font-size:11px}
#right{flex:1;display:flex;flex-direction:column;min-width:0}
#tools{display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:5px 8px;background:var(--panel);
border-bottom:1px solid var(--line)}
#tools .sep{width:1px;height:22px;background:var(--line);margin:0 4px}
button,select{background:#2c2f35;color:var(--fg);border:1px solid #454952;border-radius:4px;padding:4px 9px;
cursor:pointer;font:inherit;font-size:12px}button:hover{background:#383c44}button.on{background:var(--on);border-color:var(--acc)}
button:disabled{opacity:.4;cursor:default}
#views{flex:1;display:grid;gap:2px;background:#333;min-height:0}
#views.l1{grid-template-columns:1fr}#views.l3{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
.vp{position:relative;background:#000;overflow:hidden;min-width:0;min-height:0}
.vp.act{outline:2px solid #ffc800;outline-offset:-2px}
.vp canvas{position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair}
.vp.l3a{grid-row:1/3}
#views.l2{grid-template-columns:1fr 1fr}#views.l2 .vp .mx{display:block}
#views.mg2{grid-template-columns:1fr 1fr}#views.mg4{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
#views.maxed .vp{display:none}#views.maxed .vp.max{display:block;grid-column:1/-1;grid-row:1/-1}
.vp .mx{position:absolute;top:4px;left:calc(50% - 90px);padding:1px 7px;font-size:13px;opacity:.55;z-index:2;display:none}
#views.l3 .vp .mx{display:block}.vp .mx:hover{opacity:1}
#msg{position:fixed;left:50%;top:40%;transform:translate(-50%,-50%);background:rgba(20,21,23,.92);border:1px solid var(--line);
padding:14px 20px;border-radius:8px;display:none;z-index:5;font-size:14px}
#help{position:fixed;right:12px;top:48px;width:360px;background:#1d1f23;border:1px solid var(--line);border-radius:8px;
padding:10px 14px;display:none;z-index:6;font-size:12px;line-height:1.5}#help b{color:var(--acc)}
@media (max-width:800px){#side{width:140px;min-width:140px}.ser img{width:36px;height:36px}}
</style></head><body><div id="app">
<div id="side"><h1>EXAMES</h1><div id="list"></div></div>
<div id="right">
<div id="tools">
 <button data-tool="wl" class="on" title="Janela/nível (W)">Janela</button>
 <button data-tool="pan" title="Mover (P)">Mover</button>
 <button data-tool="zoom" title="Zoom (Z)">Zoom</button>
 <span class="sep"></span>
 <button data-tool="line" title="Régua (M)">Régua</button>
 <button data-tool="angle" title="Ângulo: 3 cliques (A)">Ângulo</button>
 <button data-tool="ellipse" title="ROI elíptica: área, média, DP (E)">Elipse</button>
 <button data-tool="rect" title="ROI retangular (R)">Retângulo</button>
 <button data-tool="probe" title="Marcar o valor de um ponto (V)">Ponto</button>
 <button data-tool="oblique" title="MPR oblíquo: trace uma linha numa imagem; o plano perpendicular a ela abre ao lado (O)">Oblíquo</button>
 <button id="clear" title="Apaga as medidas desta imagem (Del apaga a última)">Apagar medidas</button>
 <span class="sep"></span>
 <select id="preset" title="Janelas prontas (teclas 1–6; 0 = do arquivo)"></select>
 <button id="inv" title="Inverter (I)">Inverter</button>
 <button id="reset" title="Restaurar (duplo clique)">Restaurar</button>
 <button id="cine" title="Cine (espaço)">▶ Cine</button>
 <select id="slab" title="Espessura da imagem ativa (slab): junta vários cortes"><option value="0">Fino</option>
  <option value="3">3 mm</option><option value="5">5 mm</option><option value="10">10 mm</option><option value="20">20 mm</option>
  <option value="40">40 mm</option></select>
 <select id="slabmode" title="Como juntar os cortes do slab"><option value="mip">MIP</option><option value="avg">Média</option>
  <option value="minip">MinIP</option></select>
 <span class="sep"></span>
 <button id="pn" class="on" title="Imagens como foram adquiridas">Original</button>
 <button data-plane="Axial" title="Reconstrução só no plano axial">Axial</button>
 <button data-plane="Coronal" title="Reconstrução só no plano coronal">Coronal</button>
 <button data-plane="Sagital" title="Reconstrução só no plano sagital">Sagital</button>
 <button id="l3" title="Três planos com cruz sincronizada; duplo clique (ou ⤢) amplia uma vista">MPR 3 planos</button>
 <span class="sep"></span>
 <button id="mg" title="Mamografia: as incidências lado a lado, parede torácica para o centro, com a janela do tecido">Mamografia</button>
 <button id="mgq" title="Zoom por quadrante da mama: posterior e superior → posterior e inferior → imagem inteira (Q)">Quadrante</button>
 <button id="mgw" title="Janela calculada só no tecido da mama (sem o fundo)">Janela da mama</button>
 <span class="sep"></span>
 <button id="filt" title="Filtro da imagem: nitidez ou suavização (S)">Filtro</button>
 <button id="ann" class="on" title="Mostrar medidas e anotações feitas no Ipê">Medidas do exame</button>
 <button id="hbtn" title="Ajuda">?</button>
</div>
<div id="views" class="l1"></div>
</div></div>
<div id="msg"></div>
<div id="help"><b>Mouse</b><br>Esquerdo: ferramenta escolhida · Direito arrastado: zoom · Meio arrastado: mover<br>
Rodinha / setas: trocar a imagem · Ctrl+rodinha: zoom · Duplo clique: restaurar<br>
No MPR: clique (sem arrastar) numa vista move a cruz nas outras; duplo clique (ou ⤢, ou F) amplia a vista
para a tela toda e volta<br>Axial / Coronal / Sagital: reconstrói só o plano escolhido<br>
Oblíquo (O): trace uma linha numa imagem; abre ao lado o plano perpendicular que passa por ela (rodinha move o plano)<br>
Espessura (slab) + MIP/Média/MinIP: vale para a imagem ativa<br>
<b>Mamografia</b><br>Mamografia: monta CC e MLO das duas mamas lado a lado, com a parede torácica voltada
para o centro e a janela do tecido · Quadrante (Q): amplia o quadrante posterior e superior, depois o
posterior e inferior, e volta à imagem inteira — nos quadros juntos · Janela da mama: refaz a janela só
no tecido<br>
<b>Medidas</b><br>Régua e ROIs em mm (quando o exame informa o tamanho do pixel). ROI mostra área, média, DP, mín./máx.
na unidade do exame (HU na TC). Ângulo: 3 cliques. Del apaga a última; Esc cancela.<br>
<b>Teclas</b><br>1–6 janelas prontas · 0 janela do arquivo · I inverter · espaço cine · PgUp/PgDn ±10<br>
<span style="color:#9aa0a8">Não destinado a uso diagnóstico.</span></div>
<script>
"use strict";
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const PRESETS = [["Pulmão",1500,-600],["Mediastino",400,40],["Osso",2000,400],["Cérebro",80,40],["Abdome",350,50],["Fígado",160,60]];
const SER = {};           // id -> {meta, frames[], chunks{ci: promise}}
const WIN = {};           // id -> {w,l,inv}
const MEAS = {};          // chave da imagem -> [medidas]
let cur = null;           // série aberta
let layout = 1, tool = "wl", showAnn = true, cineT = null, active = null;
const views = [];
const msg = t => { const m = $("msg"); m.textContent = t || ""; m.style.display = t ? "block" : "none"; };

// ------------------------------------------------------------------ dados
const pending = {};
window.DV = { chunk(id, ci, b64){ const p = pending[id + ":" + ci]; if (p) p.resolve(b64); } };
async function inflate(b64){
  let body;
  try { body = (await fetch("data:application/octet-stream;base64," + b64)).body; }   // decodificação nativa (rápida)
  catch (e) { const bin = atob(b64), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); body = new Blob([u]).stream(); }
  return new Uint8Array(await new Response(body.pipeThrough(new DecompressionStream("deflate"))).arrayBuffer());
}
function loadChunk(S, ci){
  if (S.chunks[ci]) return S.chunks[ci];
  const c = S.meta.chunks[ci], key = S.meta.id + ":" + ci;
  S.chunks[ci] = new Promise((resolve, reject) => {
    pending[key] = {resolve: async b64 => { try {
      const bytes = await inflate(b64), N = S.meta.rows * S.meta.cols;
      for (let f = 0; f < c.n; f++){
        const off = f * 2 * N, a = new Int16Array(N);
        const hiB = bytes.subarray(off, off + N), loB = bytes.subarray(off + N, off + 2 * N);
        for (let i = 0; i < N; i++) a[i] = (hiB[i] << 8 | loB[i]) << 16 >> 16;
        S.frames[c.k0 + f] = a;
      }
      delete pending[key]; resolve();
    } catch (e) { reject(e); } }};
    const sc = document.createElement("script"); sc.src = c.file;
    sc.onerror = () => reject(new Error("não achei " + c.file)); document.head.appendChild(sc);
  });
  return S.chunks[ci];
}
function chunkOf(meta, k){ return meta.chunks.findIndex(c => k >= c.k0 && k < c.k0 + c.n); }
function ensureFrame(S, k){
  if (S.meta.color) return loadImg(S, k);
  if (S.frames[k]) return null;
  return loadChunk(S, chunkOf(S.meta, k));
}
function loadImg(S, k){
  if (S.imgs[k] && S.imgs[k].complete) return null;
  if (!S.imgs[k]){ const im = new Image(); S.imgs[k] = im;
    S.imgP[k] = new Promise(r => { im.onload = r; im.onerror = r; }); im.src = S.meta.files[k]; }
  return S.imgP[k];
}
async function ensureAll(S){
  const n = S.meta.chunks.length; let done = 0;
  if (S.frames.filter(Boolean).length === S.meta.n) return;
  const all = []; for (let ci = 0; ci < n; ci++) all.push(loadChunk(S, ci));
  msg("Carregando o volume… 0%");
  // vários blocos em paralelo (o navegador lê e descompacta ao mesmo tempo)
  await Promise.all(all.map(p => p.then(() => { done++; msg(`Carregando o volume… ${Math.round(100 * done / n)}%`); })));
  msg("");
}
const real = (m, raw) => raw * m.scale + m.offset;
const unit = m => m.modality === "CT" ? "HU" : "";

// ------------------------------------------------------------------ geometria
const LET_P = ["L","P","S"], LET_N = ["R","A","I"];
function letter(v){
  if (!v) return ""; let s = ""; const o = [0,1,2].sort((a,b) => Math.abs(v[b]) - Math.abs(v[a]));
  for (const i of o){ if (Math.abs(v[i]) < .25 || s.length === 2) break; s += v[i] > 0 ? LET_P[i] : LET_N[i]; }
  return s;
}
const neg = v => v && v.map(x => -x);
function axisVecs(m){
  const o = m.orientation; if (!o) return [null, null, null];
  const r = o.slice(0,3), c = o.slice(3,6);
  const k = m.mpr ? m.mpr.k : [r[1]*c[2]-r[2]*c[1], r[2]*c[0]-r[0]*c[2], r[0]*c[1]-r[1]*c[0]];
  return [r, c, k];
}
function dims(m){ return [m.cols, m.rows, m.n]; }
function spacings(m){
  const sp = m.spacing; const sl = m.mpr ? m.mpr.slice : (parseFloat(m.thickness) || 1);
  return sp ? [sp[1], sp[0], sl] : [1, 1, 1];
}
// plano: "n" (nativo), "r" (fixa a linha j), "c" (fixa a coluna i)
function planeAxes(m, plane){
  if (plane === "n") return {h:{a:0,f:false}, v:{a:1,f:false}, fix:2};
  const V = axisVecs(m), ax = plane === "r" ? [0,2] : [1,2], fix = plane === "r" ? 1 : 0;
  const A = V[ax[0]], B = V[ax[1]];
  const nrm = [A[1]*B[2]-A[2]*B[1], A[2]*B[0]-A[0]*B[2], A[0]*B[1]-A[1]*B[0]];
  const d = [0,1,2].reduce((b, i) => Math.abs(nrm[i]) > Math.abs(nrm[b]) ? i : b, 0);
  // eixos da tela como nas estações: axial (dir.=L, baixo=P), coronal (dir.=L, baixo=I), sagital (dir.=P, baixo=I)
  const R = d === 2 ? [1,0,0] : d === 1 ? [1,0,0] : [0,1,0];
  const D = d === 2 ? [0,1,0] : [0,0,-1];
  const dot = (p, q) => p[0]*q[0] + p[1]*q[1] + p[2]*q[2];
  let hA = ax[0], vA = ax[1];
  if (Math.abs(dot(V[ax[1]], R)) > Math.abs(dot(V[ax[0]], R))) { hA = ax[1]; vA = ax[0]; }
  return {h:{a:hA, f: dot(V[hA], R) < 0}, v:{a:vA, f: dot(V[vA], D) < 0}, fix, kind: ["Sagital","Coronal","Axial"][d]};
}

function planeKind(m, pl){
  if (m.color || !axisVecs(m)[0]) return "";
  if (pl !== "n") return m.mpr ? planeAxes(m, pl).kind : "";
  const V = axisVecs(m); if (!V[2]) return "";
  const k = V[2], d = [0,1,2].reduce((b, i) => Math.abs(k[i]) > Math.abs(k[b]) ? i : b, 0);
  return ["Sagital","Coronal","Axial"][d];
}
function planeFor(m, kind){ return ["n","r","c"].find(pl => planeKind(m, pl) === kind); }

// ------------------------------------------------------------------ vistas
class View {
  constructor(el, plane){
    this.el = el; this.plane = plane; this.cv = el.querySelector("canvas"); this.ctx = this.cv.getContext("2d");
    this.off = document.createElement("canvas"); this.octx = this.off.getContext("2d");
    this.zoom = 1; this.px = 0; this.py = 0; this.key = ""; this.vals = null; this.draft = null; this.probe = null;
    this.slab = {mm: 0, mode: "mip"}; this.obl = null;
    this.pin = null;            // mamografia: esta vista mostra uma imagem fixa (série + quadro)
    this.mirror = false;        // espelhada (parede torácica voltada para o centro da tela)
    this.alignEdge = null;      // "left"/"right": encosta a imagem nessa borda
    this.quad = -1;             // quadrante em que está (-1 = imagem inteira)
    this.bind();
  }
  get S(){ return this.pin ? this.pin.S : cur; }
  get m(){ return this.S.meta; }
  get ax(){ return this.plane === "o" ? {h: {a: -1, f: false}, v: {a: -1, f: false}, fix: -1, kind: "Oblíquo"}
    : planeAxes(this.m, this.plane); }
  fixIndex(){ if (this.pin) return this.pin.k;
    return this.plane === "o" ? this.obl.off - this.obl.minOff : this.S.cursor[this.ax.fix]; }
  mgInfo(){ const m = this.m; return (this.pin && m.mg) ? (m.mg[this.fixIndex()] || null) : null; }
  sliceCount(){ return this.plane === "o" ? this.obl.maxOff - this.obl.minOff + 1 : dims(this.m)[this.ax.fix]; }
  measKey(){ return `${this.m.id}|${this.plane}${this.obl ? this.obl.id : ""}|${this.fixIndex()}`; }
  imageSize(){ if (this.plane === "o") return [this.obl.W, this.obl.H];
    const d = dims(this.m), a = this.ax; return [d[a.h.a], d[a.v.a]]; }
  mmPerPx(){ if (this.plane === "o") return [this.obl.ps, this.obl.ps];
    const s = spacings(this.m), a = this.ax; return [s[a.h.a], s[a.v.a]]; }
  stepMM(){ return this.plane === "o" ? this.obl.ps : spacings(this.m)[this.ax.fix]; }
  rect(){
    const [W, H] = this.imageSize(), [sx, sy] = this.mmPerPx();
    const cw = this.cv.width, ch = this.cv.height, pw = W * sx, ph = H * sy;
    const fit = Math.min(cw / pw, ch / ph) * this.zoom, dw = pw * fit, dh = ph * fit;
    let x = cw / 2 - dw / 2 + this.px;
    if (this.alignEdge && dw < cw) x += (cw - dw) / 2 * (this.alignEdge === "right" ? 1 : -1);
    return {x, y: ch / 2 - dh / 2 + this.py, w: dw, h: dh, W, H};
  }
  toImg(ex, ey){ const r = this.rect(), d = devicePixelRatio;
    const fx = (ex * d - r.x) / r.w;
    return [(this.mirror ? 1 - fx : fx) * r.W, (ey * d - r.y) / r.h * r.H]; }
  toScr(p){ const r = this.rect(), fx = p[0] / r.W;
    return [r.x + (this.mirror ? 1 - fx : fx) * r.w, r.y + p[1] / r.H * r.h]; }
  valueAt(p){ if (!this.vals) return null; const [W, H] = this.imageSize(), x = Math.floor(p[0]), y = Math.floor(p[1]);
    if (x < 0 || y < 0 || x >= W || y >= H) return null; return real(this.m, this.vals[y * W + x]); }
  chestOnScreen(){ const i = this.mgInfo(); if (!i || !i.chest) return null;
    return this.mirror ? (i.chest === "right" ? "left" : "right") : i.chest; }
  quadZoom(idx){
    const info = this.mgInfo(), [W, H] = this.imageSize();
    this.quad = idx;
    if (idx < 0 || !info){ this.zoom = 1; this.px = this.py = 0; this.redraw(); return; }
    const b = info.bbox || [0, 0, W, H];
    const bw = Math.max(1, b[2] - b[0]), bh = Math.max(1, b[3] - b[1]);
    const [sx, sy] = this.mmPerPx(), cw = this.cv.width, ch = this.cv.height;
    const f0 = Math.min(cw / (W * sx), ch / (H * sy));
    const z = Math.min(8, Math.max(2, Math.min(2 * cw / (sx * f0 * bw), 2 * ch / (sy * f0 * bh))));
    this.zoom = z; this.px = this.py = 0;
    const lado = this.chestOnScreen() || this.alignEdge || "left";
    const posterior = true, superior = idx === 0;          // só dois quadrantes: os posteriores
    const chestImg = (this.mgInfo() || {}).chest;
    const ix = posterior ? (chestImg === "right" ? b[2] : b[0]) : (chestImg === "right" ? b[0] : b[2]);
    const iy = superior ? b[1] : b[3];
    const tx = posterior ? (lado === "right" ? cw : 0) : (lado === "right" ? 0 : cw);
    const ty = superior ? 0 : ch;
    const p = this.toScr([ix, iy]);
    this.px += tx - p[0]; this.py += ty - p[1];
    this.redraw();
  }
  build(){
    const S = this.S, m = this.m, a = this.ax, [W, H] = this.imageSize();
    const w = WIN[m.id], k = this.fixIndex();
    const sl = m.color ? {mm: 0, mode: ""} : this.slab, oid = this.obl ? this.obl.id : "";
    const key = [m.id, this.plane, oid, k, w.w, w.l, w.inv, sl.mm, sl.mode, imgFilter].join("|");
    if (key === this.key) return true;
    const vkey = [m.id, this.plane, oid, k, sl.mm, sl.mode].join("|");
    if (m.color){
      const p = ensureFrame(S, k); if (p){ p.then(() => draw()); return false; }
      this.off.width = W; this.off.height = H; this.octx.filter = w.inv ? "invert(1)" : "none";
      this.octx.drawImage(S.imgs[k], 0, 0, W, H); this.vals = null; this.key = key; return true;
    }
    let vals;
    const needAll = this.plane === "o" || sl.mm > 0;
    if (vkey === this.vkey && this.vals){ vals = this.vals; }       // só mudou a janela: não reamostra
    else if (needAll && !allLoaded(S)){ ensureAll(S).then(() => draw()); return false; }
    else if (sl.mm > 0){
      const half = Math.max(0, Math.round(sl.mm / this.stepMM() / 2)), n = this.sliceCount();
      const get = this.plane === "o" ? kk => obliqueSample(S, this.obl, kk + this.obl.minOff)
        : this.plane === "n" ? kk => S.frames[kk] : kk => reslice(S, a, kk, W, H);
      vals = combine(get, k, n, half, sl.mode);
    }
    else if (this.plane === "o"){ vals = obliqueSample(S, this.obl, this.obl.off); }
    else if (this.plane === "n"){
      const p = ensureFrame(S, k); if (p){ p.then(() => draw()); return false; }
      vals = S.frames[k];
    } else {
      for (let q = 0; q < m.n; q++) if (!S.frames[q]) return false;
      vals = reslice(S, a, k, W, H);
    }
    this.vals = vals; this.vkey = vkey;
    const lut = getLut(m, w), img = this.octx.createImageData(W, H), d = img.data;
    let gray = new Uint8ClampedArray(vals.length);
    for (let i = 0; i < vals.length; i++) gray[i] = lut[vals[i] + 32768];
    if (imgFilter) gray = applyFilter(gray, W, H, imgFilter);
    for (let i = 0, j = 0; i < gray.length; i++, j += 4){ const g = gray[i]; d[j] = d[j+1] = d[j+2] = g; d[j+3] = 255; }
    this.off.width = W; this.off.height = H; this.octx.putImageData(img, 0, 0); this.key = key; return true;
  }
  draw(){
    const c = this.ctx, d = devicePixelRatio, cw = this.el.clientWidth, ch = this.el.clientHeight;
    if (!cw || !ch) return;
    if (this.cv.width !== Math.round(cw * d) || this.cv.height !== Math.round(ch * d)){
      this.cv.width = Math.round(cw * d); this.cv.height = Math.round(ch * d); }
    c.setTransform(1,0,0,1,0,0); c.fillStyle = "#000"; c.fillRect(0, 0, this.cv.width, this.cv.height);
    if (!cur) return;
    const ok = this.build(); const r = this.rect();
    if (ok){ c.imageSmoothingEnabled = this.zoom < 3;
      if (this.mirror){ c.save(); c.translate(r.x * 2 + r.w, 0); c.scale(-1, 1); }
      c.drawImage(this.off, r.x, r.y, r.w, r.h);
      if (this.mirror) c.restore(); }
    else { c.fillStyle = "#aaa"; c.font = `${14*d}px system-ui`; c.textAlign = "center";
      c.fillText("Carregando…", this.cv.width / 2, this.cv.height / 2); c.textAlign = "left"; }
    if (layout === 3 && this.plane !== "o") this.drawCross();
    this.drawMeasures(); this.drawOblLines(); this.drawOverlay();
  }
  drawOblLines(){
    for (const v of views){ const o = v.obl;
      if (!o || v === this || o.src !== this || this.measKey() !== o.srcKey) continue;
      const c = this.ctx, d = devicePixelRatio, sh = o.off * o.ps;
      const P = [o.P1, o.P2].map(p => mmToImg(this, [0,1,2].map(i => p[i] + sh * o.m[i]))).map(p => this.toScr(p));
      const dx = P[1][0] - P[0][0], dy = P[1][1] - P[0][1], L = Math.hypot(dx, dy) || 1, ext = 4000 * d;
      c.save(); c.strokeStyle = "#d58cff"; c.lineWidth = 1.5 * d; c.setLineDash([8*d, 5*d]); c.beginPath();
      c.moveTo(P[0][0] - dx / L * ext, P[0][1] - dy / L * ext); c.lineTo(P[0][0] + dx / L * ext, P[0][1] + dy / L * ext);
      c.stroke(); c.restore(); }
  }
  drawCross(){
    const c = this.ctx, a = this.ax, cu = cur.cursor, [W, H] = this.imageSize(), d = devicePixelRatio;
    const hx = a.h.f ? W - 1 - cu[a.h.a] : cu[a.h.a], vy = a.v.f ? H - 1 - cu[a.v.a] : cu[a.v.a];
    const [sx, sy] = this.toScr([hx + .5, vy + .5]);
    c.lineWidth = d; c.setLineDash([6*d, 5*d]);
    c.strokeStyle = PLANE_COL[a.h.a]; c.beginPath(); c.moveTo(sx, 0); c.lineTo(sx, this.cv.height); c.stroke();
    c.strokeStyle = PLANE_COL[a.v.a]; c.beginPath(); c.moveTo(0, sy); c.lineTo(this.cv.width, sy); c.stroke();
    c.setLineDash([]);
  }
  labelTxt(meas){
    const [sx, sy] = this.mmPerPx(), mm = !!this.m.spacing, u = unit(this.m), f = v => v == null ? "" : v.toFixed(Math.abs(v) < 10 ? 1 : 0);
    const P = meas.pts;
    if (meas.kind === "oblique") return "plano oblíquo";
    if (meas.kind === "line" || meas.kind === "arrow" && meas.label){
      const L = Math.hypot((P[1][0]-P[0][0])*sx, (P[1][1]-P[0][1])*sy);
      return mm ? (L >= 10 ? (L/10).toFixed(2) + " cm" : L.toFixed(1) + " mm") : L.toFixed(0) + " px"; }
    if (meas.kind === "angle" && P.length >= 3){
      const a = [(P[0][0]-P[1][0])*sx, (P[0][1]-P[1][1])*sy], b = [(P[2][0]-P[1][0])*sx, (P[2][1]-P[1][1])*sy];
      const ang = Math.acos(Math.max(-1, Math.min(1, (a[0]*b[0]+a[1]*b[1]) / (Math.hypot(...a)*Math.hypot(...b) || 1))));
      return (ang * 180 / Math.PI).toFixed(1) + "°"; }
    if (meas.kind === "probe"){ const v = this.valueAt(P[0]); return v == null ? "" : f(v) + (u ? " " + u : ""); }
    if (meas.kind === "ellipse" || meas.kind === "rect"){
      const st = this.roiStats(meas.kind, P); if (!st) return "";
      const area = mm ? (st.area / 100).toFixed(2) + " cm²" : st.n + " px";
      if (st.mean == null) return "Área " + area;
      return `Área ${area}\nMédia ${f(st.mean)} ${u}  DP ${f(st.sd)}\nMín ${f(st.min)}  Máx ${f(st.max)}`; }
    return meas.text || "";
  }
  roiStats(kind, P){
    const [sx, sy] = this.mmPerPx(), [W, H] = this.imageSize();
    const x0 = Math.min(P[0][0], P[1][0]), x1 = Math.max(P[0][0], P[1][0]), y0 = Math.min(P[0][1], P[1][1]), y1 = Math.max(P[0][1], P[1][1]);
    if (x1 - x0 < .5 || y1 - y0 < .5) return null;
    const cx = (x0+x1)/2, cy = (y0+y1)/2, rx = (x1-x0)/2, ry = (y1-y0)/2;
    const area = kind === "ellipse" ? Math.PI * rx * sx * ry * sy : (x1-x0) * sx * (y1-y0) * sy;
    if (!this.vals) return {area, n: 0, mean: null};
    let n = 0, s = 0, s2 = 0, mn = Infinity, mx = -Infinity;
    for (let y = Math.max(0, Math.floor(y0)); y < Math.min(H, Math.ceil(y1)); y++)
      for (let x = Math.max(0, Math.floor(x0)); x < Math.min(W, Math.ceil(x1)); x++){
        if (kind === "ellipse"){ const dx = (x + .5 - cx) / rx, dy = (y + .5 - cy) / ry; if (dx*dx + dy*dy > 1) continue; }
        const v = real(this.m, this.vals[y * W + x]); n++; s += v; s2 += v*v; if (v < mn) mn = v; if (v > mx) mx = v; }
    if (!n) return {area, n: 0, mean: null};
    const mean = s / n; return {area, n, mean, sd: Math.sqrt(Math.max(0, s2 / n - mean * mean)), min: mn, max: mx};
  }
  shape(meas, color){
    const c = this.ctx, d = devicePixelRatio, P = meas.pts.map(p => this.toScr(p));
    if (!P.length) return;
    c.save(); c.lineWidth = 1.6 * d; c.strokeStyle = color; c.fillStyle = color;
    c.shadowColor = "rgba(0,0,0,.9)"; c.shadowBlur = 2 * d;
    const k = meas.kind; c.beginPath();
    if ((k === "line" || k === "arrow" || k === "calibration" || k === "height" || k === "tic" || k === "oblique") && P.length >= 2){
      c.moveTo(...P[0]); c.lineTo(...P[1]); c.stroke();
      if (k === "arrow"){ const a = Math.atan2(P[0][1]-P[1][1], P[0][0]-P[1][0]), h = 12 * d;
        for (const s of [.45, -.45]){ c.beginPath(); c.moveTo(...P[0]); c.lineTo(P[0][0] - h*Math.cos(a+s), P[0][1] - h*Math.sin(a+s)); c.stroke(); } }
      else for (const p of P.slice(0,2)){ c.beginPath(); c.arc(p[0], p[1], 2.5*d, 0, 7); c.fill(); }
    } else if ((k === "ellipse") && P.length >= 2){
      c.ellipse((P[0][0]+P[1][0])/2, (P[0][1]+P[1][1])/2, Math.abs(P[1][0]-P[0][0])/2, Math.abs(P[1][1]-P[0][1])/2, 0, 0, 7); c.stroke();
    } else if (k === "rect" && P.length >= 2){ c.strokeRect(P[0][0], P[0][1], P[1][0]-P[0][0], P[1][1]-P[0][1]);
    } else if ((k === "angle" || k === "cobb" || k === "ctr") && P.length >= 2){
      if (k === "angle"){ c.moveTo(...P[0]); for (const p of P.slice(1)) c.lineTo(...p); c.stroke(); }
      else for (let i = 0; i + 1 < P.length; i += 2){ c.beginPath(); c.moveTo(...P[i]); c.lineTo(...P[i+1]); c.stroke(); }
    } else if (k === "polygon" || k === "polyline" || k === "pencil"){
      c.moveTo(...P[0]); for (const p of P.slice(1)) c.lineTo(...p); if (k === "polygon") c.closePath(); c.stroke();
    } else if (k === "probe" || k === "spine"){ for (const p of P){ c.beginPath(); c.arc(p[0], p[1], 3*d, 0, 7); c.stroke(); } }
    const lab = this.labelTxt(meas);
    if (lab){ c.font = `${12*d}px system-ui`; const at = P[P.length-1], lines = lab.split("\n");
      lines.forEach((t, i) => c.fillText(t, at[0] + 8*d, at[1] + (i * 14 + 4) * d)); }
    c.restore();
  }
  drawMeasures(){
    if (!cur || !this.m) return;
    if (showAnn && this.plane === "n") for (const a of this.m.annotations || []) if (a.k === this.fixIndex())
      this.shape({kind: a.kind, pts: a.pts, text: a.text, label: a.kind === "arrow" ? "" : null}, "#5cff8a");
    for (const ms of MEAS[this.measKey()] || []) this.shape(ms, "#ffd24a");
    if (this.draft) this.shape(this.draft, "#ffe98a");
  }
  drawOverlay(){
    const c = this.ctx, d = devicePixelRatio, m = this.m, W = this.cv.width, H = this.cv.height, a = this.ax;
    c.font = `${12*d}px system-ui`; c.shadowColor = "#000"; c.shadowBlur = 3*d; c.fillStyle = "#eee";
    const lh = 15 * d, pad = 8 * d;
    const st = cur.study, k = this.fixIndex(), n = this.sliceCount(), w = WIN[m.id];
    const tl = [st.label, st.sub], tr = [m.label];
    const bl = [`${this.plane === "n" ? "Im" : "Corte"} ${k + 1}/${n}`];
    if (this.plane === "n" && m.thickness && !this.slab.mm) bl.push(`Esp ${parseFloat(m.thickness).toFixed(1)} mm`);
    if (this.slab.mm && !m.color) bl.push(`${SLABN[this.slab.mode]} ${this.slab.mm} mm`);
    if (this.probe != null) bl.push(this.probe);
    const br = [m.color ? "" : `W ${Math.round(w.w)}  L ${Math.round(w.l)}`, this.zoom !== 1 ? `Zoom ${Math.round(this.zoom*100)}%` : ""];
    const put = (arr, right, bottom) => arr.filter(Boolean).forEach((t, i, all) => {
      c.textAlign = right ? "right" : "left";
      c.fillText(t, right ? W - pad : pad, bottom ? H - pad - (all.length - 1 - i) * lh : pad + (i + 1) * lh - 3*d); });
    put(tl, false, false); put(tr, true, false); put(bl, false, true); put(br, true, true);
    if (layout > 1 || this.plane !== "n"){ c.textAlign = "right"; c.fillStyle = this.plane === "o" ? "#d58cff" : PLANE_COL[a.fix];
      c.font = `bold ${12*d}px system-ui`;
      c.fillText((a.kind || "Original") + (this.plane === "n" ? "" : " (reconstrução)"), W - pad, pad + 2 * lh - 3*d); c.font = `${12*d}px system-ui`; c.fillStyle = "#eee"; }
    if (this.plane === "n" && (m.keys || []).includes(k)){ c.fillStyle = "#ffd200"; c.font = `${18*d}px system-ui`;
      c.textAlign = "center"; c.fillText("★", W / 2 + 40*d, pad + 16*d); }
    // letras de orientação
    const V = axisVecs(m); let L = null;       // [esquerda, direita, cima, baixo]
    if (this.plane === "o"){ L = [letter(neg(this.obl.hv)), letter(this.obl.hv), letter(neg(this.obl.vv)), letter(this.obl.vv)]; }
    else if (V[0]){ const hv = a.h.f ? neg(V[a.h.a]) : V[a.h.a], vv = a.v.f ? neg(V[a.v.a]) : V[a.v.a];
      L = [letter(neg(hv)), letter(hv), letter(neg(vv)), letter(vv)]; }
    else if (m.porient && m.porient.length === 2){        // mamografia etc.: PatientOrientation (linhas \ colunas)
      const [r, cc] = m.porient; L = [oppL(r), r, oppL(cc), cc]; }
    if (L){ c.fillStyle = "#ffdc78"; c.font = `bold ${13*d}px system-ui`;
      c.textAlign = "left"; c.fillText(L[0], pad, H / 2); c.textAlign = "right"; c.fillText(L[1], W - pad, H / 2);
      c.textAlign = "center"; c.fillText(L[2], W / 2, pad + 13*d); c.fillText(L[3], W / 2, H - pad - lh); }
    c.textAlign = "left"; c.shadowBlur = 0;
  }
  // ---------------------------------------------------------------- mouse
  bind(){
    const cv = this.cv; let drag = null;
    cv.addEventListener("contextmenu", e => e.preventDefault());
    cv.addEventListener("mousedown", e => {
      setActive(this); e.preventDefault(); if (!cur) return;
      const p = this.toImg(e.offsetX, e.offsetY);
      drag = {b: e.button, x: e.clientX, y: e.clientY, moved: false, p0: p, zoom: this.zoom, px: this.px, py: this.py, w: {...WIN[this.m.id]}};
      if (e.button !== 0) return;
      if (tool === "angle"){
        if (!this.draft || this.draft.kind !== "angle") this.draft = {kind: "angle", pts: [p, p]};
        else if (this.draft.pts.length === 2){ this.draft.pts[1] = p; this.draft.pts.push(p); }
        else { this.draft.pts[2] = p; this.addMeas(this.draft); this.draft = null; }
        drag.done = true; draw(); return; }
      if (["line","ellipse","rect","oblique"].includes(tool)){ this.draft = {kind: tool, pts: [p, p]}; drag.meas = true; }
      if (tool === "probe"){ this.addMeas({kind: "probe", pts: [p]}); drag.done = true; }
    });
    window.addEventListener("mousemove", e => {
      const inside = e.target === cv;
      if (inside && cur){ const p = this.toImg(e.offsetX, e.offsetY), v = this.valueAt(p);
        this.probe = v == null ? null : `${m2(v)} ${unit(this.m)}  (${Math.floor(p[0])}, ${Math.floor(p[1])})`;
        if (this.draft && this.draft.kind === "angle" && !drag){ this.draft.pts[this.draft.pts.length - 1] = p; }
        if (!drag) this.redraw(); }
      if (!drag || !cur) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y, d = devicePixelRatio;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (drag.meas && inside){ this.draft.pts[1] = this.toImg(e.offsetX, e.offsetY); }
      else if (drag.done){ if (inside && this.draft) this.draft.pts[this.draft.pts.length - 1] = this.toImg(e.offsetX, e.offsetY); }
      else if (drag.b === 2 || (drag.b === 0 && tool === "zoom")){ this.zoom = Math.max(.1, Math.min(40, drag.zoom * Math.exp(-dy / 150))); }
      else if (drag.b === 1 || (drag.b === 0 && tool === "pan")){ this.px = drag.px + dx * d; this.py = drag.py + dy * d; }
      else if (drag.b === 0 && tool === "wl" && !this.m.color){ const w = WIN[this.m.id], k = Math.max(drag.w.w, 1) / 300;
        w.w = Math.max(1, drag.w.w + dx * k); w.l = drag.w.l + dy * k; $("preset").value = ""; draw(); return; }
      this.redraw();
    });
    window.addEventListener("mouseup", e => {
      if (!drag) return; const dg = drag; drag = null; if (!cur) return;
      if (dg.meas){ const ms = this.draft; this.draft = null;
        const a = this.toScr(ms.pts[0]), b = this.toScr(ms.pts[1]);
        if (Math.hypot(a[0]-b[0], a[1]-b[1]) <= 4){ this.redraw(); return; }
        if (ms.kind === "oblique"){ createOblique(this, ms.pts); return; }
        this.addMeas(ms); return; }
      if (dg.done) return;
      if (dg.b === 0 && !dg.moved && layout === 3 && !dg.done) this.setCursor(dg.p0);
    });
    cv.addEventListener("wheel", e => { e.preventDefault(); if (!cur) return;
      if (e.ctrlKey){ this.zoom = Math.max(.1, Math.min(40, this.zoom * (e.deltaY < 0 ? 1.1 : 1/1.1))); this.redraw(); }
      else this.step(e.deltaY > 0 ? 1 : -1); }, {passive: false});
    cv.addEventListener("dblclick", () => { if (tool === "angle") return;
      if (views.length > 1) return toggleMax(this);
      this.zoom = 1; this.px = this.py = 0; this.redraw(); });
    cv.addEventListener("mouseleave", () => { this.probe = null; this.redraw(); });
  }
  addMeas(ms){ (MEAS[this.measKey()] ||= []).push(ms); this.redraw(); }
  setCursor(p){
    if (this.plane === "o") return;
    const a = this.ax, [W, H] = this.imageSize(), cu = cur.cursor;
    const x = Math.max(0, Math.min(W - 1, Math.floor(p[0]))), y = Math.max(0, Math.min(H - 1, Math.floor(p[1])));
    cu[a.h.a] = a.h.f ? W - 1 - x : x; cu[a.v.a] = a.v.f ? H - 1 - y : y; draw();
  }
  step(dlt, wrap){ const n = this.sliceCount(), clampW = v => wrap ? ((v % n) + n) % n : Math.max(0, Math.min(n - 1, v));
    if (this.pin){ this.pin.k = clampW(this.pin.k + dlt); this.key = ""; }   // quadro preso (mamografia)
    else if (this.plane === "o"){ this.obl.off = clampW(this.obl.off - this.obl.minOff + dlt) + this.obl.minOff; }
    else { const a = this.ax; cur.cursor[a.fix] = clampW(cur.cursor[a.fix] + dlt); }
    this.draft = null; prefetch(); draw(); }
  redraw(){ this.draw(); }
}
const PLANE_COL = ["#ff6b6b", "#5cd6ff", "#ffd24a"];
// reconstrução: para cada coluna/linha da tela, o deslocamento dentro do quadro (eixos i, j) ou o quadro (eixo k)
function reslice(S, a, fixIdx, W, H){
  const cols = S.meta.cols, F = S.frames, out = new Int16Array(W * H);
  const idxOf = (ax, n, flip) => { const r = new Int32Array(n); for (let t = 0; t < n; t++) r[t] = flip ? n - 1 - t : t; return r; };
  const hi = idxOf(a.h.a, W, a.h.f), vi = idxOf(a.v.a, H, a.v.f);
  const stride = ax => ax === 0 ? 1 : ax === 1 ? cols : 0;
  const fixOff = stride(a.fix) * fixIdx;
  if (a.v.a === 2){                       // vertical = quadros (coronal/sagital de aquisição axial)
    const hs = stride(a.h.a);
    const off = new Int32Array(W); for (let x = 0; x < W; x++) off[x] = fixOff + hi[x] * hs;
    for (let y = 0; y < H; y++){ const f = F[vi[y]], row = y * W; for (let x = 0; x < W; x++) out[row + x] = f[off[x]]; }
  } else if (a.h.a === 2){                // horizontal = quadros
    const vs = stride(a.v.a);
    for (let y = 0; y < H; y++){ const base = fixOff + vi[y] * vs, row = y * W;
      for (let x = 0; x < W; x++) out[row + x] = F[hi[x]][base]; }
  } else {                                // plano do próprio quadro (fixo = k)
    const f = F[fixIdx], hs = stride(a.h.a), vs = stride(a.v.a);
    for (let y = 0; y < H; y++){ const base = vi[y] * vs, row = y * W; for (let x = 0; x < W; x++) out[row + x] = f[base + hi[x] * hs]; }
  }
  return out;
}
const m2 = v => Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1);
const SLABN = {mip: "MIP", avg: "Média", minip: "MinIP"};
const OPP = {L: "R", R: "L", A: "P", P: "A", H: "F", F: "H", S: "I", I: "S"};
const oppL = s => String(s).split("").map(ch => OPP[ch] || ch).join("");
function allLoaded(S){ for (let q = 0; q < S.meta.n; q++) if (!S.frames[q]) return false; return true; }
function combine(get, k, n, half, mode){
  const lo = Math.max(0, k - half), hi = Math.min(n - 1, k + half);
  const first = get(lo), N = first.length;
  if (mode === "avg"){ const acc = new Float32Array(first);
    for (let kk = lo + 1; kk <= hi; kk++){ const a = get(kk); for (let i = 0; i < N; i++) acc[i] += a[i]; }
    const out = new Int16Array(N), c = hi - lo + 1; for (let i = 0; i < N; i++) out[i] = Math.round(acc[i] / c); return out; }
  const out = Int16Array.from(first), mx = mode === "mip";
  for (let kk = lo + 1; kk <= hi; kk++){ const a = get(kk);
    if (mx){ for (let i = 0; i < N; i++) if (a[i] > out[i]) out[i] = a[i]; }
    else { for (let i = 0; i < N; i++) if (a[i] < out[i]) out[i] = a[i]; } }
  return out;
}
// ---------------------------------------------------------------- MPR oblíquo
let OBL_ID = 0;
const vsub = (a, b) => a.map((v, i) => v - b[i]), vdot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
const vcross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const vnorm = a => { const l = Math.hypot(...a) || 1; return a.map(v => v / l); };
function patVec(m, v){ const V = axisVecs(m); if (!V[0]) return v; return [0,1,2].map(c => v[0]*V[0][c] + v[1]*V[1][c] + v[2]*V[2][c]); }
function imgToMM(view, p){
  const a = view.ax, [W, H] = view.imageSize(), sp = spacings(view.m), vox = [0,0,0];
  vox[a.h.a] = a.h.f ? W - 1 - (p[0] - .5) : p[0] - .5; vox[a.v.a] = a.v.f ? H - 1 - (p[1] - .5) : p[1] - .5;
  vox[a.fix] = view.fixIndex(); return vox.map((v, i) => v * sp[i]);
}
function mmToImg(view, P){
  const a = view.ax, [W, H] = view.imageSize(), sp = spacings(view.m), vox = P.map((v, i) => v / sp[i]);
  const x = a.h.f ? W - 1 - vox[a.h.a] : vox[a.h.a], y = a.v.f ? H - 1 - vox[a.v.a] : vox[a.v.a];
  return [x + .5, y + .5];
}
function obliqueSample(S, o, off){
  const m = S.meta, sp = spacings(m), [nx, ny, nz] = dims(m), F = S.frames, W = o.W, H = o.H;
  const out = new Int16Array(W * H).fill(-32768), s = o.ps;
  const b = [0,1,2].map(i => o.O[i] + off * s * o.m[i]);
  const du = o.u.map((v, i) => v * s / sp[i]), dw = o.w.map((v, i) => v * s / sp[i]), b0 = b.map((v, i) => v / sp[i]);
  for (let y = 0; y < H; y++){
    let fi = b0[0] + y * dw[0], fj = b0[1] + y * dw[1], fk = b0[2] + y * dw[2]; const row = y * W;
    for (let x = 0; x < W; x++, fi += du[0], fj += du[1], fk += du[2]){
      const i = Math.round(fi), j = Math.round(fj), k = Math.round(fk);
      if (i >= 0 && j >= 0 && k >= 0 && i < nx && j < ny && k < nz) out[row + x] = F[k][j * nx + i]; } }
  return out;
}
async function createOblique(src, pts){
  const S = cur, m = S.meta;
  if (src.plane === "o" || !m.mpr){ msg("O plano oblíquo precisa de uma série volumétrica (e de uma imagem que não seja oblíqua)."); setTimeout(() => msg(""), 3000); return; }
  if (!volumeOk(m)) return;
  try { await ensureAll(S); } catch (e){ msg("Falha ao carregar: " + e.message); return; }
  const a = src.ax, sp = spacings(m), dm = dims(m);
  const P1 = imgToMM(src, pts[0]), P2 = imgToMM(src, pts[1]);
  let u = vnorm(vsub(P2, P1)), w = [0,0,0]; w[a.fix] = 1;
  const pn = patVec(m, vcross(u, w)), dd = [0,1,2].reduce((b, i) => Math.abs(pn[i]) > Math.abs(pn[b]) ? i : b, 0);
  const R = dd === 0 ? [0,1,0] : [1,0,0], D = dd === 2 ? [0,1,0] : [0,0,-1];
  if (vdot(patVec(m, u), R) < 0) u = u.map(v => -v);
  if (vdot(patVec(m, w), D) < 0) w = w.map(v => -v);
  const mv = vcross(u, w), ps = Math.min(...sp);
  const cs = []; for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1])
    cs.push([i * (dm[0] - 1) * sp[0], j * (dm[1] - 1) * sp[1], k * (dm[2] - 1) * sp[2]]);
  const pr = v => cs.map(c => vdot(vsub(c, P1), v)), U = pr(u), Wp = pr(w), M = pr(mv);
  const minU = Math.min(...U), minW = Math.min(...Wp);
  const O = [0,1,2].map(i => P1[i] + minU * u[i] + minW * w[i]);
  const o = {id: ++OBL_ID, O, u, w, m: mv, ps, P1, P2,
    W: Math.min(2048, Math.ceil((Math.max(...U) - minU) / ps) + 1), H: Math.min(2048, Math.ceil((Math.max(...Wp) - minW) / ps) + 1),
    off: 0, minOff: Math.floor(Math.min(...M) / ps), maxOff: Math.ceil(Math.max(...M) / ps),
    hv: patVec(m, u), vv: patVec(m, w)};
  let nv;
  if (layout === 3){
    const idx = views.indexOf(src) === 2 ? 1 : 2, old = views[idx], el = old.el;
    el.innerHTML = '<canvas></canvas><button class="mx" title="Ampliar / voltar (duplo clique, F)">⤢</button>';
    nv = new View(el, "o"); views[idx] = nv; el.querySelector(".mx").onclick = e => { e.stopPropagation(); toggleMax(nv); };
    o.src = src;
  } else {
    const plane = src.plane, z = [src.zoom, src.px, src.py];
    layout = 2; makeViews([plane, "o"], "l2"); nv = views[1];
    [views[0].zoom, views[0].px, views[0].py] = z; o.src = views[0];
  }
  o.srcKey = o.src.measKey(); nv.obl = o; setActive(nv); setTool("wl"); draw();
}
const LUTS = {};
function getLut(m, w){
  const key = [m.id, w.w, w.l, w.inv].join("|"); if (LUTS.key === key) return LUTS.lut;
  const lut = LUTS.lut || new Uint8Array(65536), lo = w.l - w.w / 2, inv = w.inv !== !!m.invert;
  for (let r = -32768; r < 32768; r++){ let g = (r * m.scale + m.offset - lo) / w.w * 255;
    g = g < 0 ? 0 : g > 255 ? 255 : g; lut[r + 32768] = inv ? 255 - g : g; }
  LUTS.key = key; LUTS.lut = lut; return lut;
}

// ------------------------------------------------------------------ interface
function setActive(v){ active = v; views.forEach(x => x.el.classList.toggle("act", x === v && views.length > 1));
  if (v && $("slab")){ $("slab").value = String(v.slab.mm); $("slabmode").value = v.slab.mode; } }
let rq = 0;
let imgFilter = 0;                     // 0 = sem filtro, 1 = nitidez, 2 = suavizar
function blur3(a, W, H){
  const t = new Float32Array(a.length), o = new Uint8ClampedArray(a.length);
  for (let y = 0; y < H; y++){
    const r = y * W;
    for (let x = 0; x < W; x++){
      const l = a[r + (x > 0 ? x - 1 : 0)], c = a[r + x], d2 = a[r + (x < W - 1 ? x + 1 : W - 1)];
      t[r + x] = (l + 2 * c + d2) / 4;
    }
  }
  for (let y = 0; y < H; y++){
    const up = (y > 0 ? y - 1 : 0) * W, dn = (y < H - 1 ? y + 1 : H - 1) * W, r = y * W;
    for (let x = 0; x < W; x++) o[r + x] = (t[up + x] + 2 * t[r + x] + t[dn + x]) / 4;
  }
  return o;
}
function applyFilter(gray, W, H, mode){
  if (mode === 2) return blur3(blur3(gray, W, H), W, H);
  const b = blur3(gray, W, H), o = new Uint8ClampedArray(gray.length);
  for (let i = 0; i < gray.length; i++) o[i] = gray[i] + 1.0 * (gray[i] - b[i]);
  return o;
}
function setFilter(n){
  imgFilter = ((n % 3) + 3) % 3;
  const b = document.getElementById("filt");
  if (b){ b.classList.toggle("on", imgFilter > 0);
    b.textContent = imgFilter === 1 ? "Nitidez" : imgFilter === 2 ? "Suavizado" : "Filtro"; }
  views.forEach(v => { v.key = null; });
  draw();
}
function draw(){ if (rq) return; rq = requestAnimationFrame(() => { rq = 0; views.forEach(v => v.draw()); }); }
function makeViews(planes, cls){
  const box = $("views"); box.innerHTML = ""; views.length = 0;
  box.className = cls || (planes.length > 1 ? "l3" : "l1");
  planes.forEach((pl, i) => { const el = document.createElement("div"); el.className = "vp" + (box.className === "l3" && i === 0 ? " l3a" : "");
    el.innerHTML = '<canvas></canvas><button class="mx" title="Ampliar / voltar (duplo clique, F)">⤢</button>';
    box.appendChild(el); const v = new View(el, pl); views.push(v);
    el.querySelector(".mx").onclick = e => { e.stopPropagation(); toggleMax(v); }; });
  setActive(views[0]);
}
function toggleMax(v){
  const box = $("views"); if (views.length < 2) return;
  const on = !(box.classList.contains("maxed") && v.el.classList.contains("max"));
  views.forEach(x => { x.el.classList.toggle("max", on && x === v); x.el.querySelector(".mx").textContent = on && x === v ? "⤡" : "⤢"; });
  box.classList.toggle("maxed", on); setActive(v); draw();
}
function prefetch(){
  if (!cur || cur.meta.color) return; const k = cur.cursor[2], ci = chunkOf(cur.meta, k);
  for (const c of [ci, ci + 1, ci - 1, ci + 2, ci - 2]) if (c >= 0 && c < cur.meta.chunks.length) loadChunk(cur, c).catch(() => {});
}
async function openSeries(st, meta, row){
  stopCine();
  document.querySelectorAll(".ser.on").forEach(x => x.classList.remove("on")); row.classList.add("on");
  const S = SER[meta.id] ||= {meta, frames: [], chunks: {}, imgs: [], imgP: []};
  S.study = st; S.cursor = S.cursor || [Math.floor(meta.cols / 2), Math.floor(meta.rows / 2), Math.floor(meta.n / 2)];
  WIN[meta.id] ||= {w: meta.window ? meta.window[0] : 255, l: meta.window ? meta.window[1] : 128, inv: false};
  cur = S; $("l3").disabled = !meta.mpr;
  document.querySelectorAll("[data-plane]").forEach(b => { const pl = planeFor(meta, b.dataset.plane);
    b.disabled = meta.color || !pl || (pl !== "n" && !meta.mpr); }); $("preset").value = ""; $("inv").classList.toggle("on", WIN[meta.id].inv);
  $("preset").disabled = !!meta.color;
  $("slab").disabled = $("slabmode").disabled = !meta.mpr;
  document.querySelector('[data-tool=oblique]').disabled = !meta.mpr;
  const temMg = studyHasMg();
  $("mg").disabled = !temMg;
  $("mgq").disabled = $("mgw").disabled = !temMg;
  $("mgq").classList.remove("on");
  setLayout(1);
}
function markLayout(id){
  ["pn", "l3", "mg"].forEach(x => $(x).classList.toggle("on", x === id));
  document.querySelectorAll("[data-plane]").forEach(b => b.classList.toggle("on", b.dataset.plane === id));
}
function volumeOk(m){
  if (!m.mpr) return false;
  if (m.rows * m.cols * m.n * 2 > 1.6e9){ msg("Série grande demais para reconstruir no navegador."); setTimeout(() => msg(""), 3000); return false; }
  return true;
}
async function setLayout(n, kind){
  if (!cur) return;
  stopCine();
  if (n === 3){
    const m = cur.meta; if (!volumeOk(m)) return;
    layout = 3; markLayout("l3");
    makeViews(["n", "r", "c"]); draw();
    try { await ensureAll(cur); } catch (e){ msg("Falha ao carregar: " + e.message); return; }
    draw(); return;
  }
  layout = 1;
  const m = cur.meta, pl = kind ? planeFor(m, kind) : "n";
  if (!pl) return;
  if (pl !== "n" && !volumeOk(m)) return;
  markLayout(pl === "n" ? (kind && kind === planeKind(m, "n") ? kind : "pn") : kind);
  makeViews([pl]); prefetch(); draw();
  if (pl !== "n"){ try { await ensureAll(cur); } catch (e){ msg("Falha ao carregar: " + e.message); return; } draw(); }
}
// ------------------------------------------------------------------ mamografia
const MG_ORDER = [["R", "CC"], ["L", "CC"], ["R", "MLO"], ["L", "MLO"]];
function mgFrames(){
  const st = cur && cur.study, out = [];
  if (!st) return out;
  (st.series || []).forEach(meta => (meta.mg || []).forEach((info, k) => out.push({meta, k, info})));
  return out;
}
function studyHasMg(){ return mgFrames().length > 0; }
function seriesState(meta){
  const S = SER[meta.id] ||= {meta, frames: [], chunks: {}, imgs: [], imgP: []};
  S.study = S.study || (cur && cur.study);
  S.cursor = S.cursor || [Math.floor(meta.cols / 2), Math.floor(meta.rows / 2), Math.floor(meta.n / 2)];
  WIN[meta.id] ||= {w: meta.window ? meta.window[0] : 255, l: meta.window ? meta.window[1] : 128, inv: false};
  return S;
}
function mgWindow(){          // janela só no tecido, para cada série mostrada
  const vistas = views.filter(v => v.pin);
  (vistas.length ? vistas : views).forEach(v => { const i = v.mgInfo();
    if (i && i.tissue){ const w = WIN[v.m.id]; w.w = i.tissue[0]; w.l = i.tissue[1]; } });
  views.forEach(v => { v.key = ""; });
  draw();
}
function mgLayout(){
  const lista = mgFrames();
  if (!lista.length){ msg("Este exame não tem mamografia com lado e incidência."); setTimeout(() => msg(""), 3500); return; }
  const achar = (s, v) => lista.find(x => x.info.side === s && String(x.info.view || "").startsWith(v));
  let celulas = MG_ORDER.map(([s, v]) => achar(s, v)).filter(Boolean);
  if (celulas.length < 2) celulas = lista.slice(0, 4);
  celulas = celulas.slice(0, 4);
  stopCine();
  layout = 1; markLayout("mg");
  makeViews(celulas.map(() => "n"), celulas.length > 2 ? "mg4" : "mg2");
  const cols = celulas.length > 2 ? 2 : celulas.length;
  celulas.forEach((c, i) => {
    const v = views[i];
    v.pin = {S: seriesState(c.meta), k: c.k};
    const naEsquerda = (i % cols) === 0 && cols > 1;
    const querParede = naEsquerda ? "right" : "left";       // parede torácica voltada para o centro
    v.alignEdge = cols > 1 ? querParede : null;
    v.mirror = !!(c.info.chest && c.info.chest !== querParede);
    v.quad = -1; v.zoom = 1; v.px = v.py = 0; v.key = "";
  });
  mgWindow();
  setActive(views[0]);
  draw();
}
function mgQuadCycle(){
  const alvos = views.filter(v => v.mgInfo());
  if (!alvos.length){ msg("O zoom por quadrante é da mamografia (use o botão Mamografia)."); setTimeout(() => msg(""), 3500); return; }
  const atual = alvos[0].quad;
  const novo = atual >= 1 ? -1 : atual + 1;
  alvos.forEach(v => v.quadZoom(novo));
  $("mgq").classList.toggle("on", novo >= 0);
}
function stopCine(){ if (cineT){ clearInterval(cineT); cineT = null; $("cine").textContent = "▶ Cine"; } }
function build(){
  if (!window.DecompressionStream){ msg("Este navegador é antigo. Use Chrome, Edge, Firefox ou Safari atualizados."); return; }
  const list = $("list"); let first = null;
  DATA.studies.forEach((st, si) => {
    const d = document.createElement("div"); d.className = "study"; d.innerHTML = "<b></b><small></small>";
    d.querySelector("b").textContent = st.label || ("Exame " + (si + 1)); d.querySelector("small").textContent = st.sub || "";
    st.series.forEach(meta => { const r = document.createElement("div"); r.className = "ser";
      const im = document.createElement("img"); im.loading = "lazy"; if (meta.thumb) im.src = meta.thumb;
      const t = document.createElement("span"); t.textContent = meta.label;
      const em = document.createElement("em");
      em.textContent = `${meta.n} im` + (meta.mpr ? " · MPR" : "") + ((meta.annotations || []).length ? ` · ${meta.annotations.length} medida(s)` : "")
        + ((meta.keys || []).length ? ` · ★${meta.keys.length}` : "");
      t.appendChild(em); r.append(im, t); r.onclick = () => openSeries(st, meta, r); d.appendChild(r);
      if (!first) first = () => openSeries(st, meta, r); });
    list.appendChild(d); });
  const ps = $("preset"); ps.innerHTML = '<option value="">Janelas…</option><option value="0">0 · Do arquivo</option>' +
    PRESETS.map((p, i) => `<option value="${i+1}">${i+1} · ${p[0]} (${p[1]}/${p[2]})</option>`).join("");
  if (first) first();
}
function preset(v){ if (!cur || cur.meta.color) return; const w = WIN[cur.meta.id], m = cur.meta;
  if (v === "0"){ w.w = m.window[0]; w.l = m.window[1]; } else { const p = PRESETS[+v - 1]; if (!p) return; w.w = p[1]; w.l = p[2]; }
  $("preset").value = v; draw(); }
document.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
function setTool(t){ tool = t; views.forEach(v => v.draft = null);
  document.querySelectorAll("[data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === t)); draw(); }
$("preset").onchange = e => preset(e.target.value);
function applySlab(){ if (!active || !cur) return;
  active.slab = {mm: +$("slab").value, mode: $("slabmode").value}; draw(); }
$("slab").onchange = applySlab; $("slabmode").onchange = applySlab;
$("inv").onclick = () => { if (!cur) return; const w = WIN[cur.meta.id]; w.inv = !w.inv; $("inv").classList.toggle("on", w.inv); draw(); };
$("reset").onclick = () => { views.forEach(v => { v.zoom = 1; v.px = v.py = 0; v.quad = -1; }); if (cur) preset("0");
  $("mgq").classList.remove("on"); draw(); };
$("clear").onclick = () => { if (active && cur){ delete MEAS[active.measKey()]; draw(); } };
$("ann").onclick = () => { showAnn = !showAnn; $("ann").classList.toggle("on", showAnn); draw(); };
$("filt").onclick = () => setFilter(imgFilter + 1);
$("pn").onclick = () => setLayout(1); $("l3").onclick = () => setLayout(3);
$("mg").onclick = () => mgLayout(); $("mgq").onclick = () => mgQuadCycle(); $("mgw").onclick = () => mgWindow();
document.querySelectorAll("[data-plane]").forEach(b => b.onclick = () => setLayout(1, b.dataset.plane));
$("hbtn").onclick = () => { const h = $("help"); h.style.display = h.style.display === "block" ? "none" : "block"; };
$("cine").onclick = () => { if (cineT) return stopCine(); if (!active) return; $("cine").textContent = "■ Cine";
  cineT = setInterval(() => active.step(1, true), 80); };
window.addEventListener("resize", draw);
window.addEventListener("keydown", e => {
  if (!active || !cur || e.target.tagName === "SELECT") return;
  const k = e.key;
  if (["ArrowDown","ArrowRight"].includes(k)) active.step(1);
  else if (["ArrowUp","ArrowLeft"].includes(k)) active.step(-1);
  else if (k === "PageDown") active.step(10); else if (k === "PageUp") active.step(-10);
  else if (k === "Home") active.step(-1e6); else if (k === "End") active.step(1e6);
  else if (k === " ") $("cine").click();
  else if (k >= "0" && k <= "6") preset(k);
  else if (k === "q" || k === "Q"){ if (!$("mgq").disabled) mgQuadCycle(); }
  else if (k === "s" || k === "S") setFilter(imgFilter + 1);
  else if (k === "Escape"){ views.forEach(v => v.draft = null); draw(); }
  else if (k === "Delete" || k === "Backspace"){ const l = MEAS[active.measKey()]; if (l && l.length){ l.pop(); draw(); } }
  else { const t = {w:"wl", p:"pan", z:"zoom", m:"line", a:"angle", e:"ellipse", r:"rect", v:"probe", o:"oblique"}[k.toLowerCase()];
    if (t) setTool(t); else if (k.toLowerCase() === "i") $("inv").click();
    else if (k.toLowerCase() === "f") toggleMax(active); else return; }
  e.preventDefault();
});
build();
</script></body></html>
"""


def _traduz(html: str) -> str:
    """Traduz os textos do visualizador exportado para o idioma em uso (o mesmo catálogo do programa).

    Troca só o que tem tradução, e apenas nos lugares em que o texto aparece: title="…", o texto entre
    marcas e as frases do script — assim nada de código é tocado.
    """
    from ipe.core import i18n
    if i18n.is_base():
        return html
    import re

    def t(v: str) -> str:
        return i18n.tr(v)

    def attr(m):
        novo = t(m.group(1))
        return m.group(0) if novo == m.group(1) else f'title="{novo}"'

    def entre(m):
        novo = t(m.group(1))
        return m.group(0) if novo == m.group(1) else f">{novo}<"

    def js(m):
        novo = t(m.group(1))
        return m.group(0) if novo == m.group(1) else f'"{novo}"'

    html = re.sub(r'title="([^"]{3,400})"', attr, html)
    html = re.sub(r">([^<>{}]{3,400})<", entre, html)
    return re.sub(r'"([^"\\\n]{3,400})"', js, html)


def page(data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _traduz(TEMPLATE).replace("__DATA__", blob)
