// Quadros do visualizador web: pilha 2D (W0) e volume (W1: MPR, oblíquo, espessura, MIP girando).
// Cornerstone3D com o carregador WADO-RS do servidor central.
// Botões do mouse como no Ipê: esquerdo = a ferramenta escolhida, meio = mover, direito = zoom, roda = rolar os
// cortes (no MIP, a roda gira). Nenhum atalho de teclado de fábrica.

import {
  Enums,
  ProgressiveRetrieveImages,
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
import { Lupa } from "./lupa";
import { FERRAMENTA_DA_ESCOLHA, adicionarFerramentas, carregarMedidas, ouvirAnotacoes, selecionarAoClicar } from "./medidas";
import { META } from "./meta";
import {
  COR_PADRAO, RAIO_MAXIMO_MM, SUV, SUV_PADRAO, carregarSeg, esquecerSegs, maximoPerto, mostrarSeg,
  propriedadesDaFusao, registrarEscalaSuv, tirarSeg, type SegCarregada,
} from "./pet";

const {
  PanTool, ZoomTool, WindowLevelTool, StackScrollTool, CrosshairsTool, MIPJumpToClickTool, ToolGroupManager,
  ReferenceLinesTool, Enums: TE,
} = csTools;

/** 0.100.3: o desenho que ficou pela metade. As medidas do Cornerstone3D também desenham em "clique, move, clique":
 * um clique só começa a linha e, enquanto ela não termina, a biblioteca acha que ainda está desenhando e ignora todas
 * as outras ferramentas em todos os botões. Se o médico clica noutro quadro, troca de ferramenta ou aperta Esc, o
 * desenho pela metade é desfeito e o mouse volta a funcionar. */
let elDoDesenho: HTMLDivElement | null = null;

export function desenhando(): boolean {
  return !!csTools.state.isInteractingWithTool;
}

export function cancelarDesenho(): boolean {
  if (!csTools.state.isInteractingWithTool) return false;
  // desfaz a medida pela metade (o "cancel" do Cornerstone3D a daria por terminada e ela iria para o banco)
  for (const id of [TG_2D, TG_VOL, TG_MIP]) {
    const tg = ToolGroupManager.getToolGroup(id);
    if (!tg) continue;
    for (const nome of Object.keys(tg.toolOptions)) {
      const f = tg.getToolInstance(nome) as unknown as {
        isDrawing?: boolean; editData?: { annotation?: { annotationUID?: string }; newAnnotation?: boolean } | null;
        _deactivateDraw?: (el: HTMLElement) => void; _deactivateModify?: (el: HTMLElement) => void } | undefined;
      if (!f?.isDrawing) continue;
      const uid = f.editData?.annotation?.annotationUID, nova = !!f.editData?.newAnnotation;
      if (elDoDesenho) {
        try { f._deactivateDraw?.(elDoDesenho); f._deactivateModify?.(elDoDesenho); } catch { /* nada */ }
        try { csTools.cursors.elementCursor.resetElementCursor(elDoDesenho); } catch { /* nada */ }
      }
      f.isDrawing = false;
      f.editData = null;
      if (nova && uid) {
        try { csTools.annotation.state.removeAnnotation(uid); } catch { /* já saiu */ }
      }
    }
  }
  csTools.state.isInteractingWithTool = false;
  elDoDesenho = null;
  for (const vp of motor?.getViewports() ?? []) vp.render();
  return true;
}

if (typeof window !== "undefined") {
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && cancelarDesenho()) e.stopPropagation();
  }, true);
  (window as unknown as Record<string, unknown>).__ipeDesenhando = desenhando;
}

/** 0.100.2: as linhas de referência entre os quadros de corte (o plano do quadro ativo cortando os outros), como no Ipê. */
let linhasRef = true;
export function linhasDeReferencia(): boolean {
  return linhasRef;
}
const MB = TE.MouseBindings;

const RE_ID = "ipe";
const TG_2D = "ipe-2d";
const TG_VOL = "ipe-vol";
const TG_MIP = "ipe-mip";
/** volumes acima disto (bytes) não são montados: a placa de vídeo comum não aguenta */
export const LIMITE_VOLUME = 1.5 * 1024 ** 3;
/** o tipo do arrasto da tira de séries (o valor é o SeriesInstanceUID) */
export const TIPO_ARRASTO = "application/x-ipe-serie";
/** 0.100.21: o exame da série arrastada (para soltar numa janela de visualização de outro exame) */
export const TIPO_ARRASTO_ESTUDO = "application/x-ipe-estudo";
let iniciado = false;
let motor: RenderingEngine | null = null;

export type Ferramenta = "janela" | "mover" | "zoom" | "rolar" | "linhas" | "regua" | "angulo" | "cobb" | "elipse"
  | "retangulo" | "poligono" | "pixel" | "seta" | "calibracao" | "suvmax" | "lupa";
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
    // 0.99.96: decodificar é trabalho de CPU em paralelo — todos os núcleos menos um (a tela fica com ele)
    maxWebWorkers: Math.max(1, Math.min(8, (navigator.hardwareConcurrency || 2) - 1)),
    beforeSend: () => cabecalhos(),
  });
  // 0.99.96: o quadro chega em HTJ2K com ordem RPCL (a cópia de envio do servidor): pedido em fluxo, o navegador
  // decodifica uma versão menor com os primeiros bytes e refina até a imagem inteira. O volume vem intercalado
  // (1 a cada 4 cortes primeiro, os vizinhos repetidos) — o MPR aparece cedo e vai se completando.
  const progressivo = { retrieveOptions: { default: { streaming: true } } };
  csUtils.imageRetrieveMetadataProvider.add("stack", { ...ProgressiveRetrieveImages.singleRetrieveStages, ...progressivo });
  csUtils.imageRetrieveMetadataProvider.add("volume", { ...ProgressiveRetrieveImages.interleavedRetrieveStages, ...progressivo });
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
  for (const t of [PanTool, ZoomTool, WindowLevelTool, StackScrollTool, CrosshairsTool, MIPJumpToClickTool, ReferenceLinesTool]) {
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
  t2.addTool(ReferenceLinesTool.toolName, { sourceViewportId: "" });
  adicionarFerramentas([t2, tv]); // W2: medidas (na pilha vão para o banco; no MPR, só na sessão)
  ouvirAnotacoes();
  aplicarBotoes("janela");
  motor = new RenderingEngine(RE_ID);
  (window as unknown as Record<string, unknown>).__ipeGeo = { planoPorDoisPontos, girarVetor }; // testes
  (window as unknown as Record<string, unknown>).__ipeCs = { imageToWorldCoords: csUtils.imageToWorldCoords, worldToImageCoords: csUtils.worldToImageCoords, cache,
    segmentation: csTools.segmentation };
  iniciado = true;
}

/** O botão esquerdo vira a ferramenta `f` (nos quadros de volume, "linhas" = a cruz das linhas de referência);
 * meio = mover, direito = zoom e a roda = rolar continuam. No MIP, o esquerdo leva os cortes ao ponto mais claro. */
/** A função de cada botão do mouse, como no Ipê (0.99.97): clicar no ícone da barra com o botão escolhe. */
export interface Botoes { esq: Ferramenta; meio: Ferramenta; dir: Ferramenta }
let botoesAtuais: Botoes = { esq: "janela", meio: "mover", dir: "zoom" };
const MB_DO_BOTAO: Record<keyof Botoes, number> = { esq: MB.Primary, meio: MB.Auxiliary, dir: MB.Secondary };
const BOTAO_DO_EVENTO: Record<number, keyof Botoes> = { 0: "esq", 1: "meio", 2: "dir" };

export function botoes(): Botoes {
  return { ...botoesAtuais };
}

/** Uma ferramenta (vai para o botão esquerdo) ou as dos três botões. */
export function aplicarBotoes(f: Ferramenta | Partial<Botoes>): void {
  cancelarDesenho();                   // 0.100.3: trocar de ferramenta desfaz a medida que ficou pela metade
  botoesAtuais = typeof f === "string" ? { ...botoesAtuais, esq: f } : { ...botoesAtuais, ...f };
  for (const id of [TG_2D, TG_VOL, TG_MIP]) {
    const tg = ToolGroupManager.getToolGroup(id);
    if (!tg) continue;
    const fixos: Record<string, number[]> = {
      [PanTool.toolName]: [],
      [ZoomTool.toolName]: [],
      [StackScrollTool.toolName]: id === TG_MIP ? [] : [MB.Wheel],
      [WindowLevelTool.toolName]: [],
    };
    if (id === TG_VOL) fixos[CrosshairsTool.toolName] = [];
    if (id !== TG_MIP) for (const nome of Object.values(FERRAMENTA_DA_ESCOLHA)) fixos[nome] = [];
    if (id === TG_MIP) fixos[MIPJumpToClickTool.toolName] = [MB.Primary];
    for (const [botao, mb] of Object.entries(MB_DO_BOTAO) as [keyof Botoes, number][]) {
      const t = botoesAtuais[botao];
      if (t === "suvmax" || t === "lupa") continue;  // tratados pela grade (SUV máximo perto do ponto; a lupa)
      if (id === TG_MIP) {
        // no MIP o esquerdo leva os cortes ao ponto clicado; os outros botões só movem, ampliam ou ajustam a janela
        if (botao !== "esq" && (t === "janela" || t === "mover" || t === "zoom")) fixos[NOME[t]].push(mb);
        continue;
      }
      if (t === "linhas") {
        // nas pilhas, o clique leva os outros quadros ao corte do ponto (tratado pela grade)
        if (id === TG_VOL) fixos[CrosshairsTool.toolName].push(mb);
      } else if (NOME[t]) {
        (fixos[NOME[t]] ??= []).push(mb);
      }
    }
    // 0.100.3: o Cornerstone3D soma os botões novos aos antigos no setToolActive e, no setToolPassive, só tira o
    // esquerdo — a função que saía do meio ou do direito continuava lá, na frente da nova ("o botão muda, mas o mouse
    // não faz"). Por isso cada ferramenta perde todos os botões antes de receber exatamente os seus.
    for (const nome of Object.keys(fixos)) tg.setToolPassive(nome, { removeAllBindings: true });
    // 0.100.18: toque — um dedo faz a função do botão esquerdo (é do Cornerstone3D); dois dedos, a pinça do zoom
    // (que também desloca); três dedos movem
    const toque: Record<string, number[]> = { [ZoomTool.toolName]: [2], [PanTool.toolName]: [3] };
    for (const [nome, bs] of Object.entries(fixos)) {
      const lig = [...bs.map((b) => ({ mouseButton: b })), ...(toque[nome] || []).map((n) => ({ numTouchPoints: n }))];
      if (lig.length) tg.setToolActive(nome, { bindings: lig as never });
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

/** 0.100.16: o corte da pilha mais perto do ponto, pela posição de cada corte nos metadados da série (o
 *  getClosestStackImageIndexForPoint do Cornerstone só vê os cortes já carregados — com a série ainda chegando, não
 *  saía do lugar). */
function indiceMaisPerto(vp: Types.IStackViewport, p: Types.Point3): number | null {
  const ids = vp.getImageIds();
  let melhor = -1, dmin = Infinity;
  ids.forEach((id, i) => {
    const m = META.get(id);
    const ipp = (m?.["00200032"]?.Value as number[] | undefined)?.map(Number);
    const iop = (m?.["00200037"]?.Value as number[] | undefined)?.map(Number);
    if (!ipp || !iop || ipp.length !== 3 || iop.length !== 6) return;
    const n = [iop[1] * iop[5] - iop[2] * iop[4], iop[2] * iop[3] - iop[0] * iop[5], iop[0] * iop[4] - iop[1] * iop[3]];
    const d = Math.abs((p[0] - ipp[0]) * n[0] + (p[1] - ipp[1]) * n[1] + (p[2] - ipp[2]) * n[2]);
    if (d < dmin) { dmin = d; melhor = i; }
  });
  if (melhor >= 0) return melhor;
  return csUtils.getClosestStackImageIndexForPoint(p, vp);
}

/** 0.100.20: um ato do médico que segue para as outras janelas de visualização */
export type Sinc = { tipo: "pos"; ponto: number[]; normal: number[]; delta: number; cantos?: number[][] | null }
  | { tipo: "voi"; lower: number; upper: number; modalidade: string } | { tipo: "zoom"; zoom: number };

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
  /** 0.100.2: o piso da janela de SUV (o arrasto do mouse no PET mexe nos dois) */
  suvMin: number;
  /** o último SUV máximo achado perto do cursor neste quadro */
  achado: string;
}

export interface Spec {
  serie: SerieCarregada | null; tipo: Tipo; plano: Plano; projecao: Projecao; espessura: number;
  sobre?: SerieCarregada | null; cor?: string; opacidade?: number; suvMax?: number; suvMin?: number;
}

/** 0.100.2: o que cada quadro do PET/CT mostra, para montar a leitura como o médico quiser. */
export type VistaPet = "fusao" | "tc" | "pet" | "mip";
export interface ConteudoPet { v: VistaPet; plano: Plano }
export const ARRANJO_PET_PADRAO: { l: number; c: number; quadros: ConteudoPet[] } = { l: 1, c: 3, quadros: [
  { v: "fusao", plano: "AXIAL" }, { v: "pet", plano: "AXIAL" }, { v: "mip", plano: "CORONAL" }] };

function fmtSuv(v: number): string {
  return (Math.round(v * 10) / 10).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export class Grade {
  quadros: Quadro[] = [];
  ativo = 0;
  linhas = 1;
  colunas = 1;
  paciente = "";
  aoMudar: () => void = () => {};
  /** 0.100.2: cada vez que um quadro desenha (para a camada do overlay) */
  aoDesenhar: (q: Quadro) => void = () => {};
  aviso: (msg: string) => void = () => {};
  /** soltaram uma série (arrastada da tira) no quadro i */
  aoSoltar: (series: string, i: number, estudo: string) => void = () => {};
  /** clicou e soltou o botão direito sem arrastar no quadro i: o menu da imagem (x, y na página) */
  aoMenu: (i: number, x: number, y: number, el: HTMLDivElement) => void = () => {};
  private direito: { x: number; y: number; i: number; el: HTMLDivElement } | null = null;

  constructor(public raiz: HTMLElement) {
    this.soltouDireito = (e: MouseEvent) => {
      const d = this.direito;
      this.direito = null;
      if (e.button !== 2 || !d) return;
      if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) return;
      if (botoesAtuais.dir === "suvmax" || botoesAtuais.dir === "lupa") return;
      this.aoMenu(d.i, e.clientX, e.clientY, d.el);
    };
    window.addEventListener("mouseup", this.soltouDireito, true);
  }

  private soltouDireito: (e: MouseEvent) => void;

  /** Monta os quadros. `specs` (opcional) diz o que vai em cada um; sem ele, ficam as séries de antes. */
  montar(linhas: number, colunas: number, specs?: Spec[]): void {
    const antigas: Spec[] = specs ?? this.quadros.map((q) => this.specDe(q));
    this.desmontar(false);
    this.ampliado = null;
    this.raiz.classList.remove("com-ampliado");
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
      // botão direito: segurar e arrastar faz a função dele; clicar e soltar abre o menu
      el.addEventListener("mousedown", (e) => {
        if (e.button === 2) this.direito = { x: e.clientX, y: e.clientY, i, el };
      }, true);
      selecionarAoClicar(el);
      const textos = document.createElement("div");
      textos.className = "textos";
      const botoes = document.createElement("div");
      botoes.className = "planos";
      cel.append(el, textos, botoes);
      cel.addEventListener("mousedown", () => this.ativar(i), true);
      cel.addEventListener("dblclick", (e) => this.duploClique(e, i));
      // arrastar a série da tira para o quadro
      cel.addEventListener("dragover", (e) => {
        if (!e.dataTransfer?.types.includes(TIPO_ARRASTO)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        cel.classList.add("alvo");
      });
      cel.addEventListener("dragleave", () => cel.classList.remove("alvo"));
      cel.addEventListener("drop", (e) => {
        cel.classList.remove("alvo");
        const uid = e.dataTransfer?.getData(TIPO_ARRASTO);
        if (!uid) return;
        e.preventDefault();
        this.ativar(i);
        this.aoSoltar(uid, i, e.dataTransfer?.getData(TIPO_ARRASTO_ESTUDO) || "");
      });
      this.raiz.append(cel);
      const id = `q${i}`;
      const q: Quadro = { id, el, textos, botoes, serie: null, tipo, plano: sp?.plano ?? "AXIAL",
        projecao: sp?.projecao ?? "fino", espessura: sp?.espessura ?? 0, girando: null,
        sobre: tipo === "plano" ? sp?.sobre ?? null : null, cor: sp?.cor ?? COR_PADRAO, opacidade: sp?.opacidade ?? 0.5,
        suvMax: sp?.suvMax ?? SUV_PADRAO, suvMin: sp?.suvMin ?? 0, achado: "" };
      el.addEventListener("mousedown", () => {
        if (csTools.state.isInteractingWithTool && elDoDesenho && elDoDesenho !== el) cancelarDesenho();
        if (!csTools.state.isInteractingWithTool) elDoDesenho = el;
      }, true);
      el.addEventListener("mousedown", (e) => this.cliqueSuvMax(e, q), true);
      el.addEventListener("mousedown", (e) => this.cliqueLupa(e, q), true);
      el.addEventListener("mousedown", (e) => this.cliqueLinhas(e, q), true);
      el.addEventListener("mousedown", (e) => this.arrastoSuv(e, q), true);
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
      q.el.addEventListener(Enums.Events.IMAGE_RENDERED, () => this.aoDesenhar(q));
      // 0.100.20: o que o médico faz no quadro ativo segue para as outras janelas de visualização
      q.el.addEventListener(Enums.Events.STACK_NEW_IMAGE, () => this.contar(q, "pos"));
      q.el.addEventListener(Enums.Events.VOI_MODIFIED, () => this.contar(q, "voi"));
      q.el.addEventListener(Enums.Events.CAMERA_MODIFIED, () => this.contar(q, "zoom"));
      q.el.addEventListener(Enums.Events.IMAGE_RENDERED, () => this.desenharLinhaDeFora(q));
    }
    this.configurarMip();
    this.sincronizar();
    this.ativo = Math.min(this.ativo, this.quadros.length - 1);
    this.marcarAtivo();
    this.fonteDasLinhas();
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
    this.fonteDasLinhas();
    this.aoMudar();
  }

  // ------------------------------------------------------------------ 0.100.5: duplo clique amplia o quadro
  /** O quadro ampliado (1×1) ou null. Os outros só se escondem: ao voltar, cada um está como estava (corte, zoom,
   * janela, medidas). */
  ampliado: number | null = null;
  /** Quem usa a grade do seu jeito (a mamografia) desliga o duplo clique daqui. */
  duploAmplia = true;

  private duploClique(e: MouseEvent, i: number): void {
    if (!this.duploAmplia || e.button !== 0 || csTools.state.isInteractingWithTool) return;
    const q = this.quadros[i];
    const vp = q ? motor?.getViewport(q.id) : undefined;
    if (vp) {
      // um duplo clique numa medida é da medida (editar o texto da seta), não da grade
      const r = vp.canvas.getBoundingClientRect();
      const ponto = [e.clientX - r.left, e.clientY - r.top] as Types.Point2;
      try {
        if (csTools.utilities.getAnnotationNearPoint(vp.element, ponto, 8)) return;
      } catch { /* sem medidas */ }
    }
    this.alternarAmpliado(i);
  }

  /** Leva o quadro para 1×1; de novo (ou noutro quadro), volta ao arranjo de antes. */
  alternarAmpliado(i: number): void {
    const cels = this.quadros.map((q) => q.el.parentElement as HTMLElement);
    if (this.ampliado !== null) {
      this.ampliado = null;
      cels.forEach((c) => { c.style.display = ""; });
      this.raiz.classList.remove("com-ampliado");
      this.raiz.style.gridTemplateColumns = `repeat(${this.colunas}, 1fr)`;
      this.raiz.style.gridTemplateRows = `repeat(${this.linhas}, 1fr)`;
    } else {
      if (this.quadros.length < 2) return;
      this.ampliado = i;
      cels.forEach((c, k) => { c.style.display = k === i ? "" : "none"; });
      this.raiz.classList.add("com-ampliado");
      this.raiz.style.gridTemplateColumns = "1fr";
      this.raiz.style.gridTemplateRows = "1fr";
    }
    this.ativar(i);
    requestAnimationFrame(() => this.redimensionar());
  }

  /** As linhas de referência saem do quadro ativo (se for de corte) e aparecem nos outros. */
  fonteDasLinhas(): void {
    const tg = ToolGroupManager.getToolGroup(TG_2D);
    if (!tg) return;
    const q = this.quadros[this.ativo];
    const nome = ReferenceLinesTool.toolName;
    if (!linhasRef || !q || q.tipo !== "pilha" || this.quadros.filter((x) => x.tipo === "pilha").length < 2) {
      tg.setToolDisabled(nome);
      return;
    }
    tg.setToolConfiguration(nome, { sourceViewportId: q.id });
    tg.setToolEnabled(nome);
    for (const x of this.quadros) if (x.tipo === "pilha") motor?.getViewport(x.id)?.render();
  }

  /** Liga ou desliga as linhas de referência. */
  ligarLinhas(on: boolean): void {
    linhasRef = on;
    this.fonteDasLinhas();
    for (const x of this.quadros) if (x.tipo === "pilha") motor?.getViewport(x.id)?.render();
  }

  /** A ferramenta "linhas de referência" nas pilhas: clicar (e arrastar) leva os outros quadros de corte ao corte
   * mais perto do ponto — o "localizador" do Ipê. */
  private cliqueLinhas(e: MouseEvent, q: Quadro): void {
    if (q.tipo !== "pilha" || botoesAtuais[BOTAO_DO_EVENTO[e.button]] !== "linhas") return;
    e.preventDefault();
    const ir = (ev: MouseEvent) => {
      const vp = motor?.getViewport(q.id) as Types.IStackViewport | undefined;
      if (!vp?.getCurrentImageId()) return;
      const r = q.el.getBoundingClientRect();
      const ponto = vp.canvasToWorld([ev.clientX - r.left, ev.clientY - r.top] as Types.Point2);
      this.irAoPontoNasPilhas(ponto as Types.Point3, q.id);
      this.irAoPonto(ponto as unknown as V3);
    };
    ir(e);
    const mover = (ev: MouseEvent) => ir(ev);
    const soltar = () => {
      window.removeEventListener("mousemove", mover, true);
      window.removeEventListener("mouseup", soltar, true);
    };
    window.addEventListener("mousemove", mover, true);
    window.addEventListener("mouseup", soltar, true);
  }

  // ---------------------------------------------------------------- 0.100.20: janelas ligadas (sincronizadas)
  /** Chamado quando o médico rola, janela ou amplia no quadro ativo (não quando a mudança veio de outra janela). */
  aoAto: ((m: Sinc) => void) | null = null;
  private mudoAte = 0;
  private ultimaPos: number[] | null = null;
  private ultimoZoom = 0;
  private pendentes = new Set<string>();

  private planoDe(vp: Types.IStackViewport): { ipp: number[]; n: number[] } | null {
    const m = META.get(vp.getCurrentImageId() || "");
    const ipp = (m?.["00200032"]?.Value as number[] | undefined)?.map(Number);
    const o = (m?.["00200037"]?.Value as number[] | undefined)?.map(Number);
    if (!ipp || !o || ipp.length !== 3 || o.length !== 6) return null;
    return { ipp, n: [o[1] * o[5] - o[2] * o[4], o[2] * o[3] - o[0] * o[5], o[0] * o[4] - o[1] * o[3]] };
  }

  private contar(q: Quadro, tipo: "pos" | "voi" | "zoom"): void {
    if (!this.aoAto || q !== this.quadros[this.ativo] || q.tipo !== "pilha" || performance.now() < this.mudoAte) return;
    if (this.pendentes.has(tipo)) return;
    this.pendentes.add(tipo);
    requestAnimationFrame(() => {
      this.pendentes.delete(tipo);
      const vp = motor?.getViewport(q.id) as Types.IStackViewport | undefined;
      if (!vp?.getCurrentImageId() || !this.aoAto || performance.now() < this.mudoAte) return;
      if (tipo === "pos") {
        const p = this.planoDe(vp);
        if (!p) return;
        const antes = this.ultimaPos;
        this.ultimaPos = p.ipp;
        const delta = antes ? (p.ipp[0] - antes[0]) * p.n[0] + (p.ipp[1] - antes[1]) * p.n[1] + (p.ipp[2] - antes[2]) * p.n[2] : 0;
        this.aoAto({ tipo: "pos", ponto: p.ipp, normal: p.n, delta, cantos: this.cantosDe(vp) });
      } else if (tipo === "voi") {
        const v = vp.getProperties().voiRange;
        if (v) this.aoAto({ tipo: "voi", lower: v.lower, upper: v.upper, modalidade: q.serie?.modalidade || "" });
      } else {
        const z = vp.getZoom();
        if (Math.abs(z - this.ultimoZoom) < 1e-4) return;
        this.ultimoZoom = z;
        this.aoAto({ tipo: "zoom", zoom: z });
      }
    });
  }

  // ---------------------------------------------------------------- 0.100.21: linha de referência entre janelas
  /** Os quatro cantos (mm, paciente) do corte mostrado. */
  private cantosDe(vp: Types.IStackViewport): number[][] | null {
    const m = META.get(vp.getCurrentImageId() || "");
    const ipp = (m?.["00200032"]?.Value as number[] | undefined)?.map(Number);
    const o = (m?.["00200037"]?.Value as number[] | undefined)?.map(Number);
    const esp = (m?.["00280030"]?.Value as number[] | undefined)?.map(Number);
    const lin = Number(m?.["00280010"]?.Value?.[0]), col = Number(m?.["00280011"]?.Value?.[0]);
    if (!ipp || !o || !esp || ipp.length !== 3 || o.length !== 6 || esp.length < 2 || !(lin > 0) || !(col > 0)) return null;
    const w = col * esp[1], h = lin * esp[0];
    const soma = (a: number[], b: number[], k: number) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
    const r = o.slice(0, 3), c = o.slice(3, 6);
    const b = soma(ipp, r, w);
    return [ipp, b, soma(b, c, h), soma(ipp, c, h)];
  }

  /** O corte que a outra janela mostra (os quatro cantos), ou nulo para apagar a linha. */
  private linhaDeFora: number[][] | null = null;

  porLinhaDeFora(cantos: number[][] | null): void {
    this.linhaDeFora = cantos;
    for (const q of this.quadros) this.desenharLinhaDeFora(q);
  }

  /** A linha onde o corte da outra janela cruza o corte deste quadro (tracejada, azul-clara). */
  private desenharLinhaDeFora(q: Quadro): void {
    const pai = q.el.parentElement;
    if (!pai) return;
    let c = pai.querySelector<HTMLCanvasElement>("canvas.linha-fora");
    const vp = q.tipo === "pilha" ? (motor?.getViewport(q.id) as Types.IStackViewport | undefined) : undefined;
    const p = vp?.getCurrentImageId() ? this.planoDe(vp) : null;
    if (!this.linhaDeFora || !vp || !p) { if (c) { c.width = c.width; c.dataset.linha = "0"; } return; }
    if (!c) {
      c = document.createElement("canvas");
      c.className = "linha-fora";
      c.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2";
      pai.append(c);
    }
    const dpr = window.devicePixelRatio || 1;
    const w = q.el.clientWidth, h = q.el.clientHeight;
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
    c.dataset.linha = "0";
    // planos paralelos (a mesma série, ou outra no mesmo plano) não se cruzam: sem linha
    const L = this.linhaDeFora;
    const u = [L[1][0] - L[0][0], L[1][1] - L[0][1], L[1][2] - L[0][2]], v = [L[3][0] - L[0][0], L[3][1] - L[0][1], L[3][2] - L[0][2]];
    const nf = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    const tam = Math.hypot(nf[0], nf[1], nf[2]) || 1;
    if (Math.abs((nf[0] * p.n[0] + nf[1] * p.n[1] + nf[2] * p.n[2]) / tam) > 0.9) return;
    const d = this.linhaDeFora.map((k) => (k[0] - p.ipp[0]) * p.n[0] + (k[1] - p.ipp[1]) * p.n[1] + (k[2] - p.ipp[2]) * p.n[2]);
    const pontos: number[][] = [];
    for (let i = 0; i < 4; i++) {
      const j = (i + 1) % 4;
      if (d[i] === 0) { pontos.push(this.linhaDeFora[i]); continue; }
      if (d[i] * d[j] < 0) {
        const t = d[i] / (d[i] - d[j]);
        const a = this.linhaDeFora[i], b = this.linhaDeFora[j];
        pontos.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]);
      }
    }
    if (pontos.length < 2) return;                    // paralelos, ou o corte de lá não passa por este
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const a = vp.worldToCanvas(pontos[0] as Types.Point3), b = vp.worldToCanvas(pontos[1] as Types.Point3);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.strokeStyle = "#4fd1ff";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([8, 5]);
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
    c.dataset.linha = "1";
  }

  /** O ato de outra janela, aplicado aqui: aos quadros de corte no mesmo plano (rolagem), da mesma modalidade
   *  (janela) e a todos (zoom). `mesmoExame`: vai pela posição no paciente; noutro exame (o anterior), anda os
   *  mesmos milímetros a partir de onde cada quadro está — alinhe uma vez com as janelas desligadas. */
  aplicarAto(m: Sinc, mesmoExame: boolean): void {
    this.mudoAte = performance.now() + 400;
    if (m.tipo === "pos") this.porLinhaDeFora(mesmoExame ? m.cantos ?? null : null);
    for (const x of this.quadros) {
      if (x.tipo !== "pilha") continue;
      const vp = motor?.getViewport(x.id) as Types.IStackViewport | undefined;
      if (!vp?.getCurrentImageId()) continue;
      if (m.tipo === "pos") {
        const p = this.planoDe(vp);
        if (!p || Math.abs(p.n[0] * m.normal[0] + p.n[1] * m.normal[1] + p.n[2] * m.normal[2]) < 0.9) continue;
        const sinal = p.n[0] * m.normal[0] + p.n[1] * m.normal[1] + p.n[2] * m.normal[2] < 0 ? -1 : 1;
        const alvo = mesmoExame ? m.ponto
          : [p.ipp[0] + p.n[0] * m.delta * sinal, p.ipp[1] + p.n[1] * m.delta * sinal, p.ipp[2] + p.n[2] * m.delta * sinal];
        if (!mesmoExame && !m.delta) continue;
        const k = indiceMaisPerto(vp, alvo as Types.Point3);
        if (k !== null && k >= 0 && k !== vp.getCurrentImageIdIndex()) void vp.setImageIdIndex(k);
        if (x === this.quadros[this.ativo]) this.ultimaPos = null;
      } else if (m.tipo === "voi") {
        if ((x.serie?.modalidade || "") !== m.modalidade) continue;
        vp.setProperties({ voiRange: { lower: m.lower, upper: m.upper } });
        vp.render();
      } else {
        vp.setZoom(m.zoom);
        vp.render();
      }
    }
  }

  /** Leva cada quadro de corte (menos `exceto`) ao corte mais perto do ponto, se o ponto cair na pilha dele. */
  irAoPontoNasPilhas(ponto: Types.Point3, exceto = ""): void {
    for (const x of this.quadros) {
      if (x.id === exceto || x.tipo !== "pilha") continue;
      const vp = motor?.getViewport(x.id) as Types.IStackViewport | undefined;
      if (!vp?.getCurrentImageId()) continue;
      const k = indiceMaisPerto(vp, ponto);
      if (k === null || k === undefined || k < 0 || k === vp.getCurrentImageIdIndex()) continue;
      void vp.setImageIdIndex(k);
    }
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

  async mostrar(i: number, s: SerieCarregada, inicio?: number): Promise<void> {
    const q = this.quadros[i];
    if (!q) return;
    if (q.tipo !== "pilha" && !this.volumeOk(s)) {
      // sem volume: o quadro volta a ser pilha
      this.especificar(i, { serie: s, tipo: "pilha", plano: q.plano, projecao: "fino", espessura: 0 });
      return;
    }
    if (q.serie && q.serie.series !== s.series) q.sobre = null; // outra série no quadro da fusão: sai a fusão
    q.serie = s;
    const vp = this.viewport(i)!;
    if (q.tipo === "pilha") {
      const pilha = vp as Types.IStackViewport;
      const meio = Math.floor(s.imageIds.length / 2);
      await pilha.setStack(s.imageIds, inicio !== undefined ? Math.max(0, Math.min(inicio, s.imageIds.length - 1)) : s.imageIds.length > 2 ? meio : 0);
      // 0.100.0: a grade pode ter sido refeita (outro layout, outra etapa) enquanto a imagem carregava — o quadro
      // de antes já não existe; mexer na câmera dele derrubava o site ("getViewUp" de null)
      if (!this.vivo(q)) return;
      // a câmera é ajustada ao tamanho de agora
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
      if (!this.vivo(q)) return;
      await setVolumesForViewports(motor!, vols, [q.id]);
      if (!this.vivo(q)) return;
      this.aplicarProjecao(q);
      const v = vp as Types.IVolumeViewport;
      if (q.sobre) {
        // a fusão: a TC embaixo em partes moles, o PET em cima com a tabela do Ipê e o que é baixo transparente
        if (s.modalidade === "CT") v.setProperties({ voiRange: { lower: -160, upper: 240 } }, vid);
        this.aplicarFusao(q);
      } else if (s.suv && q.tipo === "plano") {
        v.setProperties({ voiRange: { lower: q.suvMin, upper: q.suvMax }, invert: true });
      }
      if (q.tipo === "mip") {
        this.configurarMip();
        // a janela do MIP: na TC, larga (o MIP só tem o que é claro); no PET/MN, invertido como no Ipê
        if (s.modalidade === "CT") v.setProperties({ voiRange: { lower: -350, upper: 1150 } });
        else if (s.suv) v.setProperties({ voiRange: { lower: q.suvMin, upper: q.suvMax }, invert: true });
        else if (s.modalidade === "PT" || s.modalidade === "NM") v.setProperties({ invert: true });
      }
      v.render();
      this.reporSeg();
    }
    this.escreverTextos(q);
  }

  /** O quadro ainda está na grade (e o viewport dele no motor)? */
  private vivo(q: Quadro): boolean {
    if (!this.quadros.includes(q) || !motor) return false;
    try {
      const vp = motor.getViewport(q.id) as unknown as { getRenderer?: () => unknown } | undefined;
      return !!vp && (!vp.getRenderer || !!vp.getRenderer());
    } catch {
      return false;
    }
  }

  private specDe(q: Quadro): Spec {
    return { serie: q.serie, tipo: q.tipo, plano: q.plano, projecao: q.projecao, espessura: q.espessura,
      sobre: q.sobre, cor: q.cor, opacidade: q.opacidade, suvMax: q.suvMax, suvMin: q.suvMin };
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
  abrirPETCT(tc: SerieCarregada, pet: SerieCarregada, arranjo = ARRANJO_PET_PADRAO): boolean {
    if (!this.volumeOk(tc) || !this.volumeOk(pet)) return false;
    this.petct = { tc, pet };
    this.ativo = 0;
    this.montarPetct(arranjo.l, arranjo.c, arranjo.quadros);
    return true;
  }

  /** As séries do PET/CT aberto (para refazer o arranjo). */
  petct: { tc: SerieCarregada; pet: SerieCarregada } | null = null;

  /** 0.100.2: o arranjo do PET/CT — a grade e o que vai em cada quadro (TC, TC+PET, PET ou o MIP do PET), com o
   * plano; a cor, a opacidade e a janela de SUV continuam as de antes. */
  montarPetct(l: number, c: number, quadros: ConteudoPet[]): void {
    if (!this.petct) return;
    const { tc, pet } = this.petct;
    const ref = this.quadros.find((q) => q.sobre) ?? this.quadros.find((q) => q.serie?.modalidade === "PT");
    const comum = { cor: ref?.cor ?? COR_PADRAO, opacidade: ref?.opacidade ?? 0.5, suvMax: ref?.suvMax ?? SUV_PADRAO,
      suvMin: ref?.suvMin ?? 0 };
    const specs: Spec[] = [];
    for (let i = 0; i < l * c; i++) {
      const cp = quadros[i] ?? { v: "fusao", plano: "AXIAL" };
      const base = { ...comum, projecao: "fino" as Projecao, espessura: 0, plano: cp.plano };
      if (cp.v === "fusao") specs.push({ ...base, serie: tc, sobre: pet, tipo: "plano" });
      else if (cp.v === "tc") specs.push({ ...base, serie: tc, tipo: "plano" });
      else if (cp.v === "pet") specs.push({ ...base, serie: pet, tipo: "plano" });
      else specs.push({ ...base, serie: pet, tipo: "mip", projecao: "mip" });
    }
    this.ativo = Math.min(this.ativo, l * c - 1);
    this.montar(l, c, specs);
  }

  /** O que cada quadro do PET/CT mostra agora (para o painel e os testes). */
  arranjoPet(): ConteudoPet[] {
    const pet = this.petct?.pet.series;
    return this.quadros.map((q) => ({
      v: (q.sobre ? "fusao" : q.tipo === "mip" ? "mip" : q.serie?.series === pet ? "pet" : "tc") as VistaPet, plano: q.plano }));
  }

  /** 0.100.2: a janela do PET no arrasto — para cima e para baixo mexe no topo, para os lados no piso. Na fusão,
   * o arrasto é do PET; com Shift, da TC. Vale para todos os quadros do mesmo PET (fusão, PET e MIP). */
  private arrastoSuv(e: MouseEvent, q: Quadro): void {
    if (botoesAtuais[BOTAO_DO_EVENTO[e.button]] !== "janela" || q.tipo === "pilha") return;
    const pet = this.sobreDe(q) ?? (q.serie?.modalidade === "PT" ? q.serie : null);
    if (!pet?.suv) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (q.sobre && e.shiftKey && q.serie) {
      this.arrastoTc(e, q);
      return;
    }
    const x0 = e.clientX, y0 = e.clientY, topo0 = q.suvMax, piso0 = q.suvMin;
    const alvos = this.quadros.filter((x) => (x.sobre ?? (x.serie?.modalidade === "PT" ? x.serie : null))?.series === pet.series);
    const mover = (ev: MouseEvent) => {
      const larg = Math.max(topo0 - piso0, 0.5);
      let topo = topo0 + ((ev.clientY - y0) * larg) / 120;
      let piso = piso0 + ((ev.clientX - x0) * larg) / 240;
      piso = Math.max(0, piso);
      topo = Math.max(piso + 0.1, Math.min(topo, 200));
      for (const a of alvos) {
        a.suvMax = Math.round(topo * 100) / 100;
        a.suvMin = Math.round(piso * 100) / 100;
        this.aplicarJanelaSuv(a);
      }
    };
    const soltar = () => {
      window.removeEventListener("mousemove", mover, true);
      window.removeEventListener("mouseup", soltar, true);
      this.aoMudarSuv();
    };
    window.addEventListener("mousemove", mover, true);
    window.addEventListener("mouseup", soltar, true);
  }

  /** Shift + arrasto na fusão: a janela da TC de baixo (para os lados, a largura; para cima e para baixo, o nível). */
  private arrastoTc(e: MouseEvent, q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    const vid = `cornerstoneStreamingImageVolume:${q.serie!.series}`;
    const r0 = (vp?.getProperties(vid) as { voiRange?: { lower: number; upper: number } } | undefined)?.voiRange;
    if (!vp || !r0) return;
    const w0 = r0.upper - r0.lower, c0 = (r0.upper + r0.lower) / 2, x0 = e.clientX, y0 = e.clientY;
    const mover = (ev: MouseEvent) => {
      const w = Math.max(1, w0 + (ev.clientX - x0) * 4);
      const c = c0 + (ev.clientY - y0) * 2;
      try { vp.setProperties({ voiRange: { lower: c - w / 2, upper: c + w / 2 } }, vid); } catch { /* ainda carregando */ }
      vp.render();
      this.escreverTextos(q);
    };
    const soltar = () => {
      window.removeEventListener("mousemove", mover, true);
      window.removeEventListener("mouseup", soltar, true);
    };
    window.addEventListener("mousemove", mover, true);
    window.addEventListener("mouseup", soltar, true);
  }

  /** Avisa quem mostra a janela de SUV (o painel do PET) que ela mudou pelo mouse. */
  aoMudarSuv: () => void = () => {};

  private aplicarJanelaSuv(q: Quadro): void {
    const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
    if (!vp) return;
    if (q.sobre) this.aplicarFusao(q);
    else {
      try { vp.setProperties({ voiRange: { lower: q.suvMin, upper: q.suvMax } }); } catch { /* ainda carregando */ }
    }
    vp.render();
    this.escreverTextos(q);
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
    const p = propriedadesDaFusao(q.cor, q.opacidade, topo ?? 1, topo === undefined ? 0 : q.suvMin);
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
  fusao(o: { cor?: string; opacidade?: number; suvMax?: number; suvMin?: number }): boolean {
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
      if (o.suvMax !== undefined) q.suvMin = Math.min(o.suvMin ?? 0, q.suvMax - 0.1);
      this.aplicarFusao(q);
      motor?.getViewport(q.id)?.render();
      this.escreverTextos(q);
    }
    for (const q of pets) {
      q.suvMax = o.suvMax!;
      q.suvMin = Math.min(o.suvMin ?? 0, q.suvMax - 0.1);
      const vp = motor?.getViewport(q.id) as Types.IVolumeViewport | undefined;
      try {
        vp?.setProperties({ voiRange: { lower: q.suvMin, upper: q.suvMax } });
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

  /** 0.100.4: a lupa — enquanto o botão está apertado; a roda muda o aumento. */
  lupa: Lupa | null = null;

  private cliqueLupa(e: MouseEvent, q: Quadro): void {
    if (botoesAtuais[BOTAO_DO_EVENTO[e.button]] !== "lupa") return;
    const vp = motor?.getViewport(q.id);
    const cel = q.el.parentElement;
    if (!vp || !cel) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    this.lupa?.fechar();
    const l = new Lupa(vp, cel, q.tipo === "pilha");
    this.lupa = l;
    const r = () => vp.canvas.getBoundingClientRect();
    l.mover(e.clientX - r().left, e.clientY - r().top);
    const mover = (ev: MouseEvent) => l.mover(ev.clientX - r().left, ev.clientY - r().top);
    const roda = (ev: WheelEvent) => { ev.preventDefault(); ev.stopImmediatePropagation(); l.roda(ev.deltaY); };
    const soltar = () => {
      window.removeEventListener("mousemove", mover, true);
      window.removeEventListener("mouseup", soltar, true);
      window.removeEventListener("wheel", roda, true);
      l.fechar();
      if (this.lupa === l) this.lupa = null;
    };
    window.addEventListener("mousemove", mover, true);
    window.addEventListener("mouseup", soltar, true);
    window.addEventListener("wheel", roda, { capture: true, passive: false });
  }

  /** "Ir ao SUV máximo perto do cursor (3 cm)": o clique procura o máximo numa esfera em volta do ponto e leva
   * os cortes de todos os quadros até ele. */
  private cliqueSuvMax(e: MouseEvent, q: Quadro): void {
    if (botoesAtuais[BOTAO_DO_EVENTO[e.button]] !== "suvmax") return;
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
    canto("id", [emSuv ? `SUV ${fmtSuv(q.suvMin)}–${fmtSuv(q.suvMax)}` : jan, q.sobre ? `${Math.round(q.opacidade * 100)}%` : "",
      p.invert && !q.serie.suv ? tr("Inverter") : ""]);
  }

  // -------------------------------------------------------------- comandos do menu (0.99.97)
  /** "ajustar" à tela, "1:1" (um pixel da imagem por pixel da tela) ou "2x". */
  zoom(modo: "ajustar" | "1:1" | "2x"): void {
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp) return;
    vp.resetCamera();
    if (modo !== "ajustar") {
      const cam = vp.getCamera();
      const canvas = vp.canvas as HTMLCanvasElement;
      const im = (vp as unknown as { getImageData?: () => { spacing: number[] } | null }).getImageData?.();
      const esp = im?.spacing?.[1] || 1;
      const escala = (canvas.clientHeight / 2) * esp * (modo === "2x" ? 0.5 : 1);
      vp.setCamera({ ...cam, parallelScale: escala });
    }
    vp.render();
    this.escreverTextos(this.quadros[this.ativo]);
  }

  /** Gira 90° (sentido horário com +90) ou espelha. */
  rodar(graus: number): void {
    const vp = this.viewport() as unknown as { getViewPresentation: () => { rotation?: number };
      setViewPresentation: (p: { rotation: number }) => void; render: () => void } | null;
    if (!vp) return;
    const r = vp.getViewPresentation().rotation || 0;
    vp.setViewPresentation({ rotation: (r + graus + 360) % 360 });
    vp.render();
  }

  espelhar(eixo: "h" | "v"): void {
    const vp = this.viewport() as Types.IStackViewport | null;
    if (!vp) return;
    const cam = vp.getCamera();
    vp.setCamera(eixo === "h" ? { flipHorizontal: !cam.flipHorizontal } : { flipVertical: !cam.flipVertical });
    vp.render();
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

  /** Sai do exame: tira também o ouvinte do botão direito. */
  encerrar(): void {
    window.removeEventListener("mouseup", this.soltouDireito, true);
    this.desmontar(true);
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
