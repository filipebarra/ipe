// Mamografia no navegador (0.99.98, W4): o protocolo do Ipê com uma ou duas telas.
//
// O servidor resolve o protocolo com as mesmas regras do Ipê (imaging/mammo.py): a imagem de cada quadro (do
// exame ou do anterior), para que lado vai a parede torácica, a caixa da mama e o mamilo. Aqui só se põe a
// câmera: espelhar quando a parede veio do lado errado, enquadrar a mama (o ar fica de fora), encostar a parede
// na borda e alinhar as duas mamas da linha pelo mamilo.
//
// Duas telas: a segunda é outra janela do navegador (no outro monitor quando o navegador deixa saber onde ele
// está), que recebe o token desta por mensagem — não pede a senha — e as duas mudam de etapa juntas por um
// BroadcastChannel.
import { type Types, utilities } from "@cornerstonejs/core";

import * as API from "./api";
import { tr } from "./i18n";
import { abrirMenu, icone } from "./menu";
import { type Grade, type SerieCarregada, type Spec, carregarSerie } from "./visor";

type V3 = [number, number, number];
type P2 = [number, number];

const CANAL = "ipe-mg";
const IC_MG = {
  antes: "M15 6l-6 6 6 6",
  depois: "M9 6l6 6-6 6",
  tomo: "M4 7h16M4 12h16M4 17h16",
  telas: "M2 5h9v12H2zM13 5h9v12h-9zM6 20h2M17 20h2",
  sair: "M6 6l12 12M18 6L6 18",
};

interface Celula {
  dado: API.CelulaMg;
  sop: string;
  pronto: boolean;
  /** 0.100.2: onde cada imagem começa na pilha do quadro (índice inicial e quantos quadros) */
  posicoes?: Map<string, [number, number]>;
}

function dataCurta(d: string): string {
  return d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : d;
}

/** "CC D (anterior)" do servidor, com as partes traduzidas. */
function rotuloDa(c: API.CelulaMg): string {
  let r = c.rotulo || c.codigo;
  r = r.replace(" (anterior)", ` (${tr("anterior")})`).replace(" recombinada", ` ${tr("recombinada")}`);
  return c.data ? `${r} · ${dataCurta(c.data)}` : r;
}

const series = new Map<string, Promise<SerieCarregada | null>>();

function serieDe(study: string, uid: string): Promise<SerieCarregada | null> {
  const k = `${study}|${uid}`;
  if (!series.has(k)) series.set(k, carregarSerie(study, uid));
  return series.get(k)!;
}

/** A pilha de um quadro: só os quadros (frames) desta imagem — a 2D tem um, a tomossíntese tem os cortes. */
async function pilhaDa(im: API.ImagemMg, rotulo: string): Promise<SerieCarregada | null> {
  const s = await serieDe(im.study, im.series);
  if (!s) return null;
  const ids = s.imageIds.filter((id) => id.includes(`/instances/${im.sop}/frames/`));
  if (!ids.length) return null;
  return { ...s, imageIds: ids, descricao: rotulo, semVolume: "mg", bytes: 0 };
}

/** 0.100.2: a pilha do quadro com todas as imagens da mesma incidência (2D e cortes da tomo), como no Ipê. */
async function pilhaAgrupada(membros: API.MembroMg[], rotulo: string):
    Promise<{ s: SerieCarregada; posicoes: Map<string, [number, number]> } | null> {
  const partes = await Promise.all(membros.map(async (m) => {
    const s = await serieDe(m.study, m.series);
    return s ? { s, ids: s.imageIds.filter((id) => id.includes(`/instances/${m.sop}/frames/`)) } : null;
  }));
  const ids: string[] = [];
  const posicoes = new Map<string, [number, number]>();
  let base: SerieCarregada | null = null;
  partes.forEach((p, k) => {
    if (!p || !p.ids.length) return;
    base = base ?? p.s;
    posicoes.set(membros[k].sop, [ids.length, p.ids.length]);
    ids.push(...p.ids);
  });
  if (!base || !ids.length) return null;
  return { s: { ...(base as SerieCarregada), series: `mg-${membros[0].sop}`, imageIds: ids, descricao: rotulo, semVolume: "mg", bytes: 0 },
    posicoes };
}

/** O corte em que a imagem começa: o meio da tomo, a própria 2D. */
function inicioNaPilha(posicoes: Map<string, [number, number]>, sop: string, tomo: boolean): number | undefined {
  const p = posicoes.get(sop);
  if (!p) return undefined;
  return p[0] + (tomo ? Math.floor(p[1] / 2) : 0);
}

function soma(a: Types.Point3, d: V3): Types.Point3 {
  return [a[0] + d[0], a[1] + d[1], a[2] + d[2]] as Types.Point3;
}

/** Move a imagem para o ponto do canvas `de` ir parar em `para`. */
function moverNoCanvas(vp: Types.IStackViewport, de: P2, para: P2): void {
  const a = vp.canvasToWorld(de as Types.Point2);
  const b = vp.canvasToWorld(para as Types.Point2);
  const d: V3 = [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cam = vp.getCamera();
  vp.setCamera({ focalPoint: soma(cam.focalPoint!, d), position: soma(cam.position!, d) });
}

function noCanvas(vp: Types.IStackViewport, imageId: string, x: number, y: number): P2 {
  const w = utilities.imageToWorldCoords(imageId, [x, y]);
  const c = vp.worldToCanvas(w as Types.Point3);
  return [c[0], c[1]];
}

/** Zoom que faz a caixa da mama ocupar o quadro, partindo do ajuste da imagem inteira (mammo.zoom_da_caixa). */
export function zoomDaCaixa(quadro: P2, imagem: P2, caixa: number[], margem: number): number {
  const [qw, qh] = quadro;
  const [w, h] = imagem;
  if (qw <= 0 || qh <= 0 || w <= 0 || h <= 0) return 1;
  const bw = Math.max(1, caixa[2] - caixa[0]);
  const bh = Math.max(1, caixa[3] - caixa[1]);
  const ajuste = Math.min(qw / w, qh / h);
  const folga = 1 + 2 * Math.max(0, margem);
  const z = Math.min(qw / (ajuste * bw * folga), qh / (ajuste * bh * folga));
  return Math.max(1, Math.min(8, z));
}

let canal: BroadcastChannel | null = null;
function canalMg(): BroadcastChannel | null {
  if (!canal && "BroadcastChannel" in window) canal = new BroadcastChannel(CANAL);
  return canal;
}

// a primeira janela entrega o token à segunda, que pede assim que abre
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin) return;
  const d = e.data as { tipo?: string };
  if (d?.tipo === "ipe-mg-pronto" && e.source && API.tokenAtual()) {
    (e.source as Window).postMessage({ tipo: "ipe-mg-token", token: API.tokenAtual() }, location.origin);
  }
});

/** Na segunda tela: pede o token à janela que a abriu. `false` se não veio (abrir a página à mão, por exemplo). */
export function pedirToken(): Promise<boolean> {
  return new Promise((ok) => {
    const mae = window.opener as Window | null;
    if (!mae) { ok(false); return; }
    const fim = setTimeout(() => { window.removeEventListener("message", ouvir); ok(false); }, 10000);
    const ouvir = (e: MessageEvent) => {
      if (e.origin !== location.origin || (e.data as { tipo?: string })?.tipo !== "ipe-mg-token") return;
      clearTimeout(fim);
      window.removeEventListener("message", ouvir);
      API.usarToken(String((e.data as { token: string }).token || ""));
      ok(!!API.tokenAtual());
    };
    window.addEventListener("message", ouvir);
    mae.postMessage({ tipo: "ipe-mg-pronto" }, location.origin);
  });
}

export interface OpcoesMg {
  study: string;
  /** 1 = a janela principal; 2 = a segunda tela */
  tela: 1 | 2;
  aviso: (m: string) => void;
  /** saiu do modo mamografia (a tela principal volta ao visualizador comum) */
  aoSair: () => void;
}

export class ModoMamografia {
  passo = 0;
  telas: 1 | 2;
  barra: HTMLElement;
  private celulas: Celula[] = [];
  private ampliado: number | null = null;
  private segunda: Window | null = null;
  private vigia = 0;
  private versao = 0;
  private rotuloEtapa: HTMLElement;
  private bTelas: HTMLButtonElement;
  private bTomo: HTMLButtonElement;
  private aoCanal = (e: MessageEvent) => this.mensagem(e.data);
  private aoRedimensionar = () => { clearTimeout(this.relogio); this.relogio = window.setTimeout(() => this.enquadrar(), 150); };
  private relogio = 0;
  private aoFechar = () => { if (this.op.tela === 2) canalMg()?.postMessage({ tipo: "fechou", study: this.op.study }); };

  constructor(private g: Grade, private dados: API.Mamografia, private op: OpcoesMg) {
    this.telas = op.tela === 2 ? 2 : 1;
    const bAntes = this.botao("Etapa anterior", IC_MG.antes, () => this.ir(this.passo - 1));
    const bDepois = this.botao("Próxima etapa", IC_MG.depois, () => this.ir(this.passo + 1));
    this.rotuloEtapa = document.createElement("span");
    const bEtapa = document.createElement("button");
    bEtapa.type = "button";
    bEtapa.className = "etapa";
    bEtapa.title = tr("Escolher a etapa");
    bEtapa.append(this.rotuloEtapa);
    bEtapa.onclick = () => abrirMenu(this.dados.passos.map((p, i) => ({
      rotulo: `${i + 1}. ${tr(p.nome)}`, marcado: i === this.passo, acao: () => this.ir(i) })), 0, 0, tr("Etapas"), bEtapa);
    const bProto = document.createElement("button");
    bProto.type = "button";
    bProto.className = "protocolo";
    bProto.textContent = tr(dados.protocolo || "");
    bProto.title = tr("Protocolo de mamografia");
    bProto.onclick = () => abrirMenu(this.dados.protocolos.map((n, i) => ({
      rotulo: tr(n), marcado: i === this.dados.indice, acao: () => void this.trocarProtocolo(i) })), 0, 0, tr("Protocolo de mamografia"), bProto);
    this.bTomo = this.botao("Tomossíntese do quadro", IC_MG.tomo, () => void this.alternarTomo());
    this.bTelas = this.botao(op.tela === 2 ? "Fechar esta tela" : "Duas telas", IC_MG.telas, () => void this.alternarTelas());
    const bSair = this.botao("Sair do modo mamografia", IC_MG.sair, () => this.sair());
    if (op.tela === 2) bSair.hidden = true;
    const nota = document.createElement("span");
    nota.className = "nota-mg";
    nota.textContent = op.tela === 2 ? tr("Segunda tela") : "";
    nota.title = tr("A leitura no navegador depende do monitor: use um monitor calibrado (DICOM GSDF) para laudar.");
    const titulo = document.createElement("strong");
    titulo.textContent = tr("Mamografia");
    this.barra = document.createElement("div");
    this.barra.className = "barra-mg";
    this.barra.setAttribute("role", "toolbar");
    this.barra.setAttribute("aria-label", tr("Mamografia"));
    this.barra.append(titulo, bProto, bAntes, bEtapa, bDepois, this.bTomo, this.bTelas, nota, bSair);
    g.raiz.classList.add("mg");
    canalMg()?.addEventListener("message", this.aoCanal);
    window.addEventListener("resize", this.aoRedimensionar);
    window.addEventListener("pagehide", this.aoFechar);
    (window as unknown as Record<string, unknown>).__ipeMg = this; // testes
  }

  private botao(rotulo: string, d: string, fn: () => void): HTMLButtonElement {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ic";
    b.title = tr(rotulo);
    b.setAttribute("aria-label", tr(rotulo));
    b.append(icone(d, 18));
    b.onclick = fn;
    return b;
  }

  /** O índice desta janela entre as telas (0 = a principal). */
  private get indice(): number {
    return this.telas === 2 ? this.op.tela - 1 : 0;
  }

  ir(i: number, avisar = true): void {
    const n = this.dados.passos.length;
    if (!n) return;
    this.passo = ((i % n) + n) % n;
    if (avisar) canalMg()?.postMessage({ tipo: "passo", study: this.op.study, passo: this.passo, telas: this.telas });
    void this.aplicar();
  }

  private mensagem(m: { tipo?: string; study?: string; passo?: number; telas?: number; indice?: number }): void {
    if (!m || m.study !== this.op.study) return;
    if (m.tipo === "passo" && typeof m.passo === "number") {
      this.passo = m.passo;
      void this.aplicar();
    } else if (m.tipo === "fechou" && this.op.tela === 1 && this.telas === 2) {
      this.segunda = null;
      this.telas = 1;
      void this.aplicar();
    } else if (m.tipo === "fim" && this.op.tela === 2) {
      window.close();
    } else if (m.tipo === "protocolo" && typeof m.indice === "number" && m.indice !== this.dados.indice) {
      void this.trocarProtocolo(m.indice, false);
    } else if (m.tipo === "oi" && this.op.tela === 1) {
      // a segunda acabou de abrir: diz em que etapa estamos
      canalMg()?.postMessage({ tipo: "passo", study: this.op.study, passo: this.passo, telas: this.telas });
    }
  }

  async trocarProtocolo(i: number, avisar = true): Promise<void> {
    const d = await API.mamografia(this.op.study, i);
    if (!d) return;
    this.dados = d;
    (this.barra.querySelector("button.protocolo") as HTMLElement).textContent = tr(d.protocolo || "");
    if (avisar) canalMg()?.postMessage({ tipo: "protocolo", study: this.op.study, indice: i });
    this.passo = 0;
    void this.aplicar();
  }

  /** Monta a etapa nesta janela: a grade da tela, a imagem de cada quadro e o enquadramento. */
  async aplicar(): Promise<void> {
    const versao = ++this.versao;
    const passo = this.dados.passos[this.passo];
    if (!passo) return;
    const telas = passo.telas[String(this.telas)] || passo.telas["1"];
    const tela = telas[Math.min(this.indice, telas.length - 1)];
    this.rotuloEtapa.textContent = `${this.passo + 1}/${this.dados.passos.length} · ${tr(passo.nome)}`;
    this.bTelas.classList.toggle("ligado", this.telas === 2);
    this.ampliado = null;
    this.g.raiz.style.removeProperty("grid-template-columns");
    const vazios: Spec[] = Array.from({ length: tela.rows * tela.cols }, () =>
      ({ serie: null, tipo: "pilha", plano: "AXIAL", projecao: "fino", espessura: 0 }));
    this.g.montar(tela.rows, tela.cols, vazios);
    this.celulas = tela.celulas.slice(0, tela.rows * tela.cols).map((c) => ({ dado: c, sop: c.sop || "", pronto: false }));
    this.g.quadros.forEach((q, i) => {
      const cel = q.el.parentElement!;
      cel.addEventListener("dblclick", () => this.ampliar(i));
      const c = this.celulas[i];
      if (c && !c.sop) {
        const nota = document.createElement("div");
        nota.className = "nota-quadro";
        const n = (c.dado.nota || "").replace(c.dado.rotulo || "\u0000", rotuloDa(c.dado));
        nota.textContent = n.replace("não encontrada", tr("não encontrada"))
          .replace("(sem exame anterior)", `(${tr("sem exame anterior")})`)
          .replace("(quadro vazio no protocolo)", `(${tr("quadro vazio no protocolo")})`)
          .replace("código inválido", tr("código inválido"));
        cel.append(nota);
      }
    });
    await Promise.all(this.celulas.map((c, i) => this.carregar(i, c, versao)));
    if (versao !== this.versao) return;
    this.enquadrar();
    this.atualizarTomo();
    this.g.ativar(0);
  }

  private async carregar(i: number, c: Celula, versao: number): Promise<void> {
    if (!c.sop) return;
    const im = this.dados.imagens[c.sop];
    if (im && c.dado.pilha && c.dado.pilha.length > 1) {
      const ag = await pilhaAgrupada(c.dado.pilha, rotuloDa(c.dado));
      if (versao !== this.versao) return;
      if (ag && ag.posicoes.has(c.sop)) {
        c.posicoes = ag.posicoes;
        await this.g.mostrar(i, ag.s, inicioNaPilha(ag.posicoes, c.sop, im.tomo));
        return;
      }
    }
    const s = im ? await pilhaDa(im, rotuloDa(c.dado)) : null;
    if (versao !== this.versao) return;
    if (!s) {
      this.op.aviso(tr("Não consegui abrir uma das imagens da etapa."));
      return;
    }
    await this.g.mostrar(i, s);
  }

  private vp(i: number): Types.IStackViewport | null {
    return (this.g.viewport(i) as Types.IStackViewport) || null;
  }

  /** Espelha, enquadra a mama, encosta a parede torácica e alinha pelo mamilo os quadros mostrados. */
  enquadrar(): void {
    const passo = this.dados.passos[this.passo];
    const modo = passo?.enquadre || "mama";
    const mostrados = this.celulas.map((c, i) => i).filter((i) => this.celulas[i].sop && (this.ampliado === null || this.ampliado === i));
    const zooms = new Map<number, number>();
    for (const i of mostrados) {
      const c = this.celulas[i];
      const im = this.dados.imagens[c.sop];
      const vp = this.vp(i);
      const id = vp?.getCurrentImageId();
      if (!vp || !id || !im) continue;
      vp.resetCamera();
      const quer = c.dado.quer || null;
      const espelhar = !!(this.dados.espelhar && quer && im.parede && im.parede !== quer);
      vp.setCamera({ flipHorizontal: espelhar });
      const cw = vp.canvas.clientWidth;
      const ch = vp.canvas.clientHeight;
      const w = im.largura || 1;
      const h = im.altura || 1;
      // o ajuste de agora (pixels da tela por pixel da imagem), medido em vez de suposto
      const a = noCanvas(vp, id, 0, 0);
      const b = noCanvas(vp, id, w, 0);
      const ajuste = Math.abs(b[0] - a[0]) / w || Math.min(cw / w, ch / h);
      if (modo === "pixel") zooms.set(i, 1 / ajuste);
      else if (modo === "mama" && im.caixa) zooms.set(i, zoomDaCaixa([cw, ch], [w, h], im.caixa, this.dados.margem));
      else zooms.set(i, 1);
    }
    const valores = [...zooms.values()];
    const comum = modo === "mama" && this.dados.zoom_junto && valores.length ? Math.min(...valores) : null;
    for (const [i, z0] of zooms) {
      const c = this.celulas[i];
      const im = this.dados.imagens[c.sop];
      const vp = this.vp(i)!;
      const id = vp.getCurrentImageId()!;
      if (modo !== "imagem") vp.setZoom(comum ?? z0);
      if (modo === "mama" && im.caixa) {
        const [x0, y0, x1, y1] = im.caixa;
        const ix = im.parede === "right" ? x1 : x0;
        const iy = (y0 + y1) / 2;
        // a parede encostada na borda do lado dela, sem folga: é ali que mora o alinhamento da mamografia
        const espelhado = !!vp.getCamera().flipHorizontal;
        const naTela = im.parede ? (espelhado ? (im.parede === "left" ? "right" : "left") : im.parede) : (c.dado.quer || "left");
        const lado = this.dados.encostar && c.dado.quer ? c.dado.quer : naTela;
        const cw = vp.canvas.clientWidth;
        const ch = vp.canvas.clientHeight;
        moverNoCanvas(vp, noCanvas(vp, id, ix, iy), [lado === "right" ? cw : 0, ch / 2]);
      }
      vp.render();
    }
    // na mesma linha da tela, os mamilos na mesma altura (a média)
    if (modo === "mama" && this.dados.alinhar === "mamilo" && this.ampliado === null) {
      const linhas = new Map<number, number[]>();
      for (const i of zooms.keys()) {
        const r = Math.floor(i / this.g.colunas);
        linhas.set(r, [...(linhas.get(r) || []), i]);
      }
      for (const grupo of linhas.values()) {
        const ys = grupo.map((i) => {
          const im = this.dados.imagens[this.celulas[i].sop];
          const vp = this.vp(i)!;
          return im.mamilo ? { i, vp, p: noCanvas(vp, vp.getCurrentImageId()!, im.mamilo[0], im.mamilo[1]) } : null;
        }).filter((x): x is { i: number; vp: Types.IStackViewport; p: P2 } => !!x);
        if (ys.length < 2) continue;
        const alvo = ys.reduce((s, x) => s + x.p[1], 0) / ys.length;
        for (const { vp, p } of ys) {
          moverNoCanvas(vp, p, [p[0], alvo]);
          vp.render();
        }
      }
    }
    for (const i of zooms.keys()) this.celulas[i].pronto = true;
  }

  ampliar(i: number): void {
    const cels = this.g.quadros.map((q) => q.el.parentElement as HTMLElement);
    if (this.ampliado === i) {
      this.ampliado = null;
      cels.forEach((c) => { c.style.display = ""; });
      this.g.raiz.style.gridTemplateColumns = `repeat(${this.g.colunas}, 1fr)`;
      this.g.raiz.style.gridTemplateRows = `repeat(${this.g.linhas}, 1fr)`;
    } else {
      this.ampliado = i;
      cels.forEach((c, k) => { c.style.display = k === i ? "" : "none"; });
      this.g.raiz.style.gridTemplateColumns = "1fr";
      this.g.raiz.style.gridTemplateRows = "1fr";
    }
    this.g.ativar(i);
    requestAnimationFrame(() => {
      this.g.redimensionar();
      this.enquadrar();
    });
  }

  private atualizarTomo(): void {
    const c = this.celulas[this.g.ativo];
    this.bTomo.disabled = !c?.dado.alt;
    const im = c ? this.dados.imagens[c.sop] : undefined;
    this.bTomo.classList.toggle("ligado", !!im?.tomo);
  }

  /** Atualiza o botão da tomossíntese ao trocar de quadro ativo. */
  quadroAtivo(): void {
    this.atualizarTomo();
  }

  /** A tomossíntese da mesma incidência no quadro ativo (ou a 2D de volta). */
  async alternarTomo(): Promise<void> {
    const i = this.g.ativo;
    const c = this.celulas[i];
    if (!c?.dado.alt) return;
    c.sop = c.sop === c.dado.sop ? c.dado.alt : c.dado.sop!;
    c.pronto = false;
    // na pilha agrupada, a 2D e a tomo já estão no mesmo quadro: só pula para lá
    const vp = this.vp(i);
    const ini = c.posicoes ? inicioNaPilha(c.posicoes, c.sop, !!this.dados.imagens[c.sop]?.tomo) : undefined;
    if (vp && ini !== undefined) await vp.setImageIdIndex(ini);
    else await this.carregar(i, c, this.versao);
    this.enquadrar();
    this.atualizarTomo();
  }

  async alternarTelas(): Promise<void> {
    if (this.op.tela === 2) {
      window.close();
      return;
    }
    if (this.telas === 2) {
      canalMg()?.postMessage({ tipo: "fim", study: this.op.study });
      this.segunda?.close();
      this.segunda = null;
      this.telas = 1;
      void this.aplicar();
      return;
    }
    const url = `${location.origin}${location.pathname}#/mg/${this.op.study}/2`;
    const w = window.open(url, "ipe-mg-2", `popup,width=${screen.availWidth},height=${screen.availHeight}`);
    if (!w) {
      this.op.aviso(tr("O navegador bloqueou a segunda janela: permita janelas deste endereço."));
      return;
    }
    this.segunda = w;
    this.telas = 2;
    void this.moverParaOutroMonitor(w);
    clearInterval(this.vigia);
    this.vigia = window.setInterval(() => {
      if (this.segunda && this.segunda.closed) {
        this.segunda = null;
        clearInterval(this.vigia);
        if (this.telas === 2) {
          this.telas = 1;
          void this.aplicar();
        }
      }
    }, 1000);
    canalMg()?.postMessage({ tipo: "passo", study: this.op.study, passo: this.passo, telas: 2 });
    void this.aplicar();
  }

  /** Com a API de várias telas do navegador (Window Management), leva a segunda janela ao outro monitor. */
  private async moverParaOutroMonitor(w: Window): Promise<void> {
    type Tela = { availLeft: number; availTop: number; availWidth: number; availHeight: number };
    const pedir = (window as unknown as { getScreenDetails?: () => Promise<{ screens: Tela[]; currentScreen: Tela }> }).getScreenDetails;
    if (!pedir) return;
    try {
      const sd = await Promise.race([pedir.call(window), new Promise<null>((r) => setTimeout(() => r(null), 3000))]);
      const outra = sd?.screens.find((s) => s !== sd.currentScreen);
      if (!outra) return;
      w.moveTo(outra.availLeft, outra.availTop);
      w.resizeTo(outra.availWidth, outra.availHeight);
    } catch {
      /* sem permissão: a janela fica onde abriu, e o médico a arrasta */
    }
  }

  /** Para os testes: o que cada quadro mostra e como ficou a câmera. */
  estado(): Record<string, unknown> {
    return {
      passo: this.passo, nome: this.dados.passos[this.passo]?.nome, telas: this.telas, tela: this.op.tela,
      quadros: this.celulas.map((c, i) => {
        const im = this.dados.imagens[c.sop];
        const vp = this.vp(i);
        const id = vp?.getCurrentImageId();
        const base: Record<string, unknown> = { codigo: c.dado.codigo, sop: c.sop, study: im?.study, pronto: c.pronto || !c.sop };
        if (!vp || !id || !im) return base;
        const cw = vp.canvas.clientWidth;
        const ch = vp.canvas.clientHeight;
        const a = noCanvas(vp, id, 0, 0);
        const b = noCanvas(vp, id, 1, 0);
        const ix = im.caixa ? (im.parede === "right" ? im.caixa[2] : im.caixa[0]) : 0;
        const iy = im.caixa ? (im.caixa[1] + im.caixa[3]) / 2 : 0;
        return { ...base, espelhado: !!vp.getCamera().flipHorizontal, zoom: vp.getZoom(),
          escala: Math.hypot(b[0] - a[0], b[1] - a[1]), parede_x: noCanvas(vp, id, ix, iy)[0] / cw,
          mamilo_y: im.mamilo ? noCanvas(vp, id, im.mamilo[0], im.mamilo[1])[1] / ch : null,
          cortes: vp.getImageIds().length, corte: vp.getCurrentImageIdIndex() };
      }),
    };
  }

  sair(): void {
    this.encerrar();
    this.op.aoSair();
  }

  /** Deixa o modo: fecha a segunda tela e solta os ouvintes. */
  encerrar(): void {
    if (this.op.tela === 1) {
      canalMg()?.postMessage({ tipo: "fim", study: this.op.study });
      this.segunda?.close();
    }
    clearInterval(this.vigia);
    canalMg()?.removeEventListener("message", this.aoCanal);
    window.removeEventListener("resize", this.aoRedimensionar);
    window.removeEventListener("pagehide", this.aoFechar);
    this.g.raiz.classList.remove("mg");
    this.barra.remove();
    this.versao++;
  }

  /** Na segunda tela: avisa a principal que abriu, para receber a etapa de agora. */
  anunciar(): void {
    canalMg()?.postMessage({ tipo: "oi", study: this.op.study });
  }
}
