// Dinâmica da mama no navegador (0.99.98, W5): as fases que o servidor achou (a mesma detecção do Ipê), os mapas
// MSI, PEI, SER, realce inicial, subtração, TTP, MIP/média temporal e o mapa cinético calculados aqui, corte a
// corte, com as fórmulas de imaging/dynamic.py; os mapas que o Ipê já gravou ("SER (dinâmica)"…) e os calculados
// por cima da fase, como fusão; e as curvas tempo-intensidade das ROIs, com a classe (persistente, platô,
// washout), o realce inicial, o SER e os descritores (BAT, lavagem, iAUC90, MRT).
//
// O que fica de fora por enquanto (só no Ipê): correção de movimento, fases fora da conta e linha de base pela
// média das fases pré.
import { Enums, type Types, cache, imageLoader, metaData, utilities } from "@cornerstonejs/core";

import * as API from "./api";
import { tr } from "./i18n";
import { estatRoi, roisDaTela } from "./medidas";
import { type ItemMenu, abrirMenu } from "./menu";
import { type Grade, type SerieCarregada, type Spec, carregarSerie } from "./visor";

type P2 = [number, number];

export interface Dinamica {
  motivo: string;
  fases: { rotulo: string; tempo: number; quadros: { series: string; sop: string; quadro: number }[] }[];
  com_horario: boolean;
  pre: number;
  inicial: number;
  tardia: number;
  parametros: { threshold_pct: number; threshold_all: boolean; noise_pct: number; rapido_pct: number;
    tardio_pct: number; sinal_min_pct: number; relative: boolean };
  mapas_salvos: { series: string; descricao: string; chave: string; cores: string }[];
  classes: string[];
  mapas: Record<string, { nome: string; descricao: string; unidade: string; cores: string }>;
}

export async function dinamicaDoExame(study: string): Promise<Dinamica | null> {
  const r = await fetch(`${location.origin}/api/web/dinamica?study=${encodeURIComponent(study)}`,
    { headers: API.cabecalhos(), cache: "no-store" });
  if (!r.ok) return null;
  return (await r.json()) as Dinamica;
}

/** Os mapas que o navegador calcula (os da tabela de cores do Ipê). */
export const CALCULADOS = ["cin", "ser", "msi", "pei", "ei", "sub", "ttp", "mipt", "medt"] as const;
export type Chave = typeof CALCULADOS[number];
const SUBTRACOES = new Set(["sub", "mipt", "medt"]);
const MASCARADO = -1;
const CORES_CURVAS = ["#ff5a5a", "#50c8ff", "#78ff78", "#ffc83c", "#dc78ff", "#ff8cc8", "#a0ffe6", "#ffffff"];

// ------------------------------------------------------------------ as contas (imaging/dynamic.py)
/** Percentil com interpolação linear (o padrão do numpy). */
export function percentil(v: ArrayLike<number>, q: number): number {
  const a = Float64Array.from(v as ArrayLike<number>).sort();
  if (!a.length) return 0;
  const pos = (q / 100) * (a.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  return i + 1 < a.length ? a[i] + (a[i + 1] - a[i]) * f : a[i];
}

export interface Parametros {
  pre: number; inicial: number; tardia: number; tempos: number[]; // tempos em s desde a 1ª fase
  limiar: number; limiarEmTodos: boolean; relativo: boolean; rapido: number; tardio: number; sinalMin: number;
  ruido: number; referencia: number;
}

/** Os mapas de um corte: `st` = os pixels de cada fase (todas do mesmo tamanho). Port de DynamicMaps.compute. */
export function calcularMapas(st: Float32Array[], p: Parametros): Record<Chave, Float32Array> {
  const n = st[0].length;
  const F = st.length;
  const t = p.tempos.map((s) => s / 60);
  const pre = p.pre;
  const tp = t.slice(pre);
  const ruido = Math.max(p.ruido, 1e-6);
  const out = Object.fromEntries(CALCULADOS.map((k) => [k, new Float32Array(n)])) as Record<Chave, Float32Array>;
  const ref = p.referencia * p.sinalMin / 100;
  const e = new Float64Array(F - pre);
  for (let i = 0; i < n; i++) {
    let media = 0;
    for (let f = 0; f < F; f++) media += st[f][i];
    media /= F;
    const valido = media > ruido;
    const s0 = st[pre][i];
    const base = Math.max(s0, ruido);
    // realce das fases pós (a partir da pré)
    let pico = -Infinity;
    let iPico = 0;
    for (let j = 0; j < F - pre; j++) {
      const v = st[pre + j][i];
      e[j] = p.relativo ? (v - s0) / base * 100 : v - s0;
      if (v > pico) { pico = v; iPico = j; }
    }
    let msi = -Infinity;
    let pei = 0;
    for (let j = 0; j + 1 < e.length; j++) {
      const dt = tp[j + 1] - tp[j];
      msi = Math.max(msi, (e[j + 1] - e[j]) / Math.max(dt, 1e-6));
      pei += 0.5 * (Math.max(e[j + 1], 0) + Math.max(e[j], 0)) * dt;
    }
    msi = e.length > 1 ? Math.max(msi, 0) : 0;
    const s1 = st[p.inicial][i];
    const s2 = st[p.tardia][i];
    const eiRel = (s1 - s0) / base * 100;
    const realca = valido && eiRel >= p.limiar;
    let ser = (s1 - s0) / (s2 - s0);
    ser = Number.isFinite(ser) && s2 - s0 > 0 ? Math.min(3, Math.max(0, ser)) : 3;
    out.ser[i] = realca ? ser : MASCARADO;
    const m = p.limiarEmTodos ? realca : valido;
    out.msi[i] = m ? msi : 0;
    out.pei[i] = m ? pei : 0;
    out.ei[i] = m ? (p.relativo ? eiRel : s1 - s0) : 0;
    out.ttp[i] = m ? (tp[iPico] - tp[0]) * 60 : 0;
    out.sub[i] = s1 - s0;
    // MIP e média temporais: as fases depois da pré
    if (F > pre + 1) {
      let mx = -Infinity;
      let soma = 0;
      for (let f = pre + 1; f < F; f++) { mx = Math.max(mx, st[f][i]); soma += st[f][i]; }
      out.mipt[i] = mx - s0;
      out.medt[i] = soma / (F - pre - 1) - s0;
    }
    // mapa cinético: 0 sem cor, 1–3 realce médio, 4–6 rápido (persistente, platô, washout)
    const tecido = valido && s0 >= ref;
    const realce = (s1 - s0) / base * 100;
    let vari = (s2 - s1) / Math.max(s1, 1e-6) * 100;
    if (!Number.isFinite(vari)) vari = 0;
    let cls = 0;
    if (tecido) {
      const faixa = realce >= p.limiar && realce < p.rapido ? 0 : realce >= p.rapido ? 1 : -1;
      if (faixa >= 0) {
        if (vari >= p.tardio) cls = 1 + faixa * 3;
        else if (Math.abs(vari) < p.tardio) cls = 2 + faixa * 3;
        else if (vari <= -p.tardio) cls = 3 + faixa * 3;
      }
    }
    out.cin[i] = cls;
  }
  return out;
}

/** A classe de uma curva (DynamicMaps.classe_cinetica), com os mesmos limiares do mapa. */
export function classeDaCurva(v: number[], p: Parametros, classes: string[]): string {
  const s0 = v[p.pre];
  const base = Math.abs(s0) > 1e-6 ? s0 : 1e-6;
  const realce = (v[p.inicial] - s0) / Math.abs(base) * 100;
  const pico = v[p.inicial];
  const vari = (v[p.tardia] - pico) / (Math.abs(pico) > 1e-6 ? Math.abs(pico) : 1e-6) * 100;
  if (realce < p.limiar) return classes[0];
  const faixa = realce < p.rapido ? 0 : 1;
  if (vari >= p.tardio) return classes[1 + faixa * 3];
  if (Math.abs(vari) < p.tardio) return classes[2 + faixa * 3];
  return classes[3 + faixa * 3];
}

/** BAT (s), lavagem (%/min), iAUC90 e MRT (s) de uma curva de realce `e` (a 1ª é a pré, 0) — `descritores`. */
export function descritores(e: number[], tMin: number[]): { bat: number; wash: number; iauc: number; mrt: number } {
  const pos = e.map((x) => Math.max(x, 0));
  const pico = Math.max(...pos);
  const limiar = pico * 0.1;
  let bat = 0;
  for (let j = 1; j < pos.length; j++) {
    if (pos[j] >= limiar && pico > 0) {
      const e1 = pos[j], e0 = pos[j - 1];
      const f = e1 > e0 ? (limiar - e0) / (e1 - e0) : 0;
      bat = (tMin[j - 1] + Math.min(1, Math.max(0, f)) * (tMin[j] - tMin[j - 1])) * 60;
      break;
    }
  }
  let iPico = 0;
  for (let j = 1; j < e.length; j++) if (e[j] > e[iPico]) iPico = j;
  let wash = 0;
  for (let j = 0; j + 1 < e.length; j++) {
    if (j >= iPico) wash = Math.max(wash, -(e[j + 1] - e[j]) / Math.max(tMin[j + 1] - tMin[j], 1e-6));
  }
  const lim = 90 / 60;
  let iauc = 0;
  for (let k = 0; k + 1 < tMin.length; k++) {
    let a = tMin[k], b = tMin[k + 1];
    if (a >= lim || b <= a) continue;
    const pa = pos[k];
    let pb = pos[k + 1];
    if (b > lim) { pb = pa + (pb - pa) * (lim - a) / (b - a); b = lim; }
    iauc += 0.5 * (pa + pb) * (b - a);
    a = b;
  }
  let num = 0, den = 0;
  for (let j = 0; j + 1 < pos.length; j++) {
    const dt = tMin[j + 1] - tMin[j];
    num += 0.5 * (pos[j + 1] * tMin[j + 1] + pos[j] * tMin[j]) * dt;
    den += 0.5 * (pos[j + 1] + pos[j]) * dt;
  }
  return { bat, wash: Math.max(wash, 0), iauc, mrt: den > 0 ? num / den * 60 : 0 };
}

/** A janela de cada mapa (DynamicMaps.window): [baixo, alto]. */
function janelaFixa(chave: string): [number, number] | null {
  if (chave === "cin") return [-0.5, 6.5];
  if (chave === "ser") return [0, 2];
  return null;
}

// ------------------------------------------------------------------ as imagens dos mapas (carregador "ipedin")
let atual: ModoDinamica | null = null;
let registrado = false;

function registrarCarregador(): void {
  if (registrado) return;
  registrado = true;
  imageLoader.registerImageLoader("ipedin", (imageId: string) => ({
    promise: (async () => {
      const m = /^ipedin:([a-z0-9]+):(\d+)$/.exec(imageId);
      if (!m || !atual) throw new Error("dinâmica fechada");
      const k = Number(m[2]);
      const dados = /^fs\d+p\d+$/.test(m[1]) ? await atual.subtracaoDaFase(m[1], k) : (await atual.mapasDoCorte(k))[m[1] as Chave];
      return atual.imagemDoMapa(imageId, dados);
    })(),
  }) as never);
}

function pixelsDa(img: Types.IImage): Float32Array {
  const px = img.getPixelData() as ArrayLike<number>;
  const out = new Float32Array(px.length);
  const escalado = !!(img as unknown as { preScale?: { scaled?: boolean } }).preScale?.scaled;
  const s = escalado ? 1 : img.slope ?? 1;
  const b = escalado ? 0 : img.intercept ?? 0;
  for (let i = 0; i < px.length; i++) out[i] = px[i] * s + b;
  return out;
}

/** 0.100.2: o que cada quadro mostra — um mapa ou uma fase (com subtração e paisagem, como no Ipê), e a cor. */
export interface QuadroDin { v: Chave | "fase"; fase: number; sub: boolean; pais: number; cor: string }

const PAISAGENS = [0, 0.1, 0.2, 0.3, 0.5];

export interface OpcoesDin {
  study: string;
  aviso: (m: string) => void;
  aoSair: () => void;
}

export class ModoDinamica {
  barra: HTMLElement;
  painel: HTMLElement;
  private fases: string[][] = []; // imageIds de cada fase, por corte
  private par!: Parametros;
  private corteCache = new Map<number, Promise<Record<Chave, Float32Array>>>();
  private janelas = new Map<string, [number, number]>();
  private quadros: QuadroDin[] = [];
  private registradas = new Set<string>();
  private hover: { k: number; x: number; y: number; valores: number[] } | null = null;
  private curvaCursor = true;
  private corSobre = "";
  private sobre: { tipo: "mapa"; chave: Chave } | { tipo: "salvo"; series: string; chave: string } | null = null;
  private opacidade = 0.5;
  private salvos = new Map<string, SerieCarregada>();
  private camada: HTMLCanvasElement | null = null;
  private rolando = false;
  private soltar: (() => void)[] = [];
  private curvas: { uid: string; valores: number[]; n: number }[] = [];

  constructor(private g: Grade, private dados: Dinamica, private op: OpcoesDin) {
    registrarCarregador();
    this.barra = document.createElement("div");
    this.barra.className = "barra-din";
    this.barra.setAttribute("role", "toolbar");
    this.barra.setAttribute("aria-label", tr("Dinâmica da mama"));
    this.painel = document.createElement("section");
    this.painel.className = "painel-din";
    this.painel.setAttribute("aria-label", tr("Curvas tempo-intensidade"));
    (window as unknown as Record<string, unknown>).__ipeDin = this; // testes
  }

  /** Lê as fases, os níveis de ruído e de referência e monta o layout (fase inicial, cinético, SER, subtração). */
  async abrir(): Promise<boolean> {
    const d = this.dados;
    const porSerie = new Map<string, Map<string, string>>();
    const series = [...new Set(d.fases.flatMap((f) => f.quadros.map((q) => q.series)))];
    for (const uid of series) {
      const s = await carregarSerie(this.op.study, uid);
      if (!s) return false;
      const mapa = new Map<string, string>();
      for (const id of s.imageIds) {
        const m = /\/instances\/([^/]+)\/frames\/(\d+)$/.exec(id);
        if (m) mapa.set(`${m[1]}|${m[2]}`, id);
      }
      porSerie.set(uid, mapa);
    }
    this.fases = d.fases.map((f) => f.quadros.map((q) => porSerie.get(q.series)?.get(`${q.sop}|${q.quadro}`) || ""));
    if (this.fases.some((f) => f.some((id) => !id))) return false;
    const pa = d.parametros;
    this.par = { pre: d.pre, inicial: d.inicial, tardia: d.tardia, tempos: d.fases.map((f) => f.tempo),
      limiar: Number(pa.threshold_pct ?? 50), limiarEmTodos: !!pa.threshold_all, relativo: pa.relative !== false,
      rapido: Number(pa.rapido_pct ?? 100), tardio: Number(pa.tardio_pct ?? 10), sinalMin: Number(pa.sinal_min_pct ?? 10),
      ruido: 0, referencia: 1 };
    // ruído e referência: o percentil 99,5 do máximo entre as fases em três cortes (reference_level / noise_level)
    const n = this.fases[0].length;
    const ks = [...new Set([Math.floor(n / 3), Math.floor(n / 2), Math.floor((2 * n) / 3)])].sort((a, b) => a - b);
    let ref = 0;
    for (const k of ks) {
      const st = await this.pilhaDoCorte(k);
      const mx = new Float32Array(st[0].length).fill(-Infinity);
      for (const f of st) for (let i = 0; i < f.length; i++) if (f[i] > mx[i]) mx[i] = f[i];
      ref = Math.max(ref, percentil(mx, 99.5));
    }
    this.par.referencia = ref || 1;
    this.par.ruido = ref * Number(pa.noise_pct ?? 5) / 100;
    await this.prepararJanelas();
    for (const ch of CALCULADOS) this.registrarChave(ch);
    const q = (v: Chave | "fase"): QuadroDin => ({ v, fase: this.par.inicial, sub: false, pais: 0, cor: "" });
    this.quadros = [q("fase"), q("cin"), q("ser"), q("sub")];
    this.montarBarra();
    atual = this;
    await this.montar();
    return true;
  }

  /** A janela dos mapas que não têm janela fixa: o percentil de três cortes (DynamicMaps.window). */
  private async prepararJanelas(): Promise<void> {
    const n = this.fases[0].length;
    const ks = [...new Set([Math.floor(n / 3), Math.floor(n / 2), Math.floor((2 * n) / 3)])].sort((a, b) => a - b);
    for (const k of ks) await this.mapasDoCorte(k);
    for (const ch of CALCULADOS) {
      if (janelaFixa(ch)) continue;
      let hi = 0;
      for (const k of ks) {
        const m = (await this.mapasDoCorte(k))[ch];
        const v = SUBTRACOES.has(ch) ? m : m.filter((x) => x > 0);
        if (v.length) hi = Math.max(hi, percentil(v, SUBTRACOES.has(ch) ? 99.8 : 99.5));
      }
      if (SUBTRACOES.has(ch)) {
        const w = Math.max(hi, 1);
        this.janelas.set(ch, [w / 3 - w / 2, w / 3 + w / 2]);
      } else this.janelas.set(ch, [0, Math.max(hi, 1e-3)]);
    }
  }

  private async pilhaDoCorte(k: number): Promise<Float32Array[]> {
    const imgs = await Promise.all(this.fases.map((f) => imageLoader.loadAndCacheImage(f[Math.min(k, f.length - 1)])));
    return imgs.map((im) => pixelsDa(im as Types.IImage));
  }

  /** Os mapas do corte k (calculados uma vez; os últimos 24 cortes ficam guardados, como no Ipê). */
  mapasDoCorte(k: number): Promise<Record<Chave, Float32Array>> {
    let p = this.corteCache.get(k);
    if (!p) {
      p = this.pilhaDoCorte(k).then((st) => calcularMapas(st, this.par));
      this.corteCache.set(k, p);
      while (this.corteCache.size > 24) this.corteCache.delete(this.corteCache.keys().next().value!);
    }
    return p;
  }

  private registrarChave(ch: string): void {
    if (this.registradas.has(ch)) return;
    this.registradas.add(ch);
    const prov = utilities.genericMetadataProvider;
    this.fases[0].forEach((id0, k) => {
      const id = `ipedin:${ch}:${k}`;
      const plano = metaData.get("imagePlaneModule", id0);
      const px = metaData.get("imagePixelModule", id0) || {};
      prov.add(id, { type: "imagePlaneModule", metadata: plano });
      prov.add(id, { type: "imagePixelModule", metadata: { ...px, samplesPerPixel: 1, photometricInterpretation: "MONOCHROME2",
        bitsAllocated: 32, bitsStored: 32, highBit: 31, pixelRepresentation: 1 } });
      prov.add(id, { type: "generalSeriesModule", metadata: { ...(metaData.get("generalSeriesModule", id0) || {}), modality: "MR" } });
      const j = this.janelas.get(ch) || janelaFixa(ch) || [0, 1];
      prov.add(id, { type: "voiLutModule", metadata: { windowCenter: [(j[0] + j[1]) / 2], windowWidth: [j[1] - j[0]] } });
      prov.add(id, { type: "modalityLutModule", metadata: { rescaleSlope: 1, rescaleIntercept: 0 } });
    });
  }

  /** 0.100.2: a fase `f` menos a pré-contraste, com `pais` da anatomia de volta (a "paisagem" do Ipê). */
  async subtracaoDaFase(ch: string, k: number): Promise<Float32Array> {
    const m = /^fs(\d+)p(\d+)$/.exec(ch)!;
    const f = Number(m[1]), pais = Number(m[2]) / 100;
    const st = await this.pilhaDoCorte(k);
    const a = st[Math.min(f, st.length - 1)], pre = st[this.par.pre];
    const out = new Float32Array(a.length);
    for (let i = 0; i < a.length; i++) out[i] = a[i] - pre[i] + pais * pre[i];
    return out;
  }

  /** A chave das imagens da fase com subtração (registrada, com a janela pronta). */
  private async chaveDaSubtracao(q: QuadroDin): Promise<string> {
    const ch = `fs${q.fase}p${Math.round(q.pais * 100)}`;
    if (!this.janelas.has(ch)) {
      const n = this.fases[0].length;
      const ks = [...new Set([Math.floor(n / 3), Math.floor(n / 2), Math.floor((2 * n) / 3)])];
      let lo = Infinity, hi = 0;
      for (const k of ks) {
        const v = await this.subtracaoDaFase(ch, k);
        hi = Math.max(hi, percentil(v, 99.8));
        lo = Math.min(lo, q.pais > 0 ? percentil(v, 1) : 0);
      }
      const w = Math.max(hi, 1);
      this.janelas.set(ch, q.pais > 0 ? [lo, hi] : [w / 3 - w / 2, w / 3 + w / 2]);
    }
    this.registrarChave(ch);
    return ch;
  }

  /** Uma imagem do Cornerstone3D com os valores do mapa (como `createAndCacheLocalImage`, sem o cache). */
  imagemDoMapa(imageId: string, dados: Float32Array): Types.IImage {
    const plano = metaData.get("imagePlaneModule", imageId) as { rows: number; columns: number; rowPixelSpacing: number; columnPixelSpacing: number; frameOfReferenceUID: string };
    const vm = utilities.VoxelManager.createImageVoxelManager({ height: plano.rows, width: plano.columns, numberOfComponents: 1,
      scalarData: dados, id: imageId } as never);
    let mn = Infinity, mx = -Infinity;
    for (const v of dados) { if (v < mn) mn = v; if (v > mx) mx = v; }
    const ch = imageId.split(":")[1];
    const j = this.janelas.get(ch) || janelaFixa(ch) || [mn, mx];
    return {
      imageId, intercept: 0, slope: 1, windowCenter: (j[0] + j[1]) / 2, windowWidth: j[1] - j[0], color: false,
      numberOfComponents: 1, dataType: "Float32Array", minPixelValue: mn, maxPixelValue: mx, rows: plano.rows,
      columns: plano.columns, height: plano.rows, width: plano.columns, rgba: false,
      columnPixelSpacing: plano.columnPixelSpacing, rowPixelSpacing: plano.rowPixelSpacing,
      FrameOfReferenceUID: plano.frameOfReferenceUID, invert: false, getPixelData: () => dados,
      voxelManager: vm, sizeInBytes: dados.byteLength,
    } as unknown as Types.IImage;
  }

  private serieDoMapa(ch: Chave): SerieCarregada {
    const n = this.fases[0].length;
    return { study: this.op.study, series: `ipedin-${ch}`, imageIds: Array.from({ length: n }, (_, k) => `ipedin:${ch}:${k}`),
      modalidade: "MR", descricao: tr(this.dados.mapas[ch]?.nome || ch), numero: "", semVolume: "mapa", bytes: 0,
      suv: null, suvMotivo: "" };
  }

  private serieDaFase(i: number): SerieCarregada {
    return { study: this.op.study, series: `ipedin-fase${i}`, imageIds: this.fases[i], modalidade: "MR",
      descricao: `${tr("Fase")} ${i + 1} · ${this.dados.fases[i].rotulo} · ${Math.round(this.dados.fases[i].tempo)} s`,
      numero: "", semVolume: "fase", bytes: 0, suv: null, suvMotivo: "" };
  }

  private async serieDoQuadro(q: QuadroDin): Promise<SerieCarregada> {
    if (q.v !== "fase") return this.serieDoMapa(q.v);
    if (!q.sub) return this.serieDaFase(q.fase);
    const ch = await this.chaveDaSubtracao(q);
    const n = this.fases[0].length;
    return { study: this.op.study, series: `ipedin-${ch}`, imageIds: Array.from({ length: n }, (_, k) => `ipedin:${ch}:${k}`),
      modalidade: "MR", descricao: this.rotuloDoQuadro(q), numero: "", semVolume: "fase", bytes: 0, suv: null, suvMotivo: "" };
  }

  /** "Fase 3/5 · 180 s · subtração + 20% anatomia", ou o nome do mapa. */
  rotuloDoQuadro(q: QuadroDin): string {
    if (q.v !== "fase") return tr(this.dados.mapas[q.v]?.nome || q.v);
    const f = this.dados.fases[q.fase];
    let s = `${tr("Fase")} ${q.fase + 1}/${this.dados.fases.length} · ${Math.round(f.tempo - this.par.tempos[this.par.pre])} s`;
    if (q.sub) s += ` · ${tr("subtração")}` + (q.pais > 0 ? ` + ${Math.round(q.pais * 100)}% ${tr("anatomia")}` : "");
    return s;
  }

  private corDoQuadro(q: QuadroDin): string {
    if (q.cor) return q.cor === "gray" ? "" : q.cor;
    return q.v === "fase" ? "" : this.dados.mapas[q.v]?.cores || "";
  }

  /** O menu do quadro (botão direito no rótulo): o que mostrar, a fase, a subtração, a paisagem e a cor. */
  private menuDoQuadro(i: number, ancora: HTMLElement): void {
    const q = this.quadros[i];
    const mudar = (novo: Partial<QuadroDin>) => void this.trocarQuadro(i, { ...q, ...novo });
    const cores: ItemMenu[] = [{ rotulo: tr("Padrão"), marcado: !q.cor, acao: () => mudar({ cor: "" }) },
      { rotulo: tr("Cinza"), marcado: q.cor === "gray", acao: () => mudar({ cor: "gray" }) },
      ...Object.entries(tabelasIpe).map(([k, tb]) => ({ rotulo: tr((tb as { nome?: string }).nome || k), marcado: q.cor === k,
        acao: () => mudar({ cor: k }) }))];
    const itens: ItemMenu[] = [
      { rotulo: tr("Mostrar"), sub: [
        ...this.dados.fases.map((f, k) => ({ rotulo: `${tr("Fase")} ${k + 1}: ${f.rotulo} (${Math.round(f.tempo)} s)`,
          marcado: q.v === "fase" && q.fase === k, acao: () => mudar({ v: "fase", fase: k }) })),
        { separador: true },
        ...CALCULADOS.map((c) => ({ rotulo: tr(this.dados.mapas[c]?.nome || c), marcado: q.v === c, acao: () => mudar({ v: c }) })),
      ] },
    ];
    if (q.v === "fase") {
      itens.push({ rotulo: tr("Subtração (fase − pré-contraste)"), marcado: q.sub, acao: () => mudar({ sub: !q.sub }) });
      itens.push({ rotulo: tr("Paisagem (anatomia na subtração)"), desligado: !q.sub, sub: PAISAGENS.map((f) => ({
        rotulo: f === 0 ? tr("Sem anatomia (subtração pura)") : `${Math.round(f * 100)}% ${tr("da anatomia")}`,
        marcado: Math.abs(f - q.pais) < 1e-6, acao: () => mudar({ pais: f }) })) });
    }
    itens.push({ rotulo: tr("Cor"), sub: cores });
    abrirMenu(itens, 0, 0, tr("Quadro"), ancora);
  }

  private async montar(): Promise<void> {
    const n = this.fases[0].length;
    const corte = this.g.quadros.length && this.g.raiz.classList.contains("din") ? this.corte() : Math.floor(n / 2);
    const series = await Promise.all(this.quadros.map((q) => this.serieDoQuadro(q)));
    const vazios: Spec[] = this.quadros.map(() => ({ serie: null, tipo: "pilha", plano: "AXIAL", projecao: "fino", espessura: 0 }));
    const linhas = this.quadros.length > 2 ? 2 : 1;
    this.g.montar(linhas, Math.ceil(this.quadros.length / linhas), vazios);
    this.g.raiz.classList.add("din");
    await Promise.all(this.quadros.map(async (q, i) => {
      await this.g.mostrar(i, series[i]);
      const vp = this.g.viewport(i) as Types.IStackViewport;
      if (!vp) return;
      await vp.setImageIdIndex(Math.min(corte, n - 1));
      const cor = this.corDoQuadro(q);
      const chave = q.v !== "fase" ? q.v : q.sub ? `fs${q.fase}p${Math.round(q.pais * 100)}` : "";
      const j = chave ? this.janelas.get(chave) || janelaFixa(chave) : null;
      vp.setProperties({ ...(j ? { voiRange: { lower: j[0], upper: j[1] } } : {}), ...(cor ? { colormap: { name: `ipe-${cor}` } } : {}) });
      vp.render();
      this.rotuloNoQuadro(i);
    }));
    // os quadros andam juntos pelos cortes
    for (const [i, q] of this.g.quadros.entries()) {
      q.el.addEventListener(Enums.Events.STACK_NEW_IMAGE, () => this.sincronizar(q.id));
      q.el.addEventListener(Enums.Events.IMAGE_RENDERED, () => this.desenharSobre());
      // a curva sob o cursor (3×3 pixels, como no Ipê)
      q.el.addEventListener("mousemove", (e) => this.aoMover(i, e as MouseEvent));
    }
    this.criarCamada();
    this.atualizarCurvas();
  }

  /** O rótulo do quadro, como no Ipê: ◂ ▸ passam de fase; clicar no texto (ou o botão direito) abre o menu do quadro
   * — o que mostrar, a fase, a subtração, a paisagem e a cor. */
  private rotuloNoQuadro(i: number): void {
    const cel = this.g.quadros[i]?.el.parentElement;
    if (!cel) return;
    cel.querySelector(".rotulo-din")?.remove();
    const q = this.quadros[i];
    const caixa = document.createElement("div");
    caixa.className = "rotulo-din";
    caixa.addEventListener("mousedown", (e) => e.stopPropagation());
    caixa.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); this.menuDoQuadro(i, texto); });
    const passo = (d: number, sim: string, dica: string) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = sim;
      b.title = tr(dica);
      b.setAttribute("aria-label", `${tr(dica)} (${tr("Quadro")} ${i + 1})`);
      b.onclick = (e) => {
        e.stopPropagation();
        const n = this.dados.fases.length;
        void this.trocarQuadro(i, { ...q, fase: (q.fase + d + n) % n });
      };
      return b;
    };
    const texto = document.createElement("button");
    texto.type = "button";
    texto.className = "texto-rotulo";
    texto.textContent = this.rotuloDoQuadro(q);
    texto.title = tr("Fase, subtração, paisagem e cor (também no botão direito)");
    texto.setAttribute("aria-label", `${tr("Quadro")} ${i + 1}: ${texto.textContent}`);
    texto.onclick = (e) => { e.stopPropagation(); this.menuDoQuadro(i, texto); };
    if (q.v === "fase") caixa.append(passo(-1, "◂", "Fase anterior"), texto, passo(1, "▸", "Próxima fase"));
    else caixa.append(texto);
    cel.append(caixa);
  }

  private moverPendente: { i: number; x: number; y: number } | null = null;

  private aoMover(i: number, e: MouseEvent): void {
    if (!this.curvaCursor) return;
    const vp = this.g.viewport(i) as Types.IStackViewport | null;
    if (!vp) return;
    const r = vp.canvas.getBoundingClientRect();
    const pendente = !this.moverPendente;
    this.moverPendente = { i, x: e.clientX - r.left, y: e.clientY - r.top };
    if (pendente) requestAnimationFrame(() => void this.curvaNoCursor());
  }

  /** A curva do ponto sob o cursor (média 3×3), em todas as fases. */
  async curvaNoCursor(ponto?: { i: number; x: number; y: number }): Promise<void> {
    const m = ponto ?? this.moverPendente;
    this.moverPendente = null;
    if (!m) return;
    const vp = this.g.viewport(m.i) as Types.IStackViewport | null;
    const id = vp?.getCurrentImageId();
    if (!vp || !id) return;
    const k = vp.getCurrentImageIdIndex();
    const mundo = vp.canvasToWorld([m.x, m.y] as Types.Point2);
    const ij = utilities.worldToImageCoords(this.fases[0][k], mundo as Types.Point3) as unknown as number[] | undefined;
    if (!ij) return;
    const plano = metaData.get("imagePlaneModule", this.fases[0][k]) as { rows: number; columns: number };
    const x = Math.floor(ij[0]), y = Math.floor(ij[1]);
    if (x < 0 || y < 0 || x >= plano.columns || y >= plano.rows) return;
    const st = await this.pilhaDoCorte(k);
    const valores = st.map((f) => media3x3(f, plano.columns, plano.rows, x, y));
    this.hover = { k, x, y, valores };
    this.desenharCurvas();
  }

  private sincronizar(origem: string): void {
    if (this.rolando) return;
    const q0 = this.g.quadros.find((q) => q.id === origem);
    const vp0 = q0 ? this.g.viewport(this.g.quadros.indexOf(q0)) as Types.IStackViewport : null;
    if (!vp0) return;
    const k = vp0.getCurrentImageIdIndex();
    this.rolando = true;
    try {
      this.g.quadros.forEach((q, i) => {
        if (q.id === origem) return;
        const vp = this.g.viewport(i) as Types.IStackViewport;
        if (vp && vp.getCurrentImageIdIndex() !== k) void vp.setImageIdIndex(k);
      });
    } finally {
      this.rolando = false;
    }
  }

  corte(): number {
    return (this.g.viewport(0) as Types.IStackViewport)?.getCurrentImageIdIndex() ?? 0;
  }

  // ---------------------------------------------------------------- a barra
  private montarBarra(): void {
    const titulo = document.createElement("strong");
    titulo.textContent = tr("Dinâmica da mama");
    const rotulo = (txt: string, el: HTMLElement) => {
      const l = document.createElement("label");
      l.append(document.createTextNode(`${tr(txt)} `), el);
      return l;
    };
    const fases = this.dados.fases.map((f, i) => `${i + 1}. ${f.rotulo} (${Math.round(f.tempo)} s)`);
    const escolha = (valores: string[], sel: number, fn: (i: number) => void, nome: string) => {
      const s = document.createElement("select");
      s.setAttribute("aria-label", tr(nome));
      valores.forEach((v, i) => s.append(new Option(v, String(i), false, i === sel)));
      s.onchange = () => fn(Number(s.value));
      return s;
    };
    const sPre = escolha(fases, this.par.pre, (i) => void this.mudarFases(i, this.par.inicial, this.par.tardia), "Pré-contraste");
    const sIni = escolha(fases, this.par.inicial, (i) => void this.mudarFases(this.par.pre, i, this.par.tardia), "Fase inicial");
    const sTar = escolha(fases, this.par.tardia, (i) => void this.mudarFases(this.par.pre, this.par.inicial, i), "Fase tardia");
    // o que vai em cada quadro
    const opcoesQuadro: (Chave | "fase")[] = ["fase", ...CALCULADOS];
    const nomeQ = (q: Chave | "fase") => (q === "fase" ? tr("Fase") : tr(this.dados.mapas[q]?.nome || q));
    const quadros = this.quadros.map((q, i) => escolha(opcoesQuadro.map(nomeQ), opcoesQuadro.indexOf(q.v),
      (j) => void this.trocarQuadro(i, { ...this.quadros[i], v: opcoesQuadro[j] }), `Quadro ${i + 1}`));
    this.selectsQuadro = quadros;
    // a fusão sobre a fase
    const opcoesSobre: { rotulo: string; valor: ModoDinamica["sobre"] }[] = [
      { rotulo: tr("Nada"), valor: null },
      ...CALCULADOS.filter((c) => c !== "sub").map((c) => ({ rotulo: tr(this.dados.mapas[c]?.nome || c), valor: { tipo: "mapa" as const, chave: c } })),
      ...this.dados.mapas_salvos.map((s) => ({ rotulo: `${tr("Salvo")}: ${s.descricao}`, valor: { tipo: "salvo" as const, series: s.series, chave: s.chave } })),
    ];
    const sSobre = escolha(opcoesSobre.map((o) => o.rotulo), 0, (j) => void this.mudarSobre(opcoesSobre[j].valor), "Sobre a fase");
    const chavesCor = ["", ...Object.keys(tabelasIpe)];
    const sCorSobre = escolha(chavesCor.map((k) => (k ? tr((tabelasIpe[k] as { nome?: string }).nome || k) : tr("Padrão"))), 0,
      (j) => { this.corSobre = chavesCor[j]; this.desenharSobre(); }, "Cor da fusão");
    const cCurva = document.createElement("input");
    cCurva.type = "checkbox";
    cCurva.checked = this.curvaCursor;
    cCurva.setAttribute("aria-label", tr("Curva sob o cursor"));
    cCurva.onchange = () => { this.curvaCursor = cCurva.checked; if (!cCurva.checked) { this.hover = null; this.desenharCurvas(); } };
    const op = document.createElement("input");
    op.type = "range";
    op.min = "0";
    op.max = "100";
    op.value = String(this.opacidade * 100);
    op.setAttribute("aria-label", tr("Opacidade"));
    op.oninput = () => { this.opacidade = Number(op.value) / 100; this.desenharSobre(); };
    const sair = document.createElement("button");
    sair.type = "button";
    sair.textContent = tr("Fechar a dinâmica");
    sair.onclick = () => this.sair();
    const aviso = document.createElement("span");
    aviso.className = "nota-din";
    aviso.textContent = this.dados.com_horario ? "" : tr("Sem o horário das fases: uma fase por minuto.");
    this.barra.append(titulo, rotulo("Pré", sPre), rotulo("Inicial", sIni), rotulo("Tardia", sTar),
      ...quadros.map((q, i) => rotulo(`Q${i + 1}`, q)), rotulo("Sobre a fase", sSobre), rotulo("Cor", sCorSobre),
      rotulo("Opacidade", op), rotulo("Curva sob o cursor", cCurva), aviso, sair);
  }

  async mudarFases(pre: number, inicial: number, tardia: number): Promise<void> {
    if (!(pre < inicial && inicial <= tardia)) {
      this.op.aviso(tr("A fase inicial deve vir depois do pré-contraste, e a tardia não pode vir antes da inicial."));
      return;
    }
    this.par = { ...this.par, pre, inicial, tardia };
    this.corteCache.clear();
    // as imagens dos mapas de antes saem do cache (as das fases ficam)
    for (const ch of this.registradas) {
      this.fases[0].forEach((_id, k) => { try { cache.removeImageLoadObject(`ipedin:${ch}:${k}`); } catch { /* não estava */ } });
    }
    for (const ch of [...this.janelas.keys()]) if (ch.startsWith("fs")) this.janelas.delete(ch);
    this.registradas.clear();
    await this.prepararJanelas();
    for (const ch of CALCULADOS) this.registrarChave(ch);
    await this.montar();
  }

  async trocarQuadro(i: number, q: QuadroDin | Chave | "fase"): Promise<void> {
    const novo = typeof q === "string" ? { ...this.quadros[i], v: q } : q;
    this.quadros[i] = novo;
    const s = this.selectsQuadro?.[i];
    if (s) s.value = String(["fase", ...CALCULADOS].indexOf(novo.v));
    await this.montar();
  }

  private selectsQuadro: HTMLSelectElement[] = [];

  // ---------------------------------------------------------------- o mapa por cima da fase (fusão)
  private criarCamada(): void {
    this.camada?.remove();
    const i = this.quadros.findIndex((q) => q.v === "fase");
    if (i < 0) { this.camada = null; return; }
    const c = document.createElement("canvas");
    c.className = "camada-din";
    this.g.quadros[i].el.parentElement!.insertBefore(c, this.g.quadros[i].textos);
    this.camada = c;
    this.desenharSobre();
  }

  async mudarSobre(v: ModoDinamica["sobre"]): Promise<void> {
    this.sobre = v;
    if (v?.tipo === "salvo" && !this.salvos.has(v.series)) {
      const s = await carregarSerie(this.op.study, v.series);
      if (s) this.salvos.set(v.series, s);
    }
    this.desenharSobre();
  }

  /** Os valores do mapa sobreposto no corte k e a janela dele. */
  private async valoresSobre(k: number): Promise<{ v: Float32Array; j: [number, number]; cor: string; ch: string } | null> {
    const s = this.sobre;
    if (!s) return null;
    if (s.tipo === "mapa") {
      return { v: (await this.mapasDoCorte(k))[s.chave], j: this.janelas.get(s.chave) || janelaFixa(s.chave)!,
        cor: this.dados.mapas[s.chave]?.cores || "", ch: s.chave };
    }
    const serie = this.salvos.get(s.series);
    if (!serie) return null;
    const id = serie.imageIds[Math.min(k, serie.imageIds.length - 1)];
    const v = pixelsDa((await imageLoader.loadAndCacheImage(id)) as Types.IImage);
    let j = janelaFixa(s.chave) || this.janelas.get(s.chave);
    if (!j) j = [0, percentil(v.filter((x) => x > 0), 99.5) || 1];
    return { v, j, cor: this.dados.mapas[s.chave]?.cores || "", ch: s.chave };
  }

  private desenhando = 0;

  /** Desenha o mapa por cima da fase, com a câmera do quadro (zoom, pan, giro e espelho). */
  desenharSobre(): void {
    const c = this.camada;
    if (!c) return;
    const n = ++this.desenhando;
    const i = this.quadros.findIndex((q) => q.v === "fase");
    const vp = this.g.viewport(i) as Types.IStackViewport | null;
    const id = vp?.getCurrentImageId();
    const ctx = c.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    const w = c.parentElement!.clientWidth, h = c.parentElement!.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    if (!vp || !id || !this.sobre) return;
    const k = vp.getCurrentImageIdIndex();
    void this.valoresSobre(k).then((r) => {
      if (!r || n !== this.desenhando) return;
      const plano = metaData.get("imagePlaneModule", id) as { rows: number; columns: number };
      const W = plano.columns, H = plano.rows;
      if (r.v.length !== W * H) return;
      const lut = tabelaDeCores(this.corSobre || r.cor);
      const img = new ImageData(W, H);
      const [lo, hi] = r.j;
      for (let p = 0; p < r.v.length; p++) {
        const x = r.v[p];
        // o que não tem valor fica transparente: o fundo do mapa, o SER sem realce, o cinético sem cor
        if (!(x > lo) || (r.ch === "ser" && x < 0) || (r.ch === "cin" && x < 0.5)) continue;
        const f = Math.min(1, Math.max(0, (x - lo) / (hi - lo || 1)));
        const q = Math.round(f * 255) * 3;
        img.data[p * 4] = lut[q];
        img.data[p * 4 + 1] = lut[q + 1];
        img.data[p * 4 + 2] = lut[q + 2];
        img.data[p * 4 + 3] = Math.round(255 * this.opacidade);
      }
      const fora = document.createElement("canvas");
      fora.width = W;
      fora.height = H;
      fora.getContext("2d")!.putImageData(img, 0, 0);
      const p0 = vp.worldToCanvas(utilities.imageToWorldCoords(id, [0, 0]) as Types.Point3);
      const px = vp.worldToCanvas(utilities.imageToWorldCoords(id, [1, 0]) as Types.Point3);
      const py = vp.worldToCanvas(utilities.imageToWorldCoords(id, [0, 1]) as Types.Point3);
      ctx.setTransform(dpr * (px[0] - p0[0]), dpr * (px[1] - p0[1]), dpr * (py[0] - p0[0]), dpr * (py[1] - p0[1]),
        dpr * p0[0], dpr * p0[1]);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(fora, 0, 0);
      c.dataset.desenhado = String(k);
    });
  }

  // ---------------------------------------------------------------- as curvas das ROIs
  async atualizarCurvas(): Promise<void> {
    const rois = roisDaTela().filter((r) => this.corteDaImagem(r.imageId) !== null);
    const novas: typeof this.curvas = [];
    for (const r of rois) {
      const k = this.corteDaImagem(r.imageId)!;
      const st = await this.pilhaDoCorte(k);
      const plano = metaData.get("imagePlaneModule", this.fases[0][k]) as { rows: number; columns: number };
      const valores: number[] = [];
      let n = 0;
      for (const f of st) {
        if (r.kind === "probe") {
          valores.push(media3x3(f, plano.columns, plano.rows, Math.floor(r.pts[0][0]), Math.floor(r.pts[0][1])));
          n = 9;
          continue;
        }
        const e = estatRoi(f, plano.columns, plano.rows, r.kind, r.pts, null as never);
        valores.push(e.media ?? NaN);
        n = e.n;
      }
      if (n > 0) novas.push({ uid: r.uid, valores, n });
    }
    this.curvas = novas;
    this.desenharCurvas();
  }

  /** O corte da imagem (de uma fase ou de um mapa desta dinâmica), ou null. */
  private corteDaImagem(id: string): number | null {
    const m = /^ipedin:[a-z0-9]+:(\d+)$/.exec(id);
    if (m) return Number(m[1]);
    for (const f of this.fases) {
      const k = f.indexOf(id);
      if (k >= 0) return k;
    }
    return null;
  }

  /** A curva sob o cursor (ou null). */
  resumoDoCursor(): Record<string, unknown> | null {
    if (!this.hover) return null;
    return { ...this.resumo([{ uid: "cursor", valores: this.hover.valores, n: 9 }])[0], cursor: true,
      ponto: [this.hover.x, this.hover.y], corte: this.hover.k };
  }

  /** Os números de cada curva (para o painel e para os testes). */
  resumoDasCurvas(): Record<string, unknown>[] {
    return this.resumo(this.curvas);
  }

  private resumo(curvas: { uid: string; valores: number[]; n: number }[]): Record<string, unknown>[] {
    const p = this.par;
    const tMin = p.tempos.slice(p.pre).map((t) => (t - p.tempos[p.pre]) / 60);
    return curvas.map((c, i) => {
      const s0 = c.valores[p.pre];
      const e = c.valores.slice(p.pre).map((v) => (v - s0) / (Math.abs(s0) > 1e-6 ? s0 : 1e-6) * 100);
      const eDesc = [0, ...e.slice(1)];
      const d = descritores(eDesc, tMin);
      const s1 = c.valores[p.inicial], s2 = c.valores[p.tardia];
      const ser = s2 - s0 > 0 ? (s1 - s0) / (s2 - s0) : null;
      let iPico = 0;
      e.forEach((v, j) => { if (v > e[iPico]) iPico = j; });
      return { n: i + 1, uid: c.uid, pixels: c.n, valores: c.valores, realce: e,
        classe: classeDaCurva(c.valores, p, this.dados.classes),
        inicial: (s1 - s0) / (Math.abs(s0) > 1e-6 ? s0 : 1e-6) * 100, ser, pico: Math.max(...e),
        ttp: tMin[iPico] * 60, ...d };
    });
  }

  private desenharCurvas(): void {
    const cursor = this.resumoDoCursor();
    const r = [...(cursor ? [cursor] : []), ...this.resumoDasCurvas()];
    const p = this.par;
    this.painel.replaceChildren();
    const titulo = document.createElement("div");
    titulo.className = "titulo-painel";
    titulo.textContent = tr("Curvas tempo-intensidade");
    this.painel.append(titulo);
    if (!r.length) {
      const d = document.createElement("div");
      d.className = "dica";
      d.textContent = tr("Passe o mouse sobre a imagem para ver a curva do ponto, ou marque um ponto (valor do pixel) ou uma ROI para guardar a curva.");
      this.painel.append(d);
      return;
    }
    // o gráfico: realce (%) × tempo (min)
    const W = 320, H = 170, m = { e: 40, d: 10, c: 10, b: 28 };
    const tMin = p.tempos.slice(p.pre).map((t) => (t - p.tempos[p.pre]) / 60);
    const todas = r.flatMap((x) => x.realce as number[]);
    const yMax = Math.max(10, ...todas) * 1.1, yMin = Math.min(0, ...todas);
    const xMax = Math.max(...tMin) || 1;
    const X = (t: number) => m.e + (t / xMax) * (W - m.e - m.d);
    const Y = (v: number) => H - m.b - ((v - yMin) / (yMax - yMin)) * (H - m.b - m.c);
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "grafico-din");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", tr("Curvas tempo-intensidade"));
    const linha = (x1: number, y1: number, x2: number, y2: number, cls: string) => {
      const l = document.createElementNS(ns, "line");
      Object.entries({ x1, y1, x2, y2 }).forEach(([k, v]) => l.setAttribute(k, String(v)));
      l.setAttribute("class", cls);
      svg.append(l);
    };
    const texto = (x: number, y: number, t: string, anc = "middle") => {
      const e = document.createElementNS(ns, "text");
      e.setAttribute("x", String(x));
      e.setAttribute("y", String(y));
      e.setAttribute("text-anchor", anc);
      e.textContent = t;
      svg.append(e);
    };
    linha(m.e, H - m.b, W - m.d, H - m.b, "eixo");
    linha(m.e, m.c, m.e, H - m.b, "eixo");
    linha(m.e, Y(0), W - m.d, Y(0), "zero");
    texto(W / 2, H - 4, tr("tempo (min)"));
    texto(m.e - 4, Y(yMax / 1.1) + 4, `${Math.round(yMax / 1.1)}%`, "end");
    texto(m.e - 4, Y(0) + 4, "0", "end");
    for (const t of tMin) texto(X(t), H - m.b + 12, t.toFixed(1));
    const corDe = (c: Record<string, unknown>, i: number) => (c.cursor ? "#ffffff" : CORES_CURVAS[(cursor ? i - 1 : i) % CORES_CURVAS.length]);
    r.forEach((c, i) => {
      const cor = corDe(c, i);
      const pl = document.createElementNS(ns, "polyline");
      if (c.cursor) pl.setAttribute("stroke-dasharray", "4 3");
      pl.setAttribute("points", (c.realce as number[]).map((v, j) => `${X(tMin[j]).toFixed(1)},${Y(v).toFixed(1)}`).join(" "));
      pl.setAttribute("stroke", cor);
      pl.setAttribute("class", "curva");
      svg.append(pl);
    });
    this.painel.append(svg);
    const tab = document.createElement("table");
    tab.className = "tabela-din";
    const cab = [tr("ROI"), tr("Classe"), tr("Realce inicial"), "SER", tr("Pico"), "TTP", "BAT", tr("Lavagem"), "iAUC90", "MRT"];
    tab.append(...[cab].map((c) => {
      const tr_ = document.createElement("tr");
      c.forEach((t) => { const th = document.createElement("th"); th.textContent = t; tr_.append(th); });
      return tr_;
    }));
    const f1 = (v: unknown, suf = "") => (typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(v >= 100 ? 0 : 1)}${suf}` : "—");
    r.forEach((c, i) => {
      const linhaT = document.createElement("tr");
      const cel = (t: string, cor?: string) => { const td = document.createElement("td"); td.textContent = t; if (cor) td.style.color = cor; linhaT.append(td); };
      cel(c.cursor ? `◌ ${tr("cursor")}` : `● ${cursor ? i : i + 1}`, corDe(c, i));
      cel(tr(String(c.classe)));
      cel(f1(c.inicial, "%"));
      cel(typeof c.ser === "number" ? (c.ser as number).toFixed(2) : "—");
      cel(f1(c.pico, "%"));
      cel(f1(c.ttp, " s"));
      cel(f1(c.bat, " s"));
      cel(f1(c.wash, "%/min"));
      cel(f1(c.iauc));
      cel(f1(c.mrt, " s"));
      tab.append(linhaT);
    });
    this.painel.append(tab);
    const nota = document.createElement("div");
    nota.className = "dica";
    nota.textContent = `${tr("Fase inicial")} ${p.inicial + 1} (${Math.round(p.tempos[p.inicial] - p.tempos[p.pre])} s), ` +
      `${tr("tardia")} ${p.tardia + 1} (${Math.round(p.tempos[p.tardia] - p.tempos[p.pre])} s). ` +
      `${tr("Realce médio de")} ${p.limiar}–${p.rapido}%, ${tr("rápido acima disso")}; ${tr("tardio")} ±${p.tardio}%.`;
    this.painel.append(nota);
  }

  /** Para os testes: os parâmetros e o corte de agora. */
  estado(): Record<string, unknown> {
    return { par: this.par, corte: this.corte(), quadros: this.quadros.map((q) => q.v), detalhe: this.quadros,
      sobre: this.sobre, corSobre: this.corSobre, desenhado: this.camada?.dataset.desenhado ?? null,
      rotulos: this.g.quadros.map((q) => q.el.parentElement?.querySelector(".rotulo-din .texto-rotulo")?.textContent || "") };
  }

  sair(): void {
    this.encerrar();
    this.op.aoSair();
  }

  encerrar(): void {
    for (const f of this.soltar) f();
    this.soltar = [];
    this.camada?.remove();
    this.g.raiz.classList.remove("din");
    this.barra.remove();
    this.painel.remove();
    if (atual === this) atual = null;
  }

  /** Quando as ROIs mudam (o painel liga isto aos eventos das medidas). */
  ouvir(soltar: () => void): void {
    this.soltar.push(soltar);
  }
}

/** Média 3×3 em volta do pixel (x, y) (só os que caem na imagem). */
export function media3x3(f: Float32Array, w: number, h: number, x: number, y: number): number {
  let s = 0, n = 0;
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const xx = x + dx, yy = y + dy;
      if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
      s += f[yy * w + xx];
      n++;
    }
  }
  return n ? s / n : NaN;
}

// ------------------------------------------------------------------ tabela de cores em 256 tons
const LUTS = new Map<string, Uint8Array>();
let tabelasIpe: Record<string, { pontos: number[][]; nome?: string }> = {};

export function guardarTabelas(t: Record<string, { pontos: number[][]; nome?: string }> | undefined): void {
  tabelasIpe = t || {};
  LUTS.clear();
}

function tabelaDeCores(chave: string): Uint8Array {
  const k = chave || "gray";
  let lut = LUTS.get(k);
  if (lut) return lut;
  lut = new Uint8Array(256 * 3);
  const pts = tabelasIpe[k]?.pontos;
  for (let i = 0; i < 256; i++) {
    const x = i / 255;
    let rgb = [x, x, x];
    if (pts && pts.length) {
      let j = 0;
      while (j + 1 < pts.length && pts[j + 1][0] < x) j++;
      const a = pts[j], b = pts[Math.min(j + 1, pts.length - 1)];
      const f = b[0] > a[0] ? Math.min(1, Math.max(0, (x - a[0]) / (b[0] - a[0]))) : 0;
      rgb = [1, 2, 3].map((c) => a[c] + (b[c] - a[c]) * f);
    }
    lut[i * 3] = Math.round(rgb[0] * 255);
    lut[i * 3 + 1] = Math.round(rgb[1] * 255);
    lut[i * 3 + 2] = Math.round(rgb[2] * 255);
  }
  LUTS.set(k, lut);
  return lut;
}

(window as unknown as Record<string, unknown>).__ipeDinContas = { calcularMapas, classeDaCurva, descritores, percentil }; // testes
