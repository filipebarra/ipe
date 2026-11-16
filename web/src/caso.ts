// 0.100.56: "modo caso" — o Ipê Web aberto de um PACOTE DE CASOS (uma lista exportada pelo Ipê de mesa), sem
// servidor: os exames vêm de arquivos (DICOMweb estático em casos/dw/…), a configuração e as marcações de
// casos/…, e tudo o que precisa do servidor (laudo, IA, envio, PACS, filme) fica escondido.
//
// Em vez de mexer em cada chamada do site, as chamadas ao servidor (fetch e XHR, inclusive as do carregador de
// imagens do Cornerstone) são desviadas aqui para os arquivos do pacote. Cada caso tem duas partes: a apresentação
// (história e as séries/documentos da apresentação) e o resultado (diagnóstico, laudo, biópsia, ensino, as séries e
// documentos do resultado e as marcações), que só aparecem quando se pede "Mostrar o resultado".
import { tr } from "./i18n";

export interface Caso {
  n: number;
  titulo: string;
  study: string;
  idade: string;
  sexo: string;
  modalidades: string[];
  descricao: string;
  tags: string[];
  series: Record<string, "apresentacao" | "resultado">;
  historia: string;
  resultado: { diagnostico: string; laudo: string; patologia: string; ensino: string };
}
export interface Pacote { formato: number; versao_ipe: string; titulo: string; casos: Caso[] }

export let PACOTE: Pacote | null = null;
const BASE = new URL("casos/", document.baseURI).href;
const revelados = new Set<string>();      // exames (study) com o resultado à mostra
const ouvintes = new Set<(study: string) => void>();

export function emModoCaso(): boolean { return PACOTE !== null; }
export function casoDoExame(study: string): Caso | null { return PACOTE?.casos.find((c) => c.study === study) ?? null; }
export function revelado(study: string): boolean { return revelados.has(study); }
export function quandoRevelar(fn: (study: string) => void): () => void { ouvintes.add(fn); return () => ouvintes.delete(fn); }
export function revelar(study: string, sim = true): void {
  if (sim) revelados.add(study); else revelados.delete(study);
  for (const fn of [...ouvintes]) fn(study);
}

/** Procura o pacote (casos/casos.json ao lado do index.html); achando, liga o modo caso. */
export async function detectarPacote(): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}casos.json`, { cache: "no-store" });
    if (!r.ok) return false;
    const p = (await r.json()) as Pacote;
    if (!p || !Array.isArray(p.casos) || !p.formato) return false;
    PACOTE = p;
    instalarDesvios();
    return true;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------------ desvios das chamadas
type Desvio = { arquivo: string; tipo?: string; filtro?: (dados: unknown) => unknown } | { dados: unknown } | { nada: true };

const QUADRO = 'multipart/related; type="application/octet-stream"';
const json = (d: unknown) => new Response(JSON.stringify(d), { status: 200, headers: { "Content-Type": "application/json" } });

function parametro(u: URL, k: string): string { return u.searchParams.get(k) || ""; }

function seriesVisiveis(study: string, lista: unknown): unknown {
  const c = casoDoExame(study);
  if (!c || revelado(study) || !Array.isArray(lista)) return lista;
  return (lista as Record<string, { Value?: unknown[] }>[]).filter((s) => {
    const uid = String(s["0020000E"]?.Value?.[0] ?? "");
    return (c.series[uid] ?? "apresentacao") !== "resultado";
  });
}

function filtrarEstudos(u: URL, lista: unknown): unknown {
  if (!Array.isArray(lista)) return lista;
  const st = parametro(u, "StudyInstanceUID"), pid = parametro(u, "PatientID");
  return (lista as Record<string, { Value?: unknown[] }>[]).filter((e) =>
    (!st || String(e["0020000D"]?.Value?.[0] ?? "") === st) && (!pid || String(e["00100020"]?.Value?.[0] ?? "") === pid));
}

/** Para onde vai uma chamada ao "servidor" (ou null: não é do servidor, segue normal). */
function desvio(url: string, metodo: string): Desvio | null {
  let u: URL;
  try { u = new URL(url, location.href); } catch { return null; }
  if (u.origin !== location.origin) return null;
  const p = u.pathname;
  const i = p.indexOf("/dicomweb/");
  if (i >= 0 || p.endsWith("/dicomweb")) {
    const resto = i >= 0 ? p.slice(i + "/dicomweb/".length) : "";
    const seg = resto.split("/").filter(Boolean);
    if (seg.length === 1 && seg[0] === "studies") return { arquivo: "dw/studies.json", filtro: (d) => filtrarEstudos(u, d) };
    if (seg.length === 3 && seg[2] === "series") return { arquivo: `dw/studies/${seg[1]}/series.json`, filtro: (d) => seriesVisiveis(seg[1], d) };
    if (seg.length === 5 && (seg[4] === "metadata" || seg[4] === "thumbnail")) return { arquivo: `dw/${resto}`, tipo: seg[4] === "thumbnail" ? "image/png" : "application/dicom+json" };
    if (seg.length === 8 && seg[6] === "frames") return { arquivo: `dw/${resto}` };
    return { dados: [] };
  }
  const j = p.indexOf("/api/");
  if (j < 0) return null;
  const api = p.slice(j + "/api/".length);
  const study = parametro(u, "study");
  if (api === "web/config") return { arquivo: "config.json" };
  if (api === "web/medidas" && metodo === "GET") {
    return { arquivo: `api/medidas/${parametro(u, "series")}.json`,
      filtro: (d) => (revelado(study) || !Array.isArray(d) ? d : (d as { resposta?: boolean }[]).filter((m) => !m.resposta)) };
  }
  if (api === "web/medidas" && metodo === "POST") return { dados: { id: Math.floor(Math.random() * 1e9) + 1e9 } }; // fica só nesta aba
  if (api === "web/mamografia") {
    return casoDoExame(study)?.modalidades.includes("MG") ? { arquivo: `api/mamografia/${study}.json` }
      : { dados: { protocolo: null, motivo: "o exame não é de mamografia" } };
  }
  if (api === "web/documentos") {
    return { arquivo: `api/documentos/${study}.json`,
      filtro: (d) => ({ documentos: (Array.isArray(d) ? d as { parte?: string }[] : []).filter((x) => revelado(study) || x.parte !== "resultado") }) };
  }
  if (api === "web/documento") return { arquivo: `docs/${parametro(u, "sop")}.pdf`, tipo: "application/pdf" };
  if (api === "web/series_ia") return { dados: {} };
  if (api === "logout" || api === "web/abriu" || api === "web/erro" || api === "web/medidas/apagar") return { dados: { ok: true } };
  return { nada: true };
}

function instalarDesvios(): void {
  const original = window.fetch.bind(window);
  window.fetch = async (entrada: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof entrada === "string" ? entrada : entrada instanceof URL ? entrada.href : entrada.url;
    const metodo = (init?.method || (entrada instanceof Request ? entrada.method : "GET") || "GET").toUpperCase();
    const d = desvio(url, metodo);
    if (!d) return original(entrada, init);
    if ("nada" in d) return new Response("", { status: 404 });
    if ("dados" in d) return json(d.dados);
    const r = await original(BASE + d.arquivo);
    if (!r.ok) return new Response("", { status: 404 });
    if (d.filtro) return json(d.filtro(await r.json()));
    if (d.tipo) return new Response(await r.blob(), { status: 200, headers: { "Content-Type": d.tipo } });
    // o quadro (o carregador progressivo pede por fetch): o arquivo já é o corpo multipart — só falta dizer isso
    if (d.arquivo.includes("/frames/")) return new Response(r.body, { status: 200, headers: { "Content-Type": QUADRO } });
    return r;
  };
  // o carregador de imagens (WADO-RS) usa XMLHttpRequest: o quadro vem do arquivo, que já é o corpo multipart
  const abrir = XMLHttpRequest.prototype.open;
  const cabecalho = XMLHttpRequest.prototype.getResponseHeader;
  XMLHttpRequest.prototype.open = function (this: XMLHttpRequest & { __ipeQuadro?: boolean }, metodo: string, url: string | URL, ...resto: unknown[]) {
    const d = desvio(String(url), String(metodo).toUpperCase());
    let alvo = String(url);
    if (d && "arquivo" in d) {
      alvo = BASE + d.arquivo;
      this.__ipeQuadro = d.arquivo.includes("/frames/");
    }
    return (abrir as (...a: unknown[]) => void).call(this, metodo, alvo, ...(resto.length ? resto : [true]));
  } as typeof XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.getResponseHeader = function (this: XMLHttpRequest & { __ipeQuadro?: boolean }, nome: string) {
    if (this.__ipeQuadro && nome.toLowerCase() === "content-type") return QUADRO;
    return cabecalho.call(this, nome);
  };
}

// ------------------------------------------------------------------ telas
const SEXO: Record<string, string> = { F: "feminino", M: "masculino" };

function idadeLegivel(a: string): string {
  const m = /^(\d{3})([DWMY])$/.exec(a || "");
  if (!m) return a || "";
  const n = Number(m[1]);
  return `${n} ${tr({ D: "dias", W: "semanas", M: "meses", Y: "anos" }[m[2] as "D"] || "")}`;
}

export function resumoDoCaso(c: Caso): string {
  return [idadeLegivel(c.idade), tr(SEXO[c.sexo] || ""), c.modalidades.join(" / "), c.descricao].filter(Boolean).join(" · ");
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", texto = ""): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (texto) e.textContent = texto;
  return e;
}

/** A lista dos casos do pacote (a tela inicial). */
export function telaCasos(abrir: (c: Caso) => void): HTMLElement {
  const p = PACOTE!;
  const raiz = el("main", "telacasos");
  const topo = el("header", "topo-casos");
  topo.append(el("strong", "", tr("Ipê Web")), el("h1", "", p.titulo), el("span", "dica", `${p.casos.length} ${tr(p.casos.length === 1 ? "caso" : "casos")}`));
  const busca = el("input") as HTMLInputElement;
  busca.placeholder = tr("Procurar nos casos");
  busca.setAttribute("aria-label", tr("Procurar nos casos"));
  const lista = el("div", "cartoes-casos");
  const desenhar = () => {
    const q = busca.value.trim().toLowerCase();
    lista.replaceChildren();
    for (const c of p.casos) {
      const texto = `${c.titulo} ${c.historia} ${c.tags.join(" ")} ${c.modalidades.join(" ")} ${c.descricao}`.toLowerCase();
      if (q && !texto.includes(q)) continue;
      const b = el("button", "cartao-caso");
      b.type = "button";
      b.append(el("span", "num", String(c.n)), el("strong", "", c.titulo), el("span", "resumo", resumoDoCaso(c)));
      if (c.historia) b.append(el("span", "historia", c.historia.length > 220 ? `${c.historia.slice(0, 220)}…` : c.historia));
      if (c.tags.length) {
        const t = el("span", "tags");
        for (const x of c.tags) t.append(el("span", "tag", x));
        b.append(t);
      }
      b.onclick = () => abrir(c);
      lista.append(b);
    }
    if (!lista.childElementCount) lista.append(el("div", "dica", tr("Nenhum caso com esse texto.")));
  };
  busca.oninput = desenhar;
  desenhar();
  raiz.append(topo, busca, lista, el("div", "tarja-rodape", tr("Exames anonimizados · material de ensino · não destinado a uso diagnóstico")));
  return raiz;
}

function bloco(titulo: string, texto: string): HTMLElement | null {
  if (!texto.trim()) return null;
  const d = el("section", "bloco-caso");
  d.append(el("h3", "", tr(titulo)), el("div", "texto-caso", texto));
  return d;
}

/** O painel do caso (aba "Caso" do exame): a apresentação, o botão do resultado e o resultado. */
export class PainelCaso {
  readonly raiz = el("div", "painel-caso");
  private desligar: () => void;

  constructor(private caso: Caso, private irPara: (n: number) => void) {
    this.desligar = quandoRevelar((s) => { if (s === caso.study) this.desenhar(); });
    this.desenhar();
  }

  encerrar(): void { this.desligar(); }

  private desenhar(): void {
    const c = this.caso, rev = revelado(c.study);
    const cab = el("div", "cab-caso");
    cab.append(el("span", "num", `${tr("Caso")} ${c.n}`), el("strong", "", c.titulo), el("span", "resumo", resumoDoCaso(c)));
    const partes: HTMLElement[] = [cab];
    const h = bloco("História clínica", c.historia);
    if (h) partes.push(h);
    const b = el("button", rev ? "revelar revelado" : "revelar", rev ? tr("Esconder o resultado") : tr("Mostrar o resultado"));
    b.type = "button";
    b.onclick = () => revelar(c.study, !rev);
    partes.push(b);
    if (rev) {
      const r = c.resultado;
      const blocos = [bloco("Diagnóstico", r.diagnostico), bloco("Laudo / resultado", r.laudo),
        bloco("Biópsia / anatomopatológico", r.patologia), bloco("Pontos de ensino", r.ensino)].filter(Boolean) as HTMLElement[];
      const res = el("div", "resultado-caso");
      res.append(...(blocos.length ? blocos : [el("div", "dica", tr("Sem texto de resultado neste caso."))]),
        el("div", "dica", tr("As marcações e as séries do resultado aparecem nas imagens.")));
      partes.push(res);
    }
    const nav = el("div", "nav-caso");
    const todos = PACOTE!.casos, k = todos.indexOf(c);
    const ant = el("button", "", `◀ ${tr("Anterior")}`), prox = el("button", "", `${tr("Próximo")} ▶`);
    ant.type = prox.type = "button";
    ant.disabled = k <= 0;
    prox.disabled = k >= todos.length - 1;
    ant.onclick = () => this.irPara(todos[k - 1].n);
    prox.onclick = () => this.irPara(todos[k + 1].n);
    nav.append(ant, el("span", "dica", `${k + 1} / ${todos.length}`), prox);
    partes.push(nav);
    this.raiz.replaceChildren(...partes);
  }
}
