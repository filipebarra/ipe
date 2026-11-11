// Conversa com o servidor central: login, DICOMweb (QIDO, metadados, quadros, miniatura), configuração.
// O token fica só na memória da aba: recarregar a página pede o login de novo (nada do paciente no disco).

export class SessaoEncerrada extends Error {}

let token = "";
let aoEncerrar: (() => void) | null = null;

export const DICOMWEB = `${location.origin}/dicomweb`;

export function tokenAtual(): string {
  return token;
}

export function quandoEncerrar(fn: () => void): void {
  aoEncerrar = fn;
}

export function cabecalhos(): Record<string, string> {
  const h: Record<string, string> = { "X-Ipe-Web": "1" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function pedir(url: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(url, { ...init, headers: { ...cabecalhos(), ...(init.headers || {}) }, cache: "no-store" });
  if (r.status === 401 && token) {
    token = "";
    aoEncerrar?.();
    throw new SessaoEncerrada("401");
  }
  return r;
}

export interface Usuario {
  username: string;
  full_name: string;
  role: string;
  perms: string[];
}

export async function entrar(username: string, password: string): Promise<Usuario> {
  const r = await fetch(`${location.origin}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Ipe-Web": "1" },
    body: JSON.stringify({ username, password }),
    cache: "no-store",
  });
  if (r.status === 401) throw new Error("401");
  if (r.status === 429) throw new Error("429");
  if (!r.ok) throw new Error(String(r.status));
  const d = await r.json();
  token = d.token;
  return d as Usuario;
}

export async function sair(): Promise<void> {
  try {
    await pedir(`${location.origin}/api/logout`);
  } catch {
    /* já saiu */
  }
  token = "";
}

export interface Config {
  usuario: Usuario;
  lang: string;
  versao: string;
  "viewer.wl_presets": Record<string, [string, number, number]> | null;
  "viewer.wl_presets_mod": Record<string, Record<string, [string, number, number]>> | null;
  hanging_protocols: unknown;
  mg_protocols: unknown;
  /** 0.99.94 (W3): as tabelas de cores do Ipê — pontos [posição 0–1, r, g, b em 0–1] */
  tabelas_cores?: Record<string, { nome: string; pontos: number[][] }>;
}

export async function configuracao(): Promise<Config> {
  const r = await pedir(`${location.origin}/api/web/config`);
  return (await r.json()) as Config;
}

export async function avisarAbertura(studyUid: string): Promise<void> {
  await pedir(`${location.origin}/api/web/abriu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ study_uid: studyUid }),
  });
}

export type DicomJson = Record<string, { vr: string; Value?: unknown[]; BulkDataURI?: string }>;

export function valor(d: DicomJson, tag: string, i = 0): unknown {
  const v = d[tag]?.Value;
  return v && v.length > i ? v[i] : undefined;
}

export function texto(d: DicomJson, tag: string): string {
  const v = valor(d, tag);
  if (v == null) return "";
  if (typeof v === "object" && v !== null && "Alphabetic" in (v as object)) {
    return String((v as { Alphabetic: string }).Alphabetic || "").replace(/\^/g, " ").trim();
  }
  return String(v);
}

export async function qido(caminho: string): Promise<DicomJson[]> {
  const r = await pedir(`${DICOMWEB}${caminho}`, { headers: { Accept: "application/dicom+json" } });
  if (r.status === 404) return [];
  if (!r.ok) throw new Error(String(r.status));
  return (await r.json()) as DicomJson[];
}

export async function metadados(study: string, series: string): Promise<DicomJson[]> {
  const r = await pedir(`${DICOMWEB}/studies/${study}/series/${series}/metadata`);
  if (!r.ok) return [];
  return (await r.json()) as DicomJson[];
}

export async function miniatura(study: string, series: string): Promise<string> {
  const r = await pedir(`${DICOMWEB}/studies/${study}/series/${series}/thumbnail`);
  if (!r.ok) return "";
  return URL.createObjectURL(await r.blob());
}

// ------------------------------------------------------------------ PET/CT (0.99.94, W3)
/** O fator de SUV (pelo peso) da série de PET, pela conta do Ipê; `null` com o motivo quando não dá. */
export async function fatorSuv(study: string, series: string): Promise<{ fator: number | null; motivo: string }> {
  const r = await pedir(`${location.origin}/api/web/suv?study=${encodeURIComponent(study)}&series=${encodeURIComponent(series)}`);
  if (!r.ok) return { fator: null, motivo: String(r.status) };
  return (await r.json()) as { fator: number | null; motivo: string };
}

export interface MapaSeg {
  ref_series: string;
  descricao: string;
  segmentos: { n: number; nome: string; cor: number[] }[];
  fatias: { sop: string; r0: number; c0: number; h: number; w: number; dados: string }[];
}

/** 0.100.2: um objeto de overlay do Ipê (CAD/IA, GSPS, RTSTRUCT), em pixels da imagem. */
export interface GraficoOv { tipo: string; pontos: number[][]; texto?: string; cor?: number[]; quadro?: number }
export interface ObjetoOv {
  chave: string; fonte: string; rotulo: string; cor: number[]; achados: string[]; serie: string; descricao: string;
  por_sop: Record<string, GraficoOv[]>; todos: GraficoOv[];
  planos: { tipo: string; pontos3d: number[][]; texto?: string; cor?: number[] }[];
  mascaras: { sop: string; quadro: number; r0: number; c0: number; h: number; w: number; bits: string; cor: number[];
    rotulo: string; escala?: number[] }[];
  so_serie: string; serie_ref: string;
  /** 0.100.14: nomes em 3D (níveis da coluna, níveis linfonodais): pontos em mm, o nome vai no centro dos que o
   *  plano do quadro corta */
  rotulos3d?: { texto: string; cor: number[]; tol: number; pontos: number[][] }[];
  ia?: boolean;
}
export interface Overlays { tipos: Record<string, string>; ocultos: string[]; objetos: ObjetoOv[] }

/** 0.100.14: as séries com IA (resultado de IA ou analisadas por uma), para o selo nas miniaturas. */
export async function seriesIA(study: string): Promise<Record<string, { resultado: boolean; ferramentas: string[]; dica: string }>> {
  const r = await pedir(`${location.origin}/api/web/series_ia?study=${encodeURIComponent(study)}`);
  if (!r.ok) return {};
  return ((await r.json()) as { series: Record<string, { resultado: boolean; ferramentas: string[]; dica: string }> }).series || {};
}

export async function overlays(study: string): Promise<Overlays | null> {
  const r = await pedir(`${location.origin}/api/web/overlays?study=${encodeURIComponent(study)}`);
  if (!r.ok) return null;
  return (await r.json()) as Overlays;
}

/** A SEG como mapa de rótulos sobre a série de origem (o servidor lê a SEG como o Ipê). */
export async function mapaSeg(study: string, series: string): Promise<MapaSeg | null> {
  const r = await pedir(`${location.origin}/api/web/seg?study=${encodeURIComponent(study)}&series=${encodeURIComponent(series)}`);
  if (!r.ok) return null;
  return (await r.json()) as MapaSeg;
}

/** Os bytes de uma fatia (zlib + base64). */
export async function descomprimir(b64: string): Promise<Uint8Array> {
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const fluxo = new Blob([bin]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(fluxo).arrayBuffer());
}

// ------------------------------------------------------------------ mamografia (0.99.98, W4)
/** A segunda tela da mamografia recebe o token da primeira (a janela que a abriu), sem pedir a senha. */
export function usarToken(t: string): void {
  token = t;
}

export interface ImagemMg {
  study: string; series: string; sop: string; quadros: number; tomo: boolean; inicio: number;
  serie: string; rotulo: string;
  largura?: number; altura?: number; caixa?: number[] | null; parede?: string; mamilo?: number[] | null;
  /** 0.100.17: mm por pixel no plano da mama (ImagerPixelSpacing, grupos funcionais da tomo) */
  mm?: number;
}

export interface CelulaMg {
  codigo: string; rotulo?: string; anterior?: number; data?: string; nota?: string;
  sop?: string; alt?: string; quer?: "left" | "right" | null;
  /** 0.100.2: a pilha do quadro, como no Ipê — as 2D da mesma mama e incidência e, depois, os cortes da tomo */
  pilha?: MembroMg[];
}

export interface MembroMg { study: string; series: string; sop: string; tomo: boolean; quadros: number }

export interface TelaMg { rows: number; cols: number; celulas: CelulaMg[] }

export interface Mamografia {
  protocolo: string | null; motivo?: string; protocolos: string[]; indice: number;
  espelhar: boolean; encostar: boolean; zoom_junto: boolean; alinhar: string; margem: number;
  passos: { nome: string; enquadre: string; telas: Record<string, TelaMg[]> }[];
  imagens: Record<string, ImagemMg>;
  anteriores: { n: number; study: string; data: string }[];
}

/** O protocolo de mamografia do exame, resolvido no servidor com as regras do Ipê; `null` quando não se aplica. */
export async function mamografia(study: string, protocolo?: number): Promise<Mamografia | null> {
  const extra = protocolo === undefined ? "" : `&protocolo=${protocolo}`;
  const r = await pedir(`${location.origin}/api/web/mamografia?study=${encodeURIComponent(study)}${extra}`);
  if (!r.ok) return null;
  const d = (await r.json()) as Mamografia;
  return d.protocolo ? d : null;
}

// ------------------------------------------------------------------ RPC do servidor central (0.99.98, W6: laudo)
function decodificar(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(decodificar);
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("__dt__" in o) return o.__dt__;
    if ("__d__" in o) return o.__d__;
    if ("__t__" in o) return decodificar(o.__t__);
    if ("__s__" in o) return decodificar(o.__s__);
    if ("__dc__" in o) return decodificar(o.f);
    return Object.fromEntries(Object.entries(o).map(([k, x]) => [k, decodificar(x)]));
  }
  return v;
}

/** Chama um método do banco no servidor, com as mesmas regras (permissão, banco pessoal, trava do laudo) do
 * programa do consultório ligado ao servidor. O erro vem com o texto do servidor. */
export async function rpc<T = unknown>(method: string, args: unknown[] = [], kwargs: Record<string, unknown> = {}): Promise<T> {
  const r = await pedir(`${location.origin}/api/rpc`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ method, args, kwargs }),
  });
  const d = (await r.json().catch(() => ({}))) as { result?: unknown; error?: string };
  if (!r.ok) throw new Error(d.error || String(r.status));
  return decodificar(d.result) as T;
}
