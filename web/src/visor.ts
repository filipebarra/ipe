// Quadros 2D (W0): Cornerstone3D com o carregador WADO-RS do servidor central.
// Botões do mouse como no Ipê: esquerdo = a ferramenta escolhida (janela por padrão), meio = mover,
// direito = zoom, roda = rolar os cortes. Nenhum atalho de teclado de fábrica.

import {
  Enums,
  RenderingEngine,
  init as csInit,
  metaData,
  setUseCPURendering,
  type Types,
} from "@cornerstonejs/core";
import { init as loaderInit, wadors } from "@cornerstonejs/dicom-image-loader";
import * as csTools from "@cornerstonejs/tools";

import { DICOMWEB, cabecalhos, metadados, valor, type DicomJson } from "./api";
import { tr } from "./i18n";

const { PanTool, ZoomTool, WindowLevelTool, StackScrollTool, ToolGroupManager, Enums: TE } = csTools;
const MB = TE.MouseBindings;

const RE_ID = "ipe";
const TG_ID = "ipe-2d";
let iniciado = false;
let motor: RenderingEngine | null = null;

export type Ferramenta = "janela" | "mover" | "zoom" | "rolar";
const NOME: Record<Ferramenta, string> = {
  janela: WindowLevelTool.toolName,
  mover: PanTool.toolName,
  zoom: ZoomTool.toolName,
  rolar: StackScrollTool.toolName,
};

export async function iniciar(): Promise<void> {
  if (iniciado) return;
  const gl = document.createElement("canvas").getContext("webgl2");
  csInit();
  if (!gl) setUseCPURendering(true); // sem WebGL 2: o 2D ainda funciona pela CPU
  loaderInit({
    maxWebWorkers: Math.max(1, Math.min(4, Math.floor((navigator.hardwareConcurrency || 2) / 2))),
    beforeSend: () => cabecalhos(),
  });
  // O carregador WADO-RS lê a função da VOI LUT como lista e pega a primeira letra do texto ("SIGMOID" → "S"):
  // a mamografia da GE (sigmoide) ficava toda branca. Este provedor, consultado antes, devolve a lista.
  metaData.addProvider((tipo: string, imageId: string) => {
    if (tipo !== "voiLutModule") return undefined;
    const m = META.get(imageId);
    if (!m) return undefined;
    const nums = (tag: string) => ((m[tag]?.Value as unknown[]) || []).map(Number).filter((x) => !Number.isNaN(x));
    const fn = String(valor(m, "00281056") ?? "").trim().toUpperCase();
    return { windowCenter: nums("00281050"), windowWidth: nums("00281051"), voiLUTFunction: fn ? [fn] : undefined };
  }, 10000);
  csTools.init();
  for (const t of [PanTool, ZoomTool, WindowLevelTool, StackScrollTool]) csTools.addTool(t);
  const tg = ToolGroupManager.createToolGroup(TG_ID)!;
  for (const t of [PanTool, ZoomTool, WindowLevelTool, StackScrollTool]) tg.addTool(t.toolName);
  aplicarBotoes("janela");
  motor = new RenderingEngine(RE_ID);
  iniciado = true;
}

/** O botão esquerdo vira a ferramenta `f`; meio = mover, direito = zoom e a roda = rolar continuam. */
export function aplicarBotoes(f: Ferramenta): void {
  const tg = ToolGroupManager.getToolGroup(TG_ID);
  if (!tg) return;
  const fixos: Record<string, number[]> = {
    [PanTool.toolName]: [MB.Auxiliary],
    [ZoomTool.toolName]: [MB.Secondary],
    [StackScrollTool.toolName]: [MB.Wheel],
    [WindowLevelTool.toolName]: [],
  };
  fixos[NOME[f]] = [...fixos[NOME[f]], MB.Primary];
  for (const [nome, botoes] of Object.entries(fixos)) {
    if (botoes.length) {
      tg.setToolActive(nome, { bindings: botoes.map((b) => ({ mouseButton: b })) });
    } else {
      tg.setToolPassive(nome);
    }
  }
}

// ------------------------------------------------------------------ séries -> imageIds
const META = new Map<string, DicomJson>();

export interface SerieCarregada {
  study: string;
  series: string;
  imageIds: string[];
  modalidade: string;
  descricao: string;
  numero: string;
}

function ordem(m: DicomJson): number {
  const ipp = m["00200032"]?.Value as number[] | undefined;
  const iop = m["00200037"]?.Value as number[] | undefined;
  if (ipp && iop && ipp.length === 3 && iop.length === 6) {
    const [a, b, c, d, e, f] = iop.map(Number);
    const n = [b * f - c * e, c * d - a * f, a * e - b * d];
    return n[0] * ipp[0] + n[1] * ipp[1] + n[2] * ipp[2];
  }
  return Number(valor(m, "00200013") ?? 0);
}

export async function carregarSerie(study: string, series: string): Promise<SerieCarregada | null> {
  const meta = await metadados(study, series);
  if (!meta.length) return null;
  const temPosicao = meta.every((m) => m["00200032"]?.Value && m["00200037"]?.Value);
  const ordenados = [...meta].sort((a, b) =>
    temPosicao ? ordem(a) - ordem(b) : Number(valor(a, "00200013") ?? 0) - Number(valor(b, "00200013") ?? 0));
  const ids: string[] = [];
  for (const m of ordenados) {
    const sop = String(valor(m, "00080018") ?? "");
    const quadros = Math.max(1, Number(valor(m, "00280008") ?? 1));
    for (let q = 1; q <= quadros; q++) {
      const id = `wadors:${DICOMWEB}/studies/${study}/series/${series}/instances/${sop}/frames/${q}`;
      wadors.metaDataManager.add(id, m as never);
      META.set(id, m);
      ids.push(id);
    }
  }
  const m0 = ordenados[0];
  return {
    study, series, imageIds: ids,
    modalidade: String(valor(m0, "00080060") ?? ""),
    descricao: String(valor(m0, "0008103E") ?? ""),
    numero: String(valor(m0, "00200011") ?? ""),
  };
}

// ------------------------------------------------------------------ os quadros
export interface Quadro {
  id: string;
  el: HTMLDivElement;
  textos: HTMLDivElement;
  serie: SerieCarregada | null;
}

export class Grade {
  quadros: Quadro[] = [];
  ativo = 0;
  linhas = 1;
  colunas = 1;
  paciente = "";
  aoMudar: () => void = () => {};

  constructor(public raiz: HTMLElement) {}

  montar(linhas: number, colunas: number): void {
    const antigas = this.quadros.map((q) => q.serie);
    if (motor) for (const q of this.quadros) {
      try {
        csTools.utilities.cine.stopClip(q.el);
      } catch { /* nada tocando */ }
    }
    this.raiz.innerHTML = "";
    this.raiz.style.gridTemplateColumns = `repeat(${colunas}, 1fr)`;
    this.raiz.style.gridTemplateRows = `repeat(${linhas}, 1fr)`;
    this.linhas = linhas;
    this.colunas = colunas;
    const tg = ToolGroupManager.getToolGroup(TG_ID)!;
    for (const q of this.quadros) {
      try {
        tg.removeViewports(RE_ID, q.id);
      } catch { /* já saiu */ }
    }
    this.quadros = [];
    const entradas: Types.PublicViewportInput[] = [];
    for (let i = 0; i < linhas * colunas; i++) {
      const cel = document.createElement("div");
      cel.className = "quadro";
      const el = document.createElement("div");
      el.className = "tela";
      el.oncontextmenu = (e) => e.preventDefault();
      const textos = document.createElement("div");
      textos.className = "textos";
      cel.append(el, textos);
      cel.addEventListener("mousedown", () => this.ativar(i), true);
      this.raiz.append(cel);
      const id = `q${i}`;
      this.quadros.push({ id, el, textos, serie: null });
      entradas.push({ viewportId: id, type: Enums.ViewportType.STACK, element: el,
        defaultOptions: { background: [0, 0, 0] as Types.Point3 } });
    }
    motor!.setViewports(entradas);
    for (const q of this.quadros) {
      tg.addViewport(q.id, RE_ID);
      for (const ev of [Enums.Events.IMAGE_RENDERED, Enums.Events.VOI_MODIFIED, Enums.Events.STACK_NEW_IMAGE]) {
        q.el.addEventListener(ev, () => this.escreverTextos(q));
      }
    }
    this.ativo = Math.min(this.ativo, this.quadros.length - 1);
    this.marcarAtivo();
    // as séries que já estavam voltam aos mesmos lugares
    antigas.forEach((s, i) => { if (s && i < this.quadros.length) void this.mostrar(i, s); });
  }

  ativar(i: number): void {
    this.ativo = i;
    this.marcarAtivo();
    this.aoMudar();
  }

  marcarAtivo(): void {
    this.quadros.forEach((q, i) => q.el.parentElement!.classList.toggle("ativo", i === this.ativo));
  }

  viewport(i = this.ativo): Types.IStackViewport | null {
    const q = this.quadros[i];
    return q ? (motor!.getViewport(q.id) as Types.IStackViewport) : null;
  }

  async mostrar(i: number, s: SerieCarregada): Promise<void> {
    const q = this.quadros[i];
    if (!q) return;
    q.serie = s;
    const vp = this.viewport(i)!;
    const meio = Math.floor(s.imageIds.length / 2);
    await vp.setStack(s.imageIds, s.imageIds.length > 2 ? meio : 0);
    vp.render();
    this.escreverTextos(q);
  }

  escreverTextos(q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IStackViewport | undefined;
    if (!vp || !q.serie) {
      q.textos.innerHTML = "";
      return;
    }
    const n = vp.getCurrentImageIdIndex() + 1;
    const tot = q.serie.imageIds.length;
    const p = vp.getProperties();
    let jan = "";
    if (p.voiRange) {
      const ww = p.voiRange.upper - p.voiRange.lower;
      const wl = (p.voiRange.upper + p.voiRange.lower) / 2;
      jan = `${tr("Janela").charAt(0)} ${Math.round(ww)} / ${Math.round(wl)}`;
    }
    const zoom = (() => { try { return `${Math.round(vp.getZoom() * 100)}%`; } catch { return ""; } })();
    q.textos.innerHTML = "";
    const canto = (cls: string, linhas: string[]) => {
      const d = document.createElement("div");
      d.className = `canto ${cls}`;
      d.textContent = linhas.filter(Boolean).join("\n");
      q.textos.append(d);
    };
    canto("se", [this.paciente]);
    canto("sd", [`${tr("Se")} ${q.serie.numero} ${q.serie.modalidade}`.trim(), q.serie.descricao]);
    canto("ie", [`${tr("Im")} ${n} / ${tot}`, zoom]);
    canto("id", [jan, p.invert ? tr("Inverter") : ""]);
  }

  // -------------------------------------------------------------- comandos da barra
  janela(largura: number, nivel: number): void {
    const vp = this.viewport();
    if (!vp) return;
    vp.setProperties({ voiRange: { lower: nivel - largura / 2, upper: nivel + largura / 2 } });
    vp.render();
  }

  janelaDoArquivo(): void {
    const vp = this.viewport();
    if (!vp) return;
    vp.resetProperties();
    vp.render();
  }

  inverter(): void {
    const vp = this.viewport();
    if (!vp) return;
    vp.setProperties({ invert: !vp.getProperties().invert });
    vp.render();
  }

  restaurar(): void {
    const vp = this.viewport();
    if (!vp) return;
    vp.resetCamera();
    vp.resetProperties();
    vp.render();
  }

  cine(fps: number | null): void {
    const q = this.quadros[this.ativo];
    if (!q || !q.serie) return;
    if (fps === null) {
      csTools.utilities.cine.stopClip(q.el);
    } else {
      csTools.utilities.cine.playClip(q.el, { framesPerSecond: fps, loop: true });
    }
  }

  redimensionar(): void {
    motor?.resize(true, true);
  }

  desmontar(): void {
    for (const q of this.quadros) {
      try { csTools.utilities.cine.stopClip(q.el); } catch { /* nada */ }
    }
    const tg = ToolGroupManager.getToolGroup(TG_ID);
    for (const q of this.quadros) {
      try { tg?.removeViewports(RE_ID, q.id); } catch { /* nada */ }
      try { motor?.disableElement(q.id); } catch { /* nada */ }
    }
    this.quadros = [];
    this.raiz.innerHTML = "";
  }
}
