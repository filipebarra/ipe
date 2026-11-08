// Quadros do visualizador web: pilha 2D (W0) e volume (W1: MPR, oblíquo, espessura, MIP girando).
// Cornerstone3D com o carregador WADO-RS do servidor central.
// Botões do mouse como no Ipê: esquerdo = a ferramenta escolhida, meio = mover, direito = zoom, roda = rolar os
// cortes (no MIP, a roda gira). Nenhum atalho de teclado de fábrica.

import {
  Enums,
  RenderingEngine,
  cache,
  cornerstoneStreamingImageVolumeLoader,
  init as csInit,
  metaData,
  setUseCPURendering,
  setVolumesForViewports,
  utilities as csUtils,
  volumeLoader,
  type Types,
} from "@cornerstonejs/core";
import { init as loaderInit, wadors } from "@cornerstonejs/dicom-image-loader";
import * as csTools from "@cornerstonejs/tools";

import { DICOMWEB, cabecalhos, fatorSuv, metadados, valor, type DicomJson } from "./api";
import { tr } from "./i18n";
import { FERRAMENTA_DA_ESCOLHA, adicionarFerramentas, carregarMedidas, ouvirAnotacoes, selecionarAoClicar } from "./medidas";
import { META } from "./meta";
import {
  COR_PADRAO, RAIO_MAXIMO_MM, SUV, SUV_PADRAO, carregarSeg, esquecerSegs, maximoPerto, mostrarSeg,
  propriedadesDaFusao, registrarEscalaSuv, tirarSeg, type SegCarregada,
} from "./pet";

const {
  PanTool, ZoomTool, WindowLevelTool, StackScrollTool, CrosshairsTool, MIPJumpToClickTool, ToolGroupManager,
  Enums: TE,
} = csTools;
const MB = TE.MouseBindings;

const RE_ID = "ipe";
const TG_2D = "ipe-2d";
const TG_VOL = "ipe-vol";
const TG_MIP = "ipe-mip";
/** volumes acima disto (bytes) não são montados: a placa de vídeo comum não aguenta */
export const LIMITE_VOLUME = 1.5 * 1024 ** 3;
let iniciado = false;
let ferramentaAtual: Ferramenta = "janela";
let motor: RenderingEngine | null = null;

export type Ferramenta = "janela" | "mover" | "zoom" | "rolar" | "linhas" | "regua" | "angulo" | "cobb" | "elipse"
  | "retangulo" | "poligono" | "pixel" | "seta" | "calibracao" | "suvmax";
export type Plano = "AXIAL" | "CORONAL" | "SAGITTAL";
export type Projecao = "fino" | "mip" | "minip" | "media";
const NOME: Record<string, string> = {
  janela: WindowLevelTool.toolName,
  mover: PanTool.toolName,
  zoom: ZoomTool.toolName,
  rolar: StackScrollTool.toolName,
  ...FERRAMENTA_DA_ESCOLHA,
};

export async function iniciar(): Promise<void> {
  if (iniciado) return;
  const gl = document.createElement("canvas").getContext("webgl2");
  csInit();
  if (!gl) setUseCPURendering(true); // sem WebGL 2: o 2D ainda funciona pela CPU (o volume não)
  loaderInit({
    maxWebWorkers: Math.max(1, Math.min(4, Math.floor((navigator.hardwareConcurrency || 2) / 2))),
    beforeSend: () => cabecalhos(),
  });
  volumeLoader.registerUnknownVolumeLoader(cornerstoneStreamingImageVolumeLoader as never);
  volumeLoader.registerVolumeLoader("cornerstoneStreamingImageVolume", cornerstoneStreamingImageVolumeLoader as never);
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
  registrarEscalaSuv(); // W3: o PET chega em SUV (o fator é o do Ipê, pedido ao servidor)
  csTools.init();
  for (const t of [PanTool, ZoomTool, WindowLevelTool, StackScrollTool, CrosshairsTool, MIPJumpToClickTool]) {
    csTools.addTool(t);
  }
  const t2 = ToolGroupManager.createToolGroup(TG_2D)!;
  const tv = ToolGroupManager.createToolGroup(TG_VOL)!;
  const tm = ToolGroupManager.createToolGroup(TG_MIP)!;
  for (const tg of [t2, tv, tm]) {
    for (const t of [PanTool, ZoomTool, WindowLevelTool, StackScrollTool]) tg.addTool(t.toolName);
  }
  tv.addTool(CrosshairsTool.toolName, {
    getReferenceLineColor: (id: string) => ({ q0: "rgb(240, 90, 80)", q1: "rgb(80, 200, 120)",
      q2: "rgb(80, 160, 250)", q3: "rgb(230, 200, 60)" } as Record<string, string>)[id] || "rgb(230, 200, 60)",
    getReferenceLineControllable: () => true,
    getReferenceLineDraggableRotatable: () => true,
    getReferenceLineSlabThicknessControlsOn: () => false,
  });
  tm.addTool(MIPJumpToClickTool.toolName, { targetViewportIds: [] });
  adicionarFerramentas([t2, tv]); // W2: medidas (na pilha vão para o banco; no MPR, só na sessão)
  ouvirAnotacoes();
  aplicarBotoes("janela");
  motor = new RenderingEngine(RE_ID);
  (window as unknown as Record<string, unknown>).__ipeGeo = { planoPorDoisPontos, girarVetor }; // testes
  (window as unknown as Record<string, unknown>).__ipeCs = { imageToWorldCoords: csUtils.imageToWorldCoords, cache,
    segmentation: csTools.segmentation };
  iniciado = true;
}

/** O botão esquerdo vira a ferramenta `f` (nos quadros de volume, "linhas" = a cruz das linhas de referência);
 * meio = mover, direito = zoom e a roda = rolar continuam. No MIP, o esquerdo leva os cortes ao ponto mais claro. */
export function aplicarBotoes(f: Ferramenta): void {
  ferramentaAtual = f;
  for (const id of [TG_2D, TG_VOL, TG_MIP]) {
    const tg = ToolGroupManager.getToolGroup(id);
    if (!tg) continue;
    const fixos: Record<string, number[]> = {
      [PanTool.toolName]: [MB.Auxiliary],
      [ZoomTool.toolName]: [MB.Secondary],
      [StackScrollTool.toolName]: id === TG_MIP ? [] : [MB.Wheel],
      [WindowLevelTool.toolName]: [],
    };
    if (id === TG_VOL) fixos[CrosshairsTool.toolName] = [];
    if (id !== TG_MIP) for (const nome of Object.values(FERRAMENTA_DA_ESCOLHA)) fixos[nome] = [];
    if (id === TG_MIP) {
      fixos[MIPJumpToClickTool.toolName] = [MB.Primary];
    } else if (f === "suvmax") {
      // o clique é tratado pela grade (procura o SUV máximo perto do ponto); nenhuma ferramenta no esquerdo
    } else if (f === "linhas") {
      if (id === TG_VOL) fixos[CrosshairsTool.toolName].push(MB.Primary);
      else fixos[WindowLevelTool.toolName].push(MB.Primary);
    } else {
      fixos[NOME[f]].push(MB.Primary);
    }
    for (const [nome, botoes] of Object.entries(fixos)) {
      if (botoes.length) tg.setToolActive(nome, { bindings: botoes.map((b) => ({ mouseButton: b })) });
      else tg.setToolPassive(nome);
    }
  }
}

// ------------------------------------------------------------------ séries -> imageIds

export interface SerieCarregada {
  study: string;
  series: string;
  imageIds: string[];
  modalidade: string;
  descricao: string;
  numero: string;
  /** "" se dá para montar o volume; senão, o motivo */
  semVolume: string;
  bytes: number;
  /** W3: fator de SUV (PET com peso, dose e horários); null se não é PET ou falta dado */
  suv: number | null;
  suvMotivo: string;
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

/** Dá para montar o volume? Pelo menos 3 cortes, todos com posição, a mesma orientação e o mesmo tamanho. */
function motivoSemVolume(meta: DicomJson[]): string {
  if (meta.length < 3) return tr("a série tem poucos cortes para o volume");
  if (meta.some((m) => Number(valor(m, "00280008") ?? 1) > 1)) return tr("série de vários quadros num arquivo (sem volume por enquanto)");
  if (!meta.every((m) => m["00200032"]?.Value && m["00200037"]?.Value)) return tr("a série não tem a posição dos cortes");
  const iop0 = (meta[0]["00200037"].Value as number[]).map(Number);
  const tam0 = `${valor(meta[0], "00280010")}x${valor(meta[0], "00280011")}`;
  for (const m of meta) {
    const iop = (m["00200037"].Value as number[]).map(Number);
    if (iop.some((v, k) => Math.abs(v - iop0[k]) > 1e-3)) return tr("os cortes não têm a mesma orientação");
    if (`${valor(m, "00280010")}x${valor(m, "00280011")}` !== tam0) return tr("os cortes não têm o mesmo tamanho");
  }
  return "";
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
  const modalidade = String(valor(m0, "00080060") ?? "").toUpperCase();
  let suv: number | null = null;
  let suvMotivo = "";
  if (modalidade === "PT") {
    // antes de qualquer imagem chegar: o carregador pede o fator (scalingModule) ao montar cada uma
    const r = await fatorSuv(study, series).catch(() => ({ fator: null, motivo: "" }));
    suv = r.fator && r.fator > 0 ? r.fator : null;
    suvMotivo = r.motivo;
    if (suv) SUV.set(series, suv);
  }
  const bytes = ids.length * Number(valor(m0, "00280010") ?? 0) * Number(valor(m0, "00280011") ?? 0) * 4;
  return {
    study, series, imageIds: ids,
    modalidade: String(valor(m0, "00080060") ?? ""),
    suv, suvMotivo,
    descricao: String(valor(m0, "0008103E") ?? ""),
    numero: String(valor(m0, "00200011") ?? ""),
    semVolume: motivoSemVolume(ordenados),
    bytes,
  };
}

export async function volumeDa(s: SerieCarregada): Promise<string> {
  const id = `cornerstoneStreamingImageVolume:${s.series}`;
  if (!cache.getVolume(id)) {
    const v = await volumeLoader.createAndCacheVolume(id, { imageIds: s.imageIds });
    (v as unknown as { load: () => void }).load();
  }
  return id;
}

// ------------------------------------------------------------------ geometria
type V3 = [number, number, number];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: V3): V3 => mul(a, 1 / (Math.hypot(...a) || 1));

/** Gira o vetor `v` em torno do eixo unitário `k` por `ang` radianos (Rodrigues). */
export function girarVetor(v: V3, k: V3, ang: number): V3 {
  const c = Math.cos(ang), s = Math.sin(ang);
  return add(add(mul(v, c), mul(cross(k, v), s)), mul(k, dot(k, v) * (1 - c)));
}

/** O plano oblíquo por dois pontos (como o "oblíquo" do Ipê): contém a reta p0→p1 e a normal do plano onde ela
 * foi desenhada. Devolve a normal do plano novo e o "para cima" (a normal antiga). */
export function planoPorDoisPontos(p0: V3, p1: V3, normalAtual: V3): { normal: V3; cima: V3 } {
  const d = norm(sub(p1, p0));
  return { normal: norm(cross(d, normalAtual)), cima: norm(normalAtual) };
}

/** Nome do plano pela normal: axial, coronal, sagital ou oblíquo. */
export function nomeDoPlano(n: V3): string {
  const a = n.map((x) => Math.abs(x));
  const k = a.indexOf(Math.max(...a));
  if (a[k] < 0.985) return tr("Oblíquo");
  return [tr("Sagital"), tr("Coronal"), tr("Axial")][k];
}

// ------------------------------------------------------------------ os quadros
export type Tipo = "pilha" | "plano" | "mip";

export interface Quadro {
  id: string;
  el: HTMLDivElement;
  textos: HTMLDivElement;
  botoes: HTMLDivElement;
  serie: SerieCarregada | null;
  tipo: Tipo;
  plano: Plano;
  projecao: Projecao;
  espessura: number;
  girando: number | null;
  /** W3: a série sobreposta (o PET da fusão), com a tabela, a opacidade e o topo da janela de SUV */
  sobre: SerieCarregada | null;
  cor: string;
  opacidade: number;
  suvMax: number;
  /** o último SUV máximo achado perto do cursor neste quadro */
  achado: string;
}

interface Spec {
  serie: SerieCarregada | null; tipo: Tipo; plano: Plano; projecao: Projecao; espessura: number;
  sobre?: SerieCarregada | null; cor?: string; opacidade?: number; suvMax?: number;
}

export class Grade {
  quadros: Quadro[] = [];
  ativo = 0;
  linhas = 1;
  colunas = 1;
  paciente = "";
  aoMudar: () => void = () => {};
  aviso: (msg: string) => void = () => {};

  constructor(public raiz: HTMLElement) {}

  /** Monta os quadros. `specs` (opcional) diz o que vai em cada um; sem ele, ficam as séries de antes. */
  montar(linhas: number, colunas: number, specs?: Spec[]): void {
    const antigas: Spec[] = specs ?? this.quadros.map((q) => this.specDe(q));
    this.desmontar(false);
    this.raiz.style.gridTemplateColumns = `repeat(${colunas}, 1fr)`;
    this.raiz.style.gridTemplateRows = `repeat(${linhas}, 1fr)`;
    this.linhas = linhas;
    this.colunas = colunas;
    const entradas: Types.PublicViewportInput[] = [];
    for (let i = 0; i < linhas * colunas; i++) {
      const sp = antigas[i];
      const tipo: Tipo = sp?.tipo ?? "pilha";
      const cel = document.createElement("div");
      cel.className = "quadro";
      const el = document.createElement("div");
      el.className = "tela";
      el.oncontextmenu = (e) => e.preventDefault();
      selecionarAoClicar(el);
      const textos = document.createElement("div");
      textos.className = "textos";
      const botoes = document.createElement("div");
      botoes.className = "planos";
      cel.append(el, textos, botoes);
      cel.addEventListener("mousedown", () => this.ativar(i), true);
      this.raiz.append(cel);
      const id = `q${i}`;
      const q: Quadro = { id, el, textos, botoes, serie: null, tipo, plano: sp?.plano ?? "AXIAL",
        projecao: sp?.projecao ?? "fino", espessura: sp?.espessura ?? 0, girando: null,
        sobre: tipo === "plano" ? sp?.sobre ?? null : null, cor: sp?.cor ?? COR_PADRAO, opacidade: sp?.opacidade ?? 0.5,
        suvMax: sp?.suvMax ?? SUV_PADRAO, achado: "" };
      el.addEventListener("mousedown", (e) => this.cliqueSuvMax(e, q), true);
      this.quadros.push(q);
      entradas.push(tipo === "pilha"
        ? { viewportId: id, type: Enums.ViewportType.STACK, element: el,
          defaultOptions: { background: [0, 0, 0] as Types.Point3 } }
        : { viewportId: id, type: Enums.ViewportType.ORTHOGRAPHIC, element: el,
          defaultOptions: { background: [0, 0, 0] as Types.Point3,
            orientation: (tipo === "mip" ? Enums.OrientationAxis.CORONAL
              : Enums.OrientationAxis[q.plano]) as Enums.OrientationAxis } });
      this.botoesDePlano(q, i);
      if (tipo === "mip") {
        el.addEventListener("wheel", (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.girarMip(i, (e.deltaY > 0 ? 1 : -1) * (Math.PI / 36));
        }, { capture: true, passive: false });
      }
    }
    motor!.setViewports(entradas);
    for (const q of this.quadros) {
      ToolGroupManager.getToolGroup(q.tipo === "pilha" ? TG_2D : q.tipo === "mip" ? TG_MIP : TG_VOL)!
        .addViewport(q.id, RE_ID);
      for (const ev of [Enums.Events.IMAGE_RENDERED, Enums.Events.VOI_MODIFIED, Enums.Events.STACK_NEW_IMAGE,
        Enums.Events.VOLUME_NEW_IMAGE, Enums.Events.CAMERA_MODIFIED]) {
        q.el.addEventListener(ev, () => this.escreverTextos(q));
      }
    }
    this.configurarMip();
    this.sincronizar();
    this.ativo = Math.min(this.ativo, this.quadros.length - 1);
    this.marcarAtivo();
    antigas.forEach((s, i) => { if (s?.serie && i < this.quadros.length) void this.mostrar(i, s.serie); });
  }

  private botoesDePlano(q: Quadro, i: number): void {
    q.botoes.replaceChildren();
    const opcoes: [string, () => void][] = [
      [tr("Original"), () => this.mudarPlano(i, null)],
      ["A", () => this.mudarPlano(i, "AXIAL")],
      ["C", () => this.mudarPlano(i, "CORONAL")],
      ["S", () => this.mudarPlano(i, "SAGITTAL")],
      ["MIP", () => this.mudarParaMip(i)],
    ];
    const ativo = q.tipo === "pilha" ? tr("Original") : q.tipo === "mip" ? "MIP" : q.plano[0];
    for (const [txt, fn] of opcoes) {
      const b = document.createElement("button");
      b.textContent = txt;
      b.title = { A: tr("Axial"), C: tr("Coronal"), S: tr("Sagital"), MIP: tr("MIP girando (clique leva os cortes ao ponto mais claro)") }[txt] || tr("Os cortes como foram adquiridos");
      if (txt === ativo) b.classList.add("ligado");
      b.onclick = (e) => { e.stopPropagation(); this.ativar(i); fn(); };
      q.botoes.append(b);
    }
  }

  ativar(i: number): void {
    this.ativo = i;
    this.marcarAtivo();
    this.aoMudar();
  }

  marcarAtivo(): void {
    this.quadros.forEach((q, i) => q.el.parentElement!.classList.toggle("ativo", i === this.ativo));
  }

  viewport(i = this.ativo): Types.IViewport | null {
    const q = this.quadros[i];
    return q ? motor!.getViewport(q.id) : null;
  }

  private volumeOk(s: SerieCarregada): boolean {
    if (s.semVolume) {
      this.aviso(`${tr("Sem volume:")} ${s.semVolume}.`);
      return false;
    }
    if (s.bytes > LIMITE_VOLUME) {
      this.aviso(tr("Série grande demais para o volume no navegador (mais de 1,5 GB)."));
      return false;
    }
    return true;
  }

  async mostrar(i: number, s: SerieCarregada): Promise<void> {
    const q = this.quadros[i];
    if (!q) return;
    if (q.tipo !== "pilha" && !this.volumeOk(s)) {
      // sem volume: o quadro volta a ser pilha
      this.especificar(i, { serie: s, tipo: "pilha", plano: q.plano, projecao: "fino", espessura: 0 });
      return;
    }
    q.serie = s;
    const vp = this.viewport(i)!;
    if (q.tipo === "pilha") {
      const pilha = vp as Types.IStackViewport;
      const meio = Math.floor(s.imageIds.length / 2);
      await pilha.setStack(s.imageIds, s.imageIds.length > 2 ? meio : 0);
      // a grade pode ter sido refeita enquanto a imagem carregava: a câmera é ajustada ao tamanho de agora
      pilha.resetCamera();
      pilha.render();
      void carregarMedidas(s.study, s.series, s.imageIds, q.el); // as medidas do banco (feitas aqui ou no Ipê)
    } else {
      const vid = await volumeDa(s);
      const vols = [{ volumeId: vid }];
      if (q.sobre && q.tipo === "plano") {
        if (this.volumeOk(q.sobre)) vols.push({ volumeId: await volumeDa(q.sobre) });
        else q.sobre = null;
      }
      await setVolumesForViewports(motor!, vols, [q.id]);
      this.aplicarProjecao(q);
      const v = vp as Types.IVolumeViewport;
      if (q.sobre) {
        // a fusão: a TC embaixo em partes moles, o PET em cima com a tabela do Ipê e o que é baixo transparente
        if (s.modalidade === "CT") v.setProperties({ voiRange: { lower: -160, upper: 240 } }, vid);
        this.aplicarFusao(q);
      } else if (s.suv && q.tipo === "plano") {
        v.setProperties({ voiRange: { lower: 0, upper: q.suvMax }, invert: true });
      }
      if (q.tipo === "mip") {
        this.configurarMip();
        // a janela do MIP: na TC, larga (o MIP só tem o que é claro); no PET/MN, invertido como no Ipê
        if (s.modalidade === "CT") v.setProperties({ voiRange: { lower: -350, upper: 1150 } });
        else if (s.suv) v.setProperties({ voiRange: { lower: 0, upper: q.suvMax }, invert: true });
        else if (s.modalidade === "PT" || s.modalidade === "NM") v.setProperties({ invert: true });
      }
      v.render();
      this.reporSeg();
    }
    this.escreverTextos(q);
  }

  private specDe(q: Quadro): Spec {
    return { serie: q.serie, tipo: q.tipo, plano: q.plano, projecao: q.projecao, espessura: q.espessura,
      sobre: q.sobre, cor: q.cor, opacidade: q.opacidade, suvMax: q.suvMax };
  }

  /** Troca o que vai no quadro i (pode mudar o tipo do quadro: refaz a grade com as mesmas séries). */
  especificar(i: number, sp: Spec): void {
    const specs: Spec[] = this.quadros.map((q) => this.specDe(q));
    specs[i] = sp;
    this.montar(this.linhas, this.colunas, specs);
  }

  /** Mudar o plano com um clique: A, C, S (volume) ou o original (pilha). */
  mudarPlano(i: number, plano: Plano | null): void {
    const q = this.quadros[i];
    if (!q?.serie) return;
    if (plano === null) {
      if (q.tipo !== "pilha") this.especificar(i, { serie: q.serie, tipo: "pilha", plano: q.plano, projecao: "fino", espessura: 0 });
      return;
    }
    if (!this.volumeOk(q.serie)) return;
    if (q.tipo === "plano") {
      q.plano = plano;
      const vp = this.viewport(i) as Types.IVolumeViewport;
      vp.setOrientation(Enums.OrientationAxis[plano] as Enums.OrientationAxis);
      this.aplicarProjecao(q);
      vp.render();
      this.botoesDePlano(q, i);
      this.escreverTextos(q);
      return;
    }
    this.especificar(i, { serie: q.serie, tipo: "plano", plano, projecao: q.projecao, espessura: q.espessura,
      cor: q.cor, opacidade: q.opacidade, suvMax: q.suvMax });
  }

  mudarParaMip(i: number): void {
    const q = this.quadros[i];
    if (!q?.serie || !this.volumeOk(q.sobre ?? q.serie)) return;
    // a fusão vira o MIP do PET (o MIP da TC embaixo não diz nada)
    const s = q.sobre ?? q.serie;
    this.especificar(i, { serie: s, tipo: "mip", plano: q.plano, projecao: "mip", espessura: 0, suvMax: q.suvMax });
  }

  /** O MPR da série do quadro ativo: axial, coronal, sagital e o MIP girando, com as linhas de referência. */
  abrirMPR(): boolean {
    const s = this.quadros[this.ativo]?.serie;
    if (!s || !this.volumeOk(s)) return false;
    const sp = (tipo: Tipo, plano: Plano): Spec => ({ serie: s, tipo, plano, projecao: tipo === "mip" ? "mip" : "fino", espessura: 0 });
    this.ativo = 0;
    this.montar(2, 2, [sp("plano", "AXIAL"), sp("plano", "CORONAL"), sp("plano", "SAGITTAL"), sp("mip", "CORONAL")]);
    return true;
  }

  // -------------------------------------------------------------- PET/CT (W3)
  /** A leitura de PET como na 0.99.88 do Ipê: fusão (TC + PET), PET em cinza invertido e o MIP do PET; o clique no
   * MIP leva os cortes ao ponto mais claro e os dois axiais andam juntos. */
  abrirPETCT(tc: SerieCarregada, pet: SerieCarregada): boolean {
    if (!this.volumeOk(tc) || !this.volumeOk(pet)) return false;
    const base = { projecao: "fino" as Projecao, espessura: 0, plano: "AXIAL" as Plano };
    this.ativo = 0;
    this.montar(1, 3, [{ ...base, serie: tc, sobre: pet, tipo: "plano" }, { ...base, serie: pet, tipo: "plano" },
      { ...base, serie: pet, tipo: "mip", projecao: "mip" }]);
    return true;
  }

  private sobreDe(q: Quadro): SerieCarregada | null {
    return q.sobre ?? null;
  }

  /** O volume em SUV que o quadro mostra (o PET da fusão, ou o próprio PET). */
  private volumePetDe(q: Quadro): string | null {
    const s = this.sobreDe(q) ?? (q.serie?.modalidade === "PT" ? q.serie : null);
    return s ? `cornerstoneStreamingImageVolume:${s.series}` : null;
  }

  private aplicarFusao(q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    if (!vp || !q.sobre) return;
    const id = `cornerstoneStreamingImageVolume:${q.sobre.series}`;
    // sem o fator de SUV a janela fica nos valores da série (Bq/ml): o topo vem do arquivo
    const topo = q.sobre.suv ? q.suvMax : undefined;
    const p = propriedadesDaFusao(q.cor, q.opacidade, topo ?? 1);
    if (topo === undefined) delete (p as { voiRange?: unknown }).voiRange;
    try { vp.setProperties(p, id); } catch { /* o volume ainda não chegou: o mostrar aplica */ }
    this.amostrarFusao(q);
  }

  /** O PET de cima é traçado por raios dentro da fatia do corte: com o passo padrão (do tamanho do voxel do PET)
   * o raio quase não pega amostra numa fatia fina e a fusão some. Passo bem curto, e a opacidade medida na
   * espessura da fatia — assim a opacidade escolhida é a que aparece. */
  private amostrarFusao(q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    if (!vp || !q.sobre) return;
    const id = `cornerstoneStreamingImageVolume:${q.sobre.series}`;
    const ator = vp.getActors().find((a) => a.referencedId === id)?.actor as unknown as {
      getMapper: () => { setSampleDistance: (d: number) => void };
      getProperty: () => { setScalarOpacityUnitDistance: (i: number, d: number) => void };
    } | undefined;
    if (!ator) return;
    let fatia = 0.05;
    try { fatia = Math.max(vp.getSlabThickness() || 0.05, 0.05); } catch { /* padrão */ }
    ator.getMapper().setSampleDistance(Math.min(0.02, fatia / 3));
    ator.getProperty().setScalarOpacityUnitDistance(0, fatia);
  }

  /** Muda a fusão do quadro ativo (ou de todos, se o ativo não tem fusão): tabela, opacidade e topo do SUV. */
  fusao(o: { cor?: string; opacidade?: number; suvMax?: number }): boolean {
    const alvos = this.quadros[this.ativo]?.sobre ? [this.quadros[this.ativo]] : this.quadros.filter((q) => q.sobre);
    const pets = o.suvMax !== undefined ? this.quadros.filter((q) => !q.sobre && q.serie?.suv && q.tipo !== "pilha") : [];
    if (!alvos.length && !pets.length) {
      this.aviso(tr("Abra a fusão PET/CT antes (botão PET/CT)."));
      return false;
    }
    for (const q of alvos) {
      if (o.cor) q.cor = o.cor;
      if (o.opacidade !== undefined) q.opacidade = o.opacidade;
      if (o.suvMax !== undefined) q.suvMax = o.suvMax;
      this.aplicarFusao(q);
      motor?.getViewport(q.id)?.render();
      this.escreverTextos(q);
    }
    for (const q of pets) {
      q.suvMax = o.suvMax!;
      const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
      try {
        vp?.setProperties({ voiRange: { lower: 0, upper: q.suvMax } });
        vp?.render();
      } catch { /* o volume ainda não chegou: o mostrar usa o topo novo */ }
      this.escreverTextos(q);
    }
    return true;
  }

  private sincronizador: { destroy: () => void } | null = null;

  /** Os quadros de volume no mesmo plano (a fusão e o PET) andam juntos: corte, zoom e posição. */
  private sincronizar(): void {
    try { this.sincronizador?.destroy(); } catch { /* nada */ }
    this.sincronizador = null;
    const planos = this.quadros.filter((q) => q.tipo === "plano");
    if (planos.length < 2 || !this.quadros.some((q) => q.sobre)) return;
    const sync = csTools.synchronizers.createCameraPositionSynchronizer(`ipe-camera-${Date.now()}`);
    for (const q of planos) sync.add({ renderingEngineId: RE_ID, viewportId: q.id });
    this.sincronizador = sync as unknown as { destroy: () => void };
  }

  /** "Ir ao SUV máximo perto do cursor (3 cm)": o clique procura o máximo numa esfera em volta do ponto e leva
   * os cortes de todos os quadros até ele. */
  private cliqueSuvMax(e: MouseEvent, q: Quadro): void {
    if (ferramentaAtual !== "suvmax" || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const vid = this.volumePetDe(q);
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    if (!vid || !vp || q.tipo === "pilha" || !cache.getVolume(vid)) {
      this.aviso(tr("O SUV máximo é procurado num quadro de volume do PET (A, C, S ou a fusão)."));
      return;
    }
    const r = q.el.getBoundingClientRect();
    const ponto = vp.canvasToWorld([e.clientX - r.left, e.clientY - r.top]) as V3;
    const m = maximoPerto(vid, ponto, RAIO_MAXIMO_MM);
    if (!m) return;
    this.irAoPonto(m.ponto);
    const u = this.sobreDe(q)?.suv || q.serie?.suv ? "" : " Bq/ml";
    q.achado = `${tr("SUV máximo perto do cursor:")} ${m.valor.toFixed(2)}${u}`;
    this.aviso(`${q.achado}.`);
    this.ultimoMaximo = m;
    this.escreverTextos(q);
  }

  ultimoMaximo: { ponto: V3; valor: number } | null = null;

  /** Leva os cortes dos quadros de volume ao ponto (sem mexer no enquadramento). */
  irAoPonto(p: V3): void {
    for (const q of this.quadros) {
      if (q.tipo !== "plano") continue;
      const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
      if (!vp) continue;
      const cam = vp.getCamera();
      const n = cam.viewPlaneNormal as V3;
      const d = dot(sub(p, cam.focalPoint as V3), n);
      vp.setCamera({ focalPoint: add(cam.focalPoint as V3, mul(n, d)) as Types.Point3,
        position: add(cam.position as V3, mul(n, d)) as Types.Point3 });
      vp.render();
      this.escreverTextos(q);
    }
  }

  // SEG: a escolhida fica nos quadros de volume, mesmo depois de trocar a grade
  seg: SegCarregada | null = null;

  async mostrarSegDaSerie(study: string, segSerie: string | null,
    pegar: (series: string) => Promise<SerieCarregada | null>): Promise<SegCarregada | null> {
    if (!segSerie) {
      this.seg = null;
      tirarSeg(this.quadros.map((q) => q.id));
      return null;
    }
    const s = await carregarSeg(study, segSerie, async (ref) => {
      const sr = await pegar(ref);
      if (!sr || sr.semVolume) return null;
      return volumeDa(sr);
    });
    if (!s) {
      this.aviso(tr("Não deu para mostrar esta segmentação (a série de origem precisa formar um volume)."));
      return null;
    }
    this.seg = s;
    this.reporSeg();
    return s;
  }

  private reporSeg(): void {
    if (!this.seg) return;
    const ids = this.quadros.filter((q) => q.tipo !== "pilha" && q.serie).map((q) => q.id);
    mostrarSeg(this.seg, ids);
  }

  // -------------------------------------------------------------- espessura e projeção
  private aplicarProjecao(q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    if (!vp || q.tipo === "pilha") return;
    const B = Enums.BlendModes;
    if (q.tipo === "mip") {
      vp.setBlendMode(B.MAXIMUM_INTENSITY_BLEND);
      vp.setSlabThickness(this.diagonal(q));
      return;
    }
    const modo = { fino: B.COMPOSITE, mip: B.MAXIMUM_INTENSITY_BLEND, minip: B.MINIMUM_INTENSITY_BLEND,
      media: B.AVERAGE_INTENSITY_BLEND }[q.projecao];
    vp.setBlendMode(modo);
    if (q.projecao === "fino" || q.espessura <= 0) vp.resetSlabThickness();
    else vp.setSlabThickness(q.espessura);
    if (q.sobre) this.amostrarFusao(q);
  }

  private diagonal(q: Quadro): number {
    const v = q.serie ? cache.getVolume(`cornerstoneStreamingImageVolume:${q.serie.series}`) : null;
    if (!v) return 1000;
    const [a, b, c] = v.dimensions, [x, y, z] = v.spacing;
    return Math.hypot(a * x, b * y, c * z);
  }

  espessura(mm: number, projecao: Projecao): void {
    const q = this.quadros[this.ativo];
    if (!q || q.tipo !== "plano") {
      this.aviso(tr("A espessura vale nos quadros de volume (A, C, S)."));
      return;
    }
    q.espessura = mm;
    q.projecao = mm > 0 ? (projecao === "fino" ? "mip" : projecao) : "fino";
    this.aplicarProjecao(q);
    (this.viewport() as Types.IVolumeViewport).render();
    this.escreverTextos(q);
  }

  // -------------------------------------------------------------- MIP girando e clicável
  private configurarMip(): void {
    const tm = ToolGroupManager.getToolGroup(TG_MIP);
    if (!tm) return;
    const alvos = this.quadros.filter((q) => q.tipo !== "mip").map((q) => q.id);
    tm.setToolConfiguration(MIPJumpToClickTool.toolName, { targetViewportIds: alvos });
  }

  girarMip(i: number, ang: number): void {
    const q = this.quadros[i];
    const vp = this.viewport(i) as Types.IVolumeViewport | null;
    if (!q || q.tipo !== "mip" || !vp) return;
    const cam = vp.getCamera();
    const eixo: V3 = [0, 0, 1];                         // em volta do eixo crânio-caudal do paciente
    const n = girarVetor(cam.viewPlaneNormal as V3, eixo, ang);
    const dist = Math.hypot(...sub(cam.position as V3, cam.focalPoint as V3));
    vp.setCamera({ viewPlaneNormal: n as Types.Point3, viewUp: [0, 0, 1] as Types.Point3,
      position: add(cam.focalPoint as V3, mul(n, dist)) as Types.Point3 });
    vp.render();
  }

  girar(ligar: boolean): void {
    for (const [i, q] of this.quadros.entries()) {
      if (q.tipo !== "mip") continue;
      if (q.girando !== null) { clearInterval(q.girando); q.girando = null; }
      if (ligar) q.girando = window.setInterval(() => this.girarMip(i, Math.PI / 45), 66);
    }
  }

  // -------------------------------------------------------------- oblíquo por dois pontos
  /** Os dois próximos cliques no quadro ativo (de volume) definem a reta; o oblíquo vai para o próximo quadro de
   * volume (ou para o próprio, se só houver um). */
  obliquoPorDoisPontos(): boolean {
    const i = this.ativo;
    const q = this.quadros[i];
    if (!q || q.tipo !== "plano") {
      this.aviso(tr("O oblíquo por dois pontos parte de um quadro de volume (A, C, S)."));
      return false;
    }
    const vp = this.viewport(i) as Types.IVolumeViewport;
    const pts: V3[] = [];
    this.aviso(tr("Oblíquo: clique em dois pontos da reta no quadro ativo."));
    const clique = (e: MouseEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      const r = q.el.getBoundingClientRect();
      pts.push(vp.canvasToWorld([e.clientX - r.left, e.clientY - r.top]) as V3);
      if (pts.length < 2) return;
      q.el.removeEventListener("mousedown", clique, true);
      const alvo = this.quadros.findIndex((x, k) => k !== i && x.tipo === "plano");
      this.aplicarObliquo(alvo >= 0 ? alvo : i, pts[0], pts[1], vp.getCamera().viewPlaneNormal as V3);
      this.aviso("");
    };
    q.el.addEventListener("mousedown", clique, true);
    return true;
  }

  aplicarObliquo(i: number, p0: V3, p1: V3, normalAtual: V3): void {
    const vp = this.viewport(i) as Types.IVolumeViewport;
    const { normal, cima } = planoPorDoisPontos(p0, p1, normalAtual);
    const cam = vp.getCamera();
    const dist = Math.hypot(...sub(cam.position as V3, cam.focalPoint as V3)) || 500;
    const centro = mul(add(p0, p1), 0.5);
    vp.setCamera({ viewPlaneNormal: normal as Types.Point3, viewUp: cima as Types.Point3,
      focalPoint: centro as Types.Point3, position: add(centro, mul(normal, dist)) as Types.Point3 });
    vp.render();
    this.escreverTextos(this.quadros[i]);
  }

  // -------------------------------------------------------------- textos
  escreverTextos(q: Quadro): void {
    const vp = motor?.getViewport(q.id);
    if (!vp || !q.serie) {
      q.textos.innerHTML = "";
      return;
    }
    let posicao = "";
    let plano = "";
    if (q.tipo === "pilha") {
      const p = vp as Types.IStackViewport;
      posicao = `${tr("Im")} ${p.getCurrentImageIdIndex() + 1} / ${q.serie.imageIds.length}`;
    } else {
      const v = vp as Types.IVolumeViewport;
      try {
        posicao = q.tipo === "mip" ? "" : `${v.getSliceIndex() + 1} / ${v.getNumberOfSlices()}`;
      } catch { posicao = ""; }
      const n = v.getCamera().viewPlaneNormal as V3;
      plano = q.tipo === "mip" ? tr("MIP") : nomeDoPlano(n);
      if (q.sobre) plano = `${tr("Fusão")} ${q.sobre.modalidade} · ${plano}`;
      if (q.tipo === "plano" && q.projecao !== "fino" && q.espessura > 0) {
        plano += ` · ${{ mip: "MIP", minip: "MinIP", media: tr("Média") }[q.projecao]} ${q.espessura} mm`;
      }
    }
    let p: { voiRange?: { lower: number; upper: number }; invert?: boolean } = {};
    try { p = (vp as Types.IStackViewport).getProperties() || {}; } catch { p = {}; }
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
    canto("sd", [`${tr("Se")} ${q.serie.numero} ${q.serie.modalidade}`.trim(), q.serie.descricao, plano]);
    canto("ie", [posicao, zoom, q.achado]);
    const emSuv = q.sobre?.suv || (q.serie.suv && q.tipo !== "pilha");
    canto("id", [emSuv ? `SUV 0–${q.suvMax}` : jan, q.sobre ? `${Math.round(q.opacidade * 100)}%` : "",
      p.invert && !q.serie.suv ? tr("Inverter") : ""]);
  }

  // -------------------------------------------------------------- comandos da barra
  janela(largura: number, nivel: number): void {
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp) return;
    vp.setProperties({ voiRange: { lower: nivel - largura / 2, upper: nivel + largura / 2 } });
    vp.render();
  }

  janelaDoArquivo(): void {
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp) return;
    vp.resetProperties();
    vp.render();
  }

  inverter(): void {
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp) return;
    vp.setProperties({ invert: !vp.getProperties().invert });
    vp.render();
  }

  restaurar(): void {
    const q = this.quadros[this.ativo];
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp || !q) return;
    vp.resetCamera();
    vp.resetProperties();
    if (q.tipo !== "pilha") {
      q.projecao = q.tipo === "mip" ? "mip" : "fino";
      q.espessura = 0;
      this.aplicarProjecao(q);
    }
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

  desmontar(tudo = true): void {
    for (const q of this.quadros) {
      try { csTools.utilities.cine.stopClip(q.el); } catch { /* nada */ }
      if (q.girando !== null) clearInterval(q.girando);
    }
    for (const q of this.quadros) {
      for (const id of [TG_2D, TG_VOL, TG_MIP]) {
        try { ToolGroupManager.getToolGroup(id)?.removeViewports(RE_ID, q.id); } catch { /* nada */ }
      }
      try { motor?.disableElement(q.id); } catch { /* nada */ }
    }
    this.quadros = [];
    this.raiz.innerHTML = "";
    try { this.sincronizador?.destroy(); } catch { /* nada */ }
    this.sincronizador = null;
    if (tudo) {
      this.seg = null;
      esquecerSegs();
      try { cache.purgeVolumeCache?.(); } catch { /* nada */ }
    }
  }
}
