// 0.100.63: a Gestão DICOM no Ipê Web — os exames das modalidades estão no PACS? Inteiros? Se não, mandar.
// É a janela de Gestão do Ipê de mesa, atendida pelo servidor: quem fala com as modalidades e com o PACS é o
// servidor; a conferência e o envio seguem com esta aba fechada. Só administradores. Os nós são todos os do
// servidor (aqui não vale o "compartilhar com os clientes").
import { pedir } from "./api";
import { tr } from "./i18n";
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
        el("td", { class: "sit" }, `${SIMBOLO[l.situacao] || ""} ${tr(l.texto)}`), el("td", {}, l.fonte),
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
            el("td", { class: "num" }, s.pacs == null ? "—" : String(s.pacs)), el("td", {}, tr(s.texto)),
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

  raiz.append(el("h2", {}, tr("Gestão DICOM — exames das modalidades no PACS")),
    el("div", { class: "dica" }, tr("Quem fala com as modalidades e com o PACS é o servidor; a conferência e o envio continuam com esta página fechada.")),
    quadroCfg, aviso, el("div", { class: "gestao-barra" }, resumo, sMostrar, eBusca), erros, acoes,
    el("div", { class: "gestao-rolagem" }, tabela), quadroFila);
  (window as unknown as { __ipeGestao?: unknown }).__ipeGestao = { estado: () => estado, marcadas: () => [...marcadas], csv: () => csvDaGestao(visiveis()) };
  // a primeira leitura depois de a tela entrar na página (a atualização confere `isConnected`)
  setTimeout(() => void atualizar(), 0);
  return raiz;
}
