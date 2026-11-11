// 0.100.2: o overlay do Ipê no navegador — o botão que liga e desliga o CAD/IA (SR), as anotações de outro
// sistema (GSPS), os contornos de radioterapia (RTSTRUCT), a SEG nas pilhas, os textos dos cantos, as medidas e as
// linhas de referência. O servidor lê os objetos com o mesmo leitor do Ipê (imaging/overlays.py) e manda tudo em
// pixels da imagem (o canto do pixel 0,0 em 0,0, como no Ipê e no Cornerstone3D); aqui só se desenha, numa camada
// por quadro de corte. O que o médico esconde por tipo fica lembrado (como o "viewer.cad_ia_oculto" do Ipê).
import { type Types, metaData, utilities as csUtils } from "@cornerstonejs/core";
import * as API from "./api";
import { tr } from "./i18n";
import { partesDoImageId } from "./meta";
import { medidasMostradas, mostrarMedidas } from "./medidas";
import { type ItemMenu, abrirMenu } from "./menu";
import { type Grade, linhasDeReferencia } from "./visor";

const CHAVE = "ipe.web.overlayOcultos";
const CHAVE_IA = "ipe.web.overlayIA";

function lerIA(): boolean {
  try { return localStorage.getItem(CHAVE_IA) !== "0"; } catch { return true; }
}

type Fatia = { r0: number; c0: number; h: number; w: number; dados: Uint8Array };

function lerOcultos(padrao: string[]): Set<string> {
  try {
    const v = localStorage.getItem(CHAVE);
    if (v !== null) return new Set(JSON.parse(v) as string[]);
  } catch { /* sem armazenamento */ }
  return new Set(padrao);
}

function gravarOcultos(s: Set<string>): void {
  try { localStorage.setItem(CHAVE, JSON.stringify([...s])); } catch { /* sem armazenamento */ }
}

function rgb(c: number[] | undefined, a = 1): string {
  const [r, g, b] = c && c.length >= 3 ? c : [255, 170, 60];
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

export class Overlay {
  dados: API.Overlays | null = null;
  /** os tipos (fonte) escondidos — lembrados de um exame para o outro */
  ocultos = new Set<string>();
  /** os objetos escondidos só neste exame */
  ocultosObj = new Set<string>();
  /** o interruptor geral (o botão): desligado, some todo o overlay da imagem */
  ligado = true;
  textos = true;
  private seg: { segmentos: API.MapaSeg["segmentos"]; fatias: Map<string, Fatia> } | null = null;
  segVisivel = true;
  /** 0.100.14: o CAD/IA (achados, segmentações, níveis) ligado ou não, sem mexer nos textos e nas medidas;
   *  lembrado de um exame para o outro */
  iaOn = lerIA();
  private bits = new Map<string, Uint8Array>();

  constructor(private g: Grade, private study: string, private aoMudar: () => void = () => {}) {
    g.aoDesenhar = (q) => this.desenhar(q);
  }

  async carregar(): Promise<void> {
    this.dados = await API.overlays(this.study).catch(() => null);
    this.ocultos = lerOcultos(this.dados?.ocultos || []);
    this.redesenhar();
    this.aoMudar();
  }

  get objetos(): API.ObjetoOv[] {
    return this.dados?.objetos || [];
  }

  tem(): boolean {
    return this.objetos.length > 0 || !!this.seg;
  }

  visivel(o: API.ObjetoOv): boolean {
    return this.ligado && this.iaOn && !this.ocultos.has(o.fonte) && !this.ocultosObj.has(o.chave);
  }

  /** O botão: liga ou desliga tudo o que está na imagem (CAD/IA, textos, medidas, linhas), como no Ipê. */
  alternar(): void {
    this.ligado = !this.ligado;
    this.aplicar();
  }

  private aplicar(): void {
    this.g.raiz.classList.toggle("sem-textos", !this.ligado || !this.textos);
    mostrarMedidas(this.ligado && this.medidasOn);
    this.g.ligarLinhas(this.ligado && this.linhasOn);
    this.redesenhar();
    this.aoMudar();
  }

  medidasOn = true;
  linhasOn = linhasDeReferencia();

  /** 0.100.14: liga ou desliga só o CAD/IA (o resto do overlay fica como está). */
  mostrarIA(on: boolean): void {
    this.iaOn = on;
    try { localStorage.setItem(CHAVE_IA, on ? "1" : "0"); } catch { /* sem armazenamento */ }
    if (on) this.ligado = true;
    this.aplicar();
  }

  mostrarTipo(tipo: string, on: boolean): void {
    if (on) this.ocultos.delete(tipo);
    else this.ocultos.add(tipo);
    gravarOcultos(this.ocultos);
    if (on) this.ligado = true;
    this.aplicar();
  }

  mostrarObjeto(chave: string, on: boolean): void {
    if (on) this.ocultosObj.delete(chave);
    else this.ocultosObj.add(chave);
    if (on) this.ligado = true;
    this.aplicar();
  }

  /** A SEG escolhida no menu de segmentação também nas pilhas (o mapa de rótulos da série de origem). */
  async usarSeg(segSerie: string): Promise<void> {
    if (!segSerie) {
      this.seg = null;
      this.redesenhar();
      return;
    }
    const m = await API.mapaSeg(this.study, segSerie);
    if (!m) return;
    const fatias = new Map<string, Fatia>();
    for (const f of m.fatias) fatias.set(f.sop, { r0: f.r0, c0: f.c0, h: f.h, w: f.w, dados: await API.descomprimir(f.dados) });
    this.seg = { segmentos: m.segmentos, fatias };
    this.redesenhar();
    this.aoMudar();
  }

  /** O menu da seta do botão: cada tipo e cada objeto, os textos, as medidas e as linhas de referência. */
  menu(ancora: HTMLElement): void {
    const tipos = [...new Set(this.objetos.map((o) => o.fonte))];
    const nomes = this.dados?.tipos || {};
    const itens: ItemMenu[] = [
      { rotulo: this.ligado ? tr("Ocultar todo o overlay") : tr("Mostrar o overlay"), acao: () => this.alternar() },
      { separador: true },
      { titulo: tr("Na imagem") },
      { rotulo: tr("CAD/IA (achados, segmentações, níveis)"), marcado: this.iaOn, acao: () => this.mostrarIA(!this.iaOn) },
      { rotulo: tr("Textos nos cantos"), marcado: this.textos, acao: () => { this.textos = !this.textos; this.aplicar(); } },
      { rotulo: tr("Medidas"), marcado: this.medidasOn, acao: () => { this.medidasOn = !this.medidasOn; this.aplicar(); } },
      { rotulo: tr("Linhas de referência"), marcado: this.linhasOn,
        acao: () => { this.linhasOn = !this.linhasOn; this.aplicar(); } },
    ];
    if (this.seg) {
      itens.push({ rotulo: tr("Segmentação (SEG)"), marcado: this.segVisivel,
        acao: () => { this.segVisivel = !this.segVisivel; this.redesenhar(); this.aoMudar(); } });
    }
    if (tipos.length) {
      itens.push({ separador: true }, { titulo: tr("CAD/IA e anotações") });
      for (const t of tipos) {
        itens.push({ rotulo: tr(nomes[t] || t), marcado: !this.ocultos.has(t), desligado: !this.iaOn,
          acao: () => this.mostrarTipo(t, this.ocultos.has(t)) });
      }
      const objs = this.objetos;
      if (objs.length > 1) {
        itens.push({ rotulo: tr("Objetos"), sub: objs.map((o) => ({
          rotulo: `${o.fonte}: ${o.rotulo || o.descricao}${o.achados.length ? ` (${o.achados.length})` : ""}`,
          marcado: !this.ocultosObj.has(o.chave), desligado: this.ocultos.has(o.fonte),
          acao: () => this.mostrarObjeto(o.chave, this.ocultosObj.has(o.chave)) })) });
      }
    } else {
      itens.push({ separador: true }, { titulo: tr("Sem CAD/IA neste exame") });
    }
    abrirMenu(itens, 0, 0, tr("Overlay"), ancora);
  }

  redesenhar(): void {
    for (const q of this.g.quadros) this.desenhar(q);
  }

  /** Desenha o overlay de um quadro de corte, por cima da imagem. */
  desenhar(q: Grade["quadros"][number]): void {
    const cel = q.el.parentElement;
    if (!cel) return;
    let c = cel.querySelector<HTMLCanvasElement>("canvas.camada-ov");
    const vp = q.tipo === "pilha" ? (this.g.viewport(this.g.quadros.indexOf(q)) as Types.IStackViewport | null) : null;
    const id = vp?.getCurrentImageId?.();
    // 0.100.14: no MPR (plano reconstruído) só os nomes em 3D (níveis da coluna, linfonodais)
    const vv = q.tipo === "plano" && this.objetos.some((o) => o.rotulos3d?.length)
      ? (this.g.viewport(this.g.quadros.indexOf(q)) as Types.IVolumeViewport | null) : null;
    const nada = !this.ligado || ((!vp || !id) && !vv?.getCamera);
    if (nada && !c) return;
    if (!c) {
      c = document.createElement("canvas");
      c.className = "camada-ov";
      q.el.after(c);
    }
    const ctx = c.getContext("2d")!;
    const w = q.el.clientWidth, h = q.el.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    c.dataset.desenhados = "0";
    if (nada) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!vp || !id) {
      const cam = vv!.getCamera();
      let n = 0;
      const usados: number[][] = [];
      if (cam.viewPlaneNormal && cam.focalPoint) {
        for (const o of this.objetos) {
          if (this.visivel(o) && o.rotulos3d?.length) n += this.rotulos(ctx, o.rotulos3d, cam.focalPoint, cam.viewPlaneNormal, vv!, usados);
        }
      }
      c.dataset.desenhados = String(n);
      return;
    }
    const p = partesDoImageId(id!);
    const sop = p?.sop || "";
    const quadro = (p?.quadro || 1) - 1;
    const tela = (x: number, y: number): Types.Point2 =>
      vp!.worldToCanvas(csUtils.imageToWorldCoords(id!, [x, y]) as Types.Point3);
    let n = 0;
    // a SEG da série (o mapa de rótulos), por baixo de tudo
    if (this.seg && this.segVisivel && this.iaOn) {
      const f = this.seg.fatias.get(sop);
      if (f) {
        this.pintarMascara(ctx, f, tela, (v) => this.seg!.segmentos.find((s) => s.n === v)?.cor);
        n++;
      }
    }
    const plano = metaData.get("imagePlaneModule", id!) as {
      imagePositionPatient: number[]; rowCosines: number[]; columnCosines: number[];
      rowPixelSpacing: number; columnPixelSpacing: number; sliceThickness?: number } | undefined;
    const usados: number[][] = [];
    for (const o of this.objetos) {
      if (!this.visivel(o)) continue;
      if (o.so_serie && p && o.so_serie !== p.series) continue;
      const gs = [...(o.por_sop[sop] || []).filter((g) => g.quadro === undefined || g.quadro === -1 || g.quadro === quadro), ...o.todos];
      for (const m of o.mascaras) {
        if (m.sop !== sop || (m.quadro !== -1 && m.quadro !== quadro)) continue;
        this.pintarMascara(ctx, { r0: m.r0, c0: m.c0, h: m.h, w: m.w, dados: this.desempacotar(m) }, tela, () => m.cor, m.escala);
        n++;
      }
      for (const g of gs) {
        this.tracar(ctx, g.tipo, g.pontos.map(([x, y]) => tela(x, y)), g.texto, g.cor || o.cor);
        n++;
      }
      // 0.100.14: nomes em 3D (níveis da coluna, linfonodais): no centro dos pontos que o plano corta
      if (plano && o.rotulos3d?.length) {
        const rc = plano.rowCosines, cc = plano.columnCosines;
        n += this.rotulos(ctx, o.rotulos3d, plano.imagePositionPatient,
          [rc[1] * cc[2] - rc[2] * cc[1], rc[2] * cc[0] - rc[0] * cc[2], rc[0] * cc[1] - rc[1] * cc[0]], vp!, usados);
      }
      // contornos 3D (RTSTRUCT, SR com coordenadas 3D): os que caem neste corte
      if (plano && o.planos.length) {
        const pos = plano.imagePositionPatient, rc = plano.rowCosines, cc = plano.columnCosines;
        const nrm = [rc[1] * cc[2] - rc[2] * cc[1], rc[2] * cc[0] - rc[0] * cc[2], rc[0] * cc[1] - rc[1] * cc[0]];
        const tol = Math.max((plano.sliceThickness || 1) / 2, 0.5);
        for (const g of o.planos) {
          const dist = g.pontos3d.reduce((s, q3) => s + Math.abs((q3[0] - pos[0]) * nrm[0] + (q3[1] - pos[1]) * nrm[1] + (q3[2] - pos[2]) * nrm[2]), 0)
            / Math.max(g.pontos3d.length, 1);
          if (dist > tol) continue;
          this.tracar(ctx, g.tipo, g.pontos3d.map((q3) => vp!.worldToCanvas(q3 as Types.Point3)), g.texto, g.cor || o.cor);
          n++;
        }
      }
    }
    c.dataset.desenhados = String(n);
  }

  /** Os nomes cujo volume o plano corta (como o Ipê: num sagital, todos os níveis; num axial, o do corte). Dois
   *  nomes no mesmo lugar: fica o primeiro. */
  private rotulos(ctx: CanvasRenderingContext2D, lista: NonNullable<API.ObjetoOv["rotulos3d"]>,
    pos: ArrayLike<number>, nrm: ArrayLike<number>, vp: { worldToCanvas: (p: Types.Point3) => Types.Point2 }, usados: number[][]): number {
    const tam = Math.max(11, Math.min(15, (ctx.canvas.clientWidth || 500) / 40));
    ctx.font = `bold ${tam}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    let n = 0;
    for (const r of lista) {
      let sx = 0, sy = 0, sz = 0, k = 0;
      for (const p3 of r.pontos) {
        const d = (p3[0] - pos[0]) * nrm[0] + (p3[1] - pos[1]) * nrm[1] + (p3[2] - pos[2]) * nrm[2];
        if (Math.abs(d) > r.tol) continue;
        sx += p3[0] - d * nrm[0]; sy += p3[1] - d * nrm[1]; sz += p3[2] - d * nrm[2];
        k++;
      }
      if (k < 2) continue;
      const [x, y] = vp.worldToCanvas([sx / k, sy / k, sz / k] as Types.Point3);
      const w = ctx.measureText(r.texto).width + 6, h = tam + 2;
      const caixa = [x - w / 2, y - h / 2, x + w / 2, y + h / 2];
      if (usados.some((u) => caixa[0] < u[2] && caixa[2] > u[0] && caixa[1] < u[3] && caixa[3] > u[1])) continue;
      usados.push(caixa);
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(0, 0, 0, 0.8)";
      ctx.strokeText(r.texto, x, y);
      ctx.fillStyle = rgb(r.cor);
      ctx.fillText(r.texto, x, y);
      n++;
    }
    return n;
  }

  private desempacotar(m: API.ObjetoOv["mascaras"][number]): Uint8Array {
    const k = `${m.sop}|${m.quadro}|${m.r0}|${m.c0}|${m.bits.length}|${m.bits.slice(0, 32)}`;
    let v = this.bits.get(k);
    if (!v) {
      const bin = Uint8Array.from(atob(m.bits), (ch) => ch.charCodeAt(0));
      v = new Uint8Array(m.h * m.w);
      for (let i = 0; i < v.length; i++) v[i] = (bin[i >> 3] >> (7 - (i & 7))) & 1;
      this.bits.set(k, v);
    }
    return v;
  }

  /** A máscara (valores por pixel) pintada transparente, na posição dela na imagem. */
  private pintarMascara(ctx: CanvasRenderingContext2D, f: Fatia, tela: (x: number, y: number) => Types.Point2,
    cor: (v: number) => number[] | undefined, escala?: number[]): void {
    const img = new ImageData(f.w, f.h);
    for (let i = 0; i < f.dados.length; i++) {
      const v = f.dados[i];
      if (!v) continue;
      const c = cor(v) || [255, 170, 60];
      img.data[i * 4] = c[0];
      img.data[i * 4 + 1] = c[1];
      img.data[i * 4 + 2] = c[2];
      img.data[i * 4 + 3] = 110;
    }
    const tmp = document.createElement("canvas");
    tmp.width = f.w;
    tmp.height = f.h;
    tmp.getContext("2d")!.putImageData(img, 0, 0);
    const [sy, sx] = escala || [1, 1];
    // três cantos da caixa na tela: a imagem pode estar girada ou espelhada
    const a = tela(f.c0 * sx, f.r0 * sy);
    const b = tela((f.c0 + f.w) * sx, f.r0 * sy);
    const d = tela(f.c0 * sx, (f.r0 + f.h) * sy);
    ctx.save();
    ctx.transform((b[0] - a[0]) / f.w, (b[1] - a[1]) / f.w, (d[0] - a[0]) / f.h, (d[1] - a[1]) / f.h, a[0], a[1]);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(tmp, 0, 0);
    ctx.restore();
  }

  private tracar(ctx: CanvasRenderingContext2D, tipo: string, pts: Types.Point2[], texto: string | undefined, cor: number[]): void {
    ctx.strokeStyle = rgb(cor);
    ctx.fillStyle = rgb(cor);
    ctx.lineWidth = 1.6;
    if (tipo === "point" || pts.length === 1) {
      for (const [x, y] of pts) {
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(x - 7, y); ctx.lineTo(x - 4, y); ctx.moveTo(x + 4, y); ctx.lineTo(x + 7, y);
        ctx.moveTo(x, y - 7); ctx.lineTo(x, y - 4); ctx.moveTo(x, y + 4); ctx.lineTo(x, y + 7);
        ctx.stroke();
      }
    } else if (tipo !== "text" && pts.length) {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (tipo === "polygon") ctx.closePath();
      ctx.stroke();
    }
    if (texto && pts.length) {
      const x = Math.max(...pts.map((p) => p[0])) + 6;
      const y = Math.min(...pts.map((p) => p[1]));
      ctx.font = "12px system-ui, sans-serif";
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(0, 0, 0, 0.8)";
      ctx.strokeText(texto, x, y + 10);
      ctx.fillText(texto, x, y + 10);
    }
  }

  estado(): Record<string, unknown> {
    return {
      ligado: this.ligado, textos: this.textos, medidas: medidasMostradas(), linhas: linhasDeReferencia(),
      ocultos: [...this.ocultos], objetos: this.objetos.map((o) => ({ chave: o.chave, fonte: o.fonte, rotulo: o.rotulo })),
      seg: !!this.seg,
      desenhados: this.g.quadros.map((q) => Number(q.el.parentElement?.querySelector<HTMLCanvasElement>("canvas.camada-ov")?.dataset.desenhados || 0)),
    };
  }
}
