"""Página HTML única do visualizador simples que vai junto com a exportação (funciona offline)."""

from __future__ import annotations

import json

TEMPLATE = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Visualizador — Ipê</title>
<style>
:root{--bg:#141517;--panel:#1d1f23;--line:#33363d;--fg:#e6e8eb;--dim:#9aa0a8;--acc:#4fb3ff}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
font:14px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
#app{display:flex;height:100%}
#side{width:250px;min-width:250px;background:var(--panel);border-right:1px solid var(--line);overflow:auto}
#side h1{font-size:13px;margin:0;padding:10px 12px;color:var(--dim);font-weight:600;letter-spacing:.3px}
.study{padding:8px 12px 4px;border-top:1px solid var(--line)}
.study b{display:block;font-size:14px}.study small{color:var(--dim)}
.ser{display:flex;gap:8px;align-items:center;margin:6px 0;padding:4px;border-radius:6px;cursor:pointer}
.ser:hover{background:#2a2d33}.ser.on{background:#27405e}
.ser img{width:56px;height:56px;object-fit:contain;background:#000;border-radius:4px}
.ser span{font-size:12px}.ser em{display:block;color:var(--dim);font-style:normal}
#main{flex:1;position:relative;overflow:hidden;background:#000;cursor:crosshair;user-select:none}
#img{position:absolute;left:50%;top:50%;transform-origin:center;max-width:none;image-rendering:auto}
.ov{position:absolute;color:#eee;text-shadow:0 0 3px #000,0 0 2px #000;font-size:13px;pointer-events:none;white-space:pre}
#tl{left:10px;top:8px}#tr{right:10px;top:8px;text-align:right}#bl{left:10px;bottom:36px}#br{right:10px;bottom:36px;text-align:right}
#bar{position:absolute;left:0;right:0;bottom:0;height:30px;display:flex;align-items:center;gap:8px;padding:0 10px;
background:rgba(20,21,23,.85);border-top:1px solid var(--line)}
#bar input[type=range]{flex:1}button{background:#2c2f35;color:var(--fg);border:1px solid #454952;border-radius:4px;
padding:3px 10px;cursor:pointer;font:inherit;font-size:12px}button:hover{background:#383c44}
#help{color:var(--dim);font-size:11px}#disc{position:absolute;right:10px;top:50%;transform:rotate(90deg) translateX(50%);
transform-origin:right top;color:#666;font-size:10px}
@media (max-width:700px){#side{width:150px;min-width:150px}.ser img{width:40px;height:40px}#help{display:none}}
</style></head><body><div id="app">
<div id="side"><h1>EXAMES</h1><div id="list"></div></div>
<div id="main"><img id="img" alt="">
<div class="ov" id="tl"></div><div class="ov" id="tr"></div><div class="ov" id="bl"></div><div class="ov" id="br"></div>
<div id="disc">Não destinado a uso diagnóstico</div>
<div id="bar"><button id="play" title="Cine (espaço)">▶</button><input id="pos" type="range" min="0" value="0">
<button id="reset" title="Restaurar (duplo clique)">Restaurar</button>
<span id="help">rodinha/setas: imagens · arrastar: brilho/contraste · Ctrl+rodinha: zoom · botão direito arrastar: mover</span></div>
</div></div>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
let cur = null, idx = 0, br = 1, ct = 1, zoom = 1, px = 0, py = 0, timer = null;
const cache = {};
function src(s, k){ return s.dir + "/" + s.files[k]; }
function build(){
  const list = $("list"); let first = null;
  DATA.studies.forEach((st, si) => {
    const d = document.createElement("div"); d.className = "study";
    d.innerHTML = "<b></b><small></small>";
    d.querySelector("b").textContent = st.label || ("Exame " + (si + 1));
    d.querySelector("small").textContent = st.sub || "";
    st.series.forEach(s => {
      const r = document.createElement("div"); r.className = "ser";
      const im = document.createElement("img"); im.loading = "lazy"; im.src = src(s, Math.floor(s.files.length / 2));
      const t = document.createElement("span"); t.textContent = s.label;
      const em = document.createElement("em"); em.textContent = s.files.length + " im"; t.appendChild(em);
      r.append(im, t); r.onclick = () => open(st, s, r); d.appendChild(r);
      if (!first) first = () => open(st, s, r);
    });
    list.appendChild(d);
  });
  if (first) first();
}
function open(st, s, row){
  document.querySelectorAll(".ser.on").forEach(x => x.classList.remove("on")); row.classList.add("on");
  cur = {st, s}; idx = Math.floor(s.files.length / 2); $("pos").max = s.files.length - 1; stop(); reset(false); show();
}
function show(){
  if (!cur) return; const s = cur.s; idx = Math.max(0, Math.min(s.files.length - 1, idx));
  $("img").src = src(s, idx); $("pos").value = idx;
  for (const k of [idx + 1, idx + 2, idx - 1]) if (k >= 0 && k < s.files.length && !cache[src(s, k)]) {
    const i = new Image(); i.src = src(s, k); cache[src(s, k)] = i; }
  $("tl").textContent = (cur.st.label || "") + "\n" + (cur.st.sub || "");
  $("tr").textContent = s.label; $("bl").textContent = "Im " + (idx + 1) + "/" + s.files.length;
  $("br").textContent = (zoom !== 1 ? "Zoom " + Math.round(zoom * 100) + "%\n" : "") +
    ((br !== 1 || ct !== 1) ? "Brilho " + Math.round(br * 100) + "%  Contraste " + Math.round(ct * 100) + "%" : "");
}
function fit(){
  const im = $("img"), m = $("main"); if (!im.naturalWidth) return;
  const k = Math.min(m.clientWidth / im.naturalWidth, (m.clientHeight - 30) / im.naturalHeight) * zoom;
  im.style.width = (im.naturalWidth * k) + "px"; im.style.height = (im.naturalHeight * k) + "px";
  im.style.transform = `translate(calc(-50% + ${px}px), calc(-50% - 15px + ${py}px))`;
  im.style.filter = `brightness(${br}) contrast(${ct})`;
}
function reset(redraw = true){ br = 1; ct = 1; zoom = 1; px = 0; py = 0; if (redraw){ fit(); show(); } }
function step(d){ idx += d; show(); }
function stop(){ if (timer){ clearInterval(timer); timer = null; $("play").textContent = "▶"; } }
$("img").onload = fit; window.onresize = fit;
$("main").addEventListener("wheel", e => { e.preventDefault();
  if (e.ctrlKey){ zoom = Math.max(.2, Math.min(10, zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); fit(); show(); }
  else step(e.deltaY > 0 ? 1 : -1); }, {passive: false});
let drag = null;
$("main").addEventListener("mousedown", e => { drag = {x: e.clientX, y: e.clientY, b: e.button, br, ct, px, py}; e.preventDefault(); });
window.addEventListener("mousemove", e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (drag.b === 2 || drag.b === 1){ px = drag.px + dx; py = drag.py + dy; }
  else { ct = Math.max(.1, drag.ct * Math.exp(dx / 250)); br = Math.max(.1, drag.br * Math.exp(-dy / 250)); }
  fit(); show(); });
window.addEventListener("mouseup", () => drag = null);
$("main").addEventListener("contextmenu", e => e.preventDefault());
$("main").addEventListener("dblclick", () => reset());
$("pos").oninput = e => { idx = +e.target.value; show(); };
$("reset").onclick = () => reset();
$("play").onclick = () => { if (timer) return stop(); $("play").textContent = "■";
  timer = setInterval(() => { idx = (idx + 1) % cur.s.files.length; show(); }, 80); };
window.addEventListener("keydown", e => {
  if (["ArrowDown","ArrowRight","PageDown"].includes(e.key)) { step(e.key === "PageDown" ? 10 : 1); e.preventDefault(); }
  if (["ArrowUp","ArrowLeft","PageUp"].includes(e.key)) { step(e.key === "PageUp" ? -10 : -1); e.preventDefault(); }
  if (e.key === "Home"){ idx = 0; show(); } if (e.key === "End"){ idx = 1e9; show(); }
  if (e.key === " "){ $("play").click(); e.preventDefault(); } });
build();
</script></body></html>
"""


def page(data: dict) -> str:
    # "</" não pode aparecer cru dentro do <script>
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", blob)
