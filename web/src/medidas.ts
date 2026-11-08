// Medidas do visualizador web (W2): as ferramentas do Cornerstone3D desenham, mas o número é o do Ipê —
// mesma escala (calibração desta imagem → da série → região do ultrassom → espaçamento do arquivo → pixels),
// mesma regra da ROI (pixel conta se o centro está dentro), mesmo texto. As medidas feitas nos quadros de corte
// (pilha) vão para o banco do servidor no formato do Ipê e aparecem lá; as do MPR ficam só na sessão, como no Ipê.

import { cache, eventTarget, getRenderingEngines, utilities as csUtils, type Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import { cabecalhos, valor, type DicomJson } from "./api";
import { tr } from "./i18n";
import { META, partesDoImageId } from "./meta";

type P2 = [number, number];
type V3 = [number, number, number];
type Esp = [number, number] | null; // (linha, coluna) mm

const {
  LengthTool, AngleTool, CobbAngleTool, EllipticalROITool, RectangleROITool, PlanarFreehandROITool, ProbeTool,
  ArrowAnnotateTool, Enums: TE,
} = csTools;

export const CALIBRACAO = "Calibracao";

/** ferramenta do Cornerstone3D -> tipo de medida do Ipê */
export const TIPO: Record<string, string> = {
  [LengthTool.toolName]: "line",
  [AngleTool.toolName]: "angle",
  [CobbAngleTool.toolName]: "cobb",
  [EllipticalROITool.toolName]: "ellipse",
  [RectangleROITool.toolName]: "rect",
  [PlanarFreehandROITool.toolName]: "polygon",
  [ProbeTool.toolName]: "probe",
  [ArrowAnnotateTool.toolName]: "arrow",
  [CALIBRACAO]: "calibration",
};
const FERRAMENTA_DO_TIPO: Record<string, string> = Object.fromEntries(Object.entries(TIPO).map(([f, k]) => [k, f]));

// ------------------------------------------------------------------ as contas do Ipê (imaging/measure.py)
export function compMm(p1: P2, p2: P2, sp: Esp): number {
  const [rs, cs] = sp || [1, 1];
  return Math.hypot((p2[0] - p1[0]) * cs, (p2[1] - p1[1]) * rs);
}

export function anguloGraus(p1: P2, v: P2, p3: P2, sp: Esp): number {
  const [rs, cs] = sp || [1, 1];
  const a = [(p1[0] - v[0]) * cs, (p1[1] - v[1]) * rs], b = [(p3[0] - v[0]) * cs, (p3[1] - v[1]) * rs];
  const na = Math.hypot(a[0], a[1]), nb = Math.hypot(b[0], b[1]);
  if (!na || !nb) return 0;
  return (Math.acos(Math.min(1, Math.max(-1, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))) * 180) / Math.PI;
}

export function cobbGraus(p0: P2, p1: P2, p2: P2, p3: P2, sp: Esp): number {
  const [rs, cs] = sp || [1, 1];
  const a = [(p1[0] - p0[0]) * cs, (p1[1] - p0[1]) * rs], b = [(p3[0] - p2[0]) * cs, (p3[1] - p2[1]) * rs];
  const na = Math.hypot(a[0], a[1]), nb = Math.hypot(b[0], b[1]);
  if (!na || !nb) return 0;
  return (Math.acos(Math.min(1, Math.abs(a[0] * b[0] + a[1] * b[1]) / (na * nb))) * 180) / Math.PI;
}

function areaPoligono(pts: P2[]): number {
  if (pts.length < 3) return 0;
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}

export function areaPx(kind: string, pts: P2[]): number {
  if (kind === "ellipse" && pts.length >= 2) {
    const [[x1, y1], [x2, y2]] = pts;
    return (Math.PI * Math.abs(x2 - x1) / 2) * (Math.abs(y2 - y1) / 2);
  }
  if (kind === "rect" && pts.length >= 2) {
    const [[x1, y1], [x2, y2]] = pts;
    return Math.abs(x2 - x1) * Math.abs(y2 - y1);
  }
  return areaPoligono(pts);
}

function dentroPoligono(x: number, y: number, pts: P2[]): boolean {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if (yi !== yj && (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

export interface Estat { n: number; media: number | null; dp: number | null; min: number | null; max: number | null; areaPx: number; areaMm2: number | null }

/** Os pixels cujo centro está dentro da ROI (como `roi_mask` do Ipê); DP amostral (n − 1). */
export function estatRoi(px: ArrayLike<number>, w: number, h: number, kind: string, pts: P2[], sp: Esp): Estat {
  const a = areaPx(kind, pts);
  const areaMm2 = sp ? a * sp[0] * sp[1] : null;
  const vazio: Estat = { n: 0, media: null, dp: null, min: null, max: null, areaPx: a, areaMm2 };
  if (pts.length < 2 || (kind === "polygon" && pts.length < 3)) return vazio;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.max(0, Math.floor(Math.min(...xs))), x1 = Math.min(w, Math.ceil(Math.max(...xs)));
  const y0 = Math.max(0, Math.floor(Math.min(...ys))), y1 = Math.min(h, Math.ceil(Math.max(...ys)));
  if (x1 <= x0 || y1 <= y0) return vazio;
  let cx = 0, cy = 0, rx = 0, ry = 0;
  if (kind === "ellipse") {
    const [[ax, ay], [bx, by]] = pts;
    cx = (ax + bx) / 2; cy = (ay + by) / 2; rx = Math.abs(bx - ax) / 2; ry = Math.abs(by - ay) / 2;
    if (rx <= 0 || ry <= 0) return vazio;
  }
  let n = 0, soma = 0, soma2 = 0, mn = Infinity, mx = -Infinity;
  const vals: number[] = [];
  for (let r = y0; r < y1; r++) {
    for (let c = x0; c < x1; c++) {
      const x = c + 0.5, y = r + 0.5;
      let ok: boolean;
      if (kind === "rect") ok = x >= Math.min(...xs) && x <= Math.max(...xs) && y >= Math.min(...ys) && y <= Math.max(...ys);
      else if (kind === "ellipse") ok = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1;
      else ok = dentroPoligono(x, y, pts);
      if (!ok) continue;
      const v = px[r * w + c];
      vals.push(v);
      n++; soma += v; mn = Math.min(mn, v); mx = Math.max(mx, v);
    }
  }
  if (!n) return vazio;
  const media = soma / n;
  for (const v of vals) soma2 += (v - media) ** 2;
  return { n, media, dp: n > 1 ? Math.sqrt(soma2 / (n - 1)) : 0, min: mn, max: mx, areaPx: a, areaMm2 };
}

const num = (v: number) => (Math.abs(v) < 1000 ? v.toFixed(1) : v.toFixed(0));

// ------------------------------------------------------------------ a escala (annotate.measure_spacing)
interface Regiao { x0: number; y0: number; x1: number; y1: number; mmLinha: number; mmColuna: number }

/** As regiões do ultrassom que medem distância: as com os dois eixos em centímetros (us_regioes.py). */
export function regioesUS(m: DicomJson | undefined): Regiao[] {
  const seq = (m?.["00186011"]?.Value as DicomJson[] | undefined) || [];
  const out: Regiao[] = [];
  for (const it of seq) {
    const n = (t: string) => { const v = Number(valor(it, t)); return Number.isFinite(v) ? v : null; };
    if (n("00186024") !== 3 || n("00186026") !== 3) continue;
    const dx = n("0018602C"), dy = n("0018602E");
    const x0 = n("00186018"), y0 = n("0018601A"), x1 = n("0018601C"), y1 = n("0018601E");
    if (!dx || !dy || dx <= 0 || dy <= 0 || x0 == null || y0 == null || x1 == null || y1 == null || x1 <= x0 || y1 <= y0) continue;
    out.push({ x0, y0, x1, y1, mmLinha: dy * 10, mmColuna: dx * 10 });
  }
  return out;
}

function regiaoDoPonto(regs: Regiao[], x: number, y: number): Regiao | null {
  const d = regs.filter((r) => r.x0 <= x && x <= r.x1 && r.y0 <= y && y <= r.y1);
  if (!d.length) return null;
  return d.reduce((a, b) => ((a.x1 - a.x0) * (a.y1 - a.y0) <= (b.x1 - b.x0) * (b.y1 - b.y0) ? a : b));
}

/** Escala de uma medida no ultrassom: `null` se sai da região ou atravessa duas (vira pixel). */
export function espacamentoUS(regs: Regiao[], pts: P2[]): Esp {
  if (!regs.length || !pts.length) return null;
  const achadas = pts.map((p) => regiaoDoPonto(regs, p[0], p[1]));
  if (achadas.some((r) => r === null) || achadas.some((r) => r !== achadas[0])) return null;
  return [achadas[0]!.mmLinha, achadas[0]!.mmColuna];
}

function espacamentoDoArquivo(m: DicomJson | undefined): Esp {
  for (const tag of ["00280030", "00181164"]) {
    const v = (m?.[tag]?.Value as number[] | undefined) || [];
    if (v.length === 2 && v.every((x) => Number.isFinite(Number(x)))) return [Number(v[0]), Number(v[1])];
  }
  return null;
}

interface Calib { id: string; series: string; sop: string; quadro: number; mm: number; escopo: string; pontos: P2[] }
const CALIBS = new Map<string, Calib>(); // annotationUID -> calibração

function espacamentoDaCalib(c: Calib): Esp {
  if (c.pontos.length < 2 || !(c.mm > 0)) return null;
  const px = Math.hypot(c.pontos[1][0] - c.pontos[0][0], c.pontos[1][1] - c.pontos[0][1]);
  return px > 0 ? [c.mm / px, c.mm / px] : null;
}

/** A escala, na ordem da confiança do Ipê. Devolve também de onde ela veio. */
export function escala(imageId: string, pts: P2[]): { sp: Esp; fonte: string } {
  const p = partesDoImageId(imageId);
  if (p) {
    const todas = [...CALIBS.values()].reverse();
    const daImagem = todas.find((c) => c.sop === p.sop && c.quadro === p.quadro);
    if (daImagem) return { sp: espacamentoDaCalib(daImagem), fonte: "imagem" };
    const daSerie = todas.find((c) => c.series === p.series && c.escopo !== "imagem");
    if (daSerie) return { sp: espacamentoDaCalib(daSerie), fonte: "serie" };
  }
  const m = META.get(imageId);
  const regs = regioesUS(m);
  if (regs.length) return { sp: espacamentoUS(regs, pts), fonte: "us" };
  return { sp: espacamentoDoArquivo(m), fonte: "arquivo" };
}

// ------------------------------------------------------------------ o texto de cada medida (measure.labels)
function pixelsDa(imageId: string): { px: ArrayLike<number>; w: number; h: number } | null {
  const im = cache.getImage(imageId) as unknown as {
    getPixelData: () => ArrayLike<number>; width: number; height: number; slope?: number; intercept?: number;
    preScale?: { scaled?: boolean };
  } | undefined;
  if (!im) return null;
  const bruto = im.getPixelData();
  if (im.preScale?.scaled || ((im.slope ?? 1) === 1 && (im.intercept ?? 0) === 0)) return { px: bruto, w: im.width, h: im.height };
  const k = im.slope ?? 1, b = im.intercept ?? 0;
  const px = new Float32Array(bruto.length);
  for (let i = 0; i < bruto.length; i++) px[i] = bruto[i] * k + b;
  return { px, w: im.width, h: im.height };
}

function paraImagem(imageId: string, mundo: number[][]): P2[] {
  return mundo.map((w) => csUtils.worldToImageCoords(imageId, w as never) as unknown as P2);
}

export function pontosDaAnotacao(a: { data: Record<string, unknown> }, kind: string): number[][] {
  const d = a.data as { handles?: { points?: number[][] }; contour?: { polyline?: number[][] } };
  if (kind === "polygon") return d.contour?.polyline || [];
  return d.handles?.points || [];
}

/** Ipê guarda a elipse e o retângulo pelos dois cantos da caixa; o Cornerstone3D pelos 4 pontos. */
export function pontosIpe(kind: string, img: P2[]): P2[] {
  if ((kind === "ellipse" || kind === "rect") && img.length >= 4) {
    const xs = img.map((p) => p[0]), ys = img.map((p) => p[1]);
    return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
  }
  return img;
}

export function linhas(kind: string, pts: P2[], imageId: string, texto = "", meta: Record<string, unknown> = {}): string[] {
  const { sp } = escala(imageId, pts);
  const un = sp ? "mm" : "px";
  const mod = String(valor(META.get(imageId) || {}, "00080060") ?? "").toUpperCase();
  if (kind === "calibration") {
    if (!texto) return [tr("Calibração")];
    return [meta.escopo === "imagem" ? `${tr("Calibração:")} ${texto} mm ${tr("(só esta imagem)")}` : `${tr("Calibração:")} ${texto} mm`];
  }
  if (kind === "line" && pts.length >= 2) {
    const d = compMm(pts[0], pts[1], sp);
    return [sp ? `${d.toFixed(1)} mm` : `${d.toFixed(0)} px`];
  }
  if (kind === "angle" && pts.length >= 3) return [`${anguloGraus(pts[0], pts[1], pts[2], sp).toFixed(1)}°`];
  if (kind === "cobb" && pts.length >= 4) return [`Cobb ${cobbGraus(pts[0], pts[1], pts[2], pts[3], sp).toFixed(1)}°`];
  if (kind === "probe" && pts.length) {
    const pd = pixelsDa(imageId);
    if (!pd) return [];
    const c = Math.floor(pts[0][0]), r = Math.floor(pts[0][1]);
    if (c < 0 || r < 0 || c >= pd.w || r >= pd.h) return [];
    return [`${num(pd.px[r * pd.w + c])}${mod === "CT" ? " HU" : ""}`];
  }
  if (kind === "ellipse" || kind === "rect" || kind === "polygon") {
    const pd = pixelsDa(imageId);
    const st = pd ? estatRoi(pd.px, pd.w, pd.h, kind, pts, sp) : estatRoi([], 0, 0, kind, pts, sp);
    const u = mod === "CT" ? " HU" : "";
    const out: string[] = [];
    if (st.media !== null) {
      out.push(`${tr("Média")} ${num(st.media)} ± ${num(st.dp!)}${u}`);
      out.push(`${tr("Mín")} ${num(st.min!)}  ${tr("Máx")} ${num(st.max!)}`);
    }
    if (st.areaMm2 !== null) out.push(st.areaMm2 >= 100 ? `${tr("Área")} ${(st.areaMm2 / 100).toFixed(2)} cm²` : `${tr("Área")} ${st.areaMm2.toFixed(1)} mm²`);
    else out.push(`${tr("Área")} ${st.areaPx.toFixed(0)} px²`);
    return out;
  }
  if (kind === "arrow" && texto) return [texto];
  void un;
  return [];
}

/** O texto no MPR (sem imagem de origem): contas no espaço do paciente, em mm. */
function linhasNoVolume(kind: string, mundo: number[][], data: Record<string, unknown>, targetId: string): string[] {
  const d = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  const ang = (a: number[], v: number[], b: number[]) => {
    const x = [a[0] - v[0], a[1] - v[1], a[2] - v[2]], y = [b[0] - v[0], b[1] - v[1], b[2] - v[2]];
    const nx = Math.hypot(...x), ny = Math.hypot(...y);
    return nx && ny ? (Math.acos(Math.max(-1, Math.min(1, (x[0] * y[0] + x[1] * y[1] + x[2] * y[2]) / (nx * ny)))) * 180) / Math.PI : 0;
  };
  if ((kind === "line" || kind === "calibration") && mundo.length >= 2) return [`${d(mundo[0], mundo[1]).toFixed(1)} mm`];
  if (kind === "angle" && mundo.length >= 3) return [`${ang(mundo[0], mundo[1], mundo[2]).toFixed(1)}°`];
  const st = (data.cachedStats as Record<string, { mean?: number; stdDev?: number; area?: number; max?: number; min?: number }> | undefined)?.[targetId];
  if (st && st.mean !== undefined) {
    const out = [`${tr("Média")} ${num(st.mean)} ± ${num(st.stdDev || 0)}`];
    if (st.area !== undefined) out.push(`${tr("Área")} ${st.area.toFixed(1)} mm²`);
    return out;
  }
  if (kind === "arrow") return [String((data as { text?: string }).text || "")];
  return [];
}

function textoDe(kind: string) {
  return (data: Record<string, unknown>, targetId: string): string[] => {
    const mundo = pontosDaAnotacao({ data }, kind);
    const ipe = (data as { ipe?: { texto?: string; meta?: Record<string, unknown> } }).ipe || {};
    if (targetId.startsWith("imageId:")) {
      const imageId = targetId.slice("imageId:".length);
      try {
        const pts = pontosIpe(kind, paraImagem(imageId, mundo));
        return linhas(kind, pts, imageId, kind === "arrow" ? String((data as { text?: string }).text || "") : ipe.texto || "", ipe.meta || {});
      } catch {
        return [];
      }
    }
    return linhasNoVolume(kind, mundo, data, targetId);
  };
}

// ------------------------------------------------------------------ as ferramentas
/** Põe as ferramentas de medida nos grupos (a calibração é uma régua com outro nome). */
export function adicionarFerramentas(grupos: csTools.Types.IToolGroup[]): void {
  for (const t of [LengthTool, AngleTool, CobbAngleTool, EllipticalROITool, RectangleROITool, PlanarFreehandROITool,
    ProbeTool, ArrowAnnotateTool]) csTools.addTool(t);
  const pedirTexto = (feito: (t: string) => void) => feito(window.prompt(tr("Texto da seta:")) ?? "");
  for (const tg of grupos) {
    for (const [ferr, kind] of Object.entries(TIPO)) {
      if (ferr === CALIBRACAO) continue;
      const cfg: Record<string, unknown> = { getTextLines: textoDe(kind) };
      if (kind === "arrow") {
        cfg.getTextCallback = pedirTexto;
        cfg.changeTextCallback = (_a: unknown, _e: unknown, feito: (t: string) => void) => pedirTexto(feito);
      }
      if (kind === "polygon") cfg.calculateStats = true;
      tg.addTool(ferr, cfg);
    }
    tg.addToolInstance(CALIBRACAO, LengthTool.toolName, { getTextLines: textoDe("calibration") });
  }
}

export const FERRAMENTA_DA_ESCOLHA: Record<string, string> = {
  regua: LengthTool.toolName, angulo: AngleTool.toolName, cobb: CobbAngleTool.toolName,
  elipse: EllipticalROITool.toolName, retangulo: RectangleROITool.toolName, poligono: PlanarFreehandROITool.toolName,
  pixel: ProbeTool.toolName, seta: ArrowAnnotateTool.toolName, calibracao: CALIBRACAO,
};

// ------------------------------------------------------------------ banco do servidor
type Anot = csTools.Types.Annotation & { data: Record<string, unknown>; metadata: { toolName: string } & Record<string, unknown> };
const DB = new Map<string, number>();       // annotationUID -> id no banco
const ESPERA = new Map<string, number>();   // gravações adiadas (arrastar dispara muitas)
let carregando = false;

function renderizarTudo(): void {
  for (const re of getRenderingEngines() || []) re.render();
}

function imagemDa(a: Anot): string | null {
  const md = a.metadata as { referencedImageId?: string; volumeId?: string };
  if (!md.referencedImageId || md.volumeId) return null; // MPR: só na sessão, como no Ipê
  return partesDoImageId(md.referencedImageId) ? md.referencedImageId : null;
}

export function paraRegistro(a: Anot): Record<string, unknown> | null {
  const kind = TIPO[a.metadata.toolName];
  const imageId = imagemDa(a);
  if (!kind || !imageId) return null;
  const p = partesDoImageId(imageId)!;
  const pts = pontosIpe(kind, paraImagem(imageId, pontosDaAnotacao(a, kind)));
  const ipe = (a.data as { ipe?: { texto?: string; meta?: Record<string, unknown> } }).ipe || {};
  const texto = kind === "arrow" ? String((a.data as { text?: string }).text || "") : ipe.texto || "";
  return {
    db_id: DB.get(a.annotationUID!) ?? null, study_uid: p.study, series_uid: p.series, sop_uid: p.sop,
    frame_index: p.quadro - 1, kind, data: { points: pts, text: texto, meta: ipe.meta || {} },
  };
}

async function gravar(a: Anot): Promise<void> {
  const reg = paraRegistro(a);
  if (!reg) return;
  const r = await fetch(`${location.origin}/api/web/medidas`, {
    method: "POST", headers: { ...cabecalhos(), "Content-Type": "application/json" }, body: JSON.stringify(reg),
  });
  if (r.ok) DB.set(a.annotationUID!, (await r.json()).id);
}

async function apagar(uid: string): Promise<void> {
  const id = DB.get(uid);
  CALIBS.delete(uid);
  if (id === undefined) return;
  DB.delete(uid);
  await fetch(`${location.origin}/api/web/medidas/apagar`, {
    method: "POST", headers: { ...cabecalhos(), "Content-Type": "application/json" }, body: JSON.stringify({ db_id: id }),
  });
  renderizarTudo();
}

function registrarCalibracao(a: Anot): void {
  const imageId = imagemDa(a);
  const ipe = (a.data as { ipe?: { texto?: string; meta?: Record<string, unknown> } }).ipe;
  if (!imageId || !ipe?.texto) return;
  const p = partesDoImageId(imageId)!;
  CALIBS.set(a.annotationUID!, { id: a.annotationUID!, series: p.series, sop: p.sop, quadro: p.quadro,
    mm: Number(String(ipe.texto).replace(",", ".")), escopo: String(ipe.meta?.escopo || "serie"),
    pontos: paraImagem(imageId, pontosDaAnotacao(a, "calibration")) });
}

/** Pergunta o tamanho real da linha de calibração; no ultrassom vale só para a imagem (como no Ipê). */
export function perguntarCalibracao(a: Anot): boolean {
  const imageId = imagemDa(a) || (a.metadata as { referencedImageId?: string }).referencedImageId || "";
  const mod = String(valor(META.get(imageId) || {}, "00080060") ?? "").toUpperCase();
  const us = mod === "US" || regioesUS(META.get(imageId)).length > 0;
  const r = window.prompt(tr("Comprimento real desta linha (mm):"), "10");
  const mm = Number(String(r ?? "").replace(",", "."));
  if (!(mm > 0)) return false;
  (a.data as Record<string, unknown>).ipe = { texto: `${mm}`, meta: { escopo: us ? "imagem" : "serie" } };
  return true;
}

export function ouvirAnotacoes(): void {
  const E = TE.Events;
  eventTarget.addEventListener(E.ANNOTATION_COMPLETED, ((ev: CustomEvent) => {
    if (carregando) return;
    const a = ev.detail.annotation as Anot;
    if (a.metadata.toolName === CALIBRACAO) {
      if (!perguntarCalibracao(a)) {
        csTools.annotation.state.removeAnnotation(a.annotationUID!);
        renderizarTudo();
        return;
      }
      registrarCalibracao(a);
      renderizarTudo();
    }
    void gravar(a);
  }) as EventListener);
  eventTarget.addEventListener(E.ANNOTATION_MODIFIED, ((ev: CustomEvent) => {
    if (carregando) return;
    const a = ev.detail.annotation as Anot;
    if (!DB.has(a.annotationUID!)) return;
    if (a.metadata.toolName === CALIBRACAO) { registrarCalibracao(a); renderizarTudo(); }
    clearTimeout(ESPERA.get(a.annotationUID!));
    ESPERA.set(a.annotationUID!, window.setTimeout(() => void gravar(a), 500));
  }) as EventListener);
  eventTarget.addEventListener(E.ANNOTATION_REMOVED, ((ev: CustomEvent) => {
    const a = ev.detail.annotation as Anot;
    void apagar(a.annotationUID!);
  }) as EventListener);
}

/** Traz do banco as medidas de uma série (as dos tipos que o site desenha) para os quadros. */
export async function carregarMedidas(study: string, series: string, imageIds: string[], elemento: HTMLDivElement): Promise<number> {
  const r = await fetch(`${location.origin}/api/web/medidas?study=${study}&series=${series}`, { headers: cabecalhos(), cache: "no-store" });
  if (!r.ok) return 0;
  const regs = (await r.json()) as { id: number; sop_uid: string; frame_index: number; kind: string; data: string }[];
  const porQuadro = new Map<string, string>();
  for (const id of imageIds) {
    const p = partesDoImageId(id);
    if (p) porQuadro.set(`${p.sop}|${p.quadro - 1}`, id);
  }
  const jaTem = new Set(DB.values());
  let n = 0;
  carregando = true;
  try {
    for (const reg of regs) {
      const ferr = FERRAMENTA_DO_TIPO[reg.kind];
      const imageId = porQuadro.get(`${reg.sop_uid}|${reg.frame_index}`);
      if (!ferr || !imageId || jaTem.has(reg.id)) continue;
      const d = JSON.parse(reg.data || "{}") as { points?: P2[]; text?: string; meta?: Record<string, unknown> };
      const a = deRegistro(ferr, reg.kind, d.points || [], d.text || "", d.meta || {}, imageId);
      if (!a) continue;
      csTools.annotation.state.addAnnotation(a as never, elemento);
      DB.set(a.annotationUID!, reg.id);
      if (reg.kind === "calibration") registrarCalibracao(a);
      n++;
    }
  } finally {
    carregando = false;
  }
  renderizarTudo();
  return n;
}

function normalDa(imageId: string): V3 {
  const iop = ((META.get(imageId)?.["00200037"]?.Value as number[]) || [1, 0, 0, 0, 1, 0]).map(Number);
  const [a, b, c, d, e, f] = iop;
  return [b * f - c * e, c * d - a * f, a * e - b * d];
}

export function deRegistro(ferr: string, kind: string, pts: P2[], texto: string, meta: Record<string, unknown>, imageId: string): Anot | null {
  const mundo = (img: P2[]) => img.map((p) => csUtils.imageToWorldCoords(imageId, p as never) as unknown as number[]);
  let img: P2[] = pts;
  if ((kind === "ellipse" || kind === "rect") && pts.length >= 2) {
    const [[x0, y0], [x1, y1]] = pts;
    if (kind === "rect") img = [[x0, y0], [x1, y0], [x0, y1], [x1, y1]];
    else {
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = Math.abs(x1 - x0) / 2, ry = Math.abs(y1 - y0) / 2;
      img = [[cx, cy + ry], [cx, cy - ry], [cx - rx, cy], [cx + rx, cy]]; // baixo, cima, esquerda, direita
    }
  }
  const w = mundo(img);
  if (!w.length) return null;
  const im = META.get(imageId);
  const data: Record<string, unknown> = {
    handles: { points: kind === "polygon" ? [] : w, activeHandleIndex: null, textBox: { hasMoved: false } },
    label: "", cachedStats: {}, ipe: { texto, meta },
  };
  if (kind === "polygon") data.contour = { polyline: w, closed: true };
  if (kind === "arrow") data.text = texto;
  const ups = ((im?.["00200037"]?.Value as number[]) || [1, 0, 0, 0, 1, 0]).map(Number);
  return {
    annotationUID: csUtils.uuidv4(), highlighted: false, isLocked: false, isVisible: true, invalidated: true,
    metadata: {
      toolName: ferr, referencedImageId: imageId, FrameOfReferenceUID: String(valor(im || {}, "00200052") ?? ""),
      viewPlaneNormal: normalDa(imageId) as never, viewUp: [-ups[3], -ups[4], -ups[5]] as never,
    },
    data,
  } as unknown as Anot;
}

/** Apaga a medida selecionada (ou nada). */
/** Clicar numa medida (com qualquer ferramenta) a seleciona; clicar fora tira a seleção. */
export function selecionarAoClicar(el: HTMLDivElement): void {
  el.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const r = el.getBoundingClientRect();
    const a = csTools.utilities.getAnnotationNearPoint(el, [e.clientX - r.left, e.clientY - r.top] as Types.Point2, 8);
    if (a?.annotationUID) csTools.annotation.selection.setAnnotationSelected(a.annotationUID, true, e.shiftKey);
    else if (!e.shiftKey) csTools.annotation.selection.deselectAnnotation();
  }, true);
}

export function apagarSelecionadas(): number {
  const sel = csTools.annotation.selection.getAnnotationsSelected();
  for (const uid of sel) csTools.annotation.state.removeAnnotation(uid);
  renderizarTudo();
  return sel.length;
}

(window as unknown as Record<string, unknown>).__ipeMed = { estatRoi, compMm, anguloGraus, cobbGraus, espacamentoUS, regioesUS, linhas, DB,
  selecionadas: () => csTools.annotation.selection.getAnnotationsSelected() };
