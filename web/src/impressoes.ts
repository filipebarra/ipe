// 0.100.68: Impressões e Painel de filmes no Ipê Web — a aba Impressões do Ipê de mesa atendida pelo servidor.
// A lista do que chegou pela impressora DICOM, do que foi montado no compositor e do filme que veio no exame; a
// folha desenhada; identificar o paciente (com o OCR do cabeçalho); enviar para os destinos cadastrados no
// servidor (todos — aqui não vale o "compartilhar"); reimprimir; juntar como páginas; apagar; os parados; o
// histórico; e o painel com as contas. Só administradores e técnicos. Quem desenha, lê e imprime é o servidor.
import { pedir } from "./api";
import { getLang, tr } from "./i18n";

export interface Linha {
  k: string; kind: string; tipo: string; paciente: string; rotulo: string; id: string; modalidade: string;
  de_onde: string; quando: string; ordem: string; folhas: number; imagens: number; filme: string; situacao: string;
  status: string; destino: string; study_uid: string; pode_identificar: boolean; sem_nome: boolean;
}
interface Destino { nome: string; rotulo: string; tipo: string }
interface Lista {
  linhas: Linha[]; total: number; de: number; parados: number; faixa: string[]; aviso: string; destinos: Destino[];
  modelos: string[]; filtros: { k: string; nome: string }[]; ocr: { disponivel: boolean; motivo: string };
  pode_apagar: boolean; papel: string;
}
interface Envio { quando: string; destino: string; quem: string; como: string; modelo: string; ok: boolean; resultado: string }
interface Detalhes { k: string; folhas: number; linhas: string[]; titulo: string; envios: Envio[]; mensagem: string }
interface Candidato { texto: string; nome: string; id: string; study_uid: string; ocr: boolean }
interface Grupo { id: string; nome: string; motivo: string; simbolo: string; trabalhos: number; folhas: number; imagens: number; desde: string; pode_liberar: boolean }
interface Tempo { mediana: string; p90: string; n: number; negativos: number }
interface GrupoPainel { nome: string; filmes: number; impressos: number; pct: string; exame_filme: string; filme_impressao: string; folhas_impressas: number; reimpressoes: number }
export interface LinhaPainel {
  id: number; tipo: string; origem: string; criado: string; ordem: string; criado_por: string; paciente: string;
  modalidade: string; exame: string; descricao: string; folhas: number; imagens: number; impresso: boolean;
  impresso_em: string; impresso_por: string; destino: string; impressoes: number; exame_filme: string;
  filme_impressao: string; exame_impressao: string; study_uid: string; k: string;
}
interface Painel {
  periodos: { k: string; nome: string }[]; de: string; ate: string; modalidades: string[]; usuarios: string[];
  cartoes: {
    filmes: number; compositor: number; dicom: number; folhas: number; imagens: number; pct: string; impressos: number;
    reimpressos: number; parados: number; nao_impressos: number; dias: number; parados_lista: string[];
    exame_filme: Tempo; filme_impressao: Tempo; exame_impressao: Tempo; em_24h: string; folhas_impressas: number;
    impressoes: number; destinos: { nome: string; n: number }[];
  };
  por_mes: { mes: string; impressos: number; nao: number }[]; por_modalidade: GrupoPainel[]; por_usuario: GrupoPainel[];
  linhas: LinhaPainel[]; total: number; no_periodo: number;
}

const COLUNAS: [string, keyof Linha, boolean][] = [["Origem", "tipo", false], ["Paciente", "paciente", false], ["ID", "id", false],
  ["Modalidade", "modalidade", false], ["De onde veio", "de_onde", false], ["Chegada", "ordem", false], ["Folhas", "folhas", true],
  ["Imagens", "imagens", true], ["Filme", "filme", false], ["Situação", "situacao", false], ["Último destino", "destino", false]];
const COLUNAS_PAINEL: [string, keyof LinhaPainel][] = [["Criado em", "criado"], ["Origem", "origem"], ["Criado por", "criado_por"],
  ["Paciente", "paciente"], ["Modalidade", "modalidade"], ["Exame (data/hora)", "exame"], ["Descrição do exame", "descricao"],
  ["Folhas", "folhas"], ["Imagens", "imagens"], ["Impresso", "impresso"], ["Impresso em", "impresso_em"],
  ["Impresso por", "impresso_por"], ["Destino", "destino"], ["Impressões", "impressoes"], ["Exame → filme", "exame_filme"],
  ["Filme → impressão", "filme_impressao"], ["Exame → impressão", "exame_impressao"]];

function caminho(c: string): string {
  const idioma = getLang();
  if (idioma !== "pt") c += `${c.includes("?") ? "&" : "?"}lang=${idioma}`;
  return `${location.origin}/api/web/impressoes/${c}`;
}

async function pedirJson<T>(c: string, corpo?: unknown): Promise<T> {
  const r = await pedir(caminho(c), {
    method: corpo === undefined ? "GET" : "POST",
    headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    try { msg = (JSON.parse(msg) as { error?: string }).error || msg; } catch { /* texto */ }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

function botao(texto: string, fazer: () => void, classe = ""): HTMLButtonElement {
  const b = el("button", { type: "button" }, tr(texto));
  if (classe) b.className = classe;
  b.onclick = fazer;
  return b;
}

/** Uma janela por cima da tela (o <dialog> do navegador): título, conteúdo e os botões de baixo. */
function janela(titulo: string, conteudo: Node[], botoes: HTMLButtonElement[], larga = false): HTMLDialogElement {
  const d = el("dialog", { class: `imp-janela${larga ? " larga" : ""}`, "aria-label": titulo });
  d.append(el("h3", {}, titulo), el("div", { class: "imp-janela-corpo" }, ...conteudo), el("div", { class: "imp-janela-botoes" }, ...botoes));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}

/** Pergunta de sim ou não, numa janela; devolve o que a pessoa escolheu. */
function confirmar(titulo: string, texto: string, aviso = "", sim = "Sim"): Promise<boolean> {
  return new Promise((resolver) => {
    let resp = false;
    const bSim = botao(sim, () => { resp = true; d.close(); }, "primario");
    const d = janela(titulo, [el("p", {}, texto), ...(aviso ? [el("p", { class: "imp-aviso" }, aviso)] : [])],
      [botao("Cancelar", () => d.close()), bSim]);
    d.addEventListener("close", () => resolver(resp));
  });
}

function csv(cabecalho: string[], linhas: (string | number)[][]): string {
  const cel = (v: string | number) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [cabecalho, ...linhas].map((l) => l.map(cel).join(";")).join("\r\n");
}

/** O CSV do painel (para exportar e para os testes): uma linha por filme, com ; e aspas. */
export function csvDoPainel(ls: LinhaPainel[]): string {
  return csv(COLUNAS_PAINEL.map(([t]) => tr(t)), ls.map((l) => COLUNAS_PAINEL.map(([, k]) => {
    const v = l[k];
    return typeof v === "boolean" ? tr(v ? "Sim" : "Não") : (v as string | number);
  })));
}

function baixar(nome: string, texto: string): void {
  const url = URL.createObjectURL(new Blob(["﻿", texto], { type: "text/csv;charset=utf-8" }));
  const a = el("a", { href: url, download: nome });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ====================================================================== a tela
export async function telaImpressoes(abrirExame: (uid: string) => void): Promise<HTMLElement> {
  const raiz = el("div", { class: "impressoes" });
  let dados: Lista | null = null;
  const sel = new Set<string>();
  let atual = "";                         // o trabalho mostrado ao lado
  let folha = 0;
  let nFolhas = 0;
  let ordem: [keyof Linha, number] = ["ordem", -1];
  let urlFolha = "";
  let pedidoFolha = 0;

  const nota = el("div", { class: "imp-nota", "aria-live": "polite" });
  const dizer = (t: string, erro = false) => { nota.textContent = t; nota.classList.toggle("erro", erro); };

  // ---------------------------------------------------------------- abas
  const bLista = el("button", { type: "button", role: "tab", "aria-selected": "true" }, tr("Impressões"));
  const bPainel = el("button", { type: "button", role: "tab", "aria-selected": "false" }, tr("Painel"));
  const abaLista = el("div", { class: "imp-aba" });
  const abaPainel = el("div", { class: "imp-aba", hidden: "" });
  let painelMontado = false;
  const trocar = (painel: boolean) => {
    bLista.setAttribute("aria-selected", String(!painel));
    bPainel.setAttribute("aria-selected", String(painel));
    abaLista.hidden = painel;
    abaPainel.hidden = !painel;
    if (painel && !painelMontado) { painelMontado = true; abaPainel.append(montarPainel(abrirExame, (k) => { trocar(false); void mostrar(k, true); })); }
  };
  bLista.onclick = () => trocar(false);
  bPainel.onclick = () => trocar(true);

  // ---------------------------------------------------------------- barra
  const busca = el("input", { type: "search", placeholder: tr("Paciente, ID, origem ou rótulo"), "aria-label": tr("Filtrar as impressões") });
  const filtro = el("select", { "aria-label": tr("Mostrar") });
  const bAtualizar = botao("Atualizar", () => void carregar());
  const bEnviar = botao("Enviar para…", () => void enviar(), "primario");
  const bReimprimir = botao("Reimprimir…", () => void reimprimir());
  const bId = botao("Identificar paciente…", () => void identificar());
  const bJuntar = botao("Juntar como páginas", () => void juntar());
  const bAbrir = botao("Abrir o exame", () => { const r = linhaAtual(); if (r?.study_uid) abrirExame(r.study_uid); });
  const bApagar = botao("Apagar", () => void apagar());
  const bParados = botao("Parados…", () => void abrirParados());
  const faixa = el("div", { class: "imp-faixa", hidden: "" });
  const contagem = el("span", { class: "imp-contagem" });
  let espera: number | undefined;
  busca.oninput = () => { window.clearTimeout(espera); espera = window.setTimeout(() => void carregar(), 300); };
  filtro.onchange = () => void carregar();

  // ---------------------------------------------------------------- tabela e lado
  const corpoTabela = el("tbody");
  const marcarTodos = el("input", { type: "checkbox", "aria-label": tr("Escolher todos") });
  const cabecalho = el("tr", {}, el("th", { class: "imp-marca" }, marcarTodos));
  for (const [titulo, chave, num] of COLUNAS) {
    const th = el("th", { class: `ordena${num ? " num" : ""}` }, tr(titulo));
    th.onclick = () => { ordem = [chave, ordem[0] === chave ? -ordem[1] : (chave === "ordem" ? -1 : 1)]; desenhar(); };
    cabecalho.append(th);
  }
  marcarTodos.onchange = () => {
    sel.clear();
    if (marcarTodos.checked) for (const l of dados?.linhas ?? []) sel.add(l.k);
    desenhar();
  };
  const tabela = el("table", { class: "lista imp-tabela" }, el("thead", {}, cabecalho), corpoTabela);
  const previa = el("img", { class: "imp-previa", alt: tr("Folha do filme") });
  const semPrevia = el("div", { class: "imp-sem-previa" }, tr("Selecione um trabalho para ver a folha."));
  const rotuloFolha = el("span", { class: "imp-folha-n" });
  const bAnt = botao("◀", () => { if (folha > 0) { folha -= 1; void desenharFolha(); } });
  const bProx = botao("▶", () => { if (folha < nFolhas - 1) { folha += 1; void desenharFolha(); } });
  bAnt.setAttribute("aria-label", tr("Folha anterior"));
  bProx.setAttribute("aria-label", tr("Próxima folha"));
  const bAmpliar = botao("Ampliar", () => void ampliar());
  const detalhes = el("div", { class: "imp-detalhes" });
  const lado = el("aside", { class: "imp-lado" }, el("div", { class: "imp-quadro" }, previa, semPrevia),
    el("div", { class: "imp-folhas" }, bAnt, rotuloFolha, bProx, bAmpliar), detalhes);
  previa.hidden = true;

  const linhaAtual = (): Linha | undefined => dados?.linhas.find((l) => l.k === atual);
  const escolhidas = (): Linha[] => (dados?.linhas ?? []).filter((l) => sel.has(l.k));

  function botoes(): void {
    const ls = escolhidas();
    const um = ls.length === 1 ? ls[0] : undefined;
    bEnviar.disabled = !ls.length || !(dados?.destinos.length);
    bReimprimir.disabled = !ls.length;
    bApagar.disabled = !ls.length || !dados?.pode_apagar;
    bApagar.hidden = !dados?.pode_apagar;
    bJuntar.disabled = ls.filter((l) => l.kind === "scp").length < 2;
    bId.disabled = !(um && um.pode_identificar);
    bAbrir.disabled = !(um && um.study_uid);
    bParados.textContent = dados?.parados ? `${tr("Parados")} (${dados.parados})…` : tr("Parados…");
    contagem.textContent = dados ? `${dados.total} ${tr("de")} ${dados.de}${ls.length > 1 ? ` · ${ls.length} ${tr("escolhidos")}` : ""}` : "";
  }

  function desenhar(): void {
    if (!dados) return;
    const [chave, sentido] = ordem;
    const ls = [...dados.linhas].sort((a, b) => {
      const x = a[chave], y = b[chave];
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * sentido;
    });
    corpoTabela.replaceChildren();
    for (const l of ls) {
      const marca = el("input", { type: "checkbox", "aria-label": `${tr("Escolher")} ${l.paciente || l.rotulo}` });
      marca.checked = sel.has(l.k);
      marca.onclick = (e) => {
        e.stopPropagation();
        if (marca.checked) sel.add(l.k); else sel.delete(l.k);
        if (marca.checked) void mostrar(l.k, false);
        desenhar();
      };
      const nome = l.paciente || l.rotulo || tr("(sem identificação)");
      const linha = el("tr", { tabindex: "0", "data-k": l.k, class: `st-${l.status}${sel.has(l.k) ? " sel" : ""}` },
        el("td", { class: "imp-marca" }, marca), el("td", {}, l.tipo),
        el("td", { class: l.paciente ? "" : "imp-sem-nome", title: l.sem_nome ? tr("A impressão DICOM não manda nome nem ID; use “Identificar paciente”.") : "" }, nome),
        el("td", {}, l.id), el("td", {}, l.modalidade), el("td", {}, l.de_onde), el("td", {}, l.quando),
        el("td", { class: "num" }, String(l.folhas)), el("td", { class: "num" }, String(l.imagens)), el("td", {}, l.filme),
        el("td", { class: "sit" }, l.situacao), el("td", {}, l.destino));
      const escolher = (e: MouseEvent | KeyboardEvent) => {
        if (e.ctrlKey || e.metaKey) { if (sel.has(l.k)) sel.delete(l.k); else sel.add(l.k); } else { sel.clear(); sel.add(l.k); }
        void mostrar(l.k, false);
        desenhar();
      };
      linha.onclick = escolher;
      linha.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escolher(e); } };
      linha.ondblclick = () => { if (l.study_uid) abrirExame(l.study_uid); };
      corpoTabela.append(linha);
    }
    if (!ls.length) corpoTabela.append(el("tr", { class: "vazio" }, el("td", { colspan: String(COLUNAS.length + 1) }, tr("Nenhum trabalho na lista."))));
    cabecalho.querySelectorAll("th.ordena").forEach((th, i) => {
      if (COLUNAS[i][1] === chave) th.setAttribute("aria-sort", sentido > 0 ? "ascending" : "descending"); else th.removeAttribute("aria-sort");
    });
    marcarTodos.checked = ls.length > 0 && ls.every((l) => sel.has(l.k));
    faixa.hidden = !(dados.faixa.length || dados.aviso);
    faixa.textContent = [...dados.faixa, dados.aviso].filter(Boolean).join(" ");
    botoes();
  }

  async function desenharFolha(): Promise<void> {
    const k = atual;
    const meu = ++pedidoFolha;
    rotuloFolha.textContent = nFolhas ? `${tr("Folha")} ${folha + 1} ${tr("de")} ${nFolhas}` : "";
    bAnt.disabled = folha <= 0;
    bProx.disabled = folha >= nFolhas - 1;
    bAmpliar.disabled = !nFolhas;
    if (!k || !nFolhas) { previa.hidden = true; semPrevia.hidden = false; return; }
    try {
      const r = await pedir(caminho(`folha?k=${encodeURIComponent(k)}&i=${folha}`));
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      if (meu !== pedidoFolha) { URL.revokeObjectURL(url); return; }
      if (urlFolha) URL.revokeObjectURL(urlFolha);
      urlFolha = url;
      previa.src = url;
      previa.hidden = false;
      semPrevia.hidden = true;
    } catch {
      if (meu !== pedidoFolha) return;
      previa.hidden = true;
      semPrevia.hidden = false;
      semPrevia.textContent = tr("Não deu para desenhar esta folha.");
    }
  }

  async function ampliar(): Promise<void> {
    if (!atual || !nFolhas) return;
    try {
      const r = await pedir(caminho(`folha?k=${encodeURIComponent(atual)}&i=${folha}&grande=1`));
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      const d = janela(`${tr("Folha")} ${folha + 1} ${tr("de")} ${nFolhas}`, [el("img", { class: "imp-grande", src: url, alt: tr("Folha do filme") })],
        [botao("Fechar", () => d.close())], true);
      d.addEventListener("close", () => URL.revokeObjectURL(url));
    } catch (e) { dizer(`${tr("Não deu para desenhar esta folha.")} ${(e as Error).message}`, true); }
  }

  /** Mostra ao lado o trabalho `k` (folha, detalhes, envios). `marcar`: deixa só ele escolhido na lista. */
  async function mostrar(k: string, marcar: boolean): Promise<void> {
    if (marcar) { sel.clear(); sel.add(k); desenhar(); }
    const mudou = atual !== k;
    atual = k;
    if (mudou) folha = 0;
    if (!k) { nFolhas = 0; detalhes.replaceChildren(); semPrevia.textContent = tr("Selecione um trabalho para ver a folha."); void desenharFolha(); return; }
    try {
      const d = await pedirJson<Detalhes>(`detalhes?k=${encodeURIComponent(k)}`);
      if (atual !== k) return;
      nFolhas = d.folhas;
      folha = Math.max(0, Math.min(folha, nFolhas - 1));
      const partes: Node[] = [el("b", {}, d.titulo), ...d.linhas.filter(Boolean).map((t) => el("div", {}, t))];
      if (d.mensagem) partes.push(el("div", { class: "imp-msg" }, d.mensagem));
      if (d.envios.length) {
        const t = el("table", { class: "imp-envios" }, el("thead", {}, el("tr", {}, ...["Quando", "Destino", "Quem", "Como", "Modelo de folha", "Resultado"].map((h) => el("th", {}, tr(h))))));
        const tb = el("tbody");
        for (const e of d.envios) tb.append(el("tr", { class: e.ok ? "" : "falhou" }, ...[e.quando, e.destino, e.quem, e.como, e.modelo, e.resultado].map((v) => el("td", {}, v))));
        t.append(tb);
        partes.push(el("div", { class: "imp-envios-titulo" }, `${tr("Histórico de envios")} (${d.envios.length})`), t);
      } else partes.push(el("div", { class: "imp-envios-titulo vazio" }, tr("Ainda não foi enviado.")));
      detalhes.replaceChildren(...partes);
      if (!nFolhas) semPrevia.textContent = d.mensagem || tr("Não deu para desenhar esta folha.");
      void desenharFolha();
    } catch (e) {
      if (atual !== k) return;
      nFolhas = 0;
      detalhes.replaceChildren(el("div", { class: "imp-msg" }, (e as Error).message));
      void desenharFolha();
    }
  }

  async function carregar(manter = true): Promise<void> {
    try {
      const q = new URLSearchParams();
      if (filtro.value) q.set("tipo", filtro.value);
      if (busca.value.trim()) q.set("q", busca.value.trim());
      const r = await pedirJson<Lista>(`lista${q.toString() ? `?${q}` : ""}`);
      const primeira = !dados;
      dados = r;
      if (primeira) for (const f of r.filtros) filtro.append(el("option", { value: f.k }, f.nome));
      const vivos = new Set(r.linhas.map((l) => l.k));
      for (const k of [...sel]) if (!vivos.has(k)) sel.delete(k);
      if (!manter) sel.clear();
      desenhar();
      if (atual && !vivos.has(atual)) void mostrar("", false);
      else if (atual) void mostrar(atual, false);
    } catch (e) { dizer((e as Error).message, true); }
  }

  /** Roda uma ação do servidor com os botões travados e a resposta na linha de aviso. */
  async function agir(texto: string, fazer: () => Promise<{ mensagem?: string; falhas?: number }>): Promise<boolean> {
    dizer(tr(texto));
    raiz.classList.add("ocupado");
    try {
      const r = await fazer();
      dizer(r.mensagem || tr("Feito."), !!r.falhas);
      await carregar();
      return true;
    } catch (e) {
      dizer((e as Error).message, true);
      return false;
    } finally { raiz.classList.remove("ocupado"); }
  }

  // ---------------------------------------------------------------- enviar e reimprimir
  async function enviar(): Promise<void> {
    const ls = escolhidas();
    if (!ls.length || !dados) return;
    const destino = el("select", { "aria-label": tr("Destino") });
    for (const d of dados.destinos) destino.append(el("option", { value: d.nome }, d.rotulo));
    const lembrado = localStorage.getItem("ipe.web.impressoes.destino") || "";
    if (dados.destinos.some((d) => d.nome === lembrado)) destino.value = lembrado;
    const modelo = el("select", { "aria-label": tr("Modelo de folha") }, el("option", { value: "" }, tr("A folha como veio")));
    for (const m of dados.modelos) modelo.append(el("option", { value: m }, m));
    const bOk = botao("Enviar", () => {
      const alvo = destino.value, mod = modelo.value;
      try { localStorage.setItem("ipe.web.impressoes.destino", alvo); } catch { /* sem armazenamento */ }
      d.close();
      void agir("Enviando…", () => pedirJson("enviar", { ks: ls.map((l) => l.k), destino: alvo, modelo: mod }));
    }, "primario");
    const d = janela(tr("Enviar impressão"), [
      el("p", {}, `${tr("Enviar")} ${ls.length} ${tr("trabalho(s) para:")}`),
      el("label", { class: "imp-campo" }, el("span", {}, tr("Destino")), destino),
      el("label", { class: "imp-campo" }, el("span", {}, tr("Modelo de folha")), modelo),
      el("p", { class: "dica" }, tr("Os destinos são os cadastrados no servidor (Configurações de impressão ▸ Destinos, no Ipê de mesa)."))],
    [botao("Cancelar", () => d.close()), bOk]);
  }

  async function reimprimir(): Promise<void> {
    const ks = escolhidas().map((l) => l.k);
    if (!ks.length) return;
    try {
      const p = await pedirJson<{ plano: string; n: number; aviso?: string; mensagem?: string }>("reimprimir", { ks });
      if (!p.n) { dizer(p.mensagem || "", true); return; }
      if (await confirmar(tr("Reimprimir"), p.plano, p.aviso || "", "Reimprimir")) {
        await agir("Enviando…", () => pedirJson("reimprimir", { ks, confirmar: true }));
      }
    } catch (e) { dizer((e as Error).message, true); }
  }

  // ---------------------------------------------------------------- identificar o paciente (com o OCR)
  async function identificar(): Promise<void> {
    const r = escolhidas()[0];
    if (!r) return;
    let a: { nome: string; id: string; candidatos: Candidato[]; ocr: boolean; motivo: string };
    try { a = await pedirJson("identificar_abrir", { k: r.k }); } catch (e) { dizer((e as Error).message, true); return; }
    const nome = el("input", { type: "text", value: a.nome, "aria-label": tr("Nome") });
    const ident = el("input", { type: "text", value: a.id, "aria-label": tr("ID") });
    let escolhido = "";
    let candidatos = a.candidatos;
    const rotLista = el("div", { class: "dica" });
    const lista = el("div", { class: "imp-candidatos", role: "listbox", "aria-label": tr("Exames que combinam") });
    const lido = el("pre", { class: "imp-lido", hidden: "" });
    const rotLido = el("div", { class: "dica", hidden: "" }, tr("Texto lido no cabeçalho:"));
    const aviso = el("div", { class: "imp-aviso", hidden: "" });
    const usar = (c: Candidato, b: HTMLElement) => {
      nome.value = c.nome; ident.value = c.id; escolhido = c.study_uid;
      lista.querySelectorAll("[aria-selected=true]").forEach((x) => x.setAttribute("aria-selected", "false"));
      b.setAttribute("aria-selected", "true");
    };
    const encher = (primeiro = false) => {
      lista.replaceChildren();
      candidatos.forEach((c, i) => {
        const b = el("button", { type: "button", role: "option", "aria-selected": "false" }, c.texto);
        b.onclick = () => usar(c, b);
        lista.append(b);
        if (primeiro && i === 0) usar(c, b);
      });
      lista.hidden = rotLista.hidden = !candidatos.length;
      rotLista.textContent = candidatos.some((c) => c.ocr)
        ? tr("Pacientes do banco que combinam com o cabeçalho, e exames do mesmo aparelho e horário (clique para usar):")
        : tr("Exames do banco do mesmo aparelho e horário (clique para usar):");
    };
    nome.oninput = ident.oninput = () => { escolhido = ""; };
    const bOcr = botao("Ler o cabeçalho da folha (OCR)", async () => {
      bOcr.disabled = true;
      bOcr.textContent = tr("Lendo o cabeçalho…");
      try {
        const o = await pedirJson<{ texto: string; candidatos: Candidato[]; nome: string; id: string; certo: boolean; mensagem: string }>("ocr", { k: r.k });
        lido.textContent = o.texto || tr("(nada)");
        lido.hidden = rotLido.hidden = false;
        aviso.hidden = !o.mensagem;
        aviso.textContent = o.mensagem;
        if (o.candidatos.length) {
          const ja = new Set(o.candidatos.map((c) => c.study_uid));
          candidatos = [...o.candidatos, ...candidatos.filter((c) => !ja.has(c.study_uid))];
          encher(o.certo);
          if (o.certo) return;
        }
        if (o.nome) nome.value = o.nome;
        if (o.id) ident.value = o.id;
      } catch (e) {
        aviso.hidden = false;
        aviso.textContent = `${tr("Não deu para ler")}: ${(e as Error).message}`;
      } finally {
        bOcr.disabled = !a.ocr;
        bOcr.textContent = tr("Ler o cabeçalho da folha (OCR)");
      }
    });
    bOcr.disabled = !a.ocr;
    bOcr.title = a.ocr ? tr("Lê o texto gravado no alto da primeira folha e procura o paciente no banco. É sugestão: confira antes de confirmar.") : a.motivo;
    const bOk = botao("Confirmar", () => {
      const corpo = { k: r.k, nome: nome.value.trim(), id: ident.value.trim(), study_uid: escolhido };
      if (!corpo.nome && !corpo.id) { aviso.hidden = false; aviso.textContent = tr("Escreva o nome ou o ID do paciente."); return; }
      d.close();
      void agir("Gravando…", () => pedirJson("identificar", corpo));
    }, "primario");
    encher();
    const d = janela(tr("Identificar o paciente"), [
      el("p", { class: "dica" }, tr("A impressão DICOM não traz nome nem ID — o que aparece aqui veio do rótulo da sessão, quando a modalidade escreve algo nele.")),
      el("label", { class: "imp-campo" }, el("span", {}, tr("Nome")), nome),
      el("label", { class: "imp-campo" }, el("span", {}, tr("ID")), ident),
      rotLista, lista, bOcr, rotLido, lido, aviso],
    [botao("Cancelar", () => d.close()), bOk], true);
  }

  // ---------------------------------------------------------------- juntar, apagar, parados
  async function juntar(): Promise<void> {
    const ks = escolhidas().filter((l) => l.kind === "scp").map((l) => l.k);
    if (ks.length < 2) return;
    try {
      const p = await pedirJson<{ plano: string; aviso: string }>("juntar", { ks });
      if (await confirmar(tr("Juntar como páginas"), p.plano, p.aviso, "Juntar")) {
        await agir("Juntando…", async () => {
          const r = await pedirJson<{ mensagem: string; k: string }>("juntar", { ks, confirmar: true });
          sel.clear(); sel.add(r.k); atual = r.k; folha = 0;
          return r;
        });
      }
    } catch (e) { dizer((e as Error).message, true); }
  }

  async function apagar(): Promise<void> {
    const ls = escolhidas();
    const n = ls.filter((l) => l.kind !== "aw").length;
    if (!n) { dizer(tr("O filme que veio no exame não se apaga daqui: ele é do exame."), true); return; }
    if (await confirmar(tr("Apagar"), `${tr("Apagar")} ${n} ${tr("trabalho(s) da lista?")}`,
      tr("Os exames já guardados no banco não são apagados. Não dá para desfazer."), "Apagar")) {
      await agir("Apagando…", () => pedirJson("apagar", { ks: ls.map((l) => l.k) }));
    }
  }

  async function abrirParados(): Promise<void> {
    let p: { grupos: Grupo[]; resumo: string; prontos: number };
    try { p = await pedirJson("parados"); } catch (e) { dizer((e as Error).message, true); return; }
    const liberar = (id: string) => { d.close(); void agir("Enviando…", () => pedirJson("liberar", { id })); };
    const tb = el("tbody");
    for (const g of p.grupos) {
      const b = botao("Liberar", () => liberar(g.id));
      b.disabled = !g.pode_liberar;
      tb.append(el("tr", {}, el("td", {}, g.nome), el("td", {}, `${g.simbolo} ${g.motivo}`), el("td", { class: "num" }, String(g.trabalhos)),
        el("td", { class: "num" }, String(g.folhas)), el("td", {}, g.desde), el("td", {}, b)));
    }
    if (!p.grupos.length) tb.append(el("tr", {}, el("td", { colspan: "6" }, tr("Nenhum trabalho parado."))));
    const bTodos = botao("Liberar todos os prontos", () => liberar(""), "primario");
    bTodos.disabled = !p.prontos;
    const d = janela(tr("Parados"), [
      el("p", {}, p.resumo || tr("Nenhum trabalho parado.")),
      el("table", { class: "lista imp-parados" }, el("thead", {}, el("tr", {}, ...["Aparelho", "Situação", "Trabalhos", "Folhas", "Desde", ""].map((h) => el("th", {}, h ? tr(h) : "")))), tb),
      el("p", { class: "dica" }, tr("Liberar manda cada trabalho pela regra dele. Cadastrar a origem e as regras é no Ipê de mesa (Configurações de impressão)."))],
    [botao("Fechar", () => d.close()), bTodos], true);
  }

  // ---------------------------------------------------------------- montar
  abaLista.append(
    el("div", { class: "imp-barra" }, busca, filtro, bAtualizar, contagem),
    el("div", { class: "imp-barra" }, bEnviar, bReimprimir, bId, bJuntar, bAbrir, bApagar, bParados),
    faixa, nota,
    el("div", { class: "imp-corpo" }, el("div", { class: "imp-rolagem" }, tabela), lado));
  raiz.append(el("div", { class: "gestao-abas imp-abas", role: "tablist" }, bLista, bPainel), abaLista, abaPainel);
  await carregar();
  const relogio = window.setInterval(() => {
    if (!raiz.isConnected) { window.clearInterval(relogio); if (urlFolha) URL.revokeObjectURL(urlFolha); return; }
    if (!abaLista.hidden && !document.querySelector("dialog.imp-janela") && document.visibilityState === "visible"
      && !raiz.classList.contains("ocupado")) void carregar();
  }, 20000);
  (window as unknown as { __ipeImpressoes: unknown }).__ipeImpressoes = {
    estado: () => ({ linhas: dados?.linhas ?? [], sel: [...sel], atual, folha, nFolhas, parados: dados?.parados ?? 0 }),
    recarregar: () => carregar(), mostrar: (k: string) => mostrar(k, true),
  };
  return raiz;
}

// ====================================================================== o painel
function montarPainel(abrirExame: (uid: string) => void, verNaLista: (k: string) => void): HTMLElement {
  const raiz = el("div", { class: "imp-painel" });
  let dados: Painel | null = null;
  const periodo = el("select", { "aria-label": tr("Período") });
  const de = el("input", { type: "date", "aria-label": tr("De") });
  const ate = el("input", { type: "date", "aria-label": tr("Até") });
  const mod = el("select", { "aria-label": tr("Modalidade") });
  const usuario = el("select", { "aria-label": tr("Criado por") });
  const tipo = el("select", { "aria-label": tr("Origem") }, el("option", { value: "" }, tr("Todas as origens")),
    el("option", { value: "filme" }, tr("Compositor")), el("option", { value: "dicom" }, tr("Impressão DICOM")));
  const dias = el("input", { type: "number", min: "0", max: "365", value: localStorage.getItem("ipe.web.impressoes.dias") || "2", "aria-label": tr("Dias sem imprimir") });
  const soNao = el("input", { type: "checkbox" });
  const nota = el("div", { class: "imp-nota", "aria-live": "polite" });
  const cartoes = el("div", { class: "imp-cartoes" });
  const meses = el("div", { class: "imp-meses", role: "img" });
  const tMod = el("div"), tUser = el("div");
  const corpo = el("tbody");
  const rotLista = el("span", { class: "imp-contagem" });
  let ordem: [keyof LinhaPainel, number] = ["ordem", -1];
  const bCsv = botao("Exportar CSV", () => { if (dados) baixar("painel-de-filmes.csv", csvDoPainel(dados.linhas)); });

  const cartao = (rotulo: string, valor: string, detalhe: string, dica = "", alerta = false): HTMLElement =>
    el("div", { class: `imp-cartao${alerta ? " alerta" : ""}`, title: dica }, el("div", { class: "rot" }, tr(rotulo)),
      el("div", { class: "val" }, valor), el("div", { class: "det" }, detalhe));
  const tempo = (t: Tempo): [string, string] => [t.mediana,
    (t.n ? `p90 ${t.p90} · ${t.n} ${tr("filme(s)")}` : tr("sem dado")) + (t.negativos ? ` · ${t.negativos} ${tr("com hora errada, fora da conta")}` : "")];

  function tabelaGrupo(primeira: string, gs: GrupoPainel[]): HTMLElement {
    const t = el("table", { class: "lista imp-grupo" }, el("thead", {}, el("tr", {}, ...[primeira, "Filmes", "Impressos", "% impressos", "Exame → filme",
      "Filme → impressão", "Folhas impressas", "Reimpressões"].map((h, i) => el("th", { class: i ? "num" : "" }, tr(h))))));
    const tb = el("tbody");
    for (const g of gs) tb.append(el("tr", {}, el("td", {}, g.nome), ...[g.filmes, g.impressos, g.pct, g.exame_filme, g.filme_impressao, g.folhas_impressas, g.reimpressoes]
      .map((v) => el("td", { class: "num" }, String(v)))));
    t.append(tb);
    return t;
  }

  function linhas(): void {
    if (!dados) return;
    const [chave, sentido] = ordem;
    const cmp = chave === "criado" ? "ordem" : chave;
    const ls = [...dados.linhas].sort((a, b) => {
      const x = a[cmp], y = b[cmp];
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * sentido;
    });
    corpo.replaceChildren();
    for (const l of ls) {
      const tr_ = el("tr", { tabindex: "0", class: l.impresso ? "" : "nao-impresso" }, ...COLUNAS_PAINEL.map(([, k]) => {
        const v = l[k];
        return el("td", { class: typeof v === "number" ? "num" : (k === "impresso" ? "imp-sim-nao" : "") }, typeof v === "boolean" ? tr(v ? "Sim" : "Não") : String(v || ""));
      }));
      tr_.ondblclick = () => { if (l.tipo === "dicom" && l.study_uid) abrirExame(l.study_uid); else verNaLista(l.k); };
      tr_.title = tr("Duplo clique: ver na lista de impressões");
      corpo.append(tr_);
    }
    if (!ls.length) corpo.append(el("tr", {}, el("td", { colspan: String(COLUNAS_PAINEL.length) }, tr("Nenhum filme no período."))));
    rotLista.textContent = `${dados.total} ${tr("de")} ${dados.no_periodo} ${tr("no período")}`;
    bCsv.disabled = !ls.length;
  }

  function desenhar(): void {
    if (!dados) return;
    const c = dados.cartoes;
    const [efV, efD] = tempo(c.exame_filme), [fiV, fiD] = tempo(c.filme_impressao), [eiV, eiD] = tempo(c.exame_impressao);
    cartoes.replaceChildren(
      cartao("Filmes", String(c.filmes), (c.dicom ? `${tr("Compositor")}: ${c.compositor} · ${tr("impressão DICOM")}: ${c.dicom} · ` : "") + `${c.folhas} ${tr("folha(s)")}, ${c.imagens} ${tr("imagem(ns)")}`),
      cartao("Impressos", c.pct, `${c.impressos} ${tr("de")} ${c.filmes} ${tr("filme(s)")}` + (c.reimpressos ? ` · ${c.reimpressos} ${tr("reimpresso(s)")}` : "")),
      cartao("Parados", String(c.parados), `${tr("há mais de")} ${c.dias} ${tr("dia(s)")} · ${c.nao_impressos} ${tr("não impresso(s) no total")}`, c.parados_lista.join("\n"), c.parados > 0),
      cartao("Exame → filme", efV, efD, tr("Mediana; o percentil 90 diz quanto demoram os 10% mais lentos.")),
      cartao("Filme → impressão", fiV, fiD, tr("Mediana; o percentil 90 diz quanto demoram os 10% mais lentos.")),
      cartao("Exame → impressão", eiV, eiD + (c.em_24h ? ` · ${c.em_24h} ${tr("em até 24 h")}` : ""), tr("Mediana; o percentil 90 diz quanto demoram os 10% mais lentos.")),
      cartao("Folhas impressas", String(c.folhas_impressas), `${c.impressoes} ${tr("impressão(ões)")}`, c.destinos.map((d) => `${d.nome}: ${d.n}`).join("; ")));
    const maior = Math.max(1, ...dados.por_mes.map((m) => m.impressos + m.nao));
    meses.replaceChildren(...dados.por_mes.map((m) => el("div", { class: "mes", title: `${m.mes}: ${m.impressos} ${tr("impressos")}, ${m.nao} ${tr("não impressos")}` },
      el("div", { class: "barras" }, el("i", { class: "nao", style: `height:${(100 * m.nao) / maior}%` }), el("i", { class: "sim", style: `height:${(100 * m.impressos) / maior}%` })),
      el("span", {}, `${m.mes.slice(5)}/${m.mes.slice(2, 4)}`), el("b", {}, String(m.impressos + m.nao)))));
    meses.setAttribute("aria-label", `${tr("Filmes por mês")}: ${dados.por_mes.map((m) => `${m.mes} ${m.impressos + m.nao}`).join(", ")}`);
    tMod.replaceChildren(tabelaGrupo("Modalidade", dados.por_modalidade));
    tUser.replaceChildren(tabelaGrupo("Criado por", dados.por_usuario));
    linhas();
  }

  async function carregar(): Promise<void> {
    const q = new URLSearchParams({ periodo: periodo.value || "30d", dias: dias.value || "2" });
    if (periodo.value === "datas") { q.set("de", de.value); q.set("ate", ate.value); }
    if (mod.value) q.set("mod", mod.value);
    if (usuario.value) q.set("user", usuario.value);
    if (tipo.value) q.set("tipo", tipo.value);
    if (soNao.checked) q.set("so_nao", "1");
    try { localStorage.setItem("ipe.web.impressoes.dias", dias.value); } catch { /* sem armazenamento */ }
    try {
      const r = await pedirJson<Painel>(`painel?${q}`);
      const primeira = !dados;
      dados = r;
      if (primeira) for (const p of r.periodos) periodo.append(el("option", { value: p.k }, p.nome));
      for (const [s, valores, todos] of [[mod, r.modalidades, "Todas as modalidades"], [usuario, r.usuarios, "Todos"]] as [HTMLSelectElement, string[], string][]) {
        const antes = s.value;
        s.replaceChildren(el("option", { value: "" }, tr(todos)), ...valores.map((v) => el("option", { value: v }, v)));
        s.value = valores.includes(antes) ? antes : "";
      }
      if (periodo.value !== "datas") { de.value = r.de; ate.value = r.ate; }
      de.disabled = ate.disabled = periodo.value !== "datas";
      nota.textContent = "";
      desenhar();
    } catch (e) { nota.textContent = (e as Error).message; nota.classList.add("erro"); }
  }
  for (const w of [periodo, de, ate, mod, usuario, tipo, dias, soNao]) w.onchange = () => void carregar();
  const cab = el("tr");
  for (const [titulo, chave] of COLUNAS_PAINEL) {
    const th = el("th", { class: "ordena" }, tr(titulo));
    th.onclick = () => { ordem = [chave, ordem[0] === chave ? -ordem[1] : 1]; linhas(); };
    cab.append(th);
  }
  raiz.append(
    el("div", { class: "imp-barra" }, el("label", {}, `${tr("Período")} `, periodo), de, ate, mod, usuario, tipo,
      el("label", {}, `${tr("Parado há mais de")} `, dias, ` ${tr("dia(s)")}`), botao("Atualizar", () => void carregar())),
    nota, cartoes,
    el("div", { class: "imp-graficos" }, el("section", {}, el("h4", {}, tr("Filmes por mês")),
      el("div", { class: "imp-legenda" }, el("i", { class: "sim" }), tr("impressos"), el("i", { class: "nao" }), tr("não impressos")), meses),
    el("section", {}, el("h4", {}, tr("Por modalidade")), tMod), el("section", {}, el("h4", {}, tr("Por quem criou")), tUser)),
    el("div", { class: "imp-barra" }, el("label", {}, soNao, ` ${tr("Só os não impressos")}`), rotLista, bCsv),
    el("div", { class: "imp-rolagem" }, el("table", { class: "lista imp-filmes" }, el("thead", {}, cab), corpo)));
  void carregar();
  (window as unknown as { __ipePainelFilmes: unknown }).__ipePainelFilmes = { estado: () => dados, csv: () => (dados ? csvDoPainel(dados.linhas) : "") };
  return raiz;
}
