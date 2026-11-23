// Conversa com o servidor central: login, DICOMweb (QIDO, metadados, quadros, miniatura), configuração.
// 0.100.18: o token fica na sessão da aba (sessionStorage): some ao fechar a aba, mas sobrevive a um recarregamento —
// no celular o navegador recarrega a página sozinho (memória, troca de aplicativo) e o login voltava logo depois de
// entrar. As janelas de visualização abertas pela lista herdam a sessão. Nada do paciente vai para o disco.

export class SessaoEncerrada extends Error {}

const CHAVE_TOKEN = "ipe.web.token";
// 0.100.104: "Manter conectado neste computador" — o token também fica no localStorage até o servidor deixar
// (1 dia), e assim vale nas outras abas e nos links de abertura (#/abrir?…). Só o token: nada do paciente.
const CHAVE_LEMBRAR = "ipe.web.lembrar";
function lerLembrado(): string {
  try {
    const d = JSON.parse(localStorage.getItem(CHAVE_LEMBRAR) || "null") as { t: string; ate: number } | null;
    if (d && d.t && d.ate * 1000 > Date.now()) return d.t;
    if (d) localStorage.removeItem(CHAVE_LEMBRAR);
  } catch { /* sem armazenamento */ }
  return "";
}
function lerToken(): string {
  let t = "";
  try { t = sessionStorage.getItem(CHAVE_TOKEN) || ""; } catch { /* sem armazenamento */ }
  return t || lerLembrado();
}
function guardarToken(t: string, lembrarAte = 0): void {
  try { if (t) sessionStorage.setItem(CHAVE_TOKEN, t); else sessionStorage.removeItem(CHAVE_TOKEN); } catch { /* sem armazenamento */ }
  try {
    if (t && lembrarAte > 0) localStorage.setItem(CHAVE_LEMBRAR, JSON.stringify({ t, ate: lembrarAte }));
    else if (!t) localStorage.removeItem(CHAVE_LEMBRAR);
  } catch { /* sem armazenamento */ }
}
/** Até quando este navegador fica conectado (0 = só nesta aba). */
export function lembradoAte(): number {
  try { return (JSON.parse(localStorage.getItem(CHAVE_LEMBRAR) || "null") as { ate: number } | null)?.ate || 0; } catch { return 0; }
}
let token = lerToken();
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

export async function pedir(url: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(url, { ...init, headers: { ...cabecalhos(), ...(init.headers || {}) }, cache: "no-store" });
  if (r.status === 401 && token) {
    token = "";
    guardarToken("");
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
  must_change?: boolean;
}

export async function entrar(username: string, password: string, lembrar = false): Promise<Usuario> {
  const r = await fetch(`${location.origin}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Ipe-Web": "1" },
    body: JSON.stringify({ username, password, lembrar }),
    cache: "no-store",
  });
  if (r.status === 401) throw new Error("401");
  if (r.status === 429) throw new Error("429");
  if (!r.ok) throw new Error(String(r.status));
  const d = await r.json();
  token = d.token;
  guardarToken(token, Number(d.lembrar_ate || 0));
  return d as Usuario;
}

// 0.100.108: link de exame — abre só um exame, sem senha (o servidor prende a sessão a ele)
const CHAVE_LINK = "ipe.web.link";
export interface EntradaLink { token: string; study: string; perms: string[]; link: string[]; full_name: string; expira: number }
export async function entrarComLink(t: string): Promise<EntradaLink> {
  const r = await fetch(`${location.origin}/api/link/entrar`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Ipe-Web": "1" },
    body: JSON.stringify({ token: t }), cache: "no-store",
  });
  if (!r.ok) {
    let msg = String(r.status);
    try { msg = ((await r.json()) as { error?: string }).error || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  const d = (await r.json()) as EntradaLink;
  token = d.token;
  guardarToken(token);
  try { sessionStorage.setItem(CHAVE_LINK, d.study); } catch { /* sem armazenamento */ }
  return d;
}
/** O exame do link (vazio = sessão comum). */
export function linkExame(): string {
  try { return sessionStorage.getItem(CHAVE_LINK) || ""; } catch { return ""; }
}

export async function sair(): Promise<void> {
  try { sessionStorage.removeItem(CHAVE_LINK); } catch { /* sem armazenamento */ }
  try {
    await pedir(`${location.origin}/api/logout`);
  } catch {
    /* já saiu */
  }
  token = "";
  guardarToken("");
}

/** 0.100.18: um erro do navegador vai para o registro do servidor (para achar o defeito de um aparelho que não está
 *  à mão — o celular que não passava do login). Sem dados do paciente: só a mensagem e o navegador. */
export function relatarErro(onde: string, erro: unknown): void {
  try {
    const e = erro as { message?: string; stack?: string };
    const corpo = JSON.stringify({ onde, erro: String(e?.message ?? erro).slice(0, 500), pilha: String(e?.stack ?? "").slice(0, 1500),
      navegador: navigator.userAgent.slice(0, 300), tela: `${window.innerWidth}x${window.innerHeight}`, seguro: window.isSecureContext });
    void fetch(`${location.origin}/api/web/erro`, { method: "POST", headers: { ...cabecalhos(), "Content-Type": "application/json" },
      body: corpo, cache: "no-store", keepalive: true }).catch(() => undefined);
  } catch { /* nada a fazer */ }
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

/** 0.100.60: o tempo de abertura do exame vai para o registro do servidor ("Abertura web (…)"), para comparar
 *  versões. Sem dados do paciente: modalidades, contagens e tempos. */
export function relatarAbertura(dados: Record<string, unknown>): void {
  try {
    const ua = navigator.userAgent;
    const m = /(Firefox|Edg|OPR|Chrome|Version)\/(\d+)/.exec(ua);
    const nav = m ? `${m[1] === "Version" ? "Safari" : m[1] === "Edg" ? "Edge" : m[1]} ${m[2]}` : "?";
    void fetch(`${location.origin}/api/web/abertura`, { method: "POST", headers: { ...cabecalhos(), "Content-Type": "application/json" },
      body: JSON.stringify({ ...dados, navegador: nav, tela: `${window.innerWidth}x${window.innerHeight}` }),
      cache: "no-store", keepalive: true }).catch(() => undefined);
  } catch { /* nada a fazer */ }
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

export async function metadados(study: string, series: string, fresco = false): Promise<DicomJson[]> {
  // 0.100.105: `fresco` — a série cresceu (exame chegando do PACS): o servidor relê a lista de imagens
  const r = await pedir(`${DICOMWEB}/studies/${study}/series/${series}/metadata${fresco ? "?fresco=1" : ""}`);
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
  guardarToken(t);
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
