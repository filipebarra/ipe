// 0.100.72: esquemas-guia do laudo no navegador — um desenho de base (face, corpo, tireoide, mamas, próstata…) em
// que o médico marca os achados: ponto numerado, elipse, seta, traço livre e texto; na próstata, o clique no setor
// pinta com a categoria. Os dados são os mesmos do Ipê de mesa (pontos de 0 a 1 sobre o modelo), guardados por
// exame no servidor. A figura que vai para o PDF, para o DICOM e para o SR é desenhada pelo servidor; aqui o canvas
// desenha igual para a tela. Funciona com mouse, dedo e caneta.
import { pedir } from "./api";
import { tr } from "./i18n";
import { botao, confirmar, el } from "./impressoes";

export type TipoMarca = "ponto" | "elipse" | "traco" | "seta" | "texto";
export interface ImagemLigada { series_uid: string; sop_uid: string; frame: number; rotulo: string }
export interface Marca { tipo: TipoMarca; n: number; p: number[][]; cor: string; l: number; texto: string; imagem?: ImagemLigada }
export interface Esquema { id: string; modelo: string; titulo: string; marcas: Marca[]; setores: Record<string, string> }
interface Traco { p: number[][]; l: number; c: string }
interface Setor { id: string; nome: string; curto: string; p: number[][]; cx: number; cy: number }
export interface Modelo {
  id: string; nome: string; grupo: string; w: number; h: number; meu?: boolean; tracos: Traco[];
  rotulos: { x: number; y: number; t: string; s: number; c: string }[]; setores: Setor[];
  categorias: { k: string; nome: string; cor: string }[];
}
interface DoExame { esquemas: Esquema[]; pode: boolean; legenda: string }

const TINTA: Record<string, string> = { forte: "#282828", leve: "#969696" };
const FERRAMENTAS: [string, string, string][] = [
  ["mover", "Mover", "Arraste uma marca para mudar de lugar; um toque escolhe a marca na lista"],
  ["ponto", "Ponto", "Um toque marca um ponto numerado"],
  ["elipse", "Elipse", "Arraste para desenhar uma elipse"],
  ["seta", "Seta", "Arraste do começo até a ponta da seta"],
  ["traco", "Traço livre", "Desenhe à mão livre"],
  ["texto", "Texto", "Um toque põe um texto na figura"],
  ["setor", "Setor", "Um toque pinta o setor com a categoria escolhida; outro toque limpa"],
  ["apagar", "Apagar", "Um toque numa marca apaga"],
];

const url = (c: string): string => `${location.origin}/api/web/esquemas/${c}`;

async function json<T>(c: string, corpo?: unknown): Promise<T> {
  const r = await pedir(url(c), {
    method: corpo === undefined ? "GET" : "POST",
    headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    cache: "no-store",
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = ((await r.json()) as { error?: string }).error || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

let modelosProntos: Promise<{ modelos: Modelo[]; cores: string[] }> | null = null;
const fundos = new Map<string, HTMLImageElement>();

export function modelos(): Promise<{ modelos: Modelo[]; cores: string[] }> {
  if (!modelosProntos) {
    modelosProntos = json<{ modelos: Modelo[]; cores: string[] }>("modelos");
    modelosProntos.catch(() => { modelosProntos = null; });
  }
  return modelosProntos;
}

/** A imagem de fundo de um modelo próprio (os do Ipê são só traços). */
async function fundoDe(m: Modelo): Promise<HTMLImageElement | null> {
  if (!m.meu) return null;
  const tem = fundos.get(m.id);
  if (tem) return tem;
  try {
    const r = await pedir(url(`fundo?id=${encodeURIComponent(m.id)}`), {});
    if (!r.ok) return null;
    const img = new Image();
    img.src = URL.createObjectURL(await r.blob());
    await img.decode();
    fundos.set(m.id, img);
    return img;
  } catch {
    return null;
  }
}

export const esquemasDoExame = (study: string): Promise<DoExame> => json<DoExame>(`exame?study=${encodeURIComponent(study)}`);
const gravarEsquemas = (study: string, esquemas: Esquema[]): Promise<{ esquemas: Esquema[]; legenda: string }> =>
  json("exame", { study, esquemas });

// ---------------------------------------------------------------------- desenho
function marcaNoCanvas(c: CanvasRenderingContext2D, m: Marca, W: number, H: number, base: number, escolhida: boolean): void {
  const pts = m.p.map(([x, y]) => [x * W, y * H]);
  if (!pts.length) return;
  const larg = Math.max(2, m.l * base);
  c.lineJoin = "round";
  c.lineCap = "round";
  c.strokeStyle = m.cor;
  c.fillStyle = m.cor;
  c.lineWidth = larg;
  let onde = pts[0];
  const numero = (x: number, y: number, r: number, f: number) => {
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fillStyle = m.cor;
    c.fill();
    c.lineWidth = Math.max(1, 2 * base);
    c.strokeStyle = "#fff";
    c.stroke();
    if (m.n) {
      c.fillStyle = "#fff";
      c.font = `${Math.round(f)}px sans-serif`;
      c.textAlign = "center";
      c.textBaseline = "middle";
      c.fillText(String(m.n), x, y + 0.5);
    }
  };
  if (m.tipo === "ponto") {
    numero(pts[0][0], pts[0][1], 15 * base, 18 * base);
  } else if (m.tipo === "texto") {
    c.font = `${Math.round(20 * base)}px sans-serif`;
    c.textAlign = "left";
    c.textBaseline = "middle";
    const w = c.measureText(m.texto).width;
    c.fillStyle = "rgba(255,255,255,.84)";
    c.fillRect(pts[0][0] - 4 * base, pts[0][1] - 14 * base, w + 8 * base, 28 * base);
    c.fillStyle = m.cor;
    c.fillText(m.texto, pts[0][0], pts[0][1]);
  } else {
    if (m.tipo === "elipse" && pts.length >= 2) {
      const cx = (pts[0][0] + pts[1][0]) / 2, cy = (pts[0][1] + pts[1][1]) / 2;
      const rx = Math.max(1, Math.abs(pts[1][0] - pts[0][0]) / 2), ry = Math.max(1, Math.abs(pts[1][1] - pts[0][1]) / 2);
      c.beginPath();
      c.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      c.globalAlpha = 0.18;
      c.fill();
      c.globalAlpha = 1;
      c.stroke();
      onde = [Math.max(pts[0][0], pts[1][0]), Math.min(pts[0][1], pts[1][1])];
    } else if (m.tipo === "seta" && pts.length >= 2) {
      const [a, b] = pts;
      c.beginPath();
      c.moveTo(a[0], a[1]);
      c.lineTo(b[0], b[1]);
      c.stroke();
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
      const t = 16 * base + larg * 1.5;
      c.beginPath();
      c.moveTo(b[0], b[1]);
      c.lineTo(b[0] - t * Math.cos(ang - 0.42), b[1] - t * Math.sin(ang - 0.42));
      c.lineTo(b[0] - t * Math.cos(ang + 0.42), b[1] - t * Math.sin(ang + 0.42));
      c.closePath();
      c.fill();
    } else {
      c.beginPath();
      pts.forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y)));
      c.stroke();
    }
    if (m.n) numero(onde[0], onde[1], 12 * base, 15 * base);
  }
  if (escolhida) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const f = 22 * base;
    c.setLineDash([6 * base, 5 * base]);
    c.lineWidth = Math.max(1, 1.5 * base);
    c.strokeStyle = "#0b63ce";
    c.strokeRect(Math.min(...xs) - f, Math.min(...ys) - f, Math.max(...xs) - Math.min(...xs) + 2 * f, Math.max(...ys) - Math.min(...ys) + 2 * f);
    c.setLineDash([]);
  }
}

/** Desenha o esquema inteiro num canvas (o tamanho do canvas manda). */
export function desenhar(cv: HTMLCanvasElement, mod: Modelo, e: Esquema | null, fundo: HTMLImageElement | null = null, escolhida = -1): void {
  const c = cv.getContext("2d");
  if (!c) return;
  const W = cv.width, H = cv.height, esc = W / mod.w;
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.fillStyle = "#fff";
  c.fillRect(0, 0, W, H);
  if (fundo) c.drawImage(fundo, 0, 0, W, H);
  const cores = new Map(mod.categorias.map((k) => [k.k, k.cor]));
  const pintados = e?.setores || {};
  for (const s of mod.setores) {
    const cor = cores.get(pintados[s.id] || "");
    if (!cor) continue;
    c.beginPath();
    s.p.forEach(([x, y], i) => (i ? c.lineTo(x * esc, y * esc) : c.moveTo(x * esc, y * esc)));
    c.closePath();
    c.globalAlpha = 0.8;
    c.fillStyle = cor;
    c.fill();
    c.globalAlpha = 1;
  }
  c.lineJoin = "round";
  c.lineCap = "round";
  for (const t of mod.tracos) {
    c.beginPath();
    t.p.forEach(([x, y], i) => (i ? c.lineTo(x * esc, y * esc) : c.moveTo(x * esc, y * esc)));
    c.strokeStyle = TINTA[t.c] || TINTA.forte;
    c.lineWidth = Math.max(1, t.l * esc);
    c.stroke();
  }
  c.textAlign = "center";
  c.textBaseline = "middle";
  for (const s of mod.setores) {
    const cat = pintados[s.id];
    if (s.curto) {
      c.fillStyle = "#5a5a5a";
      c.font = `${Math.max(7, Math.round(15 * esc))}px sans-serif`;
      c.fillText(s.curto, s.cx * esc, s.cy * esc - (cat ? 9 * esc : 0));
    }
    if (cat && cores.has(cat)) {
      c.fillStyle = "#000";
      c.font = `${Math.max(9, Math.round(24 * esc))}px sans-serif`;
      c.fillText(cat, s.cx * esc, s.cy * esc + 10 * esc);
    }
  }
  for (const r of mod.rotulos) {
    c.fillStyle = TINTA[r.c] || TINTA.leve;
    c.font = `${Math.max(7, Math.round(r.s * esc))}px sans-serif`;
    c.fillText(r.t, r.x * esc, r.y * esc);
  }
  const base = W / 1000;
  (e?.marcas || []).forEach((m, i) => marcaNoCanvas(c, m, W, H, base, i === escolhida));
}

function dentro(p: number[][], x: number, y: number): boolean {
  let d = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    if ((p[i][1] > y) !== (p[j][1] > y) && x < ((p[j][0] - p[i][0]) * (y - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]) d = !d;
  }
  return d;
}

function distSegmento(px: number, py: number, a: number[], b: number[]): number {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = dx || dy ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(px - a[0] - t * dx, py - a[1] - t * dy);
}

/** A marca debaixo do ponto (em pixels do canvas), a de cima primeiro; -1 se nenhuma. */
function marcaEm(e: Esquema, x: number, y: number, W: number, H: number): number {
  const tol = Math.max(14, W * 0.022);
  for (let i = e.marcas.length - 1; i >= 0; i--) {
    const m = e.marcas[i];
    const pts = m.p.map(([a, b]) => [a * W, b * H]);
    if (m.tipo === "ponto" && Math.hypot(x - pts[0][0], y - pts[0][1]) <= tol + W * 0.012) return i;
    if (m.tipo === "texto" && x >= pts[0][0] - tol && x <= pts[0][0] + Math.max(60, m.texto.length * W * 0.011) && Math.abs(y - pts[0][1]) <= tol) return i;
    if (m.tipo === "elipse" && pts.length >= 2) {
      if (x >= Math.min(pts[0][0], pts[1][0]) - tol && x <= Math.max(pts[0][0], pts[1][0]) + tol
        && y >= Math.min(pts[0][1], pts[1][1]) - tol && y <= Math.max(pts[0][1], pts[1][1]) + tol) return i;
    }
    if (m.tipo === "seta" || m.tipo === "traco") {
      for (let k = 1; k < pts.length; k++) if (distSegmento(x, y, pts[k - 1], pts[k]) <= tol) return i;
    }
  }
  return -1;
}

const copia = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const proximo = (e: Esquema): number => Math.max(0, ...e.marcas.map((m) => m.n || 0)) + 1;

// ---------------------------------------------------------------------- escolher o modelo
export async function escolherModelo(): Promise<Modelo | null> {
  const { modelos: ms } = await modelos();
  return new Promise((resolver) => {
    let escolhido: Modelo | null = null;
    const corpo = el("div", { class: "esq-modelos" });
    const grupos = [...new Set(ms.map((m) => m.grupo))];
    for (const g of grupos) {
      corpo.append(el("h4", {}, tr(g)));
      const linha = el("div", { class: "esq-modelos-linha" });
      for (const m of ms.filter((x) => x.grupo === g)) {
        const cv = el("canvas", { width: "180", height: String(Math.round((180 * m.h) / m.w)) });
        const b = el("button", { type: "button", class: "esq-modelo", "data-modelo": m.id }, cv, el("span", {}, tr(m.nome)));
        b.onclick = () => { escolhido = m; d.close(); };
        desenhar(cv, m, null);
        if (m.meu) void fundoDe(m).then((f) => { if (f) desenhar(cv, m, null, f); });
        linha.append(b);
      }
      corpo.append(linha);
    }
    const d = el("dialog", { class: "imp-janela larga esq-escolha", "aria-label": tr("Novo esquema") });
    d.append(el("h3", {}, tr("Novo esquema")), el("div", { class: "imp-janela-corpo" }, corpo),
      el("div", { class: "imp-janela-botoes" }, botao("Cancelar", () => d.close())));
    d.addEventListener("close", () => { d.remove(); resolver(escolhido); });
    document.body.append(d);
    d.showModal();
  });
}

// ---------------------------------------------------------------------- o editor
export interface OpcoesDoEditor {
  podeEscrever: boolean;
  /** A imagem que está aberta no visualizador (para ligar a uma marca); null se não há. */
  imagemAberta?: () => { series_uid: string; sop_uid: string; frame: number } | null;
  study: string;
}

/** Abre o editor. Devolve o esquema como ficou, "excluir" ou null (cancelou). */
export async function editarEsquema(inicial: Esquema, op: OpcoesDoEditor): Promise<Esquema | "excluir" | null> {
  const { modelos: ms, cores } = await modelos();
  const mod = ms.find((m) => m.id === inicial.modelo);
  if (!mod) throw new Error(tr("O modelo deste esquema não existe mais."));
  const fundo = await fundoDe(mod);
  return new Promise((resolver) => {
    const e: Esquema = copia(inicial);
    let resultado: Esquema | "excluir" | null = null;
    let ferramenta = op.podeEscrever ? "ponto" : "mover";
    let cor = cores[0];
    let categoria = mod.categorias.length ? mod.categorias[mod.categorias.length - 2]?.k || mod.categorias[0].k : "";
    let escolhida = -1;
    let rascunho: Marca | null = null;
    let arrasto: { i: number; x: number; y: number; orig: number[][]; mexeu: boolean } | null = null;
    const desfazer: string[] = [];
    const guardar = () => { desfazer.push(JSON.stringify(e)); if (desfazer.length > 60) desfazer.shift(); bDesfazer.disabled = false; };

    const cv = el("canvas", { class: "esq-tela", tabindex: "0", "aria-label": tr(mod.nome) });
    const palco = el("div", { class: "esq-palco" }, cv);
    const lista = el("div", { class: "esq-lista" });
    const titulo = el("input", { class: "esq-titulo", "aria-label": tr("Título do esquema"), placeholder: tr(mod.nome), maxlength: "80" });
    titulo.value = e.titulo;
    titulo.oninput = () => { e.titulo = titulo.value; };
    const cNumerar = el("input", { type: "checkbox", id: "esq-numerar" });
    cNumerar.checked = true;
    const erro = el("p", { class: "cad-erro", role: "alert" });

    const ajustar = () => {
      const larg = Math.max(220, Math.min(palco.clientWidth || 600, ((palco.clientHeight || 600) * mod.w) / mod.h));
      const dpr = Math.min(3, window.devicePixelRatio || 1);
      cv.style.width = `${Math.round(larg)}px`;
      cv.style.height = `${Math.round((larg * mod.h) / mod.w)}px`;
      cv.width = Math.round(larg * dpr);
      cv.height = Math.round(((larg * mod.h) / mod.w) * dpr);
      pintar();
    };
    const pintar = () => {
      desenhar(cv, mod, rascunho ? { ...e, marcas: [...e.marcas, rascunho] } : e, fundo, escolhida);
    };

    // ---- a lista das marcas (o elo com o texto do laudo e com a imagem)
    const montarLista = (focar = -1) => {
      const linhas: HTMLElement[] = [];
      let aFocar: HTMLInputElement | null = null;
      e.marcas.forEach((m, i) => {
        if (m.tipo === "traco" && !m.n && !m.texto) return;       // traço solto: só desenho, não entra na lista
        const n = el("input", { type: "number", min: "0", max: "999", class: "esq-n", "aria-label": tr("Número") });
        n.value = m.n ? String(m.n) : "";
        n.disabled = !op.podeEscrever || m.tipo === "texto";
        n.onchange = () => { guardar(); m.n = Math.max(0, Math.min(999, Math.round(Number(n.value) || 0))); pintar(); };
        const t = el("input", { class: "esq-texto", placeholder: tr("descrição (vai para a legenda do laudo)"), maxlength: "300", "aria-label": tr("Descrição") });
        t.value = m.texto;
        t.disabled = !op.podeEscrever;
        t.onfocus = () => { escolhida = i; pintar(); };
        t.oninput = () => { m.texto = t.value; if (m.tipo === "texto") pintar(); };
        const bolinha = el("span", { class: "esq-cor" });
        bolinha.style.background = m.cor;
        const linha = el("div", { class: `esq-item${i === escolhida ? " sel" : ""}`, "data-i": String(i) }, bolinha, n, t);
        if (op.podeEscrever && m.tipo !== "texto") {
          if (m.imagem) {
            const tira = el("button", { type: "button", class: "esq-ligada", title: tr("Tirar a ligação com a imagem") }, `${m.imagem.rotulo} ×`);
            tira.onclick = () => { guardar(); delete m.imagem; montarLista(); };
            linha.append(tira);
          } else if (op.imagemAberta) {
            const liga = el("button", { type: "button", class: "esq-ligar", title: tr("Liga esta marca à imagem que está aberta no visualizador; a imagem passa a ser imagem-chave") }, tr("Ligar à imagem aberta"));
            liga.onclick = () => {
              const im = op.imagemAberta?.();
              if (!im) { erro.textContent = tr("Abra no visualizador a imagem que quer ligar a esta marca."); return; }
              erro.textContent = "";
              json<{ imagem: ImagemLigada }>("ligar", { study: op.study, ...im }).then((r) => { guardar(); m.imagem = r.imagem; montarLista(); },
                (x: Error) => { erro.textContent = x.message; });
            };
            linha.append(liga);
          }
        } else if (m.imagem) {
          linha.append(el("span", { class: "esq-ligada" }, m.imagem.rotulo));
        }
        if (op.podeEscrever) {
          const x = el("button", { type: "button", class: "esq-x", "aria-label": tr("Apagar a marca"), title: tr("Apagar a marca") }, "×");
          x.onclick = () => { guardar(); e.marcas.splice(i, 1); escolhida = -1; montarLista(); pintar(); };
          linha.append(x);
        }
        linhas.push(linha);
        if (i === focar) aFocar = t;
      });
      const pintados = Object.keys(e.setores).length;
      lista.replaceChildren(...(linhas.length ? linhas : [el("p", { class: "dica" }, tr(op.podeEscrever ? "Marque na figura: cada marca numerada ganha uma linha aqui, com a descrição que vai para o laudo." : "Nenhuma marca numerada."))]),
        ...(pintados ? [el("p", { class: "dica esq-pintados" }, `${pintados} ${tr("setor(es) pintado(s)")}`)] : []));
      (aFocar as HTMLInputElement | null)?.focus();
    };

    // ---- a barra de ferramentas
    const barra = el("div", { class: "esq-barra", role: "toolbar", "aria-label": tr("Ferramentas do esquema") });
    const dica = el("span", { class: "esq-dica" });
    const botoesF = new Map<string, HTMLButtonElement>();
    const escolherFerramenta = (k: string) => {
      ferramenta = k;
      for (const [id, b] of botoesF) b.setAttribute("aria-pressed", String(id === k));
      dica.textContent = tr(FERRAMENTAS.find((f) => f[0] === k)?.[2] || "");
      cats.hidden = k !== "setor";
      paleta.hidden = k === "setor" || k === "mover" || k === "apagar";
    };
    for (const [k, nome, ajuda] of FERRAMENTAS) {
      if (k === "setor" && !mod.setores.length) continue;
      const b = el("button", { type: "button", "data-f": k, "aria-pressed": "false", title: tr(ajuda) }, tr(nome));
      b.onclick = () => escolherFerramenta(k);
      botoesF.set(k, b);
      barra.append(b);
    }
    const paleta = el("span", { class: "esq-paleta", role: "radiogroup", "aria-label": tr("Cor") });
    for (const c of cores) {
      const b = el("button", { type: "button", role: "radio", "aria-checked": String(c === cor), "aria-label": c, "data-cor": c });
      b.style.background = c;
      b.onclick = () => { cor = c; paleta.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b))); };
      paleta.append(b);
    }
    const cats = el("span", { class: "esq-cats", role: "radiogroup", "aria-label": tr("Categoria") });
    for (const k of mod.categorias) {
      const b = el("button", { type: "button", role: "radio", "aria-checked": String(k.k === categoria), "data-cat": k.k }, k.nome);
      b.style.borderColor = k.cor;
      b.onclick = () => { categoria = k.k; cats.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b))); };
      cats.append(b);
    }
    const bDesfazer = botao("Desfazer", () => {
      const s = desfazer.pop();
      if (!s) return;
      const v = JSON.parse(s) as Esquema;
      e.marcas = v.marcas;
      e.setores = v.setores;
      escolhida = -1;
      bDesfazer.disabled = !desfazer.length;
      montarLista();
      pintar();
    });
    bDesfazer.disabled = true;
    barra.append(paleta, cats, el("label", { class: "esq-numerar", for: "esq-numerar" }, cNumerar, ` ${tr("Numerar")}`), bDesfazer);

    // ---- desenhar com o ponteiro
    const ponto = (ev: PointerEvent): [number, number] => {
      const r = cv.getBoundingClientRect();
      return [Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)), Math.max(0, Math.min(1, (ev.clientY - r.top) / r.height))];
    };
    const nova = (tipo: TipoMarca, p: number[][], numerar: boolean): Marca =>
      ({ tipo, n: numerar && cNumerar.checked ? proximo(e) : 0, p, cor, l: tipo === "traco" ? 4 : 3, texto: "" });
    cv.onpointerdown = (ev) => {
      if (!op.podeEscrever && ferramenta !== "mover") return;
      ev.preventDefault();
      cv.setPointerCapture(ev.pointerId);
      const [x, y] = ponto(ev);
      const em = marcaEm(e, x * cv.width, y * cv.height, cv.width, cv.height);
      if (ferramenta === "mover") {
        escolhida = em;
        if (em >= 0 && op.podeEscrever) arrasto = { i: em, x, y, orig: copia(e.marcas[em].p), mexeu: false };
        montarLista();
        pintar();
      } else if (ferramenta === "apagar") {
        if (em >= 0) { guardar(); e.marcas.splice(em, 1); escolhida = -1; montarLista(); pintar(); }
      } else if (ferramenta === "setor") {
        const s = mod.setores.find((z) => dentro(z.p, x * mod.w, y * mod.h));
        if (s) {
          guardar();
          if (e.setores[s.id] === categoria) delete e.setores[s.id];
          else e.setores[s.id] = categoria;
          montarLista();
          pintar();
        }
      } else if (ferramenta === "ponto") {
        guardar();
        e.marcas.push(nova("ponto", [[x, y]], true));
        escolhida = e.marcas.length - 1;
        montarLista(ev.pointerType === "mouse" ? escolhida : -1);
        pintar();
      } else if (ferramenta === "texto") {
        const t = window.prompt(tr("Texto na figura:"), "");
        if (t && t.trim()) {
          guardar();
          e.marcas.push({ ...nova("texto", [[x, y]], false), texto: t.trim().slice(0, 300) });
          montarLista();
          pintar();
        }
      } else {
        rascunho = nova(ferramenta as TipoMarca, [[x, y], [x, y]], ferramenta !== "traco");
        pintar();
      }
    };
    cv.onpointermove = (ev) => {
      const [x, y] = ponto(ev);
      if (arrasto) {
        const dx = x - arrasto.x, dy = y - arrasto.y;
        if (!arrasto.mexeu && Math.hypot(dx, dy) < 0.006) return;
        if (!arrasto.mexeu) { guardar(); arrasto.mexeu = true; }
        e.marcas[arrasto.i].p = arrasto.orig.map(([a, b]) => [Math.max(0, Math.min(1, a + dx)), Math.max(0, Math.min(1, b + dy))]);
        pintar();
      } else if (rascunho) {
        if (rascunho.tipo === "traco") {
          const u = rascunho.p[rascunho.p.length - 1];
          if (Math.hypot(x - u[0], y - u[1]) > 0.004 && rascunho.p.length < 590) rascunho.p.push([x, y]);
        } else rascunho.p[1] = [x, y];
        pintar();
      }
    };
    const soltar = (ev: PointerEvent) => {
      if (cv.hasPointerCapture(ev.pointerId)) cv.releasePointerCapture(ev.pointerId);
      arrasto = null;
      if (!rascunho) return;
      const r = rascunho;
      rascunho = null;
      const tam = Math.hypot(r.p[r.p.length - 1][0] - r.p[0][0], r.p[r.p.length - 1][1] - r.p[0][1]);
      if (r.tipo === "traco" ? r.p.length > 2 : tam > 0.012) {          // um toque sem arrastar não vira marca
        guardar();
        e.marcas.push(r);
        escolhida = e.marcas.length - 1;
        montarLista(ev.pointerType === "mouse" && r.n ? escolhida : -1);
      }
      pintar();
    };
    cv.onpointerup = soltar;
    cv.onpointercancel = soltar;

    // ---- a janela
    const bSalvar = botao("Salvar", () => { resultado = e; d.close(); }, "primario");
    const bExcluir = botao("Excluir o esquema", () => {
      void confirmar(tr("Excluir o esquema"), tr("Excluir este esquema do exame?"), "", "Excluir").then((sim) => { if (sim) { resultado = "excluir"; d.close(); } });
    });
    const lado = el("div", { class: "esq-lado" }, el("label", { class: "esq-rot" }, tr("Título"), titulo), lista, erro);
    const d = el("dialog", { class: "imp-janela esq-janela", "aria-label": tr("Esquema") });
    d.append(el("h3", {}, tr(mod.nome)), ...(op.podeEscrever ? [barra, dica] : []), el("div", { class: "esq-corpo" }, palco, lado),
      el("div", { class: "imp-janela-botoes" }, ...(op.podeEscrever ? [bExcluir, botao("Cancelar", () => d.close()), bSalvar] : [botao("Fechar", () => d.close())])));
    titulo.disabled = !op.podeEscrever;
    const obs = new ResizeObserver(() => ajustar());
    d.addEventListener("close", () => { obs.disconnect(); d.remove(); resolver(resultado); });
    document.body.append(d);
    d.showModal();
    obs.observe(palco);
    escolherFerramenta(ferramenta);
    montarLista();
    ajustar();
    (window as unknown as { __ipeEsquema: unknown }).__ipeEsquema = {
      estado: () => ({ modelo: mod.id, ferramenta, marcas: e.marcas, setores: e.setores, titulo: e.titulo }),
      setor: (id: string) => { const s = mod.setores.find((z) => z.id === id); return s ? [s.cx / mod.w, s.cy / mod.h] : null; },
    };
  });
}

// ---------------------------------------------------------------------- a seção do painel do laudo
/** "Esquemas-guia" dentro do laudo: as miniaturas do exame, novo, editar e inserir a legenda no texto. */
export class EsquemasDoLaudo {
  readonly raiz = el("details", { class: "esquemas-laudo" });
  private grade = el("div", { class: "esq-grade" });
  private msg = el("span", { class: "esq-msg", "aria-live": "polite" });
  private esquemas: Esquema[] = [];
  private pode = false;
  private podeNoServidor = false;
  private travado = false;
  private botoes: HTMLButtonElement[] = [];
  legenda = "";

  constructor(private study: string, private inserir: (texto: string) => void,
    private imagemAberta: () => { series_uid: string; sop_uid: string; frame: number } | null) {}

  async abrir(soLeitura: boolean): Promise<void> {
    try {
      const r = await esquemasDoExame(this.study);
      this.esquemas = r.esquemas;
      this.legenda = r.legenda;
      this.podeNoServidor = r.pode;
      this.travado = soLeitura;
      this.pode = r.pode && !soLeitura;
    } catch (e) {
      this.msg.textContent = (e as Error).message;
    }
    const bNovo = botao("Novo esquema…", () => void this.novo());
    const bLegenda = botao("Inserir a legenda no laudo", () => {
      if (!this.legenda) { this.msg.textContent = tr("Nenhuma marca numerada nem setor pintado para pôr na legenda."); return; }
      this.inserir(this.legenda);
      this.msg.textContent = tr("Legenda inserida no texto.");
    });
    this.botoes = [bNovo, bLegenda];
    bNovo.hidden = bLegenda.hidden = !this.pode;
    this.raiz.replaceChildren(el("summary", {}, tr("Esquemas-guia")), this.grade, el("div", { class: "botoes-laudo" }, bNovo, bLegenda), this.msg);
    await this.montar();
    (window as unknown as { __ipeEsquemas: unknown }).__ipeEsquemas = { lista: () => this.esquemas, legenda: () => this.legenda };
  }

  /** O laudo ficou só para ler (assinado, ou outro médico está laudando) ou voltou a ser rascunho. */
  travar(sim: boolean): void {
    if (sim === this.travado) return;
    this.travado = sim;
    this.pode = this.podeNoServidor && !sim;
    for (const b of this.botoes) b.hidden = !this.pode;
  }

  private async montar(): Promise<void> {
    const { modelos: ms } = await modelos();
    const cartoes: HTMLElement[] = [];
    for (const e of this.esquemas) {
      const m = ms.find((x) => x.id === e.modelo);
      if (!m) continue;
      const cv = el("canvas", { width: "240", height: String(Math.round((240 * m.h) / m.w)) });
      desenhar(cv, m, e);
      if (m.meu) void fundoDe(m).then((f) => { if (f) desenhar(cv, m, e, f); });
      const b = el("button", { type: "button", class: "esq-cartao", "data-esquema": e.id, title: tr(this.pode ? "Editar o esquema" : "Ver o esquema") },
        cv, el("span", {}, e.titulo || tr(m.nome)));
      b.onclick = () => void this.editar(e);
      cartoes.push(b);
    }
    this.grade.replaceChildren(...(cartoes.length ? cartoes : [el("p", { class: "dica" }, tr("Nenhum esquema neste exame."))]));
    this.raiz.querySelector("summary")!.textContent = this.esquemas.length ? `${tr("Esquemas-guia")} (${this.esquemas.length})` : tr("Esquemas-guia");
  }

  private async salvar(lista: Esquema[]): Promise<void> {
    try {
      const r = await gravarEsquemas(this.study, lista);
      this.esquemas = r.esquemas;
      this.legenda = r.legenda;
      this.msg.textContent = tr("Esquemas salvos: vão para o PDF, e para o exame (imagem e SR) ao assinar.");
    } catch (e) {
      this.msg.textContent = (e as Error).message;
    }
    await this.montar();
  }

  private async novo(): Promise<void> {
    const m = await escolherModelo();
    if (!m) return;
    await this.editar({ id: "", modelo: m.id, titulo: "", marcas: [], setores: {} }, true);
  }

  private async editar(e: Esquema, novo = false): Promise<void> {
    let r: Esquema | "excluir" | null;
    try {
      r = await editarEsquema(e, { podeEscrever: this.pode, imagemAberta: this.imagemAberta, study: this.study });
    } catch (x) {
      this.msg.textContent = (x as Error).message;
      return;
    }
    if (!r || !this.pode) return;
    if (r === "excluir") {
      if (!novo) await this.salvar(this.esquemas.filter((x) => x.id !== e.id));
      return;
    }
    const pronto = r;
    await this.salvar(novo ? [...this.esquemas, pronto] : this.esquemas.map((x) => (x.id === e.id ? pronto : x)));
  }
}
