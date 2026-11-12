// Ipê Web (0.99.91, fase W0): login, lista de exames, tira de séries e quadros 2D.
// Rotas pelo endereço depois do # (#/lista, #/exame/<StudyInstanceUID>): o servidor só serve o index.

import "./estilo.css";
import * as API from "./api";
import { setLang, tr } from "./i18n";
import * as csTools from "@cornerstonejs/tools";
import {
  aoMudarMedidas, apagarMedida, apagarMedidasDaImagem, copiarValor, editarTexto, listarMedidas, medidaNoPonto,
  medidaPorUid, type ResumoMedida,
} from "./medidas";
import { Overlay } from "./overlay";
import { abrirMenu, abrirPainel, fecharMenus, icone, type ItemMenu } from "./menu";
import { META, partesDoImageId } from "./meta";
import { COR_PADRAO, SUV_PADRAO, registrarCores } from "./pet";
import { Cronometro } from "./carga";
import { Disponiveis } from "./disponiveis";
import { ModoMamografia, pedirToken } from "./mamografia";
import { ModoDinamica, dinamicaDoExame, guardarTabelas } from "./dinamica";
import { PainelLaudo } from "./laudo";
import { ListaEnvios, painelEnvio } from "./envio";
import { AbaIA, TarefasIA } from "./ia";
import * as JAN from "./janelas";
import { PainelFilme } from "./filme";
import {
  Grade, TIPO_ARRASTO, aplicarBotoes, botoes, carregarSerie, iniciar, type Botoes, type Ferramenta, type Projecao,
  ARRANJO_PET_PADRAO, type ConteudoPet, type VistaPet,
  type Sinc,
} from "./visor";

const app = document.getElementById("app")!;
let config: API.Config | null = null;
let grade: Grade | null = null;
let disp: Disponiveis | null = null;

let cronometro: Cronometro | null = null;
let mg: ModoMamografia | null = null;
let din: ModoDinamica | null = null;
let painelLaudo: PainelLaudo | null = null;
let tarefasIA: TarefasIA | null = null;   // 0.100.10

function pararDisponiveis(): void {
  disp?.parar();
  disp = null;
  cronometro?.parar();
  cronometro = null;
}
const NAO_MOSTRA = new Set(["SR", "KO", "PR", "DOC", "RTSTRUCT", "RTPLAN", "SEG", "REG", "OT_PDF"]);

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, unknown> = {},
  ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = String(v);
    else if (k.startsWith("on") && typeof v === "function") (e as unknown as Record<string, unknown>)[k] = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, String(v));
  }
  e.append(...filhos);
  return e;
}

function tarja(): HTMLElement {
  return el("div", { class: "tarja" }, tr("Não destinado a uso diagnóstico"));
}

// ------------------------------------------------------------------ login
function telaLogin(msg = ""): void {
  pararDisponiveis();
  mg?.encerrar();
  mg = null;
  din?.encerrar();
  din = null;
  void painelLaudo?.fechar();
  painelLaudo = null;
  tarefasIA?.parar();
  tarefasIA = null;
  grade?.encerrar();
  grade = null;
  const u = el("input", { id: "usuario", autocomplete: "username", required: true, autocapitalize: "none",
    autocorrect: "off", spellcheck: "false" }) as HTMLInputElement;     // o teclado do celular punha maiúscula e corrigia
  const s = el("input", { id: "senha", type: "password", autocomplete: "current-password", required: true }) as HTMLInputElement;
  const erro = el("div", { class: "erro", role: "alert" }, msg);
  const form = el("form", { class: "login" },
    el("h1", {}, tr("Ipê Web")),
    el("label", { for: "usuario" }, tr("Usuário")), u,
    el("label", { for: "senha" }, tr("Senha")), s,
    el("button", { type: "submit" }, tr("Entrar")), erro, tarja());
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    erro.textContent = "";
    try {
      await API.entrar(u.value.trim(), s.value);
      config = await API.configuracao();
      setLang(config.lang);
    } catch (e) {
      const m = String((e as Error).message);
      erro.textContent = m === "401" ? tr("Usuário ou senha incorretos.")
        : m === "429" ? tr("Muitas tentativas: espere alguns minutos.") : tr("Não foi possível falar com o servidor.");
      if (m !== "401" && m !== "429") API.relatarErro("login", e);
      return;
    }
    await prepararVisor();
    rota();
  };
  app.replaceChildren(form);
  u.focus();
}

API.quandoEncerrar(() => telaLogin(tr("Sessão encerrada: entre de novo.")));

/** 0.100.18: o motor de imagens (Cornerstone3D) não pode impedir a entrada: se ele não iniciar neste navegador, a
 *  lista abre do mesmo jeito e o motivo aparece ao abrir um exame (e vai para o registro do servidor). */
let erroDoVisor = "";
async function prepararVisor(): Promise<void> {
  try {
    await iniciar();
    if (config) registrarCores(config);
    erroDoVisor = "";
  } catch (e) {
    erroDoVisor = String((e as Error)?.message || e);
    API.relatarErro("iniciar", e);
  }
}

/** A página foi recarregada (ou é uma janela de visualização aberta pela lista) com a sessão ainda válida. */
let retomando = false;
async function retomar(): Promise<void> {
  if (retomando) return;
  retomando = true;
  app.replaceChildren(el("div", { class: "estado" }, tr("Carregando…")));
  try {
    config = await API.configuracao();
    setLang(config.lang);
  } catch (e) {
    retomando = false;
    if (!(e instanceof API.SessaoEncerrada)) { API.usarToken(""); telaLogin(tr("Não foi possível falar com o servidor.")); }
    return;
  }
  await prepararVisor();
  retomando = false;
  rota();
}
window.addEventListener("error", (e) => API.relatarErro("janela", e.error ?? e.message));
window.addEventListener("unhandledrejection", (e) => { if (!(e.reason instanceof API.SessaoEncerrada)) API.relatarErro("promessa", e.reason); });

/** A segunda tela da mamografia recebeu o token: lê a configuração e abre o exame. */
async function entrouNaSegunda(): Promise<void> {
  try {
    config = await API.configuracao();
    setLang(config.lang);
  } catch {
    telaLogin();
    return;
  }
  await prepararVisor();
  rota();
}

function cabecalho(...extra: Node[]): HTMLElement {
  app.classList.remove("leitura");
  const quem = config?.usuario.full_name || config?.usuario.username || "";
  // 0.100.5: com um exame aberto, "Sair" fecha o exame e volta à lista; na lista, sai do Ipê Web
  const noExame = /^#\/(exame|mg)\//.test(location.hash);
  const b = el("button", { class: "sair", title: noExame ? tr("Fechar o exame e voltar à lista") : quem,
    onclick: async () => {
      if (noExame) { voltarALista(); return; }
      JAN.sairDasJanelas();
      await API.sair();
      try { sessionStorage.removeItem(CHAVE_BUSCA); } catch { /* sem armazenamento */ }
      config = null;
      telaLogin();
    } }, noExame ? tr("Fechar") : tr("Sair"));     // 0.100.15: no exame, "Fechar" (Close / Cerrar)
  return el("header", {}, el("strong", {}, tr("Ipê Web")), ...extra, el("span", { class: "quem" }, quem), b);
}

// ------------------------------------------------------------------ 0.100.18: janelas de visualização (uma por monitor)
/** Fechar o exame: na janela comum, volta à lista; numa janela de visualização, fecha o exame em todas e elas ficam à
 *  espera do próximo (a lista está na outra janela). */
function voltarALista(): void {
  const k = JAN.estaJanela();
  if (!k) { location.hash = "#/lista"; return; }
  JAN.fecharNasJanelas();
  location.hash = `#/espera/j${k}`;
}

function telaEspera(): void {
  pararDisponiveis();
  mg?.encerrar(); mg = null;
  din?.encerrar(); din = null;
  void painelLaudo?.fechar(); painelLaudo = null;
  tarefasIA?.parar(); tarefasIA = null;
  grade?.encerrar(); grade = null;
  document.title = `${tr("Ipê Web")} — ${tr("visualização")} ${JAN.estaJanela()}`;
  app.replaceChildren(el("div", { class: "espera" }, el("strong", {}, tr("Ipê Web")),
    el("div", {}, `${tr("Janela de visualização")} ${JAN.estaJanela()}`),
    el("div", { class: "dica" }, tr("Escolha um exame na lista (na outra janela): ele abre aqui."))), tarja());
}

JAN.canalJanelas()?.addEventListener("message", (e) => {
  const m = e.data as JAN.Recado;
  const k = JAN.estaJanela();
  if (!k) return;                               // a janela da lista não obedece a recados
  if (m.tipo === "abrir" && m.study) {
    const alvo = `#/exame/${m.study}/j${k}`;
    if (location.hash !== alvo) location.hash = alvo;
  } else if (m.tipo === "fechar") {
    if (!/^#\/espera\//.test(location.hash)) location.hash = `#/espera/j${k}`;
  } else if (m.tipo === "sair") {
    API.usarToken("");
    window.close();
  }
});
JAN.lembrarPosicao();

// ------------------------------------------------------------------ 0.100.18: celular e tablet
/** Tela de celular (estreita, ou baixa e de toque): os painéis viram gavetas, a barra rola, a lista vira cartões. */
const consultaCel = window.matchMedia("(max-width: 760px), (max-height: 520px) and (pointer: coarse)");
const consultaToque = window.matchMedia("(pointer: coarse)");
function celular(): boolean { return consultaCel.matches; }
function toque(): boolean { return consultaToque.matches; }
function marcarAparelho(): void {
  document.documentElement.classList.toggle("cel", celular());
  document.documentElement.classList.toggle("toque", toque());
}
marcarAparelho();
consultaCel.addEventListener?.("change", marcarAparelho);
consultaToque.addEventListener?.("change", marcarAparelho);

// ------------------------------------------------------------------ lista
/** 0.100.15: a busca da lista volta quando o exame é fechado (nesta aba do navegador) */
const CHAVE_BUSCA = "ipe.web.busca";
type Busca = { texto: string; de: string; ate: string; mod: string; ultimo?: string; periodo?: string; situacao?: string };
type Situacao = { laudo: string; achados: number; revisar: number };
type Previa = { study: string; paciente: string; id: string; idade: string; sexo: string; data: string; descricao: string; acesso: string;
  series: { uid: string; numero: number; modalidade: string; descricao: string; imagens: number; ia: boolean }[];
  ia: { ferramentas: string[]; contagem: Record<string, number> };
  laudo: { estado: string; quando: string; quem: string; trecho: string } | null;
  anteriores: { uid: string; data: string; descricao: string; modalidades: string }[] };
function diaIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function lerBusca(): Busca | null {
  try { const v = sessionStorage.getItem(CHAVE_BUSCA); return v ? (JSON.parse(v) as Busca) : null; } catch { return null; }
}
function gravarBusca(b: Busca): void {
  try { sessionStorage.setItem(CHAVE_BUSCA, JSON.stringify(b)); } catch { /* sem armazenamento */ }
}

const MODALIDADES = ["", "CT", "MR", "MG", "US", "PT", "NM", "CR", "DX", "XA", "RF"];

function dataBr(d: string): string {
  return d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : d;
}

async function telaLista(): Promise<void> {
  pararDisponiveis();
  mg?.encerrar();
  mg = null;
  din?.encerrar();
  din = null;
  void painelLaudo?.fechar();
  painelLaudo = null;
  grade?.encerrar();
  grade = null;
  const busca = el("input", { placeholder: tr("Nome, ID ou acesso"), id: "busca" }) as HTMLInputElement;
  const de = el("input", { type: "date", title: tr("De") }) as HTMLInputElement;
  const ate = el("input", { type: "date", title: tr("Até") }) as HTMLInputElement;
  const mod = el("select", { title: tr("Modalidade") },
    ...MODALIDADES.map((m) => el("option", { value: m }, m || tr("Todas")))) as HTMLSelectElement;
  const corpo = el("tbody");
  const estado = el("div", { class: "estado" });
  // 0.100.19: monitores e janelas (onde os exames abrem, a ordem, o que cada janela apresenta)
  const bMon = el("button", { type: "button", class: "janelas" }) as HTMLButtonElement;
  const rotuloMon = () => {
    const n = JAN.quantasJanelas();
    bMon.textContent = n ? `${tr("Monitores")}: ${n} ${tr(n === 1 ? "janela" : "janelas")}` : `${tr("Monitores")}…`;
  };
  rotuloMon();
  bMon.onclick = () => abrirPainel(JAN.painelMonitores(rotuloMon), bMon, tr("Monitores e janelas"));
  const form = el("form", { class: "filtros" }, busca, el("button", { type: "submit" }, tr("Buscar")), bMon);
  const antes = lerBusca();
  if (antes) {
    busca.value = antes.texto || "";
    de.value = antes.de || "";
    ate.value = antes.ate || "";
    mod.value = antes.mod || "";
  }
  // 0.100.20: filtros rápidos — período, modalidade e situação, um clique cada
  let periodo = antes?.periodo ?? (antes?.de || antes?.ate ? "outro" : "tudo");
  let situacao = antes?.situacao ?? "";
  let situacoes: Record<string, Situacao> = {};
  const pilulas = (rotulo: string, opcoes: [string, string][], atual: () => string, escolher: (v: string) => void, ...extra: Node[]) => {
    const grupo = el("div", { class: "pilulas", role: "group", "aria-label": tr(rotulo) }, el("span", { class: "rot" }, tr(rotulo)));
    const bs = opcoes.map(([v, nome]) => {
      const b = el("button", { type: "button", class: "pil", "data-valor": v }, tr(nome)) as HTMLButtonElement;
      b.onclick = () => { escolher(v); marcar(); };
      return b;
    });
    const marcar = () => bs.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.valor === atual())));
    marcar();
    grupo.append(...bs, ...extra);
    return { grupo, marcar };
  };
  const datas = el("span", { class: "outro-periodo" }, de, ate);
  const aplicarPeriodo = () => {
    const hoje = new Date();
    const menos = (n: number) => { const d = new Date(hoje); d.setDate(d.getDate() - n); return diaIso(d); };
    if (periodo === "hoje") { de.value = ate.value = diaIso(hoje); }
    else if (periodo === "ontem") { de.value = ate.value = menos(1); }
    else if (periodo === "7") { de.value = menos(6); ate.value = diaIso(hoje); }
    else if (periodo === "30") { de.value = menos(29); ate.value = diaIso(hoje); }
    else if (periodo === "tudo") { de.value = ate.value = ""; }
    datas.hidden = periodo !== "outro";
  };
  aplicarPeriodo();
  de.onchange = ate.onchange = () => void procurar();
  const pPeriodo = pilulas("Período", [["hoje", "Hoje"], ["ontem", "Ontem"], ["7", "7 dias"], ["30", "30 dias"], ["tudo", "Tudo"], ["outro", "Outro período…"]],
    () => periodo, (v) => { periodo = v; aplicarPeriodo(); if (v !== "outro" || de.value || ate.value) void procurar(); }, datas);
  const pMod = pilulas("Modalidade", [["", "Todas"], ...["CT", "MR", "MG", "US", "PT", "CR", "DX", "NM", "XA"].map((m) => [m, m] as [string, string])],
    () => mod.value, (v) => { mod.value = v; void procurar(); });
  const pSit = pilulas("Situação", [["", "Todos"], ["sem", "Sem laudo"], ["draft", "Rascunho"], ["final", "Assinado"], ["ia", "Com IA para revisar"]],
    () => situacao, (v) => { situacao = v; guardar(); desenhar(); });
  const rapidos = el("div", { class: "filtros-rapidos" }, pPeriodo.grupo, pMod.grupo, pSit.grupo);
  const contagem = el("div", { class: "contagem-lista" });
  const guardar = (ultimo = lerBusca()?.ultimo) =>
    gravarBusca({ texto: busca.value, de: de.value, ate: ate.value, mod: mod.value, ultimo, periodo, situacao });
  // 0.100.20: a prévia do exame selecionado, à direita (um clique seleciona; dois abrem)
  const previa = el("aside", { class: "previa", "aria-label": tr("Exame selecionado") });
  previa.hidden = true;
  let selecionado = "";
  const mostrarPrevia = async (uid: string) => {
    selecionado = uid;
    corpo.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
    corpo.querySelector(`tr[data-uid="${uid}"]`)?.classList.add("sel");
    if (celular()) return;
    previa.hidden = false;
    previa.replaceChildren(el("div", { class: "dica" }, tr("Carregando…")));
    let p: Previa;
    try {
      const r = await API.pedir(`${location.origin}/api/web/lista/previa?study=${encodeURIComponent(uid)}`);
      if (!r.ok) throw new Error(String(r.status));
      p = (await r.json()) as Previa;
    } catch {
      if (selecionado === uid) previa.replaceChildren(el("div", { class: "dica" }, tr("Não foi possível ler o exame.")));
      return;
    }
    if (selecionado !== uid) return;
    const minis = el("div", { class: "previa-series" });
    for (const se of p.series.slice(0, 12)) {
      const img = el("img", { alt: "" }) as HTMLImageElement;
      void API.miniatura(uid, se.uid).then((u) => { if (u) img.src = u; }).catch(() => undefined);
      minis.append(el("figure", { title: `${se.numero} · ${se.modalidade} · ${se.descricao} · ${se.imagens} ${tr("im")}` }, img,
        ...(se.ia ? [el("em", { class: "selo-ia" }, "IA")] : []),
        el("figcaption", {}, `${se.numero || "–"} · ${se.descricao || se.modalidade}`)));
    }
    const c = p.ia.contagem;
    const totalAch = Object.values(c).reduce((a, b) => a + b, 0);
    const linhaIA = p.ia.ferramentas.length || totalAch
      ? el("div", {}, p.ia.ferramentas.map((f) => tr(f)).join(" · "),
        ...(totalAch ? [el("div", { class: c.sugerido ? "a-revisar" : "" },
          `${totalAch} ${tr("achado(s)")}: ${c.sugerido || 0} ${tr("sugerido(s)")}, ${(c.confirmado || 0) + (c.corrigido || 0)} ${tr("revisado(s)")}`)] : []))
      : el("div", { class: "dica" }, tr("Nenhuma IA neste exame."));
    const estados: Record<string, string> = { draft: "Rascunho", final: "Assinado", amended: "Retificado" };
    const linhaLaudo = p.laudo
      ? el("div", {}, el("b", {}, tr(estados[p.laudo.estado] || p.laudo.estado)), ` · ${p.laudo.quando}${p.laudo.quem ? ` · ${p.laudo.quem}` : ""}`,
        el("div", { class: "trecho" }, p.laudo.trecho))
      : el("div", { class: "dica" }, tr("Sem laudo."));
    const ants = el("div", { class: "previa-anteriores" });
    for (const a of p.anteriores) {
      const b = el("button", { type: "button", class: "link", title: tr("Abrir este exame") }, `${dataBr(a.data)} · ${a.descricao || a.modalidades}`);
      b.onclick = () => abrir(a.uid);
      ants.append(b);
    }
    if (!p.anteriores.length) ants.append(el("div", { class: "dica" }, tr("Nenhum.")));
    const bAbrir = el("button", { type: "button", class: "primario" }, tr("Abrir o exame")) as HTMLButtonElement;
    bAbrir.onclick = () => abrir(uid);
    previa.replaceChildren(
      el("div", { class: "previa-cabeca" }, el("strong", {}, p.paciente),
        el("div", { class: "suave" }, [p.id, p.idade, p.descricao, dataBr(p.data)].filter(Boolean).join(" · "))),
      el("div", { class: "titulo-painel" }, `${tr("Séries")} (${p.series.length})`), minis,
      el("div", { class: "titulo-painel" }, tr("IA neste exame")), linhaIA,
      el("div", { class: "titulo-painel" }, tr("Laudo")), linhaLaudo,
      el("div", { class: "titulo-painel" }, tr("Exames anteriores")), ants,
      el("div", { class: "previa-acoes" }, bAbrir));
  };
  const abrir = (uid: string) => {
    guardar(uid);
    const n = celular() ? 0 : JAN.quantasJanelas();
    if (!n) { location.hash = `#/exame/${uid}`; return; }
    // 0.100.18: a lista continua aqui; o exame abre nas janelas de visualização (uma por monitor)
    estado.textContent = "";
    JAN.abrirNasJanelas(uid, n, () => {
      estado.textContent = tr("O navegador bloqueou a janela de visualização: permita os pop-ups deste endereço (ícone na barra de endereço) e abra o exame de novo.");
    });
    corpo.querySelectorAll("tr.ultimo").forEach((x) => x.classList.remove("ultimo"));
    corpo.querySelector(`tr[data-uid="${uid}"]`)?.classList.add("ultimo");
  };
  // 0.100.2: cada coluna ordena a lista (clicar no título: crescente; de novo: decrescente), e a escolha fica lembrada
  const COLUNAS: { nome: string; valor: (r: API.DicomJson) => string | number; num?: boolean }[] = [
    { nome: "Data", valor: (r) => `${API.texto(r, "00080020")}${API.texto(r, "00080030")}` },
    { nome: "Paciente", valor: (r) => API.texto(r, "00100010").toLocaleLowerCase() },
    { nome: "ID", valor: (r) => API.texto(r, "00100020") },
    { nome: "Descrição", valor: (r) => API.texto(r, "00081030").toLocaleLowerCase() },
    { nome: "Modalidade", valor: (r) => ((r["00080061"]?.Value as string[]) || []).join(", ") },
    { nome: "Imagens", valor: (r) => Number(API.texto(r, "00201208")) || 0, num: true },
  ];
  let ordem = lerPreferencia<{ col: string; desc: boolean }>("ordemLista", { col: "Data", desc: true });
  if (!COLUNAS.some((c) => c.nome === ordem.col)) ordem = { col: "Data", desc: true };
  let linhas: API.DicomJson[] = [];
  const titulos = COLUNAS.map((c) => {
    const b = el("button", { type: "button", class: "ordenar", "data-coluna": c.nome,
      title: tr("Ordenar (clique de novo para inverter)") }, tr(c.nome), el("span", { class: "seta-ordem", "aria-hidden": "true" }));
    b.onclick = () => {
      ordem = { col: c.nome, desc: ordem.col === c.nome ? !ordem.desc : c.nome === "Data" || !!c.num };
      gravarPreferencia("ordemLista", ordem);
      desenhar();
    };
    return el("th", { class: c.num ? "num" : "" }, b);
  });
  const tabela = el("table", { class: "lista" }, el("thead", {}, el("tr", {}, ...titulos)), corpo);
  app.replaceChildren(cabecalho(), el("main", { class: "telalista" },
    el("div", { class: "lista-esq" }, form, rapidos, contagem, estado, tabela), previa), tarja());
  const desenhar = () => {
    const col = COLUNAS.find((c) => c.nome === ordem.col)!;
    titulos.forEach((th, i) => {
      const sel = COLUNAS[i].nome === ordem.col;
      th.setAttribute("aria-sort", sel ? (ordem.desc ? "descending" : "ascending") : "none");
      th.querySelector(".seta-ordem")!.textContent = sel ? (ordem.desc ? " ▼" : " ▲") : "";
    });
    const k = (r: API.DicomJson) => col.valor(r);
    const ordenadas = linhas.map((r, i) => ({ r, i, v: k(r) })).sort((a, b) => {
      const c = typeof a.v === "number" && typeof b.v === "number" ? a.v - b.v
        : String(a.v).localeCompare(String(b.v), undefined, { numeric: true, sensitivity: "base" });
      return (ordem.desc ? -c : c) || a.i - b.i;
    });
    corpo.replaceChildren();
    const passa = (uid: string) => {
      const st = situacoes[uid];
      if (!situacao) return true;
      if (!st) return false;
      return situacao === "sem" ? !st.laudo : situacao === "draft" ? st.laudo === "draft"
        : situacao === "final" ? !!st.laudo && st.laudo !== "draft" : st.revisar > 0;
    };
    let mostrados = 0;
    for (const { r } of ordenadas) {
      const uid = API.texto(r, "0020000D");
      if (!passa(uid)) continue;
      mostrados++;
      const tr_ = el("tr", { tabindex: 0, "data-uid": uid },
        el("td", {}, dataBr(API.texto(r, "00080020"))),
        el("td", {}, API.texto(r, "00100010"),
          ...(situacoes[uid]?.achados ? [el("em", { class: `selo-ia${situacoes[uid].revisar ? " revisar" : ""}`,
            title: situacoes[uid].revisar ? `${situacoes[uid].revisar} ${tr("achado(s) de IA para revisar")}` : tr("Achados de IA revisados") }, "IA")] : []),
          ...(situacoes[uid]?.laudo ? [el("em", { class: `selo-laudo ${situacoes[uid].laudo === "draft" ? "rascunho" : "assinado"}`,
            title: tr(situacoes[uid].laudo === "draft" ? "Laudo em rascunho" : "Laudo assinado") }, tr(situacoes[uid].laudo === "draft" ? "R" : "L"))] : [])),
        el("td", {}, API.texto(r, "00100020")), el("td", {}, API.texto(r, "00081030")),
        el("td", {}, ((r["00080061"]?.Value as string[]) || []).join(", ")),
        el("td", { class: "num" }, API.texto(r, "00201208")));
      tr_.ondblclick = () => abrir(uid);
      tr_.onclick = () => { if (toque() || celular()) abrir(uid); else void mostrarPrevia(uid); };   // no toque não há duplo clique
      tr_.onfocus = () => { if (!celular() && selecionado !== uid && document.activeElement === tr_ && teclou) void mostrarPrevia(uid); };
      if (uid === selecionado) tr_.classList.add("sel");
      for (const [i, c] of [...tr_.children].entries()) c.setAttribute("data-col", tr(COLUNAS[i].nome));
      tr_.onkeydown = (e) => { if ((e as KeyboardEvent).key === "Enter") abrir(uid); };
      if (antes?.ultimo === uid) tr_.classList.add("ultimo");      // o exame que estava aberto
      corpo.append(tr_);
    }
    const ult = corpo.querySelector<HTMLElement>("tr.ultimo");
    if (ult) { ult.scrollIntoView({ block: "center" }); ult.focus({ preventScroll: true }); }
    contagem.textContent = linhas.length ? `${mostrados} ${tr(mostrados === 1 ? "exame" : "exames")}${mostrados < linhas.length ? ` ${tr("de")} ${linhas.length}` : ""}` : "";
    estado.textContent = linhas.length && !mostrados ? tr("Nenhum exame com esta situação.") : (linhas.length ? "" : estado.textContent);
  };
  // as setas andam pela lista e a prévia acompanha
  let teclou = false;
  corpo.addEventListener("keydown", (e) => {
    const k = (e as KeyboardEvent).key;
    if (k !== "ArrowDown" && k !== "ArrowUp") return;
    const atual = document.activeElement as HTMLElement | null;
    const alvo = (k === "ArrowDown" ? atual?.nextElementSibling : atual?.previousElementSibling) as HTMLElement | null;
    if (alvo) { e.preventDefault(); teclou = true; alvo.focus(); teclou = false; }
  });
  const procurar = async () => {
    estado.textContent = tr("Carregando…");
    corpo.replaceChildren();
    const q = new URLSearchParams();
    const t = busca.value.trim();
    if (t) q.set("PatientName", `*${t}*`);
    const d1 = de.value.replace(/-/g, ""), d2 = ate.value.replace(/-/g, "");
    if (d1 || d2) q.set("StudyDate", `${d1}-${d2}`);
    if (mod.value) q.set("ModalitiesInStudy", mod.value);
    q.set("limit", "300");
    guardar();
    pMod.marcar();
    linhas = await API.qido(`/studies?${q}`);
    estado.textContent = linhas.length ? "" : tr("Nenhum exame encontrado.");
    situacoes = {};
    desenhar();
    // a situação (laudo, IA) chega em seguida: os selos e o filtro de situação
    if (linhas.length) {
      try {
        const r = await API.pedir(`${location.origin}/api/web/lista/situacoes`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ studies: linhas.map((x) => API.texto(x, "0020000D")) }) });
        if (r.ok) { situacoes = ((await r.json()) as { estudos: Record<string, Situacao> }).estudos; desenhar(); }
      } catch { /* sem a situação: a lista continua */ }
    }
    if (antes?.ultimo && !selecionado && !celular() && linhas.some((x) => API.texto(x, "0020000D") === antes.ultimo)) void mostrarPrevia(antes.ultimo);
  };
  form.onsubmit = (e) => { e.preventDefault(); void procurar(); };
  if (!antes?.ultimo) busca.focus();
  await procurar();
}

// ------------------------------------------------------------------ exame
// 0.99.97: interface no estilo do Weasis — uma barra de ícones; cada botão do mouse com a sua função (clicar no
// ícone com o botão que deve fazê-la, como no Ipê; a marca embaixo do ícone diz qual); painéis laterais
// recolhíveis (séries à esquerda; Imagem, Medidas, DICOM e PET à direita); menu do botão direito na imagem.

const NOMES_FERRAMENTAS: Record<Ferramenta, string> = {
  janela: "Janela/nível", mover: "Mover", zoom: "Zoom", rolar: "Rolar cortes", linhas: "Linhas de referência",
  regua: "Régua", angulo: "Ângulo", cobb: "Ângulo de Cobb", elipse: "ROI elíptica", retangulo: "ROI retangular",
  poligono: "ROI livre", pixel: "Valor do pixel", seta: "Seta", calibracao: "Calibração",
  suvmax: "SUV máximo perto do cursor", lupa: "Lupa",
};

/** Ícones (24×24, traço). */
const IC: Record<string, string> = {
  ia: "M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M6 6h12v12H6zM10 10h4v4h-4z",
  enviar: "M3 11l18-8-8 18-2-8-8-2zM11 13l10-10",
  overlay: "M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5",
  voltar: "M10 6l-6 6 6 6M4 12h16",
  janela: "M12 3a9 9 0 1 0 0.01 0M12 3v18M12 8h5M12 13h7",
  mover: "M12 2v20M2 12h20M9 5l3-3 3 3M9 19l3 3 3-3M5 9l-3 3 3 3M19 9l3 3-3 3",
  zoom: "M11 4a7 7 0 1 0 0.01 0M20 20l-4.2-4.2M11 8v6M8 11h6",
  rolar: "M4 7l8-4 8 4-8 4zM4 12l8 4 8-4M4 17l8 4 8-4",
  linhas: "M12 2v7M12 15v7M2 12h7M15 12h7M12 9a3 3 0 1 0 0.01 0",
  regua: "M3 17L17 3l4 4L7 21zM7 13l2 2M10 10l2 2M13 7l2 2",
  angulo: "M4 20h16M4 20L16 6M9.5 20a6 6 0 0 0-1.6-4.4",
  cobb: "M3 6l18 3M3 18l18-3M8 7v10",
  elipse: "M12 6c5 0 9 2.7 9 6s-4 6-9 6-9-2.7-9-6 4-6 9-6z",
  retangulo: "M4 6h16v12H4z",
  poligono: "M5 8l6-4 8 4-2 10-9 2z",
  pixel: "M12 3v6M12 15v6M3 12h6M15 12h6",
  seta: "M5 19L19 5M19 5h-8M19 5v8",
  calibracao: "M3 12h18M3 8v8M21 8v8M8 10v4M13 10v4",
  suvmax: "M12 3v4M12 17v4M3 12h4M17 12h4M12 9a3 3 0 1 0 0.01 0",
  lupa: "M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13zM15.5 15.5L21 21M8 10.5h5M10.5 8v5",
  layout: "M3 3h8v8H3zM13 3h8v8h-8zM3 13h8v8H3zM13 13h8v8h-8z",
  mpr: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  espessura: "M4 6h16M4 10h16M4 14h16M4 18h16",
  obliquo: "M4 20L20 4M8 4h12v12",
  girar: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
  dinamica: "M3 20h18M4 17l4-8 3 4 4-9 5 13",
  laudo: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
  petct: "M8 12a4 4 0 1 0 8 0 4 4 0 1 0-8 0M3 12a9 9 0 1 0 18 0 9 9 0 1 0-18 0",
  seg: "M4 4h7v7H4zM13 13h7v7h-7zM11 7.5h5.5V13",
  cine: "M7 4l13 8-13 8z",
  parar: "M6 5h4v14H6zM14 5h4v14h-4z",
  inverter: "M12 3a9 9 0 1 0 0.01 0M12 3v18M7 8l3 4-3 4",
  restaurar: "M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5",
  carga: "M4 20V10M10 20V4M16 20v-7M2 20h20",
  painel: "M3 4h18v16H3zM9 4v16",
  copiar: "M8 8h12v12H8zM4 16V4h12",
  lixo: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
  texto: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
  girar90: "M4 12a8 8 0 0 1 14-5.3M18 3v4h-4",
  espelhar: "M12 3v18M8 7l-5 5 5 5M16 7l5 5-5 5",
  serie: "M4 7l8-4 8 4-8 4zM4 12l8 4 8-4",
  botoes: "M7 3h10a4 4 0 0 1 4 4v10a8 8 0 0 1-16 0V7a4 4 0 0 1 2-3.5M12 3v7",
};

/** Algumas tags DICOM com nome, para a aba DICOM (as outras aparecem só pelo número). */
const NOMES_TAGS: Record<string, string> = {
  "00080008": "ImageType", "00080016": "SOPClassUID", "00080018": "SOPInstanceUID", "00080020": "StudyDate",
  "00080021": "SeriesDate", "00080030": "StudyTime", "00080031": "SeriesTime", "00080050": "AccessionNumber",
  "00080060": "Modality", "00080070": "Manufacturer", "00080080": "InstitutionName", "00081030": "StudyDescription",
  "0008103E": "SeriesDescription", "00081090": "ManufacturerModelName", "00100010": "PatientName",
  "00100020": "PatientID", "00100030": "PatientBirthDate", "00100040": "PatientSex", "00101010": "PatientAge",
  "00101030": "PatientWeight", "00180050": "SliceThickness", "00180060": "KVP", "00180088": "SpacingBetweenSlices",
  "00181150": "ExposureTime", "00181151": "XRayTubeCurrent", "00181164": "ImagerPixelSpacing",
  "00185101": "ViewPosition", "0020000D": "StudyInstanceUID", "0020000E": "SeriesInstanceUID",
  "00200011": "SeriesNumber", "00200013": "InstanceNumber", "00200032": "ImagePositionPatient",
  "00200037": "ImageOrientationPatient", "00200052": "FrameOfReferenceUID", "00201041": "SliceLocation",
  "00280002": "SamplesPerPixel", "00280004": "PhotometricInterpretation", "00280008": "NumberOfFrames",
  "00280010": "Rows", "00280011": "Columns", "00280030": "PixelSpacing", "00280100": "BitsAllocated",
  "00280101": "BitsStored", "00280103": "PixelRepresentation", "00281050": "WindowCenter",
  "00281051": "WindowWidth", "00281052": "RescaleIntercept", "00281053": "RescaleSlope", "00281056": "VOILUTFunction",
  "00020010": "TransferSyntaxUID", "00540016": "RadiopharmaceuticalInformationSequence", "00541001": "Units",
};

const LAYOUTS_PRONTOS: [number, number][] = [[1, 1], [1, 2], [2, 1], [1, 3], [2, 2], [2, 3]];

function janelasProntas(modalidade: string): [string, number, number][] {
  const porMod = config?.["viewer.wl_presets_mod"]?.[modalidade.toUpperCase()];
  const d = (porMod && Object.keys(porMod).length ? porMod : config?.["viewer.wl_presets"]) || {};
  return Object.keys(d).sort().map((k) => d[k]).filter((x) => Array.isArray(x) && x.length >= 3);
}

function lerPreferencia<T>(chave: string, padrao: T): T {
  try {
    const v = localStorage.getItem(`ipe.web.${chave}`);
    return v === null ? padrao : (JSON.parse(v) as T);
  } catch {
    return padrao;
  }
}

function gravarPreferencia(chave: string, valor_: unknown): void {
  try { localStorage.setItem(`ipe.web.${chave}`, JSON.stringify(valor_)); } catch { /* sem armazenamento */ }
}

function botaoIcone(rotulo: string, d: string, extra: Record<string, unknown> = {}): HTMLButtonElement {
  const b = el("button", { type: "button", class: "ic", "aria-label": tr(rotulo), title: tr(rotulo), ...extra }) as HTMLButtonElement;
  b.append(icone(d, 20));
  return b;
}

function seta(): SVGSVGElement {
  const s = icone("M6 9l6 6 6-6", 10);
  s.classList.add("caret");
  return s;
}

async function telaExame(study: string, tela: 1 | 2 = 1, janela = 0, anteriorDe = ""): Promise<void> {
  if (janela) document.title = `${tr("Ipê Web")} — ${tr("visualização")} ${janela}`;
  pararDisponiveis();
  mg?.encerrar();
  mg = null;
  din?.encerrar();
  din = null;
  void painelLaudo?.fechar();
  painelLaudo = null;
  grade?.encerrar();
  fecharMenus();
  if (erroDoVisor) await prepararVisor();
  if (erroDoVisor) {
    app.replaceChildren(cabecalho(), el("div", { class: "estado" },
      `${tr("Este navegador não conseguiu iniciar o visualizador de imagens")}: ${erroDoVisor}`));
    return;
  }
  const todas = await API.qido(`/studies/${study}/series`);
  const segs = todas.filter((s) => API.texto(s, "00080060") === "SEG");
  const series = todas
    .filter((s) => !NAO_MOSTRA.has(API.texto(s, "00080060")))
    .sort((a, b) => Number(API.texto(a, "00200011") || 0) - Number(API.texto(b, "00200011") || 0));
  const estudo = (await API.qido(`/studies?StudyInstanceUID=${study}`))[0];
  if (!estudo) {
    app.replaceChildren(cabecalho(), el("div", { class: "estado" }, tr("Sem permissão para ver este exame.")));
    return;
  }
  void API.avisarAbertura(study);
  const nomePac = API.texto(estudo, "00100010");
  const idPac = API.texto(estudo, "00100020");
  // 0.100.19: a janela de comparação mostra o exame anterior mais recente do paciente (se houver)
  const confJanela = janela ? JAN.configDaJanela(janela) : null;
  if (confJanela?.papel === "compare" && !anteriorDe && idPac) {
    const data = API.texto(estudo, "00080020");
    const outros = (await API.qido(`/studies?PatientID=${encodeURIComponent(idPac)}&limit=50`).catch(() => []))
      .filter((x) => API.texto(x, "00100020") === idPac && API.texto(x, "0020000D") !== study && API.texto(x, "00080020") <= data)
      .sort((a, b) => API.texto(b, "00080020").localeCompare(API.texto(a, "00080020")));
    if (outros.length) return telaExame(API.texto(outros[0], "0020000D"), 1, janela, study);
  }
  const paciente = `${nomePac}  ${idPac}\n${dataBr(API.texto(estudo, "00080020"))}  ${API.texto(estudo, "00081030")}`;

  // ---------------------------------------------------------------- barra de ícones
  const aviso = el("div", { class: "estado", role: "status" });
  const voltar = botaoIcone("Voltar à lista", IC.voltar, { onclick: () => voltarALista() });
  const chip = el("div", { class: "paciente" }, el("strong", {}, nomePac),
    el("span", {}, `${anteriorDe ? `${tr("ANTERIOR")} · ` : ""}${idPac} · ${API.texto(estudo, "00081030")} · ${dataBr(API.texto(estudo, "00080020"))}`));
  if (anteriorDe) chip.classList.add("anterior-de");

  // ferramentas que vão para um botão do mouse (com famílias: o ícone mostra a escolhida; a setinha troca)
  type Grupo = { nome: string; membros: Ferramenta[] };
  const GRUPOS: Grupo[][] = [
    [{ nome: "Janela/nível", membros: ["janela"] }, { nome: "Mover", membros: ["mover"] },
      { nome: "Zoom e lupa", membros: ["zoom", "lupa"] }, { nome: "Rolar cortes", membros: ["rolar"] },
      { nome: "Linhas de referência", membros: ["linhas"] }],
    [{ nome: "Régua", membros: ["regua"] }, { nome: "Ângulos", membros: ["angulo", "cobb"] },
      { nome: "ROIs", membros: ["elipse", "retangulo", "poligono"] }, { nome: "Valor do pixel", membros: ["pixel"] },
      { nome: "Seta", membros: ["seta"] }, { nome: "Calibração", membros: ["calibracao"] },
      { nome: "SUV máximo perto do cursor", membros: ["suvmax"] }],
  ];
  const BOTAO_DO_EVENTO: Record<number, keyof Botoes> = { 0: "esq", 1: "meio", 2: "dir" };
  const NOME_BOTAO: Record<keyof Botoes, string> = { esq: "botão esquerdo", meio: "botão do meio", dir: "botão direito" };
  const escolhida = new Map<Grupo, Ferramenta>();
  const iconesFerr: { g: Grupo; b: HTMLButtonElement; marcas: HTMLElement[] }[] = [];
  const rodapeBotoes = el("span", { class: "botoes-mouse" });
  const atualizarMarcas = () => {
    const bs = botoes();
    for (const { g, b, marcas } of iconesFerr) {
      const f = escolhida.get(g) ?? g.membros[0];
      const quais = (["esq", "meio", "dir"] as (keyof Botoes)[]).filter((k) => g.membros.includes(bs[k]));
      (["esq", "meio", "dir"] as (keyof Botoes)[]).forEach((k, n) => marcas[n].classList.toggle("on", g.membros.includes(bs[k])));
      b.classList.toggle("ativo", quais.length > 0);
      b.dataset.ferramenta = f;
      b.replaceChildren(icone(IC[f], 20), ...(g.membros.length > 1 ? [seta()] : []), b.querySelector(".marcas") || el("span"));
      const nome = tr(NOMES_FERRAMENTAS[f]);
      const titulo = `${nome}${quais.length ? ` — ${quais.map((k) => tr(NOME_BOTAO[k])).join(", ")}` : ""}. ` +
        tr("Clique com o botão do mouse que deve fazer esta função.");
      b.title = titulo;
      b.setAttribute("aria-label", titulo);
    }
    rodapeBotoes.textContent = `${tr("Esquerdo")}: ${tr(NOMES_FERRAMENTAS[bs.esq])} · ${tr("Meio")}: ${tr(NOMES_FERRAMENTAS[bs.meio])} · ` +
      `${tr("Direito")}: ${tr(NOMES_FERRAMENTAS[bs.dir])} (${tr("segurar")}) / ${tr("menu")} (${tr("clicar")}) · ${tr("Roda")}: ${tr("cortes")}`;
  };
  const escolher = (f: Ferramenta, botao: keyof Botoes = "esq") => {
    for (const linha of GRUPOS) for (const g of linha) if (g.membros.includes(f)) escolhida.set(g, f);
    aplicarBotoes({ [botao]: f });
    gravarPreferencia("botoes", botoes());
    atualizarMarcas();
  };
  (window as unknown as Record<string, unknown>).__ipeEscolher = escolher; // testes
  (window as unknown as Record<string, unknown>).__ipeBotoes = botoes; // testes
  const ferramentas = el("div", { class: "grupo" });
  const medicao = el("div", { class: "grupo" });
  GRUPOS.forEach((linha, n) => {
    for (const g of linha) {
      const b = el("button", { type: "button", class: "ic ferr" }) as HTMLButtonElement;
      const marcas = [el("span"), el("span"), el("span")];
      const caixa = el("span", { class: "marcas", "aria-hidden": "true" }, ...marcas);
      b.append(caixa);
      b.oncontextmenu = (e) => e.preventDefault();
      b.onmousedown = (e) => {
        const botao = BOTAO_DO_EVENTO[e.button];
        if (!botao) return;
        e.preventDefault();
        const f = escolhida.get(g) ?? g.membros[0];
        // famílias: clicar na setinha (o canto direito do ícone) abre a escolha
        const r = b.getBoundingClientRect();
        if (g.membros.length > 1 && e.button === 0 && e.clientX > r.right - 12) {
          abrirMenu(g.membros.map((m) => ({ rotulo: tr(NOMES_FERRAMENTAS[m]), icone: IC[m], marcado: m === f,
            acao: () => escolher(m, "esq") })), 0, 0, tr(g.nome), b);
          return;
        }
        escolher(f, botao);
      };
      b.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escolher(escolhida.get(g) ?? g.membros[0], "esq"); } };
      iconesFerr.push({ g, b, marcas });
      (n === 0 ? ferramentas : medicao).append(b);
    }
  });

  const bLayout = botaoIcone("Layout dos quadros", IC.layout);
  bLayout.append(seta());
  const bMpr = botaoIcone("MPR", IC.mpr);
  const bEspessura = botaoIcone("Espessura e projeção", IC.espessura);
  bEspessura.append(seta());
  const bObliquo = botaoIcone("Oblíquo", IC.obliquo);
  const bGirar = botaoIcone("Girar MIP", IC.girar, { "aria-pressed": "false" });
  const bPet = botaoIcone("PET/CT", IC.petct);
  const bDin = botaoIcone("Dinâmica da mama", IC.dinamica, { "aria-pressed": "false" });
  if (!todas.some((s) => API.texto(s, "00080060") === "MR")) bDin.disabled = true;
  const bSeg = botaoIcone("Segmentação (SEG)", IC.seg);
  bSeg.append(seta());
  if (!segs.length) bSeg.disabled = true;
  const bCine = botaoIcone("Cine", IC.cine, { "aria-pressed": "false" });
  const bCineMenu = el("button", { type: "button", class: "ic estreito", "aria-label": tr("Velocidade do cine"),
    title: tr("Velocidade do cine") }, seta());
  const bLaudo = botaoIcone("Laudo", IC.laudo, { "aria-pressed": "false" });
  // 0.100.9: enviar ao PACS (só com a permissão de enviar)
  const podeEnviar = !!config?.usuario.perms?.includes("send");
  const bEnviar = botaoIcone("Enviar a um destino DICOM", IC.enviar);
  if (!podeEnviar) bEnviar.style.display = "none";      // (o estilo do botão de ícone venceria o hidden)
  const listaEnvios = new ListaEnvios();
  // 0.100.10: CAD/IA pelo navegador (só com a permissão de pedir CAD/IA)
  const podeIA = !!config?.usuario.perms?.includes("ai");
  // 0.100.16: a aba IA também para quem revisa achados (escreve laudos), mesmo sem pedir IA
  const abaIAVisivel = podeIA || !!config?.usuario.perms?.includes("report");
  const bIA = botaoIcone("CAD/IA neste exame", IC.ia);
  if (!podeIA) bIA.style.display = "none";
  const listaIA = new TarefasIA(study);
  tarefasIA = listaIA;
  const bTarefasIA = el("button", { type: "button", class: "link", style: "display: none",
    title: tr("As tarefas de IA deste exame e o andamento") }, tr("IA")) as HTMLButtonElement;
  const bEnvios = el("button", { type: "button", class: "link", style: "display: none",
    title: tr("Os envios que você pediu e o andamento") }, tr("Envios")) as HTMLButtonElement;
  const bOverlay = botaoIcone("Overlay (CAD/IA, textos, medidas)", IC.overlay, { "aria-pressed": "true" });
  const bOverlayMenu = el("button", { type: "button", class: "ic estreito", "aria-label": tr("Opções do overlay"),
    title: tr("Opções do overlay") }, seta()) as HTMLButtonElement;
  const bInverter = botaoIcone("Inverter", IC.inverter);
  const bRestaurar = botaoIcone("Restaurar", IC.restaurar);
  const bCarga = el("button", { type: "button", class: "link", "aria-pressed": "false",
    title: tr("Quanto veio pela rede, em quanto tempo, e quanto levou para decodificar") }, tr("Carga")) as HTMLButtonElement;
  const bPainelEsq = botaoIcone("Recolher o painel de séries", "M15 6l-6 6 6 6", { class: "ic recolher" });
  const bPainelDir = botaoIcone("Recolher o painel de ferramentas", "M9 6l6 6-6 6", { class: "ic recolher" });
  const trilhoEsq = el("div", { class: "trilho" }, botaoIcone("Abrir o painel de séries", "M9 6l6 6-6 6"));
  const trilhoDir = el("div", { class: "trilho" }, botaoIcone("Abrir o painel de ferramentas", "M15 6l-6 6 6 6"));
  // 0.100.19: a aparência é do usuário — onde ficam as séries e os botões, e o modo leitura
  // 0.100.20: janelas ligadas — rolar, janela e zoom desta janela seguem para as outras janelas de visualização
  const bLigar = botaoIcone("Ligar as janelas: rolagem, janela e zoom juntos nas janelas de visualização", "M9 15l6-6M10 6l2-2a4 4 0 0 1 6 6l-2 2M14 18l-2 2a4 4 0 0 1-6-6l2-2");
  bLigar.hidden = !janela;
  if (!janela) bLigar.style.display = "none";
  const bLeitura = botaoIcone("Modo leitura (só as imagens) — tecla F", "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5");
  const bAparencia = botaoIcone("Aparência: posição das séries e dos botões", "M4 5h16v14H4zM9 5v14M4 10h5");
  const bGavetaEsq = botaoIcone("Séries", "M4 5h16v4H4zM4 11h16v4H4zM4 17h16v2H4z");
  const bGavetaDir = botaoIcone("Painel de ferramentas", "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M16 4v4M10 10v4M18 16v4");
  const nav = el("nav", { class: "barra", "aria-label": tr("Ferramentas") },
    el("div", { class: "grupo" }, voltar), el("div", { class: "grupo so-cel" }, bGavetaEsq, bGavetaDir), ferramentas, medicao,
    el("div", { class: "grupo" }, bLayout, bMpr, bEspessura, bObliquo, bGirar),
    el("div", { class: "grupo" }, bPet, bDin, bSeg, bCine, bCineMenu),
    el("div", { class: "grupo" }, bInverter, bRestaurar, bOverlay, bOverlayMenu),
    el("div", { class: "grupo" }, bLaudo, bEnviar, bIA),
    el("div", { class: "grupo" }, bLigar, bLeitura, bAparencia));

  // ---------------------------------------------------------------- painéis
  const tira = el("aside", { class: "tira", "aria-label": tr("Séries") },
    el("div", { class: "titulo-painel com-botao" }, el("span", {}, tr("Séries")), bPainelEsq),
    el("div", { class: "dica" }, tr("Clique numa série para mostrar no quadro ativo, ou arraste-a até um quadro.")));
  const listaSeries = el("div", { class: "series" });
  const anteriores = el("div", { class: "anteriores" });
  tira.append(listaSeries, el("div", { class: "titulo-painel" }, tr("Exames anteriores")), anteriores);
  const telas = el("section", { class: "grade" });
  const painelCarga = el("pre", { class: "painel-carga", hidden: true });

  const ABAS = ["Imagem", "Medidas", "DICOM", "PET", "Filme", "IA"] as const;
  type Aba = typeof ABAS[number];
  const corpoAba = el("div", { class: "corpo-aba", role: "tabpanel" });
  const botoesAba = new Map<Aba, HTMLButtonElement>();
  const abas = el("div", { class: "abas", role: "tablist", "aria-label": tr("Painéis") });
  for (const a of ABAS) {
    const b = el("button", { type: "button", role: "tab", "aria-selected": "false", "data-aba": a }, tr(a)) as HTMLButtonElement;
    b.onclick = () => mostrarAba(a);
    if (a === "Filme" && !config?.usuario.perms?.includes("print")) b.style.display = "none";   // 0.100.11
    if (a === "IA" && !abaIAVisivel) b.style.display = "none";                                   // 0.100.12
    botoesAba.set(a, b);
    abas.append(b);
  }
  abas.append(bPainelDir);
  const lateral = el("aside", { class: "lateral", "aria-label": tr("Painel de ferramentas") }, abas, corpoAba);
  const geral = el("span", { class: "disponiveis", title: tr("Imagens já baixadas e prontas no navegador") });
  const cargaCurta = el("span", { class: "carga-curta" });
  const rodape = el("footer", { class: "rodape" }, geral, cargaCurta, bCarga, bEnvios, bTarefasIA, rodapeBotoes,
    el("span", { class: "tarja-rodape" }, tr("Não destinado a uso diagnóstico")));
  const area = el("div", { class: "area" }, telas, aviso, painelCarga);
  const cabeca = cabecalho(chip, nav);
  const principal = el("main", { class: "telaexame" }, trilhoEsq, tira, area, lateral, trilhoDir);
  app.replaceChildren(cabeca, principal, rodape);
  // ---------------------------------------------------------------- 0.100.19: aparência
  type PosSeries = "esquerda" | "embaixo" | "cima";
  type PosBarra = "cima" | "esquerda";
  let posSeries = lerPreferencia<PosSeries>("posSeries", "esquerda");
  let posBarra = lerPreferencia<PosBarra>("posBarra", "cima");
  const aplicarAparencia = () => {
    const c = celular();                       // no celular o layout é o do celular
    app.classList.toggle("series-embaixo", !c && posSeries === "embaixo");
    app.classList.toggle("series-cima", !c && posSeries === "cima");
    app.classList.toggle("barra-esquerda", !c && posBarra === "esquerda");
    if (!c && posBarra === "esquerda") { if (nav.parentElement !== principal) principal.prepend(nav); }
    else if (nav.parentElement !== cabeca) chip.after(nav);
    requestAnimationFrame(() => grade?.redimensionar());
  };
  aplicarAparencia();
  consultaCel.addEventListener?.("change", aplicarAparencia);
  const leitura = (ligar: boolean) => {
    app.classList.toggle("leitura", ligar);
    bLeitura.classList.toggle("ligado", ligar);
    requestAnimationFrame(() => grade?.redimensionar());
  };
  bLeitura.onclick = () => leitura(!app.classList.contains("leitura"));
  const sairLeitura = el("button", { type: "button", class: "sair-leitura", title: tr("Sair do modo leitura (Esc ou F)") }, tr("Sair do modo leitura")) as HTMLButtonElement;
  sairLeitura.onclick = () => leitura(false);
  area.append(sairLeitura);
  const teclaLeitura = (e: KeyboardEvent) => {
    if (grade !== g) { window.removeEventListener("keydown", teclaLeitura); return; }
    const alvo = e.target as HTMLElement | null;
    if (alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName))) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "f" || e.key === "F") { e.preventDefault(); leitura(!app.classList.contains("leitura")); }
    else if (e.key === "Escape" && app.classList.contains("leitura")) leitura(false);
  };
  window.addEventListener("keydown", teclaLeitura);
  bAparencia.onclick = () => {
    const serie = (v: PosSeries, r: string): ItemMenu => ({ rotulo: tr(r), marcado: posSeries === v,
      acao: () => { posSeries = v; gravarPreferencia("posSeries", v); aplicarAparencia(); } });
    const barra = (v: PosBarra, r: string): ItemMenu => ({ rotulo: tr(r), marcado: posBarra === v,
      acao: () => { posBarra = v; gravarPreferencia("posBarra", v); aplicarAparencia(); } });
    abrirMenu([{ titulo: tr("Séries") }, serie("esquerda", "À esquerda"), serie("embaixo", "Embaixo"), serie("cima", "Em cima"),
      { separador: true }, { titulo: tr("Botões (ferramentas)") }, barra("cima", "Em cima"), barra("esquerda", "À esquerda"),
      { separador: true }, { rotulo: tr("Modo leitura (só as imagens)"), dica: "F", marcado: app.classList.contains("leitura"),
        acao: () => leitura(!app.classList.contains("leitura")) }], 0, 0, tr("Aparência"), bAparencia);
  };

  const esqAberto = lerPreferencia("painelEsq", true);
  const dirAberto = lerPreferencia("painelDir", false);        // 0.100.19: recolhido por padrão
  const ajustarPaineis = (esq: boolean, dir: boolean) => {
    if (celular() && esq && dir) { if (tira.hidden) dir = false; else esq = false; }   // uma gaveta por vez
    tira.hidden = !esq;
    lateral.hidden = !dir;
    trilhoEsq.hidden = esq;
    trilhoDir.hidden = dir;
    bGavetaEsq.classList.toggle("ligado", esq);
    bGavetaDir.classList.toggle("ligado", dir);
    if (!celular()) {                       // no celular as gavetas abrem e fecham toda hora: não é preferência
      gravarPreferencia("painelEsq", esq);
      gravarPreferencia("painelDir", dir);
    }
    requestAnimationFrame(() => grade?.redimensionar());
  };
  // 0.100.18: no celular os painéis são gavetas por cima da imagem, fechadas ao abrir
  bGavetaEsq.onclick = () => ajustarPaineis(tira.hidden, false);
  bGavetaDir.onclick = () => { ajustarPaineis(false, lateral.hidden); atualizarAba(); };
  telas.addEventListener("pointerdown", () => { if (celular() && (!tira.hidden || !lateral.hidden)) ajustarPaineis(false, false); }, true);
  ajustarPaineis(celular() ? false : esqAberto, celular() ? false : dirAberto);
  bPainelEsq.onclick = () => ajustarPaineis(false, !lateral.hidden);
  bPainelDir.onclick = () => { ajustarPaineis(!tira.hidden, false); };
  trilhoEsq.querySelector("button")!.onclick = () => ajustarPaineis(true, !lateral.hidden);
  trilhoDir.querySelector("button")!.onclick = () => { ajustarPaineis(!tira.hidden, true); atualizarAba(); };

  grade = new Grade(telas);
  grade.paciente = paciente;
  grade.aviso = (m: string) => { aviso.textContent = m; };
  (window as unknown as Record<string, unknown>).__ipeGrade = grade; // para os testes de ponta a ponta
  const g = grade;
  if (janela) {
    let ligadas = lerPreferencia("janelasLigadas", true);
    const marcarLigar = () => bLigar.classList.toggle("ligado", ligadas);
    marcarLigar();
    bLigar.onclick = () => { ligadas = !ligadas; gravarPreferencia("janelasLigadas", ligadas); marcarLigar(); };
    g.aoAto = (ato) => { if (ligadas) JAN.canalJanelas()?.postMessage({ tipo: "ato", study, janela, ato } satisfies JAN.Recado); };
    const ouvirAto = (e: MessageEvent) => {
      if (grade !== g) { JAN.canalJanelas()?.removeEventListener("message", ouvirAto); return; }
      const m = e.data as JAN.Recado;
      if (m.tipo !== "ato" || !ligadas || m.janela === janela) return;
      g.aplicarAto(m.ato as Sinc, m.study === study);
    };
    JAN.canalJanelas()?.addEventListener("message", ouvirAto);
  }
  // 0.100.2: o overlay (CAD/IA, GSPS, RTSTRUCT, SEG nas pilhas, textos, medidas, linhas de referência)
  const ov = new Overlay(g, study, () => {
    bOverlay.setAttribute("aria-pressed", String(ov.ligado));
    bOverlay.classList.toggle("ligado", ov.ligado && ov.tem());
  });
  (window as unknown as Record<string, unknown>).__ipeOverlay = ov;
  bOverlay.onclick = () => ov.alternar();
  bOverlayMenu.onclick = () => ov.menu(bOverlayMenu);
  void ov.carregar();
  const d = new Disponiveis();
  disp = d;
  const cron = new Cronometro();
  cronometro = cron;
  (window as unknown as Record<string, unknown>).__ipeCarga = cron; // testes
  const barras = new Map<string, { item: HTMLElement; barra: HTMLElement; texto: HTMLElement }>();
  d.aoMudar = () => {
    for (const [uid, b] of barras) {
      const pc = d.porcentagem(uid);
      const fim = pc === null || pc >= 100;
      b.item.classList.toggle("baixando", !fim);
      b.barra.style.width = `${pc ?? 0}%`;
      b.texto.textContent = fim ? "" : `${pc}%`;
    }
    const g0 = d.geral();
    geral.textContent = g0.porcentagem >= 100 ? ""
      : `${tr("Imagens disponíveis:")} ${g0.porcentagem}%${d.cheio ? ` (${tr("memória do navegador cheia; o resto vem ao mostrar")})` : ""}`;
    const r = cron.resumo();
    cargaCurta.textContent = r.pedidos ? `${tr("Rede")} ${r.mbPorSegundo.toFixed(1)} MB/s · ${tr("decodificação")} ${r.decodificacaoMediaMs.toFixed(1)} ms` : "";
  };
  (window as unknown as Record<string, unknown>).__ipeDisp = d; // testes
  const carregadas = new Map<string, Promise<Awaited<ReturnType<typeof carregarSerie>>>>();
  const pegar = (uid: string) => {
    if (!carregadas.has(uid)) {
      carregadas.set(uid, carregarSerie(study, uid).then((s) => {
        if (s && disp === d) d.conhecer(uid, s.imageIds);
        return s;
      }));
    }
    return carregadas.get(uid)!;
  };
  const mostrarNoAtivo = async (uid: string, i = g.ativo, daTira = false) => {
    aviso.textContent = tr("Carregando…");
    const s = await pegar(uid);
    if (!s) {
      aviso.textContent = tr("Esta série não tem imagens que o navegador mostre.");
      return;
    }
    aviso.textContent = "";
    await g.mostrar(i, s);
    if (daTira && celular() && !tira.hidden) ajustarPaineis(false, false);      // escolheu a série: a gaveta sai da frente
    atualizarAba();
  };
  const itemSerie = (s: API.DicomJson) => {
    const uid = API.texto(s, "0020000E");
    const img = el("img", { alt: "" }) as HTMLImageElement;
    void API.miniatura(study, uid).then((u) => { if (u) img.src = u; });
    const barra = el("i");
    const texto = el("b");
    const item = el("button", { class: "serie", title: API.texto(s, "0008103E"), draggable: "true",
      "data-serie": uid }, img,
      el("span", {}, `${API.texto(s, "00200011")} ${API.texto(s, "00080060")} · ${API.texto(s, "00201209")}`),
      el("small", {}, API.texto(s, "0008103E")), el("div", { class: "disp" }, barra), texto);
    item.onclick = () => void mostrarNoAtivo(uid, g.ativo, true);
    item.ondragstart = (e) => {
      e.dataTransfer?.setData(TIPO_ARRASTO, uid);
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
    };
    barras.set(uid, { item, barra, texto });
    d.estimar(uid, Number(API.texto(s, "00201209") || 0));
    listaSeries.append(item);
  };
  for (const s of series) itemSerie(s);
  /** 0.100.15: as séries que a IA gravou entram na mesma sessão (sem fechar e abrir o exame): as imagens na tira
   *  e as SEG no menu de segmentação. Devolve as SEG novas. */
  const novasSeries = async (): Promise<API.DicomJson[]> => {
    const agora = await API.qido(`/studies/${study}/series`).catch(() => [] as API.DicomJson[]);
    const conhecidas = new Set(todas.map((x) => API.texto(x, "0020000E")));
    const novas = agora.filter((x) => !conhecidas.has(API.texto(x, "0020000E")));
    todas.push(...novas);
    const segsNovas = novas.filter((x) => API.texto(x, "00080060") === "SEG");
    segs.push(...segsNovas);
    if (segs.length) bSeg.disabled = false;
    for (const x of novas.filter((y) => !NAO_MOSTRA.has(API.texto(y, "00080060")))
      .sort((a, b) => Number(API.texto(a, "00200011") || 0) - Number(API.texto(b, "00200011") || 0))) {
      series.push(x);
      itemSerie(x);
    }
    return segsNovas;
  };
  // 0.100.14: o selo "IA" nas séries com resultado de IA ou analisadas por uma (como no Ipê)
  const marcarIA = () => void API.seriesIA(study).then((m) => {
    for (const [uid, info] of Object.entries(m)) {
      const b = barras.get(uid);
      if (!b || b.item.querySelector(".selo-ia")) continue;
      const dica = `${tr(info.resultado ? "Resultado de IA" : "IA nesta série")}: ${info.ferramentas.map((f) => tr(f)).join(", ")}`;
      b.item.append(el("em", { class: `selo-ia${info.resultado ? " resultado" : ""}`, title: dica }, "IA"));
      b.item.title = `${b.item.title}\n${dica}`;
    }
  }).catch(() => undefined);
  marcarIA();
  // exames anteriores do mesmo paciente (abrir troca de exame)
  void (async () => {
    if (!idPac) return;
    const outros = (await API.qido(`/studies?PatientID=${encodeURIComponent(idPac)}&limit=50`).catch(() => []))
      .filter((x) => API.texto(x, "00100020") === idPac && API.texto(x, "0020000D") !== study)
      .sort((a, b) => API.texto(b, "00080020").localeCompare(API.texto(a, "00080020")));
    if (!outros.length) anteriores.append(el("div", { class: "dica" }, tr("Nenhum.")));
    for (const o of outros) {
      const b = el("button", { type: "button", class: "anterior" }, el("span", {}, API.texto(o, "00081030") || "—"),
        el("small", {}, dataBr(API.texto(o, "00080020"))));
      b.onclick = () => { location.hash = `#/exame/${API.texto(o, "0020000D")}`; };
      anteriores.append(b);
    }
  })();
  g.aoSoltar = (uid, i) => void mostrarNoAtivo(uid, i);
  const montar = (l: number, c: number) => {
    g.montar(l, c);
    const livres = g.quadros.map((q, i) => (q.serie ? -1 : i)).filter((i) => i >= 0);
    const usadas = new Set(g.quadros.map((q) => q.serie?.series).filter(Boolean));
    let resto = series.map((s) => API.texto(s, "0020000E")).filter((u) => !usadas.has(u));
    // 0.100.18: a 2ª e a 3ª janela de visualização começam nas séries seguintes às da janela anterior
    const pulo = janela > 1 && !anteriorDe ? (JAN.janelasAtivas().slice(0, janela - 1).filter((j) => j.papel === "viewer").length) * l * c : 0;
    if (pulo && resto.length > pulo) resto = [...resto.slice(pulo), ...resto.slice(0, pulo)];
    livres.forEach((i, k) => { if (resto[k]) void mostrarNoAtivo(resto[k], i); });
  };

  // ---------------------------------------------------------------- comandos
  let tocando = false;
  let fps = 10;
  let girando = false;
  const cine = (ligar: boolean) => {
    tocando = ligar;
    g.cine(tocando ? fps : null);
    bCine.replaceChildren(icone(tocando ? IC.parar : IC.cine, 20));
    bCine.setAttribute("aria-pressed", String(tocando));
    bCine.classList.toggle("ligado", tocando);
  };
  bCine.onclick = () => cine(!tocando);
  bCineMenu.onclick = () => abrirMenu([5, 10, 15, 20, 30].map((n) => ({ rotulo: `${n} ${tr("quadros/s")}`, marcado: n === fps,
    acao: () => { fps = n; if (tocando) g.cine(fps); } })), 0, 0, tr("Velocidade do cine"), bCineMenu);
  const layoutPainel = () => {
    const grade4 = el("div", { class: "grade-layout" });
    const rotulo = el("div", { class: "rotulo-layout" }, `${g.linhas} × ${g.colunas}`);
    const cel: HTMLButtonElement[] = [];
    const marcar = (l: number, c: number) => {
      for (const x of cel) {
        const [xl, xc] = x.dataset.layout!.split("x").map(Number);
        x.classList.toggle("on", xl <= l && xc <= c);
      }
      rotulo.textContent = `${l} × ${c}`;
    };
    for (let l = 1; l <= 4; l++) {
      for (let c = 1; c <= 4; c++) {
        const b = el("button", { type: "button", "aria-label": `${l} × ${c}`, "data-layout": `${l}x${c}` }) as HTMLButtonElement;
        b.onmouseenter = () => marcar(l, c);
        b.onfocus = () => marcar(l, c);
        b.onclick = () => { fecharMenus(); montar(l, c); };
        cel.push(b);
        grade4.append(b);
      }
    }
    const prot = (nome: string, dica: string, fn: () => void) => {
      const b = el("button", { type: "button", class: "protocolo" }, el("span", {}, tr(nome)), el("small", {}, dica));
      b.onclick = () => { fecharMenus(); fn(); };
      return b;
    };
    const conteudo = el("div", { class: "conteudo-layout" },
      el("div", { class: "menu-titulo" }, tr("Grade")), grade4, rotulo,
      el("div", { class: "menu-sep" }), el("div", { class: "menu-titulo" }, tr("Protocolos")),
      prot("MPR", "2 × 2", () => bMpr.click()), prot("PET/CT", tr("fusão · PET · MIP"), () => bPet.click()));
    grade4.onmouseleave = () => marcar(g.linhas, g.colunas);
    marcar(g.linhas, g.colunas);
    abrirPainel(conteudo, bLayout, tr("Layout dos quadros"));
  };
  bLayout.onclick = layoutPainel;
  bMpr.onclick = () => {
    if (g.abrirMPR()) {
      escolher("linhas", "esq");
      aviso.textContent = "";
    }
  };
  let espessuraMm = 0;
  let projecao: Projecao = "mip";
  bEspessura.onclick = () => abrirMenu([
    { titulo: tr("Espessura (quadros A, C, S)") },
    ...[0, 3, 5, 10, 20].map((n) => ({ rotulo: n ? `${n} mm` : tr("Corte fino"), marcado: n === espessuraMm,
      acao: () => { espessuraMm = n; g.espessura(espessuraMm, projecao); } })),
    { separador: true }, { titulo: tr("Projeção da espessura") },
    ...([["mip", "MIP"], ["minip", "MinIP"], ["media", tr("Média")]] as [Projecao, string][]).map(([v, n]) => ({
      rotulo: n, marcado: v === projecao, acao: () => { projecao = v; g.espessura(espessuraMm, projecao); } })),
  ], 0, 0, tr("Espessura e projeção"), bEspessura);
  bObliquo.onclick = () => g.obliquoPorDoisPontos();
  bGirar.onclick = () => {
    girando = !girando;
    g.girar(girando);
    bGirar.setAttribute("aria-pressed", String(girando));
    bGirar.classList.toggle("ligado", girando);
  };
  bInverter.onclick = () => g.inverter();
  bRestaurar.onclick = () => g.restaurar();
  let relogio = 0;
  let ativasAntes = -1;
  listaIA.aoMudar = (ativas, total) => {
    if (ativasAntes >= 0 && ativas !== ativasAntes) void abaIA.carregar();
    ativasAntes = ativas;
    bTarefasIA.style.display = total ? "" : "none";
    bTarefasIA.textContent = ativas ? `${tr("IA")} (${ativas} ${tr("andando")})` : tr("IA");
    bTarefasIA.classList.toggle("andando", ativas > 0);
  };
  listaIA.aoTerminar = async (t) => {
    // 0.100.15: tudo aparece na mesma sessão — as séries novas na tira, a SEG no menu (e já mostrada, se nenhuma
    // estava), os nomes da coluna e dos linfonodos no overlay e o selo IA
    const segsNovas = await novasSeries();
    void ov.carregar();
    void abaIA.achados.carregar();          // 0.100.16: achados novos para revisar
    marcarIA();
    const pintar = segsNovas.find((x) => !/Níveis /.test(API.texto(x, "0008103E")));   // a coluna e os linfonodos são nomes
    if (pintar && !segEscolhida) await escolherSeg(API.texto(pintar, "0020000E"));
    if (abaAtual !== "Medidas") atualizarAba();
    aviso.replaceChildren(`${tr(t.ferramenta)}: ${tr("pronto")}${t.mensagem ? ` — ${t.mensagem}` : ""}. ${tr("O resultado já está neste exame.")}`);
  };
  if (abaIAVisivel) void listaIA.atualizar();
  const abrirAbaIA = () => {
    if (lateral.hidden) ajustarPaineis(!tira.hidden, true);
    mostrarAba("IA");
    void listaIA.atualizar();
  };
  bTarefasIA.onclick = abrirAbaIA;
  bIA.onclick = abrirAbaIA;
  listaEnvios.aoMudar = (ativos, total) => {
    bEnvios.style.display = total ? "" : "none";
    bEnvios.textContent = ativos ? `${tr("Envios")} (${ativos} ${tr("andando")})` : tr("Envios");
    bEnvios.classList.toggle("andando", ativos > 0);
  };
  if (podeEnviar) void listaEnvios.atualizar();
  bEnvios.onclick = () => { void listaEnvios.atualizar(); abrirPainel(listaEnvios.raiz, bEnvios, tr("Envios")); };
  bEnviar.onclick = async () => {
    const q = g.quadros[g.ativo];
    const real = q?.serie && !q.serie.series.startsWith("ipe") ? q.serie.series : null;
    const id = (g.viewport() as unknown as { getCurrentImageId?: () => string } | null)?.getCurrentImageId?.() || "";
    const m = /\/instances\/([^/]+)\/frames\//.exec(id);
    const lista = series.filter((x) => API.texto(x, "0020000E")).map((x) => ({
      uid: API.texto(x, "0020000E"),
      rotulo: `${API.texto(x, "00200011") || "–"} · ${API.texto(x, "00080060")} · ${API.texto(x, "0008103E") || tr("sem descrição")}`,
    }));
    for (const x of segs) lista.push({ uid: API.texto(x, "0020000E"), rotulo: `${API.texto(x, "00200011") || "–"} · SEG · ${API.texto(x, "0008103E")}` });
    const painel = await painelEnvio(study, lista, real, real && m ? decodeURIComponent(m[1]) : null, listaEnvios,
      () => fecharMenus());
    abrirPainel(painel, bEnviar, tr("Enviar a um destino DICOM"));
  };
  bCarga.onclick = () => {
    painelCarga.hidden = !painelCarga.hidden;
    bCarga.setAttribute("aria-pressed", String(!painelCarga.hidden));
    bCarga.classList.toggle("ligado", !painelCarga.hidden);
    window.clearInterval(relogio);
    if (!painelCarga.hidden) {
      const mostrar = () => {
        if (cronometro !== cron) return window.clearInterval(relogio);
        painelCarga.textContent = cron.texto(tr);
      };
      mostrar();
      relogio = window.setInterval(mostrar, 1000);
    }
  };

  // PET/CT
  let cor = COR_PADRAO;
  let opac = 0.5;
  let topo = SUV_PADRAO;
  g.aoMudarSuv = () => {
    const q = g.quadros.find((x) => x.sobre) ?? g.quadros.find((x) => x.serie?.modalidade === "PT");
    if (q) topo = q.suvMax;
    if (abaAtual === "PET") atualizarAba();
  };
  let segEscolhida = "";
  // 0.99.98 (W6): o laudo no navegador, ao lado das imagens
  const abrirLaudo = async (): Promise<PainelLaudo> => {
    if (painelLaudo) return painelLaudo;
    const p = new PainelLaudo(study, () => {
      if (painelLaudo === p) painelLaudo = null;
      bLaudo.setAttribute("aria-pressed", "false");
      bLaudo.classList.remove("ligado");
      requestAnimationFrame(() => grade?.redimensionar());
    });
    painelLaudo = p;
    // o laudo ocupa o lugar do painel de ferramentas (que volta pelo trilho, se ele quiser)
    if (!lateral.hidden) ajustarPaineis(!tira.hidden, false);
    lateral.after(p.raiz);
    bLaudo.setAttribute("aria-pressed", "true");
    bLaudo.classList.add("ligado");
    requestAnimationFrame(() => grade?.redimensionar());
    await p.abrir();
    return p;
  };
  bLaudo.onclick = async () => {
    if (painelLaudo) {
      await painelLaudo.fechar();
      return;
    }
    await abrirLaudo();
  };
  // 0.99.98 (W5): dinâmica da mama — mapas calculados no navegador e curvas das ROIs
  const fecharDin = () => {
    din?.encerrar();
    din = null;
    bDin.setAttribute("aria-pressed", "false");
    bDin.classList.remove("ligado");
  };
  bDin.onclick = async () => {
    if (din) {
      fecharDin();
      montar(...inicial);
      return;
    }
    mg?.encerrar();
    mg = null;
    aviso.textContent = tr("Procurando as fases da dinâmica…");
    const dd = await dinamicaDoExame(study).catch(() => null);
    if (!dd || dd.motivo) {
      aviso.textContent = dd?.motivo ? `${tr("Dinâmica:")} ${tr(dd.motivo)}` : tr("Não foi possível falar com o servidor.");
      return;
    }
    guardarTabelas(config?.tabelas_cores);
    const modo = new ModoDinamica(g, dd, { study, aviso: (m) => { aviso.textContent = m; },
      aoSair: () => { fecharDin(); montar(...inicial); } });
    din = modo;
    aviso.textContent = tr("Calculando os mapas…");
    area.prepend(modo.barra);
    area.append(modo.painel);
    if (!(await modo.abrir())) {
      fecharDin();
      aviso.textContent = tr("Não consegui ler as fases da dinâmica.");
      return;
    }
    aviso.textContent = "";
    modo.ouvir(aoMudarMedidas(() => void modo.atualizarCurvas()));
    bDin.setAttribute("aria-pressed", "true");
    bDin.classList.add("ligado");
  };
  bPet.onclick = async () => {
    const maior = (mod: string) => series.filter((x) => API.texto(x, "00080060") === mod)
      .sort((a, b) => Number(API.texto(b, "00201209") || 0) - Number(API.texto(a, "00201209") || 0))[0];
    const ativa = g.quadros[g.ativo]?.serie;
    const ptUid = ativa?.modalidade === "PT" ? ativa.series : (maior("PT") ? API.texto(maior("PT"), "0020000E") : "");
    const ctUid = maior("CT") ? API.texto(maior("CT"), "0020000E") : "";
    if (!ptUid || !ctUid) {
      aviso.textContent = tr("O PET/CT pede uma série de PET e uma de TC no exame.");
      return;
    }
    aviso.textContent = tr("Carregando…");
    const [tc, pet] = await Promise.all([pegar(ctUid), pegar(ptUid)]);
    aviso.textContent = "";
    if (!tc || !pet) return;
    if (!pet.suv) aviso.textContent = `${tr("Sem SUV:")} ${pet.suvMotivo || "?"}.`;
    if (g.abrirPETCT(tc, pet, lerPreferencia("arranjoPet", ARRANJO_PET_PADRAO))) {
      g.fusao({ cor, opacidade: opac, suvMax: topo });
      if (lateral.hidden) ajustarPaineis(!tira.hidden, true);
      mostrarAba("PET");
    }
  };
  const escolherSeg = async (uid: string) => {
    segEscolhida = uid;
    void ov.usarSeg(uid);
    aviso.textContent = uid ? tr("Carregando…") : "";
    const r = await g.mostrarSegDaSerie(study, uid || null, pegar);
    if (r) aviso.textContent = `${r.descricao}: ${r.segmentos.map((x) => x.nome).join(", ")}`;
    else if (uid) segEscolhida = "";
    if (abaAtual === "PET") atualizarAba();
  };
  const nomeSeg = (x: API.DicomJson) => `${API.texto(x, "00200011")} · ${API.texto(x, "0008103E") || "SEG"}`;
  bSeg.onclick = () => abrirMenu([
    { rotulo: tr("Sem segmentação"), marcado: !segEscolhida, acao: () => void escolherSeg("") },
    ...segs.map((x) => ({ rotulo: nomeSeg(x), marcado: segEscolhida === API.texto(x, "0020000E"),
      acao: () => void escolherSeg(API.texto(x, "0020000E")) })),
  ], 0, 0, tr("Segmentação (SEG)"), bSeg);

  // ---------------------------------------------------------------- abas da direita
  let abaAtual: Aba = lerPreferencia<Aba>("aba", "Medidas");
  if (!ABAS.includes(abaAtual) || (abaAtual === "Filme" && !config?.usuario.perms?.includes("print"))
    || (abaAtual === "IA" && !abaIAVisivel)) abaAtual = "Medidas";
  // 0.100.12: a aba IA — todas as ferramentas de CAD/IA, a escolhida roda para o exame aberto
  const serieDoQuadro = () => {
    const q = g.quadros[g.ativo];
    const real = q?.serie && !q.serie.series.startsWith("ipe") ? q.serie : null;
    return real ? { uid: real.series, rotulo: `${real.numero || "–"} · ${real.modalidade} · ${real.descricao}` } : null;
  };
  const abaIA = new AbaIA(study, listaIA, serieDoQuadro, podeIA);
  // 0.100.16: revisar os achados de IA — ir até o achado e mandar os revisados ao laudo
  abaIA.achados.irAte = async (a) => {
    if (!a.posicao) return;
    let i = g.quadros.findIndex((q) => q.tipo === "pilha" && q.serie?.series === a.series_uid);
    if (i < 0 && a.series_uid && barras.has(a.series_uid)) {
      i = g.ativo;
      await mostrarNoAtivo(a.series_uid, i);
    }
    if (i >= 0) g.ativar(i);
    const p = a.posicao as [number, number, number];
    g.irAoPontoNasPilhas(p as unknown as Parameters<typeof g.irAoPontoNasPilhas>[0]);
    g.irAoPonto(p);
  };
  abaIA.achados.mandarAoLaudo = async (texto) => {
    const p = await abrirLaudo();
    p.atualizarIa(texto);
    return p.inserirTexto(texto) ? tr("Os achados revisados foram para o laudo.")
      : `${tr("Não deu para escrever no laudo")}: ${p.motivoSemEscrever() || tr("abra um laudo em rascunho")}.`;
  };
  // 0.100.11: o filme (a aba Filme), montado com os quadros e impresso pelo servidor
  let painelFilme: PainelFilme | null = null;
  const filme = () => {
    painelFilme ??= new PainelFilme(study, g, (uid) => pegar(uid), `${nomePac.replace(/\^/g, " ").trim()} — ${API.texto(estudo, "00081030")}`.trim());
    return painelFilme;
  };
  const secao = (t: string) => el("div", { class: "titulo-painel" }, tr(t));
  const secaoPronta = (t: string) => el("div", { class: "titulo-painel" }, t); // já traduzida
  const imagemAtual = (): string => {
    const vp = g.viewport() as unknown as { getCurrentImageId?: () => string } | null;
    try { return vp?.getCurrentImageId?.() || ""; } catch { return ""; }
  };
  const irParaMedida = async (m: ResumoMedida) => {
    const p = partesDoImageId(m.imageId);
    if (!p) return;
    let i = g.quadros.findIndex((q) => q.tipo === "pilha" && q.serie?.series === p.series);
    if (i < 0) {
      i = g.ativo;
      await mostrarNoAtivo(p.series, i);
    }
    g.ativar(i);
    const q = g.quadros[i];
    const k = q?.serie?.imageIds.indexOf(m.imageId) ?? -1;
    const vp = g.viewport(i) as unknown as { setImageIdIndex?: (n: number) => Promise<unknown> } | null;
    if (k >= 0) await vp?.setImageIdIndex?.(k);
    csTools.annotation.selection.setAnnotationSelected(m.uid, true, false);
  };
  const conteudoAba: Record<Aba, () => Node[]> = {
    Filme: () => [filme().raiz],
    IA: () => { abaIA.mostrar(); return [abaIA.raiz]; },
    Imagem: () => {
      const s = g.quadros[g.ativo]?.serie;
      const lista = janelasProntas(s?.modalidade || "");
      const jan = el("div", { class: "lista-botoes" },
        ...lista.map(([n, w, l]) => el("button", { type: "button", class: "linha", onclick: () => g.janela(Number(w), Number(l)) },
          el("span", {}, String(n)), el("small", {}, `${w} / ${l}`))),
        el("button", { type: "button", class: "linha", onclick: () => g.janelaDoArquivo() }, el("span", {}, tr("Do arquivo")), el("small", {}, "")));
      const acoes = (itens: [string, string, () => void][]) => el("div", { class: "acoes" },
        ...itens.map(([r, ic, fn]) => { const b = botaoIcone(r, ic); b.onclick = fn; return b; }));
      return [
        secaoPronta(`${tr("Janelas prontas")}${s ? ` · ${s.modalidade}` : ""}`), jan,
        secao("Imagem"), acoes([["Inverter", IC.inverter, () => g.inverter()], ["Restaurar", IC.restaurar, () => g.restaurar()],
          ["Girar 90° à direita", IC.girar90, () => g.rodar(90)], ["Girar 90° à esquerda", "M20 12a8 8 0 0 0-14-5.3M6 3v4h4", () => g.rodar(-90)],
          ["Espelhar na horizontal", IC.espelhar, () => g.espelhar("h")], ["Espelhar na vertical", "M3 12h18M7 8l5-5 5 5M7 16l5 5 5-5", () => g.espelhar("v")]]),
        secao("Zoom"), el("div", { class: "acoes texto" },
          el("button", { type: "button", onclick: () => g.zoom("ajustar") }, tr("Ajustar")),
          el("button", { type: "button", onclick: () => g.zoom("1:1") }, "1:1"),
          el("button", { type: "button", onclick: () => g.zoom("2x") }, "2×")),
      ];
    },
    Medidas: () => {
      const ms = listarMedidas();
      const sel = new Set(csTools.annotation.selection.getAnnotationsSelected());
      const itens = ms.map((m) => {
        const p = partesDoImageId(m.imageId);
        const q = g.quadros.find((x) => x.serie?.series === p?.series)?.serie;
        const n = q ? q.imageIds.indexOf(m.imageId) + 1 : 0;
        const linha = el("div", { class: `medida${sel.has(m.uid) ? " sel" : ""}` });
        const ir = el("button", { type: "button", class: "ir", title: tr("Mostrar na imagem") },
          el("span", { class: "nome" }, m.nome, el("small", {}, n ? `Im ${n}` : "")),
          el("span", { class: "valor" }, m.linhas.join("\n") || "—"),
          ...(m.autor ? [el("small", {}, m.autor)] : []));
        ir.onclick = () => void irParaMedida(m);
        const cp = botaoIcone("Copiar valor", IC.copiar);
        cp.onclick = async () => { aviso.textContent = (await copiarValor(m.uid)) ? tr("Valor copiado.") : tr("Não deu para copiar."); };
        const ap = botaoIcone("Apagar esta medida", IC.lixo, { class: "ic perigo" });
        ap.onclick = () => apagarMedida(m.uid);
        linha.append(ir, el("div", { class: "acoes-medida" }, cp, ap));
        return linha;
      });
      return [secaoPronta(`${ms.length} ${ms.length === 1 ? tr("medida") : tr("medidas")}`),
        ...(itens.length ? itens : [el("div", { class: "dica" }, tr("Nenhuma medida ainda. Escolha uma ferramenta de medida e desenhe na imagem."))])];
    },
    DICOM: () => {
      const id = imagemAtual();
      const m = META.get(id);
      if (!m) return [el("div", { class: "dica" }, tr("Nenhuma imagem no quadro ativo."))];
      const filtro = el("input", { type: "search", placeholder: tr("Filtrar"), "aria-label": tr("Filtrar tags") }) as HTMLInputElement;
      const corpo = el("tbody");
      const linhas = Object.keys(m).sort().map((tag) => {
        const v = m[tag];
        const val = v.Value !== undefined ? (v.Value as unknown[]).map((x) => (typeof x === "object" ? (x && "Alphabetic" in (x as object) ? (x as { Alphabetic: string }).Alphabetic : "…") : String(x))).join("\\") : (v.BulkDataURI ? tr("(dados)") : "");
        const nome = NOMES_TAGS[tag] || "";
        const tr_ = el("tr", {}, el("td", { class: "tag" }, `${tag.slice(0, 4)},${tag.slice(4)}`), el("td", {}, nome),
          el("td", { class: "vr" }, String(v.vr || "")), el("td", { class: "val" }, val.length > 120 ? `${val.slice(0, 120)}…` : val));
        corpo.append(tr_);
        return { tr_, texto: `${tag} ${nome} ${val}`.toLowerCase() };
      });
      filtro.oninput = () => {
        const t = filtro.value.toLowerCase();
        for (const l of linhas) l.tr_.hidden = !!t && !l.texto.includes(t);
      };
      return [filtro, el("table", { class: "tags" }, corpo)];
    },
    PET: () => {
      const pets = g.quadros.map((q) => q.sobre ?? (q.serie?.modalidade === "PT" ? q.serie : null)).filter(Boolean);
      const pet = pets[0];
      const cores = el("select", { title: tr("Cor da fusão") },
        ...(config?.tabelas_cores ? Object.entries(config.tabelas_cores) : []).map(([k, t]) =>
          el("option", { value: k, selected: k === cor }, tr(t.nome)))) as HTMLSelectElement;
      cores.onchange = () => { cor = cores.value; g.fusao({ cor }); };
      const op = el("select", { title: tr("Opacidade da fusão") },
        ...[20, 35, 50, 65, 80, 100].map((n) => el("option", { value: n / 100, selected: Math.round(opac * 100) === n }, `${n}%`))) as HTMLSelectElement;
      op.onchange = () => { opac = Number(op.value); g.fusao({ opacidade: opac }); };
      const topos = [...new Set([3, 5, 6, 8, 10, 15, 20, topo])].sort((a, b) => a - b);
      const tp = el("select", { title: tr("Topo da janela de SUV") },
        ...topos.map((n) => el("option", { value: n, selected: n === topo }, `SUV ${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`))) as HTMLSelectElement;
      tp.onchange = () => { topo = Number(tp.value); g.fusao({ suvMax: topo }); };
      const sg = el("select", { title: tr("Segmentação (SEG)") }, el("option", { value: "" }, tr("Sem segmentação")),
        ...segs.map((x) => el("option", { value: API.texto(x, "0020000E"), selected: segEscolhida === API.texto(x, "0020000E") }, nomeSeg(x)))) as HTMLSelectElement;
      if (!segs.length) sg.disabled = true;
      sg.onchange = () => void escolherSeg(sg.value);
      const abrir = el("button", { type: "button", class: "primario", onclick: () => bPet.click() }, tr("Abrir PET/CT"));
      // 0.100.2: o arranjo da leitura — a grade e o que cada quadro mostra, lembrado para o próximo PET/CT
      const arranjo: Node[] = [];
      if (g.petct && pets.length) {
        const atual = g.arranjoPet();
        const salvar = (l: number, c: number, qs: ConteudoPet[]) => {
          gravarPreferencia("arranjoPet", { l, c, quadros: qs });
          g.montarPetct(l, c, qs);
          atualizarAba();
        };
        const grades: [number, number][] = [[1, 1], [1, 2], [1, 3], [2, 2], [2, 3], [1, 4]];
        const sl = el("select", { "aria-label": tr("Grade do PET/CT") },
          ...grades.map(([l, c]) => el("option", { value: `${l}x${c}`, selected: g.linhas === l && g.colunas === c }, `${l} × ${c}`))) as HTMLSelectElement;
        sl.onchange = () => {
          const [l, c] = sl.value.split("x").map(Number);
          const qs = Array.from({ length: l * c }, (_, i) => atual[i] ?? ARRANJO_PET_PADRAO.quadros[i % 3]);
          salvar(l, c, qs);
        };
        const VISTAS: [VistaPet, string][] = [["fusao", "TC + PET"], ["tc", "TC"], ["pet", "PET"], ["mip", "MIP do PET (3D)"]];
        const PLANOS: [string, string][] = [["AXIAL", "Axial"], ["CORONAL", "Coronal"], ["SAGITTAL", "Sagital"]];
        const linhasQ = atual.map((cp, i) => {
          const sv = el("select", { "aria-label": `${tr("Quadro")} ${i + 1}` },
            ...VISTAS.map(([v, n]) => el("option", { value: v, selected: v === cp.v }, tr(n)))) as HTMLSelectElement;
          const sp = el("select", { "aria-label": `${tr("Plano do quadro")} ${i + 1}` },
            ...PLANOS.map(([v, n]) => el("option", { value: v, selected: v === cp.plano }, tr(n)))) as HTMLSelectElement;
          sp.disabled = cp.v === "mip";
          const mudar = () => {
            const qs = atual.slice();
            qs[i] = { v: sv.value as VistaPet, plano: sp.value as ConteudoPet["plano"] };
            salvar(g.linhas, g.colunas, qs);
          };
          sv.onchange = mudar;
          sp.onchange = mudar;
          return el("div", { class: "linha-arranjo" }, el("span", {}, `${i + 1}`), sv, sp);
        });
        const padrao = el("button", { type: "button", onclick: () => salvar(ARRANJO_PET_PADRAO.l, ARRANJO_PET_PADRAO.c, ARRANJO_PET_PADRAO.quadros) },
          tr("Arranjo padrão"));
        arranjo.push(secao("Arranjo do PET/CT"), sl, ...linhasQ, padrao,
          el("div", { class: "dica" }, tr("Janela do PET: arraste no quadro (para cima e para baixo, o topo; para os lados, o piso). Na fusão, Shift + arrasto ajusta a TC.")));
      }
      return [
        ...arranjo,
        secaoPronta("SUV"), el("div", { class: "dica" }, pet ? (pet.suv ? `${tr("Pelo peso")} · ${tr("fator")} ${pet.suv.toExponential(3)}` : `${tr("Sem SUV:")} ${pet.suvMotivo || "?"}`) : tr("Nenhum PET nos quadros.")),
        abrir,
        secao("Cor da fusão"), cores, secao("Opacidade"), op, secao("Topo da janela de SUV"), tp,
        secao("Segmentações do exame"), sg,
        el("div", { class: "dica" }, `${tr("SUV máximo perto do cursor")}: ${tr("escolha a ferramenta e clique perto da lesão.")}`),
      ];
    },
  };
  function mostrarAba(a: Aba): void {
    abaAtual = a;
    gravarPreferencia("aba", a);
    for (const [k, b] of botoesAba) {
      b.setAttribute("aria-selected", String(k === a));
      b.classList.toggle("sel", k === a);
    }
    atualizarAba();
  }
  function atualizarAba(): void {
    if (lateral.hidden) return;
    const foco = document.activeElement;
    const dentro = corpoAba.contains(foco);
    corpoAba.replaceChildren(...conteudoAba[abaAtual]());
    if (dentro) (corpoAba.querySelector("input, select") as HTMLElement | null)?.focus();
  }
  const pararMedidas = aoMudarMedidas(() => { if (abaAtual === "Medidas") atualizarAba(); });
  g.aoMudar = () => { if (abaAtual !== "Medidas") atualizarAba(); mg?.quadroAtivo(); };
  const antesDeSair = grade.encerrar.bind(grade);
  grade.encerrar = () => { pararMedidas(); antesDeSair(); };
  const quandoRolar = () => { if (abaAtual === "DICOM") atualizarAba(); };
  let rolarT = 0;
  telas.addEventListener("wheel", () => { window.clearTimeout(rolarT); rolarT = window.setTimeout(quandoRolar, 250); }, { passive: true });

  // ---------------------------------------------------------------- menu do botão direito
  g.aoMenu = (i, x, y, elTela) => {
    g.ativar(i);
    const q = g.quadros[i];
    const uid = medidaNoPonto(elTela, x, y);
    const m = uid ? medidaPorUid(uid) : null;
    const imageId = imagemAtual();
    const bs = botoes();
    const itens: ItemMenu[] = [];
    if (m) {
      itens.push({ titulo: `${m.nome}${m.linhas[0] ? ` · ${m.linhas[0]}` : ""}` });
      if (m.kind === "arrow") itens.push({ rotulo: tr("Editar texto da seta"), icone: IC.texto, acao: () => editarTexto(m.uid) });
      itens.push({ rotulo: tr("Copiar valor"), icone: IC.copiar, acao: async () => { aviso.textContent = (await copiarValor(m.uid)) ? tr("Valor copiado.") : tr("Não deu para copiar."); } });
      itens.push({ rotulo: tr("Apagar esta medida"), icone: IC.lixo, perigo: true, acao: () => apagarMedida(m.uid) });
      itens.push({ separador: true });
    }
    const lista = janelasProntas(q?.serie?.modalidade || "");
    itens.push({ rotulo: tr("Janela"), icone: IC.janela, sub: [
      ...lista.map(([n, w, l]) => ({ rotulo: String(n), dica: `${w} / ${l}`, acao: () => g.janela(Number(w), Number(l)) })),
      { separador: true },
      { rotulo: tr("Do arquivo"), acao: () => g.janelaDoArquivo() },
      { rotulo: tr("Inverter"), acao: () => g.inverter() },
    ] });
    itens.push({ rotulo: tr("Zoom"), icone: IC.zoom, sub: [
      { rotulo: tr("Ajustar à tela"), acao: () => g.zoom("ajustar") },
      { rotulo: "1:1", acao: () => g.zoom("1:1") }, { rotulo: "2×", acao: () => g.zoom("2x") },
    ] });
    itens.push({ rotulo: tr("Girar e espelhar"), icone: IC.girar90, sub: [
      { rotulo: tr("Girar 90° à direita"), acao: () => g.rodar(90) },
      { rotulo: tr("Girar 90° à esquerda"), acao: () => g.rodar(-90) },
      { rotulo: tr("Espelhar na horizontal"), acao: () => g.espelhar("h") },
      { rotulo: tr("Espelhar na vertical"), acao: () => g.espelhar("v") },
    ] });
    if (q?.serie && !q.serie.semVolume) {
      itens.push({ rotulo: tr("Plano"), icone: IC.mpr, dica: q.tipo === "pilha" ? tr("Original") : q.tipo === "mip" ? "MIP" : "", sub: [
        { rotulo: tr("Original"), marcado: q.tipo === "pilha", acao: () => g.mudarPlano(i, null) },
        { rotulo: tr("Axial"), marcado: q.tipo === "plano" && q.plano === "AXIAL", acao: () => g.mudarPlano(i, "AXIAL") },
        { rotulo: tr("Coronal"), marcado: q.tipo === "plano" && q.plano === "CORONAL", acao: () => g.mudarPlano(i, "CORONAL") },
        { rotulo: tr("Sagital"), marcado: q.tipo === "plano" && q.plano === "SAGITTAL", acao: () => g.mudarPlano(i, "SAGITTAL") },
        { rotulo: "MIP", marcado: q.tipo === "mip", acao: () => g.mudarParaMip(i) },
      ] });
    }
    const subBotao = (k: keyof Botoes): ItemMenu => ({ rotulo: tr(k === "esq" ? "Botão esquerdo" : k === "meio" ? "Botão do meio" : "Botão direito"),
      dica: tr(NOMES_FERRAMENTAS[bs[k]]), sub: (Object.keys(NOMES_FERRAMENTAS) as Ferramenta[]).map((f) => ({
        rotulo: tr(NOMES_FERRAMENTAS[f]), icone: IC[f], marcado: bs[k] === f, acao: () => escolher(f, k) })) });
    itens.push({ rotulo: tr("Funções dos botões"), icone: IC.botoes, sub: [subBotao("esq"), subBotao("meio"), subBotao("dir")] });
    itens.push({ rotulo: tr("Série"), icone: IC.serie, dica: q?.serie ? `Se ${q.serie.numero}` : "", sub: series.map((s) => {
      const u = API.texto(s, "0020000E");
      return { rotulo: `${API.texto(s, "00200011")} · ${API.texto(s, "0008103E") || API.texto(s, "00080060")}`,
        marcado: q?.serie?.series === u, acao: () => void mostrarNoAtivo(u, i) };
    }) });
    itens.push({ rotulo: tr("Quadros e cine"), icone: IC.layout, sub: [
      ...LAYOUTS_PRONTOS.map(([l, c]) => ({ rotulo: `${l} × ${c}`, marcado: g.linhas === l && g.colunas === c, acao: () => montar(l, c) })),
      { separador: true },
      { rotulo: tocando ? tr("Parar o cine") : tr("Cine"), acao: () => cine(!tocando) },
    ] });
    itens.push({ separador: true });
    itens.push({ rotulo: tr("Apagar medidas da imagem"), icone: IC.lixo, desligado: !imageId, acao: () => {
      const n = apagarMedidasDaImagem(imageId);
      aviso.textContent = n ? `${n} ${tr("medidas apagadas.")}` : tr("Nenhuma medida nesta imagem.");
    } });
    itens.push({ rotulo: tr("Restaurar"), icone: IC.restaurar, acao: () => g.restaurar() });
    abrirMenu(itens, x, y, tr("Menu da imagem"));
  };

  // ---------------------------------------------------------------- começo
  const salvos = lerPreferencia<Partial<Botoes>>("botoes", {});
  const validos = (f: unknown): f is Ferramenta => typeof f === "string" && f in NOMES_FERRAMENTAS && f !== "suvmax" && f !== "linhas";
  // 0.100.18: no toque não há roda — sem escolha guardada, um dedo rola os cortes
  aplicarBotoes({ esq: validos(salvos.esq) ? salvos.esq : (toque() ? "rolar" : "janela"), meio: validos(salvos.meio) ? salvos.meio : "mover",
    dir: validos(salvos.dir) ? salvos.dir : "zoom" });
  atualizarMarcas();
  const inicial: [number, number] = confJanela?.layout && !celular() ? confJanela.layout
    : series.length >= 2 && !celular() ? [1, 2] : [1, 1];
  // 0.99.98 (W4): exame de mamografia abre no protocolo do Ipê (uma ou duas telas)
  const dadosMg = await API.mamografia(study).catch(() => null);
  if (grade !== g) return;
  if (dadosMg) {
    const modo = new ModoMamografia(g, dadosMg, { study, tela, aviso: (m) => { aviso.textContent = m; },
      aoSair: () => { mg = null; montar(...inicial); } });
    mg = modo;
    area.prepend(modo.barra);
    void modo.aplicar();
    if (tela === 2) modo.anunciar(janela === 2);
  } else {
    montar(...inicial);
  }
  mostrarAba(abaAtual);
  // pré-carga: primeiro as séries que estão nos quadros, depois as outras, na ordem da tira
  void (async () => {
    await new Promise((r) => setTimeout(r, 300));
    const nosQuadros = new Set(g.quadros.map((q) => q.serie?.series).filter(Boolean) as string[]);
    const ordem = series.map((x) => API.texto(x, "0020000E"));
    ordem.sort((a, b) => Number(nosQuadros.has(b)) - Number(nosQuadros.has(a)));
    // 0.99.99: os metadados de todas as séries vêm juntos (três de cada vez), sem esperar uma acabar para pedir a
    // próxima; os quadros entram na fila na ordem da tira assim que a série chega
    let proxima = 0;
    const pedirMais = () => {
      while (proxima < ordem.length && proxima < feitas + 3) void pegar(ordem[proxima++]).catch(() => null);
    };
    let feitas = 0;
    pedirMais();
    for (const uid of ordem) {
      if (disp !== d) return;
      const s = await pegar(uid).catch(() => null);
      feitas++;
      pedirMais();
      if (s && disp === d) d.preCarregar(s.imageIds);
    }
  })();
}

// ------------------------------------------------------------------ rotas
function rota(): void {
  if (!API.tokenAtual()) {
    // a segunda tela da mamografia: o token vem da janela que a abriu
    if (/^#\/(mg\/[0-9.]+\/2|exame\/[0-9.]+\/j[1-9]|espera\/j[1-9])$/.test(location.hash) && window.opener) {
      app.replaceChildren(el("div", { class: "estado" }, tr("Abrindo a segunda tela…")));
      void pedirToken().then((ok) => { if (ok) void entrouNaSegunda(); else telaLogin(); });
      return;
    }
    telaLogin();
    return;
  }
  if (!config) { void retomar(); return; }
  const h = location.hash || "#/lista";
  const m = h.match(/^#\/exame\/([0-9.]+)(?:\/j([1-9]))?$/);
  const m2 = h.match(/^#\/mg\/([0-9.]+)\/2$/);
  // na mamografia, a 2ª janela de visualização é a segunda tela do protocolo (como no Ipê)
  if (m) void telaExame(m[1], m[2] === "2" ? 2 : 1, Number(m[2] || 0));
  else if (m2) void telaExame(m2[1], 2);
  else if (/^#\/espera\/j[1-9]$/.test(h)) telaEspera();
  else void telaLista();
}

window.addEventListener("hashchange", rota);
// 0.100.5: fechar a aba (ou recarregar) com um exame aberto pede confirmação; a 2ª tela da mamografia não pede
window.addEventListener("beforeunload", (e) => {
  if (API.tokenAtual() && /^#\/exame\/[0-9.]+$/.test(location.hash)) {      // (as janelas de visualização não pedem)
    e.preventDefault();
    e.returnValue = "";
  }
});
(window as unknown as Record<string, unknown>).__ipeIdioma = (l: string) => { setLang(l); rota(); }; // testes
window.addEventListener("resize", () => grade?.redimensionar());
rota();
