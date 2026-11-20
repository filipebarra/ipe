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
  /** 0.100.73: o desenho do próprio modelo (por baixo das marcas do exame); se tem imagem de fundo; se é um modelo
   * do Ipê que esta instalação mudou, ou escondeu da lista. */
  base?: Marca[]; imagem?: boolean; alterado?: boolean; oculto?: boolean; origem?: string;
}
interface Modelos { modelos: Modelo[]; cores: string[]; pode_modelos?: boolean }
/** O editor no modo "modelo": o que se desenha vira o desenho do modelo (para todos os exames). */
export interface ModoModelo { nome: string; grupo: string; oculto: boolean; acao: "" | "salvar" | "copia" | "excluir" }
interface DoExame { esquemas: Esquema[]; pode: boolean; legenda: string; no_laudo?: boolean; com_desenho?: number }

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

let modelosProntos: Promise<Modelos> | null = null;
const fundos = new Map<string, HTMLImageElement>();

export function modelos(): Promise<Modelos> {
  if (!modelosProntos) {
    modelosProntos = json<Modelos>("modelos");
    modelosProntos.catch(() => { modelosProntos = null; });
  }
  return modelosProntos;
}

/** Depois de cadastrar ou mudar um modelo: a próxima leitura busca de novo no servidor. */
function esquecerModelos(id = ""): void {
  modelosProntos = null;
  if (id) fundos.delete(id);
}

/** A imagem de fundo de um modelo próprio (os do Ipê são só traços). */
async function fundoDe(m: Modelo): Promise<HTMLImageElement | null> {
  if (!m.imagem) return null;
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
  for (const m of mod.base || []) marcaNoCanvas(c, m, W, H, base, false);       // o desenho do modelo, por baixo
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

// ---------------------------------------------------------------------- escolher (e cadastrar) o modelo
function lerArquivo(f: File): Promise<string> {
  return new Promise((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => falha(new Error(tr("Não consegui ler o arquivo.")));
    r.readAsDataURL(f);
  });
}

/** Abre o editor para desenhar o próprio modelo; grava o que a pessoa decidir. Devolve se mudou alguma coisa. */
async function editarModelo(m: Modelo): Promise<boolean> {
  const modo: ModoModelo = { nome: m.nome, grupo: m.grupo, oculto: !!m.oculto, acao: "" };
  const r = await editarEsquema({ id: "", modelo: m.id, titulo: "", marcas: copia(m.base || []), setores: {} },
    { podeEscrever: true, study: "", modoModelo: modo });
  if (modo.acao === "excluir") {
    await json("modelo_excluir", { id: m.id });
  } else if (r && r !== "excluir" && modo.acao === "salvar") {
    await json("modelo", { id: m.id, nome: modo.nome, grupo: modo.grupo, oculto: modo.oculto, base: r.marcas });
  } else if (r && r !== "excluir" && modo.acao === "copia") {
    await json("modelo", { nome: modo.nome, grupo: modo.grupo, origem: m.id, base: r.marcas });
  } else {
    return false;
  }
  esquecerModelos(m.id);
  return true;
}

/** A grade dos modelos. Com `gerir`, o cadastro (0.100.74: fica em Cadastros ▸ Modelos de esquema): novo de uma
 * imagem, em branco e "Editar o modelo" em cada um; sem ele, só escolher (`aoEscolher`). */
export function gradeDeModelos(op: { gerir: boolean; aoEscolher?: (m: Modelo) => void }): HTMLElement {
  const corpo = el("div", { class: "esq-modelos" });
  const aviso = el("p", { class: "cad-erro", role: "alert" });
  const gerir = el("div", { class: "imp-barra esq-gerir", hidden: "" });
  const arquivo = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/bmp", hidden: "" });
  const tentar = async (fn: () => Promise<unknown>) => {
    aviso.textContent = "";
    try { await fn(); } catch (e) { aviso.textContent = (e as Error).message; }
    await montar();
  };
  arquivo.onchange = () => {
    const f = arquivo.files?.[0];
    arquivo.value = "";
    if (!f) return;
    const nome = window.prompt(tr("Nome do modelo:"), f.name.replace(/\.[^.]+$/, ""));
    if (!nome || !nome.trim()) return;
    void tentar(async () => {
      await json("modelo", { nome: nome.trim(), imagem: await lerArquivo(f) });
      esquecerModelos();
    });
  };
  gerir.append(botao("Novo modelo de uma imagem…", () => arquivo.click()),
    botao("Novo modelo em branco…", () => {
      const nome = window.prompt(tr("Nome do modelo:"), "");
      if (nome && nome.trim()) void tentar(async () => { await json("modelo", { nome: nome.trim() }); esquecerModelos(); });
    }), arquivo);
  gerir.title = tr("Os modelos valem para todos os usuários desta instalação");
  const montar = async () => {
    let dados: Modelos;
    try { dados = await modelos(); } catch (e) { aviso.textContent = (e as Error).message; return; }
    const pode = op.gerir && !!dados.pode_modelos;
    gerir.hidden = !pode;
    if (op.gerir && !pode) aviso.textContent = tr("Cadastrar e mudar modelos pede a permissão de configurar.");
    const ms = dados.modelos.filter((m) => pode || !m.oculto);
    const filhos: Node[] = [];
    for (const g of [...new Set(ms.map((m) => m.grupo))]) {
      filhos.push(el("h4", {}, tr(g)));
      const linha = el("div", { class: "esq-modelos-linha" });
      for (const m of ms.filter((x) => x.grupo === g)) {
        const cv = el("canvas", { width: "180", height: String(Math.round((180 * m.h) / m.w)) });
        const nome = `${tr(m.nome)}${m.oculto ? ` (${tr("oculto")})` : ""}`;
        const b = el("button", { type: "button", class: `esq-modelo${m.oculto ? " oculto" : ""}`, "data-modelo": m.id }, cv, el("span", {}, nome));
        b.onclick = () => { if (pode) void tentar(() => editarModelo(m)); else op.aoEscolher?.(m); };
        desenhar(cv, m, null);
        if (m.imagem) void fundoDe(m).then((f) => { if (f) desenhar(cv, m, null, f); });
        const caixa = el("div", { class: "esq-modelo-caixa" }, b);
        if (pode) {
          const ed = el("button", { type: "button", class: "esq-modelo-editar", "data-editar": m.id,
            title: tr("Desenhar no modelo, mudar o nome ou o grupo, ocultar, copiar ou excluir") }, tr("Editar o modelo"));
          ed.onclick = () => void tentar(() => editarModelo(m));
          caixa.append(ed);
        }
        linha.append(caixa);
      }
      filhos.push(linha);
    }
    corpo.replaceChildren(...filhos);
  };
  void montar();
  return el("div", { class: "esq-grade-modelos" }, gerir, aviso, corpo);
}

export async function escolherModelo(): Promise<Modelo | null> {
  return new Promise((resolver) => {
    let escolhido: Modelo | null = null;
    const grade = gradeDeModelos({ gerir: false, aoEscolher: (m) => { escolhido = m; d.close(); } });
    const d = el("dialog", { class: "imp-janela larga esq-escolha", "aria-label": tr("Novo esquema") });
    d.append(el("h3", {}, tr("Novo esquema")), el("div", { class: "imp-janela-corpo" }, grade),
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
  /** 0.100.73: desenhar o próprio modelo (nome, grupo, ocultar); a decisão da pessoa fica em `acao`. */
  modoModelo?: ModoModelo;
}

/** Abre o editor. Devolve o esquema como ficou, "excluir" ou null (cancelou). */
export async function editarEsquema(inicial: Esquema, op: OpcoesDoEditor): Promise<Esquema | "excluir" | null> {
  const { modelos: ms, cores } = await modelos();
  const modCompleto = ms.find((m) => m.id === inicial.modelo);
  if (!modCompleto) throw new Error(tr("O modelo deste esquema não existe mais."));
  const mm = op.modoModelo;
  // no modo "modelo" o desenho do modelo é o que se edita: não entra como fundo
  const mod: Modelo = mm ? { ...modCompleto, base: [], setores: [], categorias: [] } : modCompleto;
  const fundo = await fundoDe(mod);
  return new Promise((resolver) => {
    const e: Esquema = copia(inicial);
    let resultado: Esquema | "excluir" | null = null;
    let ferramenta = mm ? "traco" : op.podeEscrever ? "ponto" : "mover";
    let cor = mm ? cores[cores.length - 1] : cores[0];        // o desenho de um modelo começa em preto
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
    cNumerar.checked = !mm;
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
    const rotNumerar = el("label", { class: "esq-numerar", for: "esq-numerar" }, cNumerar, ` ${tr("Numerar")}`);
    rotNumerar.hidden = !!mm;
    barra.append(paleta, cats, rotNumerar, bDesfazer);

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
    let lado = el("div", { class: "esq-lado" }, el("label", { class: "esq-rot" }, tr("Título"), titulo), lista, erro);
    let botoesDaJanela: HTMLButtonElement[] = op.podeEscrever ? [bExcluir, botao("Cancelar", () => d.close()), bSalvar] : [botao("Fechar", () => d.close())];
    if (mm) {
      const nome = el("input", { id: "esq-m-nome", maxlength: "60" });
      nome.value = tr(mm.nome);
      const grupo = el("input", { id: "esq-m-grupo", maxlength: "30" });
      grupo.value = tr(mm.grupo);
      const oculto = el("input", { type: "checkbox", id: "esq-m-oculto" });
      oculto.checked = mm.oculto;
      const fechar = (acao: ModoModelo["acao"]) => {
        if (!nome.value.trim()) { erro.textContent = tr("Dê um nome ao modelo."); return; }
        mm.nome = nome.value.trim();
        mm.grupo = grupo.value.trim();
        mm.oculto = oculto.checked;
        mm.acao = acao;
        resultado = e;
        d.close();
      };
      const doIpe = !modCompleto.meu;
      lado = el("div", { class: "esq-lado" },
        el("label", { class: "esq-rot", for: "esq-m-nome" }, tr("Nome do modelo"), nome),
        el("label", { class: "esq-rot", for: "esq-m-grupo" }, tr("Grupo"), grupo),
        ...(doIpe ? [el("label", { class: "cad-caixa", for: "esq-m-oculto" }, oculto, el("span", {}, tr("Ocultar da lista de modelos")))] : []),
        el("p", { class: "dica" }, tr("O que você desenhar aqui passa a fazer parte do modelo, em todos os exames. Os esquemas já feitos com ele também mudam.")),
        ...(doIpe ? [el("p", { class: "dica" }, tr("Este é um modelo do Ipê: o desenho original fica guardado e volta com “Restaurar o original”."))] : []),
        erro);
      const bTirar = botao(doIpe ? "Restaurar o original" : "Excluir o modelo", () => {
        void confirmar(tr(doIpe ? "Restaurar o original" : "Excluir o modelo"),
          tr(doIpe ? "Desfazer tudo o que foi mudado neste modelo?" : "Excluir este modelo? Os esquemas já feitos com ele deixam de aparecer."), "",
          doIpe ? "Restaurar" : "Excluir").then((sim) => { if (sim) { mm.acao = "excluir"; d.close(); } });
      });
      bTirar.hidden = doIpe && !modCompleto.alterado;
      botoesDaJanela = [bTirar, botao("Salvar como cópia", () => fechar("copia")), botao("Cancelar", () => d.close()),
        botao("Salvar o modelo", () => fechar("salvar"), "primario")];
    }
    const d = el("dialog", { class: "imp-janela esq-janela", "aria-label": tr(mm ? "Modelo de esquema" : "Esquema") });
    d.append(el("h3", {}, mm ? `${tr("Modelo de esquema")} — ${tr(mod.nome)}` : tr(mod.nome)), ...(op.podeEscrever ? [barra, dica] : []), el("div", { class: "esq-corpo" }, palco, lado),
      el("div", { class: "imp-janela-botoes" }, ...botoesDaJanela));
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

// ---------------------------------------------------------------------- os esquemas do exame (botão do visualizador)
type ImagemAberta = () => { series_uid: string; sop_uid: string; frame: number } | null;

/** 0.100.74: os esquemas do exame, fora do laudo — as miniaturas, novo, desenhar e gravar no exame (gravar de novo
 * troca o que havia). É o que o botão **Esquema** do visualizador abre. */
export class EsquemasDoExame {
  readonly raiz = el("div", { class: "esquemas-exame" });
  private grade = el("div", { class: "esq-grade" });
  private msg = el("span", { class: "esq-msg", "aria-live": "polite" });
  private esquemas: Esquema[] = [];
  private pode = false;
  private bGravar: HTMLButtonElement | null = null;

  constructor(private study: string, private imagemAberta: ImagemAberta) {}

  async abrir(): Promise<void> {
    try {
      const r = await esquemasDoExame(this.study);
      this.esquemas = r.esquemas;
      this.pode = r.pode;
    } catch (e) {
      this.msg.textContent = (e as Error).message;
    }
    const bNovo = botao("Novo esquema…", () => void this.novo(), "primario");
    const bGravar = botao("Gravar no exame", () => {
      bGravar.disabled = true;
      this.msg.textContent = tr("Gravando no exame…");
      json<{ imagens: number }>("no_exame", { study: this.study })
        .then((r) => { this.msg.textContent = `${tr("Gravado no exame (figuras e SR):")} ${r.imagens}`; },
          (e: Error) => { this.msg.textContent = e.message; })
        .finally(() => { bGravar.disabled = false; });
    });
    bGravar.title = tr("Grava as figuras e um SR dos esquemas no exame agora, sem precisar assinar o laudo. Gravar de novo troca o que havia.");
    this.bGravar = bGravar;
    bNovo.hidden = bGravar.hidden = !this.pode;
    this.raiz.replaceChildren(this.grade, el("div", { class: "imp-barra" }, bNovo, bGravar), this.msg,
      el("p", { class: "dica" }, tr("Para o esquema sair no laudo, marque “Esquemas no laudo” no painel do laudo.")));
    await this.montar();
    (window as unknown as { __ipeEsquemas: unknown }).__ipeEsquemas = { lista: () => this.esquemas };
  }

  private async montar(): Promise<void> {
    const { modelos: ms } = await modelos();
    const cartoes: HTMLElement[] = [];
    for (const e of this.esquemas) {
      const m = ms.find((x) => x.id === e.modelo);
      if (!m) continue;
      const cv = el("canvas", { width: "240", height: String(Math.round((240 * m.h) / m.w)) });
      desenhar(cv, m, e);
      if (m.imagem) void fundoDe(m).then((f) => { if (f) desenhar(cv, m, e, f); });
      const b = el("button", { type: "button", class: "esq-cartao", "data-esquema": e.id, title: tr(this.pode ? "Editar o esquema" : "Ver o esquema") },
        cv, el("span", {}, e.titulo || tr(m.nome)));
      b.onclick = () => void this.editar(e);
      cartoes.push(b);
    }
    this.grade.replaceChildren(...(cartoes.length ? cartoes : [el("p", { class: "dica" }, tr("Nenhum esquema neste exame."))]));
    if (this.bGravar) this.bGravar.disabled = !this.esquemas.some((e) => e.marcas.length || Object.keys(e.setores).length);
  }

  private async salvar(lista: Esquema[]): Promise<void> {
    try {
      const r = await gravarEsquemas(this.study, lista);
      this.esquemas = r.esquemas;
      this.msg.textContent = tr("Esquemas salvos.");
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

/** A janela do botão Esquema do visualizador. */
export function abrirEsquemasDoExame(study: string, imagemAberta: ImagemAberta): Promise<void> {
  return new Promise((resolver) => {
    const painel = new EsquemasDoExame(study, imagemAberta);
    const d = el("dialog", { class: "imp-janela larga esq-do-exame", "aria-label": tr("Esquemas do exame") });
    d.append(el("h3", {}, tr("Esquemas do exame")), el("div", { class: "imp-janela-corpo" }, painel.raiz),
      el("div", { class: "imp-janela-botoes" }, botao("Fechar", () => d.close())));
    d.addEventListener("close", () => { d.remove(); resolver(); });
    document.body.append(d);
    d.showModal();
    void painel.abrir();
  });
}

// ---------------------------------------------------------------------- no laudo: "Esquemas no laudo"
/** No laudo o esquema só se **inclui** (como as imagens-chave): as figuras no PDF, os esquemas no SR ao assinar e a
 * legenda no texto. O desenho é feito pelo botão Esquema do visualizador. */
export class EsquemasNoLaudo {
  private caixa = el("input", { type: "checkbox", id: "esq-no-laudo" });
  private rotulo = el("span", {}, tr("Esquemas no laudo"));
  readonly raiz = el("label", { class: "cad-caixa esquemas-no-laudo", for: "esq-no-laudo",
    title: tr("Põe no laudo a seção dos esquemas-guia do exame, como as imagens-chave: as figuras com a legenda no PDF, a legenda no texto e, ao assinar, os esquemas no SR. Os esquemas são desenhados pelo botão Esquema do visualizador.") },
  this.caixa, this.rotulo);
  private pode = false;
  private travado = false;
  private n = 0;

  constructor(private study: string, private inserir: (texto: string) => void, private textoAtual: () => string) {
    this.caixa.onchange = () => void this.mudar();
  }

  async atualizar(): Promise<void> {
    try {
      const r = await esquemasDoExame(this.study);
      this.pode = r.pode;
      this.n = r.com_desenho ?? 0;
      this.caixa.checked = !!r.no_laudo && this.n > 0;
    } catch { /* fica como estava */ }
    this.estado();
  }

  travar(sim: boolean): void {
    this.travado = sim;
    this.estado();
  }

  private estado(): void {
    this.rotulo.textContent = this.n ? `${tr("Esquemas no laudo")} (${this.n})` : tr("Esquemas no laudo");
    this.caixa.disabled = !this.pode || this.travado || !this.n;
  }

  private async mudar(): Promise<void> {
    const sim = this.caixa.checked;
    try {
      const r = await json<{ no_laudo: boolean; legenda: string }>("no_laudo", { study: this.study, sim });
      this.caixa.checked = r.no_laudo;
      if (r.no_laudo && r.legenda && !this.textoAtual().includes(r.legenda)) this.inserir(r.legenda);
    } catch {
      this.caixa.checked = !sim;
    }
  }
}
