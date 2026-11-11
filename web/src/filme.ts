// 0.100.11: montar o filme no navegador e imprimir pelo servidor, com as configurações de impressão do Ipê.
//
// A montagem usa os próprios quadros do visualizador: ajuste a imagem (janela, zoom, deslocamento, giro) com as
// ferramentas de sempre e ponha no filme o quadro ativo, todos os quadros ou a série do quadro. O filme é a receita
// do compositor do Ipê (`printing/film.Film`: folhas, grade, papel e, em cada célula, a imagem e o ajuste); o servidor
// desenha as folhas com o código do Ipê — a prévia é esse mesmo desenho — e manda para a saída escolhida.
import { cache, utilities as csUtils, type Types } from "@cornerstonejs/core";
import { cabecalhos } from "./api";
import { tr } from "./i18n";
import { partesDoImageId } from "./meta";
import type { Grade, SerieCarregada } from "./visor";

export interface CelulaFilme {
  study_uid: string;
  series_uid: string;
  sop_uid: string;
  frame_index: number;
  width: number | null;
  level: number | null;
  zoom: number;
  pan_x: number;
  pan_y: number;
  invert: boolean;
  rotation: number;
  flip_h: boolean;
  measures: boolean;
  label: string;
}

interface Opcoes {
  papeis: string[];
  tamanhos?: Record<string, [number, number]>;
  layouts: string[];
  textos: Record<string, string>;
  destinos: { id: string; nome: string; grupo: string }[];
}

interface Estado {
  nome: string;
  layout: string;
  papel: string;
  paisagem: boolean;
  textos: string;
  cabecalho: boolean;
  anonimo: boolean;
  regua: boolean;
  preto: boolean;
  celulas: CelulaFilme[];
}

type VpFilme = Types.IStackViewport & {
  getCurrentImageId(): string;
  getViewPresentation(): { rotation?: number; flipHorizontal?: boolean; flipVertical?: boolean };
  setViewPresentation(p: { rotation?: number; flipHorizontal?: boolean; flipVertical?: boolean }): void;
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

async function pedir(caminho: string, corpo?: unknown): Promise<Response> {
  const r = await fetch(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...cabecalhos(), ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  return r;
}

// ------------------------------------------------------------------ o quadro ↔ a célula do filme
// O Ipê guarda o ajuste em relação a "caber na célula": zoom 1 = a imagem inteira cabendo (com o giro), e o
// deslocamento é o centro da imagem em fração do quadro, antes do giro e do espelho (ui/film/cell._image_rect).

function rot(v: [number, number], graus: number): [number, number] {
  const a = (graus * Math.PI) / 180;
  return [v[0] * Math.cos(a) - v[1] * Math.sin(a), v[0] * Math.sin(a) + v[1] * Math.cos(a)];
}

function geometria(vp: VpFilme, imageId: string) {
  const im = cache.getImage(imageId) as Types.IImage | undefined;
  if (!im) return null;
  const w = im.columns, h = im.rows;
  const aspecto = (im.rowPixelSpacing || 1) / (im.columnPixelSpacing || 1);
  const pt = (x: number, y: number) => vp.worldToCanvas(csUtils.imageToWorldCoords(imageId, [x, y]) as Types.Point3);
  const a = pt(0, 0), b = pt(1, 0);
  const escala = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const W = vp.canvas.clientWidth, H = vp.canvas.clientHeight;
  const p = vp.getViewPresentation();
  let rotacao = Math.round(((p.rotation || 0) % 360 + 360) % 360 / 90) * 90 % 360;
  let espelho = !!p.flipHorizontal;
  if (p.flipVertical) { rotacao = (rotacao + 180) % 360; espelho = !espelho; }   // espelho vertical = giro 180 + horizontal
  const girado = rotacao === 90 || rotacao === 270;
  const [bw, bh] = girado ? [H, W] : [W, H];
  const caber = Math.min(bw / w, bh / (h * aspecto));
  const c = pt(w / 2, h / 2);
  return { w, h, escala, W, H, rotacao, espelho, bw, bh, caber, centro: c };
}

/** A célula do filme com o quadro `i` como está na tela, ou o motivo de não dar. */
export function capturar(g: Grade, i: number): CelulaFilme | string {
  const q = g.quadros[i];
  if (!q?.serie) return tr("Quadro vazio.");
  if (q.tipo !== "pilha" || q.serie.series.startsWith("ipe")) return tr("Só imagens originais vão para o filme (não MPR, MIP ou mapas).");
  const vp = g.viewport(i) as unknown as VpFilme | null;
  const id = vp?.getCurrentImageId?.() || "";
  const partes = partesDoImageId(id);
  if (!vp || !partes) return tr("Imagem ainda carregando.");
  const geo = geometria(vp, id);
  if (!geo) return tr("Imagem ainda carregando.");
  const props = vp.getProperties() as { voiRange?: { lower: number; upper: number }; invert?: boolean };
  const voi = props.voiRange;
  // o centro da imagem na tela → antes do giro e do espelho → fração do quadro
  let d: [number, number] = [geo.centro[0] - geo.W / 2, geo.centro[1] - geo.H / 2];
  d = rot(d, -geo.rotacao);
  if (geo.espelho) d = [-d[0], d[1]];
  return {
    study_uid: partes.study, series_uid: partes.series, sop_uid: partes.sop, frame_index: Math.max(0, partes.quadro - 1),
    width: voi ? Math.round((voi.upper - voi.lower) * 100) / 100 : null,
    level: voi ? Math.round(((voi.upper + voi.lower) / 2) * 100) / 100 : null,
    zoom: Math.round((geo.escala / geo.caber) * 1e4) / 1e4,
    pan_x: Math.round((d[0] / geo.bw) * 1e4) / 1e4, pan_y: Math.round((d[1] / geo.bh) * 1e4) / 1e4,
    invert: !!props.invert, rotation: geo.rotacao, flip_h: geo.espelho, measures: true, label: q.serie.descricao || "",
  };
}

/** Mostra a célula no quadro `i` (para conferir ou ajustar e atualizar). */
export async function aplicar(g: Grade, i: number, c: CelulaFilme, serie: SerieCarregada): Promise<boolean> {
  const k = serie.imageIds.findIndex((id) => {
    const p = partesDoImageId(id);
    return p?.sop === c.sop_uid && p.quadro === c.frame_index + 1;
  });
  await g.mostrar(i, serie, Math.max(0, k));
  const vp = g.viewport(i) as unknown as VpFilme | null;
  if (!vp) return false;
  const props: Record<string, unknown> = { invert: !!c.invert };
  if (c.width !== null && c.level !== null) props.voiRange = { lower: c.level - c.width / 2, upper: c.level + c.width / 2 };
  vp.setProperties(props);
  vp.setViewPresentation({ rotation: c.rotation || 0, flipHorizontal: !!c.flip_h, flipVertical: false });
  vp.render();
  const id = vp.getCurrentImageId();
  let geo = geometria(vp, id);
  if (!geo || !geo.escala) return false;
  vp.setZoom(vp.getZoom() * (c.zoom * geo.caber) / geo.escala);
  vp.render();
  geo = geometria(vp, id);
  if (!geo) return false;
  let d: [number, number] = [c.pan_x * geo.bw, c.pan_y * geo.bh];
  if (c.flip_h) d = [-d[0], d[1]];
  d = rot(d, geo.rotacao);
  const querido: Types.Point2 = [geo.W / 2 + d[0], geo.H / 2 + d[1]];
  const w1 = vp.canvasToWorld(geo.centro as Types.Point2), w2 = vp.canvasToWorld(querido);
  const cam = vp.getCamera();
  const delta = [w1[0] - w2[0], w1[1] - w2[1], w1[2] - w2[2]];
  vp.setCamera({
    focalPoint: (cam.focalPoint as number[]).map((v, j) => v + delta[j]) as Types.Point3,
    position: (cam.position as number[]).map((v, j) => v + delta[j]) as Types.Point3,
  });
  vp.render();
  return true;
}

// ------------------------------------------------------------------ o painel
const PADRAO: Estado = { nome: "", layout: "2×2", papel: "A4", paisagem: false, textos: "min", cabecalho: true,
  anonimo: false, regua: true, preto: false, celulas: [] };

export class PainelFilme {
  raiz = el("div", { class: "painel-filme" });
  private est: Estado;
  private opcoes: Opcoes | null = null;
  private folha = 0;
  private sel = -1;
  private previa = el("img", { class: "previa-filme", alt: "" });
  private nota = el("div", { class: "nota" });
  private relogio = 0;
  private versao = 0;
  private corpo = el("div", { class: "corpo-filme" });

  constructor(private study: string, private g: Grade, private serieDe: (uid: string) => Promise<SerieCarregada | null>,
    nomePadrao: string) {
    this.est = { ...PADRAO, nome: nomePadrao, celulas: [] };
    try {
      const salvo = localStorage.getItem(`ipe.web.filme.${study}`);
      if (salvo) this.est = { ...this.est, ...(JSON.parse(salvo) as Partial<Estado>) };
    } catch { /* sem armazenamento */ }
    this.raiz.append(this.corpo);
    this.previa.onclick = (e) => this.cliqueNaPrevia(e);
    void this.carregarOpcoes();
  }

  private guardar(): void {
    try { localStorage.setItem(`ipe.web.filme.${this.study}`, JSON.stringify(this.est)); } catch { /* sem armazenamento */ }
  }

  private async carregarOpcoes(): Promise<void> {
    try {
      this.opcoes = (await (await pedir("/api/web/filme/opcoes")).json()) as Opcoes;
    } catch (e) {
      this.corpo.replaceChildren(el("div", { class: "erro" }, `${tr("Não consegui ler as opções de impressão")}: ${(e as Error).message}`));
      return;
    }
    this.desenhar();
  }

  get grade(): [number, number] {
    const [a, b] = this.est.layout.replace("x", "×").split("×").map(Number);
    return [Math.max(1, a || 1), Math.max(1, b || 1)];
  }

  get capacidade(): number { const [l, c] = this.grade; return l * c; }

  get folhas(): number { return Math.max(1, Math.ceil(this.est.celulas.length / this.capacidade)); }

  /** O filme no formato do Ipê (printing/film.Film). */
  filme(): Record<string, unknown> {
    const [rows, cols] = this.grade;
    const n = this.capacidade;
    const sheets = [];
    for (let f = 0; f < this.folhas; f++) {
      const cells: (CelulaFilme | null)[] = this.est.celulas.slice(f * n, (f + 1) * n);
      while (cells.length < n) cells.push(null);
      sheets.push({ rows, cols, paper: this.est.papel, landscape: this.est.paisagem, cells });
    }
    return { name: this.est.nome || tr("Filme sem nome"), sheets, overlay: this.est.textos, header: this.est.cabecalho,
      anonymize: this.est.anonimo, ruler: this.est.regua, black_page: this.est.preto };
  }

  // ---------------------------------------------------------------- montar
  adicionar(cels: CelulaFilme[]): void {
    if (!cels.length) return;
    this.est.celulas.push(...cels);
    this.folha = Math.floor((this.est.celulas.length - 1) / this.capacidade);
    this.mudou();
  }

  adicionarQuadro(i = this.g.ativo): string {
    const c = capturar(this.g, i);
    if (typeof c === "string") return c;
    this.adicionar([c]);
    return "";
  }

  adicionarTodos(): string {
    const cels: CelulaFilme[] = [];
    let motivo = "";
    this.g.quadros.forEach((_q, i) => {
      const c = capturar(this.g, i);
      if (typeof c === "string") motivo = motivo || c; else cels.push(c);
    });
    this.adicionar(cels);
    return cels.length ? "" : motivo;
  }

  /** A série do quadro ativo, uma imagem a cada `cada`, com o ajuste (janela, zoom…) do quadro. */
  adicionarSerie(cada: number): string {
    const base = capturar(this.g, this.g.ativo);
    if (typeof base === "string") return base;
    const q = this.g.quadros[this.g.ativo];
    const ids = q.serie?.imageIds || [];
    const cels: CelulaFilme[] = [];
    for (let k = 0; k < ids.length; k += Math.max(1, cada)) {
      const p = partesDoImageId(ids[k]);
      if (p) cels.push({ ...base, sop_uid: p.sop, frame_index: p.quadro - 1 });
    }
    this.adicionar(cels);
    return "";
  }

  private mudou(): void {
    this.guardar();
    this.desenhar();
  }

  // ---------------------------------------------------------------- prévia
  private pedirPrevia(): void {
    clearTimeout(this.relogio);
    if (!this.est.celulas.length) { this.previa.removeAttribute("src"); return; }
    const v = ++this.versao;
    this.relogio = window.setTimeout(async () => {
      try {
        const r = await pedir("/api/web/filme/previa", { film: this.filme(), folha: this.folha, dpi: 45 });
        const url = URL.createObjectURL(await r.blob());
        if (v !== this.versao) { URL.revokeObjectURL(url); return; }
        const velho = this.previa.src;
        this.previa.src = url;
        this.previa.dataset.folha = String(this.folha);
        if (velho.startsWith("blob:")) URL.revokeObjectURL(velho);
      } catch (e) {
        if (v === this.versao) this.nota.textContent = `${tr("Prévia")}: ${(e as Error).message}`;
      }
    }, 350);
  }

  private cliqueNaPrevia(e: MouseEvent): void {
    // a célula pela posição (as margens do Ipê: 5 mm; cabeçalho 11 mm e rodapé 5 mm)
    const r = this.previa.getBoundingClientRect();
    const tam = this.opcoes?.tamanhos?.[this.est.papel] || [210, 297];
    const [pw, ph] = this.est.paisagem ? [tam[1], tam[0]] : tam;
    const x = ((e.clientX - r.left) / r.width) * pw, y = ((e.clientY - r.top) / r.height) * ph;
    const topo = 5 + (this.est.cabecalho ? 11 : 0), baixo = 5 + (this.est.cabecalho ? 5 : 0);
    const [l, c] = this.grade;
    const col = Math.floor(((x - 5) / (pw - 10)) * c), lin = Math.floor(((y - topo) / (ph - topo - baixo)) * l);
    if (col < 0 || col >= c || lin < 0 || lin >= l) return;
    const k = this.folha * this.capacidade + lin * c + col;
    this.sel = k < this.est.celulas.length ? k : -1;
    this.desenhar();
  }

  // ---------------------------------------------------------------- imprimir
  private async imprimir(destino: string, folhas: number[]): Promise<void> {
    this.nota.textContent = tr("Desenhando as folhas…");
    try {
      if (destino === "baixar" || destino === "navegador") {
        const r = await pedir("/api/web/filme/pdf", { film: this.filme(), folhas, para: destino });
        const url = URL.createObjectURL(await r.blob());
        if (destino === "baixar") {
          const a = el("a", { href: url, download: `${(this.est.nome || "filme").replace(/[^\w\- ]+/g, "_")}.pdf` });
          document.body.append(a);
          a.click();
          a.remove();
          this.nota.textContent = tr("PDF baixado.");
        } else {
          // o PDF numa moldura escondida, e a janela de imprimir do navegador (as impressoras deste computador)
          const f = el("iframe", { class: "imprimir-filme", src: url, title: tr("Filme") });
          f.onload = () => { try { f.contentWindow?.focus(); f.contentWindow?.print(); } catch { window.open(url, "_blank"); } };
          document.body.append(f);
          setTimeout(() => f.remove(), 120000);
          this.nota.textContent = tr("Abrindo a janela de imprimir…");
        }
        return;
      }
      const r = (await (await pedir("/api/web/filme/imprimir", { film: this.filme(), destino, folhas })).json()) as { mensagem: string };
      this.nota.textContent = r.mensagem;
    } catch (e) {
      this.nota.textContent = `${tr("Não foi possível imprimir")}: ${(e as Error).message}`;
    }
  }

  // ---------------------------------------------------------------- desenho do painel
  desenhar(): void {
    const o = this.opcoes;
    if (!o) { this.corpo.replaceChildren(el("div", { class: "dica" }, tr("Carregando…"))); return; }
    const sel = (opcoes: [string, string][], atual: string, rotulo: string, mudar: (v: string) => void) => {
      const s = el("select", { "aria-label": tr(rotulo) });
      for (const [v, t] of opcoes) {
        const op = el("option", { value: v }, t);
        if (v === atual) op.selected = true;
        s.append(op);
      }
      s.onchange = () => mudar(s.value);
      return el("label", {}, `${tr(rotulo)} `, s);
    };
    const caixa = (rotulo: string, v: boolean, mudar: (b: boolean) => void) => {
      const c = el("input", { type: "checkbox" });
      c.checked = v;
      c.onchange = () => mudar(c.checked);
      return el("label", {}, c, ` ${tr(rotulo)}`);
    };
    const nome = el("input", { type: "text", "aria-label": tr("Nome do filme"), value: this.est.nome });
    nome.onchange = () => { this.est.nome = nome.value; this.guardar(); };
    const ajustes = el("div", { class: "ajustes-filme" },
      el("label", {}, `${tr("Nome")} `, nome),
      sel(o.layouts.map((l) => [l, l]), this.est.layout, "Grade", (v) => { this.est.layout = v; this.folha = 0; this.mudou(); }),
      sel(o.papeis.map((p) => [p, tr(p)]), this.est.papel, "Papel", (v) => { this.est.papel = v; this.mudou(); }),
      caixa("Paisagem", this.est.paisagem, (b) => { this.est.paisagem = b; this.mudou(); }),
      sel(Object.entries(o.textos).map(([k, t]) => [k, tr(t)]), this.est.textos, "Textos", (v) => { this.est.textos = v; this.mudou(); }),
      caixa("Cabeçalho com paciente e exame", this.est.cabecalho, (b) => { this.est.cabecalho = b; this.mudou(); }),
      caixa("Anonimizar", this.est.anonimo, (b) => { this.est.anonimo = b; this.mudou(); }),
      caixa("Régua", this.est.regua, (b) => { this.est.regua = b; this.mudou(); }),
      caixa("Fundo preto", this.est.preto, (b) => { this.est.preto = b; this.mudou(); }));

    const avisar = (m: string) => { this.nota.textContent = m; };
    const bQuadro = el("button", { type: "button" }, tr("+ Quadro ativo"));
    bQuadro.onclick = () => avisar(this.adicionarQuadro());
    const bTodos = el("button", { type: "button" }, tr("+ Todos os quadros"));
    bTodos.onclick = () => avisar(this.adicionarTodos());
    const cada = el("input", { type: "number", min: "1", value: "1", "aria-label": tr("A cada quantas imagens") });
    cada.style.width = "4em";
    const bSerie = el("button", { type: "button" }, tr("+ Série do quadro"));
    bSerie.onclick = () => avisar(this.adicionarSerie(Number(cada.value) || 1));
    const montar = el("div", { class: "montar-filme" }, bQuadro, bTodos,
      el("span", { class: "serie-cada" }, bSerie, ` ${tr("a cada")} `, cada));

    const n = this.est.celulas.length;
    this.folha = Math.min(this.folha, this.folhas - 1);
    const ant = el("button", { type: "button", class: "ic", "aria-label": tr("Folha anterior") }, "◂");
    ant.disabled = this.folha <= 0;
    ant.onclick = () => { this.folha--; this.desenhar(); };
    const prox = el("button", { type: "button", class: "ic", "aria-label": tr("Próxima folha") }, "▸");
    prox.disabled = this.folha >= this.folhas - 1;
    prox.onclick = () => { this.folha++; this.desenhar(); };
    const navega = el("div", { class: "folhas-filme" }, ant,
      el("span", { class: "contagem-filme" }, `${tr("Folha")} ${this.folha + 1}/${this.folhas} · ${n} ${tr("imagem(ns)")}`), prox);

    const acoesSel = el("div", { class: "selecao-filme" });
    if (this.sel >= 0 && this.sel < n) {
      const c = this.est.celulas[this.sel];
      const bVer = el("button", { type: "button" }, tr("Editar no quadro ativo"));
      bVer.onclick = async () => {
        const s = await this.serieDe(c.series_uid);
        if (!s) { avisar(tr("Esta série não está no exame aberto.")); return; }
        await aplicar(this.g, this.g.ativo, c, s);
        avisar(tr("Ajuste no quadro e clique em Atualizar a célula."));
      };
      const bAtual = el("button", { type: "button" }, tr("Atualizar a célula"));
      bAtual.onclick = () => {
        const nova = capturar(this.g, this.g.ativo);
        if (typeof nova === "string") { avisar(nova); return; }
        this.est.celulas[this.sel] = nova;
        this.mudou();
      };
      const mover = (d: number) => {
        const j = this.sel + d;
        if (j < 0 || j >= n) return;
        [this.est.celulas[this.sel], this.est.celulas[j]] = [this.est.celulas[j], this.est.celulas[this.sel]];
        this.sel = j;
        this.folha = Math.floor(j / this.capacidade);
        this.mudou();
      };
      const bAntes = el("button", { type: "button", "aria-label": tr("Mover para antes") }, "◂");
      bAntes.onclick = () => mover(-1);
      const bDepois = el("button", { type: "button", "aria-label": tr("Mover para depois") }, "▸");
      bDepois.onclick = () => mover(1);
      const bTirar = el("button", { type: "button", class: "perigo" }, tr("Remover"));
      bTirar.onclick = () => { this.est.celulas.splice(this.sel, 1); this.sel = -1; this.mudou(); };
      acoesSel.append(el("div", { class: "dica" }, `${tr("Célula")} ${this.sel + 1}: ${c.label || ""}`), bVer, bAtual, bAntes, bDepois, bTirar);
    } else if (n) {
      acoesSel.append(el("div", { class: "dica" }, tr("Clique numa célula da prévia para editar, mover ou remover.")));
    }
    const bLimpar = el("button", { type: "button", class: "link" }, tr("Limpar o filme"));
    bLimpar.onclick = () => { this.est.celulas = []; this.sel = -1; this.folha = 0; this.mudou(); };

    const destino = el("select", { "aria-label": tr("Saída") });
    const grupos = new Map<string, HTMLOptGroupElement>();
    for (const d of o.destinos) {
      let gr = grupos.get(d.grupo);
      if (!gr) { gr = el("optgroup", { label: tr(d.grupo) }); grupos.set(d.grupo, gr); destino.append(gr); }
      gr.append(el("option", { value: d.id }, tr(d.nome)));
    }
    const soEsta = el("input", { type: "checkbox" });
    const bImprimir = el("button", { type: "button", class: "primario" }, tr("Imprimir"));
    bImprimir.disabled = !n;
    bImprimir.onclick = async () => {
      bImprimir.disabled = true;
      await this.imprimir(destino.value, soEsta.checked ? [this.folha] : []);
      bImprimir.disabled = false;
    };
    const saida = el("div", { class: "saida-filme" }, el("label", {}, `${tr("Saída")} `, destino),
      el("label", {}, soEsta, ` ${tr("Só esta folha")}`), bImprimir);

    this.corpo.replaceChildren(
      el("div", { class: "titulo-painel" }, tr("Montar o filme")),
      el("div", { class: "dica" }, tr("Ajuste a imagem no quadro (janela, zoom, deslocamento, giro) e ponha no filme.")),
      montar, navega, n ? this.previa : el("div", { class: "previa-vazia" }, tr("O filme está vazio.")), acoesSel,
      el("div", { class: "titulo-painel" }, tr("Folha")), ajustes, bLimpar,
      el("div", { class: "titulo-painel" }, tr("Imprimir")), saida, this.nota);
    this.pedirPrevia();
  }
}
