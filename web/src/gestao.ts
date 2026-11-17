// 0.100.63: a Gestão DICOM no Ipê Web — os exames das modalidades estão no PACS? Inteiros? Se não, mandar.
// É a janela de Gestão do Ipê de mesa, atendida pelo servidor: quem fala com as modalidades e com o PACS é o
// servidor; a conferência e o envio seguem com esta aba fechada. Só administradores. Os nós são todos os do
// servidor (aqui não vale o "compartilhar com os clientes").
import { pedir } from "./api";
import { getLang, tr } from "./i18n";
import { type ItemMenu, abrirMenu } from "./menu";

interface Ident { id: number; nome: string; ae: string }
interface No { id: number; nome: string; ae: string; host: string; porta: number; identidades: Ident[] }
interface Destino { id: number; nome: string; identidades: Ident[] }
interface Cfg {
  fontes?: Record<string, { on?: boolean; ident?: number | null }>; pacs?: number | null; pacs_ident?: number | null;
  destino?: string; modo?: string; periodo?: string; ignorar?: string; exato?: boolean; so_problemas?: boolean;
}
interface Nos {
  nos: No[]; dicomweb: string[]; destinos: Destino[]; local_ae: string; cfg: Cfg;
  modos: { k: string; nome: string }[]; periodos: { k: string; nome: string }[];
}
interface Serie { numero: number; descricao: string; modalidade: string; origem: number | null; pacs: number | null; situacao: string; texto: string; faltam: number | null }
export interface Linha {
  k: string; fonte: string; situacao: string; texto: string; problema: boolean; detalhe: string; envio: string;
  data: string; hora: string; paciente: string; id: string; accession: string; descricao: string;
  series_txt: string; imagens_txt: string; series: Serie[];
}
interface ItemFila { lote: number; k: string; estado: string; paciente: string; accession: string; destino: string; modo: string; hora: string; resultado: string }
interface Estado {
  v: number; igual?: boolean; ocupado: string; mensagem: string; feitos: number; total: number; linhas: Linha[];
  resumo: string; erros: string; fila: ItemFila[]; pacs: string; quem: string; quando: string; periodo: string[];
}

const SIMBOLO: Record<string, string> = { erro: "⚠", ausente: "✖", outro_uid: "≠", incompleto: "◐", sem_contagem: "?", completo: "✔" };
const FILA: Record<string, [string, string]> = {
  fila: ["⏳", "Na fila"], enviando: ["➜", "Enviando"], ok: ["✔", "Enviado"], nada: ["✔", "Nada a enviar"],
  falhou: ["⚠", "Falhou"], parado: ["■", "Não foi"],
};
const COLUNAS: [string, keyof Linha | ""][] = [["Situação", "situacao"], ["Origem", "fonte"], ["Data", "data"], ["Paciente", "paciente"],
  ["ID", "id"], ["Accession", "accession"], ["Descrição", "descricao"], ["Séries (origem / PACS)", "series_txt"],
  ["Imagens (origem / PACS)", "imagens_txt"], ["Detalhe", "detalhe"], ["Envio", "envio"]];
const ORDEM_SIT = ["erro", "ausente", "outro_uid", "incompleto", "sem_contagem", "completo"];

async function pedirJson<T>(caminho: string, corpo?: unknown): Promise<T> {
  // 0.100.66: o servidor responde no idioma desta página (andamento, resumos, relatórios)
  const idioma = getLang();
  if (idioma !== "pt") caminho += `${caminho.includes("?") ? "&" : "?"}lang=${idioma}`;
  const r = await pedir(`${location.origin}${caminho}`, {
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

function dataBr(d: string): string {
  return d && d.length === 8 ? `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}` : d;
}

function horaBr(h: string): string {
  return h && h.length >= 4 ? `${h.slice(0, 2)}:${h.slice(2, 4)}` : "";
}

/** O texto do CSV (para exportar e para os testes): cabeçalho + uma linha por exame, com ; e aspas. */
export function csvDaGestao(linhas: Linha[]): string {
  const q = (v: string) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const cab = COLUNAS.map(([t]) => q(tr(t))).join(";");
  return [cab, ...linhas.map((l) => [l.texto, l.fonte, dataBr(l.data), l.paciente, l.id, l.accession, l.descricao,
    l.series_txt, l.imagens_txt, l.detalhe, l.envio].map(q).join(";"))].join("\r\n");
}

/** A tela da Gestão DICOM. Devolve o elemento; a atualização para sozinha quando ele sai da página. */
export async function telaGestao(): Promise<HTMLElement> {
  const raiz = el("div", { class: "tela-gestao" });
  let dados: Nos;
  try {
    dados = await pedirJson<Nos>("/api/web/gestao/nos");
  } catch (e) {
    raiz.append(el("div", { class: "erro", role: "alert" }, `${tr("Gestão DICOM")}: ${tr((e as Error).message)}`));
    return raiz;
  }
  const cfg = dados.cfg || {};
  const aviso = el("div", { class: "estado", role: "status" });

  // ---------------------------------------------------------------- as modalidades e o PACS
  const identidades = (no: { identidades: Ident[] } | undefined, atual?: number | null): HTMLSelectElement => {
    const s = el("select", { "aria-label": tr("Falar como") },
      el("option", { value: "" }, `${tr("Este servidor")} (${dados.local_ae})`),
      ...(no?.identidades || []).map((i) => el("option", { value: String(i.id) }, `${i.nome} (${i.ae})`)));
    if (atual && [...s.options].some((o) => o.value === String(atual))) s.value = String(atual);
    return s;
  };
  const botaoEco = (pegar: () => { no: number; ident: number | null } | null): [HTMLButtonElement, HTMLElement] => {
    const saida = el("span", { class: "eco" });
    const b = el("button", { type: "button", class: "link", title: tr("O nó responde a este servidor, com esta identidade? (C-ECHO)") }, tr("Testar"));
    b.onclick = async () => {
      const alvo = pegar();
      if (!alvo) return;
      saida.className = "eco";
      saida.textContent = "…";
      try {
        const r = await pedirJson<{ ok: boolean; mensagem: string; ms: number }>("/api/web/gestao/eco", alvo);
        saida.classList.add(r.ok ? "ok" : "ruim");
        saida.textContent = r.ok ? `✔ ${tr("responde")} (${r.ms} ms)` : `✖ ${r.mensagem}`;
      } catch (e) {
        saida.classList.add("ruim");
        saida.textContent = `✖ ${(e as Error).message}`;
      }
    };
    return [b, saida];
  };
  interface LinhaFonte { no: No; caixa: HTMLInputElement; ident: HTMLSelectElement }
  const fontes: LinhaFonte[] = dados.nos.map((no) => {
    const mem = cfg.fontes?.[String(no.id)] || {};
    const caixa = el("input", { type: "checkbox", "aria-label": no.nome });
    caixa.checked = !!mem.on;
    return { no, caixa, ident: identidades(no, mem.ident) };
  });
  const tFontes = el("table", { class: "lista gestao-fontes" },
    el("thead", {}, el("tr", {}, ...["", "Modalidade", "AE Title", "Falar como", ""].map((t) => el("th", {}, t ? tr(t) : "")))),
    el("tbody", {}, ...fontes.map((f) => {
      const [b, saida] = botaoEco(() => ({ no: f.no.id, ident: Number(f.ident.value) || null }));
      return el("tr", { "data-no": String(f.no.id) }, el("td", {}, f.caixa), el("td", {}, f.no.nome),
        el("td", {}, `${f.no.ae}@${f.no.host}`), el("td", {}, f.ident), el("td", {}, b, " ", saida));
    })));
  const bTodas = el("button", { type: "button", class: "link" }, tr("Marcar todas"));
  const bNenhuma = el("button", { type: "button", class: "link" }, tr("Nenhuma"));
  bTodas.onclick = () => { for (const f of fontes) f.caixa.checked = true; };
  bNenhuma.onclick = () => { for (const f of fontes) f.caixa.checked = false; };

  const sPacs = el("select", { "aria-label": tr("PACS") }, ...dados.nos.map((n) => el("option", { value: String(n.id) }, `${n.nome}  (${n.ae}@${n.host})`)));
  const palpite = cfg.pacs ?? dados.nos.find((n) => /PACS/i.test(n.nome) || /PACS/i.test(n.ae))?.id ?? dados.nos[0]?.id;
  if (palpite != null) sPacs.value = String(palpite);
  const caixaPacsIdent = el("span", {});
  let sPacsIdent = identidades(undefined);
  const eDestino = el("input", { "aria-label": tr("Destino do C-MOVE"), placeholder: "" });
  eDestino.value = cfg.destino || "";
  const pacsMudou = (ident?: number | null) => {
    const no = dados.nos.find((n) => String(n.id) === sPacs.value);
    sPacsIdent = identidades(no, ident === undefined ? Number(sPacsIdent.value) || null : ident);
    sPacsIdent.setAttribute("aria-label", tr("Falar com o PACS como"));
    caixaPacsIdent.replaceChildren(sPacsIdent);
    eDestino.placeholder = no?.ae || "";
  };
  sPacs.onchange = () => pacsMudou();
  pacsMudou(cfg.pacs_ident);
  const [bEcoPacs, ecoPacs] = botaoEco(() => (sPacs.value ? { no: Number(sPacs.value), ident: Number(sPacsIdent.value) || null } : null));

  const sModo = el("select", { "aria-label": tr("Como enviar") }, ...dados.modos.map((m) => el("option", { value: m.k }, tr(m.nome))));
  sModo.value = cfg.modo && dados.modos.some((m) => m.k === cfg.modo) ? cfg.modo : "auto";
  const sPeriodo = el("select", { "aria-label": tr("Período") }, ...dados.periodos.map((p) => el("option", { value: p.k }, tr(p.nome))));
  sPeriodo.value = cfg.periodo && dados.periodos.some((p) => p.k === cfg.periodo) ? cfg.periodo : "hoje";
  const hoje = new Date().toISOString().slice(0, 10);
  const dDe = el("input", { type: "date", title: tr("De"), value: hoje });
  const dAte = el("input", { type: "date", title: tr("Até"), value: hoje });
  const periodoMudou = () => { dDe.hidden = dAte.hidden = sPeriodo.value !== "datas"; };
  sPeriodo.onchange = periodoMudou;
  periodoMudou();
  const eIgnorar = el("input", { "aria-label": tr("Ignorar séries"), placeholder: tr("ex.: Patient Protocol; ScreenCap"),
    title: tr("Séries que a modalidade guarda e não manda ao PACS de propósito (parte da descrição; separe com ;)") });
  eIgnorar.value = cfg.ignorar || "";
  const kExato = el("input", { type: "checkbox", id: "gestao-exato" });
  kExato.checked = !!cfg.exato;
  const campo = (rotulo: string, ...c: Node[]) => el("label", { class: "campo" }, el("span", {}, tr(rotulo)), ...c);

  const bConferir = el("button", { type: "button", class: "primario" }, tr("Conferir"));
  const bParar = el("button", { type: "button" }, tr("Parar"));
  const barra = el("progress", { max: "100", value: "0" });
  const mensagem = el("span", { class: "mensagem" });
  const quadroCfg = el("div", { class: "gestao-cfg" },
    el("section", {}, el("h3", {}, tr("Modalidades")), tFontes, el("div", { class: "acoes" }, bTodas, bNenhuma),
      dados.dicomweb.length ? el("div", { class: "dica" }, `${tr("Nós DICOMweb não entram aqui")} (${dados.dicomweb.join(", ")}): ${tr("a conferência e o envio direto usam C-FIND e C-MOVE, que são DIMSE.")}`) : ""),
    el("section", {}, el("h3", {}, tr("PACS e conferência")),
      campo("PACS", sPacs, caixaPacsIdent, bEcoPacs, ecoPacs), campo("Destino do C-MOVE", eDestino), campo("Como enviar", sModo),
      campo("Período", sPeriodo, dDe, dAte), campo("Ignorar séries", eIgnorar),
      el("label", { class: "campo", for: "gestao-exato" }, el("span", {}, ""), kExato, tr("Conferir imagem por imagem (mais lento; diz quais imagens faltam)")),
      el("div", { class: "acoes" }, bConferir, bParar, barra, mensagem)));
  if (!dados.nos.length) {
    quadroCfg.prepend(el("div", { class: "dica" }, tr("Nenhum nó DICOM cadastrado no servidor. Cadastre as modalidades e o PACS em Configurações ▸ Nós DICOM, no servidor.")));
  }

  // ---------------------------------------------------------------- o resultado
  const resumo = el("div", { class: "gestao-resumo" });
  const sMostrar = el("select", { "aria-label": tr("Mostrar") }, el("option", { value: "" }, tr("Todos os exames")), el("option", { value: "1" }, tr("Só os com problema")));
  sMostrar.value = cfg.so_problemas ? "1" : "";
  const eBusca = el("input", { type: "search", placeholder: tr("Filtrar (paciente, accession, descrição)"), "aria-label": tr("Filtrar") });
  const kTodos = el("input", { type: "checkbox", "aria-label": tr("Marcar todos os que aparecem") });
  const corpo = el("tbody");
  let ordenar: keyof Linha = "situacao";
  let inverso = false;
  const cabecalhos = COLUNAS.map(([t, campoOrdem]) => {
    const th = el("th", { scope: "col" }, tr(t));
    if (campoOrdem) {
      th.classList.add("ordena");
      th.onclick = () => {
        inverso = ordenar === campoOrdem ? !inverso : false;
        ordenar = campoOrdem;
        desenhar();
      };
    }
    return th;
  });
  const tabela = el("table", { class: "lista gestao-exames" }, el("thead", {}, el("tr", {}, el("th", {}, kTodos), ...cabecalhos)), corpo);
  const erros = el("pre", { class: "gestao-erros", hidden: "" });
  const bFalta = el("button", { type: "button" }, tr("Enviar o que falta"));
  const bInteiro = el("button", { type: "button" }, tr("Enviar o exame inteiro"));
  const bFaltaPara = el("button", { type: "button" }, `${tr("Enviar o que falta para")} ▾`);
  const bInteiroPara = el("button", { type: "button" }, `${tr("Enviar o exame inteiro para")} ▾`);
  const bReconferir = el("button", { type: "button" }, tr("Conferir de novo"));
  const bProblemas = el("button", { type: "button", class: "link" }, tr("Marcar os com problema"));
  const bCsv = el("button", { type: "button", class: "link" }, tr("Exportar CSV"));
  const acoes = el("div", { class: "acoes gestao-acoes" }, bFalta, bInteiro, bFaltaPara, bInteiroPara, bReconferir, bProblemas, bCsv);
  const corpoFila = el("tbody");
  const resumoFila = el("span", { class: "mensagem" });
  const bLimpar = el("button", { type: "button", class: "link" }, tr("Limpar os terminados"));
  const quadroFila = el("section", { class: "gestao-fila", hidden: "" }, el("h3", {}, tr("Fila de envio"), " ", resumoFila, " ", bLimpar),
    el("table", { class: "lista" }, el("thead", {}, el("tr", {}, ...["Situação", "Paciente", "Accession", "Destino", "Modo", "Hora", "Resultado"].map((t) => el("th", {}, tr(t))))), corpoFila));

  let estado: Estado | null = null;
  const marcadas = new Set<string>();
  const abertas = new Set<string>();

  const visiveis = (): Linha[] => {
    if (!estado) return [];
    const texto = eBusca.value.trim().toLowerCase();
    let ls = estado.linhas.filter((l) => (!sMostrar.value || l.problema)
      && (!texto || `${l.paciente} ${l.id} ${l.accession} ${l.descricao} ${l.fonte}`.toLowerCase().includes(texto)));
    const chave = (l: Linha) => (ordenar === "situacao" ? String(ORDEM_SIT.indexOf(l.situacao)).padStart(2, "0") + l.data + l.hora
      : ordenar === "data" ? l.data + l.hora : String(l[ordenar] ?? "").toLowerCase());
    ls = [...ls].sort((a, b) => chave(a).localeCompare(chave(b), undefined, { numeric: true }));
    return inverso ? ls.reverse() : ls;
  };
  const selecionadas = (): Linha[] => (estado?.linhas || []).filter((l) => marcadas.has(l.k));

  const botoes = () => {
    const livre = !estado?.ocupado;
    const sel = selecionadas();
    bConferir.disabled = !livre || !dados.nos.length;
    bParar.disabled = livre;
    bFalta.disabled = !livre || !sel.some((l) => l.situacao === "incompleto" || l.situacao === "ausente");
    bInteiro.disabled = !livre || !sel.some((l) => l.situacao !== "erro");
    bFaltaPara.disabled = bInteiroPara.disabled = !livre || !dados.destinos.length || !sel.some((l) => l.situacao !== "erro");
    bReconferir.disabled = !livre || !sel.length;
    bCsv.disabled = !estado?.linhas.length;
    bProblemas.disabled = !estado?.linhas.some((l) => l.problema);
  };

  const desenhar = () => {
    if (!estado) return;
    const ls = visiveis();
    corpo.replaceChildren();
    for (const l of ls) {
      const caixa = el("input", { type: "checkbox", "aria-label": `${l.paciente} ${l.accession}` });
      caixa.checked = marcadas.has(l.k);
      caixa.onclick = (ev) => ev.stopPropagation();
      caixa.onchange = () => { if (caixa.checked) marcadas.add(l.k); else marcadas.delete(l.k); botoes(); };
      const tr0 = el("tr", { class: `sit-${l.situacao}`, "data-k": l.k, "data-acc": l.accession },
        el("td", {}, caixa),
        el("td", { class: "sit" }, `${SIMBOLO[l.situacao] || ""} ${l.texto}`), el("td", {}, l.fonte),
        el("td", {}, `${dataBr(l.data)} ${horaBr(l.hora)}`.trim()), el("td", {}, l.paciente), el("td", {}, l.id), el("td", {}, l.accession),
        el("td", {}, l.descricao), el("td", { class: "num" }, l.series_txt), el("td", { class: "num" }, l.imagens_txt),
        el("td", { class: "detalhe", title: l.detalhe }, l.detalhe), el("td", { class: "envio", title: l.envio }, l.envio));
      tr0.onclick = () => { if (abertas.has(l.k)) abertas.delete(l.k); else abertas.add(l.k); desenhar(); };
      corpo.append(tr0);
      if (abertas.has(l.k) && l.series.length) {
        const sub = el("table", { class: "gestao-series" },
          el("thead", {}, el("tr", {}, ...["Série", "Descrição", "Modalidade", "Imagens na origem", "Imagens no PACS", "Situação", "Faltam"].map((t) => el("th", {}, tr(t))))),
          el("tbody", {}, ...l.series.map((s) => el("tr", { class: `ser-${s.situacao}` }, el("td", {}, String(s.numero ?? "")), el("td", {}, s.descricao),
            el("td", {}, s.modalidade), el("td", { class: "num" }, s.origem == null ? "?" : String(s.origem)),
            el("td", { class: "num" }, s.pacs == null ? "—" : String(s.pacs)), el("td", {}, s.texto),
            el("td", { class: "num" }, s.faltam ? String(s.faltam) : "")))));
        corpo.append(el("tr", { class: "sub" }, el("td", {}), el("td", { colspan: String(COLUNAS.length) }, sub)));
      }
    }
    kTodos.checked = !!ls.length && ls.every((l) => marcadas.has(l.k));
    const quando = estado.quando ? ` — ${dataBr(estado.periodo[0])}${estado.periodo[1] !== estado.periodo[0] ? `–${dataBr(estado.periodo[1])}` : ""} · ${estado.pacs} · ${estado.quem}, ${estado.quando}` : "";
    resumo.textContent = estado.resumo ? `${estado.resumo}${quando}` : tr("Escolha as modalidades e o PACS e clique em Conferir.");
    erros.hidden = !estado.erros;
    erros.textContent = estado.erros;
    barra.hidden = !estado.ocupado;
    barra.removeAttribute("value");
    if (estado.total) barra.value = Math.round((100 * estado.feitos) / estado.total);
    mensagem.textContent = estado.mensagem;
    // a fila
    quadroFila.hidden = !estado.fila.length;
    corpoFila.replaceChildren(...estado.fila.map((f) => el("tr", { class: `fila-${f.estado}` },
      el("td", {}, `${FILA[f.estado]?.[0] || ""} ${tr(FILA[f.estado]?.[1] || f.estado)}`), el("td", {}, f.paciente), el("td", {}, f.accession),
      el("td", {}, f.destino), el("td", {}, f.modo), el("td", {}, f.hora), el("td", { title: f.resultado }, f.resultado))));
    const n = (e: string) => estado!.fila.filter((f) => f.estado === e).length;
    resumoFila.textContent = [n("fila") + n("enviando") ? `${n("fila") + n("enviando")} ${tr("na fila")}` : "",
      n("ok") + n("nada") ? `${n("ok") + n("nada")} ${tr("enviado(s)")}` : "", n("falhou") ? `${n("falhou")} ${tr("com falha")}` : ""].filter(Boolean).join(" · ");
    botoes();
  };

  let relogio = 0;
  const receber = (e: Estado) => {
    if (e.igual) return;
    estado = e;
    for (const k of [...marcadas]) if (!e.linhas.some((l) => l.k === k)) marcadas.delete(k);
    desenhar();
  };
  const atualizar = async () => {
    clearTimeout(relogio);
    if (!raiz.isConnected) return;
    try {
      receber(await pedirJson<Estado>(`/api/web/gestao/estado${estado ? `?v=${estado.v}` : ""}`));
      aviso.textContent = "";
    } catch (e) {
      aviso.textContent = `${tr("Sem resposta do servidor")}: ${(e as Error).message}`;
    }
    relogio = window.setTimeout(() => void atualizar(), estado?.ocupado ? 800 : 4000);
  };
  const pedirAcao = async (acao: string, corpoPedido: unknown) => {
    aviso.textContent = "";
    try {
      receber(await pedirJson<Estado>(`/api/web/gestao/${acao}`, corpoPedido));
    } catch (e) {
      aviso.textContent = tr((e as Error).message);
    }
    void atualizar();
  };

  bConferir.onclick = () => {
    marcadas.clear();
    abertas.clear();
    void pedirAcao("conferir", {
      fontes: fontes.map((f) => ({ no: f.no.id, ident: Number(f.ident.value) || null, on: f.caixa.checked })),
      pacs: sPacs.value ? { no: Number(sPacs.value), ident: Number(sPacsIdent.value) || null } : null,
      destino: eDestino.value.trim(), modo: sModo.value, periodo: sPeriodo.value,
      de: dDe.value.replace(/-/g, ""), ate: dAte.value.replace(/-/g, ""), ignorar: eIgnorar.value.trim(),
      exato: kExato.checked, so_problemas: !!sMostrar.value,
    });
  };
  bParar.onclick = () => void pedirAcao("parar", {});
  const enviar = (inteiro: boolean, para?: { no: number; ident: number | null; nome: string }) => {
    const sel = selecionadas().filter((l) => l.situacao !== "erro" && (para || inteiro || l.situacao === "incompleto" || l.situacao === "ausente"));
    if (!sel.length || !estado) return;
    const alvo = para?.nome || estado.pacs;
    const modo = dados.modos.find((m) => m.k === sModo.value)?.nome || "";
    let texto = `${tr("Enviar")} ${sel.length} ${tr("exame(s) para")} ${alvo}?\n\n${tr(inteiro ? "Exame inteiro" : "Só o que falta")} · ${tr(modo)}`;
    if (!para) texto += `\n${tr("Destino do C-MOVE")}: ${eDestino.value.trim() || eDestino.placeholder}`;
    const outro = sel.filter((l) => l.situacao === "outro_uid").length;
    if (outro) texto += `\n\n${tr("Atenção")}: ${outro} ${tr("exame(s) já estão no PACS com outro Study UID. Mandar cria um segundo exame do mesmo paciente no PACS.")}`;
    if (!window.confirm(texto)) return;
    void pedirAcao("enviar", { chaves: sel.map((l) => l.k), inteiro, modo: sModo.value, destino: eDestino.value.trim(),
      ...(para ? { para: { no: para.no, ident: para.ident } } : {}) });
  };
  bFalta.onclick = () => enviar(false);
  bInteiro.onclick = () => enviar(true);
  const menuDestinos = (botao: HTMLElement, inteiro: boolean) => {
    const itens: ItemMenu[] = dados.destinos.map((d) => (d.identidades.length
      ? { rotulo: d.nome, sub: [{ rotulo: tr("como este servidor"), acao: () => enviar(inteiro, { no: d.id, ident: null, nome: d.nome }) },
        ...d.identidades.map((i) => ({ rotulo: `${tr("como")} ${i.nome} (${i.ae})`, acao: () => enviar(inteiro, { no: d.id, ident: i.id, nome: d.nome }) }))] }
      : { rotulo: d.nome, acao: () => enviar(inteiro, { no: d.id, ident: null, nome: d.nome }) }));
    abrirMenu(itens, 0, 0, tr("Destinos de envio"), botao);
  };
  bFaltaPara.onclick = () => menuDestinos(bFaltaPara, false);
  bInteiroPara.onclick = () => menuDestinos(bInteiroPara, true);
  bReconferir.onclick = () => void pedirAcao("reconferir", { chaves: selecionadas().map((l) => l.k) });
  bLimpar.onclick = () => void pedirAcao("limpar_fila", {});
  bProblemas.onclick = () => {
    marcadas.clear();
    for (const l of visiveis()) if (l.problema) marcadas.add(l.k);
    desenhar();
  };
  kTodos.onchange = () => {
    for (const l of visiveis()) { if (kTodos.checked) marcadas.add(l.k); else marcadas.delete(l.k); }
    desenhar();
  };
  sMostrar.onchange = desenhar;
  eBusca.oninput = desenhar;
  bCsv.onclick = () => {
    const blob = new Blob(["﻿", csvDaGestao(visiveis())], { type: "text/csv;charset=utf-8" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `gestao-dicom-${new Date().toISOString().slice(0, 10)}.csv` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };

  // 0.100.65: duas abas, como na janela do Ipê de mesa — "Conferir agora" e "Automático" (as regras)
  const abaConferir = el("div", { class: "gestao-aba" }, quadroCfg, aviso, el("div", { class: "gestao-barra" }, resumo, sMostrar, eBusca), erros, acoes,
    el("div", { class: "gestao-rolagem" }, tabela), quadroFila);
  const abaAuto = painelAutomatico(dados, () => raiz.isConnected);
  abaAuto.el.hidden = true;
  const bAba1 = el("button", { type: "button", role: "tab", "aria-selected": "true" }, tr("Conferir agora"));
  const bAba2 = el("button", { type: "button", role: "tab", "aria-selected": "false" }, tr("Automático"));
  const escolherAba = (auto: boolean) => {
    abaConferir.hidden = auto;
    abaAuto.el.hidden = !auto;
    bAba1.setAttribute("aria-selected", String(!auto));
    bAba2.setAttribute("aria-selected", String(auto));
    if (auto) abaAuto.mostrar();
  };
  bAba1.onclick = () => escolherAba(false);
  bAba2.onclick = () => escolherAba(true);
  raiz.append(el("h2", {}, tr("Gestão DICOM — exames das modalidades no PACS")),
    el("div", { class: "dica" }, tr("Quem fala com as modalidades e com o PACS é o servidor; a conferência e o envio continuam com esta página fechada.")),
    el("div", { class: "abas gestao-abas", role: "tablist" }, bAba1, bAba2), abaConferir, abaAuto.el);
  (window as unknown as { __ipeGestao?: unknown }).__ipeGestao = { estado: () => estado, marcadas: () => [...marcadas], csv: () => csvDaGestao(visiveis()) };
  // a primeira leitura depois de a tela entrar na página (a atualização confere `isConnected`)
  setTimeout(() => void atualizar(), 0);
  return raiz;
}

// ------------------------------------------------------------------ 0.100.65: a aba Automático (as regras)
interface CfgRegra {
  fontes: { node_id: number; identity_id: number | null }[]; destino: { node_id: number | null; identity_id: number | null };
  move_destination: string; modalidade: string; periodo: string; ignorar: string; exato: boolean; envio: string; modo: string;
  schedule: { type: string; minutes?: number; from?: string; to?: string; at?: string; weekdays: number[] };
  repetir: { minutos: number; vezes: number };
}
interface ItemRel { paciente: string; accession: string; fonte: string; mensagem: string }
interface Relatorio {
  inicio_txt: string; resumo: string; situacao: string; destino_offline: boolean; erro: string;
  enviados: ItemRel[]; falhas: ItemRel[]; outro_uid: ItemRel[]; offline: string[];
}
interface Regra {
  id: number; nome: string; ativa: boolean; quando: string; destino: string; mandar: string; ultima: string; situacao: string;
  simbolo: string; texto: string; rodando: boolean; proxima: string; cfg: CfgRegra; ultimo: Relatorio | null;
}
interface Regras {
  regras: Regra[]; historico: { quando: string; regra: string; situacao: string; estado: string; mensagem: string }[];
  motor: boolean; padrao: CfgRegra; envios: Record<string, string>; dias: string[]; id?: number;
}

/** "a cada 30 min, 07:00–20:00 (Seg a Sex)" no idioma da página. */
function descreverHorario(sch: CfgRegra["schedule"], nomes: string[]): string {
  const wd = [...new Set(sch.weekdays || [])].filter((d) => d >= 0 && d <= 6).sort((a, b) => a - b);
  const nome = (d: number) => tr(nomes[d] || String(d));
  let dias = "";
  if (wd.length && wd.length < 7) {
    const seguidos = wd.length > 2 && wd.every((d, i) => d === wd[0] + i);
    dias = seguidos ? ` (${nome(wd[0])} ${tr("a")} ${nome(wd[wd.length - 1])})` : ` (${wd.map(nome).join(", ")})`;
  }
  if (sch.type === "daily") return `${tr("diariamente às")} ${sch.at || "06:00"}${dias}`;
  return `${tr("a cada")} ${sch.minutes || 60} min, ${sch.from || "00:00"}–${sch.to || "23:59"}${dias}`;
}

function painelAutomatico(dados: Nos, naPagina: () => boolean): { el: HTMLElement; mostrar: () => void } {
  const raiz = el("div", { class: "gestao-aba gestao-auto" });
  const aviso = el("div", { class: "estado", role: "status" });
  const corpo = el("tbody");
  const tabela = el("table", { class: "lista gestao-regras" },
    el("thead", {}, el("tr", {}, ...["Ligada", "Regra", "Quando", "Destino", "Mandar", "Última", "Situação", "Próxima"].map((t) => el("th", {}, tr(t))))), corpo);
  const bNova = el("button", { type: "button", class: "primario" }, tr("Nova regra…"));
  const bEditar = el("button", { type: "button" }, tr("Editar…"));
  const bDuplicar = el("button", { type: "button" }, tr("Duplicar"));
  const bExcluir = el("button", { type: "button" }, tr("Excluir"));
  const bRodar = el("button", { type: "button" }, tr("Rodar agora"));
  const relatorio = el("div", { class: "gestao-relatorio" });
  const corpoHist = el("tbody");
  const editor = el("section", { class: "gestao-editor", hidden: "" });
  const lista = el("div", { class: "gestao-lista-regras" },
    el("div", { class: "dica" }, tr("As regras rodam sozinhas enquanto o servidor estiver ligado. Cada uma confere as modalidades no destino e manda o que não está completo. São as mesmas regras da janela de Gestão do Ipê.")),
    el("div", { class: "acoes" }, bNova, bEditar, bDuplicar, bExcluir, bRodar), aviso,
    el("div", { class: "gestao-rolagem" }, tabela),
    el("h3", {}, tr("Último relatório da regra")), relatorio,
    el("h3", {}, tr("Histórico")),
    el("div", { class: "gestao-rolagem" }, el("table", { class: "lista gestao-hist" },
      el("thead", {}, el("tr", {}, ...["Quando", "Regra", "Situação", "Resumo"].map((t) => el("th", {}, tr(t))))), corpoHist)));
  raiz.append(lista, editor);

  let rs: Regras | null = null;
  let escolhida = 0;
  let relogio = 0;
  const atual = (): Regra | undefined => rs?.regras.find((r) => r.id === escolhida);

  const grupo = (titulo: string, itens: (ItemRel | string)[], classe: string, detalhe?: (d: ItemRel) => string): HTMLElement => {
    const d = el("details", { class: `grupo ${classe}` }, el("summary", {}, `${tr(titulo)} (${itens.length})`));
    if (itens.length && titulo !== "Completados agora") d.setAttribute("open", "");
    for (const it of itens) {
      d.append(typeof it === "string" ? el("div", { class: "item" }, el("b", {}, it.split(":")[0]), " ", it)
        : el("div", { class: "item" }, el("b", {}, `${it.paciente}  ${it.accession}  (${it.fonte})`), " ", detalhe ? detalhe(it) : it.mensagem));
    }
    return d;
  };
  const desenhar = () => {
    if (!rs) return;
    if (!rs.regras.some((r) => r.id === escolhida)) escolhida = rs.regras[0]?.id || 0;
    corpo.replaceChildren(...rs.regras.map((r) => {
      const caixa = el("input", { type: "checkbox", "aria-label": `${tr("Ligada")}: ${r.nome}` });
      caixa.checked = r.ativa;
      caixa.onclick = (ev) => ev.stopPropagation();
      caixa.onchange = () => void pedirRegras("regra_ligar", { id: r.id, on: caixa.checked });
      const linha = el("tr", { class: `regra sit-${r.situacao}${r.id === escolhida ? " escolhida" : ""}`, "data-id": String(r.id) },
        el("td", {}, caixa), el("td", {}, r.nome), el("td", {}, descreverHorario(r.cfg.schedule, rs!.dias)), el("td", {}, r.destino), el("td", {}, r.mandar),
        el("td", {}, r.ultima), el("td", { class: "sit", title: r.texto }, `${r.simbolo} ${r.texto}`), el("td", {}, r.proxima));
      linha.onclick = () => { escolhida = r.id; desenhar(); };
      return linha;
    }));
    if (!rs.regras.length) corpo.append(el("tr", {}, el("td", { colspan: "8", class: "vazio" }, tr("Nenhuma regra. Clique em Nova regra…"))));
    const r = atual();
    bEditar.disabled = bDuplicar.disabled = bExcluir.disabled = !r;
    bRodar.disabled = !r || r.rodando || !rs.motor;
    bRodar.title = rs.motor ? "" : tr("Este servidor não tem a automação ligada.");
    relatorio.replaceChildren();
    if (r) {
      const u = r.ultimo;
      if (!u) relatorio.append(el("div", { class: "dica" }, tr("Ainda não rodou.")));
      else {
        relatorio.append(el("div", { class: "cab" }, `${u.inicio_txt} — ${u.resumo}`));
        if (u.destino_offline) relatorio.append(grupo("Destino fora do ar", [u.erro], "offline"));
        relatorio.append(grupo("Completados agora", u.enviados || [], "ok"), grupo("Com erro", u.falhas || [], "erro"),
          grupo("Modalidades fora do ar", u.offline || [], "offline"),
          grupo("Mesmo accession com outro Study UID (não enviados)", u.outro_uid || [], "", () => tr("confira no destino antes de mandar")));
      }
    }
    corpoHist.replaceChildren(...rs.historico.map((h) => el("tr", { class: `hist-${h.estado}` }, el("td", {}, h.quando), el("td", {}, h.regra),
      el("td", {}, h.situacao), el("td", { title: h.mensagem }, h.mensagem))));
  };
  const receber = (r: Regras) => { rs = r; if (r.id) escolhida = r.id; desenhar(); };
  const atualizar = async () => {
    clearTimeout(relogio);
    if (!naPagina() || raiz.hidden) return;
    if (editor.hidden) {
      try { receber(await pedirJson<Regras>("/api/web/gestao/regras")); } catch (e) { aviso.textContent = tr((e as Error).message); }
    }
    relogio = window.setTimeout(() => void atualizar(), rs?.regras.some((r) => r.rodando) ? 1200 : 5000);
  };
  const pedirRegras = async (acao: string, corpoPedido: unknown): Promise<boolean> => {
    aviso.textContent = "";
    try {
      receber(await pedirJson<Regras>(`/api/web/gestao/${acao}`, corpoPedido));
      return true;
    } catch (e) {
      aviso.textContent = tr((e as Error).message);
      return false;
    }
  };

  // ---------------------------------------------------------------- o editor da regra
  const abrirEditor = (regra: Regra | null) => {
    if (!rs) return;
    const cfg: CfgRegra = JSON.parse(JSON.stringify(regra?.cfg || rs.padrao));
    const erro = el("div", { class: "erro", role: "alert" });
    const eNome = el("input", { "aria-label": tr("Nome da regra"), placeholder: tr("ex.: RM no PACS") });
    eNome.value = regra?.nome || "";
    const kAtiva = el("input", { type: "checkbox", id: "regra-ativa" });
    kAtiva.checked = regra ? regra.ativa : true;
    const idents = (no: { identidades: Ident[] } | undefined, v: number | null | undefined, rotulo: string): HTMLSelectElement => {
      const sel = el("select", { "aria-label": tr(rotulo) }, el("option", { value: "" }, `${tr("Este servidor")} (${dados.local_ae})`),
        ...(no?.identidades || []).map((i) => el("option", { value: String(i.id) }, `${i.nome} (${i.ae})`)));
      if (v && [...sel.options].some((o) => o.value === String(v))) sel.value = String(v);
      return sel;
    };
    const fontes = dados.nos.map((no) => {
      const mem = cfg.fontes.find((f) => f.node_id === no.id);
      const caixa = el("input", { type: "checkbox", "aria-label": no.nome });
      caixa.checked = !!mem;
      return { no, caixa, ident: idents(no, mem?.identity_id, "Falar como") };
    });
    const tFontes = el("table", { class: "lista gestao-fontes" },
      el("thead", {}, el("tr", {}, ...["", "Modalidade", "AE Title", "Falar como"].map((t) => el("th", {}, t ? tr(t) : "")))),
      el("tbody", {}, ...fontes.map((f) => el("tr", { "data-no": String(f.no.id) }, el("td", {}, f.caixa), el("td", {}, f.no.nome),
        el("td", {}, `${f.no.ae}@${f.no.host}`), el("td", {}, f.ident)))));
    const sDestino = el("select", { "aria-label": tr("Destino") }, el("option", { value: "" }, "—"),
      ...dados.nos.map((n) => el("option", { value: String(n.id) }, `${n.nome}  (${n.ae}@${n.host})`)));
    sDestino.value = cfg.destino.node_id ? String(cfg.destino.node_id) : "";
    const caixaComo = el("span", {});
    let sComo = idents(undefined, null, "Enviar como");
    const eMove = el("input", { "aria-label": tr("Destino do C-MOVE") });
    eMove.value = cfg.move_destination || "";
    const destinoMudou = (v?: number | null) => {
      const no = dados.nos.find((n) => String(n.id) === sDestino.value);
      sComo = idents(no, v === undefined ? Number(sComo.value) || null : v, "Enviar como");
      caixaComo.replaceChildren(sComo);
      eMove.placeholder = no?.ae || "";
    };
    sDestino.onchange = () => destinoMudou();
    destinoMudou(cfg.destino.identity_id);
    const radio = (nome: string, valor: string, marcado: boolean, rotulo: string): [HTMLInputElement, HTMLElement] => {
      const r = el("input", { type: "radio", name: nome, value: valor });
      r.checked = marcado;
      return [r, el("label", { class: "opcao" }, r, " ", tr(rotulo))];
    };
    const [rFalta, lFalta] = radio("regra-envio", "falta", cfg.envio !== "inteiro", rs.envios.falta || "Só o que falta");
    const [rInteiro, lInteiro] = radio("regra-envio", "inteiro", cfg.envio === "inteiro", rs.envios.inteiro || "O exame inteiro");
    void rFalta;
    const sModo = el("select", { "aria-label": tr("Como enviar") }, ...dados.modos.map((m) => el("option", { value: m.k }, tr(m.nome))));
    sModo.value = cfg.modo || "auto";
    const sPeriodo = el("select", { "aria-label": tr("Período") }, ...dados.periodos.filter((p) => p.k !== "datas").map((p) => el("option", { value: p.k }, tr(p.nome))));
    sPeriodo.value = cfg.periodo || "hoje";
    const eModalidade = el("input", { "aria-label": tr("Só a modalidade"), placeholder: tr("todas"), size: "6" });
    eModalidade.value = cfg.modalidade || "";
    const eIgnorar = el("input", { "aria-label": tr("Ignorar séries"), placeholder: tr("ex.: Patient Protocol; ScreenCap") });
    eIgnorar.value = cfg.ignorar || "";
    const kExato = el("input", { type: "checkbox", id: "regra-exato" });
    kExato.checked = !!cfg.exato;
    const diario = cfg.schedule.type === "daily";
    const [rIntervalo, lIntervalo] = radio("regra-horario", "interval", !diario, "A cada");
    const [rDiario, lDiario] = radio("regra-horario", "daily", diario, "Todo dia às");
    void rIntervalo;
    const nMin = el("input", { type: "number", min: "5", max: "1440", "aria-label": tr("Minutos"), value: String(cfg.schedule.minutes || 60) });
    const hDe = el("input", { type: "time", "aria-label": tr("Das"), value: cfg.schedule.from || "07:00" });
    const hAte = el("input", { type: "time", "aria-label": tr("Até as"), value: cfg.schedule.to || "20:00" });
    const hAs = el("input", { type: "time", "aria-label": tr("Hora"), value: cfg.schedule.at || "06:00" });
    const dias = rs.dias.map((nome, i) => {
      const k = el("input", { type: "checkbox", "aria-label": tr(nome) });
      k.checked = (cfg.schedule.weekdays || []).includes(i);
      return { k, rot: el("label", { class: "opcao" }, k, " ", tr(nome)) };
    });
    const kRepetir = el("input", { type: "checkbox", id: "regra-repetir" });
    kRepetir.checked = (cfg.repetir?.vezes || 0) > 0;
    const nRepMin = el("input", { type: "number", min: "1", max: "720", "aria-label": tr("Minutos até tentar de novo"), value: String(cfg.repetir?.minutos || 15) });
    const nRepVezes = el("input", { type: "number", min: "1", max: "20", "aria-label": tr("Quantas vezes"), value: String(Math.max(1, cfg.repetir?.vezes || 3)) });
    const campo = (rotulo: string, ...c: (Node | string)[]) => el("div", { class: "campo" }, el("span", {}, rotulo ? tr(rotulo) : ""), ...c);
    const bSalvar = el("button", { type: "button", class: "primario" }, tr("Salvar a regra"));
    const bCancelar = el("button", { type: "button" }, tr("Cancelar"));
    const fechar = () => { editor.hidden = true; lista.hidden = false; editor.replaceChildren(); void atualizar(); };
    bCancelar.onclick = fechar;
    bSalvar.onclick = async () => {
      const nova: CfgRegra = {
        fontes: fontes.filter((f) => f.caixa.checked).map((f) => ({ node_id: f.no.id, identity_id: Number(f.ident.value) || null })),
        destino: { node_id: Number(sDestino.value) || null, identity_id: Number(sComo.value) || null },
        move_destination: eMove.value.trim(), modalidade: eModalidade.value.trim().toUpperCase(), periodo: sPeriodo.value,
        ignorar: eIgnorar.value.trim(), exato: kExato.checked, envio: rInteiro.checked ? "inteiro" : "falta", modo: sModo.value,
        schedule: rDiario.checked ? { type: "daily", at: hAs.value, weekdays: dias.flatMap((d, i) => (d.k.checked ? [i] : [])) }
          : { type: "interval", minutes: Number(nMin.value) || 60, from: hDe.value, to: hAte.value, weekdays: dias.flatMap((d, i) => (d.k.checked ? [i] : [])) },
        repetir: { minutos: Number(nRepMin.value) || 15, vezes: kRepetir.checked ? Number(nRepVezes.value) || 3 : 0 },
      };
      erro.textContent = "";
      try {
        receber(await pedirJson<Regras>("/api/web/gestao/regra", { id: regra?.id, nome: eNome.value.trim(), ativa: kAtiva.checked, cfg: nova }));
        fechar();
      } catch (e) {
        erro.textContent = tr((e as Error).message);
      }
    };
    editor.replaceChildren(
      el("h3", {}, tr(regra ? "Editar a regra" : "Nova regra")),
      campo("Nome", eNome, el("label", { class: "opcao", for: "regra-ativa" }, kAtiva, " ", tr("Ligada"))),
      el("div", { class: "gestao-cfg" },
        el("section", {}, el("h3", {}, tr("Modalidades")), tFontes),
        el("section", {}, el("h3", {}, tr("Destino e envio")),
          campo("Destino", sDestino), campo("Enviar como", caixaComo), campo("Destino do C-MOVE", eMove),
          campo("Mandar", lFalta, lInteiro), campo("Como enviar", sModo))),
      el("div", { class: "gestao-cfg" },
        el("section", {}, el("h3", {}, tr("O que conferir")),
          campo("Período", sPeriodo, el("span", { class: "rot" }, tr("Só a modalidade")), eModalidade), campo("Ignorar séries", eIgnorar),
          campo("", el("label", { class: "opcao", for: "regra-exato" }, kExato, " ", tr("Conferir imagem por imagem (mais lento)")))),
        el("section", {}, el("h3", {}, tr("Quando")),
          campo("", lIntervalo, nMin, tr("min, das"), hDe, tr("às"), hAte), campo("", lDiario, hAs),
          campo("Dias", ...dias.map((d) => d.rot)),
          campo("", el("label", { class: "opcao", for: "regra-repetir" }, kRepetir, " ", tr("Se der erro ou algum nó estiver fora do ar, tentar de novo em")),
            nRepMin, tr("min, até"), nRepVezes, tr("vezes")))),
      erro, el("div", { class: "acoes" }, bSalvar, bCancelar));
    lista.hidden = true;
    editor.hidden = false;
    eNome.focus();
  };

  bNova.onclick = () => abrirEditor(null);
  bEditar.onclick = () => { const r = atual(); if (r) abrirEditor(r); };
  bDuplicar.onclick = () => { const r = atual(); if (r) void pedirRegras("regra_duplicar", { id: r.id }); };
  bExcluir.onclick = () => {
    const r = atual();
    if (r && window.confirm(`${tr("Excluir a regra")} “${r.nome}”?`)) void pedirRegras("regra_excluir", { id: r.id });
  };
  bRodar.onclick = () => { const r = atual(); if (r) void pedirRegras("regra_rodar", { id: r.id }).then(() => void atualizar()); };
  (window as unknown as { __ipeGestaoAuto?: unknown }).__ipeGestaoAuto = { regras: () => rs };
  return { el: raiz, mostrar: () => void atualizar() };
}
