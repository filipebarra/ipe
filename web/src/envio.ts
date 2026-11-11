// 0.100.9: enviar do navegador para um destino DICOM (PACS) — o exame, séries ou a imagem do quadro ativo — pela
// fila de envios do servidor (a mesma do Ipê), e acompanhar o andamento. Só aparece para quem tem a permissão de
// enviar. Pode ir junto o que se fez aqui: as medidas viram um GSPS e as imagens-chave um KO.
import { cabecalhos } from "./api";
import { tr } from "./i18n";

export interface Destino {
  id: number;
  nome: string;
  ae: string;
  host: string;
  porta: number;
  identidades: { id: number; nome: string; ae: string }[];
}

export interface Envio {
  id: number;
  rotulo: string;
  destino: string;
  estado: "waiting" | "running" | "done" | "error" | "cancelled";
  feitas: number;
  total: number;
  mensagem: string;
}

export interface SerieParaEnvio { uid: string; rotulo: string }

async function pedirJson(caminho: string, corpo?: unknown): Promise<unknown> {
  const r = await fetch(`${location.origin}${caminho}`, {
    method: corpo === undefined ? "GET" : "POST", cache: "no-store",
    headers: { ...cabecalhos(), ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.text()) || msg; } catch { /* sem corpo */ }
    throw new Error(msg);
  }
  return r.json();
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...filhos: (Node | string)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

const ESTADOS: Record<Envio["estado"], string> = {
  waiting: "Na fila", running: "Enviando", done: "Enviado", error: "Erro", cancelled: "Cancelado",
};

/** A lista de envios desta pessoa, que se atualiza sozinha enquanto houver envio andando. */
export class ListaEnvios {
  raiz = el("div", { class: "envios" });
  private relogio = 0;
  aoMudar: (ativos: number, total: number) => void = () => {};

  async atualizar(): Promise<Envio[]> {
    let lista: Envio[] = [];
    try {
      lista = ((await pedirJson("/api/web/envios")) as { envios: Envio[] }).envios;
    } catch { /* sem rede agora: tenta de novo */ }
    this.desenhar(lista);
    const ativos = lista.filter((e) => e.estado === "waiting" || e.estado === "running").length;
    this.aoMudar(ativos, lista.length);
    clearTimeout(this.relogio);
    if (ativos) this.relogio = window.setTimeout(() => void this.atualizar(), 1000);
    return lista;
  }

  private desenhar(lista: Envio[]): void {
    if (!lista.length) {
      this.raiz.replaceChildren(el("div", { class: "dica" }, tr("Nenhum envio ainda.")));
      return;
    }
    this.raiz.replaceChildren(...lista.map((e) => {
      const pct = e.total ? Math.round((100 * e.feitas) / e.total) : (e.estado === "done" ? 100 : 0);
      const barra = el("progress", { max: "100", value: String(pct) });
      const linha = el("div", { class: `envio ${e.estado}`, "data-id": String(e.id) },
        el("div", { class: "envio-titulo" }, `${e.rotulo} → ${e.destino}`),
        el("div", { class: "envio-estado" }, `${tr(ESTADOS[e.estado] || e.estado)}${e.total ? ` · ${e.feitas}/${e.total}` : ""}` +
          `${e.mensagem && e.estado !== "running" ? ` · ${e.mensagem}` : ""}`),
        barra);
      if (e.estado === "waiting" || e.estado === "running") {
        const b = el("button", { type: "button", class: "link" }, tr("Cancelar"));
        b.onclick = () => { void pedirJson("/api/web/envios/cancelar", { id: e.id }).then(() => this.atualizar()); };
        linha.append(b);
      }
      return linha;
    }));
  }
}

/** O painel de enviar: o que, para onde, e se vão junto as medidas (GSPS) e as imagens-chave (KO). */
export async function painelEnvio(study: string, series: SerieParaEnvio[], serieAtual: string | null,
  sopAtual: string | null, lista: ListaEnvios, fechar: () => void): Promise<HTMLElement> {
  const raiz = el("div", { class: "painel-envio" });
  let destinos: Destino[] = [];
  try {
    destinos = ((await pedirJson("/api/web/destinos")) as { destinos: Destino[] }).destinos;
  } catch (e) {
    raiz.append(el("div", { class: "erro" }, `${tr("Não consegui ler os destinos")}: ${(e as Error).message}`));
    return raiz;
  }
  if (!destinos.length) {
    raiz.append(el("div", { class: "dica" }, tr("Nenhum destino DICOM ativo no servidor.")));
    return raiz;
  }
  const nome = "o-que-" + Math.random().toString(36).slice(2, 7);
  const opcao = (valor: string, rotulo: string, marcado = false, desligado = false) => {
    const r = el("input", { type: "radio", name: nome, value: valor });
    r.checked = marcado;
    r.disabled = desligado;
    return { r, label: el("label", {}, r, ` ${tr(rotulo)}`) };
  };
  const oExame = opcao("exame", "O exame inteiro", !serieAtual);
  const asSeries = opcao("series", "Estas séries", !!serieAtual);
  const aImagem = opcao("imagem", "A imagem do quadro ativo", false, !sopAtual || !serieAtual);
  const caixas = el("div", { class: "lista-series-envio" });
  const marcadas = new Map<string, HTMLInputElement>();
  for (const s of series) {
    const c = el("input", { type: "checkbox", value: s.uid });
    c.checked = s.uid === serieAtual;
    c.onchange = () => { asSeries.r.checked = true; };
    marcadas.set(s.uid, c);
    caixas.append(el("label", {}, c, ` ${s.rotulo}`));
  }
  const sDestino = el("select", { "aria-label": tr("Destino") });
  for (const d of destinos) sDestino.append(el("option", { value: String(d.id) }, `${d.nome} (${d.ae}${d.host ? ` · ${d.host}` : ""})`));
  const sIdent = el("select", { "aria-label": tr("Identidade") });
  const rotIdent = el("label", {}, `${tr("Como")} `, sIdent);
  const trocarDestino = () => {
    const d = destinos.find((x) => String(x.id) === sDestino.value);
    sIdent.replaceChildren(el("option", { value: "" }, tr("AE do servidor")),
      ...(d?.identidades || []).map((i) => el("option", { value: String(i.id) }, `${i.nome} (${i.ae})`)));
    rotIdent.hidden = !d?.identidades.length;
  };
  sDestino.onchange = trocarDestino;
  trocarDestino();
  const cObjetos = el("input", { type: "checkbox" });
  cObjetos.checked = true;
  const nota = el("div", { class: "nota" });
  const bEnviar = el("button", { type: "button", class: "primario" }, tr("Enviar"));
  bEnviar.onclick = async () => {
    const corpo: Record<string, unknown> = { study, destino: Number(sDestino.value), objetos: cObjetos.checked };
    if (sIdent.value) corpo.identidade = Number(sIdent.value);
    if (asSeries.r.checked) {
      const escolhidas = [...marcadas.entries()].filter(([, c]) => c.checked).map(([u]) => u);
      if (!escolhidas.length) { nota.textContent = tr("Marque ao menos uma série."); return; }
      corpo.series = escolhidas;
    } else if (aImagem.r.checked && serieAtual && sopAtual) {
      corpo.series = [serieAtual];
      corpo.sops = [sopAtual];
    }
    bEnviar.disabled = true;
    nota.textContent = tr("Pondo na fila…");
    try {
      await pedirJson("/api/web/enviar", corpo);
      nota.textContent = "";
      fechar();
      await lista.atualizar();
    } catch (e) {
      nota.textContent = `${tr("Não foi possível enviar")}: ${(e as Error).message}`;
      bEnviar.disabled = false;
    }
  };
  raiz.append(
    el("div", { class: "titulo-painel" }, tr("Enviar a um destino DICOM")),
    el("fieldset", {}, el("legend", {}, tr("O que")), oExame.label, asSeries.label, caixas, aImagem.label),
    el("label", {}, `${tr("Para")} `, sDestino), rotIdent,
    el("label", { title: tr("As medidas feitas no exame viram um GSPS e as imagens-chave um KO, gravados no exame e mandados juntos") },
      cObjetos, ` ${tr("Junto: as medidas (GSPS) e as imagens-chave (KO)")}`),
    el("div", { class: "acoes" }, bEnviar), nota);
  return raiz;
}
